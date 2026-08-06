# Inherited secrets and loose ends from the dev-administration absorption

Chunk 1, task 2 absorbed `dev-administration/` into this monorepo with its 33
commits of history. This file is the durable record of what that import carried
with it, plus everything else discovered during chunk 1 that needed a durable,
in-repo record rather than living only in a task report. It has grown past its
original four items and now runs to §7 plus an unnumbered closing subsection:

- **§1–2** are exposures that came in with the imported history (§1: a Forgejo
  admin token; §2: test-account passwords). §1's rotation is no longer just a
  loose end — see the note at the top of that section, and
  `docs/post-implementation-steps.md` §0, which supersedes it with a live-validity
  finding and should be read first.
- **§3** is a cleanup that must happen at merge time (a nested git repo left in
  production).
- **§4** is a decision that needs a human ruling (an un-imported upstream
  commit). It fixes a live authorization bug, so it is elevated to
  `docs/post-implementation-steps.md` §0b rather than filed under merge
  housekeeping — see the note at the top of that section.
- **§5–7** were added during tasks 3, 5, and 6 respectively: AFFiNE
  `container_name:` collisions, the Caddyfile divergence between what production
  actually served and what was committed, and the `model-cache` volume's
  merge-time re-check.
- The unnumbered subsection between §4 and §5 records a non-issue (the
  `developers.yaml` symlink) so it isn't mistakenly re-raised later.

Nothing here is a newly *created* secret.

> **Deliberate redaction.** Credentials below are truncated. Recording them in full
> would mint a *fresh* copy at HEAD in this very file, which is the opposite of the
> point. Exact file, line, and enough of a prefix to identify the value are given so
> that whoever rotates them can find every instance.

---

## 1. Forgejo admin token in imported history (not at HEAD)

> **This section is superseded by a live-validity finding.** Everything below
> describes where the token sits in imported history and at HEAD. What it does
> not tell you is whether the token still works — it does. Verified via
> `git ls-remote --heads origin`, which succeeds using the exposed value still
> embedded in this repo's origin URL. See `docs/post-implementation-steps.md`
> §0 for the evidence and the required action, and read it **before** treating
> this as merge-adjacent housekeeping — it is not, it is live now.

**Value:** `5299ae2b…` (40-hex Forgejo admin token)

**Where, in the imported history:**

| Commit | Effect |
|---|---|
| `1e136d6` "feat(oidc): confidential clients, prefix-aware redirects, validation harness" | introduced it at `dev-administration/scripts/dev-admin.sh:15` |
| `27b1aca` "feat: one-liner provisioning, verify CLI, docs; fix user_exists endpoint" | removed the hardcoded fallback |

The line was:

```sh
TOKEN="${FORGEJO_ADMIN_TOKEN:-5299ae2b…}"
```

i.e. an env var with the live token as its default.

**HEAD does not contain it in `dev-administration/`.** Verified:

```
$ git grep -l 5299ae2b… HEAD --
HEAD:admin-asks.md

$ git show HEAD:dev-administration/scripts/dev-admin.sh | sed -n 15p
DOMAIN="${DOMAIN_NAME:-superserver.tailc67a98.ts.net}"
```

### This is not a new exposure

The same token was **already tracked in this repo before the absorption**. Verified
at the pre-task commit:

```
$ git grep -l 5299ae2b… e186a1b --
e186a1b:admin-asks.md
```

It is also embedded in the origin URLs of **both** repositories' `.git/config`, as
`https://supergoodname77:<token>@superserver.tailc67a98.ts.net/git/...` — the Aurora
clone and the nested `dev-administration` clone (item 3).

So the absorption added a **second copy, in history only**, of a token that was
already live and already committed at HEAD elsewhere.

### The fix is rotation, not history surgery

Scrubbing `1e136d6`–`27b1aca` is not worth doing while the same token sits in
plaintext at HEAD in `admin-asks.md` and in two `.git/config` files. Rewriting
history would invalidate the freshly imported commits, break the restore point, and
leave the token just as compromised.

**Action:** rotate the Forgejo admin token. Then remove it from `admin-asks.md`,
and re-point both origins at a credential helper or an env var instead of an inline
URL. Once rotated, the copy in imported history is inert and can be left alone.

