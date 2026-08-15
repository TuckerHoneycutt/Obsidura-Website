"""Agent action: enrich a fresh ingest with a description and tags.

Chain position: upload.file -> ingest_normalize -> catalog_register -> here.
The agent PROPOSES (description + tags, from whatever it chooses to read in
its envelope — the catalog index via blob_store); a deterministic step
COMMITS the enrichment to the index. Keeping the write out of the agent's
hands is the governance pattern from the spec.
"""

import base64
import json

from _agent import run_agent
from _compat import CATALOG_KEY, index_load, index_save, record, value_in

SPEC = {
    "name": "describe_agent@1",
    "model": "mock:v0",
    "repair_budget": 2,
    "tools": [{"resource": "blob_store", "verbs": ["get"]}],
    "instructions": (
        "A file was just ingested and cataloged. Your envelope: the catalog "
        "index object at key ingest/catalog.json via your blob_store tool "
        "(a JSON list of entries with sha256, kind, media_type, "
        "source_filename, summary and profiled detail), plus any blob a "
        "catalog entry names. Look up the new entry by its sha256, read what "
        "was profiled, and compose a one-paragraph description of what this "
        "data appears to be and what reports could use it, plus up to five "
        "short lowercase tags. Submit via final_result. You propose; a "
        "deterministic step commits your description to the catalog."
    ),
    "output_schema": {
        "type": "object",
        "properties": {
            "description": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        },
        "required": ["description", "tags"],
        "additionalProperties": False,
    },
}


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    prompt = (
        f"A new item was cataloged: sha256={payload['sha256']}, "
        f"kind={payload['kind']}, catalog id {payload['catalog_id']}. "
        "Describe it and tag it."
    )
    result = run_agent(ctx, SPEC, prompt, _mock)

    # Deterministic commit: fold the agent's proposal into the catalog index.
    entries = index_load(ctx, CATALOG_KEY)
    for e in entries:
        if e.get("sha256") == payload["sha256"]:
            e["summary"] = result["description"]
            detail = dict(e.get("detail") or {})
            detail["tags"] = result["tags"]
            e["detail"] = detail
    index_save(ctx, CATALOG_KEY, entries)

    return record("ingest.enriched@1", {
        "catalog_id": payload["catalog_id"],
        "sha256": payload["sha256"],
        "kind": payload["kind"],
        "description": result["description"],
        "tags": result["tags"],
        "model": result["model"],
        "audit": result["audit"],
    })


def _catalog_via(run):
    """Read the catalog index through the agent's own audited tool call."""
    out = run.call("blob_store", "get", key=CATALOG_KEY)
    if isinstance(out, dict):
        if out.get("text") is not None:
            return json.loads(out["text"])
        if out.get("b64"):
            return json.loads(base64.b64decode(out["b64"]))
    return []


def _mock(run, prompt):
    """Deterministic keyless path: same envelope, same tool calls, no model."""
    sha256 = prompt.split("sha256=", 1)[1].split(",", 1)[0]
    row = next((e for e in _catalog_via(run) if e.get("sha256") == sha256), None)
    if row is None:
        return {"description": "Cataloged item not found.", "tags": []}
    detail = row.get("detail") or {}
    tags = [row["kind"], (row["media_type"] or "").split("/")[-1][:20] or "data"]
    if detail.get("columns"):
        tags += [c["name"][:20].lower() for c in detail["columns"][:3]]
        shape = f"{detail.get('rows', '?')} rows x {len(detail['columns'])} columns"
        desc = (
            f"A {row['kind']} from {row['source_filename']} ({shape}). "
            f"Columns include {', '.join(c['name'] for c in detail['columns'][:6])}. "
            "Suitable as a data source for tabular report sections and charts."
        )
    else:
        desc = (
            f"A {row['kind']} from {row['source_filename']} "
            f"({row['media_type']}). {row['summary']} "
            "Available to report agents as a content-addressed blob."
        )
    return {"description": desc, "tags": sorted(set(t for t in tags if t))[:5]}
