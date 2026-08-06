# Connect Hermes to Forgejo

## Recommended: Forgejo MCP/API integration

1. Open Forgejo:

```text
https://superserver.tailc67a98.ts.net/git/
```

2. Create a Forgejo access token:

```text
User Settings → Applications → Generate New Token
```

Grant only the scopes needed, usually repository read/write and issue access.

3. Add the token to Hermes as a secret/environment variable. Do not put it in a committed file:

```dotenv
FORGEJO_URL=https://superserver.tailc67a98.ts.net/git
FORGEJO_TOKEN=your-token
```

4. Connect Hermes using either:

- a Forgejo MCP server, if you have one available; or
- a small custom Hermes tool that calls the Forgejo REST API.

The tool should support only the operations you need, such as:

```text
list repositories
read repository files
create branch
create commit
open pull request
read issues
comment on issue
```

## Simple alternative: Git over SSH

Forgejo SSH is currently bound on the host at port `222` and is proxied locally. Clone using the Forgejo SSH endpoint configured for your deployment, for example:

```bash
git clone ssh://git@superserver.tailc67a98.ts.net:222/USER/REPO.git
```

Use a dedicated SSH key and add its public key in Forgejo:

```text
User Settings → SSH / GPG Keys → Add Key
```

## For the reduced Compose fork

The reduced stack still needs Forgejo configuration before launch:

```dotenv
FORGEJO__server__ROOT_URL=https://superserver.tailc67a98.ts.net/git/
FORGEJO__server__DOMAIN=superserver.tailc67a98.ts.net
```

Keep Forgejo behind Caddy and do not expose its administrative port publicly.

## Security

- Use a dedicated token/key for Hermes.
- Grant the minimum repository scopes.
- Store secrets in `.env`, an external secret manager, or Docker secrets.
- Never commit the token or private key.
- Prefer read-only access until Hermes needs to write code.
- Use pull requests and human review for writes.

## Practical recommendation

Start with Git over SSH for repository operations. Add a Forgejo API/MCP tool later for repository discovery, issues, pull requests, and structured actions.

## Multi-tenant HTTP MCP (deployed)

A centralized `forgejo-mcp` container runs in `--transport http` mode with no
global token. Each operator adds their own token to their local Hermes config;
the MCP server never sees it.

### One-time setup for each operator

1. Mint a personal token at *Forgejo → Settings → Applications* with scopes
   `repository`, `issue`, `user`.
2. Inside the running hermes container:

   ```bash
   hermes mcp add forgejo --url http://forgejo-mcp:8080/mcp --auth header
   ```

3. When prompted, paste your token. Hermes stores it locally in
   `~/.hermes/.env`; nothing changes in git.
4. Test: `hermes chat -q "List issues in <owner>/<repo> on the forgejo MCP"`.
5. Restart the session (`/reset`) for the MCP tools to load.

### Why HTTP, not stdio

Each `forgejo-mcp` container holds zero credentials. Revoking a token is a
one-line Forgejo UI click — no compose redeploy, no shared secret rotation.
Multiple Hermes instances (you + team) can connect to the same server, each
authenticated with its own token.

### Upgrading forgejo-mcp

1. Bump the image tag in `compose.yml` (e.g. `v2.30.2` → `v2.31.0`)
2. `docker compose up -d forgejo-mcp` — pulls the new image and restarts
3. `hermes mcp test forgejo` — verify tools still discover
