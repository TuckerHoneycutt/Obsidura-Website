# Chunk 1: The Repo Describes Reality — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `compose.yml` a complete and truthful description of the running Aurora stack, so that a git worktree of this repo can build and run it.

**Architecture:** Three migrations from the spec — M1 absorbs `dev-administration/` into the monorepo so build contexts exist in a worktree; M3 brings AFFiNE in-tree via Compose `include:`; M2 deletes the Odysseus stack and dead commented blocks while declaring the arcadedb container that currently survives undeclared. A repo-conformance test suite is written first and drives all three.

**Tech Stack:** Docker Compose v5.3.1, Python 3.13 + pytest, git subtree, Caddy, Fedora/btrfs host.

## Global Constraints

- Host is `superserver.tailc67a98.ts.net`, repo at `~/Desktop/tai-review`, worktree at `~/Desktop/tai-review/.worktrees/ephemeral-branching` on branch `feat/ephemeral-branching`. **All work happens in the worktree.**
- Trunk branch is `master`, not `main` (`origin/main` is 30 commits stale).
- Production must stay up throughout. Any step that recreates a running container names it explicitly.
- Do **not** re-enable the commented-out cargo layer-cache block in `fjell/Dockerfile`; it has caused breakage.
- Hermes retains its `/var/run/docker.sock` mount (spec D12). Do not remove it.
- AFFiNE and arcadedb are **kept**. Odysseus, chromadb, searxng, ntfy are **deleted**.
- Python target is 3.13; the existing package uses `typer` and `pyyaml` only. Do not add **runtime** dependencies. `pytest` is a development tool and is bootstrapped in Task 1 Step 0b.
- **Run tests as `.venv/bin/python -m pytest`, never bare `pytest`.** The host has no system pytest; Task 1 Step 0b creates the virtualenv every later task depends on.
- Commit after every task. Never commit `.env`, `.venv/`, or `.pytest_cache/`.

---

## File Structure

| File | Responsibility |
|---|---|
| `tests/test_repo_conformance.py` | **New.** Asserts the repo describes reality: every build context is tracked in git, and no container in the project is undeclared. Drives every other task. |
| `tests/conftest.py` | **New.** Shared `REPO_ROOT` fixture and compose-config helper. |
| `pytest.ini` | **New.** Repo-root pytest config so `pytest` works from the top level. |
| `dev-administration/` | **Absorbed.** Moves from gitignored external repo to tracked in-tree package, history preserved. |
| `.gitignore` | Drop `dev-administration/` and `odysseus/`; add `dev-administration/.venv/`, `dev-administration/.pytest_cache/`. |
| `affine/compose.yml` | **New (moved).** AFFiNE's four services, brought in-tree from `~/.hermes/workspace/tai/affine/`. |
| `affine/config/`, `affine/data/` | **New (moved).** AFFiNE's config and bind-mounted state. |
| `compose.yml` | Add `include: ./affine/compose.yml`; add `arcadedb` service; delete commented dead blocks. |
| `Caddyfile` | Delete the `/chat` and `/chat/*` Odysseus redirect handlers. |
| `.env.template` | Drop Odysseus/Immich/Falkor/tai-db vars; add AFFiNE vars. |
| `docs/post-implementation-steps.md` | **New.** Manual steps that cannot be scripted (archive the standalone Forgejo repo, rotate the leaked token, register the MCP server). |
| `docs/testing/2026-07-27-chunk1-repo-describes-reality.md` | **New.** Required by the practices doc: what is tested, how to run it, what it deliberately does not cover. |
| `docs/implementations/2026-07-27-chunk1-repo-describes-reality.md` | **New.** Required by the practices doc; updated every iteration. |
| `docs/issues/arcadedb-oom.md` | **New.** Records the unexplained exit 137. |

---

## Task 1: Repo conformance test harness

**Files:**
- Create: `pytest.ini`
- Create: `tests/conftest.py`
- Create: `tests/test_repo_conformance.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `compose_config() -> dict` and `is_tracked(path: Path) -> bool` in `tests/conftest.py`, used by later tasks' tests.

- [ ] **Step 0a: Give the worktree an `.env`**

The worktree has no `.env` (it is gitignored), so `docker compose config` cannot resolve variables
there. Copy production's once, up front — every later task depends on this:

```bash
cd ~/Desktop/tai-review/.worktrees/ephemeral-branching
cp ~/Desktop/tai-review/.env .env
```

Verify: `docker compose config --quiet 2>&1 | head -3` prints no "variable is not set" warnings.
It will still fail on the missing `dev-administration` build context — that is the defect Task 2
fixes, not an env problem.

- [ ] **Step 0b: Bootstrap a Python test toolchain**

**Verified precondition:** pytest is not installed anywhere on this host. `python3` is 3.14.6,
`pytest` is not on `PATH`, the `pytest` module is absent from the system interpreter, and
`dev-administration/.venv` exists but is **empty** (no packages at all). `uv` is not installed.
Every `pytest` invocation in this plan fails with `ModuleNotFoundError` until this step runs.

Create a virtualenv at the worktree root:

```bash
cd ~/Desktop/tai-review/.worktrees/ephemeral-branching
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet pytest pyyaml typer
```

`pyyaml` and `typer` are the existing runtime dependencies of the `dev_administration` package
declared in its `pyproject.toml`; they are needed so that package's 7 inherited test modules can
import. This adds no new *runtime* dependency to the project — pytest is a development tool only.

Add to `.gitignore` (the repo root one, which currently contains `.env` and `.worktrees/`):

```
.venv/
```

**From this point on, every test invocation in this plan is written as `.venv/bin/python -m pytest`.**
Run it exactly as written — a bare `pytest` will not resolve on this host.

Verify:

```bash
.venv/bin/python -m pytest --version
```

Expected: a pytest version string, exit 0.

- [ ] **Step 1: Write the failing test**

Create `pytest.ini`:

```ini
[pytest]
testpaths = tests dev-administration/tests
python_files = test_*.py
```

Create `tests/conftest.py`:

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


def compose_config() -> dict:
    """Fully resolved compose configuration for the repo, as a dict."""
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
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


@pytest.fixture
def config() -> dict:
    return compose_config()
```

