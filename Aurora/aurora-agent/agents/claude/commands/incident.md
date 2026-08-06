---
description: Run the aurora incident pipeline — something is already wrong and it is live
---

`${CLAUDE_PLUGIN_ROOT}` is the aurora plugin's install directory — the one holding `pipelines/`, `skills/`, and `core/`. If it reaches you unexpanded, resolve it once and use that for every path below; `.aurora/` alone is relative to the repo being worked on.

1. Read `${CLAUDE_PLUGIN_ROOT}/core/prime-directives.md` and comply with it for the whole session. Nothing below relaxes it. Prime directive 2 governs this whole run: prod reads are fine, prod writes need explicit human consent given in this session.
2. Mint the run id `r-YYYY-MM-DD-<4hex>` and emit a `run.started` journal line (step 6).
3. Read `${CLAUDE_PLUGIN_ROOT}/pipelines/incident.yaml`. Execute its stages in order: for each stage, read `${CLAUDE_PLUGIN_ROOT}/skills/<stage.skill>/SKILL.md` and follow it with that stage's params and notes. The manifest owns the stage order — do not improvise one. Its first stage is `${CLAUDE_PLUGIN_ROOT}/skills/routing/SKILL.md`, which fires `G-CLASS`; fingerprint the live baseline before anything else and diagnose on a replica, never live.
4. Open every gate the stage lists: ask the user, block until answered. The gate object is shaped per `${CLAUDE_PLUGIN_ROOT}/core/gate.schema.json`; fires-when and shape per gate are in `${CLAUDE_PLUGIN_ROOT}/core/gates.md`. `G-CHECKPOINT` before any live apply, `G-DEPLOY` for human deploy or cleanup steps. No auto-answer, no default, no timeout.
5. Arm the manifest's tripwires. On trigger, take the action verbatim — notably: a fingerprint diff showing state the baseline did not predict means stop and report; do not remediate over an unexplained diff.
6. Append journal lines per `${CLAUDE_PLUGIN_ROOT}/core/journal.schema.json` to `.aurora/runs/<run-id>/journal.jsonl`: `stage.entered` / `stage.exited` around each stage, `gate.opened` / `gate.closed` around each ask, `run.finished` at the end.

Incident: $ARGUMENTS
