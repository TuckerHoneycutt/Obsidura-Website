"""compose.branch.yml is the ONLY configuration difference between production
and a branch, and its enumeration must be self-checking (plan finding N3).

Every expectation here is derived from the RESOLVED compose configuration —
what Compose itself will act on — and never from the artifact under test. That
separation is the point. The generator reads the resolved config; if the
checker read the generator's output instead, deleting a service from one would
delete it from the other in the same stroke and the suite would stay green
while the branch was unable to start.

Why the two keys:

  * `container_name:` opts a service OUT of project namespacing. The name is
    daemon-global, so an unreset one means the branch's container collides with
    production's and the stack does not come up.
  * `ports:` publishes on the HOST. An unreset one means the branch tries to
    bind a port production is already serving on — and if it wins the race, it
    has taken production's port.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from conftest import REPO_ROOT, compose_config, is_tracked

from aurora_cli import branch, envfile, overlay

BRANCH_ENV = {
    "COMPOSE_PROJECT_NAME": "br-probe",
    "TS_HOSTNAME": "aurora-probe",
    "TS_AUTHKEY": "tskey-fake",
}

#: Anything a Caddy inside the sidecar's network namespace cannot reach. There
#: is no loopback port of this stack in that namespace, so a variable that
#: DEFAULTS to one of these must be overridden by the branch .env or the route
#: 502s while looking perfectly healthy.
LOOPBACK_MARKERS = ("127.0.0.1", "localhost", "[::1]")


def overlay_text() -> str:
    return overlay.overlay_path(REPO_ROOT).read_text()


def declaring(config: dict, key: str) -> set[str]:
    return {
        name for name, body in (config.get("services") or {}).items()
        if (body or {}).get(key)
    }


def overlaid_config() -> dict:
    """The branch's real configuration: base + overlay, every profile active."""
    return overlay.resolve_config(
        REPO_ROOT,
        files=(overlay.BASE_COMPOSE_NAME, overlay.OVERLAY_NAME),
        env=BRANCH_ENV,
    )


# ------------------------------------------------------------- the artifact


def test_the_overlay_is_committed_not_gitignored():
    """Trap 4: `docker compose -f` is a hard error on a missing file, and a
    fresh worktree has only what git tracks. Same reason compose.agents.yml is
    committed."""
    path = overlay.overlay_path(REPO_ROOT)

    assert path.exists(), f"{path} is generated but missing — regenerate it"
    assert is_tracked(path), (
        f"{path.name} is generated but NOT tracked. Compose fails hard on a "
        "missing -f file, so a fresh worktree could not even resolve its "
        "configuration, let alone start a branch."
    )


def test_overlay_is_not_stale(config):
    """Bytes, not semantics — the same shape as
    test_agents_compose_matches_developers_yaml. The per-developer agent
    services come from developers.yaml, so this is what goes red when a
    developer is added and the overlay is not regenerated."""
    expected = overlay.render_overlay(config, REPO_ROOT)

    assert overlay_text() == expected, (
        "compose.branch.yml is stale relative to the resolved compose "
        "configuration — run `python -m dev_administration.cli "
        "render-branch-override` and commit the result"
    )


# ------------------------------------------------------------ the coverage


def test_every_container_name_declaration_is_reset(config):
    named = declaring(config, "container_name")
    assert named, (
        "no service in the resolved configuration declares container_name, "
        'which cannot be true for this stack — is COMPOSE_PROFILES="*" set?'
    )

    resets = overlay.overlay_resets(overlay_text())
    missing = sorted(
        name for name in named
        if resets.get(name, {}).get("container_name") != "!reset"
    )

    assert missing == [], (
        f"compose.branch.yml does not reset container_name for {missing}. "
        "container_name is DAEMON-GLOBAL — it opts the service out of project "
        "namespacing — so a branch carrying production's name cannot start at "
        "all. Regenerate the overlay."
    )


def test_every_published_port_is_reset(config):
    publishing = declaring(config, "ports")
    assert publishing, (
        "no service in the resolved configuration publishes a port, which "
        'cannot be true for this stack — is COMPOSE_PROFILES="*" set?'
    )
    # The case a container_name-only gate misses: services that publish a host
    # port and declare no container_name at all.
    assert publishing - declaring(config, "container_name"), (
        "every publishing service also declares container_name, so this gate "
        "can no longer be distinguished from the container_name one — check "
        "the resolved configuration before weakening it"
    )

    resets = overlay.overlay_resets(overlay_text())
    missing = sorted(
        name for name in publishing
        if resets.get(name, {}).get("ports") != "!reset"
    )

    assert missing == [], (
        f"compose.branch.yml does not reset ports for {missing}. A branch that "
        "keeps a published port tries to bind a host port production is "
        "already serving on. Note `ports: []` is NOT enough: Compose merges an "
        "untagged empty list with the inherited one. Regenerate the overlay."
    )


