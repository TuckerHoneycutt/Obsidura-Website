---
name: competing-designs
description: Use when the design space is wide and the first idea is about to become the design — F2 and F3 features, new modules, new interfaces, anything where a seam is being placed for the first time. Use when three approaches are plausible and nobody can say why one wins, when a design review needs more than one option to compare, and when an argued comparison deadlocks and the decision has to be settled by measurement instead.
origin: aurora
---

# Competing designs

Audience: the controller of an F2 or F3 run, at the point where a design must be chosen. Job: get three genuinely different designs argued to consensus, and adjudicate only if they deadlock.

Your first idea is unlikely to be the best one. Three agents that each want a different answer will surface the trade-off that one agent, agreeing with itself, never sees.

## The three roles

Spawn three agents in parallel (../dispatching-parallel-agents/SKILL.md). Each carries a **stance** and a **distinct interface constraint** — the pairing is what keeps the designs from converging on the same shape.

| # | Stance | Interface constraint |
|---|---|---|
| 1 | The simplest, most orthodox solution. What a competent engineer would write without ceremony. | Minimize the interface — 1–3 entry points, maximum leverage per entry point. |
| 2 | Unconventional but more convenient. The approach nobody reaches for first, that might be much nicer to live with. | Maximize flexibility — support many use cases and extension. |
| 3 | The highest-performance, most theoretically optimal solution. | Optimize for the most common caller — make the default case trivial. |

Constraints are from ../codebase-design/DESIGN-IT-TWICE.md; read it for the brief format and the per-agent output shape (interface, usage example, what hides behind the seam, dependency strategy, trade-offs).

Each agent gets a technical brief with real file paths, the coupling details, and the Ground Truth rows that bear on the design (../reality-gate/SKILL.md). A design argued against imagined constraints is fiction.

## They debate, they do not report

**Three reports side by side are a menu, not a decision.** The agents must exchange positions and attack each other's designs until they converge.

1. Each agent publishes its design.
2. Each reads the other two and states, specifically, where the other design is worse and where it is better than its own.
3. They iterate until a consensus design exists — often a hybrid, and that is a success, not a compromise.
4. The consensus is written up as one design with named dissent: what each agent gave up and why it accepted the loss.

The controller adjudicates **only on deadlock**. Stepping in early replaces three considered positions with one unexamined one — yours.

Consensus reached or adjudicated, the result opens `G-DESIGN`. The human chooses; the debate is the evidence they choose on.

## Judging vocabulary

Compare in the ../codebase-design/SKILL.md vocabulary, not in adjectives.

| Axis | The question |
|---|---|
| **Depth** | How much does the interface hide relative to its size? Thin wrappers over a wide surface lose. |
| **Locality** | When this changes, how many places change with it? Where does change concentrate? |
| **Seam placement** | Is the boundary drawn where the system actually joints, or where the first draft happened to stop? |

"Cleaner", "more elegant", and "more idiomatic" are not axes. If a design wins, say which axis it wins on.

## Two modes

| | **Argued** (F2) | **Measured** (F3) |
|---|---|---|
| Output | Prose designs, debated to consensus | A spike per design, built against a real ephemeral stack |
| Evidence | Reasoning about depth, locality, seams | Started or didn't. Output right or wrong. Latency. |
| Costs | Three agents, one round of debate | Three agents, three ephemeral stacks, three leases |
| Settles | Which design the humans want to own | Which design the system actually tolerates |

**Measured mode exists so an unconventional approach can lose on measurement rather than on rhetoric.** The orthodox design always sounds safer; that is a property of prose, not of the system. Make all three build something and read the numbers.

In measured mode each agent returns, at minimum: did the stack come up; is the output the expected output (the actual body, not the status code — ../practical-testing/SKILL.md); how long did the primary path take. One lease per spike, no shared namespace, `lease-discipline` applies (../../core/lease/SPEC.md).

## Spikes are prototypes

A spike is throwaway code that answers one question. Spike disposal, adapted from ../prototype/SKILL.md's rules, applies without exception:

1. Throwaway from day one and named so a casual reader can see it.
2. One command to run.
3. Committed to a **throwaway branch**, out of main.
4. The verdict — the question and the answer — captured to the ticket, with a pointer to that branch.
5. Main keeps only the validated decision. Not the spike, not three spikes, not "the spike, cleaned up."

A spike promoted to production code is the failure this whole mode exists to prevent: it wins by being already written.

## Escalation

| Condition | Consequence |
|---|---|
| Argued mode produces no consensus and the controller cannot adjudicate on the three axes | Escalate argued → measured. Build the spikes. |
| A design's advantage rests entirely on a claim nobody measured | That claim is `UNVERIFIED`; open `G-FACTS` before choosing. |
| Measured mode produces no separation | The designs are equivalent for this system. Pick the one with the smallest interface and record that as the reason. |

## Red flags

- Three agents whose designs differ in naming and nothing else.
- A "debate" that is three reports and a summary.
- The controller picking a winner before the agents have read each other.
- A comparison written in adjectives instead of depth, locality, and seam placement.
- A spike that acquired tests, a README, and a migration path.
- The unconventional design dismissed before it was built, in a run that was supposed to measure.
- Consensus recorded with no dissent — nobody gave anything up, so nobody was really arguing.
