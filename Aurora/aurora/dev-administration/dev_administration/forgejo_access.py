"""Scoped, per-developer Forgejo access tokens and repository grants.

The admin token in `.env` has scope `all` and no expiry, and has leaked into a
tracked file once already (c1d95fe). A developer who needs to clone, push or
call the API has had no other option. This gives them one.

**Who can do what is decided by Forgejo, not by us.** Measured on
15.0.5+gitea-1.22.0, against a branch stack's own Forgejo:

| Route | admin bearer token | developer's own password (basic) |
|---|---|---|
| `GET  /users/{u}/tokens` | 200 | 200 |
| `POST /users/{u}/tokens` | **401 auth method not allowed** | 201 |
| `DELETE /users/{u}/tokens/{id}` | **401 auth method not allowed** | 204 |
| `PATCH /admin/users/{u}` | 200 | n/a |

That is Gitea's `reqBasicAuth`, and a token presented as a basic-auth password
does not satisfy it. So minting and revoking are the DEVELOPER's own acts, the
admin never holds the credential, and the admin's one unilateral lever is
`set_active` — which SUSPENDS rather than revokes.

The repository half uses the collaborator route, not the org team `reconcile`
configures; see D1/D2 in docs/implementations/2026-07-31-forgejo-dev-access.md
and the refusal message in `authorize_repo`.

No secret is written to any file by this module. Forgejo stores only a hash.
"""
from __future__ import annotations

import subprocess
from collections.abc import Iterable
from fnmatch import fnmatch

from dev_administration.forgejo_org import get_user
from dev_administration.forgejo_utils import LOCAL_AUTH_SOURCE_ID, _curl

TOKEN_NAME_PREFIX = "aurora-dev-"

# What a developer's token may carry. This is a POSITIVE allowlist: a scope is
# permitted only by being listed. A blacklist ("not `all`, not `*:admin`")
# admits every spelling nobody thought of -- `all `, `ALL`, a scope Forgejo
# adds after this line was written, and `write:user`, which is the one that
# would let a token mint more tokens for itself.
ALLOWED_SCOPES = frozenset({
    "read:user",
    "read:repository",
    "write:repository",
    "read:issue",
    "write:issue",
    "read:organization",
})

# Enough to clone, push and open a PR over HTTPS, and nothing else. `read:user`
# is required for git-over-HTTP to resolve the caller at all.
DEFAULT_SCOPES = ("read:user", "write:repository")

# Positive allowlist, for the same reason the scope list is one. `admin` and
# `owner` are real Forgejo collaborator permissions and neither belongs on a
# developer grant -- `admin` can delete the repository and rewrite its
# protection rules.
ALLOWED_PERMISSIONS = frozenset({"read", "write"})


class AccessError(ValueError):
    """A token or repository operation was refused, or did not take."""


def reason(exc: Exception) -> str:
    """A one-line cause, safe to print.

    Never `str(exc)` on a CalledProcessError: that renders the whole argv,
    which callers echo to stdout.
    """
    if isinstance(exc, subprocess.CalledProcessError):
        return f"curl exit {exc.returncode}"
    return str(exc)


def token_name(username: str) -> str:
    """The one token name this tool manages. Derived, never chosen, so `ls` and
    `revoke` can tell it from the developer's own tokens with no local record."""
    return f"{TOKEN_NAME_PREFIX}{username}"


def assert_scopes_allowed(scopes: Iterable[str]) -> tuple[str, ...]:
    """Return `scopes` as a tuple, or raise naming the first disallowed one."""
    scopes = tuple(scopes)
    if not scopes:
        # Not a harmless default: a caller that reached here with an empty list
        # has lost its arguments, and Forgejo would mint a token usable for
        # nothing while reporting success.
        raise AccessError("refusing to mint a token with no scopes")
    for scope in scopes:
        if scope not in ALLOWED_SCOPES:
            raise AccessError(
                f"scope {scope!r} is not on the developer allowlist "
                f"({', '.join(sorted(ALLOWED_SCOPES))}). "
                "Widen ALLOWED_SCOPES deliberately if a developer really needs it."
            )
    return scopes


def assert_permission_allowed(permission: str) -> str:
    if permission not in ALLOWED_PERMISSIONS:
        raise AccessError(
            f"permission {permission!r} is not on the developer allowlist "
            f"({', '.join(sorted(ALLOWED_PERMISSIONS))}). "
            "`admin` and `owner` can delete the repository and rewrite its "
            "branch protection; they are not a developer grant."
        )
    return permission


