# Review A — `isolation-wt` vs `origin/main`

Adversarial review of the four merged bodies of work (P1 enumeration gate, P2 ceilings,
P3/P6 branch credentials, P4 podman runtime, rebuild job).

Prioritised, most valuable first. `NEW` = introduced by this branch, `PRE` = pre-existing.

---

## 1. `branch down` on podman queries the WRONG daemon for its "after" state, and reports a clean teardown over a live stack — NEW

`aurora-cli/aurora_cli/branch.py:1798-1803`

Every "before" query and every destructive call in `branch_down` was correctly threaded
with the runtime's `env` (lines 1710, 1712, 1715, 1750, 1752, 1760). The four "after"
queries were not:

```python
containers_after = _labelled(runner, "container", project)          # 1798  no env
volumes_after = sorted(
    set(_labelled(runner, "volume", project))                        # 1800  no env
    | set(_branch_named_volumes(runner, project))                    # 1801  no env
)
networks_after = _labelled(runner, "network", project)               # 1803  no env
```

With `env=None`, `CommandRunner.run` passes `env=None` to `subprocess.run`, so these
inherit the operator's ambient environment — i.e. **the root docker daemon** (and,
worse, whatever stale `DOCKER_HOST` the shell happened to export, the exact variable
this branch added to `STRIPPED_COMPOSE_VARS` to prevent).

Consequences on the podman path:

* `containers_after` is always `[]` (the root daemon has no `br-*` objects), so
  `containers_removed = containers_before - [] = everything`. The teardown claims to
  have removed every container **whether or not `compose down` succeeded**.
* The `RESIDUE:` note (line 1805-1809) queries the root daemon, so residue on the
  podman daemon is structurally invisible.

`_docker_out`'s own new docstring (line 1640-1646) states the failure verbatim — "a
query that reached the ROOT daemon while the teardown it feeds reached podman would
enumerate production's objects and report a branch as clean" — and then the code does
it. This also defeats the whole argument for `teardown_runtime` raising on a
record/flag mismatch: the mismatch it protects against is reintroduced four lines from
the return.

**Fix:** pass `env` to all four calls.

```python
containers_after = _labelled(runner, "container", project, env)
volumes_after = sorted(
    set(_labelled(runner, "volume", project, env))
    | set(_branch_named_volumes(runner, project, env))
)
networks_after = _labelled(runner, "network", project, env)
```

Add a unit test asserting that every `Invocation` recorded by `branch_down` on a podman
branch carries `DOCKER_HOST` — `test_every_compose_invocation_in_an_up_carries_the_runtime_socket`
(`aurora-cli/tests/test_runtime.py:219`) exists for `up` and has no `down` counterpart,
which is why this survived.

LOC delta: +4 / −4, plus ~15 for the test.

---

## 2. The `from_ref` leading-dash guard was deleted, and `from_ref` reaches `git worktree add` from the MCP wire — NEW

`aurora-cli/aurora_cli/branch.py:899-913` (the deletion site), `branch.py:927-928` (the sink),
`aurora-cli/aurora_cli/mcp.py:252` (the source)

This branch removed the guard with no replacement:

```python
-    if from_ref is not None and from_ref.startswith("-"):
-        # The only free-form string on the developer wire, and it lands in an
-        # OPTION slot of `git worktree add`. ...
-        raise BranchError(f"{from_ref!r} is not a ref: a ref may not begin with '-'.")
```

`from_ref` still lands in an option slot:

```python
argv = ["git", "-C", str(root), "worktree", "add", "-b", name, str(worktree), from_ref]
```

and it is still the one free-form string on the wire — `mcp._tool_branch_up` passes
`_optional_string(arguments, "from_ref")` straight through with no validation of any
kind (`_optional_string` only checks `isinstance(str)`). Nothing in the diff replaces
this check anywhere; `grep -rn 'not a ref'` over the worktree returns nothing.

`git worktree add` parses options positionally-agnostically, so a caller controls a git
option word on a command run in production's checkout. No shell is involved, so this is
hardening rather than injection — but it is hardening this branch removed silently, and
the commit message does not mention it.

**Fix:** restore the check verbatim at the top of `_add_worktree`. It is three lines and
it was already written.

LOC delta: +7.

---

## 3. `ops/rebuild.sh` never proves it is standing in production's checkout — NEW

`ops/rebuild.sh:44-47`

```bash
ROOT=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
cd "$ROOT"
```

