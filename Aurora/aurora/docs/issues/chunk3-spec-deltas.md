# Chunk 3 — spec deltas, deliberate deviations, and known gaps

Everything Chunk 3 measured that the spec (`PLAN.md` §4–§13) or the
implementation plan
(`docs/superpowers/plans/2026-07-29-chunk3-ephemeral-branching.md`) states
differently, plus the things this chunk deliberately did **not** do. Each entry
says what the source claims, what was measured, and what was done about it.

Nothing here is a to-do list for the next agent by default. Items that need a
human are in `docs/post-implementation-steps.md`.

**Read these first:** §1 (teardown cannot remove a branch worktree) and
§14 (`reconcile` cannot run against a seeded branch, so `aurora branch up`
never completes and no branch has working `/agent/<user>/` routes). §15 is
next: ephemeral nodes are not leaving the tailnet, which makes a second Tier B
run of the same branch name fail.

---

## 1. BLOCKING — `aurora branch down` cannot remove a branch worktree

**Severity: high. This is the single most important entry in this file.**

**Measured, 2026-07-30, on a real branch stack.** The Docker daemon creates
bind-mount source directories that do not yet exist, and it creates them as
**root**. A branch worktree therefore acquires, during `up`:

| path inside the worktree | owner | mode |
|---|---|---|
| `affine/data` | `root:root` | 755 |
| `affine/data/postgres` | `polkitd:root` (uid 999, the container's `postgres`) | 700 |
| `forgejo/ssh` | `root:root` | 700 |
| `.agent-env` | `root:root` | 755 |

The invoking user cannot unlink any of them. `branch down` therefore reports:

```
br-<name>: removed 1 containers, 0 volumes, 1 networks
  NOTE: git worktree remove exited 255: error: failed to delete
  '<production>/.worktrees/<name>': Permission denied. Uncommitted changes need
  --force.
```

`--force` does **not** help. It is a filesystem permission, not a git refusal.

**Consequences, in order of seriousness:**

1. Decision **D-F** puts branch worktrees at `<production>/.worktrees/<name>`,
   so the leaked directory is **inside production's checkout**, inside the tree
   production's Hermes container bind-mounts as its workspace. A seeded branch
   leaks ~2.6 GB *apparent* (reflinked, a few MB real) plus the root-owned
   directories.
2. A **second `up`/`down` cycle of the same name is impossible**:
   `_add_worktree` refuses when the destination exists, which it now always
   does. The plan's Task 12 asks for two cycles precisely because adoption bugs
   surface on the second one; that cycle **could not be run** and remains
   unproven.
3. `git worktree list` keeps a fourth entry until someone prunes it, because
   `git worktree prune` only reclaims administrative entries whose directory is
   *gone*.

**Why it was not fixed here.** The only mechanism available to a user without
`sudo` is a container running as root with the worktree bind-mounted
(`docker run --rm -v <worktree>:/w … rm -rf`). That is a genuinely dangerous
primitive to add to a teardown path — it is `rm -rf` as root against a path
derived from user input — and it would need its own positive guard, its own
mutation table and its own empirical tests before it could be trusted. Adding
it unverified would be worse than the leak.

**What a human should do.** Either:

* remove leaked worktrees by hand —
  `sudo rm -rf <production>/.worktrees/<name>` — and accept the manual step; or
* implement the container-based sweep in `branch.branch_down`, behind
  `guards.assert_not_production_path`, mounting **only** the worktree so the
  container cannot reach anything else, with mutations proving the guard is on
  the path.

Until then the live-stack acceptance tier is opt-in via
**`AURORA_ACCEPTANCE_STACK=1`**, and
`tests/test_branch_acceptance.py::test_teardown_could_not_remove_the_worktree_and_says_which_files_stopped_it`
asserts the defect so a fix turns it **red** rather than letting it pass
unnoticed.

---

## 2. Trap 9 is only half right: an INVALID auth key kills the sidecar

The plan's trap 9 and decision D-D rest on the measurement that a `tailscaled`
container with **no** auth key "starts anyway, prints `Logged out.` and stays
up". That is correct and still reproduces.

A container given an auth key that is **not valid** behaves differently, and the
plan predicts the opposite. Measured 2026-07-30:

```
2026/07/30 14:27:47 Received error: invalid key: unable to validate API key
backend error: invalid key: unable to validate API key
boot: Sending SIGTERM to tailscaled
boot: failed to auth tailscale: tailscale up failed: exit status 1
$ docker ps -a  ->  br-tsprobe-tailscale-1   Exited (1)
```

The container **exits 1**, taking the shared network namespace with it: a peer
running `network_mode: service:tailscale` survives but loses `eth0` (only `lo`
remains), while keeping `127.0.0.11` in `resolv.conf`.

Both endings are loud, which is what trap 9 wanted, so no code changed. But:

* the plan's Task 12 step "set a dummy key and continue: the sidecar starts and
  stays `Logged out`, and `up` must fail at the readiness poll" **cannot happen
  as written** — with a dummy key the sidecar is gone before the poll runs, and
  `up` fails earlier and for a different reason;
* `branch up`'s readiness message ("the branch's tailnet node did not become
  ready") is accurate but misleading in this case — the node is not *pending*,
  the sidecar is *dead*. Worth improving; not changed here.

Pinned by
`tests/test_branch_acceptance.py::test_a_sidecar_with_an_invalid_key_exits_rather_than_staying_logged_out`,
which fails if containerboot's behaviour changes back.

---

## 3. `aurora branch up <name>` with no `--from` produces an unusable branch today

The plan's Task 12 command is `./aurora branch up acceptance --devs testuser`.
`git worktree add` without a ref branches from production's checkout **HEAD**,
which is `main` at `e1f9ca6` — a commit that predates Chunk 2 and therefore
contains no `compose.branch.yml`, no `branch-env.yaml` and no `aurora-cli/`.
Compose's `-f` is a hard error on a missing file (trap 4), so the branch dies at
the first compose call.

Every acceptance run therefore passed `--from feat/chunk3-ephemeral-branching`.
**This resolves itself the moment this branch merges to `main`**, and it is the
same root cause as Task 11's open item 2 (the MCP registration's
`-w <production root>` finds no `aurora-cli` until the merge lands).

