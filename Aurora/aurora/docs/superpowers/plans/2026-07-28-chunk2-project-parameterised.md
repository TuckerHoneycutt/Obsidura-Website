# Chunk 2: The Stack Becomes Project-Parameterised — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove every hardcoded reference to *this* stack's identity — project name, network name, container names, host ports, upstream addresses and absolute host paths — so that the same tree, checked out elsewhere under a different `COMPOSE_PROJECT_NAME`, resolves into a complete second stack. Then give the stack its real identity: the checkout becomes `~/Desktop/aurora`, `COMPOSE_PROJECT_NAME=aurora` is set explicitly as spec §4.3 requires, and every container, network and project-scoped volume is renamed with it. Production behaviour is unchanged apart from one scheduled restart window, and verifiable at every step. No branch is created in this chunk.

**Architecture:** Three migrations from the spec — M4 converts per-developer Hermes agents from imperative `docker run` into a generated, committed `compose.agents.yml` that is `include:`d, so Compose owns them and `docker compose down` can see them; M5 replaces `docker_utils.NETWORK`, `CADDY_CONTAINER` and `BASE_PORT` with values derived from the running project, and introduces an upstream *addressing mode* so production keeps its published-port routing while a branch can route by service DNS; M6 converts the two absolute bind mounts (`~/.hermes`, `~/Desktop/tai-review`) to repo-relative paths. **The project rename lands directly on top of M5 and M6** (Task 9): `COMPOSE_PROJECT_NAME` is unset today, so the project name is the directory basename `tai-review` — a leftover from the owner's previous NAS project. M5 is what removes the `tai-review-caddy-1` and `tai-review_default` literals that a rename would otherwise have to be applied to twice, and M6 is what removes the two absolute `~/Desktop/tai-review` binds that a directory move would otherwise break. Setting `COMPOSE_PROJECT_NAME=aurora` explicitly is not cosmetic: spec §4.3 already mandates "set it explicitly per branch — don't rely on the directory-basename default", and Chunk 3's `br-<name>` project names have no meaning until production's own name is declared rather than inherited from a path. Task 10 rewrites `README.md`, which still describes a pre-Chunk-1 service inventory. Four defects surfaced by Chunk 1 land here because this is the chunk that touches the same code: the conformance gate is made profile-aware, a declaration-vs-runtime conformance test is added, the `dev-admin` startup race is closed with a healthcheck-gated `depends_on`, and the spec §5.3 project-label guard is implemented across every mutating dev-admin entry point.

**Tech Stack:** Docker Compose v5.3.1 / Docker Engine 29.6.2, Python 3.13 (container) / 3.14.6 (host venv) + pytest, Caddy, Rust (fjell), Fedora/btrfs host.

---

## Global Constraints

- Host is `superserver.tailc67a98.ts.net`. Production checkout is `~/Desktop/tai-review`, **now on branch `main` at `c7126e2`** (trunk was renamed from `master`; both refs point at the same commit and `main` is the Forgejo default). Chunk 1 is merged and deployed.
- **All work happens in a fresh worktree**, not in the production checkout:
  `git worktree add .worktrees/chunk2 -b feat/project-parameterised main`.
  The existing `.worktrees/ephemeral-branching` worktree belongs to Chunk 1 and must not be reused.
- **Production must stay up.** Everything this plan changes is inert until Task 12's single deploy. Tasks 1–11 change declarations, tests and staged state only; Task 12 is the one step that stops or recreates a running container, and it says exactly which and for how long.
- **The path and the project name change exactly once, in Task 12 Step 4.** Until then every command in this plan uses `~/Desktop/tai-review` and project `tai-review`, and both are correct. From Task 12 Step 4c-ii onward every command uses `~/Desktop/aurora`, and from 4c-iv onward the project is `aurora`. Task 9 changes only *declarations* (`.env.template`, source, tests) — it deliberately does **not** touch the production checkout's live `.env`, because a `COMPOSE_PROJECT_NAME=aurora` in a directory whose containers are still labelled `tai-review` would make `docker compose down` a no-op and `docker compose up -d` start a second, parallel stack.
- **Between Task 9 and the deploy, run the suite with `AURORA_PROJECT=tai-review`.** Task 9 flips `conftest.PRODUCTION_PROJECT`'s default to `aurora`, which is right after the deploy and wrong before it. The `AURORA_PROJECT` environment override exists for exactly this window. Forgetting it does not silently pass: Task 9 adds `test_the_conformance_gate_has_containers_to_conform_to`, which fails when the named project has no running containers.
- `sudo` is unavailable to agents (no TTY). Any step needing root goes to `docs/post-implementation-steps.md`. This plan is written to need none.
- **Git identity must be passed inline** — the repo's configured committer is `Hermes Agent <hermes@local>`, which is wrong for this work:
  `git -c user.name="supergoodname77" -c user.email="epascuales@outlook.com" commit …`
- **There is no system `pytest`.** Run tests as `.venv/bin/python -m pytest`, never bare `pytest`. Task 0 creates the venv.
- `/home` is a symlink to `/var/home`, and Go's `os.Getwd()` (used by the `docker compose` binary) trusts a stale `$PWD`. Any test comparing a compose-reported path against a Python-computed path **must `Path.resolve()` both sides** first, and must check parentage via `Path.parents`, never a string prefix.
- Do **not** re-enable the commented-out cargo layer-cache block in `fjell/Dockerfile`; it has caused breakage before.
- Hermes retains its `/var/run/docker.sock` mount (spec D12). Do not remove it. The §5.3 guard built in Tasks 3–4 is the compensating control.
- Python target for the `dev_administration` package is 3.13 (its container base image). Runtime dependencies remain `typer` and `pyyaml` only — **do not add runtime dependencies.** `pytest` is a development tool.
- Commit after every task. Never commit `.env`, `.venv/`, `.pytest_cache/`, `.hermes/`, or `.agent-env/`.

### State of the host at the time of writing (verified, not assumed)

| Fact | Evidence |
|---|---|
| 12 containers carry the `tai-review` project label; `dev-admin` is `Exited (1)` | `docker ps -a --filter label=com.docker.compose.project=tai-review` |
| `dev-admin`'s exit is the startup race: `CalledProcessError … returned non-zero exit status 22` from `curl` against `https://superserver.tailc67a98.ts.net/git/api/v1/user/applications/oauth2` | `docker logs dev-admin --tail 25` |
| The three `hermes-*` agent containers **no longer exist** — they were destroyed on the host during this plan's research window (`destroy hermes-testuser`, `hermes-cumshit42069`, `hermes-newuser`), by something other than Compose (they carried no project label, so `--remove-orphans` could not have) | `docker events --since 40m --filter event=destroy` |
| Their volumes survive: `hermes-testuser-home`, `hermes-newuser-home`, `hermes-cumshit42069-home`, plus six orphans from deleted accounts | `docker volume ls` |
| One **unlabelled** container remains: `agent-authz`, `Exited (137)`, still holding a `tai-review_default` network entry. It is a pre-compose leftover; the compose-managed one is `tai-review-agent-authz-1`, `Up` | `docker inspect agent-authz` |
| `docker compose config` in the production checkout resolves `name: tai-review` | `docker compose config --format json` |
| Forgejo's image ships `/usr/bin/curl`; `GET http://localhost:3000/api/healthz` → `200`, `{"status":"pass","checks":{"cache:ping":…,"database:ping":…}}` | `docker exec forgejo curl …` |
| `~/.hermes` is 2.7 GB; `workspace/` is 159 MB of it, containing a root-owned `postgrespg-tai/18/docker` the agent user cannot read, and an empty root-owned `workspace/tai-review` mount point | `du -sh ~/.hermes/*`, `ls -la ~/.hermes/workspace` |
| `~/Desktop/tai-review/.hermes/plans/` already exists with 4 markdown files (artefact of an earlier agent run) | `find ~/Desktop/tai-review/.hermes` |
| `/var/home` is btrfs with 143 GB free | `df -h`, `findmnt -no FSTYPE /var/home` |
| Eight services declare `container_name:` — `forgejo`, `forgejo-mcp`, `hermes`, `dev-admin`, `affine`(→`affine_server`), `affine_migration`(→`affine_migration_job`), `postgres`(→`affine_postgres`), `redis`(→`affine_redis`) | `docker compose config --format json` |
| Six services publish host ports — `affine`, `agent-authz`, `arcadedb`, `fjell`, `forgejo`, `hermes` | same |
| `fjell` declares no `image:`; Compose synthesises `tai-review-fjell` | same, plus `docker ps --format '{{.Image}}'` |
| fjell listens on `0.0.0.0:9080` and registers the route `/agent/{username}/setup` | `fjell/src/main.rs:15`, `fjell/src/routes/setup.rs:91` |
| `COMPOSE_PROJECT_NAME` is **not set anywhere** — the project name `tai-review` is the directory basename | `grep -c COMPOSE_PROJECT_NAME ~/Desktop/tai-review/.env` → `0`; `docker compose config --format json` → `"name": "tai-review"` |
| Six project-prefixed volumes exist and would be orphaned by a rename: `caddy_data` (8 KB, **no `caddy/certificates/`**), `caddy_config` (16 KB autosave), `arcadedb_config` (byte-identical to the image default), `arcadedb_log` (930 B), `arcadedb_backups` and `arcadedb_replication` (both empty) | `docker run --rm -v <vol>:/x:ro alpine find /x`; `diff -rq` against `arcadedata/arcadedb:26.7.3` |
| The nine `hermes-*-home` volumes are explicitly named, carry no project prefix, and contain **zero** references to `/opt/data/workspace/tai-review` | `docker volume ls`; `grep -rIl` inside each |
| The Forgejo repo is already named `aurora`; the git remote needs no change | `git remote -v` → `…/supergoodname77/aurora.git`; `ls forgejo/git/repositories/*/` → `aurora.git` |
| Both git worktrees store their links as absolute paths under `Desktop/tai-review`, in both directions | `cat .git/worktrees/ephemeral-branching/gitdir`, `cat .worktrees/ephemeral-branching/.git` |
| A moved venv still works for `.venv/bin/python -m pytest`; only `bin/activate` and console-script shebangs go stale | copied a `.venv` to a new path, `bin/python -c 'import sys, pytest; print(sys.prefix)'` printed the new path, pytest 9.1.1 imported |

### Compose behaviours this plan depends on (all probed on this host, v5.3.1)

| Behaviour | Probe result |
|---|---|
| A `profiles:`-gated service is omitted from `docker compose config` | `--services` → `always` only |
| `COMPOSE_PROFILES="*"` renders every service regardless of profile | `--services` → `always`, `gated` |
| `COMPOSE_PROFILES` is read from `.env` and selects correctly | `.env` with `COMPOSE_PROFILES=agent-alice` → `core`, `hermes-alice` |
| `depends_on` a service behind an inactive profile is a **hard error** | `service "app" depends on undefined service "db": invalid compose project`, exit 1 |
| A missing `include:` target is a **hard error** | `open …/compose.agents.yml: no such file or directory` |
| Compose adopts a pre-existing volume carrying `com.docker.compose.project` + `com.docker.compose.volume` labels, preserving contents | seeded `volprobe_data`, `docker compose create` → no warning, marker file intact |
| `env_file: [{path: …, required: false}]` resolves cleanly when the file is absent and merges when present | probed both ways, exit 0 |

---

## Findings from Chunk 1 that shape this plan

**F1 — `profiles:` broke the conformance gate, and the fix is one environment variable.** A service carrying `profiles:` vanishes from `docker compose config` output unless its profile is active, so its still-labelled container reads as *undeclared* and `test_no_undeclared_containers_in_project` fails. `COMPOSE_PROFILES="*"` is the documented way to ask "everything this file declares, regardless of activation" — which is exactly the question a *declaration* gate should be asking. Task 1 does this. See the D9 recommendation at the end.

**F2 — `dev-admin` has a startup race.** `depends_on: [forgejo]` with no condition means `reconcile` runs the instant Forgejo's *container* starts, before Forgejo is *serving*, and dies with `curl` exit 22. Task 11 closes it with a healthcheck-gated `depends_on` **plus** a bounded retry in `forgejo_utils._curl` — the retry is needed independently, because dev-admin reaches Forgejo *through Caddy*, so a Caddy recreate window produces the identical failure that no Forgejo healthcheck can gate.

**F3 — a branch's removals are not in force until deployed.** Live containers are governed by `com.docker.compose.project.config_files`, which on this host points at `/home/supergoodname77/Desktop/tai-review/compose.yml`, not at any worktree. This is why every deploy in this plan is concentrated in Task 12, and why Task 8's declaration change is expected to make one runtime test red until then.

**F4 — the test suite compares names only.** Nothing compares a declared image, bind source or published port against `docker inspect`. That blind spot is how a Critical defect reached final review (AFFiNE "declared" at a bind path production had never used). Task 2 adds the declaration-vs-runtime test.

**F5 — the conformance gate cannot see unlabelled containers.** One exists right now. Task 2 adds a network-membership gate that catches exactly the class of container the dev agents used to be.

---

## File Structure

| File | Responsibility |
|---|---|
| `tests/conftest.py` | **Modified.** `compose_config(all_profiles=True)`; adds `project_containers()`, `inspect_container()`, `all_container_names()`, `ALLOWED_EXTERNAL_BINDS`. |
| `tests/test_repo_conformance.py` | **Modified.** Adds the profile regression tests, the `compose.agents.yml` drift test, the Caddyfile/tailnet-IP tests, and the relative-bind tests. |
| `tests/test_runtime_conformance.py` | **New.** Declaration-vs-runtime: image, bind sources, published ports, and "every container on the project network carries the project label". |
| `tests/test_compose_startup_ordering.py` | **New.** Asserts `forgejo` declares a healthcheck and `dev-admin` gates on `service_healthy`. |
| `tests/test_second_project_ready.py` | **New.** Chunk 2 acceptance. |
| `dev-administration/dev_administration/project.py` | **New.** Project identity + the spec §5.3 guard. |
| `dev-administration/dev_administration/agents_compose.py` | **New.** `AgentSpec`, `agent_specs()`, `render_agents_compose()` — pure, no Docker. |
| `dev-administration/dev_administration/docker_utils.py` | **Modified.** `NETWORK` deleted; `run_container_detached` deleted; every mutating function guarded. |
| `dev-administration/dev_administration/caddy_utils.py` | **Modified.** Upstream addressing mode; guard on every `docker exec`. |
| `dev-administration/dev_administration/provision.py` | **Modified.** `BASE_PORT` constant → config field; agents no longer `docker run`; Caddy resolved by label. |
| `dev-administration/dev_administration/cli.py` | **Modified.** New `render-agents` command; `_load_config()` derives project identity. |
| `dev-administration/dev_administration/verify.py` | **Modified.** `CADDY_CONTAINER` literal removed. |
| `dev-administration/dev_administration/forgejo_utils.py` | **Modified.** Bounded retry on connection-class curl failures. |
| `dev-administration/tests/test_project.py` | **New.** Identity module and guard unit tests. |
| `dev-administration/tests/test_agents_compose.py` | **New.** Renderer unit tests. |
| `dev-administration/tests/test_guard_coverage.py` | **New.** Structural proof the guard covers *every* mutating entry point (spec §10.2). |
| `dev-administration/tests/test_caddy_utils.py` | **Modified.** Split into published-mode and service-mode; resolves the inherited failure with evidence. |
| `dev-administration/tests/test_docker_utils.py`, `test_provision.py`, `test_forgejo_utils.py` | **Modified.** Follow the new seams. |
| `compose.agents.yml` | **New, generated, COMMITTED.** Per-developer Hermes agents as Compose services. |
| `compose.yml` | **Modified.** `include:` the agents file; relative binds; Forgejo healthcheck; `dev-admin` depends_on condition; parameterised Caddy upstreams and Hermes tailnet bind. |
| `Caddyfile` | **Modified.** Upstreams become `{$VAR:127.0.0.1:N}` placeholders with production's current values as defaults. |
| `.env.template`, `.gitignore` | **Modified.** `COMPOSE_PROJECT_NAME=aurora`. |
| `dev-administration/scripts/dev-admin.sh` | **Modified (Task 9).** `HOST_REPO`, `CADDY_CONTAINER` and `--network` defaults carry the old project name; no other task touches this file. |
| `dev-administration/scripts/authz_test.py`, `scripts/negative_test_login_button.py` | **Modified (Task 9).** `tai-review-caddy-1` literals. |
| `dev-administration/README.md` | **Modified (Task 9).** Two stale container names. |
| `admin-asks.md` | **Modified (Task 9).** Container-side workspace path and a `git push origin master` predating the `main` rename. |
| `README.md` | **Rewritten (Task 10).** Predates Chunk 1: wrong Caddy container name, three services missing, `dev-administration` described as an out-of-tree repo. |
| `docs/superpowers/specs/2026-07-27-ephemeral-branching-design.md`, `docs/superpowers/specs/2026-07-25-multi-developer-provisioning-design.md` | **Modified (Task 9).** Forward-looking specs; their `tai-review` names become `aurora`. Every other `docs/` file is a dated historical record and is left verbatim. |
| `docs/testing/2026-07-28-chunk2-project-parameterised.md` | **New.** Required by the practices doc. |
| `docs/implementations/2026-07-28-chunk2-project-parameterised.md` | **New.** Required by the practices doc; updated every iteration. |
| `docs/issues/chunk2-spec-deltas.md` | **New.** Spec claims Chunks 1 and 2 have invalidated, so Chunk 3 does not inherit them. |
| `docs/post-implementation-steps.md` | **Modified.** Closes §D1; adds Chunk 2's human actions. |

---

## Task 0: Worktree and toolchain

**Files:**
- Create: `.worktrees/chunk2/` (worktree; its content is the branch)

**Interfaces:**
- Consumes: nothing.
- Produces: a worktree at `~/Desktop/tai-review/.worktrees/chunk2` with `.env` and `.venv`. Every later task's commands run there unless they explicitly say otherwise.

- [ ] **Step 1: Create the worktree**

```bash
cd ~/Desktop/tai-review
git worktree add .worktrees/chunk2 -b feat/project-parameterised main
```

Expected: `Preparing worktree (new branch 'feat/project-parameterised')`, then
`HEAD is now at c7126e2 Merge Chunk 1: the repo describes reality`.

- [ ] **Step 2: Give it an `.env` and a venv**

`.env` is gitignored, so the worktree has none and `docker compose config` cannot resolve variables there.

```bash
cd ~/Desktop/tai-review/.worktrees/chunk2
cp ~/Desktop/tai-review/.env .env
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet pytest pyyaml typer
.venv/bin/python -m pytest --version
```

Expected: a pytest version string, exit 0.

- [ ] **Step 3: Establish the baseline**

```bash
cd ~/Desktop/tai-review/.worktrees/chunk2
.venv/bin/python -m pytest tests dev-administration/tests -q 2>&1 | tail -5
docker compose config --quiet && echo CONFIG_OK
```

Expected: `1 failed, 33 passed` — 6 from `tests/`, 27 passing plus 1 failing from `dev-administration/tests`. The failure is `test_caddy_utils.py::test_generate_caddy_agents_conf`. `CONFIG_OK`.

**Do not "fix" that failure by deleting assertions.** Its resolution is Task 6 and is evidence-driven.

---

## Task 1: Make the conformance gate profile-aware (fixes F1)

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_repo_conformance.py`

**Interfaces:**
- Consumes: nothing.
- Produces, in `tests/conftest.py`: `compose_config(all_profiles: bool = True) -> dict`, `project_containers(project: str = PRODUCTION_PROJECT) -> dict[str, str]` (service → container name), `inspect_container(name: str) -> dict`, `all_container_names() -> list[str]`, and `ALLOWED_EXTERNAL_BINDS: tuple[Path, ...]`. Every later task's tests consume these.

**Context the implementer needs:** Chunk 1 discovered empirically that adding `profiles:` to a service removes it from `docker compose config` output, so `test_no_undeclared_containers_in_project` fails on a container that *is* declared. Task 5 gives every agent service a `profiles:` key, so this must be fixed first or Task 5 cannot go green.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_repo_conformance.py` (add `import inspect` and `import os` to its imports; `subprocess` is already there):

```python
def test_compose_config_sees_profiled_services(tmp_path):
    """Regression guard for the defect that broke Chunk 1's conformance gate.

    A service carrying `profiles:` is OMITTED from `docker compose config`
    output unless its profile is active. A gate built on that output then
    reports a declared-but-profiled service's container as *undeclared*.
    COMPOSE_PROFILES="*" activates every profile, which is why
    conftest.compose_config() sets it.

    Self-contained on purpose: it pins the Compose behaviour this repo's
    gate depends on, without depending on this repo's compose.yml.
    """
    (tmp_path / "compose.yml").write_text(
        "services:\n"
        "  always:\n"
        "    image: alpine\n"
        "    command: sleep 1\n"
        "  gated:\n"
        "    image: alpine\n"
        "    command: sleep 1\n"
        '    profiles: ["manual"]\n'
    )

    def services(profiles: str | None) -> list[str]:
        env = dict(os.environ)
        env.pop("COMPOSE_PROFILES", None)
        if profiles is not None:
            env["COMPOSE_PROFILES"] = profiles
        result = subprocess.run(
            ["docker", "compose", "config", "--services"],
            cwd=tmp_path, capture_output=True, text=True, check=True, env=env,
        )
        return sorted(line.strip() for line in result.stdout.split() if line.strip())

    assert services(None) == ["always"], (
        "Compose no longer hides inactive-profile services — re-derive the "
        "gate's assumptions before trusting conftest.compose_config()"
    )
    assert services("*") == ["always", "gated"]


def test_conformance_gate_asks_for_all_profiles():
    """Pins the mechanism, not just the outcome: a future edit that drops
    COMPOSE_PROFILES from compose_config() would silently blind the gate
    again, and every other test here would still pass."""
    from conftest import compose_config

    source = inspect.getsource(compose_config)
    assert "COMPOSE_PROFILES" in source and '"*"' in source, (
        'compose_config() must pass COMPOSE_PROFILES="*" — see '
        "test_compose_config_sees_profiled_services for why"
    )
```

- [ ] **Step 2: Run to verify**

```bash
cd ~/Desktop/tai-review/.worktrees/chunk2
.venv/bin/python -m pytest tests/test_repo_conformance.py -k "profile" -v
```