def test_every_shared_image_tag_is_reset(config):
    """An explicit `image:` is daemon-global, exactly like `container_name`.

    Two projects that name the same tag share one image. `agent-authz:local`
    and `dev-admin:local` were declared that way, so building them in a branch
    replaced what production would run on its next recreate — measured on this
    host on 2026-07-31, when `br-ownersbind` rebuilt both an hour after
    production deployed. Nothing failed and nothing warned; the branch simply
    took the tag. `fjell` was never affected because it declares `build:` with
    no tag and Compose therefore derives `<project>-fjell` for it already,
    which is what the reset restores for the other two.

    Only services that ALSO declare `build:` are in scope: resetting the tag on
    a pull-only service would leave Compose with neither an image nor a way to
    make one.
    """
    services = config.get("services") or {}
    shared = {
        name for name, body in services.items()
        if (body or {}).get("image") and (body or {}).get("build")
    }
    assert shared, (
        "no service in the resolved configuration declares BOTH an explicit "
        "image tag and a build context, which cannot be true for this stack — "
        'is COMPOSE_PROFILES="*" set?'
    )
    # The case a container_name-only gate misses, stated as the ports gate
    # states its own: an image tag is shared even when the container name is
    # already namespaced.
    assert shared - declaring(config, "container_name"), (
        "every service with a shared image tag also declares container_name, "
        "so this gate can no longer be distinguished from that one — check "
        "the resolved configuration before weakening it"
    )

    resets = overlay.overlay_resets(overlay_text())
    missing = sorted(
        name for name in shared
        if resets.get(name, {}).get("image") != "!reset"
    )

    assert missing == [], (
        f"compose.branch.yml does not reset image for {missing}. An explicit "
        "image tag is DAEMON-GLOBAL: a branch that keeps production's tag "
        "overwrites production's image when it builds. Regenerate the overlay."
    )


def test_the_overlaid_config_declares_no_container_name_and_no_ports():
    """The empirical gate — the one a bookkeeping error cannot satisfy. It
    asks Compose itself what a branch resolves to."""
    services = overlaid_config().get("services") or {}

    assert len(services) > 1, (
        f"the overlaid configuration resolved to {sorted(services)}, which is "
        "too few to be this stack — an empty or truncated parse would pass "
        "every assertion below vacuously"
    )
    assert overlay.SIDECAR_SERVICE in services, (
        "the overlay did not contribute its sidecar, so the overlay was "
        "probably not applied at all"
    )

    named = sorted(n for n, s in services.items() if (s or {}).get("container_name"))
    publishing = sorted(n for n, s in services.items() if (s or {}).get("ports"))

    assert named == [], (
        f"a branch would still declare daemon-global container names: {named}"
    )
    assert publishing == [], (
        f"a branch would still publish host ports: {publishing}"
    )


# ---------------------------------------------------------------- the flip


def test_caddy_is_flipped_into_the_sidecar_netns():
    caddy = (overlaid_config().get("services") or {})[overlay.CADDY_SERVICE]

    assert caddy.get("network_mode") == f"service:{overlay.SIDECAR_SERVICE}", (
        "a branch's Caddy must share the sidecar's network namespace, or it "
        "binds :443 on the HOST and collides with production"
    )

    sources = {v.get("source") for v in caddy.get("volumes") or []}
    assert overlay.SOCK_VOLUME in sources, (
        "Caddy has no tailscaled socket, so it can obtain no certificate"
    )
    assert "/var/run/tailscale" not in sources, (
        "Caddy still binds the HOST's tailscaled socket, so a branch would ask "
        "PRODUCTION's tailscaled for a certificate for the branch's hostname"
    )
    # `volumes: !override` replaces the list wholesale, so the mounts that are
    # not being swapped have to survive the replacement.
    targets = {v.get("target") for v in caddy.get("volumes") or []}
    assert {"/etc/caddy/Caddyfile", "/etc/caddy/Caddyfile.d", "/data", "/config"} <= targets, (
        f"the !override list dropped a Caddy mount: {sorted(targets)}"
    )


def test_no_service_in_a_branch_binds_the_hosts_tailscaled_socket():
    """Stated over every service rather than over Caddy, so a future service
    that reaches for the host socket is caught by the gate that already
    exists."""
    offenders = sorted(
        name for name, body in (overlaid_config().get("services") or {}).items()
        for v in (body or {}).get("volumes") or []
        if v.get("type") == "bind" and v.get("source") == "/var/run/tailscale"
    )

    assert offenders == [], (
        f"{offenders} bind the host's tailscaled socket; a branch must use its "
        "own sidecar's socket volume"
    )


# -------------------------------------------------------------- the sidecar


def test_the_sidecar_runs_in_kernel_mode_and_does_not_accept_magicdns():
    sidecar = (overlaid_config().get("services") or {})[overlay.SIDECAR_SERVICE]
    env = sidecar.get("environment") or {}

    assert env.get("TS_USERSPACE") == "false", (
        "userspace mode puts no tailscale0 in the shared namespace, so Caddy's "
        "bind on :443 receives no tailnet traffic"
    )
    assert env.get("TS_ACCEPT_DNS") == "false", (
        "accepting MagicDNS rewrites resolv.conf in the SHARED namespace to "
        "100.100.100.100 and removes Docker's 127.0.0.11 — every *_UPSTREAM in "
        "a branch is a Docker service name"
    )
    devices = {
        (d.get("source"), d.get("target")) for d in sidecar.get("devices") or []
    }
    assert ("/dev/net/tun", "/dev/net/tun") in devices, (
        f"kernel mode needs /dev/net/tun; got {sorted(devices)}"
    )
    assert {"NET_ADMIN", "NET_RAW"} <= set(sidecar.get("cap_add") or [])


