"""Tests for the branch-stack harness itself.

This module does NOT test the stack. It tests `tests/branch_harness.py`, by
feeding `assert_production_unchanged` snapshots that have been doctored to
describe a production that was disturbed, and requiring it to raise.

The reason is specific. Chunk 2 shipped a `pytest.skip` guard that made a
Critical-severity gate inert at every invocation the plan contained, and nobody
noticed, because a skip is not a failure. A safety check nobody has ever seen
fail is indistinguishable from a safety check that cannot fail. Every assertion
in `branch_harness` therefore has a test here that proves it fires, and the
plan's Step 4 mutation table proves each of those tests can go red.

Nothing here mutates production. The doctoring happens to a *copy* of a
snapshot dict, in memory.
"""

from __future__ import annotations

import copy
import json
import subprocess
import textwrap

import pytest

import branch_harness as bh
import conftest

# `throwaway_branch` lives in branch_harness.py, not in conftest.py, so pytest
# does not collect it automatically. Importing the fixture function into a test
# module registers it for that module — the standard idiom for a shared fixture
# that is not in a conftest. Every later Chunk 3 test module that needs a
# throwaway branch project does this same import rather than defining its own
# fixture; there is one implementation.
#
# `throwaway_branches` (the factory `throwaway_branch` is one call of) must
# be imported too: pytest resolves a fixture's own dependencies by name in
# the module that requested it, so importing only the wrapper leaves it
# unresolvable.
from branch_harness import throwaway_branch, throwaway_branches  # noqa: F401


# --------------------------------------------------------------------------
# production_snapshot
# --------------------------------------------------------------------------


def test_snapshot_refuses_an_empty_production(monkeypatch):
    """Trap 2: a gate that queries a project with no containers passes on an
    empty set. `production_snapshot` must refuse to produce such a snapshot at
    all, so that no later assertion can be built on one."""
    monkeypatch.setattr(
        conftest, "PRODUCTION_PROJECT", "br-nonexistent-project-for-this-test"
    )

    with pytest.raises(AssertionError) as excinfo:
        bh.production_snapshot()

    message = str(excinfo.value)
    assert "AURORA_PROJECT" in message, (
        "The refusal must name AURORA_PROJECT: an empty production is almost "
        "always a missing AURORA_PROJECT, and a message that does not say so "
        "sends the reader hunting for a broken stack. Got: " + message
    )


def test_snapshot_is_not_vacuous():
    """The snapshot must actually describe the live stack."""
    snapshot = bh.production_snapshot()
    assert snapshot["containers"], "empty container map"
    assert snapshot["volumes"], "production has no labelled volumes?"
    assert snapshot["networks"], "production has no labelled networks?"
    for service, detail in snapshot["containers"].items():
        assert detail["id"], f"no container id captured for {service!r}"
        assert detail["started_at"], f"no StartedAt captured for {service!r}"


def test_assert_unchanged_passes_on_an_undisturbed_production():
    """The control case. Without this, every `raises` test below is satisfied
    by an implementation that raises unconditionally."""
    before = bh.production_snapshot()
    bh.assert_production_unchanged(before)


# --------------------------------------------------------------------------
# assert_production_unchanged
# --------------------------------------------------------------------------


def test_assert_unchanged_detects_a_removed_container():
    before = bh.production_snapshot()
    doctored = copy.deepcopy(before)
    doctored["containers"]["a-service-that-was-torn-down"] = {
        "name": "some-production-container",
        "id": "0" * 64,
        "started_at": "2026-07-29T00:00:00.000000000Z",
    }

    with pytest.raises(AssertionError) as excinfo:
        bh.assert_production_unchanged(doctored)
    assert "a-service-that-was-torn-down" in str(excinfo.value)
    assert "DISAPPEARED" in str(excinfo.value)


def test_assert_unchanged_detects_an_unexpected_new_container():
    """The other direction: reality has a container the snapshot did not."""
    before = bh.production_snapshot()
    doctored = copy.deepcopy(before)
    victim = sorted(doctored["containers"])[0]
    del doctored["containers"][victim]

    with pytest.raises(AssertionError) as excinfo:
        bh.assert_production_unchanged(doctored)
    assert victim in str(excinfo.value)
    assert "APPEARED" in str(excinfo.value)


