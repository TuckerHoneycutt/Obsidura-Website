from __future__ import annotations

import secrets
import string
# Still required: seven `except subprocess.CalledProcessError:` handlers
# in this module. Dropping it does NOT break the import -- the name is
# only resolved when a handler actually runs -- so every one of them
# would raise NameError instead of catching, and reconcile's broad
# `except Exception` would swallow that as a warning. Removed once while
# de-duplicating _curl; caught by grep, not by the suite.
import subprocess

# The hardened one. This module used to carry a byte-for-byte COPY of the
# pre-Task-11 _curl, which meant the startup-race retry did not cover the
# calls that hit Forgejo FIRST: reconcile begins with ensure_org / ensure_team
# / add_team_repo, all of which live here. compose.yml's comment claiming the
# residual Caddy-recreate window "is covered by the bounded retry in
# forgejo_utils._curl" was therefore true only of the four OAuth2 endpoints.
# Worse, reconcile swallows failures from this block, so during that window
# org and team setup failed silently and reconcile reported success with
# nothing configured.
from dev_administration.forgejo_utils import LOCAL_AUTH_SOURCE_ID, _curl


def generate_temp_password(length: int = 24) -> str:
    """Generate a random temporary password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_user(forgejo_url: str, token: str, username: str) -> dict | None:
    """Fetch a Forgejo user, or None if absent.

    Uses /api/v1/users/<name> — the /admin/ variant is 405 in Forgejo v15.
    The numeric ``id`` is what the authz gate pins an agent to, because it
    survives a username change.
    """
    try:
        result = _curl(f"{forgejo_url}/api/v1/users/{username}", token)
        return result if isinstance(result, dict) else None
    except subprocess.CalledProcessError:
        return None


def user_exists(forgejo_url: str, token: str, username: str) -> bool:
    """Check if a Forgejo user exists.

    Uses the ordinary user endpoint, NOT ``/admin/users/<name>`` — that path
    does not exist in Forgejo v15 and answers 405 Method Not Allowed, which
    curl reports as a generic failure. Treating that as "user absent" makes
    provisioning try to create an existing account, fail, and (before this was
    fixed) print a temp password that was never actually set.
    """
    try:
        _curl(f"{forgejo_url}/api/v1/users/{username}", token)
        return True
    except subprocess.CalledProcessError:
        return False


def create_user(forgejo_url: str, token: str, username: str, email: str, temp_password: str) -> dict:
    """Create a Forgejo user account. Returns the user object."""
    return _curl(
        f"{forgejo_url}/api/v1/admin/users",
        token,
        method="POST",
        data={
            "username": username,
            "email": email,
            "password": temp_password,
            "must_change_password": True,
            "send_notify": False,
            "source_id": LOCAL_AUTH_SOURCE_ID,
            "login_name": username,
        },
    )


def ensure_org(forgejo_url: str, token: str, org_name: str, owner: str) -> dict | None:
    """Create a Forgejo organization if it doesn't exist. Returns org object or None."""
    try:
        return _curl(f"{forgejo_url}/api/v1/orgs/{org_name}", token)
    except subprocess.CalledProcessError:
        return _curl(
            f"{forgejo_url}/api/v1/orgs",
            token,
            method="POST",
            data={
                "username": org_name,
                "visibility": "private",
                "repo_admin_change_team_access": True,
            },
        )


def ensure_team(forgejo_url: str, token: str, org_name: str, team_name: str, permission: str = "read") -> dict | None:
    """Create a team in the org if it doesn't exist. Returns team object."""
    teams = _curl(f"{forgejo_url}/api/v1/orgs/{org_name}/teams", token)
    if teams:
        for team in teams:
            if team.get("name") == team_name:
                return team
    return _curl(
        f"{forgejo_url}/api/v1/orgs/{org_name}/teams",
        token,
        method="POST",
        data={
            "name": team_name,
            "permission": permission,
            "includes_all_repositories": False,
            "units": ["repo.code", "repo.issues", "repo.pulls"],
        },
    )


def add_team_repo(forgejo_url: str, token: str, org_name: str, team_name: str, repo_name: str) -> None:
    """Add a repo to a team (gives team read access)."""
    # Find team ID
    teams = _curl(f"{forgejo_url}/api/v1/orgs/{org_name}/teams", token)
    if not teams:
        return
    team_id = None
    for team in teams:
        if team.get("name") == team_name:
            team_id = team.get("id")
            break
    if team_id is None:
        return
    try:
        _curl(
            f"{forgejo_url}/api/v1/teams/{team_id}/repos/{org_name}/{repo_name}",
            token,
            method="PUT",
        )
    except subprocess.CalledProcessError:
        pass  # Already added


def add_team_member(forgejo_url: str, token: str, org_name: str, team_name: str, username: str) -> None:
    """Add a user to a team."""
    teams = _curl(f"{forgejo_url}/api/v1/orgs/{org_name}/teams", token)
    if not teams:
        return
    team_id = None
    for team in teams:
        if team.get("name") == team_name:
            team_id = team.get("id")
            break
    if team_id is None:
        return
    try:
        _curl(
            f"{forgejo_url}/api/v1/teams/{team_id}/members/{username}",
            token,
            method="PUT",
        )
    except subprocess.CalledProcessError:
        pass


def ensure_branch_protection(
    forgejo_url: str,
    token: str,
    org_name: str,
    repo_name: str,
    branch: str = "main",
    required_approvals: int = 1,
) -> None:
    """Set branch protection on a shared repo. No direct pushes, requires approval."""
    try:
        existing = _curl(
            f"{forgejo_url}/api/v1/repos/{org_name}/{repo_name}/branch_protections",
            token,
        )
        if existing:
            for rule in existing:
                if rule.get("rule_name") == branch or rule.get("branch_name") == branch:
                    return  # Already protected
    except subprocess.CalledProcessError:
        pass

    try:
        _curl(
            f"{forgejo_url}/api/v1/repos/{org_name}/{repo_name}/branch_protections",
            token,
            method="POST",
            data={
                "rule_name": branch,
                "enable_push": False,
                "enable_status_check": False,
                "required_approvals": required_approvals,
                "block_on_outdated_branch": True,
            },
        )
    except subprocess.CalledProcessError:
        pass