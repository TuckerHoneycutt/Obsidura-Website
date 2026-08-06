# Verbs

Audience: anyone writing an adapter or a pipeline stage. Job: the six verbs every adapter must bind, so pipelines are written once and run anywhere.

Pipelines call only these six. A pipeline that reaches for a host-specific tool is a bug in the pipeline, not a missing verb.

## `dispatch(brief) -> report`

Runs `brief` as a subordinate agent with a fresh context and returns its final report as text. The caller never sees the subordinate's intermediate work, so the brief carries every path, constraint, and acceptance check the subordinate needs — briefs contain paths, not ticket references. Dispatch is the only way a stage gets parallelism; independent tasks go out in one batch. The report is text for a human and for the caller's next step, not a machine-parsed structure.

| Binding | Bound to |
|---|---|
| Claude | `Task` tool (subagent), one call per brief |
| Hermes | subordinate session spawn, brief as the opening message |
| generic shell | a fresh CLI invocation of the agent with the brief on stdin |

## `run(cmd) -> {output, exit_code}`

Executes `cmd` in the run's worktree and returns combined stdout+stderr with the exit code. Both fields are always returned; an adapter that raises on nonzero exit is non-conforming, because pipelines assert on output text and need the failing output to do it. Every `cmd` passes the guard before execution (see `core/guard/SPEC.md`); a refusal surfaces as a nonzero exit and a `guard.refused` journal line, never as a silent skip. No interactive commands — a verb that needs a human uses `ask`.

| Binding | Bound to |
|---|---|
| Claude | `Bash` tool, guard invoked from a PreToolUse hook |
| Hermes | shell executor, guard invoked inline before exec |
| generic shell | `subprocess.run(..., capture_output=True)` behind a guard wrapper |

## `read(path) -> body`

Returns the full contents of `path` as text. Paths are relative to the run's worktree root unless absolute. Missing files raise; pipelines that tolerate absence check first rather than catching. Reads are never gated — reading prod is fine, per prime directive 2.

| Binding | Bound to |
|---|---|
| Claude | `Read` tool |
| Hermes | filesystem read |
| generic shell | `Path(path).read_text()` |

## `write(path, body)`

Replaces the contents of `path` with `body`, creating parent directories as needed. Writes outside the worktree or the run's lease are a G-CHECKPOINT trigger, not a permission the adapter grants itself. Returns nothing — a pipeline that wants to confirm the write reads it back or asserts on a test.

| Binding | Bound to |
|---|---|
| Claude | `Write` / `Edit` tools, guard invoked from a PreToolUse hook |
| Hermes | filesystem write behind the same guard predicate |
| generic shell | `Path(path).write_text(body)` behind a guard wrapper |

## `ask(gate) -> answered gate`

Takes a gate object valid against `core/gate.schema.json`, presents it to a human, and returns the same object with `status: "answered"` and `answer` filled in. Blocking: the pipeline stops until a human answers, and no adapter may auto-answer, default, or time out into a decision. The verb is renderer-agnostic — a terminal question, a web form, and a Slack message are all valid renderers of one gate object, which is why a gate is data and not a sentence. `ask` is the only way a pipeline touches a human; every call is bracketed by `gate.opened` and `gate.closed` journal lines.

| Binding | Bound to |
|---|---|
| Claude | `AskUserQuestion` (approve/choice/checklist), plain prompt for `text` |
| Hermes | operator prompt channel, gate rendered per shape |
| generic shell | interactive stdin prompt rendered from the gate object |

## `emit(event)`

Appends one schema-valid line (`core/journal.schema.json`) to `.aurora/runs/<run-id>/journal.jsonl`. File-backed and append-only: no daemon, no service, no network. The journal is the run's only durable record, so stages emit before and after anything a human would ask about later. An invalid event is dropped and reported, never written — a malformed line poisons the whole file for every reader.

| Binding | Bound to |
|---|---|
| Claude | post-tool hook appending to the run journal |
| Hermes | journal writer bound to the session's run id |
| generic shell | `open(path, "a")` + `json.dumps(event)` + newline |