def test_the_sidecar_state_survives_a_restart_and_dies_with_the_project():
    sidecar = (overlaid_config().get("services") or {})[overlay.SIDECAR_SERVICE]
    env = sidecar.get("environment") or {}
    state = [
        v for v in sidecar.get("volumes") or []
        if v.get("target") == env.get("TS_STATE_DIR")
    ]

    assert env.get("TS_STATE_DIR"), "the sidecar declares no state directory"
    assert len(state) == 1, (
        f"the sidecar's state directory {env.get('TS_STATE_DIR')!r} is not "
        "mounted; in-memory state re-registers the node on every restart"
    )
    assert state[0].get("type") == "volume", (
        "the sidecar's state must be a project-scoped NAMED volume: a bind "
        "would survive `down -v` and the ephemeral node would not deregister"
    )
    assert state[0].get("source") in (overlaid_config().get("volumes") or {}), (
        "the state volume is not declared at the top level, so it is not "
        "project-scoped and `down -v` would not remove it"
    )


def test_a_branch_without_an_authkey_is_a_config_error(monkeypatch):
    """Trap 9: a tailscaled with no key does NOT fail. It starts, stays
    `Logged out.` and serves a dead URL. `${TS_AUTHKEY:?…}` is what turns that
    into a loud failure before anything is started."""
    monkeypatch.delenv("TS_AUTHKEY", raising=False)
    env = {k: v for k, v in BRANCH_ENV.items() if k != "TS_AUTHKEY"}

    with pytest.raises(overlay.OverlayError) as excinfo:
        overlay.resolve_config(
            REPO_ROOT,
            files=(overlay.BASE_COMPOSE_NAME, overlay.OVERLAY_NAME),
            env=env,
        )

    message = str(excinfo.value)
    # On the message, not the type: TS_HOSTNAME carries the same `:?` guard and
    # `docker compose config` fails for a dozen other reasons, so a bare
    # `raises` would be satisfied by a mutant that removed this guard entirely.
    assert "TS_AUTHKEY" in message, message
    assert "TS_HOSTNAME" not in message, (
        "the failure is about the wrong variable — TS_HOSTNAME was supplied"
    )


# --------------------------------------------- agreement with Task 2's .env


def caddyfile_upstream_placeholders() -> set[str]:
    text = (REPO_ROOT / "Caddyfile").read_text()
    return {
        name for name in re.findall(r"\{\$([A-Za-z_][A-Za-z0-9_]*)", text)
        if name.endswith("_UPSTREAM")
    }


def test_the_overlay_and_the_branch_env_manifest_agree_on_the_upstreams(config):
    """The netns flip and the branch .env are two halves of one mechanism.

    Caddy in a branch resolves `{$X_UPSTREAM}` inside the sidecar's namespace,
    where the production defaults — loopback addresses — reach nothing. Chunk 2
    built the placeholders; Task 2's manifest sets them. Neither artifact is
    checked against the other anywhere else, so a placeholder added to the
    Caddyfile without a manifest entry would produce a branch that starts,
    serves 502s and looks fine.
    """
    placeholders = caddyfile_upstream_placeholders()
    assert len(placeholders) >= 3, (
        f"only {sorted(placeholders)} upstream placeholders found in the "
        "Caddyfile — the scan is probably reading the wrong syntax"
    )

    listed = {req.name for req in envfile.load_manifest()}
    assert placeholders <= listed, (
        f"{sorted(placeholders - listed)} are Caddyfile upstreams with no entry "
        "in branch-env.yaml. They default to production's loopback addresses, "
        "so a branch inherits an upstream that does not exist in the sidecar's "
        "network namespace: the stack starts and every route 502s."
    )

    caddy_env = ((config.get("services") or {})[overlay.CADDY_SERVICE]
                 .get("environment") or {})
    assert placeholders <= set(caddy_env), (
        f"{sorted(placeholders - set(caddy_env))} are read by the Caddyfile but "
        "never passed into the caddy service, so the branch .env cannot reach "
        "them at all"
    )


def test_every_loopback_default_caddy_reads_is_overridden_by_the_branch_env(config):
    """The drift-proof direction of the same rule: anything Caddy is given that
    RESOLVES to loopback must be listed in branch-env.yaml, whatever it is
    called."""
    caddy_env = ((config.get("services") or {})[overlay.CADDY_SERVICE]
                 .get("environment") or {})
    loopback = {
        key for key, value in caddy_env.items()
        if isinstance(value, str) and any(m in value for m in LOOPBACK_MARKERS)
    }
    assert loopback, (
        "no loopback-valued variable reached caddy, which cannot be true while "
        "production is host-networked — the scan is reading the wrong place"
    )

    listed = {req.name for req in envfile.load_manifest()}
    assert loopback <= listed, (
        f"{sorted(loopback - listed)} reach Caddy with a loopback value and are "
        "not overridden by branch-env.yaml. In the sidecar's network namespace "
        "127.0.0.1 reaches nothing of this stack."
    )


