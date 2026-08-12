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

**Resource** — `connector:` ∈ `postgres | s3 | http`. (Deferred: imap, mcp, memory.) Declares exposed verbs (e.g. `query`, `get`, `put`, `request`) and connection config; secrets live executor-side only. Curated web resources are `http` Resources plus registry/snapshot data, not a new kind (Appendix B).

**Approval** — minimal: a task may declare `gate: approval {approvers, timeout}`. Pending approvals persist in Postgres; approve/deny via CLI/API; run suspends durably (survives executor restart) and resumes on approve.

**Values (not nodes):** `AgentSpec` — model id, instructions, allowed tools (proxied capabilities), output schema ref, repair budget, `skills {always, routable}` (Appendix C). Keep minimal in v0; persona/memory machinery deferred. `Schema` — registry entries (§6).

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

**Standing check (not part of the v0 "eight", added after review):** the **discretion diversity test** — two materially different prompts through one pipeline must diff in both the proxy audit trail and the ReportSpec component set, or the definition has collapsed to a hardcoded formatter (Appendix A.1). It guards the Appendix A envelope against regression and only bites once fixtures are rich enough (A.3).

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

---

# Appendix A — Agent discretion is *limited*, not cosmetic (added 2026-08-09; revised after spec-agent review)

Added after a prototype review found the v0 vertical actions had collapsed the
agent into cosmetic text-reshaping: each AgentSpec's `instructions` handed the
model one exact query to run verbatim, so the only freedom left was rephrasing
the same fields as prose. Recording the intended semantics here so future
implementations do not repeat it. This is an intent clarification, not a new
mechanism — the connectors, grants and row filters already enforce the envelope
described below; what v0 got wrong was the *definitions*.

The reason an action is an *agent* and not a script is **discretion**. A script
returns the same reshaping of the same fields on every run; if that is all an
action does, it should be a script and spend no tokens. An agent earns its cost
only by exercising **limited discretion**:

- **Queryable surface (per run) = (data the requesting user may access) ∩ (data
  the action is permitted to use).** The first set is the permission model — the
  caller's grants, row filters and all. The second is whatever the action's
  definition authorises. Their intersection is a *broad but safe* envelope,
  fixed by definition and enforced at the connector seam.
- **Within that envelope the agent chooses a *subset*** — which fields, which
  rows, which of the permitted resources to touch — **according to what the
  request asks for**, and **composes the UI components** (which sections, which
  `kind`s) that convey that subset usefully. Two different requests against the
  same envelope must be able to produce genuinely different reports: different
  data pulled and different components composed, not merely different prose over
  one identical, pre-baked query.
- The definition is therefore **broad** (it describes an envelope — e.g. "you
  may query the patients table over these columns, subject to the caller's
  grant, and present what is relevant") and **not narrow** (it must not dictate
  a single literal SELECT). A narrow definition is the anti-pattern: it makes
  the model a formatter and renders the safety envelope moot.

The bound is never widened by discretion: the intersection above is the hard
ceiling, checked per call under the caller's grant, with the audit log
recording what was actually pulled. Discretion moves *inside* the envelope; it
can never reach past it. That is the whole point of preferring an agent over a
programmatic pipeline — powerful, reasoned selection and presentation, held
inside a provably safe boundary.

**A.1 — Make discretion testable (standing check, §9).** The clause "two
different requests must be able to produce genuinely different reports" is
checkable from data already logged. Run one pipeline with two *materially
different* prompts and diff (a) the proxy audit trail — the queries/verbs that
actually ran — and (b) the emitted ReportSpec's section/component set. If both
diffs are near-empty, the definition has collapsed back into the anti-pattern
(a formatter with a hardcoded query). This is the **discretion diversity
test**; without it the appendix will be re-violated, because narrow definitions
are the path of least resistance. Add it alongside acceptance tests 1–8.

**A.2 — Name the cost.** Widening a definition widens the prompt-injection
surface: an agent that chooses its own queries can be steered by a hostile
request in ways a hardcoded query cannot. The envelope is exactly the right
containment — the design working as intended, not a hole — but it moves two
**deferred** items up the phase-2 priority order (this does *not* change v0):
(1) **taint enforcement** — recorded-only (§6) was acceptable while definitions
were narrow; a broad envelope makes propagation worth enforcing; (2) **approval
gates on any envelope that includes egress-like verbs** (`http.request`,
`s3.put`), so a steered query cannot exfiltrate without a human seam.

**A.3 — Fixture richness is a precondition, not polish.** Discretion is only
*visible* when the data contains more than any single report shows — multiple
related tables, more columns and resources per vertical than one answer needs.
Barebones single-table fixtures cap how much discretion is meaningful, so the
v0 prototype may keep narrow definitions until fixtures are enriched (tracked in
`issues.md` I1). Enriching them is what lets the A.1 test bite.

---

# Appendix B — Web resources as a curated registry (added 2026-08-09)

The web is useful data by definition, but an unvetted external reference in a
run is both a reliability hole and an exfiltration channel. This adds **no new
primitive**: a "known-good web resource" is the existing `http` Resource plus
three pieces of data — a registry entry `{name, url, purpose, version}`, a
liveness status, and curation metadata.

**B.1 — Snapshot on curation; never hot-fetch in anger.** When a URL is
admitted to the registry, fetch it *once*, content-hash the bytes into the blob
store, and record the provenance:

```
snapshot { url, fetched_at, sha256, media_type }   // a Record; the bytes are a File
```

