---
name: practical-testing
description: Use after tests pass and before claiming DONE — when you have built a CLI, container, service, script, or library and need to prove it actually works. Use when writing or reviewing a `## Practical verification` section, when a report claims "tests pass" without a transcript of the real thing running, when a reviewer must independently re-run a task's primary path, or when you catch yourself about to say "it should work."
origin: aurora
---

# Practical testing

Audience: any agent that just made something work in tests. Job: prove it works by using it, and capture the transcript that proves you did.

**The best test is using the thing you built.** After the suite is green, run the real write path: invoke the CLI, start the container, execute the process, hit the endpoint, open the file it wrote. Then paste the commands and their output.

## Why tests are not enough

Unit tests are written by the implementer, from the implementer's model of the system. They mirror your assumptions — including the wrong ones. Execution does not: the container either starts or it does not, the endpoint either returns your content or it returns a stack trace, the CLI either writes the file or exits 2.

Self-fulfilling tests are the primary observed failure mode of capable coding agents. Eleven distinct shapes of test-that-cannot-fail are catalogued in ../vacuity-review/SKILL.md; every one of them passes a suite run and every one of them dies on contact with a real invocation. Config validation is not startability — `compose config` has validated mounts that could never start.

## The discipline

This runs **after** ../test-driven-development/SKILL.md, never instead of it. TDD proves the units do what you specified; practical testing proves the specification was about the real system.

1. Name the primary practical path: the single sequence a user or caller would actually perform.
2. Stand it up in the ephemeral environment or lease you already hold.
3. Run it. Real inputs, real write path — not `--dry-run`, not a mock harness.
4. Read the output. Not the exit code — the output. The rendered page, the row in the database, the bytes on disk, the log line.
5. Capture the whole transcript: every command, its output, unedited. Truncate volume, never truncate the parts that carry the proof.
6. Then exercise the edges: bad input, missing file, wrong permissions, the flag nobody passes, two invocations in a row.

**Ephemeral environments have no consequences — tear them apart.** A lease you can destroy and recreate is the one place where trying to break the thing costs nothing. An agent that treats its own sandbox gently is wasting the only safe place it has.

## What counts

| Counts as practical verification | Does not count |
|---|---|
| Invoking the built artifact and reading its real output | Re-running the unit suite (it already ran) |
| Starting the container and probing the service it serves | `docker compose config` validating the file |
| Running the CLI end to end on real input, then inspecting what it wrote | `--help` or `--version` smoke alone |
| Hitting the endpoint and asserting on the body that came back | Asserting on the status code alone |
| Reproducing the user's actual sequence, including the failure cases | Reading the code and reasoning it must be correct |
| A transcript a broken build could not have produced | "It should work"; "the logic is straightforward" |

Evidence counts only if the broken version could not have produced it. A transcript that a broken implementation would also have emitted proves nothing (../vacuity-review/SKILL.md, non-discriminating evidence).

## Enforcement in this system

Rows 1, 2 and 4 are in force now — the templates they name and the pipeline manifests carry the requirement today, test-enforced where the row says so. Row 3 is mandated but not yet mechanically enforced: it holds by orchestrator convention, and is listed here because it is required, not because it is wired.

| Where | Requirement | Status |
|---|---|---|
| Implementer reports | Must contain a `## Practical verification` section with the real commands and their captured output. A report without it is not DONE — see ../subagent-driven-development/implementer-prompt.md. | In force |
| Task reviewers | Independently re-run the primary practical path before issuing any verdict. Reading the diff and the implementer's transcript is not review — see ../subagent-driven-development/task-reviewer-prompt.md. | In force |
| Orchestrator dispatch | Every task brief names the practical path the implementer must exercise. "Test it well" produces tests that pass. | Orchestrator convention — not yet mechanically enforced |
| Pipelines | `practical-testing` is an invariant in every pipeline manifest, at every tier, in the same tier of non-negotiability as `mutation-proof`. Cost scales on deliberation, never on safety. | In force — all 8 manifests, test-enforced |

A missing practical-verification section is not a style nit. It means the only evidence the thing works is the implementer's own belief.

## Boundary

Exercise the real path **inside the ephemeral environment or the lease you hold, and nowhere else.**

- Destructive experimentation is licensed only within that boundary.
- Anything host-destructive, shared-namespace, or prod-touching is governed by ../../core/prime-directives.md — stop and open G-CHECKPOINT.
- If the only way to exercise the real path is against something live, that is a finding to report, not an obstacle to route around.
- Verify after committing, not before: a check that walks tracked files is blind to whatever you left untracked.

## Reporting

Under `## Practical verification`, for each path exercised:

```
$ <exact command>
<output, verbatim>
```

Then one line stating what the output proves, and one line stating what remains unproven. State the unproven as loudly as the proven — "all tests pass" alongside an unexercised path is a true sentence that misleads. Say **unproven**, not merely unattempted.

## Red flags

- "Tests pass, so it works."
- A report where every command is a test-runner invocation.
- A practical section with commands but no output pasted.
- Output pasted but only the exit status read.
- The happy path exercised, no edge case attempted, in a sandbox that could have been torn apart for free.
- A reviewer approving on the strength of the implementer's transcript alone.
