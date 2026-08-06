# Developer-facing ephemeral spawn: what was built

A developer inside their agent container can now create, list, inspect and
destroy their own ephemeral stacks — without a host shell and **without the
Docker socket**.

Design: `docs/superpowers/specs/2026-07-31-developer-ephemeral-spawn-design.md`.
Everything below is measured, on this host, on 2026-07-31.

---

## The shape of it

| File | Lines | Responsibility |
|---|---:|---|
| `aurora-cli/aurora_cli/devspawn.py` | 430 | Policy only: roster, namespace, ownership, quota, leases, reaper. Issues no command. |
| `aurora-cli/aurora_cli/mcp.py` | +325 | `Server` (tool table as a parameter), the developer tool table, `developer_server`. The admin table and the wire are unchanged. |
| `aurora-cli/aurora_cli/__main__.py` | +90 | `aurora mcp --as-developer`, `aurora dev-spawn ls|reap`. |
| `ops/aurora-spawn-broker` | 80 | One privileged `socat` listener per developer. |
| `ops/aurora-spawn-bridge.py` | 75 | stdio ↔ unix socket, run inside the developer's container. |
| `ops/devspawntest.sh` | 300 | Process-level guard test: stub daemon, fake production root, four mutations. |
| `aurora-cli/tests/test_devspawn.py` | 640 | 43 tests, 11 named mutations. |

**The grant, exactly.** The developer's container is given one bind mount: a
directory holding `spawn.sock` and `bridge.py`. Through that socket it can call
`spawn`, `destroy`, `list_mine`, `access`, scoped to `br-<user>-*`. It cannot
call any Docker verb. Measured inside the container:

```
$ ls -la /var/run/docker.sock
ls: cannot access '/var/run/docker.sock': No such file or directory
```

**Identity is not on the wire.** No developer schema has a `developer`, `devs`,
`name` or `project` property. The identity is a constructor argument to
`mcp.developer_server`, supplied by the broker from its own argv.

**Names are constructed, not accepted.** `spawn` takes a *label*; the project is
`br-<slug>-<label>`. There is no input to any developer tool that reaches a
project outside the caller's namespace.

---

## What was proven, and how

Every line below is a transcript from this host, not a claim about the design.

### The developer path, end to end, from inside a container

One ephemeral stack, created by the facade rather than by an operator. The
client was `nousresearch/hermes-agent:latest` — the real developer image — run
with **only** the socket directory mounted.

```
$ tools/list          -> ['spawn', 'destroy', 'list_mine', 'access']
                         properties: build, force, from_ref, label, no_seed, without
$ spawn {"label":"demo","from_ref":"main","devs":"all","force":true}
  -> BRANCH-ACCESS.md, 14544 bytes, isError=false
     project br-cumshit42069-demo, 12 containers,
     https://aurora-cumshit42069-demo.tailc67a98.ts.net/git/ = 200
$ destroy {"label":"demo","force":true}
  -> removed 14 containers, 9 volumes, 1 network
$ residue: 0 br- containers, 0 br- volumes, 0 br- networks
```

**`devs: all` and `force: true` were in the frame and were ignored.** The
evidence is discriminating: the branch's `.env` carries
`COMPOSE_PROFILES=agent-cumshit42069`, not `agents`. A server that honoured the
frame would have written `agents` and started every developer's agent.

### The negative cases, also from inside the container

| Frame | Result |
|---|---|
| `destroy {"label":"aurora"}` | acted on `br-cumshit42069-aurora`. Production untouched: container list unchanged, `/git/` 200. |
| `destroy {"label":"someoneelse-thing","developer":"someoneelse","name":"aurora","force":true}` | acted on `br-cumshit42069-someoneelse-thing`. The forged fields were never read. |
| `tools/call branch_down {"name":"aurora","all":true}` | `-32602 unknown tool 'branch_down'; this server offers ['access','destroy','list_mine','spawn']` |
| `spawn {"label":"second"}` while one stack was up | `SpawnDenied: quota: you already have 1 stack(s) up (br-cumshit42069-demo) and your limit is 1.` — and `.worktrees/` gained nothing. |

### The lease and the reaper, against the live stack

```
$ aurora dev-spawn ls
br-cumshit42069-demo   cumshit42069   expires_at=1785498544
$ (lease backdated) aurora dev-spawn reap --dry-run
would destroy br-cumshit42069-demo (owner cumshit42069, expired 29758070 min ago)
$ (lease restored)   aurora dev-spawn reap --dry-run
nothing has expired
$ br- containers still up: 12          # a dry run destroyed nothing
```

### Guards, against a stub — never the live daemon

`ops/devspawntest.sh`: stub `docker` that logs argv and executes nothing, a
throwaway git repo as production's root, and a **synthetic two-developer
roster** (`alice`, `bob`) because the live roster has one and every cross-tenant
assertion made against it is vacuous. All 24 cases pass.

The central assertion is *not* "it was refused". `destroy {"label":"bob-thing"}`
is **not** refused — the label lands in the caller's own namespace and
`br-alice-bob-thing` is torn down. The assertion is over the argv the daemon
would have seen: 3 mutating calls per case, every object `br-alice-*`.

