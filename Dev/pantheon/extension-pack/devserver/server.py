"""Dev harness for the extension pack: runs the real action bodies behind the
same POST-then-poll contract the demo shell uses.

    python3 server.py [port]      # default 8787

Routes:
    GET  /                   the interactive page
    POST /hook/upload.file   -> ingest_normalize -> catalog_register
    POST /hook/web.curate    -> web_snapshot
    POST /trigger/liveness   -> api_liveness
    GET  /runs/{id}          run status (poll target)
    GET  /catalog            ingest_catalog rows
    GET  /registry           web_registry rows
    GET  /meta               actions + sources metadata, live stats
    GET  /allowlist          the web grant allowlist
    POST /allowlist          {"add": url} | {"remove": url}
    GET  /blob/{key}         stored blob bytes
"""

import json
import mimetypes
import re
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    import yaml  # host python has pyyaml; drafts degrade gracefully without it
except ImportError:
    yaml = None

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent / "actions"))
sys.path.insert(0, str(ROOT))

import agent_answer  # noqa: E402
import agent_describe  # noqa: E402
import api_liveness  # noqa: E402
import catalog_register  # noqa: E402
import ingest_normalize  # noqa: E402
import web_snapshot  # noqa: E402
from _agent import active_model  # noqa: E402
from mockctx import BLOBS, MockCtx, _CatalogDb, allowlist, set_allowlist  # noqa: E402

RUNS = {}

CHAINS = {
    "/hook/upload.file": [
        ("ingest_normalize", ingest_normalize),
        ("catalog_register", catalog_register),
        ("agent_describe", agent_describe),
    ],
    "/hook/web.curate": [("web_snapshot", web_snapshot)],
    "/trigger/liveness": [("api_liveness", api_liveness)],
    "/hook/ask.question": [("agent_answer", agent_answer)],
}

