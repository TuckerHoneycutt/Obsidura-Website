"""P3's acceptance: two HTTP calls, both 401 (spec 2026-08-01 §4).

    * the BRANCH's token, presented to PRODUCTION's API  -> 401
    * PRODUCTION's token, presented to the BRANCH's API  -> 401

Neither is a config assertion. Both are real requests with recorded responses,
so they need a live branch -- which takes ~55s to create and a tailnet key.
This module therefore has two halves, and the split is deliberate:

**Always runs.** `test_the_acceptance_predicate_discriminates` drives the same
function the live assertions use against a 401 and a 200 and proves it tells
them apart. Without it the gated half could be gated on a variable nobody ever
sets and this file would be decoration. A gate is only honest if something
tests the thing behind it.

**Gated, loudly.** The live half runs only when `$AURORA_LIVE_BRANCH` names a
branch. That is the repository's standing rule -- "never `skip` an environment
condition; `fail` with the reason, or gate on an explicit opt-in variable" --
and this is the second form. Once the variable IS set, nothing else in here
skips: a branch that is named but absent, unreachable, or missing a `.env` is
a FAILURE, because at that point the caller has said they have a branch and
being told nothing happened is worse than being told why.

    AURORA_LIVE_BRANCH=<name> python -m pytest tests/test_branch_credentials.py

Both calls are GETs. Nothing in this file mutates production.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from aurora_cli import envfile, forgejo_token, identity


#: The opt-in. Named here once so the skip reason, the failure messages and
#: the documentation cannot disagree about what to set.
LIVE_BRANCH_VAR = "AURORA_LIVE_BRANCH"

HOW = (
    f"set {LIVE_BRANCH_VAR}=<branch name> to run the live half, e.g.\n"
    f"    {LIVE_BRANCH_VAR}=hubdev python -m pytest "
    "tests/test_branch_credentials.py -v\n"
    "  The branch must be up: these are HTTP calls to its Forgejo and to "
    "production's, not assertions about configuration."
)

TIMEOUT = 20.0


def api_status(base_url: str, token: str) -> tuple[int, str]:
    """`GET <base>/api/v1/user` with `token`. Returns (status, body).

    The single predicate both halves of this module use. An HTTP error status
    is an ANSWER here -- 401 is the whole point -- so only a transport failure
    raises.
    """
    request = urllib.request.Request(f"{base_url.rstrip('/')}/api/v1/user")
    request.add_header("Authorization", f"token {token}")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as handle:
            return handle.status, handle.read().decode("utf-8", "replace")[:300]
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")[:300]


def rejected(status: int) -> bool:
    """What "this credential is not valid on that forge" means, as one place.

    401 only. NOT `status != 200`: a 404 from a mistyped URL, a 502 from a
    Caddy that has not started, and a connection refused would all satisfy
    `!= 200` while proving nothing at all about the credential -- which is
    exactly how an isolation test passes against a stack that is switched off.
    """
    return status == 401


# ---------------------------------------------------------------------------
# always runs -- the gate is not allowed to make this file vacuous
# ---------------------------------------------------------------------------


def test_the_acceptance_predicate_discriminates():
    """`rejected()` must separate a rejection from every other outcome."""
    assert rejected(401)
    for other in (200, 403, 404, 500, 502, 0):
        assert not rejected(other), (
            f"HTTP {other} was counted as a credential rejection. A test that "
            "accepts anything but 200 passes against a forge that is simply "
            "not running.")


def test_the_opt_in_variable_is_the_documented_one():
    """The skip reason, the docstring and the failure messages name one var."""
    assert LIVE_BRANCH_VAR in HOW
    assert LIVE_BRANCH_VAR in __doc__


def test_production_and_the_branch_manifest_still_describe_this_defect():
    """The premise, asserted rather than assumed -- and it FAILS, not skips.

    If production stopped carrying `FORGEJO_ADMIN_TOKEN`, or the manifest
    stopped describing it, the live assertions below would be testing a
    situation that no longer exists.
    """
    production = envfile.parse_env(envfile.production_env_text())
    assert production.get(forgejo_token.ADMIN_TOKEN_VAR), (
        f"production's .env no longer declares "
        f"{forgejo_token.ADMIN_TOKEN_VAR}")
    assert production.get("FORGEJO_URL"), (
        "production's .env no longer declares FORGEJO_URL, so there is no "
        "production API to present a branch's token to")
    listed = {r.name for r in envfile.load_manifest()}
    assert forgejo_token.ADMIN_TOKEN_VAR in listed


# ---------------------------------------------------------------------------
# the live half
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def live_branch() -> str:
    name = (os.environ.get(LIVE_BRANCH_VAR) or "").strip()
    if not name:
        pytest.skip(
            "P3's acceptance is TWO REAL HTTP CALLS and needs a live branch, "
            f"which takes ~55s and a tailnet key to create. NOT RUN: "
            f"${LIVE_BRANCH_VAR} is unset.\n  " + HOW
        )
    return name


@pytest.fixture(scope="module")
def branch_env(live_branch) -> dict:
    """The named branch's `.env`. Every failure here is a FAILURE, not a skip.

    Past this point the caller has asserted that a branch exists. "Nothing
    happened" is then the least useful thing this file could say.
    """
    paths = identity.branch_paths(live_branch)
    env_file = Path(paths.env_file)
    if not env_file.is_file():
        pytest.fail(
            f"${LIVE_BRANCH_VAR}={live_branch!r} but there is no branch `.env` "
            f"at {env_file}. Either the branch is not up, or it was created "
            f"under a different name (`aurora branch ls`)."
        )
    values = envfile.parse_env(env_file.read_text(encoding="utf-8"))
    for required in (forgejo_token.ADMIN_TOKEN_VAR, "DOMAIN_NAME"):
        if not values.get(required):
            pytest.fail(f"{env_file} carries no {required}.")
    return dict(values)


@pytest.fixture(scope="module")
def production_env() -> dict:
    return dict(envfile.parse_env(envfile.production_env_text()))


def test_the_branch_token_is_not_productions(branch_env, production_env):
    """The cheap half, first, so a byte-identical token is named as such.

    If this fails, the two calls below fail for a reason that has nothing to
    do with HTTP and everything to do with the rotation not having run.
    """
    assert (branch_env[forgejo_token.ADMIN_TOKEN_VAR]
            != production_env[forgejo_token.ADMIN_TOKEN_VAR]), (
        "the branch `.env` carries production's admin token byte for byte, so "
        "P3's rotation did not run on this branch. The two calls below cannot "
        "mean anything until it has."
    )


def test_the_branch_token_is_rejected_by_PRODUCTIONS_api(
    branch_env, production_env, record_property
):
    """Acceptance 1. The branch's credential must not administer production."""
    url = production_env["FORGEJO_URL"]
    status, body = api_status(url, branch_env[forgejo_token.ADMIN_TOKEN_VAR])
    record_property("production_api", url)
    record_property("status", status)
    record_property("body", body)
    assert rejected(status), (
        f"the BRANCH's admin token was accepted by PRODUCTION's API at {url}: "
        f"HTTP {status} {body}. A branch holds a credential valid on "
        "production, which is the defect P3 exists to close."
    )


