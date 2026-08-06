# Multi-Developer Hermes Provisioning — Design Spec

**Date:** 2026-07-25
**Status:** Draft — pending user review
**Supersedes:** None (companion to `docs/tasks/multi-developer-provisioning-ponytail.md`)

---

## Goal

A declarative config file defines developers. Adding an entry provisions a per-developer Hermes container with isolated data, installs the Aurora profile, exposes it behind a single landing page that authenticates against Forgejo OIDC, and routes to the right container — no second login. The orchestrator is a composable CLI tool that can be called manually, by cron, or by a future master orchestrator Hermes agent.

## Architecture

A Python CLI tool (`dev-admin`) reads `developers.yaml` and reconciles Docker state: creates volumes, Forgejo OAuth2 apps, installs the Aurora profile, starts named Hermes containers, generates Caddy routes, and manages SSH authorized_keys. Caddy proxies `/agent/<username>/` to `hermes-<username>:9119`. Hermes authenticates via Forgejo OIDC (`SelfHostedOIDCProvider`). Fjell serves a landing page and a first-run API key setup form. A `Notifier` protocol provides a pluggable event seam for future alarm delivery.

## Tech Stack

- **Orchestrator:** Python 3.13, Typer (CLI), PyYAML, Docker CLI via subprocess, Forgejo REST API via curl/requests
- **Routing:** Caddy v2.11.4 (reverse proxy with generated config fragments)
- **Auth:** Forgejo OIDC (already running, RS256 endpoints verified), Hermes `SelfHostedOIDCProvider`
- **Containers:** Docker (volumes per developer, `aurora_default` network)
- **Setup portal:** Fjell (Rust/Axum, already running on :9080)
- **Developer access:** SSH with forced `docker exec` command via authorized_keys

## Repositories

Three repos in Forgejo, all under `supergoodname77/`:

| Repo | Purpose | Already exists? |
|---|---|---|
| `aurora` | Infrastructure (compose, Caddy, docs) | ✅ |
| `aurora-agent` | Hermes profile distribution (config, SOUL.md, plugins) | ✅ |
| `dev-administration` | Orchestrator CLI + developers.yaml + AGENTS.md + skill | NEW — create in this plan |

---

## Components

### 1. dev-administration repo

```
dev-administration/
  AGENTS.md                          # Master context — "this repo has the orchestrator"
  skills/
    orchestrator/
      SKILL.md                       # Skill for master Hermes: how to use dev-admin CLI
  dev_administration/
    __init__.py
    cli.py                           # Typer app: reconcile, status, doctor, add, remove, deprovision
    provision.py                     # Reconciliation logic (volume, OAuth2, profile, container, Caddy, SSH)
    notifier.py                       # Notifier protocol + StdoutNotifier + FileNotifier
    models.py                        # DeveloperConfig, OrchestratorEvent dataclasses
  developers.yaml                    # Desired state (admin's config)
  pyproject.toml                     # typer, pyyaml deps; entry point: dev-admin = dev_administration.cli:app
  tests/
    test_reconcile.py                # Reconciliation logic tests
    test_notifier.py                 # Notifier protocol tests
```

### 2. developers.yaml format

```yaml
developers:
  - username: juan
    display_name: Juan Martinez
    forgejo_user: juan
  - username: ethan
    display_name: Ethan Pascuales
    forgejo_user: supergoodname77
```

Fields:
- `username` (required) — unique identifier, used for container name, volume name, Caddy route
- `display_name` (required) — shown on landing page
- `forgejo_user` (required) — their Forgejo username for OIDC identity mapping

No secrets, no SSH keys, no API keys in this file. All developer-provided credentials are collected via the fjell setup form.

### 3. dev-admin CLI

```
dev-admin --help

  reconcile      Sync Docker state with developers.yaml
  status         Show all developers, containers, volumes, and health
  doctor         Health check: containers reachable, volumes exist, OAuth2 apps valid
  add            Add a developer entry to developers.yaml
  remove         Remove a developer entry from developers.yaml
  deprovision    Stop a developer's container (preserve volume)
```

