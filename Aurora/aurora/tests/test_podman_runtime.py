"""The podman branch runtime, against real daemons (spec 5, P4).

OPT-IN, AND NOT SILENTLY SO. Everything here needs two live container
runtimes, so it is gated on `$AURORA_PODMAN_LIVE=1`. Chunk 2 shipped a
`pytest.skip` that made a Critical gate inert at every invocation its plan
contained and passed review, because a skip is not a failure. The difference
between that and this is `test_the_podman_live_tier_is_opt_in_and_its_blocker_
is_named`, which runs UNCONDITIONALLY, names the variable, and points at the
written record of why the tier is not on by default.

What it costs to run: one throwaway compose project (`br-podprobe`) with ONE
service, built and torn down. Not a full stack -- deliberately. The claims
this phase makes are about which daemon a command reaches, which store an
image lands in, and whether a bind mount is readable; none of them need
thirteen containers, and the full-stack path is blocked on this host for a
reason that is nothing to do with podman (see `WHY NOT A FULL STACK` below).

WHY NOT A FULL STACK, measured 2026-08-01:

    ls -ldn <production>/.worktrees
    drwxr-xr-x 0 0 ... .worktrees

`aurora branch up` creates its worktree at `<production>/.worktrees/<name>`
(decision D-F) and that directory is ROOT-OWNED on this host -- the residue of
the leaked-worktree defect, left by the root docker daemon creating bind
sources inside earlier branches. uid 1000 cannot create anything in it, so
`branch up` cannot run at all here, on EITHER runtime, until a human clears it
with root. That is the pre-existing damage P4 stops happening again; it is not
something P4 can undo.

The service under test is `agent-authz`. Chosen, not arbitrary:
  * it BUILDS, so it exercises the build cache and image store -- the two
    resources §1 of the spec lists as shared and unnamespaced;
  * `compose.branch.yml` resets its `image:` to null (the 2026-07-31 escape),
    so the tag Compose derives is `br-podprobe-agent-authz` and building it can
    not overwrite anything production runs, on EITHER daemon. That property is
    what makes the M11 mutation safe to actually perform rather than describe;
  * it binds `./agent-authz/data` and nothing else, which is precisely the
    repo-relative bind the SELinux claim is about.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aurora-cli"))

from aurora_cli import envfile, exclusions, runtime as runtimes  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"

LIVE_ENV = "AURORA_PODMAN_LIVE"
LIVE_SKIP_REASON = (
    f"the podman live tier is opt-in (${LIVE_ENV}=1). It builds an image and "
    "creates a compose project on the rootless podman daemon. "
    "test_the_podman_live_tier_is_opt_in_and_its_blocker_is_named runs "
    "unconditionally so this is never a silent omission."
)
live = pytest.mark.skipif(os.environ.get(LIVE_ENV) != "1", reason=LIVE_SKIP_REASON)

#: A name nothing on this host uses. The project is `br-` prefixed so
#: `ops/docker-guard` will let the teardown through, which is itself part of
#: what is being proved -- M13: the guard is a host mechanism and is unaffected
#: by which daemon `DOCKER_HOST` names.
BRANCH = "podprobe"
PROJECT = f"br-{BRANCH}"
SERVICE = "agent-authz"


# ---------------------------------------------------------------------------
# helpers -- every one of them says WHICH daemon it asked
# ---------------------------------------------------------------------------


def _run(argv, *, env=None, cwd=None, check=True):
    proc = subprocess.run(
        argv, capture_output=True, text=True, cwd=cwd,
        env=None if env is None else {**os.environ, **env},
        stdin=subprocess.DEVNULL,
    )
    if check and proc.returncode != 0:
        raise AssertionError(
            f"`{' '.join(argv)}` exited {proc.returncode}\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
    return proc


def _podman_env():
    """The environment the product itself builds for `--runtime podman`.

    Read through `runtime.for_name` rather than assembled here: a test that
    wrote its own `DOCKER_HOST` would pass while the product pointed somewhere
    else entirely, which is the one failure this whole module exists to catch.
    """
    return runtimes.for_name(runtimes.PODMAN).environ(dict(os.environ))


def _root_env():
    """Explicitly NO `DOCKER_HOST` -- the root docker daemon's default socket."""
    env = dict(os.environ)
    env.pop(runtimes.DOCKER_HOST_VAR, None)
    return env


