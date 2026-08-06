"""Branch-stack test harness: the single implementation of "production was
not disturbed", plus throwaway `br-*` compose projects that cannot reach it.

Chunk 3 is the first chunk whose tests start and stop real containers, against
a daemon that is simultaneously serving a live production stack. Two properties
have to hold before that is safe, and both are implemented here and NOWHERE
ELSE:

1.  "Production was not disturbed" is a *measured* fact with exactly one
    implementation. Chunk 2 shipped two functions that each ran their own
    "identical" docker query (`project_services` / `find_service_container`);
    they drifted apart twice. No later task may reimplement
    `production_snapshot` / `assert_production_unchanged` — import them.

2.  A test that brings a branch stack up must be structurally unable to bring
    production down, even when its own arguments are wrong. Every destructive
    call in this module goes through `assert_not_production` first, and that
    function refuses anything that is not in the `br-` namespace — it does not
    merely refuse production's current name, because production's name is
    changing (Chunk 2's rename is blocked, not cancelled) and a check written
    against one of the two names is wrong in the other world.

Nothing here uses `pytest.skip`. Chunk 2 shipped a skip guard that made a
Critical-severity gate inert at every invocation and nobody noticed, because a
skip is not a failure. An environment this module cannot verify is a failure.
"""

from __future__ import annotations

import itertools
import json
import os
import subprocess
import tempfile

import pytest

import conftest

# Every compose project this harness is allowed to create or destroy lives
# under this prefix. `assert_not_production` is the only gate, so the prefix is
# the whole safety property.
BRANCH_PREFIX = "br-"

PROJECT_LABEL = "com.docker.compose.project"

# Files under production's state tree that legitimately change while a
# read-only seed runs, and therefore cannot participate in a "the seed did not
# mutate production" comparison (finding N6).
#
# Measured while planning, 2026-07-29: a read-only `VACUUM INTO` against
# production's live `.hermes/state.db` (47 MB, 0.05 s) left `state.db` and
# `state.db-wal` byte-identical and *rewrote* `state.db-shm`. `-shm` is the
# mmap'd WAL index, not content, so a whole-tree checksum comparison would go
# red against a correct implementation. `.lock`, `.pid` and `.log` are excluded
# for the same class of reason: production is live and writes them on its own
# schedule, so including them makes the invariant flaky in one direction while
# telling you nothing in the other.
#
# Consumed by Task 5's seeding invariant. Defined here so there is one list.
PROD_VOLATILE_SUFFIXES = ("-shm", ".lock", ".pid", ".log")

_throwaway_counter = itertools.count(1)


# --------------------------------------------------------------------------
# production identity
# --------------------------------------------------------------------------


def production_project() -> str:
    """Production's compose project label, read from conftest at CALL time.

    Deliberately NOT `from conftest import PRODUCTION_PROJECT`: a module-level
    copy is a second source of truth that drifts, and it cannot be
    monkeypatched in one place. Tests monkeypatch `conftest.PRODUCTION_PROJECT`
    and every function here sees it.
    """
    return conftest.PRODUCTION_PROJECT


def assert_not_production(project: str) -> None:
    """Refuse any compose project that is not a branch project.

    This is the guard in front of every destructive operation in Chunk 3.
    It is deliberately a whitelist (`br-` prefix), not a blacklist of
    production's name. Production carries one label today and a different one
    after the Chunk 2 rename lands, and a blacklist written against either one
    is wrong in the other world. The prefix rule is correct in both, and it is
    why this module names neither project literally.
    """
    if not isinstance(project, str):
        raise AssertionError(
            f"Refusing to operate on a non-string compose project: {project!r}"
        )
    if not project:
        raise AssertionError(
            "Refusing to operate on an empty compose project name: an empty "
            "`-p` makes docker compose fall back to the working directory's "
            "basename, which in a worktree can resolve to production."
        )
    prod = production_project()
    if project == prod:
        raise AssertionError(
            f"Refusing to operate on compose project {project!r}: that is "
            f"PRODUCTION (AURORA_PROJECT={prod!r}). Production is a live "
            "stack serving a real user."
        )
    if not project.startswith(BRANCH_PREFIX):
        raise AssertionError(
            f"Refusing to operate on compose project {project!r}: every "
            f"project this harness may create or destroy must start with "
            f"{BRANCH_PREFIX!r}. A name outside that namespace is either "
            "production under one of its two names (the pre-rename label or "
            "the post-rename one) or something else that does not belong to "
            "this test run."
        )