def test_the_agent_upstream_mode_is_switched_for_a_branch(config):
    """`AGENT_UPSTREAM_MODE=published` makes dev-admin generate per-agent Caddy
    routes pointing at 127.0.0.1 ports, which is the same 502 by another
    route — one the Caddyfile scan above cannot see, because those routes are
    generated into Caddyfile.d at reconcile time."""
    requirements = {req.name: req for req in envfile.load_manifest()}
    dev_admin_env = ((config.get("services") or {})["dev-admin"]
                     .get("environment") or {})

    assert dev_admin_env.get("AGENT_UPSTREAM_MODE") == "published", (
        "production's resolved mode is no longer `published`; if the default "
        "changed, this gate and branch-env.yaml both need rereading"
    )
    assert "AGENT_UPSTREAM_MODE" in requirements, (
        "AGENT_UPSTREAM_MODE is not in branch-env.yaml, so a branch inherits "
        "`published` and every per-agent route points at a loopback port that "
        "does not exist in the sidecar's namespace"
    )
    assert requirements["AGENT_UPSTREAM_MODE"].literal == "service"


# ----------------------------------------------------------- the generator


def test_the_render_command_ignores_an_ambient_profile_selection(tmp_path, monkeypatch):
    """A service carrying `profiles:` is omitted from `docker compose config`
    unless its profile is active. Rendering under whatever COMPOSE_PROFILES the
    invoking shell happened to export would therefore drop every per-developer
    agent from the enumeration — and those are precisely the services whose
    `container_name` is generated and therefore most likely to be forgotten."""
    from typer.testing import CliRunner

    from dev_administration import cli

    monkeypatch.setenv("COMPOSE_PROFILES", "nothing-matches-this")
    out = tmp_path / "compose.branch.yml"

    result = CliRunner().invoke(
        cli.app, ["render-branch-override", "--output", str(out)]
    )

    assert result.exit_code == 0, result.output
    assert out.read_text() == overlay_text(), (
        "render-branch-override honoured the ambient COMPOSE_PROFILES; the "
        "committed overlay is no longer a pure function of the repository"
    )


def test_the_render_command_check_mode_reports_a_stale_file(tmp_path):
    from typer.testing import CliRunner

    from dev_administration import cli

    stale = tmp_path / "compose.branch.yml"
    stale.write_text("services: {}\n")

    result = CliRunner().invoke(
        cli.app, ["render-branch-override", "--check", "--output", str(stale)]
    )

    assert result.exit_code == 1
    assert "stale" in result.output
    assert stale.read_text() == "services: {}\n", (
        "--check rewrote the file it was asked only to inspect"
    )


# ---------------------------------------------------------------------------
# the enumeration gate (P1) -- 2026-08-01
# ---------------------------------------------------------------------------


def test_no_daemon_global_key_escapes_unaccounted():
    """The generalisation of the image-tag gate, and the point of P1.

    OVER THE OVERLAID CONFIG, not the base one. This gate used to take the
    `config` fixture -- `docker compose config` over `compose.yml` alone --
    which is production's configuration and not the branch's. Spec 2 lists
    that as mutation M4 ("point the gate at production's config instead of the
    branch's -> red"), so the gate shipped as its own mutant, green. Measured
    on this host, same code, both inputs:

        gate on BASE     : {}
        gate on OVERLAID : {'tailscale': ('cap_add', 'devices', 'hostname')}

    The `tailscale` sidecar is added BY the overlay, so it is never in the
    base config's `services` -- and it is the one service that exists ONLY in
    a branch, holds the branch's tailnet identity, and declares /dev/net/tun
    and NET_ADMIN/NET_RAW. `test_every_branch_service_gets_a_ceiling` handles
    that same asymmetry explicitly ("the sidecar by name"); this did not.
    Its three declarations now carry written exemptions.

    Compose namespaces four things: containers, volumes, networks and the
    project label. EVERYTHING else a service declares is shared with
    production. Gating one key at a time means the next unenumerated key
    escapes silently, which is exactly how an explicit `image:` crossed the
    boundary until 2026-07-31 and how three `/var/run/docker.sock` binds did
    until 2026-08-01.

    So the rule is inverted: every daemon-global key a service actually
    escapes with must be RESET in the overlay or carry a written exemption.
    Adding a service with a new global attribute fails here rather than
    sharing quietly.
    """
    config = overlaid_config()
    root = overlay.identity.package_root()
    resets = overlay.overlay_resets(overlay_text())

    # The input is the branch's, and that is asserted rather than assumed: if
    # the sidecar is not in this config then this is the base config again and
    # the whole gate is pointed at the wrong stack.
    assert overlay.SIDECAR_SERVICE in (config.get("services") or {}), (
        "the resolved configuration has no sidecar, so this is production's "
        "config and not the branch's -- which is mutation M4"
    )

    # Non-vacuity, first: a gate over an empty inventory passes on nothing.
    assert overlay.DAEMON_GLOBAL_KEYS, "the daemon-global inventory is empty"
    escaping = {
        key for key in overlay.DAEMON_GLOBAL_KEYS
        for body in (config.get("services") or {}).values()
        if overlay.reaches_outside(key, body or {}, root)
    }
    assert escaping, (
        "no service in the resolved configuration escapes with ANY "
        "daemon-global key, which cannot be true for this stack -- is "
        'COMPOSE_PROFILES="*" set?'
    )

    unguarded = overlay.unguarded_globals(config, resets, root)
    assert unguarded == {}, (
        f"these declarations are shared with production and nothing accounts "
        f"for them: {unguarded}. Either reset the key in compose.branch.yml, "
        f"or add (service, key) to overlay.GLOBAL_EXEMPTIONS with a reason "
        f"saying why sharing it is safe. An exemption is a decision; silence "
        f"is not."
    )


