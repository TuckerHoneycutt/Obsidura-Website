"""Pull a file from the operator's NAS into the catalog (ingest.result@1).

The NAS is any S3-compatible store — Synology, QNAP, TrueNAS, MinIO —
whose endpoint, bucket and keys the operator enters in Settings; the
resource definition names the settings, never the host. The pulled bytes
ride the ordinary ingest path, so spreadsheets parse, tables profile, and
quality is audited exactly as if the file had been dropped on the console.
"""

import base64
import mimetypes
import posixpath

from _compat import object_get, value_in

import ingest_normalize


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    path = (payload.get("path") or "").strip().lstrip("/")
    if not path:
        raise ValueError("say which object to pull — a key like reports/q3.xlsx")

    data = object_get(ctx, "nas", path)
    filename = posixpath.basename(path) or "nas-file"
    media = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    return ingest_normalize.run(ctx, {
        "filename": filename,
        "media_type": media,
        "size_bytes": max(len(data), 1),
        "content_b64": base64.b64encode(data).decode("ascii"),
        "requester": payload.get("requester", "unknown"),
        "note": f"synced from NAS object {path}",
    })
