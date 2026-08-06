---
name: test-driven-development
description: Use before writing any production code — implementing a feature, fixing a bug, changing behavior, or refactoring. Use when you are about to write a test after the code, when you need to decide where a test belongs, when you catch yourself asserting on a status code or a mock, or when someone proposes skipping the failing-test step "just this once."
origin: aurora
derived-from: obra/superpowers@6.2.0, mattpocock/skills@2ab9580
---

# Test-driven development

Audience: any agent about to write production code. Job: write the test first, watch it fail for the right reason, and make it a test that could have failed.

## The iron law

```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

Wrote the code before the test? Delete it and start over. Not "keep it as reference," not "adapt it while writing tests," not "look at it once." Delete means delete, then implement fresh from the test.

If you did not watch the test fail, you do not know it tests anything. Violating the letter of this rule is violating its spirit.

Applies to: new features, bug fixes, refactors, behavior changes. Exceptions — throwaway prototypes, generated code, config files — are for the human to grant, not for you to assume.

## The loop

| Phase | Do | Verify before moving on |
|---|---|---|
| **RED** | Write one minimal test for one behavior at an agreed seam, named for the behavior. | Run it. It must **fail**, not error. The message must be the one you expected, and the cause must be the missing feature — not a typo or an import. If it passes, you are testing behavior that already exists; fix the test. |
| **GREEN** | Write the simplest code that passes it. No speculative options, no anticipating the next test. | Run it. It passes, the rest of the suite still passes, and the output is pristine — no stray warnings or noise. If it fails, fix the code, never the test. |
| **REFACTOR** | Line-scope tidy only (see below). | Still green. No behavior added. |
| **REPEAT** | Next failing test, next slice. | |

## Seams: where tests go

A **seam** is the public boundary you observe behavior at without reaching inside. Tests live at seams, never against internals.

**Test only at pre-agreed seams.** Before writing the first test, write down the seams under test and confirm them (gate `G-SEAMS`). No test is written at an unconfirmed seam. You cannot test everything; agreeing seams up front is how the effort lands on critical paths and complex logic instead of on every edge case someone imagined.

Ask, out loud, before starting: **"What is the public interface, and which seams should we test?"**

## Anti-patterns

| Anti-pattern | What it looks like | Why it is fatal |
|---|---|---|
| **Implementation-coupled** | Mocks internal collaborators, tests private methods, or verifies through a side channel (querying the DB instead of using the interface). | It breaks on refactor when behavior did not change, and stays green when behavior does. |
| **Tautological** | The assertion recomputes the expected value the way the code does: `expect(add(a,b)).toBe(a+b)`, a hand-derived snapshot, a constant asserted equal to itself. | It passes by construction and can never disagree with the code. Expected values must come from an independent source: a known-good literal, a worked example, the spec. |
| **Horizontal slicing** | All the tests first, then all the implementation. | Bulk tests verify *imagined* behavior — you pin the shape of things, not what a user does, and you commit to test structure before you understand the implementation. |

Work in **vertical slices** instead: one seam, one test, one minimal implementation, repeat. Each test is a tracer bullet that responds to what the last cycle taught you.

## Output-based assertions

A test must empirically show the system achieved the goal it exists for. Capture the real output and assert on it. **Never a status code alone.**

| Instead of | Assert on |
|---|---|
| HTTP 200 | The response body — the rendered HTML actually containing the expected content |
| "the write succeeded" | The row that is now in the database, read back |
| exit code 0 | The file on disk and its contents |
| "the job ran" | The captured stdout/stderr, matched against what the job was supposed to say |

Concrete: for a routing service and the page it routes to, the test proves **both** that you can route from a→b **and** that the page you arrive at contains the HTML content you expect. If output exists, capture it. A test that stops at the status code is a test that a broken renderer passes.

Do not mock what you have not read. If you are unsure of a dependency's side effects, exercise the real thing.

## The mutation hook

A test is not pinned until a named mutation reddens it.

For every fix and every load-bearing feature test, name the mutation next to the test — the specific break in production code that must turn this test red — then apply it, run it, and record the transcript. A named mutation that stays green is a failed test, whatever its coverage says.

Procedure, transcript format, and the guard-mutation safety rule live in ../mutation-proof/SKILL.md. Do not restate it here; follow it there.

## Refactor scope

| Scope | When | Example |
|---|---|---|
| **Line-scope tidy** — inside the red-green-refactor loop | Immediately after green | Rename a variable, extract a helper, remove duplication you just created |
| **Seam moves** — the review stage, not the loop | After the task's tests are all green, as a reviewed change | Relocating a boundary, changing a public interface, restructuring modules |

Moving a seam mid-loop invalidates the tests you agreed to. If a seam looks wrong, that is a finding for review, not an edit to slip into a green cycle.

## Common rationalizations

| Excuse | Reality |
|---|---|
| "I'll test after" | Tests written after pass immediately, which proves nothing. You never watched it fail, so you never proved it can catch the bug. |
| "Tests after achieve the same goals — spirit, not ritual" | Tests-after answer "what does this do?"; tests-first answer "what should this do?" After-tests are biased by the code in front of you: you cover the cases you remembered, not the ones you would have discovered. |
| "Already manually tested it" | Ad hoc, unrecorded, unrepeatable. "Worked when I tried it" is not coverage, and you cannot re-run it after the next change. |
| "Deleting X hours of work is wasteful" | Sunk cost. That time is spent either way. The real choice is rewrite with TDD (high confidence) or bolt tests onto code you cannot trust (low confidence). |
| "Keep it as reference and write tests first" | You will adapt it. That is testing after. Delete means delete. |
| "Hard to test" | Listen to the test. Hard to test is hard to use — the design is telling you something. |
| "TDD will slow me down" | The shortcut ships the debugging into production. Slower, not faster. |

## Red flags — stop and start over

Code before test · test written after implementation · the test passed the first time you ran it · you cannot explain why it failed · "tests will be added later" · "just this once" · "I already manually tested it" · "it's about spirit not ritual" · "keep as reference" · "already spent hours, deleting is wasteful" · "TDD is dogmatic, I'm being pragmatic" · "this case is different because…"

All of these mean: delete the code, start over with a failing test.

## When stuck

| Problem | Move |
|---|---|
| Don't know how to test it | Write the API you wish existed, then the assertion, then work backwards. |
| Test is too complicated | The design is too complicated. Simplify the interface. |
| Must mock everything | Too coupled. Inject dependencies. |
| Huge setup | Extract helpers; if it stays huge, the design is the problem. |

## TDD is necessary, not sufficient

A green suite proves the units do what you specified. It does not prove the specification was about the real system — your tests share your assumptions. Before claiming DONE, exercise the real write path and paste the transcript: ../practical-testing/SKILL.md.