| Mutation | Outcome |
|---|---|
| M1 — delete the name construction | still refused, by `assert_developer_owns`, 0 mutating calls |
| M2 — delete the construction **and** the ownership guard | **3 mutating calls reached `br-bob-thing`** — the tripwire fires, so its silence in every other case means something |
| M3 — same, aimed at production | 12 calls, all against `br-aurora`, none against `aurora`. `identity.branch_paths` forces the prefix, which is why running M2 was safe at all |
| M4 — delete the quota | the request gets past policy |

### Unit mutations

11 named mutations (`N1`–`N11`, tabulated in `test_devspawn.py`'s docstring),
each applied, observed red, reverted:

```
N1..N11  RED (good)
```

N1 reddens 8 tests; the rest redden the one they name.

### The suite

| Run | Result |
|---|---|
| clean `main` (baseline) | 32 failed, 542 passed, 23 skipped |
| this branch | 32 failed, 585 passed, 23 skipped |

The failing set is **byte-identical** to `main`'s (`comm -13` is empty in both
directions). Those 32 are the known `main` baseline fixed by PR #2. The +43 are
this branch's tests.

---

## Two things this harness caught in itself

1. **`ops/devspawntest.sh` passed for the wrong reason on its first run.** The
   fake production root had no `.env`, so every case failed with an
   `IdentityError` from `tailnet_suffix()` — which `isError:true` reported as a
   successful refusal. This is the sequential-guard shape: deleting a guard does
   not change the exception type. Fixed by adding the `.env` *and* by asserting
   on the message of every refusal.
2. **The first stub answered every enumeration emptily**, so the teardown path
   issued no `rm` at all and "no mutating docker call was made" would have passed
   against a completely disarmed server. Measured: mutation M2 could not make
   the tripwire fire. The stub now invents objects for whatever project it is
   asked about.

---

## Defects found, not fixed

1. **A tool failure whose message names a secret becomes an opaque frame.**
   `mcp._tool_payload` runs the leak check over the serialised payload; a
   `BranchError` naming `TS_AUTHKEY` therefore raises `AccessDocError` out of the
   handler and the caller receives `-32603 "the server refused to emit a
   response that would have carried a value marked secret"` instead of the
   diagnostic. Pre-existing, reproducible: `spawn` with no `TS_AUTHKEY_BRANCH`.
   The check is right; the failure mode is unreadable. Fixing it means
   redacting the variable *name* rather than refusing the frame.
2. **`socat`'s default `-t 0.5` silently truncates any call slower than half a
   second** once either side reaches EOF. Found the hard way: `tools/list`
   answered, `list_mine` returned zero bytes, and `spawn` (~53 s) could never
   have completed. The broker now passes `-t 3600`. Any *client* that
   half-closes needs the same — a `printf | socat -` harness does; `bridge.py`
   does not, because it shuts down only its write half.
3. **The socket mount needs `:z` on this host.** SELinux is `Enforcing`; without
   `:z` the container sees `Permission denied` on the mount even as root. Not a
   defect in this feature, but it is not optional and it is not obvious.
4. **`branch down` still cannot remove its own worktree.** The teardown reported
   `git worktree remove exited 255: Permission denied`; the daemon had created
   `.agent-env`, `arcadedb`, `affine/data` and `forgejo/ssh` inside it as root.
   Known defect, left alone: `.worktrees/cumshit42069-demo` is now a leaked
   worktree alongside `hub`, `hub2`, `ownersbind`, `perf1`, `devaccess1`. Not
   `sudo`-ed away — a permission check refusing is a defect to report, not to
   route around.
5. **`tests/test_worktree_buildable.py::test_fresh_worktree_resolves_compose_config`
   requires a `.env` in the worktree it runs from**, and a fresh worktree has
   none. It fails in any new worktree until production's `.env` is copied in.
   Environmental, pre-existing, not caused by this branch — confirmed by running
   it in a second fresh worktree off a different branch.

## What is NOT proven

- **Cross-developer isolation was proven against a synthetic roster, not a real
  one.** `developers.yaml` has one developer, so live there is no second
  namespace to fail to reach. What was proven live is the weaker, still
  load-bearing half: a label naming another party resolves into the caller's own
  namespace.
- **`hermes mcp add aurora -- python3 /run/aurora-spawn/bridge.py` was never
  registered with a real Hermes.** The bridge was exercised by running it as the
  container's process directly. What is unproven is Hermes' own MCP client
  behaviour against it — in particular whether it half-closes stdin.
- **The broker under concurrency.** One connection at a time was tested.
  `socat ...,fork` gives each connection its own process, and the quota is
  evaluated from the daemon per call, so two simultaneous `spawn`s could both
  observe zero stacks and both proceed. There is no lock. With
  `AURORA_SPAWN_MAX_TOTAL` as a backstop this is a race for the *count*, not for
  the *namespace*.
- **The reaper's destructive leg was not run live.** Candidate selection was
  (`--dry-run`, against a backdated lease on a real stack); the `branch_down`
  that follows is unit-tested only.
- **Nothing about restart, supervision or boot.** The broker was a foreground
  process for the duration of the exercise and was stopped afterwards.
