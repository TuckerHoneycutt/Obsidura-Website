# Pantheon — Prototype Spec (v0)

**How to use this document.** This is the *shape* of the system: what must exist, the contracts between parts, and what "done" means. It is deliberately lean. A companion file (`pantheon-context.md`, the full design conversation) contains the reasoning, framework analyses, rejected alternatives, and implementation tradeoffs — read it selectively when a section here needs depth; do not load it wholesale. Where this spec and the companion conflict, this spec wins.

**Hard deadline context:** demo in 8 days. The build plan (§10) is priority-ordered; if anything slips, it must be a bonus chunk, never the demo path (P0).

---

## 1. What Pantheon is

A workflow orchestration engine where **definitions are data, not code**. Tenant-authored YAML compiles into a typed IR held in Postgres; a Rust executor instantiates runs from it; task bodies run in containers speaking JSON-RPC over stdio; all resource access flows through a run-scoped proxy. Agents are ordinary tasks with extra policy, never a special execution path.

Non-negotiable invariants (violating any of these means the design has failed):

1. **The amount of Rust in the executor is constant in the number of business types.** The executor has operational duties toward kernel values only; it never contains per-domain logic.
2. **No expression language in YAML, ever.** Definitions are literal data + refs + parameters. Computation lives in tasks or in frontends that emit IR.
3. **Edges are derived from references** (`on:`, `then:`, `uses:`), never authored as entities.
4. **No framework is hardcoded at the executor level.** Pydantic AI (or any harness) is a leaf dependency inside a runner image; swapping it must touch zero executor code.
5. **Task graph shapes must stay composable.** e.g. `agent → ReportSpec → renderer` and `agent → HTML File` must both be expressible as ordinary definitions with no engine changes.

## 2. Demo target (the artifact this prototype must produce)

A user types a prompt into a minimal web page → three report websites materialize in their browser, drawn live from data spread across heterogeneous company resources, permission-scoped to that user.

- **Entry:** one hand-polished static HTML page: text box → POST to webhook trigger → poll run status endpoint → report cards appear, clicking opens each report. This page is also the dev iteration harness.
- **Three pre-wired report pipelines** (one per vertical), all following: webhook `report.request {prompt: text, requester}` → agent task (gathers permitted data via proxy, emits a **ReportSpec Record**) → deterministic **render task** (composes final static site from a hand-built template + component library stored as a Resource) → output `File` artifact (self-contained HTML/JS with data snapshot baked in; charts render/filter client-side).
- **The three verticals + synthetic fixtures** (a named workstream, starts day 1):
  1. *Financial audit* — postgres ledger + s3 receipt PDFs + http FX-rate API.
  2. *Rocket flight diagnostics* — s3 telemetry CSV (~tens of thousands of rows; exercises Table handles) + postgres test/anomaly logs.
  3. *Clinical summary* — postgres patient records + s3 scan images rendered into the report. **The permission beat lives here:** user A and user B issue the same prompt; B's report contains fewer patients; audit log shows the scope decisions.
- **Demo script order:** beauty first (the reports), governance second (the two-user permission beat + audit trail).
- Reports are **static artifacts** in v0. Spun-up interactive servers and CoW shared editing are bonus chunks only.

## 3. Layers

1. **Definition graph** — what *can* exist: triggers, tasks, resources, approvals, agent specs, schemas; plus policy (caps, budgets, user grants). Authored as YAML, compiled and registered via plan/apply.
2. **Runtime graph** — what *does* exist: runs instantiated from definitions, with contract enforcement at every seam, capability-scoped resource access, logging/status, retries, and a warm container worker pool.
3. **Contracts** — what may be exchanged: kernel values + registered Record schemas, carried in envelopes, validated at every boundary.

## 4. Primitives (tagged unions; serde `#[serde(tag="kind")]`, JSON Schema generated from the Rust types via schemars — Rust is the source of truth for the vocabulary)

**Trigger** — `source:` ∈ `cron | webhook | manual`. (Deferred: file_watch, socket, bus.) Every trigger declares `emits: <schema ref>` — the shape of the packet it produces when it fires. Manual = API/CLI fire, used by tests and the demo shell.

