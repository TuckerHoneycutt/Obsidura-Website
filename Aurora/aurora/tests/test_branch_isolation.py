"""Teardown against real Docker objects, and the invariant that production survived.

These tests bring up genuine `br-` stacks and destroy them. They are the only
place in the suite where `branch_down` touches the daemon, so the production
invariant is asserted BY THE TEST, from a snapshot the test captured itself —
never from the snapshot `branch_down` takes internally.

That distinction is the point. If the invariant were checked only by the code
under test, moving that check earlier would make it vacuous while every test
stayed green — the exact shape of several defects in this project's history
(a skip guard that made a Critical gate inert; a checker that iterated the
constant it validated). The in-code check stays, because it protects real
operators. It is just not allowed to be the only one.
"""

import subprocess
from pathlib import Path

import pytest

from aurora_cli import branch, guards
from branch_harness import (
    assert_production_unchanged,
    branch_projects,
    production_snapshot,
    project_residue,
)

# The fixtures live in branch_harness.py rather than conftest.py, so they must
# be imported into every module that uses them — pytest only auto-discovers
# fixtures in conftest. Same pattern as tests/test_branch_harness.py.
from branch_harness import throwaway_branch, throwaway_branches  # noqa: F401


@pytest.fixture(autouse=True)
def _unrelated_branches_must_survive():
    """A branch this module did not create must still be there afterwards.

    A detector, not a skip guard. The docstring at the top of this file is
    about gates that make themselves inert; refusing to run whenever a human
    has a branch up would be exactly that. So instead: snapshot the `br-*`
    projects that existed before, and fail loudly if any of them stopped
    existing. Silent collateral damage becomes a red test naming the branch
    it destroyed.
    """
    before = set(branch_projects())
    yield
    after = set(branch_projects())
    lost = before - after
    assert not lost, (
        f"this test destroyed branches it did not create: {sorted(lost)}. "
        "A teardown here must be scoped to the projects the test made."
    )


COMPOSE = """\
services:
  keeper:
    image: alpine
    command: sleep 300
    volumes:
      - data:/data
  # Profiled ON PURPOSE. `docker compose down` only considers profiles it is
  # told about, and every developer agent is profiled — so without
  # `--profile '*'` a real teardown leaves every agent behind. A probe stack
  # with no profiled service cannot detect that, and the mutation that drops
  # the flag would survive.
  gated:
    image: alpine
    command: sleep 300
    profiles: ["extra"]
volumes:
  data:
"""


def _up(project: str, tmp_path) -> None:
    (tmp_path / "compose.yml").write_text(COMPOSE)
    subprocess.run(
        ["docker", "compose", "-p", project, "--profile", "*", "up", "-d"],
        cwd=tmp_path, check=True, capture_output=True, stdin=subprocess.DEVNULL,
    )


def _counts(project: str) -> dict[str, int]:
    residue = project_residue(project)
    return {k: len(v) for k, v in residue.items()}


def test_teardown_removes_everything_it_created(throwaway_branch, tmp_path):
    project = throwaway_branch
    before = production_snapshot()

    _up(project, tmp_path)
    started = _counts(project)
    assert started["containers"] >= 2, (
        f"probe did not start both services: {started}. A profiled service "
        "must exist or the --profile '*' mutation cannot be detected."
    )
    assert started["volumes"] >= 1, f"probe created no volume: {started}"

    name = project[len(guards.BRANCH_PROJECT_PREFIX):]
    result = branch.branch_down(name, runner=branch.CommandRunner())

    after = _counts(project)
    assert after == {"containers": 0, "volumes": 0, "networks": 0}, (
        f"teardown left residue: {after}. notes={result.notes}"
    )
    # Asserted by the test, from the test's own snapshot.
    assert_production_unchanged(before)


def test_teardown_with_a_missing_worktree_still_reclaims(throwaway_branch, tmp_path):
    """N7: the worktree may be gone — removed by hand, or `up` died early.

    `docker compose -p X down` then has no compose file to read, while the
    containers and volumes still exist and still cost disk. The label-driven
    fallback is what reclaims them, and it is the path that manipulates
    objects BY NAME, so it is the one most able to do damage.
    """
    project = throwaway_branch
    before = production_snapshot()

    _up(project, tmp_path)
    assert _counts(project)["containers"] >= 2

    name = project[len(guards.BRANCH_PROJECT_PREFIX):]
    result = branch.branch_down(name, runner=branch.CommandRunner())

    assert result.used_fallback, (
        "no worktree exists for this probe project, so the compose path "
        "cannot have run — fallback should have been used"
    )
    assert _counts(project) == {"containers": 0, "volumes": 0, "networks": 0}
    assert_production_unchanged(before)


def test_a_branch_named_volume_with_no_label_is_still_reclaimed(
    throwaway_branch, tmp_path
):
    """The Tasks 5-7 review measured this one as unremovable by anything.

    A volume NAMED `br-x_data` but carrying no project label: the guard could
    not read a label, the label sweep could not see it, and every compose
    route failed — including after Compose adopted it, which adds no labels.
    Worse, residue reporting called it clean, so a teardown assertion PASSED
    over an object it could not remove.
    """
    project = throwaway_branch
    before = production_snapshot()
    orphan = f"{project}_orphan"
    subprocess.run(["docker", "volume", "create", orphan],
                   check=True, capture_output=True)
    try:
        assert orphan in subprocess.run(
            ["docker", "volume", "ls", "-q"],
            check=True, capture_output=True, text=True,
        ).stdout.split()

        name = project[len(guards.BRANCH_PROJECT_PREFIX):]
        branch.branch_down(name, runner=branch.CommandRunner())

        remaining = subprocess.run(
            ["docker", "volume", "ls", "-q"],
            check=True, capture_output=True, text=True,
        ).stdout.split()
        assert orphan not in remaining, (
            f"{orphan} survived teardown; it carries no project label, so only "
            "the name-based sweep can reclaim it"
        )
    finally:
        subprocess.run(["docker", "volume", "rm", "-f", orphan],
                       capture_output=True)
    assert_production_unchanged(before)


