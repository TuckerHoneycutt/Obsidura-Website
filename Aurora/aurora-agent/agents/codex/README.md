# Codex adapter — skeleton

Audience: whoever implements the Codex binding. Job: name what each of the six verbs would bind to, and record that nothing here runs yet.

**Status: not implemented.** No manifest, no commands, no tests. This file is the shape of the work, not the work.

## Verb bindings

The contract for all six is `core/verbs.md`; a pipeline calls only these. Bind them and the existing pipelines run unchanged.

| Verb | Codex binding |
|---|---|
| `dispatch(brief) -> report` | A nested `codex exec` invocation with the brief on stdin, fresh context, final message captured as the report. |
| `run(cmd) -> {output, exit_code}` | The sandboxed shell tool, combined stdout+stderr, exit code always returned — never raise on nonzero. Guard predicate wraps the call. |
| `read(path) -> body` | The file-read tool, or `cat` through the shell tool. Ungated. |
| `write(path, body)` | The apply-patch tool for edits, shell redirect for new files. Guard predicate wraps the call; writes outside the lease are a `G-CHECKPOINT` trigger. |
| `ask(gate) -> answered gate` | No native structured-question tool: render the gate object per shape as plain text to the user and block on the reply. Never auto-answer. |
| `emit(event)` | Append one schema-valid line to `.aurora/runs/<run-id>/journal.jsonl` via the write binding. |

## What it would consume

- `pipelines/` — the eight manifests (chore, fix, probe, incident, f0–f3) plus `pipelines/schema.yaml`. Stage order comes from the manifest.
- `skills/` — 30 harness-agnostic skills; each stage names one, read as `skills/<name>/SKILL.md`.
- `core/prime-directives.md` — injected at session level, the Codex equivalent of `AGENTS.md`.
- `core/gates.md`, `core/gate.schema.json`, `core/journal.schema.json` — gate inventory and object shapes.

Platform tool-name mapping notes already exist at `skills/routing/references/codex-tools.md`.
