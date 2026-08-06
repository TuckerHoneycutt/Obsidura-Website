"""Coverage for scoped per-developer Forgejo tokens.

Every test stubs `forgejo_access._curl` -- the HTTP transport -- and calls the
real functions. Nothing reimplements the logic it claims to pin.

The shape of this module is dictated by Forgejo, and the tests say so: minting
and deleting a token are the DEVELOPER's acts (basic auth, their password),
because an admin token is 401 "auth method not allowed" on those two routes.
The admin's lever is `set_active`. So several tests here assert on WHICH
credential a call used, not only on what it did.
"""

import base64
import subprocess
from unittest.mock import patch

import pytest

from dev_administration.forgejo_access import (
    ALLOWED_SCOPES,
    DEFAULT_SCOPES,
    AccessError,
    assert_scopes_allowed,
    assert_self_grantable,
    find_managed_token,
    mint_token,
    revoke_token,
    set_active,
    token_name,
)

URL = "https://forgejo.example.com/git"
ADMIN = "admin-token"
DEVS = ["juan"]
PW = "juans-password"


class Curl:
    """Recording stub for forgejo_access._curl.

    Records the `basic` argument of every call, so a test can prove that
    minting never used the admin token -- the property Forgejo forces on us and
    the one a well-meaning refactor would quietly undo.
    """

    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def __call__(self, url, token, method="GET", data=None, basic=None, **kw):
        self.calls.append({"method": method, "url": url, "data": data,
                           "basic": basic, "token": token})
        return self.handler(method, url, data, basic)

    def sent(self, method):
        return [c for c in self.calls if c["method"] == method]


def _install(monkeypatch, handler):
    stub = Curl(handler)
    monkeypatch.setattr("dev_administration.forgejo_access._curl", stub)
    # forgejo_access reads a user object through forgejo_org.get_user rather
    # than re-implementing GET /users/{u}, so that transport is stubbed too.
    monkeypatch.setattr("dev_administration.forgejo_org._curl", stub)
    return stub


def _user(is_admin=False, login="juan", active=True):
    return {"id": 7, "login": login, "is_admin": is_admin, "active": active}


def _token(id_, name, last8="deadbeef", scopes=("read:user", "write:repository")):
    return {"id": id_, "name": name, "token_last_eight": last8, "scopes": list(scopes)}


# --------------------------------------------------------------------------
# The scope allowlist
# --------------------------------------------------------------------------

def test_the_allowlist_itself_carries_no_admin_or_wildcard_scope():
    """Asks 'what happens when someone widens this?' of the constant itself."""
    assert ALLOWED_SCOPES, "allowlist is empty — every mint below would refuse"
    assert "all" not in ALLOWED_SCOPES
    assert not [s for s in ALLOWED_SCOPES if "admin" in s]


def test_the_allowlist_excludes_write_user_which_would_let_a_token_mint_tokens():
    """Measured against a branch's Forgejo: minting needs `write:user`.

    With it on the allowlist, a scoped token could mint itself an `all` token
    and the whole feature would be decorative.
    """
    assert "write:user" not in ALLOWED_SCOPES


def test_default_scopes_are_non_empty_and_every_one_is_allowed():
    assert DEFAULT_SCOPES, "no default scopes — the subset check below is vacuous"
    assert set(DEFAULT_SCOPES) <= ALLOWED_SCOPES
    assert "all" not in DEFAULT_SCOPES


@pytest.mark.parametrize("scope", ["all", "write:admin", "read:admin", "write:user"])
def test_scope_allowlist_refuses_the_dangerous_scopes(scope):
    with pytest.raises(AccessError) as exc:
        assert_scopes_allowed(["read:user", scope])
    # On the message, not just the type: one error class covers every refusal
    # in this module, so `raises(...)` alone would pass on the wrong one.
    assert scope in str(exc.value)


def test_scope_allowlist_refuses_a_scope_nobody_anticipated():
    """The whitelist-vs-blacklist proof.

    `write:package` is a real Forgejo scope and deliberately not allowlisted.
    A blacklist of ('all', '*admin*') would let it through; this is the
    assertion that fails if the check is ever rewritten as one.
    """
    with pytest.raises(AccessError) as exc:
        assert_scopes_allowed(["write:package"])
    assert "write:package" in str(exc.value)


def test_scope_allowlist_refuses_an_empty_request():
    with pytest.raises(AccessError) as exc:
        assert_scopes_allowed([])
    assert "no scopes" in str(exc.value)


def test_scope_allowlist_passes_the_defaults_through_unchanged():
    assert assert_scopes_allowed(DEFAULT_SCOPES) == tuple(DEFAULT_SCOPES)


# --------------------------------------------------------------------------
# Who may mint
# --------------------------------------------------------------------------

def test_mint_refuses_an_account_absent_from_developers_yaml(monkeypatch):
    stub = _install(monkeypatch, lambda m, u, d, b: _user())
    with pytest.raises(AccessError) as exc:
        mint_token(URL, "stranger", PW, DEVS)
    assert "developers.yaml" in str(exc.value)
    assert stub.calls == [], "refused, but still talked to Forgejo"