def test_the_gate_catches_a_key_nobody_enumerated(tmp_path):
    """The control. Without it the gate above passes by finding nothing.

    A service carrying a global key that is neither reset nor exempted must be
    reported, and reported BY NAME -- a gate that says "something is wrong"
    sends the next reader looking.
    """
    root = tmp_path
    fabricated = {"services": {
        "newcomer": {"privileged": True, "image": "x:latest"},
        "innocent": {"image": "y:latest"},
    }}
    unguarded = overlay.unguarded_globals(fabricated, {}, root)
    assert unguarded == {"newcomer": ("privileged",)}, unguarded

    # ...and an exemption with a reason silences exactly that one.
    overlay.GLOBAL_EXEMPTIONS[("newcomer", "privileged")] = "fabricated, for this test"
    try:
        assert overlay.unguarded_globals(fabricated, {}, root) == {}
    finally:
        del overlay.GLOBAL_EXEMPTIONS[("newcomer", "privileged")]


def test_an_exemption_without_a_reason_is_not_an_exemption(tmp_path):
    """An empty reason must not silence the gate.

    The failure this prevents is an exemption added to make a red test green,
    with the justification left for later and never written.
    """
    fabricated = {"services": {"newcomer": {"privileged": True}}}
    overlay.GLOBAL_EXEMPTIONS[("newcomer", "privileged")] = "   "
    try:
        assert overlay.unguarded_globals(fabricated, {}, tmp_path) == {
            "newcomer": ("privileged",)
        }
    finally:
        del overlay.GLOBAL_EXEMPTIONS[("newcomer", "privileged")]


def test_every_shipped_exemption_states_a_reason():
    """Every exemption in the module, not just the ones a test happens to hit."""
    assert overlay.GLOBAL_EXEMPTIONS, "no exemptions declared -- is the dict wired up?"
    blank = sorted(k for k, why in overlay.GLOBAL_EXEMPTIONS.items() if not why.strip())
    assert blank == [], f"exemptions with no stated reason: {blank}"


def test_every_exemption_names_a_key_the_gate_actually_checks():
    """An exemption for an unenumerated key silences nothing and reads as if
    it does.

    `("hermes", "group_add")` shipped with a paragraph of reasoning while
    `group_add` was not in `DAEMON_GLOBAL_KEYS` -- and `unguarded_globals`
    iterates the inventory, so that entry was dead code. Its deadness was
    direct evidence that the key was ungated, in the one file whose argument
    is that an unenumerated item is how the image-tag escape happened.
    `test_every_shipped_exemption_states_a_reason` checks only that reasons
    are non-empty, so it could not see this.
    """
    stray = sorted(
        k for k in overlay.GLOBAL_EXEMPTIONS
        if k[1] not in overlay.DAEMON_GLOBAL_KEYS
    )
    assert stray == [], (
        f"exemptions for keys the gate never consults: {stray}. Either add "
        "the key to DAEMON_GLOBAL_KEYS with a reason, or delete the exemption "
        "-- an exemption that silences nothing is worse than none, because it "
        "reads as a decision that was made."
    )


def test_the_gate_catches_every_key_the_measurements_named(tmp_path):
    """The proof for the six keys added on 2026-08-01, one fabricated service
    each.

    These are not tidying. `runtime.py`'s own module docstring states, FROM
    MEASUREMENT, that "only `--security-opt label=disable` AND `--group-add
    keep-groups` together" let a rootless container reach production's docker
    socket -- so the two keys this branch itself identifies as the entire
    escape route were the two the gate did not check. `cgroup_parent` moves a
    service out of the project's cgroup subtree and therefore defeats the P2
    ceilings wholesale; `volumes_from` names a CONTAINER, which no project
    namespaces.

    Fabricated services rather than the real config, deliberately: the claim
    is about the GATE, and a key no service happens to declare today would
    make a test over the real config pass while proving nothing.
    """
    fabricated = {
        "buildkit": {"security_opt": ["label=disable"], "group_add": ["docker"]},
        "sidecar2": {"volumes_from": ["aurora-forgejo"]},
        "runner": {"cgroup_parent": "/system.slice", "sysctls": {"net.ipv4.ip_forward": 1},
                   "uts": "host"},
    }
    unguarded = overlay.unguarded_globals({"services": fabricated}, {}, tmp_path)
    assert unguarded == {
        "buildkit": ("group_add", "security_opt"),
        "runner": ("cgroup_parent", "sysctls", "uts"),
        "sidecar2": ("volumes_from",),
    }, unguarded