ACTIONS_META = [
    {
        "name": "ingest_normalize",
        "title": "Ingest & normalize",
        "kind": "script",
        "trigger": "webhook upload.file",
        "chain": "upload.file → ingest_normalize → catalog_register",
        "description": (
            "Turns an uploaded file into kernel-value shape. CSV becomes a Table "
            "(profiled columns with sniffed dtypes, blob-store row source), small "
            "JSON becomes an inline Record, images and documents become "
            "content-addressed Files. Routing by media type lives inside the "
            "script — honest computation, not YAML."
        ),
        "input": "ingest.upload@1",
        "output": "ingest.result@1",
        "uses": [{"resource": "blob_store", "verbs": ["put", "get"]}],
        "policy": {"timeout": 120, "retry": 1, "idempotent": True},
        "entry": "actions/ingest_normalize.py",
        "run": {"label": "Upload a file", "target": "#ingest"},
    },
    {
        "name": "catalog_register",
        "title": "Catalog register",
        "kind": "script",
        "trigger": "then: after ingest_normalize",
        "chain": "upload.file → ingest_normalize → catalog_register",
        "description": (
            "Registers a normalized ingest result in the catalog, idempotent on "
            "content hash. The catalog row is what makes uploaded data "
            "discoverable to report agents — their envelope includes "
            "catalog_db.query, so 'the spreadsheet I uploaded' becomes findable "
            "data instead of dead bytes."
        ),
        "input": "ingest.result@1",
        "output": "ingest.cataloged@1",
        "uses": [{"resource": "catalog_db", "verbs": ["query"]}],
        "policy": {"timeout": 30, "retry": 2, "idempotent": True},
        "entry": "actions/catalog_register.py",
        "run": {"label": "Upload a file", "target": "#ingest"},
    },
    {
        "name": "web_snapshot",
        "title": "Web snapshot",
        "kind": "script",
        "trigger": "webhook web.curate",
        "chain": "web.curate → web_snapshot",
        "description": (
            "Snapshot-on-curation (Appendix B.1): fetch a URL once through the "
            "proxy under the grant allowlist, content-hash the bytes into the "
            "blob store, and record provenance. Downstream consumes the snapshot "
            "as an ordinary File — the URL is provenance, never a runtime "
            "dependency. A refused or failed fetch is recorded, not raised."
        ),
        "input": "web.curate_request@1",
        "output": "web.snapshot@1",
        "uses": [
            {"resource": "web", "verbs": ["request"]},
            {"resource": "blob_store", "verbs": ["put"]},
            {"resource": "catalog_db", "verbs": ["query"]},
        ],
        "policy": {"timeout": 60, "retry": 1, "idempotent": True},
        "entry": "actions/web_snapshot.py",
        "run": {"label": "Curate a URL", "target": "#external"},
    },
    {
        "name": "api_liveness",
        "title": "API liveness",
        "kind": "script",
        "trigger": "cron liveness.tick (hourly)",
        "chain": "liveness.tick → api_liveness",
        "description": (
            "Liveness sweep over the web registry (Appendix B.2) — a Pantheon "
            "workflow, not a subsystem. Probes every non-retired entry through "
            "the proxy, writes per-entry status back, and emits a web.status "
            "record. Per-entry failures are results, never task failures."
        ),
        "input": "kernel.cron_tick@1",
        "output": "web.status@1",
        "uses": [
            {"resource": "web", "verbs": ["request"]},
            {"resource": "catalog_db", "verbs": ["query"]},
        ],
        "policy": {"timeout": 120, "retry": 0, "idempotent": True},
        "entry": "actions/api_liveness.py",
        "run": {"label": "Run now", "action": "liveness"},
    },
    {
        "name": "agent_describe",
        "title": "Describe (agent)",
        "kind": "agent",
        "trigger": "then: after catalog_register",
        "chain": "upload.file → … → catalog_register → agent_describe",
        "description": (
            "An agent with limited discretion: its envelope is the ingest "
            "catalog via catalog_db.query. It looks up the fresh row, reads "
            "what was profiled, and proposes a description plus tags — a "
            "deterministic step commits the proposal to the catalog. Every "
            "proxied call it makes lands in the audit trail."
        ),
        "input": "ingest.cataloged@1",
        "output": "ingest.enriched@1",
        "uses": [{"resource": "catalog_db", "verbs": ["query"]}],
        "policy": {"timeout": 120, "retry": 0, "idempotent": True},
        "entry": "actions/agent_describe.py",
        "spec": "describe_agent@1",
        "run": {"label": "Upload a file", "target": "#ingest"},
    },
    {
        "name": "agent_answer",
        "title": "Answer (agent)",
        "kind": "agent",
        "trigger": "webhook ask.question",
        "chain": "ask.question → agent_answer",
        "description": (
            "Answers natural-language questions over the requester's data. "
            "Envelope: the ingest catalog, the web registry, and the blob "
            "store — the agent chooses what to pull per question (Appendix A "
            "discretion), cites its sources, and its audit trail shows every "
            "query and blob it touched."
        ),
        "input": "ask.question@1",
        "output": "agent.answer@1",
        "uses": [
            {"resource": "catalog_db", "verbs": ["query"]},
            {"resource": "blob_store", "verbs": ["get"]},
        ],
        "policy": {"timeout": 180, "retry": 0, "idempotent": True},
        "entry": "actions/agent_answer.py",
        "spec": "answer_agent@1",
        "run": {"label": "Ask a question", "target": "#agent"},
    },
]

