from unittest.mock import patch, MagicMock

import pytest

from dev_administration.docker_utils import (
    volume_exists, create_volume, container_exists,
    list_containers, list_volumes, stop_and_remove_container,
)


@patch("dev_administration.docker_utils.subprocess.run")
def test_volume_exists_true(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    assert volume_exists("hermes-juan-home") is True


@patch("dev_administration.docker_utils.subprocess.run")
def test_volume_exists_false(mock_run):
    mock_run.return_value = MagicMock(returncode=1)
    assert volume_exists("hermes-juan-home") is False


@patch("dev_administration.docker_utils.current_project", return_value="aurora")
@patch("dev_administration.docker_utils.subprocess.run")
def test_create_volume_applies_compose_labels(mock_run, _cp):
    """Compose adopts a pre-existing volume carrying its project and volume
    labels, preserving contents (probed on Compose v5.3.1). Without the
    labels it treats the volume as foreign."""
    mock_run.return_value = MagicMock(returncode=0)
    create_volume("aurora_hermes-juan-home")
    args = mock_run.call_args[0][0]
    assert args[:3] == ["docker", "volume", "create"]
    assert "com.docker.compose.project=aurora" in args
    assert "com.docker.compose.volume=hermes-juan-home" in args
    assert args[-1] == "aurora_hermes-juan-home"


@patch("dev_administration.docker_utils.current_project", return_value="br-demo")
@patch("dev_administration.docker_utils.subprocess.run")
def test_create_volume_refuses_an_unprefixed_name(mock_run, _cp):
    from dev_administration.project import ProjectMismatch
    with pytest.raises(ProjectMismatch):
        create_volume("hermes-juan-home")
    mock_run.assert_not_called()


@patch("dev_administration.docker_utils.subprocess.run")
def test_container_exists_true(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    assert container_exists("hermes-juan") is True


@patch("dev_administration.docker_utils.subprocess.run")
def test_container_exists_false(mock_run):
    mock_run.return_value = MagicMock(returncode=1)
    assert container_exists("hermes-juan") is False


@patch("dev_administration.docker_utils.subprocess.run")
def test_list_containers(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="hermes-juan\nhermes-ethan\n",
    )
    result = list_containers("hermes-")
    assert result == ["hermes-juan", "hermes-ethan"]


@patch("dev_administration.docker_utils.subprocess.run")
def test_list_volumes(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="hermes-juan-home\nhermes-ethan-home\n",
    )
    result = list_volumes("hermes-")
    assert result == ["hermes-juan-home", "hermes-ethan-home"]


def _subprocess_router(container_label: str):
    """One side_effect serving both modules.

    `dev_administration.project.subprocess` and
    `dev_administration.docker_utils.subprocess` are the SAME module object,
    so patching both dotted paths does NOT yield two independent mocks --
    whichever patch is applied last simply wins, and the guard then reads a
    bare MagicMock as the container's project label. Route on argv instead.
    """
    def _fake(cmd, *args, **kwargs):
        if cmd[:2] == ["docker", "inspect"]:
            return MagicMock(returncode=0, stdout=f"{container_label}\n")
        return MagicMock(returncode=0)
    return _fake


def _mutations(mock_run):
    """Commands issued that are not the guard's read-only inspect."""
    return [
        call[0][0] for call in mock_run.call_args_list
        if call[0][0][:2] != ["docker", "inspect"]
    ]


@patch("dev_administration.project.current_project", return_value="aurora")
@patch("dev_administration.docker_utils.subprocess.run")
def test_stop_and_remove_container_stops_then_removes(mock_run, _cp):
    mock_run.side_effect = _subprocess_router("aurora")
    stop_and_remove_container("hermes-juan")
    assert [m[:2] for m in _mutations(mock_run)] == [
        ["docker", "stop"], ["docker", "rm"],
    ]


@patch("dev_administration.project.current_project", return_value="br-demo")
@patch("dev_administration.docker_utils.subprocess.run")
def test_stop_and_remove_container_refuses_another_project(mock_run, _cp):
    """Spec 5.3's headline case at the docker_utils layer: a branch-context
    teardown aimed at a production container must issue NO mutation at all."""
    from dev_administration.project import ProjectMismatch
    mock_run.side_effect = _subprocess_router("aurora")
    with pytest.raises(ProjectMismatch):
        stop_and_remove_container("aurora-caddy-1")
    assert _mutations(mock_run) == []
