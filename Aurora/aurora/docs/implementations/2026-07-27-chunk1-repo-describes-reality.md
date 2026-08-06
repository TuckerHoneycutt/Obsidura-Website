# Implementation Log — Chunk 1: Repo Describes Reality

Running record of what was actually built, how it diverged from
`docs/superpowers/plans/2026-07-27-chunk1-repo-describes-reality.md`, and why.
Newest section last.

> Purpose: the plan says what was intended. This says what the running system
> actually is. Where they disagree, **this file is correct**.

---

## Outcome

A fresh `git worktree add` of this repo can now run `docker compose config`
successfully and physically contains all three build contexts
(`fjell`, `agent-authz`, `dev-administration`) — the property that was broken
at the start of this chunk, because `dev-administration/` was gitignored and
only ever existed as an untracked directory copied by hand into the production
checkout. Six tests in `tests/` plus the inherited 28-test suite in
`dev-administration/tests` (27 passing, one pre-existing failure, see Task 7)
now run from a single `pytest.ini` rootdir. Nine production containers have
unbroken uptime across all seven tasks — nothing was stopped, started, or
recreated by this chunk.

---

## Task 1 — Repo conformance test harness

Created `pytest.ini`, `tests/conftest.py`, `tests/test_repo_conformance.py`
with the two seed tests: `test_every_build_context_is_tracked_in_git` and
`test_no_undeclared_containers_in_project`. Set up a worktree-local `.venv`
(Python 3.14.6; the plan's stated target of 3.13 does not match what's
actually on this host) and copied production's `.env` into the worktree so
`docker compose config` could resolve at all.

**Verified:** first test failed exactly as predicted, implicating
`dev-administration` as an untracked build context. The second test passed —
*not* because there were no undeclared containers, but because it derived the
compose project label from `config["name"]`, which inside a git worktree is
the directory basename (`ephemeral-branching`) and matches zero running
containers. A vacuously-passing test would have silently green-lit every later
task that depends on it eventually failing and then passing for real.

**Divergence from plan, fixed same task:** introduced `PRODUCTION_PROJECT`
(`tai-review`, overridable via `AURORA_PROJECT`) in `conftest.py` and rewrote
the second test to filter on that instead of `config["name"]`. Re-run then
failed genuinely, listing `arcadedb, chromadb, ntfy, odysseus, searxng` —
the actual undeclared containers Tasks 4–6 needed to resolve.

Commits: `12317b4` (harness), `e186a1b` (fix round 1: anchor to
`PRODUCTION_PROJECT`).

---

## Task 2 — Absorb `dev-administration` into the monorepo

Imported the source repo's `feat/multi-dev-oidc-provisioning` branch (33
commits — the revision production is actually built from; the source has no
`master`) under `dev-administration/`, preserving history.

**Divergence 1:** the brief's `git subtree add` was tried first and technically
worked (33 commits became ancestors of HEAD), but those commits record paths
at the *source repo root*, so `git log -- dev-administration` saw only the
merge commit (1, not 33) — failing the plan's own acceptance check. Fixed by
rewriting the 33 commits with `git filter-branch --index-filter` to prefix
every path with `dev-administration/`, then merging that rewritten history
with `--allow-unrelated-histories`. Verified content-identical to the plain
subtree's tree object (`f239131…`); only commit SHAs differ, which is
unavoidable and intentional — this absorbs the project permanently rather than
vendoring it.

**Divergence 2:** copied (`cp -a`) rather than moved+restored the production
directory, so production was never without a live build context or bind mount
target, even transiently.