---

## 4. `branch down` leaves the git branch it created

`branch up` runs `git worktree add -b <name>`, creating `refs/heads/<name>` in
**production's** repository. `branch down` removes the worktree and prunes the
administrative entry but never deletes the ref, so production's ref namespace
accumulates one branch per branch stack ever minted — and a second `up --from`
of the same name then fails with "`<name>` already exists".

Not fixed in code (deleting a ref is a judgement call: the branch may hold work
someone wants). The acceptance module cleans up after itself, and only when the
ref still points at the exact commit `up` created it from.

---

## 5. §4.1's must-override list omits three hostname-bearing variables

Finding N1, carried here so it survives the plan. Production's `.env` holds
three variables that embed production's hostname as a literal and are not
derived from `DOMAIN_NAME`:

```
FORGEJO_URL
AFFINE_SERVER_EXTERNAL_URL
AURORA_PROFILE_URL
```

Inherited unchanged, a branch's `dev-admin` would create OAuth applications in
**production's** Forgejo, its agents would register OIDC against production's
issuer, and AFFiNE would advertise production's external URL to its own
clients. The §5.3 label guard cannot catch any of it — the guard protects
containers, and this is an HTTP call to a hostname.

All three are in `branch-env.yaml` with `fatal: true`, and
`tests/test_branch_env.py` fails in **both** directions: a rendered branch
`.env` missing an entry, and a production `.env` variable whose value contains
production's domain and is not listed. A fourth, `HERMES_TAILNET_IP`, is inert
only because `ports: !reset []` removes the publish that reads it; it is listed
anyway, `fatal: false`, so the coupling is written down.

---

## 6. `SSH_DOMAIN` still advertises production's hostname inside a branch

