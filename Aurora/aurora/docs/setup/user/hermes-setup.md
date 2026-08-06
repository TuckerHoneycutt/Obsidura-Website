# Hermes Agent Setup (per-user)

Installs the Aurora agent profile — your config, plugins, and identity. Your sessions, memories, and credentials stay untouched.

```bash
hermes profile install https://superserver.tailc67a98.ts.net/git/supergoodname77/aurora-agent.git --name aurora
```

Then fill in your `.env` (API keys, Forgejo token — see `forgejo-setup.md`).

Update later with:

```bash
hermes profile update aurora
```

---

## Your own ephemeral stacks

A complete second copy of the whole stack — its own Forgejo, its own agent, its
own tailnet name, seeded from production read-only. You get no Docker socket
and need none. Ask an operator for the mount first; then, once:

```bash
hermes mcp add aurora -- python3 /run/aurora-spawn/bridge.py
```

Four tools. You choose the **label**; the rest of the name is yours and you
cannot spell another developer's stack or production.

| Tool | Arguments | What you get |
|---|---|---|
| `spawn` | `label`, and optionally `from_ref`, `without`, `no_seed`, `build` | its `BRANCH-ACCESS.md`. **Act on that document directly** — it is the product |
| `list_mine` | — | your stacks and when each lease expires |
| `access` | `label` | one stack's `BRANCH-ACCESS.md`, regenerated |
| `destroy` | `label`, and optionally `force` | containers, volumes, network and worktree |

- **One stack at a time** (`AURORA_SPAWN_MAX_PER_DEV`), and the host caps the
  total, so `spawn` can also be refused because someone else is using it.
- **The lease is 4 hours** and expiry is a destruction, not a warning. Nothing
  you leave in the worktree survives it. `destroy` when you are done — a stack
  you forgot is a stack you cannot replace.
- `spawn` takes about a minute. If it fails, the half-built stack is left up on
  purpose; `destroy` it.
- `cannot reach /run/aurora-spawn/spawn.sock` means the broker is not running
  or your container has no mount. Ask an operator; nothing on your side fixes it.