**Task** — fields: `runner`, `input: <schema ref>`, `output: <schema ref>`, `policy {timeout, retry, budget, idempotent}`, `uses: [resource refs + verbs]`, wiring refs (`on:` trigger, `then:` next task(s)).
- `runner: script {runtime: python, entry}` — deterministic body.
- `runner: agent {spec: <AgentSpec ref>}` — stochastic body. Same execution path as script (same container, same protocol); the tag changes *policy*: output schema validation with bounded repair (§6), token budget, taint recording, audit metadata (model, spec version).
- (Deferred: `runner: model {classify|generate|regress}`.)

**Resource** — `connector:` ∈ `postgres | s3 | http`. (Deferred: imap, mcp, memory.) Declares exposed verbs (e.g. `query`, `get`, `put`, `request`) and connection config; secrets live executor-side only.

**Approval** — minimal: a task may declare `gate: approval {approvers, timeout}`. Pending approvals persist in Postgres; approve/deny via CLI/API; run suspends durably (survives executor restart) and resumes on approve.

**Values (not nodes):** `AgentSpec` — model id, instructions, allowed tools (proxied capabilities), output schema ref, repair budget. Keep minimal in v0; persona/memory machinery deferred. `Schema` — registry entries (§6).

## 5. Kernel Value (Rust, closed set, v0 = five variants)

```rust
#[derive(Serialize, Deserialize, JsonSchema, Clone)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Value {
    Text(Text),                                       // { body, lang? }
    File(FileHandle),                                 // content-addressed blob ref + media_type + capability
    Table(TableHandle),                               // column meta + blob-store row source (CSV/JSONL in v0; Arrow later)
    Record { type_ref: TypeRef, data: serde_json::Value },  // all business meaning lives here
    Error(ErrorValue),
}
```

Executor duties are operational only: store/hash/gate Files, meter Tables, validate Records against their registered schema, route Errors. Bin is folded into File (media_type distinguishes); Message deferred. Anything domain-specific (e.g. an mdzip file) is a `File` with a media_type; understanding it is an action's job at the edge.

## 6. Contracts

- **Schema registry:** flat in v0 — kernel schemas (generated from Rust) + registered Record schemas (JSON Schema documents in Postgres, versioned `name@version`). Include a nullable `refines` column now; refinement checking itself is deferred.
- **Envelope** (every value crossing a seam): `run_id, task_id, attempt, schema (ref@version), producer, caused_by (event seq), taint: [], budget_spent {tokens, ms}, ts`. Taint is **recorded and logged, not enforced** in v0.
- **Boundary validation:** every task output is validated against its declared output schema before anything downstream sees it. For `runner: agent`, failures trigger the repair loop: validation error → truncated error diff back to the model → retry, **max 2 attempts**, then typed failure into the run log.
- **Wire:** JSON everywhere; large data always by handle (File/Table), never inline.

## 7. YAML authoring rules

- One node per file or small groups; a directory = a package; `kind:` discriminator matches the Rust enum tags; refs by `name@version`.
- Literal data only. No interpolation, no conditionals, no expressions. If shapes differ between tasks, either declare a flat field-path mapping list (`to_field: from.path` — checkable against both schemas) or insert an adapter task.
- `ptn plan` shows a diff against the registry; `ptn apply` registers. Invalid definitions are rejected at plan time with errors naming the file, field, and rule violated.

## 8. Executor & runtime

- **Rust + tokio.** Drivers: cron, webhook (axum endpoint), manual. One driver per source kind owning all instances of it.
- **Run log — the load-bearing schema.** Single append-only table; executor state is a fold of events; no snapshots in v0:
  `run_events(run_id uuid, seq bigint, event_type text, payload jsonb, ts timestamptz, PRIMARY KEY(run_id, seq))`
  All of: status queries, audit trail, approval suspend/resume, crash recovery (acceptance test 7), and the demo shell's polling read from this table.
