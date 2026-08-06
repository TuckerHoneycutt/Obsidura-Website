# Chunk 3: Ephemeral Branching — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the feature the previous two chunks were prerequisites for. One command mints a complete, isolated copy of the stack from a git worktree — its own Compose project, its own tailnet identity and certificate, its own seeded state — while production keeps serving. One command destroys it and reclaims the disk. Production cannot be reconfigured, corrupted or taken down by anything a branch does, and that property is structural rather than a matter of careful scripting.

**Architecture:** Spec migrations M7 (branch override + Tailscale sidecar + ephemeral auth key) and M8 (CLI + MCP + exclusion manifest + seeder). A new host-side package `aurora-cli/aurora_cli/` owns branch lifecycle; `dev-administration/` is unchanged except for one generator. The divergence between production and a branch is exactly three artifacts: a **generated, committed** `compose.branch.yml` (the `!reset` / `!override` overlay plus the `tailscale` sidecar), a **rendered** branch `.env`, and **seeded** state. Everything else — `compose.yml`, `Caddyfile`, `compose.agents.yml`, every service definition — is byte-identical between production and a branch, which is what makes a branch a test of production rather than a test of a fiction.

**Tech Stack:** Docker Compose v5.3.1 / Docker Engine 29.6.2, Python 3.14.6 (host venv) + pytest, `tailscale/tailscale:latest` (containerboot), Caddy, Fedora/btrfs host.

---

## Global Constraints

**Read these before writing a line. Several of them are the direct product of time this project has already lost.**

- Host is `superserver.tailc67a98.ts.net`, reached as `ssh superserver`. `sudo` is unavailable.
- **All work happens in `~/Desktop/tai-review/.worktrees/chunk3`**, branch `feat/chunk3-ephemeral-branching`, based on Chunk 2's tip `e085c75`. The worktree already exists with a `.venv` and a `.env`. Other worktrees (`chunk2`, `ephemeral-branching`) belong to earlier chunks and must not be reused.
- **There is no system `pytest`.** Run `.venv/bin/python -m pytest`, never bare `pytest`.
- **Every test invocation in this plan states whether `AURORA_PROJECT` is set. This is not decoration.** `tests/conftest.py` sets `PRODUCTION_PROJECT = os.environ.get("AURORA_PROJECT", "aurora")`, and **production is still labelled `tai-review`** (Chunk 2 Task 12 was never deployed). Baseline, measured 2026-07-29:

  | Invocation | Result |
  |---|---|
  | `AURORA_PROJECT=tai-review .venv/bin/python -m pytest -q` | **129 passed, 1 xfailed** — this is the baseline |
  | `.venv/bin/python -m pytest -q` | 2 failed, 128 passed — `test_the_conformance_gate_has_containers_to_conform_to` (empty project) and `test_declared_bind_sources_match_runtime` (XPASS on `xfail(strict=True)`) |

  A missing `AURORA_PROJECT` does not produce a *silent* vacuous pass any more — Chunk 2 added the has-containers gate — but it does produce two failures that look like your change broke something. Do not "fix" them.
- **Production must not be touched.** Production is compose project `tai-review`, checkout `~/Desktop/tai-review`, 12 containers. **Never** plan or run `docker compose down/up/restart`, `docker rm/stop`, or `docker volume rm` against it. Branch stacks come up under their own project name and are torn down; that is the entire feature. Read-only operations against production (`docker inspect`, `docker exec … pg_dump`, `docker exec … cat`, reading files under `~/Desktop/tai-review`) are permitted and are how seeding works.
- **Chunk 2 Task 12 was not deployed and the rename is blocked pending the user.** Production is `tai-review` at `~/Desktop/tai-review`, not `aurora` at `~/Desktop/aurora`. **Therefore no Chunk 3 code may hardcode either name.** Production's identity is *derived* (Task 1). Treat this as a forcing function: code that derives correctly works before and after the rename, and code that hardcodes is wrong in one of the two worlds no matter which name it picks. Every task in this plan is written to work either way.
- **Do not merge to `main`.** The user reviews and merges. Work stays on `feat/chunk3-ephemeral-branching`.
- **Commit identity must be passed inline**, and multi-line messages go in a file:
  ```bash
  git -c user.name="supergoodname77" -c user.email="epascuales@outlook.com" commit -F /tmp/msg.txt
  ```
  Apostrophes in commit prose break shell quoting; `-F` is not optional advice.
- Commit after every task. Never commit `.env`, `.venv/`, `.pytest_cache/`, `.hermes/`, `.agent-env/`, `forgejo/`, `affine/data/`, `arcadedb/`, `.worktrees/`.
- Do **not** re-enable the commented-out cargo layer-cache block in `fjell/Dockerfile`.
- `/home` is a symlink to `/var/home`, and the `docker compose` binary reports unresolved `/home/...` paths (verified again while writing this plan: `docker compose config` reports `/home/supergoodname77/Desktop/tai-review/.worktrees/chunk3/Caddyfile` where Python resolves `/var/home/...`). **Any comparison between a compose-reported path and a Python-computed one must `Path.resolve()` both sides**, and check parentage with `Path.parents`, never a string prefix.
- **New runtime dependencies are not permitted** in `dev_administration` (typer + pyyaml only). The new `aurora_cli` package is **stdlib + pyyaml**, deliberately (see D-A below).

### Traps that have already cost this project real time

These are stated as rules because each of them has already been discovered the expensive way. Task briefs restate the ones they touch.

1. **Tests that pass while testing nothing.** At least ten instances across Chunks 1 and 2: a vacuous project filter; an `inspect.getsource()` check satisfied by a *docstring*; a decoy that reimplemented the logic it claimed to pin; a universal `pytest.skip` that made a Critical-defect gate inert at every invocation the plan contained; a conformance test that compared against production's identity and so went **red exactly when a branch was correct**. **Every task in this plan names concrete mutations the implementer must run to prove each new test can fail.** Running them is a step, not a suggestion. A fix is not "pinned" until a named mutation reddens it.
2. **The vacuous conformance pass.** A gate that queries a project with no containers passes on an empty set. Never assert over a container/volume set without first asserting the set is non-empty.
3. **`docker compose down` needs `--profile '*'`** or profiled services (every agent) survive the teardown.
4. **Compose `include:` is a hard error on a missing file.** This is why `compose.agents.yml` is generated *and committed*; `compose.branch.yml` follows the same rule for the same reason.
5. **`git worktree repair` needs explicit paths on this host**; a bare invocation silently no-ops.
6. **Compose adopts a pre-existing volume** that carries `com.docker.compose.project` and `com.docker.compose.volume` labels. Seeding a branch volume before `up` is therefore possible — and mislabelling one is how a branch would adopt production's.
7. **`.env` must be strict `KEY=value`.** `docker run --env-file` rejects whitespace around `=`; a stray `DOMAIN_NAME = value` in production's `.env` cost a debugging detour in Chunk 2. `tests/test_repo_conformance.py::test_dotenv_files_use_strict_key_equals_value` pins it and the branch renderer must not regress it.
8. **A branch's Caddy is `network_mode: service:tailscale` and `127.0.0.1` reaches nothing there.** Task 6/7 of Chunk 2 built `AGENT_UPSTREAM_MODE=service` and the `{$*_UPSTREAM}` placeholders for exactly this. **The branch `.env` must set them.** They default to production's `127.0.0.1:*` addresses, so forgetting them is not an error — it is a stack that starts, serves 502s, and looks fine.
9. **A `tailscaled` container with no auth key does not fail.** Verified below: it starts, prints `Logged out.` with a login URL, and stays up. `branch up` must therefore *verify* the node reached `Running` state, or every branch will "succeed" with a dead URL.

---

## State of the host, verified while writing this plan (2026-07-29)

Everything load-bearing was probed, not assumed. Probe transcripts are reproduced in the task briefs that depend on them.

| Fact | Evidence |
|---|---|
| Production is project `tai-review`, 12 containers, checkout `/home/supergoodname77/Desktop/tai-review` | `docker ps -a --format '{{.Label "com.docker.compose.project"}}'`; `docker inspect forgejo` → `com.docker.compose.project.working_dir=/home/supergoodname77/Desktop/tai-review` |
| `dev-admin` is `Exited (1)`, `affine_migration_job` `Exited (0)`; the three `hermes-*` agents are **absent** | `docker ps -a`. Both expected: Task 11's fix is undeployed, and Task 5 removed the unlabelled agent orphans. |
| The worktree's `.env` says `COMPOSE_PROJECT_NAME=aurora`; production's says `tai-review` | `grep -n '^COMPOSE_PROJECT_NAME' .env` in both |
| Baseline suite: **129 passed / 1 xfailed** with `AURORA_PROJECT=tai-review` | see table above |
| `!reset` and `!override` both work across an `include:` boundary on v5.3.1 | overlay probe: `container_name: !reset null` cleared `affine`, `postgres` (from `affine/compose.yml`) and `hermes-testuser` (from `compose.agents.yml`); `volumes: !override [...]` replaced Caddy's list wholesale |
| `${VAR:?message}` makes a missing branch variable a **hard config error** | `docker compose -f compose.yml -f overlay.yml config` without `TS_AUTHKEY` → `required variable TS_AUTHKEY is missing a value: branch needs an ephemeral Tailscale auth key` |
| Kernel-mode `tailscale/tailscale` sidecar works on this host | throwaway project `br-nsprobe`: `tailscale0` appeared in the shared netns with `cap_add: [NET_ADMIN, NET_RAW]` + `devices: [/dev/net/tun]`; `/dev/net/tun` exists and is `crw-rw-rw-` |
| A container with `network_mode: service:tailscale` **keeps Docker service DNS** | same probe: `frontend` had `eth0 172.19.0.3` and `nameserver 127.0.0.11`, and `wget http://backend:3000/` reached the peer (HTTP 404 from the file server = connection established). This is what makes `FORGEJO_UPSTREAM=forgejo:3000` work. |
| `TS_ACCEPT_DNS` must stay `false` | accepting MagicDNS rewrites the shared netns' `resolv.conf` to `100.100.100.100`, which would remove `127.0.0.11` and break the service DNS the line above depends on |
| A sidecar with **no** auth key starts anyway and stays `Logged out.` | `docker exec … tailscale status` → `Logged out. Log in at: https://login.tailscale.com/a/…`; container `running`. This is trap 9. |
| `docker compose --profile '*' down -v --remove-orphans` on a throwaway project removed 3 containers, 2 volumes and 1 network, and left production's 12 containers untouched | `br-nsprobe` teardown, then `docker ps -a --filter label=…project=tai-review \| wc -l` → 12 |
| **No Tailscale auth key exists anywhere on this host**, and minting one needs the admin console | `grep -rI 'tskey-'` over `.env`/docs → nothing; `sudo -n true` → NO_SUDO |
| `VACUUM INTO` through a **read-only** connection works on production's live WAL database and mutates nothing | `sqlite3.connect("file:forgejo/gitea/gitea.db?mode=ro", uri=True).execute("VACUUM INTO ?")` → 2.4 MB snapshot in **0.02 s**; sha256 of `gitea.db`, `-wal` and `-shm` identical before and after |
| …but a read-only `VACUUM INTO` **can rewrite the `-shm` file** | the same probe against `.hermes/state.db` (47 MB, 0.05 s) left `state.db` and `state.db-wal` byte-identical and **changed `state.db-shm`**. `-shm` is a mmap'd WAL index, not content. **The "seed does not mutate production" invariant must exclude `*-shm`** or it fails on a correct implementation. |
| The snapshot carries real identity | the vacuumed `gitea.db` holds 11 users (`supergoodname77`, org `obsidura`, `testuser`, `newuser`, `cumshit42069`, …) and 4 repos (`aurora`, `aurora-agent`, `dev-administration`, `superpowers`). These are the strings §10.3's end-to-end assertion looks for. |
| Production's SQLite databases, enumerated | `forgejo/gitea/gitea.db` (2.4 MB + **4.1 MB uncheckpointed WAL**); `.hermes/{state.db (47 MB, live -wal/-shm), kanban.db, projects.db, verification_evidence.db}`, `.hermes/cron/executions.db`, `.hermes/mnemosyne/data/mnemosyne.db` — **six**, at depths 1–3. Spec §6.3 said "at least five". Enumerate recursively; never hand-maintain the list. |
| `forgejo/ssh/ssh_host_*` are **root-owned mode 600** and unreadable to the agent user | `ls -la forgejo/ssh` → `-rw------- root root`. A naive `cp -a forgejo/` fails there. Spec §6.4 already says never clone them; now there is a second, mechanical reason. |
| `affine/data/postgres` is `polkitd:root` mode 700 and unreadable; `affine/config/private.key` is root-owned but world-readable | `ls -la affine/data affine/config`. Confirms §6.3: AFFiNE state cannot be file-copied by this user and must go through `pg_dump`. |
| `pg_dump -Fc` against the live AFFiNE Postgres works read-only | `docker exec affine_postgres pg_dump -U affine -Fc affine \| wc -c` → 256182 bytes |
| The apparently-unreadable entries under `.hermes/home/.cache/uv` are **broken symlinks** to container-side paths, not permission failures | `file .hermes/home/.cache/uv/wheels-v6/…` → `broken symbolic link to /opt/data/home/…`. `cp -a` preserves them; do not try to dereference. |
| Disk and memory budget | `/var/home` btrfs, **142 G free**; RAM 15 Gi total, **7.9 Gi available** (`free -h` "available", not "free" — "free" reads 483 Mi because of 8.6 Gi of cache) |
| `git rev-parse --path-format=absolute --git-common-dir` from a worktree resolves production's checkout | → `/var/home/supergoodname77/Desktop/tai-review/.git`; `git worktree list --porcelain` names the main worktree first |
| Forgejo's `app.ini` hardcodes production's `DOMAIN`, `SSH_DOMAIN` and `ROOT_URL`, but `compose.yml` overrides `ROOT_URL` and `DOMAIN` from `${DOMAIN_NAME}` at boot | `grep ROOT_URL forgejo/gitea/conf/app.ini`; `compose.yml` `FORGEJO__server__*`. `SSH_DOMAIN` is **not** overridden — see finding N4. |

