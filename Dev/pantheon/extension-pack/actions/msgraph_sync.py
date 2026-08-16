"""Pull a OneDrive/SharePoint file into the catalog via Microsoft Graph.

The operator registers an Entra app (client-credentials, Files.Read.All)
and enters tenant, client id and secret in Settings; the sync argument is
any OneDrive or SharePoint *sharing link*. The task mints its own
short-lived token at the governed login resource — which is why the graph
resource opts into task-supplied Authorization — then resolves the share
and downloads the file into the ordinary ingest path, where xlsx already
parses.
"""

import base64
import json
import os
import urllib.parse

from _compat import http_request, value_in

import ingest_normalize


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    link = (payload.get("link") or payload.get("path") or "").strip()
    if not link:
        raise ValueError("paste a OneDrive or SharePoint sharing link to sync")

    token = _token(ctx)
    auth = {"Authorization": "Bearer " + token}

    share = "u!" + base64.urlsafe_b64encode(link.encode()).decode().rstrip("=")
    meta_resp = http_request(
        ctx, "msgraph", "GET",
        f"/v1.0/shares/{share}/driveItem?$select=name,size,file", headers=auth)
    if meta_resp["status"] != 200:
        raise RuntimeError(
            f"Graph answered HTTP {meta_resp['status']} for that link — check "
            "that the app has Files.Read.All and the link is a sharing link")
    meta = json.loads(base64.b64decode(meta_resp.get("body_b64") or ""))
    filename = meta.get("name") or "m365-file"
    media = ((meta.get("file") or {}).get("mimeType")
             or "application/octet-stream")

    body = http_request(ctx, "msgraph", "GET",
                        f"/v1.0/shares/{share}/driveItem/content", headers=auth)
    if body["status"] != 200:
        raise RuntimeError(f"Graph refused the download (HTTP {body['status']})")
    data = base64.b64decode(body.get("body_b64") or "")

    return ingest_normalize.run(ctx, {
        "filename": filename,
        "media_type": media,
        "size_bytes": max(len(data), 1),
        "content_b64": base64.b64encode(data).decode("ascii"),
        "requester": payload.get("requester", "unknown"),
        "note": "synced from Microsoft 365",
    })


def _token(ctx) -> str:
    """Client-credentials token from the governed login resource.

    Tenant/client/secret arrive through the runner's environment — the
    settings overlay — so the operator's console entries are the source.
    """
    tenant = os.environ.get("PANTHEON_MS_TENANT", "")
    client = os.environ.get("PANTHEON_MS_CLIENT", "")
    secret = os.environ.get("PANTHEON_MS_SECRET", "")
    if not (tenant and client and secret):
        raise RuntimeError(
            "Microsoft 365 is not configured yet — set the tenant, client id "
            "and secret in Settings (the gear icon) first")
    form = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client,
        "client_secret": secret,
        "scope": "https://graph.microsoft.com/.default",
    })
    resp = http_request(
        ctx, "mslogin", "POST", f"/{tenant}/oauth2/v2.0/token",
        body=form.encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    body = json.loads(base64.b64decode(resp.get("body_b64") or ""))
    if resp["status"] != 200 or "access_token" not in body:
        raise RuntimeError(
            "Microsoft sign-in failed: "
            + str(body.get("error_description") or body.get("error")
                  or f"HTTP {resp['status']}")[:200]
            + " — check the tenant, client id and secret in Settings")
    return body["access_token"]
