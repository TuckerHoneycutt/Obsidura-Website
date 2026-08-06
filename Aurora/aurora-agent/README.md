# aurora-agent

Audience: someone installing or contributing to Aurora. Job: say what is here, where it lives, and how to consume it from each harness.

Generic agent configuration: a harness-agnostic skills framework — 30 skills, 8 pipeline manifests, six adapter verbs, eleven gates — plus one thin adapter per harness.
The Hermes profile lives at the repo root; Claude Code consumes the same tree as a plugin; any other agent reads the files directly.

## How work flows

Every request is classified into one of five classes; features additionally pick a tier. The class picks a pipeline manifest; the tier picks how much of the decision-making you keep. Depth: `docs/guide.md`.

| Class | When you reach for it |
|---|---|
| `chore` | Nothing observable changes, and you can name the blast radius up front. |
| `fix` | Something is already wrong, in dev or test. |
| `probe` | The deliverable is a fact or a decision, not a diff. |
| `incident` | Something is already wrong, and it is live. |
| `feature` | Everything else — then pick a tier. |

| Tier | Decision ownership | Human gates |
|---|---|---|
| **F0** trivial | Agent decides, reports after. | 1 |
| **F1** light | Agent proposes, human ratifies. | 4 |
| **F2** standard | Human owns the design, agent owns the implementation. | 7 |
| **F3** load-bearing | Human ratifies every decision; agent gathers facts only. | 10+ |

**What never scales down:** six invariants — `prime-directives`, `verification-law`, `output-based-assertions`, `mutation-proof`, `practical-testing`, `lease-discipline` — run identically in every class and at every tier. Cost scales on deliberation, never on safety.

## Layout

| Path | What |
|---|---|
| `skills/` | 30 skills, one `SKILL.md` per directory. Start at `skills/routing/`. |
| `pipelines/` | 8 stage manifests (`chore`, `fix`, `probe`, `incident`, `f0`–`f3`) + `schema.yaml`. Data, not prose. |
| `core/` | Harness-agnostic contracts: prime directives, six verbs, gate + journal schemas, guard and lease specs. |
| `agents/` | Per-harness adapters: `agents/claude/` (working plugin, seven commands), `agents/codex/` (skeleton). |
| `.claude-plugin/` | `plugin.json` + `marketplace.json`. Claude Code requires them at the repo root, which makes the plugin root the repo root. |
| `docs/` | `guide.md` (the tour, for humans), `framework.md` (contributor reference), `omissions.md` (upstream skills not vendored), `vendor-manifest.yaml`, the design spec. |
| `plugins/` | Third-party plugin trees consumed as-is (`ponytail`). Not part of the framework. |
| `tests/` | pytest conformance suite over the whole tree. `.venv/bin/pytest -q`. |
| `SOUL.md`, `config.yaml`, `distribution.yaml` | Hermes profile: persona, harness config, distribution manifest. |

## Why the Hermes profile is at the root

`hermes profile install <git-url>` reads `distribution.yaml` from the repository root; there is no subdirectory form of the command.
So the profile files sit at the root and the framework lives in subdirectories, rather than the reverse.

## Quickstart

This repository is private: both install paths need tailnet access to `superserver` and a Forgejo credential with read access to it. Configure that credential in your git/harness config — never in this file.

**Hermes**

```
hermes profile install https://superserver.tailc67a98.ts.net/git/supergoodname77/aurora-agent.git --name aurora
```

Set the three env vars `distribution.yaml` marks required before first run: `OPENROUTER_API_KEY`, `FORGEJO_URL`, `MCP_FORGEJO_API_KEY`.

**Claude Code**

1. `/plugin marketplace add https://superserver.tailc67a98.ts.net/git/supergoodname77/aurora-agent.git`
2. `/plugin install aurora@aurora-agent`
3. Start a fresh session. The commands appear as `/aurora:*`. Details: `agents/claude/README.md`.

## Getting started

What to do once it is installed.

**Claude Code** — seven commands, all prefixed `/aurora:`:

| Command | Does |
|---|---|
| `/aurora:help [what you want to do]` | Tour, or which-path advice. Explains and stops — never opens a pipeline. |
| `/aurora:route <request>` | Classifies, then enters the matching pipeline. |
| `/aurora:chore <task>` | `pipelines/chore.yaml` |
| `/aurora:fix <report>` | `pipelines/fix.yaml` |
| `/aurora:probe <question>` | `pipelines/probe.yaml` |
| `/aurora:incident <report>` | `pipelines/incident.yaml` |
| `/aurora:feature [f0-f3] <request>` | `pipelines/f0.yaml` … `pipelines/f3.yaml` |

Start with `/aurora:help`, in either mode:

```
/aurora:help                              # the tour: classes, tiers, gate costs, tripwires
/aurora:help I want to add SSO login      # which path: "feature at F1 — here is why, here is what it costs"
```

Mode B names the command to run next — for that request, `/aurora:feature f1 add SSO login`.

**Hermes** — `skills/`, `pipelines/`, and `core/` arrive in `$HERMES_HOME` via `hermes profile update`:

| Step | Do |
|---|---|
| 1 | `hermes profile update` — pulls the tree into `$HERMES_HOME`. |
| 2 | Read `skills/routing/SKILL.md`. Classify, state the `G-CLASS` line. |
| 3 | Follow the matching `pipelines/<class>.yaml`, stage by stage. |

**Any other agent** — read the files directly:

| Step | Do |
|---|---|
| 1 | Read `core/prime-directives.md` and comply with it for the whole session. |
| 2 | Read `skills/routing/SKILL.md`. Classify the request, state the `G-CLASS` line. |
| 3 | Follow the matching `pipelines/<class>.yaml`, stage by stage. |

## Further

- `docs/guide.md` — the tour: classes, tiers, attention cost, tripwires, one worked run.
- `docs/framework.md` — classification, tier dial, tripwires, gates, verbs, invariants.
- `docs/omissions.md` — which upstream skills are absent and what replaced them.
- `docs/superpowers/specs/2026-08-02-generic-agent-framework-design.md` — the design spec.