# --------------------------------------------------------------------------
# docker plumbing
# --------------------------------------------------------------------------


def _hard_branch_guard(project: str) -> str:
    """Second, INDEPENDENT gate in front of every destructive docker call.

    This deliberately duplicates the `br-` rule from `assert_not_production`,
    and the duplication is the point. Everything else in this module obeys
    "one implementation, no drift" — but that rule exists to stop two
    *measurements* disagreeing, and this is not a measurement, it is the last
    thing standing between a wrong argument and an irreversible
    `docker compose down -v` against a live production stack.

    Measured, 2026-07-29, with `docker compose --dry-run` against production's
    own project label, from an empty directory with no compose file present:

        docker compose --dry-run --profile '*' -p <production> down -v --remove-orphans
        -> " Container <each> Stopping / Stopped / Removing / Removed "
           for all twelve of production's containers

    i.e. a single wrong project name is a total production outage, and it
    needs no compose file to do it. A one-line mutation to `assert_not_production`
    is therefore a one-line mutation away from that outcome. Two independent
    gates mean no single edit opens the path.
    """
    if not isinstance(project, str) or not project.startswith(BRANCH_PREFIX) \
            or len(project) <= len(BRANCH_PREFIX):
        raise AssertionError(
            f"HARD GUARD: refusing a destructive docker operation on compose "
            f"project {project!r}. Only projects under the {BRANCH_PREFIX!r} "
            "namespace may be destroyed. This guard is independent of "
            "assert_not_production() on purpose."
        )
    return project


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=check
    )


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _inspect_many(names: list[str]) -> list[dict]:
    """One `docker inspect` for many containers.

    conftest.inspect_container() is the single-container form and is used by
    the tests that pin this module; batching here is purely so that a snapshot
    costs one subprocess instead of twelve. Same command, same output shape.
    """
    if not names:
        return []
    return json.loads(_docker("inspect", *names).stdout)


def _project_volumes(project: str) -> list[str]:
    return sorted(
        _lines(_docker("volume", "ls", "-q", "--filter",
                       f"label={PROJECT_LABEL}={project}").stdout)
    )


def _project_networks(project: str) -> list[str]:
    return sorted(
        _lines(_docker("network", "ls", "-q", "--filter",
                       f"label={PROJECT_LABEL}={project}").stdout)
    )


def _project_container_ids(project: str) -> list[str]:
    return sorted(
        _lines(_docker("ps", "-a", "-q", "--filter",
                       f"label={PROJECT_LABEL}={project}").stdout)
    )


def _all_volumes() -> list[str]:
    return sorted(_lines(_docker("volume", "ls", "-q").stdout))


def _all_networks() -> list[str]:
    return sorted(_lines(_docker("network", "ls", "-q").stdout))


# --------------------------------------------------------------------------
# the production-unchanged invariant
# --------------------------------------------------------------------------


def _snapshot(project: str, *, require_containers: bool) -> dict:
    services = conftest.project_containers(project)
    containers: dict[str, dict[str, str]] = {}
    names = sorted(services.values())
    by_name = {}
    for detail in _inspect_many(names):
        by_name[detail["Name"].lstrip("/")] = detail
    for service, name in sorted(services.items()):
        detail = by_name.get(name, {})
        containers[service] = {
            "name": name,
            # The ID, not the name. A `docker compose up` that recreates a
            # container keeps its name and mints a new ID, and a silent
            # recreate of a production container is precisely the event this
            # snapshot exists to catch. Comparing names would call that
            # "unchanged".
            "id": detail.get("Id", ""),
            "started_at": detail.get("State", {}).get("StartedAt", ""),
        }

    if require_containers:
        assert containers, (
            f"production_snapshot() found no containers for compose project "
            f"{project!r}, and refuses to snapshot an empty production. An "
            "empty set makes every later 'production was not disturbed' "
            "assertion vacuously true — that is trap 2, and it is how Chunk 1 "
            "shipped a conformance gate that tested nothing. Set "
            "AURORA_PROJECT to the project label the DEPLOYED containers "
            "actually carry, which is the pre-rename label until Chunk 2's "
            "rename is deployed and the post-rename one afterwards. Read it "
            "off the daemon with: docker ps -a --format "
            "'{{.Label \"com.docker.compose.project\"}}' | sort -u"
        )

    return {
        "project": project,
        "containers": containers,
        "volumes": _project_volumes(project),
        "networks": _project_networks(project),
        # Daemon-wide lists. Compared for DISAPPEARANCE only: a branch stack
        # legitimately adds volumes and networks while it is up, but nothing a
        # branch does may ever remove one that already existed — including
        # volumes that carry no compose project label at all, which the
        # project-scoped lists above cannot see.
        "all_volumes": _all_volumes(),
        "all_networks": _all_networks(),
    }


