#!/usr/bin/env python3
"""The template design seat: a full page from report_data@1, no model."""

import json

from _fakes import FakeCtx, run_tests

import render_template
from render_template import fmt

DOC = {
    "kind": "record",
    "type_ref": "report_data@1",
    "data": {
        "question": "Summarise payroll spend by department",
        "data": {
            "pay.xlsx": {
                "row_count": 3,
                "columns": [{"name": "gross_pay", "dtype": "number"}],
                "totals": {"gross_pay": {"count": 3, "sum": 27100,
                                         "mean": 9033.33, "min": 7200, "max": 10100}},
                "breakdowns": {"gross_pay by department": {
                    "Engineering": {"count": 2, "sum": 19900},
                    "Operations": {"count": 1, "sum": 7200},
                }},
                "sample_rows": {"columns": ["employee", "gross_pay"],
                                "rows": [["Ana", "9800"], ["Ben", "7200"]]},
            },
        },
    },
}


def render(doc):
    ctx = FakeCtx()
    out = render_template.run(ctx, doc)
    assert out["kind"] == "file"
    return ctx.blobs[out["blob"]][0].decode("utf-8"), ctx.blobs[out["blob"]][1]


def test_a_complete_page_comes_back_as_an_html_file():
    page, media = render(DOC)
    assert media == "text/html"
    assert "<!doctype html>" in page
    assert "<title>Summarise payroll spend by department</title>" in page


def test_kpis_tables_and_samples_carry_the_figures():
    page, _ = render(DOC)
    assert 'class="kpi"' in page and "27,100" in page
    # Breakdown rows ranked by sum, largest first.
    assert page.index("Engineering") < page.index("Operations")
    assert "19,900" in page and "7,200" in page
    assert "Ana" in page


def test_the_verbatim_dump_rides_at_the_foot():
    page, _ = render(DOC)
    assert "<details>" in page
    assert '"gross_pay by department"' in page


def test_markup_in_the_data_is_escaped():
    hostile = json.loads(json.dumps(DOC))
    hostile["data"]["question"] = "<script>alert(1)</script>"
    page, _ = render(hostile)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_quality_issues_render_as_their_own_note():
    doc = json.loads(json.dumps(DOC))
    doc["data"]["data"]["pay.xlsx"]["quality_issues"] = [
        "column 'bonus': 40% empty"]
    page, _ = render(doc)
    assert "data quality" in page
    assert "column 'bonus': 40% empty" in page
    clean, _ = render(DOC)
    assert "data quality" not in clean


def test_number_formatting():
    assert fmt(27100) == "27,100"
    assert fmt(1234.5) == "1,234.5"
    assert fmt(733.03) == "733.03"
    assert fmt("west") == "west"


if __name__ == "__main__":
    run_tests(globals())
