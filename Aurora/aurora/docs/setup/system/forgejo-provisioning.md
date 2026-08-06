# Forgejo Provisioning (admin, first start)

Run this once when Forgejo is fresh (no admin user yet). These steps set up the admin account, confirm the URL/domain config from compose, and verify the MCP server can reach Forgejo.

## 1. First-run admin setup

Forgejo shows a setup page on first visit. Open it:

```
https://superserver.tailc67a98.ts.net/git/
```

Fill in:
- **Administrator username** — your choice (this becomes the admin account)
- **Password** — strong, stored only in Forgejo's DB
- **Email** — optional but useful for notifications
- **Server domain** — should auto-fill from `FORGEJO__server__DOMAIN` in `.env` (`superserver.tailc67a98.ts.net`). If not, set it here.
- **Forgejo base URL** — should auto-fill from `FORGEJO__server__ROOT_URL` in `.env` (`https://superserver.tailc67a98.ts.net/git/`). If not, set it here.

Click **Install Forgejo**. Takes ~10 seconds.

## 2. Verify the config took

In Forgejo: **Site Administration** → **Configuration**
- `ROOT_URL` should be `https://superserver.tailc67a98.ts.net/git/`
- `Domain` should be `superserver.tailc67a98.ts.net`

If wrong, fix in `.env` and `docker compose restart forgejo`.

## 3. Confirm the forgejo-mcp server can reach Forgejo

```bash
docker exec forgejo-mcp --transport http --url https://superserver.tailc67a98.ts.net/git --help 2>&1 | head -5
# Or check it's already running and responding:
docker exec hermes curl -fsS -X POST http://forgejo-mcp:8080/mcp \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

Should return a JSON response with `serverInfo.name: "Forgejo MCP Server"`.

## 4. Each user connects independently

Point teammates at `setup/user/forgejo-setup.md`. They mint their own token and run `hermes mcp add` on their own Hermes instance. No admin action needed per user.

## 5. (Optional) Create the first repository

Either via the Forgejo web UI, or via the MCP once a user is connected:

```bash
hermes chat -q "Use the forgejo MCP to create a repo called 'infra' under my user, private"
```