def test_mint_refuses_a_forgejo_site_admin(monkeypatch):
    """A `write:repository` token on an admin account reaches every repo."""
    stub = _install(monkeypatch, lambda m, u, d, b: _user(is_admin=True))
    with pytest.raises(AccessError) as exc:
        mint_token(URL, "juan", PW, DEVS)
    assert "site admin" in str(exc.value)
    assert stub.sent("POST") == [], "refused an admin, then minted the token anyway"


def test_mint_refuses_when_the_password_belongs_to_someone_else(monkeypatch):
    """`revoke` and `ls` key off the token NAME, so the name must match whoever
    actually authenticated, or the two disagree about whose credential it is."""
    stub = _install(monkeypatch, lambda m, u, d, b: _user(login="ethan"))
    with pytest.raises(AccessError) as exc:
        mint_token(URL, "juan", PW, DEVS)
    assert "ethan" in str(exc.value)
    assert stub.sent("POST") == []


def test_assert_self_grantable_authenticates_as_the_developer_not_the_admin(monkeypatch):
    """The property Forgejo forces on us: no admin credential in this path."""
    stub = _install(monkeypatch, lambda m, u, d, b: _user())
    assert_self_grantable(URL, "juan", PW, DEVS)
    assert stub.calls, "vacuous — no call was made"
    assert all(c["basic"] == ("juan", PW) for c in stub.calls)
    assert all(not c["token"] for c in stub.calls), "an admin token leaked into the mint path"


# --------------------------------------------------------------------------
# Minting
# --------------------------------------------------------------------------

def _mint_handler(existing=(), created=None, login="juan", is_admin=False):
    def handler(method, url, data, basic):
        if url.endswith("/api/v1/user"):
            return _user(is_admin=is_admin, login=login)
        if url.endswith("/users/juan/tokens") and method == "GET":
            return list(existing)
        if url.endswith("/users/juan/tokens") and method == "POST":
            return created
        raise AssertionError(f"unexpected call {method} {url}")
    return handler


def test_mint_posts_the_derived_name_and_the_requested_scopes(monkeypatch):
    """Deliberately asks for a NON-default scope set.

    The first version of this test passed exactly DEFAULT_SCOPES, so a mutation
    replacing the caller's argument with the defaults left the whole suite
    green. A `--scope` flag that is silently discarded is the worst failure
    this feature has, and it was invisible until the mutation ran.
    """
    minted = dict(_token(11, "aurora-dev-juan"), sha1="s3cr3t")
    stub = _install(monkeypatch, _mint_handler(created=minted))

    requested = ["read:repository"]
    assert tuple(requested) != tuple(DEFAULT_SCOPES), "this mutation goes blind again"

    result = mint_token(URL, "juan", PW, DEVS, requested)

    posts = stub.sent("POST")
    assert len(posts) == 1, f"expected exactly one POST, got {posts}"
    assert posts[0]["url"] == f"{URL}/api/v1/users/juan/tokens"
    assert posts[0]["data"] == {"name": "aurora-dev-juan", "scopes": ["read:repository"]}
    assert result["sha1"] == "s3cr3t"


def test_mint_with_no_scope_argument_sends_the_defaults(monkeypatch):
    minted = dict(_token(11, "aurora-dev-juan"), sha1="s3cr3t")
    stub = _install(monkeypatch, _mint_handler(created=minted))
    mint_token(URL, "juan", PW, DEVS)
    assert stub.sent("POST")[0]["data"]["scopes"] == list(DEFAULT_SCOPES)


def test_mint_authenticates_the_post_as_the_developer(monkeypatch):
    """Forgejo answers 401 to a token here. A refactor back to the admin token
    would not fail loudly in a unit test unless something asserts this."""
    minted = dict(_token(11, "aurora-dev-juan"), sha1="s3cr3t")
    stub = _install(monkeypatch, _mint_handler(created=minted))
    mint_token(URL, "juan", PW, DEVS)
    assert stub.sent("POST")[0]["basic"] == ("juan", PW)


def test_mint_refuses_to_create_a_second_token_while_one_is_live(monkeypatch):
    """Two live tokens means `revoke` leaves a working credential behind."""
    stub = _install(monkeypatch, _mint_handler(existing=[_token(11, "aurora-dev-juan")]))
    with pytest.raises(AccessError) as exc:
        mint_token(URL, "juan", PW, DEVS)
    assert "already has" in str(exc.value)
    assert stub.sent("POST") == []


def test_mint_ignores_a_developers_own_token_of_another_name(monkeypatch):
    """A personal token must not read as 'already minted' and block the mint."""
    minted = dict(_token(12, "aurora-dev-juan"), sha1="s3cr3t")
    stub = _install(monkeypatch, _mint_handler(
        existing=[_token(9, "juans-laptop")], created=minted,
    ))
    assert mint_token(URL, "juan", PW, DEVS)["sha1"] == "s3cr3t"
    assert len(stub.sent("POST")) == 1