The comment says this resolves "to the checkout this script is IN, not to `$PWD`",
because "a human under pressure runs this from wherever they happen to be standing".
But a branch worktree *contains this script*. Run from
`<production>/.worktrees/<name>/`, `ROOT` becomes the branch worktree and the script
then runs, against **the root docker daemon**:

```bash
docker compose up -d --build "${TARGET_NAMES[@]}"   # line 199
docker compose up -d                                # line 206
```

with the branch's `.env` but **without `-f compose.branch.yml`** — so no
`container_name: !reset`, no `ports: !reset`, no image reset. Compose will try to create
containers under production's `container_name` values, and `docker compose up -d`
recreates whatever it can claim. This is the 2026-07-29 shape (a compose verb resolving
the wrong project from the directory it was run in) reached through a path
`ops/docker-guard` deliberately does not block, because `up` is deliberately not in its
destructive set. The header even says so: "NO OVERRIDE IS NEEDED AND NONE MUST BE ADDED".

The MCP path is safe (it sets `cwd=identity.production_root()`), so this is entirely a
human-shell hazard — which is the case the header is written for.

**Fix:** after `cd "$ROOT"`, refuse a linked worktree and refuse anything that is not the
main checkout:

```bash
# A branch worktree contains this script too, and `docker compose up -d` there would
# create containers under PRODUCTION's container_name values (compose.branch.yml is
# not on the -f list here). Refuse rather than guess.
COMMON=$(git rev-parse --git-common-dir)
[ "$(cd "$COMMON/.." && pwd)" = "$ROOT" ] \
  || die "$ROOT is a linked git worktree, not production's checkout. ops/rebuild.sh rebuilds PRODUCTION; use \`aurora branch rebuild <name>\` for a branch."
```

LOC delta: +6.

---

## 4. P6 puts a tailnet-wide OAuth client secret in production's `.env`, which every branch `.env` inherits verbatim and no leak check covers — NEW

`aurora-cli/aurora_cli/tailnet.py:74-75`, `branch-env.yaml` (no entry),
`aurora-cli/aurora_cli/envfile.py:669`

Verified on the host: production's `.env` now carries `TS_OAUTH_CLIENT_ID` and
`TS_OAUTH_CLIENT_SECRET`. `render_branch_env` renders a branch `.env` **from production's**
(`base = parse_env(production_env_text())`) and overrides only what `branch-env.yaml`
lists. `branch-env.yaml` does not list either variable. So:

* every branch worktree now holds a credential that mints auth keys for the **whole
  tailnet** (scope `auth_keys oauth_keys`, per the module docstring) — not just for
  `tag:aurora-branch`, since the tag is chosen by whoever calls `POST /keys`;
* every branch container that binds the worktree — `hermes` binds the worktree root
  (see `GLOBAL_EXEMPTIONS[("hermes","volumes")]`) — can read it.

This is a strict regression against P3's own stated goal ("after step 4 the branch holds
no credential valid against production"): P3 removes one production credential and P6
adds a stronger one in the same merge.

Compounding it: `access_doc.secret_variables()` is driven **only** by `secret: true` in
`branch-env.yaml`, and today that set is exactly `{TS_AUTHKEY, FORGEJO_ADMIN_TOKEN}`. So
`_assert_no_secret_leaked` will not refuse an access document or an MCP payload
containing `TS_OAUTH_CLIENT_SECRET` — nor `POSTGRES_PASSWORD`, `OPENROUTER_API_KEY`,
`HERMES_DASHBOARD_SECRET`, `ARCADEDB_ROOT_PASSWORD`, `CADDY_BASIC_AUTH_HASH`,
`OPENCODE_GO_API_KEY` (those are `PRE`; the OAuth secret is `NEW`).

**Fix (minimum, for the variable this branch introduced):** add to `branch-env.yaml`

```yaml
  - name: TS_OAUTH_CLIENT_SECRET
    literal: ""
    fatal: true
    secret: true
    why: "P6. Mints tailnet auth keys for the WHOLE tailnet. `branch up` uses it on the HOST before the branch exists; nothing inside a branch needs it, and a branch worktree is bind-mounted into hermes. Blanked, not inherited."
  - name: TS_OAUTH_CLIENT_ID
    literal: ""
    fatal: true
    why: "Half a client cannot mint (tailnet.oauth_client refuses); blanked with its secret so a branch cannot mint at all."
```

`tailnet.oauth_client` already reads production's env directly rather than the branch's,
so blanking these in the branch `.env` does not break minting. Verify with
`tests/test_branch_env.py`'s existing both-directions check.

Separately, consider making `secret_variables()` a superset check against production's
`.env` rather than an opt-in list — but that is its own change.

