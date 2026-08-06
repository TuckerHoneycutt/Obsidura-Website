import subprocess
from unittest.mock import patch, MagicMock

import pytest
from dev_administration.forgejo_utils import (
    CURL_EXIT_TIMEOUT, _curl, create_oauth2_app, find_oauth2_app,
    delete_oauth2_app,
)


@patch("dev_administration.forgejo_utils.subprocess.run")
def test_create_oauth2_app(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout='{"id": 1, "client_id": "abc123", "client_secret": "secret456"}',
    )
    client_id, client_secret = create_oauth2_app(
        "https://forgejo.example.com/git",
        "admin-token",
        "hermes-juan",
        "https://forgejo.example.com/git/agent/juan/auth/callback",
    )
    assert client_id == "abc123"
    assert client_secret == "secret456"


@patch("dev_administration.forgejo_utils.subprocess.run")
def test_find_oauth2_app_exists(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout='[{"id": 1, "name": "hermes-juan"}, {"id": 2, "name": "hermes-ethan"}]',
    )
    app_id = find_oauth2_app(
        "https://forgejo.example.com/git",
        "admin-token",
        "hermes-juan",
    )
    assert app_id == 1


@patch("dev_administration.forgejo_utils.subprocess.run")
def test_find_oauth2_app_not_found(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout='[{"id": 1, "name": "hermes-ethan"}]',
    )
    app_id = find_oauth2_app(
        "https://forgejo.example.com/git",
        "admin-token",
        "hermes-juan",
    )
    assert app_id is None


@patch("dev_administration.forgejo_utils.subprocess.run")
def test_delete_oauth2_app(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="")
    delete_oauth2_app(
        "https://forgejo.example.com/git",
        "admin-token",
        1,
    )
    mock_run.assert_called_once()


def _fail(code):
    return subprocess.CalledProcessError(code, ["curl"], output="", stderr="")


@patch("dev_administration.forgejo_utils.time.sleep")
@patch("dev_administration.forgejo_utils.subprocess.run")
def test_curl_retries_a_connection_refusal_then_succeeds(mock_run, _sleep):
    """dev-admin reaches Forgejo THROUGH Caddy, so a Caddy recreate window
    produces the same failure no Forgejo healthcheck can gate."""
    mock_run.side_effect = [
        _fail(7), _fail(7), MagicMock(returncode=0, stdout='{"ok": true}'),
    ]
    assert _curl("http://x/api", "tok") == {"ok": True}
    assert mock_run.call_count == 3


@patch("dev_administration.forgejo_utils.time.sleep")
@patch("dev_administration.forgejo_utils.subprocess.run")
def test_curl_does_not_retry_a_real_http_error(mock_run, _sleep):
    """A 404 or 401 is an answer, not an outage. Retrying it six times turns
    a clear error into a slow, confusing one -- and this is the exact exit
    code (22) the live failure produced, so retrying it would have masked a
    genuine auth problem behind a minute of silence."""
    mock_run.side_effect = _fail(22)
    with pytest.raises(subprocess.CalledProcessError):
        _curl("http://x/api", "tok")
    assert mock_run.call_count == 1


@patch("dev_administration.forgejo_utils.time.sleep")
@patch("dev_administration.forgejo_utils.subprocess.run")
def test_curl_gives_up_after_the_attempt_budget(mock_run, _sleep):
    mock_run.side_effect = _fail(7)
    with pytest.raises(subprocess.CalledProcessError):
        _curl("http://x/api", "tok", attempts=4)
    assert mock_run.call_count == 4


@patch("dev_administration.forgejo_utils.time.sleep")
@patch("dev_administration.forgejo_utils.subprocess.run")
def test_curl_backs_off_between_attempts(mock_run, mock_sleep):
    """Not in the brief. A retry loop with no delay burns its whole budget
    inside a few milliseconds and cannot outlast a container start, which
    would make the retry look present while being useless."""
    mock_run.side_effect = _fail(7)
    with pytest.raises(subprocess.CalledProcessError):
        _curl("http://x/api", "tok", attempts=3, backoff=2.0)
    assert [c[0][0] for c in mock_sleep.call_args_list] == [2.0, 4.0]


def test_curl_retry_defaults_are_actually_useful():
    """Pins the SIGNATURE defaults, not just behaviour under explicit args.

    Every other retry test passes attempts/backoff explicitly, so changing
    the defaults to attempts=1 or backoff=0.0 left them all green while
    collapsing the entire production retry to milliseconds -- verbatim the
    failure test_curl_backs_off_between_attempts says it prevents. Production
    never passes these arguments, so the defaults ARE the behaviour.
    """
    import inspect

    defaults = {
        name: param.default
        for name, param in inspect.signature(_curl).parameters.items()
    }
    assert defaults["attempts"] >= 4, (
        f"attempts default is {defaults['attempts']}; too few to outlast a "
        "container start"
    )
    assert defaults["backoff"] >= 1.0, (
        f"backoff default is {defaults['backoff']}; a retry loop with no "
        "delay burns its budget in milliseconds and cannot outlast a "
        "container start"
    )


