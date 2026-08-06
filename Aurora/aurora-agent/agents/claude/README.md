# Claude adapter

Audience: someone installing Aurora into Claude Code. Job: install the plugin, know what the seven commands do, and know how paths inside them resolve.

## Install

This repository is private: installing needs tailnet access to `superserver` and a Forgejo credential with read access to it. Configure that credential in your git config — never in this file.

1. `/plugin marketplace add https://superserver.tailc67a98.ts.net/git/supergoodname77/aurora-agent.git`
2. `/plugin install aurora@aurora-agent`
3. Start a fresh session. The commands appear as `/aurora:*`; each one reads the prime directives as its first step.

## Commands

| Command | Does |
|---|---|
| `/aurora:help [what you want to do]` | Explains the framework, or names the class and tier a described piece of work takes and why. Explains and stops — it never opens a pipeline. |
| `/aurora:route <request>` | Classifies via `skills/routing/SKILL.md`, sets the tier, enters the matching pipeline. Start here when the class is not obvious. |
| `/aurora:chore <task>` | `pipelines/chore.yaml` — no observable behaviour change, blast radius declared up front. |
| `/aurora:fix <report>` | `pipelines/fix.yaml` — something is already wrong in dev or test. |
| `/aurora:probe <question>` | `pipelines/probe.yaml` — deliverable is a fact or a decision, not a diff. |
| `/aurora:incident <report>` | `pipelines/incident.yaml` — already wrong, and live. |
| `/aurora:feature [f0-f3] <request>` | `pipelines/f0.yaml` … `pipelines/f3.yaml` — tier from the argument, or asked as a blocking choice. |

Every command reads `core/prime-directives.md` first. The six pipeline-backed commands then open gates per `core/gate.schema.json` and journal per `core/journal.schema.json` into `.aurora/runs/<run-id>/journal.jsonl`; `/aurora:help` runs no pipeline, so it mints no run id and journals nothing.

## Path resolution

Four mechanisms, in the order they apply:

1. **`.claude-plugin/marketplace.json` sits at the repo root.** Claude Code requires it there, and the directory containing `.claude-plugin/` is the marketplace root against which `source` resolves.
2. **`source: "./"` therefore makes the plugin root the repo root** — the directory holding `pipelines/`, `skills/`, and `core/`, one level above `agents/claude/`.
3. **`plugin.json` sets `"commands": ["./agents/claude/commands/"]`.** A custom `commands` path replaces the default `commands/` scan (it must start with `./`), so the seven command files register from where they live even though the plugin root is the repo root. `skills/` is different — it is always scanned in addition to any override, so the 30 skills at the root register without an entry.
4. **Command bodies spell every content path `${CLAUDE_PLUGIN_ROOT}/pipelines/chore.yaml`** and so on. The placeholder expands to the installed plugin directory, so reads do not depend on the session's cwd. `.aurora/runs/<run-id>/journal.jsonl` is deliberately *not* prefixed: the journal belongs to the repo being worked on. The reference documents placeholder expansion for skill and agent content and does not name command bodies either way, so each command opens with a one-line fallback telling the agent how to resolve the directory itself if the literal reaches it unexpanded.

### Check at first live install

- [ ] `/plugin install aurora@aurora-agent`, then `/aurora:chore` in a scratch repo — the session reads `pipelines/chore.yaml` from the plugin directory, not the scratch repo.
- [ ] All seven `/aurora:*` commands appear in the slash-command list.
- [ ] `${CLAUDE_PLUGIN_ROOT}` arrives expanded in a command body (undocumented for commands). If it arrives literal, the fallback line at the top of each command should carry the run — if that proves unreliable, hard-code the resolution differently.
- [ ] The 30 Aurora skills appear; `plugins/ponytail/` skills do not leak in as duplicates.
- [ ] `/aurora:help <some real request>` recommends a class and tier and **stops** — no worktree, no run id, no journal, no pipeline. Mode B's non-execution is prompt-enforced only; no test can catch a violation, so spot-check it on first use.
- [ ] **Known risk:** the plugin root's `agents/` directory is auto-scanned as subagent definitions. `agents/claude/CLAUDE.md`, `agents/claude/README.md`, and `agents/codex/README.md` carry no agent frontmatter, so they should be ignored — but the docs do not state what happens to frontmatter-less files there, and the documented way to override the scan (an `agents` key) has no documented "scan nothing" value. Confirm no junk subagents are registered; if any appear, either point `"agents"` at a real, empty directory or move the adapter docs out of `agents/`.
