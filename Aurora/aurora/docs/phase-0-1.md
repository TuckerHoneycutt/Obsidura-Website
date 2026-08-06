# Phase 0 + 1 — hands-on setup guide

This guide walks you through standing up the platform skeleton and the first drop-in services. You do every step yourself so you understand each piece. No file dumps from me — this is the "what and why" so you can type the commands and read the output.

---

# Phase 0 — box up (week 1)

**Goal:** a single server reachable at your domain over HTTPS, serving a static "hello" page, with the reverse proxy ready to route to future services.

**What you'll have at the end:** `https://tai.<your-tailnet>.ts.net` shows a hello page. Caddy is running, auto-managing TLS via its Tailscale integration, and is ready to route more subpaths as services come online.

## The components and what they are (common-sense version)

### Docker + Docker Compose
- **Docker** runs things in containers — isolated processes with their own filesystem, network, and dependencies. Think of a container as a lightweight VM: it won't pollute your host with "I installed node 18 for this one project."
- **Compose** is a YAML file that lists the containers you want and how they connect (networks, volumes, ports, env vars). Instead of `docker run caddy ... && docker run postgres ...` with a dozen flags each, you write one `compose.yml` and run `docker compose up -d`.
- **Why here:** every service in tai (Caddy, Postgres, FalkorDB, odysseus, Forgejo, Immich, the sandboxes) is a container. Compose is the one file that expresses "the whole platform."
- **In practice:** `docker compose up -d` starts everything, `docker compose logs -f caddy` tails one service, `docker compose down` stops all, `docker compose pull && docker compose up -d` updates images.