def test_uts_is_only_an_escape_when_it_is_host():
    """`uts: host` shares the host UTS namespace. Any other value does not, so
    a gate that fired on presence alone would be over-strict in a way that
    teaches people to add exemptions for things that are fine -- which dilutes
    the exemption list from "decisions we made" into "things we could not
    express"."""
    assert overlay.reaches_outside("uts", {"uts": "host"}, REPO_ROOT) is True
    assert overlay.reaches_outside("uts", {"uts": "private"}, REPO_ROOT) is False


def test_the_sidecar_the_overlay_adds_is_gated_too():
    """It is not in the base config, so a gate over that config never reached
    it -- and it holds NET_ADMIN, NET_RAW and /dev/net/tun. Driven from the
    overlay's own sidecar block rather than from the resolved config, so this
    stays true even if the gate above is ever repointed."""
    sidecar = overlay.load_overlay(
        overlay_text())["services"][overlay.SIDECAR_SERVICE]
    root = overlay.identity.package_root()

    # It really does declare the keys in question -- otherwise the assertion
    # below passes on a service that escapes with nothing.
    escaping = tuple(
        key for key in sorted(overlay.DAEMON_GLOBAL_KEYS)
        if overlay.reaches_outside(key, sidecar, root)
    )
    assert set(escaping) >= {"cap_add", "devices"}, escaping

    loose = overlay.unguarded_globals(
        {"services": {overlay.SIDECAR_SERVICE: sidecar}}, {}, root)
    assert loose == {}, (
        f"the branch's own sidecar escapes with {loose} and nothing accounts "
        "for it. Every entry needs a written exemption in "
        "overlay.GLOBAL_EXEMPTIONS."
    )


def test_a_repo_relative_bind_is_not_an_escape(tmp_path):
    """`/home` is a symlink to `/var/home` here and compose reports the resolved
    form, so a prefix comparison against an unresolved root marks every
    branch-private bind as external. This gate was drafted with that bug and
    reported all eleven services as unguarded."""
    inside = tmp_path / "affine" / "data"
    inside.mkdir(parents=True)
    body = {"volumes": [
        {"type": "bind", "source": str(inside), "target": "/data"},
        {"type": "bind", "source": "/var/run/docker.sock", "target": "/sock"},
    ]}
    assert overlay.host_bind_sources(body, tmp_path) == ("/var/run/docker.sock",)


# ---------------------------------------------------------------------------
# resource ceilings (P2) -- 2026-08-01
# ---------------------------------------------------------------------------


def _rendered(config, profile):
    return overlay.render_overlay(config, overlay.identity.package_root(), limits=profile)


def test_every_branch_service_gets_a_ceiling(config):
    """A branch with one unlimited service can still take the host down, and
    the host is what production runs on.

    Parsed from the overlay per SERVICE, not counted. The first version of
    this test counted `mem_limit:` lines and asserted the count was at least
    the number of base services -- which the sidecar's removal still
    satisfied, because the sidecar is one MORE than that number. A count is
    not evidence about a particular service.
    """
    parsed = overlay.load_overlay(_rendered(config, "measured"))
    services = parsed.get("services") or {}
    assert len(services) > 5, f"only {len(services)} services rendered"

    uncapped = sorted(n for n, b in services.items() if "mem_limit" not in (b or {}))
    assert uncapped == [], f"these branch services have no memory ceiling: {uncapped}"

    # The sidecar by name: it is added BY the overlay rather than read from the
    # base configuration, so it is the one service a loop over `services` in
    # the resolved config misses -- and it holds the tailnet identity.
    assert overlay.SIDECAR_SERVICE in services
    assert "mem_limit" in services[overlay.SIDECAR_SERVICE]
    assert "pids_limit" in services[overlay.SIDECAR_SERVICE]


def test_limits_none_means_none(config):
    """The mode that exists for benchmarking and deliberately heavy features.

    Asserted as ZERO, not "fewer": a profile that quietly still emitted some
    ceilings would make a benchmark measure the ceiling instead of the code.
    """
    text = _rendered(config, overlay.LIMITS_NONE)
    assert "mem_limit" not in text
    assert "pids_limit" not in text
    assert "cpus:" not in text
    # ...and the control: the same config WITH a profile does emit them, so
    # this is not passing because rendering is broken.
    assert "mem_limit" in _rendered(config, "measured")


def test_a_service_override_merges_with_the_default_rather_than_replacing_it():
    """An override that raises only `mem_limit` must keep the profile's
    `pids_limit`. Replacing wholesale would silently drop the fork-bomb guard
    from exactly the services someone bothered to tune."""
    merged = overlay.limits_for(
        "arcadedb",
        {"mem_limit": "1g", "pids_limit": 512, "cpus": "2.0"},
        {"arcadedb": {"mem_limit": "2560m"}},
    )
    assert merged == {"mem_limit": "2560m", "pids_limit": 512, "cpus": "2.0"}