Finding N4. `compose.yml` overrides `FORGEJO__server__ROOT_URL` and `DOMAIN`
from `${DOMAIN_NAME}`, but **not** `SSH_DOMAIN`, and the seeded `app.ini`
carries production's. A branch's Forgejo UI therefore offers
`ssh://…@<production host>:222/…` as its clone URL.

**Left alone deliberately.** A branch publishes no ports, so its SSH port does
not exist, and an SSH clone URL pointing at production is the *safe* direction
of the §5.4 cross-wiring concern — the hazard is a commit pushed into a forge
that is about to be destroyed, and this points the other way. Recorded so the
next reader does not "fix" it into a hazard.

---

## 7. A branch's `/agent` admin redirect is dead, and that is accepted

Finding N5. The Caddyfile's `handle /agent` (an exact match, not a prefix)
redirects to `https://{$DOMAIN_NAME}:{$HERMES_SERVE_PORT}/`, which is a
`tailscale serve` mapping that exists only on the host, for production. A
branch's sidecar runs no `serve`, so the URL leads nowhere.

Per-developer `/agent/<user>/` routes are unaffected — they are generated into
`Caddyfile.d/agents.conf` and proxied in-namespace. `BranchResult.urls()`
deliberately does not emit `/agent`, and `BRANCH-ACCESS.md` prints the reason in
its place. A URL that fails is worse than no URL.

---

## 8. The "seed did not mutate production" invariant excludes `*-shm`

Finding N6, and it is a measurement, not a convenience. A **read-only**
`VACUUM INTO` against production's live `.hermes/state.db` (47 MB, 0.05 s) left
`state.db` and `state.db-wal` byte-identical and **rewrote** `state.db-shm`.
`-shm` is the mmap'd WAL index, not content.

A whole-tree checksum comparison would therefore go red against a *correct*
seeder. `branch_harness.PROD_VOLATILE_SUFFIXES` excludes `-shm`, `.lock`,
`.pid` and `.log`, each for the same class of reason: production is live and
writes them on its own schedule.

---

## 9. RESOLVED — Tier B ran. Four of six assertions proven, two blocked

The user supplied `TS_AUTHKEY_BRANCH` on 2026-07-30. Tier B was written and
**executed** the same day against a real branch (`tierb`), a real
`tailscale/tailscale` sidecar and a real key.

| # | Assertion | Result |
|---|---|---|
| 1 | node reaches `Running` in `tailscale status` | proven |
| 2 | Caddy serves the branch's own certificate, from the branch's tailscaled | proven |
| 3 | `https://aurora-<name>.<suffix>/git/` serves the branch's own forge | proven, with one substitution |
| 4 | `/agent/<user>/` proves `AGENT_UPSTREAM_MODE=service` reached the `.env` | **blocked by §14** |
| 5 | reachable from inside production's Hermes container (§10.3) | proven |
| 6 | ephemeral node deregisters after teardown | **blocked by §15** |

Detail, and the reason assertion 3's wording changed, is in
`docs/testing/2026-07-29-chunk3-ephemeral-branching.md`. Both blocked
assertions are `xfail(strict=True)`, so each fails the suite the moment it
starts passing.

Decision D-D still stands for the *next* key: minting one is an admin-console
action an agent cannot perform.

---

## 10. Deferred from §10.3, with the reason

Two of spec §10.3's end-to-end assertions are **out of scope for this plan**,
deliberately, and are recorded here rather than left to quietly not happen:

* **Full OIDC login as a seeded user.** Needs a browser session against a
  tailnet URL: Tier B *plus* interactive credentials. Neither is available to an
  agent.
