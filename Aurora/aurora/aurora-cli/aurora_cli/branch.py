"""`aurora branch up` -- mint a complete, isolated copy of the stack (Task 8).

Spec 4.1 (corrected), 5.5 and 7.1. Almost all of this module is ORCHESTRATION:
the work is done by Tasks 1-7, and what is left is doing it in the one order
that produces a branch which actually serves. Each step's position is a
measured fact rather than a preference, and the ones that cost this project
time are:

* the branch `.env` is rendered BEFORE compose is invoked with the overlay.
  `docker compose config` interpolates `${DOCKER_GID}` and friends, so a
  worktree with no `.env` cannot even be resolved (Task 3's open item 4).
* Postgres comes up and the AFFiNE dump is restored BEFORE the rest of the
  stack (decision D-E), so `affine_migration` runs against restored data
  rather than against an empty schema.
* the tailnet node is VERIFIED to have reached `Running`. A `tailscaled` with
  a missing or rejected auth key does not fail -- it starts, reports
  `Logged out.`, and stays up (trap 9, measured). Without this step every
  branch "succeeds" and hands the developer URLs that resolve to nothing.
* compose runs a SECOND time after `reconcile`. Once agents are compose
  services, `reconcile` creates no containers: it computes what should exist
  and emits `container.missing`. Without the second `up` a branch has no
  agent and every `/agent/<user>/` URL in the access document is dead.
* every compose invocation runs with **stdin closed**. A volume carrying a
  stale `config-hash` label makes Compose ask "Recreate (data will be
  lost)?"; measured, closed stdin answers no, an open pipe HANGS
  INDEFINITELY, and a human at a terminal destroys the seed the branch was
  created for (plan defect 28).

`up` is NOT atomic, and pretending otherwise is worse than admitting it. On
failure after the worktree exists it prints the exact `aurora branch down`
command and leaves everything in place: a half-built branch is the only
artefact a developer can debug from, and an automatic teardown is one more
code path able to reach Docker objects while something is already wrong.

One property worth knowing, because it is seeding paying for itself and then
immediately costing something: production's `FORGEJO_ADMIN_TOKEN` is valid in
the branch, because the branch's Forgejo is a snapshot of production's
database -- same users, same token hashes. That is what lets a branch mint its
own credential with no extra setup, and it is also why it must: the same
property makes the branch's inherited token valid against PRODUCTION's API.
Spec 2026-08-01 P3, implemented in `aurora_cli.forgejo_token` and run here
between `await_https` and `reconcile`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import yaml

from aurora_cli import (
    access_doc, crosswire, envfile, exclusions, forgejo_token, guards, identity,
    overlay, seed, tailnet,
)
# `as runtimes` deliberately: `branch_up(runtime=...)` is the parameter name a
# caller wants, and it would shadow a module imported as `runtime` inside
# precisely the functions that use both. __main__.py records the same trap for
# `branch`, found only at `--help`.
from aurora_cli import runtime as runtimes


class BranchError(RuntimeError):
    """`aurora branch up` refused, or could not finish."""


class BranchUpFailed(BranchError):
    """A failure AFTER the worktree existed. Carries the teardown command.

    Separate from `BranchError` because the two mean different things to the
    caller: a plain `BranchError` means nothing was created and there is
    nothing to clean up, while this one means a partially-built branch is on
    the host and `teardown_command` is how it goes away. Collapsing them would
    make "did this leave anything behind?" unanswerable from the exception.
    """

    def __init__(self, message: str, *, teardown_command: str) -> None:
        super().__init__(message)
        self.teardown_command = teardown_command


# ---------------------------------------------------------------------------
# tunables, all measured
# ---------------------------------------------------------------------------

#: `docker compose` files, in overlay order. `compose.exclude.yml` is written
#: into every branch worktree even when nothing is excluded, because Compose's
#: `-f` is a hard error on a missing file (trap 4) and a caller that has to
#: decide whether to pass it is a caller that gets it wrong once.
COMPOSE_FILES: tuple[str, ...] = (
    overlay.BASE_COMPOSE_NAME,
    overlay.OVERLAY_NAME,
    exclusions.EXCLUSION_OVERLAY_NAME,
)

#: The compose variables whose ambient values are STRIPPED from every
#: invocation. The branch `.env` is the only thing allowed to answer "which
#: project" and "which profiles"; an exported `COMPOSE_PROFILES` in the
#: invoking shell silently changes the service set, which is the same trap
#: Task 3's renderer has (`resolve_config` forces `COMPOSE_PROFILES="*"`).
#:
#: `DOCKER_HOST` is here for a stronger reason than the other three: it decides
#: which DAEMON the command lands on. An exported one left over from a podman
#: session would move a docker-runtime branch onto another daemon silently, and
#: a stale one pointing at a dead socket would fail an `up` that had already
#: created a worktree. It is stripped here and then set EXPLICITLY, per
#: invocation, by `runtime.Runtime.environ` -- so on the docker path it is
#: absent (the root daemon's default socket) and on the podman path it is the
#: value this tool chose, never the value the shell happened to carry.
STRIPPED_COMPOSE_VARS: tuple[str, ...] = (
    "COMPOSE_PROJECT_NAME", "COMPOSE_PROFILES", "COMPOSE_FILE",
    runtimes.DOCKER_HOST_VAR,
)

#: Mode of the branch `.env`. It carries `TS_AUTHKEY` in clear text, and
#: decision D-F puts branch worktrees at `<production>/.worktrees/<name>` --
#: inside the tree production's Hermes bind-mounts as its workspace. At the
#: default 0644 every branch's tailnet auth key would be readable by
#: production's agent containers.
ENV_FILE_MODE = 0o600

#: Environment variable, then production `.env` variable, holding a SUPPLIED
#: ephemeral auth key.
#:
#: D-D said the key is supplied, never minted, and gave a reason: "minting
#: needs a Tailscale API key or OAuth client, neither of which exists on this
#: host". That reason EXPIRED -- `TS_OAUTH_CLIENT_ID`/`TS_OAUTH_CLIENT_SECRET`
#: are now in production's `.env` and the mint/delete calls are verified
#: against the live API (spec 2026-08-01 P6, `aurora_cli.tailnet`). The
#: decision was not wrong when it was made; its premise stopped holding. What
#: D-D got right is untouched: a sidecar with NO key does not fail, it starts,
#: says `Logged out.` and serves a dead URL, so these two remain the fallback
#: and "no key at all" remains a refusal.
AUTHKEY_ENV_VAR = "AURORA_TS_AUTHKEY"
AUTHKEY_PRODUCTION_VAR = "TS_AUTHKEY_BRANCH"

#: `$AURORA_DEV` is the first place `--devs` is looked for.
DEV_ENV_VAR = "AURORA_DEV"

DEVELOPERS_FILE = "developers.yaml"

#: Measured on this host 2026-07-30, `docker stats --no-stream`: production's
#: ten running containers hold ~918 MiB between them (hermes 323, arcadedb
#: 201, affine_server 200, forgejo 101, affine_postgres 45, agent-authz 16,
#: caddy 13, affine_redis 10, forgejo-mcp 7, fjell 1.4). A branch is that same
#: set plus a tailscale sidecar plus one Hermes per requested developer, and
#: the admin Hermes' 323 MiB is the best available estimate for an agent. So a
#: one-developer branch costs roughly 1.3 GiB resident.
MEM_PER_BRANCH_BYTES = 1300 * 1024 * 1024

#: Headroom on top of the measured per-branch cost: `--build` and the kernel.
MEM_HEADROOM_BYTES = 700 * 1024 * 1024

#: The floor `MemAvailable` must stay above: the measured cost plus headroom.
#:
#: DERIVED, not typed. It used to be a literal 2 GiB while
#: `MEM_PER_BRANCH_BYTES` appeared nowhere but inside `shortfalls()`'s message
#: string -- so the guard enforced one number while telling the operator about
#: another, and either could drift from the other with nothing to notice. A
#: constant that is named in prose and used in no computation is a comment.
#:
#: **`MemAvailable`, not `MemFree`.** On this host `MemFree` reads 608 MiB
#: because 8.2 GiB is page cache, while `MemAvailable` -- the kernel's own
#: estimate of what a new workload can get without swapping -- reads 8.0 GiB.
#: A guard reading `MemFree` refuses every branch on a perfectly healthy host,
#: which is how a safety guard gets deleted.
MEM_FLOOR_BYTES = MEM_PER_BRANCH_BYTES + MEM_HEADROOM_BYTES

#: Measured: `cp -a --reflink=auto` of production's 2.57 GB of host-path state
#: consumed **2.5 MB** of disk (btrfs extent sharing), the three agent home
#: volumes total ~140 MB, and the AFFiNE dump is ~260 KB. The unbounded term
#: is the `--build` layer cache, so the floor is generous rather than tight.
#: 150.8 GB (140 GiB) was free when this was written.
DISK_FLOOR_BYTES = 10 * 1024 * 1024 * 1024

#: Bounded waits. Every one of these is a bound on a poll loop that would
#: otherwise be unbounded, and an unbounded wait inside `branch up` is
#: indistinguishable from a hang.
COMPOSE_WAIT_TIMEOUT = 300
TAILSCALE_READY_TIMEOUT = 180.0
TAILSCALE_POLL_INTERVAL = 2.0
HTTP_READY_TIMEOUT = 240.0
HTTP_POLL_INTERVAL = 3.0

TAILSCALE_SOCKET = f"{overlay.TAILSCALE_SOCKET_DIR}/tailscaled.sock"

#: What `reconcile` is invoked as. `run --rm` rather than `up -d dev-admin`:
#: `run` gives a returncode to check, where `up -d` would need the exit status
#: fished back out of the container afterwards.
RECONCILE_SERVICE = "dev-admin"
RECONCILE_COMMAND = "reconcile"

#: The branch's Forgejo, and the CLI P3 mints through. `exec`, not `run --rm`:
#: `forgejo admin` operates on the live `/data` volume, so it has to be the
#: container that already has it.
FORGEJO_SERVICE = "forgejo"
FORGEJO_ADMIN_CLI = "forgejo"

#: The user the CLI must run as inside that container, and it is not the
#: default. Measured 2026-08-01 on `codeberg.org/forgejo/forgejo:15`: `exec`
#: lands as `uid=0(root)` because s6-overlay is the entrypoint, and
#: `generate-access-token` as root exits 1 -- with a log line on STDOUT and an
#: EMPTY stderr, which is the shape that makes a naive caller write a
#: timestamp into a `.env` and call it a token. As `git` it exits 0.
FORGEJO_CONTAINER_USER = "git"


# ---------------------------------------------------------------------------
# the one subprocess seam
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Invocation:
    """One recorded command. What the tests assert order and scope over."""

    argv: tuple[str, ...]
    cwd: Path | None = None
    env: Mapping[str, str] | None = None
    #: Verbatim, as handed to `subprocess`. Recorded rather than re-derived
    #: from `input`: a test that recomputed "well, no input was given, so
    #: stdin must have been closed" would agree with a mutant that passed
    #: `None` (inherit the terminal) and stall exactly as plan defect 28
    #: describes.
    stdin: Any = None


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class CommandRunner:
    """Every subprocess `branch up` issues goes through `run`.

    One seam, for the reason Task 6 gives for `seed._docker`: "it refused
    before doing anything" is checkable and "it refused" is not. A test
    supplies a subclass whose `_execute` returns canned results, and the
    recording -- including the stdin argument -- is shared code, so the log a
    test asserts over cannot drift from what a real run would do.
    """

    def __init__(self) -> None:
        self.invocations: list[Invocation] = []

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        input: bytes | None = None,
        check: bool = True,
        timeout: float | None = None,
    ) -> CommandResult:
        # Closed, not inherited. See plan defect 28: with an open pipe a
        # Compose prompt about a mismatched volume blocks forever, and with a
        # terminal a human answers it and destroys the seed.
        stdin = subprocess.DEVNULL if input is None else subprocess.PIPE
        self.invocations.append(Invocation(
            argv=tuple(argv), cwd=cwd, env=None if env is None else dict(env),
            stdin=stdin,
        ))
        result = self._execute(
            tuple(argv), cwd=cwd, env=env, input=input, stdin=stdin,
            timeout=timeout,
        )
        if check and result.returncode != 0:
            raise BranchError(
                f"`{' '.join(argv)}` failed with exit {result.returncode}"
                + (f" in {cwd}" if cwd is not None else "")
                + f": {result.stderr.strip() or result.stdout.strip() or '(no output)'}"
            )
        return result

    def _execute(
        self,
        argv: tuple[str, ...],
        *,
        cwd: Path | None,
        env: Mapping[str, str] | None,
        input: bytes | None,
        stdin: Any,
        timeout: float | None,
    ) -> CommandResult:
        proc = subprocess.run(
            list(argv),
            cwd=None if cwd is None else str(cwd),
            env=None if env is None else dict(env),
            input=input,
            stdin=None if input is not None else stdin,
            capture_output=True,
            timeout=timeout,
        )
        return CommandResult(
            argv=argv,
            returncode=proc.returncode,
            stdout=(proc.stdout or b"").decode("utf-8", "replace"),
            stderr=(proc.stderr or b"").decode("utf-8", "replace"),
        )


# ---------------------------------------------------------------------------
# results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResourceReading:
    """What the resource guard measured, and against what."""

    mem_available_bytes: int
    mem_floor_bytes: int
    disk_free_bytes: int
    disk_floor_bytes: int
    disk_path: Path
    forced: bool = False

    @property
    def ok(self) -> bool:
        return (self.mem_available_bytes >= self.mem_floor_bytes
                and self.disk_free_bytes >= self.disk_floor_bytes)

    def shortfalls(self) -> list[str]:
        out: list[str] = []
        if self.mem_available_bytes < self.mem_floor_bytes:
            out.append(
                f"MemAvailable is {_gib(self.mem_available_bytes)} and a "
                f"branch needs {_gib(self.mem_floor_bytes)} "
                f"(measured cost {_gib(MEM_PER_BRANCH_BYTES)} plus headroom)"
            )
        if self.disk_free_bytes < self.disk_floor_bytes:
            out.append(
                f"{self.disk_path} has {_gib(self.disk_free_bytes)} free and a "
                f"branch needs {_gib(self.disk_floor_bytes)}"
            )
        return out


@dataclass
class BranchResult:
    """Everything `branch up` did. Task 10 renders it; Task 11 returns it."""

    requested_name: str
    paths: identity.BranchPaths
    devs: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()
    from_ref: str | None = None
    reused_branch: bool = False
    seeded: bool = False
    seed_report: seed.SeedReport | None = None
    resources: ResourceReading | None = None
    hook: crosswire.HookInstall | None = None
    #: How this branch got its tailnet auth key (spec P6). A DESCRIPTION,
    #: never the key: `AuthKey.source` is the safe half of that dataclass and
    #: this field exists so "was this branch's node ephemeral?" is answerable
    #: from the result rather than from the admin console.
    authkey_source: str = ""
    #: What `forgejo_token.rotate_admin_token` did (spec P3), or `None` when
    #: it did not run -- an unseeded branch's forge has no production
    #: credential in it, and a `--without forgejo` branch has no forge.
    token_rotation: forgejo_token.RotationReport | None = None
    #: Which runtime this branch runs on. Recorded rather than assumed: it is
    #: what `branch down` must query, and a teardown that guessed would ask the
    #: wrong daemon, find nothing, and report a clean removal over a live stack.
    runtime: str = runtimes.DEFAULT_RUNTIME
    #: Anything a human must be told. The access document prints these
    #: verbatim, so a forced resource override, an inert pre-push hook or a
    #: skipped seed is recorded where the branch's user will see it rather
    #: than only in a terminal that has since scrolled away.
    notes: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.paths.name

    @property
    def project(self) -> str:
        return self.paths.project

    @property
    def domain(self) -> str:
        return self.paths.domain

    @property
    def sanitised(self) -> bool:
        """True when the name had to be changed to be usable."""
        return self.paths.name != self.requested_name

    def urls(self) -> dict[str, str]:
        """Every URL this branch serves, and NOT the ones it does not.

        `/agent` -- the admin Hermes dashboard -- is deliberately absent.
        Finding N5: production's Caddyfile redirects it to a `tailscale serve`
        mapping that exists only on the host, so in a branch it leads nowhere.
        `access_doc` prints the reason in its place; a URL that fails is worse
        than no URL, and the surest way not to print one is not to produce it.
        """
        base = f"https://{self.paths.domain}"
        urls = {
            "fjell": f"{base}/",
            "forgejo": f"{base}/git/",
            "affine": f"{base}/affine/",
        }
        for dev in self.devs:
            urls[f"agent-{dev}"] = f"{base}/agent/{dev}/"
        return urls


def _gib(value: int) -> str:
    return f"{value / (1024 ** 3):.2f} GiB"


# ---------------------------------------------------------------------------
# step 0: the resource guard (spec 5.5)
# ---------------------------------------------------------------------------


def read_mem_available(meminfo_path: Path | str = Path("/proc/meminfo")) -> int:
    """`MemAvailable` from `/proc/meminfo`, in bytes.

    `MemAvailable` and not `MemFree`, and this is not a detail. `MemFree`
    excludes page cache, which the kernel will hand over on demand: on this
    host the two read 608 MiB and 8.0 GiB respectively, a difference of 7.4
    GiB, so a guard reading `MemFree` refuses every branch on a healthy host.
    `MemAvailable` is the kernel's own estimate of what a new workload can
    have without swapping, which is exactly the question being asked.

    Absent is a hard error rather than a default. A resource guard that
    silently assumes plenty when it cannot measure is a guard that is not
    there.
    """
    path = Path(meminfo_path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BranchError(
            f"cannot read {path} to check memory before starting a branch: "
            f"{exc}. Refusing rather than assuming there is room."
        ) from exc
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        if key.strip() != "MemAvailable":
            continue
        fields = rest.split()
        if not fields:
            break
        try:
            value = int(fields[0])
        except ValueError:
            break
        unit = fields[1].lower() if len(fields) > 1 else "kb"
        return value * (1024 if unit == "kb" else 1)
    raise BranchError(
        f"{path} declares no usable `MemAvailable:` line. That is the only "
        "figure this guard accepts -- `MemFree` excludes page cache and is "
        "smaller than the truth by the size of the cache."
    )


def check_resources(
    *,
    meminfo_path: Path | str = Path("/proc/meminfo"),
    disk_path: Path | None = None,
    force: bool = False,
) -> ResourceReading:
    """Spec 5.5. Refuse a branch the host has no room for; `--force` overrides.

    The override is RECORDED on the reading and ends up in the access
    document, because "I forced this" is the first thing anyone debugging an
    OOM-killed branch needs to know.
    """
    disk_path = Path(disk_path) if disk_path is not None else identity.production_root()
    reading = ResourceReading(
        mem_available_bytes=read_mem_available(meminfo_path),
        mem_floor_bytes=MEM_FLOOR_BYTES,
        disk_free_bytes=shutil.disk_usage(disk_path).free,
        disk_floor_bytes=DISK_FLOOR_BYTES,
        disk_path=Path(disk_path),
        forced=force,
    )
    if reading.ok or force:
        return reading
    raise BranchError(
        "refusing to start a branch: "
        + "; ".join(reading.shortfalls())
        + ". Stop another branch, or pass --force to override (the override "
        "is recorded in the branch's access document)."
    )


# ---------------------------------------------------------------------------
# step 0: who the branch is for (spec 7.1)
# ---------------------------------------------------------------------------


def known_developers(root: Path | None = None) -> tuple[str, ...]:
    """Every `forgejo_user` in `developers.yaml`, in file order."""
    path = (root or identity.package_root()) / DEVELOPERS_FILE
    if not path.is_file():
        raise BranchError(f"no {DEVELOPERS_FILE} at {path}.")
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = document.get("developers") or []
    names = tuple(
        str(entry["forgejo_user"]) for entry in entries
        if isinstance(entry, Mapping) and entry.get("forgejo_user")
    )
    if not names:
        raise BranchError(
            f"{path} lists no developer with a `forgejo_user`, so `--devs` "
            "can neither be resolved nor validated."
        )
    return names


def git_user_name(root: Path | None = None, runner: CommandRunner | None = None) -> str:
    """`git config user.name`, or `""`.

    Read from PRODUCTION's checkout rather than from the branch worktree the
    plan names, and the two are the same file: a linked worktree has no config
    of its own, so `git config` in one reads (and writes) the shared config.
    Measured in Task 7 while choosing the hook mechanism. Reading it from
    production means `--devs` resolves BEFORE the worktree exists, so a
    refusal leaves nothing behind.
    """
    runner = runner or CommandRunner()
    root = root or identity.production_root()
    result = runner.run(
        ["git", "-C", str(root), "config", "--get", "user.name"], check=False,
    )
    return result.stdout.strip()


def roster_root(worktree: Path, production: Path) -> Path:
    """Which `developers.yaml` `--devs` is validated against.

    The branch's own once it exists -- `dev-admin provision` can add a
    developer INSIDE a branch, and production's roster would then refuse the
    name for existing only where it was supposed to. Before the first `up`
    the worktree does not exist and production's is the only roster there is.
    Either way `resolve_devs` still checks the name against a real roster, so
    the typo guard survives.
    """
    return worktree if (worktree / DEVELOPERS_FILE).is_file() else production


def resolve_devs(
    requested: str | Sequence[str] | None,
    *,
    root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    runner: CommandRunner | None = None,
) -> tuple[str, ...]:
    """Which developers get an agent in this branch. Never guesses.

    `--devs` accepts `none`, `all`, or a comma-separated list. Unset, it falls
    back to `$AURORA_DEV` and then to the `developers.yaml` entry whose
    `forgejo_user` matches `git config user.name`. If neither resolves this
    RAISES, naming both mechanisms, because the plausible defaults are both
    wrong in a way that is invisible:

    * defaulting to `all` starts every developer's agent in every branch,
      which is spec D7 inverted and the exact defect `COMPOSE_PROFILES=agents`
      already produced once;
    * defaulting to `none` produces a branch with no agent whose
      `/agent/<user>/` URLs 404, and the developer concludes the feature is
      broken.

    Names are validated against `developers.yaml`. An unknown name would
    render `COMPOSE_PROFILES=agent-<typo>`, which activates no profile, starts
    no agent, and is not an error anywhere.
    """
    environ = os.environ if environ is None else environ
    known = known_developers(root)

    if requested is None:
        from_env = (environ.get(DEV_ENV_VAR) or "").strip()
        if from_env:
            wanted = _split_devs(from_env)
        else:
            name = git_user_name(root, runner)
            matched = [dev for dev in known if dev == name]
            if not matched:
                raise BranchError(
                    "cannot tell which developer this branch is for, and "
                    "refusing to guess. Resolution was attempted two ways: "
                    f"${DEV_ENV_VAR} is "
                    + (f"{from_env!r}" if from_env else "unset")
                    + f", and `git config user.name` is "
                    + (f"{name!r}" if name else "unset")
                    + f", which matches no `forgejo_user` in {DEVELOPERS_FILE} "
                    f"({', '.join(known)}). Pass --devs <user>, --devs all or "
                    "--devs none explicitly. Guessing `all` would start every "
                    "developer's agent in every branch (spec D7) and guessing "
                    "`none` would produce a branch whose /agent/ URLs are all "
                    "dead."
                )
            return tuple(matched)
    elif isinstance(requested, str):
        wanted = _split_devs(requested)
    else:
        wanted = [str(item).strip() for item in requested if str(item).strip()]

    if wanted == ["none"]:
        return ()
    if wanted == ["all"]:
        return known

    unknown = sorted(set(wanted) - set(known))
    if unknown:
        raise BranchError(
            f"--devs names {unknown}, which {DEVELOPERS_FILE} does not list "
            f"({', '.join(known)}). An unknown name is not an error to "
            "Compose: it renders COMPOSE_PROFILES=agent-<name>, activates no "
            "profile, starts no agent, and looks like a branch that simply "
            "has none."
        )
    # Deduplicated in `developers.yaml` order, so the profile string and the
    # access document list developers the same way every time.
    return tuple(dev for dev in known if dev in set(wanted))


def _split_devs(value: str) -> list[str]:
    return [piece.strip() for piece in value.split(",") if piece.strip()]


# ---------------------------------------------------------------------------
# step 0: the auth key (decision D-D, revised by spec 2026-08-01 P6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthKey:
    """A resolved auth key and its provenance.

    `value` is the key. `__repr__` is overridden and drops it, because a
    traceback prints the reprs of locals and `TS_AUTHKEY` is marked
    `secret: true` for a reason. `source` and `minted` are what may safely
    appear in a note, a document or a log line -- and `source` is the reason
    this is a dataclass rather than a `str`: a branch that fell back to the
    shared reusable key must be able to SAY so.
    """

    value: str
    source: str
    minted: bool = False
    key_id: str | None = None
    expiry_seconds: int | None = None

    def __repr__(self) -> str:
        return (
            f"AuthKey(source={self.source!r}, minted={self.minted}, "
            f"key_id={self.key_id!r}, value=<redacted>)"
        )

    __str__ = __repr__


def normalise_authkey(value: str, *, where: str) -> str:
    """Strip surrounding whitespace and quotes, then RE-CHECK the result.

    `TS_AUTHKEY_BRANCH` comes out of a file a human edited, and a key carrying
    surrounding whitespace or quotes is written verbatim into the branch
    `.env`, handed to the sidecar, rejected by Tailscale -- and the sidecar
    still starts. That is the fail-open shape finding F3 is about, one
    variable over. A MINTED key goes through the same normalisation: not
    because the API is expected to return a padded key, but because a check
    that only some keys pass through is a check with a hole in it.
    """
    key = value.strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
        key = key[1:-1].strip()
    if not key:
        raise BranchError(
            f"the auth key from {where} is empty once whitespace and quotes "
            "are stripped."
        )
    bad = sorted({ch for ch in key if ch.isspace() or ch in "\"'"})
    if bad:
        raise BranchError(
            f"the auth key from {where} still contains {bad} after "
            "normalisation. A Tailscale auth key contains neither whitespace "
            "nor quotes, and a malformed one is not a visible failure: the "
            "sidecar starts anyway and stays `Logged out.`"
        )
    return key


def resolve_authkey(
    *,
    environ: Mapping[str, str] | None = None,
    production_env: Mapping[str, str] | None = None,
) -> str:
    """The SUPPLIED ephemeral auth key, from the environment or production's `.env`.

    The fallback half of `resolve_branch_authkey`, kept as its own function
    because it is the path a host with no OAuth client takes and it must keep
    behaving exactly as it did. It raises, with instructions, rather than
    falling back to a keyless sidecar -- because a keyless sidecar does not
    fail. It starts, reports `Logged out.`, and stays running, so the branch
    would "succeed" with a dead URL (trap 9).
    """
    environ = os.environ if environ is None else environ
    sources: list[tuple[str, str]] = []
    raw = environ.get(AUTHKEY_ENV_VAR)
    if raw:
        sources.append((f"${AUTHKEY_ENV_VAR}", raw))
    if production_env is None:
        production_env = identity.production_env()
    raw = production_env.get(AUTHKEY_PRODUCTION_VAR)
    if raw:
        sources.append((
            f"{AUTHKEY_PRODUCTION_VAR} in production's {envfile.ENV_FILE_NAME}",
            raw,
        ))

    if not sources:
        raise BranchError(
            "no ephemeral Tailscale auth key is available, and none could be "
            "minted.\n"
            f"  Preferred (spec P6): set {tailnet.CLIENT_ID_PRODUCTION_VAR} "
            f"and {tailnet.CLIENT_SECRET_PRODUCTION_VAR} in production's "
            f"{envfile.ENV_FILE_NAME} from an OAuth client with the "
            "`auth_keys` scope, and every branch mints its own tagged, "
            "single-use, EPHEMERAL key.\n"
            "  Otherwise create one in the Tailscale admin console "
            "(Settings -> Keys -> Generate auth key) as:\n"
            "      Reusable, Ephemeral, Pre-approved\n"
            "  Ephemeral so the node deregisters itself when the branch is "
            "torn down; reusable so one key serves every branch; pre-approved "
            "so the node needs no manual approval before it can serve.\n"
            f"  Then either export ${AUTHKEY_ENV_VAR}=tskey-... or add\n"
            f"      {AUTHKEY_PRODUCTION_VAR}=tskey-...\n"
            f"  to production's {envfile.ENV_FILE_NAME}.\n"
            "  Refusing to start a branch without one: a tailscaled with no "
            "key does NOT fail. It starts, stays `Logged out.`, and the "
            "branch would report success with a dead URL."
        )

    where, value = sources[0]
    return normalise_authkey(value, where=where)


def resolve_branch_authkey(
    name: str,
    *,
    environ: Mapping[str, str] | None = None,
    production_env: Mapping[str, str] | None = None,
    minter: Callable[..., tailnet.MintedKey] | None = None,
    notes: list[str] | None = None,
) -> AuthKey:
    """One tagged, ephemeral, single-use key for THIS branch -- or the old key.

    Spec 2026-08-01 P6. Precedence, and each step is a decision:

    1. `$AURORA_TS_AUTHKEY`, if exported. An explicit key from a human is an
       explicit instruction, and it is also the opt-out: there is no separate
       "do not mint" switch to get out of sync with this one.
    2. a freshly minted key, if production's `.env` carries an OAuth client.
       Tagged `tag:aurora-branch`, `ephemeral: true`, `reusable: false`.
    3. `TS_AUTHKEY_BRANCH`, exactly as before.

    **Why 2 matters beyond hygiene.** A key that is not ephemeral produces a
    node that deregisters roughly an hour after it stops rather than at
    teardown. On 2026-07-31 that wedged a branch: `aurora-hubdemo` was still
    registered, the replacement sidecar was given `aurora-hubdemo-1`, and
    Caddy could not obtain a certificate for its own configured hostname. The
    stack was up and healthy by every container check and served nothing.

    **A failed mint falls back rather than failing the branch**, and says so
    in `notes`. Refusing to create a branch because api.tailscale.com blipped
    is a worse outcome than creating one on the shared key -- but a silent
    downgrade would make P6 untestable in production, so the fallback is
    recorded the same way `--force` is: in the notes that reach
    `BRANCH-ACCESS.md`, where an un-ephemeral branch is never invisible.
    """
    environ = os.environ if environ is None else environ
    if production_env is None:
        production_env = identity.production_env()
    notes = notes if notes is not None else []

    explicit = (environ.get(AUTHKEY_ENV_VAR) or "").strip()
    if explicit:
        return AuthKey(
            value=normalise_authkey(explicit, where=f"${AUTHKEY_ENV_VAR}"),
            source=f"${AUTHKEY_ENV_VAR} (supplied; minting not attempted)",
        )

    client = tailnet.oauth_client(
        environ=environ, production_env=production_env)
    if client is not None:
        mint = minter if minter is not None else tailnet.mint_branch_key
        try:
            key = mint(name, client=client)
        except tailnet.TailnetError as exc:
            # NOTE, and it is not a style choice: this string is rendered
            # verbatim into `BRANCH-ACCESS.md`, and `access_doc` refuses any
            # document that so much as NAMES a variable `branch-env.yaml`
            # marks `secret: true`. Writing `TS_AUTHKEY_BRANCH` here would
            # therefore not leak a key -- it would abort `branch up` at the
            # document, several steps after the thing that went wrong. The
            # variable is described rather than named.
            notes.append(
                "TAILNET KEY NOT MINTED: falling back to the shared, reusable "
                f"branch key supplied in production's {envfile.ENV_FILE_NAME}. "
                f"{exc}\n"
                "  This branch's tailnet node is therefore NOT ephemeral: it "
                "deregisters roughly an hour after teardown rather than at "
                "it, and until it does, a branch of the same name comes back "
                "as `<hostname>-1` and Caddy cannot get a certificate for the "
                "hostname it was configured with (measured 2026-07-31)."
            )
        else:
            return AuthKey(
                value=normalise_authkey(
                    key.secret, where=f"a key minted from {client.source}"),
                source=(
                    f"minted per-branch via {client.source}: "
                    f"{', '.join(key.tags)}, ephemeral, single-use, "
                    f"expires in {key.expiry_seconds}s"
                ),
                minted=True,
                key_id=key.key_id,
                expiry_seconds=key.expiry_seconds,
            )

    return AuthKey(
        value=resolve_authkey(
            environ=environ, production_env=production_env),
        source=(
            f"{AUTHKEY_PRODUCTION_VAR} in production's "
            f"{envfile.ENV_FILE_NAME} (shared and reusable; set "
            f"{tailnet.CLIENT_ID_PRODUCTION_VAR}/"
            f"{tailnet.CLIENT_SECRET_PRODUCTION_VAR} to mint per branch)"
        ),
    )


# ---------------------------------------------------------------------------
# step 0: the `.env` readers must agree (finding F3)
# ---------------------------------------------------------------------------


def assert_env_is_unambiguous(text: str, *, where: str) -> None:
    """Refuse a `.env` whose values this repository's readers read differently.

    Finding F3, measured on this host 2026-07-30. There are three `.env`
    readers -- `identity._read_env_file`, `envfile.parse_env` and
    `hooks/pre-push`'s shell -- and they disagree on 6 of 9 value shapes.
    `envfile.parse_env` already refuses whitespace-padded assignments and now
    refuses quoted ones for the same reason, so calling it IS this check;
    this wrapper exists to say what the refusal means at this point in `up`,
    because the consequence is not "a malformed file" but a DEFENCE THAT
    FAILS OPEN:

        DOMAIN_NAME="superserver...."  -> pre-push verdict=allow on a push
        DOMAIN_NAME='superserver....'     to a BRANCH forge, where the
        DOMAIN_NAME=superserver....       unquoted form correctly rejects.

    The mechanism: the hook derives the tailnet suffix by stripping the first
    label off `DOMAIN_NAME`, so a stray quote or space rides along into the
    suffix, the branch host no longer matches it, and the push falls through
    to the allow-everything rule. A `DOMAIN_NAME` with spaces around `=` is
    not fail-open but is not right either: the hook's `sed` does not match the
    line at all, production's domain comes out empty, and production is then
    allowed only by fall-through rather than recognised -- Task 7's M7 lesson
    exactly, where `exit 0` had two sources and the test could not tell them
    apart.
    """
    try:
        envfile.parse_env(text)
    except envfile.EnvFileError as exc:
        raise BranchError(
            f"{where} cannot be used to render a branch: {exc}\n"
            "  This is refused rather than normalised because the three "
            "`.env` readers in this repository disagree about what such a "
            "value MEANS, and one of them is the pre-push hook. A quoted or "
            "padded DOMAIN_NAME makes that hook allow a push to a branch "
            "forge -- a cross-wiring defence that fails OPEN, which is the "
            "worst available outcome."
        ) from exc


# ---------------------------------------------------------------------------
# the worktree (spec 7.1)
# ---------------------------------------------------------------------------


def _branch_ref_exists(runner: CommandRunner, root: Path, name: str) -> bool:
    result = runner.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "--quiet",
         f"refs/heads/{name}"],
        check=False,
    )
    return result.returncode == 0


def _add_worktree(
    runner: CommandRunner,
    root: Path,
    worktree: Path,
    name: str,
    from_ref: str | None,
) -> bool:
    """`git worktree add`. Returns True when an existing branch was reused.

    Spec 7.1: `--from <ref>` creates the branch from that ref and FAILS if it
    already exists; without `--from`, an existing branch is reused. The
    existence check is explicit rather than left to git so the message says
    which of the two the caller wanted.
    """
    # In `_add_worktree` and not in a caller, because there are two callers and
    # only one of them was ever checked. `from_ref` is the only free-form
    # string on the developer wire -- `mcp._tool_branch_up` takes it straight
    # off JSON-RPC with nothing but an `isinstance(str)` test -- and it lands
    # in an OPTION slot of `git worktree add` below. No shell is involved, so
    # this is hardening rather than injection; git reads a leading `-` as a
    # flag, and every other input to this function is constructed.
    if from_ref is not None and from_ref.startswith("-"):
        raise BranchError(
            f"{from_ref!r} is not a ref: a ref may not begin with '-'. It "
            "would be read as an option by `git worktree add`."
        )
    if worktree.exists():
        raise BranchError(
            f"{worktree} already exists. A branch's worktree is created by "
            "`branch up` and removed by `branch down`; refusing to build on "
            "top of whatever is there."
        )
    exists = _branch_ref_exists(runner, root, name)
    if from_ref is not None:
        if exists:
            raise BranchError(
                f"--from {from_ref!r} creates branch {name!r} from that ref, "
                f"but {name!r} already exists. Drop --from to reuse the "
                "existing branch, or choose another name."
            )
        argv = ["git", "-C", str(root), "worktree", "add", "-b", name,
                str(worktree), from_ref]
    elif exists:
        argv = ["git", "-C", str(root), "worktree", "add", str(worktree), name]
    else:
        argv = ["git", "-C", str(root), "worktree", "add", "-b", name,
                str(worktree)]
    runner.run(argv)
    return exists and from_ref is None


# ---------------------------------------------------------------------------
# the branch .env
# ---------------------------------------------------------------------------


def write_branch_env(path: Path, text: str) -> Path:
    """Write the branch `.env` at mode 0600, creating it that way.

    Created with the mode rather than `chmod`-ed afterwards, and `fchmod`-ed
    as well so an existing file is corrected rather than inherited: a window
    in which a tailnet auth key is world-readable is still a window, and
    decision D-F puts this file inside the tree production's Hermes
    bind-mounts, where every production agent container could read it.
    """
    path = Path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, ENV_FILE_MODE)
    try:
        # Explicit, because `os.open`'s mode is masked by the umask and does
        # nothing at all when the file already exists.
        os.fchmod(fd, ENV_FILE_MODE)
        with os.fdopen(fd, "w", encoding="utf-8", closefd=True) as handle:
            handle.write(text)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    return path


# ---------------------------------------------------------------------------
# tailnet readiness (trap 9)
# ---------------------------------------------------------------------------


def tailscale_readiness(status: Mapping[str, Any], hostname: str) -> str:
    """`""` when the node is serving, otherwise why it is not.

    Two conditions, checked separately and reported separately, because they
    fail for different reasons and the message is the whole diagnostic:

    * `BackendState != "Running"` -- no key, a rejected key, or a node still
      registering. This is trap 9: the container is `running` and healthy in
      every sense Docker knows about.
    * `Self.DNSName` not under `hostname` -- the node joined, but as some
      other name. Tailscale appends `-1` when a name is taken, and a branch
      whose node is `aurora-demo-1` has a certificate and a URL nobody was
      told about.
    """
    state = status.get("BackendState")
    if state != "Running":
        return (
            f"the tailnet node reports BackendState={state!r}, not 'Running'. "
            "A tailscaled with a missing or rejected auth key does NOT fail: "
            "it starts, stays `Logged out.`, and every URL for this branch "
            "would resolve to nothing."
        )
    dns = str((status.get("Self") or {}).get("DNSName") or "")
    if not dns.startswith(f"{hostname}."):
        return (
            f"the tailnet node joined as Self.DNSName={dns!r}, which is not "
            f"under the requested hostname {hostname!r}. Tailscale appends a "
            "suffix when a name is already taken, so this branch's "
            "certificate and URLs would be issued for a name nobody was given."
        )
    return ""


# ---------------------------------------------------------------------------
# the orchestration
# ---------------------------------------------------------------------------


def stripped_environ() -> dict[str, str]:
    """The ambient environment, minus the compose variables a branch must own.

    One implementation, shared by `up`, `rebuild` and anything else that
    invokes Compose: an exported `COMPOSE_PROFILES` in the invoking shell
    silently changes which services exist, and an exported
    `COMPOSE_PROJECT_NAME` silently changes which project they land in.
    """
    return {k: v for k, v in os.environ.items() if k not in STRIPPED_COMPOSE_VARS}


def compose_argv(project: str, *args: str) -> list[str]:
    """`docker compose` for one branch project, with the full file set.

    All three `-f` files and an explicit `--env-file`, every time. Task 8's
    open item 2 is why this is one function: a command that passes a different
    file set resolves a DIFFERENT project graph, so `up`, `down` and `rebuild`
    disagreeing about the file list is a branch that cannot be rebuilt or torn
    down by the tool that created it.

    `-p <project>` is first and is not optional. It is the only thing between
    a `rebuild` and production's containers.
    """
    argv = ["docker", "compose", "-p", project]
    for name in COMPOSE_FILES:
        argv += ["-f", name]
    # Explicit, so the recorded command names the file the branch was
    # configured from instead of depending on Compose's discovery of a
    # `.env` in the working directory.
    argv += ["--env-file", envfile.ENV_FILE_NAME]
    return argv + list(args)


class _Up:
    """One `branch up`. A class only so the steps can share the seams."""

    def __init__(
        self,
        *,
        runner: CommandRunner,
        paths: identity.BranchPaths,
        production_root: Path,
        sleep: Callable[[float], None],
        monotonic: Callable[[], float],
        runtime: runtimes.Runtime | None = None,
    ) -> None:
        self.runner = runner
        self.paths = paths
        self.production_root = production_root
        self.sleep = sleep
        self.monotonic = monotonic
        self.runtime = runtime or runtimes.Runtime(runtimes.DOCKER)

    # -- compose ----------------------------------------------------------

    def compose_env(self) -> dict[str, str]:
        """The environment every compose invocation in this `up` runs with.

        ONE function, and it is the whole of the podman mechanism: strip the
        ambient compose variables, then set `DOCKER_HOST` from the resolved
        runtime. Every `-f` file, the project name and the overlay are
        identical between the two runtimes -- the only difference a branch on
        podman has is the socket this line names.
        """
        return self.runtime.environ(stripped_environ())

    def compose_argv(self, *args: str) -> list[str]:
        return compose_argv(self.paths.project, *args)

    def compose(self, *args: str, check: bool = True,
                timeout: float | None = None) -> CommandResult:
        return self.runner.run(
            self.compose_argv(*args),
            cwd=self.paths.worktree,
            env=self.compose_env(),
            check=check,
            timeout=timeout,
        )

    # -- steps ------------------------------------------------------------

    def up_services(self, *services: str) -> None:
        self.compose(
            "up", "-d", "--wait", "--wait-timeout", str(COMPOSE_WAIT_TIMEOUT),
            *services,
        )

    def up_everything(self, *, build: bool, held_back: Sequence[str] = ()) -> None:
        """`up -d`, optionally with some services scaled to zero.

        `held_back` exists for exactly one caller and one reason: `dev-admin`
        declares `command: ["reconcile"]` and `restart: "no"`, so the ordinary
        `up -d` RUNS a reconcile the moment the container starts. P3 rotates
        the Forgejo admin credential and has to do it before anything consumes
        the inherited one -- and `up -d` was that consumer, several steps
        before the rotation. Compose has no `--exclude`, so `--scale <svc>=0`
        is the spelling: the service is resolved, its config is validated, and
        zero containers are created. The second `up` (no `--scale`) starts it,
        by which time the branch `.env` carries the branch's OWN token.
        """
        args = ["up", "-d"]
        if build:
            args.append("--build")
        for service in held_back:
            args.extend(["--scale", f"{service}=0"])
        self.compose(*args)

    def await_tailnet(self) -> None:
        deadline = self.monotonic() + TAILSCALE_READY_TIMEOUT
        reason = "the tailnet node was never polled"
        while True:
            result = self.compose(
                "exec", "-T", overlay.SIDECAR_SERVICE,
                "tailscale", f"--socket={TAILSCALE_SOCKET}", "status", "--json",
                check=False,
            )
            if result.returncode == 0:
                try:
                    status = _load_json(result.stdout)
                except ValueError as exc:
                    reason = f"`tailscale status --json` returned no JSON: {exc}"
                else:
                    reason = tailscale_readiness(status, self.paths.hostname)
                    if not reason:
                        return
            else:
                reason = (
                    "`tailscale status` could not be run in the sidecar: "
                    f"{result.stderr.strip() or result.stdout.strip() or 'exit ' + str(result.returncode)}"
                )
            if self.monotonic() >= deadline:
                raise BranchError(
                    f"the branch's tailnet node did not become ready within "
                    f"{TAILSCALE_READY_TIMEOUT:.0f}s: {reason}"
                )
            self.sleep(TAILSCALE_POLL_INTERVAL)

    def await_https(self) -> None:
        """Poll the branch's own Forgejo URL until it answers.

        MagicDNS registration and Caddy's certificate issuance are not
        instantaneous, and `reconcile` -- the next step -- talks to the branch
        over exactly this URL. Without this poll the failure surfaces as a
        `reconcile` that cannot reach its own forge, which reads like a
        Forgejo problem.

        Deliberately NOT `--insecure`. A branch's certificate coming from its
        own tailscaled is the property being waited for; skipping validation
        would wait for the wrong thing.
        """
        url = f"https://{self.paths.domain}/git/"
        deadline = self.monotonic() + HTTP_READY_TIMEOUT
        reason = "never polled"
        while True:
            result = self.runner.run(
                ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}",
                 "--max-time", "10", url],
                check=False,
            )
            code = result.stdout.strip()
            if result.returncode == 0 and code.startswith("2"):
                return
            reason = (
                f"HTTP {code or '(none)'}"
                + (f", {result.stderr.strip()}" if result.stderr.strip() else "")
            )
            if self.monotonic() >= deadline:
                raise BranchError(
                    f"{url} did not answer within {HTTP_READY_TIMEOUT:.0f}s: "
                    f"{reason}. MagicDNS registration and certificate issuance "
                    "are what this waits for, and `reconcile` needs both."
                )
            self.sleep(HTTP_POLL_INTERVAL)

    def mint_forgejo_token(self, login: str, name: str) -> str:
        """Run the branch Forgejo's own CLI to mint an admin token.

        Forgejo 15.0.5 answers `401 auth method not allowed` to every form of
        token authentication on `POST /api/v1/users/{u}/tokens` -- it wants a
        password, and no password exists on this host. The CLI is the
        supported alternative and it writes straight to the branch's own
        database.

        Three things about this call are deliberate:

        * `--raw`, so stdout is the token and nothing else. Anything chattier
          would have to be parsed, and a parser that gets it wrong writes a
          log line into a `.env`.
        * the token appears only in STDOUT, never in argv. `Invocation.argv`
          is recorded and printed by the tests, and `CommandRunner.run`
          interpolates argv into its failure message.
        * `check=False`, and the failure message repeats only stderr. Measured:
          a failed run writes a LOG LINE to stdout and nothing to stderr, so a
          caller that trusted stdout would put a timestamp in a `.env` — and
          on a partial failure stdout can hold part of a token, which is the
          one thing that must never reach an exception that gets printed.
        """
        result = self.compose(
            "exec", "-T", "--user", FORGEJO_CONTAINER_USER, FORGEJO_SERVICE,
            FORGEJO_ADMIN_CLI, "admin", "user", "generate-access-token",
            "--username", login,
            "--token-name", name,
            "--scopes", ",".join(forgejo_token.TOKEN_SCOPES),
            "--raw",
            check=False,
        )
        if result.returncode != 0:
            raise forgejo_token.ForgejoTokenError(
                f"`forgejo admin user generate-access-token` for {login!r} in "
                f"the branch's Forgejo exited {result.returncode}: "
                f"{result.stderr.strip() or '(no stderr)'}. Its stdout is "
                "deliberately not repeated: on a partial failure it can hold "
                "part of a token."
            )
        return result.stdout

    def scope_forgejo_credential(self) -> forgejo_token.RotationReport:
        """Spec P3, and it MUST sit here: after `await_https`, before ANY consumer.

        After `await_https` because every step needs the branch's own Forgejo
        to be answering over its own URL -- the mint is an HTTP call to it.

        Before any consumer of `FORGEJO_ADMIN_TOKEN`. The previous version of
        this docstring said "before `reconcile` because `reconcile` is the
        first thing that USES it", and that sentence was FALSE -- it is the
        sentence that stopped anyone checking. `dev-admin` is an ordinary
        compose service with `command: ["reconcile"]`, `restart: "no"` and no
        `profiles:`, so the plain `up -d` above started it and it reconciled
        with PRODUCTION's inherited token several steps before this ran; the
        explicit `docker compose run --rm dev-admin reconcile` is the SECOND
        reconcile, not the first. Worse, between the two `up`s production's
        live admin token was readable from the branch's `dev-admin` container
        config, and `BranchUpFailed` deliberately tears nothing down -- so a
        failure in that window left the exposure on a half-built branch a
        human is being told to go and debug.
        `_Up.up_everything(held_back=...)` is the fix: the first `up` scales
        `dev-admin` to zero, so this rotation now genuinely precedes every use.

        Everything inside is ordered mint -> write -> purge, for the reason
        `forgejo_token`'s module docstring gives at length: the purge destroys
        the credential the mint authenticates with.
        """
        return forgejo_token.rotate_admin_token(
            base_url=f"https://{self.paths.domain}/git",
            branch_name=self.paths.name,
            env_file=self.paths.env_file,
            worktree=self.paths.worktree,
            write_env=write_branch_env,
            mint=self.mint_forgejo_token,
        )

    def reconcile(self) -> None:
        self.compose("run", "--rm", RECONCILE_SERVICE, RECONCILE_COMMAND)


def _load_json(text: str) -> Mapping[str, Any]:
    try:
        value = json.loads(text)
    except Exception as exc:  # noqa: BLE001 -- reported, not swallowed
        raise ValueError(str(exc)) from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"expected an object, got {type(value).__name__}")
    return value


def branch_up(
    name: str,
    *,
    from_ref: str | None = None,
    no_seed: bool = False,
    seed_strategy: str = seed.DEFAULT_STRATEGY,
    without: Sequence[str] = (),
    devs: str | Sequence[str] | None = None,
    limits: str | None = None,
    force: bool = False,
    build: bool = True,
    runtime: str | None = None,
    runner: CommandRunner | None = None,
    worktrees_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    sleep: Callable[[float], None] | None = None,
    monotonic: Callable[[], float] | None = None,
) -> BranchResult:
    """Create a branch stack. See the module docstring for why the order is this.

    Everything that can refuse does so BEFORE the worktree exists, so a
    refusal leaves nothing on the host at all. After that point a failure
    raises `BranchUpFailed`, which carries the `aurora branch down` command
    and does NOT tear anything down.
    """
    runner = runner if runner is not None else CommandRunner()
    environ = os.environ if environ is None else environ
    sleep = sleep if sleep is not None else time.sleep
    monotonic = monotonic if monotonic is not None else time.monotonic

    # Resolved BEFORE anything is created, with the rest of the refusals: an
    # unknown runtime name, or a podman socket that is not there, must not be
    # discovered after a worktree exists.
    runtime_name = runtimes.resolve_runtime(runtime, environ=environ)
    resolved_runtime = runtimes.for_name(runtime_name, environ=environ)

    # `--limits` next to it, and for the same reason: `overlay.sync_overlay`
    # runs AFTER `git worktree add` and after the `.env` write, so a typo in a
    # profile name used to be discovered only once a half-built branch existed.
    if limits is not None:
        overlay.resolve_limits(limits)

    # P4 x seeding do not compose, and this refuses rather than failing halfway.
    #
    # `seed._docker` is `subprocess.run([DOCKER, *args])` with no `env=`, so
    # every seeding call lands on the ROOT docker daemon whatever runtime this
    # branch is on. On podman that is not a missing parameter, it is a missing
    # DESIGN: `seed_agent_volume` mounts production's agent-home volume and the
    # branch's into ONE `docker run`, and a single container cannot mount one
    # volume from the root daemon and another from a rootless podman store. The
    # fix is an export/import stream, not an `env=` seam, and it is bigger than
    # this refusal.
    #
    # What happens without the refusal, both measured from the code:
    #   * `docker volume create` plants `br-<name>_*` volumes carrying this
    #     branch's compose labels INSIDE PRODUCTION'S DAEMON, filled with
    #     production's agent homes -- which `branch down --runtime podman` then
    #     sweeps the podman daemon for and never finds;
    #   * `seed.postgres_container` filters the root daemon for the branch's
    #     project label, finds nothing, and raises -- so `up` dies as
    #     `BranchUpFailed` AFTER the stack is already running on podman.
    # A second, independent blocker is recorded in
    # `forgejo_token.purge_production_credentials`: under rootless podman the
    # branch's `gitea.db` maps into the subuid range and the host-side purge
    # cannot open it read-write.
    if resolved_runtime.is_podman and not no_seed:
        raise BranchError(
            "--runtime podman cannot seed. Seeding runs `docker volume create` "
            "and `docker run` against the ROOT docker daemon (aurora_cli.seed "
            "has no runtime seam), and one container cannot mount production's "
            "agent-home volume from the root daemon alongside this branch's "
            "volume in the rootless podman store. Without this refusal the "
            "seed would plant labelled `br-` volumes full of production's "
            "agent homes inside PRODUCTION's daemon and then fail anyway, "
            "after the branch was already running.\n"
            f"      aurora branch up {name} --runtime podman --no-seed\n"
            "  gives an unseeded branch on podman: the stack comes up, but it "
            "is EMPTY -- no repositories, no agent memory, no AFFiNE "
            "documents -- and AFFiNE itself does not work at all unseeded on "
            "EITHER runtime (docs/issues, defect D3: the Postgres data "
            "directory is created 1000:1000 while the backends run as uid "
            "999). Seeded branches stay on docker until aurora_cli.seed learns "
            "to stream between daemons."
        )

    production_root = identity.production_root()
    paths = identity.branch_paths(name)
    if worktrees_root is not None:
        worktree = Path(worktrees_root) / paths.name
        paths = replace(
            paths,
            worktree=worktree,
            env_file=worktree / envfile.ENV_FILE_NAME,
            access_doc=worktree / paths.access_doc.name,
        )

    result = BranchResult(requested_name=name, paths=paths, from_ref=from_ref)
    result.runtime = runtime_name
    if resolved_runtime.is_podman:
        result.notes.append(runtimes.describe(resolved_runtime) + (
            ". This branch's containers, images and build cache live in this "
            "user's rootless podman store, not in production's. Production's "
            "root docker daemon is not merely guarded against from here -- the "
            "socket that reaches it is refused by SELinux and by the rootless "
            "id map, measured both ways."
        ))
    if result.sanitised:
        result.notes.append(
            f"the requested name {name!r} was sanitised to {paths.name!r} "
            "(spec 7.1: one DNS label, lowercase, alphanumerics and `-`, "
            f"short enough that {paths.hostname!r} fits in 63 octets)."
        )

    # -- refusals, all before anything is created -------------------------

    # The render source is checked BEFORE it is used. See finding F3: an
    # ambiguous value here does not produce a malformed branch, it produces a
    # pre-push hook that allows a push to a branch forge.
    assert_env_is_unambiguous(
        envfile.production_env_text(),
        where=f"production's {envfile.ENV_FILE_NAME} at {envfile.production_env_path()}",
    )

    resolved_devs = resolve_devs(
        devs, root=roster_root(paths.worktree, production_root),
        environ=environ, runner=runner,
    )
    result.devs = resolved_devs

    # VALIDATE, then take the closure. The other order computes the closure of
    # an unvalidated list and throws it away when the validation refuses, which
    # is harmless today only because `closure` keeps unknown names instead of
    # raising -- i.e. it reads as accidental and is one edit from being wrong.
    if without:
        exclusions.validate_excludable(without)
    excluded = tuple(sorted(exclusions.closure(without))) if without else ()
    result.excluded = excluded

    result.resources = check_resources(disk_path=production_root, force=force)
    if force and not result.resources.ok:
        result.notes.append(
            "RESOURCE GUARD OVERRIDDEN with --force: "
            + "; ".join(result.resources.shortfalls())
            + ". This branch may be killed by the kernel or fill the disk."
        )

    # P6. LAST among the refusals, because it is the only one with a side
    # effect that outlives the process. Minting reaches the network and creates
    # a tagged, preauthorized key on the TAILNET; nothing deletes it, and it
    # lives `tailnet.KEY_EXPIRY_SECONDS`. Minting first -- as this did -- meant
    # `--without <typo>` or a failed resource guard aborted AFTER a usable key
    # had been created, and the comment defending the position ("a branch that
    # cannot get a key leaves nothing on the host") was true about the host and
    # false about the tailnet. Everything above this line can still refuse and
    # now does so before anything exists anywhere.
    #
    # `result.notes` is passed in so a fallback to the shared reusable key
    # lands in `BRANCH-ACCESS.md` rather than nowhere.
    authkey = resolve_branch_authkey(
        paths.name, environ=environ, notes=result.notes)
    result.authkey_source = authkey.source

    # -- from here on a failure leaves something behind -------------------

    reused = _add_worktree(
        runner, production_root, paths.worktree, paths.name, from_ref,
    )
    result.reused_branch = reused
    teardown = f"aurora branch down {paths.name}"

    try:
        up = _Up(
            runner=runner, paths=paths, production_root=production_root,
            sleep=sleep, monotonic=monotonic, runtime=resolved_runtime,
        )

        # The `.env` FIRST, before any compose invocation. `docker compose
        # config` interpolates `${DOCKER_GID}` and cannot resolve a worktree
        # that has no `.env` (Task 3's open item 4).
        env_text = envfile.render_branch_env(
            paths.name,
            devs=resolved_devs,
            # `.value`, not the dataclass. `AuthKey.__repr__` redacts the key,
            # so passing the object here renders `TS_AUTHKEY=AuthKey(...)`
            # into the branch `.env` -- a sidecar that starts, stays
            # `Logged out.` and serves a dead URL, which is trap 9 reached by
            # a new route. Caught by the 0600 test, which asserts the KEY is
            # in the file rather than that a file was written.
            authkey=authkey.value,
            exclusions_env=exclusions.env_overrides_for(without) if without else None,
        )
        defects = envfile.missing_overrides(
            env_text, paths.name,
            allowed_production_references=exclusions
            .production_reference_exemptions(without),
        )
        if defects:
            raise BranchError(
                "the rendered branch `.env` would leave the branch wired to "
                "production or unable to start:\n  "
                + "\n  ".join(defects)
            )
        write_branch_env(paths.env_file, env_text)

        exclusions.write_exclusion_overlay(excluded, paths.worktree)

        # `compose.branch.yml` is TRACKED, so the worktree already carries the
        # committed ceilings and the common path renders nothing. Re-render
        # only when a profile was asked for -- including `none`, which is how
        # a branch gets no ceilings at all for benchmarking.
        #
        # KNOWN DEFECT, recorded rather than hidden. Re-rendering here modifies
        # a file GIT TRACKS, inside the worktree, which has two costs:
        #   * `git worktree remove` refuses a worktree with modified tracked
        #     files, so `aurora branch down` on a `--limits`-flavoured branch
        #     needs `--force` or leaks its worktree -- the leaked-worktree
        #     regression P4 closed, arriving through a third door;
        #   * `git commit -a` in that branch carries ONE branch's ceilings
        #     (possibly none at all) into a PR against the committed artefact,
        #     which `test_overlay_is_not_stale` then fails for everyone.
        # `exclusions.write_exclusion_overlay` is the seam that does this
        # correctly -- `compose.exclude.yml` is gitignored with a comment
        # saying exactly why -- and per-branch ceilings are the same kind of
        # fact. Moving them there means a FOURTH entry in `COMPOSE_FILES`, and
        # `docker compose -f` is a hard error on a missing file: measured
        # 2026-08-01, branches `br-hubdev` and `br-pytest-373957-1` are live on
        # this host with worktrees that would not have the new file, so the
        # change would make them untearable-down by this tool. Making the `-f`
        # list conditional is not an option either -- `compose_argv` exists
        # precisely so `up`, `down` and `rebuild` cannot resolve different
        # graphs. So the fix waits for a migration step, and until then the
        # cost is stated in the branch's own access document instead of being
        # discovered at teardown.
        if limits is not None:
            overlay.sync_overlay(paths.worktree, limits=limits)
            result.notes.append(
                f"resource ceilings: profile {limits!r}"
                + (" -- NO CEILINGS: this branch can exhaust the host"
                   if limits == overlay.LIMITS_NONE else "")
            )
            result.notes.append(
                f"--limits RE-RENDERED THE TRACKED {overlay.OVERLAY_NAME} in "
                "this worktree, so git sees a modified tracked file here. Two "
                f"consequences: `aurora branch down {paths.name}` will need "
                "`--force` (git refuses to remove a worktree with modified "
                "tracked files), and `git commit -a` in this branch would "
                f"carry THIS branch's ceilings into a PR. Restore it with "
                f"`git -C {paths.worktree} checkout -- {overlay.OVERLAY_NAME}` "
                "before committing anything."
            )

        if no_seed:
            result.notes.append(
                "NOT SEEDED (--no-seed): this branch's Forgejo, Hermes and "
                "AFFiNE start empty. Nothing in it shares production's users, "
                "repositories or agent identities."
            )
        else:
            result.seeded = True
            outcome = _seed(
                paths=paths, production_root=production_root,
                devs=resolved_devs, strategy=seed_strategy,
            )
            result.seed_report = outcome.report

        # The record first, so a teardown of a HALF-BUILT branch still knows
        # which daemon to ask. `up` is not atomic and says so; the artefact
        # that says where the containers went must exist before any are made.
        runtimes.record_runtime(paths.worktree, runtime_name)

        # Then the relabel, and its position is measured, not preferred: it
        # must run AFTER the seed (which writes most of the tree) and BEFORE
        # the first `up`. New files inherit the directory's type, so one pass
        # here covers what the containers write later; a pass before the seed
        # would cover almost nothing.
        if resolved_runtime.is_podman:
            # `worktrees_root` threaded through, so the guard inside is
            # asked about the SAME directory this `up` was told to build in.
            # Without it a lifecycle test driving `worktrees_root=tmp_path`
            # could not reach the relabel at all, and the relabel was
            # therefore "tested" by spelling `chcon` again by hand.
            note = runtimes.relabel_worktree(
                paths.worktree, runner=runner, worktrees_root=worktrees_root)
            if note:
                result.notes.append(note)

        postgres = seed.postgres_service(paths.worktree)
        up.up_services(postgres)

        if result.seeded:
            # D-E: restore into a running, healthy branch Postgres, BEFORE the
            # rest of the stack, so `affine_migration` runs against restored
            # data instead of an empty schema.
            seed.restore_postgres(
                seed.postgres_container(paths.project, paths.worktree),
                outcome.dump,
                report=result.seed_report,
            )

        # `dev-admin` is held back from THIS `up` -- see
        # `_Up.up_everything` and `scope_forgejo_credential`. It declares
        # `command: [reconcile]`, so starting it here would reconcile with
        # production's inherited FORGEJO_ADMIN_TOKEN before P3 ever runs.
        # Skipped when the service is excluded outright: `--scale` on a
        # service the resolved config does not contain is a compose error.
        held_back = (
            () if RECONCILE_SERVICE in excluded else (RECONCILE_SERVICE,)
        )
        up.up_everything(build=build, held_back=held_back)
        up.await_tailnet()
        up.await_https()

        # P3. Only where there is something to scope: an unseeded branch's
        # Forgejo is empty, so it holds no production credential to mint from
        # or to delete, and a `--without forgejo` branch has no forge at all.
        # Both conditions are recorded rather than skipped quietly -- "it did
        # not run" and "it ran and found nothing" must not look the same.
        # These notes are rendered verbatim into `BRANCH-ACCESS.md`, and
        # `access_doc` refuses a document that NAMES a `secret: true`
        # variable -- which `FORGEJO_ADMIN_TOKEN` now is. Naming it here would
        # abort `branch up` at the document rather than leak anything, which
        # is a confusing way to fail. Described, not named.
        if not result.seeded:
            result.notes.append(
                "FORGEJO ADMIN CREDENTIAL NOT ROTATED: this branch was not "
                "seeded, so its Forgejo starts empty and holds none of "
                "production's credentials. Nothing to scope."
            )
        elif RECONCILE_SERVICE in excluded or FORGEJO_SERVICE in excluded:
            result.notes.append(
                "FORGEJO ADMIN CREDENTIAL NOT ROTATED: this branch has no "
                f"Forgejo ({', '.join(excluded)} excluded). Its `.env` still "
                "carries production's admin credential, inherited from "
                "production's own file."
            )
        else:
            result.token_rotation = up.scope_forgejo_credential()

        up.reconcile()
        # The SECOND up. `reconcile` creates no containers -- it computes what
        # should exist and emits `container.missing` -- so without this a
        # branch has no agent and every /agent/<user>/ URL is dead.
        up.up_everything(build=False)

        result.hook = crosswire.install_pre_push(paths.worktree)
        if not result.hook.effective:
            result.notes.append(result.hook.advice())
    except BranchUpFailed:
        raise
    except Exception as exc:
        raise BranchUpFailed(
            f"branch {paths.name!r} was not completed: {exc}\n"
            f"  Nothing has been torn down -- a half-built branch is the only "
            f"artefact you can debug from. When you are done, remove it with:\n"
            f"      {teardown}",
            teardown_command=teardown,
        ) from exc

    return result


@dataclass(frozen=True)
class SeedOutcome:
    """What seeding produced: the report, and the dump still to be restored.

    The dump travels as its own field rather than inside `SeedReport`, because
    that report is rendered into `BRANCH-ACCESS.md` and returned over MCP, and
    a 260 KB binary blob riding along inside it is how a database dump ends up
    in a document or a JSON-RPC response.
    """

    report: seed.SeedReport
    dump: bytes


def _seed(
    *,
    paths: identity.BranchPaths,
    production_root: Path,
    devs: Sequence[str],
    strategy: str,
) -> SeedOutcome:
    """Host-path state, agent home volumes, and the AFFiNE dump.

    Agent volumes are created and filled BEFORE `up`, so Compose adopts them
    (trap 6). The AFFiNE dump is taken here too, with the rest of the reading
    of production, and restored later once the branch's Postgres is healthy
    (D-E).

    A developer whose agent home cannot be seeded is FATAL, not a warning.
    That decision was left open by Task 6 and it goes this way because the
    alternative is silent: an unseeded agent home is adopted by Compose
    without complaint and surfaces days later as "my login does not work in
    the branch", with no clue pointing back here. `--no-seed` is the way to
    ask for a branch with no seeded state, and it says so in the access
    document.
    """
    seeder = seed.get_seeder(strategy)
    report = seeder.seed_paths(production_root, paths.worktree)
    src_project = identity.production_project()
    for dev in devs:
        seed.seed_agent_volume(dev, src_project, paths.project, report=report)
    dump = seed.dump_postgres()
    report.add(
        f"{seed.postgres_service(production_root)}:dump", seed.DUMP,
        bytes=len(dump),
        detail=(
            "pg_dump -Fc of production's AFFiNE database, read-only; restored "
            "after the branch's Postgres reports healthy (decision D-E) so "
            "the migration job runs against restored data"
        ),
    )
    return SeedOutcome(report=report, dump=dump)


# ---------------------------------------------------------------------------
# `aurora branch down` — teardown (Task 9)
# ---------------------------------------------------------------------------
#
# Everything else in this chunk fails by not working. This fails by destroying
# production. Every destructive call below is reachable only through
# guards.assert_branch_project / guards.assert_not_production_path, and
# tests/test_branch_isolation.py walks this module's AST to prove it.


@dataclass
class DownResult:
    """What a teardown actually removed. Reported, not inferred."""

    project: str
    worktree: Path
    used_fallback: bool = False
    containers_removed: tuple[str, ...] = ()
    volumes_removed: tuple[str, ...] = ()
    networks_removed: tuple[str, ...] = ()
    worktree_removed: bool = False
    notes: tuple[str, ...] = ()


def _docker_out(
    runner: CommandRunner,
    argv: Sequence[str],
    env: Mapping[str, str] | None,
) -> list[str]:
    """Read-only docker query. Not guarded: it destroys nothing.

    `env` carries the runtime's `DOCKER_HOST` and is REQUIRED -- it has no
    default, and that is the fix for a defect this docstring described while
    the code committed it. A query that reached the ROOT daemon while the
    teardown it feeds reached podman would enumerate production's objects and
    report a branch as clean: `branch_down` threaded `env` through every
    *before* query and every destructive call and dropped it from all four
    *after* queries, so a podman teardown asked docker whether the branch was
    gone, found nothing, suppressed every RESIDUE note and reported a clean
    removal over a live stack.

    `None` is still a legal value and still means "the ambient environment",
    but it now has to be WRITTEN by the caller. A parameter with a default is
    a parameter that can be forgotten; this one decides which daemon the
    answer comes from, so forgetting it must not be spellable.
    """
    result = runner.run(list(argv), env=env, check=False)
    return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]


def _labelled(
    runner: CommandRunner,
    kind: str,
    project: str,
    env: Mapping[str, str] | None,
) -> list[str]:
    """Objects carrying this project's compose label."""
    if kind == "container":
        argv = ["docker", "ps", "-aq", "--filter", f"label={identity.PROJECT_LABEL}={project}"]
    elif kind == "volume":
        argv = ["docker", "volume", "ls", "-q", "--filter",
                f"label={identity.PROJECT_LABEL}={project}"]
    else:
        argv = ["docker", "network", "ls", "-q", "--filter",
                f"label={identity.PROJECT_LABEL}={project}"]
    return _docker_out(runner, argv, env)


