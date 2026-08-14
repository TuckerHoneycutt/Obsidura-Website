# Pantheon — Built vs. Spec

Audit of the working tree against `website/specs/pantheon-spec-v0.md`.
Every figure below was measured, not recalled.

```
    P0 chunks    ##--------   2 of 10 done, 3 partial
    Acceptance   #-------     1 of 8 met, 2 partial
    Invariants   ###--        3 of 5 held, 1 unprovable yet
    Tests        258 passing  (175 Go + 83 Rust)
    Coverage     86.9%        Go library, statement, merged
    Docs         0            undocumented exports, both languages
```

**The one thing to know before reading further:** there is no executor, no shim
and no resource proxy. Chunks 3 and 4 are unbuilt. The runner protocol is a
*proposal* nobody has agreed to, and invariant 4 is **asserted, not
demonstrated**. Everything below states which side of that line it sits on.

Two codebases:

| Module | Covers | Language |
|---|---|---|
| `pantheon-rs/` | P0 chunks 1–2: vocabulary crate, registry, `ptn plan/apply` | Rust |
| `pantheon-go/` | The deck: 12 actions, 3 verticals, runner SDK | Go |

---

## Contents

1. [Build plan](#1-build-plan-spec-10)
2. [Acceptance tests](#2-acceptance-tests-spec-9)
3. [The five invariants](#3-the-five-invariants-spec-1)
4. [Architecture](#4-architecture)
5. [The deck](#5-the-deck)
6. [What is verified](#6-what-is-verified)
7. [Properties, not conventions](#7-properties-not-conventions)
8. [The wire corpus](#8-the-wire-corpus)
9. [Bugs found by building](#9-bugs-found-by-building)
10. [Deferred and correctly absent](#10-deferred-and-correctly-absent)
11. [Known gaps, ranked](#11-known-gaps-ranked)
12. [Next](#12-next)
13. [Reproducing this](#13-reproducing-this)

---

## 1. Build plan (spec §10)

| # | P0 chunk | State | Evidence |
|---|---|---|---|
| 1 | Vocabulary crate — primitives, kernel `Value`, schemars | **done** | `ptn-vocab`, 33 tests, `ptn-schema` emits the document |
| 2 | Registry + `ptn plan/apply` + validation | **done** | 45 definitions applied, 6 validation rules, 50 tests |
| 3 | Run log + executor core | — | not started |
| 4 | Runner image + stdio shim + resource proxy + grants | **half** | client side, protocol proposal, `ptnfake` reference impl. Server side absent. |
| 5 | Connectors: postgres, s3, http | **half** | typed clients and fakes. No real MinIO or Postgres. |
| 6 | Fixtures workstream — three synthetic datasets | **done** | one corpus, defects planted on purpose |
| 7 | Report template + component library + render task | — | not started |
| 8 | Agent task — Pydantic AI, ReportSpec, repair loop | — | `AgentSpec` and `Runner::Agent` exist in the vocabulary only |
| 9 | Demo shell page + status endpoint | — | not started |
| 10 | Approval primitive + acceptance tests | **partial** | `ApprovalGate` parses and validates. No suspend/resume. |

---

## 2. Acceptance tests (spec §9)

| # | Test | State |
|---|---|---|
| 1 | `ptn apply` succeeds; an invalid definition is rejected with a clear, located error | **met** |
| 2 | Cron fires a two-task chain; the seam validates contracts, and a mismatched pair is rejected at plan time | **half** — plan-time rejection met; no cron, no execution |
| 3 | Webhook to report pipeline across all three connector types | blocked on 3, 4, 7 |
| 4 | Same prompt, two users, different clinical reports; audit shows each scope decision | **logic met** — proven as a millisecond unit test against the fake proxy. No rendered report. |
| 5 | Approval gate suspends across an executor restart | blocked on 3 |
| 6 | Malformed agent output repaired via bounded retry, visible in the run log | blocked on 8 |
| 7 | Executor killed mid-run; restart completes from the log | blocked on 3 |
| 8 | The human test — one prompt, three beautiful reports | blocked on the whole path |

Every blocker is chunk 3, 4, 7 or 8. **No test is blocked on something already
built.**

---

## 3. The five invariants (spec §1)

**1 — Rust in the executor is constant in the number of business types.**
Holds. Twelve actions added zero lines to `ptn-vocab`. All business meaning is
a `Record`, and the vocabulary's whole relationship with one is
`validate(schema, data)`.

**2 — No expression language in YAML, ever.**
Holds, and is tested. `TestEmittedYAMLContainsNoExpressionSyntax` greps
generated output for `${`, `{{`, `$(`. Telemetry's `Limit` type is structured
data — a column, a bound, a rate — specifically so that a rule cannot smuggle
an expression in through the payload instead.

**3 — Edges are derived from references, never authored.**
Holds by construction. The Go emitter has no way to write `on:` or `then:`, and
`TestEmittedTasksDeclareNoWiring` enforces it. Wiring lives in a separate,
hand-authored directory.

**4 — No framework is hardcoded at the executor level.**
**Asserted, not demonstrated.** Cannot be shown until an executor exists. This
is the single largest open risk in the project.

**5 — Task graph shapes stay composable.**
Partly. Go and Python tasks are interchangeable at the schema level and
`ptn plan` checks the seam between them. Unproven at runtime.

---

## 4. Architecture

### Where the two modules meet

```
   definitions/                            definitions/
   (generated by Go, drift-gated)          (hand-authored)
   what an action IS                       how actions are WIRED
            |                                     |
            +------------------+------------------+
                               |
                          ptn plan            <- resolves refs across both,
                          ptn apply              checks every seam
                               |
                          registry (45 defs)
```

Invariant 3 is why the split exists. A generator that could write an edge has
become a DSL, so the Go emitter simply cannot.

### The Go library, five layers

```
  E  THE DECK        actions/finance   actions/telemetry            2,466 lines
                     actions/clinical  actions/core                 <- the deliverable
     ------------------------------------------------------------
  D  RECORD TYPES    schema/    Go structs <-> JSON Schema
  C  DEFINITIONS     emit/      registry -> YAML + drift gate       2,542 lines
  B  AUTHORING       action/    Spec, Registry, Register[In,Out]    <- the SDK
  A  RUNTIME SDK     kernel/  serve/  res/  table/  ptnfake/
     ------------------------------------------------------------
                     Pantheon executor (Rust) — untouched, by construction
```

The SDK's job is to be boring. If A–D start growing faster than E, something
has been designed wrong.

### The finance pipeline, end to end

```
  finance.audit_request          webhook trigger, hand-authored YAML
         | emits LedgerQuery@1
         v
  fetch_ledger                   postgres.query -> proxy -> grant row-filter
         |                       parses money to MINOR UNITS once, at the edge
         | LedgerExtract@1       returns a Table handle; rows never inline
         v
  normalize_fx                   http.request -> proxy -> URL allowlist
         |                       refuses to re-base someone else's rate table
         | NormalizedLedger@1
         +---------------+-------------------+
         v               v                   v
  reconcile_ledger  match_receipts     flag_anomalies
  exact integers    gaps AND orphans   MAD, not stddev
  -> imbalance      -> both sides      -> candidates, not verdicts
```

Every downstream action **refuses a mixed-currency ledger** rather than summing
it. That refusal is only useful because `normalize_fx` is a *separate* action —
so the conversion is visible in the graph and its rates land in the audit
trail, instead of hiding inside a reconciliation.

---

## 5. The deck

Twelve actions. Five need no resource at all — they read only the handle passed
to them, which is worth stating rather than leaving implied.

### finance — postgres ledger, S3 receipts, HTTP FX

| Action | In → Out | Needs |
|---|---|---|
| `fetch_ledger` | `LedgerQuery` → `LedgerExtract` | `ledger` |
| `normalize_fx` | `FXNormalizeRequest` → `NormalizedLedger` | `fx` |
| `reconcile_ledger` | `ReconcileRequest` → `ReconciliationReport` | — |
| `match_receipts` | `ReceiptMatchRequest` → `ReceiptMatchReport` | `receipts` |
| `flag_anomalies` | `AnomalyRequest` → `AnomalyReport` | — |

### telemetry — tens of thousands of rows, never resident

| Action | In → Out | Needs |
|---|---|---|
| `ingest_csv` | `TelemetryIngestRequest` → `TelemetryExtract` | `telemetry` |
| `segment_phases` | `PhaseRequest` → `FlightPhases` | — |
| `window_stats` | `WindowStatsRequest` → `WindowStats` | — |
| `detect_anomalies` | `TelemetryAnomalyRequest` → `TelemetryAnomalyReport` | — |

### clinical — carries the permission beat

| Action | In → Out | Needs |
|---|---|---|
| `filter_cohort` | `CohortQuery` → `Cohort` | `records` |
| `manifest_scans` | `ScanManifestRequest` → `ScanManifest` | `scans` |
| `check_phi_scope` | `PHIScopeRequest` → `PHIScopeReport` | — |

Every action is `Idempotent: true, Retry: 2`. Timeouts: 30s for the PHI check,
60s for five, 120s for five, 300s for telemetry ingest — the largest single
object anything fetches.

### The permission beat, as a unit test

Spec §2's governance demo, normally a demo-day hope, is an ordinary test that
runs in milliseconds:

```go
request := clinical.CohortQuery{Status: "admitted"}   // the SAME value, both users

unrestricted.Invoke(r, "clinical.filter_cohort", request)  // -> 5 patients
scoped.Invoke(r, "clinical.filter_cohort", request)        // -> 2 patients
```

```
user A (full access)       5 patients [p-001 p-003 p-004 p-005 p-006], 4 scans
    audit: ALLOW records.query select patient_id, ward, status...
user B (cardiology only)   2 patients [p-001 p-006], 1 scan
    audit: ALLOW records.query select patient_id, ward, status... [scope: 2/5 rows]
    audit: ALLOW scans.list  prefix=scans/                        [scope: 1/5 rows]
```

It works **because `filter_cohort` does not participate**. It issues one query
with no user predicate and the proxy narrows the result. `CohortQuery` carries
no identity field, and a test asserts it never will.

---

## 6. What is verified

| | Go | Rust |
|---|---:|---:|
| Tests | 175 functions | 83 |
| Source / test lines | 6,572 / 4,985 | 2,969 / 860 |
| Statement coverage | **86.9%** | see note |
| Undocumented exports | **0** | **0** |
| Third-party dependencies | **0** | 5 |
| Formatter | `gofmt` clean | `cargo fmt` clean |
| Linter | `go vet` clean | `clippy` clean |
| Race detector | clean | — |

Coverage is Go statement coverage, union-merged across test binaries, excluding
`cmd/` mains. Rust has no built-in statement coverage; every module carries
unit tests and both binaries are tested through their CLI.

```
  actions/core       96.4  ###################-
  deck               94.1  ##################--
  fixtures           94.1  ##################--
  schema             93.1  ##################--
  res                91.8  ##################--   <- the sole egress
  emit               88.9  #################---
  actions/finance    88.1  #################---
  actions/clinical   86.4  #################---
  actions/telemetry  85.8  #################---
  ptnfake            84.9  #################---
  action             84.6  ################----
  kernel             82.9  ################----
  table              77.0  ###############-----
  serve              73.6  ##############------
  cmd/*               0.0  --------------------   <- thin main()s, by design
```

`serve` and `table` sit lowest because their uncovered branches are I/O failure
paths — a stdout write that fails, a cursor read that errors — reachable only
by breaking a pipe underneath a live process.

### Named mutation tables

Twelve test files carry one: a change to production code, and the test that
must redden when it is made. **79 entries.** A mutation that stays green fails
review and is never suppressible.

```
  actions/finance     12  ############
  actions/telemetry    8  ########
  schema               8  ########
  actions/core         7  #######
  action              11  ###########   (action_test + ctx_test)
  actions/clinical     6  ######
  emit                 6  ######
  res                  6  ######
  deck                 5  #####
  serve                5  #####
  table                5  #####
```

### The fixtures are deliberately wrong

One shared corpus. Every defect exists because some action is supposed to find
it — a clean fixture tests only the path that was never going to break.

| Planted defect | Found by |
|---|---|
| `e-004`/`e-005`: identical account, amount, day, description | `flag_anomalies` → duplicate |
| `e-006` references a receipt that does not exist | `match_receipts` → missing |
| `e-007` references no receipt at all | `match_receipts` → *distinct* reason |
| `e-999.pdf` belongs to no ledger entry | `match_receipts` → orphan |
| Debits and credits do not net to zero | `reconcile_ledger` → imbalance |
| 96.4 bar chamber-pressure spike at t=8 | `detect_anomalies` → max excursion |
| One ragged CSV row, one blank altitude cell | `ingest_csv` → skipped vs. null |
| `p-004`, `p-005` have no scans | `manifest_scans` → gap list |

---

## 7. Properties, not conventions

Each of these is enforced by a test that **has been shown to redden**. A lint
nobody has watched fail proves nothing.

| Property | Enforced by | Guards against |
|---|---|---|
| Actions cannot import `net/http`, `database/sql`, `os` | `lint/imports_test.go` | Credentials never reach the container (§8). One plausible line bypasses capability checks, taint, metering and audit at once. |
| Only `res/` may reach the network | `lint/imports_test.go` | The egress surface growing past one file. |
| A resource call not in `Spec.Uses` | `action/ctx.go`, at call time | A production proxy denial, instead of a clear message on the first unit test. |
| `Retry > 0` without `Idempotent` | `action.Register`, at init | One failure becoming two ledger entries. |
| An empty `Summary` | `action.Register`, at init | An unlabelled button on the deck. |
| Committed YAML differing from the registry | `emit.Check`, in CI | Definitions that stop describing what runs. |
| Emitted YAML containing `on:`, `then:`, `${` | `emit_test.go` | Invariants 2 and 3, broken from the inside. |
| An unknown kernel `Value` kind | `kernel`, `ptn-vocab` | A zero value handed downstream, failing far from its cause. |
| Protocol or kernel version mismatch | the `hello` handshake | v1 talking to v2, misreading envelopes, emitting plausible wrong output. |
| A verb a resource does not expose | `ptn plan` | A production denial, turned into a build error. |
| A mismatched task seam | `ptn plan` | **Acceptance test 2.** |
| CLI exit codes 0/1/2/3 | `ptn-cli/tests/cli.rs` | CI trusting an exit code nobody tested. |

### Conventions with a failure mode behind them

**Money is never `float64`.** `core.Money` is minor units plus a currency,
parsed from strings. A ledger reconciled in binary floating point invents
imbalances of 0.000000001 and hides ones of 0.01. `float64(1.15)*100` is
`114.99999999999999`, which truncates to 114.

**Resource names are constants, not input fields.** `uses:` is a static
declaration; a name arriving at runtime cannot be checked against it.

**Rows are read by name, never by index.** A tenant adding a column shifts
every position — the action keeps working *and reads the wrong column*.

**Actions do not know who is asking.** No `requester`, no `user_id`. Scope is
applied proxy-side. An action that filtered by user would put an authorisation
decision where nobody audits it, and would be indistinguishable from one that
forgot to.

**Large data travels by handle.** `table.Builder` refuses past 100k rows, so
"this should be streaming" announces itself as an error rather than arriving as
an OOM.

**Reports sort their output.** Two runs over identical data must be
byte-identical, or the report cannot be reviewed by diff — and one nobody can
diff stops being reviewed.

---

## 8. The wire corpus

`pantheon-rs/testdata/wire/` holds 13 hand-written JSON files that **both**
implementations must parse, re-serialise and reproduce.

Hand-written, not generated from either side. Generating it from Rust would
bake a Rust bug into the thing meant to catch bugs; a hand-written corpus is an
independent third opinion both sides answer to.

**It found a real bug on first run.** A *constructed* zero `Envelope` in Go
marshalled `taint` as `null` where Rust produced `[]`, and spec §6 shows
`taint: []`. Parsed envelopes were fine — which is exactly why review had
missed it, since the broken case is the one a task body produces.

It also forced a decision that would otherwise have been discovered in
production: chrono emits `+00:00` for UTC, Go emits `Z`. Both are valid
RFC 3339. Neither is wrong, which is precisely why it had to be pinned.

This is what makes "Rust is the source of truth" checkable rather than
aspirational.

---

## 9. Bugs found by building

| # | Bug | Found by |
|---|---|---|
| 1 | Zero `Envelope` emitted `taint: null`, not `[]` | wire corpus, first run |
| 2 | `TypeRef` marshalled its zero value as `""` but refused to unmarshal it — a wire type that could not round-trip itself | serve tests |
| 3 | Documented flight phase `landed` was never produced; the post-touchdown tail read as one enormous `coast`, plus a phantom one-sample `ascent` | reading `deck-demo` output |
| 4 | Schema derivation skipped embedded fields of unexported struct types, describing a shape `encoding/json` never produces | new `schema` tests |
| 5 | `ptn -h` exited 2; help only worked *after* a command | new CLI tests |
| 6 | A fixture comment claimed one planted weekend posting; there were three | reading `deck-demo` output |
| 7 | Two anomaly rules had no test at all | coverage audit |
| 8 | One test was vacuous — checked field names by marshalling a zero value, which `omitempty` hides entirely | self-review |

**Six of eight were invisible to a passing test suite.** Three came from
*reading output*, two from writing tests for untested code, one from a corpus
that made two implementations disagree out loud.

That is the argument for `cmd/deck-demo` existing at all: assertions only check
what you thought to assert.

---

## 10. Deferred and correctly absent

Present in neither codebase, and **deliberately not stubbed**. An enum arm that
parses but cannot run invites a definition that plans cleanly and fails at
runtime. Each is refused at parse time, with a test proving it:

`imap`, `mcp`, `memory` connectors — `file_watch`, `socket`, `bus` triggers —
the `model` runner kind — Arrow-backed Tables — the `Message` kernel type —
taint *enforcement* — refinement *checking* — the promotion ladder — personas
and memory policy — dynamic in-action routing — SSO.

`refines` and `taint` **are** carried, nullable and recorded respectively, so
enabling them later is a policy change rather than a retrofit of data nobody
kept.

---

## 11. Known gaps, ranked

**1. No executor.** Invariant 4 is unproven and the protocol is unratified.
Every integration claim rests on a document nobody has agreed to. Cheap to
change now, expensive later. *This blocks everything else.*

**2. The schema arrow still runs backwards.** `pantheon-go/kernel` is
hand-written; it should be generated from `ptn-schema` output with a
regenerate-and-diff gate. The corpus makes drift *visible* today; generation
would make it *impossible*.

**3. The registry is file-backed, not Postgres** (§6). Behind a `Store` trait,
so `PostgresStore` changes no caller. Deliberate — gating `ptn plan` on
standing up a database would have delayed the only part an author touches.

**4. Q3 is unmeasured.** Does the real proxy multiplex? The client is correct
either way; the *speedup* may be zero.

**5. No integration test against a branch stack**, contra prime directive 1.
Everything is unit-level against `ptnfake`.

**6. The Phase-2 decision gate was never held.** The plan says judge
Go-versus-Python after one vertical. Three exist and nobody has made the
comparison. **Still owed.**

---

## 12. Next

In spec order:

```
  chunk 3   Run log + executor core      the load-bearing schema;
                                         executor state is a fold of it
  --        PostgresStore                same trait, spec §6's real storage
  chunk 4   Shim + proxy                 <- invariant 4 stops being a claim here
  --        Reverse the schema arrow     generate kernel/ from ptn-schema,
                                         add the regenerate-and-diff gate
  chunk 7   Report template + renderer   the demo's "beauty first" beat
```

---

## 13. Reproducing this

```bash
# Go — 175 tests, race-clean, drift-gated
cd pantheon-go
go test ./...
go test -race ./...
go run ./cmd/ptn-gen check          # committed YAML matches the registry
go run ./cmd/deck-demo              # three verticals, printed for a human

# Rust — 83 tests, clippy and fmt clean, docs complete
cd ../pantheon-rs
cargo test
cargo clippy --all-targets
cargo run -p ptn-vocab --bin ptn-schema > kernel.schema.json

# Both — plan and apply the real 45-definition corpus
cargo run -p ptn-cli -- plan  --registry /tmp/r.json ../pantheon-go/definitions definitions
cargo run -p ptn-cli -- apply --registry /tmp/r.json ../pantheon-go/definitions definitions
```

**A note on the coverage figure.** `go tool cover` *concatenates* rather than
unions profiles under `-coverpkg`, and under-reports as a result — it gives
69.8% where the true union is 86.9%. The number above is a manual union, taking
the maximum hit count per block across test binaries.

---

### Where to go next in the docs

| Document | Job |
|---|---|
| `pantheon-go/README.md` | Working reference for writing a deck action |
| `pantheon-go/PROTOCOL.md` | The proposed runner wire contract |
| `pantheon-rs/README.md` | The vocabulary crate and `ptn plan/apply` |
| `pantheon-rs/testdata/wire/README.md` | The cross-language corpus contract |
| `01-constraints.md` … `05-status.md` | The original plan, and what deviated from it |
