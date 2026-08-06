---
name: framework-guide
description: Use when someone asks what this framework is, which path fits the work they are about to start, how much of their attention a path will cost, or wants a tour of the five classes and the four feature tiers. Use when a developer lands cold on this repo, when someone is deciding between chore and fix or between F1 and F2, when someone asks why a run stopped to ask them something, or when someone wants to know what the framework can do without being asked first.
origin: aurora
---

# Framework guide

Audience: someone who has never seen this framework and wants to know what it offers and which path to take. Job: explain the five classes, the four feature tiers, what each costs in attention, and what fires without being asked — then hand off to the files that are normative.

**This file is the canonical tour.** `../../docs/guide.md` is the entry point for readers outside an agent session and routes here for the worked examples and the walkthrough. Nothing here is normative: where this page and `../routing/SKILL.md`, `../../core/gates.md`, or `../../pipelines/*.yaml` disagree, those win.

**Explains, does not execute.** Classifying and then running the work is `../routing/SKILL.md` and the pipelines. This page names the path and stops.

## What the framework is

Work does not arrive in one shape, so it does not get one process. Every request is classified into one of **five classes**; features additionally pick one of **four tiers**. The class picks a pipeline manifest — an ordered list of stages, the gates each stage opens, and the tripwires it watches. The tier picks how much of the decision-making the human keeps.

What the dial does *not* touch is safety. Six invariants run identically in every class and at every tier — the smallest chore and the largest feature both run mutation-proof and practical-testing.

## The five classes

| Class | The deliverable | Reach for it when | Gates |
|---|---|---|---|
| `chore` | A change nobody can observe from outside | The behaviour is identical afterwards and you can name the blast radius up front | 1 |
| `fix` | A repaired behaviour plus the test that would have caught it | Something is already wrong, in dev or test | 1 |
| `probe` | A finding — a fact or a decision, not a diff | The answer is the deliverable; no code needs to change to produce it | 2 |
| `incident` | A live system back to correct, with the diff explained | Something is already wrong **and it is live** | 3 |
| `feature` | New observable behaviour | Everything else — then pick a tier | 1–10+ |

Gate counts are the human-blocking gates the manifest declares; some are conditional. Full accounting under **What your attention actually costs**.

The classifier is four questions in order, first match wins (`../routing/SKILL.md`). Q1 splits on the **deliverable, not the diff** — that is the rule that decides most of the near misses below.

### chore

**For:** work whose whole point is that nothing changes for anyone using the system — renames, moves, dependency bumps, formatting, dead-code removal.

**Over its neighbours:** the discriminating question is *would a user notice?* If yes, it is a feature no matter how small the diff. If something is already broken, it is `fix` or `incident` — a chore assumes a working system. A chore must name its blast radius before starting; if you cannot say which paths it touches, it is not a chore yet.

**Costs you:** one gate. You confirm the class and the blast radius, then it runs to completion.

**Feels like:** you approve one line, it disappears into a worktree, and it comes back with the diff and a pasted test transcript. No questions in the middle.

**Example:** *"rename the `db_url` config key to `database_url` across the repo."* Nothing observable changes; the deliverable is a change → **chore**, blast radius `config/`, `src/**`, `tests/**`.

### fix

**For:** something that used to work, or was always meant to work, and does not — in development, CI, or a test environment.

**Over its neighbours:** the discriminating question is *is it live?* Same bug on a production system is `incident`, which fingerprints the live baseline first and never diagnoses in place. If nothing is actually wrong and you just want new behaviour, it is a `feature`. A read-only investigation of a live problem is still `incident` — the classifier reaches question 2 before it reaches probe.

**Costs you:** one gate. The regression test and the mutation it kills are the evidence; you are not asked to design anything.

**Feels like:** it reproduces the bug in a fresh worktree first and shows you red before it shows you a theory. You get a red-to-green transcript, not an assurance.

**Example:** *"the `/agent` route 502s in dev since yesterday."* Already wrong, not live → **fix**.

### probe

**For:** questions. Which library, what is our actual p99, does this API support batching, why is the build slow. The output is a written finding with citations.

**Over its neighbours:** the discriminating question is *does the deliverable exist once no code changes?* A probe produces a document. The moment the scope grows to writing code, the run re-classifies. A probe is not a `chore` — Q1 sends fact-shaped deliverables onward, and they land at question 3.

**Costs you:** one gate always, plus `G-FACTS` if a load-bearing claim could not be measured — that gate exists so an unmeasured claim never reaches you dressed as a fact.

**Feels like:** no worktree, no code review, nothing to merge. Claims come back marked measured or unverified, and you approve the unverified ones knowingly.

**Example:** *"which message queue should we adopt — Kafka, NATS, or Redis Streams?"* Deliverable is a decision → **probe**.

### incident

**For:** a live system that is wrong right now.