---

## Findings that shape this plan

**N1 — Spec §4.1's branch-`.env` override list is still incomplete, beyond the `COMPOSE_PROFILES` correction.** The spec lists `COMPOSE_PROJECT_NAME`, `DOMAIN_NAME`, `TS_HOSTNAME`, `TS_AUTHKEY`, `COMPOSE_PROFILES` and (via §4.2/§7.4) the three `*_UPSTREAM` variables plus `AGENT_UPSTREAM_MODE`. Production's `.env` contains **three more variables that embed the production hostname as a literal and are not derived from `DOMAIN_NAME`**:

```
FORGEJO_URL=https://superserver.tailc67a98.ts.net/git
AFFINE_SERVER_EXTERNAL_URL=https://superserver.tailc67a98.ts.net/affine
AURORA_PROFILE_URL=https://superserver.tailc67a98.ts.net/git/supergoodname77/aurora-agent.git
```

Inherited unchanged, a branch's `dev-admin` would reconcile **against production's Forgejo**, its agents would register OIDC against production's issuer, and AFFiNE would advertise production's external URL. `FORGEJO_URL` is the worst of the three: it is what `dev-admin` calls to create OAuth applications. The §5.3 label guard does *not* cover this — the guard protects containers, and this is an HTTP call to a hostname. **This is the single most valuable thing this plan adds beyond the spec.** A fourth, `HERMES_TAILNET_IP`, is inert only because `ports: !reset []` removes the publish that reads it; the manifest records it anyway, because "inert because another mechanism happens to remove it" is exactly the kind of coupling that breaks silently.

**N2 — the must-override list becomes machine-readable, and the renderer is checked against it.** Chunk 2's ledger flagged this and it is still open: "a blockquote in the spec cannot fail a build." Task 2 introduces `branch-env.yaml` — every variable, how it is derived, and whether omission is fatal — plus a test that fails if a rendered branch `.env` misses any entry. Adding a hostname-bearing variable to `.env.template` without adding it to the manifest is what this must catch.

**N3 — `compose.branch.yml` must be generated, not hand-written, and the enumeration must be self-checking.** Spec §4.2 states the `!reset` rule but its own count has gone stale twice. Worse, the per-developer agent services are themselves generated from `developers.yaml`, so a hand-written override goes stale the moment a developer is added — and the failure mode is a **daemon-global `container_name` collision**, i.e. a branch that cannot start, or (with ports) a branch that steals production's published port. Task 3 generates the file from the resolved compose config, commits it (trap 4), and adds a coverage gate: *every* service the resolved config shows declaring `container_name` or `ports` must be reset by the overlay, and the test must be red if one is missing.

**N4 — `SSH_DOMAIN` in a branch's Forgejo still advertises production's hostname.** `compose.yml` overrides `FORGEJO__server__ROOT_URL` and `FORGEJO__server__DOMAIN` but not `SSH_DOMAIN`, and the seeded `app.ini` carries production's. Consequence: a branch's Forgejo UI offers `ssh://…@superserver.tailc67a98.ts.net:222/…` as the clone URL. **This is left alone deliberately** — a branch publishes no ports, so its SSH port does not exist, and an SSH clone URL pointing at production is the *safe* direction of the §5.4 cross-wiring concern. Recorded so the next reader does not "fix" it into a hazard.

**N5 — the branch's `/agent` redirect (the admin Hermes dashboard) is dead, and that is acceptable.** The Caddyfile's `handle /agent { redir https://{$DOMAIN_NAME}:{$HERMES_SERVE_PORT}/ }` points at a `tailscale serve` mapping that exists only on the host for production. A branch's sidecar runs no `serve`. Per-developer `/agent/<user>/` routes are unaffected — they are generated into `Caddyfile.d/agents.conf` and proxied in-netns. `BRANCH-ACCESS.md` must say so rather than print a URL that 502s.

**N6 — the "seed does not mutate production" invariant cannot be a naive tree checksum.** Production is *live*: its WAL files change on their own, and a read-only `VACUUM INTO` legitimately rewrites `-shm`. A test that checksums the whole tree before and after a seed is flaky in one direction and blind in the other. Task 5 defines the invariant precisely — the main `.db` files, every tracked/bulk file, and every `-wal` must be byte-identical; `*-shm`, `*.lock`, `*.pid` and `*.log` are excluded with the evidence above — and proves the test can fail by mutating the seeder to open the source read-write and checkpoint it.

**N7 — teardown must not depend on the branch worktree still existing.** `docker compose -p X down` needs a compose file; if the worktree was removed by hand (or `up` failed halfway), the project's containers and volumes are still there and still cost disk. Task 9 therefore has two paths — the compose path from the worktree, and a label-driven fallback — and **both** run behind the same project-name guard, because the fallback is the one that manipulates Docker objects by name.

---

## File Structure

| File | Responsibility |
|---|---|
| `aurora-cli/aurora_cli/__init__.py` | **New.** Package marker. |
| `aurora-cli/aurora_cli/identity.py` | **New (Task 1).** Derive production's checkout, project and domain; branch naming and sanitisation; the `br-` namespace. Hardcodes neither `tai-review` nor `aurora`. |
| `aurora-cli/aurora_cli/envfile.py` | **New (Task 2).** Strict `KEY=value` parse/render; branch `.env` rendering driven by `branch-env.yaml`. |
| `aurora-cli/aurora_cli/overlay.py` | **New (Task 3).** Render `compose.branch.yml` from the resolved compose config. |
| `aurora-cli/aurora_cli/exclusions.py` | **New (Task 4).** `branch-services.yaml` loading, transitive `also_exclude` closure, `on_exclude.env` rewiring, profile emission. |
| `aurora-cli/aurora_cli/seed.py` | **New (Tasks 5–6).** `SeedStrategy` Protocol, `get_seeder()`, `FileCopySeeder`; SQLite snapshotting, reflink copy, volume seeding, Postgres dump/restore. |
| `aurora-cli/aurora_cli/guards.py` | **New (Task 9).** Production-safety assertions shared by every destructive path. |
| `aurora-cli/aurora_cli/branch.py` | **New (Tasks 8–10).** `up`, `down`, `ls`, `access`, `shell`, `rebuild`. |
| `aurora-cli/aurora_cli/access_doc.py` | **New (Task 10).** `BRANCH-ACCESS.md` and `.worktrees/INDEX.md` rendering. |
| `aurora-cli/aurora_cli/mcp.py` | **New (Task 11).** Dependency-free stdio JSON-RPC MCP facade. |
| `aurora-cli/aurora_cli/__main__.py` | **New (Task 1, extended per task).** argparse entry point. |
| `aurora` | **New (Task 1).** Repo-root shim: `exec .venv/bin/python -m aurora_cli "$@"`. |
| `branch-env.yaml` | **New (Task 2).** The machine-readable must-override manifest (N2). |
| `branch-services.yaml` | **New (Task 4).** The exclusion manifest (spec §7.2). |
| `compose.branch.yml` | **New (Task 3), GENERATED and COMMITTED.** The only config difference between production and a branch. |
| `hooks/pre-push` | **New (Task 7).** Installed into each branch worktree; rejects pushes to a branch Forgejo (spec §5.4). |
| `tests/branch_harness.py` | **New (Task 0).** Branch-stack test harness: production snapshot/assert-unchanged, throwaway branch projects, teardown. |
| `tests/test_branch_harness.py` | **New (Task 0).** Pins the harness — it must fail when production *is* disturbed. |
| `tests/test_branch_overlay.py` | **New (Task 3).** Overlay drift + `!reset` coverage gates. |
| `tests/test_branch_env.py` | **New (Task 2).** Must-override manifest conformance. |
| `tests/test_branch_isolation.py` | **New (Task 9).** Teardown-cannot-reach-production invariants. |
| `tests/test_branch_acceptance.py` | **New (Task 12).** End-to-end acceptance. |
| `aurora-cli/tests/…` | **New.** Unit tests for each module above. |
| `dev-administration/dev_administration/cli.py` | **Modified (Task 3).** `render-branch-override` alongside `render-agents`. |
| `docs/superpowers/plans/2026-07-29-chunk3-ephemeral-branching.md` | This plan. |
| `docs/implementations/2026-07-29-chunk3-ephemeral-branching.md` | **New (Task 12).** Required by the practices doc; updated every iteration. |
| `docs/testing/2026-07-29-chunk3-ephemeral-branching.md` | **New (Task 12).** |
| `docs/issues/chunk3-spec-deltas.md` | **New (Task 12).** Spec claims Chunk 3 invalidated. |
| `docs/post-implementation-steps.md` | **Modified (Task 12).** The Tailscale auth-key credential, and MCP registration. |

---

## Decisions made while writing this plan

Recorded with their reasoning, because the spec did not settle them.

**D-A — `aurora_cli` is stdlib + `pyyaml`, driven by `argparse`, and runs on the host.** `dev_administration` uses typer, but `aurora branch up` must run *before* a branch worktree has a venv, and must be usable from a bare `python3` on the host. Every extra runtime dependency is another thing that must exist in three places (host venv, the `aurora-cli:local` image, a fresh worktree). `pyyaml` is unavoidable — `developers.yaml`, `branch-services.yaml` and `branch-env.yaml` are YAML and Compose is YAML — and it is already installed in the worktree venv. Nothing else is.

**D-B — the MCP facade is hand-written JSON-RPC over stdio, with no SDK.** MCP's stdio transport is line-delimited JSON-RPC 2.0; `initialize`, `tools/list` and `tools/call` are the whole surface §7.3 needs. An SDK dependency would violate D-A for four methods, and — more importantly — a hand-written server is testable by writing bytes to a pipe, with no network and no version drift. Task 11 pins the wire format against a recorded transcript rather than against a library's behaviour.

**D-C — the Tailscale sidecar runs in kernel mode (`TS_USERSPACE=false`), with `TS_STATE_DIR` on a project-scoped named volume, and `TS_ACCEPT_DNS=false`.** Kernel mode is what puts a real `tailscale0` in the shared netns so Caddy's bind on `:443` receives tailnet traffic (verified above; userspace mode would require `TS_DEST_IP` or a `serve` config and would not). A state *volume* rather than `mem:` means a container restart re-uses the node identity instead of re-registering and possibly landing on `aurora-<name>-1`; because the volume is project-scoped, `down -v` deletes it and the ephemeral node deregisters exactly as §4.4 requires. `TS_ACCEPT_DNS=false` is load-bearing: accepting MagicDNS replaces `127.0.0.11` in the shared netns and kills the Docker service DNS that every `*_UPSTREAM` depends on.

**D-D — the auth key is supplied, not minted.** Minting an ephemeral key programmatically needs a Tailscale API key or an OAuth client, neither of which exists on this host and neither of which an agent can create. `branch up` reads `AURORA_TS_AUTHKEY` from the environment or `TS_AUTHKEY_BRANCH` from production's `.env`, and **fails with an explicit message** if neither is set. The credential is a human step (Task 12 writes it into `docs/post-implementation-steps.md`). The compose overlay declares `${TS_AUTHKEY:?…}`, so a branch with no key is a hard config error rather than a stack that starts logged out (trap 9).

