---
description: Run the aurora feature pipeline at tier F0-F3 (tier as argument, otherwise asked)
---

`${CLAUDE_PLUGIN_ROOT}` is the aurora plugin's install directory — the one holding `pipelines/`, `skills/`, and `core/`. If it reaches you unexpanded, resolve it once and use that for every path below; `.aurora/` alone is relative to the repo being worked on.

1. Read `${CLAUDE_PLUGIN_ROOT}/core/prime-directives.md` and comply with it for the whole session. Nothing below relaxes it.
2. Mint the run id `r-YYYY-MM-DD-<4hex>` and emit a `run.started` journal line (step 7).
3. Pick the tier. `$ARGUMENTS` may name one (`f0`, `f1`, `f2`, `f3`, or the bare digit) along with the request. If it names no tier, ask — a `choice` gate in the shape of `G-CLASS`, blocking, options and the axis being decision ownership:

   | Tier | Decision ownership |
   |---|---|
   | F0 trivial | Agent decides, reports after. |
   | F1 light | Agent proposes, human ratifies. |
   | F2 standard | Human owns the design, agent owns the implementation. |
   | F3 load-bearing | Human ratifies every decision; agent owns only fact-gathering. |

   The dial buys deliberation, not safety: the six invariants are identical at every tier.
4. Read the manifest for the chosen tier and follow it:

   | Tier | Manifest |
   |---|---|
   | F0 | `${CLAUDE_PLUGIN_ROOT}/pipelines/f0.yaml` |
   | F1 | `${CLAUDE_PLUGIN_ROOT}/pipelines/f1.yaml` |
   | F2 | `${CLAUDE_PLUGIN_ROOT}/pipelines/f2.yaml` |
   | F3 | `${CLAUDE_PLUGIN_ROOT}/pipelines/f3.yaml` |

   Execute its stages in order: for each stage, read `${CLAUDE_PLUGIN_ROOT}/skills/<stage.skill>/SKILL.md` and follow it with that stage's params and notes. The manifest owns the stage order — do not improvise one. Its first stage is `${CLAUDE_PLUGIN_ROOT}/skills/routing/SKILL.md`, which fires `G-CLASS`: state class, tier, and blast radius in one line before any file is opened.
5. Open every gate the stage lists: ask the user, block until answered. The gate object is shaped per `${CLAUDE_PLUGIN_ROOT}/core/gate.schema.json`; fires-when and shape per gate are in `${CLAUDE_PLUGIN_ROOT}/core/gates.md`. No auto-answer, no default, no timeout.
6. Arm the manifest's tripwires. On trigger, take the action verbatim — each tier's manifest carries its own consequences, and they differ (F3's fix-loop ceiling halts to `G-BLOCKED` rather than escalating). Where the action is an escalation, it is free and needs no permission.
7. Append journal lines per `${CLAUDE_PLUGIN_ROOT}/core/journal.schema.json` to `.aurora/runs/<run-id>/journal.jsonl`: `stage.entered` / `stage.exited` around each stage, `gate.opened` / `gate.closed` around each ask, `escalation.fired` on any tier move, `run.finished` at the end.

Request: $ARGUMENTS
