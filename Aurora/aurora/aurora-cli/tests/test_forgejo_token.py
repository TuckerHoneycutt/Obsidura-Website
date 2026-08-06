"""Branch-scoped Forgejo admin credential (spec 2026-08-01, P3).

The claim P3 makes is empirical -- two HTTP calls, both 401 -- and the tests
that make it live in `tests/test_branch_credentials.py`, gated on a live
branch. What is here is the machinery those assertions rest on, exercised
against a real SQLite database and a Forgejo double, plus the three mutations
the spec names:

  M8  skip the purge  -> production's token still works in the branch -> red
  M9  mint but do not write to `.env` -> a LOUD failure, not a silent reuse
  M10 purge before minting -> the failure must NAME the ordering

Nothing here reaches a real forge: `forgejo_token.urllib_opener` is replaced
module-wide by an autouse tripwire, the same shape `test_branch_up.py` uses.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from aurora_cli import envfile, forgejo_token


LOGIN = "supergoodname77"
INHERITED = "d09de971d22ed863c58432336f5c5cd191ab4c5a"
MINTED = "b298ccbd1157435b4e62ed57a19fb84c980071d4"
MINTED_ID = 3
BASE = "https://aurora-demo.example.ts.net/git"


# ---------------------------------------------------------------------------
# doubles
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_real_forge(monkeypatch):
    """No test in this module may reach a real Forgejo."""
    def tripwire(url, method, headers, body):
        raise AssertionError(
            f"TRIPWIRE: this module reached the network: {method} {url}")
    monkeypatch.setattr(forgejo_token, "urllib_opener", tripwire)


class Forge:
    """A branch Forgejo, as an opener. `purged` flips it to post-purge state."""

    def __init__(self) -> None:
        self.purged = False
        self.calls: list[tuple[str, str]] = []

    def __call__(self, url, method, headers, body):
        self.calls.append((method, url))
        token = headers.get("Authorization", "").removeprefix("token ")
        known = {MINTED} if self.purged else {INHERITED, MINTED}
        if token not in known:
            return forgejo_token.Response(
                401, json.dumps({"message": "access token does not exist"}))
        if url.endswith("/api/v1/user"):
            return forgejo_token.Response(200, json.dumps({"login": LOGIN}))
        if url.endswith("/tokens") and method == "GET":
            return forgejo_token.Response(200, json.dumps([
                {"id": MINTED_ID, "name": "aurora-branch-demo",
                 "token_last_eight": MINTED[-8:]}]))
        raise AssertionError(f"unexpected {method} {url}")


@pytest.fixture
def cli_mint(branch_db):
    """`forgejo admin user generate-access-token --raw`, faithfully.

    It prints the token AND inserts the row -- the CLI writes straight to the
    branch's database, and a double that only printed would let the purge's
    `keep_token_ids` match nothing while every assertion still passed.
    """
    def mint(login: str, name: str) -> str:
        assert login == LOGIN, login
        con = sqlite3.connect(branch_db)
        with con:
            con.execute(
                "INSERT OR REPLACE INTO access_token VALUES (?,?,?,?)",
                (MINTED_ID, 1, name, "hash-minted"))
        con.close()
        return MINTED + "\n"
    return mint


@pytest.fixture
def branch_db(tmp_path) -> Path:
    """A branch worktree's copy of production's Forgejo database.

    Two `access_token` rows, because production has two -- and only one of
    them is the one `.env` names. A purge that removed "the admin token" and
    left the other behind would pass a one-row fixture and leave a live
    production credential in every branch.
    """
    path = forgejo_token.branch_database(tmp_path)
    path.parent.mkdir(parents=True)
    con = sqlite3.connect(path)
    with con:
        con.execute("CREATE TABLE access_token (id INTEGER PRIMARY KEY, "
                    "uid INTEGER, name TEXT, token_hash TEXT)")
        con.execute("CREATE TABLE forgejo_auth_token (id INTEGER PRIMARY KEY, "
                    "token_hash TEXT)")
        con.executemany(
            "INSERT INTO access_token VALUES (?,?,?,?)",
            [(1, 1, "Deva Token", "hash-one"), (2, 1, "dev-admin", "hash-two")])
        con.execute("INSERT INTO forgejo_auth_token VALUES (1, 'remember-me')")
    con.close()
    return path


@pytest.fixture
def branch_env(tmp_path) -> Path:
    path = tmp_path / envfile.ENV_FILE_NAME
    path.write_text(
        "DOMAIN_NAME=aurora-demo.example.ts.net\n"
        f"{forgejo_token.ADMIN_TOKEN_VAR}={INHERITED}\n"
        "OTHER=kept\n", encoding="utf-8")
    return path


def write_env(path: Path, text: str) -> Path:
    Path(path).write_text(text, encoding="utf-8")
    return path


def token_rows(db: Path) -> list[tuple]:
    con = sqlite3.connect(db)
    try:
        return con.execute(
            "SELECT id, name FROM access_token ORDER BY id").fetchall()
    finally:
        con.close()


def rotate(tmp_path, branch_env, forge, mint, **kwargs):
    return forgejo_token.rotate_admin_token(
        base_url=BASE, branch_name="demo", env_file=branch_env,
        worktree=tmp_path, write_env=write_env, mint=mint, opener=forge,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# the premise this whole phase rests on
# ---------------------------------------------------------------------------


def test_production_declares_the_token_a_branch_would_inherit():
    """Vacuity guard for everything below.

    P3 exists because a branch `.env` inherits `FORGEJO_ADMIN_TOKEN` from
    production's. If production stopped declaring it, every assertion in this
    module would still pass while describing a situation that no longer
    exists -- so this FAILS rather than skips, and says what to do.
    """
    production = envfile.parse_env(envfile.production_env_text())
    assert production.get(forgejo_token.ADMIN_TOKEN_VAR), (
        f"production's .env no longer declares "
        f"{forgejo_token.ADMIN_TOKEN_VAR}. Either the credential moved, in "
        "which case P3 must follow it, or Forgejo is no longer administered "
        "by token, in which case this phase needs re-deriving rather than "
        "re-running."
    )


def test_the_manifest_lists_the_token_as_a_secret_that_is_not_rendered():
    """The manifest entry is the reason `access_doc` redacts this variable.

    Both halves are asserted: `secret: true` (which is what puts it under the
    document scrubber) and a derivation that yields nothing at render time
    (which is what makes the branch INHERIT production's value, without which
    there is nothing to mint from).
    """
    from aurora_cli import access_doc

    entry = {r.name: r for r in envfile.load_manifest()}.get(
        forgejo_token.ADMIN_TOKEN_VAR)
    assert entry is not None, (
        f"{forgejo_token.ADMIN_TOKEN_VAR} is not in {envfile.MANIFEST_NAME}. "
        "A reader of that file is told `anything absent here is INHERITED`, "
        "and would conclude this one was forgotten."
    )
    assert entry.secret, "the minted token is not marked secret"
    assert not entry.fatal, (
        "a fatal entry must be overridden at render time, and this one "
        "deliberately is not: the branch must inherit production's value in "
        "order to have something to mint with."
    )
    assert forgejo_token.ADMIN_TOKEN_VAR in access_doc.secret_variables()


# ---------------------------------------------------------------------------
# the order
# ---------------------------------------------------------------------------


def test_the_rotation_mints_writes_then_purges(
    tmp_path, branch_env, branch_db, cli_mint
):
    forge = Forge()
    report = rotate(tmp_path, branch_env, forge, cli_mint)

    assert report.login == LOGIN
    assert report.token_id == MINTED_ID
    assert token_rows(branch_db) == [(MINTED_ID, "aurora-branch-demo")], (
        "production's token rows survived the purge")
    assert report.purge.deleted["access_token"] == 2
    assert report.purge.deleted["forgejo_auth_token"] == 1

    written = envfile.parse_env(branch_env.read_text(encoding="utf-8"))
    assert written[forgejo_token.ADMIN_TOKEN_VAR] == MINTED
    assert written["OTHER"] == "kept", "the rewrite dropped an unrelated value"


def test_m10_purging_before_minting_fails_and_names_the_ordering(
    tmp_path, branch_env, branch_db, cli_mint
):
    """Mutation M10. The failure must say WHICH two steps are inverted.

    A bare 401 from `/api/v1/user` reads as "the branch's Forgejo is broken",
    which is the wrong thing to go and look at. This is the one failure in
    this module whose MESSAGE is the assertion.
    """
    forgejo_token.purge_production_credentials(branch_db, keep_token_ids=())
    forge = Forge()
    forge.purged = True

    with pytest.raises(forgejo_token.ForgejoTokenError) as raised:
        rotate(tmp_path, branch_env, forge, cli_mint)
    message = str(raised.value)
    for required in ("ORDERING", "byte-copy", "before", "step 4", "401"):
        assert required in message, f"{required!r} missing from:\n{message}"


def test_m9_minting_without_writing_fails_loudly(tmp_path, branch_env, cli_mint):
    """Mutation M9. A branch that kept the inherited token must not proceed.

    The dangerous outcome is not an exception -- it is SUCCESS: every
    container starts, `reconcile` authenticates, and the only symptom is that
    a branch's dev-admin can administer production.
    """
    forge = Forge()
    minted = forgejo_token.mint_admin_token(
        BASE, inherited_token=INHERITED, branch_name="demo",
        mint=cli_mint, opener=forge)
    assert minted.secret == MINTED

    with pytest.raises(forgejo_token.ForgejoTokenError) as raised:
        forgejo_token.assert_branch_token_is_scoped(
            branch_env, production_token=INHERITED)
    assert "still carries production's" in str(raised.value)

    # And the same check PASSES once the write happens, so the assertion above
    # is discriminating rather than always-true.
    write_env(branch_env, forgejo_token.replace_admin_token(
        branch_env.read_text(encoding="utf-8"), MINTED))
    forgejo_token.assert_branch_token_is_scoped(
        branch_env, production_token=INHERITED)


def test_m8_skipping_the_purge_leaves_productions_rows_in_the_branch(
    tmp_path, branch_env, branch_db, cli_mint
):
    """Mutation M8, in the form this module can assert.

    The spec's M8 is `the second acceptance assertion goes green` -- i.e.
    production's token still authenticates against the branch. That call needs
    a live branch and lives in `tests/test_branch_credentials.py`. What is
    checkable here is the state it is a consequence of: with an empty purge
    plan, production's `token_hash` rows are still in the branch's database,
    which is exactly what makes production's token work there.
    """
    forge = Forge()
    rotate(tmp_path, branch_env, forge, cli_mint, plan=())
    survivors = token_rows(branch_db)
    assert (2, "dev-admin") in survivors and (1, "Deva Token") in survivors, (
        "M8 did not reproduce: with no purge plan the rows should survive, so "
        "this mutation is not testing what it claims")

    # Unmutated, they do not.
    branch_env.write_text(
        f"{forgejo_token.ADMIN_TOKEN_VAR}={INHERITED}\n", encoding="utf-8")
    rotate(tmp_path, branch_env, forge, cli_mint)
    assert token_rows(branch_db) == [(MINTED_ID, "aurora-branch-demo")]


# ---------------------------------------------------------------------------
# the purge, on its own
# ---------------------------------------------------------------------------


def test_the_purge_removes_every_production_credential_not_just_the_named_one(
    tmp_path, branch_db
):
    report = forgejo_token.purge_production_credentials(
        branch_db, keep_token_ids=(MINTED_ID,))
    assert report.deleted == {"access_token": 2, "forgejo_auth_token": 1}
    assert token_rows(branch_db) == []


def test_the_purge_refuses_productions_own_database():
    """The only DELETE in this repository that could reach production's data.

    Asserted by path rather than by "we would never call it that way".
    """
    from aurora_cli import identity

    production = forgejo_token.branch_database(identity.production_root())
    with pytest.raises(forgejo_token.ForgejoTokenError) as raised:
        forgejo_token.purge_production_credentials(production)
    assert "PRODUCTION's Forgejo database" in str(raised.value)


def test_a_missing_branch_database_is_an_error_not_a_quiet_success(tmp_path):
    """`nothing to purge` and `there was nothing to purge` differ by an outage.

    A purge that no-ops on a missing file reports success while production's
    token rows sit in a database somewhere else.
    """
    with pytest.raises(forgejo_token.ForgejoTokenError) as raised:
        forgejo_token.purge_production_credentials(
            forgejo_token.branch_database(tmp_path))
    assert "still in this branch's data at rest" in str(raised.value)


def test_every_purge_rule_carries_a_reason():
    assert forgejo_token.PURGE_PLAN, "the purge plan is empty; it purges nothing"
    for rule in forgejo_token.PURGE_PLAN:
        assert rule.why.strip(), f"{rule.table} has no reason recorded"


# ---------------------------------------------------------------------------
# secrets
# ---------------------------------------------------------------------------


def test_no_token_value_reaches_a_repr_or_an_error(tmp_path, branch_env, cli_mint):
    """A traceback prints the reprs of locals. This one must not print a token."""
    minted = forgejo_token.MintedToken(
        token_id=1, name="n", secret=MINTED, login=LOGIN)
    assert MINTED not in repr(minted) and MINTED not in str(minted)
    assert "<redacted>" in repr(minted)

    forge = Forge()
    forge.purged = True
    with pytest.raises(forgejo_token.ForgejoTokenError) as raised:
        forgejo_token.mint_admin_token(
            BASE, inherited_token=INHERITED, branch_name="demo",
            mint=cli_mint, opener=forge)
    assert INHERITED not in str(raised.value), (
        "the failure message repeated the credential it failed with")


def test_the_rewrite_preserves_comments_and_stays_strict(tmp_path):
    """The branch `.env` is rewritten in place, not regenerated.

    Production's `.env` is 11 KB of which most is commented configuration, and
    the diff a human reads to check a branch is worthless if a rotation
    rewrites the file.
    """
    text = ("# a comment with = in it\n"
            f"{forgejo_token.ADMIN_TOKEN_VAR}={INHERITED}\n"
            "\n"
            "# another\n"
            "KEEP=me\n")
    out = forgejo_token.replace_admin_token(text, MINTED)
    assert "# a comment with = in it" in out
    assert "# another" in out
    assert "KEEP=me" in out
    assert f"{forgejo_token.ADMIN_TOKEN_VAR}={MINTED}" in out
    assert INHERITED not in out
    envfile.parse_env(out)  # raises if the rewrite is not strict KEY=value


def test_a_branch_env_with_no_token_is_refused_rather_than_minted_around(
    tmp_path, cli_mint
):
    path = tmp_path / ".env"
    path.write_text("DOMAIN_NAME=x\n", encoding="utf-8")
    with pytest.raises(forgejo_token.ForgejoTokenError) as raised:
        rotate(tmp_path, path, Forge(), cli_mint)
    assert "no credential to mint the branch's own token with" in str(raised.value)
