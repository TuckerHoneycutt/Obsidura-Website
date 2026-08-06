"""Per-branch ephemeral Tailscale auth keys (spec 2026-08-01, P6).

The contract these tests pin was VERIFIED against the live API on 2026-08-01
(minted `kkL8r4gRpM11CNTRL`, read its capabilities back, deleted it, confirmed
the tailnet's key set was byte-identical afterwards). What is asserted here is
that this code keeps ASKING for what was verified -- the capability block is
the whole product, and a key that came back `reusable: true, ephemeral: false`
would be accepted by every other test in this repository.

No test in this module reaches api.tailscale.com: `tailnet.urllib_opener` is
replaced module-wide by an autouse tripwire.
"""

from __future__ import annotations

import json
import urllib.parse

import pytest

from aurora_cli import branch, envfile, identity, tailnet


CLIENT = tailnet.OAuthClient(
    client_id="probe-id", client_secret="probe-secret", source="a fixture")
BEARER = "tskey-client-access-token"
MINTED = "tskey-auth-minted-for-one-branch"


@pytest.fixture(autouse=True)
def no_real_tailnet(monkeypatch):
    def tripwire(url, method, headers, body):
        raise AssertionError(
            f"TRIPWIRE: this module reached the network: {method} {url}")
    monkeypatch.setattr(tailnet, "urllib_opener", tripwire)


class Api:
    """api.tailscale.com, as an opener. Records every request it was sent."""

    def __init__(self, *, key_status: int = 200) -> None:
        self.key_status = key_status
        self.requests: list[tuple[str, str, dict, object]] = []
        self.deleted: list[str] = []

    def __call__(self, url, method, headers, body):
        parsed = None
        if body and headers.get("Content-Type") == "application/json":
            parsed = json.loads(body)
        elif body:
            parsed = dict(urllib.parse.parse_qsl(body.decode()))
        self.requests.append((method, url, dict(headers), parsed))

        if url == tailnet.OAUTH_TOKEN_URL:
            return tailnet.Response(200, json.dumps(
                {"access_token": BEARER, "scope": "auth_keys oauth_keys"}))
        if url == tailnet.KEYS_URL and method == "POST":
            if self.key_status != 200:
                return tailnet.Response(self.key_status, '{"message":"nope"}')
            return tailnet.Response(200, json.dumps(
                {"id": "kTEST11CNTRL", "key": MINTED}))
        if method == "DELETE":
            self.deleted.append(url.rsplit("/", 1)[-1])
            return tailnet.Response(200, "")
        raise AssertionError(f"unexpected {method} {url}")


# ---------------------------------------------------------------------------
# the request body IS the product
# ---------------------------------------------------------------------------


def test_the_minted_key_is_ephemeral_single_use_preauthorised_and_tagged():
    """Each of the four capabilities, asserted separately, with its reason.

    Collapsed into one dict comparison this would still pass with three of
    them wrong and the test would name none of them.
    """
    create = tailnet.key_request("demo")["capabilities"]["devices"]["create"]
    assert create["ephemeral"] is True, (
        "not ephemeral: the node would deregister ~an hour after teardown "
        "rather than at it. That is the 2026-07-31 wedge -- `aurora-hubdemo` "
        "still registered, the replacement landing on `aurora-hubdemo-1`, and "
        "Caddy unable to get a certificate for its own configured hostname.")
    assert create["reusable"] is False, (
        "reusable: one key across branches is what P6 replaces.")
    assert create["preauthorized"] is True, (
        "not preauthorised: the node waits for a human in the admin console "
        "and `branch up`'s tailnet readiness poll times out.")
    assert create["tags"] == [tailnet.BRANCH_TAG], create["tags"]


def test_the_key_expiry_is_long_enough_for_the_slowest_thing_before_the_sidecar():
    """1800s, and the number is derived rather than chosen.

    The key must survive from `branch up` minting it to `tailscaled`
    presenting it. `up --wait` on Postgres alone is bounded at
    COMPOSE_WAIT_TIMEOUT and runs BEFORE the sidecar exists, so an expiry at
    or below that bound can be dead before it is ever read -- and a rejected
    key is not a loud failure, it is `Logged out.` (trap 9).

    Asserted against `branch.COMPOSE_WAIT_TIMEOUT` rather than against 300, so
    raising that constant reddens this instead of silently invalidating it.
    """
    assert tailnet.KEY_EXPIRY_SECONDS > branch.COMPOSE_WAIT_TIMEOUT, (
        f"the key expires in {tailnet.KEY_EXPIRY_SECONDS}s but a single "
        f"bounded wait before the sidecar starts can take "
        f"{branch.COMPOSE_WAIT_TIMEOUT}s"
    )
    assert tailnet.KEY_EXPIRY_SECONDS <= 3600, (
        "an unused single-use key should not stay alive for over an hour"
    )
    assert tailnet.key_request("demo")["expirySeconds"] == \
        tailnet.KEY_EXPIRY_SECONDS


