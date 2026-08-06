"""Derive production's identity. Never hardcode it.

This module is the single place that answers "what, and where, is
production?". Every other module in this package resolves production
through it and through nothing else.

Why it exists
-------------
Chunk 2's rename is blocked pending the user, not cancelled. Production
still carries the compose project label of an unrelated earlier project,
and still lives in a checkout named after it, while the repository already
declares itself ``aurora`` everywhere. The rename may land at any time. So
there are two worlds, and code that *types* a project name is wrong in one
of them whichever of the two names it picks.

Nothing here is typed. The checkout comes from git, the project name from
``docker compose config`` cross-checked against running container labels,
and the domain from production's own ``.env``.

``aurora-cli/tests/test_identity.py`` scans this file's source, with
docstrings stripped, for both project names and for production's tailnet
suffix -- and it derives all three at runtime rather than typing them, so
the scan keeps working after the rename. Comments are *in* scope for that
scan; a comment carrying a live identity is a copy-paste source. This
file therefore names neither project anywhere, docstrings included, because
``tests/test_repo_conformance.py::test_no_tracked_file_outside_docs_names_
the_old_project`` reads the raw bytes and does not care that prose is
harmless.

Two names, two derivations, and they are not the same question
--------------------------------------------------------------
* ``production_project()`` -- what the *running stack* is called. Derived
  from production's checkout and cross-checked against the daemon. Changes
  when the rename lands.
* ``declared_project()`` -- what this repository calls the product, from
  the tracked ``.env.template``. ``aurora`` in both worlds, which is why it
  and not ``production_project()`` supplies the ``aurora-<branch>`` tailnet
  hostname required by spec 7.1. A branch is named after the product, not
  after whatever label production happens to carry this week.

Dependencies: standard library only (decision D-A). Callers that need YAML
bring their own.
"""

from __future__ import annotations

import functools
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# The namespace every branch compose project lives in. The whole safety
# property of Chunk 3's destructive paths is "the project name starts with
# this", so it is defined once, here, and the test harness' copy is pinned
# against this one by a drift test.
BRANCH_PROJECT_PREFIX = "br-"

# A DNS label may not exceed 63 octets. The branch hostname is
# <prefix><name>, and the LIMIT APPLIES TO THE WHOLE LABEL -- truncating the
# name alone to 63 produces an invalid hostname and a certificate that never
# issues.
DNS_LABEL_MAX = 63

PROJECT_LABEL = "com.docker.compose.project"
WORKING_DIR_LABEL = "com.docker.compose.project.working_dir"
SERVICE_LABEL = "com.docker.compose.service"
# The label Compose writes on a named volume, carrying the KEY the volume
# has in the compose file rather than its project-prefixed name. Seeding a
# branch volume before `up` depends on both of these (trap 6), so the label
# names live here, beside the two that were already needed, and not in a
# second module.
VOLUME_LABEL = "com.docker.compose.volume"

_PROJECT_NAME_VAR = "COMPOSE_PROJECT_NAME"
_PROFILES_VAR = "COMPOSE_PROFILES"
_DOMAIN_VAR = "DOMAIN_NAME"

_ENV_TEMPLATE = ".env.template"
_ENV_FILE = ".env"

# Spec D-F: branch worktrees live under production's checkout so production's
# agent sees every branch's access document with no extra wiring.
_WORKTREE_DIRNAME = ".worktrees"
_ACCESS_DOC_NAME = "BRANCH-ACCESS.md"


class IdentityError(RuntimeError):
    """Production's identity could not be derived, or did not agree with itself.

    Never subclassed and never caught inside this module: a caller that
    cannot establish which stack is production must stop, not guess. Every
    message names the values that disagreed, because "identity mismatch" with
    no operands is the error that gets suppressed.
    """


# ---------------------------------------------------------------------------
# process helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], *, cwd: Path | None = None,
         env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        where = cwd if cwd is not None else Path.cwd()
        raise IdentityError(
            f"`{' '.join(cmd)}` failed with exit {proc.returncode} in {where}: "
            f"{proc.stderr.strip() or '(no stderr)'}"
        )
    return proc.stdout


def _read_env_file(path: Path) -> dict[str, str]:
    """Parse a KEY=value env file into a dict.

    Deliberately minimal. Task 2's ``envfile.py`` owns strict validation and
    rendering (trap 7: `docker run --env-file` rejects whitespace around
    `=`); when it lands, this should call it rather than grow a second
    parser. Keys and values are stripped here so that a file which is
    already non-strict is *read* rather than silently mis-read -- refusing it
    is the validator's job, not the reader's.
    """
    if not path.is_file():
        raise IdentityError(f"Expected an env file at {path}, found none.")
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


