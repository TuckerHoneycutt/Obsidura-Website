---
description: Run the aurora fix pipeline — something is already wrong in dev or test
---

`${CLAUDE_PLUGIN_ROOT}` is the aurora plugin's install directory — the one holding `pipelines/`, `skills/`, and `core/`. If it reaches you unexpanded, resolve it once and use that for every path below; `.aurora/` alone is relative to the repo being worked on.

1. Read `${CLAUDE_PLUGIN_ROOT}/core/prime-directives.md` and comply with it for the whole session. Nothing below relaxes it.
2. Mint the run id `r-YYYY-MM-DD-<4hex>` and emit a `run.started` journal line (step 6).
3. Read `${CLAUDE_PLUGIN_ROOT}/pipelines/fix.yaml`. Execute its stages in order: for each stage, read `${CLAUDE_PLUGIN_ROOT}/skills/<stage.skill>/SKILL.md` and follow it with that stage's params and notes. The manifest owns the stage order — do not improvise one. Its first stage is `${CLAUDE_PLUGIN_ROOT}/skills/routing/SKILL.md`, which fires `G-CLASS`; reproduce and repair in an ephemeral worktree, never in the environment that reported the bug.
4. Open every gate the stage lists: ask the user, block until answered. The gate object is shaped per `${CLAUDE_PLUGIN_ROOT}/core/gate.schema.json`; fires-when and shape per gate are in `${CLAUDE_PLUGIN_ROOT}/core/gates.md`. No auto-answer, no default, no timeout.
5. Arm the manifest's tripwires. On trigger, take the action verbatim — notably: fix loop round 3 means the task was mis-tiered, escalate one tier for the rest of the run.
6. Append journal lines per `${CLAUDE_PLUGIN_ROOT}/core/journal.schema.json` to `.aurora/runs/<run-id>/journal.jsonl`: `stage.entered` / `stage.exited` around each stage, `gate.opened` / `gate.closed` around each ask, `run.finished` at the end.

Bug report: $ARGUMENTS