def test_arcadedbs_ceiling_clears_the_heap_it_actually_declares(config):
    """Derived from compose.yml, never from a constant.

    arcadedb runs `-Xmx2g` and already has a recorded OOM kill (exit 137,
    docs/issues/arcadedb-oom.md). A ceiling at or below that heap is an OOM
    waiting for load. Reading the heap from the resolved configuration means
    lowering `mem_limit` OR raising `-Xmx` without the other reddens this.
    """
    env = (config["services"]["arcadedb"] or {}).get("environment") or {}
    java = env.get("JAVA_OPTS") if isinstance(env, dict) else None
    assert java and "-Xmx" in java, f"arcadedb declares no -Xmx to compare against: {java!r}"
    heap = java.split("-Xmx")[1].split()[0].lower()
    heap_bytes = int(heap.rstrip("gm")) * (1024**3 if heap.endswith("g") else 1024**2)

    default, overrides = overlay.resolve_limits("measured")
    ceiling = overlay.limits_for("arcadedb", default, overrides)["mem_limit"].lower()
    ceiling_bytes = int(ceiling.rstrip("gm")) * (1024**3 if ceiling.endswith("g") else 1024**2)

    assert ceiling_bytes > heap_bytes, (
        f"arcadedb's ceiling ({ceiling}) does not clear its own heap ({heap}); "
        "it will be OOM-killed under load. Raise the ceiling in "
        "branch-limits.yaml or lower -Xmx in compose.yml -- in one commit."
    )


def test_an_unknown_profile_is_refused_and_names_the_real_ones():
    """A typo must not silently fall back to unlimited."""
    with pytest.raises(overlay.OverlayError) as raised:
        overlay.resolve_limits("no-such-profile")
    message = str(raised.value)
    assert "no-such-profile" in message
    assert "measured" in message and overlay.LIMITS_NONE in message


# ---------------------------------------------------------------------------
# P2, part 2: does the ceiling actually ENFORCE? (2026-08-01)
# ---------------------------------------------------------------------------
#
# Spec 3 acceptance, verbatim: "Empirical, not declarative. A container is
# driven past its ceiling ... and must be OOM killed while production is
# measured unchanged throughout. `docker compose config` showing a `mem_limit`
# proves nothing -- cgroup enforcement is the claim."
#
# What P2 shipped was strictly LESS than what that sentence pre-rejects: the
# ceiling tests above parse the rendered overlay TEXT. So this section exists,
# and it is gated the way tests/test_podman_runtime.py gates its live tier --
# opt-in, with an unconditional test naming the variable, because a silent
# skip is how a Critical gate has already gone inert in this repository once.

LIMITS_LIVE_ENV = "AURORA_LIMITS_LIVE"
_LIMITS_LIVE_REASON = (
    f"the cgroup-enforcement tier is opt-in (${LIMITS_LIVE_ENV}=1). It creates "
    "and destroys ONE throwaway container in a br- project on the daemon. "
    "test_the_cgroup_enforcement_tier_is_opt_in_and_says_so runs "
    "unconditionally so this is never a silent omission."
)
limits_live = pytest.mark.skipif(
    os.environ.get(LIMITS_LIVE_ENV) != "1", reason=_LIMITS_LIVE_REASON
)

#: The throwaway project. `br-` prefixed so `ops/docker-guard` lets the
#: teardown through, and so nothing here can name production's project.
_OOM_PROJECT = "br-oomprobe"
_OOM_LIMIT_MB = 64


def test_the_cgroup_enforcement_tier_is_opt_in_and_says_so():
    """The skip below is not allowed to be silent.

    Unconditional, and it asserts the two things that make the omission
    honest: the variable has a name, and the spec sentence that motivates the
    tier is quoted where a reader will find it.
    """
    assert LIMITS_LIVE_ENV in _LIMITS_LIVE_REASON
    source = Path(__file__).read_text(encoding="utf-8")
    assert "cgroup enforcement is the claim" in source, (
        "the spec sentence this tier exists to satisfy is no longer quoted "
        "here, so a reader cannot tell what the gate is for"
    )
    assert "OOMKilled" in source, (
        "the enforcement test no longer asserts on OOMKilled, which is the "
        "only evidence that a ceiling was applied by the kernel rather than "
        "merely written into a file"
    )


