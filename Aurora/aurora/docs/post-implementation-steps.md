# Post-Implementation Steps

Actions that need a human, in the order they happen around the deploy.
Everything about *running* the stack — knobs, branch commands, troubleshooting
— is in `USERGUIDE.md`. This file is only the sequence.

Items settled on 2026-07-30 were deleted rather than annotated: the Odysseus
and SearXNG `.env` cleanup, `OPENAI_API_KEY`, the upstream `202fc6f` import,
archiving the standalone `dev-administration` repo, the AFFiNE migration, the
`model-cache` volume, the `Caddyfile` reconciliation, the `handle_path`
question, and the `testuser`/`newuser` accounts. What each one was is in git
history and `docs/issues/chunk1-inherited-secrets.md`.

---

## Every merge — rebuild, or production keeps serving the old binary

**Merging rebuilds nothing.** `git pull` updates the checkout and does not
touch a single image; `docker compose restart` reuses the image it already
has. On 2026-08-01 the internal hub merged at 23:00 and production served the
pre-hub `fjell` for thirteen hours — `/git/.hub/` returned a 20-byte
placeholder, `hub.css` 404'd, and every route answered 200 the whole time.

Run in order. Stop if a check fails.

1. **`cd ~/Desktop/aurora && git pull`**

2. **`bash ops/rebuild.sh --check`**
   Prints STALE / FRESH / NEVER-BUILT per service and exits 1 if any image is
   older than the last commit touching its build context. Builds nothing,
   starts nothing. This is the command that answers "do I need to deploy?".

3. **`bash ops/rebuild.sh`** — or `bash ops/rebuild.sh fjell` to scope it.
   Rebuilds every service declaring `build:` and recreates it with
   `up -d --build`. The service list is derived from `docker compose config`,
   so a fourth buildable service is picked up without editing anything.

   No `AURORA_ALLOW_PROD`. `docker compose up` is not in `ops/docker-guard`'s
   destructive set, on purpose — it is how production is restored. If you find
   yourself needing the override here, you have reached for a destructive verb.

4. **`bash ops/rebuild.sh --check`** again — must now exit 0.

An agent does the same over MCP: the `rebuild` tool, with `check: true` first.

`tests/test_build_conformance.py` fails whenever step 2 would, and names the
services and both timestamps.

---

## Deploy — 60–90 s full outage

The one-time 2026-07-30 `tai-review` → `aurora` rename. Its numbering runs
1–9 through the next section and is separate from the sequence above.

Run in order. Stop if a check fails.

1. **Merge PR #1.** Contains Chunk 2 as an ancestor and supersedes that branch.

2. **`cd ~/Desktop/tai-review && git pull`**
   The checkout must already hold the merge before the script detaches onto it.

3. **`AURORA_ALLOW_PROD=1 bash ops/deploy-rename.sh`**
   Without the prefix it exits 13 before touching anything — `ops/docker-guard`
   blocks production teardown and this is the intended override.

   It does: detach at the ref → `compose --profile '*' down` → `mv
   ~/Desktop/tai-review ~/Desktop/aurora` → `git worktree repair` (explicit
   paths) → set `COMPOSE_PROJECT_NAME=aurora` → `compose up -d`.

   It aborts if `~/Desktop/aurora` exists, if `.env` names the wrong project,
   or if any developer in `developers.yaml` lacks an `aurora_hermes-<user>-home`
   volume.

4. **`docker ps`** — 12 containers. `affine_migration_job` and `dev-admin`
   exited 0 is correct. If `dev-admin` exited 1, read its logs before blaming
   the rename.

5. **`/git/` returns 200.** Caddy re-obtains its certificate on first start;
   allow ~30 s.

Step 3's `up` runs `dev-admin reconcile` automatically, which regenerates
`Caddyfile.d/agents.conf` and `agents.json`. You do not get to schedule this;
the deploy does it.

It does **not** regenerate `agent-authz/data/owners.json` — see "Still open"
item 6. Measured on the 2026-07-30 deploy: `agents.conf` and `agents.json`
were rewritten at 23:05, `owners.json` still carried its 2026-07-27 mtime.

**Rollback:** `cd ~/Desktop/aurora && git checkout main`, revert
`COMPOSE_PROJECT_NAME`, `mv` the directory back, `compose up -d`. The
pre-rename volumes are retained.

---

## After deploying

6. **Arm the pre-push hook** — one line, once, and it must stay relative:

       git -C ~/Desktop/aurora config core.hooksPath hooks

   The hook is the tracked file `hooks/pre-push`, and `aurora branch up`
   installs it into every branch worktree. Worktrees share `.git/hooks` with
   the main checkout, so arming it the obvious way would write into
   production. A *relative* `core.hooksPath` is resolved against each
   worktree's own root, so this single write arms every present and future
   worktree. Until it runs, the hook is installed but inert.

       git -C ~/Desktop/aurora rev-parse --git-path hooks   # -> .../aurora/hooks

7. **Delete the nested standalone clone:**

       rm -rf ~/Desktop/aurora/dev-administration/.git

   A leftover clone pinned at `c0d7d8a` that shadows the tracked path. Its
   history is in this monorepo, its final commit (`202fc6f`) is imported, and
   its origin URL embeds the old token.

8. **Delete root-owned residue** — needs sudo; the Docker daemon created these
   and `branch down` cannot:

       sudo rm -rf ~/.cache/aurora-acceptance/          # 7 leaked acceptance worktrees
       sudo rm -rf /opt/data/workspace/tai/affine/      # orphaned pre-migration AFFiNE data

