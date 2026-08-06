"""Which container runtime a branch stack runs on (spec 5, P4).

**Opt-in, and docker by default.** `--runtime podman` / `$AURORA_BRANCH_RUNTIME`
points a branch's Compose invocations at the *user's rootless podman socket*
via `DOCKER_HOST`. Nothing else changes: the same `docker compose` binary, the
same three `-f` files, the same overlay, the same project name. Production
keeps the root docker daemon and is never addressed through this module.

WHY THIS IS THE STRUCTURAL FIX, AND WHAT WAS MEASURED

`ops/docker-guard` is a `PATH` wrapper in front of the `docker` *binary*. A
process that holds `/var/run/docker.sock` never runs that binary -- it speaks
HTTP to the socket -- and three branch services (`dev-admin`, `fjell`,
`hermes`) are handed that socket by configuration on every `branch up`. Under
the root daemon the escape is real; measured 2026-08-01 on this host, a
container with the socket bound answered `GET /version` from production's
daemon:

    docker run --rm -v /var/run/docker.sock:/var/run/docker.sock python:3.14-slim
      -> CONNECTED: HTTP/1.0 200 OK  Api-Version: 1.55  Server: Docker/29.6.2

The identical container under rootless podman, with the flags Compose actually
produces, is refused:

    podman run --rm -v /var/run/docker.sock:/var/run/docker.sock python:3.14-slim
      -> REFUSED: PermissionError [Errno 13] Permission denied

**Two independent layers** deny it, which is why the refusal is a property and
not an accident (each was isolated by disabling the other):

  * SELinux -- the container runs as `container_t`, the socket is
    `container_var_run_t`; with `--security-opt label=disable` the stat
    succeeds, so SELinux is doing the work by itself.
  * DAC -- the socket is `root:docker 0660`, and neither host uid 0 nor host
    gid 1001 is inside a rootless container's id map, so the socket appears as
    `nobody:nogroup` and the process falls in `other`. With SELinux disabled
    the connect STILL fails.

Only `--security-opt label=disable` *and* `--group-add keep-groups` together
let it through, and `keep-groups` is a podman extension that the Docker API
Compose speaks cannot express. So a branch on this runtime cannot reach
production's daemon even though it is still handed the path to it.

THE TWO BLOCKERS, MEASURED

1. **SELinux is Enforcing**, so a bind mount of a `user_home_t` path into a
   `container_t` process is EACCES:

       podman run -v <repo dir>:/probe debian  ->  cat: Permission denied
       podman run -v <repo dir>:/probe:z debian ->  reads fine

   The usual fix is `:z` on every bind, which would mean editing compose files
   that production also reads. This module does the same relabel HOST-SIDE
   instead, with `chcon -R -t container_file_t <worktree>`, for three reasons:

     * `:z` *is* a recursive `chcon` to `container_file_t:s0` -- measured, the
       resulting label is byte-identical -- so nothing is given up;
     * it keeps the compose files, the overlay and the `-f` list identical
       between the two runtimes, which is the whole promise of this phase;
     * the argument is a PATH, so it can be guarded. `:z` on a compose entry
       cannot be: three services bind `/var/run/docker.sock` and one binds
       `/etc/localtime`, and a blanket `:z` would relabel *those*, i.e. host
       system objects shared with production. `relabel_worktree` refuses any
       path that is not a branch worktree.

   Files created afterwards inherit the directory's type, so a single pass
   before the first `up` covers state the seed and the containers write later
   (measured: a host-created file and a container-created file under a
   relabelled directory both came out `container_file_t`).

2. **Rootless uid mapping.** Container `root` maps to the invoking uid, which
   is what fixes the leaked-worktree defect -- the daemon stops creating
   root-owned bind sources. But a container that drops to a NON-root uid maps
   into the subuid range instead. Measured with the stack's own Postgres
   (`pgvector/pgvector:pg16`, uid 999) on a repo-relative bind:

       host before:  drwxr-xr-x supergoodname77 supergoodname77  data/postgres
       container:    healthy, `stat` shows 999:0, psql works
       host after:   drwx------ 525286 1000                      data/postgres
                     (524288 + 998 -- the subuid base plus container uid - 1)

   Postgres itself is FINE: the data directory starts empty, the entrypoint
   chowns it as container-root, and the seed restores through
   `pg_dump`/`pg_restore` rather than byte-copying it. What is not fine is
   afterwards -- uid 1000 can no longer read or delete that directory:

       rm -rf .../data/postgres   ->  Permission denied
       git worktree remove        ->  would fail the same way

   which is the leaked-worktree regression coming back through a different
   door. `reclaim_worktree_ownership` is the fix and it needs no root:
   `podman unshare` enters the user namespace where 525286 is an ordinary uid,
   and `chown -R 0:0` there means "give it back to host uid 1000". Measured to
   clear the directory `rm -rf` could not touch.

Stdlib + the repo's own modules only, like everything else in this package.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from aurora_cli import guards, identity, seed

#: The two runtimes, and the default. Docker stays the default deliberately:
#: production runs on the root daemon and every existing branch was built
#: against it, so podman must be asked for, never inferred.
DOCKER = "docker"
PODMAN = "podman"
RUNTIMES: tuple[str, ...] = (DOCKER, PODMAN)
DEFAULT_RUNTIME = DOCKER

#: `--runtime` is looked up here when the flag is absent.
RUNTIME_ENV_VAR = "AURORA_BRANCH_RUNTIME"

#: The variable that actually does the work. Set for podman, and STRIPPED for
#: docker -- see `Runtime.environ`.
DOCKER_HOST_VAR = "DOCKER_HOST"

#: Where the rootless socket lives under the runtime directory. The directory
#: itself is derived from the invoking user (see `runtime_dir`) rather than
#: written as `/run/user/1000`: a hardcoded uid is correct on exactly one host
#: and silently addresses SOMEBODY ELSE'S podman everywhere else.
PODMAN_SOCKET_RELPATH = "podman/podman.sock"

#: What a relabelled worktree is labelled as. `container_file_t` at `s0` with
#: no MCS category -- the shared label, which is what `:z` produces and what
#: makes the tree readable by every container in the branch rather than by one.
SELINUX_CONTAINER_TYPE = "container_file_t"

#: Written into the worktree by `branch up` so `branch down` does not have to
#: be told again. A teardown that guessed the runtime would query the wrong
#: daemon, find nothing, and report a clean removal over a live stack.
RUNTIME_RECORD_NAME = ".aurora-runtime"


class RuntimeSelectionError(RuntimeError):
    """The requested runtime cannot be used, and was not silently swapped."""


def resolve_runtime(
    requested: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """`--runtime`, then `$AURORA_BRANCH_RUNTIME`, then docker.

    An unrecognised value RAISES rather than falling back to the default. A
    typo that silently means "docker" is the worst outcome available here: the
    caller asked for isolation, was told nothing, and got production's daemon.
    """
    environ = os.environ if environ is None else environ
    source = "--runtime"
    value = requested
    if value is None:
        value = (environ.get(RUNTIME_ENV_VAR) or "").strip() or None
        source = f"${RUNTIME_ENV_VAR}"
    if value is None:
        return DEFAULT_RUNTIME
    if value not in RUNTIMES:
        raise RuntimeSelectionError(
            f"{source}={value!r} is not a runtime this tool knows "
            f"({', '.join(RUNTIMES)}). Refusing to fall back to "
            f"{DEFAULT_RUNTIME!r}: a typo that quietly means 'the root docker "
            "daemon' would hand a caller who asked for isolation exactly the "
            "daemon they were trying to get away from."
        )
    return value


def runtime_dir(
    *,
    environ: Mapping[str, str] | None = None,
    uid: int | None = None,
) -> Path:
    """`$XDG_RUNTIME_DIR`, else `/run/user/<uid>`.

    Derived, never written down. `/run/user/1000` is true for the one account
    this stack happens to run as; on any other it names a DIFFERENT user's
    runtime directory, and a `DOCKER_HOST` pointing there is either a
    permission error or -- far worse, if the uid is shared -- somebody else's
    containers.
    """
    environ = os.environ if environ is None else environ
    explicit = (environ.get("XDG_RUNTIME_DIR") or "").strip()
    if explicit:
        return Path(explicit)
    return Path("/run/user") / str(os.getuid() if uid is None else uid)


def podman_socket(
    *,
    environ: Mapping[str, str] | None = None,
    uid: int | None = None,
) -> Path:
    """The rootless podman API socket for the invoking user."""
    return runtime_dir(environ=environ, uid=uid) / PODMAN_SOCKET_RELPATH


def podman_docker_host(
    *,
    environ: Mapping[str, str] | None = None,
    uid: int | None = None,
) -> str:
    """That socket as a `DOCKER_HOST` URL."""
    return f"unix://{podman_socket(environ=environ, uid=uid)}"


@dataclass(frozen=True)
class Runtime:
    """One resolved runtime: its name, and the `DOCKER_HOST` it implies."""

    name: str
    #: `None` for docker -- and `None` means "unset the variable", not "leave
    #: whatever the shell had". See `environ`.
    docker_host: str | None = None

    @property
    def is_podman(self) -> bool:
        return self.name == PODMAN

    def environ(self, base: Mapping[str, str]) -> dict[str, str]:
        """`base` with `DOCKER_HOST` set for podman and REMOVED for docker.

        The removal is the load-bearing half. `branch up` inherits the
        operator's environment, and an exported `DOCKER_HOST` -- left over from
        a podman session, or from anything else -- would silently move a
        docker-runtime branch onto another daemon. Every other compose variable
        this package cares about is stripped for exactly that reason
        (`branch.STRIPPED_COMPOSE_VARS`); this one decides which DAEMON the
        command lands on, so it is the last one that should be inherited.
        """
        env = {k: v for k, v in base.items() if k != DOCKER_HOST_VAR}
        if self.docker_host is not None:
            env[DOCKER_HOST_VAR] = self.docker_host
        return env


def for_name(
    name: str,
    *,
    environ: Mapping[str, str] | None = None,
    uid: int | None = None,
    check_socket: bool = True,
) -> Runtime:
    """Build the `Runtime` for a resolved runtime name.

    The socket is checked for EXISTENCE, and a missing one raises. Compose
    given a `DOCKER_HOST` that does not resolve fails late and obscurely, deep
    inside an `up` that has already created a worktree; the systemd unit that
    provides it (`podman.socket`, user scope) is named in the message because
    "not started" is the only thing that is usually wrong.
    """
    if name == DOCKER:
        return Runtime(name=DOCKER, docker_host=None)
    if name != PODMAN:
        raise RuntimeSelectionError(
            f"{name!r} is not a runtime this tool knows ({', '.join(RUNTIMES)})."
        )
    socket = podman_socket(environ=environ, uid=uid)
    if check_socket and not socket.exists():
        raise RuntimeSelectionError(
            f"--runtime podman needs the rootless podman API socket at "
            f"{socket}, and there is nothing there. Start it with:\n"
            "      systemctl --user enable --now podman.socket\n"
            "  Refusing rather than falling back to the root docker daemon: "
            "that daemon owns production."
        )
    return Runtime(name=PODMAN, docker_host=f"unix://{socket}")


# ---------------------------------------------------------------------------
# what the branch worktree remembers
# ---------------------------------------------------------------------------


def record_runtime(worktree: Path, name: str) -> Path:
    """Write the runtime name into the worktree, for `branch down` to read.

    A one-line file rather than a key in the branch `.env`: `.env` is
    interpolated by Compose and validated by `envfile.missing_overrides`, and a
    variable that means something to this CLI and nothing to Compose does not
    belong in a file whose contract is "what Compose reads".

    Deliberately NOT behind `assert_not_production_path`, unlike the two
    functions below it. This writes one inert file into a directory `up` has
    just created, exactly as `write_branch_env` and `write_exclusion_overlay`
    do and behind no guard for the same reason -- while those two mutate
    SELinux labels and ownership across a whole tree. Guarding it would also
    break `branch_up(worktrees_root=...)`, the seam the suite uses so that
    lifecycle tests never write inside production's checkout.
    """
    path = Path(worktree) / RUNTIME_RECORD_NAME
    path.write_text(name + "\n", encoding="utf-8")
    return path


def recorded_runtime(worktree: Path) -> str | None:
    """The runtime `branch up` recorded, or `None` if it did not record one.

    `None` rather than `DEFAULT_RUNTIME`: the caller has to be able to tell
    "this branch was built on docker" from "this branch predates the record",
    because only the second one may be overridden by a flag without contradicting
    something that was actually measured.
    """
    try:
        value = (Path(worktree) / RUNTIME_RECORD_NAME).read_text(
            encoding="utf-8").strip()
    except OSError:
        return None
    return value if value in RUNTIMES else None


# ---------------------------------------------------------------------------
# blocker 1: SELinux
# ---------------------------------------------------------------------------


def selinux_enforcing(runner) -> bool:
    """Is SELinux Enforcing right now? Measured, not assumed.

    Read with `getenforce` rather than from `/sys/fs/selinux/enforce`, because
    the question being asked is the policy MODE and Permissive is a real answer
    -- a relabel is pointless there and doing it anyway would silently mutate
    labels on a host that never needed it.

    `check=False` covers a non-zero exit; it does NOT cover the
    `FileNotFoundError` `subprocess.run` raises when `getenforce` is not
    installed, which is the normal state of a host without SELinux. Unwrapped,
    `relabel_worktree` crashed there instead of returning its "not Enforcing"
    note -- a podman branch on a Debian host would have failed at the relabel
    with an OSError rather than proceeding, correctly, with no relabel at all.
    """
    try:
        result = runner.run(["getenforce"], check=False)
    except OSError:
        return False
    return result.stdout.strip().lower() == "enforcing"


def relabel_worktree(
    worktree: Path,
    *,
    runner,
    force: bool = False,
    worktrees_root: Path | None = None,
) -> str | None:
    """`chcon -R -t container_file_t <worktree>`. Returns a note, or `None`.

    THE GUARD IS THE POINT. This is the one operation in the podman path that
    mutates something outside the container runtime's own storage, and the
    thing it mutates is an SELinux label on a host path. Pointed at the wrong
    path it would relabel production's checkout, or -- if it were ever driven
    from a compose `volumes:` entry instead of from a worktree path -- the
    `/var/run/docker.sock` and `/etc/localtime` that three services and Forgejo
    respectively bind from outside the repository. So the argument goes through
    `guards.assert_not_production_path` before `chcon` is spelled, exactly like
    every destructive branch operation in this package.

    A Permissive or Disabled host is a no-op with a note, not a silent skip:
    "nothing to do here" and "this ran" must be distinguishable in the record.

    `worktrees_root` is the test seam and only that -- see
    `guards.assert_not_production_path`, which cannot be widened by it. It
    exists because `<production>/.worktrees` is root-owned on this host, so
    without it the live tier could not call this function at all and "tested"
    it by spelling `chcon` again by hand.
    """
    worktree = guards.assert_not_production_path(
        worktree, worktrees_root=worktrees_root)
    if not force and not selinux_enforcing(runner):
        return (
            "SELinux is not Enforcing on this host, so the branch worktree was "
            "NOT relabelled. Under Enforcing it must be: a bind of a "
            "`user_home_t` path into a `container_t` process is EACCES."
        )
    runner.run(["chcon", "-R", "-t", SELINUX_CONTAINER_TYPE, str(worktree)])
    return (
        f"SELinux: relabelled {worktree} to {SELINUX_CONTAINER_TYPE} so the "
        "branch's containers can read their own bind mounts. This is what "
        "`:z` on every bind would do, done host-side on a path that can be "
        "guarded -- three services bind /var/run/docker.sock and forgejo binds "
        "/etc/localtime, and `:z` would have relabelled those too."
    )


# ---------------------------------------------------------------------------
# blocker 2: rootless uid mapping
# ---------------------------------------------------------------------------


#: The image the DOCKER reclaim runs `chown` in: the one the volume seeder
#: already requires, IMPORTED rather than repeated. A second copy kept equal by
#: a test is worse than one copy -- and the copy was worse than that, because
#: splitting the literal across two lines to fit is what let a conformance
#: regex capture `python:3.13-slim@sha256:` with no digest and still pass.
RECLAIM_IMAGE = seed.VOLUME_SEED_IMAGE


#: A `chown -R` that hangs is worse than one that fails: `branch down` would
#: stop with no note and no exit.
RECLAIM_TIMEOUT_SECONDS = 300


def _reclaim_owner(environ: Mapping[str, str] | None = None) -> tuple[int, int]:
    """Who the worktree should end up belonging to.

    `os.getuid()` is wrong under `sudo`: it returns 0, the argv becomes
    `chown -R 0:0`, the container exits 0 and the reclaim reports SUCCESS while
    reproducing the leak exactly. That is the one failure shape this function
    must not have, so `$SUDO_UID` wins when it is set.
    """
    environ = os.environ if environ is None else environ
    sudo_uid, sudo_gid = environ.get("SUDO_UID"), environ.get("SUDO_GID")
    if sudo_uid and sudo_uid.isdigit():
        return int(sudo_uid), int(sudo_gid) if (sudo_gid or "").isdigit() else int(sudo_uid)
    return os.getuid(), os.getgid()


def reclaim_worktree_ownership(
    worktree: Path, *, runner, runtime: Runtime,
    project: str | None = None,
    worktrees_root: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Give container-owned files in a branch worktree back to this user.

    Returns True when the reclaim ran and succeeded.

    BOTH runtimes need this and for the same reason -- a container wrote files
    as a uid this user is not -- but the uid differs, so the remedy differs.

    **podman.** Rootless podman maps container `root` to the invoking uid but a
    container's NON-root uid into the subuid range: measured, this stack's
    Postgres (uid 999) leaves `data/postgres` owned by 525286 and mode 0700,
    which uid 1000 can neither read nor remove. `podman unshare` runs the
    command inside the user namespace, where 525286 is an ordinary uid and host
    uid 1000 is 0, so `chown -R 0:0` there means "make it all mine again" on the
    host, and it needs no root and no sudo.

    **docker.** The rootful daemon runs container `root` as host uid 0, so a
    branch worktree comes back owned by ROOT. This was measured as defect D2
    (docs/measurements): the docker path leaked a 2.5 GB tree it could not then
    delete, while podman -- which had the reclaim -- cleaned up completely. The
    remedy is the same idea through the other available root: the daemon is
    already privileged, so a throwaway container chowns the bind-mounted tree
    back. No sudo, and no `AURORA_ALLOW_PROD`.

    That asymmetry is why this took a defect to find. The podman branch of this
    function existed from the start and its own docstring said the docker daemon
    "left root-owned directories behind" -- describing, in the past tense, a bug
    that was still live on the path without the fix.

    Best-effort by design (`check=False`): this runs on the teardown path, and a
    teardown that ABORTS because the reclaim failed leaves strictly more behind
    than one that carries on and lets `git worktree remove` report the real
    problem.

    `worktrees_root`: the same test seam as `relabel_worktree`, and it cannot
    widen the guard -- see `guards.assert_not_production_path`.
    """
    worktree = guards.assert_not_production_path(
        worktree, worktrees_root=worktrees_root)
    if not Path(worktree).exists():
        return False
    uid, gid = _reclaim_owner(environ=env)
    if runtime.is_podman:
        argv = ["podman", "unshare", "chown", "-R", "0:0", str(worktree)]
    else:
        # POSITIVE check, on the docker branch only, because only this branch
        # hands a path to a ROOT daemon. `assert_not_production_path` refuses
        # anything inside production -- it says nothing about the rest of the
        # filesystem, and `worktrees_root` is a test seam wide enough to admit
        # `/etc`. Under podman that was harmless (uid 1000 in a user namespace
        # owns none of it); under docker it would succeed. A git worktree
        # always has a `.git` FILE pointing at its administrative directory,
        # and no ordinary system directory does.
        if not (Path(worktree) / ".git").is_file():
            # SKIP, not raise. This whole function is best-effort by contract,
            # and `branch_down` calls it on the teardown path: raising here
            # turned "this worktree looks malformed" into a FAILED TEARDOWN,
            # which leaves strictly more behind than the leak the reclaim
            # exists to prevent. Measured -- it broke `branch down` for every
            # worktree without a `.git` file, including the half-built ones
            # most likely to need a teardown. The safety property is that no
            # root `chown` runs, and returning False achieves it; the caller
            # already turns False into a note.
            return False
        # `--network=none` because a chown has no business reaching anything,
        # and the mount is the worktree ALONE -- never its parent, so a bug
        # here cannot walk into a sibling branch or into production.
        # `--mount` rather than `-v`: the short form is colon-delimited, so a
        # resolved path containing `:` reparses as `src:dst:opts`.
        # `--network=none` because a chown has no business reaching anything.
        argv = [
            "docker", "run", "--rm", "--network=none",
            # LABELLED, so that a container which outlives `--rm` is still
            # reachable. Measured 2026-08-01: a throwaway container killed
            # between `create` and `start` survived, and being unlabelled put
            # it in the worst place available -- invisible to `branch_down`'s
            # residue sweep, which filters on this label, AND outside the
            # `br-` namespace `ops/docker-guard` will act on, so no human
            # following the teardown docs had a sanctioned command for it.
            # See docs/issues/2026-08-01-wedged-seed-container.md.
            *(["--label", f"{identity.PROJECT_LABEL}={project}"] if project else []),
            "--mount", f"type=bind,src={worktree},dst=/worktree",
            RECLAIM_IMAGE,
            "chown", "-R", f"{uid}:{gid}", "/worktree",
        ]
    try:
        result = runner.run(argv, check=False, env=env,
                            timeout=RECLAIM_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        # Best-effort means "carry on", not "hang". An unreachable daemon or a
        # `chown -R` over a very large worktree would otherwise stop `branch
        # down` with no note and no exit -- strictly worse than the leak this
        # is defending against.
        return False
    return result.returncode == 0


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------


def describe(runtime: Runtime) -> str:
    """One line for the access document and the teardown report."""
    if runtime.docker_host is None:
        return (
            f"runtime: {runtime.name} (the root docker daemon -- the same "
            "daemon production runs on)"
        )
    return f"runtime: {runtime.name} ({DOCKER_HOST_VAR}={runtime.docker_host})"
