# Multi-Developer Hermes Provisioning Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task. Wait for explicit user approval before starting each phase.

**Goal:** A central config file defines developers. Adding a name provisions a per-developer Hermes container with isolated data, installs the Aurora profile, and exposes it behind a single login page that authenticates against Forgejo OIDC and routes to the right container — no second login.

**Architecture:** Forgejo is already an OIDC provider (verified: `.well-known/openid-configuration` returns RS256 endpoints). Hermes has a built-in `SelfHostedOIDCProvider` that speaks standard OIDC. Caddy (v2.11.4, already running) frontends everything. A small orchestrator service reads a `developers.yaml` config and for each entry: creates a Docker volume for that dev's `$HERMES_HOME`, writes their `.env`, runs `hermes profile install aurora-agent`, and starts a named Hermes container. Caddy routes `/agent/<username>/` to `hermes-<username>:9119`. The Hermes dashboard's OIDC login redirects to Forgejo; on successful auth, the user lands in their own Hermes instance.

**Tech Stack:** Docker Compose, Caddy v2.11.4 (reverse proxy + OIDC-aware routing), Forgejo OIDC, Hermes `SelfHostedOIDCProvider`, a small Python orchestrator script, `developers.yaml` config.

---

## Current state (verified)

| Component | Status | Evidence |
|---|---|---|
| Forgejo OIDC | ✅ Live | `https://superserver.tailc67a98.ts.net/git/.well-known/openid-configuration` returns RS256 endpoints |
| Hermes `SelfHostedOIDCProvider` | ✅ Built in | `/opt/hermes/plugins/dashboard_auth/self_hosted/__init__.py` — standard OIDC RP with PKCE |
| Hermes dashboard auth framework | ✅ Built in | `/opt/hermes/hermes_cli/dashboard_auth/` — pluggable providers, session cookies, login page |
| Caddy | ✅ Running v2.11.4 | `tai-review-caddy-1` on `tai-review_default` network |
| Aurora agent profile | ✅ Published | `aurora-agent` repo in Forgejo — `hermes profile install` works |
| `HERMES_HOME=/opt/data` pattern | ✅ Proven | Ponytail fix showed env var + bind mount works |
| Docker network | ✅ `tai-review_default` | All services (forgejo, hermes, caddy, forgejo-mcp) share it |

## How it works end-to-end

```
Developer "juan" opens:
  https://superserver.tailc67a98.ts.net/agent/

  → Caddy checks: is there a container "hermes-juan"?
    → No → orchestrator sees the request, provisions container, waits for it
    → Yes → reverse_proxy to hermes-juan:9119

  → Hermes dashboard shows OIDC login (redirect to Forgejo)
  → Juan logs into Forgejo (once)
  → Forgejo redirects back with code
  → Hermes OIDC provider verifies, creates session
  → Juan is in his own Hermes dashboard — no second login

  Juan's data:
  - Docker volume: hermes-juan-home → /opt/data inside his container
  - His .env, his sessions, his memories, his credentials
  - Aurora profile installed: same config, same plugins, his own secrets
```

## Data isolation

Each developer gets:
- **Docker volume** `hermes-<name>-home` mounted as `/opt/data` inside their container
- **Their own `.env`** with their API keys and Forgejo token
- **Their own sessions/memories/state.db** inside their volume
- **Same config.yaml, SOUL.md, plugins** from the Aurora profile (distribution-owned, replaced on `hermes profile update`)

No shared filesystem paths. No cross-contamination. `hermes profile update aurora` on each container pulls config changes without touching user data.

---

## Phase 1 — Forgejo OIDC client registration

### Task 1.1: Create an OAuth2 application in Forgejo

**Manual step (admin, Forgejo web UI):**