9. **Register the aurora MCP server**, inside the Hermes container:

       hermes mcp add aurora --command docker \
         --args run -i --rm -v /var/run/docker.sock:/var/run/docker.sock \
         aurora-cli:local mcp

   Verify with `hermes mcp list` — transport `stdio`, status enabled. For
   Claude Code, the equivalent block goes in `.mcp.json` at the repo root.

   **This registration mounts the Docker socket, which is host root. It is the
   owner's, and it does not go in the `aurora-agent` profile repo** — every
   provisioned Hermes would inherit it. A developer gets step 10 instead.

10. **Give a developer their own ephemeral stacks** — once per developer, after
    they are in `developers.yaml`. Knobs and refusals: `USERGUIDE.md` §3.

    1. `command -v socat` — the broker is a `socat` listener; without it, 127.
    2. `ops/aurora-spawn-broker <developer>` and leave it running. It refuses a
       name not on the roster before it creates anything, and there is no unit
       file — a closed terminal is a stopped broker.
    3. Add `-v ~/.aurora-spawn/<developer>:/run/aurora-spawn:z` to that
       developer's agent container and recreate it. `:z` is not optional here;
       SELinux is `Enforcing` and the container sees `Permission denied`
       without it.
    4. Point them at `docs/setup/user/hermes-setup.md`.
    5. Schedule the reaper. Nothing else destroys an expired lease:

           */15 * * * * cd ~/Desktop/aurora && AURORA_PYTHON=/usr/bin/python3 PATH=$HOME/.local/bin:$PATH ./aurora dev-spawn reap

       Run it by hand with `--dry-run` first — it force-removes worktrees, so a
       developer's uncommitted work goes with the lease. The explicit `PATH`
       keeps `ops/docker-guard` in front of `docker`; cron inherits neither it
       nor a `.venv` that does not exist.

    The mount is deliberately **not** in `compose.agents.yml`: a bind source
    that does not exist yet is created by the daemon **as root**, inside the
    checkout — the mechanism behind this repo's leaked worktrees.

---

## Still open

1. **Revoke the old Forgejo admin token — order matters.**
   `5299ae2b…` still authenticates (verified: HTTP 200 on `/api/v1/user`). It
   was removed from `admin-asks.md` and from `.env`'s dead comment, but
   **production's `origin` URL still embeds it**, so revoking first breaks
   pushes. Re-point `origin` at the current token or a credential helper,
   *then* revoke. The current token is clean — it appears in no tracked file.

2. **Rotate `ARCADEDB_ROOT_PASSWORD`.** Still the literal value baked into the
   running container. Do it before arcadedb holds anything real.
   See `docs/issues/arcadedb-oom.md`.

3. **Move the test-account passwords out of `dev-administration/scripts/`.**
   Two values across six files (`cookie_probe.py`, `session_probe.py`,
   `spa_check.py`, `trace_oidc.py`, `e2e_login.py`, `signup_test.py`) as inline
   defaults. Use env vars with no default so they fail loudly. Less urgent
   since `testuser` was deleted, but the `signup_test.py` value is unrelated
   to it. See runbook §2.

4. **Two Tier B defects, both blocking a clean branch.** Full writeups in
   `docs/issues/chunk3-spec-deltas.md` §14 and §15.
   - `reconcile` intermittently fails on a seeded branch (2 of 4 runs), so
     branch Caddy keeps production's fragment and every `/agent/` route 502s.
   - An ephemeral node deregisters after ~1 hour, not at teardown, so a
     re-run inside that window needs a fresh branch name
     (`AURORA_TIER_B_BRANCH`).

   To re-run the tier after either is fixed (~11 min, leaves a root-owned
   worktree under `~/.cache/aurora-acceptance/`):

       AURORA_PROJECT=aurora AURORA_EXPECT_TIER_B=1 AURORA_TIER_B_BRANCH=tierb6 \
         .venv/bin/python -m pytest tests/test_branch_acceptance.py -v

6. **`reconcile` never writes the live `owners.json` — the bind is missing.**
   `provision.py:543` writes the agent→owner map to `$OWNERS_MAP_PATH`,
   defaulting to `/output/agent-authz-data/owners.json`. That path is declared
   **nowhere in `compose.yml`** — it is the only occurrence of the string in
   the repo — so `dev-admin` writes into its own container layer and the file
   is discarded when the container is removed. `agents.conf`/`agents.json`
   survive only because those are written by `docker exec` into the Caddy
   container instead.

   It fails silently: the code's `⚠ per-agent authorization will DENY` warning
   is on an `except OSError`, and `os.makedirs` inside the container succeeds.

   Live consequence today is small — `cumshit42069`'s entry is correct and its
   `client_id` matches OAuth2 app 23; the stale `testuser` (sub 3) and
   `newuser` (sub 14) entries name deleted Forgejo accounts, so no token can
   be minted for them. The forward-looking consequence is not small: **the
   next developer provisioned will get a Caddy route and no authz entry**, and
   nothing will say so.

   Likely one line on the `dev-admin` service, to be verified rather than
   assumed:

       - ./agent-authz/data:/output/agent-authz-data

7. **Retire the remaining QA accounts.** Forgejo still holds `alicetest`,
   `bobtest`, `testuser2`, `shitcum`, `jaun`, `johndear` and their
   `hermes-*-home` volumes, plus `hermes-selfreg-home`. None are in
   `developers.yaml`. Left alone deliberately — deciding what the roster
   should be is a separate pass from this cleanup.

---

Known limitations and where the spec was wrong:
`docs/issues/chunk3-spec-deltas.md`.
