---
description: Explain the aurora framework, or say which class and tier fit a described piece of work — explains and stops, never runs a pipeline
---

`${CLAUDE_PLUGIN_ROOT}` is the aurora plugin's install directory — the one holding `pipelines/`, `skills/`, and `core/`. If it reaches you unexpanded, resolve it once and use that for every path below; `.aurora/` alone is relative to the repo being worked on.

1. Read `${CLAUDE_PLUGIN_ROOT}/core/prime-directives.md` and comply with it for the whole session. Nothing below relaxes it.
2. Read `${CLAUDE_PLUGIN_ROOT}/skills/framework-guide/SKILL.md`. It is the canonical tour and the source for everything you say below.

**This command explains and stops.** It never opens a pipeline, never mints a run id, never creates a worktree, never writes code, and opens no gate; it may ask a clarifying question. It is the explain-don't-execute counterpart to `/aurora:route`, which classifies and then *runs*. When the user is ready to work, name the command and let them invoke it.

## Mode A — `$ARGUMENTS` is empty: give the tour

Cover, in this order, from the guide:

1. **The five classes** — `chore`, `fix`, `probe`, `incident`, `feature` — one line each on what it is for and the question that picks it.
2. **The four feature tiers F0–F3** on the decision-ownership axis: the tier says how much of the decision-making the human wants to own, not how large the change is.
3. **What your attention costs** — the real human-gate counts per path.
4. **What never scales down** — the six invariants, identical in every class and at every tier.
5. **What can happen without being asked** — the tripwires, in user terms.
6. **The commands**:

   | Command | Does |
   |---|---|
   | `/aurora:help [what you want to do]` | This command. Tour, or which-path advice. Never executes. |
   | `/aurora:route <request>` | Classifies, then enters the matching pipeline. |
   | `/aurora:chore <task>` | `pipelines/chore.yaml` — no observable behaviour change, blast radius declared up front. |
   | `/aurora:fix <report>` | `pipelines/fix.yaml` — already wrong, in dev or test. |
   | `/aurora:probe <question>` | `pipelines/probe.yaml` — the deliverable is a fact or a decision. |
   | `/aurora:incident <report>` | `pipelines/incident.yaml` — already wrong, and live. |
   | `/aurora:feature [f0-f3] <request>` | `pipelines/f0.yaml` … `pipelines/f3.yaml` — everything else. |

Close by offering the follow-up: *tell me what you are trying to do and I will tell you which path it takes.*

## Mode B — `$ARGUMENTS` describes intended work: say which path

Read `${CLAUDE_PLUGIN_ROOT}/skills/routing/SKILL.md` and walk its classification table against what the user described — four questions, in order, first match wins. If the class is feature, walk the tier dial too. Then report:

1. **The recommendation** — class, and tier if it is a feature.
2. **Why** — which numbered question decided it, and what the user's own words answered.
3. **The near miss** — the neighbouring class or tier this was closest to, and the specific reason it lost. A recommendation with no rejected alternative has not been reasoned.
4. **What it will cost you** — the human gates the manifest declares for that path, named, and what each one asks.
5. **How to start it** — the exact command, written out with the user's request in it, ready to copy.

Ask a clarifying question only where the answer would change the class or the tier — for example, whether the broken system is live (fix vs incident) or whether the user wants to own the design (F1 vs F2). State the assumption and recommend anyway if the user does not answer; do not stall on it.

Do not begin the work. Do not read the codebase to "check" the recommendation. Stop after the recommendation.

Request: $ARGUMENTS