def test_mint_fails_loudly_if_forgejo_returns_no_secret(monkeypatch):
    """Forgejo answering 200 with no sha1 must not read as a successful mint."""
    _install(monkeypatch, _mint_handler(created={"id": 11, "name": "aurora-dev-juan"}))
    with pytest.raises(AccessError) as exc:
        mint_token(URL, "juan", PW, DEVS)
    assert "returned no token" in str(exc.value)


def test_mint_checks_scopes_before_it_touches_forgejo(monkeypatch):
    stub = _install(monkeypatch, _mint_handler())
    with pytest.raises(AccessError):
        mint_token(URL, "juan", PW, DEVS, ["all"])
    assert stub.calls == []


# --------------------------------------------------------------------------
# Revocation
# --------------------------------------------------------------------------

def _revoke_handler(before, after=None):
    """GET returns `before`, then `after` once a DELETE has been seen."""
    state = {"deleted": False}

    def handler(method, url, data, basic):
        if method == "DELETE":
            state["deleted"] = True
            return None
        if url.endswith("/tokens"):
            if state["deleted"]:
                return list(before if after is None else after)
            return list(before)
        raise AssertionError(f"unexpected call {method} {url}")
    return handler


def test_revoke_deletes_only_the_managed_token(monkeypatch):
    """Three tokens on the account; exactly one is ours."""
    before = [
        _token(9, "juans-laptop"),
        _token(11, "aurora-dev-juan", last8="aabbccdd"),
        _token(14, "juans-ci"),
    ]
    stub = _install(monkeypatch, _revoke_handler(before, [before[0], before[2]]))

    deleted = revoke_token(URL, "juan", PW, DEVS)

    assert deleted["id"] == 11
    assert deleted["token_last_eight"] == "aabbccdd"
    urls = [c["url"] for c in stub.sent("DELETE")]
    assert urls == [f"{URL}/api/v1/users/juan/tokens/11"], (
        "revoke must delete the managed token and nothing else; sent %r" % urls
    )


def test_revoke_authenticates_as_the_developer(monkeypatch):
    before = [_token(11, "aurora-dev-juan")]
    stub = _install(monkeypatch, _revoke_handler(before, []))
    revoke_token(URL, "juan", PW, DEVS)
    assert stub.sent("DELETE")[0]["basic"] == ("juan", PW)
    assert all(not c["token"] for c in stub.calls), "an admin token leaked into revoke"


def test_revoke_reports_nothing_when_the_account_has_only_personal_tokens(monkeypatch):
    """Non-vacuous: the token list is deliberately NOT empty."""
    before = [_token(9, "juans-laptop"), _token(14, "juans-ci")]
    stub = _install(monkeypatch, _revoke_handler(before))
    assert [t["name"] for t in before], "empty list would make this test vacuous"

    assert revoke_token(URL, "juan", PW, DEVS) is None
    assert stub.sent("DELETE") == []


def test_revoke_raises_if_forgejo_still_lists_the_token_afterwards(monkeypatch):
    """A DELETE that 204s against a route that ignored it must not read as success."""
    before = [_token(11, "aurora-dev-juan")]
    _install(monkeypatch, _revoke_handler(before, after=before))
    with pytest.raises(AccessError) as exc:
        revoke_token(URL, "juan", PW, DEVS)
    assert "NOT revoked" in str(exc.value)


def test_find_managed_token_matches_the_derived_name_exactly(monkeypatch):
    _install(monkeypatch, lambda m, u, d, b: [
        _token(9, "aurora-dev-juanita"), _token(11, "aurora-dev-juan"),
    ])
    assert find_managed_token(URL, "juan", ADMIN)["id"] == 11


def test_token_name_is_derived_from_the_username():
    assert token_name("juan") == "aurora-dev-juan"


# --------------------------------------------------------------------------
# The admin's lever
# --------------------------------------------------------------------------

def _active_handler(is_admin=False, final_active=False, login="juan"):
    def handler(method, url, data, basic):
        if method == "PATCH":
            return None
        return _user(is_admin=is_admin, login=login, active=final_active)
    return handler


def test_suspend_patches_active_false_and_confirms_it_took(monkeypatch):
    stub = _install(monkeypatch, _active_handler(final_active=False))
    set_active(URL, ADMIN, "juan", False, DEVS)
    patches = stub.sent("PATCH")
    assert len(patches) == 1
    assert patches[0]["url"] == f"{URL}/api/v1/admin/users/juan"
    assert patches[0]["data"]["active"] is False
    # Required by the endpoint even when unchanged; omitting them is a 422 that
    # reads like a permission error.
    assert patches[0]["data"]["login_name"] == "juan"
    assert patches[0]["data"]["source_id"] == 0


def test_suspend_raises_when_forgejo_did_not_actually_deactivate(monkeypatch):
    """A 200 on the PATCH is not proof the account changed."""
    _install(monkeypatch, _active_handler(final_active=True))
    with pytest.raises(AccessError) as exc:
        set_active(URL, ADMIN, "juan", False, DEVS)
    assert "did NOT take" in str(exc.value)


def test_suspend_refuses_an_account_absent_from_developers_yaml(monkeypatch):
    """Otherwise this is a one-argument command that can deactivate any account."""
    stub = _install(monkeypatch, _active_handler())
    with pytest.raises(AccessError) as exc:
        set_active(URL, ADMIN, "stranger", False, DEVS)
    assert "developers.yaml" in str(exc.value)
    assert stub.calls == []