---

## 2. Test-account passwords now tracked at HEAD

These are **new at HEAD** as a direct result of the import — they did not previously
exist anywhere in this repo.

**`Sup3rTest!Pa…`** — for the live provisioned Forgejo account `testuser`:

| File | Line | Form |
|---|---|---|
| `dev-administration/scripts/cookie_probe.py` | 21 | `PW = sys.argv[2] if len(sys.argv) > 2 else "…"` |
| `dev-administration/scripts/session_probe.py` | 22 | same default-argument form |
| `dev-administration/scripts/spa_check.py` | 16 | same default-argument form |
| `dev-administration/scripts/trace_oidc.py` | 16 | same default-argument form |
| `dev-administration/scripts/e2e_login.py` | 16 | usage example in the module docstring |

**`SignUp!Tes…`**:

| File | Line | Form |
|---|---|---|
| `dev-administration/scripts/signup_test.py` | 21 | same default-argument form |

Note `e2e_login.py` is a docstring usage example rather than an executable default,
but the plaintext value is equally present and must be rotated with the others.

### Mitigating context — stated, not used to dismiss

The server is reachable only over the tailnet, and these are throwaway probe
accounts created for validating the OIDC login flow, not accounts with real data or
production authority. That genuinely lowers the severity.

It does not make the pattern acceptable. `testuser` is a **live provisioned
account** on the running stack — it appears in `dev-administration/developers.yaml`
— so this is a working credential for a real account, committed in plaintext, in a
repo whose whole purpose is to be shared and branched. The tailnet boundary is the
only thing standing between these values and use, and boundaries move.

**Action:** move all six to environment variables (e.g. `DEV_ADMIN_TEST_PASSWORD`,
`DEV_ADMIN_SIGNUP_PASSWORD`) with no inline default — fail loudly if unset rather
than falling back to a baked-in value. Rotate the two account passwords afterwards.
This is a small, self-contained change, but it is a behaviour change to the scripts
and so was deliberately left out of chunk 1.

---

## 3. Nested git repository still present in production

`~/Desktop/tai-review/dev-administration/.git` **still exists** on the production
checkout:

```
$ git -C ~/Desktop/tai-review/dev-administration rev-parse HEAD
c0d7d8ac714e42f1ad33f71d59b2e2360b8faca5
$ git -C ~/Desktop/tai-review/dev-administration status -s
 M developers.yaml
```

This is a consequence of a deliberate and correct choice during task 2: the brief
said to `mv` the directory out of production and restore it afterwards, but `cp -a`
was used instead so that production was never for a moment missing a live compose
build context and bind mount. The trade-off is that the original clone — including
its `.git` — was left in place.

Its `.git/config` origin embeds the admin token from item 1:

```
https://supergoodname77:<token>@superserver.tailc67a98.ts.net/git/supergoodname77/dev-administration.git
```

### Why this must not survive the merge

While `feat/ephemeral-branching` is unmerged this is harmless: production is on
`master`, where `dev-administration/` is still untracked, and the directory has to
physically exist for compose to build and bind-mount it.

The moment this branch merges to `master`, that same path becomes **tracked
content** — and it will be shadowed by a nested git repository that Aurora does not
control, is pinned to `c0d7d8a`, already carries an uncommitted local modification,
and is free to drift from the tracked copy indefinitely and silently.

**Action, at merge time:** delete `~/Desktop/tai-review/dev-administration/.git`.
Before deleting, confirm the working tree matches what Aurora tracks — in particular
that the uncommitted `developers.yaml` matches the version committed in `af76b76`,
which was taken from that very file. Verify with:

```
diff ~/Desktop/tai-review/dev-administration/developers.yaml \
     <(git show af76b76:dev-administration/developers.yaml)
```

Nothing is lost by deleting it: the source project's history lives on in this
monorepo and on the Forgejo remote.

---

## 4. Upstream commit `202fc6f` was deliberately not imported

