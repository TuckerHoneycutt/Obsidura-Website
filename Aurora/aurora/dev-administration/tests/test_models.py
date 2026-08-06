from pathlib import Path
from dev_administration.models import DeveloperConfig, OrchestratorEvent, parse_developers_yaml


def test_developer_config_fields():
    dev = DeveloperConfig(username="juan", display_name="Juan Martinez", forgejo_user="juan")
    assert dev.username == "juan"
    assert dev.display_name == "Juan Martinez"
    assert dev.forgejo_user == "juan"


def test_parse_developers_yaml(tmp_path):
    yaml_content = """
developers:
  - username: juan
    display_name: Juan Martinez
    forgejo_user: juan
  - username: ethan
    display_name: Ethan Pascuales
    forgejo_user: supergoodname77
"""
    path = tmp_path / "developers.yaml"
    path.write_text(yaml_content)
    devs = parse_developers_yaml(path)
    assert len(devs) == 2
    assert devs[0].username == "juan"
    assert devs[1].forgejo_user == "supergoodname77"


def test_parse_empty_developers_yaml(tmp_path):
    path = tmp_path / "developers.yaml"
    path.write_text("developers: []\n")
    devs = parse_developers_yaml(path)
    assert devs == []


def test_orchestrator_event_fields():
    event = OrchestratorEvent(
        timestamp="2026-07-25T00:00:00Z",
        event_type="developer.provisioned",
        severity="info",
        developer="juan",
        message="Provisioned container hermes-juan",
        metadata={"container": "hermes-juan", "volume": "hermes-juan-home"},
    )
    assert event.event_type == "developer.provisioned"
    assert event.metadata["container"] == "hermes-juan"
