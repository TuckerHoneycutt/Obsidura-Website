"""Save a prompt to the morning-brief schedule (schedule.added@1).

Schedules are configuration-as-data: a JSON index object in the blob store
(config/schedules.json), written through the proxy under the caller's grant
like every other piece of mutable state. The brief task reads this list on
each tick; adding here is idempotent on the prompt text.
"""

import hashlib

from _compat import envelope_ts, index_load, index_save, record, requester, value_in

SCHEDULES_KEY = "config/schedules.json"
MAX_SCHEDULES = 12


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("a schedule needs a prompt")

    entries = index_load(ctx, SCHEDULES_KEY)
    sid = hashlib.sha256(prompt.lower().encode()).hexdigest()[:10]
    if not any(e.get("id") == sid for e in entries):
        if len(entries) >= MAX_SCHEDULES:
            raise ValueError(
                f"schedule list is full ({MAX_SCHEDULES}) — remove one first")
        entries.append({
            "id": sid,
            "prompt": prompt,
            "requester": requester(ctx, payload),
            "created_at": envelope_ts(ctx),
        })
        index_save(ctx, SCHEDULES_KEY, entries)

    return record("schedule.added@1", {
        "id": sid,
        "prompt": prompt,
        "count": len(entries),
    })