def _branch_named_volumes(
    runner: CommandRunner,
    project: str,
    env: Mapping[str, str] | None,
) -> list[str]:
    """Volumes whose NAME is in this branch's namespace but which carry no label.

    The Tasks 5-7 review measured this: a volume named `br-x_data` with no
    project label was removable by NOTHING. The guard refused it (no label to
    read), the label sweep could not see it, and every compose route failed —
    including after Compose adopted it, which does not add labels. Worse,
    residue reporting called it clean, so a teardown assertion would PASS over
    an object it could not remove.

    A name in the branch namespace is sufficient evidence on its own: nothing
    in production is named that way. ops/docker-guard agrees, by name.
    """
    every = _docker_out(runner, ["docker", "volume", "ls", "-q"], env)
    return [v for v in every if v == project or v.startswith(f"{project}_")]


def teardown_runtime(
    worktree: Path,
    requested: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Which runtime a teardown must address. The RECORD wins.

    `branch up` writes the runtime into the worktree, and that record is a
    measurement of where the containers actually went. A flag is a claim about
    the same thing, so when the two disagree this RAISES instead of picking
    one: teardown against the wrong daemon does not error -- it finds no
    containers carrying the label, removes nothing, and reports a clean
    removal over a stack that is still running and still costs memory. A
    teardown that lies about what it removed is worse than one that refuses.

    With no record -- a branch built before this flag existed, or one whose
    worktree was deleted by hand -- the flag and then `$AURORA_BRANCH_RUNTIME`
    answer, and the default is docker, which is what those branches are on.
    """
    recorded = runtimes.recorded_runtime(worktree)
    if recorded is None:
        return runtimes.resolve_runtime(requested, environ=environ)
    if requested is not None and requested != recorded:
        raise BranchError(
            f"--runtime {requested!r} contradicts {worktree}/"
            f"{runtimes.RUNTIME_RECORD_NAME}, which records that this branch "
            f"was built on {recorded!r}. Refusing to guess: a teardown pointed "
            "at the wrong daemon finds no containers carrying this project's "
            "label, removes nothing, and reports success over a stack that is "
            "still running."
        )
    return recorded


def branch_down(
    name: str,
    *,
    runtime: str | None = None,
    runner: CommandRunner | None = None,
    force: bool = False,
    snapshot_before: dict | None = None,
) -> DownResult:
    """Tear a branch stack down completely, and prove production survived.

    Order matters and each step depends on the one before it:
      1. guard the project name AND the worktree path, before anything runs;
      2. compose path from the worktree, so both compose files resolve;
      3. label-driven fallback for when the worktree is gone (N7) — the branch
         is still on the daemon and still costs disk;
      4. sweep volumes the label query cannot see (see _branch_named_volumes);
      5. remove the worktree, then prune the stale git administrative entry.
    """
    runner = runner or CommandRunner()
    paths = identity.branch_paths(name)

    # (1) Both guards, before a single command is issued. assert_branch_project
    # returns the project so the guarded value is the one actually used —
    # a guard whose result is discarded and recomputed is not a guard.
    project = guards.assert_branch_project(paths.project)
    worktree = guards.assert_not_production_path(paths.worktree)

    # Which daemon owns this branch, decided once, before any query. Every
    # command below runs with this env; a mix would enumerate one daemon and
    # destroy on another.
    runtime_name = teardown_runtime(worktree, runtime)
    resolved_runtime = runtimes.for_name(runtime_name, check_socket=False)
    env = resolved_runtime.environ(stripped_environ())

    notes: list[str] = []
    used_fallback = False

    containers_before = _labelled(runner, "container", project, env)
    volumes_before = sorted(
        set(_labelled(runner, "volume", project, env))
        | set(_branch_named_volumes(runner, project, env))
    )
    networks_before = _labelled(runner, "network", project, env)

    # (2) The compose path. Needs the worktree, because `-f compose.yml -f
    # compose.branch.yml` resolve relative to it.
    compose_ok = (worktree / "compose.yml").is_file()
    if compose_ok:
        result = runner.run(
            [
                "docker", "compose",
                "-p", project,
                "--profile", "*",
                "down", "-v", "--remove-orphans",
            ],
            cwd=worktree,
            env=env,
            check=False,
        )
        if result.returncode != 0:
            notes.append(
                f"compose down exited {result.returncode}; falling back to "
                "label-driven removal"
            )
            compose_ok = False
    else:
        notes.append(
            f"no compose.yml at {worktree}; using label-driven removal "
            "(worktree removed by hand, or `up` failed before populating it)"
        )

    # (3) Fallback. This is the path that manipulates Docker objects BY NAME,
    # so it is the one most able to do damage — which is why it re-asserts the
    # guard rather than trusting the caller to have done it.
    if not compose_ok:
        used_fallback = True
        guards.assert_branch_project(project)
        for cid in _labelled(runner, "container", project, env):
            runner.run(["docker", "rm", "-f", cid], env=env, check=False)
        for net in _labelled(runner, "network", project, env):
            runner.run(["docker", "network", "rm", net], env=env, check=False)

    # (4) Sweep. `docker compose down -v` skips a volume declared external, and
    # cannot see a branch-named volume carrying no label at all. None is
    # external today; the sweep is what makes that not matter tomorrow.
    guards.assert_branch_project(project)
    for vol in sorted(
        set(_labelled(runner, "volume", project, env))
        | set(_branch_named_volumes(runner, project, env))
    ):
        runner.run(["docker", "volume", "rm", vol], env=env, check=False)

    # (5) The worktree, then the administrative entry git leaves behind.
    #
    # The reclaim comes FIRST, on BOTH runtimes, and is the difference between
    # a teardown and a leak. Each runtime leaves a different uid behind and
    # needs a different remedy; `runtime.reclaim_worktree_ownership` owns both
    # and explains them.
    worktree_removed = False
    if worktree.exists():
        guards.assert_not_production_path(worktree)
        if not runtimes.reclaim_worktree_ownership(
                worktree, runner=runner, runtime=resolved_runtime,
                project=project, env=env):
            notes.append(
                "could not reclaim container-owned paths in the worktree; "
                "`git worktree remove` may fail on files a container created "
                "as a uid this user is not. See "
                "`runtime.reclaim_worktree_ownership` for what each runtime "
                "does about it."
            )
        argv = ["git", "worktree", "remove", str(worktree)]
        if force:
            argv.append("--force")
        removed = runner.run(argv, cwd=identity.production_root(), check=False)
        if removed.returncode == 0:
            worktree_removed = True
        else:
            notes.append(
                f"git worktree remove exited {removed.returncode}: "
                f"{(removed.stderr or '').strip()[:160]}. Uncommitted changes "
                "need --force."
            )
    runner.run(["git", "worktree", "prune"], cwd=identity.production_root(), check=False)

    # `env` HERE TOO, and this is the line the whole teardown report turns on.
    # Without it these four queries inherit the ambient environment -- i.e. the
    # ROOT docker daemon, which has never held a `br-` object created on
    # podman. `containers_after` would then be `[]` whatever survived, so
    # `containers_before - []` claims everything was removed and the RESIDUE
    # notes below can never fire. See `_docker_out`, which describes exactly
    # this failure and now refuses to be called without an answer.
    containers_after = _labelled(runner, "container", project, env)
    volumes_after = sorted(
        set(_labelled(runner, "volume", project, env))
        | set(_branch_named_volumes(runner, project, env))
    )
    networks_after = _labelled(runner, "network", project, env)

    for kind, after in (
        ("containers", containers_after),
        ("volumes", volumes_after),
        ("networks", networks_after),
    ):
        if after:
            notes.append(f"RESIDUE: {len(after)} {kind} still carry {project}: {after}")

    return DownResult(
        project=project,
        worktree=worktree,
        used_fallback=used_fallback,
        containers_removed=tuple(sorted(set(containers_before) - set(containers_after))),
        volumes_removed=tuple(sorted(set(volumes_before) - set(volumes_after))),
        networks_removed=tuple(sorted(set(networks_before) - set(networks_after))),
        worktree_removed=worktree_removed,
        notes=tuple(notes),
    )


def live_branch_projects(
    runner: CommandRunner | None = None,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """Every `br-` compose project the DAEMON knows about, sorted.

    The one implementation, deliberately. `--all` teardown, `aurora branch ls`
    and `.worktrees/INDEX.md` all ask the same question and must not answer it
    differently: a branch whose worktree someone deleted by hand is still
    running, still costs memory, and is invisible to anything that enumerates
    the filesystem or reads a cached index. Only the daemon knows.

    Read-only. It issues no destructive verb and needs no guard; what it feeds
    does.
    """
    runner = runner or CommandRunner()
    every = _docker_out(
        runner,
        ["docker", "ps", "-aq", "--filter", f"label={identity.PROJECT_LABEL}"],
        env,
    )
    found: set[str] = set()
    for cid in every:
        label = runner.run(
            ["docker", "inspect", "-f",
             '{{index .Config.Labels "' + identity.PROJECT_LABEL + '"}}', cid],
            env=env,
            check=False,
        )
        value = (label.stdout or "").strip()
        if value.startswith(guards.BRANCH_PROJECT_PREFIX):
            found.add(value)
    return sorted(found)


def branch_down_all(
    projects: Iterable[str] | None = None,
    *,
    runtime: str | None = None,
    runner: CommandRunner | None = None,
    force: bool = False,
) -> list[DownResult]:
    """Tear down every branch on EVERY runtime.

    The project list is DERIVED FROM THE DAEMON, never from an index file. A
    branch whose worktree someone deleted by hand is exactly the case `--all`
    exists for, and an index would not know about it.

    BOTH runtimes, unless one was named. This is where `branch_ls`'s
    one-daemon-per-call compromise stops being acceptable: `ls` omitting a
    podman branch is a gap in a report, but `--all` -- the "clean the host"
    command -- omitting one leaves a whole stack running and costing memory
    while reporting that everything was torn down. And `_tool_branch_down` has
    no `runtime` argument at all, so over MCP the default was the only
    reachable behaviour.
    The double sweep is safe here in a way it is not in `branch_ls`: the
    results go into a SET, so a shared `runner` seam replaying canned answers
    for both daemons produces one entry per project rather than double-
    counting. `branch_down` then resolves each project's own runtime from its
    `.aurora-runtime` record, so nothing is torn down against the wrong daemon.
    """
    runner = runner or CommandRunner()
    if projects is None:
        wanted = (
            runtimes.RUNTIMES if runtime is None
            else (runtimes.resolve_runtime(runtime),)
        )
        found: set[str] = set()
        for candidate in wanted:
            env = runtimes.for_name(
                candidate, check_socket=False,
            ).environ(stripped_environ())
            found.update(live_branch_projects(runner, env))
        projects = sorted(found)

    results = []
    for project in projects:
        guards.assert_branch_project(project)
        results.append(
            branch_down(
                project[len(guards.BRANCH_PROJECT_PREFIX):],
                runtime=runtime,
                runner=runner,
                force=force,
            )
        )
    return results


def render_teardown(results: Sequence[DownResult], index: Path) -> str:
    """What a teardown removed, in one wording for every surface (Task 11).

    The CLI and the MCP facade both report a teardown, and two renderings of
    one event is the drift this package keeps designing out -- an operator
    reading a terminal and an agent reading a tool result must not be told
    different things about what is still on the host. The RESIDUE notes are
    the reason it matters: `branch_down` records "these objects still carry
    this project" rather than raising, and a surface that dropped the notes
    would report a clean teardown that left containers running.
    """
    if not results:
        return f"no branch stacks are running\nindex: {index}\n"
    lines: list[str] = []
    for result in results:
        lines.append(
            f"{result.project}: removed {len(result.containers_removed)} "
            f"containers, {len(result.volumes_removed)} volumes, "
            f"{len(result.networks_removed)} networks"
            + ("; worktree removed" if result.worktree_removed else "")
        )
        for note in result.notes:
            lines.append(f"  NOTE: {note}")
    lines.append(f"index: {index}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# `ls`, `access`, `shell`, `rebuild`, and the access documents (Task 10)
# ---------------------------------------------------------------------------
#
# `rebuild` recreates a container. That is destructive to whatever was in it,
# and `docker compose up -d --build <service>` with the wrong project is
# `docker compose up -d --build forgejo` against production. So it runs behind
# the same two guards as teardown, and `aurora-cli/tests/test_guards.py`
# asserts structurally that it does.
#
# `shell` resolves its container from the branch PROJECT's own `ps` output and
# from nothing else. The failure mode being designed out is a name lookup that
# falls through to the daemon: `docker exec -it forgejo bash` reaches
# production's forge from any directory on this host.

#: What `aurora branch shell` runs when the caller names no command. `bash`
#: per spec D6; several images in this stack ship only `sh`, which is why the
#: command is overridable and why the access document says so.
DEFAULT_SHELL: tuple[str, ...] = ("bash",)


def compose_ps(
    project: str,
    *,
    runner: CommandRunner | None = None,
    env: Mapping[str, str] | None = None,
) -> list[access_doc.ContainerRow]:
    """`docker compose -p <project> ps --format json`, parsed.

    **This is the only place container names come from.** They are Compose's:
    `compose.branch.yml` resets `container_name` to null so that Compose owns
    them, and Compose appends `-2` the first time it recreates a container
    beside one that still exists. Every name printed by this package therefore
    comes through here, and no code path concatenates a project, a service and
    a number.

    No `cwd`, and no compose file: measured on Compose v5.3.1, `ps -p <project>`
    resolves the project from container LABELS and works from an empty
    directory. That matters -- `access` and `ls` must work for a branch whose
    worktree was deleted by hand, which is exactly the branch nobody knows is
    still running.

    Read-only, so no guard. Stopped containers are included: a stopped
    container still holds its name and is still something the document must
    account for.
    """
    runner = runner or CommandRunner()
    result = runner.run(
        ["docker", "compose", "-p", project, "ps", "-a", "--format", "json"],
        env=env,
        check=False,
    )
    return parse_compose_ps(result.stdout)


def parse_compose_ps(stdout: str) -> list[access_doc.ContainerRow]:
    """NDJSON or a JSON array -- Compose has emitted both across versions.

    Split out so a test can pin the parse against a recorded transcript
    without a daemon. Unparsable input yields nothing rather than raising: a
    document with an empty container table says so loudly, while a traceback
    out of `branch access` tells a developer nothing about their branch.
    """
    text = (stdout or "").strip()
    if not text:
        return []
    records: list[Any] = []
    try:
        value = json.loads(text)
    except ValueError:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except ValueError:
                continue
    else:
        records = value if isinstance(value, list) else [value]

    rows: list[access_doc.ContainerRow] = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        name = str(record.get("Name") or record.get("Names") or "")
        if not name:
            continue
        rows.append(access_doc.ContainerRow(
            service=str(record.get("Service") or ""),
            name=name,
            state=str(record.get("State") or ""),
            status=str(record.get("Status") or ""),
            health=str(record.get("Health") or ""),
        ))
    rows.sort(key=lambda r: (r.service, r.name))
    return rows


def _summary_for(
    project: str,
    *,
    runner: CommandRunner | None = None,
    env: Mapping[str, str] | None = None,
) -> access_doc.BranchSummary:
    name = project[len(guards.BRANCH_PROJECT_PREFIX):]
    domain = ""
    worktree = Path(identity._WORKTREE_DIRNAME) / name
    try:
        paths = identity.branch_paths(name)
        domain, worktree = paths.domain, paths.worktree
    except identity.IdentityError:
        # Production's identity is unresolvable -- it is down, or mid-deploy.
        # `ls` must still list what is running, for the same reason teardown
        # must still work then: that is when someone needs to know.
        pass
    return access_doc.BranchSummary(
        name=name,
        project=project,
        domain=domain,
        worktree=worktree,
        worktree_exists=worktree.is_absolute() and worktree.is_dir(),
        containers=tuple(compose_ps(project, runner=runner, env=env)),
    )


def branch_ls(
    runner: CommandRunner | None = None,
    *,
    runtime: str | None = None,
) -> list[access_doc.BranchSummary]:
    """Every branch stack on ONE runtime, derived from that daemon.

    One runtime per call, and the docker default is unchanged. Deliberately
    NOT a merge of both: `runner` is a seam the tests drive with canned
    results, and a second sweep against a second daemon would replay the same
    canned answers and double-count every branch -- an index that invents
    stacks is worse than one that omits them.

    The omission is real and is the cost of this being opt-in: `aurora branch
    ls` with no `--runtime` does not list podman branches, and
    `.worktrees/INDEX.md` is written from whichever runtime regenerated it.
    Pass `--runtime podman` to see those. Making `ls` runtime-agnostic wants a
    seam per daemon rather than a shared one, which is a change to the test
    surface, not to this line.
    """
    runner = runner or CommandRunner()
    env = runtimes.for_name(
        runtimes.resolve_runtime(runtime), check_socket=False,
    ).environ(stripped_environ())
    return [
        _summary_for(p, runner=runner, env=env)
        for p in live_branch_projects(runner, env)
    ]


def _recorded_excluded(worktree: Path) -> tuple[str, ...]:
    """The closure `up` actually configured, read back from its own artefact.

    `compose.exclude.yml` is what Compose reads, so reading it back answers
    "what is missing from this branch" with the file that makes it missing,
    rather than with a second derivation that could disagree with it.
    """
    path = exclusions.exclusion_overlay_path(worktree)
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return ()
    services = document.get("services") or {}
    return tuple(sorted(services)) if isinstance(services, Mapping) else ()


def _recorded_devs(env_file: Path) -> tuple[str, ...]:
    try:
        values = envfile.parse_env(Path(env_file).read_text(encoding="utf-8"))
    except (OSError, envfile.EnvFileError):
        return ()
    return envfile.developers_from_profiles(values.get("COMPOSE_PROFILES", ""))


def branch_state(
    name: str, *, runner: CommandRunner | None = None,
) -> tuple[BranchResult, list[access_doc.ContainerRow]]:
    """A branch as it is NOW, reconstructed from the daemon and its worktree.

    Everything here is re-derived rather than remembered, because a document
    that is regenerated on demand and a branch that changed underneath it must
    not disagree: container names change on recreation, containers stop, and a
    worktree can be deleted while the stack keeps running.

    The one thing that cannot be re-derived is the SEED REPORT -- it describes
    an event, not a state. `seeded` is left as `None` for that case, which the
    renderer prints as "not recorded here" rather than as "nothing was
    seeded". Guessing either way would be a document that lies about whether a
    branch shares production's users.
    """
    runner = runner or CommandRunner()
    paths = identity.branch_paths(name)
    # The runtime is read back from the worktree BEFORE anything queries a
    # daemon. `.aurora-runtime` is sitting in that worktree and was ignored, so
    # a podman branch's document was rendered from the ROOT daemon: zero
    # container rows, and `result.runtime` falling back to the default so the
    # document asserted the branch was on docker. Both were written AFTER `up`
    # succeeded, with nothing to say the list was empty for a reason.
    recorded = runtimes.recorded_runtime(paths.worktree)
    result_runtime = recorded or runtimes.DEFAULT_RUNTIME
    env = runtimes.for_name(
        result_runtime, check_socket=False,
    ).environ(stripped_environ())
    rows = compose_ps(paths.project, runner=runner, env=env)
    worktree_exists = paths.worktree.is_dir()

    if not rows and not worktree_exists:
        raise BranchError(
            f"there is no branch {paths.name!r}: no container carries "
            f"{identity.PROJECT_LABEL}={paths.project} and there is no "
            f"worktree at {paths.worktree}. `aurora branch ls` lists the "
            "branches that do exist."
        )

    result = BranchResult(requested_name=name, paths=paths)
    result.runtime = result_runtime
    result.seeded = None            # unknown, and deliberately not False
    if recorded is None and worktree_exists:
        result.notes.append(
            f"No {runtimes.RUNTIME_RECORD_NAME} in the worktree, so this "
            f"document assumes the default runtime ({runtimes.DEFAULT_RUNTIME}) "
            "-- which is what every branch built before that record existed is "
            "on. If this branch is on the other runtime, its containers are "
            "not listed below."
        )
    if worktree_exists:
        result.devs = _recorded_devs(paths.env_file)
        result.excluded = _recorded_excluded(paths.worktree)
        try:
            result.hook = crosswire.hook_status(paths.worktree)
        except crosswire.CrosswireError:
            result.hook = None
        result.notes.append(
            "This document was regenerated from live state. What was seeded, "
            "and whether the resource guard was overridden, are recorded only "
            f"in the copy `aurora branch up` wrote at {paths.access_doc}."
        )
    else:
        result.notes.append(
            f"THE WORKTREE {paths.worktree} IS GONE, but this stack is still "
            "running and still costs memory and disk. Nothing here was read "
            f"from it. `aurora branch down {paths.name}` reclaims it by "
            "label."
        )
    if not rows:
        result.notes.append(
            "No container carries this project's label, so the branch is "
            "configured but not running."
        )
    return result, rows


def branch_access(name: str, *, runner: CommandRunner | None = None) -> str:
    """`BRANCH-ACCESS.md` for an existing branch, regenerated from live state.

    Returned verbatim as CLI stdout and as the MCP tool result (spec 7.4), so
    this string IS the feature.
    """
    result, rows = branch_state(name, runner=runner)
    return access_doc.render_access_doc(result, rows)


# -- the documents on disk --------------------------------------------------
#
# ONE function touches a destination. Task 5 lost production a directory mtime
# to a tripwire placed over the byte-mover rather than over the function that
# created the destination, and Task 8 found a second `mkdir` with the same
# property. Both writes below go through `_write_document`, so one tripwire
# covers the `mkdir` and the bytes.


def _write_document(path: Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_access_doc(
    result: BranchResult,
    containers: Sequence[access_doc.ContainerRow] = (),
) -> Path:
    """Write `BRANCH-ACCESS.md` into the branch's worktree.

    Guarded with `assert_not_production_path`: the destination is a directory
    this tool writes a file into, and the only acceptable destinations are
    branch worktrees. Production's checkout is not one.
    """
    worktree = guards.assert_not_production_path(result.paths.worktree)
    return _write_document(worktree / access_doc.ACCESS_DOC_NAME,
                           access_doc.render_access_doc(result, containers))


def index_path() -> Path:
    return identity.production_root() / identity._WORKTREE_DIRNAME / access_doc.INDEX_NAME


def write_index(
    runner: CommandRunner | None = None, *, runtime: str | None = None,
) -> Path:
    """Regenerate `.worktrees/INDEX.md` from the daemon.

    **This writes inside production's checkout, by design.** Decision D-F puts
    branch worktrees at `<production>/.worktrees/`, gitignored, because that
    directory is already inside the tree production's Hermes bind-mounts --
    which is precisely what makes "production's agent reads every branch's
    access document with no extra wiring" true for free (spec 7.4). The index
    is the entry point to that. `guards.assert_worktrees_index_path` is the
    positive guard that no other path can be written by this function.

    ONE RUNTIME PER REGENERATION, and the index now says which. `branch_ls`
    asks a single daemon for the reason its docstring gives (the `runner` seam
    is shared, so a second sweep would replay canned results and invent
    stacks), which means a `branch up`/`down`/`ls` on docker used to rewrite
    this file from the docker daemon and DELETE every podman branch from it
    silently. It still lists one runtime; it no longer does so silently. A
    genuinely runtime-agnostic index wants a runner per daemon, which is a
    change to the test surface rather than to this function.
    """
    runner = runner or CommandRunner()
    path = guards.assert_worktrees_index_path(index_path())
    resolved = runtimes.resolve_runtime(runtime)
    return _write_document(
        path,
        access_doc.render_index(
            branch_ls(runner, runtime=resolved), runtime=resolved,
        ),
    )


def refresh_branch_docs(
    result: BranchResult, *, runner: CommandRunner | None = None,
) -> tuple[Path, Path]:
    """Write a branch's access document and regenerate the index.

    Deliberately NOT called from inside `branch_up` or `branch_down`. Both of
    those are exercised against real Docker objects by the test suite, and
    `write_index`'s destination is derived from PRODUCTION's checkout -- so a
    call inside them would make the suite write into production's tree on
    every teardown test. The lifecycle commands do the work; this puts the
    result on disk, and every surface (the CLI today, MCP in Task 11) calls
    it.

    The `env` is derived from `result.runtime`, not left to the ambient
    environment. Without it a `--runtime podman` branch's `BRANCH-ACCESS.md` --
    the string `branch_access`'s docstring calls "the feature" -- was written
    with ZERO container rows, from the root daemon, immediately after a
    successful `up`, with nothing to say the list was empty for a reason.
    """
    runner = runner or CommandRunner()
    env = runtimes.for_name(
        result.runtime or runtimes.DEFAULT_RUNTIME, check_socket=False,
    ).environ(stripped_environ())
    rows = compose_ps(result.paths.project, runner=runner, env=env)
    return (
        write_access_doc(result, rows),
        write_index(runner, runtime=result.runtime),
    )


# -- shell ------------------------------------------------------------------


def resolve_service_container(
    name: str,
    service: str,
    *,
    runner: CommandRunner | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    """The container running `service` in THIS branch, or a refusal.

    Resolved from `docker compose -p <branch project> ps` and from nothing
    else. A lookup by service name against the daemon would find production's
    container -- `docker exec -it forgejo bash` reaches production's forge from
    any directory on this host -- so a service that is not in this branch is
    an error here, never a fallback.
    """
    paths = identity.branch_paths(name)
    project = guards.assert_branch_project(paths.project)
    rows = compose_ps(project, runner=runner, env=env)
    if not rows:
        raise BranchError(
            f"branch {paths.name!r} has no running container at all: nothing "
            f"carries {identity.PROJECT_LABEL}={project}. There is nothing to "
            "exec into."
        )
    matched = [row for row in rows if row.service == service]
    if not matched:
        raise BranchError(
            f"{service!r} is not a service in branch {paths.name!r}. It runs: "
            f"{sorted({row.service for row in rows})}. Refusing to look the "
            "name up on the daemon instead -- production runs services with "
            "these names too, and finding one there is how a branch command "
            "lands in production."
        )
    return matched[0].name


def shell_argv(
    name: str,
    service: str,
    command: Sequence[str] = (),
    *,
    runner: CommandRunner | None = None,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    container = resolve_service_container(name, service, runner=runner, env=env)
    return ["docker", "exec", "-it", container, *(command or DEFAULT_SHELL)]


def branch_shell(
    name: str,
    service: str,
    command: Sequence[str] = (),
    *,
    runtime: str | None = None,
    runner: CommandRunner | None = None,
    exec_fn: Callable[[str, Sequence[str]], Any] | None = None,
) -> list[str]:
    """Exec into one of this branch's containers, replacing this process.

    `os.execvp` rather than a subprocess: an interactive shell wants this
    terminal, and a wrapper process that has to forward signals and a tty is a
    second thing to get wrong. Returns the argv it execed for the benefit of
    tests, which pass their own `exec_fn`; in the real path it does not
    return.
    """
    worktree = identity.branch_paths(name).worktree
    resolved_runtime = runtimes.for_name(
        teardown_runtime(worktree, runtime), check_socket=False,
    )
    env = resolved_runtime.environ(stripped_environ())
    argv = shell_argv(name, service, command, runner=runner, env=env)
    # LAST, immediately before the exec. `execvp` replaces this process and
    # carries THIS process's environment, not a dict handed to a subprocess --
    # so for the podman path the variable has to be planted in os.environ.
    # Without it the exec lands on the root daemon, where a container of that
    # name may well exist: production runs services with these names too.
    #
    # It has to be the last statement because `shell_argv` above RAISES when
    # the branch has no container or no such service, and this process may
    # outlive that: `exec_fn` is a real injected seam and the MCP server is
    # long-lived. Mutating first meant a failed lookup left a DOCKER_HOST
    # behind (or removed one the operator exported) and every later call in
    # the same process ran against the wrong daemon.
    os.environ.pop(runtimes.DOCKER_HOST_VAR, None)
    if resolved_runtime.docker_host is not None:
        os.environ[runtimes.DOCKER_HOST_VAR] = resolved_runtime.docker_host
    (exec_fn or os.execvp)(argv[0], argv)
    return argv


# -- rebuild ----------------------------------------------------------------


def branch_overlay(
    name: str, *, check: bool = False, limits: str | None = None,
) -> tuple[Path, bool]:
    """Re-render a LIVE branch's `compose.branch.yml`. -> (path, was_stale).

    `up` renders the overlay once, from the services that existed then, so an
    agent provisioned into a running branch afterwards keeps the base file's
    daemon-global `container_name` and its published host port -- and Compose
    flags neither. Safe to repeat, and with `check` nothing is written.
    """
    worktree = identity.branch_paths(name).worktree
    if not worktree.is_dir():
        raise BranchError(
            f"no worktree at {worktree}. `branch overlay` re-renders the "
            "overlay of a branch that already exists; `branch up` creates one."
        )
    return overlay.sync_overlay(worktree, check=check, limits=limits)


def branch_rebuild(
    name: str,
    services: Sequence[str] = (),
    *,
    runtime: str | None = None,
    runner: CommandRunner | None = None,
    build: bool = True,
) -> CommandResult:
    """Rebuild and restart services IN THIS BRANCH ONLY (spec 7.1).

    Scoping is the whole of it. The invocation is
    `docker compose -p br-<name> ... up -d --build <service>`, built by the
    shared `compose_argv`, so it carries the branch project and the same three
    compose files every other command in this package uses. Without `-p` the
    identical command recreates PRODUCTION's container of that name, which is
    why both guards run before the argv is built and why the guarded project
    -- not `paths.project` again -- is what goes into it.
    """
    runner = runner or CommandRunner()
    paths = identity.branch_paths(name)
    project = guards.assert_branch_project(paths.project)
    worktree = guards.assert_not_production_path(paths.worktree)

    if not (worktree / overlay.BASE_COMPOSE_NAME).is_file():
        raise BranchError(
            f"no {overlay.BASE_COMPOSE_NAME} at {worktree}, so a rebuild "
            "cannot resolve this branch's compose project. The worktree was "
            f"removed by hand, or `up` never populated it; `aurora branch "
            f"down {paths.name}` reclaims what is still running."
        )

    # The runtime comes from the branch's own record, for the same reason
    # teardown's does: a rebuild on the wrong daemon does not fail. It BUILDS,
    # and on the root daemon it builds into the image store production pulls
    # its tags from -- which is the escape 2026-07-31 measured.
    resolved_runtime = runtimes.for_name(
        teardown_runtime(worktree, runtime), check_socket=False,
    )

    args = ["up", "-d"]
    if build:
        args.append("--build")
    args += list(services)
    return runner.run(
        compose_argv(project, *args),
        cwd=worktree,
        env=resolved_runtime.environ(stripped_environ()),
    )
