"""Every assumption about the runner shim's ctx API lives in this file.

RECONCILED against prototypev1's real connectors (crates/executor/src/
connectors.rs) and shim (runner/shim.py):

- ctx.resource(name).verb(**args)     JSON-RPC to the UDS proxy (verified)
- postgres query(sql=, params=[])  -> {"row_count": N, "rows": [dict, ...]}
- s3 get(key=)                     -> {"file": handle, "b64"?: str, "text"?: str}
- s3 put(key=, b64=, media_type=)  -> {"etag": ...}
- http request(method=, path=, body_b64=?) -> {"status", "headers", "body_b64"|"file"}
- ctx.blob_get(hash) / ctx.blob_put(data, media_type) -> handle dict

The devserver mock implements these same shapes, so action bodies are
byte-identical between the harness and the real engine.
"""

import base64
import hashlib
import json


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def value_in(payload):
    """Unwrap a kernel Record value into its data dict.

    Engine seams carry kernel values ({"kind": "record", "type_ref", "data"});
    the harness passes plain dicts. Tolerating both keeps bodies identical.
    """
    if isinstance(payload, dict) and payload.get("kind") == "record":
        return payload.get("data") or {}
    return payload


def record(type_ref: str, data: dict) -> dict:
    """Wrap a data dict as the kernel Record value the executor validates."""
    return {"kind": "record", "type_ref": type_ref, "data": data}


# --- the catalog and web registry as blob-store index objects ---------------
# The engine's postgres connector runs read-only transactions (write safety
# is the design posture), so mutable state lives as JSON objects in the blob
# store: every read and write crosses the proxy under the caller's grant and
# lands in the audit log.

CATALOG_KEY = "ingest/catalog.json"
REGISTRY_KEY = "web/registry.json"


def index_load(ctx, key) -> list:
    try:
        return json.loads(blob_get(ctx, key).decode("utf-8"))
    except Exception:
        return []


def index_save(ctx, key, entries: list) -> None:
    blob_put(ctx, key, json.dumps(entries).encode("utf-8"), "application/json")


def index_upsert(entries: list, match_key: str, entry: dict) -> list:
    kept = [e for e in entries if e.get(match_key) != entry.get(match_key)]
    return kept + [entry]


def blob_put(ctx, key: str, data: bytes, media_type="application/octet-stream") -> None:
    ctx.resource("blob_store").put(
        key=key, b64=base64.b64encode(data).decode("ascii"), media_type=media_type
    )


def blob_get(ctx, key: str) -> bytes:
    out = ctx.resource("blob_store").get(key=key)
    if isinstance(out, str):  # tolerate a bare-b64 stand-in
        return base64.b64decode(out)
    if out.get("b64"):
        return base64.b64decode(out["b64"])
    if out.get("text") is not None:
        return out["text"].encode("utf-8")
    handle = out.get("file") or {}
    return ctx.blob_get(handle.get("blob"))  # too large to inline


def db_query(ctx, resource: str, sql: str, params=None):
    """Rows as a list of dicts, whatever the connector wrapped them in."""
    args = {"sql": sql}
    if params is not None:
        args["params"] = params
    out = ctx.resource(resource).query(**args)
    return out.get("rows", []) if isinstance(out, dict) else out


def http_request(ctx, resource: str, method: str, url: str, body=None):
    """Normalized: {"status": int, "media_type": str, "body_b64": str}.

    The real connector returns {status, headers, body_b64|file}; the media
    type rides in the headers. Oversized bodies come back as a blob handle
    and are redeemed through ctx.blob_get.
    """
    kwargs = {"method": method, "path": url}
    if body is not None:
        kwargs["body_b64"] = base64.b64encode(
            body if isinstance(body, bytes) else str(body).encode()
        ).decode("ascii")
    out = ctx.resource(resource).request(**kwargs)
    headers = out.get("headers") or {}
    media = out.get("media_type") or _header(headers, "content-type") \
        or "application/octet-stream"
    body_b64 = out.get("body_b64")
    if body_b64 is None and out.get("file"):
        body_b64 = base64.b64encode(ctx.blob_get(out["file"].get("blob"))).decode()
    return {"status": out.get("status"), "media_type": media.split(";")[0].strip(),
            "body_b64": body_b64 or ""}


def _header(headers, name):
    for k, v in headers.items():
        if k.lower() == name:
            return v if isinstance(v, str) else (v[0] if v else None)
    return None


def sql_quote(value) -> str:
    """Single-quote a literal for inline SQL, doubling embedded quotes.

    The real connector supports bound `params` — prefer db_query(..., params=)
    for new code; this stays for the statements built before that was known.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        value = json.dumps(value)
    return "'" + str(value).replace("'", "''") + "'"


def envelope_ts(ctx) -> str:
    """ISO timestamp for provenance fields, from the run envelope."""
    return ctx.envelope["ts"]


def requester(ctx, payload: dict) -> str:
    return payload.get("requester") or ctx.envelope.get("producer", "unknown")
