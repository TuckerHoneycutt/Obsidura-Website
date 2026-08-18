"""Save (or remove) a Google sync recipe for the morning refresh.

Same configuration-as-data shape as the brief's schedule: a JSON index in
the blob store, written through the proxy under the caller's grant. The
06:30 tick reads this list and re-runs each recipe, so a Sheet or a Gmail
search stays current instead of being a snapshot of the day it was pasted.

Idempotent on (requester, source, arg) — saving the same recipe twice is
one entry — and the id is that same hash, so removal needs no other key.
"""

import hashlib

from _compat import envelope_ts, index_load, index_save, record, requester, value_in

SYNC_SCHEDULES_KEY = "config/sync-schedules.json"
MAX_SYNC_SCHEDULES = 12

# The doors the refresher knows how to reopen (drive is the pasted-link door).
SOURCES = ("drive", "gmail", "gcal", "bigquery", "gcs")


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    entries = index_load(ctx, SYNC_SCHEDULES_KEY)

    remove = (payload.get("remove") or "").strip()
    if remove:
        kept = [e for e in entries if e.get("id") != remove]
        if len(kept) != len(entries):
            index_save(ctx, SYNC_SCHEDULES_KEY, kept)
        return record("sync.scheduled@1", {
            "action": "removed", "id": remove, "count": len(kept),
        })

    source = (payload.get("source") or "").strip()
    if source not in SOURCES:
        raise ValueError(
            "say which door to refresh — one of: " + ", ".join(SOURCES))
    arg = (payload.get("arg") or "").strip()
    if source in ("drive", "bigquery", "gcs") and not arg:
        raise ValueError(
            "this door needs its argument saved with it — the link, the "
            "query, or the object path")

    who = requester(ctx, payload)
    sid = hashlib.sha256(f"{who}|{source}|{arg.lower()}".encode()).hexdigest()[:10]
    if not any(e.get("id") == sid for e in entries):
        if len(entries) >= MAX_SYNC_SCHEDULES:
            raise ValueError(
                f"the refresh list is full ({MAX_SYNC_SCHEDULES}) — remove one first")
        entries.append({
            "id": sid,
            "source": source,
            "arg": arg,
            "requester": who,
            "created_at": envelope_ts(ctx),
        })
        index_save(ctx, SYNC_SCHEDULES_KEY, entries)

    return record("sync.scheduled@1", {
        "action": "saved", "id": sid, "count": len(entries),
    })