**Over its neighbours:** the discriminating question is *is it live?* This class overrides everything: work performed on or against a live system while an incident is open is incident class even when the change itself is behaviour-neutral, and even when your part is purely read-only.

**Costs you:** three gates — the class, a checkpoint before any live apply, and a deploy gate for steps a human must run. Prime directive 2 governs the whole run: prod reads are fine, prod writes need your consent given in this session, every time.

**Feels like:** the first thing that happens is a baseline fingerprint of the live system. Diagnosis happens on a replica. The remedy is rehearsed end to end before it is proposed. You are shown the rehearsal transcript and asked to approve the apply; afterwards, a re-fingerprint compared against the baseline. If the diff shows state the baseline did not predict, it stops and reports rather than remediating over it.

**Example:** *"the prod dashboard is down."* Already wrong, and live → **incident**.

### feature

**For:** everything else. New behaviour someone will notice.

**Over its neighbours:** it is the fall-through. Anything that changes observable behaviour and is not repairing something already broken lands here. Then pick a tier.

**Costs you:** 1 to 10+ gates, depending entirely on the tier you pick.

**Feels like:** varies by tier — see the walkthrough at the end for what one F1 run feels like start to finish.

**Example:** *"add SSO login."* Observable, nothing is broken, deliverable is code → **feature**, and the tier is the real question.

## The four feature tiers

The axis is **decision ownership**. The tier is a statement about how much of the decision-making you want to own — not about lines of code, not about how hard the work is, not about how long it will take.

| | **F0** trivial | **F1** light | **F2** standard | **F3** load-bearing |
|---|---|---|---|---|
| Who decides | Agent decides, reports after | Agent proposes, human ratifies | Human owns the design, agent owns the implementation | Human ratifies every decision; agent gathers facts only |
| Questions you answer | 0 | ≤5, one pass, ~2 min | Until the decision tree is exhausted | Breadth-first grilling, then a map |
| Spec | The commit message | Inline, ≤10 lines | Spec document | Spec document + per-task named mutation table |
| Design alternatives | None | None | Argued: 3 agents, prose, to consensus | Measured: 3 agents, spikes with numbers |
| Human gates | 1 | 4 | 7 | 10+ |

How to choose:

- **Pick F0** when you would accept whatever a competent engineer did without telling you. There is no spec and no question — you find out afterwards.
- **Pick F1** when you have an opinion but not a design. You answer up to five questions, ratify a ten-line spec, and the agent runs. This is the default for most work.
- **Pick F2** when the design is the risky part and you want to own it. You are grilled until no branch of the decision tree is unanswered, three designs are argued to consensus in front of you, and you ratify a spec document before any code exists.
- **Pick F3** when being wrong is expensive and you want every decision on the record. Nothing is decided without you; the agent's job narrows to gathering facts and measuring spikes.

A large diff at F0 is fine if you genuinely do not want to be consulted. A three-line change at F3 is fine if those three lines carry the company. **Size is not the axis.**

## What your attention actually costs

The counts below are the gate entries each manifest declares — every one is a blocking stop for a human. `ask` is the only way a pipeline touches you, and blocking means blocking: no auto-answer, no default, no timeout into a decision.

| Path | Gates | Which |
|---|---|---|
| `chore` | 1 | `G-CLASS` |
| `fix` | 1 | `G-CLASS` |
| `probe` | 2 | `G-CLASS`, `G-FACTS` (conditional — only on an unverified claim) |
| `incident` | 3 | `G-CLASS`, `G-CHECKPOINT` (before any live apply), `G-DEPLOY` (conditional) |
| feature **F0** | 1 | `G-CLASS` |
| feature **F1** | 4 | `G-CLASS`, `G-SPEC`, `G-SEAMS`, `G-E2E` (skipped when nothing user-facing changed) |
| feature **F2** | 7 | `G-CLASS`, `G-FACTS`, `G-DESIGN`, `G-SPEC`, `G-SEAMS`, `G-PLANCONFLICT`, `G-E2E` |
| feature **F3** | 10+ | the F2 set plus three `G-DECISION` stages — and `G-DECISION` opens once *per decision batch*, so 10 is a floor, not a ceiling |