- **Workers:** warm container pool (~4) of **one generic Python runner image** (pydantic-ai, polars, httpx, render deps baked in). Cold-start must never be visible in the demo. Dev-mode flag runs the same shim as a bare subprocess. (Per-action images: bonus chunk.)
- **Runner protocol:** JSON-RPC over stdio. Shim receives `{envelope, payload, capabilities}`, exposes `ctx` to the body, streams log events and the output envelope back. The harness (Pydantic AI) exists only inside the body.
- **Resource proxy:** per-run Unix domain socket mounted into the container — the socket *is* the capability. Body code calls `ctx.resource("name").verb(...)`; proxy checks the run's minted grants, executes with real credentials (never shared with the container), writes an audit event, returns data.
- **Users & permissions:** static users in Postgres + bearer tokens. `grants(user_id, resource, verbs, scope)` where scope is per-connector: SQL row-filter for postgres, key prefix for s3, URL allowlist for http. Enforced at the proxy on every call.

## 9. Acceptance tests ("done" = all eight)

1. `ptn apply` on the demo definition directory succeeds; a deliberately invalid definition is rejected with a clear, located error.
2. A cron trigger fires a two-task chain; the inter-task seam validates contracts (and a mismatched pair is rejected at plan time).
3. Webhook → report pipeline produces a complete artifact site drawing on all three connector types.
4. Same prompt, two users → different clinical reports; audit log lines show each scope decision.
5. An approval gate suspends a run **across an executor restart** and resumes on approve.
6. A deliberately malformed agent output is repaired via the bounded retry loop, visibly in the run log.
7. Executor killed mid-run; on restart the run completes correctly from the log.
8. **The human test:** from the demo page, one typed prompt → three beautiful reports open in the browser, snappy, no visible cold starts. Iterated with a human in the loop until it *feels* right; automated checks do not substitute for this.

## 10. Build plan (priority-ordered chunks)

**P0 — the demo path (must ship):**
1. Vocabulary crate: primitives + kernel Value + schemars emission.
2. Registry + `ptn plan/apply` + validation (refs, contracts, grants).
3. Run log + executor core (manual driver first, then webhook, then cron).
4. Runner image + stdio shim + resource proxy (UDS) + grants enforcement.
5. Connectors: postgres, s3 (MinIO), http.
6. Fixtures workstream (three synthetic datasets — starts day 1, parallel).
7. Report template + component library (charts, tables, KPI cards) + render task.
8. Agent task (Pydantic AI harness, ReportSpec output, repair loop).
9. Demo shell page + status endpoint.
10. Approval primitive (minimal) + acceptance tests 1–8.

**Bonus chunks (independently pluggable, in order of demo value):**
- **B1 Voice:** second webhook trigger accepting an audio File → `transcribe` script task (off-the-shelf STT) → `then:` pointing at the *same* report entry task. Demonstrates: new modality = one trigger + one adapter task; existing graph unchanged.
- **B2 Runtime plan/apply closer:** an agent task emits a new definition → `ptn plan` shows the diff → human applies → the new action is live and invoked. ("The system just learned a new trick, and a human approved it.")
- **B3 Direct-HTML agent renderer:** alternative pipeline where the agent emits the HTML `File` itself (skill-injected, template-aware). Must slot in as an ordinary definition swap — this doubles as a composability test of invariant 5.
- **B4 Per-action runner images** (real dependency isolation).
- **B5 Interactive report server:** render task output feeds a template FastAPI container serving the report.
- **B6 CoW shared editing** of report data snapshots (design sketch only unless time is absurd).

## 11. Explicitly deferred (do not build, do not block on)

Vertical/tenant refinement checking (grammar specified in companion); taint *enforcement*; file_watch/socket/bus triggers; imap/mcp/memory connectors; `model` runner kind; Arrow-backed Tables; Message kernel type; personas & memory policy; dynamic in-action routing (phase 2 = declared-choice routing: output `route` field validated against a permitted-destination list in the definition — never an open catalog); promotion ladder; warm-pool sophistication beyond "N generic containers"; SSO.

# Note
Reference of full conversation context producing this document is here: /home/supergoodname77/Documents/supergoodvault77/Custom Structure/Main Notes/Research/Aurora/Pantheon/Pantheon Discussion Context.md

That doc is extremely dense but contains basically all conceived implementation details, so if you feel you are missing an important piece of knowledge neccessary to build the demo, that document is searchable. By default refer to this document's spec however.