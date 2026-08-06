from __future__ import annotations

import subprocess

from dev_administration.project import (
    ProjectMismatch,
    assert_same_project,
    current_project,
    network_name,
)

# NOTE: the module-level NETWORK constant, which was hardcoded to
# production's default bridge, was deleted in Chunk 2 (M5). The network is
# derived per call from the running project, because a branch's is
# `br-<name>_default` and no single constant can be correct for both.
# HERMES_IMAGE now lives in agents_compose.py, which is what declares the
# agent services.
#
# The old literal is deliberately not quoted anywhere in this module:
# test_guard_coverage.test_no_hardcoded_project_identity_remains scans raw
# module source including comments, on the grounds that a comment naming the
# old network is a latent copy-paste source.


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def volume_exists(name: str) -> bool:
    result = _run(["docker", "volume", "inspect", name], check=False)
    return result.returncode == 0


def create_volume(name: str) -> None:
    """Create a project-scoped volume that Compose will adopt.

    The two labels are what make adoption clean: Compose treats a
    pre-existing volume carrying its project and volume labels as its own and
    preserves the contents (probed on Compose v5.3.1: seeded volume, then
    `docker compose create`, no warning, marker file intact). The
    `config-hash` label is deliberately not forged -- Compose does not need it
    to adopt.

    Refuses an unprefixed name: `hermes-juan-home` is reachable from every
    project on the daemon, which is exactly how a branch would write into
    production's agent state.
    """
    project = current_project()
    prefix = f"{project}_"
    if not name.startswith(prefix):
        raise ProjectMismatch(
            f"Refusing to create volume {name!r}: it is not scoped to project "
            f"{project!r}. Build the name with project.agent_volume()."
        )
    _run([
        "docker", "volume", "create",
        "--label", f"com.docker.compose.project={project}",
        "--label", f"com.docker.compose.volume={name[len(prefix):]}",
        name,
    ], check=False)


def container_exists(name: str) -> bool:
    result = _run(["docker", "inspect", name], check=False)
    return result.returncode == 0


def container_status(name: str) -> str | None:
    result = _run(["docker", "inspect", "-f", "{{.State.Status}}", name], check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def run_temp_container(
    image: str,
    command: list[str],
    volumes: dict[str, str] | None = None,
    env: dict[str, str] | None = None,
    network: str | None = None,
) -> str:
    """Run a throwaway container.

    An explicitly-passed network must be this project's. Callers that just
    want "our network" pass None and let the caller-side helper supply
    network_name(); the check here is what stops a stale literal from
    attaching a branch's temp container to production's bridge, where it
    would resolve production's service DNS.
    """
    if network is not None:
        # Resolved only when a network was actually requested. Callers that
        # want "our network" pass None; making them resolve a project they
        # never asked about adds a failure mode for no benefit.
        own_network = network_name()
        if network != own_network:
            raise ProjectMismatch(
                f"Refusing to attach a temp container to {network!r}: this "
                f"project's network is {own_network!r}."
            )
    cmd = ["docker", "run", "--rm"]
    if volumes:
        for host_path, container_path in volumes.items():
            cmd.extend(["-v", f"{host_path}:{container_path}"])
    if env:
        for key, value in env.items():
            cmd.extend(["-e", f"{key}={value}"])
    if network is not None:
        cmd.extend(["--network", network])
    cmd.append(image)
    cmd.extend(command)
    result = _run(cmd)
    return result.stdout.strip()


def stop_and_remove_container(name: str) -> None:
    assert_same_project(name)
    _run(["docker", "stop", name], check=False)
    _run(["docker", "rm", name], check=False)


def list_containers(prefix: str) -> list[str]:
    result = _run(["docker", "ps", "-a", "--format", "{{.Names}}"], check=False)
    if result.returncode != 0:
        return []
    return [
        name for name in result.stdout.strip().split("\n")
        if name.startswith(prefix) and name.strip()
    ]


def list_volumes(prefix: str) -> list[str]:
    result = _run(["docker", "volume", "ls", "--format", "{{.Name}}"], check=False)
    if result.returncode != 0:
        return []
    return [
        name for name in result.stdout.strip().split("\n")
        if name.startswith(prefix) and name.strip()
    ]


def docker_exec(name: str, command: str) -> str:
    assert_same_project(name)
    result = _run(["docker", "exec", name, "sh", "-c", command], check=False)
    return result.stdout.strip()
