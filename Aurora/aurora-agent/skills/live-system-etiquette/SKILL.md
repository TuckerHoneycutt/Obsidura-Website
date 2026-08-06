---
name: live-system-etiquette
description: Use whenever work touches a system someone else depends on — incident response, migrations, anything on a host with running services, shared state, or another person's data. Use when a permission check blocks you, when you have written to something you did not intend to, when you must disclose a write, when an operation needs availability polled while it runs, and when a session is ending with a stack still up.
origin: aurora
---

# Live-system etiquette

Audience: any agent operating where a mistake reaches someone else. Job: leave the system provably as you found it, and disclose exactly what you changed.

**Mandatory for the incident class.** Advisory elsewhere — ../../core/prime-directives.md already forbids prod writes without consent given this session, so these rules cover the ground where you are legitimately near something live.

## 1. Fingerprint before and after every phase

Take a baseline, take it again after, and diff.

| Fingerprint | How |
|---|---|
| Container count and names | `docker ps -a --format '{{.Names}}'`, sorted |
| File hashes | `sha256sum` over the paths in scope |
| Endpoint codes | The status **and** the body of each probed endpoint |
| Volume and network inventory | `docker volume ls`, `docker network ls` |

**Anything unintended in the diff is a stop-and-report.** Not "note it and continue." The diff is the only evidence that the phase did what it said, and an unexplained delta is the shape every incident starts as.

## 2. Poll during the operation, not just after

Availability checked only afterwards cannot tell you whether the service was down for four minutes in the middle.

Poll on an interval **while** the operation runs, and poll an endpoint whose success is unambiguous:

- `/` returning `401` by design means an assertion that tolerates `401` tolerates an outage.
- Pick an endpoint with exactly one healthy response, and assert on the body, not the code alone.
- Record the poll series. A gap in it is a finding, whether or not anyone noticed at the time.

## 3. Disclose every write in full

Every write. Including the accidental ones. Including the ones nobody would have found.

1. State **what** was written, **where**, and the **measured scope** — bytes, rows, paths, timestamps. Measured, not estimated.
2. State it whether or not it was reverted.
3. **Never fake-restore.** A timestamp you only know to the minute cannot be restored; writing an approximation is a second write concealing the first. Report the real state instead.
4. An accidental write disclosed immediately is an incident with a known scope. The same write discovered later is an investigation.

## 4. Copy, never move

Keep both generations.

- `cp`, verify, then decide about the original — separately, later, with a human.
- The only reason three developers' agent state survived one incident is that two migrations copied instead of moving.
- Disk is cheaper than the thing you are about to move.

## 5. Do not route around a refusal

**A blocked permission is a reported defect, not an obstacle.**

When a permission check stops you, the correct output is a report naming what was blocked and why it was needed. Everything else is circumvention:

- Re-running with `sudo`, or as another user.
- Finding a second path to the same effect.
- **Writing the deletion into the product and then invoking the product.** That is circumvention with extra steps, and it launders a refusal into a feature.

The guard was right or the guard was wrong. Either way, the human decides — see ../destructive-op-awareness/SKILL.md and `AURORA_GUARD_OVERRIDE` in ../../core/guard/SPEC.md, the one override that exists and is visible in shell history.

## 6. Stop cleanly when the human leaves

**An agent killed mid-run with a live stack up is worse than one killed before it starts.**

On any signal that the session is ending — the human says goodnight, the context is running out, the task is being handed over:

1. Stash or commit uncommitted work; nothing in flight, nothing untracked and unrecorded.
2. Tear down what you stood up and **verify zero residue** — the lease releases clean or the task is blocked, not "finished with a note" (../../core/lease/SPEC.md).
3. Record the resume point: what was done, what is half-done, the exact next command.
4. Re-fingerprint and confirm the diff against the session baseline is empty or fully disclosed.

## Red flags

- A phase with no before/after fingerprint, because "it was read-only."
- An availability assertion that accepts more than one status code.
- A write mentioned in passing, without measured scope.
- A restored timestamp, mtime, or checksum that was reconstructed rather than preserved.
- `mv` on anything you did not create this session.
- A permission error followed by a second, cleverer attempt.
- A session ending with containers up and no resume point written.
