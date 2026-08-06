"""End-to-end acceptance for Chunk 3: a real branch stack, next to live production.

Three tiers, and WHICH ONE RAN IS PART OF THE RESULT. A tier reported as green
because it never executed is the defect class this project has shipped
repeatedly -- a universal `pytest.skip` made a Critical-severity gate inert at
every invocation its plan contained and passed review, because a skip is not a
failure.

  TIER A0 -- always runs, no branch stack, no worktree, no residue.
      The two auth-key refusals, and the measured behaviour of a sidecar handed
      a key that is not real. Every test here leaves the host exactly as it
      found it.

  TIER A1 -- a REAL branch stack, opt-in through $AURORA_ACCEPTANCE_STACK.
      Opt-in and not skip-by-default-and-forget: `test_the_live_stack_tier_is_
      opt_in_and_its_blocker_is_named` runs unconditionally, fails if the
      blocker stops being recorded, and fails if the tier is enabled while the
      blocker stands. The blocker is measured, not assumed -- see
      docs/issues/chunk3-spec-deltas.md, "teardown cannot remove a branch
      worktree".

  TIER B -- a REAL tailnet node, opt-in through $AURORA_EXPECT_TIER_B.
      The genuine `tailscale/tailscale` sidecar in place of Tier A1's
      namespace-holding stub, production's real ephemeral auth key, and the
      three readiness steps A1 has to stub. Six assertions, one per property
      that needs a tailnet identity of the branch's own: the node reaching
      `Running`, the branch's own certificate, its URL serving its own forge,
      `/agent/<user>/` proving `AGENT_UPSTREAM_MODE=service` reached the
      branch `.env`, reachability from inside PRODUCTION's Hermes container,
      and the ephemeral node leaving the tailnet on teardown. Opt-in for Tier
      A1's reason and no other -- every run leaves an undeletable worktree --
      and, like A1's, never silent:
      `test_tier_b_has_its_credential_and_a_written_way_to_run_it` runs
      unconditionally and the Tier B fixture RAISES rather than skipping.

WHY TIER A1 IS OPT-IN, measured on this host 2026-07-30 and not inherited from
anyone's prose: the Docker daemon creates bind-mount source directories inside
a branch worktree as root (`affine/data/postgres` -> uid 999 mode 700,
`forgejo/ssh` -> root, `.agent-env` -> root). The invoking user cannot unlink
them, so `git worktree remove` fails with

    error: failed to delete '<worktree>': Permission denied

and `--force` does not help -- it is a filesystem permission, not a git
refusal. A branch worktree therefore SURVIVES `aurora branch down`, and with
decision D-F it survives inside production's checkout. Until that is fixed,
every run of this tier leaves a directory behind that only root can remove, so
it must be an explicit act.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml

import conftest
from aurora_cli import branch, crosswire, envfile, exclusions, identity, overlay
from branch_harness import (
    assert_production_unchanged,
    branch_projects,
    production_snapshot,
    project_residue,
    teardown_branch_project,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"

#: The branch this acceptance run mints. One DNS label, so `identity`
#: sanitises nothing and the project is exactly `br-` + this.
BRANCH_NAME = "acceptance"

#: The developer the branch is provisioned for. Present in `developers.yaml`
#: and in production's seeded Forgejo, which is what makes the seeding
#: assertion about a real identity rather than about an empty table.
#: Was `testuser` until that QA account was deleted on 2026-07-30; this must
#: name a developer that really exists on both sides, not a plausible string.
BRANCH_DEV = "cumshit42069"

#: Opt-in for the live-stack tier. See the module docstring for the measured
#: reason this is not simply always-on.
STACK_ENV = "AURORA_ACCEPTANCE_STACK"

#: Tier B's credential, and the operator's way to demand it ran.
TIER_B_ENV = "AURORA_EXPECT_TIER_B"

#: Strings the seeded branch Forgejo must contain. Verified present in
#: production's live database while the plan was written: 11 users including
#: the organisation below, and 4 repositories including this one.
SEEDED_ORG = "obsidura"
SEEDED_REPO = "aurora"

STACK_SKIP_REASON = (
    f"the live-stack tier is opt-in (${STACK_ENV}=1). Each run leaves a "
    "branch worktree that only root can remove -- see the module docstring "
    "and docs/issues/chunk3-spec-deltas.md. "
    "test_the_live_stack_tier_is_opt_in_and_its_blocker_is_named runs "
    "unconditionally so this is never a silent omission."
)

stack_tier = pytest.mark.skipif(
    os.environ.get(STACK_ENV) != "1", reason=STACK_SKIP_REASON
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=check,
        stdin=subprocess.DEVNULL,
    )


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ProductionPoller(threading.Thread):
    """Poll production's own URL for the whole up/down cycle (spec 10.3).

    `/` answers 401 by design -- production's root is behind basic auth -- so
    polling it would record a "failure" on a perfectly healthy stack and the
    assertion would have to be weakened to accept it, which is how an
    availability check stops meaning anything. `/git/` answers 200.
    """

    def __init__(self, url: str, interval: float = 2.0) -> None:
        super().__init__(daemon=True)
        self.url = url
        self.interval = interval
        self.codes: list[int | str] = []
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                with urllib.request.urlopen(self.url, timeout=10) as response:
                    self.codes.append(response.status)
            except urllib.error.HTTPError as exc:
                self.codes.append(exc.code)
            except Exception as exc:                       # noqa: BLE001
                self.codes.append(f"{type(exc).__name__}: {exc}")
            self._stop.wait(self.interval)

    def stop(self) -> None:
        self._stop.set()
        self.join(timeout=15)


#: The sidecar stub. It replaces `tailscale/tailscale` with a container that
#: does nothing but hold the network namespace open.
#:
#: This is the honest half of "prove everything up to tailnet ingress". The
#: mechanic under test is spec 4.2's: Caddy runs `network_mode:
#: service:tailscale`, keeps `eth0` on the project bridge and `127.0.0.11` in
#: `resolv.conf`, and therefore reaches `forgejo:3000` by Docker service DNS.
#: A stub holds that namespace exactly as the real sidecar does, so the DNS
#: property is genuinely exercised. What a stub CANNOT do is carry tailnet
#: traffic or obtain a certificate, and nothing in this file claims it does --
#: that is Tier B, and Tier B is blocked.
#:
#: The alternative was a real sidecar with a fabricated key, and it does not
#: work: measured on this host, containerboot handed an invalid key logs
#: `invalid key: unable to validate API key` and EXITS 1, taking the shared
#: namespace with it. `test_a_sidecar_with_an_invalid_key_exits_rather_than_
#: staying_logged_out` records that measurement, because the plan predicted the
#: opposite.
SIDECAR_STUB = {
    "tailscale": {
        "image": "alpine:latest",
        "entrypoint": ["/bin/sh", "-c"],
        "command": ["echo acceptance-stub-sidecar; exec sleep infinity"],
    }
}


def _install_sidecar_stub(real_writer):
    """Wrap `exclusions.write_exclusion_overlay` so the stub lands in the file
    Compose already reads last.

    Merged into the existing document rather than appended as text: a second
    top-level `services:` key is a YAML duplicate-key error, and Compose says
    so in a way that looks like a bug in the exclusion machinery. (It cost this
    run one iteration.)
    """

    def write(excluded, worktree):
        path = Path(real_writer(excluded, worktree))
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        document.setdefault("services", {})
        document["services"].update(SIDECAR_STUB)
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        return path

    return write


class Evidence:
    """Everything measured while the branch stack was alive.

    Captured from the daemon by the fixture, asserted by the tests. The stack
    cannot stay up for the length of a module -- it is 14 containers next to a
    live production stack on a 15 GiB host -- so the alternative to a bundle is
    one enormous test whose failure says nothing about which property broke.
    """

    def __init__(self) -> None:
        self.project = ""
        self.worktree: Path | None = None
        self.result: branch.BranchResult | None = None
        self.invocations: list[branch.Invocation] = []
        self.containers: dict[str, dict] = {}
        self.production_container_ids_before: set[str] = set()
        self.production_container_names: set[str] = set()
        self.compose_ps: list[dict] = []
        self.forgejo_query: str = ""
        self.hermes_mounts: list[str] = []
        self.dns_probe: subprocess.CompletedProcess | None = None
        self.hook_refusal: subprocess.CompletedProcess | None = None
        self.origin_url: str = ""
        self.env_text: str = ""
        self.prod_db_before: dict[str, str | None] = {}
        self.prod_db_after: dict[str, str | None] = {}
        self.availability: list[int | str] = []
        self.down: branch.DownResult | None = None
        self.residue_after: dict[str, list[str]] = {}
        self.worktree_after_teardown_exists = False
        self.worktree_undeletable: list[str] = []
        self.stub_called: list[str] = []
        #: Set when `branch up` raised. Recorded rather than propagated: a
        #: half-built branch is still on the host and still measurable, and an
        #: errored fixture would throw away every observation that would say
        #: WHY. `test_branch_up_completed_every_step_it_did_not_stub` is the
        #: assertion that keeps that from becoming a soft landing.
        self.up_error: str = ""
        self.branch_ref_deleted = False


@pytest.fixture(scope="module")
def evidence() -> Evidence:
    """One real up/down cycle, with everything measured while it is live.

    Structural safety, in the order the guards fire:
      * the project name is `br-` + a sanitised label, forced by
        `identity.branch_paths`, so nothing here can name production;
      * teardown goes through `branch.branch_down`, which asserts the project
        AND the worktree path before it issues a command;
      * the fixture asserts production unchanged from a snapshot IT captured,
        never from the one `branch_down` takes internally (Task 9's M7).
    """
    if os.environ.get(STACK_ENV) != "1":              # pragma: no cover
        raise RuntimeError(STACK_SKIP_REASON)

    ev = Evidence()
    before = production_snapshot()
    ev.production_container_ids_before = {
        c["id"] for c in before["containers"].values()
    }
    ev.production_container_names = {
        c["name"] for c in before["containers"].values()
    }

    production_root = identity.production_root()
    ev.prod_db_before = {
        name: _sha256(production_root / "forgejo" / "gitea" / name)
        for name in ("gitea.db", "gitea.db-wal")
    }

    poller = ProductionPoller(f"https://{identity.production_domain()}/git/")
    poller.start()

    # NOT under /tmp, and NOT under pytest's tmp tree. Two measured reasons,
    # both of which cost this run a detour:
    #
    #  * /tmp on this host is a 7.8 GB tmpfs, i.e. RAM. Seeding copies ~2.6 GB
    #    of production's state, and `cp --reflink=auto` cannot reflink onto
    #    tmpfs -- it silently falls back to a real copy. Three runs consumed
    #    6.4 GB of tmpfs, drove MemAvailable from 7.9 GiB to 4.0 GiB and pushed
    #    the host 5.2 GiB into swap, next to a live production stack. On the
    #    same btrfs filesystem as production's checkout the same seed costs
    #    ~2.5 MB of extents.
    #  * pytest's own tmp-dir reaper would try to delete the leftover worktree
    #    on a later session and raise, because it cannot (module docstring).
    #
    # Deliberately NOT `<production>/.worktrees/`, which is where a real
    # `aurora branch up` puts it (decision D-F): until the teardown defect is
    # fixed, a test that used the real location would leave an undeletable
    # directory inside production's checkout on every run.
    scratch_root = Path.home() / ".cache" / "aurora-acceptance"
    scratch_root.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="run-", dir=str(scratch_root)))
    ev.worktree = scratch / BRANCH_NAME

    patch = pytest.MonkeyPatch()
    runner = branch.CommandRunner()
    try:
        patch.setenv(
            branch.AUTHKEY_ENV_VAR,
            # Not a real key and it cannot become one: Tailscale keys are
            # `tskey-auth-…`. Named so a human reading `docker inspect` on a
            # stray container knows instantly what they are looking at.
            "tskey-acceptance-stub-not-a-real-key",
        )
        patch.setattr(
            exclusions, "write_exclusion_overlay",
            _install_sidecar_stub(exclusions.write_exclusion_overlay),
        )
        for step in ("await_tailnet", "await_https", "reconcile"):
            patch.setattr(
                branch._Up, step,
                (lambda label: lambda self: ev.stub_called.append(label))(step),
            )

        try:
            ev.result = branch.branch_up(
                BRANCH_NAME,
                devs=BRANCH_DEV,
                # Production's checkout is on `main`, which predates Chunk 2 --
                # a worktree created from it has no `compose.branch.yml` and
                # Compose's `-f` is a hard error on a missing file. `--from` is
                # not decoration here; see docs/issues/chunk3-spec-deltas.md.
                from_ref=_current_branch(),
                build=False,
                runner=runner,
                worktrees_root=scratch,
            )
        except branch.BranchUpFailed as exc:
            ev.up_error = str(exc)
        ev.project = f"br-{BRANCH_NAME}"
        ev.invocations = list(runner.invocations)
        env_file = ev.worktree / envfile.ENV_FILE_NAME
        if env_file.is_file():
            ev.env_text = env_file.read_text(encoding="utf-8")

        _measure_live_stack(ev)
    finally:
        patch.undo()
        try:
            ev.down = branch.branch_down(BRANCH_NAME, runner=branch.CommandRunner())
        finally:
            # Whatever `branch_down` did or did not manage, the harness sweep
            # is what guarantees no `br-` object outlives this module.
            teardown_branch_project(ev.project or f"br-{BRANCH_NAME}")

        ev.residue_after = project_residue(ev.project or f"br-{BRANCH_NAME}")
        ev.worktree_after_teardown_exists = ev.worktree.exists()
        if ev.worktree_after_teardown_exists:
            ev.worktree_undeletable = sorted(
                str(p.relative_to(ev.worktree))
                for p in ev.worktree.rglob("*")
                if _foreign_owner(p)
            )[:10]
            # Move it out of the way so git's administrative entry can be
            # pruned; the tree itself is not ours to delete.
            dead = scratch / f"UNDELETABLE-{BRANCH_NAME}"
            ev.worktree.rename(dead)
        subprocess.run(
            ["git", "worktree", "prune"], cwd=str(identity.production_root()),
            capture_output=True, check=False,
        )
        # `branch down` does NOT delete the git branch `up` created, so a
        # second cycle would hit `--from <ref> ... but <name> already exists`
        # and production's repository would accumulate one ref per branch ever
        # minted. Recorded as a defect; cleaned up here so this module leaves
        # production's ref namespace as it found it. Deleted only when it still
        # points at the commit `up` created it from, so a human's branch that
        # happens to share the name is never touched.
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
            capture_output=True, text=True, check=False,
        ).stdout.strip()
        ref = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{BRANCH_NAME}"],
            cwd=str(identity.production_root()), capture_output=True, text=True,
            check=False,
        ).stdout.strip()
        if ref and ref == head:
            ev.branch_ref_deleted = subprocess.run(
                ["git", "branch", "-D", BRANCH_NAME],
                cwd=str(identity.production_root()), capture_output=True,
                check=False,
            ).returncode == 0
        ev.prod_db_after = {
            name: _sha256(production_root / "forgejo" / "gitea" / name)
            for name in ("gitea.db", "gitea.db-wal")
        }
        poller.stop()
        ev.availability = list(poller.codes)
        assert_production_unchanged(before)

    return ev


def _current_branch() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, check=True,
    ).stdout.strip()


def _foreign_owner(path: Path) -> bool:
    try:
        return path.stat(follow_symlinks=False).st_uid != os.getuid()
    except OSError:
        return True


def _measure_live_stack(ev: Evidence) -> None:
    """Everything that can only be asked while the stack is running."""
    names = [
        line for line in _docker(
            "ps", "-a", "--filter",
            f"label={identity.PROJECT_LABEL}={ev.project}",
            "--format", "{{.Names}}",
        ).stdout.split()
        if line
    ]
    for detail in (json.loads(_docker("inspect", *names).stdout) if names else []):
        ev.containers[detail["Name"].lstrip("/")] = detail

    ps = subprocess.run(
        branch.compose_argv(ev.project, "ps", "--format", "json", "-a"),
        cwd=str(ev.worktree), env=branch.stripped_environ(),
        capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL,
    ).stdout
    for line in ps.splitlines():                # NDJSON on Compose v5.3.1
        line = line.strip()
        if line.startswith("{"):
            ev.compose_ps.append(json.loads(line))

    forgejo = _service_container(ev, "forgejo")
    if forgejo:
        ev.forgejo_query = _docker(
            "exec", forgejo, "sqlite3", "/data/gitea/gitea.db",
            "select 'ORG:'||name from user where name='%s' union all "
            "select 'REPO:'||name from repository where name='%s';"
            % (SEEDED_ORG, SEEDED_REPO),
            check=False,
        ).stdout

    hermes = _service_container(ev, "hermes")
    if hermes and hermes in ev.containers:
        ev.hermes_mounts = [
            m["Source"] for m in ev.containers[hermes].get("Mounts", [])
            if m.get("Type") == "bind"
        ]

    caddy = _service_container(ev, "caddy")
    if caddy:
        # Docker service DNS inside the sidecar's namespace. `wget` because
        # the Caddy image is busybox-based and carries no curl; a non-empty
        # HTTP status line is proof the connection was established.
        ev.dns_probe = _docker(
            "exec", caddy, "wget", "-S", "-O", "/dev/null",
            "--timeout=10", "http://forgejo:3000/", check=False,
        )

    ev.origin_url = subprocess.run(
        ["git", "remote", "get-url", "origin"], cwd=str(ev.worktree),
        capture_output=True, text=True, check=False,
    ).stdout.strip()

    hook = ev.worktree / crosswire.HOOKS_DIRNAME / crosswire.HOOK_NAME
    if hook.is_file():
        ev.hook_refusal = subprocess.run(
            ["sh", str(hook), "branchforge",
             f"https://{identity.branch_domain(BRANCH_NAME)}/git/x/y.git"],
            cwd=str(ev.worktree), capture_output=True, text=True,
            check=False, stdin=subprocess.DEVNULL,
        )


def _service_container(ev: Evidence, service: str) -> str:
    for name, detail in ev.containers.items():
        labels = detail.get("Config", {}).get("Labels", {}) or {}
        if labels.get("com.docker.compose.service") == service:
            return name
    return ""


# ---------------------------------------------------------------------------
# TIER A0 -- always runs, no stack, no worktree, no residue
# ---------------------------------------------------------------------------


def test_the_branch_overlay_refuses_to_configure_without_a_tailscale_auth_key():
    """Layer one of trap 9, at the earliest possible point: config time.

    `compose.branch.yml` declares `${TS_AUTHKEY:?…}`, so a branch with no key
    is a hard `docker compose config` error rather than a stack that starts.
    Asserted against the REAL compose binary and the REAL committed overlay,
    because the property belongs to the file, not to a Python function.
    """
    env = {
        k: v for k, v in os.environ.items()
        if k not in ("TS_AUTHKEY", "COMPOSE_PROJECT_NAME", "COMPOSE_PROFILES",
                     "COMPOSE_FILE")
    }
    env.update({
        "COMPOSE_PROJECT_NAME": "br-configprobe",
        "TS_HOSTNAME": "aurora-configprobe",
        "DOMAIN_NAME": "aurora-configprobe.example.invalid",
        "DOCKER_GID": "1001",
    })
    result = subprocess.run(
        ["docker", "compose", "-f", "compose.yml", "-f", "compose.branch.yml",
         "config"],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True,
        check=False, stdin=subprocess.DEVNULL,
    )
    output = result.stdout + result.stderr

    assert "TS_AUTHKEY" in output, output
    assert "required variable" in output, output
    # The control. Without it a compose that refused every configuration --
    # a syntax error in the overlay, say -- would satisfy the assertions above.
    env["TS_AUTHKEY"] = "tskey-configprobe-not-a-real-key"
    ok = subprocess.run(
        ["docker", "compose", "-f", "compose.yml", "-f", "compose.branch.yml",
         "config", "--quiet"],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True,
        check=False, stdin=subprocess.DEVNULL,
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr


def test_branch_up_refuses_with_no_auth_key_anywhere_and_creates_nothing():
    """Layer zero: `branch up` never reaches Compose without a key.

    The refusal happens before the worktree exists, so a refused `up` leaves
    nothing at all. Asserted, not described: the contents of production's
    `.worktrees/` are compared either side of the refusal.
    """
    worktrees = sorted(
        p.name for p in (identity.production_root() / ".worktrees").iterdir()
    )
    assert worktrees, "production has no .worktrees directory to compare against"

    with pytest.raises(branch.BranchError) as excinfo:
        branch.resolve_authkey(environ={}, production_env={})
    message = str(excinfo.value)

    assert branch.AUTHKEY_ENV_VAR in message, message
    assert branch.AUTHKEY_PRODUCTION_VAR in message, message
    assert "Reusable, Ephemeral, Pre-approved" in message, message
    # The consequence, not just the fact. A message that says "missing key"
    # and not "a keyless sidecar does not fail" invites someone to remove the
    # check.
    assert "Logged out" in message, message

    assert sorted(
        p.name for p in (identity.production_root() / ".worktrees").iterdir()
    ) == worktrees, "a refused `branch up` created something under .worktrees"
    assert f"br-{BRANCH_NAME}" not in branch_projects(), (
        "a refused `branch up` left this acceptance run's project on the daemon"
    )


def test_a_sidecar_with_an_invalid_key_exits_rather_than_staying_logged_out(tmp_path):
    """CORRECTS the plan's trap 9, by measurement.

    The plan records -- correctly -- that a sidecar with NO auth key starts
    anyway and stays `Logged out.`, and builds the readiness poll around that.
    A sidecar with an INVALID key behaves differently and the difference
    matters: containerboot runs `tailscale up`, the control plane answers
    `invalid key: unable to validate API key`, containerboot SIGTERMs
    tailscaled and the container exits 1 -- taking the shared network namespace
    with it, so `network_mode: service:tailscale` peers lose `eth0`.

    Both endings are loud, which is what trap 9 wanted. But an acceptance run
    that expected a live-but-logged-out sidecar would be debugging the wrong
    thing, and a `branch up` that reported "the sidecar is not ready" when the
    real event is "the sidecar is gone" tells its user the wrong story.

    No worktree, one throwaway project, torn down here -- so this leaves
    nothing behind.
    """
    project = f"br-acceptance-keyprobe-{os.getpid()}"
    before = production_snapshot()
    (tmp_path / "compose.yml").write_text(
        yaml.safe_dump({
            "services": {
                "tailscale": {
                    "image": "tailscale/tailscale:latest",
                    "hostname": "aurora-acceptance-keyprobe",
                    "environment": [
                        "TS_AUTHKEY=tskey-acceptance-keyprobe-not-a-real-key",
                        "TS_HOSTNAME=aurora-acceptance-keyprobe",
                        "TS_STATE_DIR=/var/lib/tailscale",
                        "TS_USERSPACE=false",
                        "TS_ACCEPT_DNS=false",
                    ],
                    "devices": ["/dev/net/tun:/dev/net/tun"],
                    "cap_add": ["NET_ADMIN", "NET_RAW"],
                },
            },
        }),
        encoding="utf-8",
    )
    try:
        subprocess.run(
            ["docker", "compose", "-p", project, "up", "-d"],
            cwd=str(tmp_path), capture_output=True, text=True, check=True,
            stdin=subprocess.DEVNULL,
        )
        container = f"{project}-tailscale-1"
        deadline = time.monotonic() + 90
        state = ""
        while time.monotonic() < deadline:
            state = _docker(
                "inspect", "-f", "{{.State.Status}}", container, check=False,
            ).stdout.strip()
            if state == "exited":
                break
            time.sleep(2)

        logs = _docker("logs", container, check=False)
        transcript = logs.stdout + logs.stderr

        assert state == "exited", (
            f"the sidecar is {state!r} after 90s with an invalid key. If it is "
            "'running', containerboot's behaviour has changed and `branch up`'s "
            "readiness poll -- and this file's stub sidecar -- rest on a stale "
            f"measurement. Logs:\n{transcript[-2000:]}"
        )
        assert "invalid key" in transcript, transcript[-2000:]
        # Discriminating: this is the line that distinguishes "rejected by the
        # control plane" from "never tried", and a container that exited for
        # any other reason would not carry it.
        assert "failed to auth tailscale" in transcript, transcript[-2000:]
    finally:
        teardown_branch_project(project)
    assert project not in branch_projects()
    assert_production_unchanged(before)


def test_tier_b_has_its_credential_and_a_written_way_to_run_it():
    """Tier B is no longer blocked, and this is what replaced the leg saying so.

    The deleted leg asserted that NO auth key existed. It was the forcing
    function to write the Tier B bodies; those are written and run, so keeping
    it would mean a suite that goes red exactly when the feature works.

    The remaining legs still earn their place, and the third is reworded
    because the document it reads was rewritten:

      1. If an operator demands Tier B ($AURORA_EXPECT_TIER_B=1) without a
         key, this FAILS -- the plan's Step 1 requirement. It also stops a
         rotated-away key from surfacing as a confusing failure deep inside
         `branch up`.
      2. If the credential disappears, this FAILS unconditionally, with the
         remediation, because Tier B's assertions are now unconditional on it:
         losing the key silently returns tailnet ingress to unproven.
      3. If `docs/post-implementation-steps.md` stops telling an operator how
         to RUN the tier, this FAILS. That file no longer contains the word
         `BLOCKED` or the variable name -- it was rewritten into a terse
         deploy sequence once the key was in place, and asserting on a word
         that deliberately went would be pinning the old document rather than
         the current one. What must survive is the runnable invocation, so
         that is what is asserted.
    """
    key = os.environ.get(branch.AUTHKEY_ENV_VAR) or identity.production_env().get(
        branch.AUTHKEY_PRODUCTION_VAR
    )

    if os.environ.get(TIER_B_ENV) == "1":
        assert key, (
            f"${TIER_B_ENV}=1 demands the tailnet tier, and there is no auth "
            f"key in ${branch.AUTHKEY_ENV_VAR} or in production's "
            f"{envfile.ENV_FILE_NAME} as {branch.AUTHKEY_PRODUCTION_VAR}. "
            "Refusing to report a pass for a tier that cannot run."
        )

    assert key, (
        "Tier B's tests exist and are unconditional on a credential that has "
        f"gone: nothing in ${branch.AUTHKEY_ENV_VAR}, and no "
        f"{branch.AUTHKEY_PRODUCTION_VAR} in production's "
        f"{envfile.ENV_FILE_NAME}. Mint a Reusable, Ephemeral, Pre-approved "
        "auth key in the Tailscale admin console and restore it; until then "
        f"${TIER_B_ENV}=1 cannot run and tailnet ingress is unproven again."
    )

    steps = (DOCS / "post-implementation-steps.md").read_text(encoding="utf-8")
    assert TIER_B_ENV in steps, (
        f"docs/post-implementation-steps.md no longer tells the operator how "
        f"to run the tailnet tier (${TIER_B_ENV})"
    )
    assert "tests/test_branch_acceptance.py" in steps, (
        "docs/post-implementation-steps.md names the tier's environment "
        "variable but not the module to run it against, which is half an "
        "instruction"
    )


def test_the_live_stack_tier_is_opt_in_and_its_blocker_is_named():
    """The live-stack tier's skip is not allowed to be silent either.

    Chunk 2 shipped a `pytest.skip` that made a Critical gate inert at every
    invocation its plan contained, and it passed review. The difference between
    that and this is this test: the omission has a name, a measured cause, a
    written record, and an assertion that goes red when the cause is fixed.
    """
    deltas = (DOCS / "issues" / "chunk3-spec-deltas.md").read_text(encoding="utf-8")
    assert STACK_ENV in deltas, (
        f"${STACK_ENV} is no longer explained in docs/issues/chunk3-spec-deltas.md"
    )
    assert "git worktree remove" in deltas and "Permission denied" in deltas, (
        "the measured blocker (the daemon creates root-owned bind sources "
        "inside a branch worktree, so teardown cannot remove it) is no longer "
        "recorded in docs/issues/chunk3-spec-deltas.md"
    )

    # The blocker is a property of the shipped teardown, checked here rather
    # than assumed: nothing in `branch_down` can remove a root-owned file, so
    # if a fix lands it will be visible as a new step and this test says to
    # re-enable the tier by default.
    source = (REPO_ROOT / "aurora-cli" / "aurora_cli" / "branch.py").read_text(
        encoding="utf-8"
    )
    assert "worktree_removed" in source, "branch_down no longer reports the worktree"


def test_dev_admin_does_not_mount_a_file_into_its_read_only_package():
    """Regression guard for a defect that reached a green suite and would have
    broken production on the first `docker compose up` after merge.

    `compose.yml` mounts the package read-only:

        - ./dev-administration:/app:ro

    Mounting a file *inside* that bind requires the mountpoint to already
    exist in the SOURCE directory, because runc cannot create one on a
    read-only filesystem. The sibling `./developers.yaml:/app/developers.yaml`
    works only because `dev-administration/developers.yaml` is a real tracked
    file — luck, not design. `compose.agents.yml` has no such file, so:

        error mounting ".../compose.agents.yml" to rootfs at
        "/app/compose.agents.yml": create mountpoint for
        /app/compose.agents.yml mount: make mountpoint: read-only file system

    Measured in both directions on 2026-07-30 with throwaway containers: the
    nested form fails exactly as above, the current form starts and reads the
    file. Fixed by mounting at `/compose.agents.yml`, outside `/app`.

    Two things make this worth a permanent test rather than a deleted one.
    `docker compose config` validates the broken form happily — config
    validation cannot see it — and it survived from the compose-agents
    migration through an entire chunk of green suites because production runs
    an older `compose.yml` that never exercised it. The rule is general, so
    the assertion is general: no file may be mounted under `/app`unless its
    mountpoint exists in `dev-administration/`.
    """
    compose = (REPO_ROOT / "compose.yml").read_text(encoding="utf-8")
    assert "./dev-administration:/app:ro" in compose, (
        "the read-only /app mount is gone; this test's premise no longer "
        "holds and the rule below needs rethinking, not deleting"
    )

    # Every `- ./x:/app/y[:opts]` line in the file, whatever it names.
    nested = re.findall(r"-\s*\./([^\s:]+):/app/([^\s:]+)", compose)
    assert nested, (
        "no file is mounted under /app at all — if that is deliberate this "
        "test is inert and should be reconsidered, not silently kept"
    )

    offenders = []
    for source, target in nested:
        mountpoint = REPO_ROOT / "dev-administration" / target
        if not mountpoint.exists():
            offenders.append(f"./{source} -> /app/{target} (no {mountpoint})")

    assert offenders == [], (
        "these mounts need runc to create a mountpoint inside a read-only "
        f"bind, which fails at container start: {offenders}. Mount outside "
        "/app, or commit a real file at that path in dev-administration/."
    )

@stack_tier
def test_the_stack_that_came_up_is_the_one_the_readiness_stubs_did_not_finish(evidence):
    """The bundle is non-degenerate, and the stubs are named in the record.

    First, because every later assertion is over this data: a fixture that
    silently produced nothing would make all of them vacuously true, which is
    trap 2 wearing a fixture costume.
    """
    assert evidence.project == f"br-{BRANCH_NAME}", evidence.project
    assert evidence.containers, "the branch stack produced no containers"
    assert len(evidence.containers) >= 10, sorted(evidence.containers)
    assert evidence.invocations, "no command was recorded for this run"
    # Spec 6.5's reconcile talks to the branch over its own HTTPS URL, so it
    # cannot run without tailnet ingress. Asserted against the argv recorder
    # rather than against the stub counter, because the recorder sees what was
    # actually dispatched to Docker -- and a `reconcile` that HAD run would be
    # a branch registering OAuth applications somewhere, which is the thing
    # finding N1 is about.
    reconciles = [
        inv for inv in evidence.invocations
        if branch.RECONCILE_COMMAND in inv.argv
        and branch.RECONCILE_SERVICE in inv.argv
    ]
    assert not reconciles, (
        f"reconcile was dispatched despite having no tailnet: {reconciles}"
    )


@stack_tier
@pytest.mark.xfail(
    strict=True,
    reason=(
        "INHERITED, not Chunk 3: `dev-admin` cannot start from a clean "
        "checkout of this branch -- see "
        "test_dev_admin_cannot_start_from_a_clean_checkout_of_this_branch and "
        "docs/issues/chunk3-spec-deltas.md. Compose therefore exits non-zero "
        "and `branch up` reports the branch incomplete, even though every "
        "other service came up. `strict=True`: when the mount is fixed this "
        "XPASSes and pytest FAILS it, which is the signal to delete both the "
        "marker and the issue entry."
    ),
)
def test_branch_up_completed_every_step_it_did_not_stub(evidence):
    """The one Tier A property this host cannot satisfy today.

    Everything before this step ran for real: the worktree, the rendered
    `.env`, the seed, `up --wait postgres`, the Postgres restore, and the whole
    stack. Only the final `docker compose up -d` return code is wrong, and it
    is wrong for a reason that has nothing to do with branching.
    """
    assert not evidence.up_error, (
        "`branch up` did not complete:\n" + evidence.up_error
    )
    assert evidence.result is not None
    # Only reachable once `up` gets past Compose: these three are the LAST
    # steps, and they are the only ones this tier stubs.
    assert evidence.stub_called == ["await_tailnet", "await_https", "reconcile"], (
        f"the stubbed steps did not run in order: {evidence.stub_called}"
    )


@stack_tier
def test_every_branch_container_carries_the_branch_project_and_collides_with_nothing(
    evidence,
):
    """Spec 5.1/5.3 isolation, asserted three ways.

    Label, name and identity. The name leg is the one that matters most: every
    service that declared `container_name` in production declares a
    daemon-global name, and a branch that failed to reset one would not merely
    collide -- it would be refused, or would steal production's name.
    """
    assert evidence.containers
    for name, detail in sorted(evidence.containers.items()):
        labels = detail.get("Config", {}).get("Labels", {}) or {}
        assert labels.get(identity.PROJECT_LABEL) == evidence.project, (
            f"{name} carries project {labels.get(identity.PROJECT_LABEL)!r}"
        )
        assert name.startswith(evidence.project), (
            f"{name} is not in the branch's name namespace -- a "
            "`container_name` survived the overlay's !reset"
        )

    collisions = set(evidence.containers) & evidence.production_container_names
    assert not collisions, f"branch containers collide with production: {collisions}"
    assert evidence.production_container_names, "no production names to compare against"


@stack_tier
def test_the_branch_publishes_no_host_port_at_all(evidence):
    """Spec 5.1: a port collision must be UNREPRESENTABLE, not merely avoided.

    `agent-authz` (9140), `arcadedb` (2424/2480) and `fjell` (9080) publish in
    production and declare no `container_name`, so they are the services a
    sloppy overlay misses -- asserted by name below, so this cannot pass by
    happening to inspect none of them.
    """
    assert evidence.compose_ps, "compose ps returned nothing for the branch"
    published = {
        row.get("Service"): row.get("Publishers")
        for row in evidence.compose_ps
        if [p for p in (row.get("Publishers") or []) if p.get("PublishedPort")]
    }
    assert not published, f"the branch published host ports: {published}"

    services = {row.get("Service") for row in evidence.compose_ps}
    for service in ("agent-authz", "arcadedb", "fjell"):
        assert service in services, (
            f"{service} is missing from the branch's `compose ps`, so this "
            "test never inspected the services that publish in production"
        )


@stack_tier
def test_the_branch_forgejo_holds_productions_seeded_identity(evidence):
    """Seeding worked, asked of the branch's OWN database inside its container.

    Both strings were verified present in production's live database while the
    plan was written, and neither is a value this code could invent.
    """
    assert evidence.forgejo_query, (
        "the branch's Forgejo answered nothing; seeding cannot be assessed"
    )
    assert f"ORG:{SEEDED_ORG}" in evidence.forgejo_query, evidence.forgejo_query
    assert f"REPO:{SEEDED_REPO}" in evidence.forgejo_query, evidence.forgejo_query


@stack_tier
def test_the_branch_binds_resolve_inside_the_branch_worktree(evidence):
    """Spec 5.2, with BOTH sides resolved.

    `/home` is a symlink to `/var/home` on this host and `docker inspect`
    reports the unresolved form, so an unresolved comparison silently never
    matches -- the bug class that let AFFiNE's bind defect through Chunk 1's
    gate. `Path.parents`, never a string prefix.
    """
    assert evidence.hermes_mounts, "the branch's hermes declared no bind mounts"
    worktree = evidence.worktree.resolve()
    production = identity.production_root().resolve()

    checked = 0
    for source in evidence.hermes_mounts:
        resolved = Path(source).resolve()
        if resolved in conftest.ALLOWED_EXTERNAL_BINDS:
            # The docker socket and friends. Allowed from outside the repo by
            # `conftest.ALLOWED_EXTERNAL_BINDS`, which is resolved at
            # definition time for exactly this comparison -- `/var/run` is a
            # symlink to `/run` on this host.
            continue
        checked += 1
        assert worktree == resolved or worktree in resolved.parents, (
            f"{source} resolves to {resolved}, which is not inside the branch "
            f"worktree {worktree}"
        )
        assert production not in resolved.parents, (
            f"{source} reaches into production's checkout at {production}"
        )
    assert checked, (
        "every one of hermes' binds was an allowed external path, so this "
        f"test asserted nothing about relativity: {evidence.hermes_mounts}"
    )


@stack_tier
def test_docker_service_dns_works_inside_the_sidecar_namespace(evidence):
    """The mechanic every `*_UPSTREAM` in a branch depends on.

    Caddy runs `network_mode: service:tailscale`. `127.0.0.1` reaches nothing
    of this stack there, so every upstream is a Docker service name, and that
    only resolves because `TS_ACCEPT_DNS=false` leaves `127.0.0.11` in the
    shared namespace's `resolv.conf`. Setting it to `true` replaces that with
    `100.100.100.100` and breaks exactly this -- Task 3's M5, unpinned until
    now.
    """
    probe = evidence.dns_probe
    assert probe is not None, "no Caddy container was found in the branch"
    transcript = probe.stdout + probe.stderr
    assert "HTTP/" in transcript, (
        "the branch's Caddy could not reach http://forgejo:3000/ from inside "
        f"the sidecar namespace:\n{transcript[-1500:]}"
    )


@stack_tier
def test_production_answered_every_poll_for_the_whole_cycle(evidence):
    """Spec 10.3: production keeps serving while a branch is minted and destroyed."""
    assert len(evidence.availability) >= 5, (
        f"the availability poller recorded only {evidence.availability!r}; a "
        "handful of samples cannot show production stayed up"
    )
    bad = [code for code in evidence.availability if code != 200]
    assert not bad, f"production did not answer 200 during the cycle: {bad}"


@stack_tier
def test_seeding_did_not_mutate_productions_forgejo_database(evidence):
    """Finding N6, with the exclusion the measurement forces.

    `gitea.db` and `gitea.db-wal` must be byte-identical. `-shm` is excluded:
    measured while planning, a READ-ONLY `VACUUM INTO` against production's
    live `.hermes/state.db` left the database and its `-wal` byte-identical and
    REWROTE `state.db-shm`, which is the mmap'd WAL index and not content. A
    whole-tree checksum would go red against a correct seeder.
    """
    assert evidence.prod_db_before["gitea.db"], "production's forgejo database is missing"
    assert evidence.prod_db_before == evidence.prod_db_after, (
        f"production's Forgejo database changed during the branch cycle:\n"
        f"  before={evidence.prod_db_before}\n  after ={evidence.prod_db_after}"
    )


@stack_tier
def test_the_branch_worktree_is_cross_wired_to_production_not_to_itself(evidence):
    """Spec 5.4 layers 1 and 2, on the worktree that was actually created."""
    assert evidence.origin_url, "the branch worktree has no `origin`"
    # Compared, never printed: production's `origin` carries a Forgejo access
    # token in its userinfo, and a failure message is the last place it should
    # appear. The hook redacts for the same reason.
    assert identity.production_domain() in evidence.origin_url, (
        "the branch worktree's `origin` does not name production's host "
        "(URL withheld: it carries a credential)"
    )
    assert identity.branch_domain(BRANCH_NAME) not in evidence.origin_url, (
        "the branch worktree's `origin` points at the BRANCH's own forge, "
        "which is destroyed with the branch (URL withheld)"
    )

    refusal = evidence.hook_refusal
    assert refusal is not None, "the pre-push hook was not installed in the worktree"
    output = refusal.stdout + refusal.stderr
    assert refusal.returncode != 0, f"the hook allowed a push to a BRANCH forge: {output}"
    # The marker, not merely a non-zero exit: git reports the same exit 1 for a
    # missing hook, so "it failed" does not prove "it ran".
    assert "aurora pre-push:" in output, output


@stack_tier
def test_teardown_left_no_branch_object_on_the_daemon(evidence):
    """Containers, volumes AND networks. A residue check that looked only at
    containers would call a half-torn-down branch clean (finding N7)."""
    assert evidence.down is not None
    assert evidence.residue_after == {"containers": [], "volumes": [], "networks": []}, (
        f"teardown left residue: {evidence.residue_after}; "
        f"notes={evidence.down.notes}"
    )
    assert evidence.down.containers_removed, (
        "branch_down reported removing no containers, so this assertion is "
        "about a teardown that had nothing to tear down"
    )


@stack_tier
def test_teardown_could_not_remove_the_worktree_and_says_which_files_stopped_it(
    evidence,
):
    """THIS TEST ASSERTS A DEFECT, on purpose, and it is the loudest thing here.

    `aurora branch down` cannot remove a branch worktree that has run the
    stack. The Docker daemon creates bind-mount sources inside it as root and
    the invoking user cannot unlink them, so `git worktree remove` fails with
    `Permission denied` and `--force` does not help.

    Written as an assertion rather than a note because the alternative is a
    green suite over a feature that leaks a directory per branch -- and with
    decision D-F that directory is inside PRODUCTION's checkout. When the fix
    lands this test goes RED, which is the correct signal to delete it, drop
    the opt-in gate on this tier, and run the second full cycle the plan asks
    for (that cycle cannot run today: it needs the first cycle's worktree
    gone).

    See docs/issues/chunk3-spec-deltas.md.
    """
    assert evidence.worktree_after_teardown_exists, (
        "the branch worktree was removed after all -- the blocker this tier's "
        "opt-in gate exists for may be fixed. Re-read "
        "docs/issues/chunk3-spec-deltas.md, run the second cycle, and remove "
        "the gate."
    )
    assert evidence.worktree_undeletable, (
        "the worktree survived teardown but carries no file owned by another "
        "user, so the recorded cause is wrong and the real one is unknown"
    )
    assert evidence.down is not None and not evidence.down.worktree_removed
    assert any("worktree remove" in note for note in evidence.down.notes), (
        f"branch_down did not report the failure: {evidence.down.notes}"
    )


# ---------------------------------------------------------------------------
# TIER B -- the branch's own tailnet identity, with the REAL sidecar
# ---------------------------------------------------------------------------
#
# WHAT THIS TIER CHANGES relative to Tier A1, precisely, because it is the
# only difference and everything Tier B is allowed to claim follows from it:
#
#   * the `tailscale` service is the real `tailscale/tailscale` image, not
#     A1's `alpine` namespace-holder, and it is handed production's real
#     ephemeral auth key instead of a string that could never be one;
#   * `await_tailnet`, `await_https` and `reconcile` are NOT stubbed. A1
#     replaced all three because each needs tailnet ingress; here they run.
#
# Nothing else differs -- same `branch_up`, same overlay, same seed. So Tier B
# does NOT re-prove isolation, zero published ports, seeding, path relativity,
# service DNS, production availability, non-mutation, cross-wiring or Docker
# teardown: Tier A1 owns those and duplicating them here would only mean two
# tests going red for one cause. Tier B asserts the six things that need a
# node of the branch's own, and the two invariants that must hold for ANY
# stack this suite starts beside production (availability, and no residue).

#: Tier B's branch. A DIFFERENT name from Tier A1's on purpose: the two tiers
#: must be enable-able in one invocation without sharing a worktree, a compose
#: project or a tailnet node name. Deliberately obvious, and deliberately
#: greppable, because defect 54 means the worktree survives teardown and a
#: human has to remove it by hand.
#:
#: OVERRIDABLE, for one measured reason and no other: ephemeral nodes are not
#: leaving this tailnet on teardown (docs/issues/chunk3-spec-deltas.md), so the
#: node `aurora-tierb` outlives its branch and the NEXT run of this tier under
#: the same name registers as `aurora-tierb-1`. `tailscale_readiness()`
#: correctly refuses that, which means the tier is un-rerunnable until a human
#: deletes the stale node in the admin console. Until it is fixed, an operator
#: needs a way to re-run without that round trip. Delete this override when
#: the deregistration defect is fixed.
TIER_B_BRANCH_NAME = os.environ.get("AURORA_TIER_B_BRANCH", "tierb")

#: The developer Tier B provisions. `cumshit42069` is in `developers.yaml` and
#: in production's seeded Forgejo, so `/agent/cumshit42069/` is a route
#: `reconcile` really generates rather than one this file invented. (Was
#: `testuser` until that QA account was deleted on 2026-07-30.)
TIER_B_DEV = "cumshit42069"

#: What an unauthenticated Hermes dashboard serves. Measured against
#: production's own agent container on 2026-07-30:
#:
#:     GET http://127.0.0.1:9119/       -> 302, Location: /login?next=%2F
#:     GET http://127.0.0.1:9119/login  -> <title>Sign in — Hermes Agent</title>
#:
#: Both legs are asserted. A 502 carries neither, and neither does a Caddy
#: answering from its own static error page -- which is what makes this
#: evidence about the agent rather than about the proxy.
HERMES_LOGIN_TITLE = "Sign in — Hermes Agent"
HERMES_LOGIN_PATH = "login"

#: The per-agent Caddy fragment `reconcile` generates and the main Caddyfile
#: imports. Read out of the RUNNING container, never off disk: the committed
#: copy is production's, in published mode, and reading that instead would
#: make assertion 4's artefact leg assert the opposite of what it claims.
AGENTS_CONF_NAME = "agents.conf"

#: How long an ephemeral node may take to leave the tailnet after its stack is
#: destroyed. Generous on purpose: a deregistration that is merely SLOW is a
#: different fact from one that never happens, and the test reports the
#: measured seconds either way.
TIER_B_DEREGISTER_TIMEOUT = 300.0
TIER_B_DEREGISTER_INTERVAL = 5.0

TIER_B_SKIP_REASON = (
    f"Tier B is opt-in (${TIER_B_ENV}=1). It registers a REAL ephemeral node "
    "on the tailnet from production's auth key and, exactly like Tier A1, "
    "leaves a branch worktree that only root can remove (defect 54). "
    "This is an opt-in, NOT a silent omission: "
    "test_tier_b_has_its_credential_and_a_written_way_to_run_it runs "
    "unconditionally, and the fixture below RAISES rather than skipping if "
    "the tier is demanded and cannot run."
)

tier_b = pytest.mark.skipif(
    os.environ.get(TIER_B_ENV) != "1", reason=TIER_B_SKIP_REASON
)

#: Credential shapes that must never survive into an assertion message, a
#: stored transcript or this repository.
#:
#: The Tailscale auth key is the obvious one, and this file never reads it:
#: `branch_up` resolves it out of production's `.env` through
#: `branch.resolve_authkey`, so this pattern is a second layer and not the
#: first.
#:
#: `FORGEJO_TOKEN` was NOT obvious, and it is here because it leaked. The
#: first Tier B run failed inside `reconcile`, and the `BranchUpFailed`
#: message carries the failing subprocess' argv verbatim -- including
#: `-H 'Authorization: token <40 hex>'`, production's Forgejo admin token,
#: inherited by the branch. It reached the pytest report. The lesson
#: generalises past this one variable: a branch inherits every secret
#: production's `.env` holds that `branch-env.yaml` does not override, and
#: ANY of them can ride out on a subprocess' argv. So the pattern set is by
#: SHAPE, not by variable name, and everything this tier stores from a
#: subprocess goes through `_redact` on the way in.
_SECRETS = (
    re.compile(r"tskey-[A-Za-z0-9_\-]+"),
    # `Authorization: token <hex>` / `token=<hex>`, and bare 40-hex Forgejo
    # access tokens wherever they appear unlabelled.
    re.compile(r"(?i)(token[\"'\s:=]+)[0-9a-f]{20,}"),
    re.compile(r"\b[0-9a-f]{40}\b"),
)


def _redact(text: str) -> str:
    """Blank every credential shape in `text`, preserving the surrounding words.

    Deliberately over-broad: a 40-hex string is also what a git SHA looks
    like, and redacting a commit id costs a reader nothing while printing an
    admin token costs them a rotation.
    """
    out = text or ""
    for pattern in _SECRETS:
        out = pattern.sub(
            lambda m: (m.group(1) if m.re.groups else "") + "<redacted>", out
        )
    return out


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Hand the 3xx back instead of following it.

    `/agent/<user>/`'s redirect IS the evidence for assertion 4 -- it is what
    Hermes answers and a 502 cannot -- so it must be observable rather than
    swallowed by the opener.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _https_get(url: str, *, follow: bool = True, timeout: float = 30.0):
    """`(status, headers, body)` over TLS, validated against the system roots.

    Never an unverified context and never `--insecure`. A branch certificate
    that chains to a public root is half of assertion 2, and a fetch that
    skipped validation would prove nothing about it -- it would happily
    accept a self-signed certificate from anything at all.
    """
    opener = (
        urllib.request.build_opener()
        if follow
        else urllib.request.build_opener(_NoRedirect)
    )
    try:
        with opener.open(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
            return response.status, dict(response.headers), body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return exc.code, dict(exc.headers), body


def _peer_certificate(domain: str, *, timeout: float = 20.0) -> dict:
    """The certificate `domain` presents on :443, as validated by the host.

    `ssl.create_default_context()` verifies the chain and the hostname, so
    reaching the `getpeercert()` line at all already means the certificate is
    publicly trusted and issued for this name.
    """
    context = ssl.create_default_context()
    with socket.create_connection((domain, 443), timeout=timeout) as raw:
        with context.wrap_socket(raw, server_hostname=domain) as tls:
            return dict(tls.getpeercert() or {})


def _san_names(cert: dict) -> set[str]:
    return {value for kind, value in cert.get("subjectAltName", ()) if kind == "DNS"}


def _issuer_values(cert: dict) -> set[str]:
    return {value for rdn in cert.get("issuer", ()) for _, value in rdn}


def _tailscale_status(argv: list[str]) -> dict:
    """`tailscale status --json`, from wherever `argv` runs it.

    Errors are RECORDED, not raised: which vantage point failed and why is
    part of the evidence, and a fixture that exploded here would throw away
    every other measurement.
    """
    result = subprocess.run(
        argv, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        return {"_error": _redact((result.stderr or result.stdout).strip())[:400]}
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return {"_error": f"`tailscale status --json` returned no JSON: {exc}"}
    return value if isinstance(value, dict) else {"_error": "status was not an object"}


def _peer_domains(status: dict) -> set[str]:
    """Every PEER's fully-qualified tailnet name, trailing dot stripped.

    `DNSName` and not `HostName`: `TS_HOSTNAME` sets the node's name, but a
    container's `HostName` is whatever the image reports, and this host's
    tailnet already contains a peer whose `HostName` is `localhost`. The
    branch's identity is its DNS name, which is also what its certificate and
    its URLs are issued for.
    """
    peers = status.get("Peer") or {}
    if not isinstance(peers, dict):
        return set()
    return {
        str(peer.get("DNSName") or "").rstrip(".")
        for peer in peers.values()
        if isinstance(peer, dict) and peer.get("DNSName")
    }


def _self_domain(status: dict) -> str:
    return str((status.get("Self") or {}).get("DNSName") or "").rstrip(".")


def _branch_container_names(project: str) -> list[str]:
    return sorted(
        line
        for line in _docker(
            "ps", "-a", "--filter", f"label={identity.PROJECT_LABEL}={project}",
            "--format", "{{.Names}}", check=False,
        ).stdout.split()
        if line
    )


def _container_named(project: str, service: str) -> str:
    """One container name, by project AND service label.

    By label rather than by `docker inspect` into a dict, deliberately: the
    sidecar's `Config.Env` carries `TS_AUTHKEY` in clear text, so this tier
    never holds a full inspect of it.
    """
    names = _docker(
        "ps", "-a",
        "--filter", f"label={identity.PROJECT_LABEL}={project}",
        "--filter", f"label={identity.SERVICE_LABEL}={service}",
        "--format", "{{.Names}}", check=False,
    ).stdout.split()
    return names[0] if names else ""


def _curl_in(container: str, url: str) -> dict:
    """`curl` from INSIDE a container, reporting only the status code.

    `docker exec` creates and destroys nothing, which is why this is safe to
    point at a PRODUCTION container: it is the only way to answer spec 10.3's
    question, which is about production's network position and not about the
    host's.
    """
    result = _docker(
        "exec", container, "curl", "-sS", "-o", "/dev/null",
        "-w", "%{http_code}", "--max-time", "20", url, check=False,
    )
    return {
        "code": result.stdout.strip(),
        "returncode": result.returncode,
        "stderr": _redact(result.stderr.strip())[:400],
    }


class TailnetEvidence:
    """Everything measured while a branch with a real tailnet node was alive.

    Same shape, and the same reason, as `Evidence`: a 14-container stack
    cannot stay up for the length of a module beside live production, so the
    fixture runs one whole up/measure/down cycle and the tests assert over the
    bundle. Nothing here holds the auth key, and every captured transcript is
    passed through `_redact` on the way in.
    """

    def __init__(self) -> None:
        self.project = ""
        self.hostname = ""
        self.domain = ""
        self.worktree: Path | None = None
        self.result: branch.BranchResult | None = None
        self.up_error = ""
        #: Appended AFTER each real step returns. This is the code-path
        #: vacuity guard for the whole tier: `await_tailnet` and `await_https`
        #: are themselves assertions, and a run in which they never executed
        #: must not look like a run in which they passed.
        self.steps_completed: list[str] = []
        self.containers: list[str] = []
        self.sidecar_container = ""
        self.caddy_container = ""
        self.sidecar_status: dict = {}
        self.host_status_before: dict = {}
        self.host_status_live: dict = {}
        self.host_status_after: dict = {}
        self.peers_before: set[str] = set()
        self.peers_live: set[str] = set()
        self.peers_after: set[str] = set()
        self.deregistered = False
        self.deregistered_seconds: float | None = None
        self.branch_cert: dict = {}
        self.branch_cert_error = ""
        self.production_cert: dict = {}
        self.production_cert_error = ""
        self.caddy_tailscale_mounts: list[dict] = []
        self.agents_conf = ""
        self.env_agent_mode = ""
        self.git_status: int | None = None
        self.git_body = ""
        self.production_git_body = ""
        self.agent_status: int | None = None
        self.agent_location = ""
        self.agent_login_status: int | None = None
        self.agent_login_body = ""
        self.hermes_container = ""
        self.hermes_probe_branch: dict = {}
        self.hermes_probe_production: dict = {}
        #: Router lines from the branch's OWN Forgejo for the OAuth2
        #: application API. Captured only when `up` failed, because that is
        #: the only time they are needed: they carry the HTTP STATUS of the
        #: request `reconcile` died on, which its own traceback does not.
        self.forgejo_oauth_log: list[str] = []
        #: sha256 of production's `gitea.db` and `gitea.db-wal`, either side of
        #: the cycle. Only the first is asserted on -- see the test.
        self.prod_db_before: dict[str, str | None] = {}
        self.prod_db_after: dict[str, str | None] = {}
        self.availability: list[int | str] = []
        self.down: branch.DownResult | None = None
        self.residue_after: dict[str, list[str]] = {}
        self.worktree_after_teardown_exists = False
        self.worktree_undeletable: list[str] = []
        self.branch_ref_deleted = False


def _spy_step(ev: TailnetEvidence, label: str, real):
    """Wrap a `_Up` step so it RUNS and is recorded, rather than replaced.

    Tier A1 replaced these three with recorders because none of them can work
    without tailnet ingress. Tier B is the tier that has it, so replacing them
    would delete the assertions: `await_tailnet` fails unless the node reports
    `BackendState == "Running"` under the requested hostname, and
    `await_https` polls the branch's own URL with certificate validation on.
    The label is appended only after the real call RETURNS, so the recorder
    cannot show a step that raised.
    """

    def wrapped(self):
        real(self)
        ev.steps_completed.append(label)

    return wrapped


def _measure_tailnet(ev: TailnetEvidence) -> None:
    """Everything that can only be asked while the branch node is on the tailnet."""
    ev.containers = _branch_container_names(ev.project)

    # -- assertion 1, vantage point one: the branch's own tailscaled --------
    ev.sidecar_container = _container_named(ev.project, overlay.SIDECAR_SERVICE)
    if ev.sidecar_container:
        ev.sidecar_status = _tailscale_status([
            "docker", "exec", ev.sidecar_container,
            "tailscale", f"--socket={branch.TAILSCALE_SOCKET}", "status", "--json",
        ])

    # -- assertion 1, vantage point two: production's own node -------------
    ev.host_status_live = _tailscale_status(["tailscale", "status", "--json"])
    ev.peers_live = _peer_domains(ev.host_status_live)

    # -- assertion 2 --------------------------------------------------------
    try:
        ev.branch_cert = _peer_certificate(ev.domain)
    except Exception as exc:                                   # noqa: BLE001
        ev.branch_cert_error = _redact(f"{type(exc).__name__}: {exc}")
    try:
        ev.production_cert = _peer_certificate(identity.production_domain())
    except Exception as exc:                                   # noqa: BLE001
        ev.production_cert_error = _redact(f"{type(exc).__name__}: {exc}")

    ev.caddy_container = _container_named(ev.project, "caddy")
    if ev.caddy_container:
        mounts = _docker(
            "inspect", "-f", "{{json .Mounts}}", ev.caddy_container, check=False,
        ).stdout.strip()
        for mount in (json.loads(mounts) if mounts.startswith("[") else []):
            if mount.get("Destination") == overlay.TAILSCALE_SOCKET_DIR:
                ev.caddy_tailscale_mounts.append({
                    "Type": mount.get("Type"),
                    "Name": mount.get("Name", ""),
                    "Source": mount.get("Source", ""),
                })
        # The artefact half of assertion 4's pair.
        ev.agents_conf = _docker(
            "exec", ev.caddy_container,
            "cat", f"/etc/caddy/Caddyfile.d/{AGENTS_CONF_NAME}",
            check=False,
        ).stdout

    # -- assertion 3 --------------------------------------------------------
    ev.git_status, _, ev.git_body = _https_get(f"https://{ev.domain}/git/")
    ev.production_git_body = _https_get(
        f"https://{identity.production_domain()}/git/"
    )[2]

    # -- assertion 4 --------------------------------------------------------
    ev.agent_status, headers, _ = _https_get(
        f"https://{ev.domain}/agent/{TIER_B_DEV}/", follow=False,
    )
    ev.agent_location = headers.get("Location", "")
    ev.agent_login_status, _, ev.agent_login_body = _https_get(
        f"https://{ev.domain}/agent/{TIER_B_DEV}/{HERMES_LOGIN_PATH}"
    )

    # The branch `.env`'s own claim. Read one variable by name and nothing
    # else: this file carries the auth key in clear text (ENV_FILE_MODE 0600
    # exists for that reason) and must not be slurped into an object a
    # failure message can print.
    env_file = (ev.worktree or Path("/nonexistent")) / envfile.ENV_FILE_NAME
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == "AGENT_UPSTREAM_MODE":
                ev.env_agent_mode = value.strip()

    # -- diagnosis, only when there is something to diagnose ---------------
    if ev.up_error:
        forgejo = _container_named(ev.project, "forgejo")
        if forgejo:
            logs = _docker("logs", "--tail", "4000", forgejo, check=False)
            ev.forgejo_oauth_log = [
                _redact(line)
                for line in (logs.stdout + logs.stderr).splitlines()
                if "applications/oauth2" in line
            ][-12:]

    # -- assertion 5 --------------------------------------------------------
    ev.hermes_container = conftest.project_containers(
        identity.production_project()
    ).get("hermes", "")
    if ev.hermes_container:
        ev.hermes_probe_branch = _curl_in(
            ev.hermes_container, f"https://{ev.domain}/git/"
        )
        # The control. If `curl` in that container could not reach ANY
        # tailnet HTTPS endpoint, a failure above would say nothing about the
        # branch -- it would say production's Hermes has no egress.
        ev.hermes_probe_production = _curl_in(
            ev.hermes_container, f"https://{identity.production_domain()}/git/"
        )


def _await_deregistration(ev: TailnetEvidence) -> bool:
    """Assertion 6: poll production's own tailscaled until the peer is gone.

    Asked of the HOST's tailscaled and not of the branch's, which no longer
    exists -- that is the point. A NON-ephemeral registration would leave the
    node listed and offline forever, so absence here is exactly the property
    `Ephemeral` buys and nothing else produces it.
    """
    started = time.monotonic()
    deadline = started + TIER_B_DEREGISTER_TIMEOUT
    while True:
        ev.host_status_after = _tailscale_status(["tailscale", "status", "--json"])
        ev.peers_after = _peer_domains(ev.host_status_after)
        if ev.domain not in ev.peers_after:
            ev.deregistered_seconds = time.monotonic() - started
            return True
        if time.monotonic() >= deadline:
            ev.deregistered_seconds = time.monotonic() - started
            return False
        time.sleep(TIER_B_DEREGISTER_INTERVAL)


@pytest.fixture(scope="module")
def tailnet() -> TailnetEvidence:
    """One real branch, with a real tailnet node, up and measured and destroyed.

    The safety structure is Tier A1's, unchanged, because it is the part that
    must not be re-derived: the project name is `br-` + a sanitised label
    forced by `identity.branch_paths`; teardown goes through
    `branch.branch_down`, which guards project AND worktree before issuing a
    command, and then through the harness sweep; and production-unchanged is
    asserted from a snapshot THIS fixture captured, never the one
    `branch_down` takes internally.
    """
    if os.environ.get(TIER_B_ENV) != "1":              # pragma: no cover
        raise RuntimeError(TIER_B_SKIP_REASON)

    ev = TailnetEvidence()
    paths = identity.branch_paths(TIER_B_BRANCH_NAME)
    ev.project = paths.project
    ev.hostname = paths.hostname
    ev.domain = paths.domain

    before = production_snapshot()
    production_root = identity.production_root()
    prod_db_before = {
        name: _sha256(production_root / "forgejo" / "gitea" / name)
        for name in ("gitea.db", "gitea.db-wal")
    }

    # BEFORE anything exists, so the node's later presence is a transition and
    # not a pre-existing fact -- and so assertion 6's "gone" means "gone
    # again" rather than "never seen".
    ev.host_status_before = _tailscale_status(["tailscale", "status", "--json"])
    ev.peers_before = _peer_domains(ev.host_status_before)

    poller = ProductionPoller(f"https://{identity.production_domain()}/git/")
    poller.start()

    # Same location, and the same two measured reasons, as Tier A1's fixture:
    # /tmp is a tmpfs and reflink cannot work there, and production's
    # `.worktrees/` is where the real `aurora branch up` puts it (D-F) but
    # would leak an undeletable directory into production's checkout on every
    # run. See the `evidence` fixture for the full measurement.
    scratch_root = Path.home() / ".cache" / "aurora-acceptance"
    scratch_root.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="tierb-", dir=str(scratch_root)))
    ev.worktree = scratch / TIER_B_BRANCH_NAME

    patch = pytest.MonkeyPatch()
    runner = branch.CommandRunner()
    try:
        # NO sidecar stub: the real `tailscale/tailscale` image, which is the
        # whole point of this tier.
        #
        # NO fabricated key, and no key handling here at all. `branch_up`
        # resolves production's real ephemeral key itself through
        # `branch.resolve_authkey`, so it never passes through this file, is
        # never stored on `ev`, and cannot reach an assertion message.
        #
        # NO readiness stubs. See `_spy_step`.
        for step in ("await_tailnet", "await_https", "reconcile"):
            patch.setattr(
                branch._Up, step,
                _spy_step(ev, step, getattr(branch._Up, step)),
            )

        try:
            ev.result = branch.branch_up(
                TIER_B_BRANCH_NAME,
                devs=TIER_B_DEV,
                from_ref=_current_branch(),
                build=False,
                runner=runner,
                worktrees_root=scratch,
            )
        except branch.BranchUpFailed as exc:
            ev.up_error = _redact(str(exc))

        _measure_tailnet(ev)
    finally:
        patch.undo()
        try:
            ev.down = branch.branch_down(
                TIER_B_BRANCH_NAME, runner=branch.CommandRunner()
            )
        finally:
            teardown_branch_project(ev.project)

        ev.residue_after = project_residue(ev.project)
        # Only now: the node cannot deregister until its container is gone.
        ev.deregistered = _await_deregistration(ev)

        ev.worktree_after_teardown_exists = ev.worktree.exists()
        if ev.worktree_after_teardown_exists:
            ev.worktree_undeletable = sorted(
                str(p.relative_to(ev.worktree))
                for p in ev.worktree.rglob("*")
                if _foreign_owner(p)
            )[:10]
            dead = scratch / f"UNDELETABLE-{TIER_B_BRANCH_NAME}"
            ev.worktree.rename(dead)
        subprocess.run(
            ["git", "worktree", "prune"], cwd=str(production_root),
            capture_output=True, check=False,
        )
        # Defect 58: `down` does not delete the ref `up` created. Deleted here,
        # and only when it still points at the commit `up` branched from, so a
        # human's branch that happens to share the name is never touched.
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
            capture_output=True, text=True, check=False,
        ).stdout.strip()
        ref = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet",
             f"refs/heads/{TIER_B_BRANCH_NAME}"],
            cwd=str(production_root), capture_output=True, text=True, check=False,
        ).stdout.strip()
        if ref and ref == head:
            ev.branch_ref_deleted = subprocess.run(
                ["git", "branch", "-D", TIER_B_BRANCH_NAME],
                cwd=str(production_root), capture_output=True, check=False,
            ).returncode == 0

        ev.prod_db_before = prod_db_before
        ev.prod_db_after = {
            name: _sha256(production_root / "forgejo" / "gitea" / name)
            for name in ("gitea.db", "gitea.db-wal")
        }
        poller.stop()
        ev.availability = list(poller.codes)
        # `assert_production_unchanged` is the harness' ONE implementation of
        # "production was not disturbed" and it stays here, in the fixture, so
        # it runs whatever the tests do. The Forgejo-database comparison is
        # asserted in its own test instead -- an assertion in a `finally`
        # destroys every other measurement in the bundle when it fails.
        assert_production_unchanged(before)

    return ev


@tier_b
def test_the_tailnet_branch_came_up_and_ran_the_readiness_steps_a1_stubs(tailnet):
    """The bundle is non-degenerate, and the code paths under test really ran.

    First, because every later assertion reads this data: a fixture that
    silently produced nothing would make all of them vacuously true.

    Second, because `await_tailnet` and `await_https` are not scaffolding --
    they are shipped assertions, and this tier is the first thing ever to
    execute them. `await_tailnet` raises unless the node reports
    `BackendState == "Running"` under the requested hostname; `await_https`
    polls the branch's own URL until it answers 2xx, with certificate
    validation on. A run in which they never executed must not resemble one
    in which they passed, so the recorder is checked before anything else,
    and it is appended to only after each real call RETURNS.

    `reconcile` is deliberately NOT required here. It is the third step, it
    fails on this host for a cause that has nothing to do with tailnet
    ingress, and the test that owns that failure is
    `test_branch_up_completes_on_a_branch_with_a_real_tailnet_identity`.
    Requiring it here would make every Tier B assertion red for one unrelated
    defect.
    """
    assert len(tailnet.containers) >= 10, (
        f"the branch produced {len(tailnet.containers)} containers: "
        f"{tailnet.containers}"
    )
    assert tailnet.steps_completed[:2] == ["await_tailnet", "await_https"], (
        "the two readiness steps Tier A1 has to stub did not both run to "
        f"completion, in order: {tailnet.steps_completed}. Everything below "
        "asserts properties they are the gate for."
    )


@tier_b
@pytest.mark.xfail(
    strict=False,
    reason=(
        "MEASURED over four real Tier B runs on 2026-07-30: `reconcile` failed on runs 1 and 4 and SUCCEEDED on run 3. The defect is real and it is INTERMITTENT. Mechanism: the seed copies production's Forgejo database, so the branch's forge already holds production's `hermes-<user>` OAuth2 applications, but the seed deliberately does NOT copy `.agent-env`, production's OIDC client secrets (aurora_cli/seed.py; finding N1 is why). `provision_developer` therefore finds an app whose secret it cannot recover, takes the delete-and-recreate path, and `DELETE /api/v1/user/applications/oauth2/<id>` against the branch's own forge answers >= 400. When the branch's Forgejo has not finished exposing those rows to the API, no app is found, `reconcile` creates a fresh one and succeeds -- which is the race. That path has never executed in production, where the secret is always recoverable. See docs/issues/chunk3-spec-deltas.md. `strict=False`, and that is a deliberate, uncomfortable choice: a strict marker on an INTERMITTENT defect makes the suite flap between FAILED and XPASS on a race, which teaches a reader to ignore it. The cost is that this will not shout when the defect is fixed, so the issue entry carries the instruction instead. Make it strict again the moment the race is gone."
    ),
)
def test_branch_up_completes_on_a_branch_with_a_real_tailnet_identity(tailnet):
    """The one Tier B property this host cannot satisfy, and its diagnosis.

    Everything before `reconcile` ran for real: the worktree, the rendered
    `.env`, the seed, the Postgres restore, the whole stack, the tailnet node
    and the branch's certificate. Only the third readiness step fails, and it
    fails inside `dev-admin` rather than anywhere in the branching code.
    """
    assert not tailnet.up_error, (
        "`branch up` did not complete for the tailnet tier:\n"
        + tailnet.up_error
        + "\n  the branch forge answered:\n    "
        + "\n    ".join(tailnet.forgejo_oauth_log or ["(no matching log lines)"])
    )
    assert tailnet.steps_completed == ["await_tailnet", "await_https", "reconcile"], (
        f"the three readiness steps did not all complete: "
        f"{tailnet.steps_completed}"
    )


@tier_b
def test_the_branch_node_reached_running_on_the_tailnet(tailnet):
    """ASSERTION 1, from two independent vantage points.

    "The container is up" is not the property and asserting it would be the
    trap: a sidecar with no auth key is `running` in every sense Docker knows,
    reports `Logged out.` forever, and leaves the branch with URLs that
    resolve to nothing. So the first leg is `BackendState`, asked of the
    branch's own tailscaled over its own socket.

    The second leg is production's tailscaled seeing the node as a peer, and
    it is not a duplicate: the first says "this daemon believes it is logged
    in", the second says "the control plane agrees, and the rest of the
    tailnet can see it". The name is checked as a DNS name rather than a
    `HostName` -- this tailnet already contains a peer whose `HostName` is
    `localhost`, and a branch's identity is the name its certificate and its
    URLs are issued for.
    """
    status = tailnet.sidecar_status
    assert status and "_error" not in status, (
        f"could not read the branch sidecar's tailscale status: "
        f"{status.get('_error', 'no sidecar container was found')}"
    )
    assert status.get("BackendState") == "Running", (
        f"the branch's tailscaled reports BackendState="
        f"{status.get('BackendState')!r}, not 'Running'."
    )
    dns = str((status.get("Self") or {}).get("DNSName") or "").rstrip(".")
    assert dns == tailnet.domain, (
        f"the node joined as {dns!r}, not as {tailnet.domain!r}. Tailscale "
        "appends a suffix when a name is taken, and a branch whose node is "
        "`...-1` has a certificate and URLs nobody was given."
    )

    assert "_error" not in tailnet.host_status_live, tailnet.host_status_live
    assert _self_domain(tailnet.host_status_live) == identity.production_domain(), (
        "the host tailscale status this test parsed does not belong to "
        "production's node, so its peer list is evidence about something else"
    )
    assert tailnet.peers_live, "production's tailscaled listed no peers at all"
    assert tailnet.domain in tailnet.peers_live, (
        f"{tailnet.domain} is not a peer of production's node while the "
        f"branch is up. Peers seen: {sorted(tailnet.peers_live)}"
    )
    assert tailnet.domain not in tailnet.peers_before, (
        f"{tailnet.domain} was ALREADY on the tailnet before this branch was "
        "created, so its presence proves nothing about this run and "
        "assertion 6 cannot mean anything either. Remove the stale node."
    )


@tier_b
def test_caddy_serves_the_branchs_own_certificate_from_the_branchs_tailscaled(tailnet):
    """ASSERTION 2.

    Three legs, and the third is what makes the first two mean what they say.

    1. The certificate validates against the SYSTEM trust store for the
       branch's name -- `_peer_certificate` uses a default SSL context, so
       simply obtaining it proves chain and hostname verification passed.
    2. It is the BRANCH's certificate and not production's: production's
       domain is absent from its SANs and the two serial numbers differ.
       Without that leg a Caddy that had somehow been handed production's
       certificate would satisfy leg 1 for the wrong reason.
    3. It can only have come from the branch's own tailscaled. Tailscale's
       certificate API issues only for the requesting node's own DNS name, so
       production's tailscaled cannot obtain one for `aurora-<branch>` -- and
       the branch's Caddy has exactly one tailscaled socket available to it,
       the project-scoped `tailscale_sock` VOLUME shared from the sidecar,
       not a host bind. Asserted, because production's Caddy reaches the
       HOST's socket at the same path and the difference between the two
       configurations is invisible from inside the container.
    """
    assert not tailnet.branch_cert_error, (
        f"no TLS handshake with https://{tailnet.domain}/ : "
        f"{tailnet.branch_cert_error}"
    )
    branch_sans = _san_names(tailnet.branch_cert)
    assert branch_sans, f"the branch certificate carries no DNS SAN: {tailnet.branch_cert}"
    assert tailnet.domain in branch_sans, (
        f"the certificate served for {tailnet.domain} names {sorted(branch_sans)}"
    )
    assert identity.production_domain() not in branch_sans, (
        "the branch is serving a certificate that also names production: "
        f"{sorted(branch_sans)}"
    )
    issuer = _issuer_values(tailnet.branch_cert)
    assert any("Let's Encrypt" in value for value in issuer), (
        "the branch certificate was not issued by the CA Tailscale's "
        f"certificate API uses: {sorted(issuer)}"
    )

    assert not tailnet.production_cert_error, tailnet.production_cert_error
    assert tailnet.production_cert.get("serialNumber"), (
        "production's certificate could not be read, so 'the branch's is a "
        "different certificate' has nothing to compare against"
    )
    assert (
        tailnet.branch_cert.get("serialNumber")
        != tailnet.production_cert.get("serialNumber")
    ), "the branch and production served the SAME certificate"

    mounts = tailnet.caddy_tailscale_mounts
    assert mounts, (
        "the branch's Caddy has nothing mounted at "
        f"{overlay.TAILSCALE_SOCKET_DIR}, so it has no tailscaled to ask"
    )
    assert [m for m in mounts if m.get("Type") == "volume"], (
        f"the branch's Caddy reaches {overlay.TAILSCALE_SOCKET_DIR} through "
        f"{mounts}. A bind would be the HOST's tailscaled -- i.e. "
        "production's -- and the certificate would not be the branch's."
    )
    assert all(
        m.get("Name", "").startswith(tailnet.project) for m in mounts
    ), (
        f"the branch's Caddy shares a tailscaled socket volume outside its "
        f"own project: {mounts}"
    )


@tier_b
def test_the_branch_url_serves_the_branchs_own_forge(tailnet):
    """ASSERTION 3, with the one substitution this host forces.

    The specification asks for `GET https://<branch>/git/` returning HTML
    containing `obsidura` and `aurora`. MEASURED on 2026-07-30, against
    PRODUCTION: its own `/git/` contains neither string, and neither does
    `/git/explore/repos` -- the seeded organisation and repository are
    private, the anonymous explore page renders "Sign in", and `/git/obsidura`
    is a 404 to a logged-out client. The strings are reachable only behind an
    OIDC session, which is explicitly deferred (`docs/issues/
    chunk3-spec-deltas.md` section 10). Tier A1 already proves they are in the
    branch's own database, by querying it inside the branch's own container.

    Weakening the assertion to "something answered" was the other option and
    would have been worthless. What is asserted instead is strictly harder to
    satisfy by accident, and it is the property `/git/` was chosen to show in
    the first place -- that the branch's URL reaches the BRANCH's forge:

      * `appUrl`, which Forgejo renders from its own ROOT_URL, is the
        branch's URL. A branch that inherited `FORGEJO_URL` would render
        production's here, and finding N1 is precisely about that variable.
      * the page title carries `[BRANCH: <name>]` from `FORGEJO_APP_NAME`
        (spec 5.4 layer 3), and production's identical page does not.

    Both are compared against production's live page in the same run, so
    neither can pass by matching something both forges emit.
    """
    assert tailnet.git_status == 200, (
        f"https://{tailnet.domain}/git/ answered {tailnet.git_status}"
    )
    assert tailnet.production_git_body, (
        "production's /git/ returned nothing, so the comparisons below have "
        "no control"
    )

    expected_app_url = f"https://{tailnet.domain}/git/"
    assert expected_app_url.replace("/", "\\/") in tailnet.git_body, (
        f"the branch's /git/ does not advertise {expected_app_url} as its "
        "appUrl, so this Forgejo is configured with somebody else's URL"
    )
    assert identity.production_domain() not in tailnet.git_body, (
        "the branch's /git/ names production's domain -- FORGEJO_URL or "
        "ROOT_URL was inherited rather than derived"
    )

    marker = f"[BRANCH: {TIER_B_BRANCH_NAME}]"
    assert marker in tailnet.git_body, (
        f"the branch's forge does not render {marker!r}, so FORGEJO_APP_NAME "
        "did not reach it and spec 5.4 layer 3 is not active"
    )
    assert marker not in tailnet.production_git_body, (
        "production's own forge renders the branch marker, so this assertion "
        "does not distinguish the two"
    )


@tier_b
@pytest.mark.xfail(
    strict=False,
    reason=(
        "BLOCKED BY THE SAME INTERMITTENT DEFECT as "
        "test_branch_up_completes_on_a_branch_with_a_real_tailnet_identity. "
        "`reconcile` dies before it writes `agents.conf`, so the running "
        "Caddy still holds the COMMITTED fragment -- which is production's, "
        "generated in published mode, and names developers this branch never "
        "provisioned (`johndear`, `127.0.0.1:9122`). Every `/agent/<user>/` "
        "route on a branch therefore 502s, and it 502s for a reason that is "
        "NOT `AGENT_UPSTREAM_MODE`. MEASURED, not assumed: the branch `.env` "
        "leg of this test PASSES -- the variable did reach the branch -- and "
        "the leg that fails is the generated fragment. Failed on all four "
        "Tier B runs of 2026-07-30, including the one where `reconcile` "
        "itself succeeded, so there is more here than the OAuth race alone "
        "and assertion 4 is genuinely unproven. `strict=False` for the same "
        "reason as its sibling: the blocking defect is intermittent."
    ),
)
def test_the_agent_route_reaches_hermes_and_proves_service_upstream_mode(tailnet):
    """ASSERTION 4 -- the one that proves `AGENT_UPSTREAM_MODE=service`
    actually reached the branch `.env`.

    The route exists either way. In `published` mode -- the compose default,
    which a branch inherits if `branch-env.yaml` fails to override it --
    `reconcile` generates `reverse_proxy 127.0.0.1:9119`, and in a branch that
    address is inside the tailscale sidecar's netns where nothing of this
    stack listens. Caddy then answers 502 and nothing else changes: no error,
    no log a reader would notice, just an agent dashboard that is silently
    gone. That is why this is asserted over HTTP and not by reading the
    `.env`.

    Artefact and generator, both:
      * the GENERATED fragment inside the running Caddy names
        `hermes-<user>:9119` and not a loopback address -- and it is read out
        of the container, so it is what Caddy loaded rather than what the
        repository ships (the committed fragment is production's, in
        published mode);
      * the RESPONSE is Hermes': a 302 to the prefixed login path, and a
        login page carrying Hermes' own title. Measured against production's
        agent container. A 502 has neither, and neither does Caddy's static
        error page.
    """
    assert tailnet.env_agent_mode == "service", (
        "the branch `.env` does not set AGENT_UPSTREAM_MODE=service (got "
        f"{tailnet.env_agent_mode!r})"
    )

    conf = tailnet.agents_conf
    assert conf, (
        "the running Caddy has no generated agents.conf, so `reconcile` "
        "either did not run or did not write it"
    )
    assert f"hermes-{TIER_B_DEV}:9119" in conf, (
        "the generated Caddy fragment does not name the agent by SERVICE. "
        "In a branch, 127.0.0.1 in the sidecar netns reaches nothing and "
        "every /agent route 502s silently."
    )
    assert "127.0.0.1:9119" not in conf, (
        "the generated fragment still carries a loopback agent upstream, so "
        "it was rendered in published mode"
    )

    assert tailnet.agent_status != 502, (
        f"https://{tailnet.domain}/agent/{TIER_B_DEV}/ answered 502 -- the "
        "route exists and its upstream does not. This is exactly the failure "
        "AGENT_UPSTREAM_MODE=service prevents."
    )
    assert tailnet.agent_status == 302, (
        f"expected Hermes' redirect to its login page, got "
        f"{tailnet.agent_status}"
    )
    assert f"/agent/{TIER_B_DEV}/{HERMES_LOGIN_PATH}" in tailnet.agent_location, (
        f"the redirect went to {tailnet.agent_location!r}, which is not the "
        "prefixed Hermes login path"
    )
    assert tailnet.agent_login_status == 200, (
        f"the branch's agent login page answered {tailnet.agent_login_status}"
    )
    assert HERMES_LOGIN_TITLE in tailnet.agent_login_body, (
        "the branch served something at the agent login path that is not "
        "Hermes' login page"
    )


@tier_b
def test_the_branch_is_reachable_from_inside_productions_hermes_container(tailnet):
    """ASSERTION 5 -- spec 10.3, asked from where the spec asks it.

    Not from this host. This host IS production's tailnet node, so a request
    from here is a request from the node itself and says nothing about
    whether production's AGENT can reach a branch. Production's Hermes sits on
    a Docker bridge network, and a bridge container reaching a tailnet peer
    depends on host forwarding that no test here configures.

    The control is the same probe against production's OWN URL. Without it, a
    failure would be indistinguishable from "that container has no HTTPS
    egress at all", which is a fact about production and not about branching.
    """
    assert tailnet.hermes_container, (
        "production has no `hermes` container, so spec 10.3's question "
        "cannot be asked"
    )
    control = tailnet.hermes_probe_production
    assert control.get("code") == "200", (
        "production's Hermes cannot reach production's OWN /git/ "
        f"({control}); this probe measures egress, not branching"
    )
    probe = tailnet.hermes_probe_branch
    assert probe.get("code") == "200", (
        f"production's Hermes could not reach https://{tailnet.domain}/git/ : "
        f"{probe}"
    )


@tier_b
@pytest.mark.xfail(
    strict=False,
    reason=(
        "The key IS Ephemeral and spec 4.4 DOES hold -- eventually. What "
        "fails is the timescale, and it was measured rather than assumed: "
        "after `branch down` removed every container, volume and network, "
        "the node was still a peer of production's tailscaled 300 s later, "
        "still a peer 51 minutes later, and GONE by 71 minutes. Tailscale's "
        "control plane reclaims an ephemeral node about an hour after it "
        "goes offline, not on teardown. So the assertion as specified is not "
        "observable inside any window a test can afford -- 300 s is already "
        "generous for a fixture that also brings up a 14-container stack -- "
        "and raising the poll to an hour would make the tier unrunnable. "
        "The consequence is operational and real: for roughly an hour after "
        "a branch is destroyed its NAME is still taken, so a second "
        "`branch up` of the same name registers as `<name>-1` and "
        "`tailscale_readiness()` correctly refuses it. That is why "
        "`$AURORA_TIER_B_BRANCH` exists. `strict=False` because the "
        "reclamation time is not fixed and a strict marker on a timer makes "
        "the suite flap. See docs/issues/chunk3-spec-deltas.md."
    ),
)
def test_the_ephemeral_node_left_the_tailnet_after_teardown(tailnet):
    """ASSERTION 6.

    The property `Ephemeral` buys, and nothing else produces it: a reusable
    but NON-ephemeral key leaves one dead node on the tailnet per branch ever
    minted, each holding its name -- so the next branch of the same name
    registers as `...-1`, gets a certificate for a name nobody was given, and
    `await_tailnet` fails for a reason with no obvious cause.

    Asked of production's tailscaled, because the branch's no longer exists.
    Not vacuous: the same peer list was asserted to CONTAIN this node while
    the branch was up, and asserted NOT to contain it before the branch was
    created, so this is a measured transition in both directions.
    """
    assert tailnet.domain in tailnet.peers_live, (
        "the node was never seen on the tailnet, so its later absence is not "
        "evidence of deregistration"
    )
    assert "_error" not in tailnet.host_status_after, tailnet.host_status_after
    assert tailnet.peers_after, (
        "production's tailscaled listed no peers after teardown, so the "
        "absence below is an unreadable status rather than a departure"
    )
    assert tailnet.deregistered, (
        f"{tailnet.domain} was still a peer {tailnet.deregistered_seconds:.0f}s "
        f"after its stack was destroyed. Peers: {sorted(tailnet.peers_after)}. "
        "Measured 2026-07-30: reclamation happens between 51 and 71 minutes "
        "after the node goes offline, so this is expected to fail and the "
        "marker says so. If it PASSES, Tailscale reclaims faster than it did "
        "and the marker should be made strict again."
    )


@tier_b
def test_production_answered_every_poll_for_the_whole_tailnet_cycle(tailnet):
    """Spec 10.3's availability half, over the tailnet cycle this time.

    Tier A1 proves it for a stub-sidecar branch. This tier adds a real
    tailscaled with NET_ADMIN, NET_RAW and `/dev/net/tun` beside production's
    own, which is the configuration most able to disturb it, so the same
    invariant is measured again rather than inherited. `/` is not polled: it
    answers 401 by design.
    """
    assert len(tailnet.availability) >= 5, (
        f"the availability poller recorded only {tailnet.availability!r}"
    )
    bad = [code for code in tailnet.availability if code != 200]
    assert not bad, f"production did not answer 200 during the cycle: {bad}"


@tier_b
def test_the_tailnet_cycle_did_not_mutate_productions_forgejo_database(tailnet):
    """`gitea.db` byte-identical. `gitea.db-wal` MEASURED AND EXCLUDED.

    Tier A1 owns the seeding invariant and this does not duplicate it: A1
    asserts a stub-sidecar branch did not disturb production, and this asserts
    it of a branch that additionally held a real tailnet node, ran `reconcile`
    against a forge seeded from production's database, and was polled from
    production's own Hermes container.

    **`gitea.db-wal` cannot participate, and the measurement is why.** With no
    branch anywhere on the host and nothing running but production, on
    2026-07-30:

        20:16:03  gitea.db 4ab13cad…  gitea.db-wal 9132b816…
        20:16:48  gitea.db 4ab13cad…  gitea.db-wal c82eb14a…

    Production is live. It writes its own WAL on its own schedule -- 45 s was
    enough -- while the database content stayed byte-identical. A Tier B cycle
    takes six minutes and this suite's own availability poller adds ~180
    requests to it, so comparing `-wal` across that window goes red against a
    perfectly correct seeder. That is precisely the reasoning
    `branch_harness.PROD_VOLATILE_SUFFIXES` already gives for excluding
    `-shm`, `.lock`, `.pid` and `.log`; `-wal` belongs with them over a window
    this long.

    It is RECORDED rather than dropped: the assertion below prints both
    readings, so a reader can see whether the WAL moved and decide for
    themselves.

    NOTE, and it is a real defect rather than a note about this test:
    `test_seeding_did_not_mutate_productions_forgejo_database` (Tier A1) DOES
    compare `-wal`, over a window of the same order. It is latently flaky in
    exactly the direction measured above. Recorded in
    `docs/issues/chunk3-spec-deltas.md`; not changed here, because changing a
    test this task cannot re-run would ship an unexecuted artefact.
    """
    assert tailnet.prod_db_before.get("gitea.db"), (
        "production's Forgejo database could not be read before the cycle"
    )
    assert tailnet.prod_db_before["gitea.db"] == tailnet.prod_db_after["gitea.db"], (
        "production's Forgejo database CONTENT changed during the tailnet "
        f"cycle:\n  before={tailnet.prod_db_before}\n  after ={tailnet.prod_db_after}"
    )


@tier_b
def test_the_tailnet_branch_left_no_docker_object_behind(tailnet):
    """Containers, volumes AND networks, for this tier's own stack.

    Not a duplicate of Tier A1's teardown test: this branch owns two volumes
    A1's never had (`tailscale_state`, `tailscale_sock`), and the state volume
    is what makes the node's identity survive a restart -- so it is also what
    would keep an ephemeral node alive if teardown missed it.
    """
    assert tailnet.down is not None
    assert tailnet.residue_after == {"containers": [], "volumes": [], "networks": []}, (
        f"teardown left residue: {tailnet.residue_after}; "
        f"notes={tailnet.down.notes}"
    )
    assert tailnet.down.containers_removed, (
        "branch_down reported removing no containers, so this assertion is "
        "about a teardown that had nothing to tear down"
    )
    removed = {v.split("_", 1)[-1] for v in tailnet.down.volumes_removed}
    assert {"tailscale_state", "tailscale_sock"} <= removed, (
        "the sidecar's own volumes were not removed: "
        f"{tailnet.down.volumes_removed}. `tailscale_state` is the node's "
        "identity; leaving it behind is how an ephemeral node stops being "
        "ephemeral."
    )