SOURCES_META = [
    {
        "name": "blob_store",
        "connector": "s3",
        "verbs": ["get", "put"],
        "scope": "key prefix (per grant)",
        "mock": "local folder devserver/data/blobs/",
        "description": (
            "Content-addressed blob storage for everything big: table row "
            "sources, documents, images, web snapshots. In the prototype this is "
            "MinIO; grants scope access by key prefix."
        ),
        "yaml": (
            "kind: resource\nname: blob_store\nversion: 1\nconnector: s3\n"
            "verbs: [get, put]\nconfig:\n  bucket: pantheon-ingest"
        ),
    },
    {
        "name": "catalog_db",
        "connector": "postgres",
        "verbs": ["query"],
        "scope": "SQL row filter (per grant)",
        "mock": "SQLite at devserver/data/catalog.db",
        "description": (
            "Holds ingest_catalog and web_registry — the discovery layer report "
            "agents query inside their envelope. Grants scope rows per requester, "
            "so one user's uploads never surface in another's report."
        ),
        "yaml": (
            "kind: resource\nname: catalog_db\nversion: 1\nconnector: postgres\n"
            "verbs: [query]\nconfig:\n  database: pantheon"
        ),
    },
    {
        "name": "web",
        "connector": "http",
        "verbs": ["request"],
        "scope": "URL allowlist (per grant)",
        "mock": "live HTTP; allowlist enforced by the mock proxy",
        "editable_allowlist": True,
        "description": (
            "Generic outbound HTTP under a grant-scoped URL allowlist — the hard "
            "ceiling, checked at the proxy on every call. Used for curated "
            "snapshots and live APIs alike. Edit the allowlist below; anything "
            "outside it is refused and the refusal is recorded."
        ),
        "yaml": (
            "kind: resource\nname: web\nversion: 1\nconnector: http\n"
            "verbs: [request]\nconfig: {}"
        ),
    },
]

CONNECTOR_TEMPLATES = {
    "postgres": (
        "kind: resource\nname: <name>\nversion: 1\nconnector: postgres\n"
        "verbs: [query]\nconfig:\n  database: <database>"
    ),
    "s3": (
        "kind: resource\nname: <name>\nversion: 1\nconnector: s3\n"
        "verbs: [get, put]\nconfig:\n  bucket: <bucket>"
    ),
    "http": (
        "kind: resource\nname: <name>\nversion: 1\nconnector: http\n"
        "verbs: [request]\nconfig: {}\n"
        "# grant scope = URL allowlist, per user"
    ),
}


SCOPE_BY_CONNECTOR = {
    "postgres": "SQL row filter (per grant)",
    "s3": "key prefix (per grant)",
    "http": "URL allowlist (per grant)",
}

DRAFTS_FILE = ROOT / "data" / "sources.json"
BUILTIN_NAMES = {s["name"] for s in SOURCES_META}


def load_drafts():
    if DRAFTS_FILE.exists():
        return json.loads(DRAFTS_FILE.read_text())
    return []


def save_drafts(drafts):
    DRAFTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    DRAFTS_FILE.write_text(json.dumps(drafts, indent=2))


def register_draft(yaml_text):
    """Validate an in-page-authored resource definition; returns (draft, error)."""
    if yaml is None:
        return None, "pyyaml is not available in the harness python"
    try:
        doc = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        return None, f"invalid YAML: {exc}"
    if not isinstance(doc, dict):
        return None, "definition must be a YAML mapping"
    if doc.get("kind") != "resource":
        return None, "kind must be 'resource' (only resources register here)"
    name = doc.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9_.\-]+", name):
        return None, "name must match [a-z0-9_.-]+"
    if name in BUILTIN_NAMES:
        return None, f"'{name}' is a built-in resource; pick another name"
    connector = doc.get("connector")
    if connector not in SCOPE_BY_CONNECTOR:
        return None, f"connector must be one of {sorted(SCOPE_BY_CONNECTOR)}"
    verbs = doc.get("verbs")
    if not isinstance(verbs, list) or not all(isinstance(v, str) for v in verbs) or not verbs:
        return None, "verbs must be a non-empty list of strings"
    return {
        "name": name,
        "connector": connector,
        "verbs": verbs,
        "scope": SCOPE_BY_CONNECTOR[connector],
        "mock": "draft — registered in the harness registry only",
        "description": doc.get("description")
        or f"Draft {connector} resource authored in the page. "
           "Not reachable by actions until applied to the executor.",
        "yaml": yaml_text.strip(),
        "draft": True,
    }, None


def stats():
    db = _CatalogDb()
    catalog = db.query("SELECT COUNT(*) AS n FROM ingest_catalog")[0]["n"]
    reg = db.query(
        "SELECT COUNT(*) AS n, COALESCE(SUM(CASE WHEN live THEN 1 ELSE 0 END), 0) AS up "
        "FROM web_registry"
    )[0]
    blobs = sum(1 for p in BLOBS.rglob("*") if p.is_file()) if BLOBS.exists() else 0
    return {"catalog": catalog, "registry": reg["n"], "up": reg["up"], "blobs": blobs}


