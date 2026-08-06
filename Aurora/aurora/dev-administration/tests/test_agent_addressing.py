"""Agreement between what Compose publishes and what Caddy proxies to.

Task 5's fix round 1 made reconcile and the renderer share `agent_specs` and
recorded that as "fixed". It was not: sharing a function is not a test.
Re-review demonstrated two mutations that put the disagreement back while
the whole suite stayed green --

  * reconcile recomputing `base_port + (len-1-i)`, so Caddy proxies
    /agent/testuser/ to the container publishing newuser's agent; and
  * reconcile calling `agent_specs(..., publish_ports=False)`, so
    `host_port` is None and the generated Caddyfile contains
    `reverse_proxy 127.0.0.1:None`, which Caddy refuses to load.

Neither is caught by the drift test: that compares the committed file to a
fresh render, so it sees only the renderer moving, never reconcile moving
away from it. These tests compare the two SIDES against each other.
"""

from unittest.mock import MagicMock, patch

import pytest
import yaml

from dev_administration.agents_compose import agent_specs, render_agents_compose
from dev_administration.models import DeveloperConfig
from dev_administration.notifier import StdoutNotifier
from dev_administration.provision import ProvisionConfig, reconcile

DEVS = [
    DeveloperConfig(username="testuser", display_name="Test", forgejo_user="testuser"),
    DeveloperConfig(username="newuser", display_name="New", forgejo_user="newuser"),
    DeveloperConfig(username="third", display_name="Third", forgejo_user="third"),
]

CONFIG = ProvisionConfig(
    forgejo_url="https://forgejo.example.invalid/git",
    forgejo_token="t",
    aurora_profile_url="https://forgejo.example.invalid/git/a/b.git",
    domain="example.invalid",
    caddy_container="",
    authorized_keys_path="/tmp/authorized_keys",
    project="aurora",
)


def _published_ports_from_rendered_fragment() -> dict[str, int]:
    """username -> host port, parsed from the rendered compose fragment."""
    doc = yaml.safe_load(render_agents_compose(agent_specs(DEVS)))
    ports = {}
    for service, body in doc["services"].items():
        username = service[len("hermes-"):]
        # "127.0.0.1:9120:9119" -> 9120
        ports[username] = int(body["ports"][0].split(":")[1])
    return ports


@pytest.fixture
def caddy_dev_dicts():
    """Run reconcile and capture the dev_dicts handed to the Caddy generator.

    Everything that touches Docker, Forgejo or a live container is patched;
    `project_services` returns every agent as already up so reconcile takes
    the verify path and performs no provisioning side effects at all.
    """
    services = {f"hermes-{d.username}": f"hermes-{d.username}" for d in DEVS}
    captured = {}

    def _capture(dev_dicts, domain, *args, **kwargs):
        captured["dev_dicts"] = dev_dicts
        return ""

    with patch("dev_administration.provision.project_services", return_value=services), \
         patch("dev_administration.provision.container_status", return_value="running"), \
         patch("dev_administration.provision.find_service_container", return_value="c"), \
         patch("dev_administration.provision.get_user", return_value={"id": 1}), \
         patch("dev_administration.provision.get_oauth2_app", return_value={"client_id": "x"}), \
         patch("dev_administration.provision.ensure_org"), \
         patch("dev_administration.provision.ensure_team"), \
         patch("dev_administration.provision.add_team_repo"), \
         patch("dev_administration.provision.ensure_branch_protection"), \
         patch("dev_administration.provision.generate_caddy_agents_conf", _capture):
        # The rest of the Caddy write surface is neutralised by the autouse
        # fixture in conftest.py. Only the generator is re-patched here, to
        # capture its arguments; duplicating the others by hand is what that
        # fixture exists to prevent.
        reconcile(DEVS, StdoutNotifier(), CONFIG)

    return captured["dev_dicts"]


def test_caddy_upstream_ports_match_the_ports_compose_publishes(caddy_dev_dicts):
    """The single assertion fix round 1 was missing.

    Caddy reaches each agent on a published 127.0.0.1 port. If the port
    reconcile writes into agents.conf is not the port compose.agents.yml
    publishes for that same developer, requests land on ANOTHER developer's
    agent -- authenticated as the wrong person, which the authz gate cannot
    catch because the proxy decision happens before it.
    """
    from_caddy = {d["username"]: d["host_port"] for d in caddy_dev_dicts}
    from_compose = _published_ports_from_rendered_fragment()

    assert from_caddy == from_compose, (
        "Caddy upstream ports disagree with the ports compose.agents.yml "
        f"publishes. Caddy={from_caddy} compose={from_compose}. Requests for "
        "one developer would be proxied to another developer's agent."
    )