Create `tests/test_repo_conformance.py`:

```python
import subprocess

from conftest import PRODUCTION_PROJECT, REPO_ROOT, is_tracked


def test_every_build_context_is_tracked_in_git(config):
    """A build context that git does not track cannot exist in a worktree,
    so the stack would be unbuildable there."""
    untracked = []
    for name, service in config["services"].items():
        build = service.get("build")
        if not build:
            continue
        context = build["context"]
        if not is_tracked(REPO_ROOT / context):
            untracked.append((name, context))

    assert untracked == [], (
        "Build contexts not tracked in git — a fresh worktree cannot build "
        f"these services: {untracked}"
    )


def test_no_undeclared_containers_in_project(config):
    """Every container carrying the production project's label must
    correspond to a service declared in compose.yml.

    The label is deliberately not taken from config["name"]: in a git
    worktree that resolves to the directory basename, matches nothing, and
    the assertion passes vacuously. Set AURORA_PROJECT to check another
    stack.
    """
    declared = set(config["services"])
    result = subprocess.run(
        [
            "docker", "ps", "-a",
            "--filter", f"label=com.docker.compose.project={PRODUCTION_PROJECT}",
            "--format", "{{.Label \"com.docker.compose.service\"}}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    running = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    undeclared = sorted(running - declared)

    assert undeclared == [], (
        f"Containers labelled for project {PRODUCTION_PROJECT!r} but declared "
        f"nowhere in compose.yml: {undeclared}. Either declare them or remove them."
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd ~/Desktop/tai-review/.worktrees/ephemeral-branching && .venv/bin/python -m pytest tests/test_repo_conformance.py -v`

Expected: **both FAIL.**
- `test_every_build_context_is_tracked_in_git` fails listing `('dev-admin', './dev-administration')`.
- `test_no_undeclared_containers_in_project` fails listing `['arcadedb', 'chromadb', 'ntfy', 'odysseus', 'searxng']` — the containers running under the `tai-review` project label (`PRODUCTION_PROJECT`) that compose.yml does not declare.

If `docker compose config` itself errors because `dev-administration/` is absent from the worktree, that is the same defect surfacing earlier; proceed to Task 2, which fixes it.

- [ ] **Step 3: Commit the failing tests**

```bash
git add pytest.ini tests/
git commit -m "test: repo conformance — build contexts tracked, no undeclared containers

Both tests fail today: dev-administration/ is a gitignored build context,
and five containers carry the project label without being declared."
```

---

## Task 2: Absorb dev-administration into the monorepo (M1)

**Files:**
- Modify: `.gitignore`
- Create: `dev-administration/**` (via `git subtree`, 33 commits of history preserved)
- Create: `dev-administration/.gitignore`

**Interfaces:**
- Consumes: `is_tracked()` from Task 1.
- Produces: `dev_administration` package tracked in-tree at `dev-administration/dev_administration/`, and its 7 existing test modules become collectable from the repo root.

**Context the implementer needs:** `dev-administration/` is currently a *separate git repository* (33 commits, remote `https://superserver.tailc67a98.ts.net/git/supergoodname77/dev-administration.git`) that is gitignored by Aurora while simultaneously being a Compose build context and a bind mount (`./dev-administration:/app:ro`). Its path does not change — only its tracking status. The `dev-admin` container is currently exited, so moving the directory temporarily is safe.

- [ ] **Step 1: Preserve the live working state before touching anything**

```bash
cd ~/Desktop/tai-review
cp dev-administration/developers.yaml /tmp/developers.yaml.live
sudo cp -a dev-administration /tmp/dev-administration-backup
```

Verify the backup: `ls /tmp/dev-administration-backup/dev_administration/cli.py`

- [ ] **Step 2: Move the source repo aside and clear the ignore rule**

```bash
cd ~/Desktop/tai-review/.worktrees/ephemeral-branching
mv ~/Desktop/tai-review/dev-administration /tmp/dev-administration-src
```

Edit `.gitignore` — delete these two lines:

```
dev-administration/
odysseus/
```

(`odysseus/` goes now too; Task 5 deletes the directory itself.)

- [ ] **Step 3: Import with history preserved**

