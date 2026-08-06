"""The docker reclaim, run for real against a genuinely root-owned tree.

Every other test of this function drives a `FakeRunner` and asserts the argv.
That is how defect D2 shipped: `tests/test_podman_runtime.py` records that the
podman reclaim was once "tested" by re-spelling `podman unshare chown` in the
test instead of invoking the product function, so replacing the function body
with `return True` reddened nothing. The docker half arrived in exactly that
state — argv assertions only — and this file is the outcome test it was
missing.

What makes it an outcome test: the tree is made root-owned by a real container,
and the assertion is `st_uid` afterwards. Nothing here names `chown`, so an
implementation that stopped running one would fail.

This also covers a property no argv assertion can reach. SELinux is Enforcing
on this host, and a bind mount without `:z`/`:Z` is the classic way for a
container write to fail silently. `docker info` reports no `selinux` security
option, so the rootful daemon applies no MCS labels and the mount should work —
but that is an inference from a daemon build flag, and this test is the thing
that would notice if it stopped being true.
"""

from __future__ import annotations

import os
import subprocess

import pytest

from aurora_cli import branch as branch_mod
from aurora_cli import runtime as runtimes

#: `br-` prefixed so `ops/docker-guard` permits the teardown and so nothing
#: here can name production's project.
PROBE_PROJECT = "br-reclaimprobe"


def _run(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True)


@pytest.fixture
def root_owned_worktree(tmp_path):
    """A directory that looks like a git worktree and is owned by root.

    Made root-owned the way the real defect makes it root-owned — by a
    container writing through a bind mount — rather than by `chown`, which
    this user cannot do anyway.
    """
    worktrees = tmp_path / "worktrees"
    worktree = worktrees / "probe"
    worktree.mkdir(parents=True)
    # The guard requires this before handing any path to a root daemon.
    (worktree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")

    made = _run(
        "docker", "run", "--rm", "--network=none",
        "--label", f"com.docker.compose.project={PROBE_PROJECT}",
        "--mount", f"type=bind,src={worktree},dst=/w",
        runtimes.RECLAIM_IMAGE,
        "sh", "-c", "mkdir -p /w/data && touch /w/data/root-owned",
    )
    if made.returncode != 0:
        pytest.skip(f"could not create a root-owned tree: {made.stderr.strip()[:200]}")

    planted = worktree / "data" / "root-owned"
    if planted.stat().st_uid == os.getuid():
        pytest.skip(
            "the daemon did not write as root (rootless docker?), so there is "
            "no leak here to reclaim and this test would prove nothing"
        )

    yield worktrees, worktree

    # Unconditionally, because a FAILING run is exactly the run that leaves a
    # root-owned tree behind -- and pytest cannot reap one, so every later
    # session inherits the warning. Observed during mutation testing.
    _run("docker", "run", "--rm", "--network=none",
         "--label", f"com.docker.compose.project={PROBE_PROJECT}",
         "--mount", f"type=bind,src={worktree},dst=/w",
         runtimes.RECLAIM_IMAGE,
         "chown", "-R", f"{os.getuid()}:{os.getgid()}", "/w")


def test_the_docker_reclaim_really_gives_a_root_owned_tree_back(
        root_owned_worktree):
    """D2, measured rather than spelled.

    The precondition is asserted, not assumed: a test that reclaims a tree
    which was never root-owned passes whatever the implementation does.
    """
    worktrees, worktree = root_owned_worktree
    before = {p.stat().st_uid for p in worktree.rglob("*")}
    assert before - {os.getuid()}, (
        "nothing in the fixture is owned by another uid, so this test cannot "
        "distinguish a working reclaim from a missing one"
    )

    assert runtimes.reclaim_worktree_ownership(
        worktree,
        runner=branch_mod.CommandRunner(),
        runtime=runtimes.Runtime(name="docker"),
        worktrees_root=worktrees,
    ) is True

    after = {p.stat().st_uid for p in worktree.rglob("*")}
    assert after <= {os.getuid()}, (
        f"paths are still owned by {sorted(after - {os.getuid()})} after the "
        "reclaim, so `git worktree remove` would fail and the branch would "
        "leak its worktree -- which is defect D2, unfixed."
    )

    # The point of the reclaim is that the tree becomes removable BY US.
    (worktree / "data" / "root-owned").unlink()
    (worktree / "data").rmdir()