def _images(env):
    return sorted(
        _run(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
             env=env).stdout.split()
    )


def _containers(env):
    return sorted(
        _run(["docker", "ps", "-a", "--format", "{{.Names}}"], env=env).stdout.split()
    )


def _production_fingerprint():
    """What must be byte-identical before and after everything below.

    Containers AND images AND the forge answering: a fingerprint that only
    counted containers would miss the image-tag escape, which is the defect
    that started this spec.
    """
    root = _root_env()
    git = _run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}",
                "--max-time", "10", "http://127.0.0.1:3000/"], check=False)
    return {
        "containers": _containers(root),
        "images": _images(root),
        "forgejo_http": git.stdout.strip(),
    }


# ---------------------------------------------------------------------------
# the fixture: a real branch-shaped worktree on the podman daemon
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def branch_worktree(tmp_path_factory):
    """A git worktree carrying a rendered branch `.env` and the overlay files.

    NOT under `<production>/.worktrees/` -- see the module docstring; that
    directory is root-owned on this host. So this drives the same rendering,
    relabelling and compose code the product does, from a path the product's
    own teardown guard would refuse. The teardown here is therefore explicit
    rather than `branch_down`, and the module says so instead of pretending
    otherwise.
    """
    root = tmp_path_factory.mktemp("podman-live") / PROJECT
    _run(["git", "-C", str(REPO_ROOT), "worktree", "add", "--detach",
          str(root), "HEAD"])
    try:
        text = envfile.render_branch_env(
            BRANCH, devs=(), authkey="tskey-not-used-no-sidecar-in-this-tier",
        )
        (root / ".env").write_text(text, encoding="utf-8")
        os.chmod(root / ".env", 0o600)
        exclusions.write_exclusion_overlay((), root)
        (root / runtimes.RUNTIME_RECORD_NAME).write_text("podman\n")
        yield root
    finally:
        env = _podman_env()
        _run(["docker", "compose", "-p", PROJECT, "--profile", "*",
              "down", "-v", "--remove-orphans"], env=env, cwd=str(root),
             check=False)
        # `compose down` removes containers, volumes and the network. It does
        # NOT remove what `--build` produced, and the built image plus the
        # buildx builder container ARE residue -- the image store is one of
        # the shared resources this phase exists to separate, so a tier that
        # left images in it would be measuring the wrong daemon's tidiness.
        # Issued through `podman` rather than through the `docker` shim
        # because these are podman-store objects and the shim's guard, quite
        # correctly, refuses `rm -f` on anything not named `br-`.
        _run(["podman", "rmi", "-f", f"{PROJECT}-{SERVICE}:latest"], check=False)
        _run(["podman", "rm", "-f", "buildx_buildkit_default"], check=False)
        _run(["podman", "volume", "rm", "-f", "buildx_buildkit_default_state"],
             check=False)
        _run(["podman", "unshare", "chown", "-R", "0:0", str(root)], check=False)
        _run(["git", "-C", str(REPO_ROOT), "worktree", "remove", "--force",
              str(root)], check=False)
        shutil.rmtree(root, ignore_errors=True)
        _run(["git", "-C", str(REPO_ROOT), "worktree", "prune"], check=False)


@pytest.fixture(scope="module")
def brought_up(branch_worktree):
    """`up -d --build agent-authz` on podman, with the product's own argv."""
    from aurora_cli import branch as branch_mod
    argv = branch_mod.compose_argv(PROJECT, "up", "-d", "--build", SERVICE)
    before = _production_fingerprint()
    _run(argv, env=_podman_env(), cwd=str(branch_worktree))
    yield {"argv": argv, "production_before": before}