def production_snapshot(project: str | None = None) -> dict:
    """Capture production's observable state: container IDs, start times,
    volumes and networks.

    Raises AssertionError if the project has no containers (trap 2).
    """
    project = project if project is not None else production_project()
    return _snapshot(project, require_containers=True)


def assert_production_unchanged(before: dict) -> None:
    """Re-snapshot production and raise AssertionError naming the exact object
    that changed.

    The single implementation. Every later Chunk 3 task that needs to prove it
    did not disturb production calls this; none of them may write their own.
    """
    project = before["project"]
    after = _snapshot(project, require_containers=False)

    problems: list[str] = []

    before_c = before["containers"]
    after_c = after["containers"]

    for service in sorted(set(before_c) - set(after_c)):
        problems.append(
            f"container for service {service!r} "
            f"({before_c[service]['name']!r}, id "
            f"{before_c[service]['id'][:12]}) DISAPPEARED from project "
            f"{project!r}"
        )
    for service in sorted(set(after_c) - set(before_c)):
        problems.append(
            f"container for service {service!r} "
            f"({after_c[service]['name']!r}) APPEARED in project {project!r} "
            "— production gained a container it did not have"
        )
    for service in sorted(set(before_c) & set(after_c)):
        was, now = before_c[service], after_c[service]
        if was["id"] != now["id"]:
            problems.append(
                f"container for service {service!r} was RECREATED: id "
                f"{was['id'][:12]} -> {now['id'][:12]} (the name "
                f"{was['name']!r} is unchanged, which is exactly why this "
                "compares IDs)"
            )
        elif was["started_at"] != now["started_at"]:
            problems.append(
                f"container for service {service!r} ({was['name']!r}) was "
                f"RESTARTED: StartedAt {was['started_at']} -> "
                f"{now['started_at']}"
            )

    for kind in ("volumes", "networks"):
        gone = sorted(set(before[kind]) - set(after[kind]))
        new = sorted(set(after[kind]) - set(before[kind]))
        for item in gone:
            problems.append(
                f"{kind[:-1]} {item!r} labelled for project {project!r} was "
                "REMOVED"
            )
        for item in new:
            problems.append(
                f"{kind[:-1]} {item!r} APPEARED in project {project!r}"
            )

    for kind in ("all_volumes", "all_networks"):
        gone = sorted(set(before[kind]) - set(after[kind]))
        for item in gone:
            problems.append(
                f"{kind.replace('all_', '')[:-1]} {item!r} was REMOVED from "
                "the daemon (it carries no production project label, but it "
                "existed before and does not now)"
            )

    if problems:
        raise AssertionError(
            f"PRODUCTION WAS DISTURBED (compose project {project!r}). "
            + str(len(problems))
            + " change(s):\n  - "
            + "\n  - ".join(problems)
        )


# --------------------------------------------------------------------------
# branch projects
# --------------------------------------------------------------------------


def branch_projects() -> set[str]:
    """Every compose project on the daemon whose name starts with `br-`.

    Unions containers, volumes and networks: a half-torn-down branch can leave
    a volume behind with no container, and a residue check that only looked at
    containers would call that clean (finding N7).
    """
    found: set[str] = set()
    queries = (
        ("ps", "-a", "--format", '{{.Label "com.docker.compose.project"}}'),
        ("volume", "ls", "--format", '{{.Label "com.docker.compose.project"}}'),
        ("network", "ls", "--format", '{{.Label "com.docker.compose.project"}}'),
    )
    for query in queries:
        for name in _lines(_docker(*query).stdout):
            if name.startswith(BRANCH_PREFIX):
                found.add(name)
    return found