**Commands:**

- **`reconcile`** — reads `developers.yaml`, diffs against Docker state, applies changes. Provisions new developers, deprovisions removed ones, verifies existing ones. Idempotent. Generates `Caddyfile.d/agents.conf` + `agents.json`, reloads Caddy, updates `authorized_keys`. Emits events to Notifier.

- **`status`** — prints a table: username, container name, volume, OAuth2 app, status (running/stopped/orphaned). Non-mutating.

- **`doctor`** — health check: `curl` each container's dashboard, verify volumes exist, verify OAuth2 apps are valid in Forgejo. Emits `doctor.warning` / `doctor.critical` events for failures.

- **`add <username> [--display-name NAME] [--forgejo-user USER] [--ssh-key KEY]`** — appends a developer entry to `developers.yaml`. Does NOT provision. Prints "Run `dev-admin reconcile` to provision."

- **`remove <username>`** — removes a developer entry from `developers.yaml`. Does NOT deprovision. Prints "Run `dev-admin reconcile` to deprovision."

- **`deprovision <username>`** — stops and removes the container. Volume preserved. Emits `volume.orphaned` event.

### 4. Notifier protocol

```python
from dataclasses import dataclass
from typing import Protocol

@dataclass
class OrchestratorEvent:
    timestamp: str       # ISO 8601 UTC
    event_type: str      # "developer.provisioned", "container.stopped", "volume.orphaned", etc.
    severity: str        # "info", "warning", "critical"
    developer: str | None # username, or None for system-wide
    message: str         # human-readable
    metadata: dict       # structured details

class Notifier(Protocol):
    def notify(self, event: OrchestratorEvent) -> None: ...
```

Built-in implementations:
- `StdoutNotifier` — prints events to stdout (default)
- `FileNotifier` — appends events to a log file (path configurable)

Future implementations (not built now):
- `McpNotifier` — sends events to the admin's Hermes via MCP
- `WebhookNotifier` — POSTs events to a URL
- `DashboardNotifier` — writes to a dashboard-visible log

Notifier selection: env var `DEV_ADMIN_NOTIFIER` (`stdout`, `file`, or a Python dotted path for custom). Default: `stdout`.

### 5. Provisioning a new developer

Step-by-step (per developer, idempotent):

1. **Volume:** `docker volume create hermes-<username>-home` (skip if exists)
2. **OAuth2 app:** Create via Forgejo API (`POST /api/v1/admin/oauth2_apps`) with redirect URI `https://<domain>/agent/<username>/auth/callback`. Check if `hermes-<username>` app already exists first (idempotent). Store returned `client_id` and `client_secret`.
3. **Write .env:** Via temp alpine container with the volume mounted, write:
   ```dotenv
   FORGEJO_URL=<forgejo url>
   HERMES_HOME=/opt/data
   HERMES_DASHBOARD=1
   HERMES_DASHBOARD_HOST=0.0.0.0
   HERMES_DASHBOARD_OIDC_ISSUER=<forgejo url>
   HERMES_DASHBOARD_OIDC_CLIENT_ID=<client_id>
   HERMES_DASHBOARD_OIDC_CLIENT_SECRET=<client_secret>
   ```
   Note: `OPENROUTER_API_KEY` is NOT written by the orchestrator. The developer provides it via the fjell setup form.
4. **Install Aurora profile:** Run a temp Hermes container with the volume:
   ```bash
   docker run --rm -v hermes-<username>-home:/opt/data \
     --network aurora_default -e HERMES_HOME=/opt/data \
     nousresearch/hermes-agent:latest \
     hermes profile install <aurora-profile-url> --name aurora --force -y
   ```
5. **Start persistent container:**
   ```bash
   docker run -d --name hermes-<username> \
     --network aurora_default \
     -v hermes-<username>-home:/opt/data \
     -e HERMES_HOME=/opt/data \
     --restart unless-stopped \
     nousresearch/hermes-agent:latest gateway run
   ```
