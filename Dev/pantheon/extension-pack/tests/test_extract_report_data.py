#!/usr/bin/env python3
"""The deterministic gather seat: figures computed exactly, by code."""

import json

from _fakes import FakeCtx, run_tests

import extract_report_data
from extract_report_data import _as_numbers, _extract, _mentioned

CSV = (b"employee,department,gross_pay\n"
       b"Ana,Engineering,9800\n"
       b"Ben,Operations,7200\n"
       b"Cara,Engineering,10100\n")


def catalog_ctx(filename="pay.csv", key="ingest/tables/abc.csv"):
    entry = {"kind": "table", "sha256": "abc", "source_filename": filename,
             "created_at": "2026-08-15", "detail": {"row_source_key": key}}
    return FakeCtx(objects={
        "ingest/catalog.json": json.dumps([entry]).encode(),
        key: CSV,
    })


def test_totals_and_breakdowns_are_exact():
    out = extract_report_data.run(catalog_ctx(), {"prompt": "Summarise pay"})
    assert out["kind"] == "record" and out["type_ref"] == "report_data@1"
    extract = out["data"]["data"]["pay.csv"]
    assert extract["row_count"] == 3
    assert extract["totals"]["gross_pay"]["sum"] == 27100
    assert extract["totals"]["gross_pay"]["mean"] == round(27100 / 3, 4)
    groups = extract["breakdowns"]["gross_pay by department"]
    assert groups["Engineering"] == {"count": 2, "sum": 19900}
    assert groups["Operations"] == {"count": 1, "sum": 7200}


def test_the_question_carries_the_prompt_and_the_charge():
    out = extract_report_data.run(catalog_ctx(), {"prompt": "Summarise pay"})
    q = out["data"]["question"]
    assert q.startswith("Summarise pay")
    assert "Convey this information" in q


def test_an_empty_catalog_is_a_clear_error():
    ctx = FakeCtx(objects={"ingest/catalog.json": b"[]"})
    try:
        extract_report_data.run(ctx, {"prompt": "x"})
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "add a CSV or spreadsheet" in str(exc)


def test_a_named_file_is_chosen_over_newer_uploads():
    older = {"kind": "table", "sha256": "old1", "source_filename": "pay.csv",
             "created_at": "2026-08-01", "detail": {"row_source_key": "k1"}}
    newer = {"kind": "table", "sha256": "new1", "source_filename": "sales.csv",
             "created_at": "2026-08-15", "detail": {"row_source_key": "k2"}}
    ctx = FakeCtx(objects={
        "ingest/catalog.json": json.dumps([older, newer]).encode(),
        "k1": CSV, "k2": b"a,b\n1,2\n",
    })
    out = extract_report_data.run(ctx, {"prompt": "report on pay.csv please"})
    assert list(out["data"]["data"]) == ["pay.csv"]


def test_kernel_record_payloads_unwrap():
    payload = {"kind": "record", "type_ref": "report.request@1",
               "data": {"prompt": "Summarise pay"}}
    out = extract_report_data.run(catalog_ctx(), payload)
    assert out["data"]["question"].startswith("Summarise pay")


def test_numeric_sniff_handles_commas_blanks_and_text():
    assert _as_numbers(["1,234.5", "", "7"]) == [1234.5, None, 7.0]
    assert _as_numbers(["12", "abc"]) is None
    assert _as_numbers(["", ""]) is None  # nothing numeric to speak of


def test_sample_rows_are_capped():
    rows = b"".join(b"r%d,X,1\n" % i for i in range(40))
    extract = _extract(b"name,cat,n\n" + rows)
    assert extract["row_count"] == 40
    assert len(extract["sample_rows"]["rows"]) == extract_report_data.MAX_SAMPLE_ROWS


def test_ingest_quality_issues_ride_into_the_extract():
    entry = {"kind": "table", "sha256": "abc", "source_filename": "pay.csv",
             "created_at": "2026-08-15",
             "detail": {"row_source_key": "k1",
                        "quality": {"issues": ["2 exact duplicate row(s)"]}}}
    ctx = FakeCtx(objects={
        "ingest/catalog.json": json.dumps([entry]).encode(),
        "k1": CSV,
    })
    out = extract_report_data.run(ctx, {"prompt": "Summarise pay"})
    assert out["data"]["data"]["pay.csv"]["quality_issues"] == \
        ["2 exact duplicate row(s)"]


def test_filename_mentions_match_on_the_stem():
    assert _mentioned("pay.xlsx", "summarise pay please")
    assert not _mentioned("q.csv", "quarterly numbers")  # stem too short


if __name__ == "__main__":
    run_tests(globals())
