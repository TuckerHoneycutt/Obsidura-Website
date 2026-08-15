"""Normalize an uploaded file into kernel-value shape (ingest.result@1).

Routing lives here as ordinary computation, not in YAML — v0 has no
declared-choice routing, and a media_type switch inside one adapter task is
the honest place for it.
"""

import base64
import csv
import io
import json

from _compat import blob_get, blob_put, record, requester, sha256_hex, value_in

INLINE_RECORD_CAP = 64 * 1024  # spec §6: values small, everything big by handle

TABULAR = {"text/csv", "application/csv"}
SPREADSHEET = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}
DOCUMENT = {"application/pdf", "text/plain", "text/markdown"}


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    if payload.get("content_b64"):
        data = base64.b64decode(payload["content_b64"])
    elif payload.get("blob_sha256"):
        data = blob_get(ctx, f"uploads/{payload['blob_sha256']}")
    else:
        raise ValueError("upload carries neither content_b64 nor blob_sha256")

    media_type = payload["media_type"]
    # Spreadsheets normalize to CSV up front so every downstream step — the
    # profile, the catalog, the answer agent — sees one tabular shape. If the
    # workbook can't be read (or openpyxl is absent) it falls through to the
    # document branch and is at least stored and catalogued.
    sheet_note = ""
    if media_type in SPREADSHEET or payload["filename"].lower().endswith(
            (".xlsx", ".xlsm")):
        converted = _xlsx_to_csv(data)
        if converted is not None:
            data, sheet = converted
            media_type = "text/csv"
            sheet_note = f" (sheet '{sheet}')"
    digest = sha256_hex(data)
    result = {
        "source_filename": payload["filename"],
        "media_type": media_type,
        "sha256": digest,
        "requester": requester(ctx, payload),
    }

    if media_type in TABULAR:
        key = f"ingest/tables/{digest}.csv"
        blob_put(ctx, key, data)
        columns, rows = _profile_csv(data)
        result["kind"] = "table"
        result["table"] = {"row_source_key": key, "rows": rows, "columns": columns}
        result["summary"] = (
            f"Table from {payload['filename']}{sheet_note}: {rows} rows, "
            f"columns {', '.join(c['name'] for c in columns[:12])}"
        )
    elif media_type == "application/json" and len(data) <= INLINE_RECORD_CAP:
        parsed = json.loads(data)
        if not isinstance(parsed, dict):
            parsed = {"items": parsed}
        result["kind"] = "data"
        result["record"] = parsed
        result["summary"] = (
            f"Structured data from {payload['filename']}: "
            f"top-level keys {', '.join(list(parsed)[:12])}"
        )
    elif media_type.startswith("image/"):
        key = f"ingest/images/{digest}"
        blob_put(ctx, key, data)
        result["kind"] = "image"
        result["file"] = {"blob_key": key, "media_type": media_type}
        result["summary"] = f"Image {payload['filename']} ({len(data)} bytes)"
    else:
        # Documents and anything unrecognized: store as a File; understanding
        # the format is a downstream action's job (mdzip principle). PDF text
        # extraction is a follow-up once a pdf lib is in the runner image.
        key = f"ingest/docs/{digest}"
        blob_put(ctx, key, data)
        result["kind"] = "document"
        result["file"] = {"blob_key": key, "media_type": media_type}
        note = payload.get("note")
        result["summary"] = f"Document {payload['filename']} ({len(data)} bytes)" + (
            f" — {note}" if note else ""
        )

    return record("ingest.result@1", result)


def _xlsx_to_csv(data: bytes):
    """First worksheet as CSV bytes plus the sheet name, or None if the
    bytes aren't a readable workbook."""
    try:
        import openpyxl
    except ImportError:
        return None
    try:
        book = openpyxl.load_workbook(
            io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        return None
    try:
        sheet = book.worksheets[0]
        out = io.StringIO()
        writer = csv.writer(out)
        for row in sheet.iter_rows(values_only=True):
            writer.writerow(["" if cell is None else cell for cell in row])
        return out.getvalue().encode("utf-8"), sheet.title
    finally:
        book.close()


def _profile_csv(data: bytes):
    """Header + row count + cheap dtype sniff from a sample of rows."""
    text = data.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    header = next(reader, [])
    sample, rows = [], 0
    for row in reader:
        rows += 1
        if len(sample) < 100:
            sample.append(row)
    columns = []
    for i, name in enumerate(header):
        values = [r[i] for r in sample if i < len(r) and r[i] != ""]
        columns.append({"name": name.strip() or f"col_{i}", "dtype": _sniff(values)})
    return columns, rows


def _sniff(values) -> str:
    if not values:
        return "unknown"
    if all(_is_int(v) for v in values):
        return "int"
    if all(_is_float(v) for v in values):
        return "float"
    if all(v.lower() in ("true", "false") for v in values):
        return "bool"
    if all(_looks_like_timestamp(v) for v in values):
        return "timestamp"
    return "text"


def _is_int(v: str) -> bool:
    try:
        int(v)
        return True
    except ValueError:
        return False


def _is_float(v: str) -> bool:
    try:
        float(v)
        return True
    except ValueError:
        return False


def _looks_like_timestamp(v: str) -> bool:
    return len(v) >= 8 and v[:4].isdigit() and ("-" in v or "/" in v or ":" in v)
