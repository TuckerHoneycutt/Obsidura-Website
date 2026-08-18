"""Pull a Gmail search into the catalog as a table of messages.

The sync argument is an ordinary Gmail search — `from:stripe
newer_than:90d`, `label:receipts`, anything the search box takes — and the
result is one row per message: date, sender, recipients, subject, snippet,
labels. That shape feeds Ask ("what did legal say about the lease?") and
the delivery-style reports without pretending to be a mail client: bodies
stay in Gmail; the catalog holds the ledger of who said what, when.

Two API shapes worth knowing: the list endpoint returns ids only, so each
message costs a second, metadata-format call — which is why `limit` is
capped and conservative — and both endpoints paginate with pageToken.
"""

import base64
import urllib.parse

from _compat import http_request, value_in

import ingest_normalize
from _google import get_json, rows_to_csv, token

DEFAULT_QUERY = "newer_than:30d"
DEFAULT_LIMIT = 100
PAGE = 100  # the list endpoint's own page ceiling is 500; metadata calls gate us

HEADER = ["date", "from", "to", "subject", "snippet", "labels"]


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    query = (payload.get("query") or "").strip() or DEFAULT_QUERY
    limit = min(int(payload.get("limit") or DEFAULT_LIMIT), 500)

    auth = {"Authorization": "Bearer " + token(ctx)}

    # ids first, paginated…
    ids: list = []
    page_token = ""
    while len(ids) < limit:
        params = {"q": query, "maxResults": str(min(PAGE, limit - len(ids)))}
        if page_token:
            params["pageToken"] = page_token
        listing = get_json(
            ctx, "gmail",
            "/gmail/v1/users/me/messages?" + urllib.parse.urlencode(params),
            auth, "that Gmail search", scope="Gmail")
        ids.extend(m["id"] for m in listing.get("messages") or [])
        page_token = listing.get("nextPageToken") or ""
        if not page_token:
            break

    # …then one metadata call per message.
    rows = []
    for mid in ids[:limit]:
        msg = get_json(
            ctx, "gmail",
            f"/gmail/v1/users/me/messages/{mid}"
            "?format=metadata&metadataHeaders=From&metadataHeaders=To"
            "&metadataHeaders=Subject&metadataHeaders=Date",
            auth, "a message in that search", scope="Gmail")
        headers = {h["name"].lower(): h.get("value", "")
                   for h in (msg.get("payload") or {}).get("headers") or []}
        rows.append([
            headers.get("date", ""),
            headers.get("from", ""),
            headers.get("to", ""),
            headers.get("subject", ""),
            msg.get("snippet", ""),
            " ".join(msg.get("labelIds") or []),
        ])

    if not rows:
        raise RuntimeError(
            f"Gmail found nothing for “{query}” — try a broader search, "
            "e.g. newer_than:90d")

    return ingest_normalize.run(ctx, {
        "filename": "gmail-messages.csv",
        "media_type": "text/csv",
        "size_bytes": 1,
        "content_b64": base64.b64encode(rows_to_csv(HEADER, rows)).decode("ascii"),
        "requester": payload.get("requester", "unknown"),
        "note": f"synced from Gmail — search: {query}",
    })
