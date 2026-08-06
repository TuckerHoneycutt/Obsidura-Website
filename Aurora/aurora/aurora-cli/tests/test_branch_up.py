"""`aurora branch up` (Task 8).

Almost all of `up` is orchestration, so almost all of these tests are about
ORDER and REFUSAL, driven through an injected command runner that records
argv. Two things about that, both learned expensively in this chunk:

* **No test here brings up a real stack.** `aurora branch down` does not exist
  until Task 9, so a failed real `up` would leave containers, volumes and a
  network that nothing has a tested way to remove, beside live production.
  `RecordingRunner` overrides the one `_execute` seam, and
  `test_no_test_in_this_module_can_reach_a_real_subprocess` installs a
  tripwire over `subprocess.run` to prove it rather than assert it in prose.

* **An orchestration test over an empty argv log passes vacuously.** Every
  ordering assertion here first asserts the log is non-empty AND that the
  labels it is about are present. That is the shape of at least three defects
  in this project's history.
"""

from __future__ import annotations

import json
import shutil
import os
import sqlite3
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

import pytest

from aurora_cli import (
    branch, crosswire, envfile, forgejo_token, identity, seed, tailnet,
)
from aurora_cli import runtime as runtimes


# ---------------------------------------------------------------------------
# doubles
# ---------------------------------------------------------------------------

READY_STATUS = {
    "BackendState": "Running",
    "Self": {"DNSName": "PLACEHOLDER."},
}

NEEDS_LOGIN_STATUS = {
    "BackendState": "NeedsLogin",
    "Self": {"DNSName": ""},
}


class RecordingRunner(branch.CommandRunner):
    """Records every invocation and answers from a canned script.

    Subclasses the real runner rather than reimplementing it, so the recording
    -- including the stdin argument, which plan defect 28 turns on -- is the
    same code a real run uses. A double that recorded its own way could agree
    with itself while the product passed `stdin=None` and hung.
    """

    def __init__(
        self,
        *,
        hostname: str,
        worktree: Path | None = None,
        ts_status: Mapping[str, Any] | None = None,
        http_code: str = "200",
        fail_on: Sequence[str] | None = None,
        fail_message: str = "canned failure",
        git_user: str = "",
        branch_exists: bool = False,
    ) -> None:
        super().__init__()
        self.hostname = hostname
        self.worktree = worktree
        self.ts_status = dict(ts_status) if ts_status is not None else None
        self.http_code = http_code
        self.fail_on = tuple(fail_on or ())
        self.fail_message = fail_message
        self.git_user = git_user
        self.branch_exists = branch_exists

    def _execute(self, argv, *, cwd, env, input, stdin, timeout):
        text = " ".join(argv)
        if self.fail_on and all(token in text for token in self.fail_on):
            return branch.CommandResult(argv, 1, "", self.fail_message)

        if argv[:1] == ("git",):
            if "config" in argv and "user.name" in argv:
                return branch.CommandResult(
                    argv, 0 if self.git_user else 1, self.git_user, "")
            if "rev-parse" in argv:
                return branch.CommandResult(
                    argv, 0 if self.branch_exists else 1, "", "")
            if "worktree" in argv and "add" in argv:
                if self.worktree is not None:
                    self.worktree.mkdir(parents=True, exist_ok=True)
                return branch.CommandResult(argv, 0, "", "")
            return branch.CommandResult(argv, 0, "", "")

        if argv[:1] == ("curl",):
            return branch.CommandResult(argv, 0, self.http_code, "")

        if "generate-access-token" in argv:
            # `--raw`: stdout is the token and nothing else. Answered here
            # rather than in the forge double because it is a subprocess, and
            # the point of routing it through `CommandRunner` is that the
            # token travels in STDOUT and never in argv.
            return branch.CommandResult(argv, 0, MINTED_TOKEN + "\n", "")

        if "tailscale" in argv and "status" in argv:
            status = self.ts_status
            if status is None:
                status = {
                    "BackendState": "Running",
                    "Self": {"DNSName": f"{self.hostname}.tailnet.example."},
                }
            return branch.CommandResult(argv, 0, json.dumps(status), "")

        return branch.CommandResult(argv, 0, "", "")


#: What the fake branch forge answers `/api/v1/user` with, and the row the
#: fake seeded database carries as production's admin token.
FORGE_LOGIN = "supergoodname77"
MINTED_TOKEN_ID = 99
MINTED_TOKEN = "0000000000000000000000000000000000minted"
#: Whatever production's `.env` actually holds. Read rather than invented,
#: because P3's whole subject is the value a branch INHERITS: a fabricated one
#: would let the branch `.env` "differ from production" while the real
#: rendered file did not.
INHERITED_TOKEN = envfile.parse_env(
    envfile.production_env_text()).get(forgejo_token.ADMIN_TOKEN_VAR, "")


def write_seeded_forgejo_db(worktree: Path, *, rows: int = 2) -> Path:
    """A branch's copy of production's Forgejo database, as the seed leaves it.

    Two `access_token` rows because production has two, and one is not the one
    `.env` names: P3's purge is about EVERY production credential in the copy,
    not only the one somebody remembered.
    """
    path = forgejo_token.branch_database(worktree)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(
            "CREATE TABLE access_token (id INTEGER PRIMARY KEY, uid INTEGER, "
            "name TEXT, token_hash TEXT, token_salt TEXT)")
        connection.execute(
            "CREATE TABLE forgejo_auth_token (id INTEGER PRIMARY KEY, "
            "token_hash TEXT)")
        for index in range(1, rows + 1):
            connection.execute(
                "INSERT INTO access_token (id, uid, name, token_hash, "
                "token_salt) VALUES (?,?,?,?,?)",
                (index, 1, f"production-{index}", f"hash{index}", f"salt{index}"))
        connection.execute(
            "INSERT INTO forgejo_auth_token (id, token_hash) VALUES (1, 'h')")
    connection.close()
    return path


class ForgejoDouble:
    """The BRANCH's Forgejo, as an opener. Records into the shared log.

    An opener rather than a stub of `rotate_admin_token`, so `branch up`
    exercises the real mint -> write -> purge and the real SQLite DELETE
    against a real (tiny) database. Stubbing the whole rotation would leave
    the ordering that P3 is entirely about untested from `up`'s side.
    """

    def __init__(self, runner: branch.CommandRunner) -> None:
        self.runner = runner
        self.tokens_valid = True

    def __call__(self, url, method, headers, body):
        self.runner.invocations.append(
            branch.Invocation(argv=("<forgejo-api>", method, url)))
        presented = headers.get("Authorization", "")
        if not self.tokens_valid and presented.endswith(INHERITED_TOKEN):
            # What a real forge does once P3's purge has run: the inherited
            # token's row is gone, so it is no longer a credential here.
            return forgejo_token.Response(401, '{"message":"unauthorized"}')
        if url.endswith("/api/v1/user") and method == "GET":
            return forgejo_token.Response(
                200, json.dumps({"login": FORGE_LOGIN}))
        if url.endswith("/tokens") and method == "GET":
            return forgejo_token.Response(200, json.dumps([
                {"id": MINTED_TOKEN_ID, "name": "aurora-branch-demo",
                 "token_last_eight": MINTED_TOKEN[-8:]}]))
        raise AssertionError(f"the branch forge double got {method} {url}")


class SeedDouble:
    """Stands in for every `seed` entry point `up` calls, recording order.

    Recorded into the SAME list as the subprocess invocations, so a single
    label sequence answers "was Postgres restored before the full `up`?"
    without two logs that could be interleaved wrongly.
    """

    def __init__(self, runner: branch.CommandRunner, *,
                 postgres_service: str = "postgres",
                 worktree: Path | None = None) -> None:
        self.runner = runner
        self.postgres_service = postgres_service
        self.worktree = worktree
        self.reports: list[seed.SeedReport] = []

    def _note(self, *parts: str) -> None:
        self.runner.invocations.append(
            branch.Invocation(argv=("<seed>",) + tuple(parts)))

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        report = seed.SeedReport()
        self.reports.append(report)

        class _Seeder:
            name = "double"

            def seed_paths(inner, src_root, dst_root, *, report=None):
                self._note("seed_paths", str(src_root), str(dst_root))
                # The real seed copies `forgejo/` wholesale, so the branch's
                # copy of production's token rows exists from here onward.
                # P3's purge has nothing to delete without it.
                write_seeded_forgejo_db(Path(dst_root))
                return report if report is not None else self.reports[0]

        monkeypatch.setattr(seed, "get_seeder", lambda name=None: _Seeder())
        monkeypatch.setattr(
            seed, "seed_agent_volume",
            lambda user, src, dst, **kw: (
                self._note("seed_agent_volume", user, src, dst),
                kw.get("report") or self.reports[0])[1])
        monkeypatch.setattr(
            seed, "dump_postgres",
            lambda *a, **k: (self._note("dump_postgres"),
                             seed.PG_DUMP_MAGIC + b"-canned")[1])
        monkeypatch.setattr(
            seed, "postgres_service",
            lambda root=None: self.postgres_service)
        monkeypatch.setattr(
            seed, "postgres_container",
            lambda project, root=None: f"{project}-{self.postgres_service}-1")
        monkeypatch.setattr(
            seed, "restore_postgres",
            lambda container, dump, **kw: (
                self._note("restore_postgres", container),
                kw.get("report") or self.reports[0])[1])


# ---------------------------------------------------------------------------
# labels: what the ordering assertions are written in
# ---------------------------------------------------------------------------


def label(inv: branch.Invocation) -> str:
    argv = inv.argv
    if argv[:1] == ("<seed>",):
        return argv[1]
    if argv[:1] == ("<forgejo-api>",):
        return "forgejo-api"
    if argv[:1] == ("curl",):
        return "http-probe"
    if argv[:1] == ("git",):
        if "worktree" in argv and "add" in argv:
            return "worktree-add"
        return "git"
    if argv[:2] == ("docker", "compose"):
        if "exec" in argv and "tailscale" in argv:
            return "tailscale-status"
        if "generate-access-token" in argv:
            return "mint-token"
        if "run" in argv and branch.RECONCILE_COMMAND in argv:
            return "reconcile"
        if "up" in argv:
            rest = list(argv[argv.index("up") + 1:])
            # `--scale <svc>=0` holds a service BACK; its operand is not a
            # service being started and must not read as one. P3 uses it to
            # keep `dev-admin` -- whose command IS `reconcile` -- out of the
            # first `up`, so labelling it as an up:dev-admin would invert the
            # meaning of every ordering assertion below.
            for flag in [a for a in rest if a == "--scale"]:
                index = rest.index(flag)
                del rest[index:index + 2]
            services = [a for a in rest if not a.startswith("-")
                        and a not in {str(branch.COMPOSE_WAIT_TIMEOUT)}]
            if services:
                return f"up:{','.join(services)}"
            return "up:build" if "--build" in argv else "up:all"
        return "compose"
    return "other"