def test_suspend_refuses_to_deactivate_a_site_admin(monkeypatch):
    """Locking the admin out of its own forge is not a revocation."""
    stub = _install(monkeypatch, _active_handler(is_admin=True))
    with pytest.raises(AccessError) as exc:
        set_active(URL, ADMIN, "juan", False, DEVS)
    assert "site admin" in str(exc.value)
    assert stub.sent("PATCH") == []


def test_restore_patches_active_true(monkeypatch):
    stub = _install(monkeypatch, _active_handler(final_active=True))
    set_active(URL, ADMIN, "juan", True, DEVS)
    assert stub.sent("PATCH")[0]["data"]["active"] is True


# --------------------------------------------------------------------------
# The CLI surface
# --------------------------------------------------------------------------

DEVS_YAML = """developers:
- username: juan
  display_name: Juan
  forgejo_user: juan
"""

CLI_ENV = {
    "FORGEJO_URL": URL,
    "FORGEJO_ADMIN_TOKEN": ADMIN,
    "AURORA_PROFILE_URL": "https://example.invalid/profile.git",
    "DOMAIN_NAME": "example.invalid",
    "COMPOSE_PROJECT_NAME": "br-test",
}


def _cli(monkeypatch, tmp_path, admin_env=True):
    from typer.testing import CliRunner
    devs = tmp_path / "developers.yaml"
    devs.write_text(DEVS_YAML)
    monkeypatch.setenv("DEVELOPERS_YAML", str(devs))
    for k, v in CLI_ENV.items():
        if admin_env or k != "FORGEJO_ADMIN_TOKEN":
            monkeypatch.setenv(k, v)
    if not admin_env:
        monkeypatch.delenv("FORGEJO_ADMIN_TOKEN", raising=False)
    monkeypatch.setenv("FORGEJO_DEV_PASSWORD", PW)
    return CliRunner()


def test_cli_mint_prints_the_secret_once_and_how_to_revoke_it(monkeypatch, tmp_path):
    from dev_administration import cli
    runner = _cli(monkeypatch, tmp_path)
    minted = dict(_token(11, "aurora-dev-juan"), sha1="S3CR3TVALUE")
    _install(monkeypatch, _mint_handler(created=minted))

    result = runner.invoke(cli.app, ["access", "mint", "juan"])

    assert result.exit_code == 0, result.output
    assert result.output.count("S3CR3TVALUE") == 1, result.output
    assert "dev-admin access revoke juan" in result.output


def test_cli_mint_works_with_no_admin_token_in_the_environment(monkeypatch, tmp_path):
    """The whole point: a developer mints without holding an admin credential.

    If `mint` ever calls _load_config() this goes red on the KeyError.
    """
    from dev_administration import cli
    runner = _cli(monkeypatch, tmp_path, admin_env=False)
    minted = dict(_token(11, "aurora-dev-juan"), sha1="S3CR3TVALUE")
    _install(monkeypatch, _mint_handler(created=minted))

    result = runner.invoke(cli.app, ["access", "mint", "juan"])

    assert result.exit_code == 0, result.output
    assert "S3CR3TVALUE" in result.output


def test_cli_mint_exits_nonzero_and_prints_no_secret_when_refused(monkeypatch, tmp_path):
    from dev_administration import cli
    runner = _cli(monkeypatch, tmp_path)
    _install(monkeypatch, _mint_handler(is_admin=True))

    result = runner.invoke(cli.app, ["access", "mint", "juan"])

    assert result.exit_code == 1
    assert "site admin" in result.output


def test_cli_ls_never_prints_a_secret_even_if_the_api_returns_one(monkeypatch, tmp_path):
    """Forgejo does not return sha1 from the list route. This pins that `ls`
    would not leak it if a future Forgejo did, and that a personal token is
    labelled rather than hidden."""
    from dev_administration import cli
    runner = _cli(monkeypatch, tmp_path)
    listed = [
        dict(_token(11, "aurora-dev-juan"), sha1="LEAKED"),
        _token(9, "juans-laptop"),
    ]

    def handler(method, url, data, basic):
        if url.endswith("/tokens"):
            return listed
        if url.endswith("/branch_protections"):
            return [{"rule_name": "main"}]
        if url.endswith("/permission"):
            return {"permission": "write"}
        if url.endswith("/api/v1/user"):
            return {"login": "supergoodname77"}
        if "/repos/" in url:
            return {"full_name": "supergoodname77/aurora", "default_branch": "main"}
        return _user()
    _install(monkeypatch, handler)

    result = runner.invoke(cli.app, ["access", "ls"])

    assert result.exit_code == 0, result.output
    assert "aurora-dev-juan" in result.output, "vacuous — nothing was listed"
    assert "LEAKED" not in result.output
    assert "(personal)" in result.output
    assert "(managed)" in result.output


