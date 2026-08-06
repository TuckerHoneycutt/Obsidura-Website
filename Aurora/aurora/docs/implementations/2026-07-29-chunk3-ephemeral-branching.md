# Chunk 3 — Ephemeral branching: what was built

One command mints a complete, isolated copy of the stack from a git worktree —
its own Compose project, its own tailnet identity, its own seeded state — while
production keeps serving. One command destroys it.

Companion documents: `docs/testing/2026-07-29-chunk3-ephemeral-branching.md`
(what is proven and what is not), `docs/issues/chunk3-spec-deltas.md` (every
place reality disagrees with the spec or the plan), and
`docs/post-implementation-steps.md` (the four things a human must do).

The full task-by-task record, including every mutation table, is
`.superpowers/sdd/2026-07-29-chunk3-ephemeral-branching/progress.md`.

---

## The shape of it

The divergence between production and a branch is exactly **three artifacts**:

1. `compose.branch.yml` — **generated and committed**. The `!reset` / `!override`
   overlay plus the Tailscale sidecar.
2. a **rendered** branch `.env`.
3. **seeded** state.

Everything else — `compose.yml`, `Caddyfile`, `compose.agents.yml`, every
service definition — is byte-identical between production and a branch. That is
the property that makes a branch a test *of* production rather than a test of a
fiction, and it is why the overlay is generated from the resolved config rather
than hand-written.

| File | Responsibility |
|---|---|
| `aurora-cli/aurora_cli/identity.py` | Derive production's checkout, project and domain; branch naming; the `br-` namespace. Hardcodes neither of production's two names. |
| `aurora-cli/aurora_cli/envfile.py` | Strict `KEY=value` parse/render; branch `.env` rendering driven by `branch-env.yaml`. |
| `aurora-cli/aurora_cli/overlay.py` | Render `compose.branch.yml` from the resolved compose config. |
| `aurora-cli/aurora_cli/exclusions.py` | `branch-services.yaml`, the transitive `also_exclude` closure, profile emission. |
| `aurora-cli/aurora_cli/seed.py` | `SeedStrategy`, `FileCopySeeder`; SQLite snapshotting, reflink copy, volume seeding, Postgres dump/restore. |
| `aurora-cli/aurora_cli/crosswire.py` | Spec §5.4 layers: the `pre-push` hook and the branch marker. |
| `aurora-cli/aurora_cli/guards.py` | Production-safety assertions shared by every destructive path. |
| `aurora-cli/aurora_cli/branch.py` | `up`, `down`, `ls`, `access`, `shell`, `rebuild`. |
| `aurora-cli/aurora_cli/access_doc.py` | `BRANCH-ACCESS.md` and `.worktrees/INDEX.md` rendering. |
| `aurora-cli/aurora_cli/mcp.py` | Dependency-free stdio JSON-RPC MCP facade. |
| `branch-env.yaml` | The machine-readable must-override manifest. |
| `branch-services.yaml` | The exclusion manifest. |
| `hooks/pre-push` | Installed into each branch worktree. |
| `tests/branch_harness.py` | The single implementation of "production was not disturbed". |

---

## The decisions that shaped it

**Production's identity is derived, never typed.** Chunk 2's rename is blocked,
so production carries one compose label today and a different one after the
rename lands. Code that hardcodes either is wrong in one of the two worlds.
`identity.production_project()` derives it three ways — the checkout's
declaration, a cross-check against live containers, and working-directory label
agreement — and refuses to choose when they disagree.

**Safety is structural, not procedural.** An agent destroyed production during
this chunk's Task 0, executing a mutation table that neutered two guards around
a live call site. Prose said not to. Prose is not a guard. What exists now:

* `identity.branch_paths` forces the `br-` prefix, so a project name outside
  that namespace cannot be constructed;
* `guards.assert_branch_project` and `assert_not_production_path` run on the
  values actually about to be used, and an AST gate asserts every destructive
  call site is reachable only through them;
* `branch_harness` carries a second, deliberately duplicated `br-` check in
  front of every destructive docker call — the one place in the repository
  where duplication is correct, because it is the last thing between a wrong
  argument and an outage;
