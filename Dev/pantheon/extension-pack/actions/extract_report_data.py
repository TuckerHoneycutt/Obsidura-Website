"""Deterministic gather stage for reports over uploaded data (report_data@1).

The vertical pipelines split GATHER (grants + correctness) from DESIGN
(presentation). For uploaded files the gather seat needs no model: ingest
already normalized the upload to a typed table, so this script computes the
figures — totals, averages, group-by breakdowns — as plain arithmetic. Every
number in the report is computed here, by code, from the caller's own bytes;
the only model call left in the pipeline is the designer's.
"""

import csv
import io

from _compat import CATALOG_KEY, blob_get, index_load, record, value_in

MAX_FILES = 3          # newest uploads when the prompt names none
MAX_GROUPS = 24        # a column with more distinct values isn't a category
MAX_SAMPLE_ROWS = 15


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    prompt = (payload.get("prompt") or payload.get("question")
              or "Report on the uploaded data")

    entries = index_load(ctx, CATALOG_KEY)
    tables = [e for e in entries if e.get("kind") == "table"]
    if not tables:
        raise ValueError(
            "no uploaded tables in the catalog yet — add a CSV or spreadsheet "
            "first, then run this report")

    lowered = prompt.lower()
    named = [e for e in tables if _mentioned(e["source_filename"], lowered)]
    chosen = named or sorted(
        tables, key=lambda e: e.get("created_at", ""), reverse=True)[:MAX_FILES]

    data = {}
    for entry in chosen:
        key = (entry.get("detail") or {}).get("row_source_key") \
            or f"ingest/tables/{entry['sha256']}.csv"
        data[entry["source_filename"]] = _extract(blob_get(ctx, key))

    return record("report_data@1", {
        "question": prompt + "\n\nConvey this information to answer the "
        "question as well as it can be answered.",
        "data": data,
    })


def _mentioned(filename: str, lowered_prompt: str) -> bool:
    stem = filename.rsplit(".", 1)[0].lower()
    return filename.lower() in lowered_prompt or (
        len(stem) > 2 and stem in lowered_prompt)


def _extract(raw: bytes) -> dict:
    """Everything a designer could want from one table, computed exactly."""
    reader = csv.reader(io.StringIO(raw.decode("utf-8", errors="replace")))
    header = [h.strip() for h in next(reader, [])]
    rows = [r for r in reader if any(cell.strip() for cell in r)]

    columns = {name: [r[i].strip() if i < len(r) else "" for r in rows]
               for i, name in enumerate(header)}
    numeric, categorical = {}, {}
    for name, values in columns.items():
        nums = _as_numbers(values)
        if nums is not None:
            numeric[name] = nums
        else:
            distinct = {v for v in values if v}
            if 0 < len(distinct) <= MAX_GROUPS:
                categorical[name] = values

    out = {
        "row_count": len(rows),
        "columns": [{"name": n, "dtype": "number" if n in numeric
                     else "category" if n in categorical else "text"}
                    for n in header],
        "totals": {}, "breakdowns": {},
        "sample_rows": {"columns": header, "rows": rows[:MAX_SAMPLE_ROWS]},
    }
    for name, nums in numeric.items():
        present = [v for v in nums if v is not None]
        if present:
            out["totals"][name] = {
                "count": len(present),
                "sum": round(sum(present), 4),
                "mean": round(sum(present) / len(present), 4),
                "min": min(present),
                "max": max(present),
            }
    for cat, values in categorical.items():
        for num, nums in numeric.items():
            groups = {}
            for value, amount in zip(values, nums):
                if value and amount is not None:
                    g = groups.setdefault(value, {"count": 0, "sum": 0.0})
                    g["count"] += 1
                    g["sum"] = round(g["sum"] + amount, 4)
            if groups:
                out["breakdowns"][f"{num} by {cat}"] = groups
    return out


def _as_numbers(values):
    """The column as floats, or None when it isn't essentially numeric."""
    nums, hits, nonempty = [], 0, 0
    for v in values:
        if not v:
            nums.append(None)
            continue
        nonempty += 1
        try:
            nums.append(float(v.replace(",", "")))
            hits += 1
        except ValueError:
            return None
    return nums if nonempty and hits == nonempty else None
