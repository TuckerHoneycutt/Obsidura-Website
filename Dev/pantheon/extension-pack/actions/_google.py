"""Shared Google plumbing: the token exchange and link parsing.

One refresh token serves the whole suite. The operator registers an OAuth
client, consents once to the read-only scopes, and pastes the client id,
secret and refresh token into Settings; every Google action exchanges that
refresh token for a short-lived access token at the governed `gauth`
resource and carries the result as a task-supplied Authorization header.

Refresh-token grant rather than a service-account assertion on purpose:
the exchange is a plain form POST, where a service account would need an
RS256-signed JWT and the runner image ships no crypto library (see
runner/requirements.txt — pydantic-ai, polars, httpx). It also covers
personal accounts, which domain-wide delegation does not.
"""

import base64
import csv
import io
import json
import os
import re
import urllib.parse

from _compat import http_request

# Credentials arrive through the runner's environment — the settings
# overlay — so the operator's console entries are the source. Note this is
# the subprocess runner's behavior; the container runner forwards only
# PANTHEON_LLM_* by design, which `token` explains when it comes up empty.
CLIENT_ID = "PANTHEON_GOOGLE_CLIENT_ID"
CLIENT_SECRET = "PANTHEON_GOOGLE_CLIENT_SECRET"
REFRESH_TOKEN = "PANTHEON_GOOGLE_REFRESH_TOKEN"

# `/d/<id>/` covers Docs, Sheets, Slides and Drive file links; `?id=` covers
# the older `open?id=` and `uc?id=` download forms. Folder links are matched
# too — not because a folder can be synced, but so the caller is told that
# in plain words instead of "this is not a Drive link".
_ID_IN_PATH = re.compile(r"/d/([A-Za-z0-9_-]{10,})")
_ID_IN_FOLDER = re.compile(r"/folders/([A-Za-z0-9_-]{10,})")
_ID_IN_QUERY = re.compile(r"[?&]id=([A-Za-z0-9_-]{10,})")
_BARE_ID = re.compile(r"^[A-Za-z0-9_-]{20,}$")


def token(ctx) -> str:
    """A short-lived access token, minted at the governed login resource."""
    client = os.environ.get(CLIENT_ID, "")
    secret = os.environ.get(CLIENT_SECRET, "")
    refresh = os.environ.get(REFRESH_TOKEN, "")
    if not (client and secret and refresh):
        raise RuntimeError(
            "Google is not configured yet — set the client id, client secret "
            "and refresh token in Settings (the gear icon) first. If they are "
            "already set, this run is under the container runner, which "
            "forwards no connector credentials to task bodies; use the "
            "subprocess runner for Google syncs")
    form = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "client_id": client,
        "client_secret": secret,
        "refresh_token": refresh,
    })
    resp = http_request(
        ctx, "gauth", "POST", "/token",
        body=form.encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    body = json.loads(base64.b64decode(resp.get("body_b64") or "") or b"{}")
    if resp["status"] != 200 or "access_token" not in body:
        raise RuntimeError(
            "Google sign-in failed: "
            + str(body.get("error_description") or body.get("error")
                  or f"HTTP {resp['status']}")[:200]
            + " — reconnect Google in Settings. A refresh token stops working "
              "if it goes six months unused, if the account password changed, "
              "or if the OAuth client is still in testing mode (seven days)")
    return body["access_token"]


def file_id_from_link(link: str) -> str:
    """The Drive file id inside a pasted browser URL, or "" if there is none."""
    link = (link or "").strip()
    for pattern in (_ID_IN_PATH, _ID_IN_FOLDER, _ID_IN_QUERY):
        found = pattern.search(link)
        if found:
            return found.group(1)
    return link if _BARE_ID.match(link) else ""


def explain(status: int, what: str, scope: str = "Drive") -> str:
    """Google's refusals in the operator's language, not the wire's."""
    if status in (401, 403):
        return (f"Google refused access to {what} (HTTP {status}) — check that "
                f"the refresh token carries the {scope} read scope, and that "
                "the account that authorized Pantheon can see it")
    if status == 404:
        return (f"Google has no {what} there (HTTP 404) — check the link or "
                "name, and that it is visible to the account that authorized "
                "Pantheon")
    return f"Google refused {what} (HTTP {status})"


def rows_to_csv(header: list, rows: list) -> bytes:
    """Rows (lists of cells) as CSV bytes for the ingest path's table branch."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    for row in rows:
        writer.writerow(["" if cell is None else cell for cell in row])
    return out.getvalue().encode("utf-8")


def get_json(ctx, resource: str, path: str, auth: dict, what: str,
             scope: str = "Drive") -> dict:
    """One authorized GET, decoded, with refusals explained."""
    resp = http_request(ctx, resource, "GET", path, headers=auth)
    if resp["status"] != 200:
        raise RuntimeError(explain(resp["status"], what, scope))
    return json.loads(base64.b64decode(resp.get("body_b64") or "") or b"{}")