**D-E — AFFiNE Postgres is restored after `up`, not through an init script.** `pg_restore --clean --if-exists` into a running, healthy branch Postgres is one code path with one failure mode, and it works whether or not the data directory was already initialised. An `/docker-entrypoint-initdb.d` script would only run on a pristine volume, would need an extra bind in the overlay, and would silently do nothing on a re-seed. `up` therefore starts `postgres` (and `redis`) first, restores, then brings up the rest — so `affine_migration` runs against restored data rather than an empty schema.

**D-F — branch worktrees stay at `<production-root>/.worktrees/<name>`.** `.worktrees/` is gitignored and already inside the tree production's Hermes mounts, which is precisely what spec §7.4 relies on for "the original agent reads every branch's access doc with no extra wiring". The cost is real and should be known: production's Hermes bind is `.:/opt/data/workspace/aurora`, so every branch's seeded state — ~2.6 GB of `.hermes` per branch — appears inside production Hermes' workspace tree. It is reflinked, so it costs almost no disk, but anything that *walks* that tree now walks it. This is the same hazard already recorded as Chunk 2's open finding F6, one level deeper.

---

## Task 0: The branch-stack test harness

**Files:**
- Create: `tests/branch_harness.py`
- Create: `tests/test_branch_harness.py`

**Interfaces:**
- Consumes: `tests/conftest.py`'s `PRODUCTION_PROJECT`, `project_containers()`, `inspect_container()`.
- Produces: `production_snapshot()`, `assert_production_unchanged(before)`, `branch_projects()`, the `throwaway_branch` fixture, and `PROD_VOLATILE_SUFFIXES`. Every later task's isolation assertions build on these; nothing else in the plan is allowed to reimplement them.

**Context the implementer needs:** Chunk 3 is the first chunk whose tests start and stop real containers. Two things have to be true before that is safe. First, "production was not disturbed" must be a *measured* fact with a single implementation — three tasks each writing their own version is exactly how Chunk 2's `project_services`/`find_service_container` pair drifted twice. Second, a test that brings a branch stack up must be unable to bring production down even if its own arguments are wrong.

The harness must also be *self-testing*. Chunk 2 shipped a skip guard that made a Critical-defect gate inert at every invocation in the plan and nobody noticed, because a skip is not a failure. So `test_branch_harness.py` does not test the stack; it tests the harness, by feeding `assert_production_unchanged` a doctored snapshot and requiring it to raise.

`docker compose --profile '*' down -v --remove-orphans` on a throwaway project was verified during planning to remove 3 containers, 2 volumes and 1 network while leaving production's 12 containers untouched.

- [ ] **Step 1: Confirm the baseline before changing anything**

```bash
cd ~/Desktop/tai-review/.worktrees/chunk3
git log --oneline -1
AURORA_PROJECT=tai-review .venv/bin/python -m pytest -q 2>&1 | tail -3
```

Expected: `e085c75 docs: rewrite README for Aurora, and record the rename mapping`, then `129 passed, 1 xfailed`. If the counts differ, **stop and report** — every later expectation in this plan is stated as a delta from 129/1.

- [ ] **Step 2: Write the harness**

Create `tests/branch_harness.py`. It must provide:

