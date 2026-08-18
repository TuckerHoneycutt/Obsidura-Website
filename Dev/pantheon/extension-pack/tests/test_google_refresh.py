#!/usr/bin/env python3
"""The morning refresh: saved recipes replay, one dead recipe doesn't kill the rest."""

import json

from _fakes import FakeCtx, run_tests

import google_refresh
import sync_schedule_add
from sync_schedule_add import SYNC_SCHEDULES_KEY

CSV_BYTES = b"region,amount\nwest,10\neast,20\n"
GOOGLE_ENV = ("PANTHEON_GOOGLE_CLIENT_ID", "PANTHEON_GOOGLE_CLIENT_SECRET",
              "PANTHEON_GOOGLE_REFRESH_TOKEN")


def _with_google_env(fn):
    import os
    saved = {k: os.environ.get(k) for k in GOOGLE_ENV}
    os.environ.update({"PANTHEON_GOOGLE_CLIENT_ID": "cid",
                       "PANTHEON_GOOGLE_CLIENT_SECRET": "sec",
                       "PANTHEON_GOOGLE_REFRESH_TOKEN": "ref"})
    try:
        return fn()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_saving_a_recipe_is_idempotent_and_removal_deletes_it():
    ctx = FakeCtx()
    out1 = sync_schedule_add.run(ctx, {"requester": "alice", "source": "gmail",
                                       "arg": "from:stripe"})
    out2 = sync_schedule_add.run(ctx, {"requester": "alice", "source": "gmail",
                                       "arg": "from:stripe"})
    assert out1["data"]["id"] == out2["data"]["id"]
    assert out2["data"]["count"] == 1

    entries = json.loads(ctx.objects[SYNC_SCHEDULES_KEY])
    assert entries[0]["source"] == "gmail" and entries[0]["requester"] == "alice"

    removed = sync_schedule_add.run(ctx, {"requester": "alice",
                                          "remove": out1["data"]["id"]})
    assert removed["data"] == {"action": "removed", "id": out1["data"]["id"],
                               "count": 0}
    assert json.loads(ctx.objects[SYNC_SCHEDULES_KEY]) == []


def test_a_door_that_needs_its_argument_refuses_a_blank_one():
    try:
        sync_schedule_add.run(FakeCtx(), {"requester": "alice", "source": "bigquery"})
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "argument" in str(exc)


def test_the_tick_replays_recipes_and_survives_a_dead_one():
    ctx = FakeCtx(http={
        ("gauth", "/token"): (200, "application/json",
                              json.dumps({"access_token": "tok"}).encode()),
        # the gcs recipe works…
        ("gstorage", "/storage/v1/b/bkt/o/pay.csv"):
            (200, "application/json",
             json.dumps({"name": "pay.csv", "size": "36",
                         "contentType": "text/csv"}).encode()),
        ("gstorage", "/storage/v1/b/bkt/o/pay.csv?alt=media"):
            (200, "text/csv", CSV_BYTES),
        # …the drive recipe has no stubs: its file is gone, the sync raises.
    })
    ctx.objects[SYNC_SCHEDULES_KEY] = json.dumps([
        {"id": "aaa", "source": "gcs", "arg": "gs://bkt/pay.csv",
         "requester": "alice", "created_at": "2026-08-01T00:00:00Z"},
        {"id": "bbb", "source": "drive", "arg": "https://x/d/1AbCdEfGhIjKlMn/y",
         "requester": "alice", "created_at": "2026-08-01T00:00:00Z"},
    ]).encode()

    out = _with_google_env(lambda: google_refresh.run(ctx, {"ts": "2026-08-18T06:30:00Z"}))
    data = out["data"]
    assert data["ran"] == 1 and data["failed"] == 1
    assert "drive" in data["notes"]

    # The survivor landed in the catalog, attributed to its requester.
    catalog = json.loads(ctx.objects["ingest/catalog.json"])
    assert len(catalog) == 1
    assert catalog[0]["source_filename"] == "pay.csv"
    assert catalog[0]["requester"] == "alice"
    assert "cloud storage" in catalog[0]["summary"].lower()


if __name__ == "__main__":
    run_tests(globals())
