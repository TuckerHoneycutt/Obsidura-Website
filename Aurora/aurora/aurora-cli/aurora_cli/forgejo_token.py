"""Branch-scoped Forgejo admin credential (spec 2026-08-01, P3).

The defect
----------
`branch-env.yaml` overrides fourteen variables and `FORGEJO_ADMIN_TOKEN` is
not one of them, so a branch inherits production's. That would be merely
untidy if the two forges were unrelated -- but a branch's Forgejo is a
**byte-copy of production's database**: same users, same `access_token` rows,
same `token_hash`/`token_salt`. The inherited token therefore authenticates
against **both**, and a branch's `dev-admin` is holding a credential that is
valid on production's API. `branch.py`'s module docstring even records this as
a benefit -- "seeding paying for itself" -- which it is, for exactly one step,
and a liability from then on.

The order, which is the whole design
------------------------------------
1. the branch's Forgejo starts, seeded from production;
2. using the **inherited** token against the **branch's own** API, identify
   the account production's admin credential belongs to, and mint a NEW admin
   token for it in the branch's forge;
3. write it into the branch `.env` as `FORGEJO_ADMIN_TOKEN`;
4. delete production's token rows from the branch's copy of the database.

**Steps 2 and 4 cannot be swapped.** The credential step 2 authenticates with
is the credential step 4 destroys. Run 4 first and step 2 gets 401 -- and it
gets 401 for a reason that reads like "Forgejo is broken" rather than "you
inverted two steps", which is why `mint_admin_token` names the ordering in its
own 401 message rather than leaving the reader to work it out.

After step 4 the branch holds no credential valid against production, and
production's token hashes are not sitting in the branch's data at rest.

Where the spec and the API disagree, and why the code follows the API
---------------------------------------------------------------------
The spec says step 2 mints "via the branch's own API" with the inherited
token. **That endpoint does not accept it.** Measured 2026-08-01 against a
throwaway Forgejo seeded from a read-only snapshot of production's database,
Forgejo 15.0.5+gitea-1.22.0:

    POST /api/v1/users/{u}/tokens   Authorization: token <t>  -> 401
                                    Authorization: Basic u:<t> -> 401
                                    ?token=<t>                 -> 401
        {"message":"auth method not allowed"}
    GET  /api/v1/users/{u}/tokens   Authorization: token <t>  -> 200
    GET  /api/v1/user               Authorization: token <t>  -> 200
    forgejo admin user generate-access-token --raw (in-container) -> 0

Forgejo requires a real password on the create-token route, and no password
exists anywhere on this host. So the mint runs through the forge's own CLI
inside the branch's container, and the inherited token keeps the two jobs the
API *will* do with it: saying whose credential is being replaced, and
confirming afterwards that the new one works. The ordering constraint the
spec is built on survives unchanged -- step 2 still cannot run after step 4 --
because the identification is what step 4 destroys.

What this deliberately does not purge
-------------------------------------
`oauth2_application` rows carry client secrets copied from production, and
they are a real instance of the same class. They are out of scope here on
purpose: `dev-admin reconcile` actively creates and rewrites OAuth apps in the
branch's forge, so deleting them is a change to what a branch *is*, not a
credential-scoping fix, and it belongs in its own phase with its own
acceptance. Naming it here is the point -- an unenumerated item is how the
image-tag escape happened (spec 1).

Dependencies: standard library only.
"""

from __future__ import annotations

import json
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

#: The variable this module owns. Listed in `branch-env.yaml` as
#: `secret: true` so `access_doc` refuses to render a document naming it or
#: carrying its value, and with a derivation that resolves to nothing at
#: render time -- see `envfile._derive_minted_after_up` for why that is not an
#: oversight but the mechanism.
ADMIN_TOKEN_VAR = "FORGEJO_ADMIN_TOKEN"

#: The branch Forgejo's SQLite database, relative to the branch worktree.
#: `seed.HOST_PATH_PLAN` copies `forgejo/` wholesale and snapshots every
#: database beneath it, so this path is the branch's own copy and never
#: production's.
FORGEJO_DB_RELPATH = Path("forgejo") / "gitea" / "gitea.db"

#: Scope of the minted token. `all` matches what production's `dev-admin`
#: token carries and what `reconcile` needs (it creates users, orgs, teams,
#: branch protections and OAuth apps). A narrower scope here would be a
#: different, welcome change, but it is a change to what reconcile can do and
#: would fail at a different step, so it does not ride along with P3.
TOKEN_SCOPES: tuple[str, ...] = ("all",)

