#!/usr/bin/env python3
"""Upload normalization: CSV and xlsx become typed tables, the rest Files."""

import base64
import io

from _fakes import FakeCtx, run_tests

import ingest_normalize
from ingest_normalize import _sniff


def upload(ctx, filename, media_type, data: bytes):
    return ingest_normalize.run(ctx, {
        "filename": filename, "media_type": media_type,
        "size_bytes": len(data),
        "content_b64": base64.b64encode(data).decode("ascii"),
        "requester": "alice",
    })


def test_csv_profiles_as_a_table():
    ctx = FakeCtx()
    out = upload(ctx, "sales.csv", "text/csv",
                 b"region,amount\nwest,10\neast,20\n")
    data = out["data"]
    assert out["type_ref"] == "ingest.result@1"
    assert data["kind"] == "table"
    assert data["table"]["rows"] == 2
    names = [c["name"] for c in data["table"]["columns"]]
    assert names == ["region", "amount"]
    # The raw bytes were stored through the proxy under the digest key.
    assert data["table"]["row_source_key"] in ctx.objects


def test_xlsx_converts_to_csv_and_notes_the_sheet():
    try:
        import openpyxl
    except ImportError:
        print("  (openpyxl not installed here — xlsx branch not exercised)")
        return
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Payroll"
    sheet.append(["employee", "gross_pay"])
    sheet.append(["Ana", 9800])
    buf = io.BytesIO()
    book.save(buf)

    ctx = FakeCtx()
    out = upload(ctx, "pay.xlsx",
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                 buf.getvalue())
    data = out["data"]
    assert data["kind"] == "table"
    assert "sheet 'Payroll'" in data["summary"]
    stored = ctx.objects[data["table"]["row_source_key"]]
    assert stored.splitlines()[0] == b"employee,gross_pay"


def test_a_broken_xlsx_falls_back_to_document():
    ctx = FakeCtx()
    out = upload(ctx, "corrupt.xlsx",
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                 b"this is not a zip archive")
    assert out["data"]["kind"] == "document"


def test_json_inlines_as_a_record():
    ctx = FakeCtx()
    out = upload(ctx, "conf.json", "application/json", b'{"retries": 3}')
    assert out["data"]["kind"] == "data"
    assert out["data"]["record"] == {"retries": 3}


def test_unknown_media_stores_as_document():
    ctx = FakeCtx()
    out = upload(ctx, "notes.pdf", "application/pdf", b"%PDF-1.4 ...")
    data = out["data"]
    assert data["kind"] == "document"
    assert data["file"]["blob_key"] in ctx.objects


def test_quality_audit_measures_nulls_duplicates_and_summary_notes_them():
    rows = b"region,amount\nwest,10\nwest,10\n,30\n" + b"east,20\n" * 5
    ctx = FakeCtx()
    out = upload(ctx, "dirty.csv", "text/csv", rows)
    q = out["data"]["table"]["quality"]
    assert q["duplicate_rows"] >= 4          # one 'west' dupe + repeated 'east'
    assert q["null_rates"]["region"] > 0
    assert any("duplicate" in i for i in q["issues"])
    assert "quality issue" in out["data"]["summary"]


def test_a_clean_table_reports_no_issues():
    ctx = FakeCtx()
    out = upload(ctx, "clean.csv", "text/csv",
                 b"region,amount\nwest,10\neast,20\nnorth,30\n")
    q = out["data"]["table"]["quality"]
    assert q["issues"] == []
    assert "quality issue" not in out["data"]["summary"]


def test_extreme_outliers_are_counted():
    from ingest_normalize import _extreme_outliers
    tame = [10.0, 11, 12, 10, 11, 12, 10, 11]
    assert _extreme_outliers(tame) == 0
    assert _extreme_outliers(tame + [10000.0]) == 1
    assert _extreme_outliers([1.0] * 20) == 0    # zero spread, no division
    assert _extreme_outliers([1.0, 99.0]) == 0   # too few to judge


def test_dtype_sniffing():
    assert _sniff(["1", "2"]) == "int"
    assert _sniff(["1.5", "2"]) == "float"
    assert _sniff(["true", "false"]) == "bool"
    assert _sniff(["2026-01-05", "2026-02-01"]) == "timestamp"
    assert _sniff(["west", "east"]) == "text"
    assert _sniff([]) == "unknown"


if __name__ == "__main__":
    run_tests(globals())
