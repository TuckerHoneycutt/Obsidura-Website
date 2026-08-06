# Aurora — operator's guide

Everything needed to run, customise and troubleshoot the stack. One page.

- **Production** — one Compose project on one host, reachable only over the Tailnet.
- **Branches** — a complete second stack (`br-<name>`) beside production, minted from a git worktree, seeded from production's state, torn down without touching it.

---

## 1. Daily operations

| Task | Command |
|---|---|
| Bring the stack up | `docker compose up -d` |
| Do I need to deploy? | `bash ops/rebuild.sh --check` |
| Deploy a merge | `git pull` &rarr; `bash ops/rebuild.sh` |
| Status of all developers | `dev-admin status` |
| Add a developer | edit `developers.yaml` → `dev-admin render-agents` → commit → `dev-admin reconcile` → `docker compose up -d` |
| Remove a developer | edit `developers.yaml` → `dev-admin render-agents` → commit → `dev-admin reconcile` |
| Health check | `dev-admin verify <username>` |
| Run tests | `AURORA_PROJECT=<live project> .venv/bin/python -m pytest` |
| Front door | `https://<domain>/` &rarr; the hub. Signed in to Forgejo, it links you to your own agent; signed out, it offers a sign-in. |

**Merging does not rebuild.** `git pull` updates the checkout and touches no
image; `docker compose restart` reuses the image it already has. Production
will serve a stale binary and answer 200 on every route while doing it — that
is not hypothetical, it is what happened for thirteen hours on 2026-08-01.
`ops/rebuild.sh` is the only thing that makes a merge real. It derives the
buildable services from `docker compose config`, prints before/after image IDs
and creation times, and needs no `AURORA_ALLOW_PROD` because `up` is not a
destructive verb. Scope it with `ops/rebuild.sh <service>`.

**`reconcile` does not start containers.** Since agents became Compose services it creates the account, OAuth app, volume and env file, then reports `container.missing`. `docker compose up -d` starts them.

**`compose.agents.yml` is generated *and* committed.** Compose's `include:` is a hard error on a missing file, so a gitignored fragment breaks `docker compose config` in every fresh clone. Regenerate with `dev-admin render-agents`; a test fails if it drifts from `developers.yaml`.

**`dev-admin` exiting 0 is success.** It is a one-shot `restart: "no"` reconciler.

---

## 2. Developer access to Forgejo

A developer never needs `FORGEJO_ADMIN_TOKEN`. Access is two separate things:
**repositories** (granted by you) and a **token** (minted by them).

| Task | Who | Command |
|---|---|---|
| Grant repository access | admin | `dev-admin access authorize <user>` |
| Mint a token | **the developer** | `dev-admin access mint <user>` |
| See everything a developer has | admin | `dev-admin access ls [<user>]` |
| Take repository access away | admin | `dev-admin access deauthorize <user>` |
| Cut off all access right now | admin | `dev-admin access suspend <user>` |
| Undo that | admin | `dev-admin access restore <user>` |
| Destroy the token | **the developer** | `dev-admin access revoke <user>` |

**Forgejo will not let you mint or delete a developer's token.** `POST` and
`DELETE` on `/users/{u}/tokens` answer `401 auth method not allowed` to an
admin token; they need the developer's own password. That is why two of the
seven commands are theirs, and why `suspend` exists.

**`mint` prints the token once and writes it to no file.** Forgejo stores only
a hash. It **refuses while one is live**, so running it twice cannot leave a
second valid credential that `revoke` will not find. If it is lost: `revoke`,
then `mint` again. That is also how you rotate. There is no `--password` flag:
the password comes from a prompt or `FORGEJO_DEV_PASSWORD` only, so it cannot
reach `ps` or your shell history.

**Nothing yet puts `mint` in a developer's hands.** `mint` and `revoke` need
only `FORGEJO_URL` and the roster — but `scripts/dev-admin.sh` refuses without
`FORGEJO_ADMIN_TOKEN` and mounts the Docker socket, and a developer's container
has neither. Until a wrapper exists they mint in the Forgejo web UI instead:
`access ls` shows that token as `(personal)`, and `revoke` will not touch it.

Scopes are `read:user, write:repository`: enough to clone, push and open a PR,
and nothing else. `--scope` accepts only what is on the allowlist in
`forgejo_access.ALLOWED_SCOPES`; `all`, every `*:admin` scope and `write:user`
(which would let a token mint more tokens) are refused, as is any account that
is a Forgejo site admin or absent from `developers.yaml`.

