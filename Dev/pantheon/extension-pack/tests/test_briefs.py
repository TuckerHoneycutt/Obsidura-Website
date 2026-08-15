#!/usr/bin/env python3
"""Schedules as configuration-as-data, and the brief that answers them."""

import json

from _fakes import FakeCtx, run_tests

import morning_brief
import schedule_add

CSV = b"employee,department,gross_pay\nAna,Engineering,9800\nBen,Operations,7200\n"


def catalog_objects():
    entry = {"kind": "table", "sha256": "abc", "source_filename": "pay.csv",
             "created_at": "2026-08-15",
             "detail": {"row_source_key": "ingest/tables/abc.csv"}}
    return {
        "ingest/catalog.json": json.dumps([entry]).encode(),
        "ingest/tables/abc.csv": CSV,
    }


def test_adding_a_schedule_persists_and_is_idempotent():
    ctx = FakeCtx()
    out = schedule_add.run(ctx, {"prompt": "Summarise pay", "requester": "alice"})
    assert out["type_ref"] == "schedule.added@1"
    assert out["data"]["count"] == 1
    # Same prompt again: same id, no duplicate.
    again = schedule_add.run(ctx, {"prompt": "summarise PAY", "requester": "alice"})
    assert again["data"]["count"] == 1
    assert again["data"]["id"] == out["data"]["id"]
    saved = json.loads(ctx.objects[schedule_add.SCHEDULES_KEY])
    assert len(saved) == 1 and saved[0]["requester"] == "alice"


def test_an_empty_prompt_is_refused():
    try:
        schedule_add.run(FakeCtx(), {"prompt": "   ", "requester": "alice"})
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_the_brief_answers_every_saved_prompt_with_real_figures():
    ctx = FakeCtx(objects=catalog_objects())
    schedule_add.run(ctx, {"prompt": "Summarise pay", "requester": "alice"})
    out = morning_brief.run(ctx, {"ts": "2026-08-15T07:00:00Z"})
    assert out["kind"] == "file"
    page = ctx.blobs[out["blob"]][0].decode("utf-8")
    assert "Summarise pay" in page       # the prompt leads its section
    assert "17,000" in page              # 9800 + 7200, computed fresh
    assert "morning brief" in page.lower()


def test_a_promptless_brief_invites_rather_than_fails():
    ctx = FakeCtx()
    out = morning_brief.run(ctx, {"ts": "2026-08-15T07:00:00Z"})
    page = ctx.blobs[out["blob"]][0].decode("utf-8")
    assert "No saved prompts yet" in page


def test_a_schedule_whose_data_vanished_gets_its_say_on_the_page():
    ctx = FakeCtx(objects={"ingest/catalog.json": b"[]"})
    schedule_add.run(ctx, {"prompt": "Summarise pay", "requester": "alice"})
    out = morning_brief.run(ctx, {"ts": "2026-08-15T07:00:00Z"})
    page = ctx.blobs[out["blob"]][0].decode("utf-8")
    assert "add a CSV or spreadsheet" in page  # the miss is reported, not fatal


def test_kernel_record_ticks_unwrap():
    ctx = FakeCtx()
    wrapped = {"kind": "record", "type_ref": "ext.cron_tick@1",
               "data": {"ts": "2026-08-15T07:00:00Z"}}
    out = morning_brief.run(ctx, wrapped)
    assert out["kind"] == "file"


if __name__ == "__main__":
    run_tests(globals())