6. **Generate Caddy routes:** Append to `Caddyfile.d/agents.conf`:
   ```caddyfile
   handle /agent/<username>/setup {
       reverse_proxy fjell:9080
   }
   handle /agent/<username>/* {
       uri strip_prefix /agent/<username>
       reverse_proxy hermes-<username>:9119
   }
   handle /agent/<username> {
       reverse_proxy hermes-<username>:9119
   }
   ```
7. **Generate agents.json:** Append to `Caddyfile.d/agents.json`:
   ```json
   [{"username": "<username>", "display_name": "<display_name>"}]
   ```
7. **SSH authorized_keys:** No SSH key in this step — the developer provides their SSH public key via the fjell setup form (see Section 8).
8. **Reload Caddy:** `docker exec <caddy-container> caddy reload --config /etc/caddy/Caddyfile`
9. **Emit event:** `developer.provisioned` (info severity)

### 6. Deprovisioning

1. `docker stop hermes-<username>` (graceful, 10s timeout)
2. `docker rm hermes-<username>`
3. Volume **never deleted** — preserved indefinitely
4. Remove Caddy routes from `agents.conf` and `agents.json`
5. Remove SSH authorized_keys entry for this developer (if one exists — fjell may have added it)
6. Reload Caddy
7. Emit `volume.orphaned` (warning severity) — admin knows there's a preserved volume

### 7. Reconciliation logic

```
desired = set of usernames in developers.yaml
actual = set of running containers matching hermes-*
volumes = set of volumes matching hermes-*-home

for dev in desired - actual:
    provision(dev)

for dev in actual - desired:
    deprovision(dev)

for dev in desired ∩ actual:
    verify(dev)  # health check: container responding? volume healthy?
    if not healthy:
        emit("container.unhealthy", warning, dev)
        # attempt restart
        docker restart hermes-<dev>
```

### 8. Fjell (setup portal + landing page)

Fjell is the future internal hub. For now, two route modules:

**`src/routes/landing.rs`** — `GET /agent`
- Reads `agents.json` (mounted from Caddyfile.d)
- Renders a simple HTML page listing developers with links to `/agent/<username>/`

**`src/routes/setup.rs`** — `GET/POST /agent/<username>/setup`

- GET: HTML form with two fields:
  1. OpenRouter API key (required, password-type input)
  2. SSH public key (optional, textarea — paste your `~/.ssh/id_ed25519.pub`)
- POST: **Overwrite action.** Writes/updates both fields:
  - API key: removes any existing `OPENROUTER_API_KEY=` line from the volume's `.env`, appends the new one. Uses `docker exec hermes-<username> sh -c 'sed -i "/^OPENROUTER_API_KEY=/d" /opt/data/.env; echo "OPENROUTER_API_KEY=<value>" >> /opt/data/.env'`
  - SSH key (if provided): removes any existing authorized_keys entry matching `hermes-<username>`, appends the new forced-command entry: `command="docker exec -it hermes-<username> bash",no-port-forwarding,no-X11-forwarding <ssh_key>`
  - SSH key (if left blank): removes any existing authorized_keys entry for this developer. Does not add one.
  - Redirects to `/agent/<username>/` after write
- Revisitable: the developer can return to `/agent/<username>/setup` anytime to update either field. Each submission is an overwrite — previous values are deleted before the new ones are written.
- Requires Docker socket access (already mounted in fjell) and the developer's container to be running.

**Fjell code structure:**

```
fjell/src/
  main.rs           # Router assembly, bind 0.0.0.0:9080
  routes/
    mod.rs           # route registration — add new modules here
    landing.rs       # GET /agent — developer list
    setup.rs         # GET/POST /agent/<username>/setup — API key form
  config.rs          # Load agents.json, resolve volume paths
```

Each route module is self-contained. Future routes (dashboard, docs, admin panel) add a new module + one line in `mod.rs`.

### 9. Caddy changes

**Caddyfile** — add before the default handler:

```caddyfile
# Per-developer agent dashboards — generated by dev-admin reconcile
import /etc/caddy/Caddyfile.d/agents.conf
```

**Caddy compose volume** — add to caddy service:

