# Status

Audience: Tucker, and whoever picks this up. Job: what was actually built, where it deviates from the plan and why, and what is left.

Written after implementation. Where this and `03-build-plan.md` disagree, this is what happened.

## Update: P0 chunks 1 and 2 now exist

`pantheon-rs/` holds the vocabulary crate and the registry with `ptn plan`/`ptn apply`.
**Acceptance test 1 and the plan-time half of acceptance test 2 are met and tested.**
That changes two things written below:

- The schema arrow is no longer unanchored. `pantheon-rs/testdata/wire/` is a
  hand-written corpus both implementations must round-trip, so Rust being the
  source of truth is now checkable rather than aspirational. It caught a real Go
  bug on first run (a constructed zero envelope emitted `taint: null` where the
  spec and Rust both say `[]`).
- `ptn plan` validates the 12 generated task definitions against hand-authored
  wiring, resources and triggers — 45 definitions across two directories.

Still true: **there is no executor, no shim and no proxy**, so the runner
protocol remains a proposal and invariant 4 remains asserted rather than
demonstrated. Chunks 3 and 4 are next.

## The one deviation that matters

**The Pantheon executor did not exist when the Go library was written.** There is no Rust crate, no shim, no resource proxy, no schema registry — only Aurora's unrelated `fjell`. That was confirmed, not assumed (`find . -name Cargo.toml`).

Two consequences, both structural:

1. **Phase 0 as planned could not run.** It said "spike one action end to end through the real shim, against the real proxy", and its exit condition was "the diff to the Pantheon repo is an image reference and nothing else". There is no Pantheon repo to diff.
2. **Q1–Q4 could not be settled by reading source.** `04-open-questions.md` said they were "cheap to settle by reading the executor source". With no source, they were settled by **proposing** an answer and implementing it — `PROTOCOL.md`.

So invariant 4 — "wiring in a new harness touches zero executor code" — is **not yet demonstrated**. It cannot be until an executor exists. Everything else was built against the proposed protocol, with `ptnfake` serving a real Unix socket speaking it, so the day a real executor appears the work is to reconcile two documents rather than to write a client.

That is the honest headline: **the library is complete and tested; the integration is unproven and cannot yet be proven.**

## What was built

| Phase | Planned | Actual |
|---|---|---|
| 0 spike | one action through the real shim | **Not possible.** Replaced by `PROTOCOL.md` — the contract written down as a proposal, then implemented. |
| 1 SDK | layers A–D | Done: `kernel`, `res`, `action`, `serve`, `table`, `schema`, `emit`, `ptnfake`, plus the import lint. |
| 2 finance vertical | 4–6 actions, decision gate | Done: 5 actions, named mutation table, planted-defect fixtures. |
| 3 telemetry + clinical | verticals 2–3, populate `core/` | Done: 4 + 3 actions. `core/` populated by extraction (`Money`, `Welford`, `Percentile`, `MedianAbsDev`), each naming its callers. |
| 4 deck surface | catalog from the registry | Done: `deck.Catalog`, `ptn-gen catalog`. |
| 5 Go agent harness | not scheduled | Not built, as planned. |

**12 actions. Zero third-party dependencies.** `go build`, `go vet`, `go test`, `go test -race` all clean.

## Deviations from the plan, and why

| Plan said | What happened | Why |
|---|---|---|
| Phase 0 spike against a real executor | Wrote `PROTOCOL.md` as a proposal and implemented against it | Nothing to spike against. Leaving the contract implicit would have been worse than proposing one. |
| Kernel types generated from schemars output | Hand-written, with `schema/` deriving JSON Schema *from* them | No Rust crate to generate from. The arrow runs backwards, documented as temporary in both package docs. When the crate lands the direction reverses and CI diffs it. |
| Reuse the P0 chunk 6 fixtures | Built `fixtures/` | Those fixtures do not exist either. Still **one** corpus, per the "no second corpus" rule. |
| `core/` populated in Phase 3 by extraction | Held to | Every item in `core/` names which two callers earned it. Anything with one caller was extracted too early. |
| Measure cold start and proxy concurrency in Phase 2 | Cold start measured; concurrency **not** | Concurrency depends on the real proxy (Q3). The client multiplexes and is correct either way; the *benefit* is unmeasured and may be zero. |

## What the demo run found that the tests did not

`cmd/deck-demo` prints the three verticals' output. Reading it surfaced three real defects the passing test suite had missed:

1. **A documented phase that never existed.** `Phase.Name` documented `landed`; `segmentPhases` never produced it. The post-touchdown tail of a flight — usually most of the recording — was reported as one enormous `coast`, and altimeter settling produced a one-sample `ascent` after landing. Fixed in the classifier, and the fixture that generated sub-ground altitude was fixed too.
2. **A fixture comment that misdescribed its own data.** It claimed one planted weekend posting; there were three. The test only checked the one, so it passed.
3. **Two anomaly rules with no test at all.** `round_number` and `missing_account` never fire on the shared corpus. Now exercised directly, with a note in the fixture explaining why they are not planted there.

This is the argument for `deck-demo` existing. Assertions check what you thought to assert.

## Open questions: current state

| | |
|---|---|
| **Answered by proposal** (implemented, not agreed) | Q1 handshake, Q2 capabilities, Q4 action dispatch, Q5 table read, Q7 file handles — all in `PROTOCOL.md` |
| **Answered by building it** | Q6 — `ptn plan` consumes generated files; nothing in the plan/apply path assumes a human author. Q9 — `uses:` IS the grant declaration, and an undeclared verb is now a plan-time error. |
| **Still genuinely open** | Q3 proxy concurrency (measurable only against a real proxy), Q8 registry read at build time, Q10 second runner image build path |
| **Settled by construction** | Q11 catalog is registry-generated. Q12 no action-to-action calls — the SDK offers no way to make one, so invariant 3 cannot be broken from inside a body. |

## What is left

In rough order of value:

1. **Reconcile `PROTOCOL.md` with whoever builds the executor.** Every proposed answer is cheap to change now and expensive later. This is the only item that blocks the others.
2. **Run the real binary against a real executor** — the original Phase 0. Until then invariant 4 is asserted, not demonstrated.
3. **Reverse the schema arrow** once the Rust vocabulary crate exists: generate `kernel/` from schemars output, add the regenerate-and-diff gate, delete `schema/`'s provisional path.
4. **Measure Q3** and decide whether the proxy should multiplex.
5. **Integration test against a branch stack** (`./aurora branch up`), per prime directive 1. Everything today is unit-level against `ptnfake`.
6. **The Phase 2 decision gate has not actually been held.** The plan says judge the approach after one vertical. Three exist and the code reads well, but nobody has compared the effort against the Python equivalent. That comparison is still owed before committing further.

## Honest assessment

What is genuinely proven: the deck's business logic is correct against fixtures with planted defects; the permission beat works as a millisecond unit test; the wire format, grant enforcement, streaming, and drift gate all hold under `-race`; and the properties that matter are enforced by tests that have been shown to redden, not by convention.

What is not proven: that any of it talks to a Pantheon executor, because there is not one to talk to. Every integration claim in this directory is a claim about a protocol I proposed rather than one anyone has agreed to.