# ---------------------------------------------------------------------------
# the gate itself -- runs unconditionally
# ---------------------------------------------------------------------------


def test_the_podman_live_tier_is_opt_in_and_its_blocker_is_named():
    """The skip above is not allowed to be silent.

    Chunk 2 shipped a `pytest.skip` that made a Critical gate inert at every
    invocation, and it passed review. The difference is this test: the
    omission has a name, a measured cause, a written record, and an assertion
    that goes red if the record disappears.
    """
    record = DOCS / "issues" / "2026-08-01-podman-branch-runtime.md"
    text = record.read_text(encoding="utf-8")
    assert LIVE_ENV in text, (
        f"${LIVE_ENV} is no longer explained in {record.relative_to(REPO_ROOT)}"
    )
    assert "tests/test_podman_runtime.py" in text, (
        "the record names the variable but not the module to run it against, "
        "which is half an instruction"
    )
    # The measured blockers, both of them, must still be written down. A future
    # reader who deletes the relabel or the reclaim has to find out here why
    # they exist.
    for measured in ("container_file_t", "podman unshare", "525286"):
        assert measured in text, (
            f"{measured!r} -- a measured fact this tier depends on -- is no "
            f"longer recorded in {record.relative_to(REPO_ROOT)}"
        )


# ---------------------------------------------------------------------------
# the live tier
# ---------------------------------------------------------------------------


@live
def test_the_two_daemons_are_actually_two_daemons():
    """Cheapest possible falsification, run first.

    If `DOCKER_HOST` were being ignored -- a stale compose, a socket that is a
    proxy to the root daemon -- every other assertion below would still pass
    while proving nothing. So this compares what the two sockets SAY they are.
    """
    podman = json.loads(_run(
        ["docker", "version", "--format", "{{json .Server}}"],
        env=_podman_env()).stdout)
    root = json.loads(_run(
        ["docker", "version", "--format", "{{json .Server}}"],
        env=_root_env()).stdout)
    assert "podman" in json.dumps(podman).lower()
    assert "podman" not in json.dumps(root).lower()


@live
def test_a_repo_relative_bind_needs_the_relabel_and_the_relabel_is_enough(
        tmp_path_factory):
    """Blocker 1, both directions, on a throwaway container.

    The negative half is the one that matters. A test that only showed the
    relabelled case working would pass on a Permissive host, where the relabel
    does nothing at all, and would therefore never have detected its removal.
    """
    assert _run(["getenforce"]).stdout.strip() == "Enforcing", (
        "this assertion is only meaningful under Enforcing"
    )
    # `tmp_path_factory`, not a sibling of the repository root. The previous
    # version wrote and `rm -rf`d `<repo>/../br-podprobe-selinux-probe`, i.e.
    # a directory in the user's home next to production's checkout.
    probe = tmp_path_factory.mktemp("selinux-probe") / PROJECT
    (probe / "d").mkdir(parents=True)
    (probe / "d" / "f").write_text("secret\n")
    try:
        args = ["docker", "run", "--rm", "-v", f"{probe}:/probe",
                "docker.io/library/debian:bookworm-slim",
                "cat", "/probe/d/f"]
        before = _run(args, env=_podman_env(), check=False)
        assert before.returncode != 0 and "denied" in before.stderr.lower(), (
            f"an unrelabelled bind was readable: {before.stdout!r} "
            f"{before.stderr!r}. Either SELinux stopped applying to this path "
            "or the containers are no longer confined -- in both cases the "
            "relabel below is proving nothing."
        )
        # THE PRODUCT FUNCTION, not `chcon` spelled again by hand. Spelling it
        # by hand proved that podman behaves as measured and proved nothing
        # about this code: replacing `relabel_worktree`'s body with `return
        # None` reddened nothing. `worktrees_root` is the seam that makes the
        # call possible from here -- `<production>/.worktrees` is root-owned on
        # this host (module docstring) so the fixture worktree cannot live
        # there, and `guards.assert_not_production_path` refuses everything
        # else. It cannot widen the guard; see that function.
        from aurora_cli import branch as branch_mod
        runner = branch_mod.CommandRunner()
        note = runtimes.relabel_worktree(
            probe, runner=runner, worktrees_root=probe.parent)
        assert runtimes.SELINUX_CONTAINER_TYPE in (note or ""), note
        assert any(a.argv[0] == "chcon" for a in runner.invocations), \
            [a.argv for a in runner.invocations]

        after = _run(args, env=_podman_env())
        assert after.stdout.strip() == "secret"
    finally:
        _run(["podman", "unshare", "rm", "-rf", str(probe)], check=False)


