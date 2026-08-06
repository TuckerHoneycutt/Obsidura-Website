# dev-admin: Current Issues + Revision Needed

## Problem: container-per-command is suboptimal

The current `dev-admin` container runs one command (`reconcile`) then exits. Every subsequent CLI invocation requires `docker compose run --rm dev-admin <command>`, which spins up a new container each time. This is slow, wasteful, and awkward for interactive use.

## Root cause

The orchestrator was designed as a run-once reconciler (`restart: "no"` + `command: ["reconcile"]`). The CLI has interactive commands (`add`, `remove`, `status`, `deprovision`) that can't be used without starting a new container.

## Issues

1. **No interactive access.** `docker exec dev-admin <cmd>` fails because the container exits after `reconcile`. Only `docker compose run --rm` works, which is heavyweight for a one-line CLI command.

2. **Bazzite read-only overlay.** Bind mounts into `/app` are read-only (overlayfs). Worked around by using `/output` for Caddyfile.d, but any future writable mount needs the same pattern or a named volume.

3. **No MCP server.** The orchestrator is a CLI tool, not a service. The master orchestrator Hermes can call it via `terminal("docker compose run --rm dev-admin status")`, but that's indirect. A long-running service with an MCP interface would let the admin Hermes call `mcp_dev_admin_status()` directly.

4. **No SSH key management.** The `authorized_keys` mount is disabled (read-only overlay). SSH key management from the fjell setup form and the orchestrator's deprovision step both need a different approach (e.g., `docker exec` into the host's SSH service, or a named volume for authorized_keys).

5. **No health endpoint.** The container has no way to report its state to monitoring systems.

## Proposed revision

Transform `dev-admin` from a run-once container into a **long-running administration service**:

- **Long-running container** (`restart: unless-stopped`) with the CLI available via `docker exec`
- **MCP server** exposing orchestrator commands as tools (`dev_admin_reconcile`, `dev_admin_status`, `dev_admin_add`, `dev_admin_remove`, `dev_admin_deprovision`) — the master orchestrator Hermes connects to it like forgejo-mcp
- **HTTP health endpoint** on a dedicated port
- **Named volumes** for Caddyfile.d output and authorized_keys (avoids Bazzite overlay issues)
- **Cron loop** — optionally run `reconcile` on a schedule inside the container instead of requiring external cron

This aligns with the user's vision of a "script box" / administration service that unifies all system administration tools behind one MCP interface.
