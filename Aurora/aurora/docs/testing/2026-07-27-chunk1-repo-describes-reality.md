# Testing — Chunk 1: Repo Describes Reality

## How to run

From the repo root:

    .venv/bin/python -m pytest tests/ dev-administration/tests -v

There is no system pytest for this project; always use `.venv/bin/python -m
pytest`, never a bare `pytest`. `pytest.ini` sets `testpaths = tests
dev-administration/tests`, so both suites collect from a single rootdir.

## What is tested and why

All six tests in `tests/` are structural conformance checks against the live
`docker compose config`, not behavioural tests of any service. Each one exists
because a specific class of drift between the repo and the running stack was
found, and each test is designed to catch that class recurring, not just the
one instance that prompted it.

| Test | Defect it catches |
|---|---|
| `test_every_build_context_is_tracked_in_git` | A build context (e.g. a service's `build.context:` directory) that git does not track. This is exactly what made `dev-administration` unbuildable in a fresh worktree before Task 2 — the directory existed on disk in production but was gitignored, so `docker compose build` would fail the moment anyone cloned or worktreed the repo. |
| `test_no_undeclared_containers_in_project` | Drift between `compose.yml` and reality: a container running under the production project's label with no corresponding service declaration. This is deliberately anchored to `PRODUCTION_PROJECT` (`tai-review`, overridable via `AURORA_PROJECT`) rather than `docker compose config`'s own `config["name"]`, because inside a git worktree that name is the directory basename and matches no running container — an earlier anchoring to `config["name"]` passed vacuously and would have silently defeated the whole point of this test (see the implementation log, Task 1). |
| `test_affine_is_declared_in_this_project` | AFFiNE regressing back out of the repo. The Caddyfile has a hard routing dependency on AFFiNE; if its compose declaration were ever removed without also removing the Caddyfile routes, this fails loudly instead of leaving a silent dangling dependency. |
| `test_affine_state_paths_are_inside_the_repo` | Same regression class, for AFFiNE's bind mounts specifically: they must resolve to paths inside the repo (so a worktree gets its own isolated data directory) rather than sharing production's. Both sides are resolved with `Path.resolve()` before comparison — a `str.startswith()` comparison would both false-fail on this host's `/home` → `/var/home` symlink and false-pass a sibling directory that merely shares a string prefix with the repo root. |
| `test_compose_has_no_commented_out_services` | Dead-code reaccumulation: commented-out service blocks (Immich, FalkorDB, tai-db, NFS, the old redis/database entries) left in `compose.yml` as if they were live documentation. These mislead a reader about what the stack actually contains, and were the ~120 lines Task 6 deleted. |
| `test_fresh_worktree_resolves_compose_config` | **The acceptance gate for the whole chunk.** Creates a real throwaway `git worktree`, copies in production's `.env`, and asserts `docker compose config --quiet` succeeds and all three build contexts (`fjell`, `agent-authz`, `dev-administration`) physically exist in it. This is the end-to-end version of the first test above: it doesn't just check that build contexts are tracked in git, it proves a worktree assembled from git alone is actually buildable. |

The inherited suite at `dev-administration/tests` (28 tests, imported with the
project's history in Task 2) is not chunk-1-authored, but is exercised by the
same `pytest` invocation because both suites collect from the shared
`pytest.ini`.

## Inherited failure

`dev-administration/tests/test_caddy_utils.py::test_generate_caddy_agents_conf`
fails: it asserts `handle_path /agent/juan/setup` in the generated Caddy
config; the generator (`generate_caddy_agents_conf`) emits `handle` for that
line. This is confirmed **pre-existing**, not caused by this chunk:

- The absorbed `dev-administration` tree is byte-identical to the source
  repo's working tree at the imported revision (verified in Task 2 against a
  plain `git subtree add`'s tree object).
- Traced to its origin in Task 7: commit `97d695a` ("fix: use handle_path
  instead of handle+strip_prefix") changed the `/agent/<user>/*` wildcard
  block and the bare `/agent/<user>` block to `handle_path`, and in the same
  commit updated the test's assertion for the unrelated `/setup` line to also
  expect `handle_path` — without changing the generator's `/setup` code to
  match. The mismatch was introduced by that commit itself.

`handle` and `handle_path` differ in whether the matched path prefix is
stripped before the request reaches the upstream (fjell): `handle_path`
strips it, `handle` does not. So this is a live, unresolved question about
what fjell's `/setup` route actually expects to receive — not a stale
assertion that can be safely deleted. It's recorded as a required human
decision in `docs/post-implementation-steps.md` §D1, and was deliberately
**not** fixed here: chunk 1's mandate is to make the repo describe the
running stack accurately, not to change the stack's behaviour, and the
generator's shipped output (`handle`) is what production actually runs.

Full command and verbatim output:

    .venv/bin/python -m pytest dev-administration/tests -v

Result: **1 failed, 27 passed**.

## What these tests deliberately do NOT cover

Every test here asserts structure — that a service is declared, that a build
context exists on disk and in git, that a bind mount resolves to the expected
path, that no dead YAML lingers. **Nothing here proves a service actually
works.** There is no test that AFFiNE's login flow succeeds, that Forgejo
issues valid OAuth2 tokens, that arcadedb accepts a connection, or that the
Caddy routes it depends on actually reach a live backend. That is deliberate:
chunk 1's job was to make the repo an accurate description of what's running,
which is a claim about declarations, not about runtime correctness. End-to-end
behavioural verification — actually exercising the services these compose
files describe — is explicitly out of scope here and arrives with the
end-to-end suite planned for Chunk 3.