### Caddy (the edge / reverse proxy)
- A reverse proxy sits in front of your services and forwards requests to the right one based on the URL. `tai.<tailnet>.ts.net/` → fjell, `/chat` → odysseus, `/git` → forgejo, etc. The tailnet only ever talks to Caddy; Caddy talks to the internals.
- Caddy (vs nginx/traefik) has built-in integration with Tailscale: when it sees a `*.ts.net` hostname in the Caddyfile, it auto-fetches the cert from Tailscale's local socket, uses it, and renews it before expiry. Zero cert management on your part. (Caddy also supports traditional auto-Let's-Encrypt for public domains, but that's not what we use here — we're behind NAT.)
- **Why here:** one Caddyfile (~20 lines) routes every service, handles HTTPS via Tailscale, and later does the dynamic routing for spawned sandboxes (`<slug>.tai.<tailnet>.ts.net` → the sandbox container's port).
- **In practice:** edit `Caddyfile`, run `docker compose restart caddy`. If a route 502s, the target service is down — `docker compose logs <name>`.

### The hello page (placeholder for fjell)
- For Phase 0, the Rust app (`fjell`) is just a placeholder. You can serve a static `index.html` via Caddy directly (`file_server` directive) OR run the real bare `axum` hello-world in `fjell/`. Either works. The point is to verify the routing + TLS chain end-to-end before layering on real features.
- **In practice:** hit `https://tai.<your-tailnet>.ts.net`, see the page, check the cert is valid in your browser. That proves DNS + Caddy + TLS all work. Everything later assumes this chain is healthy.

## The two decisions you made (already settled, stated for reference)

1. **Home server behind NAT** — no public IP exposure, no port forwarding on the router.
2. **Tailscale-only for now** — whole platform lives on the tailnet. No public DNS A record, no inbound ports. Migration to public portfolio later = add Cloudflare Tunnel (no architecture change).

## Phase 0 — step by step

### 0.1 Prereqs on the server
- A Linux server (Ubuntu/Debian is easiest), SSH access, a non-root sudo user.
- Your home server, on your LAN, powered on.
- A [Tailscale](https://tailscale.com/) account (free for personal use). Install the Tailscale client on the server and on every device you'll access tai from (laptop, phone).
- In Tailscale admin (https://login.tailscale.com/admin): enable **MagicDNS** and **HTTPS Certificates** under DNS settings. These give you `<hostname>.<tailnet-name>.ts.net` hostnames with valid Let's Encrypt certs, no inbound ports required.
- Docker + Docker Compose plugin installed on the server:
  ```
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker $USER  # then log out and back in
  docker --version && docker compose version
  ```
- Tailscale client installed and authed on the server:
  ```
  curl -fsSL https://tailscale.com/install.sh | sh
  sudo tailscale up
  ```
  `tailscale up` does NOT prompt for a hostname — it uses the system hostname (e.g. `cachyos-x8664`). Rename to something clean afterwards:
  ```
  sudo tailscale set --hostname tai
  ```
  Or do it in admin web UI: https://login.tailscale.com/admin/machines → click the server → edit name → `tai`.
  Your tailnet name is shown in Tailscale admin (e.g. `fantastic-goblin.ts.net`). So your full tailnet hostname is `tai.fantastic-goblin.ts.net`.

### 0.2 Make the platform directory
Assume everything lives under one dir (call it `tai/` for the umbrella). You already have `tai/fjell` with a Cargo.toml.
```
tai/
├── compose.yml
├── Caddyfile
├── .env
└── fjell/         # exists already (with Cargo.toml + axum hello-world)
```

### 0.3 `.env` file (secrets, never committed)
Create `tai/.env`:
```
DOMAIN=tai.<your-tailnet>.ts.net
```
Replace `<your-tailnet>` with your actual tailnet name from Tailscale admin. Phase 1 adds more vars here (Postgres password, odysseus admin password, API keys). For Phase 0 just the domain.

### 0.4 `compose.yml`
Write a minimal one — just Caddy + fjell. Caddy binds to the Tailscale interface, not to public 0.0.0.0:80/443 — the home server is behind NAT and we don't forward any ports.
```yaml
services:
  caddy:
    image: caddy:2
    restart: unless-stopped
    network_mode: host          # so Caddy can listen on the Tailscale interface
    cap_add:
      - NET_ADMIN               # permission slack for the Tailscale integration
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - /var/run/tailscale:/var/run/tailscale:ro   # so Caddy can talk to tailscaled for certs
      - caddy_data:/data
      - caddy_config:/config
    environment:
      - DOMAIN=${DOMAIN}

  fjell:
    build: ./fjell              # Dockerfile in fjell/ builds the axum hello-world
    restart: unless-stopped
    # Caddy is in network_mode: host, so it reaches fjell via the host's loopback.
    # 127.0.0.1:8080:8080 = bind the host's loopback :8080, forward to container :8080.
    # Nothing on the LAN or the internet can reach this port.
    ports:
      - "127.0.0.1:8080:8080"

volumes:
  caddy_data:
  caddy_config:
```
Notes:
- `network_mode: host` on Caddy so it can listen on the Tailscale interface IP. This is the one case where host networking is justified — it's how Caddy binds to tailnet-only.
- `cap_add: NET_ADMIN` gives Caddy the permissions the Tailscale integration needs. Cheap, prevents a class of "permission denied" weirdness.
- `/var/run/tailscale:/var/run/tailscale:ro` mounts the host's Tailscale socket so Caddy can fetch/renew certs via the built-in integration. Without this mount, the cert step silently fails.
- fjell publishes on `127.0.0.1:8080` (loopback only). Caddy reaches it at `127.0.0.1:8080` from the host network. Nothing else can.
- No `ports:` on Caddy — only reachable via the Tailscale tunnel.
- No `site:/srv` volume — fjell serves the page, not Caddy.

### 0.5 `Caddyfile`
```
{$DOMAIN} {
    reverse_proxy 127.0.0.1:8080
}
```
That's the whole edge for Phase 0. Caddy sees the `*.ts.net` hostname, fetches the cert from Tailscale's socket (the volume mount in 0.4), uses it, renews it automatically. No manual cert commands, no cron, no cert files to manage. Later phases add more `reverse_proxy` lines and the dynamic sandbox routing.

### 0.6 fjell — the Dockerfile

You have the axum hello-world in `fjell/src/main.rs` already. It needs to:
- Listen on `0.0.0.0:8080` (so Docker's port publish can reach it; loopback-only `127.0.0.1` doesn't work cleanly with bridge networking).
- Be containerizable (build + run inside a Docker image).

**Multi-stage Dockerfile** in `fjell/Dockerfile` — one image compiles Rust, copies the binary into a minimal runtime image:

```dockerfile
# Stage 1: build
FROM rust:1.83 AS builder
WORKDIR /app
COPY Cargo.toml Cargo.lock ./
RUN mkdir src && echo "fn main(){}" > src/main.rs && cargo build --release && rm -rf src
COPY src ./src
RUN cargo build --release

# Stage 2: runtime
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /app/target/release/fjell /app/fjell
EXPOSE 8080
CMD ["/app/fjell"]
```

**What this does (line by line):**
- `FROM rust:1.83 AS builder` — start from the official Rust image (compiles Rust), tag this stage `builder` so we can copy from it later.
- `WORKDIR /app` — work inside `/app` in the image.
- `COPY Cargo.toml Cargo.lock ./` — copy dependency manifest first. **This ordering matters**: by copying just the manifest, building it (which downloads all deps), then copying the source, Docker caches the dependency download. If you change `src/main.rs`, Docker reuses the cached deps and only recompiles your code. If you change `Cargo.toml`, Docker re-downloads everything.
- `RUN mkdir src && echo "fn main(){}" > src/main.rs && cargo build --release && rm -rf src` — the "trick" for caching deps. We give Cargo a placeholder `main.rs` so it can resolve and download all dependencies without your actual code. Then we delete `src/`.
- `COPY src ./src` — copy the real source.
- `RUN cargo build --release` — compile the real binary.
- `FROM debian:bookworm-slim AS runtime` (second `FROM`) — start a fresh, minimal image for runtime. No Rust toolchain, no Cargo, no build deps. Just enough to run the binary.
- `RUN apt-get install ca-certificates` — needed for HTTPS calls (e.g. if fjell ever talks to odysseus over HTTPS, or fetches a cert, etc.). Tiny.
- `COPY --from=builder /app/target/release/fjell /app/fjell` — copy the compiled binary from the builder stage. Image is now ~30-50MB instead of ~2GB (the rust:1.83 image).
- `EXPOSE 8080` — documents that the container listens on 8080. (Doesn't actually publish the port — that's compose's job.)
- `CMD ["/app/fjell"]` — what to run when the container starts.

**`fjell/Cargo.toml` sanity checks** — make sure you have the basics:
- `[package]` block with `name = "fjell"`, `version = "0.1.0"`, `edition = "2021"`.
- `[[bin]]` block with `name = "fjell"`, `path = "src/main.rs"`.
- Under `[dependencies]`: `axum`, `tokio` (with the `macros` and `rt-multi-thread` features).
- Run `cargo build` locally once to generate `Cargo.lock` (needed by the Dockerfile `COPY` line). Commit `Cargo.lock`.

**Why this pattern:** keeps build images small, caches deps aggressively so rebuilds are fast (changing a single `.rs` file = seconds, not minutes), and the runtime image has no Rust toolchain (smaller attack surface).

**Build and run it:**
```
docker compose build fjell         # builds the image
docker compose up -d               # starts Caddy + fjell
```
Watch the build output the first time (~3-5 min while it downloads deps). Subsequent builds with no `Cargo.toml` changes = seconds.

### 0.7 Verify the chain
From a device on the tailnet (laptop, phone — not the server itself, to prove tailnet routing works):
```
docker compose ps                                  # on server: both services "Up"
docker compose logs caddy                          # on server: no errors, log line about obtaining the cert
docker compose logs fjell                          # on server: axum started, listening on :8080
curl -I https://tai.<your-tailnet>.ts.net          # from your laptop: 200, valid cert
```
In the browser, hit `https://tai.<your-tailnet>.ts.net` — you should see the lock icon (valid cert) and your axum hello page.

**If the cert step fails:**
- `tailscale status` on both server and client shows them connected?
- HTTPS Certificates enabled in Tailscale admin DNS settings?
- `/var/run/tailscale/` exists on the host? (Tailscale client running, socket present.)
- Caddy logs say "permission denied" on the socket → check the volume mount, or add `user: "0:0"` to the Caddy service to run as root.
- Caddy logs say "no certificate available" → Tailscale integration couldn't fetch. Verify the hostname in `.env` matches the tailnet hostname exactly (including the tailnet name).

**If fjell isn't reachable:**
- `docker compose logs fjell` — does it start? axum listening on `0.0.0.0:8080`?
- From the server: `curl http://127.0.0.1:8080` — should return the hello page. If this works, the issue is Caddy→fjell. If it doesn't, the issue is inside the container.
- `docker compose exec fjell ls /app/fjell` — is the binary there?

**Phase 0 done.** You now understand: containers, volumes, multi-stage Dockerfiles, compose networking, reverse proxy, tailnet routing, Caddy's Tailscale integration for zero-touch TLS. Everything later assumes this works.

---

# Phase 1 — drop-in NAS + agent (weeks 2–3)

**Goal:** standing up the external services — git hosting, photo storage, raw files, and the AI agent workspace — all behind Caddy auth, with no custom code. You learn multi-service compose, secrets, volumes, and MCP configuration.

**What you'll have at the end:**
- `https://tai.<your-tailnet>.ts.net/git` — Forgejo, your private git server, with basic-auth in front.
- `https://tai.<your-tailnet>.ts.net/photos` — Immich, your private Google-Photos replacement.
- Samba volume accessible on your tailnet (or LAN) for raw files (not web-exposed).
- `https://tai.<your-tailnet>.ts.net/chat` — Odysseus, your agent workspace. Chat with one model via an API key.

## The components and what they are

### Forgejo (git NAS)
- A self-hosted git server — like a private GitHub. Fork of Gitea, community-owned. Lightweight (one Go binary, one container), runs its own SQLite or talks to your Postgres.
- **Why here:** you wanted "forgio to handle my git server" — Forgejo is that. Stores your repos, serves web UI for browsing them, can mirror your public GitHub repos if you want a local copy.
- **In practice:** push repos to `https://tai.<your-tailnet>.ts.net/git/you/repo.git` (HTTPS over tailnet). The web UI is at `/git`. Create your first repo, push something, see it in the browser.

### Immich (photo NAS)
- A self-hosted photo + video manager — DAM (digital asset management) plus machine-learning-powered search (faces, objects, places). Drop-in replacement for Google Photos / iCloud Photos.
- **Why here:** you wanted to store your photos. Immich is the mature, batteries-included answer: mobile app auto-uploads, web UI, facial recognition, timeline view.
- **In practice:** install the Immich mobile app, point it at `https://tai.<your-tailnet>.ts.net/photos`, log in, turn on auto-upload. Your phone's camera roll now backs up to your server. The web UI shows your library with search.

### Samba volume (raw files)
- Samba is the SMB/CIFS file-sharing protocol — the thing that lets Windows/macOS/Linux mount a network share like a local folder. No web UI; it's filesystem-level.
- **Why here:** for documents, code dumps, private files, anything that doesn't fit Immich (photos) or Forgejo (git). You mount the share at home and drag files in.
- **In practice:** on your laptop, connect to `smb://tai.<your-tailnet>.ts.net/<share-name>` (works from any tailnet device, not just LAN), drop files in. Those files live on a docker volume that fjell's file browser (Phase 3+) will read, and that graphify (Phase 4) will index.

### Odysseus (the agent workspace)
- A self-hosted AI workspace: chat UI, model switching, MCP server config, integrations folder, agents, notes, calendar, research mode. Python (AGPL-3.0), runs in a container, web UI on port 7000.
- **Why here:** this is the entire "host my own agents + contact them from anywhere" pillar, delivered. You don't build an agent — you configure one. It already speaks MCP, which means when you expose fjell's tools as an MCP server (Phase 3), odysseus just consumes them. Swap it out any time via the decoupling contract (over-HTTP-only, never import its code).
- **In practice:** bring it up, get the admin password from logs, log in at `https://tai.<your-tailnet>.ts.net/chat`, add your Anthropic/OpenAI API key in the config, start a chat. Ask it something. That's your agent. Later phases make it actually *do* things by pointing it at your MCP server.

### Postgres + pgvector (the relational + semantic DB)
- Postgres is the relational database. pgvector is an extension that adds vector columns (arrays of floats) and similarity search to it. We use one Postgres for fjell's state (the `projects` table later) and for NAS semantic search (vector embeddings of files/documents).
- **Why here:** one DB does two jobs. Skips standing up Supabase (which is itself a stack of services) or a separate vector DB. `sqlx` in Rust gives compile-time SQL checking.
- **In practice:** for Phase 1 you don't touch Postgres from fjell yet — you just bring the container up so the other services (Forgejo can use it, odysseus can, pgvector extension is ready for Phase 4). You'll write your first `sqlx` migrations in Phase 2 when the launcher needs a `projects` table.

### FalkorDB (the graph DB)
- A Redis-backed graph database. Stores nodes and edges (like Neo4j) but runs as a Redis module — one container, lighter on resources. Uses Cypher as a query language (same as Neo4j), so queries are portable if you ever switch.
- **Why here:** this is where graphify dumps the knowledge graph of your NAS. The agent queries it via the MCP server in Phase 4. Bringing it up in Phase 1 means the infrastructure is ready; Phase 4 fills it.
- **In practice:** for Phase 1 it just runs empty. `docker exec -it <falkordb> redis-cli` and run `GRAPH.QUERY` to confirm it responds. That's enough — you'll load real data in Phase 4.

### Auth (Caddy basic-auth, for now)
- HTTP basic-auth: browser prompts for user+pass before letting you through a route. Caddy has a `basic_auth` directive. One user, one password, encoded in the Caddyfile.
- **Why here:** drop-in services like Forgejo and Immich *have their own* logins, but you don't want them directly internet-reachable. Putting basic-auth in front at the edge means: to reach Forgejo, you first authenticate to Caddy. Belt-and-braces. When fjell grows a real login (later phase), the basic-auth layer comes off the fjell route only.
- **In practice:** add a `basic_auth` block to the `/git`, `/photos`, `/chat` routes in the Caddyfile. Generate the bcrypt hash with `caddy hash-password`. Now hitting those URLs prompts for credentials.

## Phase 1 — step by step

### 1.1 Add the services to `compose.yml`
Append to the existing file (keep Caddy + fjell from Phase 0):
- `postgres`: image `ankane/pgvector` (Postgres with pgvector preinstalled), env vars for user/password/db, a named volume for data, no published port (only Caddy + fjell + odysseus talk to it on the compose network).
- `falkordb`: image `falkordb/falkordb`, a named volume, no published port.
- `forgejo`: image `codeberg.org/forgejo/forgejo`, env pointing at your Postgres, a named volume for the repos, published port `2222:22` for SSH git (optional — start with HTTPS only if simpler).
- `immich`: the Immich compose stack bundles several containers (server, machine-learning, web, redis, postgres). Check Immich's current docs for the exact service list — they ship a reference `docker-compose.yml` you copy from. Often easiest to bring Immich up in its own compose file first, then fold into the main one once it works.
- `samba`: image `dperson/samba` (or `crazymax/samba`), a volume mount of your file share, env vars for the share name + a user/pass, published ports `139:139 445:445` (SMB protocol). Only expose this on your LAN, not the internet — bind to your LAN interface IP or use Docker's `--network host` (or just don't publish and reach it over Tailscale).
- `odysseus`: build from the odysseus repo (git clone, `docker compose -f docker-compose.yml up` from inside it) — OR fold its services into your main compose if you want one file. The repo has its own `docker-compose.yml` to start from; read it to understand its env vars (admin password, model config).

### 1.2 Expand the Caddyfile
Add routes for each new service, plus basic-auth on the ones you don't want naked on the tailnet:
```
{$DOMAIN} {
    # fjell — no basic-auth, it's your public portfolio (tailnet-only for now)
    handle / {
        reverse_proxy 127.0.0.1:8080
    }

    # everything below this is authed
    basic_auth {
        you <bcrypt-hash-from-caddy-hash-password>
    }

    handle /git/*        { reverse_proxy forgejo:3000 }
    handle /photos/*     { reverse_proxy immich-server:3001 }  # check the actual port
    handle /chat/*       { reverse_proxy odysseus:7000 }
}
```
Notes:
- fjell is reached via `127.0.0.1:8080` because Caddy is in `network_mode: host` and fjell publishes on the host's loopback. (Inside the fjell container it's still `0.0.0.0:8080`; the `127.0.0.1:8080:8080` port publish makes it reachable from the host.)
- The Phase 1 services (forgejo, immich, odysseus) are on the Docker network, so Caddy reaches them at their compose service names. (For Caddy to resolve `forgejo:3000` etc., they need to be on the same default network. Compose does this by default if you put them in the same `compose.yml`.)
- `handle` blocks are mutually exclusive — Caddy picks one per request. Put the public stuff (`/`) above the basic-auth so it's reachable without credentials; the private stuff below it. Each drop-in service has its own internal port — read each one's docs and match it.

### 1.3 Add secrets to `.env`
```
DOMAIN=tai.<your-tailnet>.ts.net
POSTGRES_USER=fjell
POSTGRES_PASSWORD=<strong-random>
POSTGRES_DB=fjell
FORGEJO_USER=you
FORGEJO_PASS=<strong-random>
SMB_USER=you
SMB_PASS=<strong-random>
SAMBA_SHARE=tai
ODYSSEUS_ADMIN_PASSWORD=<from-logs-or-set-here>
ANTHROPIC_API_KEY=<your-key>   # or OPENAI_API_KEY, or Ollama host
```
`.env` is gitignored. Never commit it.

### 1.4 Bring it up in order
```
docker compose up -d postgres falkordb    # wait for healthy
docker compose up -d forgejo immich samba # the drop-ins
docker compose up -d odysseus             # the agent
docker compose ps                         # all healthy?
```
If anything fails: `docker compose logs <name>`. The most common Phase 1 issue is a service's env var not matching what the container expects — read the failing service's logs first, they tell you exactly what's missing.

### 1.5 First-pass verification
- `https://tai.<your-tailnet>.ts.net/git` → Forgejo setup page (first run prompts you to create the admin user). Create it. Push a test repo.
- `https://tai.<your-tailnet>.ts.net/photos` → Immich setup page. Create the admin user. Install the mobile app, point it at this URL, turn on auto-upload, take a photo, watch it appear.
- Mount the Samba share from your laptop (`smb://tai` on macOS Finder, or `\\tai` on Windows — uses the Tailscale hostname, works from any tailnet device). Drop a file in. Confirm it's on the volume with `docker compose exec samba ls /share`.
- `docker compose logs odysseus | grep -i password` → grab the first-run admin password. Log in at `https://tai.<your-tailnet>.ts.net/chat`, change it.

### 1.6 Wire odysseus to one model
In odysseus's config (web UI or env, depending on the release — read its setup guide), set your `ANTHROPIC_API_KEY` (or OpenAI key, or point it at a local Ollama instance if you have GPU). Start a chat. Ask: "What can you see right now?" — the honest answer is "nothing yet, I have no tools." That's correct — Phase 3 wires the tools. The Phase 1 win is: **the agent is live, reachable from your phone, talking to a real model.**

### 1.7 Backups (do not skip)
Before putting real data on this box, set up backups. Ponytail-cheapest option:
- A nightly cron on the host that `docker compose exec postgres pg_dump` → writes to a local dir, then `rclone copy` to cheap object storage (Backblaze B2, AWS S3, etc.). Same for the Immich upload volume and the Forgejo repo volume.
- Test a restore once: spin up a fresh Postgres container, load the dump, query it. If you've never tested a restore, you don't have backups, you have assumptions.

**Phase 1 done.** You now have: a portfolio page (stub), private git, private photos, private file share, a live agent endpoint — all behind TLS + auth. You understand multi-service compose, volumes, secrets, and what each drop-in service does. Phase 2 starts the real coding: the portfolio launcher in Rust.

---

## What to read next, by phase

- **Phase 2 (weeks 4–7):** Build `fjell/src/launcher.rs` + `projects.rs` — the Rust axum launcher. Learn sqlx (migrations, the `projects!` table), `bollard` crate for talking to the Docker API instead of shelling out, and askama templates for the card grid. Click a card → `compose up -d` for that project's compose file → poll the container health → redirect to `<slug>.tai.<your-tailnet>.ts.net` (Caddy learns on-demand routing for that subdomain).
- **Phase 3 (weeks 8–9):** `fjell/src/mcp.rs` — expose `list_projects`, `launch_sandbox`, `stop_sandbox`, `list_files` as an MCP server over stdio. Register it in odysseus's config (`mcp_servers/`). Now your agent can actually *do* things on your behalf. Test: ask the agent "launch my raytracer sandbox" — it calls `launch_sandbox`, you see the container come up, it gives you the URL.
- **Phase 4 (weeks 10–11):** `graphify/extract.sh` + FalkorDB + an MCP wrapper exposing `query_graph` / `recall`. Run `graphify extract ./nas-volume --backend ollama --falkordb <dsn>` on cron. Add the `recall` tool to odysseus. Ask "where's the notes file about X?" → it queries the graph, returns a path.
- **Phase 5 (week 12+):** Channels (Discord/Slack/Twilio) as odysdeus integrations, not your code. Auto-discover `projects/*/compose.yml` and register each as an MCP tool so the orchestrator grows itself. When batch feels stale → flip `graphify/extract.sh` to `--watch` mode.

Each phase builds on the previous; none restructures what came before. The Caddyfile grows, the compose grows, fjell grows — but the architecture doesn't churn.