from unittest.mock import patch, MagicMock

from dev_administration.models import DeveloperConfig, OrchestratorEvent
from dev_administration.notifier import StdoutNotifier
from dev_administration.provision import reconcile, ProvisionConfig, deprovision_developer

# `project` is passed explicitly so ProvisionConfig.__post_init__ never calls
# current_project(), which would consult the live daemon from a unit test.
CONFIG = ProvisionConfig(
    forgejo_url="https://forgejo.example.com/git",
    forgejo_token="admin-token",
    aurora_profile_url="https://forgejo.example.com/git/admin/aurora-agent.git",
    domain="forgejo.example.com",
    caddy_container="",
    authorized_keys_path="/tmp/authorized_keys",
    project="aurora",
)


@patch("dev_administration.provision.container_exists", return_value=False)
@patch("dev_administration.provision.volume_exists", return_value=False)
@patch("dev_administration.provision.create_volume")
@patch("dev_administration.provision.get_oauth2_app", return_value=None)
@patch("dev_administration.provision.create_oauth2_app",
       return_value=("client123", "secret456"))
@patch("dev_administration.provision.run_temp_container")
@patch("dev_administration.provision.network_name", return_value="aurora_default")
@patch("dev_administration.provision.project_services", return_value={})
@patch("dev_administration.provision.open", new_callable=MagicMock)
@patch("dev_administration.provision.os.makedirs")
@patch("dev_administration.provision.os.replace")
@patch("dev_administration.provision.os.fchmod")
def test_reconcile_provisions_new_developer(
    mock_fchmod, mock_replace, mock_makedirs, mock_open, mock_services, mock_network,
    mock_run_temp, mock_create_app, mock_get_app, mock_create_vol,
    mock_vol_exists, mock_container_exists,
):
    devs = [DeveloperConfig(username="juan", display_name="Juan", forgejo_user="juan")]
    events = reconcile(devs, StdoutNotifier(), CONFIG)
    # Volume name is project-scoped now: an unprefixed one is reachable from
    # every project on the daemon.
    mock_create_vol.assert_called_once_with("aurora_hermes-juan-home")
    mock_create_app.assert_called_once()
    assert any(e.event_type == "developer.provisioned" for e in events)


@patch("dev_administration.provision.container_exists", return_value=False)
@patch("dev_administration.provision.volume_exists", return_value=True)
@patch("dev_administration.provision.get_oauth2_app", return_value=None)
@patch("dev_administration.provision.create_oauth2_app", return_value=("cid", "sec"))
@patch("dev_administration.provision.run_temp_container")
@patch("dev_administration.provision.network_name", return_value="aurora_default")
@patch("dev_administration.provision.project_services", return_value={})
@patch("dev_administration.provision.open", new_callable=MagicMock)
@patch("dev_administration.provision.os.makedirs")
@patch("dev_administration.provision.os.replace")
@patch("dev_administration.provision.os.fchmod")
def test_reconcile_warns_instead_of_starting_a_container(
    mock_fchmod, mock_replace, mock_makedirs, mock_open, mock_services, mock_network,
    mock_run_temp, mock_create_app, mock_get_app, mock_vol_exists,
    mock_container_exists,
):
    """reconcile no longer creates containers — Compose does. When the
    service is not up it must say so loudly with the exact command, not
    silently succeed."""
    devs = [DeveloperConfig(username="juan", display_name="Juan", forgejo_user="juan")]
    events = reconcile(devs, StdoutNotifier(), CONFIG)
    missing = [e for e in events if e.event_type == "container.missing"]
    assert missing, "expected a container.missing warning"
    assert "docker compose up -d hermes-juan" in missing[0].message


@patch("dev_administration.provision.container_exists", return_value=False)
@patch("dev_administration.provision.volume_exists", return_value=True)
@patch("dev_administration.provision.get_oauth2_app", return_value=None)
@patch("dev_administration.provision.create_oauth2_app", return_value=("cid", "sec"))
@patch("dev_administration.provision.run_temp_container")
@patch("dev_administration.provision.network_name", return_value="aurora_default")
@patch("dev_administration.provision.project_services", return_value={})
@patch("dev_administration.provision.open", new_callable=MagicMock)
@patch("dev_administration.provision.os.makedirs")
@patch("dev_administration.provision.os.replace")
@patch("dev_administration.provision.os.fchmod")
def test_agent_secrets_are_written_atomically_and_never_inline(
    mock_fchmod, mock_replace, mock_makedirs, mock_open, mock_services,
    mock_network, mock_run_temp, mock_create_app, mock_get_app,
    mock_vol_exists, mock_container_exists,
):
    """The OIDC secret reaches the agent through a gitignored env_file.

    Written to a .tmp, chmodded on the still-open fd, then os.replace'd.
    ORDER is the point, not merely presence: Compose may read the file at any
    moment, so a partial write yields a truncated client secret that fails at
    the OIDC token exchange rather than at startup; and chmod-ing after the
    rename leaves a window in which the secret is readable at the default
    umask. MagicMock cannot show that window -- a real closed file would
    raise ValueError on .fileno() -- so the sequence is recorded explicitly.
    """
    order = []
    handle = mock_open.return_value.__enter__.return_value
    mock_fchmod.side_effect = lambda *a, **k: order.append("fchmod")
    mock_replace.side_effect = lambda *a, **k: order.append("replace")
    mock_open.return_value.__exit__.side_effect = lambda *a, **k: order.append("close")

    devs = [DeveloperConfig(username="juan", display_name="Juan", forgejo_user="juan")]
    reconcile(devs, StdoutNotifier(), CONFIG)

    mock_open.assert_called_once_with("/agent-env/juan.env.tmp", "w")
    mock_replace.assert_called_once_with(
        "/agent-env/juan.env.tmp", "/agent-env/juan.env"
    )

    written = "".join(call[0][0] for call in handle.write.call_args_list)
    assert "HERMES_DASHBOARD_OIDC_CLIENT_SECRET=sec" in written
    assert "HERMES_DASHBOARD_OIDC_CLIENT_ID=cid" in written

    mock_fchmod.assert_called_once_with(handle.fileno.return_value, 0o600)
    assert order == ["fchmod", "close", "replace"], (
        "the secret must be chmodded on the open fd and only then renamed "
        f"into place; observed {order}"
    )