* `ops/docker-guard`, installed as `~/.local/bin/docker`, refuses any
  destructive docker verb that cannot *prove* it is branch-scoped. It catches
  what no test-level tripwire can: a command typed into a shell. It was tested
  against a stub, never the real daemon — and that earned itself twice, because
  its first version passed the incident command straight through.

**The must-override list is machine-readable.** A blockquote in a spec cannot
fail a build. `branch-env.yaml` names every variable a branch must override,
how it is derived, and whether omission is fatal — and `tests/test_branch_env.py`
fails in **both** directions, including "a variable in production's `.env`
whose value contains production's domain and is not listed here". That second
direction is what finds the *next* hostname-bearing variable without anyone
remembering to look.

**The overlay is generated and its enumeration is self-checking.** The
per-developer agent services are themselves generated from `developers.yaml`, so
a hand-written override goes stale the moment a developer is added — and the
failure mode is a daemon-global `container_name` collision, i.e. a branch that
steals production's container name. A coverage gate asserts that every service
the resolved config shows declaring `container_name` or `ports` is reset by the
overlay.

**The seed reads production read-only, and the invariant that proves it excludes
`-shm`.** Production is live: its WAL files change on their own, and a
read-only `VACUUM INTO` legitimately rewrites `-shm`. A naive tree checksum is
flaky in one direction and blind in the other.

---

## What Task 12 measured that nothing before it could

Every earlier task tested a part, against injected runners and fabricated
doubles. Task 12 is the first time this code met a real daemon, a real seed and
a live production stack. It brought up a 14-container branch stack beside
production, proved isolation, and destroyed it.

**It works.** Seeding, compose resolution, container startup, isolation, zero
published ports, path relativity, service DNS inside the sidecar namespace,
production availability throughout, and Docker-object teardown are all proven —
see the testing document for how each one is backed.

**It also found four things that were not known**, in descending order of how
much they matter:

1. **`aurora branch down` cannot remove a branch worktree.** The Docker daemon
   creates bind-mount sources inside it as root; the invoking user cannot
   unlink them; `git worktree remove` fails with `Permission denied` and
   `--force` does not help. With decision D-F that directory is inside
   production's checkout. This also makes the plan's **second** up/down cycle
   impossible. `docs/issues/chunk3-spec-deltas.md` §1.
2. **`dev-admin` cannot start from a clean checkout of this branch** — inherited
   from the compose-agents migration, never deployed, and it will break
   production's `dev-admin` on the first `docker compose up` after this branch
   merges. §13.
3. **Trap 9 is only half right.** A sidecar with *no* key stays up `Logged
   out.`; a sidecar with an *invalid* key **exits**, taking the shared network
   namespace with it. Both are loud, but the plan's Task 12 procedure was
   written around the wrong one. §2.
4. **`branch up` with no `--from` produces an unusable branch today**, because
   production's checkout is on a commit that predates Chunk 2. Resolves itself
   on merge. §3.

Nothing in this list was fixed by Task 12. Each is recorded, each is pinned by
a test that goes **red** when it is fixed, and the two that need a decision are
in `docs/post-implementation-steps.md`.

---

## Deviations from the plan, with reasoning

* **The acceptance suite has three tiers, not two.** The plan's Tier A assumed
  a real branch stack could be brought up and torn down cleanly on every run.
  It cannot (defect §1), so the live-stack tests are opt-in through
  `AURORA_ACCEPTANCE_STACK=1`. The opt-in is paired with an unconditional test
  that asserts the blocker is still recorded and goes red when it is fixed —
  the difference between this and the `pytest.skip` that made a Chunk 2 gate
  inert.
* **The acceptance worktree is not at `<production>/.worktrees/<name>`.** It is
  under `~/.cache/aurora-acceptance/`. A test that used the real location would
  leave an undeletable directory inside production's checkout on every run.
  D-F's own path *was* exercised once, by hand, and disclosed in the ledger.
  **Not `/tmp`**: `/tmp` here is a 7.8 GB tmpfs, reflink does not work onto it,
  and three seeded runs consumed 6.4 GB of RAM-backed storage beside a live
  production stack. On the same btrfs filesystem the same seed costs ~2.5 MB.