@live
def test_the_branch_lands_on_podman_and_is_invisible_to_the_root_daemon(brought_up):
    """The structural claim, stated as an inventory difference.

    Not "the guard refused" -- there is no guard in this path. The root daemon
    simply does not have these objects, because they were never created there.
    """
    podman_containers = _containers(_podman_env())
    root_containers = _containers(_root_env())
    assert any(c.startswith(PROJECT) for c in podman_containers), podman_containers
    assert not any(c.startswith(PROJECT) for c in root_containers), (
        f"a container for {PROJECT} exists on the ROOT daemon: "
        f"{[c for c in root_containers if c.startswith(PROJECT)]}"
    )


@live
def test_the_branch_image_is_in_the_podman_store_and_not_the_root_one(brought_up):
    """Spec 5 acceptance, verbatim: `podman images` shows the branch's image,
    `docker images` on the root daemon does not."""
    assert any(PROJECT in i for i in _images(_podman_env()))
    assert not any(PROJECT in i for i in _images(_root_env()))


@live
def test_production_is_unchanged_across_the_whole_run(brought_up):
    """Containers, images and the forge answering -- the same fingerprint the
    run started from. Any difference is a stop-and-report, not a diff to
    explain away."""
    after = _production_fingerprint()
    before = brought_up["production_before"]
    assert after["containers"] == before["containers"]
    assert after["images"] == before["images"]
    assert after["forgejo_http"] == before["forgejo_http"]


@live
def test_the_worktree_is_reclaimable_without_sudo(branch_worktree, brought_up):
    """The leaked-worktree regression, as a POSITIVE assertion.

    `podman unshare` is the whole of it, and the assertion that it needs no
    root is `sudo` never appearing -- this process has no passwordless sudo, so
    a reclaim that needed it would fail here rather than quietly succeed.
    """
    # THE PRODUCT FUNCTION. What stood here was
    # `assert reclaim_worktree_ownership.__module__ == "aurora_cli.runtime"`
    # -- a tautology, since any function defined in that file has that
    # `__module__` -- followed by a hand-rolled `podman unshare chown`. The
    # function itself was never invoked, so replacing its body with `return
    # True` reddened nothing: only deleting the NAME did. Of the three P4
    # functions that mutate the host, the live tier drove none.
    from aurora_cli import branch as branch_mod
    runner = branch_mod.CommandRunner()
    assert runtimes.reclaim_worktree_ownership(
        branch_worktree, runner=runner,
        runtime=runtimes.Runtime(name="podman"),
        worktrees_root=branch_worktree.parent,
    ) is True
    argvs = [list(inv.argv) for inv in runner.invocations]
    assert ["podman", "unshare", "chown", "-R", "0:0", str(branch_worktree)] \
        in argvs, argvs
    # `sudo` never appears, and this process has no passwordless sudo -- so a
    # reclaim that reached for it would have failed above rather than quietly
    # succeeded.
    assert not any("sudo" in a for a in argvs), argvs
    # Everything in the tree is now this user's again, so an ordinary rmtree
    # would succeed -- which is what `git worktree remove` needs.
    owners = {p.stat().st_uid for p in branch_worktree.rglob("*")}
    assert owners <= {os.getuid()}, (
        f"paths in the worktree are still owned by uids this user cannot "
        f"remove: {sorted(owners - {os.getuid()})}"
    )
