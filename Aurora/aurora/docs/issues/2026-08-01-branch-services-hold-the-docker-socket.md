# Three branch services are handed the host's Docker socket

**Found:** 2026-08-01, while enumerating daemon-global keys for P1
**Severity:** this is the concrete mechanism by which a branch can reach production
**Status:** not a regression — inherent to the single-daemon design; P4 removes it

## Measured

`docker compose config` over the base stack, `COMPOSE_PROFILES="*"`, 13 services.
Bind mounts whose **source is outside the repository**:

| service | host path |
|---|---|
| caddy | `/var/run/tailscale` |
| forgejo | `/etc/localtime` |
| **dev-admin** | **`/var/run/docker.sock`** |
| **fjell** | **`/var/run/docker.sock`** |
| **hermes** | **`/var/run/docker.sock`** |

`compose.branch.yml` handles caddy correctly — `volumes: !override` replaces the
host's tailscaled socket with the sidecar's `tailscale_sock` volume, and there
is already a test asserting no branch service binds the host's tailscaled
socket.

**Nothing touches the other three.** A branch's `dev-admin`, `fjell` and
`hermes` each receive `/var/run/docker.sock` — the **root daemon's** socket, the
one that owns production's containers.

## Why the existing guard does not cover it

`ops/docker-guard` is a wrapper installed at `~/.local/bin/docker`, ahead of
`docker` on the operator's `PATH`. It is a **host** mechanism. It does not
exist inside a container, and a process holding the socket does not run
`docker` at all — it speaks HTTP to the socket directly.

So the guard's own documented weakness ("bypassed by anything that opens the
socket directly") is not hypothetical here: three branch services are handed
exactly that, by configuration, on every `branch up`.

## What it is not

Not a regression, and not obviously a defect to fix in place. `dev-admin`
genuinely manages containers, so it needs a daemon; with **one** daemon, the
only socket available is production's. `fjell` and `hermes` should be examined
separately — it is not obvious either needs it at all, and that is worth
checking before assuming.

## Why this raises P4's priority

The isolation spec ranks the daemon socket as a shared resource with "guard is
a PATH wrapper" as its status. This measurement makes it concrete: the socket
is not merely reachable, it is **mounted into three services by default**.

Rootless podman (P4) removes this structurally rather than by policy. Under it
the socket a branch can reach is the **user's own** podman socket, which owns
only branch containers. Production's root daemon is not merely guarded against,
it is unreachable — a different socket, a different image store, a different
process.

## Next

1. Determine whether `fjell` and `hermes` need the socket at all. If not,
   remove the bind for them — the cheapest real reduction available.
2. `dev-admin` keeps a socket, but under P4 it is the rootless one.
3. Add the P1 gate entry: a bind whose source lies outside the worktree is a
   daemon-global key and must be reset or allowlisted **with a written reason**.
   This finding is precisely what such a gate is for: nobody had enumerated
   `volumes` as global, so three sockets crossed the boundary unremarked.
