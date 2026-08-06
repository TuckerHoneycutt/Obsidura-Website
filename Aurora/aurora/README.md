# Aurora

A company-as-code development platform that runs entirely on one machine and
is reachable only over a Tailnet.

Forgejo is both the git host and the OIDC identity provider. Each developer
gets their own Hermes agent container, authenticated against that same
Forgejo account. A shared multi-tenant Forgejo MCP server gives every agent
git access under the caller's own token. Caddy puts all of it behind a single
`.ts.net` name and terminates TLS with certificates it fetches from the local
`tailscaled`.

**There is no public ingress.** Nothing here is exposed to the internet; the
only way in is to be on the Tailnet. That is why self-service sign-up is left
open on Forgejo — the network is the perimeter.

> **Naming.** The project was renamed to Aurora during Chunk 2. Documents
> under `docs/` written before 2026-07-28 use the previous name throughout
> and are deliberately left verbatim: they are dated records of what was
> observed, and rewriting them would falsify them. The mapping is in
> `docs/issues/chunk2-spec-deltas.md`.

## Services

Declared across `compose.yml`, the `include:`d `affine/compose.yml`, and the
generated `compose.agents.yml`.

| Service | Container | Purpose |
|---|---|---|
| `caddy` | `aurora-caddy-1` | Reverse proxy and TLS. `network_mode: host`, so it reaches every backend on a published `127.0.0.1` port. Certificates come from the local `tailscaled` at handshake time. |
| `forgejo` | `forgejo` | Git host **and** OIDC identity provider, served at `/git/`. Everything else authenticates against it. |
| `forgejo-mcp` | `forgejo-mcp` | Multi-tenant MCP server over HTTP. Internal only — no Caddy route. Each agent passes its own token, so there is no shared credential. |
| `hermes` | `hermes` | The admin agent. |
| `fjell` | `aurora-fjell-1` | Rust/Axum internal hub. Serves the **hub** — the front door at `/` (302 to `/git/.hub/`) — and `/agent/{username}/setup`. The hub is mounted under `/git/` so the browser sends it Forgejo's session cookie, which is how it routes each developer to their *own* agent. |
| `agent-authz` | `aurora-agent-authz-1` | Per-agent authorisation gate, called by Caddy via `forward_auth`. **It exists because Hermes' OIDC plugin authenticates but does not authorise** — it has no user allowlist, and Forgejo has no per-OAuth2-app user restriction. Without this, any valid Forgejo account could open any developer's agent. |
| `dev-admin` | `dev-admin` | One-shot reconciler, `restart: "no"`. `exit=0` is success; it is *supposed* to stop. |
| `affine` | `affine_server` | AFFiNE, for planning and shared notes. Brought in-tree in Chunk 1. |
| `affine_migration` | `affine_migration_job` | One-shot AFFiNE schema migration. |
| `postgres` | `affine_postgres` | AFFiNE's database. |
| `redis` | `affine_redis` | AFFiNE's cache. |
| `arcadedb` | `aurora-arcadedb-1` | Candidate knowledge-graph store. **Declared but not integrated with anything** — kept so it is code rather than an undeclared survivor. It has OOMed; see `docs/issues/arcadedb-oom.md` before relying on it. |
| `hermes-<username>` | `hermes-<username>` | One agent per developer, generated into `compose.agents.yml` from `developers.yaml`. Gated behind the `agents` profile. |

## Where this is going: ephemeral branching

The goal the parameterisation work serves is this: bring a *branch* of this
repo up as a **complete second stack** on the same host — its own project,
its own Tailscale name, its own volumes — test it end to end, and tear it
down again without ever touching production.

Three properties make that possible, and Chunk 2 established all three:

1. **`COMPOSE_PROJECT_NAME` is declared, not inherited.** It used to be unset,
   so Compose named the project after whatever directory the repo happened to
   be cloned into. A branch now gets `br-<name>` deliberately.
2. **Every bind mount is repo-relative.** A worktree's state is its own. Two
   absolute mounts used to make a branch share production's agent home and see
   production's tree.
3. **No code contains a literal project, network or container name.** Services
   are resolved through Compose labels at runtime, and every mutating operation
   asserts the target belongs to its own project before touching it.

