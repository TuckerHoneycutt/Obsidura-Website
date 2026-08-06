"""Runtime selection and the `DOCKER_HOST` wiring (spec 5, P4).

None of this needs a live stack, a daemon or a socket. That is deliberate:
the thing being asserted is *which daemon a command would be sent to*, and
that is a property of the argv and the environment this package builds --
observable without sending anything anywhere. The live tier lives in
tests/test_podman_runtime.py behind its own opt-in variable.

The failure this file exists to make impossible: a branch that was asked for
podman and quietly ran on the root docker daemon. Every assertion below is
some form of "the variable is EXACTLY what this tool chose", including the
negative half -- on the docker path `DOCKER_HOST` must be ABSENT, not merely
"not podman's", because an inherited one decides the daemon just as firmly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aurora_cli import branch, guards, identity, runtime as runtimes
from aurora_cli import __main__ as cli

# NOTE: this module no longer imports `_strip_docstrings`. Every assertion here
# was source-text scanning at one point; the five that remained on 2026-08-01
# have been replaced by tests that CALL the code and observe what it does --
# two of them read `branch_down` and still missed that four of its queries
# addressed the wrong daemon.


# ---------------------------------------------------------------------------
# a recording runner, so an argv can be asserted without running it
# ---------------------------------------------------------------------------


class FakeRunner(branch.CommandRunner):
    """Records every invocation and returns canned results.

    Subclasses the real `CommandRunner` rather than duck-typing one, so the
    recording -- including the stdin argument and the env dict -- is the SAME
    code the real path uses and cannot drift from it.
    """

    def __init__(self, results=None):
        super().__init__()
        self.results = dict(results or {})

    def _execute(self, argv, *, cwd, env, input, stdin, timeout):
        self.envs = getattr(self, "envs", [])
        self.envs.append(None if env is None else dict(env))
        for key, value in self.results.items():
            if key in " ".join(argv):
                return branch.CommandResult(argv, *value)
        return branch.CommandResult(argv, 0, "", "")

    def argvs(self):
        return [inv.argv for inv in self.invocations]


@pytest.fixture
def worktree(tmp_path, monkeypatch):
    """A directory that passes `guards.assert_not_production_path`.

    Production's root is faked to somewhere else entirely: the guard resolves
    it live, and a test that let it resolve to the real checkout would be one
    `chcon` away from relabelling the tree this repository is being developed
    in.
    """
    production = tmp_path / "production"
    production.mkdir()
    # Under `<production>/.worktrees/<name>`, because that is the ONLY shape
    # `guards.assert_not_production_path` accepts -- and a fixture that dodged
    # the guard would be testing a path the product never takes.
    wt = production / ".worktrees" / "br-demo"
    wt.mkdir(parents=True)
    monkeypatch.setattr(
        "aurora_cli.identity.production_root", lambda: production)
    return wt


# ---------------------------------------------------------------------------
# selection
# ---------------------------------------------------------------------------


def test_the_default_runtime_is_docker():
    """Production runs on the root docker daemon, so podman must be ASKED for.

    Not a style choice: every branch built before this phase is on docker, and
    a default that flipped would point their teardown at a daemon that has
    never heard of them.
    """
    assert runtimes.DEFAULT_RUNTIME == runtimes.DOCKER
    assert runtimes.resolve_runtime(None, environ={}) == "docker"


def test_the_flag_beats_the_environment_and_the_environment_beats_the_default():
    env = {runtimes.RUNTIME_ENV_VAR: "podman"}
    assert runtimes.resolve_runtime(None, environ=env) == "podman"
    assert runtimes.resolve_runtime("docker", environ=env) == "docker"
    assert runtimes.resolve_runtime("podman", environ={}) == "podman"


def test_an_unknown_runtime_raises_and_does_not_fall_back_to_docker():
    """The one failure mode that must never be quiet.

    A typo that means "docker" hands a caller who asked for isolation the very
    daemon they were escaping, and says nothing at all.
    """
    with pytest.raises(runtimes.RuntimeSelectionError) as exc:
        runtimes.resolve_runtime("Podman", environ={})
    assert "--runtime" in str(exc.value)
    assert "docker" in str(exc.value)

    with pytest.raises(runtimes.RuntimeSelectionError) as exc:
        runtimes.resolve_runtime(None, environ={runtimes.RUNTIME_ENV_VAR: "crun"})
    # The MESSAGE must name where the bad value came from; two sources with one
    # wording is a bug report that cannot be acted on.
    assert runtimes.RUNTIME_ENV_VAR in str(exc.value)


def test_an_empty_environment_variable_is_not_a_runtime_name():
    """`AURORA_BRANCH_RUNTIME=` exported-but-empty means "unset", not "''"."""
    assert runtimes.resolve_runtime(
        None, environ={runtimes.RUNTIME_ENV_VAR: "   "}) == "docker"


# ---------------------------------------------------------------------------
# the socket path is DERIVED, not written down
# ---------------------------------------------------------------------------


def test_the_socket_path_comes_from_the_runtime_user_not_a_literal_uid(monkeypatch):
    """`/run/user/1000` is correct on exactly one host.

    Anywhere else that literal names a DIFFERENT user's runtime directory, and
    a `DOCKER_HOST` pointing there is either a permission error or -- if uids
    collide across accounts -- somebody else's containers.
    """
    assert runtimes.podman_socket(environ={"XDG_RUNTIME_DIR": "/run/user/4242"}) == \
        Path("/run/user/4242/podman/podman.sock")

    # No XDG_RUNTIME_DIR: derived from the invoking uid, still not a literal.
    assert runtimes.podman_socket(environ={}, uid=31337) == \
        Path("/run/user/31337/podman/podman.sock")

    # ...and the discriminating half: with no XDG_RUNTIME_DIR the path must
    # FOLLOW the invoking uid. A source scan for the literal "1000" used to
    # stand here; it reddens on a rename, stays green on a wrong argument, and
    # has to dodge the measured transcripts in this module's own docstrings.
    # Driving os.getuid is the same claim, made by observation.
    monkeypatch.setattr(runtimes.os, "getuid", lambda: 4242)
    assert runtimes.podman_socket(environ={}) == \
        Path("/run/user/4242/podman/podman.sock")
    monkeypatch.setattr(runtimes.os, "getuid", lambda: 5150)
    assert runtimes.podman_socket(environ={}) == \
        Path("/run/user/5150/podman/podman.sock")


def test_the_docker_host_url_is_a_unix_socket_url():
    host = runtimes.podman_docker_host(environ={"XDG_RUNTIME_DIR": "/run/user/7"})
    assert host == "unix:///run/user/7/podman/podman.sock"


def test_a_missing_podman_socket_refuses_instead_of_falling_back(tmp_path):
    """Refusing beats reaching production.

    Compose handed a `DOCKER_HOST` that does not resolve fails late, inside an
    `up` that has already created a worktree. Refusing early leaves nothing
    behind, and the message names the unit that provides the socket because
    "not started" is what is usually wrong.
    """
    with pytest.raises(runtimes.RuntimeSelectionError) as exc:
        runtimes.for_name("podman", environ={"XDG_RUNTIME_DIR": str(tmp_path)})
    assert "podman.socket" in str(exc.value)
    assert "production" in str(exc.value)


def test_the_docker_runtime_never_consults_a_socket(tmp_path):
    """docker resolves with no filesystem check at all: it is the default."""
    rt = runtimes.for_name("docker", environ={"XDG_RUNTIME_DIR": str(tmp_path)})
    assert rt.docker_host is None
    assert not rt.is_podman


# ---------------------------------------------------------------------------
# the wiring itself
# ---------------------------------------------------------------------------


def test_podman_sets_docker_host_and_docker_removes_it():
    """The negative half is the load-bearing one.

    `DOCKER_HOST` unset means "the root daemon's default socket". Leaving an
    inherited value in place on the docker path would let a shell that had
    exported one move a docker-runtime branch onto another daemon silently,
    which is the same class of defect as an inherited COMPOSE_PROJECT_NAME --
    except it chooses the DAEMON.
    """
    base = {"PATH": "/usr/bin", "DOCKER_HOST": "unix:///somebody/elses.sock"}

    podman = runtimes.Runtime("podman", "unix:///run/user/7/podman/podman.sock")
    assert podman.environ(base)["DOCKER_HOST"] == \
        "unix:///run/user/7/podman/podman.sock"

    docker = runtimes.Runtime("docker", None)
    assert "DOCKER_HOST" not in docker.environ(base)
    assert docker.environ(base)["PATH"] == "/usr/bin"


def test_docker_host_is_stripped_from_the_ambient_environment(monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "unix:///stale.sock")
    assert runtimes.DOCKER_HOST_VAR in branch.STRIPPED_COMPOSE_VARS
    assert "DOCKER_HOST" not in branch.stripped_environ()


def test_every_compose_invocation_in_an_up_carries_the_runtime_socket(monkeypatch):
    """One seam, asserted through the function `up` actually calls.

    `_Up.compose_env` is the single place `DOCKER_HOST` is set, so this is the
    whole mechanism: if it is right here it is right for `up -d`, for
    `--build`, for `exec`, for `run --rm reconcile` and for the second `up`.
    """
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    paths = type("P", (), {"project": "br-demo", "worktree": Path("/tmp/x")})()

    podman = branch._Up(
        runner=FakeRunner(), paths=paths, production_root=Path("/tmp"),
        sleep=lambda _: None, monotonic=lambda: 0.0,
        runtime=runtimes.Runtime("podman", "unix:///run/user/7/podman/podman.sock"),
    )
    assert podman.compose_env()["DOCKER_HOST"] == \
        "unix:///run/user/7/podman/podman.sock"

    default = branch._Up(
        runner=FakeRunner(), paths=paths, production_root=Path("/tmp"),
        sleep=lambda _: None, monotonic=lambda: 0.0,
    )
    assert "DOCKER_HOST" not in default.compose_env()


def test_the_compose_argv_is_byte_identical_between_runtimes():
    """Spec 5: same binary, same overlay, same three `-f` files.

    The runtime is expressed ONLY in the environment. If it ever leaks into
    the argv -- a `--host`, a fourth `-f`, a different project -- then the two
    runtimes resolve different compose graphs and a branch stops being a test
    of production.
    """
    argv = branch.compose_argv("br-demo", "up", "-d")
    assert argv[:3] == ["docker", "compose", "-p"]
    assert argv.count("-f") == len(branch.COMPOSE_FILES) == 3
    assert not any(a in ("--host", "-H", "--context") for a in argv)


# ---------------------------------------------------------------------------
# blocker 1: SELinux relabelling, and what it is NOT allowed to touch
# ---------------------------------------------------------------------------


def test_relabelling_issues_a_recursive_chcon_to_the_container_type(worktree):
    runner = FakeRunner({"getenforce": (0, "Enforcing\n", "")})
    note = runtimes.relabel_worktree(worktree, runner=runner)
    assert ["chcon", "-R", "-t", "container_file_t", str(worktree)] in \
        [list(a) for a in runner.argvs()]
    assert "container_file_t" in note


def test_a_permissive_host_is_a_recorded_no_op_not_a_silent_skip(worktree):
    """"Nothing to do here" and "this ran" must be distinguishable afterwards."""
    runner = FakeRunner({"getenforce": (0, "Permissive\n", "")})
    note = runtimes.relabel_worktree(worktree, runner=runner)
    assert not any("chcon" in a[0] for a in runner.argvs())
    assert "NOT relabelled" in note


def test_relabelling_refuses_production_and_every_path_outside_a_worktree(
        tmp_path, monkeypatch):
    """The guard is the entire safety argument for this operation.

    `chcon -R` is the one thing on the podman path that mutates host state
    outside the runtime's own storage. Pointed at production's checkout it
    would relabel production's files; the equivalent done through compose --
    `:z` on every bind -- could not be guarded at all, because three services
    bind `/var/run/docker.sock` and forgejo binds `/etc/localtime`, both
    outside the repository.
    """
    production = tmp_path / "production"
    production.mkdir()
    monkeypatch.setattr(
        "aurora_cli.identity.production_root", lambda: production)
    runner = FakeRunner({"getenforce": (0, "Enforcing\n", "")})

    with pytest.raises(guards.GuardViolation):
        runtimes.relabel_worktree(production, runner=runner)
    assert runner.argvs() == [], (
        "the guard must refuse BEFORE any command is issued -- 'it refused' "
        "and 'it refused before doing anything' are different claims"
    )


def test_nothing_outside_the_worktree_is_ever_relabelled(worktree):
    """The only path `chcon` is ever given is the guarded worktree.

    A future edit that relabelled a compose bind SOURCE instead -- three
    services bind /var/run/docker.sock and forgejo binds /etc/localtime --
    would be a `chcon` on a host system object shared with production.

    OBSERVED, not read. This assertion used to be `body.count("chcon") == 1`
    over `inspect`-style source text: it reddens on a rename and stays green
    on a wrong argument, and two tests of that shape in this very file read
    `branch_down` without noticing that four calls inside it queried the wrong
    daemon. What is checked here is every argv the function actually issued.
    """
    runner = FakeRunner({"getenforce": (0, "Enforcing\n", "")})
    runtimes.relabel_worktree(worktree, runner=runner)

    chcons = [list(a) for a in runner.argvs() if a[0] == "chcon"]
    assert len(chcons) == 1, f"expected exactly one chcon, got {chcons}"
    # Every non-flag operand is the worktree and nothing else.
    operands = [a for a in chcons[0][1:] if not a.startswith("-")]
    assert operands[-1:] == [str(worktree)], chcons[0]
    assert all(
        Path(op) == worktree or not Path(op).is_absolute()
        for op in operands
    ), f"chcon was given a path outside the worktree: {chcons[0]}"


# ---------------------------------------------------------------------------
# blocker 2: rootless uid mapping
# ---------------------------------------------------------------------------


def test_reclaiming_ownership_uses_podman_unshare_and_needs_no_sudo(worktree):
    """`podman unshare`, never `sudo`.

    A container that drops to a non-root uid leaves its bind source owned by a
    subuid the invoking user cannot read. The whole point of this phase is
    that a branch is removable WITHOUT root, so a fix that reached for sudo
    would reintroduce the defect it is closing.
    """
    runner = FakeRunner()
    assert runtimes.reclaim_worktree_ownership(
        worktree, runner=runner, runtime=runtimes.Runtime(name="podman"),
    ) is True
    argvs = [list(a) for a in runner.argvs()]
    assert ["podman", "unshare", "chown", "-R", "0:0", str(worktree)] in argvs
    assert not any("sudo" in a for a in argvs)


def test_reclaiming_refuses_a_path_that_is_not_a_branch_worktree(
        tmp_path, monkeypatch):
    production = tmp_path / "production"
    production.mkdir()
    monkeypatch.setattr(
        "aurora_cli.identity.production_root", lambda: production)
    runner = FakeRunner()
    with pytest.raises(guards.GuardViolation):
        runtimes.reclaim_worktree_ownership(
            production, runner=runner,
            runtime=runtimes.Runtime(name="podman"))
    assert runner.argvs() == []


SOCKET = "unix:///run/user/7/podman/podman.sock"


def _podman_teardown(worktree, monkeypatch):
    """Drive the REAL `branch_down` against a recorded runner, on podman.

    Everything the function reaches for is redirected at the fixture worktree:
    the runtime record makes `teardown_runtime` answer "podman", and
    `for_name` is pinned so the test does not depend on a socket existing.
    """
    runtimes.record_runtime(worktree, "podman")
    monkeypatch.setattr(
        "aurora_cli.identity.branch_paths",
        lambda name: type("P", (), {
            "name": "demo", "project": "br-demo", "worktree": worktree,
        })(),
    )
    monkeypatch.setattr(
        runtimes, "for_name",
        lambda name, **kw: runtimes.Runtime("podman", SOCKET),
    )
    runner = FakeRunner()
    result = branch.branch_down("demo", runner=runner)
    return runner, result


def test_teardown_reclaims_before_it_removes_the_worktree(worktree, monkeypatch):
    """Order, not presence. Afterwards there is nothing left to reclaim.

    Driven, not read. The previous version compared two `body.index()` offsets
    in `branch_down`'s source; it would have stayed green on a reclaim passed
    the wrong path, and it read the very function whose four `after` queries
    were addressing the wrong daemon without seeing it.
    """
    runner, _ = _podman_teardown(worktree, monkeypatch)
    argvs = [list(a) for a in runner.argvs()]

    reclaim = [i for i, a in enumerate(argvs) if a[:2] == ["podman", "unshare"]]
    remove = [i for i, a in enumerate(argvs) if a[:3] == ["git", "worktree", "remove"]]
    assert reclaim and remove, argvs
    assert reclaim[0] < remove[0], argvs


def test_every_daemon_query_in_a_podman_teardown_carries_the_podman_socket(
        worktree, monkeypatch):
    """The test whose ABSENCE let `branch_down` verify against the wrong daemon.

    `test_every_compose_invocation_in_an_up_carries_the_runtime_socket` exists
    for `up` and had no `down` counterpart, so four `after` queries shipped
    with `env` dropped: `containers_after` was read from the ROOT docker
    daemon, which has never held a `br-` object created on podman. It is
    always `[]` there, so `containers_before - []` claimed everything was
    removed whatever survived, and the `RESIDUE:` notes could not fire.

    EVERY daemon-addressing invocation, not a sample -- the four that were
    wrong were the last four, after the report had already been half built.
    """
    runner, _ = _podman_teardown(worktree, monkeypatch)

    # `podman unshare` is excluded and only that: it enters a user namespace
    # and runs `chown` there. It speaks to no daemon and has no socket to
    # address, which is the whole reason the reclaim needs no root. Everything
    # else that names `docker` or `podman` is an API call and must say which
    # daemon it is for.
    daemon_calls = [
        inv for inv in runner.invocations
        if inv.argv[0] in ("docker", "podman") and inv.argv[1] != "unshare"
    ]
    assert len(daemon_calls) >= 8, (
        f"only {len(daemon_calls)} daemon calls recorded; a teardown queries "
        "containers, volumes and networks both before and after, so this is "
        "not exercising the path"
    )
    wrong = [
        list(inv.argv) for inv in daemon_calls
        if (inv.env or {}).get(runtimes.DOCKER_HOST_VAR) != SOCKET
    ]
    assert wrong == [], (
        f"{len(wrong)} teardown command(s) did not carry the branch's own "
        f"DOCKER_HOST: {wrong}. A query that reaches the ROOT daemon while "
        "the teardown it feeds reaches podman enumerates production's objects "
        "and reports a branch as clean."
    )


def test_a_teardown_that_removes_nothing_says_so_rather_than_claiming_success(
        worktree, monkeypatch):
    """The report is a DIFFERENCE, so both sides must come from one daemon.

    With the `after` queries on the wrong daemon they returned nothing, and
    `before - nothing` is "everything was removed" -- unconditionally, and
    with no RESIDUE note. Here the same objects answer both queries, which is
    what a failed teardown looks like, and the result must say so.
    """
    runtimes.record_runtime(worktree, "podman")
    monkeypatch.setattr(
        "aurora_cli.identity.branch_paths",
        lambda name: type("P", (), {
            "name": "demo", "project": "br-demo", "worktree": worktree,
        })(),
    )
    monkeypatch.setattr(
        runtimes, "for_name",
        lambda name, **kw: runtimes.Runtime("podman", SOCKET),
    )
    # Every `docker ps -aq --filter label=...` answers with the same container,
    # before and after: nothing was actually removed.
    runner = FakeRunner({"ps -aq": (0, "deadbeef\n", "")})
    result = branch.branch_down("demo", runner=runner)

    assert result.containers_removed == (), (
        f"claimed to have removed {result.containers_removed} while the same "
        "container was still there afterwards"
    )
    assert any("RESIDUE" in note for note in result.notes), result.notes


# ---------------------------------------------------------------------------
# a branch remembers which daemon it is on
# ---------------------------------------------------------------------------


def test_the_runtime_is_recorded_in_the_worktree_and_read_back(worktree):
    runtimes.record_runtime(worktree, "podman")
    assert runtimes.recorded_runtime(worktree) == "podman"


def test_an_absent_or_unreadable_record_is_None_not_the_default(tmp_path):
    """`None` and `"docker"` are different answers.

    "This branch predates the record" may be overridden by a flag; "this
    branch was measured to be on docker" may not.
    """
    assert runtimes.recorded_runtime(tmp_path) is None
    (tmp_path / runtimes.RUNTIME_RECORD_NAME).write_text("containerd\n")
    assert runtimes.recorded_runtime(tmp_path) is None


def test_the_record_wins_over_a_contradicting_flag(worktree):
    """A teardown on the wrong daemon does not error -- it reports success.

    It finds no container carrying the project label, removes nothing, and
    prints a clean teardown over a stack that is still running and still costs
    memory. That is strictly worse than refusing.
    """
    runtimes.record_runtime(worktree, "podman")
    assert branch.teardown_runtime(worktree, None) == "podman"
    assert branch.teardown_runtime(worktree, "podman") == "podman"
    with pytest.raises(branch.BranchError) as exc:
        branch.teardown_runtime(worktree, "docker")
    assert runtimes.RUNTIME_RECORD_NAME in str(exc.value)


def test_without_a_record_the_flag_then_the_environment_then_docker(tmp_path):
    assert branch.teardown_runtime(tmp_path, None, environ={}) == "docker"
    assert branch.teardown_runtime(tmp_path, "podman", environ={}) == "podman"
    assert branch.teardown_runtime(
        tmp_path, None, environ={runtimes.RUNTIME_ENV_VAR: "podman"}) == "podman"


# `up` ordering -- record before containers, relabel after the seed -- is
# asserted in aurora-cli/tests/test_branch_up.py, by DRIVING `branch_up`
# against its harness and observing what existed when each command was issued.
# It used to live here as three `body.index()` comparisons over `branch_up`'s
# source text, which redden on a rename and stay green on a wrong argument.


# ---------------------------------------------------------------------------
# the CLI surface
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("argv", [
    ["branch", "up", "demo", "--runtime", "podman"],
    ["branch", "down", "demo", "--runtime", "podman"],
    ["branch", "rebuild", "demo", "--runtime", "podman"],
    ["branch", "ls", "--runtime", "podman"],
])
def test_every_branch_subcommand_accepts_the_runtime_flag(argv):
    args = cli.build_parser().parse_args(argv)
    assert args.runtime == "podman"


def test_the_flag_defaults_to_none_so_the_environment_can_answer():
    """`default=None`, not `default="docker"`.

    An argparse default of "docker" would beat `$AURORA_BRANCH_RUNTIME` on
    every invocation and make the variable dead, which is exactly the kind of
    inert control this repository keeps finding.
    """
    args = cli.build_parser().parse_args(["branch", "up", "demo"])
    assert args.runtime is None


def test_an_unknown_runtime_leaves_the_cli_with_exit_1_and_a_message(capsys):
    rc = cli.main(["branch", "up", "demo", "--runtime", "containerd"])
    assert rc == 1
    assert "containerd" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# what `main()` turns into a message rather than a traceback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("error", [
    # `aurora branch overlay <name> --limits typo` -> `overlay.resolve_limits`,
    # caught nowhere before this.
    ("overlay", "OverlayError"),
    # `resolve_branch_authkey` -> `tailnet.oauth_client()` raises on HALF an
    # OAuth client, and it runs BEFORE `branch_up`'s `try`, so `BranchUpFailed`
    # does not wrap it: a typo in production's `.env` printed a stack trace
    # instead of the refusal that was carefully written for it.
    ("tailnet", "TailnetError"),
    # Not left to `branch_up`'s blanket `except Exception`: `branch_overlay`
    # and `branch_rebuild` are reachable callers too.
    ("forgejo_token", "ForgejoTokenError"),
])
def test_a_refusal_from_any_of_these_modules_is_a_message_not_a_traceback(
    error, monkeypatch, capsys
):
    """Every one of these messages names the value that could not be resolved,
    and that value is the whole diagnostic. A stack trace buries it, and a
    guard refusing is a correct outcome rather than a crash."""
    module_name, class_name = error
    module = __import__(f"aurora_cli.{module_name}", fromlist=[class_name])
    exc_type = getattr(module, class_name)

    def explode(_args):
        raise exc_type("the value that could not be resolved")

    monkeypatch.setattr(cli, "_cmd_branch_ls", explode, raising=False)
    parser = cli.build_parser()
    args = parser.parse_args(["branch", "ls"])
    monkeypatch.setattr(args, "func", explode)

    monkeypatch.setattr(
        cli.argparse.ArgumentParser, "parse_args", lambda self, argv=None: args)
    rc = cli.main(["branch", "ls"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "the value that could not be resolved" in err
    assert "Traceback" not in err


# ---------------------------------------------------------------------------
# D2: the same reclaim, through the other available root
# ---------------------------------------------------------------------------
#
# Measured (docs/measurements/2026-08-01-docker-podman-parity.md): the docker
# path leaked a 2.5 GB worktree it could not delete, while podman -- which had
# a reclaim -- cleaned up completely. The podman branch of this function had
# shipped from the start, and its own docstring described the docker daemon
# leaving "root-owned directories behind" in the PAST TENSE, for a bug that was
# still live on the path without the fix.


def test_the_docker_reclaim_chowns_the_worktree_back_and_needs_no_sudo(
        tmp_path, monkeypatch):
    """A rootful daemon writes as host uid 0; the daemon is asked to undo it.

    The assertion that this needs no privilege of ours is `sudo` never
    appearing: this process has no passwordless sudo, so a reclaim that needed
    it would fail rather than quietly succeed.
    """
    import os

    worktrees = tmp_path / "worktrees"
    worktree = worktrees / "demo"
    worktree.mkdir(parents=True)
    # A real git worktree carries a `.git` FILE naming its administrative
    # directory. The docker reclaim requires one before handing a path to a
    # root daemon, so a fixture without it is not a fixture for this function.
    (worktree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    monkeypatch.setattr(
        "aurora_cli.identity.production_root", lambda: tmp_path / "production")
    runner = FakeRunner()

    assert runtimes.reclaim_worktree_ownership(
        worktree, runner=runner, runtime=runtimes.Runtime(name="docker"),
        worktrees_root=worktrees,
    ) is True

    argvs = [list(a) for a in runner.argvs()]
    assert len(argvs) == 1, argvs
    argv = argvs[0]
    assert argv[:2] == ["docker", "run"], argv
    assert f"{os.getuid()}:{os.getgid()}" in argv, argv
    assert "chown" in argv and "-R" in argv, argv
    assert not any("sudo" in part for part in argv), argv


def test_the_docker_reclaim_mounts_the_worktree_and_nothing_above_it(
        tmp_path, monkeypatch):
    """The blast radius of a recursive chown is whatever got mounted.

    Mounting the PARENT would put every sibling branch -- and, from
    production's own `.worktrees`, production-adjacent paths -- inside a
    `chown -R`. Asserted on the `-v` value specifically, because that argument
    alone decides what the container can reach.
    """
    worktrees = tmp_path / "worktrees"
    worktree = worktrees / "demo"
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    monkeypatch.setattr(
        "aurora_cli.identity.production_root", lambda: tmp_path / "production")
    runner = FakeRunner()

    runtimes.reclaim_worktree_ownership(
        worktree, runner=runner, runtime=runtimes.Runtime(name="docker"),
        worktrees_root=worktrees)

    argv = [list(a) for a in runner.argvs()][0]
    mounts = [argv[i + 1] for i, part in enumerate(argv) if part == "--mount"]
    assert mounts == [f"type=bind,src={worktree},dst=/worktree"], mounts


def test_the_docker_reclaim_refuses_a_path_that_is_not_a_git_worktree(
        tmp_path, monkeypatch):
    """The positive check, and the reason it is docker-only.

    `assert_not_production_path` refuses anything inside production. It says
    nothing about the REST of the filesystem, and `worktrees_root` is a test
    seam wide enough to admit `/etc`. Under podman that was harmless -- uid
    1000 inside a user namespace owns none of it -- but the docker branch hands
    the path to a ROOT daemon, where `chown -R` succeeds. Nothing user-facing
    passes `worktrees_root` today; this makes that a design choice rather than
    a coincidence.

    It SKIPS rather than raising, because this runs on the teardown path and a
    refusal that aborts a teardown leaves more behind than the leak it is
    preventing. The property asserted is that no command ran at all.
    """
    victim = tmp_path / "etc"
    victim.mkdir()
    (victim / "passwd").write_text("root:x:0:0\n", encoding="utf-8")
    monkeypatch.setattr(
        "aurora_cli.identity.production_root", lambda: tmp_path / "production")
    runner = FakeRunner()

    assert runtimes.reclaim_worktree_ownership(
        victim, runner=runner, runtime=runtimes.Runtime(name="docker"),
        worktrees_root=tmp_path) is False
    # The safety property is that NO command ran, which is stronger than any
    # claim about which exception was raised.
    assert runner.argvs() == []
    assert (victim / "passwd").exists()


def test_the_reclaim_owner_is_the_invoking_user_not_root_under_sudo():
    """`os.getuid()` under sudo is 0, and `chown -R 0:0` reproduces the leak.

    The container would exit 0 and the reclaim would report success while
    having done exactly what it exists to undo -- the one failure shape that is
    indistinguishable from working.
    """
    assert runtimes._reclaim_owner(environ={"SUDO_UID": "1000", "SUDO_GID": "1000"}) \
        == (1000, 1000)
    import os as _os
    assert runtimes._reclaim_owner(environ={}) == (_os.getuid(), _os.getgid())


# ---------------------------------------------------------------------------
# a throwaway container that outlives `--rm` has to be reachable
# ---------------------------------------------------------------------------


def _docker_reclaim_argv(tmp_path, monkeypatch, **kwargs):
    worktrees = tmp_path / "worktrees"
    worktree = worktrees / "demo"
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    monkeypatch.setattr(
        "aurora_cli.identity.production_root", lambda: tmp_path / "production")
    runner = FakeRunner()
    runtimes.reclaim_worktree_ownership(
        worktree, runner=runner, runtime=runtimes.Runtime(name="docker"),
        worktrees_root=worktrees, **kwargs)
    return [list(a) for a in runner.argvs()][0]


def test_the_reclaim_container_carries_the_branch_project_label(
        tmp_path, monkeypatch):
    """`--rm` is not a guarantee, and an unlabelled survivor is unreachable.

    Measured: a throwaway container killed between `create` and `start`
    survived, and carrying no label put it in the worst position available --
    invisible to `branch_down`'s residue sweep, which filters on exactly this
    label, and outside the `br-` namespace `ops/docker-guard` will act on, so
    no human following the teardown docs had a sanctioned command for it.
    """
    argv = _docker_reclaim_argv(tmp_path, monkeypatch, project="br-demo")
    labels = [argv[i + 1] for i, part in enumerate(argv) if part == "--label"]
    assert f"{identity.PROJECT_LABEL}=br-demo" in labels, argv


def test_the_reclaim_omits_the_label_rather_than_inventing_a_project(
        tmp_path, monkeypatch):
    """No project, no label -- never a placeholder.

    A container labelled `com.docker.compose.project=None` would be swept by
    nothing and would answer a filter for a project that does not exist, which
    is worse than carrying no label at all: it looks handled.
    """
    argv = _docker_reclaim_argv(tmp_path, monkeypatch)
    assert "--label" not in argv, argv
    assert "None" not in " ".join(argv), argv


