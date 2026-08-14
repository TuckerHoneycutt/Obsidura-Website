# Architecture

Audience: the implementer. Job: the layers, the action shape, the package layout, and the two codegen directions that keep Rust the source of truth.

Everything here is a proposal to be ratified at `G-SPEC`, not a decision already made. Claims marked **[UNVERIFIED]** are load-bearing and must be measured before the design rests on them (`G-FACTS`).

## The five layers

```
  E  the deck            actions/finance, actions/telemetry, actions/clinical
                         ── the actual deliverable ──────────────────────────
  D  record types        Go structs generated from the schema registry
  C  definition emit     registry → YAML → ptn plan/apply
  B  authoring model     Action spec + typed Run func + Registry
  A  runtime SDK         kernel values, stdio shim, resource proxy client, tables
     ────────────────────────────────────────────────────────────────────────
     Pantheon executor (Rust) — untouched, by construction
```

Layers A–D are infrastructure and should total well under ~2.5k lines. Layer E is where the value is and where all the ongoing work goes. If A–D start growing, something has been designed wrong: the SDK's job is to be boring.

## Layer A — runtime SDK

| Package | Job | Notes |
|---|---|---|
| `kernel/` | The five `Value` variants, `Envelope`, `FileHandle`, `TableHandle`, `TypeRef` | **Generated** from the schemars-emitted JSON Schema. Committed, with a CI gate that regenerates and diffs. Never hand-edited. |
| `serve/` | JSON-RPC over stdio: read `{envelope, payload, capabilities}`, dispatch by task name, stream log events, write the output envelope | Panics recover into an `Error` value, not a process exit — a crashed body should produce a typed failure in the run log, not a mystery. |
| `res/` | The proxy client. `res.Postgres(ctx, "ledger").Query(...)`, `res.S3(...).Get/Put`, `res.HTTP(...).Request` | Dials the per-run UDS from `capabilities`. **The only egress in the entire library.** Enforce it — see "the one lint that matters" below. |
| `table/` | Streaming reader/writer over `TableHandle` (CSV/JSONL in v0) | Iterator style, bounded memory. The telemetry vertical exists partly to prove this. |
| `ptnfake/` | In-process fake proxy + fixture loader | Highest-leverage package for velocity. Lets an action be unit-tested with no container, no Postgres, no MinIO — just `go test`. Build it in Phase 1, not later. |

### The one lint that matters

A CI check that the `actions/` tree imports **no** network or database package — no `net/http`, no `database/sql`, no cloud SDK, no `os/exec`. Only `res/`. This is a ten-line `go list -deps` test and it converts "credentials never enter the container" from a policy into a property. Without it, the first person under deadline writes `http.Get` and nothing notices.

## Layer B — the authoring model

Go's type system fights heterogeneous registries. The idiomatic resolution is a generic registration function that erases into a uniform handler:

```go
type Spec struct {
    Name     string          // "finance.reconcile_ledger"
    Version  int             // ref becomes finance.reconcile_ledger@3
    Input    SchemaRef       // "LedgerQuery@1"
    Output   SchemaRef       // "ReconciliationReport@2"
    Uses     []ResourceUse   // {Name: "ledger", Verbs: []string{"query"}}
    Policy   Policy          // Timeout, Retry, Budget, Idempotent
    Summary  string          // one line; becomes the deck button's label
}

// Register is generic at the call site, erased inside.
func Register[In, Out any](
    r *Registry,
    spec Spec,
    run func(c *action.Ctx, in In) (Out, error),
)
```

Registration erases via a closure over `json.Unmarshal`/`Marshal`, so `Registry` stores `map[string]func(*Ctx, json.RawMessage) (json.RawMessage, error)` while authors still write fully typed bodies. One binary, many actions, dispatched by the task name that arrives in the envelope.

`Summary` is not decoration. The end-user product is a **GUI deck of buttons** (`Discussion Context.md:29`); the deck's labels should be generated from the registry, not maintained separately in a frontend.

## Layer C — definition emission, and why it is legal

`ptn-gen emit` walks the registry and writes one YAML file per action into `definitions/`, matching the Rust `kind:` discriminators, with refs by `name@version`.

Spec §1 permits "frontends that emit IR" explicitly, and §7 requires definitions be literal data. Both hold here: the emitter produces literal refs and parameters only. **It must be incapable of emitting an expression.** If the emitter ever grows a template or a conditional, invariant 2 has been broken from a new direction.

Two gates keep this honest:

1. **Drift gate** — `ptn-gen emit` output is byte-identical to what is committed, or CI fails. The YAML is the artifact of record; Go is how it is produced.
2. **Plan gate** — `ptn plan` on the emitted directory is clean, in CI, against a registry fixture.

Wiring (`on:`, `then:`) is **not** emitted from Go. Pipelines are composed in hand-authored YAML that references the emitted tasks. Go owns *what an action is*; YAML owns *how actions are wired*. Blurring that line is how this becomes a DSL.

## Layer D — record types, generated the other way