* **The merge-back test** (work committed in a branch worktree, pushed to
  production's forge, and landing on `main`). Same reason, plus a live push to
  production's Forgejo — which the pre-push hook is specifically built to make a
  deliberate act.

---

## 11. A branch's AFFiNE Postgres can fail to start, and its healthcheck lies

Observed once during acceptance exploration and **not** fully explained.
A branch's `affine/data/postgres` came out owned by uid 1000 mode 700 while the
server process runs as uid 999, so every query returned

```
FATAL: could not open file "global/pg_filenode.map": Permission denied
```

`affine_migration` then failed, and because `affine` declares
`depends_on: affine_migration: service_completed_successfully`, the whole
`docker compose up` returned non-zero.

The dangerous part is not the failure, it is that **`pg_isready` reported the
service healthy throughout** — `docker compose up --wait` was satisfied, and the
defect surfaced one service later as a migration error. A healthcheck that
passes over an unreadable data directory is worse than no healthcheck.

Not reproducible in a clean by-hand `docker compose up` of the same file set
(the directory then comes out `999:0` and everything works), so the trigger is
not yet identified. Recorded because a branch that half-starts and blames
Prisma is an expensive thing to debug from scratch. This is **not** specific to
Chunk 3 — nothing in the branch tooling touches `affine/data`, which
`seed.HOST_PATH_PLAN` marks `copy=False`.

---

## 12. Compose v5.3.1's `down` is profile-agnostic — trap 3 is stale

The plan's trap 3 says `docker compose down` needs `--profile '*'` or profiled
services survive. Measured three ways on this host: `down` with no `--profile`
removed **both** containers of a probe project including the profiled one.

The flag is kept everywhere it appears — explicit beats relying on undocumented
behaviour, and a future Compose could re-narrow it — but the *guarantee* of no
profiled residue comes from the label-and-name sweep in
`branch_harness.teardown_branch_project` and `branch.branch_down`, which is
mutation-proven, not from the flag.

---

## 13. ~~BLOCKING, INHERITED~~ **FIXED 2026-07-30 in `5ab7fbb`** — `dev-admin` could not start from a clean checkout

> **Status: fixed.** The mount now lands at `/compose.agents.yml`, outside the
> read-only `/app` bind, with `AGENTS_COMPOSE_PATH` following it. Verified in
> both directions with throwaway containers: the old form fails exactly as
> quoted below, the new form starts and reads the file.
>
> Two properties of this defect are worth carrying forward, because they are
> what let it survive an entire chunk of green suites:
>
> * **`docker compose config` validates the broken form happily.** Config
>   validation cannot see this class of failure at all — only an actual
>   container start can.
> * **Production runs an older `compose.yml` that never exercised it.** It
>   would have surfaced on the first `docker compose up` *after the merge*,
>   i.e. during the Chunk 2 rename deploy, where it would have looked like the
>   rename broke provisioning.
>
> The test that asserted this defect was **inverted rather than deleted**, and
> generalised: no file may be mounted under `/app` unless its mountpoint exists
> in `dev-administration/`. The instance is gone; the rule that catches the
> next one is not.
>
> Original report follows.

### 13 (original). BLOCKING, INHERITED — `dev-admin` cannot start from a clean checkout

**Severity: high. Not a Chunk 3 defect; Chunk 3 is the first thing to execute
it.**

`compose.yml` mounts the package read-only and then mounts a file *into* that
read-only mount:

```yaml
  dev-admin:
    volumes:
      - ./dev-administration:/app:ro
      - ./developers.yaml:/app/developers.yaml
      - ./compose.agents.yml:/app/compose.agents.yml:ro   # <- cannot work
```

runc must create `/app/compose.agents.yml` as a mountpoint. It cannot: `/app`
is a read-only bind of `./dev-administration`, and that directory contains no
such file — nor does the `dev-admin:local` image. Measured against a real
branch stack, 2026-07-30:

```
Error response from daemon: failed to create task for container: ...
error mounting "<worktree>/compose.agents.yml" to rootfs at
"/app/compose.agents.yml": create mountpoint for /app/compose.agents.yml
mount: make mountpoint "/app/compose.agents.yml": read-only file system
```

The sibling line `./developers.yaml:/app/developers.yaml` works **only**
because `dev-administration/developers.yaml` happens to be a tracked file that
can serve as the mountpoint. That is luck, not design, and it is why the
failure names only one of the two.

**Why nobody has hit it.** The mount arrived with the compose-agents migration
(`bf3ba2a`) and has never been deployed. Production runs an older `compose.yml`
from `main` at `e1f9ca6`, which has no such line — verified by `grep` in both
checkouts.

**What it costs.**

* `docker compose up` exits non-zero for the whole project, so `aurora branch
  up` reports the branch incomplete even though every other service started.
* `reconcile` can never run in a branch, and `reconcile` is what provisions
  every agent — so a branch's `/agent/<user>/` routes would never be created
  even once Tier B's auth key exists.
* **It will break production's `dev-admin` on the first `docker compose up`
  after this branch merges.**

**Not fixed here, deliberately.** The fix is a one-line change to Chunk 1/2's
`compose.yml` — mount the file somewhere outside `/app` and point
`AGENTS_COMPOSE_PATH` at it — but it changes production's deployed
configuration, and verifying it needs another real branch stack, which under §1
means another undeletable worktree. Fixing production's compose config
unrequested, from the last task of an unrelated chunk, is not a trade worth
making silently.

Pinned statically, with no stack required, by
`tests/test_branch_acceptance.py::test_dev_admin_cannot_start_from_a_clean_checkout_of_this_branch`,
and by an `xfail(strict=True)` on
`test_branch_up_completed_every_step_it_did_not_stub`. Both go **red** when it
is fixed.

---

## 14. BLOCKING — `reconcile` intermittently cannot run against a **seeded** branch

**Measured across five real Tier B runs, 2026-07-30: `reconcile` failed on two
of them and succeeded on two more** (the fifth did not reach the assertion).
When it fails, `aurora branch up` fails at its third readiness step. Everything before it succeeded: worktree, rendered
`.env`, seed, Postgres restore, the whole 14-container stack, the tailnet node
and the branch's own certificate.

Mechanism, and every step of it is a deliberate decision meeting another one:

1. the seed copies production's Forgejo database, so the branch's forge already
   holds production's `hermes-<user>` **OAuth2 applications**;
2. the seed deliberately does **not** copy `.agent-env` — production's OIDC
   client secrets — because copying them would register a branch's agents
   against production's issuer (`aurora_cli/seed.py`; finding N1);
3. `provision_developer` therefore finds an existing app whose secret it cannot
   recover, and takes the delete-and-recreate path;
4. `DELETE /api/v1/user/applications/oauth2/<id>` against the branch's own
   forge answers **≥ 400** (`curl -f`, exit 22), and `reconcile` raises.

**Why it is intermittent.** When the branch's Forgejo has not yet exposed those
rows to the API, step 3 finds no app at all, `reconcile` creates a fresh one and
succeeds. So the outcome of `aurora branch up` on a seeded branch depends on a
race — which is worse than a deterministic failure, not better: the same command
sometimes leaves a branch with an OAuth app pointing at the wrong redirect URI
and reports success.

That path has **never executed in production**, where the secret is always
recoverable from `.agent-env`, which is why an entire chunk of green suites
never saw it.

Consequences, worst first:

1. **`aurora branch up` never completes.** It raises `BranchUpFailed` and
   leaves the branch running, which is the designed behaviour for a
   half-built branch — but it is not success.
2. **`reconcile` dies before it writes `agents.conf`**, so the branch's Caddy
   keeps the *committed* fragment. That fragment is **production's**, generated
   in `published` mode, and it names developers the branch never provisioned.
   Every `/agent/<user>/` route on a branch therefore answers 502 — and for a
   reason that is not `AGENT_UPSTREAM_MODE`, which did reach the branch `.env`
   and is asserted to have done so.
3. Tier B assertion 4 cannot be proven. It is `xfail(strict=True)` on
   `test_the_agent_route_reaches_hermes_and_proves_service_upstream_mode`.

**Not fixed.** The fix is in `dev-administration`, not in the branching code,
and it needs a decision this task cannot make: either the delete path is
repaired (find out why the DELETE is refused and use the right endpoint or
scope), or `reconcile` stops trying to reuse an inherited app at all and the
seed drops `oauth2_application` rows for `hermes-*` — which is arguably the
correct answer, since a branch's OAuth apps must point at the branch's redirect
URIs anyway.

Pinned by two `xfail(**strict=False**)` tests. Non-strict is deliberate and it
is the uncomfortable half of this entry: a strict marker on an intermittent
defect flaps between FAILED and XPASS on a race, which trains a reader to ignore
it. The cost is that nothing shouts when this is fixed — **so this is the
instruction: when the race is gone, make both markers `strict=True` again and
re-run Tier B.** The two tests are
`test_branch_up_completes_on_a_branch_with_a_real_tailnet_identity` and
`test_the_agent_route_reaches_hermes_and_proves_service_upstream_mode`.

Note also that assertion 4 failed on **all four** runs, including the one where
`reconcile` succeeded. Whatever else is wrong with the `/agent/<user>/` path on
a branch, it is not only this race.

---

## 15. Ephemeral nodes leave the tailnet about an **hour** after teardown, not on it

**Measured 2026-07-30, and the first reading was misleading — it is recorded
that way on purpose.** After `aurora branch down tierb` removed every
container, volume and network, the node `aurora-tierb` was still a peer of
production's tailscaled **300 s later**, still a peer at **51 minutes**, and
**gone by 71 minutes**.

So the key **is** Ephemeral and spec §4.4 **does** hold. What is wrong is the
timescale: Tailscale's control plane reclaims an ephemeral node roughly an hour
after it goes offline, not when its stack is destroyed. The assertion as
specified — "the ephemeral node deregisters after teardown" — is therefore not
observable inside any window a test can afford. 300 s is already generous in a
fixture that also stands up a 14-container stack; an hour would make the tier
unrunnable.

The consequence is operational, and it lasts about that hour: **a second
`branch up` of the same name registers as `aurora-<name>-1`**, because the name
is still taken. `tailscale_readiness()` correctly refuses that — it is the
check that exists for exactly this — so `branch up` fails at `await_tailnet`
with a message about a name suffix. Five Tier B runs one evening therefore
needed five names, `tierb` through `tierb5`, and `$AURORA_TIER_B_BRANCH` exists
for precisely that.

Assertion 6 is **unproven in-test**, pinned by `xfail(strict=False)` on
`test_the_ephemeral_node_left_the_tailnet_after_teardown`. Non-strict because
the reclamation time is not fixed and a strict marker on a timer flaps. Nothing
in the product needs fixing; to prove the assertion you need either an hour of
watching or the Tailscale API, and a credential this suite does not have.

---

## 16. Tier A1's seeding invariant compares `gitea.db-wal`, and that is flaky

**Measured 2026-07-30, with no branch anywhere on the host and nothing running
but production:**

```
20:16:03  gitea.db 4ab13cad…  gitea.db-wal 9132b816…
20:16:48  gitea.db 4ab13cad…  gitea.db-wal c82eb14a…
```

Production is live and rewrites its own WAL on its own schedule — 45 s was
enough — while the database *content* stayed byte-identical.

`tests/test_branch_acceptance.py::test_seeding_did_not_mutate_productions_
forgejo_database` compares **both** `gitea.db` and `gitea.db-wal` across a
window of several minutes, during which this suite's own availability poller
adds ~180 requests. It therefore goes red against a perfectly correct seeder,
at random. It passed in Task 12 by landing in a quiet minute; the Tier B
fixture's copy of the same comparison failed on its second run, which is how
this was found.

The reasoning for excluding it is already written down one file away:
`tests/branch_harness.py::PROD_VOLATILE_SUFFIXES` excludes `-shm`, `.lock`,
`.pid` and `.log` because "production is live and writes them on its own
schedule". `-wal` belongs with them over a window this long. Finding N6's
measurement — that a read-only `VACUUM INTO` leaves `.db` and `-wal`
byte-identical — is about the *seed*, over a window of 0.05 s, and does not
license comparing `-wal` over six minutes.

**Not fixed.** The fix is one line, but this task could not re-run Tier A1 to
verify it without leaking another worktree, and shipping an unexecuted change
to a test is the failure mode this project keeps recording. Tier B's
equivalent test asserts `gitea.db` only, records both readings, and states the
measurement in its docstring.