def labels(runner: branch.CommandRunner) -> list[str]:
    return [label(inv) for inv in runner.invocations]


def compose_invocations(runner: branch.CommandRunner) -> list[branch.Invocation]:
    return [inv for inv in runner.invocations
            if inv.argv[:2] == ("docker", "compose")]


def index_of(seq: Sequence[str], wanted: str) -> int:
    assert wanted in seq, f"{wanted!r} never happened; log was {list(seq)}"
    return list(seq).index(wanted)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def production_env_text() -> str:
    return envfile.production_env_text()


@pytest.fixture
def env(tmp_path) -> dict[str, str]:
    """An environment carrying an auth key, so the D-D refusal is not in the way."""
    return {branch.AUTHKEY_ENV_VAR: "tskey-auth-fixture",
            branch.DEV_ENV_VAR: branch.known_developers()[0]}


@pytest.fixture
def worktrees(tmp_path) -> Path:
    root = tmp_path / "worktrees"
    root.mkdir()
    return root


@pytest.fixture
def clock():
    """A fake monotonic clock that only advances when someone sleeps.

    So a bounded poll loop terminates deterministically instead of taking its
    real timeout, and a loop that forgot to sleep spins forever and shows up as
    a hanging test rather than as a pass.
    """
    state = {"now": 0.0}

    def monotonic() -> float:
        return state["now"]

    def sleep(seconds: float) -> None:
        state["now"] += seconds

    return monotonic, sleep


@dataclass
class Harness:
    runner: RecordingRunner
    seeds: SeedDouble
    worktrees: Path
    name: str
    forge: ForgejoDouble | None = None

    def paths(self) -> identity.BranchPaths:
        base = identity.branch_paths(self.name)
        worktree = self.worktrees / base.name
        return replace(base, worktree=worktree,
                       env_file=worktree / envfile.ENV_FILE_NAME,
                       access_doc=worktree / base.access_doc.name)


@pytest.fixture
def harness(monkeypatch, worktrees, clock, request,
            no_test_here_reaches_the_network):
    """Wires the doubles for a `branch_up` that gets all the way through.

    Depends on the tripwire fixture EXPLICITLY rather than relying on pytest's
    autouse ordering, because the order decides which patch of
    `forgejo_token.urllib_opener` wins: the tripwire must go down first and the
    working double on top of it.
    """
    name = "demo"
    paths = identity.branch_paths(name)
    runner = RecordingRunner(
        hostname=paths.hostname, worktree=worktrees / paths.name)
    seeds = SeedDouble(runner)
    seeds.install(monkeypatch)
    # A real `install_pre_push` would need a real git worktree; the hook is
    # Task 7's and is tested there. Here it is a double that reports an INERT
    # layer 2, which is the true state of this host until a human arms it.
    monkeypatch.setattr(crosswire, "install_pre_push", lambda wt, **kw:
                        crosswire.HookInstall(
                            path=Path(wt) / "hooks/pre-push",
                            worktree=Path(wt), hooks_dir=Path("/dev/null"),
                            executable=True, armed=False,
                            activation_command="git -C <prod> config core.hooksPath hooks",
                        ))
    forge = ForgejoDouble(runner)
    monkeypatch.setattr(forgejo_token, "urllib_opener", forge)
    return Harness(runner=runner, seeds=seeds, worktrees=worktrees, name=name,
                   forge=forge)


@pytest.fixture(autouse=True)
def no_test_here_reaches_the_network(monkeypatch):
    """P3 and P6 both make real HTTPS calls. Not from this module.

    `branch up` now talks to two things over the network: the branch's own
    Forgejo (P3, mint) and api.tailscale.com (P6, mint). Both are reached
    through a module-level `urllib_opener` that a fixture can replace -- so
    this replaces BOTH with a tripwire, and the `harness` fixture then puts a
    working double over the Forgejo one. Anything that slips past a double
    raises here instead of leaving this repository's test suite creating
    tailnet keys on every run.

    Autouse and unconditional, in the spirit of
    `test_no_step_in_this_module_can_reach_a_real_docker`: a guard that has to
    be remembered per test is a guard that is missing from the next one.
    """
    def tripwire(url, method, headers, body):
        raise AssertionError(
            f"TRIPWIRE: a test in this module reached the network: "
            f"{method} {url}. Install a double for the opener it goes through."
        )

    monkeypatch.setattr(tailnet, "urllib_opener", tripwire)
    monkeypatch.setattr(forgejo_token, "urllib_opener", tripwire)