Design: `docs/superpowers/specs/2026-07-27-ephemeral-branching-design.md`.
All three chunks are complete; the command is below.

## Ephemeral branches: `aurora branch`

**Working on this repo, human or agent? Read `AGENTS.md` first.** It is the
short version of this section plus every gotcha that has actually cost time.

```bash
./aurora branch up <name> --devs <user> --from <ref>   # mint a branch stack
./aurora branch ls                                     # what is running
./aurora branch access <name>                          # its URLs and how to reach them
./aurora branch shell <name> <service>                 # a shell in one of its containers
./aurora branch rebuild <name> <service>               # rebuild one service in place
./aurora branch down <name>                            # destroy it
./aurora branch down --all                             # destroy every branch stack
```

`up` creates a git worktree at `.worktrees/<name>`, renders that worktree its
own `.env`, seeds it from production's live state, and brings the whole stack
up under the Compose project `br-<name>` with its own Tailscale node at
`https://aurora-<name>.<your-tailnet>/`. It writes `BRANCH-ACCESS.md` into the
worktree and refreshes `.worktrees/INDEX.md`, so an agent with the repo mounted
can read what exists without being told.

**A branch cannot collide with production, structurally rather than carefully.**
Every project name is forced into the `br-` namespace; the generated
`compose.branch.yml` `!reset`s every `container_name` and every `ports` entry,
so a branch publishes **no** host port at all; and every destructive path
asserts its target is branch-scoped before it issues a command.

Developers do not get the Docker socket. `ops/aurora-spawn-broker <developer>`
holds it on the host and offers one unix socket per developer speaking four
namespaced MCP tools (`spawn`, `destroy`, `list_mine`, `access`); see
USERGUIDE § 3 and
`docs/superpowers/specs/2026-07-31-developer-ephemeral-spawn-design.md`.

Developers do not get `FORGEJO_ADMIN_TOKEN` either. `dev-admin access` mints
scoped, enumerable, revocable per-developer tokens and grants repositories
separately from identity; see USERGUIDE § 2.

### What you need first

* **A tailnet auth key.** With `TS_OAUTH_CLIENT_ID`/`TS_OAUTH_CLIENT_SECRET`
  in the root `.env`, `up` **mints one per branch** — tagged
  `tag:aurora-branch`, ephemeral, single-use — so the node deregisters at
  teardown instead of ~an hour later. Without them it falls back to
  `$AURORA_TS_AUTHKEY` or `TS_AUTHKEY_BRANCH`, which must be **reusable,
  ephemeral, pre-approved**; see `USERGUIDE.md` §6. With neither, `up`
  refuses, deliberately: a `tailscaled` with no key does not fail, it starts,
  stays `Logged out.`, and the branch would report success with a dead URL.
* **`--devs`.** Which developer's agent to run. `up` refuses to guess, because
  guessing `all` starts every developer's agent in every branch and guessing
  `none` produces a branch whose `/agent/` URLs are all dead.
* **`--from <ref>`** while this work is unmerged: without it the worktree
  branches from the checkout's `HEAD`, which may predate the branch tooling.

### Useful flags

| Flag | Effect |
|---|---|
| `--no-seed` | start empty — no users, no repositories, no agent state |
| `--without <service>` | leave a service out, with its dependencies (`branch-services.yaml`) |
| `--no-build` | skip rebuilding images |
| `--force` | override the memory/disk floor; recorded in the access document |

### Known limitations

`down` removes every container, volume and network, but **cannot remove the
worktree directory**: the Docker daemon creates bind-mount sources inside it as
root. Reclaim it with `sudo rm -rf .worktrees/<name>` followed by
`git worktree prune`. See `docs/issues/chunk3-spec-deltas.md`.

`down` also **keeps the git branch ref** it created, so re-running `up --from`
with the same name is refused. `git branch -D <name>` first, or pick a new one.

A checkout with no `.venv` — which production's is, after the rename — cannot
run `./aurora` until you point it at an interpreter:
`AURORA_PYTHON=/usr/bin/python3 ./aurora …`. The launcher supports this
precisely because `branch up` exists to create venv-less worktrees.

## Quick start