def execute(chain, payload, requester):
    run_id = uuid.uuid4().hex[:12]
    RUNS[run_id] = {"run_id": run_id, "status": "running", "events": []}

    def work():
        data = payload
        try:
            for task_name, module in chain:
                ctx = MockCtx(run_id, task_name, requester)
                RUNS[run_id]["events"].append({"task": task_name, "ts": ctx.envelope["ts"]})
                data = module.run(ctx, data)
            RUNS[run_id].update(status="complete", output=data)
        except Exception as exc:  # a failed run is a result, not a crash
            RUNS[run_id].update(status="failed", error=f"{type(exc).__name__}: {exc}")

    threading.Thread(target=work, daemon=True).start()
    return run_id


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._send(200, (ROOT / "index.html").read_bytes(), "text/html")
        elif self.path.startswith("/runs/"):
            run = RUNS.get(self.path.removeprefix("/runs/"))
            self._json(200 if run else 404, run or {"error": "no such run"})
        elif self.path == "/catalog":
            self._json(200, _CatalogDb().query(
                "SELECT * FROM ingest_catalog ORDER BY created_at DESC LIMIT 200"))
        elif self.path == "/registry":
            self._json(200, _CatalogDb().query(
                "SELECT * FROM web_registry ORDER BY name LIMIT 200"))
        elif self.path == "/meta":
            self._json(200, {
                "actions": ACTIONS_META,
                "sources": SOURCES_META + load_drafts(),
                "templates": CONNECTOR_TEMPLATES,
                "stats": stats(),
                "allowlist": list(allowlist()),
                "agent": {
                    "model": active_model(),
                    "live": not active_model().startswith("mock:"),
                },
            })
        elif self.path == "/allowlist":
            self._json(200, list(allowlist()))
        elif self.path.startswith("/blob/"):
            key = self.path.removeprefix("/blob/")
            path = (BLOBS / key).resolve()
            if not str(path).startswith(str(BLOBS.resolve())) or not path.is_file():
                self._json(404, {"error": "no such blob"})
            else:
                media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self._send(200, path.read_bytes(), media)
        else:
            self._json(404, {"error": "unknown route"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "body must be JSON"})
            return

        if self.path == "/sources":
            drafts = load_drafts()
            if payload.get("remove"):
                kept = [d for d in drafts if d["name"] != payload["remove"]]
                if len(kept) == len(drafts):
                    self._json(404, {"error": "no draft by that name"})
                    return
                save_drafts(kept)
                self._json(200, {"removed": payload["remove"]})
                return
            draft, err = register_draft(payload.get("yaml", ""))
            if err:
                self._json(400, {"error": err})
                return
            drafts = [d for d in drafts if d["name"] != draft["name"]] + [draft]
            save_drafts(drafts)
            self._json(200, draft)
            return

        if self.path == "/allowlist":
            urls = set(allowlist())
            add, remove = payload.get("add"), payload.get("remove")
            if add:
                if not add.startswith(("http://", "https://")):
                    self._json(400, {"error": "allowlist entries must be http(s) URLs"})
                    return
                urls.add(add)
            if remove:
                urls.discard(remove)
            set_allowlist(urls)
            self._json(200, sorted(urls))
            return

        chain = CHAINS.get(self.path)
        if not chain:
            self._json(404, {"error": "unknown hook"})
            return
        run_id = execute(chain, payload, payload.get("requester", "demo"))
        self._json(202, {"run_id": run_id})

    def _send(self, code, body, media):
        self.send_response(code)
        self.send_header("Content-Type", media)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, default=str).encode(), "application/json")

    def log_message(self, fmt, *args):
        pass  # keep the console quiet; runs are inspectable at /runs/{id}


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    print(f"pantheon extension-pack dev harness -> http://localhost:{port}/")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