def test_every_agent_gets_a_usable_upstream_port(caddy_dev_dicts):
    """A None port renders `reverse_proxy 127.0.0.1:None` and Caddy refuses
    to load the config -- taking down every route in the file, not just the
    agent's."""
    bad = [d["username"] for d in caddy_dev_dicts if not isinstance(d["host_port"], int)]
    assert bad == [], (
        f"Developers with no usable upstream port: {bad}. The generated "
        "Caddyfile would contain `reverse_proxy 127.0.0.1:None` and Caddy "
        "would reject the whole file."
    )


def test_a_developer_with_no_published_port_is_left_out_of_the_caddy_config():
    """A null upstream must remove ONE route, never break the whole file.

    caddy_utils reads `dev.get("host_port", 9119)`, and a None value means
    the key IS present, so the default never applies -- the generator emits
    `reverse_proxy 127.0.0.1:None` three times per developer. That text goes
    into Caddyfile.d/agents.conf, which the main Caddyfile imports, and
    reload_caddy runs `caddy reload` with check=False and throws the failure
    away. Caddy keeps serving from memory and reconcile reports success, so
    the damage only lands at the next Caddy start -- a reboot, an unrelated
    `up -d` -- where every route in the file dies: AFFiNE, Forgejo, fjell,
    the setup form.
    """
    services = {f"hermes-{d.username}": f"hermes-{d.username}" for d in DEVS}
    captured = {}

    def _capture(dev_dicts, domain, *args, **kwargs):
        captured["dev_dicts"] = dev_dicts
        return ""

    # One developer allocated no published port.
    crippled = [
        spec if spec.username != "newuser" else spec.__class__(
            **{**spec.__dict__, "host_port": None}
        )
        for spec in agent_specs(DEVS)
    ]

    with patch("dev_administration.provision.project_services", return_value=services), \
         patch("dev_administration.provision.container_status", return_value="running"), \
         patch("dev_administration.provision.find_service_container", return_value="c"), \
         patch("dev_administration.provision.agent_specs", return_value=crippled), \
         patch("dev_administration.provision.get_user", return_value={"id": 1}), \
         patch("dev_administration.provision.get_oauth2_app", return_value={"client_id": "x"}), \
         patch("dev_administration.provision.ensure_org"), \
         patch("dev_administration.provision.ensure_team"), \
         patch("dev_administration.provision.add_team_repo"), \
         patch("dev_administration.provision.ensure_branch_protection"), \
         patch("dev_administration.provision.generate_caddy_agents_conf", _capture):
        events = reconcile(DEVS, StdoutNotifier(), CONFIG)

    usernames = [d["username"] for d in captured["dev_dicts"]]
    assert "newuser" not in usernames, (
        "a developer with no published port was still given a Caddy route; "
        "the rendered config would contain `reverse_proxy 127.0.0.1:None` "
        "and Caddy would refuse the entire file at its next start"
    )
    assert set(usernames) == {"testuser", "third"}
    assert None not in [d["host_port"] for d in captured["dev_dicts"]]

    # And it must be reported, not silently dropped.
    unaddressable = [e for e in events if e.event_type == "agent.unaddressable"]
    assert [e.developer for e in unaddressable] == ["newuser"]


def test_reconcile_passes_its_configured_upstream_mode_to_the_generator():
    """The integration point Task 6 hinges on.

    caddy_utils gained the mode, but a branch only benefits if reconcile
    actually forwards config.upstream_mode. Defaulting to "published" inside
    a branch would generate 127.0.0.1 upstreams for a Caddy that shares the
    tailscale sidecar's netns, where nothing listens on localhost -- every
    agent route dead, and the generated file looks perfectly normal.
    """
    services = {f"hermes-{d.username}": f"hermes-{d.username}" for d in DEVS}
    branch_config = ProvisionConfig(
        forgejo_url="https://forgejo.example.invalid/git",
        forgejo_token="t",
        aurora_profile_url="https://forgejo.example.invalid/git/a/b.git",
        domain="aurora-demo.invalid",
        caddy_container="",
        authorized_keys_path="/tmp/authorized_keys",
        project="br-demo",
        upstream_mode="service",
    )

    with patch("dev_administration.provision.project_services", return_value=services), \
         patch("dev_administration.provision.container_status", return_value="running"), \
         patch("dev_administration.provision.find_service_container", return_value="c"), \
         patch("dev_administration.provision.get_user", return_value={"id": 1}), \
         patch("dev_administration.provision.get_oauth2_app", return_value={"client_id": "x"}), \
         patch("dev_administration.provision.ensure_org"), \
         patch("dev_administration.provision.ensure_team"), \
         patch("dev_administration.provision.add_team_repo"), \
         patch("dev_administration.provision.ensure_branch_protection"), \
         patch("dev_administration.provision.generate_caddy_agents_conf",
               return_value="") as mock_gen:
        reconcile(DEVS, StdoutNotifier(), branch_config)

    assert mock_gen.call_args.kwargs.get("mode") == "service", (
        "reconcile did not forward config.upstream_mode; a branch would get "
        "127.0.0.1 upstreams its Caddy cannot reach"
    )
