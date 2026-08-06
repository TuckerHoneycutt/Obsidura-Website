from unittest.mock import MagicMock, patch

import pytest

from dev_administration.project import (
    ProjectMismatch,
    agent_volume,
    assert_same_project,
    container_project,
    current_project,
    find_service_container,
    network_name,
    project_services,
)


def _completed(stdout: str = "", returncode: int = 0):
    return MagicMock(returncode=returncode, stdout=stdout, stderr="")


@patch("dev_administration.project.Path")
@patch("dev_administration.project.subprocess.run")
def test_current_project_prefers_self_inspection(mock_run, mock_path):
    """The container's own label cannot be stale. COMPOSE_PROJECT_NAME can:
    spec §4.1 renders a branch's .env FROM production's, so a failed
    override would silently point a branch operation at production."""
    mock_path.return_value.read_text.return_value = "7692288ed82b\n"
    mock_run.return_value = _completed("br-demo\n")
    with patch.dict("os.environ", {"COMPOSE_PROJECT_NAME": "aurora"}):
        assert current_project() == "br-demo"
    # Self-inspection must read the file Docker actually mounts with the
    # container's own ID — not some other path that would silently make
    # this fall through to (possibly stale) COMPOSE_PROJECT_NAME instead.
    mock_path.assert_called_once_with("/etc/hostname")


@patch("dev_administration.project.Path")
@patch("dev_administration.project.subprocess.run")
def test_current_project_falls_back_to_env_outside_a_container(mock_run, mock_path):
    mock_path.return_value.read_text.side_effect = OSError
    with patch.dict("os.environ", {"COMPOSE_PROJECT_NAME": "br-demo"}):
        assert current_project() == "br-demo"
    mock_path.assert_called_once_with("/etc/hostname")


@patch("dev_administration.project.Path")
@patch("dev_administration.project.subprocess.run")
def test_current_project_refuses_to_guess(mock_run, mock_path):
    mock_path.return_value.read_text.side_effect = OSError
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ProjectMismatch) as exc:
            current_project()
    assert "COMPOSE_PROJECT_NAME" in str(exc.value)
    mock_path.assert_called_once_with("/etc/hostname")