Downstream tasks consume the snapshot as an ordinary **`File`** (content-address
+ media_type + capability, §5); the URL is *provenance, not a runtime
dependency*. This resolves four problems at once: external uptime cannot break a
run (or the demo); `version` is exact (the hash); the permission story is
unchanged (it is a File with a capability); and the audit trail can prove which
bytes were used. For static external assets — images especially — this is
strictly better than live fetching. **Live fetch stays** for genuinely dynamic
sources (the FX-rate API), already modeled as an `http` Resource with
URL-allowlist grant scope (§8).

**B.2 — Liveness monitoring is a Pantheon workflow, not a subsystem.** A `cron`
trigger → check task → status `Record`s → alert on failure. It needs no new
executor code, dogfoods the engine, and is itself a demo beat ("Pantheon
monitors its own resource registry"). Deferred for v0; noted so it is built as
definitions, never as a bespoke service.

---

# Appendix C — Skills (added 2026-08-09)

A skill is injected instructions (an agentskills.io `SKILL.md`). The rule that
holds the whole thing together: **skills are registry objects** — versioned
Files/Records that go through `plan`/`apply` like every other definition, so a
skill edit shows up in `ptn plan` and "which skill version produced this
report" is always answerable. The failure mode to prevent is skills becoming an
*unversioned side-channel* of prompt text edited ad hoc; the moment that
happens the audit story develops a hole. No new primitive — an AgentSpec gains a
`skills` object with two tiers, each a list of refs to registered skill objects
(`name@version`):

```
AgentSpec.skills {
  always:   [<skill ref>],   // injected verbatim into the system prompt, every run
  routable: [<skill ref>],   // exposed to the model as a load_skill(name) tool
}
```

- **`always`** — skills the task must always conform to (e.g. `frontend-design`
  for anything emitting a webpage; a report-writing skill for any report). Their
  order and content are **stable per spec version**: a stable system-prompt
  prefix is what makes provider prefix-caching effective, which feeds directly
  into the latency budget.
- **`routable`** — situational skills (`clinical-report`, `rocket-diagnostics`)
  exposed via a `load_skill(name)` tool. **Progressive disclosure:** the model
  sees only names/descriptions until it opens the one for the sub-case it is
  actually in, so it pays context cost for that case alone.

(v0 prototype status: implements the `always` tier as a flat pinned list —
`skills: [{name, url|path, sha256}]`, fetched and hash-verified at startup and
injected into the system prompt. The `sha256` pin is how a skill object's bytes
are sourced and versioned; `routable` + `load_skill` is not yet built. Tracked
in `issues.md` I7 and `implementation.md` D2.)
---

# Appendix D — Distinctive *and* fast: themes, vocabulary, model routing, concurrency (added 2026-08-11)

Round-three findings on making the reports not look generic and not take
minutes. Full detail in the prototype's `implementation.md` (D5–D7) and
`issues.md` (I9–I13); the load-bearing points for v1:

**D.1 — Distinctiveness is bought back as data, deliberately.** A deterministic
component library under one stylesheet produces sameness by construction (the
price of correctness). Buy uniqueness back with **themes as token sets** —
`report_spec` names a `theme`; the render appends that theme's `:root` override
so one spec renders six different-looking pages with zero component change — and
with a **wider (still closed) ReportSpec vocabulary** (layout kinds, per-section
emphasis, richer section kinds). Most "AI design is bland" is really "the IR
couldn't express anything else." An **art-direction skill** of *negative*
constraints ("never open with three equal cards", "one accent, used <5 times",
"vary the rhythm", "commit to one concept") is what pushes a model off the
training-distribution mean. Themes and the component library are registry data,
not code.

**D.2 — Two render architectures, and which to default to.** *Structured
ReportSpec → deterministic themed render* is fast (the model writes a small
validated spec; the render is sub-second and correct-by-construction) and should
be the default. *Direct-HTML* (the agent writes the whole page) is worth exactly
one "look what it can design" vertical, but it is slower (~12k tokens) and more
variable (it drops elements the instructions require). The bounded-freestyle
slot (one free-form hero, the rest themed-deterministic) is the way to keep most
of the wow with little of the variance (issues.md I13).

**D.3 — Model capability is per output *shape*, so route by it.** A model's
tool-use and its structured-output ability are independent axes. Observed:
deepseek thrashes on tool use; gemini-flash is great on flat output and
direct-HTML but *cannot* emit a nested object schema (it collapses nesting to
strings); gpt-4o-mini and claude-sonnet emit the nested ReportSpec. So the
"split model roles" idea is really **route each task to a model that can produce
its declared output shape**, and the platform should be able to *warn at apply
time* when a spec pairs a known-incapable model with a shape (issues.md I9).
Corollary: show the model a concrete JSON example of the target, not just a
schema. Because the model is a string in a definition, all of this is config.

**D.4 — Concurrency is a runner-mode choice.** The single biggest latency win
was not a model: the dev subprocess runner is one child and *serialises*
concurrent runs (the origin of a multi-minute "three reports"). The **warm
container pool** runs them in parallel — wall-clock becomes the slowest single
run. The demo path is container mode with pool ≥ the number of concurrent
reports; only the model-harness env (the LLM key) crosses into the container,
never connector credentials (those stay executor-side behind the proxy).

**D.5 — One schema of record, one validator.** The runner validated model output
in Python and the executor re-validated the crossing Record with a stricter
engine; the two disagreed on `null`-for-optional and a *valid* report failed the
boundary. Two validators of one schema is a smell — v1 should have a single
authoritative validation contract (issues.md I10). And a per-run nonce at the
*front* of the system prompt defeats provider prefix-caching; keep the stable
instructions+skills block as the cacheable prefix and put run identity at the
end (issues.md I12).