LOC delta: +10 (manifest) and a test.

---

## 5. The MCP error path skips the VALUE leg of the secret check — NEW

`aurora-cli/aurora_cli/mcp.py:673-680`

```python
except Exception as exc:
    return _tool_payload(f"{type(exc).__name__}: {exc}", (), is_error=True)
```

`_tool_payload` runs `_assert_no_secret_in(json.dumps(payload), env_files)`. With
`env_files=()`, `_assert_no_secret_in` calls `access_doc._assert_no_secret_leaked(text, None)`,
which runs **only the NAME leg** and returns at `access_doc.py:204-205`. The VALUE leg —
"the one that matters ... it catches a key printed under some other label, or inside a
note" — is disabled on exactly the path where a secret is most likely to appear.

Reachable: `CommandRunner.run` with `check=True` builds its message as
`` f"`{' '.join(argv)}` failed with exit {rc} ...: {result.stderr.strip() or result.stdout.strip()}" ``.
Compose and `dev-admin reconcile` stderr can echo `.env`-derived values; that string is
wrapped by `BranchUpFailed` and lands here verbatim.

**Fix:** derive the candidate env files from the *arguments* rather than from a result
that no longer exists.

```python
def _candidate_env_files(arguments: Mapping[str, Any]) -> tuple[Path, ...]:
    """Every `.env` whose VALUES must not appear in an error text.

    Derived from the ARGUMENTS, not from a result: the error path is where a
    secret is most likely to appear and is the one path with no result to read.
    """
    files: list[Path] = []
    name = arguments.get("name")
    if isinstance(name, str) and name.strip():
        try:
            files.append(identity.branch_paths(name).env_file)
        except Exception:
            pass
    try:
        files.append(identity.production_root() / envfile.ENV_FILE_NAME)
    except Exception:
        pass
    return tuple(files)
```

and use it at the `except`: `_tool_payload(..., _candidate_env_files(arguments), is_error=True)`.
Pin it with a test that raises from a tool handler with a branch `.env` value in the
message and asserts the payload is refused.

LOC delta: +20 including the test.

---

## 6. P3 is skipped when only `dev-admin` is excluded, and the note it writes is false — NEW

`aurora-cli/aurora_cli/branch.py:1472-1480`

```python
elif RECONCILE_SERVICE in excluded or FORGEJO_SERVICE in excluded:
    result.notes.append(
        "FORGEJO ADMIN CREDENTIAL NOT ROTATED: this branch has no "
        f"Forgejo ({', '.join(excluded)} excluded). ..."
    )
```

`branch-services.yaml:77` gives `forgejo` an `also_exclude: [forgejo-mcp, dev-admin]`,
but the closure does not run the other way. `aurora branch up --without dev-admin`
therefore produces a branch that **has a Forgejo**, seeded byte-for-byte from
production's database, and P3 does not run. The branch keeps:

* production's live `FORGEJO_ADMIN_TOKEN` in its `.env`, and
* every one of production's `access_token` / `forgejo_auth_token` rows in a database
  file sitting in the worktree,

and the note tells the reader "this branch has no Forgejo", which is untrue.

The stated reason for the skip is that nothing in the branch *uses* the token — but P3's
own module docstring says the goal is that "production's token hashes are not sitting in
the branch's data at rest". Excluding the consumer does not change the data at rest.

**Fix:** condition only on the forge, and split the note:

```python
elif FORGEJO_SERVICE in excluded:
    result.notes.append(
        "FORGEJO ADMIN CREDENTIAL NOT ROTATED: this branch has no Forgejo "
        f"({', '.join(excluded)} excluded), so there is no forge to mint in "
        "and no seeded copy of production's credential rows."
    )
else:
    result.token_rotation = up.scope_forgejo_credential()
```

`rotate_admin_token` does not touch `dev-admin` — the mint runs `docker compose exec` in
the `forgejo` container — so this needs no other change.

LOC delta: +2 / −4.

---

## 7. `branch down --all` enumerates one daemon, so podman branches survive it silently — NEW

`aurora-cli/aurora_cli/branch.py:1871-1890`, `aurora-cli/aurora_cli/mcp.py:283`

```python
env = runtimes.for_name(
    runtimes.resolve_runtime(runtime), check_socket=False,
).environ(stripped_environ())
if projects is None:
    projects = live_branch_projects(runner, env)
```

