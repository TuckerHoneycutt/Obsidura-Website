"""Project identity and the spec §5.3 safety guard.

Everything this package does to a container, volume or network is scoped to
exactly one Compose project. Per spec D12, Hermes and dev-admin both keep
`/var/run/docker.sock`, so Docker does NOT enforce that scoping for us — the
guard in this module is the only thing standing between a branch-context
operation and production. It is load-bearing, not defensive.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

_PROJECT_LABEL = "com.docker.compose.project"
_SERVICE_LABEL = "com.docker.compose.service"


class ProjectMismatch(RuntimeError):
    """Raised when an operation would touch something outside this project."""


@dataclass(frozen=True)
class _Container:
    service: str
    name: str
    running: bool


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def container_project(container: str) -> str | None:
    """The Compose project a container belongs to, or None if it carries no
    project label or does not exist."""
    result = _run([
        "docker", "inspect", "-f",
        f'{{{{index .Config.Labels "{_PROJECT_LABEL}"}}}}',
        container,
    ])
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def current_project() -> str:
    """This process's own Compose project.

    Self-inspection first, environment second. An environment variable can
    be stale or inherited: spec §4.1 renders a branch's .env FROM
    production's, so a failed COMPOSE_PROJECT_NAME override would leave a
    branch believing it is production. The container's own label cannot lie.

    Outside a container (the CLI run on the host) there is no label to read,
    so COMPOSE_PROJECT_NAME is required rather than defaulted — guessing
    here is exactly the failure this module exists to prevent.
    """
    try:
        container_id = Path("/etc/hostname").read_text().strip()
    except OSError:
        container_id = ""
    if container_id:
        own = container_project(container_id)
        if own:
            return own
    env = os.environ.get("COMPOSE_PROJECT_NAME", "").strip()
    if env:
        return env
    raise ProjectMismatch(
        "Cannot determine this process's Compose project: no project label on "
        "its own container and COMPOSE_PROJECT_NAME is unset. Refusing to "
        "guess — a wrong guess writes to another project's containers."
    )


def network_name(project: str | None = None) -> str:
    """The project's default bridge network."""
    return f"{project or current_project()}_default"


def agent_volume(username: str, project: str | None = None) -> str:
    """The project-scoped volume backing one developer's Hermes home.

    Mirrors what Compose does for `volumes: {hermes-<u>-home: {}}`. An
    unprefixed name is reachable from every project on the daemon, which is
    how a branch would end up writing into production's agent state.
    """
    return f"{project or current_project()}_hermes-{username}-home"


def assert_same_project(container: str) -> None:
    """Refuse to touch a container that is not ours.

    Spec §5.3: every mutating dev-admin operation asserts that the target
    container's com.docker.compose.project label equals its own
    COMPOSE_PROJECT_NAME, and refuses otherwise. An unlabelled or missing
    container is refused too — it cannot be proven to belong to us.
    """
    mine = current_project()
    theirs = container_project(container)
    if theirs is None:
        raise ProjectMismatch(
            f"Refusing to operate on {container!r}: it carries no "
            f"{_PROJECT_LABEL} label, so it cannot be proven to belong to "
            f"project {mine!r}."
        )
    if theirs != mine:
        raise ProjectMismatch(
            f"Refusing to operate on {container!r}: it belongs to project "
            f"{theirs!r}, not {mine!r}."
        )


def _project_containers(proj: str) -> list[_Container]:
    """Every non-one-off container in this project, newest-first, with its
    service label and running state.

    This is the single source of truth for "which container represents
    service X in this project" — project_services() and
    find_service_container() both build on this instead of each running
    its own independently-filtered `docker ps`. They drifted twice when
    they didn't: first on the oldest/newest tie-break, then on
    running-vs-stopped preference. One query, one selection rule
    (_pick_service_container below), used by both, is the only way this
    class of bug cannot recur — two "identical" filters maintained in two
    places is exactly what produced it.

    Fails closed: a nonzero `docker ps` exit raises rather than returning
    `[]`, because an empty result must not be indistinguishable from
    "Docker is unreachable" — every other function in this module treats a
    Docker failure as "cannot prove this is safe."
    """
    result = _run([
        "docker", "ps", "-a",
        "--filter", f"label={_PROJECT_LABEL}={proj}",
        "--filter", "label=com.docker.compose.oneoff=False",
        "--format", '{{.Label "' + _SERVICE_LABEL + '"}}\t{{.Names}}\t{{.State}}',
    ])
    if result.returncode != 0:
        raise ProjectMismatch(
            f"Failed to list containers for project {proj!r}: `docker ps` "
            f"exited {result.returncode}: {result.stderr.strip()}"
        )
    containers: list[_Container] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        service, _, rest = line.partition("\t")
        name, _, state = rest.partition("\t")
        service = service.strip()
        if not service:
            continue
        containers.append(
            _Container(service=service, name=name.strip(), running=state.strip() == "running")
        )
    return containers


def _pick_service_container(containers: list[_Container], service: str, proj: str) -> str:
    """Choose the one container representing `service` from a project's
    container list (already newest-first, from _project_containers()).

    Prefers a running container over a stopped one: `docker cp` succeeds
    against a stopped container, so a cp-then-exec caller (Task 4's Caddy
    reload) must not be handed a dead container just because it happens to
    be newest — a crash-looped recreate can leave a newer container
    exited and an older one still running. Among equally-preferred
    candidates the newest (first in the list) wins. Refuses rather than
    guessing if more than one container is equally preferred — `docker
    ps`'s ordering is not a contract worth betting production safety on.
    """
    candidates = [c for c in containers if c.service == service]
    if not candidates:
        raise ProjectMismatch(
            f"No container for service {service!r} in project {proj!r}. "
            "Has `docker compose up -d` run for this project?"
        )
    running = [c for c in candidates if c.running]
    pool = running or candidates
    if len(pool) > 1:
        names = [c.name for c in pool]
        raise ProjectMismatch(
            f"{len(pool)} containers carry service {service!r} in project "
            f"{proj!r}: {names}. Refusing to guess which one is live."
        )
    return pool[0].name


def project_services(project: str | None = None) -> dict[str, str]:
    """Map service name -> container name for this project, stopped included.

    See _project_containers() / _pick_service_container() for the shared
    query and selection rule this and find_service_container() both use —
    that sharing is what guarantees the two agree.
    """
    proj = project or current_project()
    containers = _project_containers(proj)
    services = {c.service for c in containers}
    return {
        service: _pick_service_container(containers, service, proj) for service in services
    }


def find_service_container(service: str, project: str | None = None) -> str:
    """Resolve a service to its container name within this project.

    This replaces a hardcoded CADDY_CONTAINER naming production's own
    container. A
    branch's Caddy is `br-<name>-caddy-1`; production's is
    `<project>-caddy-1`; neither name is knowable in advance, but the
    label pair always is.

    See _project_containers() / _pick_service_container() for the shared
    query and selection rule this and project_services() both use.
    """
    proj = project or current_project()
    containers = _project_containers(proj)
    return _pick_service_container(containers, service, proj)