def _assert_managed(username: str, developer_usernames: Iterable[str]) -> None:
    """Positive proof the target is a managed developer.

    Without it these are one-argument commands that reach any account on the
    host, including the admin's own.
    """
    known = set(developer_usernames)
    if username not in known:
        raise AccessError(
            f"{username!r} is not in developers.yaml (known: "
            f"{', '.join(sorted(known)) or 'none'}). Refusing to touch an "
            "account this stack does not manage."
        )


def _managed_user(forgejo_url: str, token: str, username: str,
                  developer_usernames: Iterable[str]) -> dict:
    """The managed, non-admin developer's user object, or raise. Admin token.

    `is_admin` matters because a grant is only as narrow as the account under
    it: `write` on a site admin reaches every repository on the host, which is
    the credential this feature exists to stop handing out.
    """
    _assert_managed(username, developer_usernames)
    user = get_user(forgejo_url, token, username)
    if user is None:
        raise AccessError(f"Forgejo has no readable user {username!r}")
    if user.get("is_admin"):
        raise AccessError(
            f"{username!r} is a Forgejo site admin. Refusing: a scoped grant on "
            "an admin account is not scoped in any way that matters, and "
            "deactivating one locks the admin out of its own forge."
        )
    return user


def assert_self_grantable(forgejo_url: str, username: str, password: str,
                          developer_usernames: Iterable[str]) -> None:
    """Prove the caller is the managed, non-admin developer they claim to be.

    Authenticated AS the developer, so this doubles as proof they hold the
    password — no admin token is involved anywhere in the minting path.
    """
    _assert_managed(username, developer_usernames)
    try:
        user = _curl(f"{forgejo_url}/api/v1/user", "", basic=(username, password))
    except subprocess.CalledProcessError as exc:
        raise AccessError(
            f"Forgejo rejected {username!r}'s password, or is unreachable "
            f"({reason(exc)})"
        ) from exc
    if not isinstance(user, dict):
        raise AccessError(f"Forgejo returned no user object for {username!r}")
    if user.get("login") != username:
        # `revoke` and `ls` key off the token NAME, so a password belonging to
        # someone else must not mint a token named for this developer.
        raise AccessError(
            f"those credentials belong to {user.get('login')!r}, not {username!r}"
        )
    if user.get("is_admin"):
        raise AccessError(
            f"{username!r} is a Forgejo site admin — a scoped token on an admin "
            "account reaches every repository on the host. Refusing."
        )


def list_tokens(forgejo_url: str, username: str, token: str = "",
                basic: tuple[str, str] | None = None) -> list[dict]:
    """Every access token on `username`'s account. Never includes the secret.

    Works with the admin token as well as with the developer's own password —
    the only route in this module that does.
    """
    result = _curl(f"{forgejo_url}/api/v1/users/{username}/tokens", token, basic=basic)
    return result if isinstance(result, list) else []


def find_managed_token(forgejo_url: str, username: str, token: str = "",
                       basic: tuple[str, str] | None = None) -> dict | None:
    """The `aurora-dev-<user>` token, or None. Ignores the developer's own tokens."""
    wanted = token_name(username)
    for entry in list_tokens(forgejo_url, username, token, basic=basic):
        if entry.get("name") == wanted:
            return entry
    return None


def mint_token(forgejo_url: str, username: str, password: str,
               developer_usernames: Iterable[str],
               scopes: Iterable[str] = DEFAULT_SCOPES) -> dict:
    """Mint the developer's own scoped token. Returns the object, including `sha1`.

    Authenticated as the developer, because Forgejo answers 401 to an admin
    token on this route. The secret is in the return value and nowhere else —
    Forgejo stores a hash, so this is the only moment it exists.
    """
    scopes = assert_scopes_allowed(scopes)
    assert_self_grantable(forgejo_url, username, password, developer_usernames)
    basic = (username, password)

    existing = find_managed_token(forgejo_url, username, basic=basic)
    if existing is not None:
        # Not an upsert. A second live token under a name `revoke` matches only
        # once is a valid credential nobody can find later.
        raise AccessError(
            f"{username} already has {token_name(username)} "
            f"(id {existing.get('id')}, ...{existing.get('token_last_eight', '?')}). "
            f"Forgejo cannot show its secret again — run "
            f"`dev-admin access revoke {username}` first if it is lost."
        )

    created = _curl(
        f"{forgejo_url}/api/v1/users/{username}/tokens", "", method="POST",
        data={"name": token_name(username), "scopes": list(scopes)}, basic=basic,
    )
    if not isinstance(created, dict) or not created.get("sha1"):
        raise AccessError(
            f"Forgejo accepted the request but returned no token for {username}: {created!r}"
        )
    return created