`branch_ls` documents this omission for the *index*; `branch_down_all` inherits it for a
*destructive sweep* and does not. With no `--runtime` (the default, and the only thing
the MCP tool can produce — `_tool_branch_down` has no runtime parameter), the sweep asks
the root docker daemon, finds no podman branches, and reports having torn down
everything. Combined with finding 1, an operator has no surface that will tell them a
podman branch is still running and still costing memory.

**Fix (small, honest):** when `projects is None` and no runtime was requested, enumerate
**both** runtimes and dispatch per-project through the branch's own record, which
`branch_down` already consults:

```python
if projects is None:
    names: set[str] = set()
    for candidate in runtimes.RUNTIMES:
        if runtime is not None and candidate != runtime:
            continue
        env = runtimes.for_name(candidate, check_socket=False).environ(stripped_environ())
        try:
            names.update(live_branch_projects(runner, env))
        except Exception:
            continue          # a runtime that is not installed is not an error here
    projects = sorted(names)
```

`branch_down` then resolves each project's runtime from `.aurora-runtime`, so no
project is torn down against the wrong daemon. If the double-sweep is genuinely
incompatible with the `runner` test seam (the reason `branch_ls` gives), then at minimum
`branch_down_all` must append a NOTE naming the runtimes it did **not** ask — silence
here is the same lie as finding 1.

LOC delta: +12.

---

## 8. The podman live tier never calls the product functions it exists to pin (decoy) — NEW

`tests/test_podman_runtime.py:331-347` and `:262-291`

```python
def test_the_worktree_is_reclaimable_without_sudo(branch_worktree, brought_up):
    assert runtimes.reclaim_worktree_ownership.__module__ == "aurora_cli.runtime"
    proc = _run(["podman", "unshare", "chown", "-R", "0:0", str(branch_worktree)])
```

The first assertion is a tautology — any function defined in `aurora_cli/runtime.py` has
that `__module__`. The second **reimplements** `reclaim_worktree_ownership`'s body. The
product function is never invoked, so replacing its body with `return True` reddens
nothing. Same shape in `test_a_repo_relative_bind_needs_the_relabel_and_the_relabel_is_enough`,
which spells `chcon -R -t <type>` by hand rather than calling `runtimes.relabel_worktree`.

Net effect: of the three P4 functions that mutate the host (`relabel_worktree`,
`reclaim_worktree_ownership`, `record_runtime`), the live tier drives **none**. It proves
that podman behaves as measured; it proves nothing about this code.

The cause is real and worth naming: both functions call
`guards.assert_not_production_path`, which requires the path to be under
`<production>/.worktrees/`, and the fixture worktree is under `tmp_path` because
`.worktrees` is root-owned on this host (module docstring). So the guard makes the
product path untestable at the very tier written to test it — while `record_runtime`
was *exempted* from the same guard (`runtime.py:288-295`) specifically so the
`worktrees_root=` seam keeps working. That asymmetry is the defect.

**Fix:** give the two host-mutating functions the same seam `branch_up` already has.
Add an explicit opt-out parameter used only by the live tier and by
`branch_up(worktrees_root=...)`:

```python
def relabel_worktree(worktree, *, runner, force=False, guard=True) -> str | None:
    worktree = guards.assert_not_production_path(worktree) if guard else Path(worktree).resolve()
```

then in the test:

```python
runner = branch_mod.CommandRunner()
assert runtimes.reclaim_worktree_ownership(branch_worktree, runner=runner, guard=False)
assert runner.invocations[-1].argv[:2] == ("podman", "unshare")
owners = {p.stat().st_uid for p in branch_worktree.rglob("*")}
assert owners <= {os.getuid()}
```

and drop the `__module__` assertion. Do the same for the relabel test. Without this,
`--runtime podman` has never been exercised end-to-end by anything.

Secondary, same file, line 272: the SELinux probe writes and `rm -rf`s
`REPO_ROOT.parent / "br-podprobe-selinux-probe"` — a sibling of the repo root, i.e. in
the user's home. Use `tmp_path_factory`.

LOC delta: +8 in `runtime.py`, +15 in the test.

---

## 9. `test_build_conformance` calls a transliteration "two independent derivations" — NEW

`tests/test_build_conformance.py:177-225`

The docstring claims: "`ops/rebuild.sh` ... is a second implementation whether anyone
wanted one or not. ... Neither side reads the other." But the Python side is a
line-for-line transliteration of the shell side:

| `ops/rebuild.sh` | `test_build_conformance.py` / `conftest.py` |
|---|---|
| `docker image inspect "$image" --format '{{.Created}}'` | `_image_created` — identical |
| `git log -1 --format=%cI -- "$context"` | `_context_commit` — identical |
| `[ "$(date -d created)" -lt "$(date -d commit)" ]` | `_parse(created) < _parse(commit)` |
| `svc.get("image") or (project + "-" + name)` | `conftest.declared_image` — identical |

