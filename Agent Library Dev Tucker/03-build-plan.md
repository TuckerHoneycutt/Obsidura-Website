# Build plan

Audience: the implementer, and Tucker deciding whether to fund each phase. Job: ordered phases with a deliverable and an exit condition each, plus the kill criteria that stop this cleanly if it turns out to be wrong.

Sequencing rule, stated once and applying throughout: **nothing in this plan competes with the Pantheon demo for attention.** If a phase needs a Rust-side change, that change waits until after the demo ships, and the phase waits with it.

## Phase 0 — the spike (~2 days, has a kill criterion)

**One action. End to end. Through the real shim, against the real proxy.**

Pick the smallest useful one — `fetch.sql` against the finance ledger, returning a `Table` handle. No SDK, no registry, no codegen, no abstraction. Hand-write the JSON-RPC framing. Hardcode the schema. Make it ugly.

| Deliverable | A Go binary that a Pantheon run invokes as a task and whose output validates at the seam. |
|---|---|
| **Exit condition** | A run completes with a Go task in the graph, and the diff to the Pantheon repo is an image reference and nothing else. |
| **What it actually proves** | Invariant 4, by construction. Everything after this is engineering; this is the only phase that answers a question. |

**Kill criteria — abandon or escalate if any hold:**

1. Wiring the Go runner in requires an executor code change. That means invariant 4 was already broken, and *that* becomes the finding worth reporting. It is a better outcome than a library.
2. The runner protocol has no version handshake and the Rust side will not add one (Q1). A second runner image against an unversioned protocol is a silent-corruption generator.
3. The proxy cannot serve a non-Python client at all — e.g. the "protocol" is in practice a Python-object convention. Then the real work is specifying the protocol, and this plan restarts after that.

Answer `04-open-questions.md` Q1–Q4 during this phase. Several are blocking and cheap to resolve by reading the executor source.

## Phase 1 — the SDK (layers A–D)

Only after Phase 0 exits green. Build in this order, because each step is testable using the one before:

1. `kernel/` + the codegen from schemars output, with the regenerate-and-diff CI gate.
2. `serve/` — extract and generalise Phase 0's hand-written framing. Panic recovery into an `Error` value.
3. `res/` — the proxy client, three connectors. Plus **the import lint** (`02-architecture.md`), on the day `res/` lands, not later.
4. `ptnfake/` — before any real action is written. Actions written before the fake exists get tested badly and stay tested badly.
5. `table/` — streaming reader/writer.
6. `ptn-gen emit` + drift gate + plan gate.
7. `ptn-gen structs --from-registry`.

**Exit condition:** Phase 0's action, rewritten as a registered `Action` with generated types, still passes its integration test — and its unit test now runs in milliseconds with no container.

## Phase 2 — one vertical, completely

**Finance.** It is the richest of the three (postgres ledger + S3 receipt PDFs + HTTP FX API — all three connector kinds), and it is the one whose correctness a non-specialist can actually check.

Four to six actions: `reconcile_ledger`, `normalize_fx`, `match_receipts`, `flag_anomalies`. Every one ships a named mutation table. `core/` stays empty during this phase, deliberately.

**Exit condition:** a finance report pipeline runs entirely on Go actions, against a branch stack, producing output a human agrees is correct. Plus: measurements for the two `[UNVERIFIED]` claims in `02-architecture.md` — cold start, and proxy concurrency behaviour under a real fan-out.

**Decision gate here, and it is the real one.** Phase 2 is where the approach is judged. If writing a finance action in Go is meaningfully more work than the Python equivalent and the typing is not buying enough, stop at one vertical and keep Go for the narrow set of actions that are hot, repeated, or safety-relevant. That is a perfectly good outcome and should not feel like failure — it is the correct scope for the evidence.

## Phase 3 — the second and third verticals

Telemetry, then clinical. Telemetry stresses `table/` (tens of thousands of rows, bounded memory). Clinical stresses the permission story (per-user scope decisions visible in the audit log).

**This is where `core/` gets populated** — by extracting the patterns that appeared twice, never by anticipation. Expect the extraction to be uncomfortable and to change some Phase 2 signatures. That is the phase working correctly.

**Exit condition:** three verticals, and a `core/` that was discovered rather than designed.

## Phase 4 — the deck surface

Generate the GUI button deck's catalog from the registry: name, summary, input schema, required grants. The end-user product is a deck of repeatable actions (`Discussion Context.md:29`), and its labels should have exactly one source.

Small phase. Mostly a JSON endpoint and a discipline about `Spec.Summary`.

## Phase 5 — optional, and explicitly not scheduled

A Go agent harness, promoting `runner: agent` tasks into Go too. Revisit only if Phases 2–3 make the case and only after the demo. Nothing in Phases 0–4 depends on it.

## Effort shape

Deliberately relative, not in days — absolute estimates on unbuilt infrastructure are guesses wearing a suit.

| Phase | Relative size | Gate |
|---|---|---|
| 0 spike | small | Hard kill criteria. |
| 1 SDK | medium | Mostly mechanical once Phase 0 answers the protocol questions. |
| 2 first vertical | medium | **The decision gate.** |
| 3 verticals 2–3 | large, and this is the ongoing work | — |
| 4 deck surface | small | — |
| 5 Go agent harness | large | Not scheduled. |

## Risks

| Risk | Mitigation |
|---|---|
| Schema drift between the Rust vocabulary and the Go mirror | Codegen plus a CI gate that regenerates and diffs. Never hand-write kernel types. This is the failure that would quietly invalidate the whole approach, so it gets the strictest gate. |
| Two runner images doubles maintenance | Keep the split clean — Go for deterministic, Python for agentic, no overlap. Two images doing *different* jobs is fine; two images doing the *same* job is the actual failure mode. |
| Go's JSON ergonomics fight dynamic Records | The `Raw json.RawMessage` projection (`02-architecture.md` Layer D). Accept that Go is worse than Python at genuinely dynamic shapes, and put the dynamic work on the Python side where it belongs. |
| Proxy serialises requests, killing the concurrency benefit | Measure in Phase 2. Do not design around the benefit until measured. If it serialises, that is a Rust-side improvement to propose after the demo, not a reason to stop. |
| Scope creep onto the demo path | Phase 0 has kill criteria; every phase is post-demo by default. If a phase starts pulling demo attention, it is the phase that yields. |
| `core/` designed too early and wrong | It stays empty until Phase 3 by rule, not by judgement. |

## Explicit non-goals

No expression language. No Go DSL that authors edges or wiring. No executor changes. No new kernel `Value` variants. No second fixture corpus. No Go agent harness in v1. No promotion-ladder automation (`01-constraints.md`).