1. Forgejo → Site Administration → **OAuth2 Applications** → **New Application**
2. Name: `Hermes Dashboard`
3. Redirect URI: `https://superserver.tailc67a98.ts.net/agent/{username}/auth/callback`
   - But: Hermes OIDC provider reconstructs redirect_uri from the request, so this needs to be a wildcard or per-user. Two options:
     - **Option A (simpler):** One OAuth2 app per developer, redirect URI pinned to their path. The orchestrator creates the OAuth2 app via Forgejo API when provisioning a new developer.
     - **Option B (one app, wildcard):** Forgejo doesn't support wildcard redirect URIs. So Option A.
4. Scopes: `openid`, `profile`, `email`
5. Save → note the **Client ID** and **Client Secret**

**Decision needed:** Option A (per-dev OAuth2 app, created by orchestrator) is the only viable path since Forgejo doesn't support wildcard redirects. The orchestrator will create the OAuth2 app via the Forgejo API when provisioning a new developer.

**Automation (for the orchestrator):**
```bash
curl -fsS -X POST "https://superserver.tailc67a98.ts.net/git/api/v1/admin/oauth2_apps" \
  -H "Authorization: token $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "hermes-juan",
    "redirect_uris": ["https://superserver.tailc67a98.ts.net/agent/juan/auth/callback"],
    "scopes": ["openid", "profile", "email"]
  }'
```

---

## Phase 2 — Orchestrator service

### Task 2.1: Create `developers.yaml` config format

**Files:**
- Create: `developers.yaml` (in the aurora repo root, next to compose.yml)

```yaml
# Adding a developer here triggers provisioning on next orchestrator run.
# Remove a developer to stop their container (data volume is preserved).
developers:
  - username: juan
    display_name: Juan Martinez
    forgejo_user: juan
    # Optional: override the aurora profile version
    # profile_ref: "main"
  - username: ethan
    display_name: Ethan Pascuales
    forgejo_user: supergoodname77
```

### Task 2.2: Write the orchestrator script

**Files:**
- Create: `orchestrator/provision.py`

**What it does:**
1. Reads `developers.yaml`
2. For each developer:
   a. Creates Docker volume `hermes-<username>-home` (if not exists)
   b. Creates a Forgejo OAuth2 app via API (if not exists) — gets client_id + client_secret
   c. Writes a per-dev `.env` file into the volume with their OIDC creds + shared env vars
   d. Runs `hermes profile install <aurora-agent-url> --name aurora --force` inside a temp container with that volume
   e. Starts (or restarts) the per-dev Hermes container on `tai-review_default`
   f. Registers the container name as a Caddy upstream (via Docker network DNS — no Caddy reload needed)
3. Removes containers for developers no longer in `developers.yaml` (preserves volumes)

**Key implementation details:**

