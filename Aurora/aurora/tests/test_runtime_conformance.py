"""Declaration-vs-runtime conformance.

Chunk 1's gate compared service NAMES only. Nothing compared a declared
image, bind source or published port against what the daemon actually runs,
and that blind spot is exactly how a Critical defect reached final review:
AFFiNE was correctly "declared" at a bind path production had never used.

These assert runtime is a subset of declaration. They deliberately do NOT
assert the converse: a declared service may be legitimately stopped, or
(after compose.agents.yml lands) gated behind an inactive profile.
"""

import subprocess
from pathlib import Path

import pytest

from conftest import (
    ALLOWED_EXTERNAL_BINDS,
    PRODUCTION_PROJECT,
    REPO_ROOT,
    all_container_names,
    compose_config,
    declared_image,
    inspect_container,
    project_containers,
)


def _production_checkout_root(containers: dict[str, str]) -> Path | None:
    """The directory `docker compose` was actually run from to bring up the
    running production containers, read from the
    `com.docker.compose.project.working_dir` label Compose stamps on every
    container it creates. None if there are no containers to ask.
    """
    for container in containers.values():
        working_dir = (inspect_container(container)["Config"]["Labels"] or {}).get(
            "com.docker.compose.project.working_dir"
        )
        if working_dir:
            return Path(working_dir).resolve()
    return None


def _rebase(path: Path, src: Path, dst: Path) -> Path:
    """Reproject a path declared relative to `src` onto `dst`.

    A declared bind source and the container it produced were computed from
    an identical compose.yml but resolved by different invocations of
    `docker compose config` — this checkout's (`src`) and whichever one
    actually brought the containers up (`dst`). A relative path resolves
    against whichever directory that invocation ran from, so the two
    absolute paths differ by exactly this prefix even when nothing is
    actually wrong. Absolute declarations (docker.sock, `~`-expanded host
    paths) are untouched: they don't live under `src` to begin with.
    """
    if path == src or src in path.parents:
        return dst / path.relative_to(src)
    return path