@patch("dev_administration.provision.container_exists", return_value=True)
@patch("dev_administration.provision.container_status", return_value="running")
@patch("dev_administration.provision.volume_exists", return_value=True)
@patch("dev_administration.provision.project_services",
       return_value={"hermes-juan": "hermes-juan"})
@patch("dev_administration.provision.open", new_callable=MagicMock)
@patch("dev_administration.provision.os.makedirs")
def test_reconcile_skips_existing_healthy(
    mock_makedirs, mock_open, mock_services, mock_vol_exists, mock_status,
    mock_container_exists,
):
    devs = [DeveloperConfig(username="juan", display_name="Juan", forgejo_user="juan")]
    events = reconcile(devs, StdoutNotifier(), CONFIG)
    assert not any(e.event_type == "developer.provisioned" for e in events)


@patch("dev_administration.provision.container_exists", return_value=True)
@patch("dev_administration.provision.container_status", return_value="running")
@patch("dev_administration.provision.project_services",
       return_value={"hermes-maria": "hermes-maria"})
@patch("dev_administration.provision.volume_exists", return_value=True)
@patch("dev_administration.provision.stop_and_remove_container")
@patch("dev_administration.provision.remove_ssh_key")
@patch("dev_administration.provision.open", new_callable=MagicMock)
@patch("dev_administration.provision.os.makedirs")
def test_reconcile_deprovisions_removed_developer(
    mock_makedirs, mock_open, mock_rm_ssh, mock_stop, mock_vol_exists,
    mock_services, mock_status, mock_container_exists,
):
    devs = []
    events = reconcile(devs, StdoutNotifier(), CONFIG)
    mock_stop.assert_called_with("hermes-maria")
    assert any(e.event_type == "volume.orphaned" for e in events)


@patch("dev_administration.provision.remove_ssh_key")
@patch("dev_administration.provision.stop_and_remove_container")
@patch("dev_administration.provision.project_services", return_value={})
def test_deprovision_of_an_absent_container_touches_no_container(
    mock_services, mock_stop, mock_rm_ssh,
):
    """A developer whose container Compose never started still needs their
    SSH key revoked. Calling stop_and_remove_container on a guessed name
    would instead raise ProjectMismatch — the guard cannot prove a
    nonexistent container is ours — and abort the revocation.
    """
    events = deprovision_developer("juan", CONFIG, StdoutNotifier())
    mock_stop.assert_not_called()
    mock_rm_ssh.assert_called_once_with("juan", "/tmp/authorized_keys")
    assert any(e.event_type == "volume.orphaned" for e in events)
    assert events[0].metadata["volume"] == "aurora_hermes-juan-home"


# --- coverage for fixes that re-review showed nothing could detect ---------

def _config(**overrides):
    base = dict(
        forgejo_url="https://forgejo.example.com/git",
        forgejo_token="admin-token",
        aurora_profile_url="https://forgejo.example.com/git/admin/aurora-agent.git",
        domain="forgejo.example.com",
        caddy_container="",
        authorized_keys_path="/tmp/authorized_keys",
        project="aurora",
    )
    base.update(overrides)
    return ProvisionConfig(**base)


@patch("dev_administration.provision.container_status", return_value="running")
@patch("dev_administration.provision.project_services",
       return_value={"hermes-juan": "hermes-juan"})
@patch("dev_administration.provision.find_service_container", return_value="c")
def test_reconcile_warns_when_the_committed_fragment_is_stale(
    mock_find, mock_services, mock_status, tmp_path,
):
    """reconcile cannot regenerate compose.agents.yml -- the file is tracked
    and it normally runs inside a container -- so it must SAY so. Without
    this, adding a developer yields an account, an OAuth app, a volume and an
    env file, then `docker compose up -d hermes-<new>` fails with `no such
    service` and nothing explains why."""
    stale = tmp_path / "compose.agents.yml"
    stale.write_text("# GENERATED by `dev-admin render-agents` — stale\nservices: {}\n")

    devs = [DeveloperConfig(username="juan", display_name="Juan", forgejo_user="juan")]
    events = reconcile(devs, StdoutNotifier(), _config(agents_compose_path=str(stale)))

    stale_events = [e for e in events if e.event_type == "compose.stale"]
    assert stale_events, "expected a compose.stale warning"
    assert "render-agents" in stale_events[0].message


