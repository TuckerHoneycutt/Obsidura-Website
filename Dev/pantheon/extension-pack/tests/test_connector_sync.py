#!/usr/bin/env python3
"""The connection importers: external sources become catalogued tables."""

import json
import urllib.parse

from _fakes import FakeCtx, run_tests

import jira_sync
import slack_sync

JIRA_PATH = ("/rest/api/3/search?jql="
             + urllib.parse.quote("ORDER BY updated DESC")
             + "&maxResults=100&fields=" + jira_sync.FIELDS)
JIRA_BODY = json.dumps({
    "total": 5,
    "issues": [
        {"key": "ENG-1", "fields": {
            "issuetype": {"name": "Bug"}, "status": {"name": "Done"},
            "assignee": {"displayName": "Ana"}, "priority": {"name": "High"},
            "created": "2026-08-01T09:00:00.000+0000",
            "resolutiondate": "2026-08-04T15:00:00.000+0000"}},
        {"key": "ENG-2", "fields": {
            "issuetype": {"name": "Story"}, "status": {"name": "In Progress"},
            "assignee": None, "priority": {"name": "Medium"},
            "created": "2026-08-10T09:00:00.000+0000",
            "resolutiondate": None}},
    ],
}).encode()


def test_jira_issues_become_a_catalogued_table():
    ctx = FakeCtx(http={("jira", JIRA_PATH): (200, "application/json", JIRA_BODY)})
    out = jira_sync.run(ctx, {"requester": "alice"})
    assert out["type_ref"] == "ingest.result@1"
    data = out["data"]
    assert data["kind"] == "table"
    assert data["source_filename"] == "jira-issues.csv"
    assert "2 of 5" in data["summary"]          # partial sync is said plainly
    stored = ctx.objects[data["table"]["row_source_key"]].decode()
    assert "ENG-1,Bug,Done,Ana,High,2026-08-01,2026-08-04,3" in stored
    assert "unassigned" in stored                # null assignee handled


def test_jira_http_errors_point_at_settings():
    ctx = FakeCtx(http={("jira", JIRA_PATH): (401, "application/json", b"{}")})
    try:
        jira_sync.run(ctx, {"requester": "alice"})
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "Settings" in str(exc)


SLACK_LIST = json.dumps({"ok": True, "channels": [
    {"id": "C0GEN", "name": "general"}, {"id": "C0ENG", "name": "eng"}]}).encode()
SLACK_HIST = json.dumps({"ok": True, "has_more": True, "messages": [
    {"ts": "1755300000.000100", "user": "U01", "text": "ship it\ntoday",
     "reply_count": 2, "reactions": [{"count": 3}]},
    {"ts": "1755300100.000200", "bot_id": "B77", "text": "deploy done"},
]}).encode()


def slack_ctx():
    return FakeCtx(http={
        ("slack", "/api/conversations.list?limit=1000&types=public_channel"):
            (200, "application/json", SLACK_LIST),
        ("slack", "/api/conversations.history?channel=C0ENG&limit=200"):
            (200, "application/json", SLACK_HIST),
    })


def test_slack_channel_names_resolve_and_messages_land():
    ctx = slack_ctx()
    out = slack_sync.run(ctx, {"requester": "alice", "channel": "#eng"})
    data = out["data"]
    assert data["source_filename"] == "slack-eng.csv"
    assert "2 messages" in data["summary"]
    assert "more history" in data["summary"]     # truncation said plainly
    body = ctx.objects[data["table"]["row_source_key"]].decode()
    assert "ship it today" in body               # newlines flatten
    assert "B77" in body                         # bot messages keep an author


def test_slack_refusals_carry_the_api_error():
    ctx = FakeCtx(http={
        ("slack", "/api/conversations.history?channel=C1&limit=200"):
            (200, "application/json",
             json.dumps({"ok": False, "error": "invalid_auth"}).encode()),
    })
    try:
        slack_sync.run(ctx, {"requester": "alice", "channel": "C1"})
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "invalid_auth" in str(exc)


def test_unknown_channel_is_a_clear_error():
    try:
        slack_sync.run(slack_ctx(), {"requester": "alice", "channel": "#nope"})
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "#nope" in str(exc)




CSV_BYTES = b"region,amount\nwest,10\neast,20\n"


def test_nas_objects_ride_the_ingest_path():
    import nas_sync
    ctx = FakeCtx(objects={"reports/q3.csv": CSV_BYTES})
    out = nas_sync.run(ctx, {"requester": "alice", "path": "reports/q3.csv"})
    data = out["data"]
    assert data["kind"] == "table" and data["source_filename"] == "q3.csv"
    assert data["table"]["rows"] == 2


def test_web_files_pull_and_parse():
    import file_sync
    ctx = FakeCtx(http={("webfile", "/exports/pay.csv?sv=TOKEN"):
                        (200, "text/csv", CSV_BYTES)})
    out = file_sync.run(ctx, {"requester": "alice",
                              "path": "exports/pay.csv?sv=TOKEN"})
    data = out["data"]
    assert data["kind"] == "table"
    assert data["source_filename"] == "pay.csv"   # the SAS token never names the file


def test_msgraph_minted_token_rides_every_call():
    import base64 as b64
    import os
    import msgraph_sync
    link = "https://contoso.sharepoint.com/:x:/s/x/doc"
    share = "u!" + b64.urlsafe_b64encode(link.encode()).decode().rstrip("=")
    ctx = FakeCtx(http={
        ("mslogin", "/tid/oauth2/v2.0/token"):
            (200, "application/json",
             json.dumps({"access_token": "tok-123"}).encode()),
        ("msgraph", f"/v1.0/shares/{share}/driveItem?$select=name,size,file"):
            (200, "application/json",
             json.dumps({"name": "pay.csv",
                         "file": {"mimeType": "text/csv"}}).encode()),
        ("msgraph", f"/v1.0/shares/{share}/driveItem/content"):
            (200, "text/csv", CSV_BYTES),
    })
    saved = {k: os.environ.get(k) for k in
             ("PANTHEON_MS_TENANT", "PANTHEON_MS_CLIENT", "PANTHEON_MS_SECRET")}
    os.environ.update({"PANTHEON_MS_TENANT": "tid",
                       "PANTHEON_MS_CLIENT": "cid",
                       "PANTHEON_MS_SECRET": "sec"})
    try:
        out = msgraph_sync.run(ctx, {"requester": "alice", "link": link})
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    data = out["data"]
    assert data["source_filename"] == "pay.csv" and data["kind"] == "table"
    graph_calls = [c for c in ctx.calls if c[0] == "msgraph"]
    assert all(c[2].get("headers", {}).get("Authorization") == "Bearer tok-123"
               for c in graph_calls)


def test_msgraph_unconfigured_points_at_settings():
    import os
    import msgraph_sync
    saved = {k: os.environ.pop(k, None) for k in
             ("PANTHEON_MS_TENANT", "PANTHEON_MS_CLIENT", "PANTHEON_MS_SECRET")}
    try:
        msgraph_sync.run(FakeCtx(), {"requester": "alice", "link": "https://x/y"})
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "Settings" in str(exc)
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


if __name__ == "__main__":
    run_tests(globals())