```bash
git clone https://<user>:<token>@<domain>/git/<owner>/<repo>.git
```

The managed token is named `aurora-dev-<user>` — derived, never chosen, so `ls`
can tell it from tokens the developer made themselves (`personal`) and `revoke`
touches only that one. The scope allowlist is `read:user`, `read:repository`,
`write:repository`, `read:issue`, `write:issue`, `read:organization`.

| Command | Environment it needs |
|---|---|
| `mint`, `revoke` | `FORGEJO_URL`, and `DEVELOPERS_YAML` (default `developers.yaml`). Password from a prompt, or `FORGEJO_DEV_PASSWORD` for a non-interactive run. **No admin token.** |
| `ls`, `authorize`, `deauthorize`, `suspend`, `restore` | the admin's `.env`: `FORGEJO_ADMIN_TOKEN`, `FORGEJO_URL`, `AURORA_PROFILE_URL`, `DOMAIN_NAME` |

### suspend is not revoke

| | stops API + git | survives `restore` | needs the developer |
|---|---|---|---|
| `suspend` | yes | **no** | no |
| `deauthorize` | repo access only | yes | no |
| `revoke` | yes, permanently | yes | **yes** |

`suspend` is the 3am lever. `deauthorize` is the durable admin-side one.
`deauthorize` exits 1 when it removed nothing, so a loop over it cannot report success for a name that was never a collaborator.

Removing someone from `developers.yaml` and running `reconcile` deauthorizes
their repositories for you. It cannot delete their token — Forgejo refuses that
to an admin — so it warns, and you follow up with `access suspend <user>`.

### `authorize` refuses write on an unprotected branch

`--permission write` is refused unless the repo's default branch has a
protection rule, because without one `write` is push-to-main. `access ls` marks
such repos `[main UNPROTECTED]`. Override with `--allow-unprotected` if that is
genuinely what you want; use `-p read` if it is not.

**As of 2026-07-31 no shared repo has branch protection**, so `authorize`
refuses `write` on all of them until you add a rule. See
`docs/implementations/2026-07-31-forgejo-dev-access.md` §D2.

**A brand-new developer must change their password in the Forgejo web UI
first.** `reconcile` creates accounts with `must_change_password`, and Forgejo
refuses basic auth until it is cleared, so `mint` will exit 1.

**Not covered:** SSH keys and git over port 222, and expiry — Forgejo tokens do
not expire, so `access ls` is how you find them.

---

## 3. Branching

```bash
./aurora branch up <name>          # mint a branch stack
./aurora branch ls                 # list live branches
./aurora branch access <name>      # URLs and credentials
./aurora branch shell <name>       # shell into it
./aurora branch down <name>        # destroy it
./aurora branch down --all         # destroy every branch
```

Options: `--devs a,b` (only these developers), `--without forgejo` (exclude a service and its dependents), `--no-seed`, `--from <ref>`, `--build`, `--runtime docker|podman`.

A branch gets its own project, Tailscale node, domain and volumes. It publishes **no host ports** — collision with production is unrepresentable, not merely avoided.

### `--runtime podman` (opt-in)

```bash
./aurora branch up <name> --runtime podman     # or export AURORA_BRANCH_RUNTIME=podman
```

Points the branch's compose at your **rootless** podman socket instead of the
root docker daemon. Same compose files, same overlay, same project name — only
`DOCKER_HOST` changes. **Default stays docker; production is always docker.**

What it buys, structurally rather than by policy:

1. **Separate image store and build cache.** A branch cannot overwrite a tag
   production runs, because the tag is in a different daemon.
2. **Production's socket becomes unreachable.** `dev-admin`, `fjell` and
   `hermes` are each handed `/var/run/docker.sock`. Under docker a container
   with that bind answers `GET /version` from production's daemon; under
   rootless podman it gets EACCES, from SELinux and from the uid map
   independently.
3. **No root-owned worktrees.** Container `root` is your uid, so the daemon
   stops creating root-owned bind sources.

Two things it does on your behalf, both needed and both measured
(`docs/issues/2026-08-01-podman-branch-runtime.md`):

- `chcon -R -t container_file_t <worktree>` before the first `up`. SELinux is
  Enforcing; without it every bind mount is EACCES. Only the branch worktree
  is ever relabelled.
- `podman unshare chown -R 0:0 <worktree>` before `branch down` removes it.
  Postgres runs as uid 999, which maps into your subuid range, and its data
  directory is otherwise unreadable and unremovable by you. **No sudo.**

