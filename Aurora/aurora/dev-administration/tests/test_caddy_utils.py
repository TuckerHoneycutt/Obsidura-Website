from dev_administration.models import DeveloperConfig
import pytest

from dev_administration.caddy_utils import (
    agent_upstream, authz_upstream, fjell_upstream,
    generate_caddy_agents_conf, generate_agents_json,
)


DEVS = [
    {"username": "juan", "display_name": "Juan", "host_port": 9120},
    {"username": "ethan", "display_name": "Ethan", "host_port": 9121},
]


def test_published_mode_routes_to_localhost_ports():
    """Production's Caddy is network_mode: host, so it cannot resolve Docker
    DNS and must reach every backend on a published 127.0.0.1 port."""
    conf = generate_caddy_agents_conf(
        DEVS, "superserver.tailc67a98.ts.net", mode="published"
    )
    assert "reverse_proxy 127.0.0.1:9120" in conf
    assert "reverse_proxy 127.0.0.1:9121" in conf
    assert "reverse_proxy 127.0.0.1:9080" in conf                # fjell
    assert "forward_auth @needs_authz 127.0.0.1:9140" in conf     # agent-authz


def test_service_mode_routes_by_service_dns():
    """A branch's Caddy is network_mode: service:tailscale — it shares the
    sidecar's netns, where 127.0.0.1 reaches nothing, and a branch publishes
    no host ports at all (spec §5.1). Service DNS is the only address that
    exists there."""
    conf = generate_caddy_agents_conf(
        DEVS, "aurora-demo.tailc67a98.ts.net", mode="service"
    )
    assert "reverse_proxy hermes-juan:9119" in conf
    assert "reverse_proxy hermes-ethan:9119" in conf
    assert "reverse_proxy fjell:9080" in conf
    assert "forward_auth @needs_authz agent-authz:9140" in conf
    assert "127.0.0.1" not in conf, (
        "A branch's Caddy cannot reach 127.0.0.1 — any localhost address left "
        "in the generated conf is a dead route"
    )


def test_setup_route_does_not_strip_its_prefix():
    """RESOLVED (Chunk 2); previously docs/post-implementation-steps.md §D1.

    fjell registers the route as `/agent/{username}/setup`
    (fjell/src/routes/setup.rs:91) — it expects the FULL path. `handle_path`
    strips the matched prefix and would deliver bare `/setup`, which fjell
    does not route. So `handle` is correct here, and the old
    `handle_path /agent/juan/setup` assertion was simply wrong.

    Verified against source rather than opinion: setup.rs:91 is
    `.route("/agent/{username}/setup", ...)` and the form at setup.rs:21
    POSTs to the same unstripped path.

    Note the deliberate contrast with the dashboard blocks, which DO use
    handle_path: Hermes wants the prefix stripped and re-supplied via
    X-Forwarded-Prefix.
    """
    conf = generate_caddy_agents_conf(DEVS, "example.ts.net")
    assert "handle /agent/juan/setup {" in conf
    assert "handle_path /agent/juan/setup" not in conf
    assert "handle_path /agent/juan/* {" in conf
    assert "handle_path /agent/ethan/* {" in conf


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        generate_caddy_agents_conf(DEVS, "example.ts.net", mode="magic")


def test_upstream_helpers_reject_an_unknown_mode():
    """The generator is not the only entry point — reconcile passes
    config.upstream_mode straight through, and a typo in .env must not
    silently fall back to production addressing inside a branch."""
    for fn, args in (
        (agent_upstream, (DEVS[0],)),
        (fjell_upstream, ()),
        (authz_upstream, ()),
    ):
        with pytest.raises(ValueError):
            fn(*args, "magic")


def test_generate_agents_json():
    devs = [
        DeveloperConfig(username="juan", display_name="Juan Martinez", forgejo_user="juan"),
    ]
    json_str = generate_agents_json(devs)
    assert '"username": "juan"' in json_str
    assert '"display_name": "Juan Martinez"' in json_str