```bash
cd ~/Desktop/tai-review/.worktrees/ephemeral-branching
git add .gitignore
git commit -m "chore: stop ignoring dev-administration and odysseus"
git subtree add --prefix=dev-administration /tmp/dev-administration-src master
```

Expected: `git log --oneline -- dev-administration | wc -l` reports at least 33.

- [ ] **Step 4: Ignore the Python build artefacts**

Create `dev-administration/.gitignore`:

```
.venv/
.pytest_cache/
__pycache__/
*.egg-info/
```

Then remove any that slipped in:

```bash
cd ~/Desktop/tai-review/.worktrees/ephemeral-branching
git rm -r --cached --ignore-unmatch dev-administration/.venv dev-administration/.pytest_cache
```

- [ ] **Step 5: Restore the directory in the production checkout**

The production checkout is still on `master`, where `dev-administration/` is untracked — but compose
builds and bind-mounts that path, so the directory must physically exist there until this branch
merges. Copy it back:

```bash
cp -a /tmp/dev-administration-src ~/Desktop/tai-review/dev-administration
cp /tmp/developers.yaml.live ~/Desktop/tai-review/dev-administration/developers.yaml
```

**Do not run `git checkout` in `~/Desktop/tai-review`.** It has uncommitted runtime-generated
changes (`Caddyfile`, `Caddyfile.d/agents.conf`, `Caddyfile.d/agents.json`,
`agent-authz/data/owners.json`) that a checkout would destroy.

Verify prod is undisturbed:

```bash
ls ~/Desktop/tai-review/dev-administration/dev_administration/cli.py
docker ps --filter label=com.docker.compose.project=tai-review --format '{{.Names}}\t{{.Status}}'
```

Expected: the file exists, and the same containers are listed as before, all still `Up`.

- [ ] **Step 6: Run the build-context test to verify it now passes**

Run: `cd ~/Desktop/tai-review/.worktrees/ephemeral-branching && .venv/bin/python -m pytest tests/test_repo_conformance.py::test_every_build_context_is_tracked_in_git -v`

Expected: **PASS.**

- [ ] **Step 7: Run the absorbed package's own tests**

Run: `cd ~/Desktop/tai-review/.worktrees/ephemeral-branching && .venv/bin/python -m pytest dev-administration/tests -v`

Expected: all 7 test modules collect and pass. If any fail, they were already failing before absorption — record each failure verbatim in `docs/issues/chunk1-inherited-test-failures.md` and continue. Do not fix them here; that is out of scope for this task.

- [ ] **Step 8: Commit**

```bash
git add -A dev-administration/ .gitignore
git commit -m "feat: absorb dev-administration into the monorepo

It was a gitignored directory that was simultaneously a compose build
context, so a worktree could never build the stack. History preserved
via git subtree (33 commits)."
```

---

## Task 3: Bring AFFiNE in-tree (M3)

**Files:**
- Create: `affine/compose.yml` (moved from `~/.hermes/workspace/tai/affine/compose.yml`)
- Create: `affine/config/config.json` (moved)
- Modify: `compose.yml` — add `include:`
- Modify: `.env.template` — add AFFiNE variables
- Modify: `.gitignore` — ignore `affine/data/` and `.pytest_cache/`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: services `affine`, `affine_migration`, `redis`, `postgres` declared under the `tai-review` project.

**Context the implementer needs:** AFFiNE currently runs as its own compose project named `affine`, rooted at `~/.hermes/workspace/tai/affine/` — a path inside the Hermes container's workspace — while being a hard dependency of the production Caddyfile (`/affine/*`, `/admin/*`, `/graphql`, `/api/auth/*`). Two verified Compose behaviours make this safe: a `name:` in an included file is ignored (the parent project name wins), and relative bind paths in an included file resolve against **that file's own directory**, so `./data/postgres` becomes `<repo>/affine/data/postgres` and correctly follows into a worktree.

Its Postgres holds ~13MB of real data. **Do not delete the data directories.**

- [ ] **Step 1: Write the failing test**

Append to `tests/test_repo_conformance.py`:

Add `from pathlib import Path` to the file’s imports if not already there.

```python
def test_affine_is_declared_in_this_project(config):
    """AFFiNE is a hard dependency of the Caddyfile, so it must be declared
    here rather than living in a compose file outside the repo."""
    assert "affine" in config["services"], (
        "AFFiNE is routed by the Caddyfile but not declared in compose.yml"
    )


def test_affine_state_paths_are_inside_the_repo(config):
    """AFFiNE's bind mounts must resolve inside the repo so a worktree gets
    its own isolated copy rather than sharing production's.

    Both sides are resolved before comparison: docker compose reports the
    source from Go's os.Getwd(), which trusts a stale $PWD, so on this host
    (where /home is a symlink to /var/home) it can report an unresolved path
    while REPO_ROOT is always resolved.
    """
    offending = []
    for name in ("affine", "affine_migration", "postgres"):
        service = config["services"].get(name, {})
        for volume in service.get("volumes", []):
            if volume.get("type") != "bind":
                continue
            source = Path(volume["source"]).resolve()
            if source != REPO_ROOT and REPO_ROOT not in source.parents:
                offending.append((name, str(source)))

    assert offending == [], (
        f"AFFiNE bind mounts resolve outside the repo: {offending}"
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_repo_conformance.py -k affine -v`