Two spellings of one algorithm agree by construction. They agree *wrongly* on every
interesting case:

* **an uncommitted working tree reads FRESH.** Both compare an image against the last
  *commit*. Edit `fjell/src/main.rs`, don't commit, and `--check` says "no deploy
  needed" — which is a confident wrong answer, the exact thing `_tool_rebuild`'s
  docstring says the tool exists to avoid.
* **a fully cache-hit rebuild reads STALE forever.** If the last commit touching the
  context only changed a `.dockerignore`d file, `docker build` reuses the image and its
  `.Created` does not move — so `ops/rebuild.sh:212` fires
  `die "still STALE after a build"` on a build that was correct and complete.

**Fix:** make one of the two sides measure something the other cannot fake. The cheapest
is to compare the image against the **tree**, not the commit clock:

```bash
# In ops/rebuild.sh, replace the timestamp comparison:
#   the source hash the image was built from, stamped as a label at build time.
#   A clock comparison cannot see an uncommitted edit and cannot see a cache hit.
want=$(git rev-parse "HEAD:${context#$ROOT/}" 2>/dev/null || git hash-object -t tree /dev/null)
have=$(docker image inspect "$image" --format '{{index .Config.Labels "aurora.source-tree"}}' 2>/dev/null || true)
```
with `labels: {aurora.source-tree: "${AURORA_SOURCE_TREE}"}` on each buildable service.
That is a larger change than a review note; at minimum, **record the two known holes in
the docstring** and drop the "two independent derivations" claim, and change line 212's
`die` to a warning that names the cache-hit case.

LOC delta: ~+25 for the tree-hash version, +6 for the honest-docstring version.

---

## 10. The P1 gate has an exemption for a key it does not enumerate, and never sees the one service the overlay adds — NEW

`aurora-cli/aurora_cli/overlay.py:81-96` and `:139-143`

`GLOBAL_EXEMPTIONS` carries `("hermes", "group_add")` with a written reason.
`group_add` is **not** in `DAEMON_GLOBAL_KEYS`, and `unguarded_globals` iterates
`DAEMON_GLOBAL_KEYS` only (line 212). So that exemption silences nothing and the key is
never checked — the gate's own "an unenumerated item is how the image-tag escape
happened" argument, one file over. `test_every_shipped_exemption_states_a_reason`
(`tests/test_branch_overlay.py:555`) checks only that reasons are non-empty, so it cannot
catch this.

Second hole: `unguarded_globals(config, ...)` runs over the **resolved base** config. The
`tailscale` sidecar is added *by* the overlay, so it is never in `config["services"]` and
is never gated — and it declares `devices: /dev/net/tun` and `cap_add: [NET_ADMIN, NET_RAW]`,
two keys the inventory itself calls daemon-global. `test_every_branch_service_gets_a_ceiling`
handles this exact asymmetry explicitly for `mem_limit` ("the sidecar by name"); the P1
gate does not.

**Fix (both, ~10 lines):**

```python
DAEMON_GLOBAL_KEYS = {
    ...,
    "group_add": "a supplementary group is a HOST gid, not a project-scoped one",
    "security_opt": "`label=disable` / `seccomp=unconfined` opt out of host confinement",
    "sysctls": "a namespaced sysctl is still tuned per-kernel, not per-project",
}
```

and add to `tests/test_branch_overlay.py`:

```python
def test_every_exemption_names_a_key_the_gate_actually_checks():
    """An exemption for an unenumerated key silences nothing and reads as if it does."""
    stray = sorted(k for k in overlay.GLOBAL_EXEMPTIONS if k[1] not in overlay.DAEMON_GLOBAL_KEYS)
    assert stray == [], f"exemptions for keys the gate never checks: {stray}"

def test_the_sidecar_the_overlay_adds_is_gated_too():
    """It is not in the base config, so the gate above never reaches it -- and it
    holds NET_ADMIN, NET_RAW and /dev/net/tun."""
    sidecar = overlay.load_overlay(overlay_text())["services"][overlay.SIDECAR_SERVICE]
    root = overlay.identity.package_root()
    loose = overlay.unguarded_globals({"services": {overlay.SIDECAR_SERVICE: sidecar}}, {}, root)
    assert loose == {}, loose
```
(the second will initially fail, which is the point — add
`(SIDECAR_SERVICE, "devices")` and `(SIDECAR_SERVICE, "cap_add")` exemptions with the
reasons already written in `compose.branch.yml`.)

