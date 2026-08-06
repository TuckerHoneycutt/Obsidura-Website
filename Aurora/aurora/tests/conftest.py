import functools
import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# The project whose running containers we conform to. `aurora` since
# Task 9's rename; override with AURORA_PROJECT while the deployed stack
# still carries the old label. Deliberately NOT
# derived from `docker compose config`: inside a git worktree the compose
# project name comes from the directory basename, which matches no running
# containers and would make the conformance assertion vacuous.
PRODUCTION_PROJECT = os.environ.get("AURORA_PROJECT", "aurora")

# Host paths a service may legitimately bind from outside the repo. Anything
# else must resolve inside REPO_ROOT, or a second copy of this stack would
# silently share production's state — which is the whole point of Chunk 2.
#
# Resolved at definition time, not left as typed. Every consumer compares
# these against a `.resolve()`d actual mount source, and on this host
# /var/run is a symlink to /run and /etc/localtime to a zoneinfo file under
# /usr/share/zoneinfo — so an unresolved entry here would silently never
# match, no matter how correct the running container is. That exact bug
# class (comparing a resolved path against an unresolved one across a
# symlink) is what let AFFiNE's bind-path defect through Chunk 1's gate and
# is Task 6's open `handle_path` failure; don't let it hide a third time in
# the allowlist meant to catch it.
#
# Deliberately does NOT include hermes' `~/.hermes` or its whole-repo bind:
# those are exactly the two absolute, outside-the-repo binds Task 8 (M6)
# exists to remove (spec §5.2 — they are what makes a branch share
# production's agent state). Allowlisting them here would let
# tests/test_runtime_conformance.py::test_declared_bind_sources_match_runtime
# pass whether or not Task 8's fix is present; it is marked `xfail(strict=True)`
# there instead, so it stays red until Task 8 lands.
ALLOWED_EXTERNAL_BINDS = tuple(
    p.resolve()
    for p in (
        Path("/var/run/docker.sock"),
        Path("/var/run/tailscale"),
        Path("/etc/localtime"),
    )
)


def compose_config(all_profiles: bool = True) -> dict:
    """Fully resolved compose configuration for the repo, as a dict.

    COMPOSE_PROFILES="*" is set for a reason that cost Chunk 1 a working
    gate: a service carrying `profiles:` is omitted from this output unless
    its profile is active, so its still-labelled container reads as
    *undeclared*. Verified on Compose v5.3.1 — see
    tests/test_repo_conformance.py::test_compose_config_sees_profiled_services.

    Pass all_profiles=False to ask the different question "what would a
    default `docker compose up` actually start?".
    """
    env = dict(os.environ)
    env.pop("COMPOSE_PROFILES", None)
    if all_profiles:
        env["COMPOSE_PROFILES"] = "*"
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return json.loads(result.stdout)


@functools.cache
def compose_config_cached() -> dict:
    """`compose_config()` rendered once per session.

    Every call spawns `docker compose config`, which resolves the whole
    repository; a dozen callers asking the same question is most of this
    suite's wall clock. Not memoised on `compose_config` itself, because
    test_repo_conformance asserts what that function passes subprocess.run.
    Treat the result as read-only -- it is shared.
    """
    return compose_config()


def declared_image(service_name: str, service: dict) -> str:
    """What image Compose would use for one service.

    A build-only service has no `image:` key and Compose synthesises
    `<project>-<service>` — so the project name has to come from somewhere,
    and it deliberately comes from PRODUCTION_PROJECT rather than from
    `docker compose config`'s `name`. Inside a git worktree that field is the
    directory basename, which names images that were never built, and every
    caller here would then be asking about a stack that does not exist.

    Lives in conftest because two test modules need it and the answer must be
    the same one: test_runtime_conformance compares it against what a
    container is running, and test_build_conformance compares its creation
    time against git. Two spellings of "which image is this service's" is the
    drift this repository keeps paying for.
    """
    return service.get("image") or f"{PRODUCTION_PROJECT}-{service_name}"


def buildable_services(config: dict) -> dict[str, tuple[str, str]]:
    """service -> (image, build context), for every service declaring `build:`.

    Derived from the resolved config, never a hardcoded list: the three
    services that build from source today (fjell, agent-authz, dev-admin) are
    a fact about this commit, not about this stack.
    """
    return {
        name: (declared_image(name, service), service["build"]["context"])
        for name, service in config["services"].items()
        if service.get("build")
    }


def is_tracked(path: Path) -> bool:
    """True if git tracks at least one file under `path`."""
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def project_containers(project: str = PRODUCTION_PROJECT) -> dict[str, str]:
    """Map compose service name -> container name for one project.

    Includes stopped containers: a stopped container still holds its name,
    its ports and its binds, and is still something the repo must describe.
    """
    result = subprocess.run(
        [
            "docker", "ps", "-a",
            "--filter", f"label=com.docker.compose.project={project}",
            "--format", '{{.Label "com.docker.compose.service"}}\t{{.Names}}',
        ],
        capture_output=True, text=True, check=True,
    )
    mapping: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        service, _, container = line.partition("\t")
        if service.strip():
            mapping[service.strip()] = container.strip()
    return mapping


def inspect_container(name: str) -> dict:
    result = subprocess.run(
        ["docker", "inspect", name],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)[0]


def all_container_names() -> list[str]:
    result = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        capture_output=True, text=True, check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


@pytest.fixture(scope="session")
def config() -> dict:
    return compose_config_cached()


@pytest.fixture(autouse=True)
def _clear_identity_caches():
    """See aurora-cli/tests/conftest.py -- the same fixture, same reason.

    `identity`'s three memoised answers are per-process pure and per-TEST
    wrong the moment a test repoints production's root. Clearing them here is
    what makes keeping the `lru_cache`s (a subprocess each, dozens of calls
    per command) compatible with a suite that monkeypatches the root.
    """
    import sys
    identity = sys.modules.get("aurora_cli.identity")
    if identity is None:
        yield
        return
    identity.reset_caches()
    yield
    identity.reset_caches()