```python
#!/usr/bin/env python3
"""Provision per-developer Hermes containers from developers.yaml."""

import subprocess, json, os, sys, yaml

FORGEJO_URL = os.environ["FORGEJO_URL"]
FORGEJO_TOKEN = os.environ["FORGEJO_ADMIN_TOKEN"]
AURORA_PROFILE_URL = os.environ.get(
    "AURORA_PROFILE_URL",
    f"{FORGEJO_URL}/supergoodname77/aurora-agent.git"
)
NETWORK = "tai-review_default"
IMAGE = "nousresearch/hermes-agent:latest"
HERMES_PORT = "9119"

def run(cmd, check=True):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, check=check)

def create_volume(name):
    run(f"docker volume create {name}", check=False)  # ignore "already exists"

def create_oauth2_app(username):
    """Create a Forgejo OAuth2 app for this developer's Hermes dashboard."""
    redirect = f"https://superserver.tailc67a98.ts.net/agent/{username}/auth/callback"
    result = run(f'''curl -fsS -X POST "{FORGEJO_URL}/api/v1/admin/oauth2_apps" \
        -H "Authorization: token {FORGEJO_TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{json.dumps({"name": f"hermes-{username}", "redirect_uris": [redirect], "scopes": ["openid","profile","email"]})}' ''')
    app = json.loads(result.stdout)
    return app["client_id"], app["client_secret"]

def provision(dev):
    name = dev["username"]
    vol = f"hermes-{name}-home"
    container = f"hermes-{name}"

    # 1. Volume
    create_volume(vol)

    # 2. OAuth2 app
    client_id, client_secret = create_oauth2_app(name)

    # 3. Write .env into the volume (via temp container)
    env_content = f"""OPENROUTER_API_KEY={os.environ.get('OPENROUTER_API_KEY','')}
FORGEJO_URL={FORGEJO_URL}
HERMES_DASHBOARD=1
HERMES_DASHBOARD_HOST=0.0.0.0
HERMES_DASHBOARD_OIDC_ISSUER={FORGEJO_URL}
HERMES_DASHBOARD_OIDC_CLIENT_ID={client_id}
HERMES_DASHBOARD_OIDC_CLIENT_SECRET={client_secret}
HERMES_HOME=/opt/data
"""
    run(f'docker run --rm -v {vol}:/opt/data alpine sh -c \'cat > /opt/data/.env << "ENVEOF"\n{env_content}ENVEOF\'')

    # 4. Install aurora profile (via temp container with the volume)
    run(f'docker run --rm -v {vol}:/opt/data --network {NETWORK} -e HERMES_HOME=/opt/data '
        f'{IMAGE} hermes profile install {AURORA_PROFILE_URL} --name aurora --force -y')

    # 5. Start the per-dev container
    run(f'docker rm -f {container}', check=False)
    run(f'''docker run -d --name {container} \
        --network {NETWORK} \
        -v {vol}:/opt/data \
        -e HERMES_HOME=/opt/data \
        --restart unless-stopped \
        {IMAGE} gateway run''')

    print(f"✓ Provisioned {name} → {container} on :{HERMES_PORT}")

def deprovision(dev):
    name = dev["username"]
    container = f"hermes-{name}"
    run(f'docker rm -f {container}', check=False)
    print(f"✓ Stopped {container} (volume preserved)")

if __name__ == "__main__":
    with open("developers.yaml") as f:
        config = yaml.safe_load(f)
    devs = {d["username"]: d for d in config.get("developers", [])}

    # Provision new/updated devs
    for dev in config.get("developers", []):
        provision(dev)

    # Deprovision removed devs
    existing = {c.split("-")[1] for c in
                run("docker ps -a --format '{{.Names}}' | grep '^hermes-'").stdout.split()}
    for name in existing - set(devs):
        deprovision({"username": name})
```

### Task 2.3: Add orchestrator to compose

**Files:**
- Modify: `compose.yml` — add an `orchestrator` service

```yaml
  orchestrator:
    image: python:3.13-slim
    container_name: orchestrator
    restart: "no"  # run-once, not a daemon
    volumes:
      - ./developers.yaml:/app/developers.yaml:ro
      - ./orchestrator:/app/orchestrator:ro
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - FORGEJO_URL=${FORGEJO_URL}
      - FORGEJO_ADMIN_TOKEN=${FORGEJO_ADMIN_TOKEN}
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
    working_dir: /app
    command: ["python", "-m", "orchestrator.provision"]
    depends_on:
      - forgejo
      - forgejo-mcp
```

**Note:** The orchestrator runs once on `docker compose up`, provisions all developers, then exits. Re-run with `docker compose run --rm orchestrator` after editing `developers.yaml`.

---

## Phase 3 — Caddy dynamic routing

### Task 3.1: Add per-developer route to Caddyfile

**Files:**
- Modify: `Caddyfile`

The challenge: Caddy needs to route `/agent/<username>/` to `hermes-<username>:9119`, but the set of usernames is dynamic. Two approaches:

**Approach A (recommended): Caddy `handle_path` with a variable upstream**

