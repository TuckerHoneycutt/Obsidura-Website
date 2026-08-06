"""Per-branch ephemeral Tailscale auth keys (spec 2026-08-01, P6).

Why this module exists, and why it did not before
-------------------------------------------------
Decision **D-D** says the branch auth key is *supplied, never minted*, and the
reason it gives is a fact about the host rather than a principle:

    minting needs a Tailscale API key or OAuth client, neither of which exists
    on this host and neither of which an agent can create.

That fact stopped being true. `TS_OAUTH_CLIENT_ID` / `TS_OAUTH_CLIENT_SECRET`
are in production's `.env`, and the three calls below are **verified against
the live API**, not derived from documentation:

    POST /api/v2/oauth/token   client_id, client_secret,
                               grant_type=client_credentials      -> 200
                               scope granted: "auth_keys oauth_keys"
    POST /api/v2/tailnet/-/keys                                   -> 200
    DELETE /api/v2/tailnet/-/keys/{id}                            -> 200

So D-D's *reason* expired; D-D was not wrong when it was written. That
distinction matters, because "the decision was wrong" invites re-litigating
the rest of it, and the rest of it -- a keyless sidecar does not fail, it
starts, says `Logged out.` and serves a dead URL -- is still exactly right and
is still what `branch.resolve_authkey` refuses over.

What a minted key buys beyond hygiene
-------------------------------------
One reusable key shared by every branch produces **non-ephemeral nodes**, and
a non-ephemeral node deregisters roughly an hour after it stops rather than at
teardown. On **2026-07-31** that wedged a branch: `aurora-hubdemo` was still
registered when its replacement sidecar came up, the replacement was given
`aurora-hubdemo-1`, and Caddy could then not obtain a certificate for the
hostname it had been configured with. The branch was up, healthy by every
container check, and served nothing. An ephemeral node deregisters when it
disconnects, which closes that failure mode rather than shortening it.

Secrets
-------
Nothing in this module puts a client secret or an auth key into an exception
message, a log line, a `repr`, or an argv. `MintedKey.__repr__` is overridden
for that reason: a traceback prints reprs, and a traceback is the one place
nobody remembers to check. `branch-env.yaml` marks `TS_AUTHKEY` `secret: true`
and `access_doc` refuses to render a document naming it -- this module must
not hand anything to a code path that would defeat that.

Dependencies: standard library only.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass

#: The tailnet identifier. `-` means "the tailnet the credential belongs to"
#: and is accepted by every endpoint used here (verified). Preferred over the
#: literal tailnet name, which is a second place to be wrong and which changes
#: if the tailnet is ever renamed.
TAILNET = "-"

API_ROOT = "https://api.tailscale.com/api/v2"
OAUTH_TOKEN_URL = f"{API_ROOT}/oauth/token"
KEYS_URL = f"{API_ROOT}/tailnet/{TAILNET}/keys"

#: Where the OAuth client lives. The environment first so a caller can point a
#: run at a different client without editing production's file, then
#: production's `.env`, which is where it actually is.
CLIENT_ID_ENV_VAR = "AURORA_TS_OAUTH_CLIENT_ID"
CLIENT_SECRET_ENV_VAR = "AURORA_TS_OAUTH_CLIENT_SECRET"
CLIENT_ID_PRODUCTION_VAR = "TS_OAUTH_CLIENT_ID"
CLIENT_SECRET_PRODUCTION_VAR = "TS_OAUTH_CLIENT_SECRET"

#: Every minted key is tagged. A tag is what makes the node's ownership a
#: property of the tailnet's ACL rather than of whoever happened to run
#: `branch up`, and it is what makes "which nodes are branches?" answerable
#: from the admin console.
#:
#: **The one part of P6 that could not be verified from here.** That the tag
#: is accepted is measured -- `POST /keys` with it answers 200, which it would
#: not if `tagOwners` did not name it. What a tagged NODE is then allowed to
#: do is an ACL question, and this OAuth client's scope (`auth_keys
#: oauth_keys`) cannot read the ACL: `GET /acl` 403s. A tagged device does not
#: inherit the implicit access of the user who created it, so if the ACL does
#: not let devices reach `tag:aurora-branch`, a branch's URL stops resolving
#: for its developer -- `branch up`'s tailnet readiness poll and its HTTPS
#: probe are both bounded and both would fail loudly, but they would fail.
#: The first `branch up` after this lands is what settles it.
BRANCH_TAG = "tag:aurora-branch"

#: How long a minted key stays usable.
#:
#: **300s was a probe value and is not defensible as a product value.** What
#: the key must survive is the interval between `branch up` minting it and
#: `tailscaled` presenting it -- NOT the life of the branch. A node that has
#: registered keeps working after its auth key expires; ephemeral nodes are
#: removed when they disconnect, not when the key dies.
#:
#: That interval is bounded below by ~55s (the measured warm `branch up`) and
#: above by everything `up` does before the sidecar starts: `git worktree
#: add`, the seed, `up --wait` on Postgres -- bounded by COMPOSE_WAIT_TIMEOUT
#: at **300s on its own** -- the AFFiNE restore, and then an image `--build`,
#: which is the default and which nothing bounds. 300s could therefore be
#: expired before the sidecar ever reads it, on a path the warm case never
#: exercises: the key would be rejected, and a rejected key does not fail
#: loudly, it produces `Logged out.` (trap 9).
#:
#: 1800s is ~32x the warm path and comfortably clears the one bounded wait
#: that could consume 300s by itself, while still keeping an unused key alive
#: for well under an hour. The key is additionally `reusable: false`, so once
#: `tailscaled` has spent it the remaining window buys an attacker nothing.
KEY_EXPIRY_SECONDS = 1800

#: Bounds on every HTTP call. `urllib` has no default timeout, and an
#: unbounded call inside `branch up` is indistinguishable from a hang.
HTTP_TIMEOUT = 30.0


class TailnetError(RuntimeError):
    """A Tailscale API call failed. Never carries a secret."""


@dataclass(frozen=True)
class OAuthClient:
    """The OAuth client credentials, and where they came from."""

    client_id: str
    client_secret: str
    source: str

    def __repr__(self) -> str:                      # pragma: no cover - trivial
        return f"OAuthClient(source={self.source!r})"

    __str__ = __repr__


@dataclass(frozen=True)
class MintedKey:
    """One per-branch ephemeral auth key.

    `secret` is the key itself and is the reason `__repr__` is overridden: a
    traceback prints reprs of locals, and `TS_AUTHKEY` is marked `secret:
    true` precisely so that it never reaches a file a human might read.
    """

    key_id: str
    secret: str
    expiry_seconds: int
    tags: tuple[str, ...]
    description: str

    def __repr__(self) -> str:
        return (
            f"MintedKey(key_id={self.key_id!r}, "
            f"expiry_seconds={self.expiry_seconds}, tags={self.tags!r}, "
            "secret=<redacted>)"
        )

    __str__ = __repr__


# ---------------------------------------------------------------------------
# the one HTTP seam
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Response:
    status: int
    body: str

    def json(self) -> object:
        try:
            return json.loads(self.body)
        except ValueError as exc:
            raise TailnetError(
                f"the Tailscale API returned HTTP {self.status} with a body "
                f"that is not JSON: {exc}"
            ) from exc


#: `(url, method, headers, body) -> Response`. One seam, so a test drives the
#: real code with canned answers instead of a reimplementation of it, and so
#: no test in this repository can reach api.tailscale.com by accident.
Opener = Callable[[str, str, Mapping[str, str], bytes | None], Response]


def urllib_opener(
    url: str,
    method: str,
    headers: Mapping[str, str],
    body: bytes | None,
) -> Response:
    """The real opener. An HTTP error status is an ANSWER, not an exception.

    `urllib` raises on 4xx/5xx, which would turn "Tailscale said 403" into a
    stack trace that reads like a bug in this file. Every status comes back as
    a `Response` so the caller decides what it means, and only a transport
    failure raises.
    """
    request = urllib.request.Request(url, data=body, method=method)
    for key, value in headers.items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as handle:
            return Response(handle.status, handle.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return Response(exc.code, exc.read().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001 -- reported, never swallowed
        raise TailnetError(
            f"{method} {url} could not be completed: {type(exc).__name__}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# credentials
# ---------------------------------------------------------------------------


def oauth_client(
    *,
    environ: Mapping[str, str] | None = None,
    production_env: Mapping[str, str] | None = None,
) -> OAuthClient | None:
    """The OAuth client, or `None` when this host has none.

    `None` is a supported answer, not a failure: P6's contract is that a host
    WITHOUT the credentials falls back to the supplied `TS_AUTHKEY_BRANCH`
    exactly as before. Half a client -- an id with no secret -- is NOT a
    supported answer and raises, because it is a typo in production's `.env`
    that would otherwise degrade silently to the old behaviour.
    """
    environ = environ or {}
    production_env = production_env or {}

    def pick(env_var: str, prod_var: str) -> tuple[str, str] | None:
        raw = (environ.get(env_var) or "").strip()
        if raw:
            return raw, f"${env_var}"
        raw = (production_env.get(prod_var) or "").strip()
        if raw:
            return raw, f"{prod_var} in production's .env"
        return None

    got_id = pick(CLIENT_ID_ENV_VAR, CLIENT_ID_PRODUCTION_VAR)
    got_secret = pick(CLIENT_SECRET_ENV_VAR, CLIENT_SECRET_PRODUCTION_VAR)

    if got_id is None and got_secret is None:
        return None
    if got_id is None or got_secret is None:
        missing = CLIENT_ID_PRODUCTION_VAR if got_id is None \
            else CLIENT_SECRET_PRODUCTION_VAR
        present = got_secret[1] if got_id is None else got_id[1]
        raise TailnetError(
            f"{present} is set but {missing} is not. Half an OAuth client "
            "cannot mint anything, and falling back to the shared reusable "
            "key here would silently undo P6 on a host that was configured "
            "for it -- so this is a refusal rather than a degradation. Set "
            "both, or neither."
        )
    return OAuthClient(
        client_id=got_id[0], client_secret=got_secret[0],
        source=got_id[1],
    )


def access_token(client: OAuthClient, *, opener: Opener | None = None) -> str:
    """Exchange the OAuth client for a bearer token.

    Form-encoded, not JSON: verified against the live endpoint. The granted
    scope is `auth_keys oauth_keys`, which is exactly enough to create and
    delete keys and is not enough to read the ACL (that 403s, and does not
    matter here).

    `opener` defaults to `None` rather than to `urllib_opener` so the default
    is looked up at CALL time. A default bound at `def` time cannot be
    monkeypatched, which would leave every test in this repository one
    forgotten argument away from a real request to api.tailscale.com.
    """
    opener = opener if opener is not None else urllib_opener
    body = urllib.parse.urlencode({
        "client_id": client.client_id,
        "client_secret": client.client_secret,
        "grant_type": "client_credentials",
    }).encode("ascii")
    response = opener(
        OAUTH_TOKEN_URL, "POST",
        {"Content-Type": "application/x-www-form-urlencoded"},
        body,
    )
    if response.status != 200:
        raise TailnetError(
            f"the Tailscale OAuth token endpoint answered HTTP "
            f"{response.status} for the client from {client.source}. The "
            "response body is deliberately not repeated here: it can echo the "
            "credential back."
        )
    payload = response.json()
    if not isinstance(payload, Mapping) or not payload.get("access_token"):
        raise TailnetError(
            "the Tailscale OAuth token endpoint answered 200 with no "
            "`access_token` field."
        )
    return str(payload["access_token"])


# ---------------------------------------------------------------------------
# minting and deleting
# ---------------------------------------------------------------------------


def key_request(
    branch_name: str, *, expiry_seconds: int = KEY_EXPIRY_SECONDS,
) -> dict:
    """The exact body posted to `/keys`. A function so a test can read it.

    Every capability here is load-bearing and none is a default:

    * `reusable: false` -- one key, one branch, spent on first use. This is
      the difference from `TS_AUTHKEY_BRANCH`, which every branch shares.
    * `ephemeral: true` -- the node deregisters when it disconnects instead of
      lingering ~an hour. This is the 2026-07-31 `aurora-hubdemo-1` wedge.
    * `preauthorized: true` -- otherwise the node needs manual approval in the
      admin console before it serves, and `branch up`'s tailnet readiness poll
      would time out waiting for a human.
    * `tags` -- ownership belongs to the ACL, not to whoever ran the command.
    """
    return {
        "capabilities": {
            "devices": {
                "create": {
                    "reusable": False,
                    "ephemeral": True,
                    "preauthorized": True,
                    "tags": [BRANCH_TAG],
                }
            }
        },
        "expirySeconds": int(expiry_seconds),
        "description": f"aurora branch {branch_name}",
    }


def mint_branch_key(
    branch_name: str,
    *,
    client: OAuthClient,
    expiry_seconds: int = KEY_EXPIRY_SECONDS,
    opener: Opener | None = None,
    token: str | None = None,
) -> MintedKey:
    """Mint one tagged, ephemeral, single-use key for `branch_name`."""
    opener = opener if opener is not None else urllib_opener
    token = token if token is not None else access_token(client, opener=opener)
    request = key_request(branch_name, expiry_seconds=expiry_seconds)
    response = opener(
        KEYS_URL, "POST",
        {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json.dumps(request).encode("utf-8"),
    )
    if response.status != 200:
        raise TailnetError(
            f"minting a branch auth key answered HTTP {response.status}: "
            f"{_safe_body(response)}"
        )
    payload = response.json()
    if not isinstance(payload, Mapping):
        raise TailnetError("the key endpoint answered 200 with a non-object body.")
    key = payload.get("key")
    key_id = payload.get("id")
    if not key or not key_id:
        raise TailnetError(
            "the key endpoint answered 200 without both `key` and `id`. "
            "Without the id the key cannot be deleted, and a key that cannot "
            "be deleted is worse than one that was never minted."
        )
    return MintedKey(
        key_id=str(key_id),
        secret=str(key),
        expiry_seconds=int(expiry_seconds),
        tags=(BRANCH_TAG,),
        description=str(request["description"]),
    )


def delete_key(
    key_id: str,
    *,
    client: OAuthClient | None = None,
    token: str | None = None,
    opener: Opener | None = None,
) -> int:
    """Delete a key by id. Returns the HTTP status, which the caller checks.

    Used by the verification tests to clean up after themselves. It is
    deliberately NOT wired into `branch down`: a minted key is `reusable:
    false` and expires in `KEY_EXPIRY_SECONDS`, so by teardown it is already
    spent and dead, and what deleting an auth key does to a node that already
    authenticated with it is not a behaviour to discover for the first time
    while tearing a developer's branch down.
    """
    opener = opener if opener is not None else urllib_opener
    if token is None:
        if client is None:
            raise TailnetError("delete_key needs either a token or a client.")
        token = access_token(client, opener=opener)
    response = opener(
        f"{KEYS_URL}/{urllib.parse.quote(str(key_id))}", "DELETE",
        {"Authorization": f"Bearer {token}"}, None,
    )
    return response.status


def _safe_body(response: Response) -> str:
    """A bounded slice of an error body, for a message that must stay useful.

    Bounded because an HTML error page in an exception message buries the
    status that actually explains the failure. Only ever called on a
    non-2xx response from an endpoint that does not echo credentials.
    """
    text = " ".join(response.body.split())
    return text[:300] if text else "(empty body)"


__all__ = [
    "BRANCH_TAG",
    "CLIENT_ID_PRODUCTION_VAR",
    "CLIENT_SECRET_PRODUCTION_VAR",
    "KEYS_URL",
    "KEY_EXPIRY_SECONDS",
    "MintedKey",
    "OAUTH_TOKEN_URL",
    "OAuthClient",
    "Response",
    "TailnetError",
    "access_token",
    "delete_key",
    "key_request",
    "mint_branch_key",
    "oauth_client",
    "urllib_opener",
]
