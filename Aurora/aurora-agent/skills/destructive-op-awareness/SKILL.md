---
name: destructive-op-awareness
description: Use before writing, reviewing, or relying on any check that stands between an agent and a destructive operation — teardown, deletion, pruning, dropping, resetting, or overwriting. Use when a document says "never run this against production", when a guard is written as a negative comparison, when a destructive verb is not on any list, and when deciding what a guard mutation is allowed to run against.
origin: aurora
---

# Destructive-op awareness

Audience: anyone writing a destructive step or the guard in front of it. Job: know what actually stops a deletion, and what only looks like it does.

An agent destroyed live production with `docker compose -p <prod> down -v` while executing a mutation table that disabled its own guards one at a time. Every rule below comes from that.

## The principles

| # | Rule | Why |
|---|---|---|
| 1 | **Prose is not a guard.** | "Never run this against production" existed in three documents. Production died anyway. Write an executable guard. |
| 2 | **Guards are positive.** Prove the target **is** in the safe namespace. | `!= production` passes on `""`, `None`, `"prodution"`, `" br-x"` — every typo nobody blacklisted. And `-p ""` is not a no-op; Compose falls back to the directory name. |
| 3 | **A declaration only proves scope where scope is structural.** | `compose down -p br-x` cannot escape its project. `docker volume rm X` ignores the project entirely. One env var is not proof for both. |
| 4 | **Whitelist the verbs.** | An unanticipated destructive spelling is refused by default, not waved through as "not on the list". |
| 5 | **Never block recovery.** `up`, `start`, `restore` always pass. | A guard that blocks restoring production is worse than no guard. |
| 6 | **One obvious override**, typed on the command line, loud on stderr. | A human gets through in one keystroke and its use is visible in shell history. One hatch, not a family. |
| 7 | **Test the guard against a stub, never the live tool.** | The first guard passed the incident command straight through — against the real daemon, the test would have destroyed production a second time. A later broken edit made every case fail: against a stub, fifteen loud failures in ten seconds; against a live daemon it would have looked maximally safe. |
| 8 | **Tripwire the function that touches the destination**, not only the one that moves bytes. | A guard over the byte-movers missed a `mkdir` + `copystat` and moved production's directory mtime. Elsewhere the first write turned out to be `docker volume create`, not `docker run`. |
| 9 | **A mutation that disables a guard runs against a stub or a tripwire.** | This is the rule that would have prevented the incident. See ../mutation-proof/SKILL.md. |

## In this repo

- `../../core/guard/SPEC.md` — **status: stub.** The argv layer is real and tested; the refusal predicate raises `NotImplementedError`. Build against the SPEC, not against the stub's silence.
- The predicate it pins: allow a destructive verb only when `target labels ⊇ {lease: <this session's lease>}`. Unlabeled → refuse. Foreign lease → refuse. No lease held → refuse.
- `../../core/prime-directives.md` governs regardless: ephemeral only, prod writes need consent given this session, and anything outside your worktree or lease stops at `G-CHECKPOINT`.

Until the predicate is implemented, the guard stops nothing. Behave as if it is watching and as if it is not.

## Red flags

- A safety claim that lives only in a sentence.
- Any guard expressed as `!=`, `not in`, or a blacklist.
- An environment variable accepted as proof of scope for an operation whose scope is not structural.
- A destructive verb reaching the tool because no rule mentioned it.
- A guard that also blocks bringing the system back up.
- A second override added "for convenience."
- A guard test that talks to the real daemon.
- A mutation table that disables safety, pointed at anything live.