def test_cli_revoke_exits_nonzero_when_there_was_nothing_to_revoke(monkeypatch, tmp_path):
    """`revoke` reporting success on a no-op tells an admin access is gone
    when it may never have been managed here in the first place."""
    from dev_administration import cli
    runner = _cli(monkeypatch, tmp_path)
    _install(monkeypatch, _revoke_handler([_token(9, "juans-laptop")]))

    result = runner.invoke(cli.app, ["access", "revoke", "juan"])

    assert result.exit_code == 1
    assert "No aurora-dev-juan" in result.output


def test_cli_suspend_says_plainly_that_it_is_not_a_revocation(monkeypatch, tmp_path):
    """An admin who believes `suspend` destroyed the token will not chase the
    token that is still there. The wording is the safety property."""
    from dev_administration import cli
    runner = _cli(monkeypatch, tmp_path)
    _install(monkeypatch, _active_handler(final_active=False))

    result = runner.invoke(cli.app, ["access", "suspend", "juan"])

    assert result.exit_code == 0, result.output
    assert "not a revocation" in result.output
    assert "access restore juan" in result.output


def test_cli_offers_no_way_to_put_a_password_in_argv(monkeypatch, tmp_path):
    """A password in argv is visible to every user on the host via `ps` and
    lands in shell history. `--password hunter2` is exactly how someone puts it
    there, so the flag has to not EXIST -- its help text saying "never from an
    argument" while accepting one is worse than no warning at all."""
    from dev_administration import cli
    runner = _cli(monkeypatch, tmp_path)
    _install(monkeypatch, _mint_handler(created=dict(_token(11, "aurora-dev-juan"), sha1="X")))

    for command in ("mint", "revoke"):
        assert "--password" not in runner.invoke(
            cli.app, ["access", command, "--help"]).output
        assert runner.invoke(
            cli.app, ["access", command, "juan", "--password", PW]).exit_code != 0
    assert runner.invoke(cli.app, ["access", "mint", "juan", PW]).exit_code != 0


def test_curl_sends_basic_credentials_through_stdin_not_argv():
    """Pins the fix, not the intent: argv is world-readable via `ps`, and
    subprocess copies it verbatim into CalledProcessError.cmd."""
    from dev_administration import forgejo_utils
    with patch("dev_administration.forgejo_utils.subprocess.run") as run:
        run.return_value = type("R", (), {"stdout": "{}", "returncode": 0})()
        forgejo_utils._curl(URL, "", method="POST", basic=("juan", "hunter2"))
    argv, kwargs = run.call_args[0][0], run.call_args[1]
    assert "hunter2" not in " ".join(argv), f"password leaked into argv: {argv}"
    assert "juan" not in " ".join(argv)
    encoded = base64.b64encode(b"juan:hunter2").decode()
    assert encoded in kwargs["input"], "credentials were not sent at all"
    assert "-K" in argv and "-" in argv


def test_a_newline_in_a_password_cannot_inject_curl_options():
    """curl's config file is LINE-oriented, so escaping only `\\` and `"` -- as
    the first version did -- left a password containing a newline able to add
    `insecure` or `proxy = ...` lines of its own. Verified against curl 8.18.0.
    FORGEJO_DEV_PASSWORD comes from the environment, so this needed no
    terminal. base64's alphabet contains no newline, which is why the fix is
    structural rather than another escape rule."""
    from dev_administration import forgejo_utils
    evil = 'x"\ninsecure\nproxy = http://attacker.invalid'
    with patch("dev_administration.forgejo_utils.subprocess.run") as run:
        run.return_value = type("R", (), {"stdout": "{}", "returncode": 0})()
        forgejo_utils._curl(URL, "", basic=("juan", evil))
    config = run.call_args[1]["input"]
    assert config.count("\n") == 1, f"the password added config lines: {config!r}"
    assert "insecure" not in config and "proxy" not in config


def test_curl_sends_the_bearer_token_through_stdin_not_argv():
    """The admin token is scope `all`. In argv it is world-readable via `ps`,
    and subprocess copies argv into CalledProcessError.cmd -- so a single 404
    reproduced it in every traceback, and `access ls` prints those."""
    from dev_administration import forgejo_utils
    with patch("dev_administration.forgejo_utils.subprocess.run") as run:
        run.return_value = type("R", (), {"stdout": "{}", "returncode": 0})()
        forgejo_utils._curl(URL, "tok123")
    argv, kwargs = run.call_args[0][0], run.call_args[1]
    assert "tok123" not in " ".join(argv), f"token leaked into argv: {argv}"
    assert "Authorization: token tok123" in kwargs["input"]
    assert "-K" in argv and "-" in argv


# --------------------------------------------------------------------------
# Repository access
#
# A token proves identity and grants nothing. These pin the half that makes it
# mean something -- and the reason it is the collaborator route rather than the
# org team `reconcile` configures.
# --------------------------------------------------------------------------

from dev_administration.forgejo_access import (  # noqa: E402
    ALLOWED_PERMISSIONS,
    assert_permission_allowed,
    authorize_repo,
    collaborators,
    deauthorize_repo,
    default_branch_protection,
    repo_permission,
    resolve_shared_repos,
)

REPO = "supergoodname77/aurora"


