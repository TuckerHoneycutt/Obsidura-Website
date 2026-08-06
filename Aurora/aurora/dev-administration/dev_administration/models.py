from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class DeveloperConfig:
    username: str
    display_name: str
    forgejo_user: str
    # Dropped by parse_developers_yaml until 2026-07-31, which is why
    # `dev-admin provision --email` never reached the Forgejo account.
    email: str = ""


@dataclass
class OrchestratorEvent:
    timestamp: str
    event_type: str
    severity: str
    developer: str | None
    message: str
    metadata: dict = field(default_factory=dict)


def parse_developers_yaml(path: Path) -> list[DeveloperConfig]:
    """Parse developers.yaml into a list of DeveloperConfig."""
    data = yaml.safe_load(path.read_text())
    raw_devs = data.get("developers", []) if data else []
    return [
        DeveloperConfig(
            username=d["username"],
            display_name=d.get("display_name", d["username"]),
            forgejo_user=d.get("forgejo_user", d["username"]),
            email=d.get("email", ""),
        )
        for d in raw_devs
    ]
