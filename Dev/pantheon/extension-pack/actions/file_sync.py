"""Pull a file from a direct URL into the catalog (ingest.result@1).

For hosts that hand out pre-authorized links — an Azure Blob SAS URL, a
presigned S3 link, any static file host. The operator sets the base URL in
Settings (the credential, if any, rides in the link's own query string);
the sync argument is the path under it. Bytes ride the ordinary ingest
path: spreadsheets parse, tables profile, quality is audited.
"""

import base64
import mimetypes
import posixpath
import urllib.parse

from _compat import http_request, value_in

import ingest_normalize


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    path = (payload.get("path") or "").strip()
    if not path:
        raise ValueError("say which file to pull — a path under the configured base URL")

    resp = http_request(ctx, "webfile", "GET", "/" + path.lstrip("/"))
    if resp["status"] != 200:
        raise RuntimeError(
            f"the file host answered HTTP {resp['status']} — check the base "
            "URL in Settings and the path (for SAS links, include the token)")
    data = base64.b64decode(resp.get("body_b64") or "")

    clean = urllib.parse.urlparse(path).path
    filename = posixpath.basename(clean) or "pulled-file"
    media = (mimetypes.guess_type(filename)[0]
             or resp.get("media_type")
             or "application/octet-stream")

    return ingest_normalize.run(ctx, {
        "filename": filename,
        "media_type": media,
        "size_bytes": max(len(data), 1),
        "content_b64": base64.b64encode(data).decode("ascii"),
        "requester": payload.get("requester", "unknown"),
        "note": "synced from a direct link",
    })
