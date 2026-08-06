"""Render `compose.branch.yml` — the ONLY configuration difference between
production and a branch (spec §4.2, plan finding N3).

Why this file is generated rather than written by hand:

`container_name:` opts a service OUT of Compose's project namespacing, so the
name it declares is DAEMON-GLOBAL. A branch that inherits one cannot start,
because production already owns the name. An inherited `ports:` entry is
worse than that -- it makes the branch try to bind a host port production is
already publishing, and whichever stack loses the race is the one that breaks.

The enumeration cannot be maintained by hand. The per-developer agent services
are themselves generated from `developers.yaml`, so a written list is stale the
moment a developer is added -- and the spec's own count has gone stale twice
already. So the list is derived from the RESOLVED compose configuration, which
is the same thing Compose itself will act on, and the drift between the
committed artifact and a fresh render is a test failure.

Two Compose behaviours this depends on, both probed on this host (v5.3.1):

  * `container_name: !reset null` and `ports: !reset []` work across an
    `include:` boundary -- `affine`/`postgres` come from `affine/compose.yml`
    and the agents from `compose.agents.yml`, and all of them are cleared by a
    top-level `-f` overlay.
  * `volumes: !override [...]` replaces a service's volume list wholesale,
    which is how Caddy's host `/var/run/tailscale` bind is swapped for the
    sidecar's socket volume.

Stdlib + pyyaml only (decision D-A).
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from aurora_cli import identity

# ---------------------------------------------------------------- constants

OVERLAY_NAME = "compose.branch.yml"
BASE_COMPOSE_NAME = "compose.yml"

#: The two keys that make a service unable to coexist with production
#: unconditionally. `container_name` is daemon-global; `ports` is host-global.
RESET_KEYS = ("container_name", "ports")

#: `image` is daemon-global too, and that was missed until 2026-07-31. An
#: EXPLICIT tag is shared by every project that names it: production's
#: `agent-authz:local` and a branch's are the same image, so building in a
#: branch overwrites what production runs on its next recreate. Measured on
#: this host -- `br-ownersbind` rebuilt `agent-authz:local` and
#: `dev-admin:local` at 23:24, out from under a production that had been
#: deployed an hour earlier. Nothing failed; the branch simply took the tag.
#:
#: Conditional, because resetting it is only safe where the service can still
#: produce an image without it -- i.e. where it also declares `build:`.
#: Resetting `image` on a pull-only service (caddy, forgejo, hermes, arcadedb)
#: would leave Compose with neither an image nor a way to make one, which is
#: why this cannot simply join RESET_KEYS. Services that build WITHOUT an
#: explicit tag (fjell) already get `<project>-<service>` from Compose and
#: need nothing here -- which is exactly why fjell was isolated and the other
#: two were not.
CONDITIONAL_RESET_KEYS = ("image",)

#: The one service the overlay ADDS. Defined here, above the inventory, because
#: `GLOBAL_EXEMPTIONS` is keyed by service and the sidecar has entries in it:
#: it is not in the base compose config, so the gate reached it only once the
#: gate was pointed at the overlaid configuration.
SIDECAR_SERVICE = "tailscale"


#: Every service key that names something the DAEMON owns rather than something
#: Compose namespaces per project. Compose namespaces exactly four things --
#: containers, volumes, networks and the project label -- so anything listed
#: here is shared with production unless the overlay resets it or an exemption
#: below explains why it is safe.
#:
#: The value is WHY the key is global. A key with no reason is a key nobody
#: checked, which is how `image` crossed the boundary unremarked until
#: 2026-07-31 and how three `docker.sock` binds did until 2026-08-01.
DAEMON_GLOBAL_KEYS: dict[str, str] = {
    "container_name": "a container name is unique across the daemon, not the project",
    "ports": "a published port binds a host address no project owns",
    "image": "two projects naming one tag share one image, so a branch build replaces it",
    "volumes": "a bind whose source is outside the worktree reaches production's files",
    "network_mode": "`host` or `container:` puts the service in someone else's namespace",
    "pid": "`host` shares the host process table",
    "ipc": "`host` shares host shared memory",
    "userns_mode": "`host` opts out of user-namespace isolation",
    "privileged": "a privileged container is not isolated from the host at all",
    "devices": "a host device node is shared with every project that maps it",
    "cap_add": "a capability applies to the host kernel, not to the project",
    "hostname": "announced on shared networks",
    "mac_address": "a duplicate MAC collides on any shared L2 network",
    # The six below were measured missing on 2026-08-01, by fabricating
    # services that carried them and watching `unguarded_globals` return `{}`.
    # The first two are not incidental: `runtime.py`'s own module docstring
    # states, from measurement, that "only `--security-opt label=disable` AND
    # `--group-add keep-groups` together" let a rootless container reach
    # production's docker socket. The two keys this branch itself identifies
    # as the entire escape route were the two the gate did not check -- and
    # `GLOBAL_EXEMPTIONS[("hermes", "group_add")]` sat here silencing nothing,
    # which is direct evidence the omission was noticed and dropped.
    "security_opt": (
        "`label=disable` / `seccomp=unconfined` opt out of the host "
        "confinement that IS the isolation -- measured as one of the two "
        "halves of reaching production's socket from a rootless container"
    ),
    "group_add": (
        "a supplementary group is a HOST gid whatever the project label says "
        "-- the other half of that same measured escape"
    ),
    "volumes_from": "names a CONTAINER, and no project namespaces a container",
    "cgroup_parent": (
        "a cgroup path outside the project's subtree escapes the ceilings P2 "
        "just added, so this key defeats a whole phase rather than one service"
    ),
    "sysctls": (
        "the namespaced ones are per-netns; the rest are the host kernel's, "
        "tuned per-kernel and not per-project"
    ),
    "uts": "`host` shares the host UTS namespace, i.e. the host's hostname",
}

#: Declarations deliberately left alone, keyed by (service, key), each with the
#: reason. Keyed per SERVICE on purpose: a blanket exemption for a key would
#: re-open the class for every service added later.
#:
#: An entry whose reason is empty fails the gate. An exemption nobody wrote
#: down is an exemption nobody checked.
GLOBAL_EXEMPTIONS: dict[tuple[str, str], str] = {
    ("caddy", "cap_add"): (
        "NET_ADMIN/NET_RAW are needed to serve on the tailnet interface. They "
        "apply inside the sidecar's network namespace, which the branch owns."
    ),
    ("caddy", "network_mode"): (
        "`service:tailscale` is the isolation, not a hole in it: it puts Caddy "
        "in the BRANCH sidecar's namespace instead of the host's."
    ),
    ("caddy", "volumes"): (
        "binds the HOST's /var/run/tailscale, but compose.branch.yml replaces "
        "caddy's volumes wholesale with `!override` so a branch mounts the "
        "sidecar's socket instead. Pinned by "
        "test_no_service_in_a_branch_binds_the_hosts_tailscaled_socket -- if "
        "that test goes, delete this exemption with it."
    ),
    ("forgejo", "volumes"): (
        "binds /etc/localtime read-only. A timezone file carries no state and "
        "cannot be written back through the mount."
    ),
    ("dev-admin", "volumes"): (
        "binds /var/run/docker.sock -- the ROOT daemon's socket, which owns "
        "production's containers. dev-admin manages containers, and with one "
        "daemon there is no other socket to give it. NOT safe, merely "
        "unavoidable today: P4 (rootless podman) replaces it with the user's "
        "own socket, which owns only branch containers. "
        "docs/issues/2026-08-01-branch-services-hold-the-docker-socket.md"
    ),
    ("fjell", "volumes"): (
        "binds /var/run/docker.sock. Unlike dev-admin it is NOT established "
        "that fjell needs a daemon at all -- answer that before P4 rather than "
        "carrying it forward. Same issue doc as dev-admin."
    ),
    ("hermes", "volumes"): (
        "binds /var/run/docker.sock, and the worktree root, and .hermes. The "
        "socket is the one that matters and it is the same hole as dev-admin's; "
        "whether the admin agent needs it is likewise unanswered. Same issue doc."
    ),
    ("hermes", "group_add"): (
        "the docker group, required only because hermes is given the daemon "
        "socket. Reconsider both together -- docs/issues/"
        "2026-08-01-branch-services-hold-the-docker-socket.md."
    ),
    # The sidecar is added BY the overlay, so it is not in the base compose
    # config and the gate never reached it while the gate ran over the base.
    # It is now run over the OVERLAID config, which is the branch's real
    # configuration and the only one that decides -- and these three are what
    # that surfaced. All three are on the one service that exists ONLY in a
    # branch, which is why an ungated sidecar was the worst place for a hole.
    (SIDECAR_SERVICE, "devices"): (
        "/dev/net/tun, and it is shared with the host by necessity: kernel-"
        "mode tailscaled needs it and every container that maps it gets the "
        "same read-write clone device. Opening a tun CLONE grants no access "
        "to any other namespace's interfaces -- what you get is a new "
        "interface in your own netns, which is the branch's."
    ),
    (SIDECAR_SERVICE, "cap_add"): (
        "NET_ADMIN/NET_RAW, needed to bring the tailnet interface up. They "
        "apply inside the sidecar's OWN network namespace, which the branch "
        "owns -- the same reason caddy's entry above gives, and caddy is in "
        "that namespace because of this service."
    ),
    (SIDECAR_SERVICE, "hostname"): (
        "${TS_HOSTNAME}, derived per branch by `envfile.branch_hostname` from "
        "the branch name. It is the one hostname in the stack that is "
        "guaranteed NOT to collide, and it is the node name the branch is "
        "reached by."
    ),
}


def host_bind_sources(body: dict, root: Path) -> tuple[str, ...]:
    """Bind sources this service mounts from OUTSIDE `root`.

    A repo-relative bind is branch-private -- the seed gave the branch its own
    copy. A bind from anywhere else is production's file, reached through a
    path the project label does not scope.
    """
    # RESOLVED on both sides. `/home` is a symlink to `/var/home` on this host
    # and compose reports the resolved form, so string-prefixing an unresolved
    # root marks every repo-relative bind as external. Cost three debugging
    # sessions before this rule was written down, and one more when this
    # function was first drafted against it.
    root = Path(root).resolve()
    outside = []
    for entry in body.get("volumes") or []:
        if not isinstance(entry, dict) or entry.get("type") != "bind":
            continue
        source = str(entry.get("source", ""))
        if not source:
            continue
        try:
            resolved = Path(source).resolve()
        except OSError:
            outside.append(source)
            continue
        if resolved != root and root not in resolved.parents:
            outside.append(source)
    return tuple(sorted(outside))


def reaches_outside(key: str, body: dict, root: Path) -> bool:
    """Does this service's declaration of `key` actually escape its project?

    Presence is not escape. `volumes` is global only for sources outside the
    worktree; `network_mode: service:<x>` names a service in THIS project and
    is how a branch is isolated, not how it leaks; an `image:` tag matters only
    where the service can also build one and thereby overwrite it.
    """
    value = body.get(key)
    if not value:
        return False
    if key == "volumes":
        return bool(host_bind_sources(body, root))
    if key == "network_mode":
        return not str(value).startswith("service:")
    if key == "image":
        return bool(body.get("build"))
    if key == "uts":
        return str(value) == "host"
    return True


def unguarded_globals(
    config: dict, resets: dict[str, dict[str, str | None]], root: Path,
) -> dict[str, tuple[str, ...]]:
    """service -> daemon-global keys it escapes with that nothing accounts for.

    Accounted for means: reset in the overlay, or carrying a non-empty written
    exemption. Anything else is a resource shared with production that no one
    decided to share.
    """
    unguarded: dict[str, tuple[str, ...]] = {}
    for name, body in sorted((config.get("services") or {}).items()):
        body = body or {}
        loose = tuple(
            key for key in sorted(DAEMON_GLOBAL_KEYS)
            if reaches_outside(key, body, root)
            and resets.get(name, {}).get(key) is None
            and not GLOBAL_EXEMPTIONS.get((name, key), "").strip()
        )
        if loose:
            unguarded[name] = loose
    return unguarded


def conditionally_resettable(key: str, body: dict) -> bool:
    """May `key` be reset for this service without leaving it unbuildable?"""
    if key == "image":
        return bool(body.get("build"))
    return False


#: What each key is reset TO. `null` and `[]` are the empty values Compose
#: expects for the respective types; the `!reset` tag is what actually removes
#: the inherited value -- an untagged `ports: []` MERGES with the base list and
#: changes nothing. `image: !reset null` removes the key outright, verified
#: against Compose rather than assumed: the resolved service then carries no
#: `image` at all and Compose derives `<project>-<service>` at build time.
RESET_VALUES = {
    "container_name": "!reset null",
    "ports": "!reset []",
    "image": "!reset null",
}

CADDY_SERVICE = "caddy"
STATE_VOLUME = "tailscale_state"
SOCK_VOLUME = "tailscale_sock"

#: Where tailscaled's socket lives, on the host and in the sidecar alike.
TAILSCALE_SOCKET_DIR = "/var/run/tailscale"

_GENERATED_MARKER = (
    "  # --- generated from the resolved config: every service that declares\n"
    "  # --- container_name or ports, and therefore cannot be namespaced ---"
)

_HEADER = """\
# GENERATED by `dev-admin render-branch-override` — do not edit.
#
# The ONLY configuration difference between production and a branch, together
# with the branch .env and its seeded state. Every service definition is
# byte-identical to production's, which is what makes a branch a test OF
# production rather than a test of a fiction.
#
# Regenerate after ANY change to compose.yml, affine/compose.yml,
# compose.agents.yml or developers.yaml:
#
#     python -m dev_administration.cli render-branch-override
#
# and COMMIT the result. Compose's `-f` is a hard error on a missing file and
# a fresh worktree has only what git tracks, which is the same reason
# compose.agents.yml is committed.
#
# tests/test_branch_overlay.py fails if this file and the resolved config
# disagree, and fails separately if any service the resolved config shows
# declaring container_name or ports is missing from the list below.
"""

_SIDECAR_BLOCK = """\
  # The branch's own tailnet node. Everything else in the stack keeps
  # production's definition; this service exists only in a branch.
  tailscale:
    image: tailscale/tailscale:latest@sha256:cdf5612ded5be1344f1a704b8c5e53496db97376bb533e5e15f141e48bf60cc0
    hostname: ${TS_HOSTNAME:?a branch needs TS_HOSTNAME}
    environment:
      # `:?` on purpose (D-D): a tailscaled with NO auth key does not fail.
      # It starts, prints `Logged out.` with a login URL and stays up, so a
      # branch would "succeed" with a dead URL. Making it a hard config error
      # is the only way the failure is loud.
      - TS_AUTHKEY=${TS_AUTHKEY:?a branch needs an ephemeral Tailscale auth key}
      - TS_HOSTNAME=${TS_HOSTNAME}
      - TS_STATE_DIR=/var/lib/tailscale
      - TS_SOCKET=/var/run/tailscale/tailscaled.sock
      # Kernel mode, NOT userspace: Caddy shares this netns and binds :443
      # there, which only receives tailnet traffic if a real tailscale0
      # interface exists in the namespace. Verified on this host with
      # NET_ADMIN/NET_RAW and /dev/net/tun.
      - TS_USERSPACE=false
      # Load-bearing. Accepting MagicDNS rewrites resolv.conf in the SHARED
      # netns to 100.100.100.100, removing Docker's 127.0.0.11 — and every
      # *_UPSTREAM in a branch is a Docker service name, not an address.
      - TS_ACCEPT_DNS=false
    volumes:
      # A project-scoped volume, NOT `mem:`. With in-memory state a restart
      # re-registers the node and can land it on `<hostname>-1`; with a volume
      # the identity survives a restart, and because the volume is
      # project-scoped `down -v` still deletes it and the ephemeral node
      # deregisters (§4.4).
      - tailscale_state:/var/lib/tailscale
      - tailscale_sock:/var/run/tailscale
    devices:
      - /dev/net/tun:/dev/net/tun
    cap_add: [NET_ADMIN, NET_RAW]
    restart: unless-stopped