> **Elevated in the runbook.** This describes a live, user-facing
> authorization bug, not a merge-housekeeping decision — it was previously
> filed in `docs/post-implementation-steps.md` under "Behavioural decisions"
> alongside items like a stale test assertion. It now has its own section,
> §0b, positioned next to the other live-and-independent-of-the-merge item
> (§0). Read that section for the action; this section is the historical
> record of the import decision.

The source repository's local branch `feat/multi-dev-oidc-provisioning` was one
commit **behind** its own remote. The import took the local tip, `c0d7d8a`
(33 commits). It did not take:

```
202fc6f  fix: denial page no longer links to the admin's personal dashboard
         dev_administration/caddy_utils.py | 21 +++++++++++--------
```

**Reasoning for the decision:** `c0d7d8a` is the revision the running stack is built
from. `202fc6f` is not deployed. Chunk 1's entire purpose is to make this repo an
accurate description of the running Docker stack, so importing a commit that is not
running would have defeated the goal at the moment of achieving it.

**Not lost.** It remains at
`https://superserver.tailc67a98.ts.net/git/supergoodname77/dev-administration.git`
on branch `feat/multi-dev-oidc-provisioning`.

By its message it fixes two real problems: a denial page linking denied developers
to the *admin's* personal dashboard, and `write_denied_page()` having become dead
code so 403s returned plain text. If accurate, that is a user-facing authorization
bug still present in production.

**Action:** a human must decide whether to apply it as an ordinary change on top of
the monorepo. It is out of scope for chunk 1 either way, since applying it would
change the stack's behaviour rather than describe it. Note this decision must be
made before the source repository is retired, or the commit becomes hard to find.

---

## Not an issue: the two `developers.yaml` paths

For the record, because it looks like a problem and has already been raised once:
`developers.yaml` at the repo root and `dev-administration/developers.yaml` are
**not** two files that can diverge. The root entry is a symlink:

```
$ git ls-files -s developers.yaml dev-administration/developers.yaml
120000 4c22a7bf5ff0759488a756be8cb17b2c4e27f97c 0	developers.yaml
100644 35aa7ca2f329a5533e94d612b2911883b91400fd 0	dev-administration/developers.yaml

$ git cat-file -p HEAD:developers.yaml
dev-administration/developers.yaml
```

Git mode `120000` is a symlink, and its blob is the literal target path. There is
exactly one real file. Divergence is impossible. Leave both as they are.

---

## 5. AFFiNE's `container_name:` values will collide at merge time

Chunk 1, task 3 brought AFFiNE's compose declaration into this monorepo via
`include: ./affine/compose.yml`, so that a hard Caddyfile dependency is finally
declared where it is used. This did not touch any running container — `docker
compose config` is parse-only, and it was verified with `docker ps` that
`affine_server` and its three siblings are still running exactly as they were,
under their original, separate `affine` compose project.

That is precisely the problem this item records.

AFFiNE's four services declare fixed `container_name:` values:

| Service (in `affine/compose.yml`) | `container_name:` |
|---|---|
| `affine` | `affine_server` |
| `affine_migration` | `affine_migration_job` |
| `redis` | `affine_redis` |
| `postgres` | `affine_postgres` |

These same four names are **already in use** by the running containers of the
separate `affine` compose project (verified live, all `Up`). Docker enforces
container-name uniqueness engine-wide, not per-project. Right now there is no
conflict, because this repo's own compose project (`tai-review` in production,
a worktree-derived name here) has never been brought up with AFFiNE included —
only `docker compose config` has been run against it.

**The conflict is deferred, not avoided.** The moment someone runs
`docker compose up -d` against this repo in production — after this branch
merges — Docker will try to create containers named `affine_server`,
`affine_migration_job`, `affine_redis`, and `affine_postgres`, find all four
names already taken by the still-running `affine` project's containers, and
fail with a name-conflict error. `tai-review`'s own new services would come up;
AFFiNE's four would not, and production would be split across two compose
projects pointing at the same container names.

### This is deliberate and out of scope for Chunk 1

Chunk 1's job is to make the repo *describe* the running stack accurately —
not to change what is running. Actually stopping the four live AFFiNE
containers and bringing them back up under the `tai-review` project is a
one-way operation with its own risk profile: it means a moment of AFFiNE
downtime, and it is exactly the kind of action that should happen once,
deliberately, at merge time — not as a side effect of a chunk whose stated
goal is "no behavior change."

