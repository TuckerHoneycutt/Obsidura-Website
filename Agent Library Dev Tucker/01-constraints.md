# Constraints

Audience: whoever designs or implements the Go action library. Job: name every rule the library must obey, where it comes from, and what it forbids — so no design cycle is spent rediscovering them.

Sources: `website/specs/pantheon-spec-v0.md` (normative, wins on conflict), `website/specs/Pantheon Discussion Context.md` (reasoning), `Aurora/aurora-agent/core/*` (development doctrine), `Aurora/aurora/AGENTS.md` (how to test).

## From the Pantheon spec — the five invariants, read as constraints on Go

| Invariant | What it forbids in this library |
|---|---|
| 1. Rust in the executor is constant in the number of business types | The Go library may **never** require an executor change to add an action. Adding the 200th action must touch zero Rust. If a design needs a new `Value` variant or a new executor branch, the design is wrong. |
| 2. No expression language in YAML, ever | The Go library may not become a backdoor DSL that authors control flow into definitions. Go emits *literal* definitions — refs, parameters, flat field-path mappings. Computation lives inside the action body. |
| 3. Edges are derived from references, never authored | Emitted YAML declares `on:`, `then:`, `uses:` as refs. Go code never emits an edge entity. |
| 4. No framework is hardcoded at the executor level | This is the one the library **proves**. A second runner image existing at all is the acceptance test for invariant 4. If wiring Go in requires touching executor code, invariant 4 was already broken and this work found it. |
| 5. Task graph shapes stay composable | A Go action must be swappable with a Python action of the same input/output schema, with no engine change. Same seam, same envelope, same validation. |

## Hard interface facts the library inherits

These are given. Do not redesign them.

| Thing | Spec | Consequence for Go |
|---|---|---|
| Kernel `Value` — `Text`, `File`, `Table`, `Record`, `Error` | §5, closed set of five | Go mirrors these; it does not extend them. Anything domain-specific is a `Record` or a `File` with a media type. |
| Rust is the source of truth for the vocabulary, JSON Schema generated via schemars | §4 | Go types for the kernel are **generated** from that emitted schema, never hand-written. Hand-writing them creates a second source of truth and invariant 1 dies quietly. |
| Envelope: `run_id, task_id, attempt, schema, producer, caused_by, taint, budget_spent, ts` | §6 | Go populates all of it. Taint is recorded, not enforced, in v0 — record it anyway. |
| Every task output validated against its declared output schema before anything downstream sees it | §6 | Executor validation is authoritative. Go validating too is defence in depth and a better error message, not a substitute. |
| JSON everywhere; large data always by handle, never inline | §6 | The 10k-row telemetry case is a `Table` handle streamed from blob store. An action that materialises a whole table in memory to pass it on is a bug. |
| Bodies run in containers, JSON-RPC over stdio, `{envelope, payload, capabilities}` in | §8 | The Go binary is a shim implementation, not a new protocol. |
| Resource access **only** through the per-run Unix domain socket; the socket is the capability; credentials never enter the container | §8 | Go actions get no connection strings, no API keys, no `os.Getenv("DATABASE_URL")`. An action that opens its own network connection has bypassed the entire security model. This is the single easiest thing to get wrong in Go, where `database/sql` is right there. |
| Schemas registered as `name@version`, JSON Schema in Postgres, nullable `refines` column | §6 | Go structs for business Records are **generated from the registry**, keyed `name@version`. |
| Definitions authored as YAML, `ptn plan` diffs, `ptn apply` registers | §7 | Go-emitted YAML must be indistinguishable from hand-authored YAML and must survive `ptn plan` cleanly. |

## What the spec explicitly leaves free

- **The language a task body is written in.** §8 names one generic Python runner image for v0 and calls per-action images a bonus chunk (B4). Nothing says a second image kind is forbidden — invariant 4 says the opposite.
- **How definitions get authored.** §1 permits "frontends that emit IR" by name. A Go registry that emits YAML is exactly such a frontend, and this is the legal basis for the whole approach. It is not a loophole; it is the sanctioned path.
- **Whether actions are deterministic or agentic.** `runner: script` and `runner: agent` are both ordinary tasks. The Go library starts as `runner: script` only.

## What is deferred and must not be built here

From §11: the promotion ladder, taint enforcement, `model` runner kind, Arrow-backed Tables, vertical/tenant refinement *checking*, dynamic in-action routing.

The distinction that matters: **building actions that happen to be the hardened tier is fine; building the machinery that automatically promotes an agent task into a Go action is deferred.** The library is a destination the ladder will eventually point at. Do not build the ladder.

## From Aurora doctrine — how this gets developed

`Aurora/aurora-agent/` supplies the process, and it is not optional. The six invariants run at every tier: `prime-directives`, `verification-law`, `output-based-assertions`, `mutation-proof`, `practical-testing`, `lease-discipline`.

| Rule | Source | Bite here |
|---|---|---|
| All development and testing in an ephemeral worktree and environment, never prod | `core/prime-directives.md` #1 | Integration tests run against `./aurora branch up <name>`, not the live stack. ~53s to stand up; there is no excuse. |
| A fix is not pinned until a named mutation reddens it | `aurora/AGENTS.md` #6, `skills/mutation-proof` | Every action ships a named mutation table. A mutation that stays green fails review and is never suppressible. |
| Output-based assertions | invariant | Assert on the action's emitted envelope and payload, not on internal state or mocks' call counts. |
| Verify after committing, not before | `aurora/AGENTS.md` #3 | Gates walk `git ls-files`; a green run on a dirty tree measures a tree about to stop existing. |
| Reality gate: measure load-bearing claims, do not assert them | `skills/reality-gate`, tripwire | Every performance claim in `02-architecture.md` and `03-build-plan.md` is marked UNVERIFIED until measured. Cold-start numbers especially. |
| Run journal, append-only JSONL, closed event vocabulary | `core/journal.md` | If the Go SDK emits run logs, it emits the *Pantheon* run log (`run_events` table, §8) — not a second journal format. The Aurora journal governs the development runs, not the product's runtime. Do not conflate them. |

## The two-journal trap

Worth stating separately because it will otherwise cost a day. There are two logging systems in scope and they are unrelated:

- **`run_events` in Postgres** (Pantheon §8) — the product's runtime log. Executor state is a fold of it. Go actions stream log events into this via the shim.
- **`.aurora/runs/<run-id>/journal.jsonl`** (aurora-agent `core/journal.md`) — the *development* run log, recording how you built the thing, gates opened, mutations killed.

They share the word "run". They share nothing else.
