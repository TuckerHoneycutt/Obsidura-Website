"""Liveness check over the web registry (Appendix B.2), fired by cron.

A Pantheon workflow, not a subsystem: read the registry index, probe each
non-retired entry through the proxy, write statuses back, emit a
web.status@1 record. Per-entry failures are results, never task failures.
"""

from _compat import (REGISTRY_KEY, envelope_ts, http_request, index_load,
                     index_save, record, value_in)


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    entries = index_load(ctx, REGISTRY_KEY)

    failed = []
    checked = 0
    for entry in entries:
        if entry.get("status") == "retired":
            continue
        checked += 1
        try:
            resp = http_request(ctx, "web", "GET", entry["url"])
            if resp["status"] >= 400:
                raise RuntimeError(f"HTTP {resp['status']}")
            entry["live"] = True
            entry["last_error"] = None
        except Exception as exc:
            entry["live"] = False
            entry["last_error"] = str(exc)[:500]
            failed.append({"name": entry["name"], "url": entry["url"],
                           "error": entry["last_error"]})
        entry["last_checked"] = envelope_ts(ctx)

    index_save(ctx, REGISTRY_KEY, entries)
    return record("web.status@1",
                  {"checked": checked, "ok": checked - len(failed), "failed": failed})
