---
name: routing
description: Use at the very start of every session and at every new request, before any other skill — classifies the work as chore, fix, probe, incident, or feature, sets the F0–F3 tier for features, and names the gates and tripwires that govern the rest of the run. Use when a request arrives with no ticket, when you cannot tell which pipeline applies, when the ceremony of a run feels mismatched to its risk, or when a tripwire fires mid-run and the tier must move.
origin: aurora
---

# Routing

Audience: any agent receiving a request, before it has done anything about it. Job: classify the work, set the tier, and name the gates and tripwires the rest of the run obeys.

## First act

Read ../../core/prime-directives.md and comply with it for the whole session. Do this before classifying, before asking a question, before opening a file. Nothing below relaxes it and nothing below is allowed to.

## Classification

Four questions, asked in order. **First match wins** — do not keep reading once a row answers.

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

**Q1 splits on the deliverable, not on the diff.** A pure investigation changes nothing and is still not a chore: it falls through, so a read-only diagnosis of a live problem reaches **incident** at question 2, and a pure fact-gathering job reaches **probe** at question 3.

**Live work during an incident is incident class.** Work performed on or against a live system while an incident is open belongs to the incident class regardless of how question 1 would classify it — a behaviour-neutral change made mid-incident is still incident work.

**chore carries a declared blast radius.** Name it before you start: which paths, which files, which surfaces. A chore whose diff exceeds its declared radius is no longer a chore — it changed behaviour someone did not sign off on.

State the answer in one line and wait for confirmation:

```
This is a <class>[ at <tier>]. Blast radius: <paths or surfaces>. Pipeline: pipelines/<name>.yaml.
```

That line is gate `G-CLASS`, and it fires on every run before anything else.

## Tier dial (features only)

The axis is **decision ownership** — who is allowed to decide, not how hard the work is.

| Tier | Decision ownership | Questions asked | Spec | Design | Human gates |
|---|---|---|---|---|---|
| **F0** trivial | Agent decides, reports after. | 0 | The commit message. | None. | 1 |
| **F1** light | Agent proposes, human ratifies. | ≤5, one pass, ~2 minutes | Inline, ≤10 lines, on the ticket. | None. | 4 |
| **F2** standard | Human owns the design, agent owns the implementation. | Until the decision tree is exhausted (../grilling/SKILL.md) | Spec document (../to-spec/SKILL.md). | Argued: 3 agents, prose, debated to consensus (../competing-designs/SKILL.md). | 7 |
| **F3** load-bearing | Human ratifies every decision; agent owns only fact-gathering. | Breadth-first grilling, then a wayfinder map (../wayfinder/SKILL.md) | Spec document plus a per-task named mutation table (../mutation-proof/SKILL.md). | Measured: 3 agents, 3 ephemeral stacks, spikes with numbers. | 10+ |

Gate counts are the entries the tier's manifest declares; `G-DECISION` opens once per decision batch, so F3's 10 is a floor. Triggered gates (`G-CHECKPOINT`, `G-BLOCKED`) are not counted — they fire at any tier.

Picking a tier picks how much deliberation the run buys. It does not pick how safe the run is.

## The invariant

**Cost scales on deliberation, never on safety.**

The invariants list is identical at every tier and in every class:

`prime-directives`, `verification-law`, `output-based-assertions`, `mutation-proof`, `practical-testing`, `lease-discipline`.

F0 carries the same six as F3. A chore carries the same six as an incident. **There is no quick mode that skips them.** An agent that proposes one has mis-read this skill.

(The doctrine is stated here; per-mechanism enforcement status — which requirements are wired today versus mandated and awaiting their mechanism — lives in ../practical-testing/SKILL.md's enforcement table.)

## Tripwires

These fire automatically on the condition, regardless of the tier anyone chose. Escalation is free and needs no permission. Exactly one automatic de-escalation exists — the last row.

| Tripwire | Consequence |
|---|---|
| Reality gate returns `UNVERIFIED` on a load-bearing claim | Run cannot sit below F1. Open `G-FACTS`. |
| A step resolves to a destructive verb, or targets a resource with no lease label | The task becomes a checkpoint task. Open `G-CHECKPOINT`. Tier unchanged. |
| Fix loop reaches round 3 on any task | The task was mis-tiered. Escalate one tier for the rest of the run. |
| Competing designs fail to reach consensus | Escalate argued → measured. Spike in ephemeral stacks. |
| A named mutation stays green | Fails spec review at every tier. Never suppressible. |
| A chore's diff exceeds its declared blast radius | Reclassify chore → F1. Re-enter at the spec stage. |
| A step is **about to** write outside this run's lease | Pause the task; open `G-CHECKPOINT` (prime directive 3). |
| A write has **already landed** on a resource without this run's lease label | Halt. Fingerprint against baseline, disclose in full, open `G-BLOCKED`. |
| Breadth-first grilling at F3 surfaces no fog | De-escalate to F2. The only automatic de-escalation. |

A tripwire is not advice. When the condition holds, the consequence has already happened — your job is to say so, not to decide whether it applies.

## Gates

Eleven ids exist: `G-CLASS` classification; `G-FACTS` a load-bearing claim could not be measured; `G-SEAMS` before the first test is written; `G-SPEC` spec ratification; `G-DESIGN` competing designs have reported; `G-DECISION` each map or grilling decision; `G-CHECKPOINT` destructive verb, live resource, shared namespace, or a step about to write outside the run's lease; `G-PLANCONFLICT` a review finding contradicts plan text; `G-BLOCKED` fix-loop breaker tripped on a load-bearing finding, or a write has already landed on a resource without this run's lease label; `G-E2E` before PR on user-facing work; `G-DEPLOY` the change needs human deploy or cleanup steps.

Fires-when, shape, and tiers for each: ../../core/gates.md. That file is the inventory — read it there, do not carry a stale copy in your head.

## Class → pipeline

| Class | Pipeline |
|---|---|
| chore | ../../pipelines/chore.yaml |
| fix | ../../pipelines/fix.yaml |
| probe | ../../pipelines/probe.yaml |
| incident | ../../pipelines/incident.yaml |
| feature F0 | ../../pipelines/f0.yaml |
| feature F1 | ../../pipelines/f1.yaml |
| feature F2 | ../../pipelines/f2.yaml |
| feature F3 | ../../pipelines/f3.yaml |

The manifest names the stages, the gates each stage opens, and the tripwires it watches. Follow it; do not improvise a stage order from this page.

## Platform references

Skills speak in actions — "dispatch a subagent", "read a file". Where your harness names those tools differently, the mapping is in references/codex-tools.md and references/gemini-tools.md.

## Red flags

- Classifying and starting work in the same breath, with no `G-CLASS` line stated.
- "It's only a chore" with no blast radius named.
- A tier chosen for how long the work will take rather than who owns the decisions.
- An invariant dropped "because this one is small."
- A tripwire noticed and then argued with.
- Reaching for a pipeline before reading ../../core/prime-directives.md.