#: Seconds SQLite waits for the branch Forgejo's own writer to release the
#: database before giving up. The file is bind-mounted into a RUNNING
#: container, so contention is expected rather than exceptional; the default
#: of 5s turns an ordinary commit into `database is locked` mid-`branch up`.
SQLITE_BUSY_TIMEOUT = 30.0

HTTP_TIMEOUT = 30.0


class ForgejoTokenError(RuntimeError):
    """The branch's admin credential could not be scoped to the branch.

    Never carries a token value: this is raised on paths that `branch up`
    turns into `BranchUpFailed`, whose message is printed.
    """


# ---------------------------------------------------------------------------
# what gets purged, and why -- data, not code
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PurgeRule:
    """One table of production credentials to remove from the branch's copy.

    A table with a written reason, rather than a hard-coded `DELETE`, for the
    reason `branch-env.yaml` is a file: a list somebody remembered is the same
    failure one release later, and a rule that declines to say what it is
    protecting cannot be reviewed.
    """

    table: str
    why: str
    #: Column matched against the ids to keep. `None` means keep nothing.
    keep_column: str | None = None


PURGE_PLAN: tuple[PurgeRule, ...] = (
    PurgeRule(
        table="access_token",
        keep_column="id",
        why=(
            "Every API token production had. Each row is a `token_hash` and "
            "`token_salt` that production's Forgejo will accept, so every one "
            "of them is a live production credential sitting in the branch's "
            "database -- not just the one `.env` names. The row minted in "
            "step 2 is the only survivor."
        ),
    ),
    PurgeRule(
        table="forgejo_auth_token",
        why=(
            "Long-term `remember me` web-session tokens. Same shape as the "
            "API tokens one table over: copied byte-wise, valid against "
            "production's web UI, and reachable by anyone who can read the "
            "branch's worktree. Nothing in the branch needs them -- their "
            "owners log in again."
        ),
    ),
)


@dataclass
class PurgeReport:
    """How many rows each rule removed, and which tables were absent."""

    deleted: dict[str, int] = field(default_factory=dict)
    absent: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return sum(self.deleted.values())

    def summary(self) -> str:
        parts = [f"{table}: {count}" for table, count in sorted(self.deleted.items())]
        if self.absent:
            parts.append(f"absent tables: {', '.join(self.absent)}")
        return "; ".join(parts) or "nothing to purge"


@dataclass(frozen=True)
class MintedToken:
    """A token minted in the branch's own forge.

    `secret` is the token. `__repr__` is overridden because a traceback prints
    the reprs of locals, and this value is the entire point of P3.
    """

    token_id: int
    name: str
    secret: str
    login: str

    def __repr__(self) -> str:
        return (
            f"MintedToken(token_id={self.token_id!r}, name={self.name!r}, "
            f"login={self.login!r}, secret=<redacted>)"
        )

    __str__ = __repr__


@dataclass
class RotationReport:
    """What `rotate_admin_token` did. Safe to put in a note or a document."""

    login: str = ""
    token_id: int = 0
    token_name: str = ""
    purge: PurgeReport = field(default_factory=PurgeReport)
    env_file: Path | None = None

    def summary(self) -> str:
        return (
            f"minted {self.token_name!r} (id {self.token_id}) as {self.login} "
            f"in the branch's own forge, wrote it to the branch .env, then "
            f"purged production's credential rows -- {self.purge.summary()}"
        )


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
            raise ForgejoTokenError(
                f"the branch's Forgejo answered HTTP {self.status} with a body "
                f"that is not JSON: {exc}"
            ) from exc


#: `(url, method, headers, body) -> Response`. The seam exists so no test in
#: this repository can reach a real forge by accident, and so the tests drive
#: the real code rather than a second implementation of it.
Opener = Callable[[str, str, Mapping[str, str], bytes | None], Response]


