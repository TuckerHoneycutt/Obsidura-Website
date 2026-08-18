"""Pull an object from Google Cloud Storage into the catalog.

The sync argument is `gs://bucket/path/to/object`, or a bare object path
against the default bucket from Settings. The JSON API keeps this on the
same OAuth credential as the rest of the suite — one consent, one refresh
token — where the S3-interop route would mean minting HMAC keys just for
this connector.

Object names ride in the URL path, so they are percent-encoded whole:
`reports/q3.csv` is one path segment (`reports%2Fq3.csv`) to the API.
"""

import base64
import os
import urllib.parse

from _compat import http_request, value_in

import ingest_normalize
from _google import explain, get_json, token

MAX_SYNC_BYTES = 25 * 1024 * 1024


def _target(payload: dict) -> tuple:
    path = (payload.get("path") or payload.get("link") or "").strip()
    if not path:
        raise ValueError(
            "name the object to pull — gs://bucket/key, or a key in the "
            "default bucket")
    if path.startswith("gs://"):
        rest = path[len("gs://"):]
        bucket, _, key = rest.partition("/")
        if not (bucket and key):
            raise ValueError(
                "a gs:// path needs both halves — gs://bucket/path/to/object")
        return bucket, key
    bucket = os.environ.get("PANTHEON_GCS_BUCKET", "")
    if not bucket:
        raise RuntimeError(
            "no bucket named — use gs://bucket/key, or set the default "
            "Cloud Storage bucket in Settings (the gear icon) first")
    return bucket, path


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    bucket, key = _target(payload)
    quoted = urllib.parse.quote(key, safe="")

    auth = {"Authorization": "Bearer " + token(ctx)}
    meta = get_json(
        ctx, "gstorage",
        f"/storage/v1/b/{bucket}/o/{quoted}",
        auth, f"gs://{bucket}/{key}", scope="Cloud Storage")

    size = int(meta.get("size") or 0)
    if size > MAX_SYNC_BYTES:
        raise ValueError(
            f"gs://{bucket}/{key} is {size // (1024 * 1024)} MB — this door "
            f"takes objects up to {MAX_SYNC_BYTES // (1024 * 1024)} MB for now")

    body = http_request(
        ctx, "gstorage", "GET",
        f"/storage/v1/b/{bucket}/o/{quoted}?alt=media",
        headers=auth)
    if body["status"] != 200:
        raise RuntimeError(
            explain(body["status"], f"gs://{bucket}/{key}", scope="Cloud Storage"))
    data = base64.b64decode(body.get("body_b64") or "")
    if not data:
        raise RuntimeError(f"gs://{bucket}/{key} came back empty — nothing to catalog")

    return ingest_normalize.run(ctx, {
        "filename": key.rsplit("/", 1)[-1] or "gcs-object",
        "media_type": meta.get("contentType") or "application/octet-stream",
        "size_bytes": max(len(data), 1),
        "content_b64": base64.b64encode(data).decode("ascii"),
        "requester": payload.get("requester", "unknown"),
        "note": f"synced from Google Cloud Storage — gs://{bucket}/{key}",
    })