**Action, at merge time, before anyone runs `docker compose up -d` in
production against the merged compose file:** stop the old standalone
project and bring AFFiNE back up under the `tai-review` project — wipe and
rebuild, not preserve. **The owner has confirmed this AFFiNE instance is
completely fresh — never logged into, no admin account, no workspace data —
so there is nothing to migrate.** For context on why the paths diverge (worth
understanding even though nothing needs preserving): the repo's
`affine/compose.yml` declares the Postgres bind mount as `./data/postgres`,
relative to `affine/compose.yml`, which resolves to
`~/Desktop/tai-review/affine/data/postgres`. The live container's actual bind
source (verified via `docker inspect affine_postgres --format
'{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'`) is instead
**`/opt/data/workspace/tai/affine/data/postgres`**, because AFFiNE's compose
project has always been driven from inside the Hermes container, not from
this repo's checkout, so the daemon materialised its binds under Hermes' own
volume — the two paths share no ancestor.

The fix is `docker compose -p affine down` (stops the old project's four
containers and frees the `container_name:` values), copy nothing, then bring
AFFiNE up under the merged project so Docker creates `affine/data/postgres`
and `affine/data/storage` fresh under `~/Desktop/tai-review/affine/data/` and
Postgres initialises a new, empty database — followed by AFFiNE's first-run
admin setup. A fresh instance also regenerates its own `private.key` (server
identity) on first boot, so there is nothing to copy there either. The old
data at `/opt/data/workspace/tai/affine/` is left orphaned and root-owned,
removable with `sudo rm -rf` once the new instance is confirmed working. The
full procedure, with exact commands, is in `docs/post-implementation-steps.md`
§A step 3 — follow it. **The previous claim here that "data volumes under
`affine/data/` are bind mounts and survive container recreation untouched"
was false** and has been removed; it described the repo-relative path, not
the path the live container actually uses. Until the old project is stopped
and the merged one brought up, `docker compose up -d` in production **will
fail** on these four name conflicts regardless. This is not a regression
introduced by task 3 — it is the necessary, deliberate seam between "declared
correctly" (this chunk) and "running under one project" (a merge-time
action).

---

## 6. Production's Caddyfile was live-edited and never committed; master's copy was a service generation stale

This is the sharpest instance in the whole chunk of the defect chunk 1 exists to
eliminate: **the repo described a fiction while reality sat uncommitted in a working
tree.** It was found during task 5, when the Odysseus `/chat` routes were removed and
the resulting config could not be safely reloaded.

### What was actually true

| Copy | Contents |
|---|---|
| Production **working tree** (`~/Desktop/tai-review/Caddyfile`) — *what Caddy actually serves* | AFFiNE routes → `127.0.0.1:3010`. No Immich routes. **Uncommitted** (` M Caddyfile`). |
| **`master`'s committed** `Caddyfile` | Immich routes → `127.0.0.1:2283`. No AFFiNE routes. |
| `feat/ephemeral-branching` (before the fix) | inherited master's committed version, i.e. the Immich one. |

Caddy bind-mounts the working-tree file:

```
$ docker inspect tai-review-caddy-1 --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
/var/home/supergoodname77/Desktop/tai-review/Caddyfile -> /etc/caddy/Caddyfile
```

So the committed Caddyfile had never been what production served. The live edit that
introduced AFFiNE routing was made directly in the working tree and never committed,
and `master` drifted an entire service generation behind: Immich → AFFiNE.

Immich is **gone** — there is no `immich` container on the engine and nothing is
listening on `2283`. Every one of the six `reverse_proxy 127.0.0.1:2283` directives in
master's committed Caddyfile points at a service that does not exist.

### Why merging as-is would have broken AFFiNE

Deploying the branch's inherited Caddyfile would not merely have failed to serve
AFFiNE — it would have actively broken part of it, via a named-matcher collision.