`branch up` records the runtime in the worktree, so `down`, `rebuild` and
`shell` need no flag. Passing one that contradicts the record is refused.

Caveat: `branch ls` covers one runtime per invocation — pass `--runtime podman`
to list podman branches.
### Letting a developer spawn their own

A developer has no host shell, and the Docker socket is root on this host — mounting it into their agent container grants them root on production. Instead run one broker per developer; the socket stays here and the container gets a protocol. Needs `socat` on the host.

```bash
ops/aurora-spawn-broker <developer> [socket-dir]   # foreground; one per developer
aurora mcp --as-developer <user>                   # that server alone, no socket
./aurora dev-spawn ls                              # every stack, with its lease (`--json` before `dev-spawn`)
./aurora dev-spawn reap --dry-run                  # what would go
./aurora dev-spawn reap [--no-force]               # destroy expired stacks (cron this)
```

Then mount **only** that developer's socket directory into their agent container. The developer's half — registering the bridge, and the four tools — is `docs/setup/user/hermes-setup.md`; the sequence for standing one up is `docs/post-implementation-steps.md` §10.

```bash
-v ~/.aurora-spawn/<developer>:/run/aurora-spawn:z          # :z is required; SELinux is Enforcing
```

They get four tools — `spawn`, `destroy`, `list_mine`, `access` — scoped to `br-<developer>-*`. They choose a **label**; the rest of the name is theirs and is not negotiable, so no input they can send names another developer's stack or production.

| Knob | Default | Meaning |
|---|---|---|
| `AURORA_SPAWN_MAX_PER_DEV` | 1 | stacks one developer may have up |
| `AURORA_SPAWN_MAX_TOTAL` | 3 | stacks on the host, whoever made them |
| `AURORA_SPAWN_TTL_SECONDS` | 14400 | lease length; `reap` destroys what expires. Above the 24 h ceiling it is **refused, not clamped** |
| `AURORA_SPAWN_SOCKET_DIR` | `~/.aurora-spawn` | where the per-developer sockets live; the broker's second argument wins over it |
| `AURORA_MCP_DEVELOPER` | — | whose tool table `aurora mcp` serves. The broker exports it; nothing on the wire can set it |
| `AURORA_SPAWN_SOCKET` | `/run/aurora-spawn/spawn.sock` | read by `bridge.py` **inside** the developer's container |

A stack created by `aurora branch up` carries no lease and is **never** reaped.

**`reap` force-removes worktrees by default** — uncommitted work inside an expired stack is discarded. `--no-force` keeps a dirty worktree instead. Always `--dry-run` first.

**The broker is a foreground process**: no unit file, no restart, no `reap` schedule. It refuses at start-up — before creating any directory named after the argument — for a name not in `developers.yaml`, and for a roster where two names collapse to one namespace (`alice two` and `alice-two`), which would let each destroy the other's stacks. That refusal is global: it stops **every** broker, not just the ambiguous pair.

Quota is counted from the daemon per call and nothing holds a lock, so two simultaneous `spawn`s can both pass it. `AURORA_SPAWN_MAX_TOTAL` is the backstop.

---

## 4. Configuration knobs (`.env`)

`.env` must be strict `KEY=value` — **no spaces around `=`**. Compose tolerates them; `docker run --env-file` rejects the whole file.

| Variable | Purpose | Notes |
|---|---|---|
| `COMPOSE_PROJECT_NAME` | Names the project | Must be declared, never inherited from the directory name |
| `COMPOSE_PROFILES` | `agents` in production | Without it the stack starts with **no developer agents**. A branch sets `agent-<user>` |
| `AFFINE_UPSTREAM` `FORGEJO_UPSTREAM` `FJELL_UPSTREAM` | Where Caddy proxies | Default to `127.0.0.1:*` for production's host-networked Caddy. A branch must set service DNS (`forgejo:3000`) — its Caddy shares the Tailscale netns where localhost reaches nothing |
| `AGENT_UPSTREAM_MODE` | `published` or `service` | Same reason. Wrong value = routes exist and silently 502 |
| `HERMES_TAILNET_IP` | Admin dashboard publish | This host's tailnet address |
| `TS_OAUTH_CLIENT_ID` `TS_OAUTH_CLIENT_SECRET` | Mints a per-branch tailnet key | Preferred. Tagged, ephemeral, single-use, per branch. See §6 |
| `TS_AUTHKEY_BRANCH` | Fallback branch Tailscale auth key | Used when no OAuth client is set. Ephemeral + reusable + pre-approved. See §6 |
| `FORGEJO_ADMIN_TOKEN` | Forgejo admin credential | A branch INHERITS production's, then replaces it with one minted in its own forge and deletes production's rows from its copy of the database (`branch-env.yaml`) |
| `AGENTS_COMPOSE_PATH` | Where `reconcile` reads the agent fragment | Mounted at `/compose.agents.yml`, **outside** `/app` |
| `AURORA_PROJECT` | Test-only | Names the project the runtime tests compare against |

