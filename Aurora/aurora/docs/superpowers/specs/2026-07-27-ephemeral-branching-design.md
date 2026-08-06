# Ephemeral Branchable Infrastructure — Design Spec

**Date:** 2026-07-27
**Status:** Approved design, pending implementation plan
**Branch:** `feat/ephemeral-branching`
**Worktree:** `~/Desktop/aurora/.worktrees/ephemeral-branching`

---

## Corrections from implementation (2026-07-28)

Chunk 1 and Chunk 2's research window invalidated several claims below. Each is corrected in place
rather than silently rewritten; where a decision still stands, only its rationale changes. See:

- **D3** and **§4.2** — the "unmodified prod Caddyfile" claim was false. The decision (per-branch
  Tailscale sidecar) stands; the justification is corrected.
- **§4.2** — the `container_name: !reset null` enumeration ("four services") is stale; restated as a
  rule.
- **§6.1 / §6.2** — the measured-state table omitted the 2.7 GB admin Hermes home, and §6.2's
  "sub-second copy" conclusion is corrected.
- **§6.3** — the SQLite DB count ("four") is corrected; the seeder must enumerate rather than
  enumerate-by-hand.
- **§4.1** step 5 — the `reconcile`/agent-provisioning ordering is corrected for Chunk 2's
  compose-services agents.
- **§7.4** — the access-doc URL set gets a caveat about `AGENT_UPSTREAM_MODE`.
- **D9 / §7.2** — the exclusion-manifest decision stands and is strengthened with verified evidence;
  the `also_exclude` closure is reclassified from tidiness to mandatory.
- **New §5.6**, "Operational hazards learned in Chunk 1" — durable lessons stated as rules.
- **§13** gains an open risk (unexplained `hermes-*` container destruction) that must be resolved
  before Chunk 3's concurrency tests can be trusted.

Full evidence trail: `docs/superpowers/plans/2026-07-28-chunk2-project-parameterised.md`.

---

## 1. Problem

Aurora is a single-host Docker Compose stack (Caddy, Forgejo, Forgejo-MCP, Hermes, fjell,
agent-authz, dev-admin, AFFiNE) serving a small team over a Tailscale tailnet. Iterating on it is
currently unsafe: there is one stack, and any change to a container is a change to production.

The goal is to make the whole infrastructure **ephemerally branchable** — while the normal
production stack keeps running, a developer can mint a complete, isolated copy of the stack that
differs by exactly the delta they are working on, exercise it end-to-end, and tear it down
completely. Iteration on infrastructure becomes fearless.

### 1.1 Why the repo cannot be branched today

Verified on the host, not assumed:

- `compose.yml` declares 7 services. 12 containers carry the `aurora` project label. Odysseus,
  chromadb, searxng, ntfy and arcadedb run but are declared nowhere — the
  `include: ./odysseus/docker-compose.yml` at the bottom of `compose.yml` is commented out. A
  `docker compose up -d --remove-orphans` today would delete five running containers.
- The three developer agents (`hermes-testuser`, `hermes-newuser`, `hermes-cumshit42069`) carry no
  compose project label at all. They are created imperatively by `docker run` in
  `dev_administration/docker_utils.py:38`.
- `dev-administration/` is listed in `.gitignore` but is a **build context** in `compose.yml`.
  Running `docker compose config` inside a fresh worktree fails: the directory does not exist there.
  A branch-as-worktree is therefore currently impossible, not merely awkward.
- AFFiNE is a separate compose project rooted at `/opt/data/workspace/tai/affine/compose.yml` — a
  path inside the Hermes container — while being a hard dependency of the production Caddyfile
  (`/affine/*`, `/admin/*`, `/graphql`, `/api/auth/*`).

**A branch of a repo that does not describe the running system tests a fiction.** Making the repo
describe reality is a prerequisite, not a nicety, and it accounts for most of the work below.

---

## 2. Goals and non-goals

### Goals

1. One command (CLI or agent tool) mints a complete, isolated stack from a git worktree.
2. The branch stack is seeded from production state so login and identity work with no new setup.
3. Production cannot be corrupted, reconfigured, or taken down by anything a branch does.
4. Committing from the branch worktree goes to **production** Forgejo; hitting the branch's own
   Forgejo by accident must be very difficult.
5. Branch containers are trivially distinguishable from production containers, and their
   observation point is discoverable.
6. Branch containers are reachable from the developer's original Hermes agent, so context is not
   lost by moving between environments.
7. Teardown of one branch or all branches is a single command and reclaims all disk.
8. Agent-agnostic control surface (MCP), plus a plain CLI, with no always-on extra container.
9. A change validated in a branch, once merged and rebuilt, produces the same behaviour in prod.

### Non-goals (explicitly deferred)

- **Hot reload.** Nothing in the stack has it today. It is a separate feature, to be designed later.
  In particular the commented-out cargo layer-cache block in `fjell/Dockerfile` must be left alone —
  it has caused breakage before.
