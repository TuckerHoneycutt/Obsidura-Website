# pantheon-go

Audience: anyone writing or reviewing a deck action. Job: say what this module is, how to add an action, and what will refuse you.

A library of callable business processes — **the deck** — authored as typed Go actions, plus the thin SDK that makes them ordinary Pantheon tasks. Twelve actions across three verticals today. Zero third-party dependencies.

> New to this module? **[`../PANTHEON.md`](../PANTHEON.md)** is the tour — architecture, all twelve actions, the data flow, and what is measured versus asserted. This file is the working reference for writing one.

**This is not on the Pantheon demo path.** See `../README.md` for where it sits.

## Status

| | |
|---|---|
| Builds, vets, tests, `-race` clean | yes, Go 1.26 |
| Runs against a real executor | **no — one does not exist yet** |
| Runner protocol | proposed in `PROTOCOL.md`, implemented here, not agreed with anyone |
| Kernel types | hand-written; the arrow reverses when the Rust vocabulary crate lands |

Everything is exercised end to end against `ptnfake`, which serves a **real Unix socket speaking the real protocol** with real grant enforcement. What is not exercised is a real executor, real Postgres, real MinIO. `04-open-questions.md` lists what only the Rust side can answer.

## Try it

```bash
go test ./...                  # everything, ~2s
go run ./cmd/deck-demo         # all three verticals against the fixtures, printed
go run ./cmd/ptn-gen catalog   # the GUI deck's buttons, as JSON
go run ./cmd/ptn-gen check     # the drift gate
```

`deck-demo` exists because passing tests are not a result a human has looked at. It found three defects the tests had not: a documented `landed` phase that was never produced, a fixture comment that misdescribed its own data, and two anomaly rules with no test at all.

## Layout

| Path | Job |
|---|---|
| `kernel/` | The five kernel `Value` variants, the envelope, the handles. Wire format pinned by test. |
| `res/` | The resource proxy client. **The only egress in the module.** |
| `action/` | `Spec`, `Registry`, `Register[In,Out]`, and the `Ctx` a body receives. |
| `serve/` | The stdio shim. Implements `PROTOCOL.md` and holds no business logic. |
| `table/` | Chunked iteration over Table handles. Memory does not scale with row count. |
| `schema/` | Go types → JSON Schema. Provisional; see the package doc. |
| `emit/` | Registry → YAML definitions + the drift gate. |
| `ptnfake/` | Real-socket fake proxy with real grants and an audit log. |
| `fixtures/` | One synthetic corpus, shared. Deliberately contains planted defects. |
| `actions/core/` | What two verticals turned out to need. Was empty until they existed. |
| `actions/finance/`, `actions/telemetry/`, `actions/clinical/` | The deck. |
| `deck/` | Assembles every vertical; produces the GUI catalog. |
| `definitions/` | **Generated, committed.** The artifact `ptn apply` reads. |
| `lint/` | Build-time properties review cannot be trusted to enforce by reading. |

## Adding an action

```go
action.Register(r, action.Spec{
    Name:    "finance.flag_anomalies",
    Version: 1,
    Input:   kernel.Ref("finance.AnomalyRequest", 1),
    Output:  kernel.Ref("finance.AnomalyReport", 1),
    Uses:    []action.ResourceUse{{Name: "ledger", Verbs: []string{"query"}}},
    Policy:  action.Policy{Timeout: 60 * time.Second, Retry: 2, Idempotent: true},
    Summary: "Flag unusual ledger entries.",
}, func(c *action.Ctx, in AnomalyRequest) (AnomalyReport, error) {
    rows, err := c.Postgres("ledger").Query(sql, in.Period)
    ...
})
```

Then `go run ./cmd/ptn-gen emit` and commit `definitions/`. Registration is generic at the call site and erased inside, so adding the two-hundredth action touches no dispatch code.

## What will refuse you, and why

These are properties, not conventions. Each one exists because review under deadline will not catch the thing it catches.