Expected: **both FAIL** — `affine` is not in `config["services"]`.

- [ ] **Step 3: Move AFFiNE's files into the repo**

```bash
cd ~/Desktop/tai-review/.worktrees/ephemeral-branching
mkdir -p affine
cp -a ~/.hermes/workspace/tai/affine/compose.yml affine/compose.yml
cp -a ~/.hermes/workspace/tai/affine/config affine/config
```

Do **not** copy `data/` into the worktree — production's live AFFiNE data stays where it is until this branch merges. Chunk 1's acceptance is that the *declaration* is correct.

- [ ] **Step 4: Remove the redundant project name from the included file**

Edit `affine/compose.yml` and delete its first line:

```
name: affine
```

Compose ignores it when included, but leaving it is misleading to a reader.

- [ ] **Step 5: Wire the include**

Edit `compose.yml`. At the very top of the file, above `services:`, add:

```yaml
include:
  - ./affine/compose.yml
```

Also delete the commented-out block at the bottom of `compose.yml`:

```yaml
# include:
#   - ./odysseus/docker-compose.yml
```

- [ ] **Step 6: Add AFFiNE variables to the env template**

Append to `.env.template`:

```bash
# --- AFFiNE (notes / planning workspace) ---
AFFINE_PORT=3010
AFFINE_INDEXER_ENABLED=false
AFFINE_SERVER_EXTERNAL_URL=https://superserver.tailc67a98.ts.net/affine
POSTGRES_USER=affine
POSTGRES_DB=affine
# POSTGRES_PASSWORD — set in .env, never committed
```

Then copy the four live values into the real `.env` so `docker compose config` resolves:

```bash
grep -E '^(AFFINE_|POSTGRES_)' ~/.hermes/workspace/tai/affine/.env >> ~/Desktop/tai-review/.env
grep -E '^(AFFINE_|POSTGRES_)' ~/.hermes/workspace/tai/affine/.env >> .env
```

Also append to the repo-root `.gitignore` — this task is what makes `affine/data/`
a repo-relative path for the first time, and nothing excludes it yet:

```
affine/data/
.pytest_cache/
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_repo_conformance.py -k affine -v`

Expected: **both PASS.**

- [ ] **Step 8: Verify the config resolves without touching running containers**

Run: `docker compose config --quiet && echo OK`

Expected: `OK`, with no errors. This is a parse-only check — it must not start or stop anything. Confirm with `docker ps --format '{{.Names}}'` that `affine_server` is still up under its old project.

- [ ] **Step 9: Commit**

```bash
git add affine/ compose.yml .env.template .gitignore
git commit -m "feat: bring AFFiNE into the monorepo via compose include

AFFiNE was a hard Caddyfile dependency whose compose file lived outside
the repo at ~/.hermes/workspace/tai/affine/. Relative bind paths in an
included file resolve against that file's directory, so affine/data/
follows into a worktree correctly."
```

---

## Task 4: Declare arcadedb (M2, part 1)

**Files:**
- Modify: `compose.yml` — add the `arcadedb` service
- Modify: `.env.template`
- Create: `docs/issues/arcadedb-oom.md`

**Interfaces:**
- Consumes: nothing.
- Produces: service `arcadedb` declared, satisfying part of `test_no_undeclared_containers_in_project`.

**Context the implementer needs:** `tai-core-arcadedb` carries the `tai-review` project label but is declared nowhere. It exited with code **137** four days ago, which is a SIGKILL — most likely the OOM killer, since the image defaults to `ARCADEDB_OPTS_MEMORY=-Xms2G -Xmx2G` on a 15.5GiB host running everything else. It is being kept as a candidate future knowledge graph. Configuration below was reconstructed from `docker inspect`.

- [ ] **Step 1: Add the service declaration**

Add to `compose.yml` under `services:`:

```yaml
  # Candidate knowledge-graph store. Not yet integrated with any service —
  # kept declared so it is code rather than an undeclared survivor.
  # Exited 137 (SIGKILL, most likely OOM) on 2026-07-23. NOTE: JAVA_OPTS below
  # lowers the INITIAL heap (-Xms 2G -> 512m) but NOT the maximum: -Xmx2g is the
  # same value as the image default -Xmx2G, so the OOM ceiling is unchanged.
  # See docs/issues/arcadedb-oom.md before relying on this service.
  arcadedb:
    image: arcadedata/arcadedb:26.7.3
    restart: unless-stopped
    environment:
      - JAVA_OPTS=-Xms512m -Xmx2g
      - ARCADEDB_ROOT_PASSWORD=${ARCADEDB_ROOT_PASSWORD}
    ports:
      - 127.0.0.1:2424:2424
      - 127.0.0.1:2480:2480
    volumes:
      - ./arcadedb:/home/arcadedb/databases
      - arcadedb_backups:/home/arcadedb/backups
      - arcadedb_config:/home/arcadedb/config
      - arcadedb_log:/home/arcadedb/log
      - arcadedb_replication:/home/arcadedb/replication
```

