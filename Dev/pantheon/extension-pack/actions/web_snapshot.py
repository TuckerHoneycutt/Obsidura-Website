"""Snapshot-on-curation (Appendix B.1): admit a URL to the registry.

Fetch once through the proxy (grant allowlist enforced there), content-hash
the bytes into the blob store, record provenance in the web registry — a
JSON index object in the blob store (the engine's postgres connector is
read-only by design). A fetch failure is recorded, not raised.
"""

import base64

from _compat import (REGISTRY_KEY, blob_put, envelope_ts, http_request,
                     index_load, index_save, index_upsert, record,
                     sha256_hex, value_in)


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    name, url = payload["name"], payload["url"]
    snapshot = {"name": name, "url": url, "fetched_at": envelope_ts(ctx)}

    try:
        resp = http_request(ctx, "web", "GET", url)
        if resp["status"] >= 400:
            raise RuntimeError(f"HTTP {resp['status']}")
        data = base64.b64decode(resp["body_b64"])
        media_type = resp.get("media_type") or "application/octet-stream"
    except Exception as exc:
        snapshot.update(status="failed", error=str(exc)[:500])
        _register(ctx, payload, snapshot)
        return record("web.snapshot@1", snapshot)

    digest = sha256_hex(data)
    blob_key = f"web/snapshots/{digest}"
    blob_put(ctx, blob_key, data, media_type)
    snapshot.update(status="ok", sha256=digest, media_type=media_type, blob_key=blob_key)
    _register(ctx, payload, snapshot)
    return record("web.snapshot@1", snapshot)


def _register(ctx, payload: dict, snapshot: dict) -> None:
    entries = index_load(ctx, REGISTRY_KEY)
    entry = {
        "name": snapshot["name"],
        "url": snapshot["url"],
        "purpose": payload["purpose"],
        "requester": payload["requester"],
        "status": snapshot["status"],
        "sha256": snapshot.get("sha256"),
        "media_type": snapshot.get("media_type"),
        "blob_key": snapshot.get("blob_key"),
        "last_error": snapshot.get("error"),
        "fetched_at": snapshot["fetched_at"],
        "live": None,
        "last_checked": None,
    }
    index_save(ctx, REGISTRY_KEY, index_upsert(entries, "name", entry))
