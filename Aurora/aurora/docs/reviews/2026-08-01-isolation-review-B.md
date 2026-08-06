# Review B — system view: does the ephemeral-stack isolation branch actually isolate?

Worktree `/home/supergoodname77/aurora-isolation-wt`, branch `isolation-wt`, vs `origin/main`.
Read-only review. Scope: the spec's shared-resource inventory as a claim to be tested,
interactions between P1/P2/P3/P4, unhappy paths, and duplication with what already existed.

**Headline.** Three of the four bodies of work do not compose. The podman runtime (P4) is
wired into Compose only; every other daemon call in `branch up` / `branch down` /
`branch access` still lands on the root docker daemon, so a podman branch cannot be seeded,
cannot be documented, and reports a clean teardown while still running. The P1 enumeration
gate is pointed at production's compose config rather than the branch's — which is the
spec's own M4 mutation — and is green while three unaccounted daemon-global keys sit on the
one service that exists only in a branch. P2 ships with no enforcement test of any kind,
which the spec explicitly pre-rejects ("`docker compose config` showing a `mem_limit`
proves nothing").

---

## 1. `branch down` verifies the teardown against the wrong daemon — a podman branch is reported clean while still running

`aurora-cli/aurora_cli/branch.py:1798-1803` — **introduced by this branch**

`branch_down` builds `env` (carrying the runtime's `DOCKER_HOST`) and threads it through
every *before* query and every destructive call. The four *after* queries drop it:

```python
containers_after = _labelled(runner, "container", project)          # 1798 — no env
volumes_after = sorted(
    set(_labelled(runner, "volume", project))                       # 1800 — no env
    | set(_branch_named_volumes(runner, project))                   # 1801 — no env
)
networks_after = _labelled(runner, "network", project)              # 1803 — no env
```

`CommandRunner.run(env=None)` passes `env=None` to `subprocess.run`, i.e. inherits
`os.environ`, and neither `branch_up` nor `branch_down` ever puts `DOCKER_HOST` into
`os.environ` (only `branch_shell` does, at line 2316). So on `--runtime podman` the residue
check asks the **root docker daemon** whether the branch's objects are gone. They were never
there, so:

* the `RESIDUE:` notes never fire, whatever survived;
* `containers_removed` / `volumes_removed` / `networks_removed` are computed as
  `podman_before - docker_after`, i.e. they claim everything was removed unconditionally.

This is the exact failure `_docker_out`'s own docstring at branch.py:1583-1589 warns about,
word for word: *"a query that reached the ROOT daemon while the teardown it feeds reached
podman would enumerate production's objects and report a branch as clean."* The docstring
was written; the call sites were not updated.

It fails in the other direction too: `env=None` inherits an *unstripped* environment, so an
exported `DOCKER_HOST` from a podman session makes a **docker** branch's residue check land
on podman.

**Fix** — pass `env` at all four sites:

```python
containers_after = _labelled(runner, "container", project, env)
volumes_after = sorted(
    set(_labelled(runner, "volume", project, env))
    | set(_branch_named_volumes(runner, project, env))
)
networks_after = _labelled(runner, "network", project, env)
```

Then make it un-regressable: give `_docker_out` a required keyword-only `env` (no default)
so a caller physically cannot omit it. LOC delta: **+4 / −4**, plus ~6 lines to make `env`
required across `_labelled` / `_branch_named_volumes` / `live_branch_projects`.

---

## 2. Seeding always talks to the root docker daemon, so a seeded podman branch cannot be built — and it plants volumes on production's daemon

`aurora-cli/aurora_cli/seed.py:999-1041` (`_docker`), reached from `branch.py:1541-1545`
(`_seed`) and `branch.py:1443-1447` (`restore_postgres`) — **introduced by this branch** (the
`seed` module is pre-existing; P4 made it wrong).

`seed._docker` is `subprocess.run([DOCKER, *args], ...)` with no `env=` parameter at all —
there is no seam through which a runtime could be supplied. Consequences on
`branch up --runtime podman` without `--no-seed`:

* `seed.seed_agent_volume(dev, src_project, paths.project)` runs `docker volume create` and
  `docker run` on the **root daemon**, creating `br-<name>_…` volumes carrying the branch's
  compose labels *inside production's daemon*, and filling them with production's agent
  homes. Compose on podman then creates its own empty volumes, so the agent homes are silently
  unseeded — precisely the "my login does not work in the branch" symptom `_seed`'s docstring
  says is fatal-by-design to avoid.
* `seed.postgres_container(paths.project, ...)` runs `docker ps -a --filter
  label=…project=br-<name>` on the root daemon, finds zero containers, and raises
  `SeedError("expected exactly one container … found []")`. `branch up` then dies as
  `BranchUpFailed` **after** the stack is up on podman.

So a seeded `--runtime podman` branch cannot complete today, and it leaves labelled volumes
behind on production's daemon that `branch down --runtime podman` will not sweep (it sweeps
the podman daemon). Combined with finding 1, the leak is invisible in the report.

The spec's P4 acceptance — *"A full `branch up` on podman that passes the existing branch
acceptance suite unmodified"* (§5) — is **not met, and cannot be met by this code**. Nothing
in `tests/test_podman_runtime.py` runs `branch_up`; see finding 15.

**Fix** — give `seed` the same runtime seam Compose got. Minimal version: add a module-level
`_ENV: Mapping[str,str] | None = None` set by a context manager, or (better, and consistent
with the rest of the package) thread an `env: Mapping[str,str] | None = None` parameter
through `_docker` and every public entry point `branch._seed` calls
(`seed_agent_volume`, `postgres_container`, `container_credentials`, `restore_postgres`,
`volume_exists`, `volume_labels`, `create_labelled_volume`, `_assert_container_labelled_branch`),
then pass `resolved_runtime.environ(stripped_environ())` from `_seed` for everything that
addresses the *branch*, and the docker env for `dump_postgres` /
`production_postgres_container`, which address *production* and must stay on the root daemon.
The dump/restore asymmetry is the real design content here and is worth a two-line comment.
LOC delta: **≈ +45 / −25**. Until it exists, `branch_up` should refuse
`--runtime podman` without `--no-seed` rather than fail halfway (a 6-line guard among the
refusals at branch.py:1286).

---

## 3. The P1 enumeration gate is pointed at production's config, not the branch's — the spec's own M4 mutation, shipped green

`tests/test_branch_overlay.py:392` (`test_no_daemon_global_key_escapes_unaccounted(config)`),
`tests/conftest.py:compose_config` — **introduced by this branch**

The `config` fixture is `docker compose config` over **`compose.yml` only**. The gate
therefore never sees the branch's real resolved configuration, and in particular never sees
the `tailscale` sidecar — the one service that exists *only* in a branch, holds the branch's
tailnet identity, and carries `/dev/net/tun` and `NET_ADMIN`/`NET_RAW`.

Measured on the host, same code, both configs:

```
gate on BASE (what the suite runs):        {}
gate on OVERLAID (the branch's real cfg):  {'tailscale': ('cap_add', 'devices', 'hostname')}
```

Spec §2 lists M4 as *"point the gate at production's config instead of the branch's → red
(wrong-identity conformance)"*. The shipped gate **is** that mutant, and it is green. The
module's own `overlaid_config()` helper — used by four other tests in the same file — is the
correct input and is right there.

**Fix** — run the gate over `overlaid_config()`, and add the three sidecar exemptions the
overlay's author already has reasons for:

```python
def test_no_daemon_global_key_escapes_unaccounted():
    config = overlaid_config()
    ...
```

```python
("tailscale", "devices"): (
    "/dev/net/tun is a shared host device by necessity: kernel-mode tailscaled "
    "needs it and it is read-write for every container that maps it. Sharing a "
    "tun clone device grants no access to another namespace's interfaces."
),
("tailscale", "cap_add"): (
    "NET_ADMIN/NET_RAW apply inside the sidecar's own network namespace, which "
    "the branch owns — the same reason caddy's entry gives."
),
("tailscale", "hostname"): (
    "${TS_HOSTNAME}, derived per branch by envfile.branch_hostname; it is the "
    "one hostname in the stack that is guaranteed NOT to collide."
),
```

LOC delta: **+16 / −2**. Keep the base-config run as a second, cheaper assertion if you want
both, but the branch's config is the one that decides.

---

## 4. The daemon-global inventory omits the two keys P4's own analysis names as the only escapes — and one exemption in the file proves it

`aurora-cli/aurora_cli/overlay.py:76-102` (`DAEMON_GLOBAL_KEYS`), `overlay.py:~158`
(`("hermes", "group_add")`) — **introduced by this branch**

`GLOBAL_EXEMPTIONS` contains `("hermes", "group_add")` with a paragraph of reasoning.
`group_add` is **not in `DAEMON_GLOBAL_KEYS`**, so `unguarded_globals` never consults that
entry. It is dead code, and its deadness is direct evidence that the key is ungated.

I fabricated four plausible new service declarations and ran `overlay.unguarded_globals`
against them on the host:

```
{"metrics":  {"pid": "host", "volumes": [bind /proc]}}      -> ('pid', 'volumes')   caught
{"dns":      {"userns_mode": "host", "dns": [...]}}         -> ('userns_mode',)     caught
{"buildkit": {"security_opt": ["label=disable"],
              "group_add": ["docker"]}}                     -> {}                   NOT CAUGHT
{"sidecar2": {"volumes_from": ["aurora-forgejo"],
              "extra_hosts": [...]}}                        -> {}                   NOT CAUGHT
{"runner":   {"cgroup_parent": "/system.slice",
              "sysctls": {...}, "uts": "host"}}             -> {}                   NOT CAUGHT
```

`security_opt` and `group_add` are not incidental omissions. `runtime.py:20-45` — this
branch's own P4 module — states, from measurement, that *"Only `--security-opt
label=disable` **and** `--group-add keep-groups` together let it through"* for reaching
production's docker socket from a rootless container. The two keys that the branch itself
identifies as the entire escape route are the two the gate does not check.

`cgroup_parent` is worse than untidy in combination with P2: it moves a service out of the
project's cgroup subtree and can therefore defeat the ceilings that phase just added.
`volumes_from` names a *container* by definition — it cannot be project-scoped.

So the spec's central claim — *"this class is closed"* (§2) — is **false as shipped**.

**Fix** — extend the inventory and teach `reaches_outside` the two that need conditions:

```python
    "security_opt": "label=disable / seccomp=unconfined removes the confinement that is the isolation",
    "group_add": "a host GID inside the container is a host GID, whatever the project label says",
    "volumes_from": "names a CONTAINER, which no project namespaces",
    "cgroup_parent": "a cgroup path outside the project subtree escapes the branch's ceilings",
    "sysctls": "namespaced sysctls are per-netns, but the non-namespaced ones are the host's",
    "uts": "`host` shares the host UTS namespace",
```

and in `reaches_outside`:

```python
    if key == "uts":
        return str(value) == "host"
    if key in ("pid", "ipc"):
        return str(value) == "host"       # `pid: container:x` and `service:x` differ; be explicit
```

(`pid`/`ipc` currently return `True` for *any* value, including the harmless `pid: private`;
that is over-strict rather than unsafe, but it makes the inventory's semantics inconsistent
key to key.) LOC delta: **+14 / −0**, plus one added exemption for `("hermes","group_add")`
becoming live — the reason text already exists.

---

## 5. P2 ships with zero enforcement evidence; the spec pre-rejects the only test that exists

`tests/test_branch_overlay.py:558-660`, `branch-limits.yaml` — **introduced by this branch**

Spec §3 acceptance, verbatim: *"Empirical, not declarative. A container is driven past its
ceiling … and must be OOM killed while production is measured unchanged throughout.
`docker compose config` showing a `mem_limit` proves nothing — cgroup enforcement is the
claim."*

What shipped: `test_every_branch_service_gets_a_ceiling` parses the **rendered overlay text**
and asserts `mem_limit` is present per service. That is strictly less than `docker compose
config`, which the spec names as insufficient. Grepping the whole suite for `stress`,
`OOMKilled`, `137`, `memory.max` or `HostConfig.Memory` returns nothing outside a comment.
M5 (drop `mem_limit` → OOM test goes green → red) and M6 (ceiling above host RAM → red) are
**not implemented**; only M7 (`--limits none` emits nothing) is.

Related: the ceilings and the pre-existing resource guard were designed independently and now
contradict each other. `branch.py:155 MEM_PER_BRANCH_BYTES = 1300 MiB` is the guard's estimate
of a branch's cost — and it is referenced **only inside a message string** (`branch.py:331`),
never in a computation. Meanwhile the `measured` profile's ceilings sum to ~15.6 GB of
permitted memory on a 15.5 GiB host (verified by resolving the branch config: 11 × 1 GiB +
2560m + 1536m + sidecar). Nothing relates the two numbers, and nothing implements M6.

**Fix**, in decreasing value:

1. One live test, gated on an explicit opt-in the way `test_podman_runtime` gates its tier,
   that adds a throwaway `mem_limit: 64m` service to a `br-` project, allocates past it, and
   asserts `docker inspect --format '{{.State.OOMKilled}}'` is `true` — with production's
   container list fingerprinted before and after. ~60 LOC.
2. A cheap non-live gate that *is* discriminating: bring nothing up, but assert the resolved
   branch config's `mem_limit` values are what `branch-limits.yaml` says **and** that
   `sum(mem_limit) <= MemTotal` is either true or explicitly recorded as a decision. That is
   M6, and it is ~15 LOC.
3. Delete `MEM_PER_BRANCH_BYTES` or use it: `check_resources` should require
   `MemAvailable >= MEM_FLOOR_BYTES + MEM_PER_BRANCH_BYTES` rather than name the constant in
   prose. ~4 LOC.

---

## 6. Every document-producing path is runtime-blind: a podman branch's access document lists no containers, and `INDEX.md` erases it

`aurora-cli/aurora_cli/branch.py:2234` (`refresh_branch_docs`), `:2101`/`:2119` (`branch_state`),
`:2047` (`branch_ls`), `:2204` (`write_index`) — **introduced by this branch**

`compose_ps` gained an `env` parameter (branch.py:1942-1947) and `branch_ls`/`_summary_for`
pass it. `refresh_branch_docs` does not:

```python
rows = compose_ps(result.paths.project, runner=runner)   # branch.py:2234 — no env
```

Both `_cmd_branch_up` (`__main__.py:88`) and `_tool_branch_up` (`mcp.py:260`) call this
immediately after a successful `branch_up`. So a `--runtime podman` branch's
`BRANCH-ACCESS.md` — the string `branch_access`'s own docstring calls *"the feature"* — is
written with **zero container rows**, and it is written *after* `up` succeeded, so nothing
signals that the list is empty for a reason.

`branch_state` compounds it: it re-derives devs, exclusions and hook status from the
worktree but never reads `.aurora-runtime`, which is sitting in that same worktree. So
`result.runtime` falls back to `DEFAULT_RUNTIME` and every regenerated document asserts the
branch is on docker. `write_index` calls `branch_ls(runner)` with no runtime, so **any**
`branch up`/`branch down`/`branch ls` on docker rewrites `.worktrees/INDEX.md` from the
docker daemon and deletes every podman branch from the index.

**Fix**:

```python
# branch_state
recorded = runtimes.recorded_runtime(paths.worktree)
result.runtime = recorded or runtimes.DEFAULT_RUNTIME
env = runtimes.for_name(result.runtime, check_socket=False).environ(stripped_environ())
rows = compose_ps(paths.project, runner=runner, env=env)
```

and in `refresh_branch_docs`, derive `env` from `result.runtime` the same way. For
`write_index`, either union both runtimes (give `branch_ls` a per-runtime runner as its own
docstring suggests) or, cheaper and honest, have `render_index` state which daemon it was
generated from. LOC delta: **+12 / −3** for the first two; the index question is a design
call, ~25 LOC either way.

Note the same class in `branch_down_all` (branch.py:1874) and `_tool_branch_down(all=true)`:
both enumerate one daemon, so `aurora branch down --all` — the "clean the host" command —
silently leaves every podman branch running, and over MCP there is no `runtime` argument at
all to correct it with. `branch_ls`'s docstring admits the omission; `branch_down_all`'s
does not, and it is the one where the omission costs memory.

---

## 7. P3 rotates the credential *after* `dev-admin` has already reconciled with production's token — and its docstring says otherwise

`aurora-cli/aurora_cli/branch.py:1214-1237` (`scope_forgejo_credential`), sequenced at
`branch.py:1452-1486` — **introduced by this branch**

The docstring claims:

> Before `reconcile` because `reconcile` is the first thing that USES
> `FORGEJO_ADMIN_TOKEN`, and it reads it out of the branch `.env` at
> `docker compose run` time.

That is false. `dev-admin` is a long-running compose **service** with
`command: ["reconcile"]`, `restart: "no"`, no `profiles:` (verified against the resolved
config). `up.up_everything(build=build)` at branch.py:1452 starts the whole stack, so
`dev-admin` runs `reconcile` — with production's inherited `FORGEJO_ADMIN_TOKEN` baked into
its container environment — several steps *before* `scope_forgejo_credential()` is called at
branch.py:1480. The explicit `up.reconcile()` at branch.py:1482 is the *second* reconcile,
not the first.

Two consequences:

* the branch's first reconcile authenticates with production's credential, which is exactly
  what P3 exists to prevent. It happens to point at the branch's own `FORGEJO_URL`, so it is
  not a write to production — but the property being claimed is about the *credential*, not
  the URL.
* between branch.py:1452 and the second `up` at branch.py:1486, production's live admin
  token is readable from the branch's `dev-admin` container config (`docker inspect`). The
  second `up -d` does recreate it (the resolved env changed, so the config hash changed), so
  the exposure is a window rather than permanent — but if `up` fails anywhere between those
  two lines, `BranchUpFailed` deliberately tears nothing down and the window becomes
  indefinite, on a half-built branch a human is being told to go and debug.

**Fix** — the ordering constraint is real but the placement is wrong. Bring the stack up
*without* the token consumer, rotate, then converge:

```python
up.up_everything(build=build, exclude=(RECONCILE_SERVICE,))   # or: up specific services
up.await_tailnet()
up.await_https()
...
result.token_rotation = up.scope_forgejo_credential()
up.up_everything(build=False)     # dev-admin starts here, with the branch's own token
```

Compose has no `--exclude`, so the honest spelling is `up -d --no-deps <every service except
dev-admin>` derived from the resolved config, or `--scale dev-admin=0` on the first `up`.
Either way, delete the false sentence from the docstring — it is the sentence that stopped
anyone checking. LOC delta: **+15 / −8**.

---

## 8. P3 and P4 do not compose, and the branch knows it — in an error string rather than a gate

`aurora-cli/aurora_cli/forgejo_token.py:530-543` — **introduced by this branch**

`purge_production_credentials` opens the branch's `forgejo/gitea/gitea.db` **read-write from
the host**. Under rootless podman the Forgejo container's uid maps into the subuid range, so
the bind-mounted database becomes unwritable by uid 1000. The code contains a prepared
failure hint saying exactly that:

> Under ROOTLESS podman (spec P4) container uid 1000 maps into the subuid range instead, and
> this purge needs `--userns=keep-id` to stay possible. That is a known cost of P4, recorded
> here rather than discovered later.

Nothing implements `--userns=keep-id`, nothing refuses the combination, and P4 shipped
anyway. "Recorded here rather than discovered later" is the shape criterion 3 is about: a
paragraph defending a combination that is known not to work. Combined with finding 2 (the
seed dies first), `--runtime podman` + seeding is a guaranteed `BranchUpFailed` on two
independent counts.

**Fix** — one of: (a) implement `userns_mode: keep-id` on the podman path for `forgejo` (it
is a `!override`-able service key and belongs in the generated overlay, gated on the
runtime); or (b) refuse `--runtime podman` with seeding among `branch_up`'s pre-worktree
refusals, naming both blockers, until (a) lands. (b) is 8 LOC and honest; (a) is the real
fix and needs the overlay renderer to learn about the runtime, ~30 LOC.

---

## 9. The MCP `rebuild` tool runs production's rebuild with the ambient environment

`aurora-cli/aurora_cli/mcp.py:411-414`, `ops/rebuild.sh` — **introduced by this branch**

```python
completed = subprocess.run(
    _rebuild_argv(check, services),
    cwd=root, capture_output=True, text=True,
)     # no env= : inherits os.environ
```

`branch.stripped_environ()` exists precisely because an ambient `COMPOSE_PROJECT_NAME`,
`COMPOSE_PROFILES`, `COMPOSE_FILE` or `DOCKER_HOST` silently redirects a Compose command
(branch.py:105-121, and `DOCKER_HOST` was added to that tuple *by this branch*). The one
command in the repository that is pointed at **production on purpose** does not use it, and
`ops/rebuild.sh` sets `COMPOSE_PROFILES='*'` only for its `config` call, never for
`docker compose up -d --build`.

Concretely: an operator or agent with `DOCKER_HOST=unix:///run/user/1000/podman/podman.sock`
exported — which is exactly what a podman branch session encourages — invokes the `rebuild`
tool and gets: every image reported `NEVER-BUILT` (they are not in podman's store), a full
build into podman's store, `docker compose up -d` creating a **second copy of production's
stack** on the rootless daemon, and a transcript that says it deployed. Production keeps
serving the stale images the tool was written to catch. An ambient `COMPOSE_PROJECT_NAME`
produces the same class of outcome under a different project label.

**Fix** — in `mcp.py`:

```python
completed = subprocess.run(
    _rebuild_argv(check, services),
    cwd=root, capture_output=True, text=True,
    env=branch.stripped_environ(),
)
```

and in `ops/rebuild.sh`, unset them at the top so a human running the script directly gets
the same protection:

```sh
unset DOCKER_HOST COMPOSE_PROJECT_NAME COMPOSE_PROFILES COMPOSE_FILE
```

The script already claims (in a comment) that the only verbs it issues are safe; that claim
is about *verbs* and says nothing about *which daemon*. LOC delta: **+3 / −1**.

---

## 10. A tailnet key is minted before two refusals that can still abort, and nothing deletes it

`aurora-cli/aurora_cli/branch.py:1337-1346` — **introduced by this branch**

Order in `branch_up`: `assert_env_is_unambiguous` → `resolve_devs` → **mint** →
`exclusions.validate_excludable` → `check_resources` → `_add_worktree`.

The comment says *"Minting reaches the network, so it happens here, among the refusals,
BEFORE the worktree exists — a branch that cannot get a key leaves nothing on the host."*
True about the host, false about the tailnet: `--without <typo>` or a failed resource guard
aborts *after* a tagged, preauthorized key has been created on the tailnet, and
`tailnet.delete_key` is deliberately not wired to any failure path (its docstring only
declines to wire it into `branch down`, which is a different and defensible decision). The
key lives `KEY_EXPIRY_SECONDS = 1800`.

**Fix** — mint last among the refusals, since it is the only one with an external side
effect, and wrap the remaining pre-worktree steps so a failure deletes it:

```python
resolved_devs = resolve_devs(...)
if without:
    exclusions.validate_excludable(without)
excluded = tuple(sorted(exclusions.closure(without))) if without else ()
result.resources = check_resources(disk_path=production_root, force=force)
...
authkey = resolve_branch_authkey(paths.name, environ=environ, notes=result.notes)
```

That alone removes the two reachable leaks and costs **+4 / −6** (pure reordering).
Wiring `delete_key` into the `BranchUpFailed` path for a *minted* key is a further ~10 LOC
and worth it only if you also accept that a spent key is harmless to delete.

Also, a readability nit in the same block: `exclusions.closure(without)` is computed at
branch.py:1341 **before** `validate_excludable(without)` at branch.py:1343. It is harmless
today — `closure` keeps unknown names rather than raising, and the result is discarded when
`validate_excludable` refuses — but computing the closure of an unvalidated list and then
validating it reads as accidental. Swap the two lines: **+1 / −1**.

---

## 11. `--limits` mutates a *tracked* file inside the worktree, reinventing the untracked-overlay seam that already exists

`aurora-cli/aurora_cli/branch.py:1402-1408`, `overlay.sync_overlay` — **introduced by this branch**

`compose.branch.yml` is committed and tracked. `branch up --limits none|tight` re-renders it
**into the branch worktree**, so:

* the worktree now has a modified tracked file. Verified locally: `git worktree remove`
  refuses with *"contains modified or untracked files, use --force to delete it"*, so
  `branch down` on any `--limits`-flavoured branch needs `--force` or leaks its worktree —
  the exact regression P4 was supposed to close, arriving through a third door.
* a developer working in that branch who runs `git commit -a` carries one branch's ceilings
  (possibly *no* ceilings) into a PR against the committed artefact, which
  `test_overlay_is_not_stale` will then fail for everyone.

This is duplication with an abstraction the package already has. `exclusions.write_exclusion_overlay`
writes `compose.exclude.yml`, which is **gitignored with a comment saying exactly why**
(".gitignore:36-40 — *which services a branch omits is a property of that branch, so a
committed one would apply one branch's exclusions to every branch*"), and it is already the
third entry in `branch.COMPOSE_FILES`. Per-branch ceilings are the same kind of fact and want
the same file.

**Fix** — render ceilings into `compose.exclude.yml`'s slot (or a fourth, similarly
gitignored `compose.limits.yml`) rather than rewriting the committed overlay, and leave
`compose.branch.yml` as the pure function of the repository its header claims it is. That
also fixes the reporting hole: `branch_state` cannot re-derive "this branch has no ceilings"
today, so the spec's promise that *"`none` is recorded in `BRANCH-ACCESS.md` … so an
unlimited branch is never invisible"* (§3) holds only for the copy `up` wrote; regenerate the
document with `aurora branch access` and the note is gone. Reading `mem_limit` back from a
per-branch overlay file makes it re-derivable in three lines. LOC delta: **≈ +35 / −12**.

Related, cheap: `.aurora-runtime` is not in `.gitignore`, so every branch worktree now
carries an untracked file. `BRANCH-ACCESS.md` already had this property, so `--force` was
often needed before — but the fix is one line and removes one more reason to reach for
`--force` habitually. **+2 / −0** in `.gitignore`.

---

## 12. Two spellings of `br-`, deliberately re-introduced

`aurora-cli/aurora_cli/guards.py:29` — **introduced by this branch**

```diff
-#: An alias, not a second literal: `identity` states it is defined once,
-#: there, and this module's callers reach it through this name.
-BRANCH_PROJECT_PREFIX = identity.BRANCH_PROJECT_PREFIX
+BRANCH_PROJECT_PREFIX = "br-"
```

`guards` still imports `identity` at module scope, so there is no cycle to break.
`seed.py:1108/1162/1183` read `identity.BRANCH_PROJECT_PREFIX` while `branch.py` reads
`guards.BRANCH_PROJECT_PREFIX`; the two literals now have to agree by hand, and they are the
values every destructive guard in the package is phrased against. Revert. **+3 / −1**.

## 13. `identity`'s subprocess caches were removed with nothing put in their place

`aurora-cli/aurora_cli/identity.py:163, 192, 218` — **introduced by this branch**

Three `functools.lru_cache` decorators were deleted from `production_root()` (a
`git worktree list --porcelain` subprocess), `declared_project()` (a file read), and
`_compose_declared_project()` (**a `docker compose config` subprocess**, the slowest single
operation in this repository). There are 42 call sites of these three across the CLI package,
and `branch_ls` / `branch_down_all` / `_summary_for` call `identity.branch_paths` — hence
`production_root` — once per branch in a loop.

If the caches were removed because they leak across tests that repoint the root (the usual
reason), say so and provide the seam: keep `lru_cache` and expose
`identity.reset_caches()` for a `conftest` autouse fixture. If they were removed by accident
during the `devspawn` deletion — the comments referenced the deleted broker's fork-per-connection
model — restore them. Either way the current state pays a subprocess per call for no stated
benefit. **+6 / −0** (restore + `reset_caches`).

---

## 14. The tests that should have caught findings 1, 2 and 6 assert over source text instead of behaviour

`aurora-cli/tests/test_runtime.py:150-156, 304-316, 351-355, 402-411` — **introduced by this branch**

Five assertions in the P4 test module read `inspect.getsource(...)` and assert on substrings
and `body.index(...)` ordering:

* `test_the_socket_path_comes_from_the_runtime_user_not_a_literal_uid` — `assert "1000" not in body`
* `test_nothing_outside_the_worktree_is_ever_relabelled` — asserts a verbatim source line and `body.count("chcon") == 1`
* `test_teardown_reclaims_before_it_removes_the_worktree` — `body.index("reclaim_worktree_ownership") < body.index(...)`
* `test_up_records_the_runtime_before_it_starts_any_container` — three `body.index()` comparisons

These are non-discriminating in the direction that matters. They redden on a rename and stay
green on a wrong argument — and in fact `branch_down` **is** the function two of them read,
and neither noticed that four calls inside it query the wrong daemon (finding 1). The module
already has a recording `CommandRunner` fake, which is the discriminating instrument: the
ordering claims are all expressible as assertions over `runner.invocations` from a driven
`branch_down` / `branch_up`, and those assertions would additionally pin the `env` of every
recorded invocation — which is the property this whole phase turns on.

**Fix** — replace the four source-text tests with one behavioural test:

```python
def test_every_daemon_query_in_a_podman_teardown_carries_the_podman_socket(...):
    runner = FakeRunner(...)
    branch.branch_down("probe", runner=runner)
    docker_calls = [i for i in runner.invocations if i.argv[0] in ("docker", "podman")]
    assert docker_calls
    for call in docker_calls:
        assert (call.env or {}).get("DOCKER_HOST") == expected_socket, call.argv
```

That single test fails today on finding 1 and would have failed on it the day it was written.
LOC delta: **+25 / −45**.

---

## 15. The P4 live tier is thinner than the spec's acceptance, and the one test that always runs is a documentation grep

`tests/test_podman_runtime.py` — **introduced by this branch**

* `test_the_podman_live_tier_is_opt_in_and_its_blocker_is_named` is the only unconditional
  test. It asserts that `docs/issues/2026-08-01-podman-branch-runtime.md` contains the strings
  `AURORA_PODMAN_LIVE`, `tests/test_podman_runtime.py`, `container_file_t`, `podman unshare`
  and `525286`. It is a grep over a markdown file. It tells you nothing about podman, and it
  does not make the gated tier "not inert" — it makes the tier's *absence* documented, which
  is a different and much smaller claim than the module docstring makes for it.
* `test_the_worktree_is_reclaimable_without_sudo` asserts
  `runtimes.reclaim_worktree_ownership.__module__ == "aurora_cli.runtime"` and then runs
  `podman unshare chown -R 0:0` **itself**. It never calls the function it names. That is the
  decoy pattern: the checker reimplements the logic it claims to pin, so deleting the
  function's body would leave the test green (only deleting the *name* reddens it).
* The live tier brings up **one service** (`agent-authz`) via `compose_argv` and never calls
  `branch_up`, never seeds, never starts the sidecar, never rotates a credential, never
  applies a ceiling. The spec's P4 acceptance — *"a full `branch up` on podman that passes the
  existing branch acceptance suite unmodified — same URLs, same 200s, same seeded Forgejo,
  same per-developer agent route"* — is untested and, per finding 2, currently impossible.

The module is honest about *why* it is thin (a root-owned `.worktrees` on this host), and
that is genuinely valuable institutional knowledge — keep it, compressed. But the spec's §5
acceptance section should be amended to say what was actually proved (which daemon a command
reaches; that `:z`-equivalent relabelling is necessary and sufficient; that a subuid-owned
tree is reclaimable) and what was not. As written, §5 asserts something that did not happen.

**Fix** — (a) make `test_the_worktree_is_reclaimable_without_sudo` call
`runtimes.reclaim_worktree_ownership(branch_worktree, runner=branch.CommandRunner())` instead
of shelling out itself (**+2 / −3**); (b) amend spec §5 acceptance to the measured claims
(**+8 / −4** in the doc).

---

## 16. `test_build_conformance` pins the rebuild script against a copy of its own rule

`tests/test_build_conformance.py:160-225` — **introduced by this branch**

`test_the_rebuild_script_sees_the_same_services_and_reaches_the_same_verdict` compares
`ops/rebuild.sh --check`'s per-service verdict against a Python recomputation. The docstring
defends this as *"two independent derivations … Neither side reads the other."* They do not
read each other, but they are not independent: both compute
`docker image inspect .Created  <  git log -1 --format=%cI -- <context>` over the same two
sources. A systematically wrong *rule* — comparing committer date rather than author date, or
missing a build input that lives outside the context directory (`compose.yml` build args, the
base image, a shared vendored directory) — is identical on both sides and invisible here. The
test detects a typo in the bash, which is worth something, but it is not the "second
implementation, checked" the docstring claims.

The SET half of the same test *is* genuinely independent and worth keeping.

Also worth stating plainly: this file's own docstring says *"THIS FILE IS EXPECTED TO BE RED
when production is behind the checkout."* A gate that is expected to be red is a gate people
learn to ignore, and it is now the file that also carries the SET assertion, which is not
expected to be red. Split them: the staleness *report* belongs in `ops/rebuild.sh --check`
(where it already is) and in a `pytest.warns`/`record_property` reporting test; the
conformance assertions belong in a file that is green when the repository is correct.
LOC delta: **≈ +10 / −10** (a `@pytest.mark.xfail(strict=False)` on the staleness test with
the reason spelled out is the minimum honest form).

---

## 17. Smaller, still real

* **`overlay.unguarded_globals` can only be satisfied by an exemption for 10 of its 13 keys.**
  `overlay_resets` (overlay.py:387-412) reads only `RESET_KEYS + CONDITIONAL_RESET_KEYS`, so
  a service whose `privileged`/`cap_add`/`hostname` a future overlay legitimately resets
  cannot be recognised as fixed — the only way to green is to add an exemption, which dilutes
  the exemption list from "decisions we made" to "things we could not express". Either teach
  `overlay_resets` the full key set (**+4 / −2**) or say in `unguarded_globals`' docstring
  that exemption is the only route for these keys. Currently the docstring says "reset in the
  overlay, or … exemption", which is not true for most of the inventory.

* **Spec §6 still lists P6 as "specced, not built (blocked on you)"** while
  `aurora_cli/tailnet.py` (445 lines) ships it and `branch_up` calls it on every run. The
  spec table is now false about the state of the system it describes; §6 should move P6 into a
  delivered section and record the ACL caveat `tailnet.py:80-92` raises (a tagged node's
  reachability could not be verified from this host).

* **`tests/test_branch_credentials.py:105` is a tautology.**
  `assert LIVE_BRANCH_VAR in HOW` where `HOW` is an f-string built from `LIVE_BRANCH_VAR`.
  It cannot fail. The `in __doc__` half of the same test is a real (weak) check. Delete the
  first assertion (**+0 / −1**). The rest of that module is the best-constructed acceptance
  test on the branch — `rejected()` being `status == 401` rather than `!= 200`, and the
  "branch token still works on the branch" control, are exactly right.

* **`forgejo_token.FORGEJO_DB_RELPATH` hardcodes SQLite.** If Forgejo is ever moved to
  Postgres, `purge_production_credentials` raises "the branch's Forgejo database is not at
  …" and P3 silently stops being possible via a message that reads like a seeding bug. One
  sentence in the constant's comment naming the assumption is enough (**+2 / −0**).

* **`overlay.RESET_VALUES` / `_reset_lines` emit YAML by string concatenation** while
  `load_overlay` parses it back with a custom loader that exists to preserve the very tags the
  strings hand-write. Generating text and then parsing it with a bespoke loader to check it is
  two mechanisms where one would do; a `Tagged`-aware *dumper* would let the renderer build a
  document and dump it, and would delete `_reset_lines`, `_limit_lines`, `_GENERATED_MARKER`
  and the manual `caddy:` block assembly (overlay.py:592-628). Not urgent, but it is the
  reason the module carries a comment warning that "two `caddy:` keys in one mapping is
  last-wins in YAML" — a hazard that only exists because the output is built as strings.
  LOC delta: **≈ −60** net, but it touches the byte-for-byte staleness test, so it is a
  separate change.

---

## What I checked and found genuinely fine

Not padding the list: `guards.assert_branch_project` / `assert_not_production_path` coverage
of the new destructive paths (`relabel_worktree`, `reclaim_worktree_ownership`,
`branch_rebuild`) is correct and consistent; `teardown_runtime` refusing rather than guessing
when flag and record disagree is the right call and its error message says why;
`mcp._safe_service_names` using `fullmatch` plus a `--` separator is correct defence for a
value that becomes argv; `forgejo_token`'s `Opener` seam and the `MintedToken.__repr__` /
`AuthKey.__repr__` redactions are the right shape; `envfile._resolve` refusing a non-`str`
derivation (rather than `str()`-coercing an `AuthKey` into a `.env`) is a real bug class
closed properly.