@patch("dev_administration.forgejo_utils.time.sleep")
@patch("dev_administration.forgejo_utils.subprocess.run")
def test_forgejo_org_helpers_catch_a_failed_call_rather_than_exploding(mock_run, _sleep):
    """forgejo_org shares forgejo_utils._curl and must still CATCH its errors.

    forgejo_org used to carry its own byte-for-byte copy of the un-hardened
    _curl, so Task 11's retry did not cover reconcile's FIRST Forgejo calls
    (ensure_org / ensure_team / add_team_repo). De-duplicating it removed the
    module's `import subprocess` -- which does not break the import, because
    the name is only resolved when a handler runs. Every
    `except subprocess.CalledProcessError:` in the module would then raise
    NameError instead of catching, and reconcile's broad `except Exception`
    would have swallowed that as a warning. The suite stayed green; only a
    grep caught it.

    This pins the behaviour rather than the import: a failed call must
    return a value, not propagate.
    """
    from dev_administration import forgejo_org

    mock_run.side_effect = subprocess.CalledProcessError(7, ["curl"])
    assert forgejo_org.user_exists("http://x/git", "tok", "bob") is False


def test_there_is_exactly_one_curl_implementation():
    """Two copies drifted once and cost the startup-race fix its coverage."""
    import inspect

    from dev_administration import forgejo_org, forgejo_utils

    assert forgejo_org._curl is forgejo_utils._curl, (
        "forgejo_org has its own _curl again; reconcile's first Forgejo "
        "calls would bypass the startup-race retry"
    )
    assert "def _curl" not in inspect.getsource(forgejo_org), (
        "forgejo_org defines _curl locally"
    )


# ---------------------------------------------------------------------------
# _curl is bounded (2026-07-31)
# ---------------------------------------------------------------------------


@patch("dev_administration.forgejo_utils.subprocess.run")
def test_curl_is_bounded_in_time(mock_run):
    """`curl` has no default timeout, so an unbounded call can hang forever.

    reconcile calls the Forgejo API on the branch's PUBLIC hostname from a
    container that is not in the tailscale sidecar's network namespace. When
    that hostname stopped resolving to the branch, the first attempt hung
    indefinitely: the retry loop never ran, and exit 28 sat in the transient
    set waiting for a timeout that could not arrive.
    """
    mock_run.return_value = MagicMock(returncode=0, stdout="{}")
    _curl("https://example.invalid/api", "tok")

    cmd = mock_run.call_args[0][0]
    assert "--max-time" in cmd, cmd
    assert "--connect-timeout" in cmd, cmd
    # and the process itself cannot outlive curl's own budget
    assert mock_run.call_args[1].get("timeout") is not None, (
        "subprocess.run was given no timeout"
    )


@patch("dev_administration.forgejo_utils.time.sleep")
@patch("dev_administration.forgejo_utils.subprocess.run")
def test_a_hanging_curl_is_retried_then_surfaces(mock_run, _sleep):
    """A wedged curl must take the connection-class path, not escape as a
    TimeoutExpired that no caller catches."""
    mock_run.side_effect = subprocess.TimeoutExpired(["curl"], 1)
    with pytest.raises(subprocess.CalledProcessError) as raised:
        _curl("https://example.invalid/api", "tok", attempts=3)
    assert mock_run.call_count == 3
    assert raised.value.returncode == CURL_EXIT_TIMEOUT, raised.value.returncode


@patch("dev_administration.forgejo_utils.time.sleep")
@patch("dev_administration.forgejo_utils.subprocess.run")
def test_a_post_is_not_retried_once_it_may_have_been_delivered(mock_run, _sleep):
    """A timeout can fire AFTER Forgejo processed the request. Retrying the
    OAuth2-app POST then registers a SECOND app, and the client_id the caller
    keeps no longer matches the secret Forgejo stored."""
    mock_run.side_effect = subprocess.TimeoutExpired(["curl"], 1)
    with pytest.raises(subprocess.CalledProcessError):
        _curl("http://x/api", "tok", method="POST", data={"name": "x"}, attempts=6)
    assert mock_run.call_count == 1, (
        f"the POST was sent {mock_run.call_count} times; a duplicate OAuth2 "
        "app is not recoverable"
    )
