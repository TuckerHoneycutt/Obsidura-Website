---
description: Run the aurora chore pipeline — no observable behaviour change, declared blast radius
---

`${CLAUDE_PLUGIN_ROOT}` is the aurora plugin's install directory — the one holding `pipelines/`, `skills/`, and `core/`. If it reaches you unexpanded, resolve it once and use that for every path below; `.aurora/` alone is relative to the repo being worked on.

1. Read `${CLAUDE_PLUGIN_ROOT}/core/prime-directives.md` and comply with it for the whole session. Nothing below relaxes it.
2. Mint the run id `r-YYYY-MM-DD-<4hex>` and emit a `run.started` journal line (step 6).
3. Read `${CLAUDE_PLUGIN_ROOT}/pipelines/chore.yaml`. Execute its stages in order: for each stage, read `${CLAUDE_PLUGIN_ROOT}/skills/<stage.skill>/SKILL.md` and follow it with that stage's params and notes. The manifest owns the stage order — do not improvise one. Its first stage is `${CLAUDE_PLUGIN_ROOT}/skills/routing/SKILL.md`, which fires `G-CLASS`: state the class and the declared blast radius in one line before any file is opened.
4. Open every gate the stage lists: ask the user, block until answered. The gate object is shaped per `${CLAUDE_PLUGIN_ROOT}/core/gate.schema.json`; fires-when and shape per gate are in `${CLAUDE_PLUGIN_ROOT}/core/gates.md`. No auto-answer, no default, no timeout.
5. Arm the manifest's tripwires. On trigger, take the action verbatim — notably: a diff that exceeds the declared blast radius reclassifies chore → feature F1 and re-enters at the spec stage.
6. Append journal lines per `${CLAUDE_PLUGIN_ROOT}/core/journal.schema.json` to `.aurora/runs/<run-id>/journal.jsonl`: `stage.entered` / `stage.exited` around each stage, `gate.opened` / `gate.closed` around each ask, `run.finished` at the end.

Task: $ARGUMENTS
