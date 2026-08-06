---
description: Classify a request, set the tier, and enter the matching aurora pipeline
---

`${CLAUDE_PLUGIN_ROOT}` is the aurora plugin's install directory — the one holding `pipelines/`, `skills/`, and `core/`. If it reaches you unexpanded, resolve it once and use that for every path below; `.aurora/` alone is relative to the repo being worked on.

1. Read `${CLAUDE_PLUGIN_ROOT}/core/prime-directives.md` and comply with it for the whole session. Nothing below relaxes it.
2. Mint the run id `r-YYYY-MM-DD-<4hex>` and emit a `run.started` journal line (step 6).
3. Read `${CLAUDE_PLUGIN_ROOT}/skills/routing/SKILL.md`. Walk its classification table in order — first match wins — and, if the class is feature, walk the tier dial (decision ownership, not difficulty). State the result in one line and wait for confirmation: that line is gate `G-CLASS`.

   ```
   This is a <class>[ at <tier>]. Blast radius: <paths or surfaces>. Pipeline: pipelines/<name>.yaml.
   ```
4. Follow the matching manifest:

   | Class | Manifest |
   |---|---|
   | chore | `${CLAUDE_PLUGIN_ROOT}/pipelines/chore.yaml` |
   | fix | `${CLAUDE_PLUGIN_ROOT}/pipelines/fix.yaml` |
   | probe | `${CLAUDE_PLUGIN_ROOT}/pipelines/probe.yaml` |
   | incident | `${CLAUDE_PLUGIN_ROOT}/pipelines/incident.yaml` |
   | feature F0 | `${CLAUDE_PLUGIN_ROOT}/pipelines/f0.yaml` |
   | feature F1 | `${CLAUDE_PLUGIN_ROOT}/pipelines/f1.yaml` |
   | feature F2 | `${CLAUDE_PLUGIN_ROOT}/pipelines/f2.yaml` |
   | feature F3 | `${CLAUDE_PLUGIN_ROOT}/pipelines/f3.yaml` |

   Execute its stages in order: for each stage, read `${CLAUDE_PLUGIN_ROOT}/skills/<stage.skill>/SKILL.md` and follow it with that stage's params and notes. The manifest owns the stage order — do not improvise one.
5. Open every gate the stage lists: ask the user, block until answered. The gate object is shaped per `${CLAUDE_PLUGIN_ROOT}/core/gate.schema.json`; fires-when and shape per gate are in `${CLAUDE_PLUGIN_ROOT}/core/gates.md`. No auto-answer, no default, no timeout. Arm the manifest's tripwires; on trigger, take the action verbatim.
6. Append journal lines per `${CLAUDE_PLUGIN_ROOT}/core/journal.schema.json` to `.aurora/runs/<run-id>/journal.jsonl`: `stage.entered` / `stage.exited` around each stage, `gate.opened` / `gate.closed` around each ask, `run.finished` at the end.

Request: $ARGUMENTS
