# Journal

Audience: pipeline authors and adapter implementers. Job: what a run records, where it lands, and the exact event vocabulary.

One file per run at `.aurora/runs/<run-id>/journal.jsonl`, one JSON object per line, append-only. File-backed: no daemon, no service, no network. Written only through `emit(event)`; every line validates against `core/journal.schema.json`.

## Line fields

| Field | Required | Meaning |
|---|---|---|
| `ts` | yes | ISO 8601 UTC instant the event happened. |
| `run` | yes | Run id, e.g. `r-2026-08-02-ex01`. Same for every line in the file. |
| `event` | yes | One of the vocabulary below. Closed enum. |
| `actor` | yes | Who did it: `orchestrator`, `human`, `guard`, `agent:<task-id>`. |
| `class` | no | `chore` / `fix` / `probe` / `incident` / `feature`. |
| `tier` | no | 0–3. |
| `stage` | no | Pipeline stage name. |
| `gate` | no | Gate id, required in practice on `gate.*` events. |
| `detail` | no | Free-form object. Everything event-specific goes here. |

Unknown top-level keys are allowed (`additionalProperties: true`) so adapters can add their own; readers ignore what they do not know.

## Event vocabulary

| Event | Emitted when |
|---|---|
| `run.started` | Run begins, after classification is proposed. |
| `run.finished` | Run ends, delivered or abandoned. |
| `stage.entered` | A pipeline stage begins. |
| `stage.exited` | A pipeline stage completes. |
| `task.dispatched` | `dispatch(brief)` called. |
| `task.reported` | A dispatched task returned its report. |
| `review.finding` | A reviewer raised a finding. |
| `mutation.result` | A mutation run completed, with killed/survived counts. |
| `gate.opened` | `ask(gate)` called, before the human sees it. |
| `gate.closed` | The human answered, or the gate expired. |
| `lease.acquired` | A lease on a resource was taken. |
| `lease.released` | A lease was returned. |
| `escalation.fired` | A tripwire escalated the run's tier or class. |
| `guard.refused` | The guard refused a verb, with exit code 3. |

## Rules

1. Emit before and after anything a human would ask about later. The journal is the run's only durable record.
2. An invalid event is dropped and reported, never written — one malformed line poisons the file for every reader.
3. Never rewrite or delete a line. Corrections are new lines.
4. `gate.opened` and `gate.closed` always come in pairs carrying the same gate id.

## Example

`core/examples/journal-lines.jsonl` — one fictional `fix` run end to end.
