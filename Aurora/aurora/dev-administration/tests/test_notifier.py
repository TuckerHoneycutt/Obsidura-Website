from dev_administration.models import OrchestratorEvent
from dev_administration.notifier import StdoutNotifier, FileNotifier, get_notifier


def _make_event(event_type="developer.provisioned", developer="juan"):
    return OrchestratorEvent(
        timestamp="2026-07-25T00:00:00Z",
        event_type=event_type,
        severity="info",
        developer=developer,
        message="Test event",
        metadata={"container": "hermes-juan"},
    )


def test_stdout_notifier_does_not_raise(capsys):
    notifier = StdoutNotifier()
    notifier.notify(_make_event())
    captured = capsys.readouterr()
    assert "developer.provisioned" in captured.out
    assert "juan" in captured.out


def test_file_notifier_writes_to_file(tmp_path):
    log_path = tmp_path / "events.log"
    notifier = FileNotifier(path=str(log_path))
    notifier.notify(_make_event())
    notifier.notify(_make_event(event_type="container.stopped", developer="ethan"))
    content = log_path.read_text()
    assert "developer.provisioned" in content
    assert "container.stopped" in content
    assert "juan" in content
    assert "ethan" in content


def test_get_notifier_returns_stdout():
    notifier = get_notifier("stdout")
    assert isinstance(notifier, StdoutNotifier)


def test_get_notifier_returns_file(tmp_path):
    notifier = get_notifier("file", path=str(tmp_path / "events.log"))
    assert isinstance(notifier, FileNotifier)