```yaml
volumes:
  - ./Caddyfile.d:/etc/caddy/Caddyfile.d:ro
```

### 10. Compose changes

New services in `compose.yml`:

```yaml
# dev-administration orchestrator — run-once or cron-triggered
dev-admin:
  image: python:3.13-slim
  container_name: dev-admin
  restart: "no"
  volumes:
    - ./dev-administration:/app:ro
    - ./developers.yaml:/app/developers.yaml
    - /var/run/docker.sock:/var/run/docker.sock
    - ./Caddyfile.d:/app/Caddyfile.d
    # authorized_keys is mounted read-write so both fjell (setup form)
    # and dev-admin (deprovision cleanup) can manage SSH entries.
    - ~/.ssh/authorized_keys:/app/authorized_keys
  environment:
    - FORGEJO_URL=${FORGEJO_URL}
    - FORGEJO_ADMIN_TOKEN=${FORGEJO_ADMIN_TOKEN}
    - AURORA_PROFILE_URL=${AURORA_PROFILE_URL}
    - DOMAIN_NAME=${DOMAIN_NAME}
  working_dir: /app
  command: ["python", "-m", "dev_administration.cli", "reconcile"]
  depends_on:
    - forgejo
```

Fjell gets two new volume mounts (Docker socket + authorized_keys) for the setup form. Updated compose entry:

```yaml
fjell:
  build: ./fjell
  restart: unless-stopped
  ports:
    - 127.0.0.1:9080:9080
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock
    - ~/.ssh/authorized_keys:/app/authorized_keys
```

### 11. Aurora profile OIDC config

Add to `aurora-agent/config.yaml`:

```yaml
dashboard:
  oauth:
    provider: self-hosted
    self_hosted:
      issuer: https://superserver.tailc67a98.ts.net/git
      scopes: "openid profile email"
```

`client_id` and `client_secret` come from per-dev `.env` (set by the orchestrator during provisioning).

### 12. .env additions (aurora repo)

```dotenv
FORGEJO_ADMIN_TOKEN=<forgejo admin token>
AURORA_PROFILE_URL=https://superserver.tailc67a98.ts.net/git/supergoodname77/aurora-agent.git
```

### 13. AGENTS.md (dev-administration repo)

```markdown
# dev-administration

This repo contains the `dev-admin` CLI for provisioning per-developer Hermes containers.

## Usage

Load the `orchestrator` skill for command reference: `skill_view("orchestrator")`.

Key commands:
- `dev-admin reconcile` — sync Docker state with developers.yaml
- `dev-admin status` — show all developers and container states
- `dev-admin doctor` — health check all containers
- `dev-admin add <username> --display-name "Name" --forgejo-user user` — add a developer
- `dev-admin remove <username>` — remove a developer
- `dev-admin deprovision <username>` — stop a developer's container (preserves volume)

The config file is `developers.yaml` at the repo root. The orchestrator is
idempotent and can be called manually, by cron, or by the master orchestrator Hermes.

## Composability

The CLI is non-interactive and designed for automation:
- Cron: `0 * * * * cd /app && python -m dev_administration.cli reconcile`
- Master Hermes: `terminal("dev-admin status")` or `terminal("dev-admin reconcile")`
- Events emitted via the Notifier protocol are available for future alarm systems
```

### 14. Orchestrator skill (for master Hermes)

`skills/orchestrator/SKILL.md` — full command reference, `developers.yaml` schema, event types list, and usage examples. The master Hermes loads this skill when asked about developer management, container lifecycle, or system reconciliation.

---

## Data Flow

