# Omissions

Audience: anyone looking for an upstream skill that is not in `../skills/`. Job: say why it is absent and where its job went.

Vendored/omitted lists are machine-readable in `vendor-manifest.yaml`. Upstreams: `obra/superpowers@6.2.0` (sp), `mattpocock/skills@2ab9580` (mp). Both MIT — notices in `../LICENSE-THIRD-PARTY.md`.

| Omitted skill | Upstream | Reason | Replacement |
|---|---|---|---|
| `brainstorming` | sp | Its two jobs split cleanly: interrogating the idea, and deciding how much ceremony the work gets. | `../skills/grilling/` + `../skills/routing/` |
| `test-driven-development` | sp | Merged with the mp skill into one derivative rather than shipping two competing red-green disciplines. | `../skills/test-driven-development/` |
| `using-superpowers` | sp | Skill-discovery preamble; routing already owns "read this before anything else". | `../skills/routing/` — its two reference files (`codex-tools.md`, `gemini-tools.md`) are vendored into `../skills/routing/references/` |
| `systematic-debugging` | sp | Standalone loop overlapped the mp debugging skill; the parts worth keeping are references, not a skill. | Folded into `../skills/diagnosing-bugs/references/` |
| `tdd` | mp | Merged with the sp skill into one derivative. | `../skills/test-driven-development/` |
| `implement` | mp | An implementation loop is a pipeline stage order, not a skill — it belongs in data the adapters read. | `../pipelines/*.yaml` |
| `code-review` | mp | Review is not a single act here; it is axes applied at named stages of the loop. | Reviewer axes (standards / spec / vacuity) in `../pipelines/f1.yaml`–`f3.yaml`, `../skills/requesting-code-review/`, `../skills/vacuity-review/` |
| `research` | mp | Superseded: fact-gathering is gated on measurement, and a fact-shaped deliverable is its own class. | `../skills/reality-gate/` + `../pipelines/probe.yaml` |
| `resolving-merge-conflicts` | mp | Good skill, not framework-critical. Deferred, not rejected. | None — revisit when merge volume justifies it |
| `setup-matt-pocock-skills` | mp | Tracker-coupled installer for the upstream toolchain; nothing to install here. | None — `../skills/wayfinder/`'s reference to it is rewritten to a note |
| `triage` | mp | Tracker-coupled: assumes the upstream issue tracker's shape. | `../skills/routing/` classification |
| `ask-matt` | mp | Tracker-coupled and person-coupled to the upstream author. | The skill: none. Its discovery *function* — "what is this and which path do I take" — is `../skills/framework-guide/` and `/aurora:help`. |
| `grill-me` | mp | Productivity set, out of scope. The interrogation discipline itself is vendored. | `../skills/grilling/` |
| `grill-with-docs` | mp | Productivity set, out of scope. | `../skills/grilling/` |
| `handoff` | mp | Productivity set, out of scope. | None |
| `teach` | mp | Productivity set, out of scope. | None |
| `writing-great-skills` | mp | Productivity set, out of scope; overlapped the sp skill that is vendored. | `../skills/writing-skills/` |

mp `deprecated/`, `in-progress/`, `misc/`, and `personal/` buckets are out of scope entirely and are not enumerated above.