Add to the `volumes:` block at the bottom of `compose.yml`:

```yaml
  arcadedb_backups:
  arcadedb_config:
  arcadedb_log:
  arcadedb_replication:
```

- [ ] **Step 2: Move the root password out of the image env and into .env**

The password is currently baked into the container's environment as `ARCADEDB_ROOT_PASSWORD=shit`. Add to `.env.template`:

```bash
# --- arcadedb (candidate knowledge graph) ---
# ARCADEDB_ROOT_PASSWORD — set in .env, never committed
```

And set a real value in `.env` (both the production `.env` and the worktree's):

```bash
echo 'ARCADEDB_ROOT_PASSWORD=shit' >> ~/Desktop/tai-review/.env
echo 'ARCADEDB_ROOT_PASSWORD=shit' >> .env
```

Keep the existing value for now so nothing breaks; rotating it is listed in `docs/post-implementation-steps.md` (Task 7).

- [ ] **Step 3: Record the OOM as a known issue**

Create `docs/issues/arcadedb-oom.md`:

```markdown
# arcadedb exited 137

`tai-core-arcadedb` exited with code 137 (SIGKILL) on 2026-07-23. The most
likely cause is the OOM killer: the image ships
`ARCADEDB_OPTS_MEMORY=-Xms2G -Xmx2G` and the host has 15.5GiB total with
roughly 7.7GiB free while the rest of the stack runs.

The service declaration sets `JAVA_OPTS=-Xms512m -Xmx2g`, matching what the
container was actually started with — but this only lowers the **initial**
heap (2G -> 512m). The **maximum** heap is unchanged: `-Xmx2g` and the image
default `-Xmx2G` are the same value (Java heap suffixes are case-insensitive).
Since the maximum is what determines OOM risk, not the initial size, this
declaration does **not** reduce the OOM ceiling. Whether `ARCADEDB_OPTS_MEMORY`
or `JAVA_OPTS` wins when both are present is therefore moot for this
question — either way the max heap arrives at the same 2G figure. The actual
cause of the SIGKILL has **not** been confirmed. Before relying on arcadedb
for anything:

1. Start it and watch `docker events --filter event=oom`.
2. If a lower ceiling is desired, `JAVA_OPTS` must actually be lowered (e.g.
   `-Xmx1g`) rather than left at a value equal to the default, and it must be
   confirmed which of `ARCADEDB_OPTS_MEMORY` / `JAVA_OPTS` the image honors
   when both are set.

## Orphaned container and volumes on first start

The exited container is named `tai-core-arcadedb` and was started outside of
this compose project (its four non-bind volumes are anonymous, hash-named
volumes, not the named volumes declared here). Compose has no way to adopt
it: running `docker compose up arcadedb` will create a **new** container
(`tai-review-arcadedb-1`) backed by the **new** named volumes
(`arcadedb_backups`, `arcadedb_config`, `arcadedb_log`,
`arcadedb_replication`) declared in `compose.yml`, rather than reusing the
old container or its anonymous volumes. `tai-core-arcadedb` and its
anonymous volumes become orphans that must be cleaned up manually.

Practical impact is low: the old container's full lifetime was
2026-07-23T04:47:33Z to 2026-07-23T04:48:23Z (~50 seconds) before it was
killed, so little to no data could have accumulated in those volumes.
Still, whoever starts the service should expect to start with **empty**
volumes, not to find any prior state.

Not blocking Chunk 1 — the service is being declared, not started.
```

- [ ] **Step 4: Verify the config parses and arcadedb is declared**

Run: `docker compose config --format json | python -c "import json,sys; print('arcadedb' in json.load(sys.stdin)['services'])"`

Expected: `True`

- [ ] **Step 5: Commit**

```bash
git add compose.yml .env.template docs/issues/arcadedb-oom.md
git commit -m "feat: declare arcadedb in compose

It carried the tai-review project label while being declared nowhere.
Config reconstructed from docker inspect. Exited 137 four days ago;
recorded as a known issue rather than silently restarted."
```

---

## Task 5: Remove the Odysseus stack (M2, part 2)

**Files:**
- Modify: `Caddyfile` — delete the `/chat` handlers
- Modify: `.env.template` — delete Odysseus/searxng variables
- Delete: `odysseus/` directory
- Delete: containers `tai-review-odysseus-1`, `tai-review-chromadb-1`, `tai-review-searxng-1`, `tai-review-ntfy-1`
- Delete: volumes `tai-review_chromadb-data`, `tai-review_searxng-data`, `tai-review_ntfy-cache`

**Interfaces:**
- Consumes: nothing.
- Produces: `test_no_undeclared_containers_in_project` passes.

**Context the implementer needs:** These four containers carry the `tai-review` project label but are declared nowhere, because the `include:` that used to declare them is commented out (deleted in Task 3, Step 5). Verified: nothing in Aurora's own Python, Rust, or Caddy configuration references chromadb, searxng, or ntfy — `notifier.py` only implements stdout and file notifiers. The only Aurora-side reference to Odysseus is the `/chat` redirect in the Caddyfile.

- [ ] **Step 1: Confirm nothing references them before deleting**

```bash
cd ~/Desktop/tai-review/.worktrees/ephemeral-branching
grep -rniE "odysseus|chromadb|searxng|ntfy" \
  --include="*.py" --include="*.rs" --include="*.yml" --include="*.conf" \
  --include="Caddyfile" . | grep -v "^./odysseus/" | grep -v "^./docs/"
```

Expected: only the two `/chat` handler blocks in `Caddyfile`. If anything else appears, stop and report it — the deletion is not safe as planned.

- [ ] **Step 2: Delete the Caddy routes**

Edit `Caddyfile` and delete this entire block:

```
	# Odysseus — no subpath support, served via Tailscale Serve on :7443.
	# ponytail: clean entry point via /chat, browser redirects to Odysseus at root.
	handle /chat/* {
		redir https://{$DOMAIN_NAME}:{$ODYSSEUS_SERVE_PORT}{uri} 302
	}
	handle /chat {
		redir https://{$DOMAIN_NAME}:{$ODYSSEUS_SERVE_PORT}/ 302
	}
```

Also delete the `ODYSSEUS_SERVE_PORT` environment entry from the `caddy` service in `compose.yml`:

```yaml
      - ODYSSEUS_SERVE_PORT=${ODYSSEUS_SERVE_PORT:-7443}
```

- [ ] **Step 3: Validate the Caddyfile before applying it**

```bash
docker run --rm -v "$PWD/Caddyfile:/etc/caddy/Caddyfile:ro" \
  -e DOMAIN_NAME=example.ts.net -e CADDY_BASIC_AUTH_USER=x \
  -e CADDY_BASIC_AUTH_HASH=y -e HERMES_SERVE_PORT=7444 \
  caddy:latest caddy validate --config /etc/caddy/Caddyfile
```

Expected: `Valid configuration`. The `import /etc/caddy/Caddyfile.d/agents.conf` line will fail to resolve in this throwaway container — if that is the only error, it is expected; confirm by checking the error text names only that import.

- [ ] **Step 4: Stop and remove the containers**

```bash
docker stop tai-review-odysseus-1 tai-review-chromadb-1 tai-review-searxng-1 tai-review-ntfy-1
docker rm   tai-review-odysseus-1 tai-review-chromadb-1 tai-review-searxng-1 tai-review-ntfy-1
```

- [ ] **Step 5: Remove their volumes, including the orphaned `tai_*` set**

The `tai_*` volumes are leftovers from a previous project name and belong to nothing:

```bash
docker volume rm \
  tai-review_chromadb-data tai-review_searxng-data tai-review_ntfy-cache \
  tai_caddy_config tai_caddy_data tai_chromadb-data tai_model-cache \
  tai_ntfy-cache tai_searxng-data
```

`tai-review_model-cache` is deliberately **not** removed here — it is still declared in
`compose.yml`, so compose would simply recreate it. Task 6 deletes the declaration and then the
volume, in that order.

Expected: each name echoed on success. If any reports "volume is in use", stop — something still references it and the earlier grep missed it.

- [ ] **Step 6: Delete the source directory**

```bash
rm -rf ~/Desktop/tai-review/odysseus
```

(`odysseus/` was un-ignored in Task 2 Step 2 but never added, so there is nothing to `git rm`.)

- [ ] **Step 7: Remove the dead environment variables**

Delete from `.env.template` and from `~/Desktop/tai-review/.env`:

```
ODYSSEUS_ADMIN_USER, ODYSSEUS_ADMIN_PASSWORD, ODYSSEUS_SERVE_PORT,
SEARXNG_INSTANCE, LLM_HOST
```

Leave `OPENAI_API_KEY` in place — it is not provably Odysseus-only, and removing a live key is not reversible. Note it in `docs/post-implementation-steps.md`.

- [ ] **Step 8: Run the conformance test**

Run: `.venv/bin/python -m pytest tests/test_repo_conformance.py -v`

Expected: **all PASS**, including `test_no_undeclared_containers_in_project`.

- [ ] **Step 9: Verify production is still serving**

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://superserver.tailc67a98.ts.net/git/
curl -sS -o /dev/null -w '%{http_code}\n' https://superserver.tailc67a98.ts.net/affine/
```

Expected: `200` for both. Then reload Caddy with the edited config:

```bash
docker exec tai-review-caddy-1 caddy reload --config /etc/caddy/Caddyfile
curl -sS -o /dev/null -w '%{http_code}\n' https://superserver.tailc67a98.ts.net/git/
```

Expected: `200`. If Caddy fails to reload it keeps serving the old config — check `docker logs tai-review-caddy-1 --tail 20` and fix before committing.

- [ ] **Step 10: Commit**

```bash
git add Caddyfile compose.yml .env.template
git commit -m "feat: remove the Odysseus stack

Odysseus, chromadb, searxng and ntfy carried the tai-review project label
while being declared nowhere. Nothing in Aurora's code referenced them;
the only reference was the /chat redirect in the Caddyfile. Also drops
the orphaned tai_* volume set from a previous project name."
```

---

## Task 6: Delete the dead commented blocks and stale directories (M2, part 3)

**Files:**
- Modify: `compose.yml` — delete ~120 lines of commented-out services
- Modify: `.env.template` — delete Immich/Falkor/tai-db/NFS variables
- Delete: `falkor-tai/`, `postgrespg-tai/`, `postgres/`, `library/`, `shared/`, `nfs-exports.txt`

**Interfaces:**
- Consumes: nothing.
- Produces: no interface; this is pure removal.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_repo_conformance.py`:

```python
def test_compose_has_no_commented_out_services():
    """Commented-out service blocks are dead weight that misleads readers
    about what the stack contains."""
    dead_markers = [
        "immich-server", "immich-machine-learning", "falkordb",
        "tai-db", "erichough/nfs-server",
    ]
    text = (REPO_ROOT / "compose.yml").read_text()
    found = [marker for marker in dead_markers if marker in text]

    assert found == [], (
        f"compose.yml still contains dead service definitions: {found}"
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_repo_conformance.py::test_compose_has_no_commented_out_services -v`

Expected: **FAIL**, listing all five markers.

- [ ] **Step 3: Delete the commented blocks**

In `compose.yml`, delete every commented-out service block: `immich-server`, `immich-machine-learning`, `redis`, `database`, `nfs`, `tai-db`, `falkordb`. Also delete `model-cache:` from the `volumes:` block, since only the deleted Immich ML service used it.

- [ ] **Step 4: Delete the dead environment variables**

Delete from `.env.template` and `~/Desktop/tai-review/.env`:

```
IMMICH_VERSION, UPLOAD_LOCATION, DB_DATA_LOCATION, DB_PASSWORD,
DB_USERNAME, DB_DATABASE_NAME, FALKORDB_PASSWORD,
FALKOR_DB_DATA_LOCATION, TAI_DB_DATA_LOCATION, TAILSCALE_IP
```

Note: `TAILSCALE_IP` was only used by the deleted NFS service. The Hermes service hardcodes `100.86.36.78` rather than using it — leave that hardcoding alone, it is Chunk 2's concern.

- [ ] **Step 5: Remove the now-undeclared model-cache volume**

Only after Step 3 removed its declaration:

```bash
docker volume rm tai-review_model-cache
```

- [ ] **Step 6: Delete the stale directories**

Three of these are root-owned and need sudo:

```bash
cd ~/Desktop/tai-review
rm -rf falkor-tai postgrespg-tai nfs-exports.txt
sudo rm -rf postgres library shared
```

Expected: `ls` shows none of them remaining. If sudo prompts for a password and none is available, stop and hand these three commands to the user rather than skipping them silently.

- [ ] **Step 7: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`

Expected: **all PASS.**

- [ ] **Step 8: Verify compose still resolves and prod still serves**

```bash
docker compose config --quiet && echo CONFIG_OK
curl -sS -o /dev/null -w '%{http_code}\n' https://superserver.tailc67a98.ts.net/git/
```

Expected: `CONFIG_OK` then `200`.

- [ ] **Step 9: Commit**

```bash
git add compose.yml .env.template
git commit -m "chore: delete dead service blocks and stale directories

Removes ~120 lines of commented-out immich/falkordb/tai-db/nfs/redis
definitions, their env vars, and the empty directories they left behind."
```

---

## Task 7: Chunk 1 acceptance — a fresh worktree can build

**Files:**
- Create: `docs/post-implementation-steps.md`
- Create: `docs/implementations/2026-07-27-chunk1-repo-describes-reality.md`
- Create: `tests/test_worktree_buildable.py`

**Interfaces:**
- Consumes: everything above.
- Produces: the acceptance gate for Chunk 1. Chunk 2 may not begin until this passes.

- [ ] **Step 1: Write the acceptance test**

Create `tests/test_worktree_buildable.py`:

```python
"""Chunk 1 acceptance: a throwaway worktree must be able to resolve the
full compose configuration, which is the property that was broken before
dev-administration was absorbed."""

import subprocess
import tempfile
from pathlib import Path

from conftest import REPO_ROOT


def test_fresh_worktree_resolves_compose_config():
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "probe"
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(target), "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        )
        try:
            # The worktree has no .env; supply the production one so this
            # tests structure rather than secret availability.
            subprocess.run(
                ["cp", str(REPO_ROOT / ".env"), str(target / ".env")],
                check=True,
            )
            result = subprocess.run(
                ["docker", "compose", "config", "--quiet"],
                cwd=target, capture_output=True, text=True,
            )
            assert result.returncode == 0, (
                "A fresh worktree cannot resolve compose config:\n"
                f"{result.stderr}"
            )

            # Every build context must physically exist in the worktree.
            for context in ("fjell", "agent-authz", "dev-administration"):
                assert (target / context).is_dir(), (
                    f"Build context {context!r} is missing from a fresh "
                    "worktree — it is still not tracked in git"
                )
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(target)],
                cwd=REPO_ROOT, capture_output=True, text=True,
            )
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python -m pytest tests/test_worktree_buildable.py -v`

Expected: **PASS.** If `dev-administration` is reported missing, Task 2 did not complete — the subtree add failed or the `.gitignore` edit did not take.

- [ ] **Step 3: Write the post-implementation steps doc**

Create `docs/post-implementation-steps.md`:

```markdown
# Post-Implementation Steps

