# Generic Agent Framework — Design

**Audience:** implementing agents and reviewers of the `feat/skills-framework` branch. Job: define exactly what this repo becomes, so any task brief can be checked against it.

**Goal:** convert `aurora-agent` from a Hermes-only profile distribution into a generic agent configuration repo: a harness-agnostic skills framework at top level, per-harness adapters under `agents/`, Hermes remaining the root profile.

## Measured facts (do not re-litigate; re-measure if suspicious)

- `hermes profile install <git-url>` git-clones the repo and requires `distribution.yaml` **at the repo root**. No subdirectory support. Provisioning (`dev-administration`) runs `hermes profile install <aurora-agent-url> --name aurora --force`.
- `distribution_owned` may list any top-level path, including `skills/` — listed paths are replaced from git on `hermes profile update`; user-owned paths are never touched.
- `config.yaml` supports `${ENV_VAR}` interpolation; plugins vendored into a distribution must have `.git` removed.
- Sources vendored from: `.sources/superpowers-6.2.0/` (obra/superpowers v6.2.0, MIT) and `.sources/mattpocock-skills/` (mattpocock/skills @ 2ab9580, MIT). `.sources/` is gitignored working material, never committed.
- In-house source texts: `.sources/agent-implementation-practices.md`, `.sources/sdd-meta-process.md`.

## Layout

```
aurora-agent/
├─ distribution.yaml        # hermes manifest — MUST stay at root; distribution_owned += skills/, pipelines/, core/
├─ config.yaml  SOUL.md  plugins/ponytail/   # hermes adapter; content unchanged except SOUL.md prime section
├─ README.md                # what this repo is; why hermes lives at root; per-harness quickstart
├─ skills/<name>/SKILL.md   # 29 harness-agnostic skills (+ support files)
├─ pipelines/               # schema.yaml + 8 manifests
├─ core/                    # prime-directives.md, verbs.md, gate/journal schemas, guard/ + lease/ specs & stubs
├─ agents/
│  ├─ claude/               # working Claude Code plugin
│  └─ codex/README.md       # skeleton
├─ tests/                   # pytest conformance suite
└─ docs/
   ├─ framework.md          # terse rationale (routing, tiers, gates, verbs, rulings)
   ├─ omissions.md          # every upstream skill NOT vendored + reason
   └─ superpowers/specs/    # this file
```

## core/prime-directives.md (top tier — above the skill system)

≤ 20 lines. Injected at session level by every adapter; invariant #0 of every pipeline; the routing skill points to it first.

1. All development and testing happens in an ephemeral worktree + ephemeral environment. Never in prod. No task is too small for this.
2. Prod writes require explicit human consent given this session. Prod reads are fine. Standing up an ephemeral cluster using prod-resident tooling, when the given task obviously requires it, is fine.
3. About to modify anything outside your worktree or lease → stop and open G-CHECKPOINT.

## Skills inventory

### Vendored from superpowers 6.2.0 (10)

writing-plans, subagent-driven-development (incl. `scripts/`, `*-prompt.md`), executing-plans, verification-before-completion, requesting-code-review (incl. code-reviewer.md), receiving-code-review, dispatching-parallel-agents, using-git-worktrees, finishing-a-development-branch, writing-skills.

### Vendored from mattpocock @ 2ab9580 (9)

