# tai — Self-hosted personal platform

> "tai" = the umbrella. "fjell" = the Rust app (Norwegian for "mountain" — the one piece you build yourself, everything else is drop-in services around it).

## What tai is

A single-server platform for one person (you) that does three things:

1. **Portfolio launcher** — a website of clickable project cards. Click one, a sandbox container spins up running that project, you get redirected to it. Like a portfolio site, but every project is *live and interactive* instead of a screenshot.
2. **Personal NAS** — store photos, documents, code, anything. Backed by drop-in services (Forgejo for git, Immich for photos, a Samba volume for raw files) plus a custom file browser you build in Rust.
3. **Self-hosted agent** — an AI assistant ("Jarvis / secretary") that can see your NAS data as a knowledge graph, answer questions about your life and projects, and *call your own hosted projects as tools* — acting as a master orchestrator over everything you build.

## The stack (why each piece, ponytail style)

| Layer | Choice | Why this, not the heavier option |
|---|---|---|
| Orchestration | Docker + Compose | One `compose.yml` at the platform root. Not k8s — you'd spend more time on k8s than on the actual product. Compose is one file, one command, one server. |
| Edge / TLS | Caddy + Tailscale | Home server behind NAT — no public ports. Caddy serves on the tailnet; Caddy's built-in Tailscale integration auto-fetches and auto-renews certs via the Tailscale socket (DNS-01, no inbound ports). ~20-line Caddyfile, zero cert management. Survives a 3am pager. Migration to public: add Cloudflare Tunnel later (no architecture change). |
| App (bespoke) | Rust + axum, **monolith** | One binary, modules for launcher / files / MCP. You like Rust. No microservices — two people, one box. Split later only if a module truly demands it. |
| DB | Postgres + pgvector | Relational state for your app + vector search for NAS semantic queries. One container. Skips Supabase (5 services for one guy: GoTrue/PostgREST/Realtime/Storage/Studio). Query layer: `sqlx`, compile-time checked SQL. |
| Graph | FalkorDB | Redis-backed graph DB, one container, lighter than Neo4j. Holds the graphified view of your NAS. Queried by the agent. |
| Agent | Odysseus (drop-in) | Self-hosted AI workspace: chat UI, MCP servers, model switching, integrations (Discord/Slack/etc.), containers. Replaces two whole phases of custom work. **Decoupled** — your Rust app never imports it, only reaches it over HTTP. Swap it out any time. |
| Graph extractor | graphify (CLI, batch) | Runs on cron, walks a NAS volume, produces a knowledge graph, pushes to FalkorDB. Has a `--update` / watch mode we can flip on later for near-live. Seam designed in from day one (see below). |
| Frontend (Rust side) | askama + HTMX + Tailwind + DaisyUI | Server-rendered HTML, modern look, no JS build pipeline. DaisyUI gives modern components (cards, modals, drawers, chat bubbles) as CSS classes — AI cooks snippets easily because it's just classes on plain HTML, no JSX to hallucinate. |
| Frontend (agent side) | Odysseus's own UI | Inherited, not rebuilt. Reached at `/chat` via Caddy. |
| Drop-in NAS | Forgejo (git), Immich (photos), Samba (raw files) | Containers in compose, behind Caddy auth. No custom code for these. |
| Auth | bcrypt password in Postgres, session cookie. Caddy basic-auth until the real login exists. | No OIDC/OAuth until you have a second user (you won't). |

## The chat bubble pattern

Every Rust-served page inherits a small JS snippet (`chat-bubble.js`, ~30 lines): floating button bottom-right, opens a panel, posts to the odysseus chat endpoint, streams the reply over SSE. Same model, same tools, same conversation memory, available on every page. This is the *only* custom JS on the Rust side besides htmx itself.

If odysseus doesn't expose a clean embeddable HTTP/SSE endpoint, fallback is an `<iframe src="https://tai.<tailnet>.ts.net/chat/embed">` in the panel — still decoupled, slightly less slick. Decide at Phase 1 bring-up after we see odysseus's actual routes.

## How the three pillars connect

```
                         ┌─────────────────────┐
                         │   Caddy (edge/TLS)  │
                         │   one Caddyfile      │
                         └──────────┬──────────┘
        ┌───────────────┬───────────┼────────────┬──────────────┐
        ▼               ▼           ▼            ▼              ▼
   /             /chat         /git         /photos       /sandbox/<slug>
   │             │             │             │             │
   rust-app   odysseus      forgejo       immich      dynamic container
   (fjell)    (agent)        (git NAS)    (photo NAS)  (spawned by fjell)
   │             │
   │  MCP stdio  │
   └─────────────┘  fjell exposes tools (list_projects, launch_sandbox,
                    list_files, recall) as an MCP server; odysseus consumes
                    them → "agent as master orchestrator" pillar
   │
   ▼
   postgres + pgvector   (fjell state + NAS semantic search)
   falkordb              (graphified NAS, built by graphify cron)
```

## Decoupling contract for odysseus (swap any time, no license taint)

1. **fjell never imports odysseus code** — only reaches it over HTTP at `http://odysseus:7000` (compose service name). Swap = point Caddy + the chat-widget snippet at a new upstream.
2. **Tool dispatch is MCP** (Model Context Protocol) — declared in odysseus's `mcp_servers/` config pointing at fjell's MCP server module. Any agent that speaks MCP (odysseus today, a custom one tomorrow, OpenAI Agents SDK next year) can consume the same tools. The MCP server is the seam; odysseus is one consumer of it.

License: odysseus is AGPL-3.0. AGPL covers odysseus's own source and derivatives. fjell is a *separate process reached over network* — not a derivative work. You keep whatever license you want on fjell. Just don't copy odysseus's source into fjell.

(Standard hedge: this is the engineering read, not formal legal advice. If you ever ship commercially, spend 30 min with a lawyer.)

## graphify batch → live migration path

Build so live triggers slot in without a rewrite:

1. **Now (batch):** `graphify/extract.sh` is a thin wrapper; cron calls it nightly with a `VOLUMES` list from env. Output: graph lands in FalkorDB. The script is the *only* thing that knows "batch vs live" — everything downstream reads FalkorDB.
2. **Seam for live:** `extract.sh` accepts an optional `--watch <dir>` flag that runs `graphify extract ... --update` on inotify events. Downstream contract (FalkorDB schema, MCP query surface) does not change — odysseus keeps querying the same graph.
3. **Migration step (when you want it):** replace the cron line in `compose.yml` with a long-running `graphify-watcher` service using the same script + `--watch`. Zero changes to fjell, MCP server, or odysseus config.

Batched cron now, swap one compose service later. FalkorDB schema is stable across both modes — that's the key invariant.

## Security stance

Caddy handles TLS/HTTPS, HTTP→HTTPS redirect, HSTS, modern protocols, strong cipher suites — automatically, by default. Everything below, Caddy does NOT decide for you. These are standing decisions baked into the plan; enforced incrementally as each phase ships.

### Caddy gives you for free
- Auto-renewing Let's Encrypt certs
- HTTP→HTTPS redirect
- HSTS header
- Modern TLS only (no SSLv3/TLS 1.0/1.1), strong default cipher suites

### You must do yourself (standing decisions)
1. **Auth on every internet-facing service.** Default-deny in the Caddyfile; explicitly allow the public portfolio route. Private routes (`/git`, `/photos`, `/chat`, `/sandbox/<slug>`) behind `basic_auth` until a real login (fjell Phase 2+) replaces it for fjell's own pages.
2. **No published ports except 80/443 on Caddy.** Internal services talk on the compose network. Compose port publishing is opt-in — never publish Postgres/Immich/Forgejo/odysseus ports to the host. The only published ports are Caddy's.
3. **Don't expose container management.** No Docker socket mounted into any web-accessible container. No `:2375` (Docker API) on the public internet. Sandboxes you spawn are fine; control plane is not.
4. **Sandbox isolation is a core root of trust.** Each portfolio project's container is a "visitor can execute code here" boundary. Phase 2 hardening stanza in every `projects/<slug>/compose.yml`: `read_only: true` where possible, `cap_drop: [ALL]`, no `privileged`, non-root user, isolated compose network (only Caddy reaches it), CPU + memory limits.
5. **Public vs private divide.** Portfolio page (the launcher itself) is the *only* world-readable thing. Everything else is behind auth.
6. **Secrets handling.** `.env` gitignored, `chmod 600`, for dev. Production: Docker secrets or an external manager (Infisical / Vault) when it stops being just you. Never log secrets. Never hard-code in compose.
7. **Backups = security.** Ransomware, accidental delete, disk failure all have the same mitigation: nightly off-site backup + tested restore. Phase 1 deliverable, not optional. Untested backup = assumption.
8. **Updates = security.** Images have CVEs; patches ship weekly. Pick a cadence and stick to it: Watchtower (auto-pulls + restarts) for a one-person platform, OR quarterly manual review with notifications.
9. **Logging + intrusion detection.** Caddy access logs to a file. Crowdsec (preferred, has Caddy integration) or fail2ban on the auth paths. Check logs once a month. Bots *will* hammer login endpoints.
10. **Rate limiting** on auth and chat endpoints. Caddy `rate_limit` directive or `caddy-ratelimit` plugin. Cheap, blocks dumb attacks.
11. **CORS.** Default same-origin is fine. The chat widget on fjell pages calling odysseus's API will need explicit CORS allowlist at Phase 1 bring-up — default-deny cross-origin, allow only your domain.

### Things that sound important but aren't (for this scope)
- WAFs — overkill; basic-auth + rate-limit + updates covers realistic threats.
- CAPTCHAs / bot detection — only if launch-on-click is public; we decided launches are auth-gated, so not an issue.
- DDoS protection — only if services are public AND high-traffic; Cloudflare proxy in front handles for free. Bare VPS without Cloudflare: accept light attacks, Caddy holds up fine for low-bandwidth.

### Locked decision — exposure model
**Tailscale-only, home server.** No public DNS A record, no port forwarding. Whole platform lives on the tailnet; only devices with the Tailscale client + auth to your tailnet can reach it.

- Server: home machine behind NAT, running Tailscale client.
- Domain: tailnet hostname (`tai.<tailnet-name>.ts.net`) — auto-issued by Tailscale when HTTPS/MagicDNS enabled in admin.
- TLS: Caddy 2.5+ has built-in Tailscale integration. Caddy sees the `*.ts.net` hostname in the Caddyfile, talks to the Tailscale daemon's local socket (mounted into the container), and auto-fetches + auto-renews the cert. Zero cert commands, zero cron. The compose file mounts `/var/run/tailscale:/var/run/tailscale:ro` into the Caddy service.
- Caddy binds to the Tailscale interface IP, not `0.0.0.0`.

**Migration path to public portfolio** (if/when wanted): add Cloudflare Tunnel as a second Caddy upstream-facing ingress, OR swap Tailscale for direct public DNS + open ports. The Caddyfile's route structure doesn't change — public portfolio route stays above the `basic_auth` block, private routes stay authed. **One file edit, no re-architecture.**

### Per-phase security checklist
- **Phase 0:** TLS via Caddy (auto). No published ports except 80/443.
- **Phase 1:** `basic_auth` on private routes. CORS allowlist for chat widget. Watchtower or update cadence. Backup script + tested restore. Crowdsec or fail2ban.
- **Phase 2:** Sandbox hardening stanza in each `projects/<slug>/compose.yml` (read-only, cap-drop, non-root, isolated net, resource limits). fjell's own login replacing basic-auth on fjell routes.
- **Phase 4:** Indexer runs as non-root, reads only permitted files, does not scan ephemeral sandbox volumes.

## Roadmap (each phase = build + learn)

### Phase 0 — box up (week 1)
One server, Docker, Caddy, wildcard cert, one static "hello" page at your domain.
*Learn: containers, reverse proxy, TLS, DNS.*
→ See `docs/phase-0-1.md` for the hands-on guide.

### Phase 1 — drop-in NAS + agent (weeks 2–3)
Stand up Forgejo + Immich + Samba + odysseus, all behind Caddy basic-auth. No custom code. Get odysseus chatting with one API key.
*Learn: volumes, secrets, multi-service compose, backups, MCP config.*
→ See `docs/phase-0-1.md` for the hands-on guide.

### Phase 2 — portfolio launcher v1 (weeks 4–7)
Rust axum monolith (`fjell`). DB table `projects(slug, title, image_url, repo_url, compose_target)`. UI: card grid (Tailwind+DaisyUI). Click → backend spawns `docker compose -f projects/<slug>/compose.yml up -d`, polls health, redirects to `<slug>.tai.<tailnet>.ts.net`. Caddy routes the subdomain to the container's published port.
*Learn: Rust web, sqlx, process spawning / bollard (Docker API), dynamic proxying.*

### Phase 3 — integrations as MCP (weeks 8–9)
Expose `list_projects`, `launch_sandbox`, `stop_sandbox`, `list_files` from fjell as an MCP server; register in odysseus config. Now "agent as master orchestrator" works *for your own tools*.
*Learn: MCP server implementation, tool dispatch semantics.*

### Phase 4 — graphify NAS (weeks 10–11)
graphify cron → FalkorDB → MCP → odysseus. Start with one volume (docs/repos). Add `recall` style queries to the agent. Add pgvector for NAS semantic search.
*Learn: embeddings, graph modeling in FalkorDB, cron jobs in compose.*

### Phase 5 — channels + orchestrator polish (week 12+)
Discord/Slack/Twilio as odysseus integrations (not your code). Auto-discover `projects/*/compose.yml` and register each as an MCP tool. Model switching via odysseus UI. When batch feels stale → flip `extract.sh` to `--watch` mode.
*Learn: bot adapters, tool auto-discovery, live graph updates.*

~14 weeks of evenings to a working v1 of all three pillars; nothing-to-everything.

## Repo layout (fewest dirs that work — add dirs only when a second file needs them)

```
tai/
├── compose.yml                  # platform root: caddy, postgres, falkordb, odysseus, forgejo, immich, samba, fjell
├── Caddyfile
├── .env.example
├── docs/
│   ├── PLAN.md                  # this file
│   └── phase-0-1.md             # hands-on phase 0+1 guide
├── fjell/                       # the one bespoke binary (you build this)
│   ├── Cargo.toml
│   ├── src/
│   │   ├── main.rs
│   │   ├── launcher.rs          # spawned later
│   │   ├── projects.rs
│   │   ├── files.rs
│   │   └── mcp.rs
│   ├── templates/
│   └── static/
├── projects/                    # one subdir per portfolio project, brought up on click
│   └── <slug>/compose.yml
└── graphify/
    ├── extract.sh               # cron target (batch now, --watch seam for live later)
    ├── config.toml
    └── falkor-init.cql
```