LOC delta: +20.

---

## 11. `branch_shell` mutates the process environment before it can raise — NEW

`aurora-cli/aurora_cli/branch.py:2316-2321`

```python
os.environ.pop(runtimes.DOCKER_HOST_VAR, None)
if resolved_runtime.docker_host is not None:
    os.environ[runtimes.DOCKER_HOST_VAR] = resolved_runtime.docker_host

argv = shell_argv(name, service, command, runner=runner, env=env)
(exec_fn or os.execvp)(argv[0], argv)
```

The comment justifies the mutation for `execvp` — correct as far as it goes. But the
mutation happens **before** `shell_argv`, which raises `BranchError` when the branch has
no container or no such service. On that path the process keeps a `DOCKER_HOST` it was
never asked to set (or has lost one the operator exported), and every subsequent call in
the same process — the MCP server is long-lived, and `exec_fn` is a real injected seam,
not test-only — runs against the wrong daemon.

**Fix:** move the mutation to the last statement before the exec.

```python
argv = shell_argv(name, service, command, runner=runner, env=env)
# Last thing before the exec: `execvp` carries THIS process's environment, and
# `shell_argv` above can raise -- a failed lookup must not leave the variable behind.
os.environ.pop(runtimes.DOCKER_HOST_VAR, None)
if resolved_runtime.docker_host is not None:
    os.environ[runtimes.DOCKER_HOST_VAR] = resolved_runtime.docker_host
(exec_fn or os.execvp)(argv[0], argv)
```

LOC delta: +0 (a move).

---

## 12. Three `functools.lru_cache` decorators removed, one of them from a function that shells out — NEW

`aurora-cli/aurora_cli/identity.py:166`, `:195`, `:221`

The diff deletes the caches from `production_root()`, `declared_project()` and
`_compose_declared_project(root)`, along with the comments explaining them. The last one
runs `docker compose config` — a full compose resolution, the single most expensive
subprocess in this package — and is called via `production_project()`, which
`guards.assert_branch_project` calls on **every destructive operation** (`branch_down`
calls it three times per teardown, plus once per volume in the sweep loop at
`branch.py:1758-1763`).

`production_root()` walks git on every call and is called from
`assert_not_production_path`, `refuse_production_database`, `identity.production_env()`,
`branch_down`'s `git worktree remove` / `prune`, and more.

No commit in this branch explains the removal and nothing in the diff replaces it. If
the motive was test isolation (a cached `production_root` surviving a `monkeypatch`),
the fix is `cache_clear()` in a fixture, not deleting the cache.

**Fix:** restore all three decorators and their comments. If tests need it, add to
`aurora-cli/tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def _clear_identity_caches():
    for fn in (identity.production_root, identity.declared_project,
               identity._compose_declared_project):
        fn.cache_clear()
    yield
```

LOC delta: +6 restored, +6 fixture.

---

## 13. `guards.BRANCH_PROJECT_PREFIX` is now a second literal — NEW

`aurora-cli/aurora_cli/guards.py:29`

```python
-#: An alias, not a second literal: `identity` states it is defined once,
-#: there, and this module's callers reach it through this name.
-BRANCH_PROJECT_PREFIX = identity.BRANCH_PROJECT_PREFIX
+BRANCH_PROJECT_PREFIX = "br-"
```

`guards` already imports `identity` two lines above, so there is no circularity to work
around. This is exactly the "two spellings of one fact" drift the rest of the repository
argues against at length, and it sits in the module whose whole purpose is the branch
namespace. `branch.py:1885` slices project names with
`project[len(guards.BRANCH_PROJECT_PREFIX):]` while `identity.branch_paths` builds them
with `identity.BRANCH_PROJECT_PREFIX`; if the two diverge, that slice silently produces a
wrong branch name and `branch_down_all` tears down the wrong thing.

**Fix:** revert the three lines.

LOC delta: +3 / −1.

---

## 14. `BranchResult.authkey_source` and `BranchResult.token_rotation` are write-only — NEW

`aurora-cli/aurora_cli/branch.py:355-363`, set at `:1339` and `:1480`

Both fields carry long docstrings explaining what question they let a reader answer
("was this branch's node ephemeral?", "what the rotation did"). Neither is read by any
product code: `access_doc.py` has **no diff at all** in this branch, and
`__main__._cmd_branch_up`'s JSON payload adds only `"runtime": result.runtime`.
`RotationReport.summary()` — a method whose docstring is "Safe to put in a note or a
document" — is called nowhere outside tests. `grep -rn 'authkey_source\|token_rotation'`
returns only `branch.py` and `test_branch_up.py`.