# ---------------------------------------------------------------------------
# where the code is, and where production is
# ---------------------------------------------------------------------------


def package_root() -> Path:
    """The checkout this code is running *from* -- a worktree, usually.

    Not production. The two differ every time this package runs from a
    branch worktree, which is the normal case, and conflating them is the
    bug the whole module exists to prevent.
    """
    return Path(__file__).resolve().parents[2]


#: Cached: pure for the life of a process, and the broker forks a process per
#: connection, so staleness is bounded by one developer session. It runs a
#: `git worktree list` SUBPROCESS and is reached from
#: `assert_not_production_path`, `refuse_production_database`,
#: `production_env()`, every `branch_paths` (hence once per branch inside
#: `branch_ls` / `branch_down_all`'s loops) and both `git worktree remove` /
#: `prune`. A test that repoints the root clears it through `reset_caches()`
#: below rather than paying a subprocess per call forever.
@functools.lru_cache(maxsize=1)
def production_root() -> Path:
    """Production's checkout: the *main* git worktree.

    `git worktree list --porcelain` names the main worktree first; linked
    worktrees follow. That is a property of git's output order, not of this
    host, so it holds from any worktree.

    Resolved, always. `/home` is a symlink to `/var/home` on this host and
    the compose CLI reports the unresolved form; comparing a resolved path
    against an unresolved one has cost this project three separate debugging
    sessions.
    """
    out = _run(["git", "worktree", "list", "--porcelain"], cwd=package_root())
    for line in out.splitlines():
        prefix, sep, value = line.partition(" ")
        if prefix == "worktree" and sep:
            root = Path(value.strip()).resolve()
            if not root.is_dir():
                raise IdentityError(
                    f"git names {root} as the main worktree but it is not a "
                    "directory."
                )
            return root
    raise IdentityError(
        "`git worktree list --porcelain` named no worktree; cannot locate "
        f"production's checkout from {package_root()}."
    )


#: Cached; see `production_root`. A tracked-file read, per call, from
#: everything that builds a branch hostname.
@functools.lru_cache(maxsize=1)
def declared_project() -> str:
    """What this repository declares the product is called.

    Read from the tracked `.env.template`, which carries
    `COMPOSE_PROJECT_NAME=aurora` both before and after Chunk 2's rename --
    it is the *intended* identity, and it is pinned by
    `tests/test_repo_conformance.py::test_the_project_name_is_declared_not_
    inherited_from_the_directory`.

    This is the source of the `aurora-<branch>` tailnet hostname (spec 7.1).
    Using `production_project()` for that instead would name every branch
    after production's current runtime label, which until the rename lands is
    still the name of an unrelated earlier project -- i.e. every branch
    hostname would re-introduce the exact mistake Chunk 2 spent a chunk
    undoing.
    """
    template = package_root() / _ENV_TEMPLATE
    value = _read_env_file(template).get(_PROJECT_NAME_VAR, "")
    if not value:
        raise IdentityError(
            f"{template} declares no {_PROJECT_NAME_VAR}; the product name is "
            "read from there and nowhere else."
        )
    return value


#: Cached; the `docker compose config` subprocess is the expensive half of
#: `production_project()` -- the single slowest operation in this package --
#: and `production_project()` is itself NOT cached: its cross-check against the
#: daemon is an assertion, and an assertion answered from a cache is a comment.
#: `guards.assert_branch_project` calls it on every destructive operation, and
#: `branch_down` calls that three times per teardown plus once per swept volume.
@functools.lru_cache
def _compose_declared_project(root: Path) -> str:
    """The compose project name declared by the checkout at `root`.

    `docker compose config`, not `docker ps`: a declaration has to be
    readable when the stack is down, and the cross-check in
    `production_project()` is what turns a declaration into a fact.

    `COMPOSE_PROJECT_NAME` is dropped from the environment first. The
    question asked here is "what does *that checkout* declare", and an
    ambient variable inherited from whatever shell invoked us is not that
    checkout. `COMPOSE_PROFILES="*"` is set for the reason
    `tests/conftest.py::compose_config` documents: a service carrying
    `profiles:` is otherwise omitted from the resolved output.
    """
    env = dict(os.environ)
    env.pop(_PROJECT_NAME_VAR, None)
    env[_PROFILES_VAR] = "*"
    raw = _run(
        ["docker", "compose", "config", "--format", "json"], cwd=root, env=env
    )
    try:
        config = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IdentityError(
            f"`docker compose config` in {root} produced output that is not "
            f"JSON: {exc}"
        ) from exc
    name = str(config.get("name", "")).strip()
    if not name:
        raise IdentityError(
            f"`docker compose config` in {root} declared no project name."
        )
    return name