def test_the_description_names_the_branch():
    assert tailnet.key_request("hubdemo")["description"] == \
        "aurora branch hubdemo"


def test_the_oauth_exchange_is_form_encoded_client_credentials():
    """Verified shape: form body, not JSON. JSON gets a 400 from this endpoint."""
    api = Api()
    assert tailnet.access_token(CLIENT, opener=api) == BEARER
    method, url, headers, body = api.requests[0]
    assert (method, url) == ("POST", tailnet.OAUTH_TOKEN_URL)
    assert headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert body == {
        "client_id": CLIENT.client_id,
        "client_secret": CLIENT.client_secret,
        "grant_type": "client_credentials",
    }


def test_minting_uses_the_bearer_token_and_returns_a_deletable_id():
    api = Api()
    key = tailnet.mint_branch_key("demo", client=CLIENT, opener=api)
    assert key.secret == MINTED
    assert key.key_id == "kTEST11CNTRL", (
        "without an id the key cannot be deleted, and a key that cannot be "
        "deleted is worse than one that was never minted")
    post = [r for r in api.requests if r[1] == tailnet.KEYS_URL][0]
    assert post[2]["Authorization"] == f"Bearer {BEARER}"

    assert tailnet.delete_key(key.key_id, token=BEARER, opener=api) == 200
    assert api.deleted == ["kTEST11CNTRL"]


def test_a_key_response_without_an_id_is_refused():
    class Truncated(Api):
        def __call__(self, url, method, headers, body):
            if url == tailnet.KEYS_URL and method == "POST":
                return tailnet.Response(200, json.dumps({"key": MINTED}))
            return super().__call__(url, method, headers, body)

    with pytest.raises(tailnet.TailnetError) as raised:
        tailnet.mint_branch_key("demo", client=CLIENT, opener=Truncated())
    assert "cannot be deleted" in str(raised.value)


# ---------------------------------------------------------------------------
# credentials
# ---------------------------------------------------------------------------


def test_productions_env_carries_the_oauth_client():
    """The premise of P6 on THIS host, asserted rather than assumed.

    Fails rather than skips: if the credentials went away, the fallback path
    is what runs, and a suite that quietly stopped exercising minting would
    look identical to one where minting works.
    """
    production = envfile.parse_env(envfile.production_env_text())
    client = tailnet.oauth_client(environ={}, production_env=production)
    assert client is not None, (
        f"production's .env no longer carries "
        f"{tailnet.CLIENT_ID_PRODUCTION_VAR}/"
        f"{tailnet.CLIENT_SECRET_PRODUCTION_VAR}. Every branch is back on the "
        "shared reusable key, which is the 2026-07-31 wedge."
    )


def test_no_credentials_is_a_supported_answer_but_half_a_client_is_not():
    assert tailnet.oauth_client(environ={}, production_env={}) is None, (
        "a host without an OAuth client must fall back, not fail")
    with pytest.raises(tailnet.TailnetError) as raised:
        tailnet.oauth_client(
            environ={}, production_env={tailnet.CLIENT_ID_PRODUCTION_VAR: "x"})
    assert "Set both, or neither" in str(raised.value)


def test_no_secret_reaches_a_repr_or_an_error_message():
    """Tracebacks print the reprs of locals."""
    key = tailnet.MintedKey(
        key_id="k1", secret=MINTED, expiry_seconds=1800,
        tags=(tailnet.BRANCH_TAG,), description="d")
    assert MINTED not in repr(key) and MINTED not in str(key)
    assert CLIENT.client_secret not in repr(CLIENT)

    class Refusing(Api):
        def __call__(self, url, method, headers, body):
            if url == tailnet.OAUTH_TOKEN_URL:
                return tailnet.Response(
                    401, f'{{"error":"bad client {CLIENT.client_secret}"}}')
            return super().__call__(url, method, headers, body)

    with pytest.raises(tailnet.TailnetError) as raised:
        tailnet.access_token(CLIENT, opener=Refusing())
    assert CLIENT.client_secret not in str(raised.value), (
        "the OAuth endpoint echoed the credential back and this repeated it")


# ---------------------------------------------------------------------------
# how `branch up` chooses
# ---------------------------------------------------------------------------


def test_an_explicit_key_wins_and_minting_is_not_attempted():
    """`$AURORA_TS_AUTHKEY` is the opt-out; there is no second switch."""
    def never(*a, **k):
        raise AssertionError("minted despite an explicit key")

    resolved = branch.resolve_branch_authkey(
        "demo",
        environ={branch.AUTHKEY_ENV_VAR: "tskey-explicit"},
        production_env={tailnet.CLIENT_ID_PRODUCTION_VAR: "i",
                        tailnet.CLIENT_SECRET_PRODUCTION_VAR: "s"},
        minter=never,
    )
    assert resolved.value == "tskey-explicit"
    assert resolved.minted is False