Manual actions that cannot be scripted, or that require a human decision.

## After Chunk 1

1. **Archive the standalone `dev-administration` Forgejo repo.** Its history
   now lives in Aurora under `dev-administration/` via git subtree. Mark the
   standalone repo archived in Forgejo so nobody pushes to a dead remote.

2. **Rotate the Forgejo admin token.** The token is embedded in cleartext in
   three places: `.git/config`'s `origin` URL in both this repo and the old
   dev-administration repo, and in `admin-asks.md`, which is tracked in git.
   Rotate it in Forgejo, then store it via a git credential helper rather
   than in the remote URL.

3. **Decide on `OPENAI_API_KEY`.** It survived the Odysseus removal because
   it is not provably Odysseus-only. Confirm whether anything still uses it
   and remove it from `.env` if not.

4. **Decide on `ARCADEDB_ROOT_PASSWORD`.** Currently the literal value that
   was baked into the running container. Rotate before arcadedb is used for
   anything real.

## After Chunk 3 — register the aurora MCP server

Run inside the Hermes container:

    hermes mcp add aurora --command docker \
      --args run -i --rm -v /var/run/docker.sock:/var/run/docker.sock \
      aurora-cli:local mcp

Verify with `hermes mcp list` — `aurora` should appear with transport
`stdio` and status enabled.

