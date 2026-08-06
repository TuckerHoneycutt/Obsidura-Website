from __future__ import annotations

import base64
import json
import subprocess
import time

CURL_EXIT_TIMEOUT = 28              # operation timed out
_SUBPROCESS_GRACE = 5.0             # seconds curl gets to exit after its own --max-time

#: curl exits meaning "the far end was not ready", as opposed to "the far end
#: answered and the answer was an error". A 401 or 404 arrives as exit 22, an
#: HTTP status, and retrying an answer six times turns a clear failure into a
#: slow, confusing one.
#: 6 could not resolve host / 7 failed to connect / 35 SSL connect error /
#: 52 empty reply / 56 failure receiving network data.
_TRANSIENT_CURL_EXITS = frozenset({6, 7, CURL_EXIT_TIMEOUT, 35, 52, 56})

#: Exits that prove the request was never delivered. Only these may be retried
#: for a non-idempotent method -- a retried POST creates a second object.
_PRE_SEND_CURL_EXITS = frozenset({6, 7, 35})

#: Methods a second identical request cannot damage.
_IDEMPOTENT_METHODS = frozenset({"GET", "DELETE"})

#: Forgejo's built-in local account database. `source_id` selects the auth
#: source (non-zero is an external LDAP/OAuth one), and both POST /admin/users
#: and PATCH /admin/users/{u} require it even when unchanged -- omitting it is
#: a 422 that reads like a permission error.
LOCAL_AUTH_SOURCE_ID = 0


def _curl(
    url: str,
    token: str,
    method: str = "GET",
    data: dict | None = None,
    attempts: int = 6,
    backoff: float = 2.0,
    basic: tuple[str, str] | None = None,
    connect_timeout: float = 5.0,
    max_time: float = 30.0,
) -> dict | list | None:
    """Call the Forgejo API, retrying only connection-class failures.

    dev-admin reaches Forgejo through Caddy, so this survives a Caddy recreate
    window as well as a Forgejo that is up but not yet serving.

    Bounded on both sides -- `--max-time` for curl's own work, `timeout=` for
    the process -- because curl has no default timeout of any kind, and an
    unbounded first attempt hangs forever with the retry loop never running
    (measured once against a branch hostname that stopped resolving). Exit 22
    is an HTTP status, i.e. an answer, so it is never retried; nor is anything
    outside `_PRE_SEND_CURL_EXITS` for a non-idempotent method.

    `basic` is required by POST/DELETE /users/{u}/tokens, which answer 401
    "auth method not allowed" to a bearer token (Gitea's `reqBasicAuth`).
    """
    cmd = [
        "curl", "-fsS",
        "--connect-timeout", str(connect_timeout),
        "--max-time", str(max_time),
        "-X", method,
        url,
    ]
    if basic is not None:
        auth = "Basic " + base64.b64encode(("%s:%s" % basic).encode()).decode()
    else:
        auth = "token " + token
    # Never in argv: argv is world-readable via `ps`, and subprocess copies it
    # into CalledProcessError.cmd, so it reappears in every traceback. base64
    # also needs no escaping -- its alphabet contains no `"`, `\` or newline,
    # and curl's config parser is line-oriented, so a password containing one
    # would otherwise inject arbitrary curl options.
    config = 'header = "Authorization: %s"\n' % auth
    cmd.extend(["-K", "-", "-H", "Content-Type: application/json"])
    if data:
        cmd.extend(["-d", json.dumps(data)])

    # A timeout can fire AFTER Forgejo processed the request, so retrying one
    # on a POST would register a second OAuth2 app whose secret nothing holds.
    retryable = (
        _TRANSIENT_CURL_EXITS if method.upper() in _IDEMPOTENT_METHODS
        else _PRE_SEND_CURL_EXITS
    )

    last: subprocess.CalledProcessError | None = None
    for attempt in range(attempts):
        try:
            result = subprocess.run(
                cmd, input=config, capture_output=True, text=True, check=True,
                timeout=max_time + connect_timeout + _SUBPROCESS_GRACE,
            )
        except subprocess.TimeoutExpired as exc:
            # curl outlived its own --max-time: the connection-class failure
            # exit 28 names, so surfaced and handled as exactly that.
            last = subprocess.CalledProcessError(CURL_EXIT_TIMEOUT, cmd, "", str(exc))
        except subprocess.CalledProcessError as exc:
            last = exc
        else:
            return json.loads(result.stdout) if result.stdout.strip() else None
        if last.returncode not in retryable:
            raise last
        if attempt + 1 < attempts:
            time.sleep(backoff * (attempt + 1))

    assert last is not None
    raise last


def create_oauth2_app(
    forgejo_url: str,
    token: str,
    name: str,
    redirect_uri: str,
) -> tuple[str, str]:
    """Create an OAuth2 application in Forgejo. Returns (client_id, client_secret)."""
    app = _curl(
        f"{forgejo_url}/api/v1/user/applications/oauth2",
        token,
        method="POST",
        data={
            "name": name,
            "redirect_uris": [redirect_uri],
            "scopes": ["openid", "profile", "email"],
            # Hermes authenticates the token exchange with a client_secret, so
            # the app MUST be registered as confidential. A public client makes
            # Forgejo reject/ignore the secret and the ID token never arrives,
            # which surfaces downstream as "provider unreachable".
            "confidential_client": True,
        },
    )
    return app["client_id"], app["client_secret"]


def delete_oauth2_app(
    forgejo_url: str,
    token: str,
    app_id: int,
) -> None:
    """Delete an OAuth2 application by ID."""
    _curl(
        f"{forgejo_url}/api/v1/user/applications/oauth2/{app_id}",
        token,
        method="DELETE",
    )


def get_oauth2_app(
    forgejo_url: str,
    token: str,
    name: str,
) -> dict | None:
    """Return the full OAuth2 app object by name, or None.

    Note: Forgejo only returns ``client_secret`` at creation time, so the
    secret is always empty here. Used to inspect ``confidential_client``
    and ``redirect_uris`` for drift detection.
    """
    apps = _curl(f"{forgejo_url}/api/v1/user/applications/oauth2", token)
    for app in apps or []:
        if app.get("name") == name:
            return app
    return None


def find_oauth2_app(forgejo_url: str, token: str, name: str) -> int | None:
    """The ID of the OAuth2 app named `name`, or None."""
    app = get_oauth2_app(forgejo_url, token, name)
    return app["id"] if app else None
