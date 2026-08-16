"""One person's workspace, as a JSON file the console can render.

The catalog and schedule indexes live in the blob store behind the proxy,
so the page can't read them directly; this task reads them under the
caller's grant, narrows to their workspace (the same requester rule every
other surface uses), and returns the summary as a kernel File. Reading
your own workspace is itself a governed, audited run — which is the point.
"""

import json

from _compat import CATALOG_KEY, index_load, requester, value_in
from schedule_add import SCHEDULES_KEY


def run(ctx, payload: dict) -> dict:
    payload = value_in(payload)
    who = requester(ctx, payload)

    files = []
    for e in index_load(ctx, CATALOG_KEY):
        if e.get("requester") not in (who, None, "", "unknown"):
            continue
        detail = e.get("detail") or {}
        files.append({
            "filename": e.get("source_filename") or "unnamed",
            "kind": e.get("kind") or "data",
            "rows": detail.get("rows"),
            "columns": len(detail.get("columns") or []),
            "quality_issues": (detail.get("quality") or {}).get("issues") or [],
            "tags": detail.get("tags") or [],
            "added": (e.get("created_at") or "")[:10],
            "summary": (e.get("summary") or "")[:240],
        })
    files.sort(key=lambda f: f["added"], reverse=True)

    schedules = [
        {"prompt": s.get("prompt") or "", "created": (s.get("created_at") or "")[:10]}
        for s in index_load(ctx, SCHEDULES_KEY)
        if s.get("requester") in (who, None, "", "unknown")
    ]

    doc = {"user": who, "files": files, "schedules": schedules}
    return {"kind": "file",
            **ctx.blob_put(json.dumps(doc).encode("utf-8"), "application/json")}
