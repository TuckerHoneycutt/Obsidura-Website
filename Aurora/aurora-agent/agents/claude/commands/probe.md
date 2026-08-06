---
description: Run the aurora probe pipeline — the deliverable is a decision or a fact, not code
---

`${CLAUDE_PLUGIN_ROOT}` is the aurora plugin's install directory — the one holding `pipelines/`, `skills/`, and `core/`. If it reaches you unexpanded, resolve it once and use that for every path below; `.aurora/` alone is relative to the repo being worked on.

1. Read `${CLAUDE_PLUGIN_ROOT}/core/prime-directives.md` and comply with it for the whole session. Nothing below relaxes it.
2. Mint the run id `r-YYYY-MM-DD-<4hex>` and emit a `run.started` journal line (step 6).
3. Read `${CLAUDE_PLUGIN_ROOT}/pipelines/probe.yaml`. Execute its stages in order: for each stage, read `${CLAUDE_PLUGIN_ROOT}/skills/<stage.skill>/SKILL.md` and follow it with that stage's params and notes. The manifest owns the stage order — do not improvise one. Its first stage is `${CLAUDE_PLUGIN_ROOT}/skills/routing/SKILL.md`, which fires `G-CLASS`; a probe produces a finding, not a diff — no worktree and no code review.
4. Open every gate the stage lists: ask the user, block until answered. The gate object is shaped per `${CLAUDE_PLUGIN_ROOT}/core/gate.schema.json`; fires-when and shape per gate are in `${CLAUDE_PLUGIN_ROOT}/core/gates.md`. `G-FACTS` is conditional — it fires on any load-bearing claim that came back UNVERIFIED. No auto-answer, no default, no timeout.
5. Arm the manifest's tripwires. On trigger, take the action verbatim — notably: if the scope grows to writing or changing code, re-enter routing and pick the class the new deliverable answers to.
6. Append journal lines per `${CLAUDE_PLUGIN_ROOT}/core/journal.schema.json` to `.aurora/runs/<run-id>/journal.jsonl`: `stage.entered` / `stage.exited` around each stage, `gate.opened` / `gate.closed` around each ask, `run.finished` at the end.

Question: $ARGUMENTS
