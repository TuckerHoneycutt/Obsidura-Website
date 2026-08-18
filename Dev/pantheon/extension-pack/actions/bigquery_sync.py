"""Run a BigQuery query and land the result in the catalog as a table.

Materialization, not a live query surface: the statement runs once, the
rows become a catalogued CSV with dtypes and a quality audit, and every
existing surface — Ask, the reports, the brief, the benchmark — can read
them with no further BigQuery cost. (The live-resource path is phase 4 of
docs/google-integration.md; it needs the connector to hold a refreshable
token, which is engine work.)

The jobs.query endpoint is synchronous-with-an-asterisk: it waits up to
timeoutMs, then hands back a job id to poll. Both shapes are handled, with
the poll bounded well inside the task's own timeout. Results are capped —
a warehouse can produce more rows than a report can want.
"""

import base64
import json
import os
import time

from _compat import http_request, value_in

import ingest_normalize
from _google import explain, get_json, rows_to_csv, token

MAX_ROWS = 10000
WAIT_MS = 20000       # how long jobs.query itself may hold the line
POLL_TRIES = 24       # * POLL_S ≈ two minutes of polling, inside timeout_ms
POLL_S = 5


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    sql = (payload.get("sql") or "").strip()
    if not sql:
        raise ValueError(
            "write the query to run — e.g. SELECT vendor, SUM(amount) "
            "FROM billing.spend GROUP BY vendor")
    project = os.environ.get("PANTHEON_GCP_PROJECT", "")
    if not project:
        raise RuntimeError(
            "BigQuery needs a project id — set the Google Cloud project "
            "in Settings (the gear icon) first")

    auth = {"Authorization": "Bearer " + token(ctx)}
    body = json.dumps({
        "query": sql,
        "useLegacySql": False,
        "maxResults": MAX_ROWS,
        "timeoutMs": WAIT_MS,
    })
    resp = http_request(
        ctx, "gbigquery", "POST",
        f"/bigquery/v2/projects/{project}/queries",
        body=body.encode(),
        headers={**auth, "Content-Type": "application/json"})
    out = json.loads(base64.b64decode(resp.get("body_b64") or "") or b"{}")
    if resp["status"] != 200:
        err = ((out.get("error") or {}).get("message") or "")[:300]
        raise RuntimeError(
            err and f"BigQuery refused the query: {err}"
            or explain(resp["status"], "the query", scope="BigQuery"))

    # A slow job comes back incomplete; poll it to completion.
    tries = 0
    while not out.get("jobComplete"):
        if tries >= POLL_TRIES:
            raise RuntimeError(
                "the query is still running after two minutes — narrow it, "
                "or materialize a smaller slice")
        tries += 1
        time.sleep(POLL_S)
        job = (out.get("jobReference") or {}).get("jobId", "")
        out = get_json(
            ctx, "gbigquery",
            f"/bigquery/v2/projects/{project}/queries/{job}"
            f"?timeoutMs={WAIT_MS}&maxResults={MAX_ROWS}",
            auth, "the query's result", scope="BigQuery")

    fields = [f.get("name", f"col{i}")
              for i, f in enumerate((out.get("schema") or {}).get("fields") or [])]
    rows = [[_cell(c.get("v")) for c in r.get("f") or []]
            for r in out.get("rows") or []]
    if not fields:
        raise RuntimeError("the query returned no columns — nothing to catalog")

    total = int(out.get("totalRows") or len(rows))
    note = f"synced from BigQuery — {total} row(s)"
    if total > len(rows):
        note += f", first {len(rows)} kept"

    return ingest_normalize.run(ctx, {
        "filename": "bigquery-results.csv",
        "media_type": "text/csv",
        "size_bytes": 1,
        "content_b64": base64.b64encode(rows_to_csv(fields, rows)).decode("ascii"),
        "requester": payload.get("requester", "unknown"),
        "note": note,
    })


def _cell(v):
    """BigQuery cells arrive as strings or nested {v: …} lists; flatten."""
    if isinstance(v, list):
        return json.dumps([_cell(x.get("v") if isinstance(x, dict) else x)
                           for x in v])
    if isinstance(v, dict):
        return json.dumps(v)
    return v
