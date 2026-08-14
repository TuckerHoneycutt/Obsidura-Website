# pantheon-rs

Audience: whoever builds the rest of the executor. Job: say what exists, what it decides, and what comes next.

**P0 chunks 1 and 2** from the spec's build plan: the vocabulary crate, and the registry with `ptn plan`/`ptn apply`.

> Project-wide status and architecture: **[`../PANTHEON.md`](../PANTHEON.md)**. This file is the working reference for this crate.

## Status

| Chunk | State |
|---|---|
| 1. Vocabulary crate — primitives, kernel `Value`, schemars emission | **done** |
| 2. Registry + `ptn plan/apply` + validation | **done**, file-backed registry; Postgres is the next implementation of the same trait |
| 3. Run log + executor core | not started |
| 4. Runner image + stdio shim + resource proxy | not started (`pantheon-go/PROTOCOL.md` proposes the contract; `ptnfake` is a reference implementation of the proxy side) |

Acceptance test 1 and the plan-time half of acceptance test 2 are **met and tested** (`crates/ptn-registry/tests/acceptance.rs`).

## Try it

```bash
cargo test                       # 83 tests (vocab 33, registry 36, cli 14)
cargo run -p ptn-vocab --bin ptn-schema > /tmp/kernel.schema.json

# plan the real corpus: 12 generated task definitions + hand-authored wiring
cargo run -p ptn-cli -- plan  --registry /tmp/reg.json ../pantheon-go/definitions definitions
cargo run -p ptn-cli -- apply --registry /tmp/reg.json ../pantheon-go/definitions definitions
```

## Layout

| Path | Job |
|---|---|
| `crates/ptn-vocab/` | The kernel vocabulary. **Source of truth for the wire format.** |
| `crates/ptn-registry/` | Loading, validation, planning, and the registry store. |
| `crates/ptn-cli/` | The `ptn` command. |
| `testdata/wire/` | **The cross-language conformance corpus.** Read by Rust *and* Go. |
| `definitions/` | Hand-authored resources, triggers and wiring — the half Go never emits. |

## The two things worth understanding

### Rust is the source of truth, and now that is checkable

`pantheon-go/kernel` was hand-written before this crate existed, so its types are a mirror rather than a generation. `testdata/wire/` holds the two ends together: thirteen hand-written JSON files that **both** implementations must parse, re-serialise, and reproduce.

Hand-written, not generated from either side — generating the corpus from Rust would bake a Rust bug into the thing meant to catch bugs. It is an independent third opinion both sides answer to.

It earned its place immediately. It caught a real Go bug the moment it ran: a constructed zero `Envelope` marshalled `taint` as `null` where Rust produced `[]`, and spec §6 shows `taint: []`. Parsed envelopes were fine, which is why review had not caught it — the broken case was the one a *body* produces. Also pinned: chrono emits `+00:00` for UTC where Go emits `Z`. Both are valid RFC 3339, which is exactly why it had to be decided rather than discovered.

### Two definition directories, one registry

| Directory | Owns | Written by |
|---|---|---|
| `../pantheon-go/definitions/` | what an action **is** — contract, policy, resource needs | generated, drift-gated, never hand-edited |
| `definitions/` | how actions are **wired**, and what they connect to | hand-authored |

Invariant 3 says edges are derived from references, never authored as entities. `on:` and `then:` are those references, and Go never emits them — a generator that could write an edge has become a DSL. `ptn plan` takes both directories and validates them as one graph.

## What `ptn plan` checks

Everything runs at plan time. The alternative is discovering that two tasks disagree about the value crossing their seam when the second one receives it, three minutes into a run, in production.

| Rule | Catches |
|---|---|
| `unparseable` | malformed YAML, with line and column |
| `duplicate-name` | one `name@version` declared twice, naming both files |
| `unresolved-ref` | an `input`/`output`/`on`/`then`/`uses`/`refines` pointing at nothing |
| `undeclared-verb` | a task using a verb its resource does not expose — a production proxy denial, turned into a build error |
| `contract-mismatch` | a wired pair, or a trigger seam, disagreeing about the value crossing it (**acceptance test 2**) |
| `invalid-field` | a required field absent or unusable |

Every diagnostic names **file, field and rule**, as spec §7 requires. Every problem is reported, not just the first: an author who fixes one error per plan run is an author who stops running plan.

```
/tmp/badwiring/broken.yaml: on: contract-mismatch: trigger finance.audit_request@1 emits
  finance.LedgerQuery@1 but this task declares input finance.LedgerExtract@1
/tmp/badwiring/broken.yaml: then[0]: contract-mismatch: this task outputs
  finance.ReconciliationReport@1 but finance.flag_anomalies@1 declares input
  finance.AnomalyRequest@1; insert an adapter task or a field-path mapping
/tmp/badwiring/broken.yaml: uses[0].verbs: undeclared-verb: resource "ledger" does not
  expose verb "drop_table"; it exposes ["query"]
```

## Decisions made here that someone may want to revisit

Each is cheap to change now and expensive later, which is why they are listed rather than buried.

| Decision | Reasoning |
|---|---|
| The registry is file-backed, behind a `Store` trait | Spec §6 says Postgres. `ptn plan` is useful the moment it can validate a directory, and making that wait on a database would delay the only part an author touches. `PostgresStore` implements the same trait and changes no caller. |
| Orphans are reported, never removed | Deleting a definition out from under a mid-flight run is a different operation with different safety questions. Folding it into `apply` would answer them by accident. |
| No `--force` on a failed plan | A definition that fails validation is one the executor cannot run, so applying it only moves the failure later. |
| `uses:` resolves a resource by name, ignoring version | A resource is a connection to something that already exists, not a contract versioned independently. One place to change if that is wrong. |
| Deferred variants are absent, not stubbed | `imap`, `mcp`, `memory`, the `model` runner, `file_watch`/`socket`/`bus` triggers. An arm that parses but cannot run is an invitation to author a definition that plans cleanly and fails at runtime. |
| Durations are quoted strings with explicit units | A bare `1:30` is sexagesimal to a YAML 1.1 reader and a string to a YAML 1.2 one. A timeout meaning ninety seconds to one parser and ninety minutes to another is not found until production. |
| A schema is a definition with `kind: schema` | Spec §6 makes the schema registry a first-class thing. This required changing the Go emitter, which used to write loose `.json` files the loader would have had to special-case. |

## Next

1. **Chunk 3** — the run log (`run_events`) and executor core. The load-bearing schema; executor state is a fold of it.
2. **`PostgresStore`** — same trait, spec §6's actual storage.
3. **Chunk 4** — the shim and proxy, against `pantheon-go/PROTOCOL.md`. This is where invariant 4 stops being asserted and starts being demonstrated.
4. **Reverse the schema arrow** — generate `pantheon-go/kernel` from `ptn-schema` output and add a regenerate-and-diff gate. The corpus makes drift visible today; generation would make it impossible.