`@immich_root` and `@affine_static` are each a **named matcher carrying several path
patterns**, not a single bare path. Caddy's Caddyfile adapter only auto-sorts `handle`
blocks by descending path specificity when each block's matcher is a single bare path;
a named matcher with multiple patterns can't be ranked that way, so blocks using one
fall back to file order — and in master's committed Caddyfile, `@immich_root` is
declared before AFFiNE's routes would have been. The two matchers collide on exactly
three of AFFiNE's five claimed paths: `/favicon.ico`, `/favicon-*.png`, and
`/manifest.json`. They do **not** collide on `/robots.txt` (Immich doesn't claim it)
or `/apple-touch-icon.png` (Immich claims `/apple-icon-*.png` — a different literal
prefix that does not match `apple-touch-icon.png`).

`/affine/` would have gone dark on those three paths, and task 3 — which had just
brought AFFiNE into the monorepo so that this very Caddyfile dependency was declared
where it is used — would have been partially undone in the same merge.

**Correction to a claim previously made in this section:** it originally also asserted
that Immich's `handle /api/*` would have shadowed AFFiNE's `handle /api/auth/*`,
declared later in the file. That is almost certainly wrong. `handle` blocks that each
carry a *single* bare path matcher — which is exactly what `/api/*` and `/api/auth/*`
are — get sorted by the Caddyfile adapter by descending specificity (longer, more
specific path first), independent of file order. `/api/auth/*` is more specific than
`/api/*` and so would have been tried first regardless. The named-matcher collision
above is the collision that actually mattered; the single-path-matcher claim is
retracted.

### What was done

The branch's `Caddyfile` is now **production's live file, minus Odysseus**:

1. `~/Desktop/tai-review/Caddyfile` was copied into the worktree (read-only on the
   production side — copied *from*, never written *to*).
2. The two Odysseus redirect blocks (`handle /chat/*`, `handle /chat`) and their comment
   header were deleted — the original task 5 change, re-applied to the correct base.
3. Verified: no `/chat`, no `2283`, no Immich references remain; the AFFiNE routes
   (`/affine/*`, `/affine`, `/admin/*`, `@affine_static`, `/graphql`, `/api/auth/*`),
   Forgejo `/git/*`, Hermes `/agent`, the `agents.conf` import and the fjell default
   handler are all present and unchanged.
4. Validated in a throwaway `caddy validate` container: `Valid configuration`.

One comment-only deviation from byte-identical: the AFFiNE comment header opened with
*"(must come before Immich to claim /favicon.ico, …)"*, an ordering constraint against a
service that no longer exists. That clause was dropped; the sentence now reads
"AFFiNE — routes all AFFiNE paths to the backend." No directive changed.

**Production's Caddy was deliberately NOT reloaded.** The config is now correct, but
reloading is a deploy action and belongs to the merge, not to this branch. Production
still serves its own working-tree file, which still contains the dead `/chat` redirect
(it points at Tailscale Serve port `:7443`, which no longer has a backend — a dead
redirect, not an outage; `/git/` and `/affine/` are unaffected and verified serving).

### Action, at merge time

Production's working-tree `Caddyfile` is modified-uncommitted, so it **will conflict**
with the incoming branch version.

1. **Diff against production's live file first — do not resolve unconditionally in
   favour of the branch.** The branch's `Caddyfile` (committed at `fef099b`) is a
   snapshot of production's live file as it stood on 2026-07-28, minus the Odysseus
   block and minus one stale comment clause (see above). But production's `Caddyfile`
   is still uncommitted and live-editable — the exact property that caused this whole
   problem — so it can move again before the merge actually happens.
   ```
   diff ~/Desktop/tai-review/Caddyfile <(git show fef099b:Caddyfile)
   ```
   - If the only differences are the Odysseus block and the dropped comment clause
     (or there are no differences at all), production has not been touched since the
     2026-07-28 snapshot: take the branch version.
   - If production's file differs in any other way, someone edited it again after the
     snapshot was taken. Do **not** silently discard that edit by taking the branch
     wholesale — reconcile the new edit by hand into the branch's version, the same
     discipline applied just below to `Caddyfile.d/agents.conf`, `Caddyfile.d/agents.json`,
     and `agent-authz/data/owners.json`: diff against the committed copy and decide
     deliberately, rather than letting whichever side git happens to favour win.
2. Then `docker exec tai-review-caddy-1 caddy reload --config /etc/caddy/Caddyfile` to
   apply whatever was decided (this also drops the dead `/chat` redirect from the
   running proxy, if the branch version was taken as-is).
3. If the reload fails, Caddy keeps serving its previous config — check
   `docker logs tai-review-caddy-1 --tail 30` and fix forward. **Do not restart the
   Caddy container:** a failed reload is recoverable, a restart with a broken config is
   an outage.

### The same hazard applies to three more runtime files

`Caddyfile` was not the only file live-edited in production and never committed. Also
modified-uncommitted at the time of writing:

```
$ git -C ~/Desktop/tai-review status --short
 M Caddyfile
 M Caddyfile.d/agents.conf
 M Caddyfile.d/agents.json
 M agent-authz/data/owners.json
 D nfs-exports.txt
```

- **`Caddyfile.d/agents.conf`** and **`Caddyfile.d/agents.json`** — generated by
  `dev-admin reconcile`, bind-mounted into Caddy, and imported by the Caddyfile. The
  running per-developer dashboard routes live here.
- **`agent-authz/data/owners.json`** — live authorization state for `agent-authz`.

Each carries the identical risk: **the committed copy is not what production runs, and
a merge will overwrite the working tree with a stale version.** For generated and
state-carrying files the right resolution is usually the *opposite* of the Caddyfile's
— keep production's working-tree copy, since it is the live state — but each must be
diffed against its committed version and decided deliberately at merge time, not
resolved by whichever side git happens to favour.

(`D nfs-exports.txt` is a tracked file deleted out-of-band; task 6 owns it.)

---

## 7. `tai-review_model-cache` was removed on the branch only — production's compose.yml still declares it until merge

Task 6 deleted ~120 lines of commented-out service definitions from
`feat/ephemeral-branching`'s `compose.yml` (Immich, FalkorDB, tai-db, NFS, redis),
including the `model-cache:` volume declaration that only the now-deleted Immich
machine-learning block referenced. After removing the declaration, the orphaned
volume was removed live:

```
$ docker volume rm tai-review_model-cache
tai-review_model-cache
$ docker volume ls | grep model-cache
(nothing)
```

Nothing currently references this volume and nothing was restarted to remove it.

### Why this is not actually finished

Task 6's write restriction on the production checkout permits editing only `.env`
and deleting the named stale directories — **not** `compose.yml`. So the
`model-cache:` declaration was deleted only in the worktree's copy of
`compose.yml`. Production's own `compose.yml` at
`~/Desktop/tai-review/compose.yml` **still declares `model-cache:` today**.

This matters because the running containers are not labeled against the
worktree's file. Verified directly:

```
$ docker inspect tai-review-caddy-1 \
    --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}'
/var/home/supergoodname77/Desktop/tai-review/compose.yml
```

Every container in the `tai-review` project carries this same label, pointing at
production's file, not the branch's. **The live project is governed by whichever
`compose.yml` is named in `com.docker.compose.project.config_files` on the running
containers — the branch's edits are not in force until that file is what's on
disk in production.** This generalizes beyond this one volume: any service or
volume removed on `feat/ephemeral-branching` (or any branch) remains fully
declared, from the running project's point of view, until the branch is deployed
to production.

### Practical effect between now and merge

If anyone runs `docker compose up` (or restarts/recreates a service) in
production **before this branch is merged and deployed**, compose will re-read
production's still-unmodified `compose.yml`, see `model-cache:` declared, and
silently recreate it — empty, unused, and orphaned exactly as it was before task
6 ran. The cleanup would be quietly reversed with no error and no visible signal
that it happened.

### Required action at merge time

After the merged `compose.yml` (the one with `model-cache:` already removed) is
deployed to production — i.e. after production's working copy is the branch's
version — **re-check for the volume and remove it again if it reappeared**:

```
docker volume ls | grep model-cache
# if present:
docker volume rm tai-review_model-cache
```

Do this once, after deployment, before considering task 6's cleanup complete.
If nothing recreated it in the interim, the check is a no-op confirmation. If
something did (an incidental restart, a manual `compose up`, etc.), this is the
step that finishes the removal for real.