| Refusal | Where | Because |
|---|---|---|
| An action importing `net/http`, `database/sql`, `os` | `lint/imports_test.go` | Credentials live executor-side and never reach the container (spec §8). One plausible-looking line bypasses capability enforcement, taint recording, budget metering and the audit log at once. |
| A resource call the action did not declare in `Uses` | `action/ctx.go` | The proxy would refuse it in production anyway; failing locally turns that into a clear message on the first unit test. |
| `Retry > 0` without `Idempotent` | `action.Register`, at init | Retrying a non-idempotent action is how one failure becomes two ledger entries. |
| An empty `Summary` | `action.Register`, at init | It is the deck's button label. An action with no summary is an unlabelled button. |
| Committed `definitions/` differing from the registry | `emit.Check`, in CI | The YAML is the artifact of record; without a gate it and the code diverge and the definitions stop describing what runs. |
| Emitted YAML containing `on:`, `then:`, or `${` | `emit/emit_test.go` | Invariant 3 (edges are derived, not authored) and invariant 2 (no expression language). Go owns what an action *is*; YAML owns how actions are *wired*. |
| An unknown kernel `Value` kind on the wire | `kernel/value.go` | The kernel is a closed set of five. Skipping an unrecognised variant hands downstream tasks a zero value and the failure surfaces far from its cause. |
| A kernel/protocol version mismatch | the `hello` handshake | An SDK on kernel v1 talking to an executor on kernel v2 misreads envelopes and emits plausible wrong output — the most expensive failure available. |

## Conventions worth knowing before you write one

- **Money is never `float64`.** `core.Money` is minor units plus a currency, parsed from strings. `Add` refuses to mix currencies. A ledger reconciled in binary floating point invents imbalances of 0.000000001 and hides ones of 0.01.
- **Resource names are constants, not input fields.** `uses:` is a static declaration; a name arriving at runtime cannot be checked against it.
- **Rows are read by name, never by index.** A tenant that adds a column shifts every position.
- **Actions do not know who is asking.** No `requester`, no `user_id`. Scope is applied proxy-side from the run's grants. An action that filters by user has put an authorisation decision where nobody audits it.
- **Large data travels by handle.** `table.Each` iterates in chunks; `table.Builder` refuses past 100k rows so "this should be streaming" announces itself rather than arriving as an OOM.
- **Reports sort their output.** Two runs over identical data must be byte-identical, or the report cannot be reviewed by diff — and one nobody can diff stops being reviewed.

## Measurements

Per the reality-gate rule: measured, not asserted.

| Claim | Measured | Caveat |
|---|---|---|
| Runner cold start | 4.0 ms min / **5.2 ms median** / 215 ms max over 20 spawns, process start → `hello` reply. 4.3 MB static binary. | Darwin, bare process, no container. **This does not settle whether the warm pool is needed** — spec §8's pool exists because of container plus interpreter start, and container start is not measured here. The max is first-run page-cache cost. |
| 25,000-sample telemetry ingest + segmentation + windowing | completes in the `deck-demo` run; `-race` clean | Fake proxy, in-memory. Real S3 latency not included. |
| Proxy concurrency benefit | **not measured, possibly zero** | Open question Q3. The client multiplexes; if the real proxy serialises, everything still works with no speedup. No correctness depends on it. |

## Testing conventions

- **Assert on artifacts, not spies.** `ptnfake` records an audit log; tests read that. Nothing counts mock calls.
- **Every vertical carries a named mutation table** at the top of its test file: a change to production code, and the test that must redden. A mutation that stays green fails review and is never suppressible.
- **Fixtures are deliberately wrong.** A duplicate posting, a missing receipt, an orphan receipt, a pressure spike, a ragged CSV row. Every defect exists because some action is supposed to find it; a clean fixture tests only the path that was never going to break.
- **Watch for vacuous assertions.** One test here originally checked field names by marshalling a zero value — with `omitempty`, that passes no matter what fields exist. Guards against that now sit beside the tests that need them.