Caddy v2.11.4 supports `reverse_proxy` with a dynamically constructed upstream name via `{http.matchers.path.capture}`. But Caddy's `reverse_proxy` doesn't support variable interpolation in the upstream address directly. So:

**Approach B (pragmatic): Orchestrator rewrites Caddyfile + reloads Caddy**

The orchestrator, after provisioning, generates the per-dev Caddy blocks and reloads Caddy. This is simpler and more reliable:

```caddyfile
# Per-developer Hermes dashboards — generated by orchestrator
handle /agent/juan/* {
    uri strip_prefix /agent/juan
    reverse_proxy hermes-juan:9119
}
handle /agent/juan {
    reverse_proxy hermes-juan:9119
}

handle /agent/ethan/* {
    uri strip_prefix /agent/ethan
    reverse_proxy hermes-ethan:9119
}
handle /agent/ethan {
    reverse_proxy hermes-ethan:9119
}
```

**Approach C (best): Caddy layer4 or `dynamic_upstreams` with Docker labels**

Caddy's `dynamic_upstreams` can discover upstreams from SRV records or A records, but not from Docker labels directly. There are community Caddy plugins for Docker discovery, but adding a plugin requires a custom Caddy build.

**Decision: Approach B.** The orchestrator generates a `Caddyfile.d/agents.conf` fragment and signals Caddy to reload. This is the fewest moving parts and uses Caddy's built-in `import` directive.

**Caddyfile changes:**

Add to the main site block, before the default handler:

```caddyfile
# Per-developer agent dashboards — generated by orchestrator
import /etc/caddy/Caddyfile.d/agents.conf
```

Create directory: `Caddyfile.d/` (mounted into Caddy container).

**Orchestrator addition:** After provisioning, write `Caddyfile.d/agents.conf` and reload Caddy:

```python
def write_caddy_config(devs):
    lines = []
    for name in sorted(devs):
        lines.append(f"""
handle /agent/{name}/* {{
    uri strip_prefix /agent/{name}
    reverse_proxy hermes-{name}:9119
}}
handle /agent/{name} {{
    reverse_proxy hermes-{name}:9119
}}""")
    with open("Caddyfile.d/agents.conf", "w") as f:
        f.write("\n".join(lines))
    run("docker exec tai-review-caddy-1 caddy reload --config /etc/caddy/Caddyfile")
```

### Task 3.2: Landing page

**Files:**
- Modify: `Caddyfile` — add a handler for `/agent` (no trailing username)

```caddyfile
# Landing page — lists developers with links to their dashboards
handle /agent {
    respond `<!DOCTYPE html>
<html><head><title>Aurora — Agent Dashboard</title></head>
<body style="font-family:system-ui;max-width:600px;margin:80px auto">
<h1>Aurora</h1>
<p>Select your agent dashboard:</p>
<div id="agents"></div>
<script>
fetch("/agents.json").then(r=>r.json()).then(devs=>{
    document.getElementById("agents").innerHTML =
    devs.map(d=>`<p><a href="/agent/${d.username}/">${d.display_name}</a></p>`).join("");
});
</script>
</body></html>` 200
}

# Agent list for the landing page
handle /agents.json {
    respond `{"developers":[{"username":"ethan","display_name":"Ethan Pascuales"}]}` 200
    # ponytail: hardcoded JSON; orchestrator should generate this file
}
```

**Better approach:** The orchestrator writes `agents.json` to a file served by Caddy, instead of hardcoding it in the Caddyfile.

---

## Phase 4 — Hermes OIDC configuration

### Task 4.1: Add OIDC config to the Aurora profile

**Files:**
- Modify: `aurora-agent/config.yaml` — add dashboard OIDC settings

```yaml
dashboard:
  oauth:
    provider: self-hosted
    self_hosted:
      issuer: https://superserver.tailc67a98.ts.net/git
      # client_id and client_secret come from per-dev .env
      # (HERMES_DASHBOARD_OIDC_CLIENT_ID / _CLIENT_SECRET)
      scopes: "openid profile email"
```