def _project_containers(project: str) -> list[dict[str, str]]:
    """Every container -- running or not -- labelled with `project`.

    Stopped containers count. A stopped container still holds its name, its
    binds and its published ports, and it is still evidence that this
    project is the one deployed from this checkout.
    """
    fmt = '{{.Names}}\t{{.Label "' + WORKING_DIR_LABEL + '"}}'
    out = _run([
        "docker", "ps", "-a",
        "--filter", f"label={PROJECT_LABEL}={project}",
        "--format", fmt,
    ])
    containers: list[dict[str, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        name, _, working_dir = line.partition("\t")
        containers.append(
            {"name": name.strip(), "working_dir": working_dir.strip()}
        )
    return containers


def reset_caches() -> None:
    """Drop every memoised answer in this module.

    The seam a test needs when it repoints production's root: the caches above
    are correct for the life of a process and wrong across a `monkeypatch`, and
    "delete the cache" is not the fix for that -- `aurora-cli/tests/conftest.py`
    calls this from an autouse fixture instead.
    """
    for fn in (production_root, declared_project, _compose_declared_project):
        fn.cache_clear()


def production_project() -> str:
    """Production's compose project name, derived and then cross-checked.

    Three steps, and the second two are the point:

    1. Read what production's checkout *declares*.
    2. Require that the declaration matches at least one container on this
       daemon. A declared name matching no containers is trap 2 -- the
       vacuous conformance pass -- in a new costume: every downstream guard
       phrased as "is this production?" would answer "no" for everything.
    3. Require every such container's working-directory label to resolve to
       production's checkout. This is what catches a *second* stack, or a
       stale project of the same name deployed from somewhere else.

    Both sides of the path comparison are resolved. On this host `/home` is
    a symlink to `/var/home`, and every one of production's containers
    carries a working-directory label under the unresolved `/home/...` form
    while Python resolves to `/var/home/...`; comparing the strings makes
    this function raise on a perfectly healthy host.

    Raises `IdentityError` naming both operands whenever the declaration and
    the runtime disagree. It never silently prefers one -- a wrong answer
    here is how a branch operation reaches production.
    """
    root = production_root()
    declared = _compose_declared_project(root)
    containers = _project_containers(declared)

    if not containers:
        raise IdentityError(
            f"The checkout at {root} declares compose project {declared!r}, "
            f"but no container on this daemon carries "
            f"{PROJECT_LABEL}={declared}. Either the stack is down -- in "
            "which case bring it up rather than letting every "
            "'is this production?' check answer no -- or the declaration is "
            "stale."
        )

    labelled = {c["working_dir"] for c in containers if c["working_dir"]}
    if not labelled:
        raise IdentityError(
            f"Containers for project {declared!r} carry no "
            f"{WORKING_DIR_LABEL} label, so the declaration at {root} cannot "
            f"be tied to them: {sorted(c['name'] for c in containers)}"
        )

    mismatched = sorted(w for w in labelled if Path(w).resolve() != root)
    if mismatched:
        raise IdentityError(
            f"The checkout at {root} declares compose project {declared!r}, "
            f"but containers with that label were deployed from {mismatched}. "
            "Two stacks share a project name, or this is not production's "
            "checkout. Refusing to choose between them."
        )
    return declared


def production_env() -> dict[str, str]:
    """Production's `.env`, read from production's checkout.

    Not this worktree's `.env`. Until the rename lands the two differ by
    construction -- production's `COMPOSE_PROJECT_NAME` is the old name,
    every worktree's is `aurora` -- and that divergence is the cheapest
    available test of whether a caller actually derived anything.
    """
    return _read_env_file(production_root() / _ENV_FILE)


def production_domain() -> str:
    """Production's fully-qualified tailnet name, from its `DOMAIN_NAME`."""
    domain = production_env().get(_DOMAIN_VAR, "")
    if not domain:
        raise IdentityError(
            f"Production's {_ENV_FILE} at {production_root()} declares no "
            f"{_DOMAIN_VAR}."
        )
    return domain


def tailnet_suffix() -> str:
    """The tailnet domain: production's domain minus its first label.

    `<host>.<tailnet>.ts.net` -> `<tailnet>.ts.net`. Derived so that the
    tailnet name appears in no source file: a tailnet suffix is an
    account-scoped identifier, hardcoding it makes this package usable on
    exactly one tailnet, and the literal scan in this module's tests bans it
    for that reason.
    """
    domain = production_domain()
    _, sep, suffix = domain.partition(".")
    if not sep or not suffix:
        raise IdentityError(
            f"Production's {_DOMAIN_VAR} is {domain!r}, which has no domain "
            "part; a branch hostname cannot be derived from it."
        )
    return suffix


# ---------------------------------------------------------------------------
# branch naming
# ---------------------------------------------------------------------------


def branch_hostname_prefix() -> str:
    """The prefix every branch's tailnet hostname carries: `<product>-`."""
    return f"{declared_project()}-"


def sanitise_branch_name(raw: str) -> str:
    """Spec 7.1: a git branch name reduced to one safe DNS label.

    Lowercased, every run of non-alphanumerics collapsed to a single `-`,
    leading and trailing `-` stripped, then truncated so that the *hostname*
    -- prefix included -- fits in a DNS label.

    The budget is `63 - len(prefix)`, not 63. Truncating the name to 63 is
    the off-by-a-prefix that produces `aurora-<63 chars>`: 70 octets, an
    invalid label, and a Tailscale node that registers under a name nobody
    asked for or fails to register at all.

    Idempotent -- `f(f(x)) == f(x)` -- because callers sanitise defensively
    and a second pass must not erode the name further. Raises on input that
    sanitises to nothing, rather than returning `""`, which would make the
    branch project name the bare namespace prefix.
    """
    if not isinstance(raw, str):
        raise IdentityError(
            f"A branch name must be a string, got {type(raw).__name__}: {raw!r}"
        )
    collapsed = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    if not collapsed:
        raise IdentityError(
            f"{raw!r} contains no alphanumeric character, so it sanitises to "
            "the empty string; a branch needs a name."
        )
    budget = DNS_LABEL_MAX - len(branch_hostname_prefix())
    if budget < 1:
        raise IdentityError(
            f"The hostname prefix {branch_hostname_prefix()!r} leaves no room "
            f"inside a {DNS_LABEL_MAX}-octet DNS label."
        )
    truncated = collapsed[:budget].strip("-")
    if not truncated:
        raise IdentityError(
            f"{raw!r} sanitises to {collapsed!r}, which is empty once "
            f"truncated to {budget} characters."
        )
    return truncated


def branch_project(name: str) -> str:
    """The compose project name for a branch: `br-<name>`.

    Sanitised on the way through even though callers are expected to have
    sanitised already. `sanitise_branch_name` is idempotent so this costs
    nothing, and the namespace prefix is the only thing standing between a
    destructive compose call and production.
    """
    return f"{BRANCH_PROJECT_PREFIX}{sanitise_branch_name(name)}"


def branch_hostname(name: str) -> str:
    """The branch's tailnet node name: `<product>-<name>`."""
    hostname = f"{branch_hostname_prefix()}{sanitise_branch_name(name)}"
    if len(hostname) > DNS_LABEL_MAX:
        raise IdentityError(
            f"{hostname!r} is {len(hostname)} octets; a DNS label may not "
            f"exceed {DNS_LABEL_MAX}."
        )
    return hostname


def branch_domain(name: str) -> str:
    """The branch's fully-qualified name: `<product>-<name>.<tailnet>`."""
    return f"{branch_hostname(name)}.{tailnet_suffix()}"


@dataclass(frozen=True)
class BranchPaths:
    """Everything a branch lifecycle command needs to locate on disk."""

    name: str
    project: str
    hostname: str
    domain: str
    worktree: Path
    env_file: Path
    access_doc: Path


def branch_paths(name: str) -> BranchPaths:
    """Resolve a branch's project, hostname, domain and on-disk locations.

    The worktree sits at `<production checkout>/.worktrees/<name>` per
    decision D-F: `.worktrees/` is gitignored and already inside the tree
    production's agent mounts, which is what makes "the original agent reads
    every branch's access document with no extra wiring" true for free.
    """
    sanitised = sanitise_branch_name(name)
    worktree = production_root() / _WORKTREE_DIRNAME / sanitised
    return BranchPaths(
        name=sanitised,
        project=branch_project(sanitised),
        hostname=branch_hostname(sanitised),
        domain=branch_domain(sanitised),
        worktree=worktree,
        env_file=worktree / _ENV_FILE,
        access_doc=worktree / _ACCESS_DOC_NAME,
    )


def describe() -> dict[str, str]:
    """Production's derived identity, flattened for display.

    One place builds this so `aurora branch ls` and the MCP facade cannot
    report different answers to the same question.
    """
    return {
        "production_project": production_project(),
        "production_root": str(production_root()),
        "production_domain": production_domain(),
        "declared_project": declared_project(),
        "tailnet_suffix": tailnet_suffix(),
        "branch_project_prefix": BRANCH_PROJECT_PREFIX,
        "branch_hostname_prefix": branch_hostname_prefix(),
        "running_from": str(package_root()),
    }