def test_the_permission_allowlist_excludes_admin_and_owner():
    """`admin` can delete the repository and rewrite its branch protection."""
    assert ALLOWED_PERMISSIONS, "empty allowlist — every grant below would refuse"
    assert "admin" not in ALLOWED_PERMISSIONS
    assert "owner" not in ALLOWED_PERMISSIONS
    assert ALLOWED_PERMISSIONS == {"read", "write"}


@pytest.mark.parametrize("perm", ["admin", "owner", "ADMIN", "", "none"])
def test_permission_allowlist_refuses_anything_not_listed(perm):
    with pytest.raises(AccessError) as exc:
        assert_permission_allowed(perm)
    assert repr(perm) in str(exc.value)


def _repo_handler(members=(), permission=None, is_admin=False, exists=True,
                  members_after=None, protected=True, default_branch="main"):
    """`members` before any write; `members_after` once a PUT/DELETE is seen.

    `protected` defaults to True so the existing grant tests exercise the happy
    path; the branch-protection guard has its own tests below.
    """
    state = {"written": False}

    def handler(method, url, data, basic):
        if method in ("PUT", "DELETE"):
            state["written"] = True
            return None
        if url.endswith("/branch_protections"):
            return [{"rule_name": default_branch}] if protected else []
        if url.endswith("/collaborators"):
            now = members if not state["written"] else (
                members if members_after is None else members_after)
            return [{"login": m} for m in now]
        if url.endswith("/permission"):
            return {"permission": permission}
        if url.endswith("/api/v1/user"):
            return {"login": "supergoodname77"}
        if "/users/" in url:
            return _user(is_admin=is_admin)
        if "/repos/" in url:
            if not exists:
                raise subprocess.CalledProcessError(22, "curl")
            return {"full_name": REPO, "default_branch": default_branch}
        raise AssertionError(f"unexpected {method} {url}")
    return handler


def test_authorize_puts_the_permission_and_confirms_forgejo_agrees(monkeypatch):
    stub = _install(monkeypatch, _repo_handler(
        members=(), members_after=("juan",), permission="write"))

    assert authorize_repo(URL, ADMIN, "juan", REPO, "write", DEVS) == "write"

    puts = stub.sent("PUT")
    assert len(puts) == 1
    assert puts[0]["url"] == f"{URL}/api/v1/repos/{REPO}/collaborators/juan"
    assert puts[0]["data"] == {"permission": "write"}


def test_authorize_raises_when_the_grant_did_not_take(monkeypatch):
    """PUT answers 204 whether or not the grant means anything.

    The org-team path this replaces failed silently for months for exactly
    this reason: nobody read back.
    """
    _install(monkeypatch, _repo_handler(members=(), members_after=(), permission=None))
    with pytest.raises(AccessError) as exc:
        authorize_repo(URL, ADMIN, "juan", REPO, "write", DEVS)
    assert "did NOT take" in str(exc.value)


def test_authorize_raises_when_forgejo_granted_a_different_permission(monkeypatch):
    _install(monkeypatch, _repo_handler(
        members=(), members_after=("juan",), permission="read"))
    with pytest.raises(AccessError) as exc:
        authorize_repo(URL, ADMIN, "juan", REPO, "write", DEVS)
    assert "reports 'read'" in str(exc.value)


def test_authorize_refuses_an_account_absent_from_developers_yaml(monkeypatch):
    stub = _install(monkeypatch, _repo_handler(members_after=("stranger",), permission="write"))
    with pytest.raises(AccessError) as exc:
        authorize_repo(URL, ADMIN, "stranger", REPO, "write", DEVS)
    assert "developers.yaml" in str(exc.value)
    assert stub.sent("PUT") == []


def test_authorize_refuses_a_site_admin(monkeypatch):
    stub = _install(monkeypatch, _repo_handler(
        is_admin=True, members_after=("juan",), permission="write"))
    with pytest.raises(AccessError) as exc:
        authorize_repo(URL, ADMIN, "juan", REPO, "write", DEVS)
    assert "site admin" in str(exc.value)
    assert stub.sent("PUT") == []


def test_authorize_checks_the_permission_before_it_touches_forgejo(monkeypatch):
    stub = _install(monkeypatch, _repo_handler())
    with pytest.raises(AccessError):
        authorize_repo(URL, ADMIN, "juan", REPO, "admin", DEVS)
    assert stub.calls == []


def test_deauthorize_removes_and_confirms(monkeypatch):
    stub = _install(monkeypatch, _repo_handler(members=("juan",), members_after=()))
    assert deauthorize_repo(URL, ADMIN, "juan", REPO, DEVS) is True
    assert [c["url"] for c in stub.sent("DELETE")] == [
        f"{URL}/api/v1/repos/{REPO}/collaborators/juan"
    ]


def test_deauthorize_raises_if_the_collaborator_survives(monkeypatch):
    _install(monkeypatch, _repo_handler(members=("juan",), members_after=("juan",)))
    with pytest.raises(AccessError) as exc:
        deauthorize_repo(URL, ADMIN, "juan", REPO, DEVS)
    assert "NOT removed" in str(exc.value)


