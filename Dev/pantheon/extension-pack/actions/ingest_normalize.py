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
        columns, rows, quality = _profile_csv(data)
        result["kind"] = "table"
        result["table"] = {"row_source_key": key, "rows": rows,
                           "columns": columns, "quality": quality}
        result["summary"] = (
            f"Table from {payload['filename']}{sheet_note}: {rows} rows, "
            f"columns {', '.join(c['name'] for c in columns[:12])}"
        )
        if quality["issues"]:
            result["summary"] += (
                f" — {len(quality['issues'])} quality issue(s): "
                + "; ".join(quality["issues"][:3]))
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
    """Header, row count, dtype sniff, and a deterministic quality audit.

    One full pass (uploads are webhook-capped, so the table fits in memory):
    dtypes from the non-empty values, and quality from the whole column —
    null rates, exact duplicate rows, extreme numeric outliers (3×IQR), and
    mostly-numeric columns polluted by stray text. Every figure is computed,
    never judged; the describe agent narrates, this code measures.
    """
    text = data.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    header = next(reader, [])
    all_rows = [r for r in reader]
    rows = len(all_rows)

    columns, null_rates, outliers, issues = [], {}, {}, []
    for i, raw_name in enumerate(header):
        name = raw_name.strip() or f"col_{i}"
        cells = [r[i].strip() if i < len(r) else "" for r in all_rows]
        values = [v for v in cells if v != ""]
        dtype = _sniff(values[:100])
        columns.append({"name": name, "dtype": dtype})

        empties = len(cells) - len(values)
        if rows and empties:
            pct = round(100 * empties / rows, 1)
            null_rates[name] = pct
            if pct >= 5:
                issues.append(f"column '{name}': {pct}% empty")

        if dtype in ("int", "float"):
            wild = _extreme_outliers([float(v) for v in values])
            if wild:
                outliers[name] = wild
                issues.append(f"column '{name}': {wild} extreme outlier(s)")
        elif dtype == "text" and values:
            numeric = sum(1 for v in values if _is_float(v.replace(",", "")))
            if 0 < len(values) - numeric <= len(values) * 0.4 and numeric >= len(values) * 0.6:
                issues.append(f"column '{name}': mixed types "
                              f"({len(values) - numeric} non-numeric among "
                              f"{len(values)} values)")

    dupes = rows - len({tuple(r) for r in all_rows})
    if dupes:
        issues.append(f"{dupes} exact duplicate row(s)")

    quality = {"issues": issues, "duplicate_rows": dupes,
               "null_rates": null_rates, "outliers": outliers}
    return columns, rows, quality


def _extreme_outliers(values) -> int:
    """Count beyond 3×IQR of the quartiles — the far-out kind only."""
    if len(values) < 8:
        return 0
    ranked = sorted(values)
    q1 = ranked[len(ranked) // 4]
    q3 = ranked[(3 * len(ranked)) // 4]
    spread = q3 - q1
    if spread <= 0:
        return 0
    lo, hi = q1 - 3 * spread, q3 + 3 * spread
    return sum(1 for v in values if v < lo or v > hi)


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
