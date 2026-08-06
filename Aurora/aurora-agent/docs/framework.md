# Framework

Audience: contributors and agents orienting to how work flows through this repo. Job: name the classification, the tier dial, the tripwires, the gates, and the verbs — and route to the normative file for each.

New here and wanting the tour rather than the reference? `guide.md`.

Normative copies live elsewhere and win on conflict: `../skills/routing/SKILL.md` (classification, tier dial, tripwires), `../core/gates.md` (gates), `../core/verbs.md` (verbs), `../core/prime-directives.md` (the three rules never scaled down), `../pipelines/*.yaml` (stage order).

## Classification

Four questions, in order, first match wins. Normative: `../skills/routing/SKILL.md`.

| # | Ask | Answer | Class |
|---|---|---|---|
| 1 | Does any observable behaviour change? | no, and the deliverable is a change | **chore** |
| | | no, but the deliverable is a fact or a decision | go to 2 |
| | | yes | go to 2 |
| 2 | Is something already wrong? | yes, and it is live | **incident** |
| | | yes, in dev or test | **fix** |
| | | no | go to 3 |
| 3 | Is the deliverable a decision or a fact rather than code? | yes | **probe** |
| | | no | go to 4 |
| 4 | Everything else. | — | **feature** — continue to the tier dial |

Q1 splits on the deliverable, not on the diff. A chore declares its blast radius before it starts. Work performed on or against a live system during an incident is **incident** class regardless of how Q1 would classify it. The one-line answer is gate `G-CLASS`.

| Class | Pipeline |
|---|---|
| chore | `../pipelines/chore.yaml` |
| fix | `../pipelines/fix.yaml` |
| probe | `../pipelines/probe.yaml` |
| incident | `../pipelines/incident.yaml` |
| feature F0–F3 | `../pipelines/f0.yaml` … `../pipelines/f3.yaml` |

## Tier dial (features only)

The axis is decision ownership — who is allowed to decide, not how hard the work is.

| | F0 trivial | F1 light | F2 standard | F3 load-bearing |
|---|---|---|---|---|
| Decision ownership | Agent decides, reports after. | Agent proposes, human ratifies. | Human owns design, agent owns implementation. | Human ratifies every decision; agent gathers facts only. |
| Question budget | 0 | ≤5, one pass, ~2 min | Until the decision tree is exhausted | Breadth-first, then a wayfinder map |
| Spec artifact | The commit message. | Inline, ≤10 lines, on the ticket. | Spec document. | Spec document + per-task named mutation table. |
| Design alternatives | None. | None. | Argued: 3 agents, prose, debated to consensus. | Measured: 3 agents, spikes with numbers. |
| Review axes | Standards only. | Standards + spec; vacuity on request. | Standards + spec + vacuity. | Standards + spec + vacuity. |
| Stacks | Worktree only. | Worktree only. | Worktree only. | 3 ephemeral stacks for the spikes. |
| Human gates | 1 | 4 | 7 | 10+ |

Counts are the gate entries each manifest declares (`G-DECISION` opens once per decision batch, so F3's 10 is a floor). Gates that a manifest does not schedule — `G-CHECKPOINT`, `G-BLOCKED` — are excluded and fire on top, except where a manifest schedules one outright, as `incident.yaml` does with `G-CHECKPOINT` before the live apply. Non-feature classes: chore 1, fix 1, probe 2, incident 3.

## Tripwires

Fire automatically on the condition, whatever tier anyone chose. Escalation is free and needs no permission.

| Tripwire | Consequence |
|---|---|
| Reality gate returns `UNVERIFIED` on a load-bearing claim | Run cannot sit below F1. Open `G-FACTS`. |
| A step resolves to a destructive verb, or targets a resource with no lease label | Checkpoint task. Open `G-CHECKPOINT`. Tier unchanged. |
| A step is **about to** write outside the run's lease | Pause the task; open `G-CHECKPOINT` (prime directive 3). |
| A write has **already landed** on a resource without this run's lease label | Halt. Fingerprint against baseline, disclose in full, open `G-BLOCKED`. |
| Fix loop reaches round 3 on any task | Mis-tiered. Escalate one tier for the rest of the run. |
| Competing designs fail to reach consensus | Escalate argued → measured. Spike in ephemeral stacks. |
| A named mutation stays green | Fails spec review at every tier. Never suppressible. |
| A chore's diff exceeds its declared blast radius | Reclassify chore → F1. Re-enter at the spec stage. |
| Breadth-first grilling at F3 surfaces no fog | De-escalate to F2. The only automatic de-escalation. |

## Gates

Eleven ids. Fires-when, shape, and tiers are in `../core/gates.md` — read them there, do not carry a copy.

| id | One line |
|---|---|
| `G-CLASS` | Classification, every run, before anything else. |
| `G-FACTS` | A load-bearing claim could not be measured. |
| `G-SEAMS` | Before the first test is written. |
| `G-SPEC` | Spec ratification. |
| `G-DESIGN` | Competing designs have reported. |
| `G-DECISION` | Each map or grilling decision. |
| `G-CHECKPOINT` | Destructive verb, live resource, shared namespace, or a write about to leave the lease. |
| `G-PLANCONFLICT` | A review finding contradicts plan text. |
| `G-BLOCKED` | Fix-loop breaker on a load-bearing finding, or a write already landed off-lease. |
| `G-E2E` | Before PR on user-facing work. |
| `G-DEPLOY` | The change needs human deploy or cleanup steps. |

## Verbs

Pipelines call only these six. Adapter bindings: `../core/verbs.md`.

| Verb | One line |
|---|---|
| `dispatch(brief) -> report` | Run a brief as a subordinate agent with fresh context; the brief carries every path it needs. |
| `run(cmd) -> {output, exit_code}` | Execute in the worktree behind the guard; always return both fields. |
| `read(path) -> body` | Full contents as text. Never gated. |
| `write(path, body)` | Replace contents; outside the worktree or lease is a `G-CHECKPOINT` trigger, not an adapter's call. |
| `ask(gate) -> answered gate` | The only way a pipeline touches a human. Blocking; no auto-answer, default, or timeout. |
| `emit(event)` | Append one schema-valid line to the run journal. File-backed, append-only. |

## Conflict rulings

| Ruling | Resolution |
|---|---|
| Paths live in briefs, not tickets | Map tickets and specs are path-free and interface-level — they live for weeks and paths rot under them. Task briefs are generated at dispatch and carry exact paths, signatures, and test code; consumed within the hour, never stored. |
| Refactor scope | Line-scope tidy — rename, extract a helper — belongs inside the red-green loop. Anything that moves a seam belongs to the review stage or the anti-entropy pass, never mid-loop. |
| Continuous vs checkpoint | Continuous execution is the default; a run does not stop to be admired. A task touching a destructive verb, a live resource, or a shared namespace is a checkpoint task and breaks the run for human approval. |

## Invariants

Identical at every tier and in every class — F0 carries the same six as F3, a chore the same six as an incident:

`prime-directives`, `verification-law`, `output-based-assertions`, `mutation-proof`, `practical-testing`, `lease-discipline`.

**Cost scales on deliberation, never on safety.** There is no quick mode that skips an invariant; an agent proposing one has mis-read the framework.

(Doctrine is stated here and in routing; per-mechanism enforcement status — which requirements are in force today versus mandated and awaiting wiring — lives in `../skills/practical-testing/SKILL.md`'s enforcement table.)