def test_credentials_present_means_a_minted_key_and_the_source_says_so():
    api = Api()
    resolved = branch.resolve_branch_authkey(
        "demo", environ={},
        production_env={tailnet.CLIENT_ID_PRODUCTION_VAR: "i",
                        tailnet.CLIENT_SECRET_PRODUCTION_VAR: "s",
                        branch.AUTHKEY_PRODUCTION_VAR: "tskey-shared"},
        minter=lambda name, client: tailnet.mint_branch_key(
            name, client=client, opener=api),
    )
    assert resolved.minted and resolved.value == MINTED
    assert resolved.key_id == "kTEST11CNTRL"
    assert "ephemeral" in resolved.source and tailnet.BRANCH_TAG in resolved.source
    assert resolved.value not in repr(resolved)


def test_no_credentials_falls_back_to_the_supplied_key_exactly_as_before():
    resolved = branch.resolve_branch_authkey(
        "demo", environ={},
        production_env={branch.AUTHKEY_PRODUCTION_VAR: "tskey-shared"},
    )
    assert resolved.value == "tskey-shared"
    assert resolved.minted is False
    assert branch.AUTHKEY_PRODUCTION_VAR in resolved.source


def test_a_failed_mint_falls_back_and_the_fallback_is_RECORDED():
    """The downgrade must be visible, the same way `--force` is.

    Refusing to create a branch because api.tailscale.com blipped is worse
    than creating one on the shared key -- but a SILENT downgrade would make
    P6 untestable in production, so the note goes into `result.notes`, which
    `BRANCH-ACCESS.md` prints verbatim.
    """
    def failing(name, client):
        raise tailnet.TailnetError("api.tailscale.com answered HTTP 503")

    notes: list[str] = []
    resolved = branch.resolve_branch_authkey(
        "demo", environ={},
        production_env={tailnet.CLIENT_ID_PRODUCTION_VAR: "i",
                        tailnet.CLIENT_SECRET_PRODUCTION_VAR: "s",
                        branch.AUTHKEY_PRODUCTION_VAR: "tskey-shared"},
        minter=failing, notes=notes,
    )
    assert resolved.value == "tskey-shared" and not resolved.minted
    assert notes, "the fallback was silent"
    assert "NOT MINTED" in notes[0] and "503" in notes[0]
    assert "hostname" in notes[0], (
        "the note does not say what the downgrade costs")


def test_a_minted_key_goes_through_the_same_normalisation_as_a_supplied_one():
    """A check that only some keys pass through is a check with a hole in it."""
    resolved = branch.resolve_branch_authkey(
        "demo", environ={},
        production_env={tailnet.CLIENT_ID_PRODUCTION_VAR: "i",
                        tailnet.CLIENT_SECRET_PRODUCTION_VAR: "s"},
        minter=lambda name, client: tailnet.MintedKey(
            key_id="k", secret='  "tskey-padded"  ', expiry_seconds=1800,
            tags=(tailnet.BRANCH_TAG,), description="d"),
    )
    assert resolved.value == "tskey-padded"

    with pytest.raises(branch.BranchError) as raised:
        branch.resolve_branch_authkey(
            "demo", environ={},
            production_env={tailnet.CLIENT_ID_PRODUCTION_VAR: "i",
                            tailnet.CLIENT_SECRET_PRODUCTION_VAR: "s"},
            minter=lambda name, client: tailnet.MintedKey(
                key_id="k", secret="tskey with spaces", expiry_seconds=1800,
                tags=(tailnet.BRANCH_TAG,), description="d"),
        )
    assert "Logged out" in str(raised.value)


def test_the_refusal_still_names_both_ways_to_supply_a_key():
    """With neither an OAuth client nor a supplied key, `up` must refuse.

    D-D's substance is untouched by P6: a keyless sidecar does not fail, so
    the refusal has to happen here and has to be actionable.
    """
    with pytest.raises(branch.BranchError) as raised:
        branch.resolve_branch_authkey(
            "demo", environ={}, production_env={})
    message = str(raised.value)
    for required in (tailnet.CLIENT_ID_PRODUCTION_VAR,
                     branch.AUTHKEY_PRODUCTION_VAR,
                     branch.AUTHKEY_ENV_VAR, "Logged out"):
        assert required in message, f"{required!r} missing from:\n{message}"


def test_the_authkey_variable_is_still_a_secret_the_documents_refuse():
    """P6 must not have loosened the redaction it writes new values into."""
    from aurora_cli import access_doc

    secrets = access_doc.secret_variables()
    assert secrets, "no variable is marked secret; the leak check is inert"
    assert any("AUTHKEY" in name for name in secrets), sorted(secrets)