def test_assert_unchanged_detects_a_recreated_container():
    """A recreate keeps the container NAME and mints a new ID. A snapshot that
    recorded names would call that unchanged, so this test first proves the
    snapshot records real container IDs, then proves a changed ID is caught."""
    before = bh.production_snapshot()
    victim = sorted(before["containers"])[0]
    recorded = before["containers"][victim]

    truth = conftest.inspect_container(recorded["name"])
    assert recorded["id"] == truth["Id"], (
        f"snapshot recorded {recorded['id']!r} for service {victim!r}, but "
        f"the container's real Id is {truth['Id']!r}. The snapshot must hold "
        "container IDs; a recreate preserves the name and changes only the ID."
    )
    assert len(recorded["id"]) == 64 and recorded["id"] != recorded["name"], (
        f"snapshot identity for {victim!r} is {recorded['id']!r}, which is "
        "not a 64-hex container ID. Comparing container names cannot detect a "
        "recreate."
    )

    doctored = copy.deepcopy(before)
    doctored["containers"][victim]["id"] = "f" * 64

    with pytest.raises(AssertionError) as excinfo:
        bh.assert_production_unchanged(doctored)
    assert victim in str(excinfo.value)
    assert "RECREATED" in str(excinfo.value)


def test_assert_unchanged_detects_a_restarted_container():
    """Same ID, different StartedAt — a `docker restart` or a crash-loop."""
    before = bh.production_snapshot()
    victim = sorted(before["containers"])[0]
    doctored = copy.deepcopy(before)
    doctored["containers"][victim]["started_at"] = "1999-01-01T00:00:00Z"

    with pytest.raises(AssertionError) as excinfo:
        bh.assert_production_unchanged(doctored)
    assert victim in str(excinfo.value)
    assert "RESTARTED" in str(excinfo.value)


def test_assert_unchanged_detects_a_removed_volume():
    before = bh.production_snapshot()
    doctored = copy.deepcopy(before)
    doctored["volumes"] = sorted(
        doctored["volumes"] + ["a-production-volume-that-was-deleted"]
    )

    with pytest.raises(AssertionError) as excinfo:
        bh.assert_production_unchanged(doctored)
    assert "a-production-volume-that-was-deleted" in str(excinfo.value)
    assert "REMOVED" in str(excinfo.value)


def test_assert_unchanged_detects_a_removed_network():
    before = bh.production_snapshot()
    doctored = copy.deepcopy(before)
    doctored["networks"] = sorted(
        doctored["networks"] + ["a-production-network-that-was-deleted"]
    )

    with pytest.raises(AssertionError) as excinfo:
        bh.assert_production_unchanged(doctored)
    assert "a-production-network-that-was-deleted" in str(excinfo.value)
    assert "REMOVED" in str(excinfo.value)


def test_assert_unchanged_detects_an_unlabelled_volume_deletion():
    """Production's volumes all carry a compose project label today, but a
    teardown that reached too far could delete one that does not. The
    daemon-wide list catches that; the project-scoped list cannot."""
    before = bh.production_snapshot()
    doctored = copy.deepcopy(before)
    doctored["all_volumes"] = sorted(
        doctored["all_volumes"] + ["an-unlabelled-volume-that-was-deleted"]
    )

    with pytest.raises(AssertionError) as excinfo:
        bh.assert_production_unchanged(doctored)
    assert "an-unlabelled-volume-that-was-deleted" in str(excinfo.value)


# --------------------------------------------------------------------------
# assert_not_production
# --------------------------------------------------------------------------


def test_assert_not_production_refuses_production_and_bare_names():
    """Both production names appear here on purpose. Production is
    `tai-review` today and `aurora` once the Chunk 2 rename is deployed; a
    guard written against one of them is wrong in the other world, so the rule
    is a `br-` whitelist and BOTH names must be refused under either setting of
    AURORA_PROJECT."""
    refused = [
        conftest.PRODUCTION_PROJECT,
        "",
        "aurora",
        "tai-review",
        "notbr-x",
    ]
    for project in refused:
        with pytest.raises(AssertionError):
            bh.assert_not_production(project)

    bh.assert_not_production("br-x")
    bh.assert_not_production("br-pytest-1-1")


def test_assert_not_production_refuses_both_names_under_either_project(
    monkeypatch,
):
    """The pre-/post-rename symmetry, made explicit: flipping AURORA_PROJECT
    must not make the other production name acceptable."""
    for prod in ("tai-review", "aurora"):
        monkeypatch.setattr(conftest, "PRODUCTION_PROJECT", prod)
        for project in ("tai-review", "aurora"):
            with pytest.raises(AssertionError):
                bh.assert_not_production(project)
        bh.assert_not_production("br-x")


# --------------------------------------------------------------------------
# branch_projects
# --------------------------------------------------------------------------


def test_branch_projects_excludes_production():
    projects = bh.branch_projects()
    assert conftest.PRODUCTION_PROJECT not in projects
    assert all(p.startswith(bh.BRANCH_PREFIX) for p in projects), projects


# --------------------------------------------------------------------------
# the throwaway fixture
# --------------------------------------------------------------------------


PROBE_COMPOSE = textwrap.dedent(
    """\
    services:
      plain:
        image: alpine
        command: sleep 300
        volumes:
          - probedata:/data
      profiled:
        image: alpine
        # Trap 3: `docker compose down` was recorded as needing --profile '*'
        # or profiled services survive. Every per-developer agent service in
        # this repo is profiled, so the fixture's teardown must cope with one.
        profiles: ["agents"]
        command: sleep 300
    volumes:
      probedata:
    """
)