**Note:** The `issuer` is shared across all developers (same Forgejo). The `client_id` and `client_secret` are per-developer (each gets their own OAuth2 app in Forgejo), injected via `.env`.

### Task 4.2: Verify OIDC login flow

After provisioning, open `https://superserver.tailc67a98.ts.net/agent/<username>/`:

1. Hermes dashboard shows login page
2. Click login → redirects to Forgejo OIDC authorize endpoint
3. User logs into Forgejo (if not already)
4. Forgejo redirects back to Hermes with auth code
5. Hermes exchanges code for ID token, verifies, creates session
6. User is in their Hermes dashboard — no second login

**Potential issue: redirect URI mismatch.** The Hermes OIDC provider reconstructs `redirect_uri` from the incoming request. Behind Caddy reverse_proxy, the `X-Forwarded-Host` and `X-Forwarded-Proto` headers determine the redirect URI. Caddy sets these automatically. The redirect URI will be `https://superserver.tailc67a98.ts.net/agent/<username>/auth/callback` — which must match what was registered in the Forgejo OAuth2 app. The orchestrator handles this by creating the OAuth2 app with the correct redirect URI.

**Potential issue: path prefix.** Hermes dashboard expects to run at `/`, not at `/agent/<username>/`. The Caddy `strip_prefix` handles this — Hermes sees requests as if they're at root. But the OIDC redirect_uri is reconstructed from the *original* request path (before stripping). Need to verify that Hermes' `SelfHostedOIDCProvider` uses `X-Forwarded-*` headers correctly when behind a path-stripping proxy. If not, the redirect URI won't match and OIDC will fail.

**Mitigation if path prefix breaks OIDC:** Use a subdomain per developer instead (`juan.agent.superserver.tailc67a98.ts.net`), which avoids path stripping entirely. But this requires wildcard DNS + TLS certificates. Caddy can do wildcard TLS via Tailscale or Let's Encrypt. This is the clean solution but more setup. Start with path prefix; fall back to subdomains if OIDC breaks.

---

## Phase 5 — Lazy container start (spin-up on demand)

### The problem

Running all developer containers 24/7 wastes resources. The user wants: container starts when the developer logs in, not before.

### Two approaches

**Approach A (simpler): Orchestrator starts all containers on compose up**

Just start all containers. With `restart: unless-stopped`, they stay up. For a small team (< 10 developers), this is fine — each Hermes container uses ~200-400MB idle. Ponytail says: don't build on-demand spin-up until the team is big enough to matter.

**Approach B (on-demand): Caddy + orchestrator webhook**

1. Caddy receives request to `/agent/<username>/`
2. Caddy checks if `hermes-<username>` is up (via a tiny health-check script)
3. If not, Caddy calls the orchestrator API to start the container
4. Orchestrator starts the container and waits for health
5. Caddy proxies the request

This requires a Caddy plugin or an `http.handler` that can trigger a subprocess — not built-in. The pragmatic version:

- A tiny sidecar service (fjell, already Rust/Axum) that receives `POST /start/<username>` from Caddy's `handle` with a `reverse_proxy` to a "waiting" page, then starts the container and returns 200
- Caddy uses `try` + `handle` to attempt the proxy, fall back to the sidecar, retry

**Decision: Approach A for now.** Start all containers. The team is small. Add on-demand spin-up when resource usage matters. YAGNI.

---

## Phase 6 — Documentation

### Task 6.1: Add admin setup guide

**Files:**
- Create: `docs/setup/system/multi-developer-setup.md`

Covers:
- How to add a developer to `developers.yaml`
- How to run the orchestrator
- How to create a Forgejo admin token for the orchestrator
- How to verify a developer's container is working

### Task 6.2: Add developer onboarding guide

**Files:**
- Create: `docs/setup/user/developer-onboarding.md`