Which variables a branch **must** override is declared in `branch-env.yaml` and enforced by a test — not by convention.

Two knob sets are deliberately **not** in `.env`, because they are per-invocation rather than per-stack: what `dev-admin access` needs (§2) and what the spawn broker reads (§3).

---

## 5. Customising

| To change | Edit | Then |
|---|---|---|
| Who has an agent | `developers.yaml` | `dev-admin render-agents`, commit |
| What a branch may omit | `branch-services.yaml` | Dependents close transitively; nothing in code names a service |
| What a branch must override | `branch-env.yaml` | A test fails if a rendered branch misses an entry |
| What a branch resets | `compose.branch.yml` | Generated — regenerate, don't hand-edit |
| An image version | the `image:` digest, in `compose.yml`, `affine/compose.yml`, or the generator that writes it | `bash ops/rebuild.sh` — see below |
| Routing | `Caddyfile`, `Caddyfile.d/` | `agents.conf` is generated by `reconcile`. **Recreate Caddy, do not reload it** — see below |

**Edited the `Caddyfile`? `caddy reload` may not see it.** It is a *file* bind mount, so a tool that replaces the file (git, most editors) leaves the container bound to the old inode and the reload re-reads the old content — with no error. `docker compose up -d --force-recreate caddy`.

**Upgrading a pinned image.** Every external image is pinned `tag@sha256:…`, so nothing moves on its own — security updates included. That is deliberate: five of these tags floated once, and all five had already drifted away from what production was running. To move one on purpose:

```bash
docker pull <name>:<tag>
docker image inspect <name>:<tag> --format '{{index .RepoDigests 0}}'
# put that digest in the compose file, then:
bash ops/rebuild.sh
```

If the compose file is **generated** (`compose.agents.yml`), edit the generator's constant instead — a conformance test fails if the two disagree. `tests/test_image_pinning.py` fails if any external image loses its digest.

**Adding a service?** If it declares `container_name` or `ports`, the branch overlay must reset both — `container_name` is daemon-global, so a missed reset means a branch that cannot start, or one that steals production's published port. A coverage gate catches this.

---

## 6. Safety mechanisms

**`ops/docker-guard`** (installed at `~/.local/bin/docker`) refuses destructive docker commands not provably scoped to a `br-*` project. Override for real production work:

```bash
AURORA_ALLOW_PROD=1 docker compose down    # etc.
```

It exists because an agent once ran `compose down -v` against the live production project. Prose said not to; prose is not a guard.

**Pre-push hook** rejects pushes aimed at a branch's Forgejo (commits would vanish with the branch). Arm it once:

```bash
git -C <production checkout> config core.hooksPath hooks
```

Must be **relative** — an absolute path written from a worktree repoints *production's* hooks at a directory that vanishes on teardown. Note the hook stops the push, not the handshake: git contacts the remote before hooks run.

**Project guard** — every mutating `dev-admin` operation asserts the target carries its own project label. The docker socket is shared, so Docker does not enforce this for us.

**Spawn facade** — a developer's session is created with one fixed identity and a tool table that has no field for one, so every name it can produce is constructed from that identity. Its guards are tested against a stub daemon (`ops/devspawntest.sh`), never the live one.

---

## 7. Tailscale auth key

**Preferred: let each branch mint its own.** Put an OAuth client with the
`auth_keys` scope in `.env` as `TS_OAUTH_CLIENT_ID` / `TS_OAUTH_CLIENT_SECRET`
and `branch up` mints a key per branch: **tagged `tag:aurora-branch`,
ephemeral, single-use, pre-approved**, valid 30 minutes.

1. Admin console → Settings → OAuth clients → Generate, scope `auth_keys`.
2. Define `tag:aurora-branch` in the ACL's `tagOwners`, and grant it whatever
   access your branches need — **a tagged node does not inherit your implicit
   access**, so getting this wrong makes a branch's URL unreachable for its
   own developer.
