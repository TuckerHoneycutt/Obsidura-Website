"""Stand-in for the executor's run-scoped resource proxy, for local dev only.

The action bodies are the real ones from ../actions; only the runtime is
mocked: catalog_db -> SQLite, blob_store -> a local folder, web -> real HTTP
behind a grant-style URL allowlist. The pg-only cast suffixes (::jsonb etc.)
are stripped for SQLite; the actions themselves stay byte-identical to what
ships against the real prototype.
"""

import base64
import json
import re
import sqlite3
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).parent / "data"
BLOBS = DATA / "blobs"
DB = DATA / "catalog.db"
ALLOWLIST_FILE = DATA / "allowlist.json"

# The mock's grant scope for the `web` resource, prefix-matched like the
# real proxy's URL allowlist. Editable at runtime (the UI's "grant" editor
# writes allowlist.json); refusals surface as failed runs, like the proxy.
DEFAULT_ALLOWLIST = (
    "https://api.frankfurter.dev/",
    "https://raw.githubusercontent.com/",
    "https://en.wikipedia.org/",
)


def allowlist():
    if ALLOWLIST_FILE.exists():
        return tuple(json.loads(ALLOWLIST_FILE.read_text()))
    return DEFAULT_ALLOWLIST


def set_allowlist(urls):
    DATA.mkdir(parents=True, exist_ok=True)
    ALLOWLIST_FILE.write_text(json.dumps(sorted(set(urls)), indent=2))

DDL = """
CREATE TABLE IF NOT EXISTS ingest_catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256 TEXT NOT NULL UNIQUE,
    requester TEXT NOT NULL,
    kind TEXT NOT NULL,
    media_type TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    summary TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS web_registry (
    name TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    purpose TEXT NOT NULL,
    requester TEXT NOT NULL,
    status TEXT NOT NULL,
    sha256 TEXT,
    media_type TEXT,
    blob_key TEXT,
    detail TEXT NOT NULL DEFAULT '{}',
    fetched_at TEXT,
    last_checked TEXT,
    live BOOLEAN,
    last_error TEXT
);
"""

_db_lock = threading.Lock()


def _connect():
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.executescript(DDL)
    return conn


class _BlobStore:
    # Real s3 connector contract: put(key, b64, media_type) -> {etag},
    # get(key) -> {file, b64?, text?} with small objects inlined.
    def put(self, key, b64=None, media_type=None, body=None):
        path = BLOBS / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(b64 if b64 is not None else body))
        return {"etag": "mock"}

    def get(self, key):
        data = (BLOBS / key).read_bytes()
        out = {"file": {"blob": key, "media_type": "application/octet-stream"},
               "b64": base64.b64encode(data).decode("ascii")}
        try:
            out["text"] = data.decode("utf-8")
        except UnicodeDecodeError:
            pass
        return out


class _CatalogDb:
    # Real postgres connector contract: query(sql, params?) -> {row_count, rows}.
    def query(self, sql, params=None):
        sql = re.sub(r"::\w+", "", sql)  # pg casts are no-ops in SQLite
        with _db_lock:
            conn = _connect()
            try:
                cur = conn.execute(sql, params or [])
                rows = [dict(r) for r in cur.fetchall()]
                conn.commit()
                return {"row_count": len(rows), "rows": rows}
            finally:
                conn.close()


class _Web:
    # Real http connector contract: request(method, path, body_b64?) ->
    # {status, headers, body_b64}.
    def request(self, method, path, body_b64=None):
        if not path.startswith(allowlist()):
            raise PermissionError(f"proxy refused: url not in grant allowlist: {path}")
        req = urllib.request.Request(
            path, method=method, headers={"User-Agent": "pantheon-devserver"},
            data=base64.b64decode(body_b64) if body_b64 else None,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read(8 * 1024 * 1024)
            return {
                "status": resp.status,
                "headers": {"content-type": resp.headers.get_content_type()},
                "body_b64": base64.b64encode(data).decode("ascii"),
            }


class MockCtx:
    _RESOURCES = {"blob_store": _BlobStore, "catalog_db": _CatalogDb, "web": _Web}

    def __init__(self, run_id, task_id, requester):
        self.envelope = {
            "run_id": run_id,
            "task_id": task_id,
            "attempt": 1,
            "producer": requester,
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    def resource(self, name):
        return self._RESOURCES[name]()

    # shim.py parity: content-addressed blob helpers
    def blob_put(self, data, media_type="application/octet-stream"):
        import hashlib
        h = hashlib.sha256(data).hexdigest()
        path = BLOBS / "_cas" / h
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {"blob": h, "media_type": media_type, "size_bytes": len(data)}

    def blob_get(self, hash_):
        return (BLOBS / "_cas" / hash_).read_bytes()