def test_deauthorize_refuses_when_the_collaborator_list_is_unreadable(monkeypatch):
    """Fail closed. An unreadable route is not "nobody has access": returning
    [] here made deauthorize report "was not a collaborator", skip the DELETE,
    and leave the admin believing they had revoked the access."""
    def handler(method, url, data, basic):
        if url.endswith("/collaborators"):
            raise subprocess.CalledProcessError(22, "curl")
        return _user()
    stub = _install(monkeypatch, handler)
    with pytest.raises(AccessError) as exc:
        deauthorize_repo(URL, ADMIN, "juan", REPO, DEVS)
    assert "NOT removed" in str(exc.value)
    assert stub.sent("DELETE") == [], "could not read the list, then deleted anyway"


def test_deauthorize_reports_false_when_they_were_not_a_collaborator(monkeypatch):
    """Non-vacuous: the collaborator list is deliberately not empty."""
    stub = _install(monkeypatch, _repo_handler(members=("ethan", "alice")))
    assert deauthorize_repo(URL, ADMIN, "juan", REPO, DEVS) is False
    assert stub.sent("DELETE") == []


def test_collaborators_returns_logins(monkeypatch):
    _install(monkeypatch, _repo_handler(members=("juan", "ethan")))
    assert collaborators(URL, ADMIN, REPO) == ["juan", "ethan"]


def test_repo_permission_reads_the_permission_field(monkeypatch):
    _install(monkeypatch, _repo_handler(permission="write"))
    assert repo_permission(URL, ADMIN, "juan", REPO) == "write"


def test_resolve_shared_repos_derives_the_owner_from_the_token(monkeypatch):
    """Never a hardcoded owner: the same code runs against production and a
    branch, and a constant is the wrong-identity failure that makes a test go
    red exactly when a branch is correct."""
    _install(monkeypatch, _repo_handler())
    assert resolve_shared_repos(URL, ADMIN, ["aurora"]) == ["supergoodname77/aurora"]


def test_resolve_shared_repos_drops_names_that_do_not_exist(monkeypatch):
    _install(monkeypatch, _repo_handler(exists=False))
    assert resolve_shared_repos(URL, ADMIN, ["aurora", "nope"]) == []


# --------------------------------------------------------------------------
# CLI, repository half
# --------------------------------------------------------------------------

def test_cli_authorize_grants_and_says_a_token_is_still_needed(monkeypatch, tmp_path):
    from dev_administration import cli
    runner = _cli(monkeypatch, tmp_path)
    _install(monkeypatch, _repo_handler(members=(), members_after=("juan",), permission="write"))

    result = runner.invoke(cli.app, ["access", "authorize", "juan", "--repo", REPO])

    assert result.exit_code == 0, result.output
    assert "juan -> write" in result.output
    assert "access mint juan" in result.output


def test_cli_authorize_refuses_admin_permission(monkeypatch, tmp_path):
    from dev_administration import cli
    runner = _cli(monkeypatch, tmp_path)
    stub = _install(monkeypatch, _repo_handler())

    result = runner.invoke(
        cli.app, ["access", "authorize", "juan", "--repo", REPO, "-p", "admin"])

    assert result.exit_code == 1
    assert "not on the developer allowlist" in result.output
    assert stub.sent("PUT") == []


def test_cli_deauthorize_exits_nonzero_when_nothing_was_removed(monkeypatch, tmp_path):
    from dev_administration import cli
    runner = _cli(monkeypatch, tmp_path)
    _install(monkeypatch, _repo_handler(members=("ethan",)))

    result = runner.invoke(cli.app, ["access", "deauthorize", "juan", "--repo", REPO])

    assert result.exit_code == 1
    assert "was not a collaborator" in result.output


def test_cli_ls_reports_repository_access_not_only_tokens(monkeypatch, tmp_path):
    """A token that reaches no repository is the failure this feature hit in
    its first acceptance run. `ls` has to show that state."""
    from dev_administration import cli
    runner = _cli(monkeypatch, tmp_path)

    def handler(method, url, data, basic):
        if url.endswith("/tokens"):
            return [dict(_token(11, "aurora-dev-juan"), sha1="LEAKED")]
        if url.endswith("/branch_protections"):
            return []
        if url.endswith("/permission"):
            return {"permission": "none"}
        if url.endswith("/api/v1/user"):
            return {"login": "supergoodname77"}
        if "/repos/" in url:
            return {"full_name": REPO, "default_branch": "main"}
        return _user()
    _install(monkeypatch, handler)

    result = runner.invoke(cli.app, ["access", "ls"])

    assert result.exit_code == 0, result.output
    assert "aurora-dev-juan" in result.output, "vacuous — nothing was listed"
    assert "LEAKED" not in result.output
    assert "repo supergoodname77/aurora: none" in result.output


# --------------------------------------------------------------------------
# The branch-protection guard
#
# `write` on a repo whose default branch has no protection rule is push access
# to main. The acceptance run against a branch stack found exactly that: the
# push succeeded, because reconcile's ensure_branch_protection targets the org
# namespace while the repos are user-owned, so it has never protected anything.
# --------------------------------------------------------------------------

