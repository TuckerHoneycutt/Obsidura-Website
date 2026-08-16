"""Sync a Slack channel's history into the catalog (ingest.result@1).

Same importer shape as Jira: messages fetched through the governed `slack`
resource (bot token from the operator's Settings) become a typed table in
the catalog — timestamps, authors, text, thread and reaction counts — so
Ask can answer "what did we discuss about X?" and the briefs can digest a
channel, with zero downstream changes.
"""

import datetime
import json
import urllib.parse

from _compat import blob_put, http_request, record, requester, sha256_hex, value_in
from ingest_normalize import _profile_csv

DEFAULT_LIMIT = 200


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    channel = (payload.get("channel") or "").strip()
    if not channel:
        raise ValueError("say which channel to sync — an id like C0123 or a #name")
    limit = min(int(payload.get("limit") or DEFAULT_LIMIT), 500)

    name = channel.lstrip("#")
    if channel.startswith("#"):
        channel = _resolve(ctx, name)

    resp = _api(ctx, f"/api/conversations.history?channel="
                f"{urllib.parse.quote(channel)}&limit={limit}")
    messages = resp.get("messages") or []

    rows = []
    for m in messages:
        try:
            ts = datetime.datetime.fromtimestamp(
                float(m.get("ts", 0)), datetime.timezone.utc
            ).strftime("%Y-%m-%d %H:%M")
        except (ValueError, OverflowError):
            ts = str(m.get("ts", ""))
        text = " ".join(str(m.get("text") or "").split())[:500]
        reactions = sum(int(r.get("count", 0)) for r in (m.get("reactions") or []))
        rows.append([ts, m.get("user") or m.get("bot_id") or "unknown",
                     text, int(m.get("reply_count") or 0), reactions])

    csv_bytes = _csv(["ts", "user", "text", "replies", "reactions"], rows)
    digest = sha256_hex(csv_bytes)
    key = f"ingest/tables/{digest}.csv"
    blob_put(ctx, key, csv_bytes, "text/csv")
    columns, count, quality = _profile_csv(csv_bytes)

    summary = f"Synced {len(rows)} messages from #{name} on Slack."
    if resp.get("has_more"):
        summary += f" The channel has more history than the {limit} fetched."
    if quality["issues"]:
        summary += " Quality: " + "; ".join(quality["issues"][:3])

    return record("ingest.result@1", {
        "source_filename": f"slack-{name}.csv",
        "media_type": "text/csv",
        "sha256": digest,
        "requester": requester(ctx, payload),
        "kind": "table",
        "table": {"row_source_key": key, "rows": count,
                  "columns": columns, "quality": quality},
        "summary": summary,
    })


def _resolve(ctx, name: str) -> str:
    """A #name to its channel id, through the same governed resource."""
    resp = _api(ctx, "/api/conversations.list?limit=1000&types=public_channel")
    for c in resp.get("channels") or []:
        if c.get("name") == name:
            return c["id"]
    raise ValueError(f"no public channel named #{name} — check the name, or "
                     "use the channel id")


def _api(ctx, path: str) -> dict:
    import base64
    resp = http_request(ctx, "slack", "GET", path)
    if resp["status"] != 200:
        raise RuntimeError(f"Slack answered HTTP {resp['status']}")
    body = json.loads(base64.b64decode(resp.get("body_b64") or ""))
    if not body.get("ok"):
        raise RuntimeError(
            f"Slack refused: {body.get('error', 'unknown')} — check the bot "
            "token in Settings and the app's scopes")
    return body


def _csv(header, rows) -> bytes:
    import csv
    import io
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    w.writerows(rows)
    return out.getvalue().encode("utf-8")