- `PROD_VOLATILE_SUFFIXES = ("-shm", ".lock", ".pid", ".log")` — with a comment recording the measured reason (a read-only `VACUUM INTO` against `.hermes/state.db` left `state.db` and `state.db-wal` byte-identical and rewrote `state.db-shm`; `-shm` is the mmap'd WAL index, not content).
- `production_snapshot() -> dict` capturing, for `PRODUCTION_PROJECT`: every container's **ID** (not name — a recreate keeps the name and changes the ID, and that is precisely the event to catch), its `State.StartedAt`, the full list of `docker volume ls -q`, and the full list of `docker network ls -q`. It must `assert` the container map is non-empty with a message naming `AURORA_PROJECT` (trap 2).
- `assert_production_unchanged(before: dict) -> None` re-snapshotting and diffing, raising `AssertionError` naming the exact object that changed.
- `branch_projects() -> set[str]` — every compose project on the daemon whose name starts with `br-`.
- `assert_not_production(project: str)` — refuses any project equal to `PRODUCTION_PROJECT` or not starting with `br-`.
- a `throwaway_branch` pytest fixture yielding a unique `br-pytest-<pid>-<n>` project name and, on teardown, running `docker compose --profile '*' -p <name> down -v --remove-orphans` from a tmp dir plus a label-driven sweep of anything left, then `assert_production_unchanged`.

- [ ] **Step 3: Write the tests that pin the harness**

Create `tests/test_branch_harness.py` with at least:

- `test_snapshot_refuses_an_empty_production` — monkeypatch `PRODUCTION_PROJECT` to a name with no containers; `production_snapshot()` must raise, and the message must mention `AURORA_PROJECT`.
- `test_assert_unchanged_detects_a_removed_container` / `…_a_recreated_container` / `…_a_removed_volume` — build a real snapshot, delete one entry / change one ID / drop one volume from the *copy*, and require `assert_production_unchanged` to raise for each.
- `test_assert_not_production_refuses_production_and_bare_names` — `PRODUCTION_PROJECT`, `""`, `"aurora"`, `"tai-review"` and `"notbr-x"` all raise; `"br-x"` does not. **Both** production names appear here on purpose: the module must be wrong under neither the pre- nor the post-rename world.
- `test_throwaway_fixture_leaves_no_residue` — uses the fixture to `up` a single-container project (`image: alpine`, `command: sleep 300`), asserts the container exists, and after the fixture tears down asserts zero containers, volumes and networks carry that project label.

- [ ] **Step 4: Prove the tests can fail**

Run each mutation, confirm the named test goes red, then revert:

| # | Mutation | Must redden |
|---|---|---|
| M1 | `assert_production_unchanged` returns immediately | all three `…_detects_…` tests |
| M2 | `production_snapshot` compares container **names** instead of IDs | `…_detects_a_recreated_container` |
| M3 | `production_snapshot` drops the non-empty assertion | `test_snapshot_refuses_an_empty_production` |
| M4 | `assert_not_production` checks only `!= PRODUCTION_PROJECT` (drops the `br-` prefix rule) | `…_refuses_production_and_bare_names` |
| M5 | the fixture's teardown drops `--profile '*'` | `test_throwaway_fixture_leaves_no_residue`, if the probe project declares a profiled service — **add one**, otherwise this mutation survives and trap 3 is unguarded |

Record the transcript. **M5 is the one that matters**: the fixture is what every later task trusts to clean up, and profiled services are exactly what it is most likely to miss.

- [ ] **Step 5: Run the suite and commit**

```bash
cd ~/Desktop/tai-review/.worktrees/chunk3
AURORA_PROJECT=tai-review .venv/bin/python -m pytest -q 2>&1 | tail -3
```

Expected: `129 + N passed, 1 xfailed`, where N is the number of harness tests added. Then commit with `-F` (see Global Constraints).

---

## Task 1: Derive production's identity — never hardcode it

**Files:**
- Create: `aurora-cli/aurora_cli/__init__.py`, `aurora-cli/aurora_cli/identity.py`, `aurora-cli/aurora_cli/__main__.py`
- Create: `aurora-cli/tests/__init__.py`, `aurora-cli/tests/test_identity.py`
- Create: `aurora` (repo-root shim, `chmod +x`)
- Modify: `pytest.ini` (add `aurora-cli/tests` to `testpaths`)

**Interfaces:**
- Consumes: `git`, `docker`, `docker compose`.
- Produces: `production_root() -> Path`, `production_project() -> str`, `production_env() -> dict[str,str]`, `production_domain() -> str`, `tailnet_suffix() -> str`, `sanitise_branch_name(raw) -> str`, `branch_project(name) -> str`, `branch_hostname(name) -> str`, `branch_domain(name) -> str`, `BranchPaths`. Every later task resolves production through this module and nothing else.

**Context the implementer needs:** **Chunk 2 Task 12 was never deployed.** Production is compose project `tai-review` in `~/Desktop/tai-review`; the repo *declares* `COMPOSE_PROJECT_NAME=aurora`. The rename is blocked pending the user and may land at any time. Code that hardcodes either name is wrong in one of those two worlds, so this module derives:

1. **Production's checkout** is the **main git worktree** — `git worktree list --porcelain`, first `worktree ` line — resolved with `Path.resolve()`. Verified: from the chunk3 worktree this yields `/var/home/supergoodname77/Desktop/tai-review`. (`git rev-parse --path-format=absolute --git-common-dir` and stripping `/.git` gives the same answer; either is acceptable, the porcelain form is less fragile.)
2. **Production's project name** is `docker compose config --format json | .name` **run in that directory**, with `COMPOSE_PROFILES="*"`. Verified today → `tai-review`; after the rename → `aurora`. Not `docker ps`, because a declaration must be readable even when the stack is down.
3. …but a declared name that matches **no running containers** is the vacuous-gate trap (trap 2) wearing a different hat. `production_project()` therefore **cross-checks**: the running containers labelled with that project must be non-empty *and* their `com.docker.compose.project.working_dir` label must resolve to `production_root()`. If the declaration and the runtime disagree, raise with both values — do not prefer one silently.

**Both sides of every path comparison must be `Path.resolve()`d.** The compose CLI reports `/home/...` where Python resolves `/var/home/...`; this has bitten the project three times.

`sanitise_branch_name` implements §7.1: lowercase, non-alphanumerics collapsed to `-`, leading/trailing `-` stripped, truncated so that `aurora-<name>` fits in a 63-character DNS label. It must be idempotent, must reject an input that sanitises to the empty string, and must return the sanitised form so callers can report when it differs from the input.

- [ ] **Step 1: Write the failing tests first**

`aurora-cli/tests/test_identity.py`, covering at minimum:

- `test_production_root_is_the_main_worktree` — equals `Path("~/Desktop/tai-review").expanduser().resolve()` *computed from `git worktree list`*, not typed as a literal, and asserts it is **not** the current worktree.
- `test_production_project_is_derived_not_hardcoded` — asserts the returned value equals what `docker compose config` reports in `production_root()`, and separately asserts that **neither** `"aurora"` nor `"tai-review"` appears as a string literal anywhere in `identity.py`'s source with docstrings stripped. Reuse `dev_administration`'s `_strip_docstrings` helper rather than writing a second one — Chunk 2 proved a whole-line blanker hides `def f(): "doc"; X = "literal"`, and that implementation blanks by column.
- `test_production_project_refuses_a_declaration_with_no_containers` — monkeypatch the compose-config call to return a fabricated name; must raise, message naming both the declared name and the empty container set.
- `test_production_project_refuses_a_working_dir_mismatch`.
- `test_sanitise_*` — `"Feature/Foo Bar"` → `"feature-foo-bar"`; idempotence; a 90-character input truncates so `len("aurora-" + out) <= 63`; `"///"` raises.
- `test_branch_names_are_namespaced` — `branch_project("x") == "br-x"`; `branch_hostname("x") == "aurora-x"`; `branch_domain("x") == "aurora-x." + tailnet_suffix()`, where the suffix is derived from production's `DOMAIN_NAME` and `tailc67a98.ts.net` is **not** a literal in the module.

- [ ] **Step 2: Implement, then prove the tests can fail**

| # | Mutation | Must redden |
|---|---|---|
| M1 | `production_project()` returns `os.environ["COMPOSE_PROJECT_NAME"]` | `…_is_derived_not_hardcoded` (the worktree's `.env` says `aurora`, production is `tai-review`) |
| M2 | plant `_FALLBACK = "tai-review"` as executable code in `identity.py` | the literal-scan assertion |
| M3 | plant the same literal inside a docstring | must **stay green** — otherwise the scan is over-eager and will be neutered by the first person it annoys |
| M4 | drop the non-empty-containers cross-check | `…_refuses_a_declaration_with_no_containers` |
| M5 | compare the `working_dir` label as a raw string instead of `Path.resolve()`ing both sides | `test_production_root_is_the_main_worktree` or the mismatch test — this is the `/home` → `/var/home` trap and it **must** be covered by a test, not by a comment |
| M6 | `sanitise_branch_name` truncates to 63 instead of `63 - len("aurora-")` | the length test |

- [ ] **Step 3: Wire the entry point**

`aurora-cli/aurora_cli/__main__.py` gets an argparse root with `branch` and `mcp` subcommands; at this task only `aurora branch ls` need do anything, and it may print the derived identity. The repo-root `aurora` shim:

```sh
#!/usr/bin/env sh
# Host-side entry point. Runs from the production checkout OR any worktree.
here=$(cd "$(dirname "$0")" && pwd)
exec "${AURORA_PYTHON:-$here/.venv/bin/python}" -m aurora_cli "$@"
```

with `PYTHONPATH` handled by a `conftest.py`-independent mechanism — add `aurora-cli` to `sys.path` inside `__main__.py` via `Path(__file__).resolve().parents[2]`, and to `pytest.ini` via `testpaths`.

```bash
cd ~/Desktop/tai-review/.worktrees/chunk3
./aurora branch ls
```

Expected: it prints the derived production project as **`tai-review`** and production's root as `/var/home/supergoodname77/Desktop/tai-review`, from a worktree whose own `.env` says `aurora`. That divergence is the whole point of the task; record the output in the report.

- [ ] **Step 4: Suite and commit**

`AURORA_PROJECT=tai-review .venv/bin/python -m pytest -q` — expected: Task 0's total plus the new identity tests, still `1 xfailed`, zero failures. Commit with `-F`.

---

## Task 2: The must-override manifest and the branch `.env` renderer

**Files:**
- Create: `branch-env.yaml`
- Create: `aurora-cli/aurora_cli/envfile.py`
- Create: `aurora-cli/tests/test_envfile.py`
- Create: `tests/test_branch_env.py`

**Interfaces:**
- Consumes: Task 1's identity module.
- Produces: `parse_env(text) -> dict`, `render_env(pairs) -> str`, `REQUIRED: list[Requirement]` loaded from `branch-env.yaml`, `render_branch_env(name, *, devs, authkey, exclusions_env) -> str`, `missing_overrides(text, name) -> list[str]`.

**Context the implementer needs:** A branch's `.env` is rendered **from production's**, so anything not explicitly overridden is **inherited**, and omission is invisible rather than an error. That inheritance already produced one corrected spec defect (`COMPOSE_PROFILES`, which would have started every developer's agent in every branch). Finding N1 above shows the spec's list is *still* short by three variables that embed production's hostname as a literal:

```
FORGEJO_URL=https://superserver.tailc67a98.ts.net/git
AFFINE_SERVER_EXTERNAL_URL=https://superserver.tailc67a98.ts.net/affine
AURORA_PROFILE_URL=https://superserver.tailc67a98.ts.net/git/supergoodname77/aurora-agent.git
```

`FORGEJO_URL` is the dangerous one: `dev-admin reconcile` uses it to create OAuth applications, so a branch that inherits it **writes into production's Forgejo**. The §5.3 container-label guard does not cover this, because it is an HTTP call to a hostname rather than an operation on a container.

`branch-env.yaml` is the machine-readable list Chunk 2's ledger asked for. Shape:

```yaml
# Every variable a branch .env MUST override, and how it is derived.
# A branch .env is rendered FROM production's, so anything absent here is
# INHERITED — and inheritance failures are silent. tests/test_branch_env.py
# fails if a rendered branch .env misses any entry, and if any variable in
# production's .env whose VALUE contains production's domain is not listed.
variables:
  - name: COMPOSE_PROJECT_NAME
    derive: branch_project          # br-<name>
    fatal: true
    why: "Without it the branch adopts production's project and `down -v` reaches production's volumes."
  - name: COMPOSE_PROFILES
    derive: agent_profiles          # agent-<user>, or "" for --devs none
    fatal: true
    why: "Inherited `agents` starts EVERY developer's agent, contradicting D7."
  - name: DOMAIN_NAME
    derive: branch_domain
    fatal: true
  - name: TS_HOSTNAME
    derive: branch_hostname
    fatal: true
  - name: TS_AUTHKEY
    derive: ephemeral_authkey
    fatal: true
    secret: true
  - name: AGENT_UPSTREAM_MODE
    literal: service
    fatal: true
    why: "published mode points Caddy at 127.0.0.1 ports that do not exist in the sidecar netns; the routes then 502 silently."
  - name: AFFINE_UPSTREAM
    literal: affine:3010
    fatal: true
  - name: FORGEJO_UPSTREAM
    literal: forgejo:3000
    fatal: true
  - name: FJELL_UPSTREAM
    literal: fjell:9080
    fatal: true
  - name: FORGEJO_URL
    derive: branch_url
    suffix: /git
    fatal: true
    why: "N1. dev-admin creates OAuth apps here; inherited, a branch reconciles into PRODUCTION's Forgejo."
  - name: AFFINE_SERVER_EXTERNAL_URL
    derive: branch_url
    suffix: /affine
    fatal: true
  - name: AURORA_PROFILE_URL
    derive: branch_url
    suffix: /git/supergoodname77/aurora-agent.git
    fatal: true
  - name: HERMES_TAILNET_IP
    literal: 127.0.0.1
    fatal: false
    why: "Inert only because `ports: !reset []` removes the publish that reads it. Listed so the coupling is written down rather than assumed."
```

`parse_env`/`render_env` must enforce strict `KEY=value` (trap 7): no whitespace around `=`, comments and blank lines preserved on round-trip, and a value containing a newline rejected. Production's `.env` is 11 KB and ~260 lines, most of it commented-out Odysseus configuration containing `=` inside comment text — the parser must not be fooled by it, and the renderer must not reformat it.

- [ ] **Step 1: Write the failing tests**

`aurora-cli/tests/test_envfile.py`:
- round-trip of production's real `.env`: `render_env(parse_env(text))` preserves every non-comment `KEY=value` line and every comment line, verified against the real file.
- `KEY = value` with spaces is **rejected** on parse with a message naming `docker run --env-file`.
- a rendered branch `.env` passes the same predicate `tests/test_repo_conformance.py::test_dotenv_files_use_strict_key_equals_value` uses — import it, do not restate it.

`tests/test_branch_env.py` (the conformance half):
- `test_rendered_branch_env_sets_every_required_variable` — renders for a fake branch and asserts `missing_overrides(...) == []`.
- `test_every_fatal_variable_is_actually_different_from_production` — for each `fatal: true` entry, the rendered value must **differ** from production's. This is what catches a "derivation" that silently returns the inherited value.
- `test_no_inherited_value_contains_productions_domain` — scan the rendered `.env` for `production_domain()`; any hit that is not in an explicit `ALLOWED_PRODUCTION_REFERENCES` set fails, naming the variable. **This is the test that finds the next N1 automatically**, and it is the reason the manifest exists.
- `test_manifest_covers_every_hostname_bearing_variable_in_production_env` — the inverse direction: any variable in production's `.env` whose value contains production's domain and is not listed in `branch-env.yaml` fails the test. Adding such a variable to `.env.template` later then fails here rather than in a branch.

- [ ] **Step 2: Implement and prove the tests can fail**

| # | Mutation | Must redden |
|---|---|---|
| M1 | delete the `COMPOSE_PROFILES` entry from `branch-env.yaml` | `…_sets_every_required_variable` |
| M2 | delete the `FORGEJO_URL` entry | `…_sets_every_required_variable` **and** `test_no_inherited_value_contains_productions_domain` — two independent detectors, on purpose |
| M3 | make `branch_url` return production's URL unchanged | `…_is_actually_different_from_production` |
| M4 | append `SOMETHING=https://<production domain>/x` to a copy of production's `.env` used as the render source | `…_covers_every_hostname_bearing_variable_in_production_env` |
| M5 | `render_env` emits `KEY = value` | the strict-format test |
| M6 | `AGENT_UPSTREAM_MODE` reverts to `published` | `…_is_actually_different_from_production` |

M2 and M4 are the ones to run twice: they are the only defence against the *next* hostname-bearing variable somebody adds.

- [ ] **Step 3: Suite and commit**

`AURORA_PROJECT=tai-review .venv/bin/python -m pytest -q`. Commit with `-F`.

---

## Task 3: Generate `compose.branch.yml`, and keep its enumeration honest

**Files:**
- Create: `compose.branch.yml` (generated, **committed**)
- Create: `aurora-cli/aurora_cli/overlay.py`, `aurora-cli/tests/test_overlay.py`
- Create: `tests/test_branch_overlay.py`
- Modify: `dev-administration/dev_administration/cli.py` (a `render-branch-override` command, mirroring `render-agents`)

**Interfaces:**
- Consumes: Task 1's identity; `docker compose config` over `compose.yml` with `COMPOSE_PROFILES="*"`.
- Produces: `render_overlay(config: dict) -> str` and the committed file. Task 8 invokes `docker compose -f compose.yml -f compose.branch.yml`.

**Context the implementer needs:** Spec §4.2 states the rule ("`container_name: !reset null` on *every* service that declares one") and its own count has already gone stale twice. The agent services are themselves generated from `developers.yaml`, so a hand-maintained overlay is stale the moment a developer is added. The failure is not cosmetic: `container_name` opts a service **out** of project namespacing, so an unreset one is a daemon-global name and the branch stack fails to start; an unreset `ports` entry makes a branch bind a host port production is already using — `agent-authz` (9140), `arcadedb` (2424/2480) and `fjell` (9080) are live examples that a naive overlay would miss.

Probed on this host, v5.3.1, while writing this plan (reproduce it before trusting it):

- `container_name: !reset null` and `ports: !reset []` work **across an `include:` boundary** — `affine` and `postgres` come from `affine/compose.yml`, `hermes-testuser` from `compose.agents.yml`, and all three were cleared by a top-level `-f` overlay.
- `volumes: !override [...]` replaces a service's volume list wholesale, which is how Caddy's host `/var/run/tailscale` bind is swapped for the sidecar's socket volume.
- `${TS_AUTHKEY:?message}` makes a missing key a hard `docker compose config` error.
- Resolved services declaring `container_name` today: `affine`, `affine_migration`, `dev-admin`, `forgejo`, `forgejo-mcp`, `hermes`, `postgres`, `redis`, plus one per developer. Publishing ports today: `affine`, `agent-authz`, `arcadedb`, `fjell`, `forgejo`, `hermes`, plus one per developer.

The generated file's body:

```yaml
# GENERATED by `dev-admin render-branch-override` — do not edit.
# The ONLY configuration difference between production and a branch (spec D8).
# Regenerate after ANY change to compose.yml, affine/compose.yml,
# compose.agents.yml or developers.yaml. tests/test_branch_overlay.py fails if
# this file and the resolved config disagree.

services:
  tailscale:
    image: tailscale/tailscale:latest
    hostname: ${TS_HOSTNAME:?a branch needs TS_HOSTNAME}
    environment:
      - TS_AUTHKEY=${TS_AUTHKEY:?a branch needs an ephemeral Tailscale auth key}
      - TS_HOSTNAME=${TS_HOSTNAME}
      - TS_STATE_DIR=/var/lib/tailscale
      - TS_SOCKET=/var/run/tailscale/tailscaled.sock
      # Kernel mode, NOT userspace: Caddy shares this netns and binds :443
      # there, which only receives tailnet traffic if a real tailscale0
      # interface exists in the namespace.
      - TS_USERSPACE=false
      # Load-bearing. Accepting MagicDNS rewrites resolv.conf in the SHARED
      # netns to 100.100.100.100, removing Docker's 127.0.0.11 — and every
      # *_UPSTREAM in a branch is a Docker service name.
      - TS_ACCEPT_DNS=false
    volumes:
      - tailscale_state:/var/lib/tailscale
      - tailscale_sock:/var/run/tailscale
    devices:
      - /dev/net/tun:/dev/net/tun
    cap_add: [NET_ADMIN, NET_RAW]
    restart: unless-stopped

  caddy:
    network_mode: service:tailscale
    depends_on:
      tailscale:
        condition: service_started
    volumes: !override
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - ./Caddyfile.d:/etc/caddy/Caddyfile.d
      # The SIDECAR's socket, not the host's. Read-only is proven sufficient
      # for cert issuance by production, which mounts the host socket :ro.
      - tailscale_sock:/var/run/tailscale:ro
      - caddy_data:/data
      - caddy_config:/config

  # --- generated: one block per service declaring container_name or ports ---
  forgejo:
    container_name: !reset null
    ports: !reset []
  # … etc, emitted in sorted order …

volumes:
  tailscale_state:
  tailscale_sock:
```

`caddy_data` is **not** seeded and needs no entry: it is a project-scoped named volume, so a branch gets an empty one and its own tailscaled issues its own certificate (spec §6.4).

- [ ] **Step 1: Write the failing tests**

`tests/test_branch_overlay.py`:
- `test_overlay_is_not_stale` — regenerate in memory from the live resolved config and compare **bytes** with the committed file, exactly as `test_agents_compose_matches_developers_yaml` does.
- `test_every_container_name_declaration_is_reset` — resolve `compose.yml` with `COMPOSE_PROFILES="*"`, collect every service with a truthy `container_name`, and assert the overlay resets each. Failure message must name the missing services and say *why* (daemon-global collision).
- `test_every_published_port_is_reset` — same shape for `ports`.
- `test_the_overlaid_config_declares_no_container_name_and_no_ports` — the empirical version: run `docker compose -f compose.yml -f compose.branch.yml config --format json` with `COMPOSE_PROJECT_NAME=br-probe`, `COMPOSE_PROFILES='*'`, `TS_HOSTNAME=aurora-probe`, `TS_AUTHKEY=tskey-fake` and assert **no** service has a `container_name` and **no** service has `ports`. This is the one that cannot be satisfied by a bookkeeping error, and it must assert the service set is non-empty first (trap 2).
- `test_caddy_is_flipped_into_the_sidecar_netns` — `network_mode == "service:tailscale"`, the host `/var/run/tailscale` bind is **gone**, and `tailscale_sock` is mounted.
- `test_a_branch_without_an_authkey_is_a_config_error` — the same config invocation with `TS_AUTHKEY` unset must exit non-zero with a message naming `TS_AUTHKEY`.

- [ ] **Step 2: Implement, generate, commit the artifact, and prove the tests can fail**

| # | Mutation | Must redden |
|---|---|---|
| M1 | delete the `hermes` block from `compose.branch.yml` | `…_container_name_declaration_is_reset` **and** `…_overlaid_config_declares_no_container_name…` |
| M2 | delete the `arcadedb` block | `…_published_port_is_reset` + the empirical test (`arcadedb` declares ports but **no** `container_name`, so it is the case a container_name-only gate misses) |
| M3 | add a service to `developers.yaml`, regenerate `compose.agents.yml` **but not** the overlay | `test_overlay_is_not_stale` — then revert both files |
| M4 | change `ports: !reset []` to `ports: []` on one service | must still redden something; if nothing catches it, the empirical test is reading the wrong key |
| M5 | `TS_ACCEPT_DNS=true` | nothing yet — record this honestly as **unpinned at this task**; Task 12's acceptance run is where it becomes observable, and the brief for Task 12 names it |
| M6 | drop `:?` from `TS_AUTHKEY` | `…_without_an_authkey_is_a_config_error` |

- [ ] **Step 3: Suite and commit**

`AURORA_PROJECT=tai-review .venv/bin/python -m pytest -q`. `git add compose.branch.yml` — **it must be committed** (trap 4: a `-f` pointing at a missing file is a hard error, and a fresh worktree has only what git tracks). Commit with `-F`.

---

## Task 4: The exclusion manifest and its transitive closure

**Files:**
- Create: `branch-services.yaml`
- Create: `aurora-cli/aurora_cli/exclusions.py`, `aurora-cli/tests/test_exclusions.py`

**Interfaces:**
- Consumes: the resolved compose config; Task 2's env rendering.
- Produces: `load_manifest()`, `closure(names) -> set[str]`, `validate_excludable(names)`, `profiles_for(excluded) -> str`, `env_overrides_for(excluded) -> dict`.

**Context the implementer needs:** Spec §7.2, strengthened 2026-07-28. The closure is **mandatory, not tidiness**: verified on v5.3.1, a service whose `depends_on` target sits behind an inactive profile makes the *whole project invalid* — `service "app" depends on undefined service "db": invalid compose project`, exit 1. Excluding `forgejo` without also excluding `forgejo-mcp` does not leave a dangling reference for later; it fails the next `docker compose` invocation outright.

The manifest uses **service keys**, not `container_name` values. The spec's own example was wrong about this once and was corrected: the in-tree `affine/compose.yml` declares `affine`, `affine_migration`, `redis`, `postgres` — the `affine_*` names in `docker ps` are `container_name` values and will not match.

Exclusion is expressed as Compose `profiles`, so Compose performs the omission natively (D9). Note the interaction with `COMPOSE_PROFILES`, which Task 2 already sets to `agent-<user>`: the branch's profile string is the **union** of the agent profile and any exclusion profiles, and the overlay adds `profiles:` to excluded services. Get this wrong and either every developer's agent starts or the exclusion silently does nothing.

Starting content (keep it small; the point is that adding an entry is YAML, not code):

```yaml
services:
  forgejo:
    excludable: true
    also_exclude: [forgejo-mcp]
    on_exclude:
      env:
        FORGEJO_URL: "{production_url}/git"      # point the branch at prod's Forgejo
  affine:
    excludable: true
    also_exclude: [affine_migration, postgres, redis]
  arcadedb:
    excludable: true
  agent-authz:
    excludable: false
    why: "Caddy's forward_auth targets it; without it every agent route fails closed."
```

- [ ] **Step 1: Write the failing tests**

- `test_closure_is_transitive` — a three-level chain in a fixture manifest closes fully; a cycle terminates rather than recursing.
- `test_excluding_forgejo_pulls_in_forgejo_mcp` — against the **real** manifest.
- `test_manifest_names_only_real_service_keys` — every key and every `also_exclude` entry must appear in the resolved `docker compose config --services` output with `COMPOSE_PROFILES="*"`. This is what stops the `affine_server`-vs-`affine` mistake recurring. Assert the service list is non-empty first.
- `test_excluding_without_the_closure_is_a_compose_error` — the empirical proof: generate an overlay excluding `forgejo` **but not** `forgejo-mcp`, run `docker compose … config`, assert exit non-zero and `depends on undefined service` in stderr. Then with the closure, assert exit 0. Without this test the closure is justified only by prose.
- `test_a_non_excludable_service_is_refused` — `--without agent-authz` raises, message quoting the manifest's `why`.
- `test_on_exclude_env_is_applied` — excluding `forgejo` yields `FORGEJO_URL` pointing at **production's** domain, and the value is derived from Task 1, not a literal.

- [ ] **Step 2: Implement and prove the tests can fail**

| # | Mutation | Must redden |
|---|---|---|
| M1 | `closure()` returns its input unchanged | `…_is_transitive`, `…_pulls_in_forgejo_mcp`, `…_without_the_closure_is_a_compose_error` |
| M2 | `closure()` recurses one level only | `…_is_transitive` |
| M3 | rename `affine_migration` to `affine_migration_job` in the manifest | `…_names_only_real_service_keys` |
| M4 | `validate_excludable` accepts anything | `…_non_excludable_service_is_refused` |
| M5 | `profiles_for` returns `""` | the compose-error test (nothing gets excluded, so the run succeeds where it must fail) — if it stays green, the test is asserting on the wrong artifact |

- [ ] **Step 3: Suite and commit**

`AURORA_PROJECT=tai-review .venv/bin/python -m pytest -q`. Commit with `-F`.

---

## Task 5: Seeding, part 1 — the seam, and host-path state

**Files:**
- Create: `aurora-cli/aurora_cli/seed.py`, `aurora-cli/tests/test_seed.py`

**Interfaces:**
- Consumes: Task 1's identity.
- Produces: `SeedStrategy` Protocol, `get_seeder(name="filecopy")`, `FileCopySeeder.seed_paths(src_root, dst_root, *, report)`, `snapshot_sqlite(src, dst)`, `enumerate_sqlite(root)`, and `SeedReport`.

**Context the implementer needs:** Spec §6. Measured on this host while writing this plan — reproduce before trusting:

- `sqlite3.connect("file:<abs>?mode=ro", uri=True).execute("VACUUM INTO ?", (dst,))` against production's **live** `forgejo/gitea/gitea.db` produced a 2.4 MB consistent snapshot in **0.02 s** and left `gitea.db`, `gitea.db-wal` and `gitea.db-shm` **byte-identical**.
- The same against `.hermes/state.db` (47 MB, live `-wal`/`-shm`) took **0.05 s**, left `state.db` and `state.db-wal` byte-identical, and **rewrote `state.db-shm`**. `-shm` is the mmap'd WAL index, not content. **The no-mutation invariant must exclude `*-shm`** — see N6. A test that does not exclude it fails against a correct seeder, which is the same defect shape as Chunk 2's `PRODUCTION_PROJECT` comparison that went red exactly when a branch was right.
- `mode=ro` is not a nicety. It is what makes "seeding only ever reads production" (§6.6) a property of the *connection* rather than of the code's good intentions: SQLite refuses the write rather than performing it.
- Production's SQLite files, found by recursive enumeration: `forgejo/gitea/gitea.db`; `.hermes/state.db`, `kanban.db`, `projects.db`, `verification_evidence.db`, `cron/executions.db`, `mnemosyne/data/mnemosyne.db`. **Six under `.hermes`, at depths 1–3.** The spec said "at least five" and listed four. Enumerate; never hand-maintain.
- `forgejo/ssh/ssh_host_*` are **root-owned mode 600** and unreadable to this user. `cp -a forgejo/` fails there. §6.4 says never clone them anyway — so exclude `forgejo/ssh` explicitly and let Forgejo regenerate. A seeder that merely "ignores errors" would also swallow real failures.
- `.hermes/home/.cache/uv/**` contains **broken symlinks** to container-side paths. `cp -a` preserves them correctly; anything that dereferences will fail.
- `/var/home` is btrfs with 142 G free; `cp -a --reflink=auto` shares extents, so 2.6 GB costs approximately nothing. On a filesystem without reflink the same command still works, slower — which is the whole reason §6.2 chose it.

What is copied, per §6:

| Source | Treatment |
|---|---|
| `forgejo/` minus `ssh/` minus `gitea/gitea.db*` | `cp -a --reflink=auto` (git objects, LFS, attachments, `conf/app.ini` are write-once or config) |
| `forgejo/gitea/gitea.db` | `VACUUM INTO`; the `-wal`/`-shm` are **not** copied |
| `.hermes/` minus every `*.db`, `*.db-wal`, `*.db-shm`, `*.pid`, `*.lock`, `*.sock` | `cp -a --reflink=auto` |
| every `*.db` under `.hermes/` | `VACUUM INTO`, path-preserving |
| `Caddyfile.d/` | **not** copied — regenerated by `reconcile` (§6.5) |
| `agent-authz/data/owners.json` | **not** copied — regenerated (§6.5) |
| `.agent-env/` | **not** copied — OIDC secrets are regenerated against the branch hostname |
| `caddy_data`, `caddy_config` | **never** — project-scoped volumes; the branch gets its own certificate (§6.4) |
| `affine/config/` | copied (`config.json`, `private.key`; root-owned but world-readable) |
| `affine/data/` | **not** copied — root-owned/unreadable; Postgres goes through `pg_dump` in Task 6 |
| `arcadedb/` | **not** copied — the service is `Exited 137` in production and its state is not identity |

`SeedReport` records every decision (path, action, bytes, duration) and is what `BRANCH-ACCESS.md` prints as "what was seeded".

- [ ] **Step 1: Write the failing tests, against a fixture stack**

Do **not** build the primary tests against live production — production is written to while the test runs, so the assertions would be flaky in one direction and blind in the other. Build a `tmp_path` fixture that reproduces the shapes that matter: a WAL-mode SQLite database **with a writer thread committing during the seed**, a nested `*.db`, a broken symlink, a mode-600 file the test cannot read, and a bulk directory.

- `test_snapshot_of_a_database_written_during_the_copy_is_consistent` — the snapshot opens, `PRAGMA integrity_check` returns `ok`, and its row count is one of the committed values (not a torn one).
- `test_seed_does_not_mutate_the_source` — sha256 every source file before and after, excluding `PROD_VOLATILE_SUFFIXES` (Task 0), assert identical. Assert the compared set is non-empty and **includes at least one `.db` and one `-wal`**, or the exclusion list could silently swallow everything.
- `test_enumerate_finds_databases_at_every_depth` — six for a `.hermes`-shaped fixture; then add a seventh at a new depth with a new name and assert it is found without editing the seeder.
- `test_ssh_host_keys_are_not_cloned` and `test_caddy_data_is_not_cloned`.
- `test_broken_symlinks_survive` — the link is copied as a link, and the seed does not fail.
- `test_seed_report_lists_every_action`.
- One live, read-only check: `test_production_gitea_db_snapshots_read_only` — snapshot production's real `gitea.db` into `tmp_path`, assert the copy contains the org `obsidura` and the repo `aurora`, and assert production's `gitea.db` and `gitea.db-wal` sha256 are unchanged. This is the only test that touches production and it is read-only by construction (`mode=ro`).

- [ ] **Step 2: Implement and prove the tests can fail**

| # | Mutation | Must redden |
|---|---|---|
| M1 | `snapshot_sqlite` becomes `shutil.copy2` | `…_written_during_the_copy_is_consistent` (a torn copy fails `integrity_check` or loses the last commit). If it survives, the fixture's writer is not actually writing during the copy — fix the fixture, the test is not real yet. |
| M2 | open the source with `mode=rwc` and `PRAGMA wal_checkpoint(TRUNCATE)` | `test_seed_does_not_mutate_the_source` — **and confirm the `-shm` exclusion did not hide it**; the `-wal` must be what fails |
| M3 | `enumerate_sqlite` uses a hardcoded list of five names | `…_at_every_depth` |
| M4 | drop the `forgejo/ssh` exclusion | `…_ssh_host_keys_are_not_cloned`, and against production it would also raise `Permission denied` |
| M5 | `PROD_VOLATILE_SUFFIXES` widened to include `-wal` | `test_seed_does_not_mutate_the_source` must **still** catch M2. If it does not, the invariant has been hollowed out and N6's precision is lost |
| M6 | `cp` without `--reflink=auto` | nothing (correctness is unchanged) — record as deliberately unpinned; it is a performance property, and Task 12 measures it |

- [ ] **Step 3: Suite and commit**

`AURORA_PROJECT=tai-review .venv/bin/python -m pytest -q`. Commit with `-F`.

---

## Task 6: Seeding, part 2 — agent volumes and AFFiNE Postgres

**Files:**
- Modify: `aurora-cli/aurora_cli/seed.py`
- Modify: `aurora-cli/tests/test_seed.py`

**Interfaces:**
- Consumes: Task 1's identity, Task 5's `snapshot_sqlite`/`SeedReport`.
- Produces: `seed_agent_volume(username, src_project, dst_project)`, `dump_postgres(container) -> bytes`, `restore_postgres(container, dump)`.

**Context the implementer needs:** Two kinds of state live outside the repo tree and cannot be reached with a host-side `cp`.

**Agent homes** are named volumes. Production's are `<project>_hermes-<user>-home` — today `tai-review_hermes-testuser-home`, after the rename `aurora_hermes-testuser-home`, which is exactly why the project prefix comes from Task 1 and is never typed. `/var/lib/docker/volumes/*/_data` is root-owned, so the copy must go through a container that mounts both volumes. Use `python:3.13-slim` and feed it the *same* snapshot logic on stdin, so agent SQLite state gets `VACUUM INTO` for the same reason production's does — a Hermes home is full of live SQLite, and this is the "my login does not work in the branch" failure §6.3 exists to prevent. Do not use `alpine`: busybox `cp` has no `--reflink` and no `sqlite3`.

Compose **adopts** a pre-existing volume that carries `com.docker.compose.project` and `com.docker.compose.volume` labels (trap 6). Seeding therefore happens **before** `up`, by creating the destination volume with the right labels and filling it. Get the labels wrong and Compose creates a second, empty volume and the seed is silently discarded; get the *project* label wrong and the branch writes into production's agent state.

**AFFiNE Postgres.** `affine/data/postgres` is `polkitd:root` mode 700 — unreadable to this user, so a file copy is impossible even before the consistency argument. `docker exec affine_postgres pg_dump -U affine -Fc affine` was measured at **256182 bytes** and is read-only against the live instance. Restore happens after the branch's Postgres is up and healthy (D-E): `docker exec -i <branch postgres> pg_restore -U affine -d affine --clean --if-exists`. `--clean --if-exists` is what makes it idempotent against the schema `affine_migration` may already have created.

The Postgres credentials come from the **branch's** `.env` (`POSTGRES_USER`/`POSTGRES_DB`), which Task 2 renders from production's, so they match. Do not type `affine`.

- [ ] **Step 1: Write the failing tests**

- `test_agent_volume_seed_is_project_scoped` — the destination volume name is `<branch project>_hermes-<u>-home` and the source is `<production project>_hermes-<u>-home`, both derived. Assert that neither production's project name appears as a literal in `seed.py` (reuse the docstring-stripping scan from Task 1).
- `test_agent_volume_seed_refuses_to_write_into_productions_volume` — call with the destination project equal to production's; must raise before any container runs. Assert with a `docker run` double that records invocations, and assert **zero** invocations.
- `test_seeded_volume_carries_the_labels_compose_expects` — after seeding a throwaway volume, `docker volume inspect` shows `com.docker.compose.project=<branch>` and `com.docker.compose.volume=hermes-<u>-home`; then `docker compose create` against a minimal project using it **adopts** it (marker file intact) rather than replacing it.
- `test_agent_volume_databases_are_snapshotted_not_copied` — seed a throwaway source volume containing a WAL-mode DB with an uncheckpointed WAL and no matching `-shm`; the destination's DB must pass `integrity_check` and contain the WAL-only rows.
- `test_postgres_dump_is_read_only` — dump production, then assert production's container ID and `StartedAt` are unchanged (Task 0's snapshot) and the dump is non-empty and begins with the custom-format magic `PGDMP`.
- `test_postgres_restore_is_idempotent` — restore twice into a throwaway Postgres, second run succeeds and row counts match.

Volume-touching tests use Task 0's `throwaway_branch` naming and clean up through it.

- [ ] **Step 2: Implement and prove the tests can fail**

| # | Mutation | Must redden |
|---|---|---|
| M1 | derive the source volume with a hardcoded `aurora_` prefix | `…_is_project_scoped` (production is `tai-review` today — this mutation is what the whole "derive, don't hardcode" constraint exists to catch, and it must fail *now*, not after the rename) |
| M2 | drop the destination-project guard | `…_refuses_to_write_into_productions_volume` |
| M3 | omit `com.docker.compose.volume` from the labels | `…_carries_the_labels_compose_expects` |
| M4 | volume seeding uses plain `cp` for `*.db` | `…_databases_are_snapshotted_not_copied` |
| M5 | `pg_restore` without `--clean --if-exists` | `…_restore_is_idempotent` |
| M6 | `dump_postgres` shells into the branch's Postgres instead of production's | `…_dump_is_read_only` should fail on an empty/missing container; if it passes, the test is not asserting the dump has content |

- [ ] **Step 3: Suite and commit**

`AURORA_PROJECT=tai-review .venv/bin/python -m pytest -q`, then confirm production is untouched:

```bash
docker ps -a --filter label=com.docker.compose.project=tai-review --format '{{.Names}}' | wc -l
docker volume ls -q | grep -c '^br-' || echo 0
```

Expected: `12`, and `0`. Commit with `-F`.
---

## Task 7: Cross-wiring defences — the pre-push hook and the branch marker

**Files:**
- Create: `hooks/pre-push`
- Create: `aurora-cli/aurora_cli/crosswire.py`, `aurora-cli/tests/test_crosswire.py`
- Modify: `compose.yml` (parameterise `FORGEJO____APP_NAME`), `.env.template`, `branch-env.yaml`
- Modify: `tests/test_repo_conformance.py`

**Interfaces:**
- Consumes: Task 1's identity, Task 2's manifest.
- Produces: `install_pre_push(worktree)`, `branch_app_name(name)`. Task 8 calls both.

**Context the implementer needs:** Spec §5.4 wants three independent layers, of which only the first exists today.

1. **Structural** — a new worktree inherits `origin` pointing at production's Forgejo, and the branch's Forgejo is a different hostname entirely. Already true; assert it rather than build it.
2. **Mechanical** — a `pre-push` hook that rejects any push whose remote URL names a branch host.
3. **Visual** — the branch Forgejo renders as `null-hub [BRANCH: <name>]`.

For (2), the pattern must be derived, not typed. A branch's host is `aurora-<name>.<tailnet suffix>`; production's is `<production domain>`. The hook must reject a push to anything matching `aurora-*.<suffix>` and **allow** production's own hostname — which is a real distinction, because production's domain also ends in the suffix. Getting this backwards produces a hook that blocks all pushes, which developers will delete within a day; that is worse than no hook.

Git worktrees share `.git/hooks` with the main checkout by default (`core.hooksPath` is unset and the worktree's `.git` file points at `…/.git/worktrees/<name>`, whose `hooks` resolves to the **common** dir). **Installing a hook into a branch worktree by writing `.git/hooks/pre-push` would therefore install it into production's checkout too.** Verify this on the host before choosing an approach; the safe form is a per-worktree `core.hooksPath` set with `git -C <worktree> config core.hooksPath <worktree>/.githooks`, which is worktree-local because `git config` in a worktree writes to the shared config **unless** `--worktree` is used and `extensions.worktreeConfig` is enabled. **Probe both, record what you find, and choose the one that provably does not modify production's checkout.** This is exactly the class of thing this project has been bitten by: a plausible mechanism that quietly reaches production.

For (3), `compose.yml` currently hardcodes `FORGEJO____APP_NAME=null-hub`. Change it to `${FORGEJO_APP_NAME:-null-hub}` — production-neutral, because the default is production's current value — and add `FORGEJO_APP_NAME` to `branch-env.yaml` deriving `null-hub [BRANCH: <name>]`.

- [ ] **Step 1: Probe the hook-sharing question and record the answer**

```bash
cd ~/Desktop/tai-review/.worktrees/chunk3
git rev-parse --git-path hooks
git config --get core.hooksPath || echo "(unset)"
git config --get extensions.worktreeConfig || echo "(unset)"
ls ~/Desktop/tai-review/.git/hooks/ | head
```

Write the results into the task report **before** writing code. If `git rev-parse --git-path hooks` resolves into the common `.git` directory, approach (a) is disqualified.

- [ ] **Step 2: Write the failing tests**

- `test_hook_rejects_a_branch_remote` / `test_hook_allows_production` — invoke the hook as git does (remote name + URL on argv, ref lines on stdin) with a branch URL and with production's URL; assert exit 1 and exit 0 respectively, with production's URL derived from Task 1.
- `test_hook_allows_a_non_forgejo_remote` — e.g. a GitHub URL passes.
- `test_installing_the_hook_does_not_touch_production` — snapshot the mtime and content of production's `.git/hooks` and of production's `.git/config`, install into a throwaway worktree, assert both unchanged. **This is the test that justifies Step 1.**
- `test_branch_app_name_marks_the_branch` — `"null-hub [BRANCH: demo]"`, and `compose.yml`'s value is parameterised (add a repo-conformance assertion that `FORGEJO____APP_NAME` contains `${` and defaults to `null-hub`, so the parameterisation cannot be reverted silently).

- [ ] **Step 3: Implement and prove the tests can fail**

| # | Mutation | Must redden |
|---|---|---|
| M1 | the hook always exits 0 | `…_rejects_a_branch_remote` |
| M2 | the hook always exits 1 | `…_allows_production` **and** `…_allows_a_non_forgejo_remote` — both, because a hook that blocks everything is the failure mode that gets it deleted |
| M3 | the hook matches on the tailnet suffix alone | `…_allows_production` |
| M4 | install writes to `.git/hooks/pre-push` | `…_does_not_touch_production` |
| M5 | `FORGEJO____APP_NAME` reverted to the literal | the repo-conformance assertion |

- [ ] **Step 4: Suite and commit**

`AURORA_PROJECT=tai-review .venv/bin/python -m pytest -q`; also `docker compose config --quiet && echo CONFIG_OK` to prove the `compose.yml` edit resolves. Commit with `-F`.

---

## Task 8: `aurora branch up`

**Files:**
- Create: `aurora-cli/aurora_cli/branch.py`
- Modify: `aurora-cli/aurora_cli/__main__.py`
- Create: `aurora-cli/tests/test_branch_up.py`

**Interfaces:**
- Consumes: Tasks 1–7 in full.
- Produces: `branch_up(name, *, from_ref, no_seed, seed, without, devs, force) -> BranchResult`. Task 10 renders `BranchResult`; Task 11 returns it over MCP.

**Context the implementer needs:** Spec §4.1, corrected. The order is not negotiable and each step has a reason recorded in the spec or in Chunk 2's ledger:

1. `git worktree add <production root>/.worktrees/<name> -b <name>` (or reuse an existing branch; `--from <ref>` creates from that ref and **fails** if the branch already exists — §7.1).
2. Render `.env` (Task 2). Resolve `--devs`: `$AURORA_DEV`, else the `developers.yaml` entry whose `forgejo_user` matches `git config user.name`; if neither resolves, **fail with an explicit message rather than guessing** (§7.1).
3. Resource guard (§5.5): refuse if `MemAvailable` would drop below the floor. Size it against the **measured** figures, not §5.5's original ones — the spec itself flags that its sizing predates the corrected §6.2 table. Today: 15 Gi total, **7.9 Gi available** (read `MemAvailable` from `/proc/meminfo`; `free`'s "free" column reads 483 Mi because of 8.6 Gi of cache and is the wrong number). Disk floor against 142 G free on btrfs. `--force` overrides; the override must be logged into the access doc.
4. Seed (Tasks 5–6), unless `--no-seed`. Host-path state goes into the worktree; agent volumes are created and filled **before** `up` so Compose adopts them (trap 6).
5. `docker compose -f compose.yml -f compose.branch.yml up -d postgres redis` first, wait for `service_healthy`, `pg_restore` (D-E), then `up -d --build` for the rest.
6. **Verify the tailnet node actually came up.** This is trap 9 and it is not optional: a sidecar with a bad key starts, prints `Logged out.`, and stays running. Poll `docker exec <ts container> tailscale --socket=/var/run/tailscale/tailscaled.sock status --json` until `BackendState == "Running"` and `Self.DNSName` starts with the expected hostname, with a bounded timeout, and **fail the whole `up`** otherwise. Then poll `https://<branch domain>/git/` from the host until it answers, because MagicDNS registration and Caddy's certificate issuance are not instantaneous and `reconcile` is about to depend on both.
7. `docker compose … run --rm dev-admin reconcile` (or `up -d dev-admin` and await exit 0) — regenerates OAuth apps against the branch hostname and writes the branch's `Caddyfile.d`.
8. **`docker compose … up -d` a second time.** Corrected in the spec 2026-07-28: once agents are compose services, `reconcile` creates no containers — it only emits `container.missing`. Without the second `up`, a branch has no agent.
9. Install the pre-push hook (Task 7), write `BRANCH-ACCESS.md`, regenerate `.worktrees/INDEX.md` (Task 10), return the access content as stdout.

Failure handling: `up` is not atomic and pretending otherwise is worse than admitting it. On failure **after** the worktree exists, print the exact `aurora branch down <name>` command and leave everything in place — do not auto-teardown, because a half-built branch is the only artifact a developer can debug from.

Note the property that makes seeding pay off: production's `FORGEJO_ADMIN_TOKEN` is valid in the branch, because the branch's Forgejo is a snapshot of production's database — same users, same token hashes. Nothing extra is needed for `reconcile` to authenticate.

- [ ] **Step 1: Write the tests**

Most of `up` is orchestration, so most of the tests are about **order and refusal**, driven through an injected command runner that records argv:

- `test_the_second_up_runs_after_reconcile` — assert the recorded argv sequence contains `up` … `reconcile` … `up`, in that order. Chunk 2's ledger records this exact ordering being wrong in a brief; pin it.
- `test_postgres_is_restored_before_the_full_up`.
- `test_tailscale_readiness_failure_aborts_the_up` — feed a `status --json` double reporting `NeedsLogin`; `up` must raise, and the argv recorder must show **no** `reconcile` and no second `up`. This is trap 9 in executable form.
- `test_devs_resolution_refuses_to_guess` — no `$AURORA_DEV`, `git config user.name` matching no developer → raises, message naming both mechanisms.
- `test_resource_guard_refuses_and_force_overrides` — with a stubbed `/proc/meminfo`.
- `test_up_never_targets_productions_project` — every recorded `docker compose` invocation carries `-p br-<name>` or `COMPOSE_PROJECT_NAME=br-<name>`; assert **no** invocation resolves to production's project. Assert the recorded invocation list is non-empty first.
- `test_from_ref_fails_when_the_branch_exists`.
- `test_sanitised_name_is_reported_when_it_differs`.

- [ ] **Step 2: Implement and prove the tests can fail**

| # | Mutation | Must redden |
|---|---|---|
| M1 | drop the second `up` | `…_second_up_runs_after_reconcile` |
| M2 | treat any `tailscale status` output as success | `…_readiness_failure_aborts_the_up` |
| M3 | `--devs` falls back to `all` when unresolved | `…_refuses_to_guess` |
| M4 | drop `-p` from one compose invocation | `…_never_targets_productions_project` — if it stays green the assertion is scanning the wrong argv |
| M5 | restore Postgres after the full `up` | `…_restored_before_the_full_up` |
| M6 | resource guard reads `MemFree` instead of `MemAvailable` | `…_resource_guard_refuses…` with a fixture whose two values differ by a cache-sized margin — that difference is 7.4 Gi on this host |

- [ ] **Step 3: Suite and commit**

`AURORA_PROJECT=tai-review .venv/bin/python -m pytest -q`. **No real branch is brought up in this task** — that is Task 12, after teardown exists. Bringing one up before `down` exists means a failure leaves containers nobody has a tested way to remove. Commit with `-F`.

---

## Task 9: `aurora branch down` — teardown that provably cannot reach production

**Files:**
- Create: `aurora-cli/aurora_cli/guards.py`
- Modify: `aurora-cli/aurora_cli/branch.py`, `aurora-cli/aurora_cli/__main__.py`
- Create: `aurora-cli/tests/test_guards.py`
- Create: `tests/test_branch_isolation.py`

**Interfaces:**
- Consumes: Task 0's harness, Task 1's identity.
- Produces: `assert_branch_project(project)`, `assert_not_production_path(path)`, `branch_down(name|--all, force)`.

**Context the implementer needs:** **This is the most safety-critical code in the chunk.** Everything else fails by not working; this fails by destroying production. Spec §4.4 plus §10.2.

Every destructive call routes through `guards.py` first, and the guard is *positive* — it asserts the target **is** a branch, rather than asserting it is not production. A negative guard ("not equal to production") passes on typos, on an empty string, and on `None`; a positive guard (`project.startswith("br-")` **and** `project != production_project()` **and** the project's containers all carry that label) does not. Both clauses are required: after the rename production is `aurora`, and a guard that only checked the prefix would be correct today and correct then, but a guard that only checked inequality would let `docker compose -p "" down -v` through, which Compose resolves to the current directory's basename.

Teardown, in order:

1. Guard the project name and the worktree path (`assert_not_production_path` refuses `production_root()` and anything that is not a child of `production_root()/.worktrees`, comparing `Path.resolve()`d values via `Path.parents`, never string prefixes).
2. Snapshot production (Task 0) **before** anything destructive.
3. `docker compose -p br-<name> --profile '*' down -v --remove-orphans`, run from the branch worktree so `-f compose.yml -f compose.branch.yml` resolve. **`--profile '*'` is trap 3** — without it every agent container survives the teardown.
4. **Fallback path for N7**: if the worktree is gone (or `up` failed before it was populated), fall back to label-driven removal — `docker ps -aq --filter label=com.docker.compose.project=br-<name>` then `docker rm -f`, then `docker volume ls -q --filter label=com.docker.compose.project=br-<name>` then `docker volume rm`, then the network. **Both paths call the same guard first**; the fallback is the one that manipulates Docker objects by name and is therefore the one most able to do damage.
5. Sweep any volume still carrying the branch project label (a `docker compose down -v` misses a volume declared `external: true`; none is today, but the sweep is what makes that not matter).
6. `git worktree remove` — refuses on uncommitted changes unless `--force`. Then `git worktree prune`.
7. `assert_production_unchanged(before)`.
8. Regenerate `.worktrees/INDEX.md`.

The ephemeral tailnet node deregisters itself once the state volume is gone and the container is stopped; verify it in Task 12 rather than asserting it here.

`--all` iterates `branch_projects()` from Task 0 — **derived from the daemon**, not from a file, so a branch whose worktree was deleted by hand is still reachable.

- [ ] **Step 1: Write the failing tests**

`aurora-cli/tests/test_guards.py` — the table of refusals, each asserting that **zero** commands were issued (an injected runner that records argv and raises if called):
`""`, `None`, `"aurora"`, `"tai-review"`, `production_project()`, `"br"`, `"notbr-x"`, `"BR-x"`, `"br-"`, `" br-x"`. Only `"br-x"` proceeds. Both production names appear explicitly, so the guard is right before and after the rename.

Path refusals: `production_root()`, `production_root()/".."`, `/`, `~`, `production_root()/"forgejo"`, and a path that merely *string-prefixes* the worktrees dir (`…/.worktrees-evil/x`) — the last one is what catches a `str.startswith` implementation.

`tests/test_branch_isolation.py` — the empirical half, using Task 0's `throwaway_branch`:
- `test_down_removes_everything_it_created` — bring up a minimal two-service throwaway project **including one profiled service**, tear down, assert zero containers/volumes/networks carry the label.
- `test_down_with_a_missing_worktree_still_reclaims` — remove the worktree first, then `branch_down`; the label-driven fallback must clean up.
- `test_down_all_leaves_production_untouched` — snapshot production, run `--all` while production is running, `assert_production_unchanged`. This is spec §10.2's named invariant.
- `test_down_refuses_when_the_worktree_is_dirty_without_force`.

- [ ] **Step 2: Implement and prove the tests can fail**

| # | Mutation | Must redden |
|---|---|---|
| M1 | guard becomes `project != production_project()` | the `""`, `"br"`, `"notbr-x"` and `" br-x"` rows |
| M2 | guard becomes `project.startswith("br-")` only | nothing in the current world — **record this honestly**; then add a test that monkeypatches `production_project()` to return `"br-legacy"` and assert the guard still refuses it. A guard whose two clauses cannot both be exercised is half-tested. |
| M3 | path guard uses `str.startswith` | the `.worktrees-evil` row |
| M4 | drop `--profile '*'` | `…_removes_everything_it_created` — **only if** the probe project really declares a profiled service. Verify the mutation reddens before believing the test. |
| M5 | drop `-v` | `…_removes_everything_it_created` (volume assertion) |
| M6 | `--all` reads a JSON index file instead of the daemon | `…_with_a_missing_worktree_still_reclaims` |
| M7 | `assert_production_unchanged` moved to before the teardown | `…_all_leaves_production_untouched` must still pass, but the test is then vacuous — so also assert the call ordering, or capture the snapshot in the test itself rather than trusting `branch_down` to do it |

M7 is the shape of defect this project keeps producing. Prefer capturing the snapshot **in the test**, so the invariant does not depend on the code under test choosing to check itself.

- [ ] **Step 3: Suite and commit**

`AURORA_PROJECT=tai-review .venv/bin/python -m pytest -q`, then:

```bash
docker ps -a --filter label=com.docker.compose.project=tai-review --format '{{.Names}}' | wc -l
docker ps -a --format '{{.Names}}' | grep -c '^br-' || echo 0
```

Expected `12` and `0`. Commit with `-F`.

---

## Task 10: `ls`, `access`, `shell`, `rebuild`, and the access documents

**Files:**
- Create: `aurora-cli/aurora_cli/access_doc.py`, `aurora-cli/tests/test_access_doc.py`
- Modify: `aurora-cli/aurora_cli/branch.py`, `aurora-cli/aurora_cli/__main__.py`

**Interfaces:**
- Consumes: Tasks 1, 4, 5, 8, 9.
- Produces: `render_access_doc(result) -> str`, `render_index(branches) -> str`, `branch_ls()`, `branch_access(name)`, `branch_shell(name, service)`, `branch_rebuild(name, service)`.

**Context the implementer needs:** Spec §7.4. `BRANCH-ACCESS.md` is returned verbatim as CLI stdout **and** as the MCP tool result, so it is the product, not documentation about the product. It contains:

- The URL set: fjell root, `/git/`, `/agent/<developer>/`, `/affine/` — all against the branch domain.
- **`/agent` (the admin Hermes dashboard) must be listed as unavailable in a branch**, with the reason. Finding N5: the Caddyfile redirects it to `https://{$DOMAIN_NAME}:{$HERMES_SERVE_PORT}/`, which is a `tailscale serve` mapping that exists only on the host, for production. Printing a URL that 502s is worse than printing nothing.
- The service → container-name table, read from `docker compose -p br-<name> ps`, not constructed by string concatenation — the whole point of `container_name: !reset null` is that Compose owns those names.
- Paste-ready `docker exec -it <container> bash` lines.
- Rebuild and teardown commands, with the branch name already substituted.
- What was excluded (Task 4's closure, showing both the requested and the transitively-added services) and what was seeded (Task 5's `SeedReport`, including whether `--force` overrode the resource guard).

`.worktrees/INDEX.md` is regenerated on every `up` and `down`. Because `.worktrees/` sits inside the tree production's Hermes mounts, production's agent reads every branch's access doc with no extra wiring (§7.4) — the reason D-F keeps branch worktrees there.

`shell` and `rebuild` are thin, and their only interesting property is scoping: `rebuild` must be `docker compose -p br-<name> up -d --build <service>`, so it **cannot** restart a production container (§7.1).

- [ ] **Step 1: Write the tests**

- `test_access_doc_names_the_branch_domain_and_never_productions` — scan for `production_domain()`; the only permitted hit is the explicitly labelled "commits still go to production Forgejo" line, asserted by exact match.
- `test_access_doc_marks_the_admin_dashboard_unavailable` — N5.
- `test_access_doc_container_names_come_from_compose_ps` — feed a `ps` double with a deliberately surprising name and assert the doc prints that, not a constructed one.
- `test_access_doc_records_exclusions_and_seeding`.
- `test_rebuild_is_scoped_to_the_branch_project` — argv contains `-p br-<name>`; assert **no** invocation resolves to production's project.
- `test_index_lists_live_branches_only` — derived from the daemon, not from a stale file.
- `test_shell_refuses_a_service_not_in_the_branch`.

- [ ] **Step 2: Implement and prove the tests can fail**

| # | Mutation | Must redden |
|---|---|---|
| M1 | the doc builds container names as `f"br-{name}-{service}-1"` | `…_come_from_compose_ps` |
| M2 | the doc prints the `/agent` admin URL as live | `…_marks_the_admin_dashboard_unavailable` |
| M3 | `rebuild` drops `-p` | `…_scoped_to_the_branch_project` |
| M4 | the doc interpolates production's domain into the fjell URL | `…_never_productions` |
| M5 | `INDEX.md` is read from a cached file | `…_lists_live_branches_only` |

- [ ] **Step 3: Suite and commit**

`AURORA_PROJECT=tai-review .venv/bin/python -m pytest -q`. Commit with `-F`.

---

## Task 11: The MCP facade

**Files:**
- Create: `aurora-cli/aurora_cli/mcp.py`, `aurora-cli/tests/test_mcp.py`
- Modify: `aurora-cli/aurora_cli/__main__.py`
- Create: `aurora-cli/Dockerfile` (image `aurora-cli:local`)

**Interfaces:**
- Consumes: Tasks 8–10.
- Produces: `aurora mcp` — a stdio JSON-RPC server exposing `branch_up`, `branch_down`, `branch_list`, `branch_access`.

**Context the implementer needs:** Spec D5 and §7.3. Stdio means no daemon, no port, no always-on container. **Both surfaces must call identical code** — the tools are thin adapters over the same functions the CLI calls, and a test must prove it (assert the tool handler is literally the same object, or that patching the shared function changes both paths).

Per D-B the transport is hand-written: line-delimited JSON-RPC 2.0 over stdin/stdout, handling `initialize`, `notifications/initialized`, `tools/list` and `tools/call`, and nothing else. Four methods do not justify a dependency that must then exist in the host venv, in a fresh worktree, and in the image.

Registration (documented, not executed — it needs a human):

```
hermes mcp add aurora --command docker \
  --args run -i --rm -v /var/run/docker.sock:/var/run/docker.sock aurora-cli:local mcp
```

**That invocation as written cannot work and the plan must say so rather than copy it forward.** `branch up` runs `git worktree add` and `cp --reflink` against host paths, and Compose resolves bind sources **host-side**. A container holding only the docker socket has no repo. The image must therefore also mount production's checkout at its own host path, and the working directory must match:

```
docker run -i --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v <production root>:<production root> \
  -w <production root> \
  aurora-cli:local mcp
```

Write the *derived* form into `docs/post-implementation-steps.md` (Task 12) so it is correct before and after the rename. If Docker-in-Docker path identity turns out not to hold when probed, **record that and narrow the deliverable to the host-side CLI plus a documented MCP limitation** — G8 is then satisfied for host-shell agents (Claude Code over Tailscale SSH) and narrowed for Hermes, which is spec §12's option 2 and an acceptable, honest outcome. Do not fake it.

- [ ] **Step 1: Write the tests**

- `test_initialize_handshake` — a recorded byte-level transcript: `initialize` → a response carrying `protocolVersion`, `serverInfo` and a `tools` capability.
- `test_tools_list_declares_all_four`.
- `test_tools_call_invokes_the_same_function_as_the_cli` — patch `branch.branch_up` and assert the MCP path observes the patch.
- `test_malformed_json_gets_a_parse_error_not_a_traceback` — `-32700`, and the server stays alive for the next message.
- `test_unknown_method_returns_method_not_found` — `-32601`.
- `test_tool_error_is_returned_as_an_error_result_not_a_crash` — `branch_up` raising becomes a tool result with `isError`, and the process survives.

- [ ] **Step 2: Implement, build the image, and prove the tests can fail**

| # | Mutation | Must redden |
|---|---|---|
| M1 | `tools/call` re-implements `branch_up` instead of calling it | `…_same_function_as_the_cli` |
| M2 | remove one tool from `tools/list` | `…_declares_all_four` |
| M3 | let a handler exception propagate | `…_returned_as_an_error_result_not_a_crash` |
| M4 | respond to `initialize` without `protocolVersion` | `…_handshake` |

Then build and smoke the image:

```bash
cd ~/Desktop/tai-review/.worktrees/chunk3
docker build -t aurora-cli:local aurora-cli/
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  | docker run -i --rm aurora-cli:local mcp
```

Expected: a single JSON-RPC response line. Record whether the container can see production's checkout when the mount above is added, and write the honest answer into the report.

- [ ] **Step 3: Suite and commit**

`AURORA_PROJECT=tai-review .venv/bin/python -m pytest -q`. Commit with `-F`.

---

## Task 12: End-to-end acceptance — a real branch stack, up and down

**Files:**
- Create: `tests/test_branch_acceptance.py`
- Create: `docs/implementations/2026-07-29-chunk3-ephemeral-branching.md`
- Create: `docs/testing/2026-07-29-chunk3-ephemeral-branching.md`
- Create: `docs/issues/chunk3-spec-deltas.md`
- Modify: `docs/post-implementation-steps.md`, `README.md`

**Interfaces:**
- Consumes: everything.
- Produces: the acceptance gate for Chunk 3.

**Context the implementer needs:** Every earlier task tested a part. This one brings up a **real** branch stack against **live production**, proves isolation, and tears it down.

**It runs in two tiers, and which tier ran must be stated in the report.** A skipped tier reported as a pass is precisely the defect class this project has hit repeatedly.

**Tier A — no Tailscale auth key required.** Everything except tailnet ingress. Runs unconditionally.
**Tier B — requires an ephemeral auth key.** Spec §10.3's URL-level assertions. Per D-D, **no auth key exists on this host and an agent cannot mint one.** If `AURORA_TS_AUTHKEY` is unset, Tier B does **not** run and the task's outcome is **BLOCKED on Tier B**, recorded in the ledger and in `docs/post-implementation-steps.md` exactly as Chunk 2 Task 12 recorded its blocked deploy. Do not weaken the tests, do not mark them `skip` and call the run green, and do not invent a key.

**Tier A steps** (each an assertion, not a demonstration):

- Production snapshot before anything (Task 0).
- `./aurora branch up acceptance --devs testuser` with `AURORA_TS_AUTHKEY` unset → must **fail at config time** with a message naming `TS_AUTHKEY` (the `${TS_AUTHKEY:?}` guard), proving trap 9 is closed at the earliest possible point. Then set a dummy key and continue: the sidecar will start and stay `Logged out`, and **`up` must fail at the readiness poll**, proving the second layer. Assert the argv recorder shows no `reconcile` ran.
- With the readiness poll stubbed to succeed (Tier A only; the stub must be visible in the test name), bring the stack up and assert:
  - **Isolation:** every container carries `com.docker.compose.project=br-acceptance`; **no** container name collides with production's; production's container IDs are unchanged; the branch published **zero** host ports (`docker compose -p br-acceptance ps --format json` → every `Publishers` entry empty) — this is spec §5.1's "port collision is unrepresentable, not merely avoided".
  - **Seeding worked:** `docker exec` into the branch's Forgejo and query its SQLite for the org `obsidura` and the repo `aurora`. These strings were verified present in production's live database during planning.
  - **Path relativity (§5.2):** the branch's `hermes` binds resolve inside the branch worktree, not inside production's checkout — compare `docker inspect` mounts against the worktree with **both sides `Path.resolve()`d**.
  - **Service DNS in the sidecar netns:** `docker exec` into the branch's Caddy container and reach `http://forgejo:3000/` — this is the mechanic verified in the `br-nsprobe` probe and the reason `FORGEJO_UPSTREAM=forgejo:3000` works. It also, finally, pins Task 3's M5 (`TS_ACCEPT_DNS=true` breaks exactly this).
  - **Production availability:** poll production's URL throughout the entire up/down cycle from a background thread; assert **zero** non-200 responses (§10.3).
  - **Seed did not mutate production:** sha256 of production's `forgejo/gitea/gitea.db` and `-wal` before and after (excluding `-shm`, per N6).
  - **Cross-wire:** the worktree's `origin` points at production; the pre-push hook rejects a push to a branch URL.
- `./aurora branch down acceptance`, then: zero `br-acceptance` containers, volumes and networks; the worktree is gone; `assert_production_unchanged`.
- Re-run `branch up`/`down` a second time to prove idempotence — a teardown that leaves residue only shows up on the second cycle.

**Tier B steps** (only with a real key): the branch's tailnet node reaches `Running`; `GET https://aurora-acceptance.<suffix>/git/` returns HTML **containing `obsidura` and `aurora`**; `/agent/testuser/` returns the agent's login page rather than a 502 (this is what proves `AGENT_UPSTREAM_MODE=service` reached the branch `.env`); from **inside production's Hermes container**, `curl` the branch URL and receive the branch's HTML (§10.3 reachability); after teardown, the node is gone from `tailscale status`.

Full OIDC login as a seeded user (§10.3) and the merge-back test are **out of scope for this plan** and go into `docs/issues/chunk3-spec-deltas.md` as explicitly deferred, with the reason: both need a browser session against a tailnet URL, i.e. Tier B plus interactive credentials. Say so rather than letting them quietly not happen.

- [ ] **Step 1: Write the acceptance suite**

With every assertion above, and with Tier B guarded by an explicit `AURORA_TS_AUTHKEY` check that **fails loudly** rather than skipping when the operator has set `AURORA_EXPECT_TIER_B=1`.

- [ ] **Step 2: Run Tier A**

```bash
cd ~/Desktop/tai-review/.worktrees/chunk3
AURORA_PROJECT=tai-review .venv/bin/python -m pytest tests/test_branch_acceptance.py -v -m "not tier_b" 2>&1 | tail -30
```

Record the full output. Then confirm the host is clean:

```bash
docker ps -a --filter label=com.docker.compose.project=tai-review --format '{{.Names}}' | wc -l
docker ps -a --format '{{.Names}}' | grep -c '^br-' || echo 0
docker volume ls -q | grep -c '^br-' || echo 0
git -C ~/Desktop/tai-review worktree list
```

Expected: `12`, `0`, `0`, and no `acceptance` worktree.

- [ ] **Step 3: Run Tier B, or record BLOCKED**

If `AURORA_TS_AUTHKEY` is set, run the tier-B selection and record the results. Otherwise write into the ledger and into `docs/post-implementation-steps.md`:

> **BLOCKED — Tier B acceptance needs a Tailscale credential no agent can create.** In the Tailscale admin console, create a **reusable, ephemeral, pre-approved** auth key (or an OAuth client with the `auth_keys` scope) and put it in production's `.env` as `TS_AUTHKEY_BRANCH=…`. Then run `AURORA_EXPECT_TIER_B=1 .venv/bin/python -m pytest tests/test_branch_acceptance.py -m tier_b`. Until this is done, a branch stack builds, seeds, isolates and tears down correctly, but has **no tailnet ingress and no certificate** — the URLs in `BRANCH-ACCESS.md` are unreachable.

- [ ] **Step 4: Full suite, both ways**

```bash
AURORA_PROJECT=tai-review .venv/bin/python -m pytest -q 2>&1 | tail -3
.venv/bin/python -m pytest -q 2>&1 | tail -5
```

Expected: the first is fully green with `1 xfailed`. The second still shows the two known failures caused by production carrying the `tai-review` label while the repo declares `aurora`; **that is Chunk 2 Task 12's undeployed rename, not a Chunk 3 defect**, and it must be reported as such rather than "fixed".

- [ ] **Step 5: Documentation**

`docs/implementations/…` (what was built, every deviation from this plan, every mutation transcript reference), `docs/testing/…` (what is proven, what is not, which tier ran), `docs/issues/chunk3-spec-deltas.md` (at minimum: N1's three hostname-bearing variables, N4's `SSH_DOMAIN`, N5's dead `/agent` redirect, N6's `-shm` exclusion, D-D's auth-key dependency, and the deferred OIDC-login and merge-back tests), `docs/post-implementation-steps.md` (the auth key, the MCP registration in its derived form, and the still-blocked Chunk 2 rename), and a `README.md` section describing `aurora branch`.

- [ ] **Step 6: Commit**

Commit with `-F`. **Do not merge to `main`** — the user reviews and merges.