def _image_id(ref: str) -> str | None:
    """The local image ID `ref` resolves to, or None if it resolves to nothing."""
    proc = subprocess.run(
        ["docker", "image", "inspect", ref, "--format", "{{.Id}}"],
        capture_output=True, text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


def test_declared_image_matches_runtime():
    """Is each container running the image the repo declares?

    Compared by image ID rather than by the reference STRING. Every external
    image is pinned as `tag@sha256:...`, so a container created before the pin
    reports `Config.Image` as the bare tag while the repo now names the same
    bytes with a digest -- identical software, two spellings. Comparing strings
    reports that as production drift, and is wrong.

    The ID comparison is not the weaker check: a pin genuinely moved to a
    different image resolves to a different ID and still fails here. What it
    stops doing is failing on how the same image is written down.
    """
    config = compose_config()
    mismatches = []
    for service, container in project_containers().items():
        declared = config["services"].get(service)
        if declared is None:
            continue  # covered by test_no_undeclared_containers_in_project
        expected_ref = declared_image(service, declared)
        inspected = inspect_container(container)
        if "@sha256:" not in expected_ref:
            # A `build:` service has no registry identity to conform to: its
            # tag moves on every rebuild while the container keeps the bytes it
            # started with. Comparing IDs here would report STALENESS, which
            # `test_build_conformance.py::test_no_image_is_older_than_its_build_context`
            # already owns and already reports for the same services. Two gates
            # for one property is how one of them stops being read.
            actual = inspected["Config"]["Image"]
            if actual != expected_ref:
                mismatches.append((service, container, expected_ref, actual))
            continue
        expected_id = _image_id(expected_ref)
        actual_id = inspected["Image"]
        if expected_id is None or actual_id != expected_id:
            mismatches.append((service, container, expected_ref,
                               expected_id or "<declared ref not in local store>",
                               actual_id))

    assert mismatches == [], (
        "Containers running an image the repo does not declare "
        "(service, container, declared ref, declared id, running id): "
        + repr(mismatches)
    )


def test_declared_bind_sources_match_runtime():
    """Every bind a container actually holds must be declared, and must
    resolve either inside the repo or to an explicitly allowed host path.

    Both sides are resolved before comparison: `docker compose config`
    reports paths from Go's os.Getwd(), which trusts a stale $PWD, and on
    this host /home is a symlink to /var/home.

    Relative bind sources resolve against whichever directory `docker
    compose config` runs from, so a naive comparison is only meaningful
    when REPO_ROOT (this checkout) is the same directory that actually
    brought the running containers up — inside a git worktree it never is.
    Rather than let that make the assertion vacuous (skip) or wrong (compare
    anyway and report every relative bind as a false "undeclared bind"),
    declared sources are rebased from REPO_ROOT onto whichever directory
    actually deployed the stack (read from the compose-stamped
    `com.docker.compose.project.working_dir` label), and the repo-escape
    check is made against that same directory. This makes the assertion
    meaningful from any checkout, worktree included, and is what actually
    executes this test's logic in every plan step that runs it — no step
    ever runs pytest from the checkout that deployed the stack, so a skip
    here would leave this test permanently inert.

    This was `xfail(strict=True)` until 2026-07-31. ~/.hermes and the
    whole-repo bind under hermes were absolute binds outside REPO_ROOT that
    Task 8 (M6) removed from the DECLARATION and Task 12 from the runtime —
    but production went on running containers created before either, so the
    runtime half stayed false until the Chunk 2 project rename recreated
    every container. The strict marker then did exactly what its
    reason said it would: it failed as XPASS and demanded its own removal
    rather than decaying into a stale xfail that masks a regression.

    It is now an ordinary assertion, and it is the regression guard for
    spec §5.2 — a container holding an undeclared bind outside the repo is
    how a second stack comes to share production's agent state.
    """
    containers = project_containers()
    production_root = _production_checkout_root(containers)
    containment_root = production_root if production_root is not None else REPO_ROOT

    config = compose_config()
    problems = []
    for service, container in containers.items():
        declared_service = config["services"].get(service)
        if declared_service is None:
            continue
        declared = set()
        for v in declared_service.get("volumes", []):
            if v.get("type") != "bind":
                continue
            source = Path(v["source"]).resolve()
            if production_root is not None:
                source = _rebase(source, REPO_ROOT, production_root)
            declared.add(source)
        for mount in inspect_container(container)["Mounts"]:
            if mount["Type"] != "bind":
                continue
            actual = Path(mount["Source"]).resolve()
            if actual not in declared:
                problems.append((service, container, str(actual), "undeclared bind"))
            elif actual not in ALLOWED_EXTERNAL_BINDS and (
                actual != containment_root and containment_root not in actual.parents
            ):
                problems.append((service, container, str(actual), "outside the repo"))

    assert problems == [], (
        "Bind mounts that are undeclared or escape the repo — a second copy "
        "of this stack would share production's state through them: "
        + repr(problems)
    )


def test_declared_published_ports_match_runtime():
    config = compose_config()
    problems = []
    for service, container in project_containers().items():
        declared_service = config["services"].get(service)
        if declared_service is None:
            continue
        declared = {
            (
                p.get("host_ip") or "0.0.0.0",
                str(p["published"]),
                f'{p["target"]}/{p.get("protocol", "tcp")}',
            )
            for p in declared_service.get("ports", [])
        }
        bindings = inspect_container(container)["HostConfig"]["PortBindings"] or {}
        for target, hosts in bindings.items():
            for host in hosts or []:
                actual = (host.get("HostIp") or "0.0.0.0", host.get("HostPort"), target)
                if actual not in declared:
                    problems.append((service, container, actual, sorted(declared)))

    assert problems == [], (
        "Containers publishing host ports the repo does not declare "
        "(service, container, running, declared): " + repr(problems)
    )


def test_every_container_on_the_project_network_carries_the_project_label():
    """A container with no compose labels is invisible to every
    project-label filter — including `docker compose down --remove-orphans`.
    Joining `<project>_default` for service DNS is one place it cannot hide
    this way, though not the only place it could exist: `caddy` itself runs
    on `network_mode: host`, so an unlabelled container on host or default
    bridge networking would still evade this specific check.

    This is the exact shape the three `hermes-*` dev agents had before M4.
    """
    network = f"{PRODUCTION_PROJECT}_default"
    offenders = []
    for name in all_container_names():
        data = inspect_container(name)
        if network not in (data["NetworkSettings"]["Networks"] or {}):
            continue
        labels = data["Config"]["Labels"] or {}
        if labels.get("com.docker.compose.project") != PRODUCTION_PROJECT:
            offenders.append((name, data["State"]["Status"]))

    assert offenders == [], (
        f"Containers attached to {network} without the {PRODUCTION_PROJECT!r} "
        f"project label. Compose cannot see, stop or remove them: {offenders}"
    )