def test_throwaway_fixture_name_is_unique_and_safe(throwaway_branch):
    assert throwaway_branch.startswith("br-pytest-")
    bh.assert_not_production(throwaway_branch)


def test_throwaway_fixture_leaves_no_residue(throwaway_branch, tmp_path):
    """The fixture is what every later Chunk 3 task trusts to clean up. Bring
    up a project that contains all three kinds of residue this repo can
    actually produce — a plain service, a *profiled* service (trap 3), and a
    container carrying only the project label, which is what a half-finished
    `up` leaves (finding N7) — then run the exact teardown the fixture runs and
    require that nothing survives."""
    (tmp_path / "compose.yml").write_text(PROBE_COMPOSE)

    subprocess.run(
        ["docker", "compose", "--profile", "*", "-p", throwaway_branch,
         "up", "-d"],
        cwd=tmp_path, capture_output=True, text=True, check=True,
    )
    subprocess.run(
        ["docker", "run", "-d", "--name", f"{throwaway_branch}-stray",
         "--label", f"com.docker.compose.project={throwaway_branch}",
         "alpine", "sleep", "300"],
        capture_output=True, text=True, check=True,
    )

    started = bh.project_residue(throwaway_branch)
    assert len(started["containers"]) == 3, (
        "expected plain + profiled + stray containers, got " + str(started)
    )
    assert started["volumes"], "probe project created no volume"
    assert started["networks"], "probe project created no network"
    assert throwaway_branch in bh.branch_projects()

    bh.teardown_branch_project(throwaway_branch)

    left = bh.project_residue(throwaway_branch)
    assert left == {"containers": [], "volumes": [], "networks": []}, (
        f"teardown left residue: {left!r}"
    )
    assert throwaway_branch not in bh.branch_projects()


def test_teardown_refuses_a_non_branch_project():
    """The guard in front of the only destructive code path in this module."""
    for project in (conftest.PRODUCTION_PROJECT, "aurora", "tai-review", ""):
        with pytest.raises(AssertionError):
            bh.teardown_branch_project(project)


def test_teardown_still_refuses_production_with_assert_not_production_DISABLED(
    monkeypatch,
):
    """Defence in depth, and the most important test in this file.

    `teardown_branch_project` runs `docker compose -p <project> down -v
    --remove-orphans`, which needs no compose file: compose resolves the
    project from container labels. Measured with `--dry-run` on 2026-07-29,
    pointing it at production's label from an empty directory schedules all
    twelve production containers for Stopping/Removing. A single wrong
    argument is therefore a total outage.

    That means `assert_not_production` must not be the ONLY thing in the way,
    because a one-line edit to it — exactly the plan's own M4 mutation — is
    then one line away from destroying production. This test neuters
    `assert_not_production` completely and requires the independent hard guard
    to still refuse. Without it, running M4 while AURORA_PROJECT was unset
    would have torn production down, because the surviving equality check
    compares against the DEFAULT project name, not the deployed one.

    This test disables a production safety guard, so it MUST NOT be able to
    reach a real docker command even if every guard in the module fails. Both
    subprocess entry points are replaced with tripwires first. Without them
    this test is a loaded gun: run it with the hard guard mutated away and it
    executes `docker compose -p <production> down -v` for real. That is not
    hypothetical - it happened on 2026-07-29 while running exactly that
    mutation, and it destroyed production's twelve containers, nine named
    volumes and its network. The tripwires are the fix; never remove them.
    """
    fired = []

    def _tripwire(*args, **kwargs):
        fired.append(args)
        raise AssertionError(
            "TRIPWIRE: a docker command was reached with the production "
            f"guards disabled: {args!r}. No guard should have let this "
            "through, and no test may execute it."
        )

    monkeypatch.setattr(bh.subprocess, "run", _tripwire)
    monkeypatch.setattr(bh, "_docker", _tripwire)
    monkeypatch.setattr(bh, "assert_not_production", lambda project: None)

    for project in (conftest.PRODUCTION_PROJECT, "aurora", "tai-review", "",
                    "notbr-x", "br-"):
        with pytest.raises(AssertionError, match="HARD GUARD"):
            bh.teardown_branch_project(project)

    assert fired == [], (
        "the hard guard let a docker command through: " + repr(fired)
    )


def test_prod_volatile_suffixes_records_the_shm_finding():
    """N6: `-shm` must be excluded or the seeding invariant fails against a
    correct implementation."""
    assert "-shm" in bh.PROD_VOLATILE_SUFFIXES
    assert set(bh.PROD_VOLATILE_SUFFIXES) == {"-shm", ".lock", ".pid", ".log"}
