"""Unit tests for aurora_cli.overlay — the renderer, against synthetic
configurations.

These never invoke docker. The gates that hold the COMMITTED artifact against
the REAL resolved configuration live in tests/test_branch_overlay.py, and they
deliberately derive their expectations from the resolved config rather than
from this module's output: if the generator and the checker both read the same
source, deleting an entry blinds both at once and the suite stays green while
the branch is misconfigured.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aurora_cli import overlay

CADDYFILE_BIND = {
    "type": "bind",
    "source": "/repo/Caddyfile",
    "target": "/etc/caddy/Caddyfile",
    "read_only": True,
}
HOST_SOCKET_BIND = {
    "type": "bind",
    "source": "/var/run/tailscale",
    "target": "/var/run/tailscale",
    "read_only": True,
}
CADDY_DATA = {"type": "volume", "source": "caddy_data", "target": "/data"}


def make_config(services: dict | None = None, caddy: dict | None = None) -> dict:
    """A minimal resolved-config shape: caddy plus whatever else is asked for."""
    resolved = {
        "caddy": caddy
        if caddy is not None
        else {"volumes": [CADDYFILE_BIND, HOST_SOCKET_BIND, CADDY_DATA]}
    }
    resolved.update(services or {})
    return {"services": resolved}


def render(config: dict, root: str | Path = "/repo") -> str:
    return overlay.render_overlay(config, Path(root))


# ------------------------------------------------------------ enumeration


def test_reset_targets_selects_only_the_services_that_cannot_be_namespaced():
    config = make_config({
        "named": {"container_name": "forgejo"},
        "published": {"ports": [{"published": "9080"}]},
        "both": {"container_name": "hermes", "ports": [{"published": "9119"}]},
        "neither": {"image": "redis"},
    })

    assert overlay.reset_targets(config) == {
        "both": ("container_name", "ports"),
        "named": ("container_name",),
        "published": ("ports",),
    }


def test_reset_targets_ignores_a_declared_but_empty_ports_list():
    """An empty list needs no reset, and an entry for it is noise the next
    reader has to explain away before they can trust the rest of the file."""
    config = make_config({"quiet": {"ports": [], "container_name": ""}})

    assert "quiet" not in overlay.reset_targets(config)


def test_reset_targets_refuses_a_configuration_with_no_services():
    """Trap 2 in the generator: an empty parse renders an overlay that resets
    nothing and passes every coverage gate vacuously."""
    with pytest.raises(overlay.OverlayError) as excinfo:
        overlay.reset_targets({"services": {}})

    # Asserting on the message, not merely the type: render_overlay raises the
    # same type from three other guards, so a bare `raises` here would be
    # satisfied by any of them and would pin nothing.
    assert "COMPOSE_PROFILES" in str(excinfo.value)


def test_the_sorted_order_is_stable_across_input_order():
    forward = make_config({
        "a": {"container_name": "a"}, "z": {"container_name": "z"},
    })
    backward = make_config({
        "z": {"container_name": "z"}, "a": {"container_name": "a"},
    })

    assert render(forward) == render(backward)


# ---------------------------------------------------------------- tagging


def test_every_target_is_reset_for_exactly_the_keys_it_declares():
    config = make_config({
        "named": {"container_name": "forgejo"},
        "published": {"ports": [{"published": "9080"}]},
        "both": {"container_name": "hermes", "ports": [{"published": "9119"}]},
        "neither": {"image": "redis"},
    })

    resets = overlay.overlay_resets(render(config))

    assert resets["named"] == {"container_name": "!reset"}
    assert resets["published"] == {"ports": "!reset"}
    assert resets["both"] == {"container_name": "!reset", "ports": "!reset"}
    assert "neither" not in resets


def test_an_untagged_key_is_not_read_as_a_reset():
    """`ports: []` and `ports: !reset []` are indistinguishable once the tag is
    dropped, and they do OPPOSITE things: Compose merges the untagged empty
    list with the inherited one and the branch keeps production's published
    port. Every coverage gate therefore reads the TAG."""
    text = (
        "services:\n"
        "  untagged:\n"
        "    ports: []\n"
        "  tagged:\n"
        "    ports: !reset []\n"
    )

    resets = overlay.overlay_resets(text)

    assert resets["untagged"] == {"ports": None}
    assert resets["tagged"] == {"ports": "!reset"}


def test_the_loader_refuses_two_blocks_for_one_service():
    """YAML resolves a duplicate key last-wins and silently. Without this, the
    caddy-folding test below would prove nothing: a second `caddy:` block would
    simply discard the network-namespace flip and the parse would succeed."""
    text = "services:\n  caddy:\n    ports: !reset []\n  caddy:\n    image: x\n"

    with pytest.raises(overlay.OverlayError) as excinfo:
        overlay.load_overlay(text)

    assert "duplicate" in str(excinfo.value)


# ------------------------------------------------------------------ caddy


def test_caddy_resets_are_folded_into_the_network_namespace_block():
    """Caddy is the one service that is reconfigured rather than merely
    un-namespaced. If it ever gains a container_name or a published port, its
    reset has to go INSIDE that block."""
    config = make_config(caddy={
        "container_name": "caddy",
        "ports": [{"published": "443"}],
        "volumes": [CADDYFILE_BIND, HOST_SOCKET_BIND],
    })

    text = render(config)
    doc = overlay.load_overlay(text)

    assert text.count("\n  caddy:\n") == 1
    assert doc["services"]["caddy"]["network_mode"] == "service:tailscale"
    assert overlay.overlay_resets(text)["caddy"] == {
        "container_name": "!reset", "ports": "!reset",
    }


def test_caddy_swaps_the_host_socket_for_the_sidecar_volume():
    volumes = overlay.caddy_branch_volumes(make_config(), Path("/repo"))

    assert volumes == [
        "./Caddyfile:/etc/caddy/Caddyfile:ro",
        "tailscale_sock:/var/run/tailscale:ro",
        "caddy_data:/data",
    ]


def test_caddy_gets_the_sidecar_socket_even_with_no_host_bind_to_replace():
    """`volumes: !override` replaces the list wholesale, so an overlay that
    merely REMOVED the host bind would leave Caddy with no tailscaled socket at
    all and no certificate."""
    config = make_config(caddy={"volumes": [CADDY_DATA]})

    volumes = overlay.caddy_branch_volumes(config, Path("/repo"))

    assert volumes == ["caddy_data:/data", "tailscale_sock:/var/run/tailscale:ro"]


def test_the_caddy_volume_list_is_derived_not_copied():
    """A volume added to Caddy in compose.yml must appear in the branch's
    override list. `!override` is wholesale: a hand-copied list that went stale
    would drop the mount with no error anywhere."""
    extra = {"type": "volume", "source": "new_thing", "target": "/new"}
    config = make_config(caddy={"volumes": [HOST_SOCKET_BIND, extra]})

    assert "new_thing:/new" in overlay.caddy_branch_volumes(config, Path("/repo"))


def test_a_bind_source_is_relativised_across_a_symlinked_parent(tmp_path):
    """On this host /home is a symlink to /var/home and `docker compose config`
    reports the UNRESOLVED path. Both sides are resolved before subtraction; a
    string prefix test would never match and every bind would be emitted as an
    absolute host path, pinning the branch's Caddyfile to production's tree."""
    real = tmp_path / "var" / "repo"
    real.mkdir(parents=True)
    link = tmp_path / "home"
    link.symlink_to(tmp_path / "var")

    config = make_config(caddy={"volumes": [
        {"type": "bind", "source": str(link / "repo" / "Caddyfile"),
         "target": "/etc/caddy/Caddyfile", "read_only": True},
    ]})

    volumes = overlay.caddy_branch_volumes(config, real)

    assert volumes[0] == "./Caddyfile:/etc/caddy/Caddyfile:ro"


def test_rendering_refuses_a_configuration_with_no_caddy():
    with pytest.raises(overlay.OverlayError) as excinfo:
        overlay.render_overlay({"services": {"forgejo": {"container_name": "f"}}})

    assert "caddy" in str(excinfo.value)


def test_rendering_refuses_a_base_configuration_that_already_has_a_sidecar():
    """The overlay ADDS the sidecar. If the base ever declared one, the two
    would merge and the branch would inherit whatever the base said — including
    an auth key with no `:?` guard."""
    config = make_config({"tailscale": {"image": "tailscale/tailscale:latest"}})

    with pytest.raises(overlay.OverlayError) as excinfo:
        render(config)

    assert "sidecar" in str(excinfo.value)


# ---------------------------------------------------------------- sidecar


def test_the_sidecar_runs_in_kernel_mode_and_refuses_magicdns():
    text = render(make_config())

    assert "TS_USERSPACE=false" in text
    assert "TS_ACCEPT_DNS=false" in text
    assert "/dev/net/tun:/dev/net/tun" in text
    assert "NET_ADMIN" in text and "NET_RAW" in text


def test_the_sidecar_state_is_a_project_scoped_volume_not_memory():
    text = render(make_config())
    doc = overlay.load_overlay(text)

    mounts = doc["services"][overlay.SIDECAR_SERVICE]["volumes"]

    assert "TS_STATE_DIR=/var/lib/tailscale" in text
    # Read from the parsed document, not the raw text: the comment above the
    # list explains why `mem:` is wrong, so a substring scan of the file would
    # be reddened by its own justification.
    assert f"{overlay.STATE_VOLUME}:/var/lib/tailscale" in mounts
    assert not [m for m in mounts if m.startswith("mem:")]
    assert set(doc["volumes"]) == {overlay.STATE_VOLUME, overlay.SOCK_VOLUME}


def test_the_branch_variables_are_hard_config_errors_when_absent():
    text = render(make_config())

    assert "${TS_AUTHKEY:?" in text
    assert "${TS_HOSTNAME:?" in text