def revoke_token(forgejo_url: str, username: str, password: str,
                 developer_usernames: Iterable[str]) -> dict | None:
    """Delete the managed token and confirm it is gone. None if there was none.

    The developer's own act, for the same reason minting is. The confirming
    re-read is the point: a DELETE that 204s against a route that ignored it
    would otherwise read as success, and "revoked" is a claim someone stops
    worrying about.
    """
    _assert_managed(username, developer_usernames)
    basic = (username, password)
    try:
        existing = find_managed_token(forgejo_url, username, basic=basic)
    except subprocess.CalledProcessError as exc:
        raise AccessError(
            f"cannot read {username}'s tokens ({reason(exc)}) — wrong password, "
            "or Forgejo is unreachable. Nothing was revoked."
        ) from exc
    if existing is None:
        return None

    _curl(f"{forgejo_url}/api/v1/users/{username}/tokens/{existing['id']}",
          "", method="DELETE", basic=basic)

    if find_managed_token(forgejo_url, username, basic=basic) is not None:
        raise AccessError(
            f"Forgejo still lists {token_name(username)} after DELETE — "
            "the token is NOT revoked. Revoke it in the Forgejo UI."
        )
    return existing


def set_active(forgejo_url: str, token: str, username: str, active: bool,
               developer_usernames: Iterable[str]) -> dict:
    """Suspend or restore a developer's whole Forgejo account. Admin token.

    It SUSPENDS, it does not revoke: reactivating the account brings the same
    token back to life, so the durable fix is still the developer running
    `access revoke`. Measured: with `active=false` the token answers 403 on the
    API and git-over-HTTPS refuses the fetch.
    """
    _managed_user(forgejo_url, token, username, developer_usernames)
    # login_name and source_id are required by the endpoint even when
    # unchanged; omitting them is a 422 that reads like a permission error.
    _curl(
        f"{forgejo_url}/api/v1/admin/users/{username}", token, method="PATCH",
        data={"login_name": username, "source_id": LOCAL_AUTH_SOURCE_ID,
              "active": active},
    )
    after = get_user(forgejo_url, token, username)
    if not after or after.get("active") is not active:
        raise AccessError(
            f"Forgejo reports active={(after or {}).get('active')!r} for "
            f"{username} after asking for {active!r} — the change did NOT take."
        )
    return after


# ---------------------------------------------------------------------------
# Repository access
#
# A token proves who you are; it grants nothing on its own. On this stack the
# lever that works is the repository collaborator route, not the org team --
# every shared repo is owned by the ADMIN's user namespace, and a Gitea team
# can only hold repos owned by its own org. See D1 in
# docs/implementations/2026-07-31-forgejo-dev-access.md.
# ---------------------------------------------------------------------------


def collaborators(forgejo_url: str, token: str, repo: str) -> list[str]:
    """Logins with explicit collaborator access to `repo` ("owner/name").

    A failed read propagates. Swallowing it made an unreadable route
    indistinguishable from "nobody has access", and `deauthorize_repo` then
    reported a removal it had never performed.
    """
    result = _curl(f"{forgejo_url}/api/v1/repos/{repo}/collaborators", token)
    return [c.get("login") for c in (result or []) if isinstance(c, dict)]


def _collaborators_or_refuse(forgejo_url: str, token: str, repo: str,
                             username: str) -> list[str]:
    try:
        return collaborators(forgejo_url, token, repo)
    except subprocess.CalledProcessError as exc:
        raise AccessError(
            f"cannot read {repo}'s collaborators ({reason(exc)}), so "
            f"{username}'s access was NOT removed. Fix the read and re-run."
        ) from exc


def repo_permission(forgejo_url: str, token: str, username: str, repo: str) -> str | None:
    """`username`'s effective permission on `repo`, or None if unreadable."""
    route = f"{forgejo_url}/api/v1/repos/{repo}/collaborators/{username}/permission"
    try:
        result = _curl(route, token)
    except subprocess.CalledProcessError:
        return None
    return result.get("permission") if isinstance(result, dict) else None