def test_productions_token_is_rejected_by_the_BRANCHS_api(
    branch_env, production_env, record_property
):
    """Acceptance 2. Production's credential must not survive in the copy.

    This is the assertion mutation M8 turns green: skip the purge and
    production's `access_token` rows are still in the branch's database, so
    production's token authenticates there.
    """
    url = f"https://{branch_env['DOMAIN_NAME']}/git"
    status, body = api_status(
        url, production_env[forgejo_token.ADMIN_TOKEN_VAR])
    record_property("branch_api", url)
    record_property("status", status)
    record_property("body", body)
    assert rejected(status), (
        f"PRODUCTION's admin token was accepted by the BRANCH's API at {url}: "
        f"HTTP {status} {body}. Production's token rows survive in this "
        "branch's copy of the database -- step 4 of the rotation did not run."
    )


def test_the_branch_token_still_works_on_the_BRANCHS_own_api(
    branch_env, record_property
):
    """The control. Without it both assertions above pass on a dead forge.

    Two 401s prove isolation only if something proves the branch's API is
    answering and accepting the credential it was given.
    """
    url = f"https://{branch_env['DOMAIN_NAME']}/git"
    status, body = api_status(url, branch_env[forgejo_token.ADMIN_TOKEN_VAR])
    record_property("status", status)
    assert status == 200, (
        f"the branch's own token does not work against its own API at {url}: "
        f"HTTP {status} {body}. Until this passes the two 401s above are "
        "consistent with a Forgejo that rejects everything."
    )