def test_down_all_is_derived_from_the_daemon(throwaway_branches, tmp_path):
    """`--all` must find a branch whose worktree someone deleted by hand.

    Derived from the daemon, never from an index file — an index cannot know
    about a branch it was never told about, which is precisely the case
    `--all` exists to clean up. Two projects, so the assertion is not over a
    set of one, and never over an empty set (trap 2).
    """
    first, second = throwaway_branches(), throwaway_branches()
    before = production_snapshot()

    for project in (first, second):
        d = tmp_path / project
        d.mkdir()
        _up(project, d)

    live = branch_projects()
    assert {first, second} <= live, f"probes not visible on the daemon: {live}"

    # Derived from the daemon -- and then INTERSECTED with what this test
    # created. `branch_down_all()` with no `projects` targets every `br-*`
    # project on the box, which on a developer's machine includes the branch
    # they are using. On 2026-07-31 this line destroyed a live branch mid-
    # session: the suite was run while `br-hubdev` was up, and the next
    # command restarted only the services it named, which left a five-
    # container stack whose tailscale sidecar re-registered under a new name
    # and wedged the branch. The test asserted production was unchanged and
    # was, so nothing went red.
    #
    # The property under test is that the list comes FROM THE DAEMON, not
    # from an index. Asserting the derivation contains the probes proves
    # exactly that, without the collateral.
    derived = set(branch.live_branch_projects(branch.CommandRunner()))
    assert {first, second} <= derived, (
        f"`--all` derives from the daemon but did not see the probes: {derived}"
    )
    results = branch.branch_down_all(
        projects=sorted(derived & {first, second}), runner=branch.CommandRunner(),
    )
    torn = {r.project for r in results}
    assert {first, second} <= torn, f"--all missed a live branch: {torn}"

    for project in (first, second):
        assert _counts(project) == {"containers": 0, "volumes": 0, "networks": 0}
    assert_production_unchanged(before)


def test_the_compose_path_runs_when_a_worktree_exists(throwaway_branch, tmp_path, monkeypatch):
    """Exercises the COMPOSE path, which the tests above never reach.

    Both tests above use projects with no worktree, so `compose_ok` is False
    and the fallback does all the work — meaning the compose invocation's
    flags were never executed by anything. Mutations dropping `--profile '*'`
    and `-v` both SURVIVED the first mutation run for exactly that reason.
    That is the vacuous-pass trap wearing a code-path costume: the assertions
    were real, they just measured the other branch of an `if`.

    production_root is redirected at a tmp directory so a genuine
    `<root>/.worktrees/<name>` exists and satisfies the path guard, without
    creating anything inside production's real tree.
    """
    project = throwaway_branch
    name = project[len(guards.BRANCH_PROJECT_PREFIX):]
    before = production_snapshot()

    fake_root = tmp_path / "prod"
    worktree = fake_root / ".worktrees" / name
    worktree.mkdir(parents=True)
    (worktree / "compose.yml").write_text(COMPOSE)
    # branch_paths resolves the branch domain through production's .env, so the
    # redirected root needs one. Strict KEY=value, per trap 7.
    (fake_root / ".env").write_text("DOMAIN_NAME=example.invalid\n")
    monkeypatch.setattr("aurora_cli.identity.production_root", lambda: fake_root)

    _up(project, worktree)
    started = _counts(project)
    assert started["containers"] >= 2, f"probe did not start both services: {started}"
    assert started["volumes"] >= 1, f"probe created no volume: {started}"

    result = branch.branch_down(name, runner=branch.CommandRunner())

    assert not result.used_fallback, (
        "a worktree with a compose.yml exists, so the compose path should "
        f"have carried the teardown. notes={result.notes}"
    )
    assert _counts(project) == {"containers": 0, "volumes": 0, "networks": 0}, (
        f"compose path left residue: {_counts(project)} notes={result.notes}"
    )
    assert_production_unchanged(before)


def test_the_path_guard_refuses_a_worktree_outside_the_branch_directory(monkeypatch):
    """A VALID `br-` project pointed at an invalid path must still refuse.

    The project guard fires first for every input the other tests use, so
    skipping the path guard entirely survived the first mutation run. This
    supplies a good project and a bad path, which is the only shape that can
    reach the second guard.
    """
    from aurora_cli import identity as ident

    bad = Path("/tmp/not-a-branch-worktree")
    monkeypatch.setattr(
        ident, "branch_paths",
        lambda n: ident.BranchPaths(
            name=n, project=f"br-{n}", hostname="h", domain="d",
            worktree=bad, env_file=bad / ".env", access_doc=bad / "A.md",
        ),
    )

    class Exploding(branch.CommandRunner):
        def run(self, argv, **kwargs):  # pragma: no cover - must not run
            raise AssertionError(f"guard let a command through: {list(argv)!r}")

    with pytest.raises(guards.GuardViolation) as excinfo:
        branch.branch_down("x", runner=Exploding())
    assert "not inside" in str(excinfo.value)