def project_residue(project: str) -> dict[str, list[str]]:
    """Everything on the daemon still carrying `project`'s compose label."""
    return {
        "containers": _project_container_ids(project),
        "volumes": _project_volumes(project),
        "networks": _project_networks(project),
    }


def teardown_branch_project(project: str) -> None:
    """Destroy a branch project completely, and prove it.

    Two paths, both behind the same guard (finding N7): the compose path, which
    needs nothing but the project name because compose resolves a project from
    container labels when no compose file is present; and a label-driven sweep,
    which is what actually guarantees completeness.

    The sweep is not belt-and-braces. Measured on Compose v5.3.1, 2026-07-29: a
    container carrying `com.docker.compose.project=<p>` but no
    `com.docker.compose.service` label SURVIVES
    `docker compose -p <p> down -v --remove-orphans`. That is the shape of
    residue a half-finished `up`, or any container created outside compose,
    leaves behind — and the sweep is the only thing that removes it.

    Idempotent: safe to call on a project that is already gone, and safe to
    call twice.
    """
    assert_not_production(project)
    _hard_branch_guard(project)

    with tempfile.TemporaryDirectory(prefix="branch-teardown-") as workdir:
        subprocess.run(
            [
                "docker", "compose",
                # Retained deliberately even though it is provably inert for
                # `down` on Compose v5.3.1 (measured 2026-07-29: `down`
                # resolves the project from container labels and removes
                # profiled services with or without this flag). Trap 3 was
                # recorded against an earlier compose; if a future version
                # re-narrows `down` to active profiles, this flag is what keeps
                # every agent container from surviving teardown. The *guarantee*
                # of no profiled residue comes from the sweep and the residue
                # assertion below, not from this flag.
                "--profile", "*",
                "-p", _hard_branch_guard(project),
                "down", "-v", "--remove-orphans",
            ],
            cwd=workdir,
            capture_output=True,
            text=True,
            check=False,
        )

    residue = project_residue(_hard_branch_guard(project))
    for container in residue["containers"]:
        _hard_branch_guard(project)
        _docker("rm", "-f", container, check=False)
    for volume in residue["volumes"]:
        _hard_branch_guard(project)
        _docker("volume", "rm", "-f", volume, check=False)
    for network in residue["networks"]:
        _hard_branch_guard(project)
        _docker("network", "rm", network, check=False)

    left = project_residue(project)
    if any(left.values()):
        raise AssertionError(
            f"Teardown of branch project {project!r} left residue behind: "
            f"{left!r}. Anything still carrying this project's label costs "
            "disk and can be adopted by a later `up` (trap 6)."
        )


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def throwaway_branches(request):
    """A factory for as many throwaway `br-` compose projects as a test needs.

    Each call yields a unique `br-pytest-<pid>-<n>`. On teardown every project
    handed out is destroyed completely (compose path + label sweep + residue
    assertion) and production is then asserted byte-for-byte the stack it was
    before the test ran.

    A factory rather than one more single-project fixture because volume
    seeding has a SOURCE project and a DESTINATION project which must differ --
    otherwise the copy reads what it writes -- and a second fixture with a
    copy-pasted body is exactly the drift this module exists to prevent.
    `throwaway_branch` is this factory, called once.

    Teardown failures are AssertionErrors, not skips or warnings: a test that
    leaves a branch stack running, or that disturbs production, must be red.
    """
    before = production_snapshot()
    handed_out: list[str] = []

    def make() -> str:
        project = (
            f"{BRANCH_PREFIX}pytest-{os.getpid()}-{next(_throwaway_counter)}"
        )
        assert_not_production(project)
        # If a previous run died mid-test, start from a clean slate rather than
        # adopting its containers or volumes (trap 6).
        teardown_branch_project(project)
        handed_out.append(project)
        return project

    try:
        yield make
    finally:
        failures: list[str] = []
        for project in handed_out:
            try:
                teardown_branch_project(project)
            except AssertionError as exc:      # keep tearing the rest down
                failures.append(str(exc))
        assert_production_unchanged(before)
        assert not failures, (
            "throwaway project teardown left residue:\n" + "\n".join(failures)
        )


@pytest.fixture
def throwaway_branch(throwaway_branches):
    """One unique, guaranteed-non-production compose project name."""
    return throwaway_branches()