* **The sidecar is stubbed rather than run with a dummy key**, because a dummy
  key kills it (§2). Named in the module docstring and in the tier's own
  documentation.
* **`reconcile` is stubbed too.** The plan stubs only the readiness poll, but
  `reconcile` talks to the branch over its own HTTPS URL and therefore also
  needs tailnet ingress. The argv recorder is asserted to show it never ran.
* **There are no Tier B test bodies.** Writing assertions about tailnet ingress
  with no key to develop them against would produce artefacts that have never
  executed. The blocked-tier test turns red the moment a key exists, and the
  testing document specifies exactly what those tests must assert.
* **The second up/down cycle was not run.** Blocked by §1, not skipped for
  convenience. Docker-object residue is proven clean after one cycle; volume
  and filesystem *adoption* on a second `up` is not.
* **No second `README.md` rewrite.** Chunk 2 rewrote it; Chunk 3 adds one
  section describing `aurora branch`.

---

## Post-Task-12 changes (2026-07-30)

Three changes landed after the acceptance run, all on
`feat/chunk3-ephemeral-branching`. None of them touched production.

### `5ab7fbb` — the `dev-admin` mount that would have broken the deploy

`compose.yml` mounted `./compose.agents.yml` at `/app/compose.agents.yml`,
*inside* the read-only bind of `./dev-administration`. runc must create that
mountpoint and cannot. The sibling `./developers.yaml:/app/developers.yaml`
works only because `dev-administration/developers.yaml` is a real tracked file
able to serve as one — luck, not design.

Introduced in Chunk 2's Task 5 fix round, for the `compose.stale` check. It
survived a full chunk of green suites because `docker compose config`
validates the broken form and production runs an older `compose.yml`. Fixed by
mounting at `/compose.agents.yml`; `AGENTS_COMPOSE_PATH` follows.

Task 12's test asserting the defect was **inverted and generalised** rather
than deleted: no file may be mounted under `/app` unless its mountpoint exists
in `dev-administration/`.

While inverting it, a text slice from `def` to the next `def` swallowed the
`@stack_tier` decorator above the following function, un-gating a live-tier
test (12 skipped → 11 skipped + 1 error). Restored. The safe boundary when
editing Python as text is the **decorator**, not the `def` — and this was only
visible because that module raises `RuntimeError` rather than `pytest.skip`
when its tier is disabled. Under a plain skip it would have shown up as one
fewer skip and nothing else.

### `ops/deploy-rename.sh` — Chunk 2's restart, made durable

The rename/deploy procedure previously existed only as a file in `/tmp`, which
is tmpfs here; it evaporated and the ledger's reference to it dangled. It is
now a reviewed, version-controlled script that refuses to run without
`AURORA_ALLOW_PROD=1` (verified: exits 13 before touching anything) and
enforces its own pre-flight. Documented in full in
`docs/post-implementation-steps.md` §C3-3.

### Documentation brought up to date

`docs/post-implementation-steps.md` C3-1 records that the Tailscale key is
supplied, and why the key is deliberately **untagged** for now.
`docs/issues/chunk3-spec-deltas.md` items 9 and 13 carry status updates.

## What is proven, and what is not

**Proven end to end** (Task 12, against live production): a real 14-container
branch stack minted from a genuine `git worktree add`, seeded from production's
live state, brought up beside live production, measured and destroyed, with
production answering 200 on every poll. Isolation by label *and* by name; zero
published host ports; Docker service DNS inside the sidecar netns; the seed not
mutating `gitea.db` or its WAL; teardown across containers, volumes and
networks. `docker events` captured throughout (4,014 events, fully attributed);
the unexplained `hermes-*` destruction from spec §13.6 did not recur.

**Not proven.** Tier B — node registration, certificate issuance, the branch
URL serving seeded HTML, `/agent/<user>/` confirming service-mode addressing,
and node deregistration on teardown. The credential now exists; the run does
not. Also unproven: **volume adoption on a second `up`**, because plan defect
54 (a branch worktree that has hosted a running stack cannot be removed by the
tooling) meant the second acceptance cycle never ran.
