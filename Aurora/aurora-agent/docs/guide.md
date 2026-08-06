# Guide

Audience: someone who has never seen this framework — browsing the repo, or driving it from a harness that is not Claude Code. Job: explain what it offers, which path fits your work, and what each path costs you in attention.

**`../skills/framework-guide/SKILL.md` is canonical for the worked examples, the per-class discriminating questions, the tripwire consequences, and the end-to-end walkthrough** — this page does not restate any of them. What it does carry is the skimmable payload for readers outside an agent session: the class, tier, and attention-cost tables, which appear in both files deliberately because they are the thing people come for.

Normative files win over both: `../skills/routing/SKILL.md` (classification, tiers, tripwires), `../core/gates.md` (gates), `../core/prime-directives.md` (the three rules), `../pipelines/*.yaml` (stage order). `framework.md` is the contributor-facing reference for the same machinery.

## How work flows

A request is classified into one of five classes; features additionally pick a tier. The class picks a pipeline manifest — the stages, the gates each opens, the tripwires it watches. The tier picks how much of the decision-making you keep.

| Class | The deliverable | Reach for it when | Example |
|---|---|---|---|
| `chore` | A change nobody can observe | Behaviour is identical afterwards and you can name the blast radius up front | "rename a config key across the repo" |
| `fix` | A repaired behaviour plus the test that would have caught it | Something is already wrong, in dev or test | "the /agent route 502s in dev" |
| `probe` | A finding — a fact or a decision, not a diff | The answer *is* the deliverable | "which message queue should we adopt" |
| `incident` | A live system back to correct, with the diff explained | Already wrong, **and live** | "prod dashboard is down" |
| `feature` | New observable behaviour | Everything else — then pick a tier | "add SSO login" |

Four questions decide it, in order, first match wins. The one that resolves most near misses: **question 1 splits on the deliverable, not the diff.** A read-only diagnosis of a live problem is `incident`, not `probe`; a pure fact-gathering job is `probe`, not `chore`.

## The four feature tiers

The axis is **decision ownership** — how much of the decision-making you want to own. Not lines of code, not difficulty, not duration. A large diff at F0 is fine if you truly do not want to be consulted; a three-line change at F3 is fine if those three lines carry the company.

| Tier | Who decides | Spec | Human gates |
|---|---|---|---|
| **F0** trivial | Agent decides, reports after | The commit message | 1 |
| **F1** light | Agent proposes, human ratifies | Inline, ≤10 lines | 4 |
| **F2** standard | Human owns the design, agent owns the implementation | Spec document | 7 |
| **F3** load-bearing | Human ratifies every decision; agent gathers facts only | Spec document + per-task named mutation table | 10+ |

## What your attention costs

Every gate is a blocking stop for a human — no auto-answer, no default, no timeout into a decision.

| Path | Gates | Which |
|---|---|---|
| `chore` / `fix` / feature `F0` | 1 | `G-CLASS` |
| `probe` | 2 | `G-CLASS`, `G-FACTS` (conditional) |
| `incident` | 3 | `G-CLASS`, `G-CHECKPOINT` before any live apply, `G-DEPLOY` (conditional) |
| feature `F1` | 4 | `G-CLASS`, `G-SPEC`, `G-SEAMS`, `G-E2E` (skipped when nothing user-facing changed) |
| feature `F2` | 7 | the F1 set plus `G-FACTS`, `G-DESIGN`, `G-PLANCONFLICT` |
| feature `F3` | 10+ | the F2 set plus three `G-DECISION` stages, each opening once per decision batch |

`G-CHECKPOINT` and `G-BLOCKED` are usually triggered rather than scheduled, so they are not in these counts and can fire in any class at any tier on top of them — except where a manifest schedules one outright, as `incident.yaml` does with `G-CHECKPOINT` before the live apply, which is why it is counted in incident's three. Inventory: `../core/gates.md`.

## What never scales down

Six invariants, identical in every class and at every tier — F0 carries the same six as F3, a chore the same six as an incident:

`prime-directives`, `verification-law`, `output-based-assertions`, `mutation-proof`, `practical-testing`, `lease-discipline`.

On a two-line chore that still means an ephemeral worktree rather than an edit in place, a named mutation shown turning the suite red, the change exercised the way a caller uses it, and a pasted command with its output before any claim that it works.

**Cost scales on deliberation, never on safety.** There is no quick mode that skips an invariant; an agent offering one has mis-read the framework.

## What happens without you asking

Tripwires fire on their condition whatever tier was chosen, and need no permission. A run can reclassify itself, escalate a tier, pause for your approval, or halt outright mid-flight — your chore can become an F1 feature and ask you to ratify a spec you were not expecting, and that is the framework working, not malfunctioning. It only ever becomes more careful, with one exception.

The nine conditions and what each does to your run: `../skills/framework-guide/SKILL.md`. Normative: `../skills/routing/SKILL.md`.

## Starting a run

| You are using | Do this |
|---|---|
| **Claude Code** | `/aurora:help` for the tour, `/aurora:help <what you want to do>` for which-path advice; then `/aurora:route`, or the class command directly. `/aurora:help` explains and stops — it never opens a pipeline |
| **Hermes** | `skills/`, `pipelines/`, and `core/` arrive in `$HERMES_HOME` via `hermes profile update`. Start at `skills/routing/SKILL.md` |
| **Any other agent** | Read `../core/prime-directives.md`, then `../skills/routing/SKILL.md`, then follow the matching `../pipelines/<class>.yaml` stage by stage |

Worked examples per class, the discriminating question that separates each class from its neighbours, and a gate-by-gate walkthrough of one F1 feature run: `../skills/framework-guide/SKILL.md`.