3. Put both values in `.env`. Nothing else to do; `TS_AUTHKEY_BRANCH` becomes
   the fallback.

Why per-branch: a shared key is **reusable**, so its nodes are not ephemeral,
so a node lingers ~an hour after teardown. On 2026-07-31 that wedged a branch
— `aurora-hubdemo` was still registered, its replacement came back as
`aurora-hubdemo-1`, and Caddy could not get a certificate for the hostname it
was configured with.

**Fallback: one supplied key.** Create it in the admin console as **ephemeral
+ reusable + pre-approved** and put it in `.env` as `TS_AUTHKEY_BRANCH`. Used
whenever no OAuth client is set, and whenever a mint fails — in which case
`BRANCH-ACCESS.md` says so, because the branch's node is then not ephemeral.

- **Ephemeral** — the node deregisters on teardown. Without it every branch leaves a dead node.
- **Reusable** — one key serves every branch. Single-use mints exactly one and then `branch up` fails.
- **Pre-approved** — otherwise the node joins but carries no traffic, and the branch comes up serving nothing.

`export AURORA_TS_AUTHKEY=tskey-...` overrides both and skips minting.

A `tailscaled` with **no** key starts anyway and reports `Logged out.`; with an **invalid** key it exits 1 and takes the shared netns with it. `branch up` verifies the node reached `Running` rather than trusting the container to be up.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Stack up, no developer agents | `COMPOSE_PROFILES` not set | Set `COMPOSE_PROFILES=agents` |
| `dev-admin` exited 1 at boot | Forgejo not serving yet | Fixed by a healthcheck + retry; check its logs before assuming otherwise |
| Branch serves 502 everywhere | `*_UPSTREAM` / `AGENT_UPSTREAM_MODE` still on production's values | Set service DNS in the branch `.env` |
| Branch URL unreachable, containers healthy | Tailscale node not `Running` | Check the auth key; a bad key fails quietly |
| `docker compose up -d` prompts and hangs | Volume carries a stale `config-hash` | Compose is asking to delete it. Answer no; run with stdin closed |
| Compose refuses a destructive command | `ops/docker-guard` | Intended. Prefix `AURORA_ALLOW_PROD=1` if you mean it |
| A merged change is not being served, all routes 200 | The image predates the merge; nothing rebuilds on merge | `bash ops/rebuild.sh --check`, then `bash ops/rebuild.sh <service>` |
| Two tests fail without `AURORA_PROJECT` | Tests compare against the live project label | Set `AURORA_PROJECT=<live project>` |
| `branch down` leaves the worktree directory | Root-owned bind sources created by the daemon | `sudo rm -rf` it. Known limitation |
| Agents boot on empty homes | Project-prefixed volumes missing | Volumes are `<project>_hermes-<user>-home`; they need both compose adoption labels |
| `aurora-spawn-bridge: cannot reach /run/aurora-spawn/spawn.sock` | No broker, or the container has no mount | Start `ops/aurora-spawn-broker <dev>`; check the `-v` |
| The mount is `Permission denied` inside the container, even as root | SELinux is `Enforcing` | The bind needs `:z` |
| `spawn` answers `-32603 AccessDocError: refusing to render … naming TS_AUTHKEY` | The tool failed, and its message named a `secret: true` variable, so the leak check ate the frame | Usually `TS_AUTHKEY_BRANCH` unset. Known defect: `docs/implementations/2026-07-31-developer-ephemeral-spawn.md` |
| The broker exits before it prints a socket path | The name is not in `developers.yaml`, or two roster names collapse to one namespace | Fix the roster; the check is `devspawn.assert_namespaces_are_unambiguous` |

---

## 9. Facts worth knowing before you debug

- `docker compose config` **validates configurations that cannot start.** Only a real container start catches a bad mount.
- `docker compose down` removes profiled services whether or not you pass `--profile '*'` (measured on v5.3.1). The flag is kept as explicitness, not as load-bearing.
- Compose **adopts** a pre-existing volume carrying its project and volume labels — this is what makes seeding possible, and mislabelling one is how a branch would adopt production's.
- `/tmp` is tmpfs here. Reflink copies silently become real copies; a large seed will eat RAM.
- `/home` is a symlink to `/var/home`. Compare resolved paths, never string prefixes.
- `git worktree repair` needs explicit paths — a bare invocation silently does nothing.
- Seeding **reads** production and never writes to it. SQLite is snapshotted read-only; AFFiNE goes through `pg_dump`. Host keys are never cloned.