Expected: `test_compose_config_sees_profiled_services` **PASSES** (it asserts Compose's behaviour, which is already true), `test_conformance_gate_asks_for_all_profiles` **FAILS** — `compose_config()` does not set `COMPOSE_PROFILES`.

- [ ] **Step 3: Rewrite `tests/conftest.py`**

```python
import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# The project whose running containers we conform to. Deliberately NOT
# derived from `docker compose config`: inside a git worktree the compose
# project name comes from the directory basename, which matches no running
# containers and would make the conformance assertion vacuous.
PRODUCTION_PROJECT = os.environ.get("AURORA_PROJECT", "tai-review")

# Host paths a service may legitimately bind from outside the repo. Anything
# else must resolve inside REPO_ROOT, or a second copy of this stack would
# silently share production's state — which is the whole point of Chunk 2.
ALLOWED_EXTERNAL_BINDS = (
    Path("/var/run/docker.sock"),
    Path("/var/run/tailscale"),
    Path("/etc/localtime"),
)


def compose_config(all_profiles: bool = True) -> dict:
    """Fully resolved compose configuration for the repo, as a dict.

    COMPOSE_PROFILES="*" is set for a reason that cost Chunk 1 a working
    gate: a service carrying `profiles:` is omitted from this output unless
    its profile is active, so its still-labelled container reads as
    *undeclared*. Verified on Compose v5.3.1 — see
    tests/test_repo_conformance.py::test_compose_config_sees_profiled_services.

    Pass all_profiles=False to ask the different question "what would a
    default `docker compose up` actually start?".
    """
    env = dict(os.environ)
    env.pop("COMPOSE_PROFILES", None)
    if all_profiles:
        env["COMPOSE_PROFILES"] = "*"
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return json.loads(result.stdout)


def is_tracked(path: Path) -> bool:
    """True if git tracks at least one file under `path`."""
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def project_containers(project: str = PRODUCTION_PROJECT) -> dict[str, str]:
    """Map compose service name -> container name for one project.

    Includes stopped containers: a stopped container still holds its name,
    its ports and its binds, and is still something the repo must describe.
    """
    result = subprocess.run(
        [
            "docker", "ps", "-a",
            "--filter", f"label=com.docker.compose.project={project}",
            "--format", '{{.Label "com.docker.compose.service"}}\t{{.Names}}',
        ],
        capture_output=True, text=True, check=True,
    )
    mapping: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        service, _, container = line.partition("\t")
        if service.strip():
            mapping[service.strip()] = container.strip()
    return mapping


def inspect_container(name: str) -> dict:
    result = subprocess.run(
        ["docker", "inspect", name],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)[0]


def all_container_names() -> list[str]:
    result = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        capture_output=True, text=True, check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


@pytest.fixture
def config() -> dict:
    return compose_config()
```

- [ ] **Step 4: Run the whole suite**

```bash
.venv/bin/python -m pytest tests -v
```

Expected: **8 passed** (Chunk 1's 6 plus these 2).

- [ ] **Step 5: Commit**

```bash
git -c user.name="supergoodname77" -c user.email="epascuales@outlook.com" \
  commit -am "test: make the conformance gate profile-aware

A service carrying profiles: is omitted from \`docker compose config\`
unless its profile is active, so its labelled container read as
undeclared and the gate failed. Verified fix: COMPOSE_PROFILES=\"*\".
Task 5 gives every agent service a profile, so this had to land first."
```

---

## Task 2: Declaration-vs-runtime conformance (fixes F4 and F5)

**Files:**
- Create: `tests/test_runtime_conformance.py`
- Delete: container `agent-authz` (the unlabelled, exited leftover)

**Interfaces:**
- Consumes: `compose_config()`, `project_containers()`, `inspect_container()`, `all_container_names()`, `ALLOWED_EXTERNAL_BINDS`, `PRODUCTION_PROJECT`, `REPO_ROOT`.
- Produces: the gate that Task 12's deploy is verified against.

**Context the implementer needs:** Chunk 1's gate compares service *names* only. AFFiNE passed it while declared at a bind path production had never used — a Critical defect that reached final review. This task asserts that what the repo *declares* is what the daemon is *running*, for the three attributes that actually differ when a stack is mis-parameterised: image, bind source, published port.

Note the deliberate asymmetry: these assert *runtime ⊆ declaration*. They cannot assert the converse, because a declared service may legitimately be stopped or (after Task 5) gated behind an inactive profile.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_runtime_conformance.py`:

```python
"""Declaration-vs-runtime conformance.

Chunk 1's gate compared service NAMES only. Nothing compared a declared
image, bind source or published port against what the daemon actually runs,
and that blind spot is exactly how a Critical defect reached final review:
AFFiNE was correctly "declared" at a bind path production had never used.

These assert runtime is a subset of declaration. They deliberately do NOT
assert the converse: a declared service may be legitimately stopped, or
(after compose.agents.yml lands) gated behind an inactive profile.
"""

from pathlib import Path

from conftest import (
    ALLOWED_EXTERNAL_BINDS,
    PRODUCTION_PROJECT,
    REPO_ROOT,
    all_container_names,
    compose_config,
    inspect_container,
    project_containers,
)


def _declared_image(service_name: str, service: dict) -> str:
    """What image Compose would use. A build-only service has no `image:` key
    and Compose synthesises `<project>-<service>` — itself project-scoped,
    which is on-theme for this chunk."""
    return service.get("image") or f"{PRODUCTION_PROJECT}-{service_name}"


def test_declared_image_matches_runtime():
    config = compose_config()
    mismatches = []
    for service, container in project_containers().items():
        declared = config["services"].get(service)
        if declared is None:
            continue  # covered by test_no_undeclared_containers_in_project
        expected = _declared_image(service, declared)
        actual = inspect_container(container)["Config"]["Image"]
        if actual != expected:
            mismatches.append((service, container, expected, actual))

    assert mismatches == [], (
        "Containers running an image the repo does not declare "
        "(service, container, declared, running): " + repr(mismatches)
    )


def test_declared_bind_sources_match_runtime():
    """Every bind a container actually holds must be declared, and must
    resolve either inside the repo or to an explicitly allowed host path.

    Both sides are resolved before comparison: `docker compose config`
    reports paths from Go's os.Getwd(), which trusts a stale $PWD, and on
    this host /home is a symlink to /var/home.
    """
    config = compose_config()
    problems = []
    for service, container in project_containers().items():
        declared_service = config["services"].get(service)
        if declared_service is None:
            continue
        declared = {
            Path(v["source"]).resolve()
            for v in declared_service.get("volumes", [])
            if v.get("type") == "bind"
        }
        for mount in inspect_container(container)["Mounts"]:
            if mount["Type"] != "bind":
                continue
            actual = Path(mount["Source"]).resolve()
            if actual not in declared:
                problems.append((service, container, str(actual), "undeclared bind"))
            elif actual not in ALLOWED_EXTERNAL_BINDS and (
                actual != REPO_ROOT and REPO_ROOT not in actual.parents
            ):
                problems.append((service, container, str(actual), "outside the repo"))

    assert problems == [], (
        "Bind mounts that are undeclared or escape the repo — a second copy "
        "of this stack would share production's state through them: "
        + repr(problems)
    )


def test_declared_published_ports_match_runtime():
    config = compose_config()
    problems = []
    for service, container in project_containers().items():
        declared_service = config["services"].get(service)
        if declared_service is None:
            continue
        declared = {
            (
                p.get("host_ip") or "0.0.0.0",
                str(p["published"]),
                f'{p["target"]}/{p.get("protocol", "tcp")}',
            )
            for p in declared_service.get("ports", [])
        }
        bindings = inspect_container(container)["HostConfig"]["PortBindings"] or {}
        for target, hosts in bindings.items():
            for host in hosts or []:
                actual = (host.get("HostIp") or "0.0.0.0", host.get("HostPort"), target)
                if actual not in declared:
                    problems.append((service, container, actual, sorted(declared)))

    assert problems == [], (
        "Containers publishing host ports the repo does not declare "
        "(service, container, running, declared): " + repr(problems)
    )


def test_every_container_on_the_project_network_carries_the_project_label():
    """A container with no compose labels is invisible to every
    project-label filter — including `docker compose down --remove-orphans`.
    Network membership is where it cannot hide: joining `<project>_default`
    is what gives it service DNS inside the stack.

    This is the exact shape the three `hermes-*` dev agents had before M4.
    """
    network = f"{PRODUCTION_PROJECT}_default"
    offenders = []
    for name in all_container_names():
        data = inspect_container(name)
        if network not in (data["NetworkSettings"]["Networks"] or {}):
            continue
        labels = data["Config"]["Labels"] or {}
        if labels.get("com.docker.compose.project") != PRODUCTION_PROJECT:
            offenders.append((name, data["State"]["Status"]))

    assert offenders == [], (
        f"Containers attached to {network} without the {PRODUCTION_PROJECT!r} "
        f"project label. Compose cannot see, stop or remove them: {offenders}"
    )
```

- [ ] **Step 2: Run to verify the last one fails**

```bash
.venv/bin/python -m pytest tests/test_runtime_conformance.py -v
```

Expected: the first three **PASS**; the fourth **FAILS** listing `[('agent-authz', 'exited')]`.

If any of the first three fail, **stop and report** — production has drifted from the repo in a way Chunk 1 did not catch. That is a finding, not a step to work around.

- [ ] **Step 3: Remove the unlabelled leftover**

Confirm both facts before removing anything:

```bash
docker inspect agent-authz --format '{{.State.Status}} {{.State.ExitCode}} {{json .Config.Labels}}'
docker inspect tai-review-agent-authz-1 --format '{{.State.Status}} {{index .Config.Labels "com.docker.compose.project"}}'
```

Expected: `exited 137 {}` (no labels at all) and `running tai-review`. Only then:

```bash
docker rm agent-authz
```

Expected: `agent-authz` echoed. This removes a **stopped** container; nothing is serving from it.

- [ ] **Step 4: Re-run**

```bash
.venv/bin/python -m pytest tests/test_runtime_conformance.py -v
```

Expected: **4 passed.**

- [ ] **Step 5: Commit**

```bash
git add tests/test_runtime_conformance.py
git -c user.name="supergoodname77" -c user.email="epascuales@outlook.com" \
  commit -m "test: assert the repo's declarations match what Docker runs

Chunk 1's gate compared service names only, which is how AFFiNE passed
while declared at a bind path production had never used. These compare
image, bind source and published port against docker inspect, and close
the unlabelled-container hole via project-network membership."
```

---

## Task 3: Project identity module and the §5.3 guard

**Files:**
- Create: `dev-administration/dev_administration/project.py`
- Create: `dev-administration/tests/test_project.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces, all in `dev_administration.project`:
  - `class ProjectMismatch(RuntimeError)`
  - `current_project() -> str`
  - `network_name(project: str | None = None) -> str`
  - `container_project(container: str) -> str | None`
  - `assert_same_project(container: str) -> None`
  - `find_service_container(service: str, project: str | None = None) -> str`
  - `project_services(project: str | None = None) -> dict[str, str]`
  - `agent_volume(username: str, project: str | None = None) -> str`

**Context the implementer needs:** Spec §5.3 is the load-bearing safety control of the whole design — D12 promoted it from defense-in-depth precisely because Hermes and dev-admin both keep the docker socket. Today `provision.py` hardcodes `CADDY_CONTAINER=tai-review-caddy-1` as a fallback literal, `docker_utils.NETWORK = "tai-review_default"`, and `provision.py` passes `network="tai-review_default"` inline at the profile-install step. A branch's `reconcile` running with any of those would rewrite **production's** Caddy configuration.

`current_project()` prefers **self-inspection** over the environment, because an environment variable can be stale or inherited: spec §4.1 renders a branch's `.env` *from production's*, so a failed `COMPOSE_PROJECT_NAME` override would leave a branch believing it is production. The container's own label cannot lie. Verified on this host: `docker inspect dev-admin --format '{{.Config.Hostname}}'` → `7692288ed82b`, the short container ID, whose `com.docker.compose.project` label is `tai-review`.

- [ ] **Step 1: Write the failing tests**

Create `dev-administration/tests/test_project.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from dev_administration.project import (
    ProjectMismatch,
    agent_volume,
    assert_same_project,
    container_project,
    current_project,
    find_service_container,
    network_name,
    project_services,
)


def _completed(stdout: str = "", returncode: int = 0):
    return MagicMock(returncode=returncode, stdout=stdout, stderr="")


@patch("dev_administration.project.Path.read_text", return_value="7692288ed82b\n")
@patch("dev_administration.project.subprocess.run")
def test_current_project_prefers_self_inspection(mock_run, _read):
    """The container's own label cannot be stale. COMPOSE_PROJECT_NAME can:
    spec §4.1 renders a branch's .env FROM production's, so a failed
    override would silently point a branch operation at production."""
    mock_run.return_value = _completed("br-demo\n")
    with patch.dict("os.environ", {"COMPOSE_PROJECT_NAME": "tai-review"}):
        assert current_project() == "br-demo"


@patch("dev_administration.project.Path.read_text", side_effect=OSError)
@patch("dev_administration.project.subprocess.run")
def test_current_project_falls_back_to_env_outside_a_container(mock_run, _read):
    with patch.dict("os.environ", {"COMPOSE_PROJECT_NAME": "br-demo"}):
        assert current_project() == "br-demo"


@patch("dev_administration.project.Path.read_text", side_effect=OSError)
@patch("dev_administration.project.subprocess.run")
def test_current_project_refuses_to_guess(mock_run, _read):
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ProjectMismatch) as exc:
            current_project()
    assert "COMPOSE_PROJECT_NAME" in str(exc.value)


@patch("dev_administration.project.current_project", return_value="br-demo")
def test_network_name_is_derived(_cp):
    assert network_name() == "br-demo_default"
    assert network_name("tai-review") == "tai-review_default"


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
def test_assert_same_project_allows_own_project(mock_run, _cp):
    mock_run.return_value = _completed("br-demo\n")
    assert_same_project("br-demo-caddy-1")  # must not raise


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
def test_assert_same_project_refuses_another_project(mock_run, _cp):
    """The single most important safety assertion in the build: a
    branch-context operation aimed at production's Caddy must refuse."""
    mock_run.return_value = _completed("tai-review\n")
    with pytest.raises(ProjectMismatch) as exc:
        assert_same_project("tai-review-caddy-1")
    message = str(exc.value)
    assert "tai-review-caddy-1" in message
    assert "tai-review" in message
    assert "br-demo" in message


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
def test_assert_same_project_refuses_an_unlabelled_container(mock_run, _cp):
    """An unlabelled container belongs to no project, so it can never be
    proven safe. Refusing is the only correct answer — and this is exactly
    the shape the imperative `docker run` dev agents had."""
    mock_run.return_value = _completed("\n")
    with pytest.raises(ProjectMismatch):
        assert_same_project("hermes-testuser")


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
def test_assert_same_project_refuses_a_missing_container(mock_run, _cp):
    mock_run.return_value = _completed("", returncode=1)
    with pytest.raises(ProjectMismatch):
        assert_same_project("does-not-exist")


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
def test_find_service_container_resolves_by_label(mock_run, _cp):
    """This replaces CADDY_CONTAINER=tai-review-caddy-1: the Caddy container
    is whichever container carries THIS project's label and the `caddy`
    service label, whatever it happens to be named."""
    mock_run.return_value = _completed("br-demo-caddy-1\n")
    assert find_service_container("caddy") == "br-demo-caddy-1"
    args = mock_run.call_args[0][0]
    assert "label=com.docker.compose.project=br-demo" in args
    assert "label=com.docker.compose.service=caddy" in args


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
def test_find_service_container_raises_when_absent(mock_run, _cp):
    mock_run.return_value = _completed("\n")
    with pytest.raises(ProjectMismatch):
        find_service_container("caddy")


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
def test_project_services_maps_service_to_container(mock_run, _cp):
    mock_run.return_value = _completed(
        "caddy\tbr-demo-caddy-1\nhermes-juan\tbr-demo-hermes-juan-1\n"
    )
    assert project_services() == {
        "caddy": "br-demo-caddy-1",
        "hermes-juan": "br-demo-hermes-juan-1",
    }


@patch("dev_administration.project.current_project", return_value="br-demo")
def test_agent_volume_is_project_scoped(_cp):
    """An unprefixed volume name is reachable from every project on the
    host — precisely how a branch would write into production's agent
    state. Compose namespaces them; so must we when we name one directly."""
    assert agent_volume("juan") == "br-demo_hermes-juan-home"
    assert agent_volume("juan", "tai-review") == "tai-review_hermes-juan-home"


@patch("dev_administration.project.subprocess.run")
def test_container_project_returns_none_for_unlabelled(mock_run):
    mock_run.return_value = _completed("\n")
    assert container_project("whatever") is None
```

- [ ] **Step 2: Run to verify they fail**

```bash
.venv/bin/python -m pytest dev-administration/tests/test_project.py -v
```

Expected: **collection error** — `ModuleNotFoundError: No module named 'dev_administration.project'`.

- [ ] **Step 3: Implement the module**

Create `dev-administration/dev_administration/project.py`:

```python
"""Project identity and the spec §5.3 safety guard.

Everything this package does to a container, volume or network is scoped to
exactly one Compose project. Per spec D12, Hermes and dev-admin both keep
`/var/run/docker.sock`, so Docker does NOT enforce that scoping for us — the
guard in this module is the only thing standing between a branch-context
operation and production. It is load-bearing, not defensive.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_PROJECT_LABEL = "com.docker.compose.project"
_SERVICE_LABEL = "com.docker.compose.service"


class ProjectMismatch(RuntimeError):
    """Raised when an operation would touch something outside this project."""


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def container_project(container: str) -> str | None:
    """The Compose project a container belongs to, or None if it carries no
    project label or does not exist."""
    result = _run([
        "docker", "inspect", "-f",
        f'{{{{index .Config.Labels "{_PROJECT_LABEL}"}}}}',
        container,
    ])
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def current_project() -> str:
    """This process's own Compose project.

    Self-inspection first, environment second. An environment variable can
    be stale or inherited: spec §4.1 renders a branch's .env FROM
    production's, so a failed COMPOSE_PROJECT_NAME override would leave a
    branch believing it is production. The container's own label cannot lie.

    Outside a container (the CLI run on the host) there is no label to read,
    so COMPOSE_PROJECT_NAME is required rather than defaulted — guessing
    here is exactly the failure this module exists to prevent.
    """
    try:
        container_id = Path("/etc/hostname").read_text().strip()
    except OSError:
        container_id = ""
    if container_id:
        own = container_project(container_id)
        if own:
            return own
    env = os.environ.get("COMPOSE_PROJECT_NAME", "").strip()
    if env:
        return env
    raise ProjectMismatch(
        "Cannot determine this process's Compose project: no project label on "
        "its own container and COMPOSE_PROJECT_NAME is unset. Refusing to "
        "guess — a wrong guess writes to another project's containers."
    )


def network_name(project: str | None = None) -> str:
    """The project's default bridge network."""
    return f"{project or current_project()}_default"


def agent_volume(username: str, project: str | None = None) -> str:
    """The project-scoped volume backing one developer's Hermes home.

    Mirrors what Compose does for `volumes: {hermes-<u>-home: {}}`. An
    unprefixed name is reachable from every project on the daemon, which is
    how a branch would end up writing into production's agent state.
    """
    return f"{project or current_project()}_hermes-{username}-home"


def assert_same_project(container: str) -> None:
    """Refuse to touch a container that is not ours.

    Spec §5.3: every mutating dev-admin operation asserts that the target
    container's com.docker.compose.project label equals its own
    COMPOSE_PROJECT_NAME, and refuses otherwise. An unlabelled or missing
    container is refused too — it cannot be proven to belong to us.
    """
    mine = current_project()
    theirs = container_project(container)
    if theirs is None:
        raise ProjectMismatch(
            f"Refusing to operate on {container!r}: it carries no "
            f"{_PROJECT_LABEL} label, so it cannot be proven to belong to "
            f"project {mine!r}."
        )
    if theirs != mine:
        raise ProjectMismatch(
            f"Refusing to operate on {container!r}: it belongs to project "
            f"{theirs!r}, not {mine!r}."
        )


def project_services(project: str | None = None) -> dict[str, str]:
    """Map service name -> container name for this project, stopped included."""
    proj = project or current_project()
    result = _run([
        "docker", "ps", "-a",
        "--filter", f"label={_PROJECT_LABEL}={proj}",
        "--format", '{{.Label "' + _SERVICE_LABEL + '"}}\t{{.Names}}',
    ])
    mapping: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        service, _, container = line.partition("\t")
        if service.strip():
            mapping[service.strip()] = container.strip()
    return mapping


def find_service_container(service: str, project: str | None = None) -> str:
    """Resolve a service to its container name within this project.

    This replaces the hardcoded CADDY_CONTAINER="tai-review-caddy-1". A
    branch's Caddy is `br-<name>-caddy-1`; production's is
    `tai-review-caddy-1`; neither name is knowable in advance, but the label
    pair always is.
    """
    proj = project or current_project()
    result = _run([
        "docker", "ps", "-a",
        "--filter", f"label={_PROJECT_LABEL}={proj}",
        "--filter", f"label={_SERVICE_LABEL}={service}",
        "--format", "{{.Names}}",
    ])
    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not names:
        raise ProjectMismatch(
            f"No container for service {service!r} in project {proj!r}. "
            "Has `docker compose up -d` run for this project?"
        )
    return names[0]
```

- [ ] **Step 4: Run**

```bash
.venv/bin/python -m pytest dev-administration/tests/test_project.py -v
```

Expected: **13 passed.**

- [ ] **Step 5: Commit**

```bash
git add dev-administration/dev_administration/project.py dev-administration/tests/test_project.py
git -c user.name="supergoodname77" -c user.email="epascuales@outlook.com" \
  commit -m "feat: project identity module and the spec 5.3 label guard

Self-inspection first, COMPOSE_PROJECT_NAME second, refuse to guess third.
find_service_container() replaces the hardcoded tai-review-caddy-1 by
resolving the compose service label within this project.

Not yet wired into any caller — that is the next task."
```

---

## Task 4: Wire the guard into every mutating entry point

**Files:**
- Modify: `dev-administration/dev_administration/docker_utils.py`
- Modify: `dev-administration/dev_administration/caddy_utils.py`
- Modify: `dev-administration/dev_administration/verify.py`
- Create: `dev-administration/tests/test_guard_coverage.py`
- Modify: `dev-administration/tests/test_docker_utils.py`

**Interfaces:**
- Consumes: `dev_administration.project` from Task 3.
- Produces: `docker_utils` and `caddy_utils` with `NETWORK` and every hardcoded container name removed, and every mutating function guarded. `docker_utils.run_container_detached` is **deleted** — Task 5 replaces it with Compose.

**Context the implementer needs:** Spec §10.2 requires the guard to cover **every mutating entry point, not a representative sample**. The enumeration below is exhaustive as of `c7126e2`:

| Module | Function | Mutating? | Guard |
|---|---|---|---|
| `docker_utils` | `volume_exists`, `container_exists`, `container_status`, `list_containers`, `list_volumes` | no (read) | none |
| `docker_utils` | `create_volume` | yes | project-scoped name asserted, compose labels applied |
| `docker_utils` | `run_container_detached` | yes | **deleted** (Task 5) |
| `docker_utils` | `run_temp_container` | yes | network must be this project's |
| `docker_utils` | `stop_and_remove_container` | yes | `assert_same_project` |
| `docker_utils` | `docker_exec` | yes | `assert_same_project` |
| `caddy_utils` | `reload_caddy` | yes | `assert_same_project` |
| `caddy_utils` | `write_via_caddy` | yes | `assert_same_project` |
| `caddy_utils` | `write_denied_page` | yes | `assert_same_project` |
| `caddy_utils` | `write_agent_chooser` | yes | `assert_same_project` |

`caddy_utils.write_owners_map` writes a file path, not a container, so this mechanism does not apply — its isolation comes from the path being repo-relative, which Task 8 completes.

- [ ] **Step 1: Write the failing coverage test**

Create `dev-administration/tests/test_guard_coverage.py`:

```python
"""Spec §10.2: the project-label guard requires exhaustive coverage —
"every mutating entry point, not a representative sample".

This test is deliberately structural. A behavioural test per function would
keep passing while a NEW unguarded function was added tomorrow; this fails
the moment the enumeration and the source disagree.
"""

import inspect

from dev_administration import caddy_utils, docker_utils

# Every function that changes container, volume or network state. Adding a
# mutating function without adding it here is itself the bug.
MUTATING = {
    docker_utils: [
        "create_volume",
        "run_temp_container",
        "stop_and_remove_container",
        "docker_exec",
    ],
    caddy_utils: [
        "reload_caddy",
        "write_via_caddy",
        "write_denied_page",
        "write_agent_chooser",
    ],
}


def test_every_mutating_function_consults_the_guard():
    """`assert_same_project` guards a named container; `network_name` /
    `current_project` guard the two functions whose target is a network or a
    volume name rather than a container."""
    unguarded = []
    for module, names in MUTATING.items():
        for name in names:
            source = inspect.getsource(getattr(module, name))
            if not any(
                token in source
                for token in ("assert_same_project", "network_name", "current_project")
            ):
                unguarded.append(f"{module.__name__}.{name}")
    assert unguarded == [], (
        "Mutating functions with no project guard — per spec D12 the docker "
        f"socket is not enforced by Docker, so this IS the boundary: {unguarded}"
    )


def test_no_hardcoded_project_identity_remains():
    """The literals M5 exists to delete."""
    offenders = []
    for module in (caddy_utils, docker_utils):
        source = inspect.getsource(module)
        for literal in ("tai-review_default", "tai-review-caddy-1"):
            if literal in source:
                offenders.append(f"{module.__name__}: {literal}")
    assert offenders == [], f"Hardcoded production identity still present: {offenders}"


def test_run_container_detached_is_gone():
    """Per M4 agents are Compose services now. A surviving imperative
    `docker run` path would recreate the exact defect M4 removes: a
    container Compose cannot see, stop, or tear down."""
    assert not hasattr(docker_utils, "run_container_detached")
```

- [ ] **Step 2: Run to verify it fails**

```bash
.venv/bin/python -m pytest dev-administration/tests/test_guard_coverage.py -v
```

Expected: **3 failed** — every mutating function is unguarded, both literals are present, `run_container_detached` still exists.

- [ ] **Step 3: Rewrite `docker_utils.py`**

Replace `dev-administration/dev_administration/docker_utils.py` entirely with:

```python
from __future__ import annotations

import subprocess

from dev_administration.project import (
    ProjectMismatch,
    assert_same_project,
    current_project,
    network_name,
)

# NOTE: the module-level NETWORK = "tai-review_default" constant was deleted
# in Chunk 2 (M5). The network is derived per call from the running project,
# because a branch's is `br-<name>_default` and no constant can be right for
# both. HERMES_IMAGE now lives in agents_compose.py, which is what declares
# the agent services.


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def volume_exists(name: str) -> bool:
    result = _run(["docker", "volume", "inspect", name], check=False)
    return result.returncode == 0


def create_volume(name: str) -> None:
    """Create a project-scoped volume that Compose will adopt.

    The two labels are what make adoption clean: Compose treats a
    pre-existing volume carrying its project and volume labels as its own and
    preserves the contents (probed on Compose v5.3.1: seeded volume, then
    `docker compose create`, no warning, marker file intact). The
    `config-hash` label is deliberately not forged — Compose does not need it
    to adopt.

    Refuses an unprefixed name: `hermes-juan-home` is reachable from every
    project on the daemon, which is exactly how a branch would write into
    production's agent state.
    """
    project = current_project()
    prefix = f"{project}_"
    if not name.startswith(prefix):
        raise ProjectMismatch(
            f"Refusing to create volume {name!r}: it is not scoped to project "
            f"{project!r}. Build the name with project.agent_volume()."
        )
    _run([
        "docker", "volume", "create",
        "--label", f"com.docker.compose.project={project}",
        "--label", f"com.docker.compose.volume={name[len(prefix):]}",
        name,
    ], check=False)


def container_exists(name: str) -> bool:
    result = _run(["docker", "inspect", name], check=False)
    return result.returncode == 0


def container_status(name: str) -> str | None:
    result = _run(["docker", "inspect", "-f", "{{.State.Status}}", name], check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def run_temp_container(
    image: str,
    command: list[str],
    volumes: dict[str, str] | None = None,
    env: dict[str, str] | None = None,
    network: str | None = None,
) -> str:
    """Run a throwaway container.

    An explicitly-passed network must be this project's. Callers that just
    want "our network" pass None and let the caller-side helper supply
    network_name(); the check here is what stops a stale literal from
    attaching a branch's temp container to production's bridge, where it
    would resolve production's service DNS.
    """
    own_network = network_name()
    if network is not None and network != own_network:
        raise ProjectMismatch(
            f"Refusing to attach a temp container to {network!r}: this "
            f"project's network is {own_network!r}."
        )
    cmd = ["docker", "run", "--rm"]
    if volumes:
        for host_path, container_path in volumes.items():
            cmd.extend(["-v", f"{host_path}:{container_path}"])
    if env:
        for key, value in env.items():
            cmd.extend(["-e", f"{key}={value}"])
    if network is not None:
        cmd.extend(["--network", network])
    cmd.append(image)
    cmd.extend(command)
    result = _run(cmd)
    return result.stdout.strip()


def stop_and_remove_container(name: str) -> None:
    assert_same_project(name)
    _run(["docker", "stop", name], check=False)
    _run(["docker", "rm", name], check=False)


def list_containers(prefix: str) -> list[str]:
    result = _run(["docker", "ps", "-a", "--format", "{{.Names}}"], check=False)
    if result.returncode != 0:
        return []
    return [
        name for name in result.stdout.strip().split("\n")
        if name.startswith(prefix) and name.strip()
    ]


def list_volumes(prefix: str) -> list[str]:
    result = _run(["docker", "volume", "ls", "--format", "{{.Name}}"], check=False)
    if result.returncode != 0:
        return []
    return [
        name for name in result.stdout.strip().split("\n")
        if name.startswith(prefix) and name.strip()
    ]


def docker_exec(name: str, command: str) -> str:
    assert_same_project(name)
    result = _run(["docker", "exec", name, "sh", "-c", command], check=False)
    return result.stdout.strip()
```

- [ ] **Step 4: Guard `caddy_utils.py`**

In `dev-administration/dev_administration/caddy_utils.py`:

1. Add to the module-level imports:

```python
from dev_administration.project import assert_same_project
```

2. Delete the function-local `import subprocess` / `import json` / `import os` / `import html` statements inside `write_owners_map`, `write_denied_page`, `write_agent_chooser` and `write_via_caddy`, and add `import html` and `import os` to the module-level imports (`json` and `subprocess` are already there).

3. Add `assert_same_project(container_name)` as the **first statement** of `reload_caddy`, `write_via_caddy`, `write_denied_page` and `write_agent_chooser`. For example:

```python
def reload_caddy(container_name: str) -> None:
    """Signal Caddy to reload its config.

    Guarded: a branch's reconcile reloading PRODUCTION's Caddy is the exact
    failure spec §5.3 names as the reason the guard exists.
    """
    assert_same_project(container_name)
    subprocess.run(
        ["docker", "exec", container_name, "caddy", "reload",
         "--config", "/etc/caddy/Caddyfile"],
        capture_output=True, text=True, check=False,
    )
```

- [ ] **Step 5: Remove the last literal from `verify.py`**

In `dev-administration/dev_administration/verify.py`, replace:

```python
CADDY = os.environ.get("CADDY_CONTAINER", "tai-review-caddy-1")
```

with:

```python
def _caddy_container() -> str:
    """Resolved from THIS project's compose labels rather than a fixed name,
    so `dev-admin verify` inside a branch checks the branch's Caddy.
    CADDY_CONTAINER remains an escape hatch, and every use site is guarded."""
    override = os.environ.get("CADDY_CONTAINER")
    if override:
        return override
    from dev_administration.project import find_service_container
    return find_service_container("caddy")


CADDY = _caddy_container()
```

Also update the module docstring's `Environment:` block:
`CADDY_CONTAINER   caddy container name (default: resolved from this project's compose labels)`.

- [ ] **Step 6: Update the `docker_utils` tests for the new seams**

Two existing tests break for a subtle reason worth stating: they patch
`dev_administration.docker_utils.subprocess.run`, but the guard lives in
`project.py` and calls `dev_administration.project.subprocess.run`. Unpatched,
`assert_same_project` would issue a **real** `docker inspect` against the test
host. Both patches are therefore required.

In `dev-administration/tests/test_docker_utils.py`, add `import pytest` and
`create_volume` to the imports, replace `test_create_volume_idempotent` with:

```python
@patch("dev_administration.docker_utils.current_project", return_value="tai-review")
@patch("dev_administration.docker_utils.subprocess.run")
def test_create_volume_applies_compose_labels(mock_run, _cp):
    """Compose adopts a pre-existing volume carrying its project and volume
    labels, preserving contents (probed on Compose v5.3.1). Without the
    labels it treats the volume as foreign."""
    mock_run.return_value = MagicMock(returncode=0)
    create_volume("tai-review_hermes-juan-home")
    args = mock_run.call_args[0][0]
    assert args[:3] == ["docker", "volume", "create"]
    assert "com.docker.compose.project=tai-review" in args
    assert "com.docker.compose.volume=hermes-juan-home" in args
    assert args[-1] == "tai-review_hermes-juan-home"


@patch("dev_administration.docker_utils.current_project", return_value="br-demo")
@patch("dev_administration.docker_utils.subprocess.run")
def test_create_volume_refuses_an_unprefixed_name(mock_run, _cp):
    from dev_administration.project import ProjectMismatch
    with pytest.raises(ProjectMismatch):
        create_volume("hermes-juan-home")
    mock_run.assert_not_called()
```

and replace `test_stop_and_remove_container` with:

```python
@patch("dev_administration.project.current_project", return_value="tai-review")
@patch("dev_administration.project.subprocess.run")
@patch("dev_administration.docker_utils.subprocess.run")
def test_stop_and_remove_container_stops_then_removes(mock_run, mock_guard, _cp):
    """Both subprocess modules must be patched: the guard runs in project.py,
    and an unpatched assert_same_project would issue a REAL docker inspect."""
    mock_guard.return_value = MagicMock(returncode=0, stdout="tai-review\n")
    mock_run.return_value = MagicMock(returncode=0)
    stop_and_remove_container("hermes-juan")
    assert mock_run.call_count == 2
    assert mock_run.call_args_list[0][0][0][:2] == ["docker", "stop"]
    assert mock_run.call_args_list[1][0][0][:2] == ["docker", "rm"]


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
@patch("dev_administration.docker_utils.subprocess.run")
def test_stop_and_remove_container_refuses_another_project(mock_run, mock_guard, _cp):
    """Spec §5.3's headline case, at the docker_utils layer: a branch-context
    teardown aimed at a production container must not issue `docker stop`."""
    from dev_administration.project import ProjectMismatch
    mock_guard.return_value = MagicMock(returncode=0, stdout="tai-review\n")
    with pytest.raises(ProjectMismatch):
        stop_and_remove_container("tai-review-caddy-1")
    mock_run.assert_not_called()
```

- [ ] **Step 7: Run the package suite**

```bash
.venv/bin/python -m pytest dev-administration/tests -v
```

Expected: `test_guard_coverage.py` **3 passed**, `test_project.py` **13 passed**, `test_docker_utils.py` **10 passed** (the original 8, with `test_create_volume_idempotent` and `test_stop_and_remove_container` each replaced by a pair).

Two suites fail at this commit, both expected and both owned by later tasks — record the exact text and move on:
- `test_provision.py` — 3 errors: it patches `run_container_detached`, which no longer exists. Task 5.
- `test_caddy_utils.py::test_generate_caddy_agents_conf` — the inherited failure. Task 6.

- [ ] **Step 8: Commit**

```bash
git add dev-administration/
git -c user.name="supergoodname77" -c user.email="epascuales@outlook.com" \
  commit -m "feat: enforce the project-label guard on every mutating operation (M5)

Deletes docker_utils.NETWORK, verify.py's CADDY_CONTAINER literal, and
run_container_detached. Every docker exec / stop / rm / volume create now
asserts the target carries this project's label first. Per D12 the socket
is not enforced by Docker, so this is the boundary.

test_provision.py fails at this commit — it patches the deleted
run_container_detached. Task 5 replaces that code path with Compose."
```

---

## Task 5: Generate `compose.agents.yml` (M4)

**Files:**
- Create: `dev-administration/dev_administration/agents_compose.py`
- Create: `dev-administration/tests/test_agents_compose.py`
- Create: `compose.agents.yml` (generated, **committed**)
- Modify: `compose.yml`, `.gitignore`, `.env.template`
- Modify: `dev-administration/dev_administration/provision.py`, `cli.py`
- Modify: `dev-administration/tests/test_provision.py`
- Modify: `tests/test_repo_conformance.py`

**Interfaces:**
- Consumes: `dev_administration.project` (Task 3), the guarded `docker_utils` (Task 4), `compose_config()` (Task 1).
- Produces:
  - `agents_compose.AgentSpec` — frozen dataclass: `username: str`, `display_name: str`, `service: str`, `container_name: str`, `volume: str`, `host_port: int | None`, `profiles: tuple[str, ...]`, `env_file: str`
  - `agents_compose.DEFAULT_BASE_PORT: int = 9120`
  - `agent_specs(devs: list[DeveloperConfig], base_port: int = DEFAULT_BASE_PORT, publish_ports: bool = True) -> list[AgentSpec]`
  - `render_agents_compose(specs: list[AgentSpec], domain_var: str = "DOMAIN_NAME") -> str`
  - `dev-admin render-agents [--output PATH] [--check]`
  - A committed `compose.agents.yml` at the repo root.
  - `ProvisionConfig` gains `project: str`, `base_port: int`, `upstream_mode: str`, `agent_env_dir: str`.

### Decisions this task settles

**Committed, not gitignored.** Compose's `include:` is a hard failure when the target file is missing — probed: `open …/compose.agents.yml: no such file or directory`. A gitignored generated file would therefore break Chunk 1's acceptance gate (`test_fresh_worktree_resolves_compose_config`) in every fresh worktree, which is the exact property Chunk 1 exists to protect. Regenerated by `dev-admin render-agents`; drift is caught by a test.

**Profiles, not per-branch file rewriting.** Each agent gets `profiles: ["agents", "agent-<username>"]`. Production's `.env` sets `COMPOSE_PROFILES=agents`; Chunk 3's branch `.env` sets `COMPOSE_PROFILES=agent-<user>` to satisfy D7 without editing a tracked file inside the worktree — which would leave the worktree dirty and make every `aurora branch down` require `--force`. Probed: `COMPOSE_PROFILES` read from `.env` selects correctly, and `COMPOSE_PROFILES="*"` renders all of them for the conformance gate.

**`container_name:` is kept.** Production's `hermes-<user>` names are load-bearing today (`ssh_utils.add_ssh_key` writes `docker exec -it hermes-<user> bash`; operator habit and docs assume them). Spec D8 already plans `container_name: !reset null` in `compose.branch.yml`, which is what makes them safe in a branch. Task 12 pins the enumeration so Chunk 3 cannot miss one.

**Volumes become project-scoped.** `hermes-<user>-home` → `tai-review_hermes-<user>-home`. Spec §5.1 states that project-prefixed volumes are what makes "`down -v` provably cannot reach `tai-review_*`" structural rather than conventional; an unprefixed or `external: true` volume would leave that guarantee to convention. This needs a one-time data migration — Step 8, which copies rather than moves so the old volumes remain the rollback.

**`reconcile` no longer starts agents.** It renders the file, ensures the volume and its `.env`/profile, writes the per-agent OIDC env file, then *verifies* Compose has a container for each desired agent — emitting a `container.missing` warning with the exact command if not. Compose is what starts containers. This is checked rather than assumed: the `dev-admin` image installs Debian's `docker.io`, which does **not** include the Compose plugin, so `docker compose` is not reliably available inside that container. Chunk 3's `aurora branch up` runs `docker compose up -d` from the host after `reconcile`, so the branch flow closes there.

- [ ] **Step 1: Write the failing renderer tests**

Create `dev-administration/tests/test_agents_compose.py`:

```python
import yaml

from dev_administration.agents_compose import (
    agent_specs, render_agents_compose,
)
from dev_administration.models import DeveloperConfig

DEVS = [
    DeveloperConfig(username="juan", display_name="Juan", forgejo_user="juan"),
    DeveloperConfig(username="ethan", display_name="Ethan", forgejo_user="ethan"),
]


def test_agent_specs_allocate_sequential_ports():
    specs = agent_specs(DEVS, base_port=9120)
    assert [s.host_port for s in specs] == [9120, 9121]
    assert [s.service for s in specs] == ["hermes-juan", "hermes-ethan"]
    assert [s.container_name for s in specs] == ["hermes-juan", "hermes-ethan"]
    assert [s.volume for s in specs] == ["hermes-juan-home", "hermes-ethan-home"]


def test_agent_specs_publish_nothing_when_asked():
    """A branch publishes no host ports at all (spec §5.1): port collision
    becomes unrepresentable rather than merely avoided."""
    specs = agent_specs(DEVS, base_port=9120, publish_ports=False)
    assert [s.host_port for s in specs] == [None, None]


def test_agent_specs_carry_both_profiles():
    assert agent_specs(DEVS)[0].profiles == ("agents", "agent-juan")


def test_render_is_valid_yaml_with_one_service_per_developer():
    doc = yaml.safe_load(render_agents_compose(agent_specs(DEVS)))
    assert sorted(doc["services"]) == ["hermes-ethan", "hermes-juan"]
    assert sorted(doc["volumes"]) == ["hermes-ethan-home", "hermes-juan-home"]


def test_rendered_service_is_compose_managed_not_docker_run():
    """The whole point of M4: without this, `docker compose down` cannot see
    a developer's agent and a branch stack has no agents at all."""
    doc = yaml.safe_load(render_agents_compose(agent_specs(DEVS)))
    juan = doc["services"]["hermes-juan"]
    assert juan["image"] == "nousresearch/hermes-agent:latest"
    assert juan["container_name"] == "hermes-juan"
    assert juan["command"] == "gateway run"
    assert juan["restart"] == "unless-stopped"
    assert juan["volumes"] == ["hermes-juan-home:/opt/data"]
    assert juan["ports"] == ["127.0.0.1:9120:9119"]
    assert juan["profiles"] == ["agents", "agent-juan"]


def test_rendered_service_carries_the_uvicorn_forwarded_ips_fix():
    """FORWARDED_ALLOW_IPS rode on the imperative `docker run` and is
    load-bearing: without it uvicorn ignores X-Forwarded-Proto, writes the
    session cookie without Secure AND under a different name, and the user
    ping-pongs between the dashboard and the sign-in page."""
    doc = yaml.safe_load(render_agents_compose(agent_specs(DEVS)))
    env = doc["services"]["hermes-juan"]["environment"]
    assert env["FORWARDED_ALLOW_IPS"] == "*"
    assert env["HERMES_HOME"] == "/opt/data"
    assert env["HERMES_DASHBOARD_HOST"] == "0.0.0.0"
    assert env["HERMES_DASHBOARD_PUBLIC_URL"] == "https://${DOMAIN_NAME}/agent/juan"


def test_rendered_service_reads_its_secrets_from_an_optional_env_file():
    """OIDC client id/secret are per-install secrets written by reconcile.
    They must not enter a committed file, and the reference must be optional
    so a fresh worktree still resolves `docker compose config` before
    reconcile has ever run (probed: absent optional env_file, exit 0)."""
    body = render_agents_compose(agent_specs(DEVS))
    doc = yaml.safe_load(body)
    assert doc["services"]["hermes-juan"]["env_file"] == [
        {"path": "./.agent-env/juan.env", "required": False}
    ]
    assert "CLIENT_SECRET" not in body


def test_render_has_no_host_ports_in_service_mode():
    doc = yaml.safe_load(render_agents_compose(agent_specs(DEVS, publish_ports=False)))
    assert "ports" not in doc["services"]["hermes-juan"]
    assert doc["services"]["hermes-juan"]["expose"] == ["9119"]


def test_render_is_deterministic():
    """The drift test compares bytes, so ordering must be stable."""
    assert render_agents_compose(agent_specs(DEVS)) == render_agents_compose(agent_specs(DEVS))


def test_render_announces_that_it_is_generated():
    body = render_agents_compose(agent_specs(DEVS))
    assert body.startswith("# GENERATED by `dev-admin render-agents`")
    assert "do not edit" in body


def test_render_of_no_developers_is_still_valid_compose():
    doc = yaml.safe_load(render_agents_compose([]))
    assert doc["services"] == {}
    assert doc["volumes"] == {}
```

- [ ] **Step 2: Run to verify they fail**

```bash
.venv/bin/python -m pytest dev-administration/tests/test_agents_compose.py -v
```

Expected: collection error — `No module named 'dev_administration.agents_compose'`.

- [ ] **Step 3: Implement the renderer**

Create `dev-administration/dev_administration/agents_compose.py`:

```python
"""Render per-developer Hermes agents as Compose services (spec M4).

Before this, agents were created by `docker run` in docker_utils, so they
carried no compose project label at all. Consequences, all verified on the
host: `docker compose down` could not see them, `--remove-orphans` could not
remove them, and a branch stack would have had no agents whatsoever.

The output is COMMITTED, not gitignored: Compose's `include:` is a hard
failure on a missing file, so a generated-but-absent fragment would break
`docker compose config` in every fresh worktree — precisely the property
Chunk 1 exists to guarantee. Drift is caught by
tests/test_repo_conformance.py::test_agents_compose_matches_developers_yaml.
"""

from __future__ import annotations

from dataclasses import dataclass

from dev_administration.models import DeveloperConfig

HERMES_IMAGE = "nousresearch/hermes-agent:latest"
DEFAULT_BASE_PORT = 9120  # 9119 is the admin agent's dashboard
AGENT_ENV_DIR = "./.agent-env"

_HEADER = """\
# GENERATED by `dev-admin render-agents` from developers.yaml — do not edit.
#
# Regenerate after ANY change to developers.yaml:
#     dev-admin render-agents
# tests/test_repo_conformance.py::test_agents_compose_matches_developers_yaml
# fails if this file and developers.yaml disagree.
#
# Profiles: `agents` activates every developer (production sets
# COMPOSE_PROFILES=agents in .env); `agent-<username>` activates exactly one,
# which is how spec D7's `--devs` provisions only the requesting developer in
# a branch without editing any tracked file inside the worktree.
"""


@dataclass(frozen=True)
class AgentSpec:
    username: str
    display_name: str
    service: str
    container_name: str
    volume: str
    host_port: int | None
    profiles: tuple[str, ...]
    env_file: str


def agent_specs(
    devs: list[DeveloperConfig],
    base_port: int = DEFAULT_BASE_PORT,
    publish_ports: bool = True,
) -> list[AgentSpec]:
    """One spec per developer, ports allocated in developers.yaml order.

    `publish_ports=False` is the branch case: spec §5.1 requires a branch to
    publish no host ports at all, so collision with production is
    unrepresentable rather than merely avoided.
    """
    return [
        AgentSpec(
            username=dev.username,
            display_name=dev.display_name,
            service=f"hermes-{dev.username}",
            container_name=f"hermes-{dev.username}",
            volume=f"hermes-{dev.username}-home",
            host_port=(base_port + index) if publish_ports else None,
            profiles=("agents", f"agent-{dev.username}"),
            env_file=f"{AGENT_ENV_DIR}/{dev.username}.env",
        )
        for index, dev in enumerate(devs)
    ]


def render_agents_compose(
    specs: list[AgentSpec],
    domain_var: str = "DOMAIN_NAME",
) -> str:
    """Render the Compose fragment.

    Hand-written YAML rather than yaml.dump so ${VAR} interpolation, comments
    and key order survive byte-for-byte — the drift test compares bytes.
    """
    if not specs:
        return _HEADER + "\nservices: {}\n\nvolumes: {}\n"

    lines: list[str] = [_HEADER, "services:"]
    for spec in specs:
        lines.extend([
            f"  {spec.service}:",
            f"    image: {HERMES_IMAGE}",
            f"    container_name: {spec.container_name}",
            "    profiles: [" + ", ".join(f'"{p}"' for p in spec.profiles) + "]",
            "    restart: unless-stopped",
            "    command: gateway run",
            "    volumes:",
            f"      - {spec.volume}:/opt/data",
            "    environment:",
            "      HERMES_HOME: /opt/data",
            '      HERMES_DASHBOARD: "1"',
            "      HERMES_DASHBOARD_HOST: 0.0.0.0",
            f"      HERMES_DASHBOARD_PUBLIC_URL: https://${{{domain_var}}}/agent/{spec.username}",
            "      FORGEJO_URL: ${FORGEJO_URL}",
            "      HERMES_DASHBOARD_OIDC_ISSUER: ${FORGEJO_URL}",
            # uvicorn only honours X-Forwarded-* from peers in
            # forwarded_allow_ips (default 127.0.0.1). Caddy reaches this
            # container from the bridge gateway, so without this uvicorn sees
            # scheme=http, writes the session cookie without Secure and under
            # a different NAME (__Secure- prefix), and the session written at
            # login is not read back — the user ping-pongs between the
            # dashboard and the sign-in page.
            '      FORWARDED_ALLOW_IPS: "*"',
            "    env_file:",
            # OIDC client id/secret are per-install secrets written by
            # `dev-admin reconcile`. required: false so a fresh worktree still
            # resolves `docker compose config` before reconcile has ever run.
            f"      - path: {spec.env_file}",
            "        required: false",
            "    expose:",
            '      - "9119"',
        ])
        if spec.host_port is not None:
            lines.extend([
                "    ports:",
                f'      - "127.0.0.1:{spec.host_port}:9119"',
            ])
        lines.append("")
    lines.append("volumes:")
    lines.extend(f"  {spec.volume}:" for spec in specs)
    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 4: Run the renderer tests**

```bash
.venv/bin/python -m pytest dev-administration/tests/test_agents_compose.py -v
```

Expected: **11 passed.**

- [ ] **Step 5: Add the `render-agents` CLI command**

In `dev-administration/dev_administration/cli.py`, add to the imports:

```python
from dev_administration.agents_compose import (
    DEFAULT_BASE_PORT, agent_specs, render_agents_compose,
)
from dev_administration.project import current_project
```

and add this command:

```python
@app.command("render-agents")
def render_agents(
    output: str = typer.Option(
        "compose.agents.yml", "--output", "-o",
        help="Where to write the fragment (repo root by default)",
    ),
    check: bool = typer.Option(
        False, "--check",
        help="Exit 1 if the file on disk differs from a fresh render",
    ),
):
    """Regenerate compose.agents.yml from developers.yaml.

    Run after every developers.yaml change and commit the result: the file is
    `include:`d by compose.yml and Compose fails hard on a missing include,
    so it cannot be gitignored.
    """
    devs = _load_devs()
    base_port = int(os.environ.get("AGENT_BASE_PORT", DEFAULT_BASE_PORT))
    publish = os.environ.get("AGENT_UPSTREAM_MODE", "published") == "published"
    body = render_agents_compose(agent_specs(devs, base_port, publish))

    path = Path(output)
    if check:
        current = path.read_text() if path.exists() else ""
        if current != body:
            typer.echo(
                f"{output} is stale — run `dev-admin render-agents` and commit it.",
                err=True,
            )
            raise typer.Exit(1)
        typer.echo(f"{output} is up to date ({len(devs)} developers).")
        return

    path.write_text(body)
    typer.echo(f"Wrote {output} for {len(devs)} developers.")
```

- [ ] **Step 6: Generate the file and wire the include**

```bash
cd ~/Desktop/tai-review/.worktrees/chunk2
PYTHONPATH=dev-administration DEVELOPERS_YAML=developers.yaml \
  .venv/bin/python -m dev_administration.cli render-agents
grep -n 'hermes-\|127.0.0.1:' compose.agents.yml
```

Expected: `Wrote compose.agents.yml for 3 developers.`, and services `hermes-testuser`, `hermes-newuser`, `hermes-cumshit42069` on ports 9120 / 9121 / 9122 in that order (developers.yaml order).

Extend `compose.yml`'s existing `include:` block at the top of the file:

```yaml
include:
  - ./affine/compose.yml
  # Per-developer Hermes agents. GENERATED — see compose.agents.yml's header.
  # Before Chunk 2 these were created by `docker run` in dev_administration
  # and carried no compose label at all, so `docker compose down` could not
  # see them and a branch stack had none.
  - ./compose.agents.yml
```

Append to `.gitignore`:

```
# Per-agent OIDC credentials written by `dev-admin reconcile`. Repo-relative
# so a branch gets its own set; gitignored because they are secrets.
/.agent-env/
```

Create the directory now, so Docker does not create it root-owned at first `up`:

```bash
mkdir -p ~/Desktop/tai-review/.agent-env ~/Desktop/tai-review/.worktrees/chunk2/.agent-env
```

Append to `.env.template`:

```bash
# --- Project identity (Chunk 2 / M5) ---
# Set explicitly so dev-admin can fall back to it when run outside a
# container. INSIDE a container the compose project LABEL wins, which is what
# stops a branch that inherited this file from acting on production.
COMPOSE_PROJECT_NAME=tai-review
# `agents` activates every developer declared in compose.agents.yml. Without
# it `docker compose up -d` starts the stack with NO developer agents.
# A branch sets COMPOSE_PROFILES=agent-<username> instead (spec D7).
COMPOSE_PROFILES=agents
# published | service — see Task 6. Production's Caddy is network_mode: host
# and reaches agents on 127.0.0.1:<port>; a branch's Caddy shares the
# tailscale sidecar's netns and must use service DNS.
AGENT_UPSTREAM_MODE=published
AGENT_BASE_PORT=9120
```

Add the same four lines to **both** live `.env` files:

```bash
for f in ~/Desktop/tai-review/.env ~/Desktop/tai-review/.worktrees/chunk2/.env; do
  printf 'COMPOSE_PROJECT_NAME=tai-review\nCOMPOSE_PROFILES=agents\nAGENT_UPSTREAM_MODE=published\nAGENT_BASE_PORT=9120\n' >> "$f"
done
grep -c COMPOSE_PROFILES ~/Desktop/tai-review/.env
```

Expected: `1`.

- [ ] **Step 7: Add the conformance tests**

Append to `tests/test_repo_conformance.py` (add `import sys` to its imports):

```python
def _dev_administration_on_path():
    path = str(REPO_ROOT / "dev-administration")
    if path not in sys.path:
        sys.path.insert(0, path)


def test_agents_compose_matches_developers_yaml():
    """compose.agents.yml is generated AND committed. Committed, because
    Compose's `include:` is a hard failure on a missing file and a fresh
    worktree must still resolve `docker compose config`. Generated, so a
    developer is added by editing one YAML list — hence this drift check."""
    _dev_administration_on_path()
    from dev_administration.agents_compose import agent_specs, render_agents_compose
    from dev_administration.models import parse_developers_yaml

    devs = parse_developers_yaml(REPO_ROOT / "developers.yaml")
    expected = render_agents_compose(agent_specs(devs))
    actual = (REPO_ROOT / "compose.agents.yml").read_text()

    assert actual == expected, (
        "compose.agents.yml is stale relative to developers.yaml — run "
        "`dev-admin render-agents` and commit the result"
    )


def test_every_developer_has_a_declared_agent_service(config):
    _dev_administration_on_path()
    from dev_administration.models import parse_developers_yaml

    devs = parse_developers_yaml(REPO_ROOT / "developers.yaml")
    missing = [
        d.username for d in devs
        if f"hermes-{d.username}" not in config["services"]
    ]
    assert missing == [], (
        f"Developers with no compose service: {missing}. Before M4 these were "
        "`docker run` containers Compose could not see at all."
    )


def test_env_activates_the_agents_profile():
    """Agents carry `profiles:`, so a default `docker compose up -d` starts
    none of them unless COMPOSE_PROFILES says otherwise."""
    assert "COMPOSE_PROFILES=agents" in (REPO_ROOT / ".env").read_text(), (
        "Set COMPOSE_PROFILES=agents in .env, or `docker compose up -d` "
        "silently brings the stack up with no developer agents."
    )
```

- [ ] **Step 8: Migrate the three agent volumes to project scope**

The data lives in unprefixed volumes; Compose will look for `tai-review_hermes-<user>-home`. The three agent *containers* were already destroyed on the host, so nothing needs stopping and no service is interrupted.

Create the destination volumes with exactly the labels Compose adopts (probed on v5.3.1):

```bash
for u in testuser newuser cumshit42069; do
  docker volume create \
    --label com.docker.compose.project=tai-review \
    --label "com.docker.compose.volume=hermes-$u-home" \
    "tai-review_hermes-$u-home"
done
docker volume inspect tai-review_hermes-testuser-home --format '{{json .Labels}}'
```

Expected: three names echoed, then the two labels printed.

Copy the data:

```bash
for u in testuser newuser cumshit42069; do
  docker run --rm \
    -v "hermes-$u-home:/from:ro" \
    -v "tai-review_hermes-$u-home:/to" \
    alpine sh -c 'cp -a /from/. /to/'
done
```

Verify before trusting it — this is 70 MB of a developer's real Hermes home each:

```bash
for u in testuser newuser cumshit42069; do
  old=$(docker run --rm -v "hermes-$u-home:/v:ro" alpine sh -c 'du -sk /v | cut -f1')
  new=$(docker run --rm -v "tai-review_hermes-$u-home:/v:ro" alpine sh -c 'du -sk /v | cut -f1')
  echo "$u old=${old}K new=${new}K"
done
```

Expected: the two numbers match for each developer. If any differ, **stop** — do not let Compose start an agent on a partial copy.

The old unprefixed volumes are deliberately **left in place** as the rollback path; removing them is a human step in `docs/post-implementation-steps.md`.

- [ ] **Step 9: Rewrite `provision.py` to stop running containers**

Edits to `dev-administration/dev_administration/provision.py`:

1. Delete the module-level `BASE_PORT = 9120` line (currently the second line of the file) and drop `run_container_detached` from the `docker_utils` import list. Add:

```python
from dev_administration.agents_compose import DEFAULT_BASE_PORT
from dev_administration.project import (
    agent_volume, current_project, find_service_container, network_name,
    project_services,
)
```

2. Add fields to `ProvisionConfig`, after `authorized_keys_path`:

```python
    project: str = ""
    base_port: int = DEFAULT_BASE_PORT
    upstream_mode: str = "published"
    agent_env_dir: str = "/agent-env"
```

and at the end of `__post_init__`:

```python
        if not self.project:
            self.project = current_project()
```

3. In `provision_developer`, change the signature's `host_port: int = 9120` to `host_port: int | None = None`, and change the volume name:

```python
    vol = agent_volume(name, config.project)
```

4. Replace the entire "5. Start persistent container with all env vars as -e flags" block (from `dev_env = {` through the `run_container_detached(...)` call and the `developer.provisioned` emit that follows it) with:

```python
    # 5. Hand the credentials to Compose.
    #
    # Before M4 this called `docker run` directly, producing a container with
    # NO compose project label: `docker compose down` could not see it,
    # `--remove-orphans` could not remove it, and a branch stack had no agents
    # at all. The container is now declared in compose.agents.yml. All this
    # step does is write the per-agent secrets Compose reads via `env_file:`
    # and confirm Compose has actually started it.
    #
    # Everything the old dev_env dict carried that is NOT a secret now lives
    # in compose.agents.yml — including FORWARDED_ALLOW_IPS, without which
    # uvicorn ignores X-Forwarded-Proto and login loops.
    os.makedirs(config.agent_env_dir, exist_ok=True)
    env_path = os.path.join(config.agent_env_dir, f"{name}.env")
    agent_env_lines = []
    if client_id:
        agent_env_lines.append(f"HERMES_DASHBOARD_OIDC_CLIENT_ID={client_id}")
    if client_secret:
        agent_env_lines.append(f"HERMES_DASHBOARD_OIDC_CLIENT_SECRET={client_secret}")
    tmp_path = f"{env_path}.tmp"
    with open(tmp_path, "w") as fh:
        fh.write("\n".join(agent_env_lines) + ("\n" if agent_env_lines else ""))
    os.replace(tmp_path, env_path)  # atomic: Compose never reads a partial file

    service = f"hermes-{name}"
    if service in project_services(config.project):
        events.append(_emit(
            notifier, "developer.provisioned", "info", name,
            f"Provisioned {service} (compose-managed)",
            service=service, volume=vol,
        ))
    else:
        events.append(_emit(
            notifier, "container.missing", "warning", name,
            f"No container for service {service} in project {config.project}. "
            f"Run: docker compose up -d {service}",
            service=service, volume=vol,
        ))
```

Delete the now-unused `container = f"hermes-{name}"` local at the top of the function.

5. In `deprovision_developer`, resolve the container by label rather than by name so the guard has something real to check:

```python
    container = project_services(config.project).get(f"hermes-{username}")
    vol = agent_volume(username, config.project)

    if container:
        stop_and_remove_container(container)  # guarded: asserts our project
    remove_ssh_key(username, config.authorized_keys_path)
```

and change the emitted message to reference `container or f"hermes-{username}"`.

6. In `reconcile`, replace the name-prefix container scan:

```python
    # Agents scoped to THIS project's labels. A name-prefix scan (`hermes-`)
    # would also match another project's agents on the same daemon, which is
    # exactly the cross-project bleed §5.3 forbids.
    services_now = project_services(config.project)
    actual = {
        svc[len("hermes-"):] for svc in services_now if svc.startswith("hermes-")
    }
```

7. Replace both `BASE_PORT + i` occurrences with `config.base_port + i`, and the hardcoded temp-container network at the profile-install step with:

```python
        network=network_name(config.project),
```

8. Replace the Caddy container resolution block:

```python
    # Resolved from THIS project's compose labels. The old code defaulted to
    # the literal "tai-review-caddy-1", which would have made a branch's
    # reconcile rewrite PRODUCTION's Caddy configuration — spec §5.3's
    # headline failure. CADDY_CONTAINER survives as an override, and every
    # write below is guarded and will refuse a foreign container.
    caddy_container = os.environ.get("CADDY_CONTAINER") or find_service_container(
        "caddy", config.project
    )
```

9. Replace `cli.py`'s `_load_config()`:

```python
def _load_config() -> ProvisionConfig:
    return ProvisionConfig(
        forgejo_url=os.environ["FORGEJO_URL"],
        forgejo_token=os.environ["FORGEJO_ADMIN_TOKEN"],
        aurora_profile_url=os.environ["AURORA_PROFILE_URL"],
        # No production default: a wrong domain writes production URLs into a
        # branch's Caddy config and its OAuth redirect URIs.
        domain=os.environ["DOMAIN_NAME"],
        caddy_container=os.environ.get("CADDY_CONTAINER", ""),
        authorized_keys_path=os.environ.get("AUTHORIZED_KEYS", "/app/authorized_keys"),
        project=os.environ.get("COMPOSE_PROJECT_NAME") or current_project(),
        base_port=int(os.environ.get("AGENT_BASE_PORT", DEFAULT_BASE_PORT)),
        upstream_mode=os.environ.get("AGENT_UPSTREAM_MODE", "published"),
        agent_env_dir=os.environ.get("AGENT_ENV_DIR", "/agent-env"),
    )
```

10. In `compose.yml`, update the `dev-admin` service. Delete the `- CADDY_CONTAINER=tai-review-caddy-1` line and its two-line comment, and add:

```yaml
      # No CADDY_CONTAINER: resolved from this project's compose labels.
      - COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-tai-review}
      - AGENT_BASE_PORT=${AGENT_BASE_PORT:-9120}
      - AGENT_UPSTREAM_MODE=${AGENT_UPSTREAM_MODE:-published}
      - AGENT_ENV_DIR=/agent-env
```

and add to its `volumes:` block:

```yaml
      # Where reconcile writes each agent's OIDC credentials; compose.agents.yml
      # reads them back as an optional env_file. Repo-relative, so a branch
      # writes its own.
      - ./.agent-env:/agent-env
```

- [ ] **Step 10: Update `test_provision.py`**

The three tests patch `run_container_detached`, which no longer exists. Replace the module's `CONFIG` and the first test with the following, and apply the same decorator changes to the other two:

```python
CONFIG = ProvisionConfig(
    forgejo_url="https://forgejo.example.com/git",
    forgejo_token="admin-token",
    aurora_profile_url="https://forgejo.example.com/git/admin/aurora-agent.git",
    domain="forgejo.example.com",
    caddy_container="",
    authorized_keys_path="/tmp/authorized_keys",
    project="tai-review",
)


@patch("dev_administration.provision.container_exists", return_value=False)
@patch("dev_administration.provision.volume_exists", return_value=False)
@patch("dev_administration.provision.create_volume")
@patch("dev_administration.provision.find_oauth2_app", return_value=None)
@patch("dev_administration.provision.create_oauth2_app",
       return_value=("client123", "secret456"))
@patch("dev_administration.provision.run_temp_container")
@patch("dev_administration.provision.network_name", return_value="tai-review_default")
@patch("dev_administration.provision.find_service_container",
       return_value="tai-review-caddy-1")
@patch("dev_administration.provision.project_services",
       return_value={"caddy": "tai-review-caddy-1", "hermes-juan": "hermes-juan"})
@patch("dev_administration.provision.generate_caddy_agents_conf", return_value="caddy-conf")
@patch("dev_administration.provision.generate_agents_json", return_value="[]")
@patch("dev_administration.provision.reload_caddy")
@patch("dev_administration.provision.open", new_callable=MagicMock)
@patch("dev_administration.provision.os.makedirs")
@patch("dev_administration.provision.os.replace")
def test_reconcile_provisions_new_developer(
    mock_replace, mock_makedirs, mock_open, mock_reload, mock_gen_json,
    mock_gen_conf, mock_services, mock_find_caddy, mock_network, mock_run_temp,
    mock_create_app, mock_find_app, mock_create_vol, mock_vol_exists,
    mock_container_exists,
):
    devs = [DeveloperConfig(username="juan", display_name="Juan", forgejo_user="juan")]
    events = reconcile(devs, StdoutNotifier(), CONFIG)
    # Volume name is project-scoped now: an unprefixed one is reachable from
    # every project on the daemon.
    mock_create_vol.assert_called_once_with("tai-review_hermes-juan-home")
    mock_create_app.assert_called_once()
    assert any(e.event_type == "developer.provisioned" for e in events)
```

Note `project_services` is patched to already contain `hermes-juan`, which is
what makes the `developer.provisioned` branch fire. For
`test_reconcile_skips_existing_healthy`, patch it to
`{"hermes-juan": "hermes-juan"}` and drop the `list_containers` patch; for
`test_reconcile_deprovisions_removed_developer`, patch it to
`{"hermes-maria": "hermes-maria"}` and keep `mock_stop.assert_called_with("hermes-maria")`.

Add a new test pinning the replaced behaviour:

```python
@patch("dev_administration.provision.project_services", return_value={})
@patch("dev_administration.provision.container_exists", return_value=False)
@patch("dev_administration.provision.volume_exists", return_value=True)
@patch("dev_administration.provision.find_oauth2_app", return_value=None)
@patch("dev_administration.provision.create_oauth2_app", return_value=("cid", "sec"))
@patch("dev_administration.provision.run_temp_container")
@patch("dev_administration.provision.network_name", return_value="tai-review_default")
@patch("dev_administration.provision.find_service_container", return_value="c")
@patch("dev_administration.provision.generate_caddy_agents_conf", return_value="")
@patch("dev_administration.provision.generate_agents_json", return_value="[]")
@patch("dev_administration.provision.reload_caddy")
@patch("dev_administration.provision.open", new_callable=MagicMock)
@patch("dev_administration.provision.os.makedirs")
@patch("dev_administration.provision.os.replace")
def test_reconcile_warns_instead_of_starting_a_container(
    mock_replace, mock_makedirs, mock_open, mock_reload, mock_gen_json,
    mock_gen_conf, mock_find_caddy, mock_network, mock_run_temp,
    mock_create_app, mock_find_app, mock_vol_exists, mock_container_exists,
    mock_services,
):
    """reconcile no longer creates containers — Compose does. When the
    service is not up it must say so loudly with the exact command, not
    silently succeed."""
    devs = [DeveloperConfig(username="juan", display_name="Juan", forgejo_user="juan")]
    events = reconcile(devs, StdoutNotifier(), CONFIG)
    missing = [e for e in events if e.event_type == "container.missing"]
    assert missing, "expected a container.missing warning"
    assert "docker compose up -d hermes-juan" in missing[0].message
```

- [ ] **Step 11: Run both suites**

```bash
cd ~/Desktop/tai-review/.worktrees/chunk2
.venv/bin/python -m pytest dev-administration/tests -v
.venv/bin/python -m pytest tests -v
docker compose config --quiet && echo CONFIG_OK
```

Expected: `dev-administration/tests` — everything passes except `test_caddy_utils.py::test_generate_caddy_agents_conf` (Task 6). `tests/` — all pass. `CONFIG_OK`.

Confirm the agents are in the resolved config, and correctly *inactive* by default:

```bash
docker compose config --services | grep hermes-
COMPOSE_PROFILES= docker compose config --services | grep -c hermes- || echo "0 (correct: profile inactive)"
```

Expected: three `hermes-*` services with `COMPOSE_PROFILES=agents` from `.env`; `0 (correct: profile inactive)` with it cleared.

- [ ] **Step 12: Commit**

```bash
git add compose.agents.yml compose.yml .gitignore .env.template dev-administration/ tests/
git -c user.name="supergoodname77" -c user.email="epascuales@outlook.com" \
  commit -m "feat: dev agents become compose services (M4)

compose.agents.yml is generated from developers.yaml by
\`dev-admin render-agents\` and COMMITTED — Compose's include: is a hard
failure on a missing file, so a gitignored fragment would break
\`docker compose config\` in every fresh worktree.

Each agent carries profiles: [agents, agent-<user>], which is how D7's
--devs will select one developer in a branch without dirtying the worktree.
Volumes are project-scoped (tai-review_hermes-<u>-home) so a branch's
\`down -v\` structurally cannot reach production's. reconcile no longer
docker-runs anything: it writes the agent's OIDC env file and verifies
Compose started the service."
```

---

## Task 6: Agent upstream addressing mode (M5) and the inherited test failure

**Files:**
- Modify: `dev-administration/dev_administration/caddy_utils.py`
- Modify: `dev-administration/dev_administration/provision.py`
- Modify: `dev-administration/tests/test_caddy_utils.py`

**Interfaces:**
- Consumes: `ProvisionConfig.upstream_mode` (Task 5).
- Produces, in `caddy_utils`:
  - `UpstreamMode = Literal["published", "service"]`
  - `agent_upstream(dev: dict, mode: UpstreamMode = "published") -> str`
  - `fjell_upstream(mode: UpstreamMode = "published") -> str`
  - `authz_upstream(mode: UpstreamMode = "published") -> str`
  - `generate_caddy_agents_conf(devs: list[dict], domain: str, mode: UpstreamMode = "published") -> str`

**Context the implementer needs — and the resolution of the open behavioural question.**

`docs/post-implementation-steps.md` §D1 records `test_generate_caddy_agents_conf` as a live behavioural question. It is now answered from source rather than opinion:

- **`fjell/src/routes/setup.rs:91` registers `/agent/{username}/setup`.** fjell expects the *full, unstripped* path. `handle_path` strips the matched prefix and would deliver bare `/setup`, which fjell does not route. **The generator's shipped `handle` is correct; the test's `handle_path` assertion is wrong.** Fix the test, not the generator.
- The same test's `assert "reverse_proxy fjell:9080"` is **older** than §D1 records. `git log -S` shows that string entering at `4e30ee6` and never being touched again; `63b23b7` ("Caddy host network mode — route to 127.0.0.1:port, not Docker DNS names") changed the *implementation* and updated other assertions but left this one — one commit *before* `97d695a`. So the test has carried at least three stale assertions, not one, and §D1's account should be corrected.
- That stale assertion is not merely stale — it describes the **branch** case. A branch's Caddy runs `network_mode: service:tailscale` (spec §4.2), sharing the sidecar's network namespace, where `127.0.0.1:9080` reaches nothing. `fjell:9080` is exactly right there. So the test is *split* rather than deleted: its published-mode half is corrected, its service-mode half becomes the new branch-addressing test.

Verified addressing facts: fjell listens on `0.0.0.0:9080`; agents expose `9119` and are reachable at `hermes-<user>:9119` by service DNS on the project network; `agent-authz` listens on `9140`.

- [ ] **Step 1: Rewrite the test**

Replace `test_generate_caddy_agents_conf` in `dev-administration/tests/test_caddy_utils.py` with (adding `import pytest` to the module imports):

```python
DEVS = [
    {"username": "juan", "display_name": "Juan", "host_port": 9120},
    {"username": "ethan", "display_name": "Ethan", "host_port": 9121},
]


def test_published_mode_routes_to_localhost_ports():
    """Production's Caddy is network_mode: host, so it cannot resolve Docker
    DNS and must reach every backend on a published 127.0.0.1 port."""
    conf = generate_caddy_agents_conf(
        DEVS, "superserver.tailc67a98.ts.net", mode="published"
    )
    assert "reverse_proxy 127.0.0.1:9120" in conf
    assert "reverse_proxy 127.0.0.1:9121" in conf
    assert "reverse_proxy 127.0.0.1:9080" in conf                # fjell
    assert "forward_auth @needs_authz 127.0.0.1:9140" in conf     # agent-authz


def test_service_mode_routes_by_service_dns():
    """A branch's Caddy is network_mode: service:tailscale — it shares the
    sidecar's netns, where 127.0.0.1 reaches nothing, and a branch publishes
    no host ports at all (spec §5.1). Service DNS is the only address that
    exists there."""
    conf = generate_caddy_agents_conf(
        DEVS, "aurora-demo.tailc67a98.ts.net", mode="service"
    )
    assert "reverse_proxy hermes-juan:9119" in conf
    assert "reverse_proxy hermes-ethan:9119" in conf
    assert "reverse_proxy fjell:9080" in conf
    assert "forward_auth @needs_authz agent-authz:9140" in conf
    assert "127.0.0.1" not in conf, (
        "A branch's Caddy cannot reach 127.0.0.1 — any localhost address left "
        "in the generated conf is a dead route"
    )


def test_setup_route_does_not_strip_its_prefix():
    """RESOLVED (Chunk 2); previously docs/post-implementation-steps.md §D1.

    fjell registers the route as `/agent/{username}/setup`
    (fjell/src/routes/setup.rs:91) — it expects the FULL path. `handle_path`
    strips the matched prefix and would deliver bare `/setup`, which fjell
    does not route. So `handle` is correct here, and the old
    `handle_path /agent/juan/setup` assertion was simply wrong.

    Note the deliberate contrast with the dashboard blocks, which DO use
    handle_path: Hermes wants the prefix stripped and re-supplied via
    X-Forwarded-Prefix.
    """
    conf = generate_caddy_agents_conf(DEVS, "example.ts.net")
    assert "handle /agent/juan/setup {" in conf
    assert "handle_path /agent/juan/setup" not in conf
    assert "handle_path /agent/juan/* {" in conf
    assert "handle_path /agent/ethan/* {" in conf


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        generate_caddy_agents_conf(DEVS, "example.ts.net", mode="magic")
```

- [ ] **Step 2: Run to verify**

```bash
.venv/bin/python -m pytest dev-administration/tests/test_caddy_utils.py -v
```

Expected: `test_published_mode_routes_to_localhost_ports` and `test_setup_route_does_not_strip_its_prefix` **PASS** (the generator already behaves that way); `test_service_mode_routes_by_service_dns` and `test_unknown_mode_is_rejected` **FAIL** — `generate_caddy_agents_conf()` takes no `mode`.

- [ ] **Step 3: Add the addressing mode**

In `dev-administration/dev_administration/caddy_utils.py`, add near the top:

```python
from typing import Literal

UpstreamMode = Literal["published", "service"]

# Production's Caddy is network_mode: host — it cannot resolve Docker DNS, so
# every backend must be reached on a published 127.0.0.1 port. A branch's
# Caddy is network_mode: service:tailscale (spec §4.2): it shares the
# sidecar's network namespace, 127.0.0.1 reaches nothing there, and the branch
# publishes no host ports at all. Same generator, two address spaces.
_FJELL_PORT = 9080
_AUTHZ_PORT = 9140
_AGENT_PORT = 9119


def _check_mode(mode: str) -> None:
    if mode not in ("published", "service"):
        raise ValueError(
            f"Unknown upstream mode {mode!r}; expected 'published' or 'service'"
        )


def agent_upstream(dev: dict, mode: UpstreamMode = "published") -> str:
    _check_mode(mode)
    if mode == "service":
        return f"hermes-{dev['username']}:{_AGENT_PORT}"
    return f"127.0.0.1:{dev.get('host_port', 9119)}"


def fjell_upstream(mode: UpstreamMode = "published") -> str:
    _check_mode(mode)
    return f"fjell:{_FJELL_PORT}" if mode == "service" else f"127.0.0.1:{_FJELL_PORT}"


def authz_upstream(mode: UpstreamMode = "published") -> str:
    _check_mode(mode)
    return (
        f"agent-authz:{_AUTHZ_PORT}" if mode == "service"
        else f"127.0.0.1:{_AUTHZ_PORT}"
    )
```

Change the signature to
`def generate_caddy_agents_conf(devs: list[dict], domain: str, mode: UpstreamMode = "published") -> str:`,
make `_check_mode(mode)` its first statement, and inside the per-developer loop
replace `port = dev.get("host_port", 9119)` with:

```python
        agent_addr = agent_upstream(dev, mode)
```

Then substitute, within that loop:

| Old | New |
|---|---|
| `"    reverse_proxy 127.0.0.1:9080",` | `f"    reverse_proxy {fjell_upstream(mode)}",` |
| `"    forward_auth @needs_authz 127.0.0.1:9140 {",` | `f"    forward_auth @needs_authz {authz_upstream(mode)} {{",` |
| every `f"reverse_proxy 127.0.0.1:{port}"` — **four sites**: the `@unauthenticated` inner proxy, the main `handle_path /agent/<u>/*` proxy, and the bare `handle_path /agent/<u>` proxy | `f"reverse_proxy {agent_addr}"` |

Update the docstring:

```python
    """Generate Caddy route blocks for per-developer agent dashboards.

    Each dev dict needs: username, host_port (int; published mode only).

    `mode` selects the address space:
      published — 127.0.0.1:<host_port>, for production's host-networked Caddy
      service   — hermes-<user>:9119, for a branch's Caddy sharing the
                  tailscale sidecar's netns, where 127.0.0.1 reaches nothing
    """
```

- [ ] **Step 4: Pass the mode through `reconcile`**

In `provision.py`'s `reconcile`, change:

```python
    conf = generate_caddy_agents_conf(dev_dicts, config.domain)
```

to:

```python
    conf = generate_caddy_agents_conf(dev_dicts, config.domain, mode=config.upstream_mode)
```

- [ ] **Step 5: Run**

```bash
.venv/bin/python -m pytest dev-administration/tests -v
```

Expected: **all pass.** This is the first point in the plan at which `dev-administration/tests` is fully green — the inherited failure is resolved, not deleted.

- [ ] **Step 6: Commit**

```bash
git add dev-administration/
git -c user.name="supergoodname77" -c user.email="epascuales@outlook.com" \
  commit -m "feat: agent Caddy config gains an upstream addressing mode (M5)

published -> 127.0.0.1:<published port> for production's host-networked
Caddy; service -> hermes-<user>:9119 / fjell:9080 / agent-authz:9140 for a
branch's Caddy, which shares the tailscale sidecar's netns and reaches no
localhost port of this stack.

Resolves the inherited test failure (post-implementation-steps §D1) with
evidence: fjell registers /agent/{username}/setup (routes/setup.rs:91), so
it needs the UNSTRIPPED path and \`handle\` is correct — the test's
handle_path assertion was wrong. The same test's stale
'reverse_proxy fjell:9080' dates from 63b23b7, one commit earlier than §D1
records, and turns out to describe the branch case; it is now the
service-mode assertion."
```

---

## Task 7: De-hardcode the static Caddyfile and the Hermes tailnet bind (M5)

**Files:**
- Modify: `Caddyfile`, `compose.yml`, `.env.template`
- Modify: `tests/test_repo_conformance.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: a `Caddyfile` whose upstreams are `{$VAR:<production default>}` placeholders, so the *same file* works host-networked and sidecar-networked.

**Context the implementer needs:** Spec D3 claims a branch "runs the *unmodified* prod Caddyfile with only `DOMAIN_NAME` differing". **That claim is false as written**, and this task repairs it. Production's `Caddyfile` hardcodes `127.0.0.1:3010` (AFFiNE, five blocks), `127.0.0.1:3000` (Forgejo) and `127.0.0.1:9080` (fjell). Under `network_mode: service:tailscale` the Caddy container shares the sidecar's network namespace — a bridge namespace, not the host's — so every one of those reaches nothing. Caddy already uses `{$VAR}` placeholders here (`{$DOMAIN_NAME}`, `{$CADDY_BASIC_AUTH_USER}`) and supports `{$VAR:default}`, so the change is mechanical and production-behaviour-neutral: the defaults are production's current values.

The Hermes service's `100.86.36.78:9119:9119` publish is the last hardcoded host identity in `compose.yml`; Chunk 1 explicitly deferred it here.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_repo_conformance.py`:

```python
CADDYFILE_UPSTREAM_VARS = ("AFFINE_UPSTREAM", "FORGEJO_UPSTREAM", "FJELL_UPSTREAM")


def test_caddyfile_has_no_hardcoded_upstreams():
    """Spec D3 wants a branch to run the SAME Caddyfile as production. It
    cannot while the upstreams are literal 127.0.0.1 addresses: a branch's
    Caddy runs network_mode: service:tailscale and shares the sidecar's
    network namespace, where no localhost port of this stack exists."""
    text = (REPO_ROOT / "Caddyfile").read_text()
    leftovers = [
        line.strip() for line in text.splitlines()
        if "reverse_proxy" in line and "127.0.0.1" in line
    ]
    assert leftovers == [], (
        f"Caddyfile still routes to literal localhost addresses: {leftovers}"
    )
    missing = [v for v in CADDYFILE_UPSTREAM_VARS if "{$" + v not in text]
    assert missing == [], f"Caddyfile does not parameterise: {missing}"


def test_compose_declares_no_literal_tailnet_ip():
    """100.86.36.78 is THIS host's tailnet address. A branch reaches its own
    address through its own sidecar and publishes nothing."""
    raw = (REPO_ROOT / "compose.yml").read_text()
    assert "100.86.36.78" not in raw, (
        "compose.yml still hardcodes this host's tailnet IP — use "
        "${HERMES_TAILNET_IP:-100.86.36.78}"
    )
```

- [ ] **Step 2: Run to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_repo_conformance.py -k "caddyfile or tailnet" -v
```

Expected: **both FAIL** — seven literal `reverse_proxy 127.0.0.1:*` lines and the literal `100.86.36.78`.

- [ ] **Step 3: Parameterise the Caddyfile**

In `Caddyfile` (line numbers as of `c7126e2`):

| Lines | Old | New |
|---|---|---|
| 13, 23, 27, 31, 34 | `reverse_proxy 127.0.0.1:3010` | `reverse_proxy {$AFFINE_UPSTREAM:127.0.0.1:3010}` |
| 40 | `reverse_proxy 127.0.0.1:3000` | `reverse_proxy {$FORGEJO_UPSTREAM:127.0.0.1:3000}` |
| 58 | `reverse_proxy 127.0.0.1:9080` | `reverse_proxy {$FJELL_UPSTREAM:127.0.0.1:9080}` |

Line 13 keeps its `{ header_up X-Forwarded-Prefix /affine }` body.

Add immediately below the opening `{$DOMAIN_NAME} {` line:

```
	# Upstream addresses are parameterised, not literal, because the SAME
	# file must work in two address spaces. Production's Caddy is
	# network_mode: host and reaches every backend on a published
	# 127.0.0.1 port — hence the defaults below. A branch's Caddy is
	# network_mode: service:tailscale (spec §4.2): it shares the sidecar's
	# network namespace, publishes no host ports, and must use Docker
	# service DNS. Set *_UPSTREAM in the branch's .env to switch.
```

- [ ] **Step 4: Wire the variables through Compose**

Add to the `caddy` service's `environment:` block in `compose.yml`:

```yaml
      - AFFINE_UPSTREAM=${AFFINE_UPSTREAM:-127.0.0.1:3010}
      - FORGEJO_UPSTREAM=${FORGEJO_UPSTREAM:-127.0.0.1:3000}
      - FJELL_UPSTREAM=${FJELL_UPSTREAM:-127.0.0.1:9080}
```

and change the `hermes` service's second published port:

```yaml
    ports:
      - 127.0.0.1:9119:9119
      # This host's tailnet address, so remote Hermes Desktop clients can
      # reach the admin dashboard. Parameterised because it is THIS host's
      # identity: a branch reaches its own address through its own sidecar
      # and publishes nothing (spec §5.1).
      - ${HERMES_TAILNET_IP:-100.86.36.78}:9119:9119
```

Append to `.env.template`:

```bash
# --- Caddy upstreams (Chunk 2 / M5) ---
# Defaults match production, whose Caddy is network_mode: host. A branch sets
# these to service DNS because its Caddy shares the tailscale sidecar's netns.
# AFFINE_UPSTREAM=127.0.0.1:3010
# FORGEJO_UPSTREAM=127.0.0.1:3000
# FJELL_UPSTREAM=127.0.0.1:9080
# This host's tailnet IP, used only for the admin Hermes dashboard publish.
HERMES_TAILNET_IP=100.86.36.78
```

and add `HERMES_TAILNET_IP=100.86.36.78` to both live `.env` files.

- [ ] **Step 5: Validate the Caddyfile before it can ever reach production**

```bash
cd ~/Desktop/tai-review/.worktrees/chunk2
docker run --rm -v "$PWD/Caddyfile:/etc/caddy/Caddyfile:ro" \
  -e DOMAIN_NAME=example.ts.net -e CADDY_BASIC_AUTH_USER=x \
  -e CADDY_BASIC_AUTH_HASH=y -e HERMES_SERVE_PORT=7444 \
  caddy:latest caddy validate --config /etc/caddy/Caddyfile 2>&1 | tail -5
```

Expected: the only error names the unresolvable `import /etc/caddy/Caddyfile.d/agents.conf`, which does not exist in a throwaway container. **Any other error must be fixed before continuing.**

Then prove the placeholders actually resolve to service DNS when asked:

```bash
docker run --rm -v "$PWD/Caddyfile:/etc/caddy/Caddyfile:ro" \
  -e DOMAIN_NAME=example.ts.net -e CADDY_BASIC_AUTH_USER=x \
  -e CADDY_BASIC_AUTH_HASH=y -e HERMES_SERVE_PORT=7444 \
  -e FJELL_UPSTREAM=fjell:9080 -e FORGEJO_UPSTREAM=forgejo:3000 \
  -e AFFINE_UPSTREAM=affine:3010 \
  caddy:latest caddy adapt --config /etc/caddy/Caddyfile 2>/dev/null \
  | grep -o '"dial":"[^"]*"' | sort -u
```

Expected: exactly `"dial":"affine:3010"`, `"dial":"forgejo:3000"`, `"dial":"fjell:9080"` — and **no** `127.0.0.1`.

And that the defaults still resolve to production's addresses when the variables are absent:

```bash
docker run --rm -v "$PWD/Caddyfile:/etc/caddy/Caddyfile:ro" \
  -e DOMAIN_NAME=example.ts.net -e CADDY_BASIC_AUTH_USER=x \
  -e CADDY_BASIC_AUTH_HASH=y -e HERMES_SERVE_PORT=7444 \
  caddy:latest caddy adapt --config /etc/caddy/Caddyfile 2>/dev/null \
  | grep -o '"dial":"[^"]*"' | sort -u
```

Expected: `"dial":"127.0.0.1:3000"`, `"dial":"127.0.0.1:3010"`, `"dial":"127.0.0.1:9080"` — production behaviour is unchanged.

- [ ] **Step 6: Run the tests**

```bash
.venv/bin/python -m pytest tests -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add Caddyfile compose.yml .env.template tests/
git -c user.name="supergoodname77" -c user.email="epascuales@outlook.com" \
  commit -m "feat: parameterise Caddy upstreams and the Hermes tailnet bind (M5)

Spec D3 claims a branch runs the UNMODIFIED prod Caddyfile. It could not:
every reverse_proxy target was a literal 127.0.0.1 port, and a branch's
Caddy runs network_mode: service:tailscale, sharing the sidecar's netns
where no such port exists. Now {\$VAR:127.0.0.1:N} with production's values
as defaults — verified byte-identical after \`caddy adapt\` with the
variables unset."
```

---

## Task 8: Repo-relative bind mounts (M6)

**Files:**
- Modify: `compose.yml`, `.gitignore`
- Modify: `tests/test_repo_conformance.py`
- Create: `~/Desktop/tai-review/.hermes/` (runtime state, gitignored)

**Interfaces:**
- Consumes: `ALLOWED_EXTERNAL_BINDS` (Task 1).
- Produces: a compose config in which no service binds a host path outside the repo except the three allowed ones.

**Context the implementer needs:** Two absolute mounts break spec §5.2's path-relativity guarantee:

```yaml
      - ~/.hermes:/opt/data
      - ~/Desktop/tai-review:/opt/data/workspace/tai-review
```

The first makes a branch share production's agent state; the second makes a branch's Hermes see production's tree instead of its own worktree.

Measured before writing this: `~/.hermes` is **2.7 GB**, of which `workspace/` is 159 MB. `workspace/tai/` holds the *old* AFFiNE + `postgrespg-tai` data that `docs/post-implementation-steps.md` §A.3 already schedules for deletion, part of it root-owned and **unreadable to the agent user** — a naive `cp -a` of the whole tree fails there. `workspace/tai-review` is a root-owned, empty directory: only the mount point Docker created for the second bind. **Neither needs copying**, so the migration copies everything *except* `workspace/` and recreates it empty. That is faster and drops 159 MB of dead weight.

`/var/home` is btrfs with 143 GB free, so `cp -a --reflink=auto` shares extents and costs approximately nothing.

**The copy is a copy, not a move.** `~/.hermes` is left completely untouched, so rollback is reverting two lines of `compose.yml` and restarting one container. Deleting `~/.hermes` is a human step scheduled in `docs/post-implementation-steps.md` after a soak.

**Deployment is deferred to Task 12**, per F3. That means one test — `test_declared_bind_sources_match_runtime` — goes **red between this task and Task 12's deploy**, because the running `hermes` container still holds `/var/home/supergoodname77/.hermes` while the repo now declares `./.hermes`. That is not a defect; it is the F3 property made visible by a test, and Task 12 Step 5 is where it goes green. Step 6 below says so explicitly so nobody "fixes" it by weakening the test.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_repo_conformance.py` (add `from conftest import ALLOWED_EXTERNAL_BINDS` to its imports):

```python
def test_no_service_binds_a_path_outside_the_repo(config):
    """Spec §5.2: `./forgejo`, `./Caddyfile.d`, `./agent-authz/data` are
    already relative, so a worktree's are its own. Two absolute mounts broke
    that — ~/.hermes made a branch share production's agent state, and
    ~/Desktop/tai-review made a branch's Hermes see production's tree.

    Both sides are resolved before comparison: `docker compose config`
    reports paths from Go's os.Getwd(), which trusts a stale $PWD, and on
    this host /home is a symlink to /var/home.
    """
    offending = []
    for name, service in config["services"].items():
        for volume in service.get("volumes", []):
            if volume.get("type") != "bind":
                continue
            source = Path(volume["source"]).resolve()
            if source in ALLOWED_EXTERNAL_BINDS:
                continue
            if source != REPO_ROOT and REPO_ROOT not in source.parents:
                offending.append((name, str(source), volume["target"]))

    assert offending == [], (
        "Bind mounts resolving outside the repo — a second copy of this "
        f"stack would share production's state through them: {offending}"
    )


def test_hermes_sees_its_own_worktree_not_a_fixed_path(config):
    """The workspace mount must be `.`, so a branch's Hermes sees the branch,
    and its TARGET must not encode which checkout it is."""
    hermes = config["services"]["hermes"]
    workspace = [
        v for v in hermes["volumes"]
        if v.get("target", "").startswith("/opt/data/workspace/")
    ]
    assert len(workspace) == 1, f"expected one workspace bind, got {workspace}"
    assert Path(workspace[0]["source"]).resolve() == REPO_ROOT
    assert workspace[0]["target"] == "/opt/data/workspace/aurora"
```

- [ ] **Step 2: Run to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_repo_conformance.py -k "outside_the_repo or own_worktree" -v
```

Expected: **both FAIL**, listing `('hermes', '/var/home/supergoodname77/.hermes', '/opt/data')` and `('hermes', '/var/home/supergoodname77/Desktop/tai-review', '/opt/data/workspace/tai-review')`.

- [ ] **Step 3: Clear the pre-existing `.hermes` directory out of the way**

`~/Desktop/tai-review/.hermes/plans/` already exists with four markdown files from an earlier agent run. `cp -a ~/.hermes/plans <target>/` into a directory that already contains `plans` would nest it as `plans/plans`, so move it aside first:

```bash
ls -A ~/Desktop/tai-review/.hermes
mv ~/Desktop/tai-review/.hermes ~/Desktop/tai-review/.hermes.pre-m6
```

Expected: `plans` listed, then the move succeeds silently.

- [ ] **Step 4: Stage the Hermes state inside the repo**

This runs against the **production checkout**, because that is where the mount will resolve.

```bash
mkdir -p ~/Desktop/tai-review/.hermes/workspace
find ~/.hermes -mindepth 1 -maxdepth 1 ! -name workspace \
  -exec cp -a --reflink=auto {} ~/Desktop/tai-review/.hermes/ \;
```

Expected: no output, exit 0. If any `Permission denied` appears, **stop and report** — something outside `workspace/` is root-owned and this plan's premise is wrong.

Verify:

```bash
du -sh ~/Desktop/tai-review/.hermes
ls ~/Desktop/tai-review/.hermes/state.db ~/Desktop/tai-review/.hermes/config.yaml
diff <(ls -A ~/.hermes | grep -vx workspace | sort) \
     <(ls -A ~/Desktop/tai-review/.hermes | grep -vx workspace | sort) && echo ENTRIES_MATCH
diff -rq ~/Desktop/tai-review/.hermes.pre-m6/plans ~/Desktop/tai-review/.hermes/plans
```

Expected: roughly `2.6G`; both files listed; `ENTRIES_MATCH`; and the last `diff -rq` prints nothing, confirming the four pre-existing plan files are already present in the copy. Only then:

```bash
rm -rf ~/Desktop/tai-review/.hermes.pre-m6
```

If that last diff reports differences, keep `.hermes.pre-m6` and report — do not delete anything.

- [ ] **Step 5: Ignore it before it can be committed**

Append to the worktree's `.gitignore` — note the leading slash, and that the existing `shared/.hermes/` line is a *different* path and must be left alone:

```
# Admin Hermes state, bind-mounted at /opt/data (M6). ~2.6 GB of runtime
# state; repo-relative so a branch worktree gets its own.
/.hermes/
```

```bash
cd ~/Desktop/tai-review/.worktrees/chunk2
git status --porcelain | grep '^?? \.hermes' | wc -l
```

Expected: `0`.

- [ ] **Step 6: Change the mounts**

In `compose.yml`, replace the `hermes` service's `volumes:` block:

```yaml
    volumes:
      # Repo-relative (M6). Was ~/.hermes, which made every branch share
      # production's agent state — sessions, keys, kanban, the lot.
      - ./.hermes:/opt/data
      - /var/run/docker.sock:/var/run/docker.sock
      # Repo-relative, and the TARGET is deliberately `aurora` rather than a
      # checkout name: a branch's Hermes must see its own worktree at a
      # stable path, not production's tree at a path that names production.
      - .:/opt/data/workspace/aurora
```

- [ ] **Step 7: Verify the declaration**

```bash
cd ~/Desktop/tai-review/.worktrees/chunk2
docker compose config --quiet && echo CONFIG_OK
.venv/bin/python -m pytest tests/test_repo_conformance.py -k "outside_the_repo or own_worktree" -v
.venv/bin/python -m pytest tests/test_runtime_conformance.py -v
```

Expected: `CONFIG_OK`; the two repo-conformance tests **PASS**; and
`test_declared_bind_sources_match_runtime` **FAILS**, reporting
`('hermes', 'hermes', '/var/home/supergoodname77/.hermes', 'undeclared bind')`.

**That failure is correct and expected.** It is finding F3 made visible: the
declaration has changed and the running container has not. Do **not** weaken
the test. Task 12 Step 5 is where it goes green, after the deploy.

- [ ] **Step 8: Commit**

```bash
git add compose.yml .gitignore tests/
git -c user.name="supergoodname77" -c user.email="epascuales@outlook.com" \
  commit -m "feat: Hermes binds become repo-relative (M6)

~/.hermes -> ./.hermes and ~/Desktop/tai-review -> .:/opt/data/workspace/aurora.
Without this a branch shares production's agent state and its Hermes sees
production's tree — spec §5.2's two named exceptions to path relativity.

State was COPIED (cp -a --reflink=auto on btrfs), not moved, so ~/.hermes
remains a byte-identical rollback. workspace/ was deliberately not copied:
workspace/tai-review is an empty mount point, and workspace/tai is the old
AFFiNE data already scheduled for deletion, part of which is root-owned and
unreadable to this user.

test_declared_bind_sources_match_runtime is red until Task 12 deploys.
That is finding F3, not a defect."
```

---

## Task 9: The project becomes `aurora` (completes M5's §4.3 requirement)

**Files:**
- Modify: `.env.template`
- Modify: `tests/conftest.py`, `tests/test_repo_conformance.py`
- Modify: `dev-administration/tests/test_guard_coverage.py`
- Modify: `dev-administration/scripts/dev-admin.sh`, `scripts/authz_test.py`, `scripts/negative_test_login_button.py`
- Modify: `dev-administration/README.md`, `admin-asks.md`
- Modify: `docs/superpowers/specs/2026-07-27-ephemeral-branching-design.md`, `docs/superpowers/specs/2026-07-25-multi-developer-provisioning-design.md`
- Modify: unit-test fixture literals across `dev-administration/tests/`
- Create: `aurora_hermes-testuser-home`, `aurora_hermes-newuser-home`, `aurora_hermes-cumshit42069-home` (Docker volumes, not files)

**Interfaces:**
- Consumes: M5's identity seam — `project.current_project()`, `network_name()`, `find_service_container()` (Tasks 3–4), the `COMPOSE_PROJECT_NAME` plumbing and `AGENT_*` variables added to `.env.template` (Task 5 Step 6), the parameterised `dev-admin` environment (Task 6 Step 9 item 10), and M6's repo-relative binds (Task 8).
- Produces: a tree in which the only remaining occurrences of `tai-review` are dated historical records under `docs/` and one deliberate regression-guard literal; `.env.template` declaring `COMPOSE_PROJECT_NAME=aurora`; `conftest.PRODUCTION_PROJECT` defaulting to `aurora`; three `aurora_`-prefixed agent volumes holding the agents' data; and a written, verified directory-move procedure that Task 12 Step 4 executes. Task 10 consumes the service inventory this task confirms; Task 12 consumes the move procedure and the volumes.

### Why the rename belongs here and not earlier

`COMPOSE_PROJECT_NAME` **is not set anywhere on this host** — verified: `grep -c COMPOSE_PROJECT_NAME ~/Desktop/tai-review/.env` was `0` before Task 5 Step 6, and `docker compose config --format json | jq -r .name` returns `tai-review`, which Compose derived from the directory basename. Renaming the directory therefore renames every container, the default network and every project-prefixed volume, all at once, with no compose edit at all.

That is also why it could not be done first. Three things had to move out of the way:

1. `compose.yml:112` bound `~/Desktop/tai-review:/opt/data/workspace/tai-review` and `:110` bound `~/.hermes:/opt/data` — absolute host paths that a directory move breaks outright. **M6 (Task 8) made both repo-relative**, and deliberately chose the container-side target `/opt/data/workspace/aurora`, so the workspace path is already correct before the host path changes.
2. `compose.yml:159` set `CADDY_CONTAINER=tai-review-caddy-1`, and `docker_utils.NETWORK` was `"tai-review_default"`. **M5 (Tasks 4 and 6) deleted both**, so this task does not have to edit them and then edit them again.
3. Spec §4.3 requires `COMPOSE_PROJECT_NAME` to be **set explicitly per branch — not left to the directory-basename default**. Task 5 Step 6 put the variable in place; this task gives it the right value. Until production's own project name is a declaration rather than an artefact of where someone happened to clone the repo, Chunk 3's `br-<name>` naming has nothing to be a sibling of.

**Doing it in the other order costs two passes over the same literals** and leaves a window in which `compose.yml` names a directory that no longer exists.

### The hazard: six declared volumes rename, and Docker does not migrate their data

A project-prefixed volume is `<project>_<declared name>`. Rename the project and Compose looks for a volume that does not exist, **creates a fresh empty one, and leaves the original sitting there with the data still in it**. Nothing warns you. The six declared in `compose.yml`:

`tai-review_caddy_data`, `tai-review_caddy_config`, `tai-review_arcadedb_backups`, `tai-review_arcadedb_config`, `tai-review_arcadedb_log`, `tai-review_arcadedb_replication`

Every one was opened and read before this plan was written. Per-volume decision:

| Volume | Actual contents (read, not assumed) | Decision |
|---|---|---|
| `tai-review_caddy_data` | 8 KB total: `caddy/instance.uuid`, `caddy/last_clean.json`, an empty `caddy/locks/`. **There is no `caddy/certificates/` directory at all.** | **Regenerate** |
| `tai-review_caddy_config` | 16 KB: `caddy/autosave.json` — Caddy's autosave of the last config it loaded, rewritten on every load and reload | **Regenerate** |
| `tai-review_arcadedb_config` | 7 files. `diff -rq` of the volume against `/home/arcadedb/config` inside `arcadedata/arcadedb:26.7.3` itself **exits 0 with no output** — byte-identical to the image defaults | **Regenerate** |
| `tai-review_arcadedb_log` | 930 bytes of boot log in `arcadedb.log.0`, plus a zero-byte `.lck` and a zero-byte event-log jsonl | **Regenerate** |
| `tai-review_arcadedb_backups` | 0 files | **Regenerate** |
| `tai-review_arcadedb_replication` | 0 files | **Regenerate** |

**On `caddy_data` specifically**, because it is the one that would hurt: the absence of `caddy/certificates/` is not the only evidence. `DOMAIN_NAME` is `superserver.tailc67a98.ts.net`, which resolves only inside the tailnet — no public DNS, no reachable :80 or :443 from the internet — so ACME's HTTP-01 and TLS-ALPN-01 challenges are *not performable* for this name. The certificate cannot have come from ACME. Caddy mounts `/var/run/tailscale:/var/run/tailscale:ro` and takes `.ts.net` certificates from the local `tailscaled` at TLS-handshake time; that is why the volume that has served HTTPS for weeks contains no certificate state. Step 2 below re-verifies this at execution time rather than trusting the table.

**Three more project-prefixed volumes exist by the time this task runs.** Task 5 Step 8 created `tai-review_hermes-testuser-home`, `tai-review_hermes-newuser-home` and `tai-review_hermes-cumshit42069-home` by *copying* from the unprefixed originals. These hold real agent state — 70.2 MB, 32.0 MB and 35.5 MB — and **must be migrated.** Because Task 5 copied rather than moved, the pristine sources are still there, so Step 4 recreates them under the `aurora_` prefix from those same sources rather than chaining a copy off a copy.

### What is safe, stated so nobody panics mid-deploy

- **The nine `hermes-*-home` volumes are untouched.** They carry explicit, unprefixed names, so no project prefix applies: `hermes-alicetest-home`, `hermes-bobtest-home`, `hermes-cumshit42069-home`, `hermes-jaun-home`, `hermes-johndear-home`, `hermes-newuser-home`, `hermes-selfreg-home`, `hermes-shitcum-home`, `hermes-testuser-home`. Verified: none of the nine contains a single reference to `/opt/data/workspace/tai-review`.
- **Every bind mount in `compose.yml` is relative** after Task 8 — `./forgejo`, `./affine`, `./Caddyfile`, `./Caddyfile.d`, `./agent-authz/data`, `./arcadedb`, `./dev-administration`, `./developers.yaml`, `./.hermes`, `./.agent-env`, `.` — plus the three allowed external binds (`/var/run/docker.sock`, `/var/run/tailscale`, `/etc/localtime`), which are absolute host paths outside the repo and unaffected by the move. **All of that data moves with the directory.** ArcadeDB's real databases live in the `./arcadedb` bind, not in the four `arcadedb_*` volumes.
- **The Forgejo remote needs no change.** Verified: `git remote -v` in the production checkout already points at `…/git/supergoodname77/aurora.git`, and `ls forgejo/git/repositories/*/` lists `aurora.git`, `aurora-agent.git`, `dev-administration.git`, `superpowers.git`. The Forgejo repo has been named `aurora` all along; only the working directory was not.
- **The venvs survive the move for the way this plan uses them.** Probed by copying `.venv` to a different path and running it: `.venv/bin/python -c 'import sys, pytest; print(sys.prefix)'` printed the *new* path and imported pytest 9.1.1. `bin/python` is a symlink to an absolute system interpreter and `sys.prefix` is derived from `pyvenv.cfg`'s location, so `.venv/bin/python -m pytest` — the only form this plan ever uses — is path-independent. What does break is `bin/activate` (`VIRTUAL_ENV='/var/home/.../Desktop/tai-review/...'`) and every console-script shebang such as `.venv/bin/pytest`. Neither is used here. Step 8 records this so nobody rebuilds three venvs for no reason.
- **Untracked and gitignored occurrences are deliberately out of scope**, and the Step 1 gate scans only `git ls-files` output so it cannot trip over them. Four categories exist and none is a live reference: `.hermes/plans/*.md` — four agent plan documents from an earlier run, carried into `./.hermes` by Task 8, whose `cd /opt/data/workspace/tai-review` lines are a record of what an agent did, not configuration; `.worktrees/ephemeral-branching/.superpowers/sdd/**` — Chunk 1's SDD progress and task briefs, a dated record in exactly the sense `docs/` is; `~/.hermes/skills/**` and `~/.hermes/logs/**` — Hermes' own skill library and logs, user content this plan does not own; and `**/__pycache__/*.pyc` and `.venv/**`, which are rebuilt. The one Hermes item worth naming: `~/.hermes/state.db` holds `/opt/data/workspace/tai-review` strings in session history, but M6 already changed the container-side target to `/opt/data/workspace/aurora`, so those are stale by Task 8 regardless of this task, and they are last-CWD records the agent re-resolves rather than a path anything reads.
- **`~/.aurora-last-restore-point` is unaffected.** It contains `/home/supergoodname77/aurora-restore-20260727-230449` — a Chunk 1 snapshot directory in `$HOME`, not under `~/Desktop`. Its `MANIFEST.txt` and `prod-uncommitted.patch` name the old path, but as a record of a moment in time. Leave both alone.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_repo_conformance.py`:

```python
# The old project name, assembled at runtime. Written this way on purpose:
# the gate below scans tracked files for it, and a literal here would make
# this file its own first offender.
OLD_PROJECT = "tai" + "-review"


def test_the_project_name_is_declared_not_inherited_from_the_directory():
    """Spec §4.3: set COMPOSE_PROJECT_NAME explicitly, do not rely on the
    directory-basename default. Before Chunk 2 it was unset, so the project
    was named after whichever directory the repo happened to be cloned into —
    which is also why Chunk 3's `br-<name>` had no sibling to be named
    against."""
    template = (REPO_ROOT / ".env.template").read_text()
    assert "COMPOSE_PROJECT_NAME=aurora" in template


def test_no_tracked_file_outside_docs_names_the_old_project():
    """The stack was named after an unrelated earlier project until Chunk 2.

    Everything under docs/ is a dated record of what was true when it was
    written and is left verbatim. Anything else naming it is a LIVE
    reference — a container name, a network, a host path — that would either
    break outright or, worse, quietly resolve against nothing.
    """
    # One deliberate exception: test_guard_coverage.py asserts that the M5
    # literals are ABSENT from dev_administration's source, so it has to
    # contain them itself.
    allowed = {"dev-administration/tests/test_guard_coverage.py"}

    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.split("\0")

    offenders = []
    for rel in tracked:
        if not rel or rel.startswith("docs/") or rel in allowed:
            continue
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue        # binary or unreadable: nothing to name anything
        if OLD_PROJECT in body:
            offenders.append(rel)

    assert offenders == [], (
        f"Tracked files still naming {OLD_PROJECT!r}: {offenders}. If one is "
        "a historical record, it belongs under docs/; if it is live, fix it."
    )


def test_the_conformance_gate_has_containers_to_conform_to():
    """PRODUCTION_PROJECT names the project whose containers every runtime
    test compares the declaration against. If that name is wrong the query
    returns an empty set and the entire runtime gate passes VACUOUSLY —
    which is precisely what a project rename does to a conformance suite.

    While the declarations name the new project and the deployed containers
    still carry the old label, run the suite with AURORA_PROJECT set to the
    live project name.
    """
    from conftest import PRODUCTION_PROJECT, project_containers

    assert project_containers(), (
        "No running containers carry com.docker.compose.project="
        f"{PRODUCTION_PROJECT!r}. Either the stack is down, or "
        "PRODUCTION_PROJECT is stale — set AURORA_PROJECT to the live "
        "project name. Do NOT let the runtime gate pass on an empty set."
    )
```

- [ ] **Step 2: Run to verify, and re-confirm the volume evidence first-hand**

```bash
cd ~/Desktop/tai-review/.worktrees/chunk2
AURORA_PROJECT=tai-review .venv/bin/python -m pytest tests/test_repo_conformance.py \
  -k "declared_not_inherited or outside_docs_names or containers_to_conform" -v
```

Expected: `test_the_conformance_gate_has_containers_to_conform_to` **PASSES**; the other two **FAIL** — `.env.template` still says `COMPOSE_PROJECT_NAME=tai-review`, and the offender list is non-empty.

Now re-read the volumes, because the table above is only as good as the day it was written:

```bash
docker run --rm -v tai-review_caddy_data:/x:ro alpine find /x -mindepth 1 | sort
for v in arcadedb_backups arcadedb_replication; do
  echo -n "$v files="; docker run --rm -v "tai-review_$v:/x:ro" alpine sh -c 'find /x -type f | wc -l'
done
docker run --rm -v tai-review_arcadedb_config:/x:ro arcadedata/arcadedb:26.7.3 \
  sh -c 'diff -rq /x /home/arcadedb/config; echo DIFF_EXIT=$?'
docker run --rm -v tai-review_arcadedb_log:/x:ro alpine sh -c 'wc -c /x/*'
```

Expected: exactly `/x/caddy`, `/x/caddy/instance.uuid`, `/x/caddy/last_clean.json`, `/x/caddy/locks` — **and no `/x/caddy/certificates` entry**; `0` for both arcadedb volumes; `DIFF_EXIT=0` with no preceding diff lines, meaning the config volume is byte-identical to the image's own `/home/arcadedb/config` (the `sh -c` wrapper is needed — the image sets an entrypoint that would otherwise swallow the command); and roughly 930 bytes in `arcadedb.log.0` with two zero-byte siblings.

**If a `caddy/certificates` path appears, stop.** The premise that Caddy holds no durable certificate state is then false, and `caddy_data` must be migrated like the agent volumes in Step 4 rather than regenerated. Record which it was in the implementation log either way.

- [ ] **Step 3: Set the name in the declarations**

In `.env.template`, change the line Task 5 Step 6 added:

```bash
COMPOSE_PROJECT_NAME=aurora
```

and extend the comment above it:

```bash
# --- Project identity (Chunk 2 / M5) ---
# Set explicitly so dev-admin can fall back to it when run outside a
# container. INSIDE a container the compose project LABEL wins, which is what
# stops a branch that inherited this file from acting on production.
# Spec §4.3: declared, never inherited from the directory basename. It WAS
# inherited until Chunk 2, which is the only reason this stack ever carried
# the name of an unrelated earlier project.
```

In `tests/conftest.py`:

```python
# The project whose running containers we conform to. Deliberately NOT
# derived from `docker compose config`: inside a git worktree the compose
# project name comes from the directory basename, which matches no running
# containers and would make the conformance assertion vacuous.
# `aurora` from Task 9's rename. Override with AURORA_PROJECT while the
# deployed stack still carries the old label — see the constraint at the top
# of the Chunk 2 plan.
PRODUCTION_PROJECT = os.environ.get("AURORA_PROJECT", "aurora")
```

In `dev-administration/tests/test_guard_coverage.py`, widen the literal list so the guard forbids the *new* name too — a regression test that only bans a name nobody would type any more is a museum piece:

```python
        for literal in (
            "tai-review_default", "tai-review-caddy-1",
            "aurora_default", "aurora-caddy-1",
        ):
```

Only the worktree's own `.env` is updated, never production's:

```bash
cd ~/Desktop/tai-review/.worktrees/chunk2
sed -i 's/^COMPOSE_PROJECT_NAME=tai-review$/COMPOSE_PROJECT_NAME=aurora/' .env
grep -n '^COMPOSE_PROJECT_NAME=' .env ~/Desktop/tai-review/.env
```

Expected: the worktree's `.env` shows `aurora`; **the production checkout's still shows `tai-review`.** That is deliberate — Task 12 Step 4b changes it, after the old project has been torn down under its own name.

- [ ] **Step 4: Migrate the three agent volumes to the `aurora_` prefix**

Task 5 Step 8 copied the unprefixed originals into `tai-review_hermes-<u>-home`. Those originals are untouched, so copy from them again rather than from the copy. No container is stopped: the three agent containers do not exist yet — Task 12's `up` is what first creates them.

```bash
for u in testuser newuser cumshit42069; do
  docker volume create \
    --label com.docker.compose.project=aurora \
    --label "com.docker.compose.volume=hermes-$u-home" \
    "aurora_hermes-$u-home"
done
docker volume inspect aurora_hermes-testuser-home --format '{{json .Labels}}'
```

Expected: three volume names echoed, then a labels object containing both `com.docker.compose.project:aurora` and `com.docker.compose.volume:hermes-testuser-home`. Those two labels are what make Compose *adopt* a pre-existing volume with its contents intact instead of complaining — probed on v5.3.1, recorded in the behaviours table at the top of this plan.

```bash
for u in testuser newuser cumshit42069; do
  docker run --rm \
    -v "hermes-$u-home:/from:ro" \
    -v "aurora_hermes-$u-home:/to" \
    alpine sh -c 'cp -a /from/. /to/'
done
```

Expected: no output, exit 0 each time.

Verify by size, not by faith:

```bash
for u in testuser newuser cumshit42069; do
  old=$(docker run --rm -v "hermes-$u-home:/v:ro"        alpine sh -c 'du -sk /v | cut -f1')
  new=$(docker run --rm -v "aurora_hermes-$u-home:/v:ro" alpine sh -c 'du -sk /v | cut -f1')
  printf '%-14s old=%s new=%s\n' "$u" "$old" "$new"
  docker run --rm -v "aurora_hermes-$u-home:/v:ro" alpine ls /v/state.db
done
```

Expected: the two sizes match within a few KB per user — around `71900` for `testuser`, `32800` for `newuser`, `36400` for `cumshit42069` — and `/v/state.db` is listed for each. A `new=` of `0` or a missing `state.db` means the copy silently did nothing; do not proceed to Task 12.

The `tai-review_hermes-*-home` volumes from Task 5 are now dead. **Leave them in place** — they are a second rollback copy and cost ~140 MB. Task 12 Step 9 schedules their deletion.

- [ ] **Step 5: Sweep the remaining literals in tracked code**

Each of these is a live reference no earlier task touches. Applied one file at a time so the diff is reviewable:

1. `dev-administration/scripts/dev-admin.sh` — three lines:
   - `HOST_REPO="${HOST_REPO:-/home/supergoodname77/Desktop/tai-review}"` → `.../Desktop/aurora`
   - `-e "CADDY_CONTAINER=${CADDY_CONTAINER:-tai-review-caddy-1}"` → `${CADDY_CONTAINER:-aurora-caddy-1}`
   - `--network tai-review_default` → `--network aurora_default`
2. `dev-administration/scripts/authz_test.py` — `"docker", "exec", "tai-review-caddy-1", …` → `"aurora-caddy-1"`.
3. `dev-administration/scripts/negative_test_login_button.py` — `CADDY = "tai-review-caddy-1"` → `"aurora-caddy-1"`.
4. `dev-administration/README.md` — the `CADDY_CONTAINER` default row (`tai-review-caddy-1` → `aurora-caddy-1`) and `docker logs tai-review-fjell-1` (→ `aurora-fjell-1`).
5. `admin-asks.md` — `cd /opt/data/workspace/tai-review && git push origin master` → `cd /opt/data/workspace/aurora && git push origin main`. Two corrections in one line: M6 already changed the container-side workspace target to `/opt/data/workspace/aurora`, and trunk was renamed from `master` to `main` before Chunk 1.
6. Unit-test **fixture** strings written by Tasks 3–6, in `dev-administration/tests/test_project.py`, `test_docker_utils.py`, `test_caddy_utils.py` and `test_provision.py`: `"tai-review"` → `"aurora"`, `"tai-review_default"` → `"aurora_default"`, `"tai-review-caddy-1"` → `"aurora-caddy-1"`, `"tai-review_hermes-juan-home"` → `"aurora_hermes-juan-home"`. These are project-name-agnostic mock values — the code under test derives the project at runtime — so this is consistency, not behaviour. `test_guard_coverage.py` is **excluded**: it must keep the old literals, plus the new ones added in Step 3.

```bash
cd ~/Desktop/tai-review/.worktrees/chunk2
git ls-files -z | grep -zv '^docs/' | grep -zv 'test_guard_coverage.py$' \
  | xargs -0 grep -l 'tai-review' 2>/dev/null
```

Expected: **exactly one filename — `README.md`.** Any other filename is a miss in the list above. `README.md` is deliberately left: it needs a rewrite, not a substitution, and that is Task 10. This is why `test_no_tracked_file_outside_docs_names_the_old_project` stays red for the length of one task.

- [ ] **Step 6: Update the two forward-looking specs**

Everything under `docs/` is a dated record **except** the two design specs, which describe how the system is meant to work next and are read by Chunk 3. In both, `tai-review` becomes `aurora`:

- `docs/superpowers/specs/2026-07-27-ephemeral-branching-design.md` — the worktree path in the header, the project-label sentence in §"12 containers", the `~/Desktop/tai-review/  project tai-review` diagram row, the `tai-review_*` volume guarantee in the named-volumes table, the `~/Desktop/tai-review:/opt/data/workspace/tai-review` M6 row, the `CADDY_CONTAINER=tai-review-caddy-1` reference, the `config_files` path, the M6 table row, and the `tai-review_*` container/volume sentence.
- `docs/superpowers/specs/2026-07-25-multi-developer-provisioning-design.md` — four `tai-review_default` network references.

Leave every other `docs/` file alone, including `docs/issues/*`, `docs/tasks/*`, `docs/implementations/*`, `docs/testing/*` and the two earlier plans. Rewriting them would falsify a record of what was actually observed. `docs/post-implementation-steps.md` is edited by Task 12 Step 9, not here, so its old-path references are corrected in the same pass that closes §D1.

```bash
grep -rc 'tai-review' docs/superpowers/specs/
```

Expected: `0` for both files.

- [ ] **Step 7: Verify the declaration end to end**

```bash
cd ~/Desktop/tai-review/.worktrees/chunk2
docker compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])'
docker compose config --quiet && echo CONFIG_OK
AURORA_PROJECT=tai-review .venv/bin/python -m pytest tests dev-administration/tests -q 2>&1 | tail -5
```

Expected: `aurora` — the worktree now resolves under the declared name rather than its own directory basename `chunk2`, which is the whole point of §4.3. `CONFIG_OK`.

The suite reports **exactly two failures and no others**:

1. `test_declared_bind_sources_match_runtime` — finding F3, red since Task 8, green at Task 12 Step 5.
2. `test_no_tracked_file_outside_docs_names_the_old_project` — red because `README.md` is the one remaining offender, green at Task 10 Step 3.

Both are red on purpose and both have a named task that clears them. A third failure is a real one.

- [ ] **Step 8: Write the move procedure into the plan of record**

The directory move itself is **not performed here.** It requires the stack to be down, and this plan has exactly one downtime window (Task 12 Step 4). Confirm now that the two things the move will break are both repairable, so Task 12 is not discovering them under an outage:

```bash
cd ~/Desktop/tai-review
git worktree list
cat .git/worktrees/ephemeral-branching/gitdir
cat .worktrees/ephemeral-branching/.git
```

Expected: two linked worktrees listed (`ephemeral-branching` from Chunk 1, `chunk2` from Task 0 — three lines including the main checkout); and **two absolute paths under `Desktop/tai-review`**, one in each direction. Git stores worktree links absolutely in both files, so both go stale the moment the parent directory is renamed and every command run inside a worktree fails with `fatal: not a git repository: (null)`.

The repair is `git worktree repair <path> …`, run from the *new* main checkout, **with the worktree paths named**. Probed on this host in a scratch repo: a bare `git worktree repair` with no arguments does **not** fix this case — it exits silently and leaves both files pointing at the old path. With the paths given it prints `repair: gitdir incorrect: …` per worktree and both directions are corrected. That is Task 12 Step 4c-iii; it is recorded here so the deploy is not the first time anyone finds out which form works.

```bash
head -1 dev-administration/.venv/bin/pytest
grep -n "^VIRTUAL_ENV=" dev-administration/.venv/bin/activate
```

Expected: a shebang and a `VIRTUAL_ENV=` both naming `/var/home/supergoodname77/Desktop/tai-review/...`. **These stay stale after the move and that is acceptable**, because this plan invokes `.venv/bin/python -m pytest` and never `bin/activate` or the `bin/pytest` console script; `sys.prefix` is derived from `pyvenv.cfg`'s location and follows the directory. Verified by copying a venv to a new path and importing pytest from it successfully. Note it in the implementation log rather than rebuilding three venvs.

- [ ] **Step 9: Commit**

```bash
cd ~/Desktop/tai-review/.worktrees/chunk2
git add .env.template tests/ dev-administration/ admin-asks.md docs/superpowers/specs/
git -c user.name="supergoodname77" -c user.email="epascuales@outlook.com" \
  commit -m "feat: the project is named aurora, not tai-review

COMPOSE_PROJECT_NAME was never set, so the project name was the directory
basename — a leftover from a previous NAS project. Spec §4.3 requires it to
be declared, and Chunk 3's br-<name> projects need production's own name to
be a declaration rather than an artefact of where the repo was cloned.

Lands after M5 and M6 on purpose: M5 deleted the tai-review-caddy-1 and
tai-review_default literals and M6 made the ~/Desktop/tai-review binds
relative, so the rename touches each hardcoded string exactly once and the
directory move breaks no mount.

Declarations only. The directory move, the .env change in the production
checkout and the single restart are Task 12 Step 4. Agent volumes were
re-copied under the aurora_ prefix from the untouched unprefixed originals;
the six declared tai-review_* volumes are left in place and regenerate empty
(read and justified per volume in the plan)."
```

**Rollback for this task:** `git revert` the commit, `sed` the worktree `.env` back to `COMPOSE_PROJECT_NAME=tai-review`, and `docker volume rm aurora_hermes-{testuser,newuser,cumshit42069}-home`. Nothing deployed has changed, and no source volume was written to.

**This task commits with two tests red** (Step 7). That is deliberate and both are named there. Do not weaken either to get a green commit.

---

## Task 10: Rewrite `README.md`

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: the service inventory this task gathers in Step 1, the test-invocation form from Task 0, the `docs/` directories that already exist from Chunk 1, and Task 9's `test_no_tracked_file_outside_docs_names_the_old_project`, which this task turns green.
- Produces: a `README.md` that describes the repo as it is at this commit. Nothing later in the plan consumes it.

**Context the implementer needs:** the current `README.md` predates Chunk 1 and is wrong in ways that mislead rather than merely age. It names the Caddy container `tai-review-caddy-1`; it lists six services when nine now run; it omits `agent-authz`, AFFiNE and `arcadedb` entirely; it describes `dev-administration/` as a "separate repo, gitignored here", which Chunk 1 made false by vendoring it; its repo-layout tree has no `docs/implementations/`, `docs/testing/` or `tests/`; and it says nothing about ephemeral branching, which is the thing the project is now being built toward.

**Write it against the repo, not against this plan.** The sections and the facts each must contain are specified below; the prose is not, deliberately — a README copied out of a plan document describes the plan, and this one has already been wrong once for exactly that reason. Read the files named in each bullet and write what is true at the commit you are on.

- [ ] **Step 1: Gather the facts**

```bash
cd ~/Desktop/tai-review/.worktrees/chunk2
COMPOSE_PROFILES='*' docker compose config --services | sort
docker ps --filter label=com.docker.compose.project=tai-review \
  --format '{{.Names}}\t{{.Image}}\t{{.Status}}'
ls docs docs/superpowers
```

`COMPOSE_PROFILES='*'` matters: without it the per-developer agent services are omitted entirely and the inventory you write will be missing them. The `docker ps` filter still uses `tai-review` — the stack has not been renamed yet, only its declarations have. Record the output; the sections below are checked against it.

- [ ] **Step 2: Rewrite the file with these sections**

1. **What Aurora is.** A single Tailnet-only host running a self-contained development platform: Forgejo as both git host and OIDC identity provider, one Hermes agent container per developer authenticated against it, a shared multi-tenant Forgejo MCP server, and a reverse proxy that puts all of it behind one `.ts.net` name. State explicitly that there is no public ingress and that this is why self-service sign-up is open. Note that the project was renamed to Aurora in Chunk 2 and that documents under `docs/` written before 2026-07-28 use the previous name throughout, pointing at `docs/issues/chunk2-spec-deltas.md` for the mapping. **Do not write the old name here** — Task 9's gate forbids it in any tracked file outside `docs/`, and the mapping belongs in the record, not in the front door.

2. **Service inventory.** One row per service actually declared in `compose.yml` (including the `include:`d `affine/compose.yml` and `compose.agents.yml`), with its container name and one line of purpose. It must cover: `caddy` (reverse proxy, TLS from tailscaled, `network_mode: host`), `forgejo` (git + OIDC IdP, `/git/`), `forgejo-mcp` (multi-tenant HTTP MCP, internal only, no Caddy in front), `hermes` (the admin agent), `fjell` (Rust/Axum internal hub serving the landing page and `/agent/{username}/setup`), `agent-authz` (per-agent authorisation gate called by Caddy's `forward_auth`; state why it exists — Hermes' OIDC plugin authenticates but does not authorise, so without it any valid Forgejo account could open any developer's agent), `dev-admin` (one-shot `restart: "no"` reconciler; `exit=0` is success), `affine` + `affine_migration` + `postgres` + `redis` (AFFiNE, brought in-tree in Chunk 1), `arcadedb` (declared but not integrated with anything — say so, and point at `docs/issues/arcadedb-oom.md`), and the generated per-developer `hermes-<username>` agent services. Use the real container names from Step 1; do not guess at the compose-synthesised ones.

3. **Where this is going: ephemeral branching.** The goal the parameterisation work serves — a branch of this repo can be brought up as a *complete second stack* on the same host, under its own `COMPOSE_PROJECT_NAME` (`br-<name>`), its own Tailscale name and its own volumes, and torn down again without touching production. Name the three properties that make it possible and that Chunk 2 established: `COMPOSE_PROJECT_NAME` is declared, not inherited; every bind is repo-relative; and no code contains a literal project, network or container name. Point at `docs/superpowers/specs/2026-07-27-ephemeral-branching-design.md` for the design and say which chunks are done.

4. **Quick start.** Clone, `cp .env.template .env` and fill it in, `docker compose up -d`. Must state that `COMPOSE_PROFILES=agents` is required or the stack comes up with no developer agents at all, and that `.env` must set `COMPOSE_PROJECT_NAME` — the directory basename is no longer relied on.

5. **Managing developers.** Keep the existing `dev-admin` CLI flow, but correct it for M4: `reconcile` no longer starts containers. It renders `compose.agents.yml`, ensures volumes and OIDC credentials, and reports `container.missing`; `docker compose up -d` is what starts an agent. Adding a developer is: edit `developers.yaml` → `dev-admin render-agents` → commit the regenerated `compose.agents.yml` → `reconcile` → `up -d`.

6. **Developer onboarding.** The existing four-step flow (`/agent/<username>/setup` → key entry → `/agent/<username>/` → Forgejo OIDC login) and the SSH-on-port-222 note are still accurate — verify against `fjell/src/routes/setup.rs` and the Caddyfile before keeping them.

7. **Running the tests.** `pytest.ini` sets `testpaths = tests dev-administration/tests`. **There is no system pytest**; the form is `.venv/bin/python -m pytest` from the repo root, with a venv created by `python3 -m venv .venv && .venv/bin/pip install pytest pyyaml typer`. Say what the suite is: repo-conformance tests that assert `compose.yml` matches the repo, runtime-conformance tests that assert the running containers match `compose.yml`, and `dev-administration`'s unit tests. Mention that the runtime tests need the stack up and take `AURORA_PROJECT` to name the project they compare against.

8. **Repo layout.** Replace the stale tree. It must include `tests/`, `compose.agents.yml` (generated **and** committed — say why: `include:` is a hard error on a missing file), `.agent-env/` and `.hermes/` (both gitignored runtime state), `.worktrees/`, and `dev-administration/` as an in-tree directory rather than an external repo.

9. **Where the documents live.** `docs/superpowers/specs/` = design specs; `docs/superpowers/plans/` = implementation plans; `docs/implementations/` = what was actually built, per chunk; `docs/testing/` = what each test catches and what is deliberately untested; `docs/issues/` = investigated problems with evidence; `docs/setup/user/` and `docs/setup/system/` = operator guides; `docs/post-implementation-steps.md` = the standing list of actions requiring a human or root.

10. **Related repos.** Keep the existing table — verified still correct: `aurora`, `aurora-agent`, `dev-administration`, `superpowers` all exist in Forgejo.

- [ ] **Step 3: Check it against the repo**

```bash
cd ~/Desktop/tai-review/.worktrees/chunk2
grep -c 'tai-review' README.md
for s in $(COMPOSE_PROFILES='*' docker compose config --services); do
  case "$s" in hermes-*) continue ;; esac        # agents are described generically
  grep -q -- "$s" README.md || echo "MISSING: $s"
done
grep -q 'hermes-<username>' README.md && echo AGENTS_DESCRIBED
AURORA_PROJECT=tai-review .venv/bin/python -m pytest tests/test_repo_conformance.py \
  -k "outside_docs_names" -v
```

Expected: `0` (the README must not name the old project at all — see Step 2 item 1); no `MISSING:` lines; `AGENTS_DESCRIBED`; and `test_no_tracked_file_outside_docs_names_the_old_project` **PASSES** — Task 9 Step 5 left `README.md` as its last offender, and this task is what clears it.

The `hermes-*` services are skipped in the loop on purpose: they are one per developer and named after real accounts, so the README describes the *shape* (`hermes-<username>`) rather than enumerating today's three. `developers.yaml` is the enumeration.

- [ ] **Step 4: Commit**

```bash
git add README.md
git -c user.name="supergoodname77" -c user.email="epascuales@outlook.com" \
  commit -m "docs: rewrite README for the stack as it actually is

The old README predated Chunk 1: it named the Caddy container
tai-review-caddy-1, listed six services where nine run, omitted agent-authz,
AFFiNE and arcadedb, and described dev-administration as an out-of-tree repo
that Chunk 1 vendored. Adds the ephemeral-branching goal, how to run the
test suite, and where specs, plans, implementation logs and runbooks live."
```

---

## Task 11: Close the `dev-admin` startup race (F2)

**Files:**
- Modify: `compose.yml`
- Modify: `dev-administration/dev_administration/forgejo_utils.py`
- Create: `tests/test_compose_startup_ordering.py`
- Modify: `dev-administration/tests/test_forgejo_utils.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `forgejo_utils._curl(url, token, method="GET", data=None, attempts=6, backoff=2.0)` with bounded retry on connection-class failures.

**Context the implementer needs:** `dev-admin` declares `depends_on: [forgejo]` with no condition, so `reconcile` starts the instant Forgejo's *container* starts, before Forgejo is *serving*. Observed on the host right now: `dev-admin` is `Exited (1)` with
`CalledProcessError: Command '['curl', '-fsS', '-X', 'GET', 'https://superserver.tailc67a98.ts.net/git/api/v1/user/applications/oauth2', …]' returned non-zero exit status 22`. Re-running after startup works. Every fresh deploy hits it.

Two fixes are needed, not one. A healthcheck on Forgejo gates on Forgejo — but **dev-admin reaches Forgejo through Caddy**, as that URL shows, so a Caddy recreate window produces the identical failure no Forgejo healthcheck can prevent. The retry covers that; the healthcheck covers the common case cleanly and makes the dependency legible.

Verified: Forgejo's image ships `/usr/bin/curl`, and `GET http://localhost:3000/api/healthz` returns `200` with `{"status":"pass","checks":{"cache:ping":…,"database:ping":…}}`. The repo already uses `condition: service_healthy` (in `affine/compose.yml`), so the idiom is established.

curl exit 22 is `--fail` on an HTTP error; 6 is DNS, 7 connection refused, 28 timeout, 35 TLS, 52 empty reply, 56 receive error. Only the connection class is retried — a genuine 401 or 404 must fail immediately rather than being retried six times.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_compose_startup_ordering.py`:

```python
"""dev-admin's startup race.

`depends_on: [forgejo]` with no condition means `reconcile` runs the instant
Forgejo's CONTAINER starts, before Forgejo is SERVING, and dies with curl
exit 22. Observed on this host: dev-admin Exited (1) on every fresh deploy.
"""

from conftest import compose_config


def test_forgejo_declares_a_healthcheck():
    healthcheck = compose_config()["services"]["forgejo"].get("healthcheck")
    assert healthcheck, (
        "Forgejo declares no healthcheck, so nothing downstream can gate on "
        "it actually serving"
    )
    assert "healthz" in " ".join(healthcheck["test"]), (
        "Health must be checked against Forgejo's own /api/healthz, which "
        "reports cache and database readiness, not merely a listening socket"
    )


def test_dev_admin_waits_for_forgejo_to_be_healthy():
    depends = compose_config()["services"]["dev-admin"].get("depends_on") or {}
    assert "forgejo" in depends, "dev-admin must still depend on forgejo"
    assert depends["forgejo"].get("condition") == "service_healthy", (
        "A bare depends_on waits for the container to START, not for Forgejo "
        "to SERVE. That is the race that kills dev-admin on every deploy."
    )
```

Append to `dev-administration/tests/test_forgejo_utils.py` (add any of these imports that are not already present):

```python
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from dev_administration.forgejo_utils import _curl


def _fail(code):
    return subprocess.CalledProcessError(code, ["curl"], output="", stderr="")


@patch("dev_administration.forgejo_utils.time.sleep")
@patch("dev_administration.forgejo_utils.subprocess.run")
def test_curl_retries_a_connection_refusal_then_succeeds(mock_run, _sleep):
    """dev-admin reaches Forgejo THROUGH Caddy, so a Caddy recreate window
    produces the same failure no Forgejo healthcheck can gate."""
    mock_run.side_effect = [
        _fail(7), _fail(7), MagicMock(returncode=0, stdout='{"ok": true}'),
    ]
    assert _curl("http://x/api", "tok") == {"ok": True}
    assert mock_run.call_count == 3


@patch("dev_administration.forgejo_utils.time.sleep")
@patch("dev_administration.forgejo_utils.subprocess.run")
def test_curl_does_not_retry_a_real_http_error(mock_run, _sleep):
    """A 404 or 401 is an answer, not an outage. Retrying it six times turns
    a clear error into a slow, confusing one."""
    mock_run.side_effect = _fail(22)
    with pytest.raises(subprocess.CalledProcessError):
        _curl("http://x/api", "tok")
    assert mock_run.call_count == 1


@patch("dev_administration.forgejo_utils.time.sleep")
@patch("dev_administration.forgejo_utils.subprocess.run")
def test_curl_gives_up_after_the_attempt_budget(mock_run, _sleep):
    mock_run.side_effect = _fail(7)
    with pytest.raises(subprocess.CalledProcessError):
        _curl("http://x/api", "tok", attempts=4)
    assert mock_run.call_count == 4
```

- [ ] **Step 2: Run to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_compose_startup_ordering.py dev-administration/tests/test_forgejo_utils.py -v
```

Expected: the two compose tests **FAIL** (no healthcheck; `depends_on` is a bare list) and the three `_curl` tests **FAIL** (`_curl` takes no `attempts`; `forgejo_utils.time` does not exist).

- [ ] **Step 3: Add the healthcheck and the condition**

In `compose.yml`, add to the `forgejo` service after `restart: unless-stopped`:

```yaml
    # Gates dev-admin. Without it, dev-admin runs `reconcile` the instant this
    # CONTAINER starts — before Forgejo is SERVING — and dies with curl exit
    # 22 on every fresh deploy. /api/healthz reports cache and database
    # readiness, not merely a listening socket. curl ships in this image.
    healthcheck:
      test: ["CMD", "curl", "-fsS", "-o", "/dev/null", "http://localhost:3000/api/healthz"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 30s
```

and replace `dev-admin`'s dependency:

```yaml
    depends_on:
      forgejo:
        condition: service_healthy
      # dev-admin reaches Forgejo THROUGH Caddy and docker-execs into Caddy to
      # write Caddyfile.d, so Caddy must at least exist. Compose offers no
      # health condition for a host-networked container that serves before its
      # own generated config is written, so the residual window is covered by
      # the bounded retry in forgejo_utils._curl.
      caddy:
        condition: service_started
```

- [ ] **Step 4: Add the bounded retry**

Replace the top of `dev-administration/dev_administration/forgejo_utils.py` through the end of `_curl`:

```python
from __future__ import annotations

import json
import subprocess
import time

# curl exit codes meaning "the far end was not ready", as opposed to "the far
# end answered and the answer was an error". Only these are retried: a 401 or
# 404 (exit 22, an HTTP status) is an answer, and retrying it six times turns
# a clear failure into a slow, confusing one.
_TRANSIENT_CURL_EXITS = frozenset({
    6,   # could not resolve host
    7,   # failed to connect
    28,  # operation timed out
    35,  # SSL connect error
    52,  # empty reply from server
    56,  # failure receiving network data
})


def _curl(
    url: str,
    token: str,
    method: str = "GET",
    data: dict | None = None,
    attempts: int = 6,
    backoff: float = 2.0,
) -> dict | list | None:
    """Call the Forgejo API, retrying only connection-class failures.

    dev-admin reaches Forgejo through Caddy, so this survives a Caddy recreate
    window as well as a Forgejo that is up but not yet serving — the failure
    that leaves dev-admin `Exited (1)` after every deploy.
    """
    cmd = [
        "curl", "-fsS",
        "-X", method,
        url,
        "-H", f"Authorization: token {token}",
        "-H", "Content-Type: application/json",
    ]
    if data:
        cmd.extend(["-d", json.dumps(data)])

    last: subprocess.CalledProcessError | None = None
    for attempt in range(attempts):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as exc:
            if exc.returncode not in _TRANSIENT_CURL_EXITS:
                raise
            last = exc
            if attempt + 1 < attempts:
                time.sleep(backoff * (attempt + 1))
            continue
        if not result.stdout.strip():
            return None
        return json.loads(result.stdout)

    assert last is not None
    raise last
```

- [ ] **Step 5: Run**

```bash
.venv/bin/python -m pytest tests/test_compose_startup_ordering.py dev-administration/tests -v 2>&1 | tail -8
AURORA_PROJECT=tai-review .venv/bin/python -m pytest tests dev-administration/tests -v 2>&1 | tail -8
```

Expected: everything passes **except** `test_declared_bind_sources_match_runtime`, which stays red until Task 12's deploy (Task 8 Step 7). `test_no_tracked_file_outside_docs_names_the_old_project` is green again by now — Task 10 cleared it.

The `AURORA_PROJECT=tai-review` override is required until the deploy — see the constraint at the top of this plan; without it `test_the_conformance_gate_has_containers_to_conform_to` (Task 9) fails, because the deployed containers still carry the old project label.

The behavioural proof — that a real `--force-recreate` no longer leaves `dev-admin` at `exit=1` — cannot run before the deploy and is executed as **Task 12 Step 4d**.

- [ ] **Step 6: Commit**

```bash
git add compose.yml dev-administration/ tests/
git -c user.name="supergoodname77" -c user.email="epascuales@outlook.com" \
  commit -m "fix: dev-admin no longer races Forgejo's startup

Forgejo gains a /api/healthz healthcheck and dev-admin gates on
service_healthy. Because dev-admin reaches Forgejo THROUGH Caddy, a
healthcheck alone cannot cover a Caddy recreate window, so _curl also
retries connection-class curl exits (6/7/28/35/52/56) with backoff while
still failing an HTTP error immediately.

Live proof runs at deploy time — Task 12 Step 4d."
```

---

## Task 12: Chunk 2 acceptance, deploy, and documentation

**Files:**
- Create: `tests/test_second_project_ready.py`
- Create: `docs/testing/2026-07-28-chunk2-project-parameterised.md`
- Create: `docs/implementations/2026-07-28-chunk2-project-parameterised.md`
- Create: `docs/issues/chunk2-spec-deltas.md`
- Modify: `docs/post-implementation-steps.md`

**Interfaces:**
- Consumes: everything above — in particular Task 9's move procedure, its three `aurora_`-prefixed agent volumes and its per-volume regenerate decisions.
- Produces: the acceptance gate for Chunk 2, and the one deploy. Chunk 3 may not begin until it passes.

**Context the implementer needs:** Chunk 2 builds no branch, so its acceptance cannot be "a branch works". The testable property is: *everything Chunk 3 will need to override is enumerated, and nothing else escapes the project*. Two enumerations are load-bearing, because spec §4.2 was written before AFFiNE came in-tree and before agents became compose services, and the counts it states are now wrong.

**This task contains the plan's only downtime.** Step 4 tears the whole stack down under its old project name, renames the directory, and brings it back up under the new one. Every other change in Chunk 2 rides along in that same window, so there is exactly one restart, not two.

**The path changes mid-task.** Steps 1–3 and Step 4a run in `~/Desktop/tai-review`; Step 4b renames it; everything from 4c onward runs in `~/Desktop/aurora`. Steps 2 and 3 need `AURORA_PROJECT=tai-review`; from Step 5 onward they must **not** have it.

- [ ] **Step 1: Write the acceptance tests**

Create `tests/test_second_project_ready.py`:

```python
"""Chunk 2 acceptance: the stack is project-parameterised.

Chunk 2 builds no branch, so acceptance is not "a branch works". It is:
everything Chunk 3's compose.branch.yml must override is enumerated here, and
nothing else escapes the project. If a later change adds a container_name or
a published port without updating these lists, Chunk 3's `!reset` override
would silently miss it and two stacks would collide on a daemon-global name.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from conftest import ALLOWED_EXTERNAL_BINDS, REPO_ROOT, compose_config

# Every service declaring container_name:. Spec §4.2 says "the four services
# that declare one" — written before AFFiNE came in-tree (Chunk 1) and before
# agents became compose services (Chunk 2, M4). It is eight plus one per
# developer. Chunk 3 must `container_name: !reset null` on all of them:
# container_name opts a service OUT of project namespacing, so an unreset one
# collides daemon-globally and the second stack fails to start.
EXPECTED_CONTAINER_NAMES = {
    "affine": "affine_server",
    "affine_migration": "affine_migration_job",
    "dev-admin": "dev-admin",
    "forgejo": "forgejo",
    "forgejo-mcp": "forgejo-mcp",
    "hermes": "hermes",
    "postgres": "affine_postgres",
    "redis": "affine_redis",
}

# Every service publishing a host port. Chunk 3 sets `ports: !reset []` on all
# of them — a branch publishes none (spec §5.1), which makes port collision
# unrepresentable rather than merely avoided.
EXPECTED_PUBLISHING_SERVICES = {
    "affine", "agent-authz", "arcadedb", "fjell", "forgejo", "hermes",
}


def _agent_services(config: dict) -> set[str]:
    return {s for s in config["services"] if s.startswith("hermes-")}


def _escaping_binds(config: dict, root: Path) -> list[tuple[str, str]]:
    escapes = []
    for name, svc in config["services"].items():
        for vol in svc.get("volumes", []):
            if vol.get("type") != "bind":
                continue
            source = Path(vol["source"]).resolve()
            if source in ALLOWED_EXTERNAL_BINDS:
                continue
            if source != root and root not in source.parents:
                escapes.append((name, str(source)))
    return escapes


def test_container_name_declarations_are_enumerated():
    config = compose_config()
    declared = {
        name: svc["container_name"]
        for name, svc in config["services"].items()
        if svc.get("container_name")
    }
    expected = dict(EXPECTED_CONTAINER_NAMES)
    expected.update({a: a for a in _agent_services(config)})
    assert declared == expected, (
        "container_name: declarations changed. Update this list AND spec §4.2 "
        "AND Chunk 3's compose.branch.yml — an unreset container_name is a "
        "daemon-global name two stacks cannot share."
    )


def test_published_port_declarations_are_enumerated():
    config = compose_config()
    publishing = {n for n, svc in config["services"].items() if svc.get("ports")}
    assert publishing == EXPECTED_PUBLISHING_SERVICES | _agent_services(config), (
        "Published-port set changed. Chunk 3's `ports: !reset []` list must "
        "cover exactly this set."
    )


def test_no_service_escapes_the_repo_via_a_bind():
    assert _escaping_binds(compose_config(), REPO_ROOT) == []


def test_a_fresh_worktree_resolves_as_an_independent_project():
    """The Chunk 2 property, end to end: an identical tree under a different
    project name resolves a complete config whose every relative path points
    at ITSELF, not at production."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "probe"
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(target), "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        )
        try:
            env_text = (REPO_ROOT / ".env").read_text().replace(
                "COMPOSE_PROJECT_NAME=aurora",
                "COMPOSE_PROJECT_NAME=br-probe",
            )
            assert "COMPOSE_PROJECT_NAME=br-probe" in env_text, (
                "The .env this test rewrites no longer declares "
                "COMPOSE_PROJECT_NAME=aurora — the substitution silently did "
                "nothing and the probe would inherit the directory basename"
            )
            (target / ".env").write_text(env_text)

            env = dict(os.environ)
            env["COMPOSE_PROFILES"] = "*"
            result = subprocess.run(
                ["docker", "compose", "config", "--format", "json"],
                cwd=target, capture_output=True, text=True, env=env,
            )
            assert result.returncode == 0, (
                f"A fresh worktree cannot resolve compose config:\n{result.stderr}"
            )
            config = json.loads(result.stdout)
            assert config["name"] == "br-probe"

            escapes = _escaping_binds(config, target.resolve())
            assert escapes == [], (
                "A second project's binds still point outside its own tree — "
                f"it would share production's state: {escapes}"
            )
            assert _agent_services(config), (
                "No hermes-* services in a fresh worktree — compose.agents.yml "
                "is either uncommitted or not included"
            )
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(target)],
                cwd=REPO_ROOT, capture_output=True, text=True,
            )
```

- [ ] **Step 2: Run the acceptance suite**

```bash
cd ~/Desktop/tai-review/.worktrees/chunk2
AURORA_PROJECT=tai-review .venv/bin/python -m pytest tests/test_second_project_ready.py -v
```

Expected: **4 passed.** If the fresh-worktree test reports escaping binds, Task 8 is incomplete. If it reports no agent services, `compose.agents.yml` was not committed — check `git ls-files compose.agents.yml`. If its `COMPOSE_PROJECT_NAME=br-probe` assertion fires, Task 9 Step 3 did not reach the worktree's `.env`.

- [ ] **Step 3: Full sweep in the worktree**

```bash
AURORA_PROJECT=tai-review .venv/bin/python -m pytest tests dev-administration/tests -v 2>&1 | tail -8
docker compose config --quiet && echo CONFIG_OK
docker compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])'
```

Expected: one failure only — `test_declared_bind_sources_match_runtime`, still red pending the deploy. `CONFIG_OK`, and the project name `aurora`. Record the exact counts for the implementation log. This is the last run that needs the `AURORA_PROJECT` override.

- [ ] **Step 4: Merge, rename, and deploy**

Everything above is inert in production until this runs (F3), and it all lands in one window. **Expected disruption: a full outage of 60–90 seconds.** Because the project is being renamed, this is a complete `down` and `up` rather than the rolling recreate an ordinary Chunk 2 deploy would have been — `com.docker.compose.project` is fixed at container-create time, so no running container can be moved between projects. Unavailable for the whole window: `/git/`, `/affine/`, `/admin/`, `/agent/*`, the fjell landing page, and the Hermes dashboards on `127.0.0.1:9119` and the tailnet `:7444` serve. Nothing is unavailable before 4c-i or after 4c-v.

**4a — merge.** Run this from the *old* path; the rename happens in 4c.

```bash
cd ~/Desktop/tai-review
git -c user.name="supergoodname77" -c user.email="epascuales@outlook.com" \
  merge --no-ff feat/project-parameterised \
  -m "Merge Chunk 2: the stack becomes project-parameterised"
```

**4b — pre-flight.** Nothing below is reversible cheaply once the stack is down, so check first. The `.hermes` staging (Task 8) and both volume migrations (Task 5 Step 8, Task 9 Step 4) must already be done, or Hermes and the agents boot on empty state:

```bash
ls ~/Desktop/tai-review/.hermes/state.db
for u in testuser newuser cumshit42069; do
  docker volume inspect "aurora_hermes-$u-home" --format '{{.Name}} {{.Labels}}'
done
grep -n '^COMPOSE_PROJECT_NAME=' ~/Desktop/tai-review/.env
ls -d ~/Desktop/aurora 2>&1
```

Expected: `state.db` listed; three volume lines each showing
`com.docker.compose.project:aurora`; the production `.env` **still** reading
`COMPOSE_PROJECT_NAME=tai-review`; and `~/Desktop/aurora` reported as
**No such file or directory**. If `~/Desktop/aurora` already exists, stop —
something is half-renamed and the `mv` below would nest one tree inside the
other.

**4c — the rename and the deploy. This is the whole downtime window.**

**Expected downtime: 60–90 seconds**, of which the teardown and the `mv` are
a few seconds each and the rest is service startup. During it, *everything*
on `superserver.tailc67a98.ts.net` is unavailable — `/git/`, `/affine/`,
`/agent/*`, the fjell landing page, the Hermes dashboards on :9119 and :7444.
This is a full `down`/`up`, not a rolling recreate, because a project rename
cannot be applied to a running container: the project name is baked into
`com.docker.compose.project` at create time. Announce it before starting.

The order matters and each command depends on the one before it:

```bash
# i. Tear down the OLD project, while .env still names it.
cd ~/Desktop/tai-review
docker compose --profile '*' down --remove-orphans
docker ps -a --filter label=com.docker.compose.project=tai-review -q | wc -l
```

Expected: Compose removing every container and the `tai-review_default`
network, then `0`.

Two things can go wrong here and both are recoverable if caught now:

- **`Error response from daemon: error while removing network … has active endpoints`.** An unlabelled container is still attached, and `down` cannot see it to remove it — a *stopped* container still holds its endpoint. Task 2 Step 3 already removed the one that existed (`agent-authz`, `Exited (137)`), so this should not recur; if it does, find it with `docker network inspect tai-review_default --format '{{json .Containers}}'`, confirm it is stopped, and `docker rm` it. The old network being left behind is harmless to the rename but means the teardown was incomplete.
- **A non-zero container count.** Something survived. Identify it before renaming rather than after: it will keep the old project alive alongside the new one.

Note `--profile '*'`: the agent services carry `profiles:` as of M4, and `down` only removes services whose profile is active. Production's `.env` sets `COMPOSE_PROFILES=agents`, which would cover them anyway; the explicit flag makes the teardown independent of that variable being right.

```bash
# ii. Rename the directory. This is the rename.
cd ~
mv ~/Desktop/tai-review ~/Desktop/aurora
ls -d ~/Desktop/aurora ~/Desktop/tai-review 2>&1
```

Expected: `~/Desktop/aurora` listed, `~/Desktop/tai-review` reported as
**No such file or directory**.

```bash
# iii. Repair the two git worktrees, whose links are stored absolutely.
cd ~/Desktop/aurora
git worktree repair .worktrees/ephemeral-branching .worktrees/chunk2
git worktree list
cat .git/worktrees/chunk2/gitdir
(cd .worktrees/chunk2 && git status -s >/dev/null && echo LINKED_OK)
```

**Pass the paths explicitly.** Probed on this host: after moving a repo whose
worktrees live inside it, a bare `git worktree repair` with no arguments
**silently does nothing** — `git worktree list` still shows the old path and
the linked worktree still reports `fatal: not a git repository: (null)`.
Naming each worktree path fixes both directions of the link in one call: the
`.git` file inside the worktree and `.git/worktrees/<id>/gitdir` in the main
checkout.

Expected: one line per repaired worktree, of the form
`repair: gitdir incorrect: /var/home/supergoodname77/Desktop/aurora/.git/worktrees/chunk2/gitdir`;
then `git worktree list` showing three entries all under
`/var/home/supergoodname77/Desktop/aurora`; the `gitdir` file naming the new
path; and `LINKED_OK`. Skipping this leaves every later command that runs
inside a worktree — including Step 5's test run — failing with
`fatal: not a git repository`.

```bash
# iv. Declare the new project name in the live .env.
cd ~/Desktop/aurora
sed -i 's/^COMPOSE_PROJECT_NAME=tai-review$/COMPOSE_PROJECT_NAME=aurora/' .env
grep -n '^COMPOSE_PROJECT_NAME=' .env
docker compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])'
docker compose config --quiet && echo CONFIG_OK
```

Expected: `COMPOSE_PROJECT_NAME=aurora`, then `aurora`, then `CONFIG_OK`.
The `sed` must have matched — if `grep` still shows `tai-review`, the line
was not exactly as Task 5 Step 6 wrote it; fix it by hand rather than
proceeding, or the `up` below recreates the *old* project at the *new* path.

```bash
# v. Bring the new project up.
mkdir -p ~/Desktop/aurora/.agent-env
docker compose up -d
```

Expected: Compose *creating* — not recreating — every container under the new
name: `aurora-caddy-1`, `aurora-fjell-1`, `aurora-agent-authz-1`,
`aurora-arcadedb-1`, plus the `container_name:`-pinned `forgejo`,
`forgejo-mcp`, `hermes`, `dev-admin`, `affine_server`, `affine_postgres`,
`affine_redis`, `affine_migration_job`, and the three agents
`hermes-testuser`, `hermes-newuser`, `hermes-cumshit42069`. It also creates
the six declared volumes fresh and **empty** under the `aurora_` prefix —
`aurora_caddy_data`, `aurora_caddy_config`, `aurora_arcadedb_backups`,
`aurora_arcadedb_config`, `aurora_arcadedb_log`, `aurora_arcadedb_replication`
— which is the decision taken and justified per volume in Task 9. It must
**not** report creating `aurora_hermes-*-home`: those already exist with the
migrated data and are adopted by their labels.

```bash
# vi. Prove the six regenerated volumes regenerated.
docker run --rm -v aurora_caddy_data:/x:ro alpine find /x -mindepth 1 | sort
docker run --rm -v aurora_arcadedb_config:/x:ro alpine sh -c 'find /x -type f | wc -l'
docker volume ls --format '{{.Name}}' | grep -E '^(tai-review|aurora)_' | sort
```

Expected: Caddy has written `caddy/instance.uuid` and `caddy/last_clean.json`
again — regenerated, exactly as predicted, with still no `caddy/certificates`;
`7` config files restored from the image; and both the `tai-review_*` and
`aurora_*` volume sets listed side by side. The `tai-review_*` set is the
rollback and is deleted only in Step 9's post-implementation list.

Two host-level things deliberately need **no** action here, stated so nobody
goes looking: the `tailscale serve --bg --https 7444 http://127.0.0.1:9119`
mapping is tailscaled configuration keyed on a loopback port, not on a path or
a container name; and the Forgejo git remote already points at
`…/supergoodname77/aurora.git` (Task 9 verified it), so no remote is
re-pointed.

**4d — the F2 proof** (deferred from Task 11 Step 5):

```bash
docker compose up -d --force-recreate forgejo dev-admin
sleep 90
docker inspect forgejo  --format '{{.State.Health.Status}}'
docker inspect dev-admin --format '{{.State.Status}} exit={{.State.ExitCode}}'
docker logs dev-admin --tail 5
```

Expected: `healthy`; `exited exit=0`; and a final log line `Reconciled 3 developers. N events emitted.` — **not** a `CalledProcessError` traceback. `exit=0` is correct for `dev-admin`: it is a one-shot `restart: "no"` job.

**4e — service checks:**

```bash
docker compose ps
curl -sS -o /dev/null -w 'git=%{http_code}\n'    https://superserver.tailc67a98.ts.net/git/
curl -sS -o /dev/null -w 'affine=%{http_code}\n' https://superserver.tailc67a98.ts.net/affine/
curl -sS -o /dev/null -w 'root=%{http_code}\n'   https://superserver.tailc67a98.ts.net/
curl -sS -o /dev/null -w 'agent=%{http_code}\n'  https://superserver.tailc67a98.ts.net/agent/testuser/
docker exec hermes-testuser ls /opt/data/state.db
```

Expected: every service `running` except `dev-admin` and `affine_migration` (both `exited (0)`); `git=200`, `affine=200`, `root=401` (basic auth — correct, not a failure), `agent=` `200` or `302` (the OIDC bounce). A `502` on `agent=` means the agent is not reachable and must be fixed before claiming completion. The last command proves the migrated volume data actually arrived in the running agent.

**These four `curl`s are also the certificate test.** They are HTTPS against `superserver.tailc67a98.ts.net` served by a Caddy whose `/data` volume is brand new and empty. If they return HTTP codes at all, Caddy obtained a certificate with no prior certificate state — which is the regenerate decision for `caddy_data` proven in production rather than argued from a directory listing. A TLS error here (`curl: (60)`, `curl: (35)`, or a hang) is the one outcome that would have justified migrating that volume; if it happens, roll back per the rollback note, migrate `tai-review_caddy_data` into `aurora_caddy_data` with the same `cp -a` recipe used for the agent volumes, and redeploy.

Finally, confirm the repo itself is intact after the move:

```bash
cd ~/Desktop/aurora
git status -s
git worktree list
```

Expected: `git status -s` shows **only** the three runtime-generated files — `Caddyfile.d/agents.conf`, `Caddyfile.d/agents.json`, `agent-authz/data/owners.json` — and `git worktree list` shows three entries under the new path. Anything else means the merge or the move left something behind.

**4f — the M6 watch item.** `.hermes` now lives inside the tree that is itself mounted at `/opt/data/workspace/aurora`, so from inside the container `/opt/data/workspace/aurora/.hermes` exposes 2.6 GB of Hermes' own state to anything walking the workspace. Nested binds are not propagated, so the recursion terminates one level down, but a workspace-wide file scan now has 2.6 GB more to walk:

```bash
docker stats --no-stream hermes
docker logs hermes --since 3m 2>&1 | tail -20
```

Expected: CPU settles to its normal idle within a minute or two, and no repeated scan/index messages naming `workspace/aurora/.hermes`. If it does not settle, record it in `docs/issues/` and add a workspace exclusion — do **not** revert the mount, which would reintroduce the isolation defect.

**Rollback for the whole deploy.** Two independent layers:

*The code:* `git revert` the merge commit and `docker compose up -d`. `~/.hermes` and the nine unprefixed `hermes-*-home` volumes were copied, never moved, so all prior state is intact.

*The rename:* it is reversible by undoing 4c in reverse — `docker compose --profile '*' down`, `mv ~/Desktop/aurora ~/Desktop/tai-review`, `git worktree repair` from the old path, `sed` `COMPOSE_PROJECT_NAME` back to `tai-review`, `docker compose up -d`. The `tai-review_*` volumes were never deleted, so the old project comes back on exactly the state it left.

**The one thing that is not reversible is volume data that was not migrated.** The six declared volumes were deliberately allowed to regenerate; anything Caddy or ArcadeDB writes into the `aurora_*` set *after* the deploy exists only there. Rolling the rename back after a soak therefore reverts Caddy's instance UUID and ArcadeDB's log — both regenerable, which is why they were chosen — but the choice is one-way for anything written since. The three agent volumes were migrated precisely so this does not apply to them. **Do not delete any `tai-review_*` volume as part of this task**; that is a post-soak step in Step 9.

- [ ] **Step 5: Run the full gate against the deployed stack**

Note the path — the worktree moved with its parent — and note that there is
**no `AURORA_PROJECT` override any more**: `conftest.PRODUCTION_PROJECT`'s
default of `aurora` is now the truth.

```bash
cd ~/Desktop/aurora/.worktrees/chunk2
.venv/bin/python -m pytest tests dev-administration/tests -v 2>&1 | tail -8
```

Expected: **everything passes, including `test_declared_bind_sources_match_runtime`** — the test Task 8 left red — and including `test_the_conformance_gate_has_containers_to_conform_to`, which is now the proof that the rename actually reached the running containers rather than merely the declarations. This step is the reason Task 2 exists: it proves the deploy matches the declaration, for image, bind source and published port, across every container in the project.

If the suite reports `fatal: not a git repository`, step 4c-iii's
`git worktree repair` was skipped.

- [ ] **Step 6: Write the spec-deltas issue**

Create `docs/issues/chunk2-spec-deltas.md` recording, with evidence, each spec claim Chunks 1 and 2 have invalidated, so Chunk 3 does not inherit it:

1. **§4.2 "`container_name: !reset null` on the four services that declare one"** — it is eight, plus one per developer. Evidence: `tests/test_second_project_ready.py::test_container_name_declarations_are_enumerated`.
2. **D3 "Branch runs the *unmodified* prod Caddyfile with only `DOMAIN_NAME` differing"** — false as written: every upstream was a literal `127.0.0.1` address, unreachable from a sidecar netns. Repaired in Task 7; a branch now differs by `DOMAIN_NAME` **and** `AFFINE_UPSTREAM` / `FORGEJO_UPSTREAM` / `FJELL_UPSTREAM` **and** `AGENT_UPSTREAM_MODE=service`.
3. **D9 / §7.2 "emit Compose `profiles` in the branch override"** — sound, but only once the conformance gate uses `COMPOSE_PROFILES="*"` (Task 1). Full reasoning in the recommendation at the end of the Chunk 2 plan. Also note: the gate is now permissive in one direction, so Chunk 3 should add `test_no_container_runs_from_an_inactive_profile` using `compose_config(all_profiles=False)`.
4. **§6.1 "Hermes volume, per developer 70 MB" and §6.2 "Total seedable state is ~100-200 MB, which copies in well under a second"** — the *admin* Hermes home is **2.7 GB** and appears nowhere in §6.1's table. Reflink keeps the copy cheap on btrfs, but §6.2's plain-copy fallback claim is wrong by an order of magnitude, and §5.5's resource guard should be sized against the real figure.
5. **§6.3 "each Hermes volume's four DBs"** — the admin home holds at least `state.db` (46 MB, with live `-wal` and `-shm`), `kanban.db`, `projects.db`, `cron/executions.db` **and** `verification_evidence.db`. The seeder must enumerate `*.db` rather than a fixed list of four.
6. **§4.1 step 5 "`dev-admin reconcile` … provisions the requesting developer's agent"** — after M4, `reconcile` creates no containers. `aurora branch up` must run `docker compose up -d` *after* `reconcile`, not instead of it. The `container.missing` warning event is the signal.
7. **§7.4 BRANCH-ACCESS.md's `/agent/<developer>/` URLs** — correct, but dead unless the branch `.env` sets `AGENT_UPSTREAM_MODE=service`. Add it to the branch `.env` renderer alongside the three `*_UPSTREAM` variables.
8. **§5.1's volume row** — now true rather than aspirational: agent volumes are `<project>_hermes-<user>-home` as of M4. Chunk 3's teardown test can assert it directly.
9. **Every `tai-review` name in the spec is now `aurora`.** §4.3's "set `COMPOSE_PROJECT_NAME` explicitly, don't rely on the directory-basename default" was describing a requirement production itself did not meet: the variable was unset and the name came from the directory. Task 9 fixed that and renamed the checkout to match. Record here, for Chunk 3, that: the production project is `aurora`; the network is `aurora_default`; the compose-synthesised container names are `aurora-<service>-1`; the checkout is `~/Desktop/aurora`; and `docs/` written before 2026-07-28 uses the old name throughout and was deliberately not rewritten, because it records what was observed at the time. The two design specs *were* updated (Task 9 Step 6) because Chunk 3 reads them as instructions rather than as history.
10. **Six project-prefixed volumes did not survive the rename, by design.** `caddy_data`, `caddy_config` and the four `arcadedb_*` were read and found to contain only regenerable state — no `caddy/certificates/` (the `.ts.net` certificate comes from tailscaled at handshake time, and ACME cannot validate a tailnet-only name at all), and an ArcadeDB config byte-identical to the image default. Chunk 3 must assume the same for `br-<name>` stacks: **a project-prefixed volume does not follow a project rename, and Compose gives no warning when it silently creates an empty replacement.** Any branch teardown/re-create flow that relies on volume contents must migrate them explicitly.

- [ ] **Step 7: Write the testing doc**

Create `docs/testing/2026-07-28-chunk2-project-parameterised.md` covering:

- **What each test catches:** the profile pair (a gate that goes blind the moment a service is profiled); `test_runtime_conformance.py` (declaration/runtime drift — the AFFiNE class of defect); the project-network label test (imperative `docker run` containers Compose cannot see); `test_guard_coverage.py` (a new mutating function added without a guard); `test_agents_compose_matches_developers_yaml` (a generated file committed stale); `test_compose_startup_ordering.py` plus the `_curl` retry tests (the deploy-time race); `test_second_project_ready.py` (the Chunk 2 acceptance property and the two enumerations Chunk 3 depends on).
- **How to run:** `.venv/bin/python -m pytest tests dev-administration/tests -v` from the repo root, using the worktree venv. There is no system pytest.
- **What is deliberately NOT covered:** no branch is created, so nothing here proves two stacks coexist — that is Chunk 3's `test_concurrent_prod_and_branch`. The §5.3 guard is unit-tested against mocked `docker inspect`; spec §10.2's live test ("a branch-context operation aimed at prod's Caddy must refuse") needs a second running project and lands in Chunk 3. The `service` upstream mode is asserted at the string level and by `caddy adapt`; nothing routes through it until a branch exists.
- **The one manual check:** Step 4f's Hermes CPU/log observation, which cannot be asserted.
- **The rename's two gates:** `test_no_tracked_file_outside_docs_names_the_old_project` (a live reference to `tai-review` surviving outside the historical record, with the one documented exception for `test_guard_coverage.py`) and `test_the_conformance_gate_has_containers_to_conform_to` (the runtime gate passing vacuously because `PRODUCTION_PROJECT` names a project that has no containers — the specific way a project rename blinds a conformance suite).
- **The one test that is intentionally red mid-chunk:** `test_declared_bind_sources_match_runtime`, between Task 8 and the deploy — and why that is finding F3 rather than a defect.
- **The window that needs an environment override:** between Task 9 and the deploy the suite must be run as `AURORA_PROJECT=tai-review …`, because the declarations name `aurora` and the running containers still say `tai-review`. After the deploy the override must be dropped. Say so, because it is the kind of incantation that gets copied forward forever.

- [ ] **Step 8: Write the implementation log**

Create `docs/implementations/2026-07-28-chunk2-project-parameterised.md` recording, per task: what changed, what was verified and how (commands and their *actual* output, not the expected output copied from this plan), and every divergence from this plan with its reason. Per the practices doc this file is updated on every iteration, not written once. Include verbatim: the volume-migration size comparisons from Task 5 Step 8 **and Task 9 Step 4**, the re-verified volume-contents listings from Task 9 Step 2 (including whether `caddy/certificates` was present — the one finding that would have changed the migrate-or-regenerate decision), the `caddy adapt` dial lists from Task 7 Step 5, and the full deploy output from Step 4 including the measured length of the outage window against the 60–90 s estimate.

- [ ] **Step 9: Update `docs/post-implementation-steps.md`**

**Close §D1.** Replace its body with the resolution: fjell registers `/agent/{username}/setup` (`fjell/src/routes/setup.rs:91`), so the route must not strip its prefix; `handle` is correct and the test's `handle_path` assertion was wrong. Note also that the same test's `reverse_proxy fjell:9080` was stale from `63b23b7`, one commit *earlier* than §D1 records, and that it now serves as the service-mode assertion. Fixed in Task 6.

**Correct the file's own paths.** This document is a live runbook, not a dated record, so unlike the rest of `docs/` it must be updated: every `~/Desktop/tai-review` becomes `~/Desktop/aurora`, `tai-review-caddy-1` becomes `aurora-caddy-1`, `docker compose -p tai-review` becomes `-p aurora`, and `tai-review_model-cache` — already removed in Chunk 1 — stays named as it was, since that step is about a volume that no longer exists.

**Add an "After Chunk 2" section:**

1. **Delete `~/.hermes` after a soak.** Task 8 copied rather than moved, so 2.6 GB is duplicated (reflinked, so the real cost is near zero on btrfs). Once the admin agent has run normally for a week from `./.hermes`, `rm -rf ~/.hermes`. Verify first that nothing mounts it:
   `docker ps -q | xargs docker inspect --format '{{.Name}} {{range .Mounts}}{{.Source}} {{end}}' | grep -F '/.hermes'` should name only the repo-relative path.
2. **Delete the six orphaned agent volumes and the three superseded unprefixed ones.** After the project-scoped volumes are confirmed working: `hermes-alicetest-home`, `hermes-bobtest-home`, `hermes-jaun-home`, `hermes-johndear-home`, `hermes-selfreg-home`, `hermes-shitcum-home` belong to deleted accounts; `hermes-testuser-home`, `hermes-newuser-home`, `hermes-cumshit42069-home` are the pre-migration copies kept as rollback.
3. **Establish what destroyed the three agent containers.** During this plan's research window the host destroyed `hermes-testuser`, `hermes-cumshit42069` and `hermes-newuser` (`docker events --since 40m --filter event=destroy`), by something other than Compose — they carried no project label, so `--remove-orphans` could not have. Find out what before trusting the host to be quiescent during Chunk 3's concurrency tests, which assert that production is untouched throughout a branch lifecycle.
4. **Decide whether `developers.yaml`'s joke account (`cumshit42069`) should go** before Chunk 3. It now costs a compose service, a project-scoped volume and a Caddy route in every branch created with `--devs all`.
5. **Rotate `AURORA_PROFILE_URL`'s embedded credentials path.** `provision_developer` still injects `supergoodname77:<FORGEJO_ADMIN_TOKEN>@` into the profile clone URL, so the admin token reaches every agent container's process arguments. Not introduced by Chunk 2, but Chunk 2 read the code and it belongs on this list alongside §0.
6. **Delete the nine superseded `tai-review_*` volumes after a soak.** Six are the pre-rename originals that were deliberately allowed to regenerate — `tai-review_caddy_data`, `tai-review_caddy_config`, `tai-review_arcadedb_backups`, `tai-review_arcadedb_config`, `tai-review_arcadedb_log`, `tai-review_arcadedb_replication`; three are the intermediate agent copies Task 5 made before the rename existed — `tai-review_hermes-testuser-home`, `tai-review_hermes-newuser-home`, `tai-review_hermes-cumshit42069-home`. Together they are the rename's rollback and cost roughly 140 MB. Once `aurora` has served normally for a week, `docker volume rm` them. Check nothing is attached first: `docker ps -aq | xargs docker inspect --format '{{.Name}} {{range .Mounts}}{{.Name}} {{end}}' | grep tai-review` should print nothing.
7. **Rebuild the three `.venv` directories if anyone needs `activate` or a console script.** The move left `bin/activate`'s `VIRTUAL_ENV=` and every `bin/<script>` shebang pointing at `/var/home/supergoodname77/Desktop/tai-review/...`. `.venv/bin/python -m pytest` — the only form this repo's docs use — is unaffected, so this is a convenience item, not a defect: `rm -rf .venv && python3 -m venv .venv && .venv/bin/pip install pytest pyyaml typer` in each of the repo root, `dev-administration/`, and each worktree.
8. **Delete the nested `~/Desktop/aurora/dev-administration/.git`.** Still present — this is the pre-existing §4 item from the Chunk 1 list, restated with its new path so it is not lost to a stale directory name.

- [ ] **Step 10: Commit**

```bash
cd ~/Desktop/aurora/.worktrees/chunk2
git add tests/ docs/
git -c user.name="supergoodname77" -c user.email="epascuales@outlook.com" \
  commit -m "test: chunk 2 acceptance — an identical tree resolves as a second project

Adds the acceptance gate, the testing doc, the implementation log, and
docs/issues/chunk2-spec-deltas.md recording the ten spec claims Chunks 1
and 2 have invalidated, so Chunk 3 does not inherit them — including the
project rename and the fact that a project-prefixed volume does not follow
a rename."
```

Then merge the remaining documentation commits into production, which is now `~/Desktop/aurora`:

```bash
cd ~/Desktop/aurora
git -c user.name="supergoodname77" -c user.email="epascuales@outlook.com" \
  merge --no-ff feat/project-parameterised -m "Merge Chunk 2 documentation"
git status -s
```

Expected: a fast-forward or merge commit, and a working tree showing only the runtime-generated files (`Caddyfile.d/agents.conf`, `Caddyfile.d/agents.json`, `agent-authz/data/owners.json`).

---

## Definition of Done

Chunk 2 is complete when all of the following hold:

1. `.venv/bin/python -m pytest tests dev-administration/tests` passes with **zero** failures — including the previously-inherited `test_generate_caddy_agents_conf`, resolved with evidence rather than deleted, and `test_declared_bind_sources_match_runtime`, green only after the deploy.
2. `docker compose config` resolves in a fresh worktree under a different `COMPOSE_PROJECT_NAME`, and **every** bind in the result points inside that worktree except `/var/run/docker.sock`, `/var/run/tailscale` and `/etc/localtime`.
3. The three developer agents run as Compose services carrying the `aurora` project label, from project-scoped volumes (`aurora_hermes-<user>-home`), with their pre-migration data intact (`docker exec hermes-testuser ls /opt/data/state.db`).
4. No container attached to `aurora_default` lacks the project label.
5. Every mutating dev-admin operation refuses a container belonging to another project, and `test_guard_coverage.py` proves the enumeration is exhaustive.
6. `docker compose up -d --force-recreate forgejo dev-admin` leaves `dev-admin` at `exit=0`, not `exit=1`.
7. Production serves `/git/` and `/affine/` with `200`, `/` with `401`, and `/agent/testuser/` with `200` or `302`.
8. `docs/implementations/2026-07-28-chunk2-project-parameterised.md`, `docs/testing/2026-07-28-chunk2-project-parameterised.md` and `docs/issues/chunk2-spec-deltas.md` are current, and `docs/post-implementation-steps.md` §D1 is closed.
9. The checkout is `~/Desktop/aurora`, `docker compose config` reports `name: aurora`, `git worktree list` shows three worktrees all under the new path, and the only files naming `tai-review` are dated records under `docs/` plus `dev-administration/tests/test_guard_coverage.py`'s deliberate regression literals (`test_no_tracked_file_outside_docs_names_the_old_project`).
10. `README.md` describes the nine-service stack that actually runs, the ephemeral-branching goal, how to run the test suite, and where specs, plans, implementation logs, testing docs and runbooks live.

**Not in scope, deferred to Chunk 3:** `compose.branch.yml` and the `!reset` overrides; the Tailscale sidecar and ephemeral auth keys; the seeder and `SeedStrategy`; the `aurora` CLI and MCP facade; `branch-services.yaml` and `--without`; the live project-guard test that requires a second running project; the pre-push hook; `test_no_container_runs_from_an_inactive_profile`.

---

## Recommendation on Finding #1 (the profiles / D9 problem)

**Keep D9's profile mechanism. Fix the test. Do not redesign.**

The Chunk 1 finding was real but diagnosed one level too shallow. The defect is not "Compose profiles are incompatible with our conformance test"; it is "our conformance test asks Compose a question whose answer depends on which profiles are active, and never says which". Three facts, all probed on this host at Compose v5.3.1, settle it:

1. `docker compose config --services` on a file with one profiled service prints only the unprofiled one. That is the behaviour that broke the gate.
2. `COMPOSE_PROFILES="*" docker compose config --services` prints **both**. There is a single-variable way to ask "everything this file declares, regardless of activation" — precisely the question a *declaration* gate should be asking.
3. `COMPOSE_PROFILES` read from `.env` selects correctly at `up` time, so production activating `agents` and a branch activating `agent-<user>` needs no code, no flags, and no rewriting of a tracked file inside the worktree (which would leave every branch dirty and force `--force` on every teardown).

Task 1 implements (2); Task 5 puts (3) into production on the real stack. That is materially better than deferring the question: D9's mechanism becomes load-bearing in production *before* Chunk 3 depends on it, rather than being first exercised inside the feature that needs it to work.

Two caveats Chunk 3 must carry:

- **The gate becomes permissive in one direction.** With `COMPOSE_PROFILES="*"` the declared set is a superset of what a default `up` starts, so a container running from a service whose profile is *inactive* would no longer be flagged. That is a genuinely different assertion, and `compose_config(all_profiles=False)` exists in Task 1's conftest precisely so Chunk 3 can add `test_no_container_runs_from_an_inactive_profile` when exclusions become real.
- **`--without` still needs its transitive closure, for a reason unrelated to the gate.** Probed: a service whose `depends_on` target sits behind an inactive profile makes the whole project invalid — `service "app" depends on undefined service "db": invalid compose project`, exit 1. Spec §7.2's `also_exclude` closure is therefore not defensive tidiness; it is what keeps the file parseable. That part of D9 needs no change.

The one thing that would genuinely have justified redesigning D9 — profiles interfering with teardown — does not occur: `docker compose down` removes containers by project label, not by profile activation.
