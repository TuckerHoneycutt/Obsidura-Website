"""Coverage for the CLI commands the volume migration silently broke.

`dev-admin status` and `reset` had NO tests at all. Both kept scanning
unprefixed `hermes-*` names after agent volumes moved to
`<project>_hermes-<u>-home`, so they matched only the stale rollback copies
and reported every developer as having no volume while the live data was
intact. Re-review confirmed that reverting either fix left the whole suite
green, so the fix was recorded as verified when nothing could detect its
reversal. These are those tests.
"""

from unittest.mock import patch

from typer.testing import CliRunner

from dev_administration import cli

runner = CliRunner()

DEVS_YAML = """developers:
- username: juan
  display_name: Juan
  forgejo_user: juan
"""


def _write_devs(tmp_path):
    path = tmp_path / "developers.yaml"
    path.write_text(DEVS_YAML)
    return path


def test_status_reports_the_project_scoped_volume(tmp_path, monkeypatch):
    """The regression that motivated this file.

    A `hermes-` prefix scan matches `hermes-juan-home` (the rollback copy)
    but NOT `aurora_hermes-juan-home` (the live one), so status rendered
    the live volume as absent.
    """
    monkeypatch.setenv("DEVELOPERS_YAML", str(_write_devs(tmp_path)))

    with patch("dev_administration.cli.current_project", return_value="aurora"), \
         patch("dev_administration.cli.project_services",
               return_value={"hermes-juan": "hermes-juan"}), \
         patch("dev_administration.cli.list_volumes",
               return_value=["aurora_hermes-juan-home"]) as mock_volumes, \
         patch("dev_administration.cli.container_status", return_value="running"):
        result = runner.invoke(cli.app, ["status"])

    assert result.exit_code == 0, result.output
    # Queried under the project prefix, not the bare agent prefix.
    mock_volumes.assert_called_once_with("aurora_hermes-")
    assert "aurora_hermes-juan-home" in result.output
    assert "hermes-juan" in result.output
    assert "running" in result.output


def test_status_does_not_scan_containers_across_the_whole_daemon(tmp_path, monkeypatch):
    """`list_containers("hermes-")` was a global name scan, so a branch's
    `dev-admin status` listed PRODUCTION's agents -- the cross-project
    disclosure §5.3 exists to stop. Resolution must go through the project
    label instead."""
    monkeypatch.setenv("DEVELOPERS_YAML", str(_write_devs(tmp_path)))

    # Patched at the DEFINITION site, not on the cli module. An earlier
    # version asserted `not hasattr(cli, "list_containers")`, which only
    # describes how the name happens to be imported: re-adding the scan as
    # `docker_utils.list_containers(...)` or `import ... as _scan_all` left
    # that assertion true and the daemon-wide scan back in place. Exploding
    # at the definition catches every spelling.
    def _forbidden(*args, **kwargs):
        raise AssertionError(
            "status scanned container names across the whole daemon; a "
            "branch would list production's agents (spec 5.3)"
        )

    with patch("dev_administration.cli.current_project", return_value="br-demo"), \
         patch("dev_administration.cli.project_services", return_value={}) as mock_services, \
         patch("dev_administration.docker_utils.list_containers", _forbidden), \
         patch("dev_administration.cli.list_volumes", return_value=[]), \
         patch("dev_administration.cli.container_status", return_value=None):
        result = runner.invoke(cli.app, ["status"])

    assert result.exit_code == 0, result.output
    mock_services.assert_called_once_with("br-demo")


def test_status_renders_a_developer_with_neither_container_nor_volume(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVELOPERS_YAML", str(_write_devs(tmp_path)))

    with patch("dev_administration.cli.current_project", return_value="aurora"), \
         patch("dev_administration.cli.project_services", return_value={}), \
         patch("dev_administration.cli.list_volumes", return_value=[]), \
         patch("dev_administration.cli.container_status", return_value=None):
        result = runner.invoke(cli.app, ["status"])

    assert result.exit_code == 0, result.output
    assert "juan" in result.output


def test_status_lists_only_project_scoped_orphans(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVELOPERS_YAML", str(_write_devs(tmp_path)))

    with patch("dev_administration.cli.current_project", return_value="aurora"), \
         patch("dev_administration.cli.project_services", return_value={}), \
         patch("dev_administration.cli.list_volumes",
               return_value=["aurora_hermes-juan-home",
                             "aurora_hermes-ghost-home"]), \
         patch("dev_administration.cli.container_status", return_value=None):
        result = runner.invoke(cli.app, ["status"])

    assert result.exit_code == 0, result.output
    assert "aurora_hermes-ghost-home" in result.output
    assert "(orphaned)" in result.output


def test_reset_resolves_its_container_and_volume_through_the_project(tmp_path, monkeypatch):
    """`reset` named both by convention. The container name gave the §5.3
    guard nothing it could prove was ours, and the volume name pointed at the
    rollback copy, so it reported "preserved" about a volume reconcile will
    never touch again."""
    for key, value in {
        "FORGEJO_URL": "https://example.invalid/git",
        "FORGEJO_ADMIN_TOKEN": "t",
        "AURORA_PROFILE_URL": "https://example.invalid/git/a/b.git",
        "DOMAIN_NAME": "example.invalid",
    }.items():
        monkeypatch.setenv(key, value)

    # The resolved container name deliberately DIFFERS from the guessed one.
    # With container_name: !reset null (spec 4.2) a branch's agent is named
    # br-demo-hermes-juan-1, not hermes-juan -- so asserting on "hermes-juan"
    # would pass under both the fix and the bug, which is exactly what let
    # the guessed-name version survive mutation.
    with patch("dev_administration.provision.current_project", return_value="aurora"), \
         patch("dev_administration.cli.project_services",
               return_value={"hermes-juan": "br-demo-hermes-juan-1"}), \
         patch("dev_administration.cli.stop_and_remove_container") as mock_stop, \
         patch("dev_administration.cli.find_oauth2_app", return_value=None), \
         patch("dev_administration.cli.volume_exists", return_value=True) as mock_vol, \
         patch("dev_administration.cli.user_exists", return_value=False):
        result = runner.invoke(cli.app, ["reset", "juan"])

    assert result.exit_code == 0, result.output
    mock_stop.assert_called_once_with("br-demo-hermes-juan-1")
    mock_vol.assert_called_once_with("aurora_hermes-juan-home")
    assert "aurora_hermes-juan-home" in result.output


def test_render_agents_ignores_the_environment(tmp_path, monkeypatch):
    """The tracked fragment must be a pure function of developers.yaml.

    Three readers have to agree on it byte-for-byte: this renderer, the drift
    test, and reconcile's compose.stale check. Any environment input makes
    them disagree -- AGENT_UPSTREAM_MODE=service rewrote it to the no-ports
    variant, and AGENT_BASE_PORT shifted the ports so `render-agents --check`
    said "stale" while the drift test said "fine".
    """
    monkeypatch.setenv("DEVELOPERS_YAML", str(_write_devs(tmp_path)))
    monkeypatch.setenv("AGENT_UPSTREAM_MODE", "service")
    monkeypatch.setenv("AGENT_BASE_PORT", "9200")

    out = tmp_path / "compose.agents.yml"
    result = runner.invoke(cli.app, ["render-agents", "--output", str(out)])

    assert result.exit_code == 0, result.output
    body = out.read_text()
    assert "127.0.0.1:9120:9119" in body, (
        "render-agents honoured the environment; the tracked fragment is no "
        "longer a pure function of developers.yaml"
    )
