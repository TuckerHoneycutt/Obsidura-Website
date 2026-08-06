---
name: vacuity-review
description: Use when reviewing tests — in a code review, a task review, or your own work before reporting DONE — to check whether each test could actually fail. Use when a suite is green but you are not sure it proves anything, when a mutation stayed green, when a test asserts on a docstring or a mock or its own reimplementation of the logic, or when someone asks you to "review test quality."
origin: aurora
---

# Vacuity review

Audience: anyone reviewing tests, including your own. Job: for every test in the diff, name which of the eleven vacuity shapes it is, or state "none of the eleven."

A vacuous test passes while testing nothing. Eleven shapes, each with a different mechanism, from two chunks of real work — which is exactly why "write better tests" is not actionable. Recognising the **shapes** is.

## The eleven shapes

| Shape | What happens | Catch it by |
|---|---|---|
| **Vacuous filter** | Asserting over a set that is empty. A gate querying a project with no containers passes on nothing. | Assert the set is non-empty **first**, then assert over it. |
| **Docstring satisfaction** | A source-text search is matched by the docstring that describes it, not by any real code. | Walk the AST for real call nodes; strip docstrings and comments before scanning. |
| **Decoy** | The test reimplements the logic it claims to pin, then asserts on its own copy. | The test must **call** the thing under test. If it reimplements, it proves only that you can write the function twice. |
| **Universal skip** | A skip guard that is true at every invocation makes a critical gate inert. A skip is not a failure, so nothing ever goes red. | Never `skip` on an environment condition — **fail** with the reason, or gate on an explicit opt-in variable. |
| **Wrong-identity conformance** | A resolved value is compared against *production's* identity, so the test goes red exactly when the branch is correct. | Compare against the identity of the thing under test, never a hardcoded constant from elsewhere. |
| **Self-blinding artefact** | Generator and checker read the same source. Delete an entry and both go blind together; the suite stays green. | Derive the checker's expectations from an independent source — the resolved config, not the file that generated it. |
| **Artifact vs generator** | A test reading the committed file cannot catch a broken generator, and a test of the generator cannot catch a stale committed file. | Cover both directions, with a matched mutation for each. |
| **Code-path vacuity** | The assertions are real but they measure the other branch of an `if`. Two survived because no test ever executed the compose path. | Before believing a mutation cannot redden, verify the path under test actually ran. |
| **Non-discriminating evidence** | A recorded transcript that the broken implementation would also have produced (single-replica container names looked identical either way). | Evidence counts only if the mutant could not have produced it. |
| **Sequential-guard `raises`** | Deleting a guard does not change the exception *type* — the next guard raises the same type on the same input, so the test stays green. | Assert on the message or the specific condition. Never `pytest.raises(X)` alone. |
| **Inconsequent workarounds justified by comment** | A docstring carrying a paragraph-long justification for a function that behaves oddly or over-specifically. The length of the excuse is the tell: the function was not designed to complete its task while cutting footgun surface area. | Make the function prove **both** that its existence is *necessary* **and** that it is the simplest, most logical, most effective way to accomplish the subunit of the task it serves. Neither alone. |

## Reviewer procedure

For every test added or changed in the diff:

1. Name the shape it matches, or state **"none of the eleven."** Silence is not a verdict.
2. Name the production change that would make this test fail. If you cannot name one, the test is vacuous regardless of which shape it is.
3. Check the mutation record: is there a named mutation next to this test, and a transcript showing it red then green? See ../mutation-proof/SKILL.md.
4. Check the assertion target: real output, or a status code / a mock / the test's own arithmetic? (../test-driven-development/SKILL.md, output-based assertions.)
5. Report per-test with a `file:line`. "Tests look fine" is not a review.

A reviewer holding a closed taxonomy beats a reviewer told to "review test quality." The taxonomy is closed on purpose: eleven named shapes force a decision on each test. An open instruction lets every test pass by default.

## The meta-rule

**A fix is not pinned until a named mutation reddens it.**

Run the mutation, revert it, record the transcript. Nine tenths of the value of the mutation table was finding tests that could not fail — not finding bugs in the product. A green mutation is a finding at every tier and is never suppressible. Procedure: ../mutation-proof/SKILL.md.

## "Correct today" and "cannot rot" are different tests

An exemption whose properties all hold exactly as written, with nothing preventing it from widening, will widen. A rule that is correct today and unenforced tomorrow is a rule that has already failed; it just has not been noticed yet.

Ask of every rule, guard, exemption, and invariant: **what happens when someone deletes this?**

- If the answer is "a test goes red with a message that says what to do" — it cannot rot.
- If the answer is "nothing" or "we'd notice in review" — it is prose, not a guard. Prose is not a guard.
- If the answer is "the suite still passes" — you have found the vacuity before it found you.

Deliberately red tests are legitimate when they assert a real blocker and carry, in the failure message, the instruction for what to do when they fire. Convert them when they fire; never delete them. A blocker assertion converts naturally into a regression assertion.

## Antidote

Vacuity is a property of tests written from the implementer's model of the system. The direct antidote is contact with the real system: exercise the actual write path and read the actual output — ../practical-testing/SKILL.md. Every one of the eleven shapes survives a suite run; none of them survives a real invocation with its transcript pasted.
