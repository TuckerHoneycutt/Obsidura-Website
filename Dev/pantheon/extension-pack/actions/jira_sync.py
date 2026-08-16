"""Sync Jira issues into the catalog (ingest.result@1).

An importer, not a query surface: issues fetched through the governed
`jira` resource (site and credentials come from the operator's Settings,
resolved at call time) are shaped into the same typed table an upload
takes — profile, quality audit and all — and handed to the catalog chain.
From there the Delivery report, Ask, and the briefs see real tickets with
zero further changes.
"""

import json
import urllib.parse

from _compat import blob_put, http_request, record, requester, sha256_hex, value_in
from ingest_normalize import _profile_csv

DEFAULT_JQL = "ORDER BY updated DESC"
PAGE = 100
FIELDS = "summary,issuetype,status,assignee,priority,created,resolutiondate"


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    jql = (payload.get("jql") or DEFAULT_JQL).strip()

    path = ("/rest/api/3/search?jql=" + urllib.parse.quote(jql)
            + f"&maxResults={PAGE}&fields={FIELDS}")
    resp = http_request(ctx, "jira", "GET", path)
    if resp["status"] != 200:
        raise RuntimeError(
            f"Jira answered HTTP {resp['status']} — check the site URL and "
            "credentials in Settings")
    body = json.loads(_body(resp))

    issues = body.get("issues") or []
    total = body.get("total", len(issues))
    rows = [_row(i) for i in issues]
    csv_bytes = _csv(
        ["key", "type", "status", "assignee", "priority",
         "created", "resolved", "cycle_days"], rows)

    digest = sha256_hex(csv_bytes)
    key = f"ingest/tables/{digest}.csv"
    blob_put(ctx, key, csv_bytes, "text/csv")
    columns, count, quality = _profile_csv(csv_bytes)

    summary = (f"Synced {len(issues)} of {total} Jira issues "
               f"(JQL: {jql}).")
    if total > len(issues):
        summary += f" Only the first {PAGE} are included."
    if quality["issues"]:
        summary += (" Quality: " + "; ".join(quality["issues"][:3]))

    return record("ingest.result@1", {
        "source_filename": "jira-issues.csv",
        "media_type": "text/csv",
        "sha256": digest,
        "requester": requester(ctx, payload),
        "kind": "table",
        "table": {"row_source_key": key, "rows": count,
                  "columns": columns, "quality": quality},
        "summary": summary,
    })


def _row(issue):
    f = issue.get("fields") or {}
    created = str(f.get("created") or "")[:10]
    resolved = str(f.get("resolutiondate") or "")[:10]
    cycle = ""
    if created and resolved:
        try:
            import datetime
            d0 = datetime.date.fromisoformat(created)
            d1 = datetime.date.fromisoformat(resolved)
            cycle = str((d1 - d0).days)
        except ValueError:
            pass
    return [
        issue.get("key", ""),
        (f.get("issuetype") or {}).get("name", ""),
        (f.get("status") or {}).get("name", ""),
        (f.get("assignee") or {}).get("displayName") or "unassigned",
        (f.get("priority") or {}).get("name", ""),
        created,
        resolved,
        cycle,
    ]


def _csv(header, rows) -> bytes:
    import csv
    import io
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    w.writerows(rows)
    return out.getvalue().encode("utf-8")


def _body(resp) -> bytes:
    import base64
    return base64.b64decode(resp.get("body_b64") or "")