Two more gates are usually triggered rather than scheduled, so they are not in these counts: `G-CHECKPOINT` (a destructive verb, a live resource, or a write about to leave the run's lease) and `G-BLOCKED` (a fix loop that cannot be broken, or a write that already landed off-lease). They can fire in any class and at any tier, on top of the numbers above — **except where a manifest schedules one outright, as `incident.yaml` does with `G-CHECKPOINT` before the live apply, which is why it is counted in incident's three.** Full inventory: `../../core/gates.md`.

## What never scales down

Six invariants, identical in every class and at every tier. F0 carries the same six as F3; a chore carries the same six as an incident:

`prime-directives`, `verification-law`, `output-based-assertions`, `mutation-proof`, `practical-testing`, `lease-discipline`.

Concretely, on a two-line chore you still get: an ephemeral worktree rather than an edit in place; a named mutation, injected into the code, shown to turn the suite red; the feature exercised the way a caller uses it rather than a green unit suite offered as proof; and a pasted command with its output before any claim that it works.

**Cost scales on deliberation, never on safety.** There is no quick mode that skips an invariant. An agent that offers you one has mis-read the framework, and that is the single most useful thing to know about it.

(Doctrine here; per-mechanism enforcement status — what is wired today versus mandated and awaiting its mechanism — is the enforcement table in `../practical-testing/SKILL.md`.)

## What can happen without you asking

Tripwires fire on their condition, regardless of the tier anyone picked. Escalation is free and needs no permission — so a run can get *more* careful mid-flight without consulting you. It never gets less careful, with exactly one exception, the last row.

| If this happens | This happens to your run |
|---|---|
| Your chore's diff outgrows the blast radius you declared | It stops being a chore. Reclassified to feature **F1**, re-entering at the spec stage — so you get asked to ratify a spec you were not expecting |
| A load-bearing claim comes back unverified | The run cannot sit below **F1**, and `G-FACTS` opens so you can ratify or reject the claim knowingly |
| A step resolves to a destructive verb, or targets a resource with no lease label | It pauses for your approval (`G-CHECKPOINT`). Tier unchanged — this is a stop, not an escalation |
| A step is about to write outside the run's lease | Same pause, before the write, by prime directive 3 |
| A write already landed off-lease | Full halt. Fingerprint against baseline, complete disclosure, `G-BLOCKED` |
| The fix loop hits round 3 on any task | The task was mis-tiered. One tier up for the rest of the run (at F3 there is no higher tier, so it halts instead) |
| Competing designs cannot reach consensus | Argued mode escalates to measured — real spikes with numbers instead of prose |
| A named mutation stays green | Fails spec review at every tier. Never suppressible |
| Breadth-first grilling at F3 surfaces no fog | De-escalates to F2. **The only automatic de-escalation** |

None of these need your permission to fire, and none can be argued with — when the condition holds, the consequence has already happened. Knowing they exist is the point: a chore that suddenly asks you to ratify a spec is not malfunctioning.

## One F1 feature run, start to finish

*"Add SSO login"*, taken at F1 — you have an opinion but not a design.

1. **Routing → `G-CLASS` opens.** You are shown one line: the class, the tier, the blast radius, and the manifest that will run. You confirm it or correct it. Nothing has been opened yet.
2. **Grilling → `G-SPEC` opens.** Up to five questions, one pass, around two minutes: which identity provider, what happens to existing password accounts, is session length changing, what does failure look like to the user. The answers become an inline spec of ten lines or fewer. You ratify that spec. **This is your design input; there is no second chance at it.**
3. **Reality gate — no gate, unless.** Every load-bearing claim the spec rests on is measured for real. If one cannot be measured, `G-FACTS` opens here — chronologically your third stop, and an unscheduled one, taking the run from four gates to five — and you decide whether the run may rest on the claim.
4. **Worktree.** An ephemeral worktree and environment. Nothing happens in your working tree.
5. **Tickets.** Only if the work is more than one slice; a single-slice feature goes straight to the test.
6. **TDD → `G-SEAMS` opens.** Before the first test is written, you are shown the seams it intends to test at — the checklist that decides whether the tests will be worth anything. Agree or redirect.
7. **Mutation-proof — no gate.** A named mutation per behaviour, injected, shown turning the suite red. If a mutation stays green, that fails review and cannot be waived.
8. **Practical testing — no gate.** The login flow exercised the way a user drives it, not the way the unit suite calls it.
9. **Verification — no gate.** The command and its output pasted before any claim of success.
10. **Code review — no gate.** Standards and spec axes; the vacuity axis on request.
11. **Finishing → `G-E2E` opens.** SSO is user-facing, so before the PR you get an end-to-end checklist to confirm against. On work with no user-facing surface this gate is skipped, and the run costs three.

Four stops. Between them it runs continuously — a run does not stop to be admired.

## Where to go next

This page is a tour. Every rule it describes is stated normatively somewhere else, and those files win:

| For | Read |
|---|---|
| Classification, the tier dial, tripwires — the normative form | `../routing/SKILL.md` |
| The gate inventory: fires-when, shape, tiers | `../../core/gates.md` |
| The three rules never scaled down | `../../core/prime-directives.md` |
| Exact stage order, gates, and tripwires per path | `../../pipelines/` — one manifest per class and tier |
| A condensed version outside an agent session | `../../docs/guide.md` |

To actually start work, hand off: `../routing/SKILL.md` classifies and enters the pipeline. This skill does not.
