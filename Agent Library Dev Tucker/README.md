# Agent Library Dev — Go action library

Audience: Tucker, and any agent picking this work up. Job: say what this directory is, what the thing being built is, and the order to read it in.

**Status:** planned and built, on two tracks.

- `pantheon-go/` — 12 working actions across three verticals, with the SDK under them. Parallel track, not the demo path.
- `pantheon-rs/` — **P0 chunks 1 and 2** from the spec: the vocabulary crate, and the registry with `ptn plan`/`ptn apply`. This *is* the demo path, taken in spec order.

Read `05-status.md` for what was actually built, where it deviates from the plan, and the one thing that cannot yet be proven: **the Pantheon executor does not exist**, so the runner protocol is a proposal (`pantheon-go/PROTOCOL.md`) rather than an agreement, and invariant 4 is asserted rather than demonstrated.

## What is being built

A **library of callable business processes — "the deck" — authored as typed Go actions**, plus the thin Go SDK those actions need in order to be ordinary Pantheon tasks.

Not an agent harness (Pydantic AI keeps that job for now). Not a replacement executor (Rust keeps that job permanently). A Go binary that registers many named actions, speaks the existing JSON-RPC-over-stdio runner protocol, reaches resources only through the existing run-scoped proxy, and emits its own YAML definitions for `ptn plan/apply`.

## The thesis, in one paragraph

Your own design notes already contain the argument: *"types harden from data to Rust the same way actions harden from agent to script"* (`Pantheon Discussion Context.md:846`). An agent figures out a task once, it gets repeated, and eventually it deserves to stop being stochastic. **The Go library is the hardened end of that ladder.** Python-plus-agent is the exploratory tier — flexible, expensive, variable. Go is the solidified tier — typed against the vertical Record schemas, compile-time checked against schema drift, milliseconds to start, cheap to run a thousand times a day. Building the hardened tier's substrate is not the same as building the promotion *automation*, which §11 of the spec defers; see `01-constraints.md`.

## Read in this order

| File | Job |
|---|---|
| **`PANTHEON.md`** | **Start here.** Self-contained audit of both codebases against the spec: build plan, acceptance tests, invariants, architecture, the deck, what is verified, and every bug the build found. Portable CommonMark — renders the same anywhere. |
| `01-constraints.md` | The box this library must live inside — what the Pantheon spec and Aurora doctrine pin down, and what they leave free. Read before designing anything. |
| `02-architecture.md` | The five layers, the action shape, package layout, and how definitions stay data. |
| `03-build-plan.md` | Phases, deliverables, kill criteria, sequencing against the demo. |
| `04-open-questions.md` | What cannot be answered from the spec and must come from the Rust side. Several are blocking on Phase 0. |
| `05-status.md` | **What was actually built**, the deviations and their reasons, and what is left. Written after implementation; wins over `03-build-plan.md` on any disagreement. |
| `pantheon-go/` | The Go deck library. Working reference: `README.md`, then `PROTOCOL.md`. |
| `pantheon-rs/` | **P0 chunks 1–2**: the vocabulary crate and `ptn plan`/`apply`. Acceptance tests 1 and 2 (plan-time) met. |

## The one-line summary of the plan

Spike a single Go action end to end through the real shim and real proxy first (Phase 0, ~2 days, has a kill criterion); only then build the SDK; only then build the deck, one vertical at a time, extracting what generalizes.

## Class and tier

`G-CLASS`: **feature, F2** — human owns the design, agent owns the implementation. Justification: it is new load-bearing infrastructure with a wide solution space, but the spec already constrains the seams hard enough that F3's per-decision ratification would be ceremony. Pipeline: `Aurora/aurora-agent/pipelines/f2.yaml`. Escalate to F3 if the proxy concurrency question (`04-open-questions.md` Q3) comes back badly enough to require an executor change.
