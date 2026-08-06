# Forgejo Org + Permissions Design Spec

**Date:** 2026-07-25
**Status:** Draft

---

## Goal

Developers get their own Forgejo accounts (created by the orchestrator), their own repos (full control), read+PR access to shared repos (no merge without code owner approval), and the admin has full access to everything.

## Forgejo Organization Structure

```
aurora (org)
├── aurora              (shared infra repo — branch protection, code owner approval required)
├── aurora-agent        (shared profile — branch protection, code owner approval required)
├── dev-administration   (shared tool — branch protection, code owner approval required)
├── superpowers          (shared plugin — branch protection, code owner approval required)
├── teams/
│   ├── developers      (read access to all shared repos)
│   └── owners          (admin — full access to all repos)
└── users/
    └── <username>/     (developer's own repos — full control)
```

## Permission Matrix

| Actor | Shared repos (aurora, aurora-agent, etc.) | Developer's own repos |
|---|---|---|
| Developer | Read, create PR, comment. **Cannot merge** without code owner approval. | Full read/write/merge |
| Admin (org owner) | Full access (read, write, merge, delete, admin) | Full access to all |

## Account Creation Flow

1. Admin adds developer to `developers.yaml` with `email` field
2. `reconcile` creates Forgejo user account via admin API:
   - `POST /api/v1/admin/users` with username, email, temp password, `must_change_password=true`
   - Temp password is generated randomly and printed once to stdout
3. Orchestrator adds user to `aurora` org's `developers` team
4. Developer logs into Forgejo with temp password → forced to change it
5. Developer visits `/agent/<username>/` → OIDC → Forgejo → Hermes dashboard

## Branch Protection (shared repos)

Each shared repo gets a branch protection rule on `main`:
- `enable_push: false` (no direct pushes)
- `enable_status_check: true` (if CI exists)
- `required_approvals: 1` (at least one code owner approval)
- `block_on_outdated_branch: true` (must be up to date before merge)

Code owners: admin user only (for now). Can be extended via CODEOWNERS file later.

## developers.yaml Change

```yaml
developers:
  - username: juan
    display_name: Juan Martinez
    forgejo_user: juan
    email: juan@example.com
```

`email` is required for Forgejo account creation. The orchestrator generates a random temp password and prints it once.

## Implementation

### New model: ForgejoOrgConfig

```python
@dataclass
class ForgejoOrgConfig:
    org_name: str       # "aurora"
    team_name: str      # "developers"
    shared_repos: list[str]  # ["aurora", "aurora-agent", "dev-administration", "superpowers"]
```

### New module: `forgejo_org.py`

- `ensure_org(forgejo_url, token, org_name)` — create org if it doesn't exist
- `ensure_team(forgejo_url, token, org_name, team_name, permission)` — create team if it doesn't exist
- `add_team_repo(forgejo_url, token, org_name, team_name, repo)` — add shared repo to team with read access
- `ensure_branch_protection(forgejo_url, token, org_name, repo, required_approvals)` — set branch protection on main
- `create_user(forgejo_url, token, username, email, temp_password)` — create Forgejo user via admin API
- `add_team_member(forgejo_url, token, team_id, username)` — add user to team

### provision.py changes

After OAuth2 app creation, before starting the container:
1. Create Forgejo user (if not exists)
2. Add user to developers team
3. Generate + print temp password (if new user)

### Config

Add to `.env`:
```
FORGEJO_ORG=aurora
FORGEJO_DEV_TEAM=developers
```