def urllib_opener(
    url: str,
    method: str,
    headers: Mapping[str, str],
    body: bytes | None,
) -> Response:
    """The real opener. A 4xx is an ANSWER and comes back as a `Response`.

    Deliberately not `curl` through `branch.CommandRunner`, even though that
    is the one-subprocess-seam pattern this package otherwise follows: an
    `Authorization: token ...` header passed as argv is visible in `ps`, is
    recorded verbatim in `Invocation.argv`, and is interpolated into
    `CommandRunner.run`'s failure message. Three leaks, for a stylistic match.
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
        raise ForgejoTokenError(
            f"{method} {url} could not be completed: {type(exc).__name__}: {exc}"
        ) from exc


def _api(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/api/v1{path}"


def whoami(base_url: str, token: str, *, opener: Opener | None = None) -> str:
    """The login the token authenticates as, from the forge at `base_url`.

    `opener` defaults to `None` rather than to `urllib_opener` so the default
    is resolved at CALL time and can be replaced by a test. A default bound at
    `def` time cannot be monkeypatched, which would leave every test in this
    repository one forgotten argument away from a real HTTPS request.
    """
    opener = opener if opener is not None else urllib_opener
    response = opener(
        _api(base_url, "/user"), "GET",
        {"Authorization": f"token {token}"}, None,
    )
    if response.status != 200:
        raise ForgejoTokenError(
            f"GET /api/v1/user against {base_url} answered HTTP "
            f"{response.status}."
        )
    payload = response.json()
    if not isinstance(payload, Mapping) or not payload.get("login"):
        raise ForgejoTokenError(
            f"{base_url} answered 200 to /api/v1/user with no `login` field."
        )
    return str(payload["login"])


def token_name(branch_name: str) -> str:
    """The name the minted token carries in the branch's forge.

    Names the branch, so a token found in a forge answers "which branch minted
    this?" without a lookup, and so a second `branch up` of the same name
    collides visibly (Forgejo refuses a duplicate token name for a user)
    instead of quietly accumulating credentials.
    """
    return f"aurora-branch-{branch_name}"


def list_token_ids(
    base_url: str, login: str, token: str, *, opener: Opener | None = None,
) -> dict[str, int]:
    """`{token_last_eight: id}` for `login`, read with `token`.

    Unlike creating one, LISTING tokens is allowed with token auth on Forgejo
    15.0.5 (measured: 200). This is how the minted row's id is discovered --
    from the forge's own API rather than by reading the database this module
    is about to write to, so the id the purge keeps and the id Forgejo thinks
    it created cannot disagree.
    """
    opener = opener if opener is not None else urllib_opener
    response = opener(
        _api(base_url, f"/users/{urllib.parse.quote(login)}/tokens"), "GET",
        {"Authorization": f"token {token}"}, None,
    )
    if response.status != 200:
        raise ForgejoTokenError(
            f"listing {login}'s tokens at {base_url} answered HTTP "
            f"{response.status}: {_safe_body(response)}"
        )
    payload = response.json()
    if not isinstance(payload, list):
        raise ForgejoTokenError(
            f"{base_url} answered 200 to the token list with a non-array body."
        )
    out: dict[str, int] = {}
    for entry in payload:
        if isinstance(entry, Mapping) and entry.get("token_last_eight"):
            out[str(entry["token_last_eight"])] = int(entry["id"])
    return out


def mint_admin_token(
    base_url: str,
    *,
    inherited_token: str,
    branch_name: str,
    mint: Callable[[str, str], str],
    opener: Opener | None = None,
) -> MintedToken:
    """Step 2. Mint a new admin token in the BRANCH's forge.

    **Not `POST /api/v1/users/{u}/tokens`, and that is a measurement rather
    than a preference.** On the Forgejo this stack runs (15.0.5+gitea-1.22.0)
    that endpoint answers `401 {"message":"auth method not allowed"}` to token
    auth, to `Basic <login>:<token>`, and to `?token=` alike -- verified
    2026-08-01 against a throwaway Forgejo seeded from a read-only snapshot of
    production's database. It wants a real password, which nothing on this
    host has. So the mint goes through the forge's own CLI inside the branch's
    container (`forgejo admin user generate-access-token --raw`), supplied by
    the caller as `mint(login, name) -> token`; keeping it a parameter is what
    keeps this module free of any knowledge of Compose.

    **The inherited token is still load-bearing, and so is the ordering.** It
    is what answers *whose* token this is: `GET /api/v1/user` below returns
    the login that production's admin credential belongs to, and that is the
    account the branch's replacement must be minted for. Deriving it any other
    way -- the first admin in the table, a name in a config file -- is a guess,
    and a guess that is wrong mints a working token for the wrong user and
    leaves the right one's credential in place.

    That call works here for exactly the reason that is also the defect: the
    branch's database is a byte-copy of production's. Which is why it must run
    BEFORE the purge, and why a 401 from it is reported as an ordering failure
    rather than as a Forgejo problem -- the same credential was valid a moment
    earlier, against the same database, so something removed it.
    """
    opener = opener if opener is not None else urllib_opener
    try:
        login = whoami(base_url, inherited_token, opener=opener)
    except ForgejoTokenError as exc:
        raise ForgejoTokenError(
            f"{exc}\n"
            "  ORDERING: the token inherited from production is valid in a "
            "branch only because the branch's Forgejo database is a "
            "byte-copy of production's, and this call is what identifies the "
            "account whose credential is being replaced. Step 2 (identify + "
            "mint) MUST run before step 4 (delete production's token rows), "
            "because step 4 destroys the very credential step 2 "
            "authenticates with. A 401 here means those two steps ran in the "
            "wrong order, or the branch was never seeded from production."
        ) from exc

    name = token_name(branch_name)
    secret = mint(login, name).strip()
    if not secret:
        raise ForgejoTokenError(
            f"minting {name!r} for {login} in the branch's own Forgejo "
            "produced no token. `forgejo admin user generate-access-token` "
            "prints the token and nothing else with `--raw`; an empty result "
            "means it did not run, not that it succeeded quietly."
        )

    # Verified against the branch's API with the NEW token, not assumed from
    # the CLI's exit status: what P3 claims is that this credential works on
    # the branch, and only the branch's API can say so.
    if whoami(base_url, secret, opener=opener) != login:
        raise ForgejoTokenError(
            f"the token minted for {login} authenticates as somebody else "
            f"against {base_url}."
        )
    ids = list_token_ids(base_url, login, secret, opener=opener)
    token_id = ids.get(secret[-8:])
    if token_id is None:
        raise ForgejoTokenError(
            f"the token minted for {login} is not in {base_url}'s list of "
            f"{login}'s tokens. Without its id the purge cannot tell the new "
            "row from production's, and would delete the credential it was "
            "creating."
        )
    return MintedToken(
        token_id=int(token_id), name=name, secret=secret, login=login,
    )


def _safe_body(response: Response) -> str:
    text = " ".join(response.body.split())
    return text[:300] if text else "(empty body)"


# ---------------------------------------------------------------------------
# step 4: the purge
# ---------------------------------------------------------------------------


def branch_database(worktree: Path | str) -> Path:
    return Path(worktree) / FORGEJO_DB_RELPATH


def refuse_production_database(db_path: Path | str) -> None:
    """Refuse production's Forgejo database, by resolved path.

    The only DELETE in this repository that could reach production's data is
    the one below, so the guard lives immediately next to it rather than in a
    caller. Compared after `resolve()` so a symlink, a `..` or a relative path
    cannot walk around it.

    A host where production's root cannot be determined is not treated as
    permission to proceed: `identity.production_root()` raising is re-raised
    as a refusal, because "we could not tell whether this is production" and
    "this is not production" are the same input to a `DELETE`.
    """
    from aurora_cli import identity  # local: identity is heavier than this module

    try:
        production = branch_database(identity.production_root()).resolve()
    except Exception as exc:  # noqa: BLE001 -- turned into a refusal, not swallowed
        raise ForgejoTokenError(
            "refusing to purge credential rows: production's root could not "
            f"be determined ({type(exc).__name__}: {exc}), so this cannot be "
            "shown to be a branch's database rather than production's."
        ) from exc
    if Path(db_path).resolve() == production:
        raise ForgejoTokenError(
            f"refusing to delete credential rows from {db_path}: that is "
            "PRODUCTION's Forgejo database. This function exists to scope a "
            "BRANCH's copy, and pointing it at production would delete every "
            "real admin token on the host."
        )


def purge_production_credentials(
    db_path: Path | str,
    *,
    keep_token_ids: Sequence[int] = (),
    plan: Sequence[PurgeRule] = PURGE_PLAN,
) -> PurgeReport:
    """Step 4. Delete production's credential rows from the BRANCH's database.

    Writable, and that is the one thing about this function to be careful
    with: everything else in this package opens Forgejo's database `mode=ro`
    (`seed.connect_readonly`), because everything else in this package is
    reading PRODUCTION's. This one writes -- so before it opens anything it
    refuses production's own database by path, which is the only DELETE in
    this repository that could reach it.

    The database is bind-mounted into a running Forgejo. SQLite is built for
    that (WAL, one writer at a time), so the only accommodation needed is a
    busy timeout long enough for Forgejo's own commits.
    """
    db_path = Path(db_path)
    refuse_production_database(db_path)
    if not db_path.is_file():
        raise ForgejoTokenError(
            f"the branch's Forgejo database is not at {db_path}. Nothing was "
            "purged, so production's token rows are still in this branch's "
            "data at rest."
        )
    keep = [int(value) for value in keep_token_ids]

    report = PurgeReport()
    absent: list[str] = []
    connection = sqlite3.connect(db_path, timeout=SQLITE_BUSY_TIMEOUT)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        for rule in plan:
            if not _table_exists(connection, rule.table):
                absent.append(rule.table)
                continue
            if rule.keep_column and keep:
                placeholders = ",".join("?" for _ in keep)
                cursor = connection.execute(
                    f"DELETE FROM {rule.table} "  # noqa: S608 - table names are module constants
                    f"WHERE {rule.keep_column} NOT IN ({placeholders})",
                    keep,
                )
            else:
                cursor = connection.execute(
                    f"DELETE FROM {rule.table}"  # noqa: S608 - as above
                )
            report.deleted[rule.table] = cursor.rowcount
        connection.commit()
    except sqlite3.Error as exc:
        connection.rollback()
        hint = ""
        if "readonly" in str(exc) or "permission" in str(exc).lower():
            owner = _owner_of(db_path)
            hint = (
                f"\n  {db_path} is owned by {owner} and this process cannot "
                "write it. On the docker runtime the branch's Forgejo runs as "
                "USER_UID=1000 -- the same uid as the host user -- so the "
                "bind-mounted database is writable from here. Under ROOTLESS "
                "podman (spec P4) container uid 1000 maps into the subuid "
                "range instead, and this purge needs `--userns=keep-id` to "
                "stay possible. That is a known cost of P4, recorded here "
                "rather than discovered later."
            )
        raise ForgejoTokenError(
            f"purging production's credential rows from {db_path} failed: "
            f"{exc}. The branch still holds a credential valid against "
            f"production.{hint}"
        ) from exc
    finally:
        connection.close()
    report.absent = tuple(absent)
    return report


def _owner_of(path: Path) -> str:
    try:
        stat = Path(path).stat()
    except OSError:
        return "an owner this process cannot read"
    return f"uid {stat.st_uid}:gid {stat.st_gid}"


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# step 3 and the check that makes step 3 non-optional
# ---------------------------------------------------------------------------


def replace_admin_token(env_text: str, token: str) -> str:
    """Return `env_text` with `FORGEJO_ADMIN_TOKEN` set to `token`.

    Goes through `envfile.parse_env`/`render_env` rather than a regex so the
    result is subject to the same strict `KEY=value` rules as every other
    write to a branch `.env`, and so production's commented bulk survives.
    """
    from aurora_cli import envfile  # local: envfile must not import this module

    parsed = envfile.parse_env(env_text)
    lines = list(parsed.lines)
    replaced = False
    for index, line in enumerate(lines):
        if line.kind == "assignment" and line.key == ADMIN_TOKEN_VAR:
            lines[index] = envfile.EnvLine(
                "assignment", line.raw, ADMIN_TOKEN_VAR, token)
            replaced = True
    if not replaced:
        lines.append(envfile.EnvLine("blank", ""))
        lines.append(envfile.EnvLine(
            "comment",
            f"# {ADMIN_TOKEN_VAR}: minted in this branch's own Forgejo "
            "(spec P3). Production's copy of this variable is valid on "
            "production; this one is not.",
        ))
        lines.append(envfile.EnvLine("assignment", "", ADMIN_TOKEN_VAR, token))
    return envfile.render_env(envfile.EnvFile(lines))


def assert_branch_token_is_scoped(
    env_file: Path | str, *, production_token: str
) -> None:
    """Refuse to continue while the branch `.env` still holds production's token.

    Mutation M9: mint the token but skip the write, and without this check the
    branch simply carries on using the inherited credential -- every container
    starts, `reconcile` succeeds, and the only symptom is that a branch's
    `dev-admin` can administer production. That is a silent failure of the
    exact kind P3 exists to remove, so the write is verified from the file
    rather than assumed from the call having returned.
    """
    from aurora_cli import envfile  # local, as above

    path = Path(env_file)
    try:
        values = envfile.parse_env(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ForgejoTokenError(
            f"cannot read the branch `.env` at {path} to confirm its admin "
            f"token was rotated: {exc}"
        ) from exc
    current = values.get(ADMIN_TOKEN_VAR, "")
    if not current:
        raise ForgejoTokenError(
            f"{path} carries no {ADMIN_TOKEN_VAR}. `dev-admin reconcile` "
            "would start with no credential at all."
        )
    if production_token and current == production_token:
        raise ForgejoTokenError(
            f"{path} still carries production's {ADMIN_TOKEN_VAR}. A token "
            "was minted in the branch's forge but never written, so this "
            "branch would keep using a credential that is valid on "
            "PRODUCTION's API -- which is the whole defect P3 exists to "
            "close. Refusing to continue rather than reconciling with it."
        )


# ---------------------------------------------------------------------------
# the ordered whole
# ---------------------------------------------------------------------------


def rotate_admin_token(
    *,
    base_url: str,
    branch_name: str,
    env_file: Path | str,
    worktree: Path | str,
    write_env: Callable[[Path, str], Path],
    mint: Callable[[str, str], str],
    opener: Opener | None = None,
    plan: Sequence[PurgeRule] = PURGE_PLAN,
) -> RotationReport:
    """Steps 2, 3 and 4, in that order, on a branch whose Forgejo is serving.

    `write_env` and `mint` are required parameters rather than imports.
    `write_env` because the branch `.env` must be written at mode 0600
    (`branch.write_branch_env`) and a second implementation of that here is a
    second place for the mode to be wrong; `mint` because minting means
    running the forge's CLI inside the branch's container, which is Compose's
    business and not this module's. Passing both also keeps this module free
    of a `branch` import, which would be circular.

    The order below is the load-bearing part and is asserted by two tests in
    `aurora-cli/tests/test_forgejo_token.py` --
    `test_the_rotation_mints_writes_then_purges` (the positive) and
    `test_m10_purging_before_minting_fails_and_names_the_ordering` (the
    mutation). The name this used to cite existed nowhere: a reader who
    followed the citation found nothing and had no way to tell whether the
    test had been renamed or never written, in a docstring that calls the
    ordering the whole design.

      2. mint  -- authenticates with the INHERITED token, which is valid here
                  only because the database is a copy of production's;
      3. write -- and then READ BACK, so a mint that never reached the file
                  fails loudly instead of leaving the inherited token in use;
      4. purge -- destroys the credential step 2 needed. Last, always.
    """
    from aurora_cli import envfile  # local: avoids a circular import

    opener = opener if opener is not None else urllib_opener
    env_path = Path(env_file)
    inherited = envfile.parse_env(
        env_path.read_text(encoding="utf-8")
    ).get(ADMIN_TOKEN_VAR, "")
    if not inherited:
        raise ForgejoTokenError(
            f"{env_path} carries no {ADMIN_TOKEN_VAR}, so there is no "
            "credential to mint the branch's own token with. A branch `.env` "
            "inherits it from production's; if it is absent, production's is "
            "too and `reconcile` was never going to work."
        )

    # -- step 2 -----------------------------------------------------------
    minted = mint_admin_token(
        base_url, inherited_token=inherited, branch_name=branch_name,
        mint=mint, opener=opener,
    )

    # -- step 3 -----------------------------------------------------------
    write_env(env_path, replace_admin_token(
        env_path.read_text(encoding="utf-8"), minted.secret))
    assert_branch_token_is_scoped(env_path, production_token=inherited)

    # -- step 4, and NOT before step 2 ------------------------------------
    purge = purge_production_credentials(
        branch_database(worktree), keep_token_ids=(minted.token_id,), plan=plan,
    )

    return RotationReport(
        login=minted.login, token_id=minted.token_id, token_name=minted.name,
        purge=purge, env_file=env_path,
    )


__all__ = [
    "ADMIN_TOKEN_VAR",
    "FORGEJO_DB_RELPATH",
    "ForgejoTokenError",
    "MintedToken",
    "PURGE_PLAN",
    "PurgeReport",
    "PurgeRule",
    "Response",
    "RotationReport",
    "assert_branch_token_is_scoped",
    "branch_database",
    "mint_admin_token",
    "purge_production_credentials",
    "replace_admin_token",
    "rotate_admin_token",
    "token_name",
    "urllib_opener",
    "whoami",
]