@patch("dev_administration.project.current_project", return_value="br-demo")
def test_network_name_is_derived(_cp):
    assert network_name() == "br-demo_default"
    assert network_name("aurora") == "aurora_default"


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
def test_assert_same_project_allows_own_project(mock_run, _cp):
    mock_run.return_value = _completed("br-demo\n")
    assert_same_project("br-demo-caddy-1")  # must not raise


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
def test_assert_same_project_refuses_another_project(mock_run, _cp):
    """The single most important safety assertion in the build: a
    branch-context operation aimed at production's Caddy must refuse."""
    mock_run.return_value = _completed("aurora\n")
    with pytest.raises(ProjectMismatch) as exc:
        assert_same_project("aurora-caddy-1")
    message = str(exc.value)
    assert "aurora-caddy-1" in message
    assert "aurora" in message
    assert "br-demo" in message


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
def test_assert_same_project_refuses_a_sibling_branch(mock_run, _cp):
    """Fixture names elsewhere in this file (br-demo vs aurora) are
    maximally dissimilar and would still pass under a loosened, e.g.
    case-insensitive-substring, comparison. Sibling branch stacks all share
    the `br-` prefix once Chunk 2 lands, so `br-demo` vs `br-demo-2` is the
    realistic near-miss a substring check would wrongly allow."""
    mock_run.return_value = _completed("br-demo-2\n")
    with pytest.raises(ProjectMismatch):
        assert_same_project("br-demo-2-caddy-1")


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
def test_assert_same_project_refuses_an_unlabelled_container(mock_run, _cp):
    """An unlabelled container belongs to no project, so it can never be
    proven safe. Refusing is the only correct answer — and this is exactly
    the shape the imperative `docker run` dev agents had."""
    mock_run.return_value = _completed("\n")
    with pytest.raises(ProjectMismatch):
        assert_same_project("hermes-testuser")


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
def test_assert_same_project_refuses_a_missing_container(mock_run, _cp):
    mock_run.return_value = _completed("", returncode=1)
    with pytest.raises(ProjectMismatch):
        assert_same_project("does-not-exist")


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
def test_find_service_container_resolves_by_label(mock_run, _cp):
    """This replaces CADDY_CONTAINER=aurora-caddy-1: the Caddy container
    is whichever container carries THIS project's label and the `caddy`
    service label, whatever it happens to be named. Also excludes one-off
    containers: they can carry the same project+service label pair as the
    long-running service without being it."""
    mock_run.return_value = _completed("caddy\tbr-demo-caddy-1\trunning\n")
    assert find_service_container("caddy") == "br-demo-caddy-1"
    args = mock_run.call_args[0][0]
    assert "label=com.docker.compose.project=br-demo" in args
    assert "label=com.docker.compose.oneoff=False" in args
    assert "-a" in args


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
def test_find_service_container_returns_stopped_container_when_none_running(mock_run, _cp):
    """Before `docker compose up` for a fresh branch, or after a stop,
    nothing is running yet, but reconcile may still need to name a stopped
    container (e.g. to remove it)."""
    mock_run.return_value = _completed("caddy\tbr-demo-caddy-1\texited\n")
    assert find_service_container("caddy") == "br-demo-caddy-1"


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
def test_find_service_container_refuses_when_ambiguous(mock_run, _cp):
    """`docker ps` ordering (newest-first) is not a contract worth betting
    production safety on. Two equally-preferred (here: both running)
    containers claiming the same service label must never be silently
    disambiguated by picking list order."""
    mock_run.return_value = _completed(
        "caddy\tbr-demo-caddy-1\trunning\ncaddy\tbr-demo-caddy-2\trunning\n"
    )
    with pytest.raises(ProjectMismatch):
        find_service_container("caddy")


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
def test_find_service_container_raises_when_absent(mock_run, _cp):
    mock_run.return_value = _completed("\n")
    with pytest.raises(ProjectMismatch):
        find_service_container("caddy")


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
def test_find_service_container_and_project_services_agree_when_newest_is_stopped(
    mock_run, _cp
):
    """The axis a first fix round missed: a crash-looped recreate leaves a
    newer container exited and an older one still running. `docker ps`
    lists newest-first, so naive "first match" logic picks the newer, dead
    one. find_service_container() and project_services() now derive their
    candidate set from the same _project_containers()/_pick_service_container()
    helpers, so they must agree — a running preference implemented on only
    one side is exactly how a cp-then-exec caller (Task 4's Caddy reload)
    ends up targeting two different containers for the same service."""
    mock_run.return_value = _completed(
        "caddy\tbr-demo-caddy-1-b\texited\ncaddy\tbr-demo-caddy-1-a\trunning\n"
    )
    assert find_service_container("caddy") == "br-demo-caddy-1-a"
    assert project_services()["caddy"] == "br-demo-caddy-1-a"


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
def test_project_services_maps_service_to_container(mock_run, _cp):
    mock_run.return_value = _completed(
        "caddy\tbr-demo-caddy-1\trunning\nhermes-juan\tbr-demo-hermes-juan-1\trunning\n"
    )
    assert project_services() == {
        "caddy": "br-demo-caddy-1",
        "hermes-juan": "br-demo-hermes-juan-1",
    }


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
def test_project_services_keeps_running_over_stopped_leftover(mock_run, _cp):
    """A stopped leftover sharing a service label with its live replacement
    must not silently overwrite the live one in the map — and, since
    project_services() and find_service_container() now share the same
    selection helper, this is enforced in exactly one place for both."""
    mock_run.return_value = _completed(
        "caddy\tbr-demo-caddy-1\trunning\ncaddy\tbr-demo-caddy-1-old\texited\n"
    )
    assert project_services()["caddy"] == "br-demo-caddy-1"


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
def test_project_services_refuses_when_ambiguous(mock_run, _cp):
    """project_services() shares find_service_container()'s selection rule
    by construction: two equally-preferred containers for the same service
    must refuse here too, not just in find_service_container()."""
    mock_run.return_value = _completed(
        "caddy\tbr-demo-caddy-1\trunning\ncaddy\tbr-demo-caddy-2\trunning\n"
    )
    with pytest.raises(ProjectMismatch):
        project_services()


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.project.subprocess.run")
def test_project_services_fails_closed_on_docker_error(mock_run, _cp):
    """Every other function in this module fails closed on a Docker error.
    An empty {} here would make "Docker is unreachable" and "this project
    has no services" indistinguishable — the one silent-permissive shape
    in the module."""
    mock_run.return_value = _completed("", returncode=1)
    with pytest.raises(ProjectMismatch):
        project_services()


@patch("dev_administration.project.current_project", return_value="br-demo")
def test_agent_volume_is_project_scoped(_cp):
    """An unprefixed volume name is reachable from every project on the
    host — precisely how a branch would write into production's agent
    state. Compose namespaces them; so must we when we name one directly."""
    assert agent_volume("juan") == "br-demo_hermes-juan-home"
    assert agent_volume("juan", "aurora") == "aurora_hermes-juan-home"


@patch("dev_administration.project.subprocess.run")
def test_container_project_returns_none_for_unlabelled(mock_run):
    mock_run.return_value = _completed("\n")
    assert container_project("whatever") is None
    # Pin the exact command: subprocess.run is mocked, so a mutated
    # subcommand (e.g. "docker inspect" -> "docker bogus-subcommand") would
    # still return this same canned result and this test would still pass
    # without this assertion — it is the only thing that can tell "we asked
    # docker inspect and it said no label" from "we never really asked."
    args = mock_run.call_args[0][0]
    assert args == [
        "docker", "inspect", "-f",
        '{{index .Config.Labels "com.docker.compose.project"}}',
        "whatever",
    ]


@patch("dev_administration.project.subprocess.run")
def test_container_project_returns_none_on_docker_failure(mock_run):
    """A nonzero exit (missing container, daemon hiccup) must return None,
    not raise and not fabricate a project — callers (current_project,
    assert_same_project) decide what "unknown" means for them."""
    mock_run.return_value = _completed("", returncode=1)
    assert container_project("does-not-exist") is None
