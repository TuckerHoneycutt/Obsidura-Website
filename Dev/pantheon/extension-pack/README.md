# Pantheon extension pack — ingestion, uploads, external APIs

A drop-in set of definitions (YAML) and action bodies (Python) that extend the
Pantheon prototype with three capabilities, all built as ordinary definitions —
zero executor changes, per invariant 1:

1. **Data ingestion** (`definitions/ingestion/`) — anything entering the system
   is normalized into kernel values (File / Table / Record) and registered in a
   queryable catalog, so every downstream agent can discover it inside its
   permission envelope.
2. **Desktop file uploads** (`shell/upload-fragment.html` + the ingestion flow) —
   the B1-voice pattern applied to files: one new webhook trigger + one adapter
   task, fanning into the existing graph. No engine changes.
3. **External API connections** (`definitions/external/`) — `http` Resources
   under URL-allowlist grants, the Appendix-B snapshot-on-curation flow, and a
   cron liveness workflow defined in Pantheon itself (dogfooding, per B.2).

Plus `definitions/agents/report-envelope.yaml`: a broad-envelope AgentSpec
(Appendix A compliant) showing how the existing report pipelines gain access to
ingested/uploaded/external data — the agents are told the catalog exists and
choose what to pull, within the caller's grant.

## Layout

```
schemas/            Record schemas (name@version) for every seam in the pack
definitions/
  ingestion/        upload trigger → normalize → catalog chain
  external/         http resources, snapshot task, cron liveness workflow
  agents/           broad-envelope AgentSpec example (Appendix A)
actions/            Python task bodies; _compat.py holds ALL shim assumptions
shell/              upload control fragment for the demo shell page
sql/                catalog + web-registry DDL and example grants (fixtures side)
```

## Data flow

```
[desktop file] → webhook upload.file → ingest_normalize → catalog_register
                                            │                    │
                                     blob store (s3)      catalog_db (postgres)
                                                                 │
[report prompt] → report.request → report agents ────────────────┘
                                    (envelope now includes the catalog: agents
                                     may query it and pull permitted handles)

[curate URL]   → web.curate → web_snapshot → File + web.snapshot Record → catalog
[cron hourly]  → liveness.tick → api_liveness → web.status Record
```

## Integration checklist — RECONCILED against `prototypev1`

The real source now lives at `Dev/cum/pantheon-v1/pantheon` (a git worktree of
`origin/prototypev1`). Status of each original assumption:

1. **YAML vocabulary — ✅ reconciled.** All definition files now use the real
   shapes: document-stream YAML (`---` separators), `runner: {type: script,
   runtime: python, entry: module.function}` / `{type: agent, spec: ref}`,
   `source: {type: webhook, path: /hooks/<name>}` / `{type: cron, schedule}`,
   `on:` as a list, `policy: {timeout_ms, retry, budget: {tokens}, idempotent}`,
   `connector: {type: postgres|s3|http, ...}` objects with `*_env` secrets,
   `kind: schema` with `document:`, and `kind: grant` definitions with typed
   scopes (`prefix`, `row_filter`, `url_allowlist`).
2. **Script entry — ✅ reconciled.** Entries are dotted module paths
   (`ext_actions.ingest_normalize.run`); ship `actions/` on the runner image's
   python path as the `ext_actions` package (add it in `runner/Dockerfile`).
3. **`ctx` surface — ✅ verified.** The shim exposes exactly
   `ctx.resource(name).verb(**args)` (JSON-RPC to the UDS proxy) as `_compat`
   assumed, plus `ctx.blob_get(hash)` / `ctx.blob_put(data, media_type)` for
   content-addressed blobs — consider switching `_compat.blob_*` to those
   helpers instead of an s3 resource round-trip.
4. **Endpoints — ✅ verified.** The executor serves `POST /hooks/{path}`
   (exact match against each trigger's declared path), `GET /runs`,
   `GET /runs/{run_id}`, and `POST /runs/{id}/approvals`. The fragment now
   posts to `/hooks/upload`.
5. **Binary ingress** — v0 webhook payloads are JSON, so uploads ride as base64
   (capped at 8 MB in the fragment). If the webhook driver supports
   multipart-to-File, switch the fragment and drop the base64 leg from
   `ingest_normalize`. Inline base64 violates "large data by handle" at exactly
   one seam — the system boundary — where a handle cannot exist yet.
6. **Cron emit schema** — `liveness.tick` emits `kernel.cron_tick@1`; the
   prototype's cron driver already emits some packet shape. Use its name.
7. **Resource naming** — we declare `blob_store` (s3) and `catalog_db`
   (postgres). If the prototype already registers equivalents (it stores report
   assets somewhere), reuse those names instead of adding parallel resources.
8. **Schema registration kind** — Record schemas here are `kind: schema` docs
   with an inline `json_schema:` body. Match the prototype's registration form.
9. **Registry append-only friction (I8/I11)** — iterating on these definitions
   still costs version bumps or wipe+reseed. Known, deferred to Phase 4
   (supersede semantics), not made worse by this pack.
10. **SQL string building** — the proxy's `query` verb takes one `sql` string
    (no parameter binding per issues I5), so `catalog_register` escapes values
    by quote-doubling. Demo-grade; move to bound parameters when the connector
    grows them.

## What the report pipelines gain

The four demo functions never change their wiring. The report agents'
instructions (see `definitions/agents/report-envelope.yaml`) now describe two
additional envelope members: the ingest catalog and the web-snapshot registry.
Per Appendix A, the agents *choose* whether a given request warrants pulling
uploaded or external data — the grant + row-filter remain the hard ceiling, and
every pull lands in the audit log.
