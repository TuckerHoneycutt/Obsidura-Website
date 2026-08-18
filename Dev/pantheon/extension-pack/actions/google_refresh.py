"""The morning refresh: re-run every saved Google sync recipe.

Fires at 06:30 UTC — deliberately before the 07:00 brief, so the brief
reads data synced this morning, not yesterday's. The cron packet carries
only a timestamp; everything else lives in the sync-schedule index the
clock buttons write.

Composition is in-process, the house pattern: each recipe calls its
phase-2 action body, then catalog_register, the way a manual sync's
then-chain would — minus the agent_describe hop, so a refreshed file
keeps a deterministic summary until someone syncs it by hand. One dead
recipe (a revoked token, a deleted Sheet) is recorded and skipped; the
rest of the list still runs. Re-synced bytes that didn't change upsert
into the same catalog row — no churn, and "added" reads as "last synced".
"""

from _compat import record, index_load, value_in

import bigquery_sync
import catalog_register
import gcal_sync
import gcs_sync
import gmail_sync
import google_sync
from sync_schedule_add import SYNC_SCHEDULES_KEY

RUNNERS = {
    "drive": (google_sync, "link"),
    "gmail": (gmail_sync, "query"),
    "gcal": (gcal_sync, "range"),
    "bigquery": (bigquery_sync, "sql"),
    "gcs": (gcs_sync, "path"),
}


def run(ctx, payload: dict) -> dict:
    value_in(payload)  # the tick packet: {"ts"} — nothing to read but proof of shape
    entries = index_load(ctx, SYNC_SCHEDULES_KEY)
    ran, failed, notes = 0, 0, []

    for e in entries:
        source = e.get("source", "")
        runner = RUNNERS.get(source)
        if not runner:
            failed += 1
            notes.append(f"{e.get('id')}: unknown door {source!r}")
            continue
        action, arg_key = runner
        try:
            result = action.run(ctx, {
                "requester": e.get("requester", "unknown"),
                arg_key: e.get("arg", ""),
            })
            catalog_register.run(ctx, result)
            ran += 1
        except Exception as exc:  # one dead recipe must not kill the rest
            failed += 1
            notes.append(f"{source} ({e.get('id')}): {str(exc)[:160]}")

    return record("sync.refreshed@1", {
        "ran": ran,
        "failed": failed,
        "notes": "; ".join(notes)[:1000],
    })