grilling, domain-modeling, wayfinder, codebase-design (incl. DEEPENING.md, DESIGN-IT-TWICE.md), improve-codebase-architecture (incl. HTML-REPORT.md), to-spec (tracker refs rewritten: publish to `docs/superpowers/specs/` when no tracker is configured — F2/F3 pipelines need its spec template), to-tickets, diagnosing-bugs (plus, folded in as references: superpowers systematic-debugging's `root-cause-tracing.md` and `defense-in-depth.md`), prototype (incl. LOGIC.md, UI.md).

### Written new (10)

| Skill | Content source |
|---|---|
| `routing` | Classifier: 4 questions → class (chore/fix/probe/incident/feature); tier dial F0–F3 (decision-ownership axis); tripwire table; points to prime-directives first. Replaces superpowers using-superpowers as entry point. |
| `test-driven-development` | Merge: superpowers red-green mechanics + mattpocock pre-agreed seams & anti-patterns + output-based assertions (capture real output, never status codes alone) + mutation-gate hook. |
| `practical-testing` | THE emphasized discipline — see below. |
| `vacuity-review` | The 11 test-vacuity shapes from agent-implementation-practices.md Part 2, as a closed reviewer taxonomy with catch-by procedures. |
| `mutation-proof` | Named-mutation procedure: run mutation, record transcript, revert. A named mutation staying green = failed spec review. Mutations disabling guards run against stubs only. |
| `reality-gate` | Measured-or-cited rule; Ground Truth block; `UNVERIFIED` marks block specs/plans/briefs. From sdd-meta-process.md §1 + practices Part 5.3. |
| `competing-designs` | 3 roles (orthodox / unconventional / theoretically-optimal) × constraint framings; debate to consensus; argued vs measured (spike) modes; judged on depth/locality/seam vocabulary. |
| `doc-budget` | Docs scale with the interface, never with implementation effort. Per-sentence deletion test; audience+job line opens every doc; explanations get one line unless recording a paid-for failure; long docs must be long in tables/imperatives/contracts, never narrative; route-don't-restate; ledgers vs guides never merge. No numeric line cap. |
| `live-system-etiquette` | practices Part 6 as imperatives: fingerprint before/after phases; poll unambiguous endpoints during; disclose every write; copy never move; never route around a refusal; stop cleanly when the human leaves. |
| `destructive-op-awareness` | Thin skill pointing at core/guard SPEC + prime-directives; positive-guard principles from practices Part 3 (agent-readable summary; the enforcement lives in core/guard when implemented). |

Note: prime-directives lives in `core/`, not `skills/` — the 10th new *skill* is destructive-op-awareness.

### practical-testing (write this one first among new skills)

Claim: **the best test is using the thing you built.** Ephemeral environments have no consequences — so exercise the real write path: invoke the tool, start the container, run the process, hit the service; capture the transcript. Unit tests mirror the implementer's assumptions; execution doesn't. TDD is necessary, not sufficient.

Enforcement (not advisory):
- Implementer report contract gains a mandatory **Practical verification** section: commands actually run against the built artifact in the ephemeral env + captured output. Missing → report is not DONE.
- Task reviewers independently **re-run the primary practical path** before any verdict. Reading the diff alone is not review.
- Invariant in all 8 pipelines, same tier as the mutation gate.
- Orchestrator dispatch briefs must name the practical path to exercise.

### Vendoring rules

- Frontmatter of every vendored SKILL.md gains `origin: obra/superpowers@6.2.0` or `origin: mattpocock/skills@2ab9580` and `license: MIT`. Content otherwise byte-faithful, except:
  - Cross-references rewritten to this repo's paths (e.g. `superpowers:writing-plans` → `skills/writing-plans`).
  - References to omitted skills rewritten to their replacements (brainstorming → grilling + routing; sp TDD → merged TDD).
  - `subagent-driven-development/implementer-prompt.md` and `task-reviewer-prompt.md`: amended per practical-testing above; frontmatter/note marks `vendored-with-amendment`, amendment described in one line.
- LICENSE-THIRD-PARTY.md at repo root: both upstream MIT notices.

### Omitted (documented in docs/omissions.md with these reasons)

sp brainstorming (→ grilling + routing), sp test-driven-development (→ merged), sp using-superpowers (→ routing), sp systematic-debugging as standalone (best references folded into diagnosing-bugs), mp implement (→ pipeline manifests), mp tdd (→ merged), mp code-review (→ folded into reviewer axes of the loop), mp ask-matt / triage / grill-with-docs / setup-matt-pocock-skills / wayfinder's tracker-setup dependency noted (wayfinder vendored but its `/setup-matt-pocock-skills` reference rewritten to a note), mp research (superseded by reality-gate + probe pipeline), mp resolving-merge-conflicts (fine skill, defer — not framework-critical), mp handoff/teach/grill-me/writing-great-skills (productivity set out of scope; grilling itself is vendored), mp prototype deprecated/* (deprecated upstream).

## pipelines/

`schema.yaml` defines the manifest shape; 8 manifests: `chore.yaml`, `fix.yaml`, `probe.yaml`, `incident.yaml`, `f0.yaml`, `f1.yaml`, `f2.yaml`, `f3.yaml`.

Each manifest declares:
- `class`, `tier` (features only), `entry` (classification conditions from routing)
- `invariants`: **always** `[prime-directives, verification-law, output-based-assertions, mutation-proof, practical-testing, lease-discipline(stub)]` — identical across all 8; cost scales on deliberation, never safety
- `stages`: ordered list, each `{skill: <name>, params, gates: [G-*], notes}`
- `tripwires`: from the routing table (fix-loop round 3 → escalate tier; no consensus → argued→measured; chore exceeds blast radius → F1; unleased write → halt + G-BLOCKED; F3 no-fog → F2; UNVERIFIED load-bearing claim → ≥F1; destructive verb / no lease label → checkpoint task)
- `journal`: agents append JSONL lines to `.aurora/runs/<run-id>/journal.jsonl` per `core/journal.schema.json` (convention, no machinery)

Tier axis (decision ownership): F0 agent decides/reports; F1 agent proposes ≤5 questions ~2min + inline spec ≤10 lines, human ratifies; F2 human owns design (grilling exhausted, competing-designs argued, spec doc, G-DESIGN); F3 human ratifies every decision (wayfinder map, competing-designs measured via spikes, mutation table named per task). Human gates: F0=1, F1=3, F2=6, F3=9+.

## core/

- `verbs.md` — six-verb adapter contract: `dispatch(brief)`, `run(cmd)`, `read(path)`, `write(path, body)`, `ask(gate)`, `emit(event)`. What each adapter must bind them to.
- `gate.schema.json` + `gates.md` — gate object (id, run, stage, shape: approve|choice|text|checklist, blocking, prompt, context, items, status, answer) + the G-* inventory: G-CLASS, G-FACTS, G-SEAMS, G-SPEC, G-DESIGN, G-DECISION, G-CHECKPOINT, G-PLANCONFLICT, G-BLOCKED, G-E2E, G-DEPLOY (fires-when / shape / tiers). One valid example per shape in `core/examples/`.
- `journal.schema.json` + `journal.md` — event line shape + vocabulary: run.started/finished, stage.entered/exited, task.dispatched/reported, review.finding, mutation.result, gate.opened/closed, lease.acquired/released, escalation.fired, guard.refused. Example lines in `core/examples/`.
- `guard/SPEC.md` + `guard/check.py` (stub) — argv contract `check.py <verb> <target> [--labels k=v...]`; positive lease-label predicate (`target labels ⊇ {lease: <session>}`); destructive-verb whitelist (refuse unlisted destructive spellings by default); recovery verbs (`up`, restore) always pass; single override env `AURORA_GUARD_OVERRIDE=1` (visible in shell history); exit codes 0 allow / 3 refuse / 4 unknown-verb. Arg-parse layer real and tested; predicate body raises `NotImplementedError`; `status: stub` in SPEC frontmatter. Guard tests run against stubs, never live tools.
- `lease/SPEC.md` + `lease/lease.py` (stub) — lease id `aurora-eph-<8hex>`; acquire/release contract; isomorphism `1 ticket = 1 brief = 1 worktree = 1 lease = 1 review package = 1 ledger line`; release is a task-completion gate; aurora `compose.branch.yml` / `--devs` named as the integration point, not built.

## agents/claude/ (working plugin)

- `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` (installable from this Forgejo repo; plugin name `aurora`).
- `commands/`: `route.md`, `chore.md`, `fix.md`, `probe.md`, `incident.md`, `feature.md` (feature takes tier arg, default asks G-CLASS style). Each command: inject prime-directives, load its pipeline manifest, resolve referenced skills within the installed plugin tree, execute stages, honor gates via AskUserQuestion-or-equivalent, append journal lines.
- Plugin-level `CLAUDE.md` carrying prime-directives injection.
- 1:1 command↔manifest mapping is conformance-tested (route ↔ routing skill; other five ↔ five class manifests; feature covers f0–f3 via tier arg).

## agents/codex/README.md

Skeleton: the six verbs, what a Codex binding would map them to, pointer to pipelines/. No implementation.

## Hermes integration

- `distribution.yaml`: version → 0.2.0; description updated; `distribution_owned` += `skills/`, `pipelines/`, `core/`.
- `SOUL.md`: append a marked `## Prime directives` section mirroring core/prime-directives.md (hermes has no plugin-level injection; SOUL is its session-level surface). Rest unchanged.
- `config.yaml`, `plugins/ponytail/`: unchanged.

## docs/

- `framework.md` — terse: the routing table, tier dial, tripwire table, gate inventory, six verbs, the three conflict rulings (paths-in-briefs-not-tickets; refactor scope; continuous-vs-checkpoint), the invariants list. Tables and imperatives only.
- `omissions.md` — table: omitted skill / reason / replacement.
- `README.md` (root) — rewritten: what this repo is, layout map with one line per dir, why hermes is at root (measured constraint), quickstart per harness (hermes install cmd; claude plugin install; generic = read pipelines/ + skills/), pointer to framework.md.
- All docs obey doc-budget: audience+job opening line, deletion test, tables over narrative.

## tests/ (pytest)

Every test docstring names its mutation: what to break and the expected redden.

1. `test_skills_conformance.py` — every `skills/*/SKILL.md` has frontmatter with name+description; names unique; vendored ones carry origin+license; no skill named like an omitted one.
2. `test_pipelines.py` — schema.yaml valid; 8 manifests parse + schema-validate; referenced skills exist in `skills/`; referenced gates exist in gates inventory; all 8 share the identical invariants list including prime-directives and practical-testing; tripwires present per class.
3. `test_core_schemas.py` — gate/journal schemas are valid JSON Schema; every example in `core/examples/` validates; every G-* in gates.md has a schema-valid example shape.
4. `test_distribution.py` — distribution.yaml at root, parses, version 0.2.0, `distribution_owned` includes skills/, pipelines/, core/, and every listed path exists; env_requires entries have name+description.
5. `test_claude_plugin.py` — plugin.json/marketplace.json parse; commands ↔ manifests 1:1; every command references prime-directives.
6. `test_docs.py` — omissions.md lists every upstream skill absent from `skills/` (computed against `.sources/` when present, else against a committed manifest `docs/vendor-manifest.yaml`); framework.md exists and contains the routing + gate tables; README quickstart names all three consumption paths.
7. `test_stubs.py` — guard/lease stubs: arg-parse contracts hold (exit codes for bad argv), predicate raises NotImplementedError, SPEC frontmatter says stub.
8. `test_soul_prime.py` — SOUL.md contains the marked prime-directives section and it matches core/prime-directives.md content.

`docs/vendor-manifest.yaml`: committed list of vendored/omitted upstream skills + versions (so test 6 runs without `.sources/`).

## Out of scope

Guard/lease implementations (stubs only); F2/F3 spike execution machinery; codex adapter beyond README; control plane; any change to the `aurora` repo; live `hermes profile install` integration test (deferred); resolving-merge-conflicts and mp productivity skills.

## Acceptance

- `pytest` green from repo root (with `.sources/` present).
- Practical verification (per practical-testing, applied to this deliverable): fresh-clone simulation — copy repo to temp dir without `.sources/`, pytest still green (vendor-manifest path); render/parse every manifest and command; grep-proof no `superpowers:` or mattpocock-tracker references remain in vendored text.
- PR `feat/skills-framework` → main on Forgejo with summary + this spec linked; human merges.