def test_authorize_refuses_write_when_the_default_branch_is_unprotected(monkeypatch):
    stub = _install(monkeypatch, _repo_handler(
        members_after=("juan",), permission="write", protected=False))
    with pytest.raises(AccessError) as exc:
        authorize_repo(URL, ADMIN, "juan", REPO, "write", DEVS)
    assert "no branch protection" in str(exc.value)
    assert "'main'" in str(exc.value)
    assert stub.sent("PUT") == [], "refused, then granted write anyway"


def test_authorize_allows_write_when_the_branch_is_protected(monkeypatch):
    stub = _install(monkeypatch, _repo_handler(
        members_after=("juan",), permission="write", protected=True))
    assert authorize_repo(URL, ADMIN, "juan", REPO, "write", DEVS) == "write"
    assert len(stub.sent("PUT")) == 1


def test_authorize_allows_read_on_an_unprotected_repo(monkeypatch):
    """Read cannot push, so the guard must not block it — a guard that blocks
    the safe case gets disabled wholesale."""
    stub = _install(monkeypatch, _repo_handler(
        members_after=("juan",), permission="read", protected=False))
    assert authorize_repo(URL, ADMIN, "juan", REPO, "read", DEVS) == "read"
    assert len(stub.sent("PUT")) == 1


def test_authorize_write_on_an_unprotected_repo_needs_an_explicit_override(monkeypatch):
    stub = _install(monkeypatch, _repo_handler(
        members_after=("juan",), permission="write", protected=False))
    assert authorize_repo(
        URL, ADMIN, "juan", REPO, "write", DEVS, allow_unprotected=True) == "write"
    assert len(stub.sent("PUT")) == 1


def test_protection_is_matched_against_the_repos_own_default_branch(monkeypatch):
    """A rule on `main` does not protect a repo whose default branch is
    `trunk`. Comparing against a constant instead of the repo's own identity is
    the wrong-identity failure this project has already been bitten by."""
    _install(monkeypatch, _repo_handler(
        members_after=("juan",), permission="write",
        protected=True, default_branch="trunk"))
    branch, protected = default_branch_protection(URL, ADMIN, REPO)
    assert branch == "trunk"
    assert protected is True


def test_default_branch_protection_reports_false_when_there_are_no_rules(monkeypatch):
    _install(monkeypatch, _repo_handler(protected=False))
    assert default_branch_protection(URL, ADMIN, REPO) == ("main", False)


def test_cli_authorize_refuses_write_on_an_unprotected_repo(monkeypatch, tmp_path):
    from dev_administration import cli
    runner = _cli(monkeypatch, tmp_path)
    stub = _install(monkeypatch, _repo_handler(
        members_after=("juan",), permission="write", protected=False))

    result = runner.invoke(cli.app, ["access", "authorize", "juan", "--repo", REPO])

    assert result.exit_code == 1
    assert "no branch protection" in result.output
    assert "--allow-unprotected" in result.output
    assert stub.sent("PUT") == []


def test_cli_ls_flags_an_unprotected_default_branch(monkeypatch, tmp_path):
    """An admin reading `ls` needs to see that write here means push-to-main."""
    from dev_administration import cli
    runner = _cli(monkeypatch, tmp_path)

    def handler(method, url, data, basic):
        if url.endswith("/tokens"):
            return [_token(11, "aurora-dev-juan")]
        if url.endswith("/branch_protections"):
            return []
        if url.endswith("/permission"):
            return {"permission": "write"}
        if url.endswith("/api/v1/user"):
            return {"login": "supergoodname77"}
        if "/repos/" in url:
            return {"full_name": REPO, "default_branch": "main"}
        return _user()
    _install(monkeypatch, handler)

    result = runner.invoke(cli.app, ["access", "ls"])

    assert result.exit_code == 0, result.output
    assert "main UNPROTECTED" in result.output


def test_an_unreadable_branch_protections_route_reads_as_unprotected(monkeypatch):
    """Fail closed. If we cannot tell whether main is defended, we must not
    hand out push access to it — `except: return True` is how a guard becomes
    decorative without anyone noticing."""
    def handler(method, url, data, basic):
        if url.endswith("/branch_protections"):
            raise subprocess.CalledProcessError(22, "curl")
        if "/repos/" in url:
            return {"full_name": REPO, "default_branch": "main"}
        return _user()
    _install(monkeypatch, handler)
    assert default_branch_protection(URL, ADMIN, REPO) == ("main", False)


def test_authorize_refuses_write_when_protection_cannot_be_read(monkeypatch):
    def handler(method, url, data, basic):
        if url.endswith("/branch_protections"):
            raise subprocess.CalledProcessError(22, "curl")
        if url.endswith("/collaborators"):
            return []
        if url.endswith("/api/v1/user"):
            return {"login": "supergoodname77"}
        if "/users/" in url:
            return _user()
        if "/repos/" in url:
            return {"full_name": REPO, "default_branch": "main"}
        return _user()
    stub = _install(monkeypatch, handler)
    with pytest.raises(AccessError):
        authorize_repo(URL, ADMIN, "juan", REPO, "write", DEVS)
    assert stub.sent("PUT") == []