@patch("dev_administration.provision.container_status", return_value="running")
@patch("dev_administration.provision.project_services",
       return_value={"hermes-juan": "hermes-juan"})
@patch("dev_administration.provision.find_service_container", return_value="c")
def test_reconcile_is_silent_when_the_committed_fragment_is_current(
    mock_find, mock_services, mock_status, tmp_path,
):
    """The other half: a fresh file must NOT warn, or the warning is noise
    and gets ignored the one time it matters."""
    from dev_administration.agents_compose import agent_specs, render_agents_compose

    devs = [DeveloperConfig(username="juan", display_name="Juan", forgejo_user="juan")]
    fresh = tmp_path / "compose.agents.yml"
    fresh.write_text(render_agents_compose(agent_specs(devs)))

    events = reconcile(devs, StdoutNotifier(), _config(agents_compose_path=str(fresh)))
    assert not [e for e in events if e.event_type == "compose.stale"]


@patch("dev_administration.provision.container_status", return_value="running")
@patch("dev_administration.provision.project_services",
       return_value={"hermes-juan": "hermes-juan"})
@patch("dev_administration.provision.find_service_container", return_value="c")
def test_reconcile_reports_an_unreadable_fragment_rather_than_passing_silently(
    mock_find, mock_services, mock_status, tmp_path,
):
    devs = [DeveloperConfig(username="juan", display_name="Juan", forgejo_user="juan")]
    missing = tmp_path / "does-not-exist.yml"
    events = reconcile(devs, StdoutNotifier(), _config(agents_compose_path=str(missing)))
    assert [e for e in events if e.event_type == "compose.unreadable"]


@patch("dev_administration.provision.container_exists", return_value=False)
@patch("dev_administration.provision.volume_exists", return_value=True)
@patch("dev_administration.provision.get_oauth2_app", return_value=None)
@patch("dev_administration.provision.create_oauth2_app", return_value=("cid", "sec"))
@patch("dev_administration.provision.run_temp_container")
@patch("dev_administration.provision.network_name", return_value="aurora_default")
@patch("dev_administration.provision.project_services", return_value={})
@patch("dev_administration.provision.open", new_callable=MagicMock)
@patch("dev_administration.provision.os.makedirs")
@patch("dev_administration.provision.os.replace")
@patch("dev_administration.provision.os.fchmod")
def test_reconcile_queries_the_project_only_once(
    mock_fchmod, mock_replace, mock_makedirs, mock_open, mock_services,
    mock_network, mock_run_temp, mock_create_app, mock_get_app,
    mock_vol_exists, mock_container_exists,
):
    """provision_developer used to re-query project_services AFTER creating
    the Forgejo user, recreating the OAuth app and writing the volume.
    project_services is fail-closed, so one transient `docker ps` failure at
    that instant aborted reconcile with every side effect applied and Caddy
    never updated -- the crash-after-irreversible-work class Task 4 existed
    to remove. The caller's map is passed down instead."""
    devs = [DeveloperConfig(username="juan", display_name="Juan", forgejo_user="juan")]
    reconcile(devs, StdoutNotifier(), CONFIG)
    assert mock_services.call_count == 1, (
        f"project_services called {mock_services.call_count}x; a second call "
        "happens after irreversible side effects and can abort reconcile"
    )


@patch("dev_administration.provision.container_status", return_value="running")
@patch("dev_administration.provision.find_service_container", return_value="c")
@patch("dev_administration.provision.remove_ssh_key")
@patch("dev_administration.provision.stop_and_remove_container")
def test_the_admin_agent_is_not_mistaken_for_a_developer(
    mock_stop, mock_rm_ssh, mock_find, mock_status,
):
    """Exercises reconcile, not a copy of its comprehension.

    The previous version of this test reimplemented the `startswith` filter
    inline and asserted on its own result, so loosening the real prefix to
    "hermes" -- the exact mutation its docstring claimed to catch -- left the
    suite green. Under that mutation the admin agent's service `hermes`
    yields username "", which lands in `actual - desired` and reaches
    remove_ssh_key("") plus a teardown of the admin agent itself.
    """
    services = {"hermes": "hermes", "caddy": "aurora-caddy-1"}
    with patch("dev_administration.provision.project_services", return_value=services):
        events = reconcile([], StdoutNotifier(), CONFIG)

    mock_stop.assert_not_called()
    mock_rm_ssh.assert_not_called()
    assert not [e for e in events if e.event_type == "volume.orphaned"], (
        "the admin agent (service `hermes`, no dash) was treated as a "
        "developer and deprovisioned"
    )