"""

_CADDY_COMMENT = """\
  # Production's Caddy is network_mode: host and reads the HOST's tailscaled
  # socket. A branch's Caddy joins the sidecar's netns instead, so it binds
  # :443 on the BRANCH's tailnet address and issues the BRANCH's certificate.
  #
  # Consequence, and the reason branch-env.yaml exists: 127.0.0.1 in that
  # netns reaches nothing of this stack. Every upstream must be a Docker
  # service name (AGENT_UPSTREAM_MODE=service and the *_UPSTREAM variables),
  # which survives because TS_ACCEPT_DNS=false keeps 127.0.0.11 in resolv.conf.
"""


class OverlayError(RuntimeError):
    """The overlay cannot be rendered from the configuration it was given."""


# ------------------------------------------------------------ tagged YAML


@dataclass(frozen=True)
class Tagged:
    """A YAML node carrying an explicit tag, e.g. `!reset null`.

    Kept as a value rather than collapsed to the underlying scalar because the
    TAG is the whole point: `ports: !reset []` removes the inherited list and
    `ports: []` silently merges with it. A loader that dropped the tag would
    read both as an empty list and could not tell the working overlay from the
    broken one.
    """

    tag: str
    value: object = None


class OverlayLoader(yaml.SafeLoader):
    """SafeLoader that keeps `!`-tags and refuses duplicate mapping keys."""


def _construct_tagged(loader, tag_suffix, node):
    if isinstance(node, yaml.MappingNode):
        value = loader.construct_mapping(node, deep=True)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_scalar(node)
        if value == "null" or value == "":
            value = None
    return Tagged("!" + tag_suffix, value)


def _construct_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            # A duplicate key in YAML is silently last-wins, which would let a
            # generated `caddy:` block quietly discard the hand-written one.
            raise OverlayError(f"duplicate key {key!r} in the overlay")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


OverlayLoader.add_multi_constructor("!", _construct_tagged)
OverlayLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def load_overlay(text: str) -> dict:
    """Parse an overlay, keeping `!reset` / `!override` tags as `Tagged`."""
    return yaml.load(text, Loader=OverlayLoader) or {}


def overlay_resets(text: str) -> dict[str, dict[str, str | None]]:
    """service -> {key: tag or None} for every resettable key the overlay declares.

    `None` means the key is present but UNTAGGED, which is the dangerous case:
    it looks like a reset in a diff and does nothing at all.

    Covers CONDITIONAL_RESET_KEYS as well as RESET_KEYS. A reader that knew
    only about the unconditional ones would report "no reset" for a key the
    generator had just written, so the gate built on it could never go green
    -- which is exactly what happened when `image` was added here.
    """
    doc = load_overlay(text)
    services = doc.get("services") or {}
    out: dict[str, dict[str, str | None]] = {}
    for name, body in services.items():
        if not isinstance(body, dict):
            continue
        found = {}
        for key in RESET_KEYS + CONDITIONAL_RESET_KEYS:
            if key in body:
                value = body[key]
                found[key] = value.tag if isinstance(value, Tagged) else None
        if found:
            out[name] = found
    return out


# -------------------------------------------------------- resolved config


def resolve_config(
    root: Path | None = None,
    *,
    files: tuple[str, ...] = (BASE_COMPOSE_NAME,),
    profiles: str = "*",
    env: dict[str, str] | None = None,
) -> dict:
    """`docker compose config --format json`, fully resolved.

    COMPOSE_PROFILES="*" is not optional: a service carrying `profiles:` is
    omitted from the output unless its profile is active, so without it every
    per-developer agent — the services whose enumeration this module exists to
    keep honest — would read as nonexistent and the overlay would be rendered
    from a config that cannot see them.
    """
    root = Path(root) if root is not None else identity.package_root()
    environ = dict(os.environ)
    environ["COMPOSE_PROFILES"] = profiles
    if env:
        environ.update(env)

    cmd = ["docker", "compose"]
    for name in files:
        cmd += ["-f", name]
    cmd += ["config", "--format", "json"]

    result = subprocess.run(
        cmd, cwd=root, capture_output=True, text=True, env=environ,
    )
    if result.returncode != 0:
        raise OverlayError(
            f"`{' '.join(cmd)}` failed in {root}: {result.stderr.strip()}"
        )
    return json.loads(result.stdout)


def reset_targets(config: dict) -> dict[str, tuple[str, ...]]:
    """service -> the keys it declares that a branch must reset.

    Truthiness, not presence: `docker compose config` emits neither key when a
    service does not declare it, but a service with an EMPTY ports list needs
    no reset and an entry for it would be noise the next reader has to explain.

    `CONDITIONAL_RESET_KEYS` are included only where `conditionally_resettable`
    says the service survives losing them -- see its note on `image`.
    """
    services = config.get("services") or {}
    if not services:
        raise OverlayError(
            "the resolved compose configuration declares no services — refusing "
            "to render an overlay that would be vacuously correct. Check that "
            "`docker compose config` runs in the repo root and that "
            'COMPOSE_PROFILES="*" is set.'
        )
    targets: dict[str, tuple[str, ...]] = {}
    for name in sorted(services):
        body = services[name] or {}
        keys = tuple(key for key in RESET_KEYS if body.get(key))
        keys += tuple(
            key for key in CONDITIONAL_RESET_KEYS
            if body.get(key) and conditionally_resettable(key, body)
        )
        if keys:
            targets[name] = keys
    return targets


# ------------------------------------------------------------- rendering


def _short_volume(entry: dict, root: Path) -> str:
    """Render one resolved volume entry back to its short `src:dst[:ro]` form.

    Bind sources come back from Compose as absolute host paths, and on this
    host `/home` is a symlink to `/var/home` — so both sides are `.resolve()`d
    before they are compared or subtracted. A string prefix test here would
    silently never match and every bind would be emitted as an absolute path.
    """
    target = entry.get("target", "")
    suffix = ":ro" if entry.get("read_only") else ""
    source = entry.get("source", "")
    if entry.get("type") == "bind":
        resolved = Path(source).resolve()
        root = Path(root).resolve()
        if root == resolved or root in resolved.parents:
            return f"./{resolved.relative_to(root)}:{target}{suffix}"
        return f"{source}:{target}{suffix}"
    return f"{source}:{target}{suffix}"


def caddy_branch_volumes(config: dict, root: Path) -> list[str]:
    """Caddy's volume list with the HOST tailscaled socket swapped for the
    sidecar's.

    Derived from the resolved config rather than copied out of it, so that a
    volume added to Caddy in compose.yml is not silently dropped by an
    `!override` list nobody updated. `!override` replaces the list wholesale,
    which makes a stale copy of it invisible: the branch would simply not have
    the mount, with no error anywhere.

    Read-only is proven sufficient for certificate issuance — production
    mounts the host socket `:ro` and its HTTPS works.
    """
    caddy = (config.get("services") or {}).get(CADDY_SERVICE)
    if caddy is None:
        raise OverlayError(
            f"the resolved config has no {CADDY_SERVICE!r} service; the branch "
            "overlay cannot flip it into the sidecar's network namespace"
        )
    host_socket = Path(TAILSCALE_SOCKET_DIR).resolve()
    sidecar = f"{SOCK_VOLUME}:{TAILSCALE_SOCKET_DIR}:ro"

    rendered: list[str] = []
    swapped = False
    for entry in caddy.get("volumes") or []:
        if (
            entry.get("type") == "bind"
            and Path(entry.get("source", "")).resolve() == host_socket
        ):
            rendered.append(sidecar)
            swapped = True
            continue
        rendered.append(_short_volume(entry, root))
    if not swapped:
        rendered.append(sidecar)
    return rendered


#: Where the branch resource ceilings live, and how to choose one.
#: A data file rather than constants: an operator tuning a ceiling should not
#: be editing Python, and the reasons (arcadedb's -Xmx2g) belong beside the
#: numbers they constrain.
LIMITS_FILE = "branch-limits.yaml"
LIMITS_ENV_VAR = "AURORA_BRANCH_LIMITS"

#: The one profile name that is not in the file: it means "no ceilings".
#: Spelled out rather than implied by an empty profile, because an unlimited
#: branch is a decision and is recorded in the access document as one.
LIMITS_NONE = "none"

#: Emitted in this order so a diff of two overlays lines up.
LIMIT_KEYS = ("mem_limit", "pids_limit", "cpus")


def limits_path(root: Path | None = None) -> Path:
    """The profiles file for `root`, falling back to this checkout's own.

    A branch worktree carries its own tracked copy, so a branch can tune its
    ceilings. A caller rendering an overlay for some OTHER root -- a test with
    a synthetic config, a probe against a fabricated tree -- has no reason to
    own one, and demanding it there turned rendering into a FileNotFoundError
    for seven tests that never asked about limits. Fall back rather than
    refuse; raise only when neither exists, naming both paths.
    """
    here = identity.package_root() / LIMITS_FILE
    if root is None:
        return here
    candidate = Path(root) / LIMITS_FILE
    if candidate.is_file() or not here.is_file():
        return candidate
    return here


def resolve_limits(
    profile: str | None = None, root: Path | None = None,
    *, environ: Mapping[str, str] | None = None,
) -> tuple[dict, dict]:
    """`(default ceiling, per-service overrides)` for `profile`.

    `none` returns empty mappings, which render no ceilings at all -- the mode
    that exists for benchmarking and for features whose whole point is to be
    resource-hungry.

    An unset `profile` falls back to `$AURORA_BRANCH_LIMITS` before the file's
    `default_profile`. The variable is half of what the spec offers as the way
    to choose a profile, and it was defined here and read nowhere until a
    measurement went looking for it (docs/measurements). The fallback is
    resolved BEFORE the `none` check so `AURORA_BRANCH_LIMITS=none` means what
    `--limits none` means.
    """
    environ = os.environ if environ is None else environ
    if profile is None:
        profile = environ.get(LIMITS_ENV_VAR) or None
    if profile == LIMITS_NONE:
        return {}, {}
    path = limits_path(root)
    if not path.is_file():
        raise OverlayError(
            f"no {LIMITS_FILE} at {path} and none in this checkout, so branch "
            f"resource ceilings cannot be resolved. Pass "
            f"limits={LIMITS_NONE!r} to render without any."
        )
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    profiles = document.get("profiles") or {}
    name = profile or document.get("default_profile")
    if name not in profiles:
        raise OverlayError(
            f"{name!r} is not a profile in {LIMITS_FILE} "
            f"(have: {', '.join(sorted(profiles)) or 'none'}, plus "
            f"{LIMITS_NONE!r} for no ceilings at all)."
        )
    body = profiles[name] or {}
    return dict(body.get("default") or {}), dict(body.get("services") or {})


def limits_for(service: str, default: dict, overrides: dict) -> dict:
    """The ceiling for one service: the profile default, then its override.

    Merged per KEY, not replaced wholesale: an override that raises only
    `mem_limit` must keep the profile's `pids_limit` rather than silently
    dropping it.
    """
    if not default and not overrides.get(service):
        return {}
    resolved = dict(default)
    resolved.update(overrides.get(service) or {})
    return {k: resolved[k] for k in LIMIT_KEYS if k in resolved}


def _limit_lines(ceiling: dict) -> list[str]:
    return [f"    {key}: {ceiling[key]}" for key in LIMIT_KEYS if key in ceiling]


def _reset_lines(keys: tuple[str, ...]) -> list[str]:
    return [f"    {key}: {RESET_VALUES[key]}" for key in keys]


def render_overlay(
    config: dict, root: Path | None = None, limits: str | None = None,
) -> str:
    """The full text of `compose.branch.yml` for one resolved configuration."""
    root = Path(root) if root is not None else identity.package_root()
    targets = reset_targets(config)
    default_ceiling, ceiling_overrides = resolve_limits(limits, root)
    services = config.get("services") or {}

    def ceiling(name: str) -> list[str]:
        return _limit_lines(limits_for(name, default_ceiling, ceiling_overrides))

    if SIDECAR_SERVICE in (config.get("services") or {}):
        raise OverlayError(
            f"the base configuration already declares a {SIDECAR_SERVICE!r} "
            "service; the overlay would merge into it instead of adding the "
            "branch's sidecar"
        )

    # The sidecar is added BY this overlay, so it is not in `services` and the
    # loop below never reaches it. Without this it would be the one service in
    # a branch with no ceiling -- and it is the one holding the tailnet
    # identity, so "every branch service is capped" has to be true of it too.
    lines: list[str] = [_HEADER, "services:", _SIDECAR_BLOCK.rstrip("\n")]
    lines.extend(ceiling(SIDECAR_SERVICE))
    lines.append("")

    # Caddy is emitted by hand because it is the one service that is
    # RECONFIGURED rather than merely un-namespaced. Its resets, if it ever
    # declares either key, are folded into the same block: two `caddy:` keys
    # in one mapping is last-wins in YAML and would silently drop this one.
    lines.append(_CADDY_COMMENT.rstrip("\n"))
    lines.append(f"  {CADDY_SERVICE}:")
    lines.append("    network_mode: service:tailscale")
    lines.append("    depends_on:")
    lines.append("      tailscale:")
    lines.append("        condition: service_started")
    lines.extend(_reset_lines(targets.get(CADDY_SERVICE, ())))
    lines.extend(ceiling(CADDY_SERVICE))
    lines.append("    volumes: !override")
    lines.extend(f"      - {v}" for v in caddy_branch_volumes(config, root))
    lines.append("")

    lines.append(_GENERATED_MARKER)
    for name in sorted(services):
        if name == CADDY_SERVICE:
            continue
        body = _reset_lines(targets.get(name, ())) + ceiling(name)
        if not body:
            continue
        lines.append(f"  {name}:")
        lines.extend(body)
    lines.append("")

    lines.append("volumes:")
    lines.append(f"  {STATE_VOLUME}:")
    lines.append(f"  {SOCK_VOLUME}:")
    return "\n".join(lines).rstrip("\n") + "\n"


# ---------------------------------------------------------------- on disk


def overlay_path(root: Path | None = None) -> Path:
    root = Path(root) if root is not None else identity.package_root()
    return root / OVERLAY_NAME


def render_from_disk(root: Path | None = None, limits: str | None = None) -> str:
    """Resolve the repo's compose configuration and render the overlay."""
    root = Path(root) if root is not None else identity.package_root()
    return render_overlay(resolve_config(root), root, limits=limits)


def sync_overlay(
    root: Path | None = None, *, check: bool = False, limits: str | None = None,
) -> tuple[Path, bool]:
    """Render the overlay for `root`, writing it unless `check`. -> (path, was_stale).

    One render, not two: `docker compose config` is a subprocess, and asking
    "is it stale?" and "make it fresh" separately paid for it twice.
    """
    path = overlay_path(root)
    fresh = render_from_disk(root, limits=limits)
    stale = (path.read_text() if path.exists() else "") != fresh
    if stale and not check:
        path.write_text(fresh)
    return path, stale