```bash
git clone <forgejo>/aurora && cd aurora
cp .env.template .env      # then fill it in
docker compose up -d
```

Two entries in `.env` are load-bearing:

- **`COMPOSE_PROJECT_NAME=aurora`** — the directory basename is no longer
  relied on.
- **`COMPOSE_PROFILES=agents`** — without it the stack comes up with **no
  developer agents at all**. They carry `profiles:` so that a branch can
  activate exactly one of them.

## Managing developers

`developers.yaml` is the source of truth. Adding someone is four steps:

```bash
$EDITOR developers.yaml
dev-admin render-agents        # regenerate compose.agents.yml
git add compose.agents.yml && git commit
dev-admin reconcile            # Forgejo account, OAuth2 app, volume, env file
docker compose up -d           # start the agent
```

**`reconcile` does not start containers.** Since M4 the agents are Compose
services; `reconcile` prepares everything one needs — the account, the OAuth2
app, the project-scoped volume, the OIDC credentials — and then *reports*
whether Compose has actually started it, emitting `container.missing` with the
exact command if not. Starting containers is Compose's job.

`compose.agents.yml` is generated **and committed**. It has to be: Compose's
`include:` is a hard error on a missing file, so a gitignored fragment would
break `docker compose config` in every fresh clone and worktree. A test fails
if it drifts from `developers.yaml`.

## Developer onboarding

1. Open `https://<host>.ts.net/agent/<username>/setup`.
2. Supply an OpenRouter API key and an SSH public key. Nothing else is needed.
3. Open `https://<host>.ts.net/agent/<username>/`.
4. Sign in through Forgejo. The authorisation gate checks the caller owns that
   agent.

Git over SSH is on port **222** (22 belongs to the host).

## Running the tests

There is **no system pytest**:

```bash
python3 -m venv .venv
.venv/bin/pip install pytest pyyaml typer
.venv/bin/python -m pytest
```

`pytest.ini` sets `testpaths = tests dev-administration/tests`. Three kinds of
test:

- **Repo conformance** (`tests/test_repo_conformance.py`) — asserts
  `compose.yml` matches the repo: build contexts are tracked, binds stay inside
  it, no hardcoded identities.
- **Runtime conformance** (`tests/test_runtime_conformance.py`) — asserts the
  *running containers* match what the repo declares. Needs the stack up. Takes
  `AURORA_PROJECT` to name the project it compares against; if that name is
  wrong the query returns nothing and the gate passes **vacuously**, so it
  checks that it found containers at all.
- **Unit tests** (`dev-administration/tests/`) — the orchestrator.

## Repo layout

```
compose.yml              the stack
compose.agents.yml       per-developer agents (GENERATED, and committed)
Caddyfile / Caddyfile.d/ routing; Caddyfile.d holds generated fragments
developers.yaml          source of truth for who exists
dev-administration/      the orchestrator, in-tree (vendored in Chunk 1)
fjell/                   Rust hub: front page + setup form
agent-authz/             per-agent authorisation gate
affine/                  AFFiNE compose fragment
tests/                   conformance tests
docs/                    see below
.agent-env/              per-agent OIDC secrets      (gitignored)
.hermes/                 admin agent state           (gitignored)
.worktrees/              branch checkouts            (gitignored)
```

## Where the documents live

| Path | Contents |
|---|---|
| `docs/superpowers/specs/` | Design specs — what is meant to be built, and why |
| `docs/superpowers/plans/` | Implementation plans, per chunk |
| `docs/implementations/` | What was actually built |
| `docs/testing/` | What each test catches, and what is deliberately untested |
| `docs/issues/` | Investigated problems, with the evidence |
| `docs/setup/user/`, `docs/setup/system/` | Operator guides |
| `docs/post-implementation-steps.md` | Standing list of actions needing a human or root |
| `AGENTS.md` (repo root) | How to use ephemeral branches, and what refuses you |

## Related repositories

| Repo | Purpose |
|---|---|
| `aurora` | This one: the whole stack as code |
| `aurora-agent` | The Hermes agent profile installed into each developer's container |
| `dev-administration` | Upstream of the vendored orchestrator |
| `superpowers` | Shared agent skills |