```
Admin edits developers.yaml
  → dev-admin reconcile
    → for each new developer:
      1. docker volume create hermes-<name>-home
      2. Forgejo API: create OAuth2 app → client_id, client_secret
      3. Write .env to volume (FORGEJO_URL, OIDC creds, HERMES_HOME)
      4. Temp container: hermes profile install aurora-agent
      5. docker run -d hermes-<name> (restart: unless-stopped)
      6. Generate Caddy routes + agents.json
      7. Update authorized_keys (SSH forced docker exec)
      8. Reload Caddy
      9. Emit developer.provisioned event

Developer opens https://superserver.../agent/<name>/
  → Caddy strips /agent/<name>, proxies to hermes-<name>:9119
  → Hermes dashboard shows OIDC login
  → Redirect to Forgejo /login/oauth/authorize
  → Developer logs into Forgejo (if not already)
  → Forgejo redirects back with auth code
  → Hermes verifies ID token, creates session
  → Developer is in their Hermes dashboard

First time: developer visits /agent/<name>/setup
  → Fjell serves API key form
  → Developer pastes OpenRouter API key
  → Fjell writes to volume's .env
  → Developer restarts their container (or Hermes reloads .env)

Developer SSH access:
  ssh <name>@superserver.tailc67a98.ts.net -p 222
  → forced command: docker exec -it hermes-<name> bash
  → lands directly in their container
```

---

## Security

- **Secrets isolation:** Each developer's `.env` is in their own Docker volume. No cross-access. The orchestrator writes OIDC creds but never API keys.
- **SSH:** Forced `docker exec` command — no host shell access. `no-port-forwarding`, `no-X11-forwarding` restrictions.
- **Forgejo admin token:** Used by the orchestrator to create OAuth2 apps. Stored in the aurora `.env` (gitignored). Powerful — rotate if leaked.
- **OIDC:** Each developer gets their own OAuth2 app in Forgejo with a pinned redirect URI. Revoking the app blocks their access.
- **Volumes:** Never auto-deleted. Admin manually cleans up orphaned volumes via `docker volume rm`.
- **Network:** `forgejo-mcp` and developer containers share `aurora_default`. No public ports on developer containers — only Caddy can reach them.

---

## Risks

1. **OIDC redirect URI behind path prefix.** Hermes `SelfHostedOIDCProvider` must correctly reconstruct the redirect URI from `X-Forwarded-*` headers when behind Caddy's `strip_prefix`. If it constructs the URI as `https://superserver.../auth/callback` (without the `/agent/<username>/` prefix), the OAuth2 app's registered redirect won't match and auth will fail. **Mitigation:** test with one developer first. Fallback: subdomain-based routing.

2. **Fjell writing to developer volumes.** Fjell writes `.env` files via `docker exec` into the developer's container. This requires Docker socket access in fjell (already mounted) and the developer's container to be running. If the container is stopped, the setup form can't write. **Mitigation:** the setup form shows a message "Container is starting, please wait" if the container isn't reachable, and retries. The orchestrator starts the container before the developer would visit the setup page.

3. **Caddy reload timing.** The orchestrator writes `agents.conf` then signals Caddy to reload. If Caddy is mid-reload and a developer hits the route, they get a 502. **Mitigation:** Caddy reloads are atomic (old config serves until new config validates). Low risk.

4. **Forgejo OAuth2 app accumulation.** Removed developers' OAuth2 apps stay in Forgejo. **Mitigation:** the orchestrator can delete the OAuth2 app on deprovision (via Forgejo API `DELETE /api/v1/admin/oauth2_apps/<id>`). Requires storing the app ID. Add to `developers.yaml` as an optional `oauth2_app_id` field, or query Forgejo by name.

5. **Container resource usage.** All developer containers start on `compose up`. For <10 developers this is fine (~200-400MB idle each). **Mitigation:** YAGNI — add on-demand spin-up when it matters.

---

## Open Questions (for future specs)

- **Alarm/notification delivery:** The `Notifier` protocol is designed. Concrete implementations (MCP, webhook, dashboard tab) are a separate spec.
- **On-demand container spin-up:** When a developer logs in and their container is stopped, start it automatically. Requires a Caddy + orchestrator webhook. Future spec.
- **Master orchestrator Hermes:** The admin's Hermes instance that uses `dev-admin` as a tool, handles events, and escalates to the human admin. Separate spec.
- **Fjell as internal hub:** Landing page, docs, admin panel, dashboards. Fjell's modular structure supports this. Separate spec per feature.
