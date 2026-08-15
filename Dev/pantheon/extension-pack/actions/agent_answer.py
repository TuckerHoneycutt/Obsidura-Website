"""Agent action: answer a natural-language question over the user's data.

Triggered by webhook ask.question. The envelope is the ingest catalog, the
web registry, and the blob store — the agent chooses what to pull per
question (Appendix A discretion), and every pull lands in the audit trail.
"""

import csv
import io
import json

from _agent import run_agent
from _compat import CATALOG_KEY, blob_get, record, value_in

SPEC = {
    "name": "answer_agent@1",
    "model": "mock:v0",
    "repair_budget": 2,
    "tools": [
        {"resource": "blob_store", "verbs": ["get"]},
        {"resource": "financial_ledger", "verbs": ["query"]},
        {"resource": "clinical_patients", "verbs": ["query"]},
        {"resource": "rocket_test_logs", "verbs": ["query"]},
    ],
    "instructions": (
        "Answer the requester's question using their data. Your envelope, "
        "enforced at the proxy under the requester's grant:\n"
        "- blob_store (verb get): the catalog index at key "
        "ingest/catalog.json (a JSON list of entries — sha256, kind, "
        "media_type, source_filename, summary, detail with "
        "row_source_key/blob_key, profiled columns, and any quality issues "
        "noted at ingest), the web registry at web/registry.json, and any "
        "blob a catalog entry names.\n"
        "- financial_ledger (verb query, SELECT only): table ledger "
        "(id, date, account, amount numeric, currency, vendor, department). "
        "Amounts are in their own currency — never total across currencies "
        "without saying so.\n"
        "- clinical_patients (verb query, SELECT only): table patients "
        "(id, name, age, ward, diagnosis_code).\n"
        "- rocket_test_logs (verb query, SELECT only): table test_logs "
        "(id, ts, event, channel, message, severity).\n"
        "Uploaded-file questions go to the catalog; questions about the "
        "ledger, patients, or the test bench go to SQL — compute aggregates "
        "in SQL, copy results digit for digit. A refused call means the "
        "requester's grant does not cover it: report that honestly rather "
        "than working around it (another user may see different rows by "
        "design). Choose what to query per question — never one fixed "
        "query. Answer concisely, cite what you used in sources (filenames "
        "or table names), note relevant quality issues, and if the data "
        "cannot answer the question, say so plainly. Submit via final_result."
    ),
    "output_schema": {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["answer", "sources"],
        "additionalProperties": False,
    },
}


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    result = run_agent(ctx, SPEC, payload["question"], _mock)
    return record("agent.answer@1", {
        "question": payload["question"],
        "answer": result["answer"],
        "sources": result.get("sources", []),
        "model": result["model"],
        "audit": result["audit"],
    })


def run_engine(ctx, payload: dict) -> dict:
    """Engine entry: same answer, delivered as a kernel.file so the demo
    shell can read it — /runs/{id} exposes File outputs only, so a Record
    answer would be invisible to the page. The blob is the agent.answer
    record as JSON; the shell fetches and renders it inline."""
    answer = run(ctx, payload)["data"]
    handle = ctx.blob_put(
        json.dumps(answer).encode("utf-8"), "application/json"
    )
    return {"kind": "file", **handle}


# ------------------------- deterministic mock --------------------------------

STOPWORDS = {"the", "a", "an", "of", "in", "on", "for", "to", "is", "are",
             "what", "which", "how", "many", "much", "does", "do", "my",
             "i", "we", "have", "about", "tell", "me", "show"}


def _mock(run, question):
    out = run.call("blob_store", "get", key=CATALOG_KEY)
    try:
        text = out.get("text") if isinstance(out, dict) else None
        if text is None and isinstance(out, dict) and out.get("b64"):
            import base64 as _b64
            text = _b64.b64decode(out["b64"]).decode("utf-8")
        rows = json.loads(text or "[]")
    except Exception:
        rows = []
    rows = sorted(rows, key=lambda r: r.get("created_at", ""), reverse=True)
    if not rows:
        return {"answer": "Nothing has been ingested yet — upload a file and ask again.",
                "sources": []}

    words = {w.strip("?,.!").lower() for w in question.split()} - STOPWORDS
    scored = []
    for r in rows:
        hay = f"{r['source_filename']} {r['summary']}".lower()
        score = sum(1 for w in words if w and w in hay)
        scored.append((score, r))
    scored.sort(key=lambda s: -s[0])
    best_score, best = scored[0]

    if best_score == 0:
        listing = "; ".join(f"{r['source_filename']} ({r['kind']})" for r in rows[:8])
        return {
            "answer": f"Nothing in the catalog matches that directly. "
                      f"Cataloged items: {listing}.",
            "sources": [r["source_filename"] for r in rows[:8]],
        }

    detail = best.get("detail") or {}
    if best["kind"] == "table" and detail.get("row_source_key"):
        stats = _table_stats(run, detail["row_source_key"])
        answer = (
            f"{best['source_filename']} looks most relevant. It is a table with "
            f"{detail.get('rows', '?')} rows and columns "
            f"{', '.join(c['name'] for c in detail.get('columns', []))}. {stats}"
        )
    else:
        answer = f"{best['source_filename']} looks most relevant: {best['summary']}"
    return {"answer": answer, "sources": [best["source_filename"]]}


def _table_stats(run, key):
    """Quick numeric profile of the table's row source — real blob access."""
    try:
        data = blob_get(run.ctx, key)
        run.audit.append({"resource": "blob_store", "verb": "get", "detail": key})
    except Exception:
        return ""
    reader = csv.DictReader(io.StringIO(data.decode("utf-8", errors="replace")))
    sums, counts = {}, {}
    for row in reader:
        for col, val in row.items():
            try:
                sums[col] = sums.get(col, 0.0) + float(val)
                counts[col] = counts.get(col, 0) + 1
            except (TypeError, ValueError):
                continue
    parts = [f"mean {c} = {sums[c] / counts[c]:.2f}" for c in sums if counts.get(c)]
    return ("Numeric summary: " + "; ".join(parts[:4]) + ".") if parts else ""