- **True large-scale CoW.** See §6. Deferred behind a swappable seam, not built now.
- **Kubernetes / multi-node.** The design maps onto namespace-per-PR if the system ever leaves one
  box, but that is not being built.
- **Public ingress.** Everything stays tailnet-only.

---

## 3. Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Aurora becomes a **monorepo**; `dev-administration/` moves in-tree | It is fundamental infrastructure and a build context. A branch is then a single worktree with no per-component ref pinning. |
| D2 | A branch is a **git worktree + a compose project**; no template engine | Compose's project namespacing and env interpolation already express the whole delta. Generated YAML drifts from its source; a second config language is a maintenance cost with no benefit. |
| D3 | Addressing via **per-branch Tailscale sidecar** — branches only, prod unchanged | Branch gets its own tailnet hostname and origin, so cookies/OIDC/redirect URIs cannot collide. **Corrected 2026-07-28: the original claim that a branch runs the "unmodified" prod Caddyfile was false and was never actually true.** Every `reverse_proxy` target in `Caddyfile` was a literal `127.0.0.1:3010` / `:3000` / `:9080`, and a branch's Caddy runs `network_mode: service:tailscale`, sharing the sidecar's network namespace, where none of those addresses exist — a branch Caddy would reach nothing. The decision itself still stands; only the justification changes. What actually makes the test end-to-end is that prod and a branch run the **same parameterised config**: Chunk 2 Task 7 rewrites the upstreams as `{$VAR:127.0.0.1:N}` placeholders (`AFFINE_UPSTREAM`, `FORGEJO_UPSTREAM`, `FJELL_UPSTREAM`, defaulting to prod's current values) plus an `AGENT_UPSTREAM_MODE` of `published` (prod, host-networked, keeps its published agent ports) or `service` (branch, routes by Docker service DNS). Prod keeps its host-networked Caddy, so there is no cutover risk. |
| D4 | Seed **clones identity and data, regenerates machine credentials** | Forgejo users, password hashes and repos carry over so login is frictionless. OAuth client secrets and redirect URIs *must* be regenerated because the old ones point at prod's hostname. Outbound LLM keys carry over so branch agents work — accepted consequence: a branch can spend real API credit. |
| D5 | **One CLI + stdio MCP facade** in the same package | Stdio means no daemon, no port, no always-on container. Both surfaces call identical code so they cannot drift. |
| D6 | Shell access via **access doc + `aurora branch shell`**, not per-branch SSH | Branch containers run on the host the developer already reaches via Tailscale SSH. Zero new infrastructure. |
| D7 | Branches provision **only the requesting developer** by default | ~250-300MB per agent against ~7.7GB free. `--devs all` overrides. `reconcile` still runs, so the provisioning code path is still exercised. |
| D8 | Divergence lives in **one `compose.branch.yml` override** using `!reset` | Verified working on Compose v5.3.1. Prod's `compose.yml` needs no edits *for name/port isolation* — `container_name` and `ports` are reset from the override rather than deleted from the base. Prod's compose is still edited by M6 for the unrelated absolute-bind-mount fix. |
| D9 | Exclusions are driven by a **manifest**, not coded flags | `--no-forgejo` is an alias for `--without forgejo`. Adding a newly excludable container is a YAML block with no code change. **Verified 2026-07-28, Compose v5.3.1, after this was briefly thought broken:** `docker compose config` omits profiled services by default, which made a labelled-but-profiled container read as "undeclared" to Chunk 1's conformance gate — but `COMPOSE_PROFILES="*" docker compose config --services` lists them, so a *declaration* gate simply has to ask that question, and a service's profile does not make it undeclared. Separately, `docker compose down` removes containers by project label regardless of which profiles were active at `up` time, so teardown is unaffected by profile usage. D9's mechanism stands unmodified; only the conformance gate needed the `COMPOSE_PROFILES="*"` fix. |
| D10 | Seeding hides behind a **`SeedStrategy` Protocol** with one implementation | Mirrors the existing `Notifier` Protocol + `get_notifier()` factory in `notifier.py`. ~10 lines; swapping in btrfs snapshots later is one new class. |
| D11 | Cleanup: delete Odysseus/chromadb/searxng/ntfy and the dead commented blocks; **keep** arcadedb and AFFiNE | arcadedb is a candidate future knowledge graph. AFFiNE is the intended company notes/planning platform and must be brought into the monorepo. |
| D12 | Hermes **keeps** its `/var/run/docker.sock` mount; the §5.3 project-label guard is the protection | Resolved 2026-07-27 (see §12). Minting containers requires Docker access, so removing the socket would make G8 unachievable for Hermes regardless of transport. The socket is therefore a permanent trust boundary, not a temporary affordance, and the guard is load-bearing rather than defense-in-depth. dev-admin keeps its socket (functionally required); fjell's is flagged for a separate decision. |

---

## 4. Architecture

```
~/Desktop/aurora/               project aurora   →  superserver.tailc67a98.ts.net
└── .worktrees/
    ├── INDEX.md                    regenerated on every up/down
    └── <name>/                     project br-<name>    →  aurora-<name>.tailc67a98.ts.net
        ├── BRANCH-ACCESS.md
        ├── compose.yml             identical to prod's
        ├── compose.branch.yml      the ONLY config difference
        └── .env                    project name, domain, TS hostname + ephemeral auth key
```

`.worktrees/` is gitignored (committed as `c9908c7`).

### 4.1 `aurora branch up <name>`

1. `git worktree add .worktrees/<name> -b <name>` (or reuse an existing branch via `--from <ref>`).
2. Render `<worktree>/.env` from prod's, overriding `COMPOSE_PROJECT_NAME=br-<name>`,
   `DOMAIN_NAME=aurora-<name>.tailc67a98.ts.net`, `TS_HOSTNAME`, an ephemeral `TS_AUTHKEY`,
   and `COMPOSE_PROFILES=agent-<username>` (see below).
   LLM keys carry through per D4.

   > **`COMPOSE_PROFILES` must be on this list.** Added 2026-07-29, after Task 5 shipped
   > `COMPOSE_PROFILES=agents` into `.env.template`. Because a branch's `.env` is rendered
   > *from production's*, anything not explicitly overridden here is INHERITED — so a branch
   > would silently start every developer's agent, contradicting D7's "only the requesting
   > developer". This is the same inheritance hazard as `COMPOSE_PROJECT_NAME`: the danger of
   > deriving a branch's config from production's is that omission is invisible, and the
   > failure is over-provisioning rather than an error. Chunk 3 must set it explicitly.

3. Seed state (§6), unless `--no-seed`.
4. `docker compose up -d --build` with `-f compose.yml -f compose.branch.yml`.
5. `dev-admin reconcile` inside the branch project: regenerates OAuth apps against the branch
   hostname and writes the branch's `Caddyfile.d`. **Corrected 2026-07-28:** the original wording
   ("provisions the requesting developer's agent") was written before Chunk 2 (M4) turned
   developer agents into `compose.agents.yml` services. `reconcile` itself creates no containers
   once agents are compose-managed — it only computes what should exist and emits a
   `container.missing` event when it doesn't. `aurora branch up` must therefore run
   `docker compose up -d` a **second time**, *after* `reconcile`, so the newly reconciled agent
   service(s) actually start.
6. Write `BRANCH-ACCESS.md`, regenerate `.worktrees/INDEX.md`, return the access content as CLI
   stdout and as the MCP tool result.

### 4.2 `compose.branch.yml`

**Corrected 2026-07-28:** this section originally said a branch's Caddy runs "the unmodified prod
Caddyfile with only `DOMAIN_NAME` differing" — that was false as written (see D3). Every
`reverse_proxy` target in `Caddyfile` was a literal `127.0.0.1:3010` / `:3000` / `:9080`, and a
branch's Caddy runs `network_mode: service:tailscale`, sharing the sidecar's network namespace,
where none of those addresses exist. The Caddyfile itself must therefore differ between prod and a
branch — not in structure, but in the values supplied to it. Chunk 2 Task 7 rewrites the upstreams as
`{$AFFINE_UPSTREAM:127.0.0.1:3010}` / `{$FORGEJO_UPSTREAM:127.0.0.1:3000}` /
`{$FJELL_UPSTREAM:127.0.0.1:9080}`, so the file itself is genuinely identical between prod and a
branch — only the environment differs, via three `*_UPSTREAM` variables and `AGENT_UPSTREAM_MODE`.

The entire difference between prod and a branch:

- Adds the `tailscale` sidecar (`tailscale/tailscale`, `TS_HOSTNAME`, ephemeral `TS_AUTHKEY`,
  `TS_STATE_DIR`, socket shared by volume).
- Flips Caddy from `network_mode: host` to `network_mode: service:tailscale`.
- Sets the branch's `.env`: `DOMAIN_NAME`, the three `*_UPSTREAM` variables (pointed at Docker
  service DNS — e.g. `forgejo:3000` — instead of the `127.0.0.1:*` defaults that only resolve inside
  prod's host-networked Caddy), and `AGENT_UPSTREAM_MODE=service` so agent routes resolve by Docker
  service DNS instead of prod's published ports (§7.4).
- `container_name: !reset null` on every service that declares one. **Corrected 2026-07-28:** this
  was "the four services that declare one" — stale even at time of writing once Chunk 1 merged.
  State it as a rule, not a count, because it will go stale again: *every* service declaring
  `container_name` gets `!reset null`. Currently that is **eight** — the original four
  (`forgejo`, `forgejo-mcp`, `hermes`, `dev-admin`) plus AFFiNE's four, brought in-tree during
  Chunk 1 (`affine_server`, `affine_migration_job`, `affine_redis`, `affine_postgres`) — **plus one
  per developer** once Chunk 2 (M4) turns agents into compose services with their own
  `container_name`.
- `ports: !reset []` on every service — a branch publishes **no** host ports.
- `profiles:` entries implementing exclusions (§7.2).

### 4.3 Naming

Compose project `br-<name>` yields `br-<name>-caddy-1`, `br-<name>-forgejo-1`, etc. `docker ps` is
scannable by prefix; `docker compose -p br-<name> ps` is scoped.

The subtle hazard runs opposite to intuition: **`container_name:` opts a service out of project
namespacing**, so prod and a branch would collide on a Docker-daemon-global name and the second
stack would fail to start. Resetting it is what makes prefixing safe. Inter-container DNS is
unaffected — Compose resolves by *service* name and network alias, which remain `forgejo`, `hermes`,
etc. inside every project.

### 4.4 Teardown

`aurora branch down <name>` / `--all`:

1. `docker compose -p br-<name> down -v --remove-orphans`
2. Remove branch-scoped volumes.
3. `git worktree remove` — refuses on uncommitted changes unless `--force`.
4. The tailnet node deregisters itself, because the auth key is ephemeral.

---

## 5. Isolation and safety model

The requirement is that "a branch cannot touch prod" is structural, not a matter of careful
scripting.

### 5.1 Enforced by Docker

| Boundary | Mechanism | Failure mode if it regressed |
|---|---|---|
| Names | Project namespacing after `container_name: !reset null` | Hard startup failure on duplicate name — never silent sharing |
| Networks | Separate `br-<name>_default` bridge | No cross-project service DNS exists |
| Named volumes | Project-prefixed | `down -v` provably cannot reach `aurora_*` |
| Host ports | Branches publish none; sidecar is sole ingress | Port collision is unrepresentable, not merely avoided |

### 5.2 Enforced by path relativity

`./forgejo`, `./Caddyfile.d`, `./agent-authz/data` are already relative, so a branch's `./forgejo`
*is* its own worktree directory. This is why bind mounts are kept rather than converted to named
volumes: relative bind mounts deliver isolation and cheap seeding simultaneously.

Two absolute mounts break this and must be fixed (M6):

- `~/.hermes:/opt/data` → `./.hermes` (otherwise a branch shares prod's agent state)
- `~/Desktop/aurora:/opt/data/workspace/aurora` → `.:/opt/data/workspace/aurora`
  (otherwise a branch's Hermes sees prod's tree instead of its own worktree)

### 5.3 The docker socket

Per D12, Hermes and `dev-admin` both retain the socket, because both need to create containers. The
socket is consequently the one boundary Docker does not enforce for us, which makes the following
guard **load-bearing rather than defensive**: it is the only thing standing between a branch-context
operation and production.

**Every mutating dev-admin operation asserts that the target container's
`com.docker.compose.project` label equals its own `COMPOSE_PROJECT_NAME`, and refuses otherwise.**

This directly fixes today's hardcoded `CADDY_CONTAINER=aurora-caddy-1`, which would otherwise
cause a branch's `reconcile` to rewrite **production's** Caddy configuration. This is the single
most important safety item in the build and is tested with the socket deliberately re-enabled.

### 5.4 Forgejo cross-wiring

Three independent layers:

1. **Structural** — the worktree inherits `origin` pointing at prod, and the branch Forgejo is a
   different hostname entirely. Committing to the wrong one requires deliberately adding a remote.
2. **Mechanical** — a `pre-push` hook in the worktree rejects any push whose remote URL matches
   `aurora-*.tailc67a98.ts.net`.
3. **Visual** — the branch Forgejo's `APP_NAME` renders as `null-hub [BRANCH: <name>]`.

`--without forgejo` removes the question entirely by pointing the branch at prod's Forgejo.

### 5.5 Resource guard

Bring-up refuses if free RAM would fall below a floor; `--force` overrides. With ~7.7GB free against
~1.5-2GB per branch, the honest ceiling is 2-3 concurrent branches, and that should surface as an
error message rather than an OOM in production.

**Flagged 2026-07-28:** this sizing was computed against §6.1's measured-state table, which omitted
the 2.7 GB admin Hermes home (§6.2). The RAM figures above are about running containers, not seed
data, so they are not directly falsified by that omission — but the seed-time and disk-headroom
assumptions this guard was sized alongside were, and the whole guard should be recomputed against
§6.2's corrected figures before implementation rather than carried forward on the original estimate.

### 5.6 Operational hazards learned in Chunk 1

Durable lessons from building and deploying Chunk 1, stated as rules so they are not re-discovered
per chunk:

- **A branch's service/volume removals are not in force until deployed.** The live project is
  governed by the `com.docker.compose.project.config_files` label on running containers — on this
  host, `/home/supergoodname77/Desktop/aurora/compose.yml` — not by whatever the branch's
  worktree file currently says. A declaration change and a deployed change are different facts
  until a deploy actually runs.
- **Conformance tests that compare names only cannot catch a declaration that points at the wrong
  reality.** A Critical AFFiNE bind-path defect — declared at a path production had never actually
  used — reached final review with a fully green test suite for exactly this reason: nothing
  compared the declared image, bind source or published port against `docker inspect`.
- **A container with no compose labels is invisible to project-label filters** — including
  `docker compose down --remove-orphans`. This was the exact shape of the three `hermes-*` dev
  agents before Chunk 2 made them compose services.
- **`/home` is a symlink to `/var/home`, and Go's `os.Getwd()` (used by the `docker compose`
  binary) trusts a stale `$PWD`.** `docker compose` can therefore report an unresolved path
  (`/home/...`) for the same location Python's `Path.resolve()` resolves to `/var/home/...`. Any
  code or test comparing a compose-reported path against a Python-computed path must
  `Path.resolve()` **both** sides before comparing, and check parentage via `Path.parents`, never a
  string prefix.
- **`dev-admin` has a startup race.** `depends_on: [forgejo]` with no health condition means
  `reconcile` runs the instant Forgejo's *container* starts, before Forgejo is *serving*, and dies
  with `curl` exit 22. Every fresh deploy hits this until a healthcheck gates the dependency — and a
  healthcheck alone is not sufficient, because `dev-admin` reaches Forgejo *through Caddy*, so a
  Caddy recreate window reproduces the identical failure that no Forgejo healthcheck can prevent.

---

## 6. Seeding

### 6.1 Measured state

**Corrected 2026-07-28:** the table below originally omitted the admin Hermes home entirely — it
measured only the three developer agents, not the `dev-admin`-adjacent admin agent, whose volume is
two orders of magnitude larger than a developer's. §6.2's conclusion was drawn from this incomplete
table and is corrected below.

| Data | Size | Engine |
|---|---|---|
| `forgejo/` (repos, LFS, attachments, DB) | 14 MB | SQLite, WAL mode (2.4MB db, 4.1MB uncheckpointed WAL) |
| Hermes volume, per developer | 70 MB | SQLite DBs — see §6.3 for the correct count |
| **Admin Hermes home** | **2.7 GB** | SQLite DBs, including a 46 MB `state.db` with a live `-wal`/`-shm` — see §6.3 |
| AFFiNE Postgres | 13 MB | PostgreSQL 16 |

### 6.2 No CoW subsystem is built

**Corrected 2026-07-28:** the original text here read "Total seedable state is ~100-200MB, which
copies in well under a second," and concluded that the design therefore does not need a CoW
subsystem. That conclusion was drawn from §6.1's table before the 2.7 GB admin Hermes home was
counted, and is wrong at that size: a plain `cp` fallback of ~2.8 GB total is **not** a sub-second
operation on a filesystem without reflink support. The corrected conclusion is narrower than the
original but reaches the same design choice for a different reason:

`cp -a --reflink=auto` on btrfs — copy-on-write where the filesystem supports it (verified working
on `/var/home`) and a plain copy where it does not — remains the right default **precisely because
it degrades gracefully** rather than because the data is small. On this host's btrfs, reflink makes
the 2.7 GB admin home cost approximately nothing to seed (shared extents, not a byte-for-byte copy);
on a filesystem without reflink, the same command still works, just slower. No btrfs subvolume
management, no snapshot lifecycle, no special teardown path is still the right amount of machinery —
but the `SeedStrategy` seam (D10) is load-bearing sooner than originally implied: a future host or a
future data shape without reflink support turns "approximately nothing" into a real multi-second
cost, and the seam is precisely what lets that be swapped out without a redesign. §5.5's RAM/resource
guard sizing was computed alongside the original, incomplete figures and needs recomputing against
the corrected ones.

### 6.3 The real problem is consistency

Reflink copy across many files is **not atomic**. Forgejo currently holds 4.1MB of uncheckpointed
WAL — larger than the database itself. A file-by-file copy of a live WAL-mode SQLite database can
land the `.db` and `-wal` out of step, producing a branch that either fails to open its database or
silently loses recent writes. That surfaces as "my login does not work in the branch", defeating the
frictionless property in G2.

Seeding therefore splits by data type:

- **Live SQLite** (Forgejo's `gitea.db`; each Hermes volume's SQLite DBs) — `VACUUM INTO`, SQLite's
  supported online-snapshot primitive, producing a consistent single file from a running database
  without stopping it. **Corrected 2026-07-28:** this originally said "each Hermes volume's four
  DBs" and named four (`state.db`, `kanban.db`, `projects.db`, `cron/executions.db`). There are at
  least **five** — `verification_evidence.db` was missing from the list, and the admin home's
  `state.db` alone is 46 MB with a live `-wal`/`-shm` pair, which is exactly the
  not-atomic-across-files hazard this section exists to describe. A fixed list is the wrong shape
  for this: **the seeder must enumerate `*.db` in each Hermes volume** rather than snapshot a
  hand-maintained list that will silently miss whatever the next DB happens to be named.
- **Bulk immutable data** (git objects, LFS, attachments, avatars) — `cp -a --reflink=auto`. Git
  objects are write-once, so a live copy is safe.
- **AFFiNE Postgres** — `pg_dump -Fc` from prod, restored into the branch's Postgres on first boot.

### 6.4 Never cloned

- `caddy_data` — the branch obtains its own certificate from its own tailscaled for its own
  hostname. Copying prod's cert store would be both wrong and useless.
- `forgejo/ssh/ssh_host_*` — regenerated. Cloning makes the branch present prod's host key under a
  different hostname, tripping SSH host-key warnings on every developer machine.

### 6.5 Regenerated rather than copied

OAuth applications and redirect URIs, `Caddyfile.d/agents.conf`, `agent-authz/data/owners.json` —
all produced by `reconcile` against the branch hostname.

### 6.6 Safety property

**Seeding only ever reads production.** No prod container is stopped or paused and no prod file is
written; `VACUUM INTO` and `pg_dump` are both read-only against a live instance. This is directly
testable (§10).

### 6.7 Swappable seam

`SeedStrategy` Protocol with `get_seeder(name)`, mirroring `notifier.py`. One implementation today
(`FileCopySeeder`). No registry, no plugin discovery, no config surface beyond a single
`seed_strategy` key.

---

## 7. Control surface

### 7.1 CLI

```
aurora branch up <name> [--from <ref>] [--no-seed] [--without svc[,svc]]
                        [--devs <user|all|none>] [--force]
aurora branch down <name> | --all [--force]
aurora branch ls
aurora branch shell <name> [service]
aurora branch rebuild <name> <service>
aurora branch access <name>
aurora mcp
```

`rebuild` is scoped to the branch project, so rebuilding a branch service cannot restart or disturb
any production container.

**Resolution rules, stated to remove ambiguity:**

- `--devs` defaults to the *requesting developer*, resolved as `$AURORA_DEV` if set, else the
  `developers.yaml` entry whose `forgejo_user` matches `git config user.name` in the worktree. If
  neither resolves, `up` fails with an explicit message rather than guessing.
- `<name>` is sanitised to a DNS label for the tailnet hostname: lowercased, non-alphanumerics
  collapsed to `-`, trimmed to fit within the 63-character label limit including the `aurora-`
  prefix. The sanitised form is recorded in `BRANCH-ACCESS.md` when it differs from the input.
- If a git branch named `<name>` already exists, `up` reuses it; `--from <ref>` creates it from that
  ref instead and fails if the branch already exists.

### 7.2 Exclusion manifest

`branch-services.yaml` describes each service once:

```yaml
services:
  forgejo:
    excludable: true
    also_exclude: [forgejo-mcp]        # forgejo-mcp depends_on forgejo
    on_exclude:
      env:
        FORGEJO_URL: https://superserver.tailc67a98.ts.net/git
  affine:
    excludable: true
    # Service KEYS, not container_name values. The in-tree affine/compose.yml
    # declares affine, affine_migration, redis, postgres — the affine_* names
    # visible in `docker ps` are container_name values and will NOT match here.
    also_exclude: [affine_migration, postgres, redis]
```

`--without <svc>` validates excludability, computes the transitive `also_exclude` closure, applies
`on_exclude.env` rewiring, and emits Compose `profiles` in the branch override so Compose performs
the omission natively. The closure is what prevents an exclusion from leaving a `depends_on`
dangling, which Compose treats as a hard error.

**Strengthened 2026-07-28:** this closure is **mandatory, not tidiness**. Verified on Compose
v5.3.1: a service whose `depends_on` target sits behind a profile that is not active makes the whole
project invalid — `service "app" depends on undefined service "db": invalid compose project`, exit
1. Skipping the closure does not merely leave a dangling reference for later; it fails the entire
`docker compose` invocation immediately. Separately, see D9: `docker compose config` omits profiled
services by default, which is why the conformance gate must run with `COMPOSE_PROFILES="*"` to see
everything the file declares — but this is orthogonal to the closure requirement above, which is
about `depends_on` parse-time validity, not about what a gate can observe.

### 7.3 MCP facade

Same functions over stdio. Tools: `branch_up`, `branch_down`, `branch_list`, `branch_access`.
Registration is documented in `docs/post-implementation-steps.md` so it can be handed to Hermes and
persisted into the profile repo that provisions new developers:

```
hermes mcp add aurora --command docker \
  --args run -i --rm -v /var/run/docker.sock:/var/run/docker.sock aurora-cli:local mcp
```

with an equivalent `.mcp.json` entry for Claude Code.

### 7.4 Access output

`<worktree>/BRANCH-ACCESS.md`, returned verbatim as CLI stdout and MCP tool result. Contains:

- URL set: fjell root, `/git/`, `/agent/<developer>/`, `/affine/`. **Caveat added 2026-07-28:** the
  `/agent/<developer>/` URLs are correct but **dead unless the branch `.env` sets
  `AGENT_UPSTREAM_MODE=service`** (§4.2, D3) — without it, Caddy still tries to reach agents at
  prod's published-port addresses, which do not exist inside the branch's sidecar network
  namespace. The branch `.env` renderer must set this alongside the three `*_UPSTREAM` variables.
- service → container-name table
- paste-ready `docker exec -it <container> bash` lines
- rebuild and teardown commands
- record of what was excluded and what was seeded

`.worktrees/INDEX.md` is regenerated on every up/down as the known location listing live branches.
Because `.worktrees/` sits inside the directory prod Hermes already mounts, the original agent reads
every branch's access doc with no extra wiring.

---

## 8. Prerequisite migrations

| | Migration | Why it blocks branching |
|---|---|---|
| M1 | Absorb `dev-administration/` into the monorepo (`git subtree`, preserve history, archive the standalone Forgejo repo) | It is a build context that does not exist in a worktree. Nothing builds without it. |
| M2 | Reconcile orphans: delete Odysseus + chromadb + searxng + ntfy (containers, volumes, `/chat` Caddy route, `.env` vars, `odysseus/`); delete dead commented blocks and stale dirs; **declare** arcadedb | The repo must describe the running system or a branch tests a fiction. |
| M3 | Bring AFFiNE in-tree as `affine/compose.yml` + `include:` | It is a hard Caddyfile dependency living outside the repo. |
| M4 | Dev agents: `docker run` → generated `compose.agents.yml`, `include:`d | Without it, branch stacks have no agents and `compose down` cannot see them. Largest code change. |
| M5 | De-hardcode project identity (`docker_utils.NETWORK`, `CADDY_CONTAINER`, `BASE_PORT`) | Prod keeps published agent ports (host-networked Caddy needs them); branches use service DNS and publish nothing. |
| M6 | Fix absolute bind mounts (`~/.hermes`, `~/Desktop/aurora`) | Otherwise a branch shares prod's Hermes state and sees prod's tree. Hermes' docker.sock mount is retained per D12. |
| M7 | Branch override + Tailscale sidecar + ephemeral auth key handling | The feature. |
| M8 | CLI + MCP + exclusion manifest + seeder | The feature. |

---

## 9. Sequencing

Three independently landable chunks:

1. **M1-M3 — the repo describes reality.** Touches the running prod stack. Independently valuable
   even if branching were abandoned.
2. **M4-M6 — the stack becomes project-parameterised.** No branch exists yet; prod behaviour is
   unchanged and verifiable.
3. **M7-M8 — the feature.** The smaller half.

---

## 10. Testing strategy

Per the practices doc: tests are written before code, and assert empirical outcomes rather than
status codes.

### 10.1 Unit

Exclusion-closure computation; env rendering; container-name derivation; `VACUUM INTO` snapshot
correctness; project-label guard logic.

### 10.2 Safety invariants

- **Seed does not mutate prod** — checksum prod's tree before and after a seed; assert identical.
- **Teardown cannot reach prod** — run `branch down --all` with prod running; assert every
  `aurora_*` container ID and volume is untouched.
- **Project-label guard** — a branch-context dev-admin operation aimed at prod's Caddy must refuse.
  Per D12 this is the only control protecting production from a socket-holding container, so it
  requires exhaustive coverage: every mutating entry point, not a representative sample.
- **Concurrent prod + branch** — both healthy, no name collision.

### 10.3 End-to-end

- `GET https://aurora-<name>.tailc67a98.ts.net/git/` returns HTML **containing the seeded org and
  repo names**, proving the SQLite snapshot carried real data.
- Full OIDC login as a seeded user against the branch lands on Hermes dashboard HTML containing that
  user — the executable form of "passwords preserved, no new setup".
- **Cross-wire** — `git push` from the worktree lands in prod Forgejo (verified via prod's API); a
  push aimed at the branch Forgejo is rejected by the pre-push hook.
- **Prod availability** — poll prod's URL throughout a full branch up/down cycle; assert zero
  non-200 responses.
- **Reachability** — from inside prod Hermes, `curl` the branch URL and receive the branch's HTML.
- **Merge-back** — change fjell in the branch; branch serves the change; merge to master; rebuild
  prod; prod serves the same change.

### 10.4 Required documents

Spec (this file), Plan, Implementation (updated every iteration), Issues, Testing, plus
`post-implementation-steps.md`.

---

## 11. Verified facts

Everything load-bearing below was checked on the host or against current upstream documentation
rather than assumed, per practices §2.1.

| Claim | Evidence |
|---|---|
| btrfs reflink works on `/var/home` | `cp --reflink=always` → `REFLINK_OK`; `findmnt` reports btrfs |
| Compose `!reset` removes `container_name` and `ports` | `docker compose -f a -f b config` on v5.3.1 → both absent, exit 0 |
| Caddy fetches `.ts.net` certs from local tailscaled at handshake time | [Caddy Automatic HTTPS docs](https://caddyserver.com/docs/automatic-https); [Tailscale Caddy certificates](https://tailscale.com/docs/integrations/web-servers/caddy/caddy-certificates). Requires tailnet HTTPS enabled (prod proves it is) and Caddy as root or `TS_PERMIT_CERT_UID` |
| Tailscale container supports ephemeral nodes, `TS_HOSTNAME`, `TS_STATE_DIR`, `TS_AUTHKEY` | [Tailscale Docker parameters](https://tailscale.com/docs/features/containers/docker/docker-params) — "an ephemeral node is automatically removed from your tailnet shortly after it disconnects" |
| Hermes consumes both stdio and HTTP MCP servers | `hermes mcp add --help` shows `--command` and `--url`; one HTTP server currently registered |
| Prod Hermes resolves MagicDNS and reaches tailnet hosts | `getent hosts superserver.tailc67a98.ts.net` → `100.86.36.78`; `curl` → HTTP 200; container inherits `tailc67a98.ts.net` search domain |
| Fresh worktree cannot build the stack | `docker compose config` in the worktree; `dev-administration/` absent |
| Host access is via Tailscale SSH, not authorized_keys | `RunSSH: true`; `~/.ssh/authorized_keys` is a root-owned directory |
| Host budget | 16 CPU, 15.5GiB RAM (~7.7GiB free), 143GB free on `/var/home` |

---

## 12. RESOLVED — D12 vs G8

**Decision (2026-07-27): option 1. Hermes keeps the socket.** D12 above is updated accordingly, M6
no longer touches Hermes' socket mount, and the §5.3 project-label guard is promoted from
defense-in-depth to a load-bearing safety control with mandatory test coverage.

The conflict, recorded for future readers:

**D12** removes Hermes' `/var/run/docker.sock` mount. **G8** requires the branch control surface to
be usable from Hermes. But minting and destroying containers *requires* Docker access, and this is
independent of MCP-vs-CLI: the stdio MCP server is spawned by the agent as
`docker run -i --rm ... aurora-cli:local mcp`, which Hermes cannot do without the socket. No
transport choice works around this — an agent that cannot reach Docker cannot create a stack.

Three ways forward:

1. **Hermes keeps the socket; the §5.3 project-label guard is the protection.** G8 is satisfied in
   full. This matches the stated intent behind asking for the guard as "an extra layer" in case the
   socket gets re-enabled. The socket is then a permanent trust boundary rather than a temporary
   affordance.
2. **Hermes' socket stays removed; only host-shell agents (Claude Code over Tailscale SSH) can mint
   branches.** D12 is satisfied in full, G8 is narrowed — Hermes can still *read* every branch's
   `BRANCH-ACCESS.md` and reach branch URLs over the tailnet, but cannot create or tear down.
3. **A filtered docker-socket proxy container** gives Hermes create/destroy rights scoped to `br-*`
   only. Strongest isolation, but it is exactly the extra always-on container ruled out as slop.

Option 1 was chosen: the guard was specifically requested to cover this case, and option 3 was
already rejected on other grounds.

---

## 13. Known issues carried into implementation

1. **Forgejo admin token exposure.** The token is embedded in `.git/config`'s origin URL and written
   in cleartext in `admin-asks.md`, which is tracked in git. Should be rotated and moved to a
   credential helper. Not caused by this work, but this work touches both files.
2. **SSH-to-agent is broken.** `~/.ssh/authorized_keys` is a root-owned directory, so the
   forced-command scheme in `ssh_utils.py` cannot work. The README's documented
   `ssh <user>@host -p 222` also does not do what it claims — port 222 is Forgejo's git SSH, not a
   shell. Out of scope here (D6 routes around it) but should be either fixed or removed from docs.
3. **fjell's docker.sock mount** is retained pending a separate decision; it exists for the
   not-yet-built sandbox launcher.
4. **arcadedb is currently exited (137).** It is being declared in compose per D11, but why it was
   killed is unknown and should be established before relying on it.
5. **`developers.yaml` contains a joke account** (`cumshit42069`) with a real running container and
   volume. Harmless, but it will be cloned into branches under D7 only if `--devs all` is used.
6. **Open risk, added 2026-07-28: unexplained agent container destruction.** During Chunk 2's
   research window, `docker events` recorded three `destroy` events that removed the
   `hermes-testuser`, `hermes-newuser` and `hermes-cumshit42069` agent containers. It was not
   Compose — they carried no project label at the time, so `--remove-orphans` could not have been
   the cause. Their volumes survived, and `reconcile` rebuilt the containers automatically. The
   cause is unknown. This matters beyond curiosity: Chunk 3's concurrency tests (§10.2, "concurrent
   prod + branch") assume a quiescent host between the compose actions under test. That assumption
   should not be trusted until this is explained — an unattributed destroy event during a
   concurrency test would be indistinguishable from a real isolation defect.