For Claude Code, add to `.mcp.json` at the repo root:

    {
      "mcpServers": {
        "aurora": {
          "command": "docker",
          "args": ["run", "-i", "--rm",
                   "-v", "/var/run/docker.sock:/var/run/docker.sock",
                   "aurora-cli:local", "mcp"]
        }
      }
    }

**To make this reproducible for new developers**, commit the registration
into the `aurora-agent` profile repo that `dev-admin reconcile` installs
into every provisioned Hermes volume, so a newly provisioned developer gets
the `aurora` MCP server without manual setup.
```

- [ ] **Step 4: Write the implementation log**

Create `docs/implementations/2026-07-27-chunk1-repo-describes-reality.md` recording, for each of Tasks 1-7: what changed, what was verified and how, and anything that differed from this plan. Per the practices doc this file is updated on every iteration, not written once.

- [ ] **Step 5: Write the testing doc**

The practices doc requires a Testing markdown per feature. Create
`docs/testing/2026-07-27-chunk1-repo-describes-reality.md` covering:

- **What is tested and why:** each of the five tests in `tests/`, stating the defect it catches —
  `test_every_build_context_is_tracked_in_git` catches the gitignored-build-context class of bug
  that made worktrees unbuildable; `test_no_undeclared_containers_in_project` catches drift between
  compose and reality; `test_affine_*` catch AFFiNE regressing back out of the repo;
  `test_compose_has_no_commented_out_services` catches dead-code reaccumulation;
  `test_fresh_worktree_resolves_compose_config` is the acceptance gate.
- **How to run:** `.venv/bin/python -m pytest tests/ dev-administration/tests -v` from the repo root.
- **What these tests deliberately do NOT cover:** they assert structure, not behaviour. Nothing here
  proves a service actually works — that arrives with the end-to-end suite in Chunk 3.
- **Any inherited failures** recorded from Task 2 Step 7.

- [ ] **Step 6: Full verification sweep**

```bash
.venv/bin/python -m pytest tests/ dev-administration/tests -v
docker compose config --quiet && echo CONFIG_OK
docker ps --filter label=com.docker.compose.project=tai-review --format '{{.Names}}\t{{.Status}}'
curl -sS -o /dev/null -w 'git=%{http_code}\n'    https://superserver.tailc67a98.ts.net/git/
curl -sS -o /dev/null -w 'affine=%{http_code}\n' https://superserver.tailc67a98.ts.net/affine/
curl -sS -o /dev/null -w 'root=%{http_code}\n'   https://superserver.tailc67a98.ts.net/
```

Expected: all tests pass; `CONFIG_OK`; the container list contains no `odysseus`, `chromadb`, `searxng` or `ntfy`; `git` and `affine` return `200`; `root` returns `401` (it is behind basic auth — that is correct, not a failure).

- [ ] **Step 7: Commit**

```bash
git add tests/ docs/
git commit -m "test: chunk 1 acceptance — fresh worktree resolves compose config

Adds the acceptance gate, the post-implementation steps doc, the testing
doc, and the implementation log."
```

---

## Definition of Done

Chunk 1 is complete when all of the following hold:

1. `.venv/bin/python -m pytest tests/ dev-administration/tests` passes.
2. A fresh worktree resolves `docker compose config` and contains all three build contexts.
3. No container carrying the `tai-review` project label is undeclared.
4. Production still serves `/git/` and `/affine/` with `200`.
5. `docs/implementations/2026-07-27-chunk1-repo-describes-reality.md` is current.

**Not in scope, deferred to Chunk 2:** absolute bind mounts (`~/.hermes`, `~/Desktop/tai-review`), the hardcoded `tai-review_default` network and `tai-review-caddy-1` container names, converting dev-agent provisioning from `docker run` to a generated compose fragment, and the hardcoded `100.86.36.78` in the Hermes port binding.