So the questions the fields exist to answer are still unanswerable from any surface a
human or agent sees, and P6's own fallback path is only visible via the separate `notes`
append. Every function/field must justify its existence; these currently justify it to
the test suite only.

**Fix:** append them to `result.notes` at the point they are set, which is the one
channel that already reaches `BRANCH-ACCESS.md`:

```python
result.authkey_source = authkey.source
result.notes.append(f"tailnet auth key: {authkey.source}")
```
```python
result.token_rotation = up.scope_forgejo_credential()
result.notes.append(f"forgejo admin credential: {result.token_rotation.summary()}")
```

Both strings are already secret-free by construction (`AuthKey.source`, `RotationReport`
carry no values) and neither names a `secret: true` variable, so `access_doc`'s refusal
does not fire. Assert that in the test rather than assuming it.

LOC delta: +4, +6 test.

---

## 15. `TailnetError` and `OverlayError` escape `main()` as tracebacks — NEW

`aurora-cli/aurora_cli/__main__.py:410-423`

The `except` tuple gained `runtimes.RuntimeSelectionError` but not
`tailnet.TailnetError` or `overlay.OverlayError`. Two reachable paths:

* `resolve_branch_authkey` → `tailnet.oauth_client()` raises `TailnetError` on "half an
  OAuth client" (id set, secret unset). This runs **before** `branch_up`'s `try`, so it
  is not wrapped by `BranchUpFailed`. A typo in production's `.env` gives a Python
  traceback instead of the carefully written refusal message.
* `aurora branch overlay <name> --limits typo` → `branch_overlay` →
  `overlay.resolve_limits` raises `OverlayError`, never caught.

**Fix:**

```python
    except (
        identity.IdentityError,
        branch.BranchError,
        guards.GuardViolation,
        access_doc.AccessDocError,
        runtimes.RuntimeSelectionError,
        overlay.OverlayError,
        tailnet.TailnetError,
        forgejo_token.ForgejoTokenError,
    ) as exc:
```
(plus the two imports). `ForgejoTokenError` is included because
`branch_overlay`/`branch_rebuild` are not the only reachable callers and relying on
`branch_up`'s blanket `except Exception` to wrap it is incidental.

LOC delta: +5.

---

## 16. `--limits` is validated only after a worktree exists — NEW

`aurora-cli/aurora_cli/branch.py:1286-1287` vs `:1402-1403`

`--runtime` is resolved among the refusals, before anything is created, with a comment
saying exactly why: "an unknown runtime name ... must not be discovered after a worktree
exists." `--limits` is not: `overlay.sync_overlay(paths.worktree, limits=limits)` runs
after `git worktree add` and after the `.env` write, so `aurora branch up x --limits
tihgt` leaves a half-built branch behind for a typo. `test_an_unknown_profile_is_refused_and_names_the_real_ones`
tests `resolve_limits` in isolation and does not notice.

**Fix:** validate next to the runtime resolution.

```python
runtime_name = runtimes.resolve_runtime(runtime, environ=environ)
resolved_runtime = runtimes.for_name(runtime_name, environ=environ)
if limits is not None:
    overlay.resolve_limits(limits)      # refuse a typo before anything is created
```

LOC delta: +3.

---

## 17. `forgejo_token.rotate_admin_token` cites a test that does not exist — NEW

`aurora-cli/aurora_cli/forgejo_token.py:668-669`

> The order below is the load-bearing part and is asserted by
> `aurora-cli/tests/test_forgejo_token.py::test_the_mint_precedes_the_purge`

`grep -rn test_the_mint_precedes_the_purge` matches that docstring and nothing else. The
ordering *is* covered — by `test_the_rotation_mints_writes_then_purges` (line 203) and
`test_m10_purging_before_minting_fails_and_names_the_ordering` (line 221) — but a reader
who follows the citation finds nothing and has no way to know whether the test was
renamed or never written. In a 67-line module docstring that argues the ordering is
"the whole design", a dangling citation to the only thing that enforces it is the part
that matters.

**Fix:** name the two tests that exist.

LOC delta: +1 / −1.

---

## 18. Smaller items, listed rather than argued