**Verified:** `test_every_build_context_is_tracked_in_git` now passes;
`git log --oneline -- dev-administration | wc -l` → 34 (33 imports + the merge
commit, ≥ the plan's 33 requirement); production containers unchanged
(3h → 4h uptime, no restarts).

**Inherited test failure surfaced, not fixed:** `dev-administration/tests`
runs at 1 failed / 27 passed, not the plan's predicted "all pass."
`test_generate_caddy_agents_conf` expects `handle_path` where the generator
emits `handle` for the `/setup` route. Recorded in
`docs/issues/chunk1-inherited-test-failures.md`; root-caused fully in Task 7
(see below).

**Documentation added:** `docs/issues/chunk1-inherited-secrets.md`, recording
the imported Forgejo admin token (already exposed elsewhere, not a new leak),
six newly-tracked test-account password defaults, the leftover nested
`dev-administration/.git` in production, and the deliberately-unimported
upstream commit `202fc6f`.

Commits: `2ea3723`, `d2af8d2`, `af76b76`, `c312bb8`; fix round 1: `45cde99`
(the secrets doc — approved with no code changes).

---

## Task 3 — Bring AFFiNE into the monorepo via `compose include`

Added `affine/compose.yml` (four services: `affine`, `affine_migration`,
`redis`, `postgres`) and wired it in via `include:` in the root `compose.yml`,
so the Caddyfile's hard dependency on AFFiNE is finally declared where it's
used. Did not touch the live, separately-managed `affine` compose project —
`docker compose config` is parse-only.

**Verified:** `test_affine_is_declared_in_this_project` passed immediately.
`test_affine_state_paths_are_inside_the_repo` initially failed with bind-mount
paths reported under `/home/...` instead of the expected `/var/home/...`.
Root cause: this host's `/home` is a symlink to `/var/home`, and Go's
`os.Getwd()` (used by the `docker compose` binary) trusts a stale `$PWD` over
the resolved syscall cwd. A plain `cd ~/...` over SSH leaves `$PWD`
unresolved; `cd -P` fixes it. This is a host quirk, not a defect in the AFFiNE
declaration.

**Fix round 1** made the test itself cwd-independent (resolve both sides with
`Path.resolve()` before comparing, and check `REPO_ROOT` is a real parent, not
just a string prefix — closing a second boundary bug the review also found)
and closed a `.gitignore` gap (`affine/data/`, `.pytest_cache/`). Verified
passing both with and without `cd -P`.

**Documented, not fixed (deliberately deferred):** AFFiNE's fixed
`container_name:` values already belong to the live, separately-managed
`affine` project's containers. `docker compose up -d` against this repo will
fail on all four names until they're migrated at merge time — recorded as
runbook item 5.

Commits: `7c1075f`; fix round 1: `cefa732`.

---

## Task 4 — Declare `arcadedb` (M2, part 1)

Reconstructed the `arcadedb` service block in `compose.yml` from
`docker inspect` of the already-running (but `Exited (137)`) container:
image, restart policy, `JAVA_OPTS`, `ARCADEDB_ROOT_PASSWORD`,
127.0.0.1-bound ports, five volumes (one bind, four now-named). Never started
the container — it remains exited throughout.

**Verified:** `docker compose config` resolves `arcadedb` as a service;
`test_no_undeclared_containers_in_project`'s failure list shrank from five
containers to four (`chromadb, ntfy, odysseus, searxng`) — exactly as
expected, since `arcadedb` was the one this task owned.

**Fix round 1 (comment accuracy only, no behaviour change):** the original
compose comment claimed `JAVA_OPTS` "caps" the heap below the image default.
False — `-Xmx2g` (branch) and the image's default `-Xmx2G` are the same
maximum heap (Java heap suffixes are case-insensitive); only the *initial*
heap actually drops (2G → 512m). Corrected the comment and
`docs/issues/arcadedb-oom.md`, and added a new section there noting the
running container's four volumes are anonymous (started outside compose), so
`docker compose up arcadedb` will create a fresh container with fresh named
volumes rather than adopting the old one — low practical impact, since the
old container's full lifetime was ~50 seconds.

Commits: `b8d068c`; fix round 1: `0014313`.

---

## Task 5 — Remove the Odysseus stack

Removed the `/chat` and `/chat/*` redirect blocks from the Caddyfile, the
`ODYSSEUS_SERVE_PORT` wiring from `compose.yml`, stopped and removed the four
Odysseus-family containers (`odysseus`, `chromadb`, `searxng`, `ntfy`), removed
their now-orphaned volumes, and deleted the five now-dead `.env` variables
(plus their explanatory comments) from production's `.env`.

**Verified:** all four containers gone; the other nine production containers
kept climbing in uptime (13h → 17h) with no restarts;
`test_no_undeclared_containers_in_project` passed for the first time.

**Major divergence, root-caused mid-task:** production's committed `Caddyfile`
(on `master`) was an entire service generation stale — it still routed to
**Immich** (`127.0.0.1:2283`), a service that no longer exists on the engine,
while production's actual live, *uncommitted* Caddyfile had already been
hand-edited to route to **AFFiNE** instead. The branch had inherited master's
stale, Immich-routed copy. Deploying it as originally planned would have taken
`/affine/` down and silently undone Task 3 in the same merge, via a
named-matcher collision between Immich's `@immich_root` and AFFiNE's
`@affine_static` (three of AFFiNE's five static paths — `/favicon.ico`,
`/favicon-*.png`, `/manifest.json` — collide; two do not).

**Fix round 1:** re-based the Odysseus removal onto a copy of production's
actual live Caddyfile instead of master's stale commit, re-verified in a
throwaway `caddy validate` container (`Valid configuration`), and documented
the whole incident plus the required merge-time conflict resolution as
runbook item 6. Production's own Caddy was deliberately **not** reloaded —
that's a deploy action, not a description-of-reality action, and belongs to
the merge.

Commits: `650621d`; fix round 1: `fef099b`.

---

## Task 6 — Delete dead commented blocks and stale directories

Deleted ~120 lines of commented-out service definitions (`immich-server`,
`immich-machine-learning`, `redis`, `database`, `nfs`, `tai-db`, `falkordb`)
and the orphaned `model-cache:` volume declaration from the worktree's
`compose.yml`; deleted 10 dead `.env` keys from both the production and
worktree `.env` files; removed the now-unreferenced `tai-review_model-cache`
volume live; removed the tracked-but-production-already-deleted
`nfs-exports.txt`.

**Divergences (all discovered by checking reality first, not assumed from the
plan):** all five stale directories the plan named as possibly needing `sudo`
(`postgres/`, `library/`, `shared/`, `falkor-tai/`, `postgrespg-tai/`) were
already absent from both checkouts — no `rm -rf` of any kind was needed.
`.env.template` contained none of the 10 dead keys, so it wasn't touched.

**Verified:** all 5 tests in `tests/test_repo_conformance.py` passed,
including the new `test_compose_has_no_commented_out_services`; production's
`compose.yml` (which the write-restriction forbade editing directly) still
declares `model-cache:` until the merge lands, so the live volume removal is
**not durably safe** — any `docker compose up` in production before the merge
will silently recreate it. Recorded as runbook item 7, with the required
merge-time re-check.

Commit: `e7733f8`.

---

## Task 7 — Chunk 1 acceptance

Added the acceptance gate, `tests/test_worktree_buildable.py`: spins up a
throwaway, detached `git worktree`, copies production's `.env` into it,
resolves `docker compose config --quiet` inside it, asserts all three build
contexts physically exist, then tears the worktree down. **Passed** — this is
the property that was broken at the start of the chunk and is now fixed.

**Corrected two claims in the merge runbook (`chunk1-inherited-secrets.md`
§6)** that predate this task and turned out to be partly wrong on inspection:

1. The claim that Immich's `handle /api/*` would have shadowed AFFiNE's
   `handle /api/auth/*` is very likely false: Caddy's Caddyfile adapter sorts
   `handle` blocks that each carry a single bare path matcher by descending
   specificity, independent of file order — `/api/auth/*` would have been
   tried first regardless. The claim that *did* matter and is now stated
   precisely: `@immich_root` and `@affine_static` are named matchers with
   several path patterns each, which Caddy cannot specificity-sort, so they
   fall back to file order and genuinely collide — on exactly three of
   AFFiNE's five paths (`/favicon.ico`, `/favicon-*.png`, `/manifest.json`),
   not all five.
2. The merge instruction "resolve in favour of the branch" was unconditional.
   Changed to: diff production's live file against the branch's 2026-07-28
   snapshot first; only take the branch outright if nothing else changed.
   Production's `Caddyfile` is still live-editable, so an unconditional rule
   risks silently discarding a future edit — the same failure mode this whole
   chunk exists to eliminate.

**New findings surfaced and recorded in `docs/post-implementation-steps.md`,**
not fixed here (out of scope — this chunk describes reality, it doesn't
change running behaviour):

- The Forgejo admin token situation is more tangled than previously recorded:
  `.env`'s live `FORGEJO_ADMIN_TOKEN` already differs from the token exposed
  in `admin-asks.md` and both `.git/config` origin URLs — but `git ls-remote`
  confirms the *old*, exposed token is still valid server-side. A partial,
  incomplete rotation already happened.
- `Caddyfile.d/agents.conf`, `Caddyfile.d/agents.json`, and
  `agent-authz/data/owners.json` are not just stale relative to the commit —
  they disagree with *each other* and with the current `developers.yaml`.
  Production's live `owners.json` matches the current roster; its live
  `agents.json` is empty; its live `agents.conf` still routes the old
  usernames. The likely correct merge-time fix is to run `dev-admin
  reconcile` post-merge rather than hand-pick a side for any one file.
- The inherited `handle`-vs-`handle_path` test failure was traced to its
  origin: commit `97d695a` changed the `/agent/<user>/*` and bare
  `/agent/<user>` blocks to `handle_path` (for `X-Forwarded-Prefix`
  correctness) and, in the same commit, updated the test's assertion for the
  unrelated `/setup` line to also expect `handle_path` — without changing the
  generator's `/setup` code to match. The mismatch is original to that
  commit, not drift since. This is a live behavioural question (what does
  fjell actually receive on `/setup`?), not a stale assertion — recorded for
  a human decision, not resolved here.
- Verified precisely (not estimated): production's `.env` holds exactly 27
  commented-out `ODYSSEUS_*`/`SEARXNG_*` lines, including a commented
  `SEARXNG_SECRET=`.

**Verified, acceptance:**
```
.venv/bin/python -m pytest tests/test_worktree_buildable.py -v   # 1 passed
.venv/bin/python -m pytest tests/ dev-administration/tests -v    # 6 passed (tests/), 1 failed / 27 passed (dev-administration/tests)
docker compose config --quiet && echo CONFIG_OK                  # CONFIG_OK
```
No `odysseus`, `chromadb`, `searxng`, or `ntfy` containers exist. `/git/` and
`/affine/` both return `200`. Production's nine containers were never
stopped, started, or recreated by this task.

Commit: see task 7 report for the final SHA.
