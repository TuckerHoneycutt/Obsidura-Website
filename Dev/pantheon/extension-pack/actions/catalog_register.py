"""Register a normalized ingest result in the catalog (ingest.cataloged@1).

The catalog is a JSON index object in the blob store (ingest/catalog.json):
the engine's postgres connector is read-only by design, so mutable state
crosses the proxy as blob get/put — audited like every other call. The row
is what makes ingested data discoverable to the answer agent. Idempotent on
sha256: re-uploading the same bytes replaces the entry.
"""

from _compat import (CATALOG_KEY, envelope_ts, index_load, index_save,
                     index_upsert, record, value_in)


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    entries = index_load(ctx, CATALOG_KEY)
    entry = {
        "id": payload["sha256"][:12],
        "sha256": payload["sha256"],
        "requester": payload.get("requester", "unknown"),
        "kind": payload["kind"],
        "media_type": payload["media_type"],
        "source_filename": payload["source_filename"],
        "summary": payload["summary"],
        "detail": payload.get("table") or payload.get("file") or payload.get("record") or {},
        "created_at": envelope_ts(ctx),
    }
    index_save(ctx, CATALOG_KEY, index_upsert(entries, "sha256", entry))
    return record("ingest.cataloged@1", {
        "catalog_id": entry["id"],
        "sha256": payload["sha256"],
        "kind": payload["kind"],
    })
