#!/usr/bin/env python3
"""The benchmark seat: exact figures in, sourced comparisons out."""

import json
import os

from _fakes import FakeCtx, run_tests

import market_compare
from market_compare import _render

CSV = b"employee,department,gross_pay\nAna,Engineering,9800\nBen,Operations,7200\n"

ENV_KEYS = ("PANTHEON_AGENT_MODEL", "PANTHEON_LLM_ANTHROPIC_API_KEY",
            "ANTHROPIC_API_KEY")


def catalog_ctx():
    entry = {"kind": "table", "sha256": "abc", "source_filename": "pay.xlsx",
             "created_at": "2026-08-15",
             "detail": {"row_source_key": "ingest/tables/abc.csv"}}
    return FakeCtx(objects={
        "ingest/catalog.json": json.dumps([entry]).encode(),
        "ingest/tables/abc.csv": CSV,
    })


def test_keyless_runs_produce_a_labeled_illustrative_page():
    ctx = catalog_ctx()
    saved = {k: os.environ.pop(k, None) for k in ENV_KEYS}
    try:
        out = market_compare.run(ctx, {"prompt": "vs industry", "requester": "alice"})
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
    assert out["kind"] == "file"
    page = ctx.blobs[out["blob"]][0].decode("utf-8")
    assert "mock:benchmark" in page          # the model is named on the page
    assert "Illustrative benchmarks" in page  # and labeled as such


def test_the_figures_fed_to_the_agent_are_computed_not_copied():
    ctx = catalog_ctx()
    seen = {}

    def spy(ctx_, spec, prompt, mock_fn):
        seen["prompt"] = prompt
        return {"summary": "s", "comparisons": [], "model": "spy", "audit": []}

    original = market_compare.run_agent
    market_compare.run_agent = spy
    try:
        market_compare.run(ctx, {"prompt": "vs industry", "requester": "alice"})
    finally:
        market_compare.run_agent = original
    assert '"sum": 17000' in seen["prompt"]           # 9800 + 7200, computed
    assert '"gross_pay by department"' in seen["prompt"]


def test_an_empty_catalog_is_a_clear_error():
    ctx = FakeCtx(objects={"ingest/catalog.json": b"[]"})
    try:
        market_compare.run(ctx, {"prompt": "x"})
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "add a CSV or spreadsheet" in str(exc)


def test_the_page_prints_comparisons_sources_and_the_audit():
    result = {
        "summary": "Ahead of the market.",
        "model": "anthropic:claude-sonnet-5",
        "comparisons": [{
            "metric": "avg pay", "our_value": "$8,480", "benchmark_value": "$6,519",
            "benchmark_label": "BLS implied monthly", "note": "different basis",
            "source_url": "https://api.bls.gov/publicAPI/v2/timeseries/data/X",
        }],
        "audit": [{"resource": "bls", "verb": "request", "detail": "/publicAPI/v2/x"}],
    }
    page = _render("vs industry", {"pay.xlsx": {"row_count": 2}}, result)
    assert "Ahead of the market." in page
    assert "$8,480" in page and "$6,519" in page
    assert 'href="https://api.bls.gov' in page
    assert "bls · request" in page
    assert "anthropic:claude-sonnet-5" in page


def test_an_empty_result_still_renders_honestly():
    page = _render("q", {}, {"summary": "nothing reachable",
                             "comparisons": [], "model": "m", "audit": []})
    assert "No comparisons could be made." in page


if __name__ == "__main__":
    run_tests(globals())
