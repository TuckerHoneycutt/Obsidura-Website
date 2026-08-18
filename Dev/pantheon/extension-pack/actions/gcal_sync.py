"""Pull a window of the primary calendar into the catalog.

The sync argument is a date range — `2026-07-01..2026-09-30` — or nothing,
which means the surrounding quarter: thirty days back, sixty forward from
the run's own timestamp (the envelope's, so a rerun of the same run reads
the same window). One row per event: start, end, title, who called it,
who came, where. Meeting-load questions and delivery reports read it the
same way they read a sprint export.
"""

import base64
import re
import urllib.parse

from _compat import envelope_ts, value_in

import ingest_normalize
from _google import get_json, rows_to_csv, token

_RANGE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s*\.\.\s*(\d{4}-\d{2}-\d{2})$")
DEFAULT_LIMIT = 250

HEADER = ["start", "end", "summary", "organizer", "attendees", "location", "status"]


def _window(payload: dict, ts: str) -> tuple:
    given = (payload.get("range") or "").strip()
    if given:
        m = _RANGE.match(given)
        if not m:
            raise ValueError(
                "write the range as two dates — e.g. 2026-07-01..2026-09-30")
        return m.group(1), m.group(2)
    # The surrounding quarter, anchored to the run envelope's day. Purely
    # arithmetic on the date string — no clock reads in an action body.
    day = ts[:10]
    year, month = int(day[:4]), int(day[5:7])
    lo_m, lo_y = (month - 1, year) if month > 1 else (12, year - 1)
    hi_m, hi_y = (month + 2, year) if month <= 10 else (month - 10, year + 1)
    return f"{lo_y:04d}-{lo_m:02d}-01", f"{hi_y:04d}-{hi_m:02d}-01"


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    lo, hi = _window(payload, envelope_ts(ctx))
    limit = min(int(payload.get("limit") or DEFAULT_LIMIT), 500)

    auth = {"Authorization": "Bearer " + token(ctx)}

    rows: list = []
    page_token = ""
    while len(rows) < limit:
        params = {
            "timeMin": f"{lo}T00:00:00Z",
            "timeMax": f"{hi}T00:00:00Z",
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": str(min(250, limit - len(rows))),
        }
        if page_token:
            params["pageToken"] = page_token
        listing = get_json(
            ctx, "gcalendar",
            "/calendar/v3/calendars/primary/events?"
            + urllib.parse.urlencode(params),
            auth, "the calendar", scope="Calendar")
        for ev in listing.get("items") or []:
            start = ev.get("start") or {}
            end = ev.get("end") or {}
            rows.append([
                start.get("dateTime") or start.get("date") or "",
                end.get("dateTime") or end.get("date") or "",
                ev.get("summary", ""),
                (ev.get("organizer") or {}).get("email", ""),
                " ".join(a.get("email", "")
                         for a in (ev.get("attendees") or [])[:20]),
                ev.get("location", ""),
                ev.get("status", ""),
            ])
        page_token = listing.get("nextPageToken") or ""
        if not page_token:
            break

    if not rows:
        raise RuntimeError(
            f"the calendar has nothing between {lo} and {hi} — widen the range")

    return ingest_normalize.run(ctx, {
        "filename": "calendar-events.csv",
        "media_type": "text/csv",
        "size_bytes": 1,
        "content_b64": base64.b64encode(rows_to_csv(HEADER, rows)).decode("ascii"),
        "requester": payload.get("requester", "unknown"),
        "note": f"synced from Google Calendar — {lo} to {hi}",
    })