Covers:
- "Your admin added you to the system. Go to: `https://superserver.tailc67a98.ts.net/agent/`"
- "Click your name. Log in with your Forgejo credentials."
- "You're in your own Hermes. Your data is isolated."

---

## Files likely to change

| File | Action | Phase |
|---|---|---|
| `developers.yaml` | Create | 2.1 |
| `orchestrator/provision.py` | Create | 2.2 |
| `compose.yml` | Modify (add orchestrator service, mount Caddyfile.d) | 2.3 |
| `Caddyfile` | Modify (add import for agents.conf, landing page) | 3.1 |
| `Caddyfile.d/agents.conf` | Generated by orchestrator | 3.1 |
| `aurora-agent/config.yaml` | Modify (add OIDC dashboard config) | 4.1 |
| `docs/setup/system/multi-developer-setup.md` | Create | 6.1 |
| `docs/setup/user/developer-onboarding.md` | Create | 6.2 |
| `.env` | Modify (add FORGEJO_ADMIN_TOKEN) | 2.3 |
| `.env.template` | Modify (document FORGEJO_ADMIN_TOKEN) | 2.3 |

## Risks / open questions

1. **Path prefix + OIDC redirect URI.** Hermes dashboard runs at `/` by default. Behind Caddy with `strip_prefix /agent/<username>`, the OIDC redirect URI is reconstructed from `X-Forwarded-*` headers. If Hermes doesn't respect `X-Forwarded-Host` / `X-Forwarded-Proto` for OIDC redirect construction, the redirect won't match the registered URI and auth will fail. **Mitigation:** Test with one developer first. If it fails, switch to subdomain-based routing (`<username>.agent.superserver...`) which avoids path stripping entirely.

2. **Forgejo OAuth2 app creation requires admin token.** The orchestrator needs a Forgejo admin token to create OAuth2 apps via the API. This token goes in `.env` as `FORGEJO_ADMIN_TOKEN`. It's powerful — store securely, rotate if leaked.

3. **Per-dev OAuth2 apps accumulate.** Each developer gets their own OAuth2 app in Forgejo. Removing a developer from `developers.yaml` stops their container but doesn't auto-delete the OAuth2 app. An admin should clean those up manually (or extend the orchestrator).

4. **All containers start on compose up (Phase 5 decision).** For a small team this is fine. For >10 developers, consider on-demand spin-up. The orchestrator is designed to be extended with this later.

5. **`hermes profile install` inside a temp container.** The orchestrator runs the profile install in a throwaway container with the dev's volume mounted. This should work (same pattern as the main Hermes container), but needs verification that `profile install` can reach the Forgejo git URL from inside the Docker network.

6. **Caddy reload mechanism.** The orchestrator writes `Caddyfile.d/agents.conf` then calls `caddy reload` inside the Caddy container. If the orchestrator doesn't have Docker exec access, this fails. The orchestrator service mounts the Docker socket (same as Hermes), so it can `docker exec tai-review-caddy-1 caddy reload`.

7. **Single Caddyfile.d mount.** Caddy needs to `import /etc/caddy/Caddyfile.d/agents.conf`. The `Caddyfile.d/` directory must be mounted into the Caddy container. Add to compose: `- ./Caddyfile.d:/etc/caddy/Caddyfile.d:ro`.

## Tests / validation

After running the orchestrator with `developers.yaml` containing one entry:

```bash
# 1. Container is up
docker ps | grep hermes-juan

# 2. Volume exists
docker volume ls | grep hermes-juan-home

# 3. Caddy routes correctly
curl -fsS -o /dev/null -w "%{http_code}" https://superserver.tailc67a98.ts.net/agent/juan/
# Expected: 200 or 302 (redirect to OIDC login)

# 4. OIDC login works (manual: open in browser, log into Forgejo, land in dashboard)

# 5. Data isolation
docker exec hermes-juan ls /opt/data/sessions/
# Should show juan's sessions only, not ethan's
```