def resolve_shared_repos(forgejo_url: str, token: str, names: Iterable[str]) -> list[str]:
    """Turn bare repo names into "owner/name" against whoever owns the token.

    Deliberately probes rather than assuming an owner: the same code runs
    against production and against a branch, and a hardcoded owner is the
    wrong-identity failure that made a conformance test go red exactly when a
    branch was correct.
    """
    me = _curl(f"{forgejo_url}/api/v1/user", token)
    owner = me.get("login") if isinstance(me, dict) else None
    if not owner:
        raise AccessError("could not resolve the admin token's own account")
    found = []
    for name in names:
        try:
            _curl(f"{forgejo_url}/api/v1/repos/{owner}/{name}", token)
        except subprocess.CalledProcessError:
            continue
        found.append(f"{owner}/{name}")
    return found


def default_branch_protection(forgejo_url: str, token: str, repo: str) -> tuple[str, bool]:
    """(default branch, whether a protection rule covers it). Fails closed.

    Both reads are guarded and neither guesses a branch name: this answer
    decides whether `write` means push-to-main, and a guessed `main` would have
    the guard checking rules for a branch the repo does not use.
    """
    try:
        info = _curl(f"{forgejo_url}/api/v1/repos/{repo}", token)
    except subprocess.CalledProcessError as exc:
        raise AccessError(
            f"cannot read {repo} ({reason(exc)}), so its default branch is unknown"
        ) from exc
    branch = (info or {}).get("default_branch")
    if not branch:
        raise AccessError(f"{repo} reports no default branch — refusing to guess one")
    try:
        rules = _curl(f"{forgejo_url}/api/v1/repos/{repo}/branch_protections", token)
    except subprocess.CalledProcessError:
        return branch, False
    for rule in rules or []:
        name = rule.get("rule_name") or rule.get("branch_name") or ""
        if name and (name == branch or fnmatch(branch, name)):
            return branch, True
    return branch, False


def authorize_repo(forgejo_url: str, token: str, username: str, repo: str,
                   permission: str, developer_usernames: Iterable[str],
                   allow_unprotected: bool = False) -> str:
    """Give `username` `permission` on `repo`, then prove Forgejo agrees.

    The confirming read is not ceremony: `PUT` answers 204 whether or not the
    grant means anything, and the org-team path this replaces failed silently
    for months precisely because nobody read back.
    """
    assert_permission_allowed(permission)
    _managed_user(forgejo_url, token, username, developer_usernames)

    if permission == "write" and not allow_unprotected:
        # Positive proof that the default branch is defended BEFORE handing out
        # push rights. Checking "is this production" instead would pass here:
        # the repo is a branch's copy and still unprotected.
        branch, protected = default_branch_protection(forgejo_url, token, repo)
        if not protected:
            raise AccessError(
                f"{repo} has no branch protection on {branch!r}, so `write` "
                f"would let {username} push straight to it. Protect the branch "
                f"first, or pass --allow-unprotected if that is really intended. "
                f"(reconcile's ensure_branch_protection does NOT cover this repo "
                f"— it targets the org namespace and these repos are user-owned.)"
            )

    _curl(f"{forgejo_url}/api/v1/repos/{repo}/collaborators/{username}",
          token, method="PUT", data={"permission": permission})

    got = repo_permission(forgejo_url, token, username, repo)
    if got != permission:
        raise AccessError(
            f"asked for {permission!r} on {repo}, Forgejo reports {got!r} — "
            "the grant did NOT take."
        )
    return got


def deauthorize_repo(forgejo_url: str, token: str, username: str, repo: str,
                     developer_usernames: Iterable[str]) -> bool:
    """Remove `username` from `repo`. True if they were on it. Confirms removal."""
    _assert_managed(username, developer_usernames)
    if username not in _collaborators_or_refuse(forgejo_url, token, repo, username):
        return False

    _curl(f"{forgejo_url}/api/v1/repos/{repo}/collaborators/{username}",
          token, method="DELETE")

    if username in _collaborators_or_refuse(forgejo_url, token, repo, username):
        raise AccessError(
            f"Forgejo still lists {username} on {repo} after DELETE — "
            "access is NOT removed."
        )
    return True
