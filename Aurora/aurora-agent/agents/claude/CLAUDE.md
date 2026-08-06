# Aurora — Claude adapter contract

Audience: humans reading the adapter, and any session working inside a checkout of this repo. Job: state what a `/aurora:*` command obliges the agent to do, and how the six verbs bind to Claude Code tools.

**This file is not auto-loaded by the plugin.** Claude Code does not inject a plugin's `CLAUDE.md` at install or session start. Prime-directive injection rides step 1 of every command, which reads `${CLAUDE_PLUGIN_ROOT}/core/prime-directives.md` before anything else. The copy below is the contract in readable form — `core/prime-directives.md` is the source of truth, and `tests/test_soul_prime.py::test_claude_adapter_contains_directives` keeps the three numbered directive lines below identical to it, in order.

## Prime directives

Verbatim from `core/prime-directives.md`. They are never scaled down, in any class or tier.

1. All development and testing happens in an ephemeral worktree and ephemeral environment. Never in prod. No task is too small for this.
2. Prod writes require explicit human consent given in this session. Prod reads are fine. Standing up an ephemeral cluster using prod-resident tooling, when the given task obviously requires it, is fine.
3. About to modify anything outside your worktree or lease: stop and open G-CHECKPOINT.

## On any /aurora command

`/aurora:help` is the one exception to this section: it explains and stops — no manifest, no run id, no journal, no gate but a clarifying question. Steps 1–5 below govern the six pipeline-backed commands.

Paths below are written repo-relative for reading. The command bodies spell the same paths `${CLAUDE_PLUGIN_ROOT}/pipelines/…` so they resolve against the installed plugin root; `.aurora/runs/` alone is relative to the working repo, not the plugin.

1. Read the pipeline manifest the command names (`pipelines/<name>.yaml`). It is the authority on stage order — do not improvise one.
2. Execute its stages in order. For each stage, read `skills/<stage.skill>/SKILL.md` and follow it with that stage's params and notes.
3. Honor every gate the stage lists. `ask` binds to your question tool (`AskUserQuestion` for approve/choice/checklist, a plain prompt for `text`). The gate object is shaped per `core/gate.schema.json`; the inventory is `core/gates.md`. Blocking means blocking — never auto-answer, default, or time out into a decision.
4. Arm the manifest's tripwires. When a condition holds, the consequence has already happened: take the action verbatim, no permission needed to escalate.
5. Append journal lines per `core/journal.schema.json` to `.aurora/runs/<run-id>/journal.jsonl`. `emit` binds to plain file writes (append-only, no daemon, no network). Mint the run id `r-YYYY-MM-DD-<4hex>` at start; bracket every `ask` with `gate.opened` and `gate.closed` lines.

## Verb bindings

| Verb | Bound to |
|---|---|
| `dispatch` | `Task` tool, one call per brief |
| `run` | `Bash` tool |
| `read` | `Read` tool |
| `write` | `Write` / `Edit` tools |
| `ask` | `AskUserQuestion`, plain prompt for `text` gates |
| `emit` | append a line to the run journal with `Write` |

Full contract: `core/verbs.md`.