* `aurora-cli/aurora_cli/forgejo_token.py:342-346` — `list_token_ids` keys on
  `token_last_eight` and `mint_admin_token:419` looks up `secret[-8:]`. Duplicate
  last-eight values silently overwrite (`out[...] = ...`), so a collision hands the purge
  the *wrong* id and it deletes the credential it just minted. Cheap fix: build
  `dict[str, list[int]]` and raise if the minted suffix maps to more than one id — the
  error message is already written for the `None` case. `NEW`. +6 LOC.
* `aurora-cli/aurora_cli/tailnet.py:389-403` — `delete_key` exists solely for tests and
  is exported in `__all__` with a paragraph explaining why it is not wired into
  `branch down`. It is dead product code; either wire it or move it into the test module.
  `NEW`. −20 LOC.
* `aurora-cli/aurora_cli/branch.py:212-228`, `:262` — `Invocation` records `dict(env)`, i.e. a
  full copy of `os.environ` per compose call, and the tests print invocations on failure.
  With `AURORA_TS_OAUTH_CLIENT_SECRET` or `AURORA_TS_AUTHKEY` exported, a red test prints
  them. Record only the keys this package sets/strips. `PRE` (aggravated by
  `DOCKER_HOST` joining `STRIPPED_COMPOSE_VARS`). +4 LOC.
* `aurora-cli/aurora_cli/overlay.py:168-173` — `host_bind_sources`'s `except OSError`
  around `Path.resolve()` is dead: non-strict `resolve()` does not raise for a missing
  path on any supported Python. Either drop it or use `strict=True` and mean it.
  `NEW`. −3 LOC.
* `aurora-cli/aurora_cli/runtime.py:322-331` — `selinux_enforcing` calls
  `runner.run(["getenforce"], check=False)`; `check=False` does not cover
  `FileNotFoundError` from `subprocess.run` when `getenforce` is absent, which is the
  normal state of a non-SELinux host. `relabel_worktree` would then crash rather than
  return its "not Enforcing" note. Wrap in `try/except OSError: return False`.
  `NEW`. +3 LOC.
* `ops/rebuild.sh:132-141` — `fingerprint()` declares `local ... context` and never uses
  it (twice, also in `staleness`), and `printf` the header row inside the function that
  is called twice. Cosmetic. `NEW`.
* `aurora-cli/aurora_cli/mcp.py:340` — a 200-column comment line in a file that is
  otherwise wrapped at 79. `NEW`.

---

## Things I checked and found genuinely sound

Stated only because they were in scope and it is worth knowing they were looked at:

* No secret reaches `argv` anywhere on the new paths. `mint_forgejo_token`
  (`branch.py:1172-1216`) keeps the token in stdout, uses `check=False`, and its failure
  message repeats stderr only — the reasoning in that docstring is correct and the code
  matches it. `urllib_opener` in both `forgejo_token` and `tailnet` is a header, not a
  subprocess, for the stated (and correct) reason that `CalledProcessError.cmd` retains
  argv.
* `MintedToken.__repr__` / `MintedKey.__repr__` / `AuthKey.__repr__` / `OAuthClient.__repr__`
  all redact, and all set `__str__ = __repr__` (the half people forget).
* The purge deletes what it claims and only that: `PURGE_PLAN` is two tables,
  `refuse_production_database` resolves both sides before comparing, and the
  `keep_token_ids` clause is parameterised. `test_the_purge_removes_every_production_credential_not_just_the_named_one`
  uses a **two-row** fixture, which is the version of that test that can fail.
* `mcp._safe_service_names` uses `fullmatch` with a leading-character class that excludes
  `-`, `_rebuild_argv` puts `--` before operands, and `ops/rebuild.sh` re-validates every
  name against the derived buildable set with `awk -v` (no shell interpolation). The
  rebuild tool cannot issue anything but `up`, and `test_the_rebuild_tool_can_only_ever_issue_up`
  enumerates it with a `len(seen) == 6` non-vacuity assertion.
* The P1 gate tests (`tests/test_branch_overlay.py:475-573`) are not vacuous: there is an
  explicit non-empty-inventory assertion, an explicit "something actually escapes"
  assertion, a positive control that fabricates an unguarded service, and a blank-reason
  control. The `/home` → `/var/home` resolution bug is pinned by its own test.
* The P2 ceiling tests avoid the counting decoy explicitly and derive arcadedb's floor
  from `-Xmx` in `compose.yml` rather than from a constant.
* `tests/test_branch_credentials.py` is gated but not vacuous: `rejected()` is `== 401`
  rather than `!= 200`, there is a discrimination test that always runs, and there is a
  positive control (`test_the_branch_token_still_works_on_the_BRANCHS_own_api`) without
  which the two 401s would pass against a dead forge.
