from __future__ import annotations

import json
from typing import Protocol

from dev_administration.models import OrchestratorEvent


class Notifier(Protocol):
    def notify(self, event: OrchestratorEvent) -> None: ...


class StdoutNotifier:
    def notify(self, event: OrchestratorEvent) -> None:
        print(
            f"[{event.timestamp}] {event.severity.upper()} "
            f"{event.event_type} developer={event.developer} "
            f"{event.message}"
        )


class FileNotifier:
    def __init__(self, path: str):
        self._path = path

    def notify(self, event: OrchestratorEvent) -> None:
        line = json.dumps({
            "timestamp": event.timestamp,
            "event_type": event.event_type,
            "severity": event.severity,
            "developer": event.developer,
            "message": event.message,
            "metadata": event.metadata,
        })
        with open(self._path, "a") as f:
            f.write(line + "\n")


def get_notifier(name: str, **kwargs) -> Notifier:
    if name == "stdout":
        return StdoutNotifier()
    elif name == "file":
        return FileNotifier(**kwargs)
    else:
        raise ValueError(f"Unknown notifier: {name}")
