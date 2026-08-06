---
name: mutation-proof
description: Use when a test must be proven able to fail — after fixing a bug, after writing a load-bearing feature test, when a task brief names mutations, or when a reviewer asks "what would make this test red?" Use when building a mutation table, when deciding whether a mutation may touch a live tool, and whenever you need to record a mutation.result journal line.
origin: aurora
---

# Mutation proof

Audience: implementers pinning a fix, and reviewers checking that it is pinned. Job: prove each load-bearing test can actually fail, by breaking the code on purpose and recording the transcript.

**A fix is not pinned until a named mutation reddens it.** Coverage says a line ran. A mutation says the test would have caught it.

## Procedure

| Step | Do | Record |
|---|---|---|
| 1 | **Name** the mutation next to the test, before you run anything. In the test's docstring: `Mutation: <break> -> <expected redden>`. | The docstring line, committed with the test. |
| 2 | **Apply** it — make that exact edit to the production code. One mutation at a time. | The diff of the mutation. |
| 3 | **Run** the covering test. It must go **red**, and the failure must be the one you predicted. | The full transcript: command and output. |
| 4 | **Revert** the mutation cleanly. Verify the working tree is back to where it started. | `git diff` empty (or the revert diff). |
| 5 | **Re-run.** It must go **green** again. | The transcript. |

Both transcripts, or it did not happen. A red run with no green run afterwards leaves a mutation in the tree; a green run with no red run proves nothing at all.

### Naming a mutation

The name states the break and the predicted consequence, specifically enough to be wrong:

```python
"""Mutation: delete the origin key from one vendored SKILL.md -> test_vendored_provenance fails.
Mutation: change the guard from `in SAFE` to `!= "production"` -> test_guard_rejects_empty_project fails.
"""
```

Not "break the guard" — which break, and which test, with which message.

## What a green mutation means

A named mutation that stays green is a **failed test**, not an inconvenience. It means the code can be broken in a way you specifically anticipated and nothing tells you.

- It is a finding at every tier — F0 through F3, chore through incident. Cost scales on deliberation, never on safety.
- It is **never suppressible**. Not by a comment, not by "the mutation was unrealistic," not by "coverage is high elsewhere."
- The response is to fix the test until the mutation reddens it, then re-run steps 2–5. Changing the mutation to one that already reddens is grading your own work.
- Before concluding "this mutation cannot redden," verify the mutated path actually executes under the test. Most of these are code-path vacuity, not impossible mutations (../vacuity-review/SKILL.md).

Nine tenths of the value of a mutation table is finding tests that could not fail — not finding bugs in the product.

## Evidence rules

**Evidence counts only if the mutant could not have produced it.** Before accepting a transcript as proof:

- Would the mutated build have emitted this same output? If yes, the evidence is non-discriminating and proves nothing.
- Does the red failure message name the behavior you predicted, or is it an import error, a typo, or a different guard raising the same exception type?
- Sequential guards: deleting one often leaves the next one raising the identical exception type on the identical input. Assert on the message or the specific condition, never on the exception type alone.

## Guard mutations: stubs only, never live tools

**A mutation that disables a guard must run against a stub or a tripwire. Never against the live tool.**

This is the rule written after an agent destroyed live production by running `docker compose -p <prod> down -v` while executing a mutation table that disabled its own guards one at a time. A mutation table that turns off safety, by construction, must never face a real daemon.

- Test the guard against a stub that records what it was asked to do. The incident command passed straight through on the first attempt — against the real daemon, the test itself would have destroyed production a second time.
- A stub also makes failure legible: a later broken edit made every case fail, which against the stub read as fifteen loud failures in ten seconds. Against a live daemon the same broken state would have looked maximally safe.
- Tripwire the function that touches the destination, not only the one that moves bytes — a `mkdir` + `copystat` moved a production directory's mtime past a guard that covered only the byte-movers.
- Anything a guard mutation would let through is, by definition, host-destructive or prod-touching: ../../core/prime-directives.md governs, and G-CHECKPOINT is the only way past it.

See also ../destructive-op-awareness/SKILL.md for guard construction itself.

## Fan-out

Each mutation is independent: one edit, one test run, one revert. That makes a mutation table embarrassingly parallel.

With an environment per mutation — an ephemeral worktree and lease each — a 200-row table is a fan-out, not a serial grind. Dispatch N agents, one mutation each, each returning its red and green transcripts. See ../dispatching-parallel-agents/SKILL.md.

Rules that survive the fan-out:
- One mutation per environment. Two mutations in one tree cannot tell you which test caught which break.
- Never mutate a tree another agent is running against. A suite run against a worktree mid-mutation manufactures phantom failures someone will be sent to chase.
- Each agent reverts its own mutation and proves green before reporting.

## Journal

Record every mutation run as a journal line with `event: "mutation.result"`, valid against ../../core/journal.schema.json. Put the mutation name, the covering test, and the red/green outcome in `detail`.

```json
{"ts":"2026-08-02T14:02:11Z","run":"r-4812","event":"mutation.result","actor":"implementer-t6",
 "detail":{"mutation":"delete origin key from one vendored SKILL.md","test":"test_vendored_provenance","red":true,"green_after_revert":true}}
```

An unrecorded mutation is an unproven one. The ledger is what a later agent reconstructs the run from.

## Red flags

- A mutation named after the fact, chosen because it reddens.
- A red transcript with no matching green-after-revert.
- A mutation applied to the test instead of to the production code.
- "The mutation didn't redden, but the test is obviously fine."
- A guard mutation whose target is anything other than a stub or tripwire.
- Several mutations applied at once "to save time."
- A mutation table in a brief that says "test it well" instead of naming the breaks. Briefs name their mutations; vague briefs produce tests that pass.