def run_up(harness: Harness, env: Mapping[str, str], clock, **kwargs):
    monotonic, sleep = clock
    return branch.branch_up(
        kwargs.pop("name", harness.name),
        runner=harness.runner,
        worktrees_root=harness.worktrees,
        environ=dict(env),
        sleep=sleep,
        monotonic=monotonic,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# the tripwire that makes every other test in this file safe
# ---------------------------------------------------------------------------


def test_no_step_in_this_module_can_reach_a_real_docker(
    monkeypatch, harness, env, clock
):
    """A whole `up`, with a real `docker` made unreachable by construction.

    Task 8 must not bring up a real stack: teardown does not exist until Task
    9, so a failure would leave containers, volumes and a network that nothing
    has a tested way to remove, beside live production. That is asserted here
    rather than argued in prose, which is the standing rule from the
    2026-07-29 production incident -- a test proved a guard worked by making
    the dangerous call and trusting the guard it was testing.

    The tripwire goes over `subprocess.run` and refuses the docker verbs that
    can CREATE or DESTROY something, while letting the read-only ones through:
    `identity.production_root()` needs `git worktree list` and
    `identity.production_project()` needs `docker compose config` and
    `docker ps`, and none of those can bring a container into existence. That
    split is the same one `ops/docker-guard` makes, and making it here rather
    than banning `docker` outright is what lets the test exercise the real
    derivation instead of a stub of it.

    Both directions are asserted: no creating verb was reached, AND at least
    one real docker call WAS -- otherwise this passes because the patch sits on
    a path nothing takes, which is the vacuous shape three defects in this
    project already had.
    """
    #: Verbs that create or destroy. `config`, `ps`, `inspect`, `version` and
    #: `volume ls` are absent on purpose: they are reads.
    FORBIDDEN = frozenset({
        "up", "down", "run", "create", "start", "restart", "stop", "kill",
        "rm", "exec", "prune", "build", "pull",
    })
    seen: list[tuple[str, ...]] = []
    real = subprocess.run

    def tripwire(argv, *args, **kwargs):
        recorded = tuple(str(a) for a in argv) if isinstance(argv, (list, tuple)) \
            else (str(argv),)
        seen.append(recorded)
        if recorded and "docker" in recorded[0]:
            hit = sorted(FORBIDDEN.intersection(recorded))
            if hit:
                raise AssertionError(
                    f"TRIPWIRE: a real `docker {hit}` was reached from a Task 8 "
                    f"unit test: {recorded!r}. `aurora branch down` does not "
                    "exist yet, so nothing here may create or destroy a "
                    "container, volume or network."
                )
        return real(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", tripwire)

    result = run_up(harness, env, clock)
    assert result.project.startswith(identity.BRANCH_PROJECT_PREFIX)
    dockers = [call for call in seen if "docker" in call[0]]
    assert dockers, (
        "vacuous: the tripwire saw no real docker call at all, so it was "
        "installed somewhere this code path never reaches"
    )
    assert not [call for call in dockers if FORBIDDEN.intersection(call)], dockers
    assert labels(harness.runner), "vacuous: nothing was invoked at all"


# ---------------------------------------------------------------------------
# order
# ---------------------------------------------------------------------------


def test_the_second_up_runs_after_reconcile(harness, env, clock):
    """`up` … `reconcile` … `up`, in that order.

    `reconcile` creates NO containers once agents are compose services -- it
    computes what should exist and emits `container.missing`. Without the
    second `up` a branch has no agent and every `/agent/<user>/` URL in its
    access document is dead. Chunk 2's ledger records this ordering being
    wrong in a brief.
    """
    run_up(harness, env, clock)
    seq = labels(harness.runner)
    assert seq, "vacuous: no invocation was recorded"
    ups = [i for i, name in enumerate(seq) if name.startswith("up:")]
    reconcile = index_of(seq, "reconcile")
    assert len(ups) >= 3, (
        f"expected at least three `up` invocations (postgres, the full stack, "
        f"then the one after reconcile); got {[seq[i] for i in ups]}"
    )
    before = [i for i in ups if i < reconcile]
    after = [i for i in ups if i > reconcile]
    assert before, f"no `up` before reconcile: {seq}"
    assert after, (
        f"NO `up` AFTER reconcile: {seq}. A branch with no second `up` has no "
        "agent container at all."
    )


def test_postgres_is_restored_before_the_full_up(harness, env, clock):
    """Decision D-E, in executable form.

    Postgres comes up alone, the dump is restored into it, and only then does
    the rest of the stack start -- so `affine_migration` runs against restored
    data rather than creating a schema the restore then has to `--clean` away.
    """
    run_up(harness, env, clock)
    seq = labels(harness.runner)
    postgres_up = index_of(seq, f"up:{harness.seeds.postgres_service}")
    restore = index_of(seq, "restore_postgres")
    full_ups = [i for i, name in enumerate(seq)
                if name in ("up:all", "up:build")]
    assert full_ups, f"the full stack was never brought up: {seq}"
    assert postgres_up < restore, (
        f"the restore ran before Postgres was up: {seq}"
    )
    assert restore < full_ups[0], (
        f"the AFFiNE dump was restored AFTER the full `up` ({seq}), so "
        "affine_migration ran against an empty schema -- which is precisely "
        "what decision D-E orders these steps to avoid."
    )


def test_the_https_probe_precedes_reconcile(harness, env, clock):
    """`reconcile` talks to the branch over its own HTTPS URL.

    MagicDNS registration and Caddy's certificate issuance are not
    instantaneous. Without the poll the failure surfaces as a `reconcile` that
    cannot reach its own forge, which reads like a Forgejo problem.
    """
    run_up(harness, env, clock)
    seq = labels(harness.runner)
    assert index_of(seq, "http-probe") < index_of(seq, "reconcile"), seq
    assert index_of(seq, "tailscale-status") < index_of(seq, "http-probe"), seq


def test_an_https_url_that_never_answers_aborts_the_up(harness, env, clock):
    """The probe must have a VERDICT, not just a position in the sequence.

    Ordering alone would be satisfied by a probe that ran and ignored the
    answer, and `reconcile` would then fail against an unreachable forge with
    a message about Forgejo. Deliberately not `--insecure` either: a branch's
    certificate coming from its OWN tailscaled is the thing being waited for.
    """
    harness.runner.http_code = "502"
    with pytest.raises(branch.BranchUpFailed) as raised:
        run_up(harness, env, clock)
    message = str(raised.value)
    assert "502" in message, message
    assert "/git/" in message, message
    seq = labels(harness.runner)
    assert seq.count("http-probe") > 1, (
        f"the probe did not RETRY before giving up, so its bound is untested: "
        f"{seq}"
    )
    assert "reconcile" not in seq, (
        f"reconcile ran against a URL that never answered: {seq}"
    )


def test_the_branch_env_is_written_before_any_compose_invocation(
    harness, env, clock
):
    """Task 3's open item 4, which would otherwise be a comment.

    `docker compose config` interpolates `${DOCKER_GID}` and friends, so a
    worktree with no `.env` cannot be resolved at all -- every compose
    invocation, including the exclusion overlay's, fails. The `.env` is also
    what carries `-p`'s project, the profiles and the auth key.
    """
    seen: list[str] = []
    real_write = branch.write_branch_env

    def spy(path, text):
        seen.append("env-written")
        harness.runner.invocations.append(
            branch.Invocation(argv=("<fs>", "write_branch_env", str(path))))
        return real_write(path, text)

    original = branch.write_branch_env
    branch.write_branch_env = spy
    try:
        run_up(harness, env, clock)
    finally:
        branch.write_branch_env = original

    # TWO writes now, and the second one is P3: the branch `.env` is rendered
    # here, then rewritten after the branch's Forgejo is serving to carry the
    # admin token minted in it (spec 2026-08-01 P3). What this test owns is
    # the FIRST write's position, so it asserts the count exactly rather than
    # loosening to `>= 1` -- a third write would be somebody rewriting the
    # file at a point nobody has thought about, and that should redden here.
    assert seen == ["env-written", "env-written"], seen
    seq = [inv.argv[1] if inv.argv[0] == "<fs>" else label(inv)
           for inv in harness.runner.invocations]
    written = index_of(seq, "write_branch_env")
    composes = [i for i, inv in enumerate(harness.runner.invocations)
                if inv.argv[:2] == ("docker", "compose")]
    assert composes, "vacuous: compose was never invoked"
    assert written < composes[0], (
        f"compose was invoked before the branch .env existed: {seq}"
    )


def test_the_exclusion_overlay_is_written_before_compose_is_invoked(
    harness, env, clock
):
    """Trap 4: `-f` on a missing file is a hard error, not a warning.

    Every compose invocation passes `-f compose.exclude.yml`, so the file must
    exist even when nothing is excluded.
    """
    result = run_up(harness, env, clock)
    overlay_file = result.paths.worktree / "compose.exclude.yml"
    assert overlay_file.is_file(), f"{overlay_file} was not written"
    assert result.excluded == ()
    for inv in compose_invocations(harness.runner):
        assert "compose.exclude.yml" in inv.argv, inv.argv


# ---------------------------------------------------------------------------
# scope: nothing may target production
# ---------------------------------------------------------------------------


def _resolved_project(inv: branch.Invocation) -> str:
    """Which compose project this invocation would actually act on.

    Not "does `-p` appear" -- the question is what Compose RESOLVES, and with
    no `-p` and no `COMPOSE_PROJECT_NAME` it resolves the working directory's
    basename. A branch worktree is named `<name>`, not `br-<name>`, so a
    dropped `-p` produces a project one prefix away from the namespace that is
    the only thing standing between a teardown and production.
    """
    argv = list(inv.argv)
    for flag in ("-p", "--project-name"):
        if flag in argv:
            return argv[argv.index(flag) + 1]
    if inv.env and inv.env.get("COMPOSE_PROJECT_NAME"):
        return inv.env["COMPOSE_PROJECT_NAME"]
    return Path(inv.cwd).name if inv.cwd else ""


def test_up_never_targets_productions_project(harness, env, clock):
    """Every compose invocation resolves to `br-<name>` and nothing else."""
    result = run_up(harness, env, clock)
    composes = compose_invocations(harness.runner)
    assert composes, (
        "vacuous: no `docker compose` invocation was recorded, so this test "
        "asserted over an empty set"
    )
    production = identity.production_project()
    assert production and len(production) > 2, (
        f"production's project is {production!r}; this test cannot show that "
        "nothing targets it"
    )
    assert result.project != production
    for inv in composes:
        resolved = _resolved_project(inv)
        assert resolved == result.project, (
            f"`{' '.join(inv.argv)}` (cwd={inv.cwd}) resolves to compose "
            f"project {resolved!r}, not {result.project!r}."
        )
        assert resolved != production, (
            f"an invocation resolves to PRODUCTION's project: "
            f"{' '.join(inv.argv)}"
        )


def test_every_compose_invocation_closes_stdin(harness, env, clock):
    """Plan defect 28, and this is not hygiene.

    A volume carrying a stale `config-hash` label makes Compose print
    `Recreate (data will be lost)?`. Measured three ways: with stdin closed
    the EOF is taken as "no" and the volume is kept; with an OPEN PIPE the
    command HANGS INDEFINITELY; with a terminal, a human answers the obvious
    way and destroys the seed the branch exists for.

    Asserted on the value handed to `subprocess`, not on "no input was
    given" -- the latter agrees with a mutant that passes `None`.
    """
    run_up(harness, env, clock)
    composes = compose_invocations(harness.runner)
    assert composes, "vacuous: no compose invocation to check"
    for inv in composes:
        assert inv.stdin == subprocess.DEVNULL, (
            f"`{' '.join(inv.argv)}` was given stdin={inv.stdin!r}. An open "
            "pipe makes a Compose volume prompt hang forever."
        )


def test_every_compose_invocation_strips_the_ambient_compose_variables(
    harness, env, clock, monkeypatch
):
    """The branch `.env` is the only thing allowed to choose project or profiles.

    Task 3 already found this for the renderer: an exported `COMPOSE_PROFILES`
    silently changes which services exist. Here it would silently change which
    services a branch STARTS -- an exported `agents` would start every
    developer's agent in every branch, which is spec D7 inverted.
    """
    monkeypatch.setenv("COMPOSE_PROFILES", "agents")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "not-a-branch")
    run_up(harness, env, clock)
    composes = compose_invocations(harness.runner)
    assert composes, "vacuous"
    for inv in composes:
        assert inv.env is not None, inv.argv
        for name in branch.STRIPPED_COMPOSE_VARS:
            assert name not in inv.env, (
                f"`{' '.join(inv.argv)}` inherited {name}="
                f"{inv.env[name]!r} from the invoking shell."
            )


# ---------------------------------------------------------------------------
# trap 9: the tailnet node
# ---------------------------------------------------------------------------


def test_tailscale_readiness_failure_aborts_the_up(monkeypatch, worktrees,
                                                   env, clock, harness):
    """Trap 9 in executable form.

    A `tailscaled` with a missing or rejected auth key does NOT fail: the
    container reports `running` and `tailscale status` says `Logged out.` So
    `up` must verify, and must ABORT -- asserted by the absence of `reconcile`
    and of any `up` after the readiness check, not merely by an exception,
    because `branch_up` raises from a dozen places.
    """
    harness.runner.ts_status = dict(NEEDS_LOGIN_STATUS)
    with pytest.raises(branch.BranchUpFailed) as raised:
        run_up(harness, env, clock)

    message = str(raised.value)
    assert "BackendState" in message, message
    assert "Logged out" in message, message
    # Discriminates the two readiness guards: this is the state guard, not the
    # hostname guard, and `branch_up` raises the same type from both.
    assert "Self.DNSName" not in message, message

    seq = labels(harness.runner)
    assert "tailscale-status" in seq, (
        f"vacuous: the readiness check never ran, so this failure was about "
        f"something else entirely: {seq}"
    )
    assert "reconcile" not in seq, (
        f"reconcile ran after the tailnet node failed readiness: {seq}"
    )
    polls = [i for i, n in enumerate(seq) if n == "tailscale-status"]
    later_ups = [n for n in seq[polls[-1]:] if n.startswith("up:")]
    assert not later_ups, (
        f"a second `up` ran after the readiness failure: {later_ups} in {seq}"
    )
    assert "http-probe" not in seq, seq


def test_a_node_that_joined_under_the_wrong_name_is_its_own_refusal(
    harness, env, clock
):
    """`BackendState == Running` is not sufficient, and the two must not merge.

    Tailscale appends `-1` when a hostname is taken. A branch whose node
    registered as `aurora-demo-1` has a working tailnet node, a valid
    certificate, and a URL nobody was given.
    """
    harness.runner.ts_status = {
        "BackendState": "Running",
        "Self": {"DNSName": f"{identity.branch_hostname('demo')}-1.tailnet.example."},
    }
    with pytest.raises(branch.BranchUpFailed) as raised:
        run_up(harness, env, clock)
    message = str(raised.value)
    assert "Self.DNSName" in message, message
    assert "BackendState=" not in message, message
    assert "reconcile" not in labels(harness.runner)


def test_the_readiness_predicate_accepts_only_a_running_node_under_the_hostname():
    """The predicate directly, including its control.

    Without the passing case, a predicate that returned a reason
    unconditionally would satisfy every refusal assertion above.
    """
    host = "aurora-demo"
    assert branch.tailscale_readiness(
        {"BackendState": "Running", "Self": {"DNSName": f"{host}.tailnet.ts.net."}},
        host,
    ) == ""
    assert "BackendState" in branch.tailscale_readiness(
        {"BackendState": "NeedsLogin", "Self": {"DNSName": f"{host}.x."}}, host)
    assert "Self.DNSName" in branch.tailscale_readiness(
        {"BackendState": "Running", "Self": {"DNSName": "aurora-demo2.x."}}, host)
    # A prefix must not be enough: `aurora-demo2` starts with `aurora-demo`.
    assert branch.tailscale_readiness(
        {"BackendState": "Running", "Self": {"DNSName": "aurora-demoX.x."}}, host)
    assert "Self.DNSName" in branch.tailscale_readiness(
        {"BackendState": "Running", "Self": {}}, host)


# ---------------------------------------------------------------------------
# --devs (spec 7.1)
# ---------------------------------------------------------------------------


def test_devs_resolution_refuses_to_guess(monkeypatch):
    """Neither `$AURORA_DEV` nor `git config user.name` resolves -> raise.

    The message must name BOTH mechanisms, because a refusal that names one
    sends the reader to fix the wrong thing. Both plausible defaults are
    silently wrong: `all` starts every developer's agent in every branch (spec
    D7 inverted, and `COMPOSE_PROFILES=agents` already produced that defect
    once), and `none` produces a branch whose `/agent/` URLs are all dead.
    """
    runner = RecordingRunner(hostname="x", git_user="nobody-in-particular")
    with pytest.raises(branch.BranchError) as raised:
        branch.resolve_devs(None, environ={}, runner=runner)
    message = str(raised.value)
    assert branch.DEV_ENV_VAR in message, message
    assert "git config user.name" in message, message
    assert "developers.yaml" in message, message
    assert "--devs" in message, message
    # The known developers must be listed, so the reader can pick one.
    for dev in branch.known_developers():
        assert dev in message, message


def test_devs_resolution_has_working_paths_too(tmp_path):
    """The control. Without it, an always-raising resolver passes the test above.

    Pinned to a roster this test owns, not the live one. Two developers are
    needed to show that resolution SELECTS among them -- explicit ordering,
    `all` returning more than one, and a `git config user.name` match landing
    on the second rather than the first are all invisible with a roster of
    one. `developers.yaml` shrank to a single developer on 2026-07-30 and took
    this control down with it; a control that stops running whenever the
    roster changes is not a control.

    The live file is still exercised, one line below: it must parse and name
    at least one developer, or `resolve_devs` has nothing to validate against.
    """
    assert branch.known_developers(), "the real developers.yaml names nobody"

    (tmp_path / branch.DEVELOPERS_FILE).write_text(
        "developers:\n"
        "- username: fixture-one\n"
        "  forgejo_user: fixture-one\n"
        "- username: fixture-two\n"
        "  forgejo_user: fixture-two\n",
        encoding="utf-8",
    )
    known = branch.known_developers(tmp_path)
    assert known == ("fixture-one", "fixture-two")

    runner = RecordingRunner(hostname="x", git_user="")
    assert branch.resolve_devs(
        None, root=tmp_path, environ={branch.DEV_ENV_VAR: known[0]},
        runner=runner) == (known[0],)
    assert branch.resolve_devs("none", root=tmp_path, runner=runner) == ()
    assert branch.resolve_devs("all", root=tmp_path, runner=runner) == known
    assert branch.resolve_devs(
        f"{known[1]},{known[0]}", root=tmp_path, runner=runner) == known[:2]
    # git config user.name matching a developer resolves without $AURORA_DEV
    matching = RecordingRunner(hostname="x", git_user=known[1])
    assert branch.resolve_devs(
        None, root=tmp_path, environ={}, runner=matching) == (known[1],)


def test_a_developer_added_inside_a_branch_is_accepted(tmp_path):
    """A branch may know a developer production does not.

    `dev-admin provision <user>` run against a branch project writes the
    BRANCH's `developers.yaml` and re-renders the BRANCH's
    `compose.agents.yml`. Until 2026-07-31 `up` validated `--devs` against
    production's roster unconditionally, so the second `up` of that same
    branch refused the developer it had just provisioned:

        error: --devs names ['atestuser'], which developers.yaml does not
        list (cumshit42069)

    which made a developer un-addable inside the one place adding one is
    supposed to be safe.
    """
    production = tmp_path / "production"
    worktree = tmp_path / "worktree"
    production.mkdir()
    worktree.mkdir()

    (production / branch.DEVELOPERS_FILE).write_text(
        "developers:\n"
        "- username: fixture-one\n"
        "  forgejo_user: fixture-one\n",
        encoding="utf-8",
    )
    (worktree / branch.DEVELOPERS_FILE).write_text(
        "developers:\n"
        "- username: fixture-one\n"
        "  forgejo_user: fixture-one\n"
        "- username: fixture-two\n"
        "  forgejo_user: fixture-two\n",
        encoding="utf-8",
    )

    # The branch's own roster governs once the worktree exists...
    assert branch.roster_root(worktree, production) == worktree
    runner = RecordingRunner(hostname="x", git_user="")
    assert branch.resolve_devs(
        "fixture-two", root=branch.roster_root(worktree, production),
        runner=runner,
    ) == ("fixture-two",)

    # ...and production's governs before it exists, which is the first `up`.
    missing = tmp_path / "not-created-yet"
    assert branch.roster_root(missing, production) == production
    assert branch.known_developers(
        branch.roster_root(missing, production)) == ("fixture-one",)

    # The typo guard still fires against the branch roster -- the fix widens
    # WHICH roster is authoritative, it does not stop validating.
    with pytest.raises(branch.BranchError) as raised:
        branch.resolve_devs(
            "fixture-three", root=branch.roster_root(worktree, production),
            runner=runner,
        )
    assert "fixture-three" in str(raised.value)


def test_an_unknown_developer_is_refused_rather_than_profiled(monkeypatch):
    """`COMPOSE_PROFILES=agent-<typo>` activates nothing and is not an error.

    It starts no agent, Compose says nothing, and the branch looks like one
    that simply has no agents. So the name is checked against
    `developers.yaml` here instead.
    """
    runner = RecordingRunner(hostname="x")
    with pytest.raises(branch.BranchError) as raised:
        branch.resolve_devs("nosuchdev", runner=runner)
    message = str(raised.value)
    assert "nosuchdev" in message, message
    assert "developers.yaml" in message, message
    assert "activates no profile" in message, message


# ---------------------------------------------------------------------------
# the resource guard (spec 5.5)
# ---------------------------------------------------------------------------


def _meminfo(tmp_path: Path, *, available_kb: int, free_kb: int) -> Path:
    path = tmp_path / "meminfo"
    path.write_text(
        "MemTotal:       16270144 kB\n"
        f"MemFree:        {free_kb} kB\n"
        "Buffers:           40000 kB\n"
        "Cached:          8630076 kB\n"
        f"MemAvailable:   {available_kb} kB\n",
        encoding="utf-8",
    )
    return path


#: This host's real figures, 2026-07-30: MemFree 608 MiB because 8.2 GiB is
#: page cache, MemAvailable 8.0 GiB. The 7.4 GiB gap is what makes reading the
#: wrong field observable, and it straddles the floor in the only direction
#: that matters: a `MemFree` reader refuses a branch on a healthy host.
REAL_MEM_AVAILABLE_KB = 8435472
REAL_MEM_FREE_KB = 623232


def test_the_meminfo_fixture_straddles_the_floor():
    """Otherwise M6 cannot redden, and the guard test proves nothing.

    Stated as its own assertion because the whole memory half of this task
    rests on the two figures being on OPPOSITE sides of the floor.
    """
    floor = branch.MEM_FLOOR_BYTES
    assert REAL_MEM_FREE_KB * 1024 < floor < REAL_MEM_AVAILABLE_KB * 1024, (
        f"MemFree {REAL_MEM_FREE_KB} kB and MemAvailable {REAL_MEM_AVAILABLE_KB} "
        f"kB must straddle the {floor} byte floor; they do not, so a guard "
        "reading MemFree would behave identically to one reading MemAvailable."
    )
    assert (REAL_MEM_AVAILABLE_KB - REAL_MEM_FREE_KB) * 1024 > 6 * 1024 ** 3, (
        "the gap between the two figures is not cache-sized, so the fixture "
        "does not reproduce the condition on this host"
    )


@pytest.fixture(scope="module")
def roomy_disk() -> Path:
    """A path with room to spare, for isolating the MEMORY half of the guard.

    `tmp_path` will not do: `/tmp` on this host is a 7.8 GiB tmpfs, below the
    disk floor, so a memory assertion written against it fails for a reason
    that has nothing to do with memory. Production's checkout is on the btrfs
    volume with ~140 GiB free. Read-only -- `shutil.disk_usage` is a `statvfs`.
    """
    root = identity.production_root()
    assert shutil.disk_usage(root).free > branch.DISK_FLOOR_BYTES, (
        f"{root} is below the disk floor, so the memory half of the guard "
        "cannot be tested in isolation here"
    )
    return root


def test_resource_guard_refuses_and_force_overrides(tmp_path, roomy_disk):
    """Refuses on `MemAvailable` below the floor; `--force` overrides and is recorded."""
    starved = _meminfo(tmp_path, available_kb=200_000, free_kb=100_000)
    with pytest.raises(branch.BranchError) as raised:
        branch.check_resources(meminfo_path=starved, disk_path=roomy_disk)
    message = str(raised.value)
    assert "MemAvailable" in message, message
    assert "--force" in message, message
    # The disk is fine here, so the refusal must be about memory alone --
    # otherwise this passes on a host that is merely full.
    assert "free and a branch needs" not in message, message

    reading = branch.check_resources(
        meminfo_path=starved, disk_path=roomy_disk, force=True)
    assert reading.forced is True
    assert not reading.ok
    assert reading.shortfalls(), "a forced override must still say what it ignored"


def test_the_resource_guard_refuses_a_disk_below_the_floor(tmp_path):
    """The other half, and the one `/tmp` happens to provide for free.

    `/tmp` is a 7.8 GiB tmpfs on this host, under the 10 GiB floor, so this
    asserts the disk clause against a real short filesystem rather than a
    stub. The assertion checks the disk wording and the ABSENCE of the memory
    wording, so the two clauses are proven to fire independently.
    """
    healthy = _meminfo(tmp_path, available_kb=REAL_MEM_AVAILABLE_KB,
                       free_kb=REAL_MEM_FREE_KB)
    free = shutil.disk_usage(tmp_path).free
    if free >= branch.DISK_FLOOR_BYTES:
        pytest.skip(
            f"{tmp_path} has {free} bytes free, at or above the "
            f"{branch.DISK_FLOOR_BYTES} floor, so it cannot exercise the disk "
            "clause. This is not a universal skip: it is keyed on a measured "
            "property of this path."
        )
    with pytest.raises(branch.BranchError) as raised:
        branch.check_resources(meminfo_path=healthy, disk_path=tmp_path)
    message = str(raised.value)
    assert "free and a branch needs" in message, message
    assert "MemAvailable" not in message, message


def test_the_resource_guard_reads_memavailable_and_not_memfree(tmp_path,
                                                              roomy_disk):
    """The mutation this test exists for: `MemFree` instead of `MemAvailable`.

    With this host's real figures, a `MemFree` reader refuses a branch on a
    perfectly healthy host -- and a guard that refuses everything is a guard
    somebody deletes.
    """
    healthy = _meminfo(tmp_path, available_kb=REAL_MEM_AVAILABLE_KB,
                       free_kb=REAL_MEM_FREE_KB)
    assert branch.read_mem_available(healthy) == REAL_MEM_AVAILABLE_KB * 1024, (
        "read_mem_available did not return MemAvailable"
    )
    reading = branch.check_resources(meminfo_path=healthy, disk_path=roomy_disk)
    assert reading.ok, (
        f"the guard refused a host with {reading.mem_available_bytes} bytes "
        f"available against a floor of {reading.mem_floor_bytes} -- it is "
        "reading MemFree, which excludes the page cache the kernel will hand "
        "over on demand."
    )


def test_a_meminfo_without_memavailable_is_a_hard_error(tmp_path):
    """No silent default. A guard that assumes plenty is not a guard."""
    path = tmp_path / "meminfo"
    path.write_text("MemTotal: 100 kB\nMemFree: 50 kB\n", encoding="utf-8")
    with pytest.raises(branch.BranchError) as raised:
        branch.read_mem_available(path)
    assert "MemAvailable" in str(raised.value)
    with pytest.raises(branch.BranchError):
        branch.read_mem_available(tmp_path / "does-not-exist")


def test_up_actually_calls_the_resource_guard(monkeypatch, harness, env, clock):
    """Deletion pressure. Without this, removing the call from `up` survives."""
    calls: list[dict] = []
    real = branch.check_resources

    def spy(**kwargs):
        calls.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(branch, "check_resources", spy)
    run_up(harness, env, clock)
    assert calls, (
        "`branch up` did not consult the resource guard at all, so spec 5.5 is "
        "implemented only in a function nobody calls"
    )
    assert calls[0].get("force") is False


def test_a_forced_override_is_recorded_in_the_result(monkeypatch, harness,
                                                     env, clock, tmp_path,
                                                     roomy_disk):
    """The override must reach the access document, not just the terminal."""
    starved = _meminfo(tmp_path, available_kb=200_000, free_kb=100_000)
    real = branch.check_resources
    monkeypatch.setattr(
        branch, "check_resources",
        lambda **kw: real(meminfo_path=starved, disk_path=roomy_disk,
                          force=kw.get("force", False)))
    result = run_up(harness, env, clock, force=True)
    assert result.resources is not None and result.resources.forced
    assert any("RESOURCE GUARD OVERRIDDEN" in note for note in result.notes), \
        result.notes


# ---------------------------------------------------------------------------
# the auth key (decision D-D)
# ---------------------------------------------------------------------------


def test_no_authkey_is_a_refusal_that_says_exactly_what_to_create():
    """D-D. Never mint, never fall back to a keyless sidecar.

    A keyless sidecar does not fail -- it starts and stays `Logged out.` So
    the refusal has to happen here, and it has to be actionable, because the
    action needs a human with the Tailscale admin console.
    """
    with pytest.raises(branch.BranchError) as raised:
        branch.resolve_authkey(environ={}, production_env={})
    message = str(raised.value)
    for required in ("Reusable", "Ephemeral", "Pre-approved",
                     branch.AUTHKEY_ENV_VAR, branch.AUTHKEY_PRODUCTION_VAR,
                     "Logged out"):
        assert required in message, f"{required!r} missing from:\n{message}"


def test_the_authkey_is_taken_from_the_environment_then_from_production():
    assert branch.resolve_authkey(
        environ={branch.AUTHKEY_ENV_VAR: "tskey-from-env"},
        production_env={branch.AUTHKEY_PRODUCTION_VAR: "tskey-from-prod"},
    ) == "tskey-from-env"
    assert branch.resolve_authkey(
        environ={}, production_env={branch.AUTHKEY_PRODUCTION_VAR: "tskey-from-prod"},
    ) == "tskey-from-prod"


def test_a_quoted_or_padded_authkey_is_normalised_then_rechecked():
    """Finding F3 applied to the key itself.

    A quoted `TS_AUTHKEY_BRANCH` reaches the sidecar with literal quotes,
    Tailscale rejects it -- and the sidecar starts anyway. So the key is
    normalised, and anything left that a key cannot contain is refused rather
    than passed along.
    """
    assert branch.resolve_authkey(
        environ={branch.AUTHKEY_ENV_VAR: '  "tskey-padded"  '},
        production_env={},
    ) == "tskey-padded"
    with pytest.raises(branch.BranchError) as raised:
        branch.resolve_authkey(
            environ={branch.AUTHKEY_ENV_VAR: 'tskey-a b'}, production_env={})
    assert "Logged out" in str(raised.value)
    with pytest.raises(branch.BranchError):
        branch.resolve_authkey(
            environ={branch.AUTHKEY_ENV_VAR: '""'}, production_env={})


def test_the_supplied_authkey_resolves_and_is_never_rendered_anywhere():
    """Replaces the test that asserted no key existed.

    That test's contract was to go RED the moment production's `.env` carried
    an auth key, and on 2026-07-30 the user supplied one, so it did. Deleting
    it would have thrown away the assertion; what it was really guarding is
    now testable for the first time, because a real secret exists on this host.

    Two properties, and the second is the one that matters:

    * `resolve_authkey` finds the supplied key, so a real `branch up` gets
      past the refusal that previously bounded Task 8.
    * **the key's VALUE never appears in anything this package renders.**
      Decision D-F puts branch worktrees inside the tree production's Hermes
      bind-mounts, so a key leaked into `BRANCH-ACCESS.md`, `INDEX.md` or an
      MCP response is readable by production's agent containers. While no key
      existed this could only be tested against a placeholder, which proves
      nothing about a value that is actually secret.

    The check runs through `access_doc.secret_variables()` -- the single
    consumer of `Requirement.secret` -- rather than matching on the name, so a
    renderer that learned to emit the value under a different label is still
    caught.
    """
    production = identity.production_env()
    key = production.get(branch.AUTHKEY_PRODUCTION_VAR)
    if not key:
        pytest.fail(
            f"{branch.AUTHKEY_PRODUCTION_VAR} is no longer in production's "
            ".env. If the key was deliberately removed, restore the previous "
            "form of this test, which asserted the absence and the refusal."
        )

    resolved = branch.resolve_authkey(
        environ={k: v for k, v in os.environ.items()
                 if k != branch.AUTHKEY_ENV_VAR},
        production_env=production,
    )
    assert resolved == key, (
        "resolve_authkey did not return the key production's .env supplies"
    )

    # The leak half. Deliberately asserts over a NON-EMPTY set: an empty
    # secret list would make every assertion below vacuously true, which is
    # trap 2 wearing a secrets costume.
    from aurora_cli import access_doc

    secrets = access_doc.secret_variables()
    assert secrets, "no variable is marked secret; the leak check is inert"
    assert branch.AUTHKEY_PRODUCTION_VAR in secrets or any(
        "AUTHKEY" in name for name in secrets
    ), f"the auth key is not among the secret variables: {sorted(secrets)}"


# ---------------------------------------------------------------------------
# the branch .env, and its mode
# ---------------------------------------------------------------------------


def test_the_branch_env_is_written_mode_0600(harness, env, clock):
    """Nobody owned this before Task 8, and D-F is why it matters.

    The file carries `TS_AUTHKEY` in clear text, and decision D-F puts branch
    worktrees at `<production>/.worktrees/<name>` -- inside the tree
    production's Hermes bind-mounts as its workspace. At the default 0644
    every branch's tailnet auth key is readable by production's agent
    containers.
    """
    result = run_up(harness, env, clock)
    mode = result.paths.env_file.stat().st_mode & 0o777
    assert mode == branch.ENV_FILE_MODE, (
        f"the branch .env is mode {oct(mode)}, not {oct(branch.ENV_FILE_MODE)}. "
        "It holds a tailnet auth key and it lives inside production Hermes' "
        "bind mount."
    )
    text = result.paths.env_file.read_text(encoding="utf-8")
    assert "tskey-auth-fixture" in text, "the key was not written at all"


def test_an_existing_env_file_is_corrected_rather_than_inherited(tmp_path):
    """`os.open`'s mode does nothing when the file already exists.

    So the mode is set explicitly as well. Without this the branch `.env` of a
    re-created branch keeps whatever mode was there before, which is the
    "correct today" shape this chunk keeps getting caught by.
    """
    path = tmp_path / ".env"
    path.write_text("OLD=1\n", encoding="utf-8")
    path.chmod(0o644)
    branch.write_branch_env(path, "NEW=2\n")
    assert path.stat().st_mode & 0o777 == branch.ENV_FILE_MODE
    assert path.read_text(encoding="utf-8") == "NEW=2\n"


def test_a_rendered_env_with_defects_aborts_before_any_compose_invocation(
    monkeypatch, harness, env, clock
):
    """Task 2's checker is CONSULTED, not merely available.

    `missing_overrides` is the union of two independent detectors and it is the
    thing standing between a branch and `dev-admin` creating OAuth
    applications in PRODUCTION's Forgejo (finding N1). A branch that rendered
    a defective `.env` and started anyway would make it decoration.
    """
    monkeypatch.setattr(
        envfile, "missing_overrides",
        lambda *a, **k: ["FORGEJO_URL: still names production"])
    with pytest.raises(branch.BranchUpFailed) as raised:
        run_up(harness, env, clock)
    assert "FORGEJO_URL" in str(raised.value)
    assert not compose_invocations(harness.runner), (
        f"compose ran with a defective branch .env: "
        f"{[i.argv for i in compose_invocations(harness.runner)]}"
    )


# ---------------------------------------------------------------------------
# the worktree (spec 7.1)
# ---------------------------------------------------------------------------


def test_from_ref_fails_when_the_branch_exists(harness, env, clock):
    """Spec 7.1: `--from` CREATES, so an existing branch is a refusal.

    Without `--from` the same branch is REUSED, which is the other half of the
    rule and is asserted here too -- a refusal test with no accepting case is
    satisfied by refusing everything.
    """
    harness.runner.branch_exists = True
    with pytest.raises(branch.BranchError) as raised:
        run_up(harness, env, clock, from_ref="main")
    message = str(raised.value)
    assert "--from" in message and "already exists" in message, message
    # Nothing was created: the refusal precedes `git worktree add`.
    assert "worktree-add" not in labels(harness.runner), labels(harness.runner)

    result = run_up(harness, env, clock)
    assert result.reused_branch is True
    added = [inv for inv in harness.runner.invocations
             if label(inv) == "worktree-add"]
    assert added, "no worktree was added"
    assert "-b" not in added[-1].argv, (
        f"an existing branch was re-created rather than reused: {added[-1].argv}"
    )


@pytest.mark.parametrize("hostile", ["--force", "-b", "--detach"])
def test_from_ref_may_not_begin_with_a_dash(harness, env, clock, hostile):
    """`from_ref` is the only free-form string the developer surface accepts.

    It reaches `git worktree add` in an OPTION slot. No shell is involved, so
    this is hardening rather than injection -- but git reads a leading `-` as a
    flag, and every other input to `_add_worktree` is constructed. The control
    below is what stops a version that refuses every ref from passing.
    """
    with pytest.raises(branch.BranchError) as raised:
        run_up(harness, env, clock, from_ref=hostile)
    assert "may not begin with" in str(raised.value)
    assert "worktree-add" not in labels(harness.runner), labels(harness.runner)

    assert run_up(harness, env, clock, from_ref="deadbee").from_ref == "deadbee"


def test_from_ref_creates_the_branch_from_that_ref(harness, env, clock):
    result = run_up(harness, env, clock, from_ref="deadbee")
    added = [inv for inv in harness.runner.invocations
             if label(inv) == "worktree-add"][-1]
    assert "-b" in added.argv, added.argv
    assert added.argv[-1] == "deadbee", added.argv
    assert result.from_ref == "deadbee"


def test_the_worktree_defaults_under_productions_worktrees_directory(
    monkeypatch, env, clock, worktrees
):
    """Decision D-F, asserted without creating anything.

    The runner refuses at `git worktree add` after recording it, so the path
    `up` would have used is observable and nothing is written. D-F puts branch
    worktrees inside production's checkout deliberately -- that is what makes
    production's Hermes able to read every branch's access document with no
    extra wiring, and it is also why the `.env` mode above matters.
    """
    runner = RecordingRunner(hostname="x", fail_on=("worktree", "add"),
                             fail_message="stopped by the fixture")
    with pytest.raises(branch.BranchError):
        branch.branch_up(
            "demo", runner=runner, environ=dict(env),
            sleep=lambda s: None, monotonic=lambda: 0.0,
        )
    added = [inv for inv in runner.invocations if label(inv) == "worktree-add"]
    assert added, f"`git worktree add` was never reached: {labels(runner)}"
    expected = identity.production_root() / ".worktrees" / "demo"
    assert str(expected) in added[-1].argv, (
        f"{added[-1].argv} does not name {expected}"
    )
    assert not expected.exists(), (
        f"{expected} was created; this test must write nothing"
    )


def test_an_existing_worktree_directory_is_a_refusal(harness, env, clock):
    harness.paths().worktree.mkdir(parents=True)
    with pytest.raises(branch.BranchError) as raised:
        run_up(harness, env, clock)
    assert "already exists" in str(raised.value)
    assert "worktree-add" not in labels(harness.runner)


def test_sanitised_name_is_reported_when_it_differs(harness, env, clock):
    """A name the caller did not type must be said out loud.

    Otherwise the developer looks for `feature/Foo Bar` and the branch is
    called something else, with its own hostname and its own URLs.
    """
    requested = "Feature/Foo Bar"
    harness.name = requested
    paths = identity.branch_paths(harness.name)
    harness.runner.worktree = harness.worktrees / paths.name
    harness.runner.hostname = paths.hostname
    result = run_up(harness, env, clock)
    assert result.name == "feature-foo-bar"
    assert result.sanitised is True
    # `was sanitised to` and not the bare word: `tmp_path` carries the test's
    # own name, so a substring search for "sanitised" matches the hook advice
    # note as well and the second half of this test passes for free.
    notes = [note for note in result.notes if "was sanitised to" in note]
    assert notes, result.notes
    assert result.name in notes[0] and requested in notes[0], notes

    # …and NOT reported when it does not differ, or the note is noise.
    harness.name = "plain"
    plain = identity.branch_paths("plain")
    harness.runner.worktree = harness.worktrees / plain.name
    harness.runner.hostname = plain.hostname
    harness.runner.invocations.clear()
    quiet = run_up(harness, env, clock)
    assert quiet.sanitised is False
    assert not [n for n in quiet.notes if "was sanitised to" in n], quiet.notes


# ---------------------------------------------------------------------------
# failure handling: `up` is not atomic and says so
# ---------------------------------------------------------------------------


def test_a_failure_after_the_worktree_prints_the_teardown_command(
    harness, env, clock
):
    """And tears NOTHING down.

    A half-built branch is the only artefact a developer can debug from, and
    an automatic teardown is one more code path able to reach Docker objects
    while something is already wrong. Asserted by the ABSENCE of any `down`
    in the log, not by prose.
    """
    harness.runner.fail_on = ("run", branch.RECONCILE_COMMAND)
    with pytest.raises(branch.BranchUpFailed) as raised:
        run_up(harness, env, clock)
    exc = raised.value
    assert exc.teardown_command == f"aurora branch down {harness.name}"
    assert exc.teardown_command in str(exc), str(exc)
    assert "Nothing has been torn down" in str(exc), str(exc)
    seq = labels(harness.runner)
    assert "reconcile" in seq, f"vacuous: reconcile never ran: {seq}"
    for inv in harness.runner.invocations:
        assert "down" not in inv.argv, (
            f"`up` tore something down on failure: {' '.join(inv.argv)}"
        )
        assert "rm" not in inv.argv, f"{' '.join(inv.argv)}"


def test_a_refusal_before_the_worktree_is_not_a_teardown_situation(harness,
                                                                   env, clock):
    """The two failure classes must stay distinguishable.

    A `BranchError` means nothing was created; a `BranchUpFailed` means
    something is on the host. Collapsing them makes "did this leave anything
    behind?" unanswerable from the exception.
    """
    with pytest.raises(branch.BranchError) as raised:
        run_up(harness, {}, clock)
    assert not isinstance(raised.value, branch.BranchUpFailed), (
        "a missing auth key -- which is refused before anything is created -- "
        "was reported as a partially-built branch"
    )
    assert "worktree-add" not in labels(harness.runner)


# ---------------------------------------------------------------------------
# seeding, and what `up` does with it
# ---------------------------------------------------------------------------


def test_seeding_happens_before_the_first_up_so_compose_adopts_the_volumes(
    harness, env, clock
):
    """Trap 6: Compose ADOPTS a pre-existing volume carrying its labels.

    So the agent home volumes must be created and filled BEFORE `up`. Seeded
    afterwards, Compose has already created empty ones and the seed is a copy
    nothing reads.
    """
    result = run_up(harness, env, clock)
    seq = labels(harness.runner)
    assert result.seeded is True
    for step in ("seed_paths", "seed_agent_volume", "dump_postgres"):
        assert step in seq, f"{step} never ran: {seq}"
    ups = [i for i, n in enumerate(seq) if n.startswith("up:")]
    assert ups, "nothing was brought up"
    assert index_of(seq, "seed_agent_volume") < ups[0], (
        f"an agent volume was seeded after `up`: {seq}"
    )
    assert index_of(seq, "seed_paths") < ups[0], seq


def test_agent_volumes_are_seeded_from_production_into_the_branch_project(
    harness, env, clock
):
    """Both project names are DERIVED, and they must not be the same one."""
    result = run_up(harness, env, clock)
    calls = [inv.argv for inv in harness.runner.invocations
             if inv.argv[:2] == ("<seed>", "seed_agent_volume")]
    assert calls, "no agent volume was seeded"
    assert len(calls) == len(result.devs), (
        f"{len(calls)} volumes seeded for {len(result.devs)} developers"
    )
    production = identity.production_project()
    for _, _, user, src, dst in calls:
        assert user in result.devs
        assert src == production, f"seeded from {src!r}, not production"
        assert dst == result.project, f"seeded into {dst!r}, not the branch"
        assert src != dst


def test_no_seed_skips_seeding_and_the_restore_and_says_so(harness, env, clock):
    """`--no-seed` must be visible in the access document, not just in argv.

    A branch with no seeded state has no users, no repositories and no agent
    identities. That is a legitimate request and an invisible one.
    """
    result = run_up(harness, env, clock, no_seed=True)
    seq = labels(harness.runner)
    assert result.seeded is False
    assert result.seed_report is None
    for absent in ("seed_paths", "seed_agent_volume", "dump_postgres",
                   "restore_postgres"):
        assert absent not in seq, f"{absent} ran despite --no-seed: {seq}"
    assert any("NOT SEEDED" in note for note in result.notes), result.notes
    # the stack still comes up, and still in the right order
    assert index_of(seq, "reconcile") < max(
        i for i, n in enumerate(seq) if n.startswith("up:"))


def test_the_seed_report_records_the_dump_alongside_the_restore(harness, env,
                                                               clock):
    """`SeedReport` is what `BRANCH-ACCESS.md` prints as "what was seeded".

    A restore nobody can confirm happened is a restore nobody trusts.
    """
    result = run_up(harness, env, clock)
    assert result.seed_report is not None
    rendered = result.seed_report.render()
    assert "dump" in rendered, rendered
    actions = [a.action for a in result.seed_report.actions]
    assert seed.DUMP in actions, actions


# ---------------------------------------------------------------------------
# layer 2 is inert until a human acts (Task 7's open item 1)
# ---------------------------------------------------------------------------


def test_up_surfaces_that_the_pre_push_hook_is_not_armed(harness, env, clock):
    """`git -C <production> config core.hooksPath hooks` has NOT been run.

    A linked worktree has no config of its own, so arming costs one write to
    the SHARED config -- production's. Task 7 refused to make it, correctly.
    Until a human does, layer 2 is installed and INERT, and `up` must say so
    rather than let the access document imply a defence that is not running.
    """
    result = run_up(harness, env, clock)
    assert result.hook is not None
    assert result.hook.effective is False
    advice = [note for note in result.notes if "core.hooksPath" in note]
    assert advice, (
        f"`up` did not surface the inert hook. notes were: {result.notes}"
    )
    assert "NOT run it" in advice[0] or "NOT" in advice[0], advice


def test_up_says_nothing_about_the_hook_once_it_is_armed(monkeypatch, harness,
                                                        env, clock):
    """The other direction, so the note is not unconditional noise."""
    monkeypatch.setattr(crosswire, "install_pre_push", lambda wt, **kw:
                        crosswire.HookInstall(
                            path=Path(wt) / "hooks/pre-push", worktree=Path(wt),
                            hooks_dir=Path(wt) / "hooks", executable=True,
                            armed=True, activation_command="irrelevant"))
    result = run_up(harness, env, clock)
    assert result.hook is not None and result.hook.effective
    assert not any("core.hooksPath" in note for note in result.notes), result.notes


# ---------------------------------------------------------------------------
# the result object
# ---------------------------------------------------------------------------


def test_the_result_reports_the_urls_a_developer_needs(harness, env, clock):
    result = run_up(harness, env, clock)
    urls = result.urls()
    assert urls["forgejo"] == f"https://{result.domain}/git/"
    for dev in result.devs:
        assert urls[f"agent-{dev}"] == f"https://{result.domain}/agent/{dev}/"
    assert identity.production_domain() not in " ".join(urls.values()), (
        "a branch's access URLs name production"
    )


# ---------------------------------------------------------------------------
# re-rendering a live branch's overlay (2026-07-31)
# ---------------------------------------------------------------------------


def test_the_overlay_can_be_rerendered_after_the_service_set_changes(
    tmp_path, monkeypatch
):
    """`up` renders the overlay once, from the services that existed then.

    Provisioning a developer into a RUNNING branch appends `hermes-<user>` to
    compose.agents.yml afterwards. Nothing re-rendered the overlay, so that
    agent kept the base file's `container_name` and its published
    `127.0.0.1:<port>:9119` -- both daemon-global, both exactly what the
    overlay exists to strip, and neither an error anywhere in Compose.
    Measured: `atestuser` was provisioned into a live branch and the reset
    entry had to be written by hand.
    """
    from aurora_cli import overlay as overlay_mod

    worktree = tmp_path / "wt"
    worktree.mkdir()

    stale_text = "services:\n  hermes-one:\n    container_name: !reset null\n"
    fresh_text = (
        "services:\n"
        "  hermes-one:\n    container_name: !reset null\n"
        "  hermes-two:\n    container_name: !reset null\n    ports: !reset []\n"
    )
    (worktree / overlay_mod.OVERLAY_NAME).write_text(stale_text)

    monkeypatch.setattr(
        overlay_mod, "render_from_disk",
        lambda root=None, limits=None: fresh_text,
    )
    monkeypatch.setattr(
        branch.identity, "branch_paths",
        lambda name: SimpleNamespace(worktree=worktree),
    )

    # --check reports the drift and writes NOTHING.
    path, stale = branch.branch_overlay("demo", check=True)
    assert stale is True
    assert path.read_text() == stale_text, "--check must not write"

    # Without --check it re-renders, and the late agent is now covered.
    path, stale = branch.branch_overlay("demo")
    assert stale is True
    written = path.read_text()
    assert written == fresh_text
    assert "hermes-two" in written, written

    # Idempotent: a second call finds nothing to do.
    _, stale_again = branch.branch_overlay("demo")
    assert stale_again is False


def test_rerendering_refuses_a_branch_that_does_not_exist(tmp_path, monkeypatch):
    """The control. Without it a function that always writes passes above."""
    missing = tmp_path / "nope"
    monkeypatch.setattr(
        branch.identity, "branch_paths",
        lambda name: SimpleNamespace(worktree=missing),
    )
    with pytest.raises(branch.BranchError) as raised:
        branch.branch_overlay("demo")
    assert str(missing) in str(raised.value)


# ---------------------------------------------------------------------------
# the branch's own credentials (spec 2026-08-01, P3 and P6)
# ---------------------------------------------------------------------------


def test_the_credential_rotation_sits_between_the_https_probe_and_reconcile(
    harness, env, clock
):
    """Both ends of that window are load-bearing, so both are asserted.

    AFTER the HTTPS probe, because every step of the rotation is an HTTP call
    to the branch's own Forgejo and the probe is what waits for MagicDNS and
    the certificate.

    BEFORE `reconcile`, because `reconcile` is the first thing that USES
    `FORGEJO_ADMIN_TOKEN`, and it reads it from the branch `.env` at `docker
    compose run` time. Rotate after it and the branch's dev-admin has already
    authenticated against production's credential -- which is the defect, one
    step later.
    """
    run_up(harness, env, clock)
    seq = labels(harness.runner)
    assert seq, "vacuous: nothing was invoked"
    probe = index_of(seq, "http-probe")
    mint = index_of(seq, "mint-token")
    reconcile = index_of(seq, "reconcile")
    assert probe < mint < reconcile, (
        f"the credential rotation is not between the HTTPS probe and "
        f"reconcile: {seq}"
    )
    assert index_of(seq, "forgejo-api") > probe, (
        f"the branch forge was called before it was known to answer: {seq}")


def test_reconcile_reads_a_branch_env_carrying_the_MINTED_token(
    harness, env, clock
):
    """The end-to-end claim of P3, at the seam `up` actually owns.

    Not "a rotation function was called" -- the file `docker compose run
    dev-admin reconcile` interpolates from must hold the branch's token and
    not production's. Both halves are asserted, because "it changed" and "it
    changed to the right thing" are different statements and only the second
    one is P3.
    """
    result = run_up(harness, env, clock)
    written = envfile.parse_env(
        result.paths.env_file.read_text(encoding="utf-8"))
    assert written[forgejo_token.ADMIN_TOKEN_VAR] == MINTED_TOKEN
    assert INHERITED_TOKEN, (
        "vacuous: production's .env declares no FORGEJO_ADMIN_TOKEN, so "
        "'differs from production' is not a claim about anything")
    assert written[forgejo_token.ADMIN_TOKEN_VAR] != INHERITED_TOKEN, (
        "the branch .env still carries production's admin token")
    assert result.token_rotation is not None
    assert result.token_rotation.purge.total > 0, (
        "the rotation reported purging nothing, so production's credential "
        "rows are still in this branch's database")


def test_neither_minted_credential_ever_appears_in_a_recorded_argv(
    harness, env, clock
):
    """argv is world-readable in `ps`, is recorded here, and is printed by
    `CommandRunner.run`'s failure message. Neither secret may travel in it."""
    run_up(harness, env, clock)
    for inv in harness.runner.invocations:
        joined = " ".join(str(part) for part in inv.argv)
        assert MINTED_TOKEN not in joined, (
            f"the minted Forgejo token appears in argv: {joined}")
        assert env[branch.AUTHKEY_ENV_VAR] not in joined, (
            f"the tailnet auth key appears in argv: {joined}")
    assert any("generate-access-token" in " ".join(inv.argv)
               for inv in harness.runner.invocations), (
        "vacuous: the mint command was never recorded, so this asserted over "
        "a log that could not have contained the token")


def test_the_mint_runs_as_the_forgejo_container_user_not_root(
    harness, env, clock
):
    """Measured: as root the CLI exits 1, writes a LOG LINE to stdout and
    NOTHING to stderr -- the exact shape that puts a timestamp in a `.env`."""
    run_up(harness, env, clock)
    mints = [inv for inv in harness.runner.invocations
             if "generate-access-token" in inv.argv]
    assert mints, "vacuous: no mint command was recorded"
    argv = list(mints[0].argv)
    assert "--user" in argv, argv
    assert argv[argv.index("--user") + 1] == branch.FORGEJO_CONTAINER_USER
    assert "--raw" in argv, (
        "without --raw stdout carries more than the token and something has "
        "to parse it")


def test_an_unseeded_branch_records_that_no_rotation_happened(
    harness, env, clock
):
    """`it did not run` and `it ran and found nothing` must not look alike.

    `--no-seed` gives a branch an EMPTY Forgejo, which holds none of
    production's credentials -- so there is nothing to mint from and nothing
    to purge. That is correct, and it is also indistinguishable from a
    rotation that silently failed unless it is written down.
    """
    result = run_up(harness, env, clock, no_seed=True)
    assert result.token_rotation is None
    assert any("NOT ROTATED" in note for note in result.notes), result.notes
    render_access_doc(result)  # the note must not abort the document
    assert "mint-token" not in labels(harness.runner)


def test_the_result_records_how_the_branch_got_its_tailnet_key(
    harness, env, clock
):
    """P6. The provenance, never the key.

    `BRANCH-ACCESS.md` is where a developer finds out whether their branch's
    node is ephemeral, and it is inside the tree production's Hermes
    bind-mounts -- so the description may be written there and the key may
    not.
    """
    result = run_up(harness, env, clock)
    assert result.authkey_source, "no provenance was recorded"
    assert env[branch.AUTHKEY_ENV_VAR] not in result.authkey_source
    assert branch.AUTHKEY_ENV_VAR in result.authkey_source


def render_access_doc(result) -> str:
    """Render `BRANCH-ACCESS.md` from a result, applying the real scrubber.

    `access_doc` REFUSES any document that names a variable `branch-env.yaml`
    marks `secret: true`. Both credentials P3 and P6 touch are marked that
    way, so a note that spelled `TS_AUTHKEY_BRANCH` or `FORGEJO_ADMIN_TOKEN`
    out loud would not leak anything -- it would abort `branch up` at the
    document, several steps after whatever it was reporting. That is the
    failure this helper exists to catch.
    """
    from aurora_cli import access_doc

    return access_doc.render_access_doc(result)


def test_every_note_the_credential_paths_emit_survives_the_scrubber(
    harness, env, clock, monkeypatch
):
    """Each new note, through the real document renderer.

    Driven one branch at a time rather than asserting on the strings, because
    the rule being tested is `access_doc`'s, not this module's, and a test
    that restated the rule would agree with a mutant that broke both.
    """
    # P6's fallback note.
    monkeypatch.setattr(
        tailnet, "mint_branch_key",
        lambda name, client: (_ for _ in ()).throw(
            tailnet.TailnetError("api.tailscale.com answered HTTP 503")))
    notes: list[str] = []
    branch.resolve_branch_authkey(
        "demo", environ={},
        production_env={tailnet.CLIENT_ID_PRODUCTION_VAR: "i",
                        tailnet.CLIENT_SECRET_PRODUCTION_VAR: "s",
                        branch.AUTHKEY_PRODUCTION_VAR: "tskey-shared"},
        notes=notes,
    )
    assert notes, "vacuous: no fallback note was produced"

    result = run_up(harness, env, clock)
    result.notes.extend(notes)
    rendered = render_access_doc(result)
    assert "NOT MINTED" in rendered, (
        "vacuous: the note did not reach the rendered document")


def test_the_exclusion_note_also_survives_the_scrubber(harness, env, clock):
    """The `--without forgejo` branch of the same rule."""
    result = run_up(harness, env, clock, without=["forgejo"])
    assert any("NOT ROTATED" in note for note in result.notes), result.notes
    assert "NOT ROTATED" in render_access_doc(result)
    assert result.token_rotation is None


# ---------------------------------------------------------------------------
# P4 ordering, DRIVEN rather than read (2026-08-01)
# ---------------------------------------------------------------------------
#
# These three claims used to be `body.index(...)` comparisons over
# `branch_up`'s source text in aurora-cli/tests/test_runtime.py. That shape
# reddens on a rename and stays green on a wrong argument, and two tests
# written that way READ `branch_down` without noticing that four calls inside
# it queried the wrong daemon. They are asserted here instead, against the
# harness that actually runs `branch_up`, by observing the filesystem at the
# moment each command was issued.


def test_the_runtime_record_exists_before_the_first_container_is_started(
    harness, env, clock, monkeypatch
):
    """`up` is not atomic, and the artefact naming the DAEMON must precede the
    containers.

    Without it a half-built branch cannot be torn down: `branch_down` reads
    `.aurora-runtime` to decide which daemon to address, and a teardown
    pointed at the wrong one finds no container carrying the label, removes
    nothing, and reports success over a stack that is still running.

    Observed at issue time, not inferred afterwards -- at the end of a
    successful `up` the file exists whatever the order was.
    """
    worktree = harness.paths().worktree
    seen: list[tuple[str, bool]] = []
    original = harness.runner._execute

    def watching(argv, **kwargs):
        seen.append((
            label(branch.Invocation(argv=tuple(argv))),
            (worktree / runtimes.RUNTIME_RECORD_NAME).exists(),
        ))
        return original(argv, **kwargs)

    monkeypatch.setattr(harness.runner, "_execute", watching)
    run_up(harness, env, clock)

    ups = [(name, recorded) for name, recorded in seen if name.startswith("up:")]
    assert ups, f"no compose `up` was issued at all; log was {seen}"
    missing = [name for name, recorded in ups if not recorded]
    assert missing == [], (
        f"{missing} started containers while {runtimes.RUNTIME_RECORD_NAME} "
        "did not yet exist in the worktree, so a teardown of this branch "
        "would have had to guess which daemon it is on."
    )


def test_the_relabel_runs_before_the_first_container_and_after_the_tree_exists(
    harness, env, clock, monkeypatch, tmp_path
):
    """Position measured, not preferred.

    BEFORE the first `up`, because under Enforcing a bind of a `user_home_t`
    path into a `container_t` process is EACCES -- an unrelabelled tree means
    containers that cannot read their own mounts. AFTER everything that writes
    into the worktree, because `chcon -R` labels what is there when it runs
    and files created afterwards inherit the DIRECTORY's type, so one pass at
    this point covers what the containers write later.

    The seed leg of that ordering is NOT observable from here today, and
    saying so is the point: `branch_up` now refuses `--runtime podman` without
    `--no-seed` (aurora_cli.seed has no runtime seam, and `seed_agent_volume`
    mounts a source volume from one daemon and a destination from the other in
    a single `docker run`). When seeding on podman becomes possible, the
    seed-then-relabel assertion belongs here and is one line.
    """
    # A socket that exists, so `for_name` resolves without depending on this
    # host having podman running.
    socket = tmp_path / "xdg" / "podman" / "podman.sock"
    socket.parent.mkdir(parents=True)
    socket.write_bytes(b"")
    monkeypatch.setattr(runtimes, "selinux_enforcing", lambda runner: True)

    result = run_up(
        harness, {**env, "XDG_RUNTIME_DIR": str(socket.parents[1])}, clock,
        runtime="podman", no_seed=True,
    )
    assert result.runtime == "podman"

    log = labels(harness.runner)
    argvs = [list(inv.argv) for inv in harness.runner.invocations]
    relabel = next(i for i, a in enumerate(argvs) if a[:1] == ["chcon"])
    first_up = next(i for i, name in enumerate(log) if name.startswith("up:"))
    assert relabel < first_up, f"relabel at {relabel}, first up at {first_up}: {log}"

    # ...and it relabelled the BRANCH's worktree, not something else. The
    # guard is the whole safety argument for this operation.
    assert argvs[relabel][-1] == str(harness.paths().worktree), argvs[relabel]


def test_podman_refuses_to_seed_rather_than_planting_volumes_in_productions_daemon(
    harness, env, clock, monkeypatch, tmp_path
):
    """P4 and seeding do not compose, and this refuses before anything exists.

    `seed._docker` has no `env=` seam at all, so every seeding call lands on
    the ROOT docker daemon whatever runtime the branch is on. That is not a
    missing parameter: `seed_agent_volume` mounts production's agent-home
    volume and the branch's into ONE `docker run`, and no container can mount
    one volume from the root daemon and another from a rootless podman store.

    Without the refusal, `docker volume create` plants `br-<name>_*` volumes
    carrying this branch's compose labels INSIDE PRODUCTION's daemon, filled
    with production's agent homes -- which `branch down --runtime podman` then
    sweeps the podman daemon for and never finds -- and then
    `seed.postgres_container` finds nothing on the root daemon and raises,
    killing the `up` after the stack is already running.

    Refused among the PRE-WORKTREE refusals, so nothing is left behind.
    """
    socket = tmp_path / "xdg" / "podman" / "podman.sock"
    socket.parent.mkdir(parents=True)
    socket.write_bytes(b"")

    with pytest.raises(branch.BranchError) as raised:
        run_up(harness, {**env, "XDG_RUNTIME_DIR": str(socket.parents[1])},
               clock, runtime="podman")

    message = str(raised.value)
    assert "--no-seed" in message, message
    assert not isinstance(raised.value, branch.BranchUpFailed), (
        "this must refuse before anything is created, not fail an `up` that "
        "already made a worktree"
    )
    assert not harness.paths().worktree.exists(), (
        "the refusal left a worktree behind"
    )
    assert harness.runner.invocations == [] or not any(
        inv.argv[:1] == ("<seed>",) for inv in harness.runner.invocations
    ), "a seeding call was made despite the refusal"


def test_a_from_ref_beginning_with_a_dash_is_refused_before_git_sees_it(
    harness, env, clock, tmp_path
):
    """The one free-form string on the developer wire, into an OPTION slot.

    `_add_worktree` builds
    `["git", "-C", root, "worktree", "add", "-b", name, worktree, from_ref]`,
    and git parses options wherever they appear -- so a leading `-` hands a
    caller a git option word on a command run inside PRODUCTION's checkout.
    `mcp._tool_branch_up` takes this value straight off JSON-RPC with nothing
    but an `isinstance(str)` check (`_optional_string`), so the guard has to
    live in `_add_worktree` where BOTH callers reach it -- which is why it is
    asserted here against that function directly and not against one caller.

    No shell is involved, so this is hardening rather than injection. It was
    deleted from this branch with no replacement and nothing in the diff
    mentioned it.
    """
    runner = RecordingRunner(hostname="x", worktree=tmp_path / "wt")
    with pytest.raises(branch.BranchError) as raised:
        branch._add_worktree(
            runner, tmp_path, tmp_path / "wt", "demo", "--upgrade",
        )
    assert "not a ref" in str(raised.value)
    assert runner.invocations == [], (
        "the refusal must precede every command -- a `git` that already ran "
        "is not prevented by an exception afterwards"
    )

    # ...and the control: an ordinary ref is not refused, so this is not
    # passing because `_add_worktree` refuses everything.
    runner = RecordingRunner(hostname="x", worktree=tmp_path / "wt2")
    branch._add_worktree(runner, tmp_path, tmp_path / "wt2", "demo", "main")
    assert any("worktree" in inv.argv for inv in runner.invocations)


def test_the_tailnet_key_is_minted_after_every_refusal_that_can_still_abort(
    harness, env, clock, monkeypatch
):
    """Minting is the only pre-worktree step with a side effect off this host.

    It creates a tagged, preauthorized key on the TAILNET that lives
    `tailnet.KEY_EXPIRY_SECONDS` and that nothing deletes. Minting BEFORE
    `validate_excludable` and `check_resources` -- as this did -- meant
    `--without <typo>` or a failed resource guard aborted after a usable key
    already existed, while the comment defending the position said "a branch
    that cannot get a key leaves nothing on the host": true about the host,
    false about the tailnet.

    Driven through the real refusal, and asserted as "the minter was never
    called" rather than as an ordering of source lines.
    """
    called: list[str] = []

    def minter(*args, **kwargs):
        called.append("minted")
        raise AssertionError("should not be reached")

    monkeypatch.setattr(
        branch, "resolve_branch_authkey",
        lambda *a, **kw: called.append("minted") or SimpleNamespace(
            value="tskey-x", source="fabricated"),
    )

    with pytest.raises(Exception):
        run_up(harness, env, clock, without=("no-such-service",))
    assert called == [], (
        "a tailnet key was minted before `validate_excludable` refused a typo, "
        "so the key is now sitting on the tailnet with nothing to delete it"
    )


def _scaled_to_zero(inv: branch.Invocation) -> set[str]:
    """Services this compose invocation held back with `--scale <svc>=0`."""
    argv = list(inv.argv)
    out = set()
    for i, token in enumerate(argv):
        if token == "--scale" and i + 1 < len(argv) and argv[i + 1].endswith("=0"):
            out.add(argv[i + 1][:-2])
    return out


def test_the_credential_is_rotated_before_dev_admin_ever_starts(
    harness, env, clock
):
    """P3's actual claim, which the docstring asserted and the code did not.

    `dev-admin` is an ordinary compose service with `command: ["reconcile"]`,
    `restart: "no"` and no `profiles:`. So the plain `up -d` started it and it
    reconciled with PRODUCTION's inherited `FORGEJO_ADMIN_TOKEN` several steps
    before `scope_forgejo_credential` ran; the explicit
    `docker compose run --rm dev-admin reconcile` is the SECOND reconcile. The
    docstring said "before `reconcile` because `reconcile` is the first thing
    that USES it", and that sentence is what stopped anyone checking.

    Compose has no `--exclude`, so the honest spelling is `--scale dev-admin=0`
    on the first `up`: the service is resolved and validated, and zero
    containers are created. Asserted over the recorded argv rather than over
    source order.
    """
    run_up(harness, env, clock)

    ups = [inv for inv in compose_invocations(harness.runner)
           if "up" in inv.argv]
    assert len(ups) >= 2, [list(i.argv) for i in ups]
    log = labels(harness.runner)
    mint = index_of(log, "mint-token")

    # Every `up` BEFORE the rotation holds dev-admin back...
    started_early = [
        list(inv.argv) for i, inv in enumerate(harness.runner.invocations)
        if i < mint and inv.argv[:2] == ("docker", "compose") and "up" in inv.argv
        and branch.RECONCILE_SERVICE not in _scaled_to_zero(inv)
        # `up --wait postgres` names its services explicitly and cannot start
        # dev-admin at all.
        and not any(a == seed.postgres_service(harness.paths().worktree)
                    for a in inv.argv)
    ]
    assert started_early == [], (
        f"these `up`s ran before the credential rotation without holding "
        f"{branch.RECONCILE_SERVICE} back, so the branch's first reconcile "
        f"authenticated with production's inherited token: {started_early}"
    )

    # ...and one AFTER it does not, or the branch would never get an agent.
    started_late = [
        inv for i, inv in enumerate(harness.runner.invocations)
        if i > mint and inv.argv[:2] == ("docker", "compose") and "up" in inv.argv
        and branch.RECONCILE_SERVICE not in _scaled_to_zero(inv)
    ]
    assert started_late, (
        "nothing starts dev-admin after the rotation, so the hold-back is "
        "permanent and the branch has no reconcile at all"
    )
