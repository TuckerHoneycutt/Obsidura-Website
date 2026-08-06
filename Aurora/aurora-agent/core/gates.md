# Gates

Audience: pipeline authors and adapter implementers. Job: the complete inventory of moments a run stops for a human, and the shape of the object it stops with.

A gate is data, not a sentence. Every gate is an object valid against `core/gate.schema.json`, and `ask(gate)` is the only way a pipeline touches a human — so the same gate renders as a terminal question, a web form, or a Slack message without the pipeline knowing which.

## Inventory

| id | Fires when | Shape | Tiers |
|---|---|---|---|
| `G-CLASS` | Every run, before anything else. | choice | all |
| `G-FACTS` | A load-bearing claim could not be measured. | approve | conditional |
| `G-SEAMS` | Before the first test is written. | checklist | F1+ |
| `G-SPEC` | Spec drafted — inline at F1, document at F2/F3. | approve | F1+ |
| `G-DESIGN` | Competing designs have reported. | choice | F2/F3 |
| `G-DECISION` | Each map or grilling decision. Map decisions offer options; a free-form grilling decision uses the `text` shape. | choice | F3, every decision |
| `G-CHECKPOINT` | A checkpoint-task tripwire fired — destructive verb, live resource, shared namespace, or a step about to write outside the run's lease. | approve | all, conditional |
| `G-PLANCONFLICT` | A review finding contradicts plan text. | choice | all, conditional |
| `G-BLOCKED` | Fix-loop breaker tripped on a load-bearing finding, or a write has already landed on a resource without this run's lease label. | text | all, conditional |
| `G-E2E` | Before PR, user-facing work only. | checklist | F1+ |
| `G-DEPLOY` | Change needs human deploy or cleanup steps. | checklist | conditional |

## Rules

1. Blocking means blocking. No adapter auto-answers, defaults, or times out into a decision.
2. `conditional` gates fire at every tier when their trigger fires — the tier dial never suppresses them.
3. One gate per moment. Batching two decisions into one prompt loses the answer to the second.
4. `blocking: true` on every gate above; `blocking: false` is reserved for informational gates no pipeline currently opens.
5. Every `ask` is bracketed by a `gate.opened` and a `gate.closed` journal line, both carrying the gate id.

## Examples

One valid object per shape lives in `core/examples/`: `gate-approve.json`, `gate-choice.json`, `gate-text.json`, `gate-checklist.json`.
