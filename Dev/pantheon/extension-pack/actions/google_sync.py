"""Pull a Drive file — or a Sheet or Doc — into the catalog.

The sync argument is whatever the browser had in its address bar: a Drive
file link, a Sheets link, a Docs link. Native Google formats have no bytes
to download, so they are *exported*: a Sheet becomes CSV and lands in the
ingest path's tabular branch with real columns, dtypes and a quality audit;
a Doc becomes markdown for the freeform designer. Everything else — an
uploaded csv, pdf, image — downloads as itself.

Exporting a Sheet to CSV is the reason this connector is cleaner than the
Microsoft one: no spreadsheet parsing is involved at all, where xlsx needs
openpyxl, which the runner image does not ship.
"""

import base64
import json
import urllib.parse

from _compat import http_request, value_in

import ingest_normalize
from _google import explain, file_id_from_link, token

FOLDER = "application/vnd.google-apps.folder"

# What each native Google format is asked for on the way out, and the
# suffix that makes the ingest path recognize it.
EXPORTS = {
    "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
    "application/vnd.google-apps.document": ("text/markdown", ".md"),
    "application/vnd.google-apps.presentation": ("text/plain", ".txt"),
    "application/vnd.google-apps.drawing": ("image/png", ".png"),
}

# A Drive link can point at a video as easily as a spreadsheet. The cap is
# not the wire's — the connector spills large bodies to the blob store — it
# is a courtesy, so a mis-pasted link fails in a second rather than a minute.
MAX_SYNC_BYTES = 25 * 1024 * 1024


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    link = (payload.get("link") or payload.get("path") or "").strip()
    if not link:
        raise ValueError("paste a Google Drive, Sheets or Docs link to sync")
    file_id = file_id_from_link(link)
    if not file_id:
        raise ValueError(
            "that does not look like a Drive link — paste the address bar of "
            "the file, e.g. https://docs.google.com/spreadsheets/d/<id>/edit")

    auth = {"Authorization": "Bearer " + token(ctx)}

    meta_resp = http_request(
        ctx, "gdrive", "GET",
        f"/drive/v3/files/{file_id}"
        "?fields=name,mimeType,size&supportsAllDrives=true",
        headers=auth)
    if meta_resp["status"] != 200:
        raise RuntimeError(explain(meta_resp["status"], "that file"))
    meta = json.loads(base64.b64decode(meta_resp.get("body_b64") or "") or b"{}")

    mime = meta.get("mimeType") or "application/octet-stream"
    name = meta.get("name") or "google-file"
    if mime == FOLDER:
        raise ValueError(
            f"{name} is a folder — paste a link to a single file (folder sync "
            "is not here yet)")

    # Native formats carry no size; only an uploaded file has one to check.
    size = int(meta.get("size") or 0)
    if size > MAX_SYNC_BYTES:
        raise ValueError(
            f"{name} is {size // (1024 * 1024)} MB — this door takes files up "
            f"to {MAX_SYNC_BYTES // (1024 * 1024)} MB for now")

    if mime in EXPORTS:
        media, suffix = EXPORTS[mime]
        path = (f"/drive/v3/files/{file_id}/export"
                f"?mimeType={urllib.parse.quote(media, safe='')}")
        if not name.lower().endswith(suffix):
            name += suffix
    else:
        media = mime
        path = f"/drive/v3/files/{file_id}?alt=media&supportsAllDrives=true"

    body = http_request(ctx, "gdrive", "GET", path, headers=auth)
    if body["status"] != 200:
        raise RuntimeError(explain(body["status"], f"the download of {name}"))
    data = base64.b64decode(body.get("body_b64") or "")
    if not data:
        raise RuntimeError(f"{name} came back empty — nothing to catalog")

    return ingest_normalize.run(ctx, {
        "filename": name,
        "media_type": media,
        "size_bytes": max(len(data), 1),
        "content_b64": base64.b64encode(data).decode("ascii"),
        "requester": payload.get("requester", "unknown"),
        # Load-bearing: workspace_snapshot._source_of reads this phrase back
        # to attribute the file to the Google connection.
        "note": "synced from Google Drive",
    })
