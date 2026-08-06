# Connect Hermes to Forgejo (per-user)

Run this once inside your Hermes container after the admin has provisioned Forgejo (see `system/forgejo-provisioning.md`).

## 1. Create a personal access token

1. Open Forgejo: **https://superserver.tailc67a98.ts.net/git/**
2. If this is your first login, **change your password** — the account is
   created with `must_change_password` and nothing else works until you do.
3. Top-right avatar → **Settings** → **Applications** → **Generate New Token**
4. Scopes: `repository` (read+write), `issue` (read+write), `user` (read).
   Do not pick `all` or anything `:admin`.
5. Copy the token

The same token is your git password over HTTPS:

```bash
git clone https://<you>:<token>@superserver.tailc67a98.ts.net/git/<owner>/<repo>.git
```

**A token grants nothing on its own.** If `clone` says *Repository not found*,
ask an admin to run `dev-admin access authorize <you>` — that is a separate
step and it is theirs. `USERGUIDE.md` §2 is the whole picture, including how an
admin can cut your access off (`access suspend`) and what survives it.

## 2. Wire Hermes to the MCP server

```bash
hermes mcp add forgejo --url http://forgejo-mcp:8080/mcp --auth header
```

When prompted, paste your token. Hermes stores it in `~/.hermes/.env` — never in git.

## 3. Verify

```bash
hermes mcp list              # should show forgejo ✓ enabled
hermes mcp test forgejo      # should discover ~128 tools
```

Restart your session (`/reset`) if tools don't appear immediately.

## 4. Rotate your token

There is no rotation command and no window in which two tokens are valid:
delete, then create. Forgejo → Settings → Applications → delete old token, mint
new one:

```bash
hermes config set mcp_servers.forgejo.headers.Authorization "Bearer <new-token>"
/reset
```
