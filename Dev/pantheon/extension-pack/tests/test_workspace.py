#!/usr/bin/env python3
"""The workspace snapshot: one person's inventory, nobody else's."""

import json

from _fakes import FakeCtx, run_tests

import workspace_snapshot


def test_the_snapshot_is_scoped_and_summarized():
    catalog = [
        {"kind": "table", "source_filename": "pay.csv", "requester": "alice",
         "created_at": "2026-08-15T10:00:00Z",
         "detail": {"rows": 9, "columns": [{"name": "a"}, {"name": "b"}],
                    "quality": {"issues": ["1 exact duplicate row(s)"]},
                    "tags": ["payroll"]},
         "summary": "A payroll table."},
        {"kind": "table", "source_filename": "jira-issues.csv",
         "requester": "alice", "created_at": "2026-08-17T09:00:00Z",
         "detail": {"rows": 3, "columns": []},
         "summary": "Synced 3 of 3 Jira issues (JQL: ORDER BY updated DESC)."},
        {"kind": "table", "source_filename": "secret.csv", "requester": "bob",
         "created_at": "2026-08-16T10:00:00Z", "detail": {}, "summary": "Bob's."},
        {"kind": "document", "source_filename": "legacy.pdf",
         "created_at": "2026-08-01T10:00:00Z", "detail": {}, "summary": "Old."},
    ]
    schedules = [
        {"prompt": "Summarise pay", "requester": "alice",
         "created_at": "2026-08-15T09:00:00Z"},
        {"prompt": "Bob's brief", "requester": "bob",
         "created_at": "2026-08-15T09:00:00Z"},
    ]
    ctx = FakeCtx(objects={
        "ingest/catalog.json": json.dumps(catalog).encode(),
        "config/schedules.json": json.dumps(schedules).encode(),
    })
    out = workspace_snapshot.run(ctx, {"requester": "alice"})
    assert out["kind"] == "file"
    doc = json.loads(ctx.blobs[out["blob"]][0])
    names = [f["filename"] for f in doc["files"]]
    assert "pay.csv" in names and "legacy.pdf" in names   # hers + unattributed
    assert "secret.csv" not in names                       # bob's stays his
    pay = next(f for f in doc["files"] if f["filename"] == "pay.csv")
    assert pay["rows"] == 9 and pay["columns"] == 2
    assert pay["quality_issues"] == ["1 exact duplicate row(s)"]
    assert pay["column_list"] == [{"name": "a", "dtype": ""},
                                  {"name": "b", "dtype": ""}]
    assert pay["source"] == "upload"
    assert [s["prompt"] for s in doc["schedules"]] == ["Summarise pay"]
    jira = next(f for f in doc["files"] if f["filename"] == "jira-issues.csv")
    assert jira["source"] == "jira"


def test_an_empty_workspace_is_a_valid_page_not_an_error():
    ctx = FakeCtx(objects={"ingest/catalog.json": b"[]"})
    out = workspace_snapshot.run(ctx, {"requester": "bob"})
    doc = json.loads(ctx.blobs[out["blob"]][0])
    assert doc["files"] == [] and doc["schedules"] == []


if __name__ == "__main__":
    run_tests(globals())