@limits_live
def test_a_container_past_its_mem_limit_is_oom_killed_by_the_kernel():
    """The claim P2 actually makes, measured.

    One throwaway container in a `br-` project, given `--memory 64m` -- the
    same knob `mem_limit` renders to -- and asked to allocate well past it.
    The evidence is `.State.OOMKilled` from the daemon, which is the kernel's
    answer and not Compose's; a container that merely exits non-zero proves
    nothing (a Python MemoryError would do that with no cgroup involved at
    all), so BOTH the OOM flag and the 137 exit are checked.

    Production is fingerprinted before and after. This creates a container, so
    "it did not touch production" is a measurement here, not an argument.
    """
    def containers() -> list[str]:
        out = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}"],
            capture_output=True, text=True, check=True,
        )
        return sorted(out.stdout.split())

    before = containers()
    name = f"{_OOM_PROJECT}-probe"
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True)
    try:
        # `--memory` and NOT `--memory-swap` left default: with swap allowed
        # the allocation succeeds and the test would pass on a host where the
        # ceiling does nothing. Equal values disable swap for this container.
        run = subprocess.run(
            [
                "docker", "run", "--name", name,
                "--label", f"com.docker.compose.project={_OOM_PROJECT}",
                "--memory", f"{_OOM_LIMIT_MB}m",
                "--memory-swap", f"{_OOM_LIMIT_MB}m",
                "--network=none",
                "docker.io/library/python:3.14-slim",
                "python", "-c",
                # Touch every page, so this is resident memory and not a
                # lazily-mapped allocation the cgroup never sees.
                f"b = bytearray({_OOM_LIMIT_MB * 8} * 1024 * 1024)\n"
                "for i in range(0, len(b), 4096): b[i] = 1\n"
                "print('ALLOCATED', len(b))",
            ],
            capture_output=True, text=True,
        )
        inspected = subprocess.run(
            ["docker", "inspect", name, "--format",
             "{{.State.OOMKilled}} {{.State.ExitCode}}"],
            capture_output=True, text=True, check=True,
        ).stdout.split()

        assert "ALLOCATED" not in run.stdout, (
            f"the container allocated {_OOM_LIMIT_MB * 8} MiB under a "
            f"{_OOM_LIMIT_MB} MiB ceiling. The ceiling is not being enforced "
            "by the kernel, so every `mem_limit` this repository renders is "
            "decoration."
        )
        assert inspected[0] == "true", (
            f"the container died but .State.OOMKilled is {inspected[0]!r}. "
            "Something other than the memory cgroup killed it, so this proves "
            "nothing about the ceiling."
        )
        assert inspected[1] == "137", inspected
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True)

    assert containers() == before, (
        "production's container list changed across this test -- the "
        "throwaway container was not cleaned up, or something else moved"
    )


def _mem_bytes(value: str) -> int:
    """`1g` / `2560m` / a plain byte count, as bytes."""
    text = str(value).strip().lower()
    if text.endswith("g"):
        return int(float(text[:-1]) * 1024 ** 3)
    if text.endswith("m"):
        return int(float(text[:-1]) * 1024 ** 2)
    if text.endswith("k"):
        return int(float(text[:-1]) * 1024)
    return int(text)


def _mem_total_bytes() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemTotal:"):
            return int(line.split()[1]) * 1024
    raise AssertionError("/proc/meminfo has no MemTotal")


def test_no_single_ceiling_exceeds_host_ram_and_an_overcommitted_sum_is_declared(config):
    """M6, and the cheap half of the enforcement question.

    Two different claims, and only the first is unconditional:

    * NO SINGLE ceiling may exceed host RAM. One that does cannot ever be
      reached, so it is not a ceiling -- it is the absence of one, written to
      look like its presence.
    * the SUM may exceed host RAM, because ceilings are not reservations, but
      it may not do so SILENTLY. Measured 2026-08-01 the `measured` profile
      sums to ~15.6 GB on a 15.5 GiB host and nothing anywhere related the two
      numbers. A profile in that position must declare `sum_exceeds_host_ram:
      true` in branch-limits.yaml, where the reasoning sits next to the
      numbers it is about.
    """
    total = _mem_total_bytes()
    document = yaml.safe_load(
        overlay.limits_path(REPO_ROOT).read_text(encoding="utf-8"))
    profiles = document["profiles"]
    assert profiles, "branch-limits.yaml declares no profiles"

    for profile in sorted(profiles):
        parsed = overlay.load_overlay(_rendered(config, profile))
        ceilings = {
            name: _mem_bytes(body["mem_limit"])
            for name, body in (parsed.get("services") or {}).items()
            if body and "mem_limit" in body
        }
        assert ceilings, f"profile {profile!r} rendered no ceiling at all"

        too_big = sorted(n for n, v in ceilings.items() if v > total)
        assert too_big == [], (
            f"profile {profile!r} gives {too_big} a ceiling above this host's "
            f"{total / 1024 ** 3:.1f} GiB of RAM. A ceiling that cannot be "
            "reached is not a ceiling."
        )

        declared = bool((profiles[profile] or {}).get("sum_exceeds_host_ram"))
        overcommitted = sum(ceilings.values()) > total
        assert overcommitted == declared, (
            f"profile {profile!r}: its ceilings sum to "
            f"{sum(ceilings.values()) / 1024 ** 3:.1f} GiB against "
            f"{total / 1024 ** 3:.1f} GiB of host RAM, but "
            f"`sum_exceeds_host_ram` is {declared}. Ceilings are not "
            "reservations and an overcommitted sum is allowed -- it is not "
            "allowed to be undeclared, and a declaration that has stopped "
            "being true is worse than none."
        )


def test_the_branch_memory_estimate_is_used_and_not_merely_named():
    """`MEM_PER_BRANCH_BYTES` was referenced only inside a message string.

    A constant that appears in prose and in no computation is a comment with a
    type annotation: it can drift from the number the guard actually uses and
    nothing notices, and the message then quotes a measurement that no longer
    relates to the floor being enforced. The floor is now DERIVED from it.
    """
    assert branch.MEM_FLOOR_BYTES == (
        branch.MEM_PER_BRANCH_BYTES + branch.MEM_HEADROOM_BYTES
    ), (
        "MEM_FLOOR_BYTES is no longer derived from the measured per-branch "
        "cost, so `shortfalls()` quoting that cost is a claim about a number "
        "the guard does not use"
    )
    assert branch.MEM_PER_BRANCH_BYTES > 0 and branch.MEM_HEADROOM_BYTES > 0