`ptn-gen structs --from-registry` turns registered Record schemas (`ReportSpec@1`, `Invoice@2`) into Go structs.

This is where Go earns its place over Python and is worth being explicit about: **rename a field in a vertical type and every action that touches it fails to compile.** That is the drift protection the discussion context flags as valuable (`:846`) and it is free here. In Python that same rename is a runtime `KeyError` in production, on the third Tuesday of the quarter.

### Refinement without refinement checking

Spec §11 defers refinement *checking*, but the compounding argument depends on it: an action written once against vertical `Invoice` should run on tenant `AcmeInvoice` (`Discussion Context.md:348, 601`). The Go-side approximation, which needs no executor support:

```go
type Invoice struct {
    ID     string          `json:"id"`
    Total  Money           `json:"total"`
    // ... vertical fields ...
    Raw    json.RawMessage `json:"-"`  // full tenant payload, preserved
}
```

Decode the tenant payload onto the vertical struct — extra fields land nowhere, which is fine, and `Raw` keeps them addressable for the rare action that needs one. Round-tripping preserves the tenant's shape. Narrowed constraints are the registry's problem, not Go's. This gives the compounding property today and costs nothing when real refinement checking arrives.

## Layer E — the deck

The deliverable. Organised so that generalisation is discovered, not predicted.

```
actions/
  core/        cross-vertical, discovered by extraction — not designed up front
               fetch.sql · fetch.s3_prefix · fetch.http_json
               table.join · table.aggregate · table.window
               render.report · export.pdf · notify.email
  finance/     reconcile_ledger · normalize_fx · match_receipts · flag_anomalies
  telemetry/   ingest_csv · segment_phases · window_stats · detect_anomalies
  clinical/    filter_cohort · manifest_scans · check_phi_scope
```

`core/` starts **empty**. It is populated by extracting the second occurrence of a pattern, never by anticipating the first. A `core/` designed before any vertical exists is a guess, and guesses in a shared package are expensive to unwind.

### The agentic question, deferred on purpose

Some deck entries want judgement, not determinism. v1 answer: **Go actions are `runner: script` only.** An agentic step stays a Python `runner: agent` task and the two are wired together in YAML as ordinary graph neighbours — which is exactly what invariant 5 promises works. A Go agent harness is a separate, later, optional decision; it is not needed to build the deck, and taking it on now doubles the scope for no deck value.

Clean split, no overlap: **Go image for deterministic actions, Python image for agentic ones.** Two images, two jobs. Not two images doing the same job.

## Repo placement

One repo, one Go module, `sdk/` and `actions/` as packages. Separate from the Pantheon repo, consumed as a versioned dependency.

Why separate: invariant 4 says wiring in a new harness touches zero executor code. If the Go library lives in a different repo and the Pantheon repo's diff for adopting it is one image reference, that invariant is demonstrated rather than asserted.

Why one module rather than splitting SDK from actions: two modules is real friction — every SDK change becomes a version bump and a dependency update — and there is currently one consumer. **Split when a second consumer appears**, not before.

Version-lock the SDK to the kernel schema version explicitly. A Go SDK built against kernel v1 talking to an executor on kernel v2 must fail loudly at handshake, not corrupt an envelope quietly. This depends on `04-open-questions.md` Q1.

## Where Go is expected to pay off, and how to check

Each of these is a hypothesis with a measurement, not a benefit.

| Claim | Status | How to settle it |
|---|---|---|
| Single static binary starts fast enough that the warm pool is unnecessary for Go actions | **[UNVERIFIED]** | Measure cold start of the Go runner image vs the Python one, same host. Keep the warm pool in v1 regardless — do not fork executor behaviour to chase this. |
| Goroutines let one action fan out over hundreds of proxy calls (e.g. 200 receipt PDFs) | **[UNVERIFIED, and possibly false]** | Depends entirely on whether the proxy handles concurrent requests on one UDS. See `04-open-questions.md` Q3. If the proxy serialises, this benefit is zero and the design must not assume it. |
| Compile-time schema drift detection catches renames Python would find in production | High confidence, still worth demonstrating | Named mutation: rename a field in a vertical type, confirm the build reddens. This is a mutation-table entry, not a claim in a doc. |
| One binary holding many actions is cheaper to operate than per-action images | Follows from B4 being a bonus chunk | No measurement needed; it is the same argument the spec already makes for one generic Python image. |

## Testing

| Level | Mechanism |
|---|---|
| Unit | `ptnfake` in-process proxy. No containers. Should be the overwhelming majority, and fast enough to run on save. |
| Golden | Reuse the three synthetic datasets from P0 chunk 6. **Do not build a second fixture corpus** — divergent fixtures are worse than no fixtures. |
| Mutation | A named mutation table per action, in its test file. A mutation that stays green fails review and is never suppressible (`aurora-agent/skills/mutation-proof`). |
| Integration | The real binary, real shim, real proxy, against a stack from `./aurora branch up`. Per prime directive 1, never against prod. |
| Contract | The drift gate and the plan gate from Layer C, plus the import lint from Layer A. All three are cheap and all three catch things review will not. |
