# Developer-facing ephemeral spawn — design

**Date:** 2026-07-31
**Status:** implemented as the narrow slice described in §7; §8 is designed, not built
**Branch:** `feat/dev-ephemeral-spawn`

---

## 1. Problem

`aurora branch up` is admin-only in a way that is structural, not accidental: it
needs a shell on the host and it needs the Docker socket. A developer lives
inside a Hermes agent container. So today the sentence "test in a branch, not in
production" is advice a developer cannot act on.

The obvious fix is to mount `/var/run/docker.sock` into the agent container.
**That is not an option and no configuration of it makes it one.** The socket is
the daemon's full API; `docker run -v /:/host --privileged` is one call from it,
and the daemon runs as root. Mounting the socket into a developer's container
grants that developer root on the host, including on production.

## 2. Goals

1. A developer, from inside their agent container, can create, list, inspect and
   destroy ephemeral stacks.
2. No developer can reach production through the facade.
3. No developer can reach another developer's stack through the facade.
4. A forgotten stack disappears on its own.
5. The host cannot be exhausted by one developer.
6. The container never holds anything that grants more than 1–5 allow.

**Non-goals.** Nested spawning (a stack's own agent spawning further stacks).
Cross-host scheduling. Per-stack resource quotas beyond the existing memory and
disk floor. A UI.

## 3. Decisions

**D1 — the socket stays on the host; the developer gets a protocol, not an API.**
A privileged listener (`ops/aurora-spawn-broker`) runs on the host, holds the
Docker socket by virtue of being a host process, and accepts connections on a
unix socket. What it speaks is `aurora mcp --as-developer <user>`: four
schema-validated MCP tools. The developer's container is given a bind mount of
one directory containing one socket. That directory is the entire grant.

What that grants, exactly: `spawn`, `destroy`, `list_mine`, `access`, scoped to
`br-<user>-*`. What it does not grant: any Docker verb, any path, any image, any
mount, any container in production, any other developer's stack.

The broker process itself remains root-adjacent — a code-execution bug in
`aurora_cli` running under it is a host compromise. That was already true of
`aurora branch up`. What changes is the reachable surface: previously anyone
with a host shell, now a caller restricted to four typed calls.

**D2 — identity is not on the wire.** No developer tool schema has a
`developer`, `devs`, `name` or `project` property, and every schema is
`additionalProperties: false`. The identity is a constructor argument to
`mcp.developer_server`, supplied by the broker from its own argv. A caller
cannot claim to be someone else because the protocol has no field in which to
make the claim. Which socket a container can open is a bind-mount decision made
by an operator, so identity is carried by the filesystem.

**D3 — names are constructed, never accepted.** `spawn` takes a **label**. The
branch name is `<developer slug>-<label>`; the project is
`br-<developer slug>-<label>`. There is no input to any developer tool that
reaches a project outside the caller's namespace. Containment is therefore a
property of the input space, not of a check that could be deleted —
`ops/devspawntest.sh` M2/M3 demonstrate that even with both policy layers
deleted, `identity.branch_paths` still forces `br-`, so a fully disarmed session
issues commands against `br-aurora`, never `aurora`.

**D4 — the prefix rule is only sound while namespaces are unambiguous.**
Developer `a` with label `b-x` and developer `a-b` with label `x` both produce
`br-a-b-x`. `devspawn.assert_namespaces_are_unambiguous` refuses a roster in
which one namespace prefix contains another, on every identity resolution rather
than once at deploy time. The live roster has one developer, so this rule is
vacuous in production and is pinned against a synthetic two-developer roster in
both test harnesses.

**D5 — quotas are counted from the daemon.** One stack per developer
(`AURORA_SPAWN_MAX_PER_DEV`), three per host (`AURORA_SPAWN_MAX_TOTAL`), counted
from `branch.live_branch_projects()`. Not from a file: a stack whose worktree
someone deleted is still running and still costs 1.3 GB. Size is *not* a new
knob — `branch.check_resources` already reads real memory and disk, and `force`,
which overrides it, is deliberately absent from the developer schema.

**D6 — leases, and a reaper.** `spawn` writes `.spawn-lease.json` into the
worktree: developer, project, name, creation time, TTL (default 4 h, ceiling
24 h). `aurora dev-spawn reap` destroys everything expired and is meant for
cron. A stack with **no** lease is never reaped — an operator's own
`aurora branch up` writes none, and a reaper that removed what it could not
explain would delete their work.

**D7 — the reaper trusts the daemon over the lease.** A lease is a file inside a
worktree, and a file is not evidence about what is running. The name and project
come from `branch_ls()`; the lease supplies only the owner and the expiry, and a
lease that disagrees with the daemon is skipped rather than reconciled.

**D8 — one transport, two tables.** `mcp.Server` makes the tool table a
parameter. The admin table is unchanged and still reached by `aurora mcp`. The
error model, the JSON-RPC framing and — critically — `_emit`'s secret-leak check
are shared, because a second server would be a second place to forget them.

**D9 — the bridge inside the container is twenty lines of Python.** `socat` is
not installed in `nousresearch/hermes-agent:latest` (measured); `python3` is.
`ops/aurora-spawn-bridge.py` relays stdio to the unix socket. It holds no
credential and makes no decision: everything it can do, a developer with a shell
in their own container can already do by opening the socket directly.

## 4. Threat cases and what refuses them

| Attempt | What stops it | Proven by |
|---|---|---|
| `destroy` another developer's stack | D3: the label lands in your own namespace. D2 second: even a forged `developer` field is never read. | `devspawntest.sh` §1, §"forged"; `test_destroy_resolves_into_the_callers_namespace_whatever_the_label_says` |
| name production | D3, then `guards.assert_branch_project`, then `assert_developer_owns` | `devspawntest.sh` M3; `test_a_label_always_lands_in_the_callers_namespace` |
| reach an admin tool (`branch_down` with an arbitrary name) | D8: the session's own table | `test_a_developer_session_cannot_reach_an_admin_tool` (mutation N10) |
| start every developer's agent in your stack (`devs: all`) | `devs` forced to the caller | mutation N8 |
| override the memory/disk floor (`force: true`) | `force` absent from the schema, hardcoded `False` | mutation N9 |
| fill the host with stacks | D5, refused before anything is created | `devspawntest.sh` §quota; mutation N4 |
| walk out of `.worktrees` when writing the lease | `guards.assert_not_production_path` on the path builder | mutation N11 |
| spawn as someone not on the roster | `assert_known_developer`, at broker start-up | `devspawntest.sh` §unknown developer |

## 5. What a developer sees

```
spawn      {label, from_ref?, without?, no_seed?, build?}  -> BRANCH-ACCESS.md
destroy    {label, force?}                                 -> teardown report
list_mine  {}                                              -> their stacks + leases
access     {label}                                         -> BRANCH-ACCESS.md
```

## 6. Operator surface

```
ops/aurora-spawn-broker <developer> [socket-dir]   # one per developer
aurora dev-spawn ls                                # leases
aurora dev-spawn reap [--dry-run]                  # cron
AURORA_SPAWN_MAX_PER_DEV / _MAX_TOTAL / AURORA_SPAWN_TTL_SECONDS
```

## 7. Deliberately not done

1. **The broker is not supervised.** No systemd unit, no socket activation, no
   restart. It is a foreground process an operator starts. A unit file is
   trivial and is left to whoever chooses the init story for this host.
2. **The socket mount is not wired into `compose.agents.yml`.** The generated
   agents compose is what production runs, and a bind source that does not exist
   is **created by the daemon as root** — the same mechanism that produces this
   repo's leaked, root-owned worktrees. A mount that appears in production's
   default compose file before a broker exists would therefore plant a
   root-owned directory in the checkout. The mount belongs in an opt-in overlay
   rendered at provisioning time; that generator is not built.
3. **No `reap` cron entry is installed.** The command exists and is tested; the
   schedule is an operator decision.
4. **Nested spawning is not prevented explicitly.** A stack's own agent has no
   broker, so it cannot spawn today; the global quota is what would bound it if
   one were ever wired in.
5. **No audit log.** Who spawned what is recoverable from lease files and
   Docker labels, not from an append-only record.

## 8. The version this slice is not: a supervised broker

The honest full design differs from §7.1–7.2 only in operational plumbing, and
it is worth writing down because the security argument is unchanged:

- a systemd socket unit per developer (`aurora-spawn@<user>.socket`), so the
  broker is started on demand, restarted on failure, and its lifetime is not a
  terminal;
- `dev-admin provision` renders both the socket units and a
  `compose.spawn.yml` overlay carrying the per-developer bind mount, so the
  directory exists before any container references it — which is what makes
  the mount safe to put in compose at all;
- a `reap` timer;
- an append-only spawn log written by the broker, outside any worktree.

None of that changes D1–D9. It changes who starts the process and who creates
the directory.
