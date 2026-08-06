# A killed `docker run` left a container the daemon cannot remove

**Status:** live on the host; needs a docker daemon restart, which restarts
production
**Date:** 2026-08-01
**Cause:** mine — `pkill -9` on a pytest run that had a `docker run` in flight

## What happened

Two pytest runs were executing concurrently against the same daemon (an ssh
wrapper timed out locally without killing the remote process, and a second run
was started alongside it). Clearing that with `pkill -9` killed a test while it
was mid-`docker run`, and the container never finished being created:

```
jolly_keller | python:3.13-slim | Created | "python -"
```

`python -` is `seed.VOLUME_SEED_IMAGE` running the volume-seed payload from
stdin, so this is a `seed_agent_volume` container, killed between `create` and
`start`.

## Why it cannot simply be removed

Both of these hang indefinitely — not error, hang:

```
docker inspect jolly_keller     # timed out at 166s
docker rm jolly_keller          # timed out at 120s
```

The daemon holds a reference it cannot resolve. Nothing short of restarting
`dockerd` clears it.

## What it breaks

`tests/test_runtime_conformance.py::test_every_container_on_the_project_network_carries_the_project_label`
iterates **every** container on the host and calls `docker inspect` on each. It
reaches `jolly_keller` and hangs, taking the whole test run with it. Two full
regression runs were lost to this before the cause was found; the first
diagnosis — concurrency between agents — was wrong.

Production is unaffected. The container is inert, is attached to no network,
and holds no volume.

## Clearing it

```bash
sudo systemctl restart docker
```

Every production container carries `restart: unless-stopped` and returns on its
own. This is an operator decision, not an automated one: it is a brief outage
of a live system to clean up test residue.

## The general defect it demonstrates

Throwaway containers in this repository carry **no compose project label**:

- `seed.seed_agent_volume` — `docker run --rm -i --network=none …`
- `runtime.reclaim_worktree_ownership` — `docker run --rm --network=none …`

`--rm` handles the normal case, and neither survives a successful run. But when
one does survive, it is in the worst possible position:

1. **Invisible to every project-scoped sweep.** `branch_down` finds residue by
   filtering on `com.docker.compose.project`; an unlabelled container matches
   nothing and is reported by no teardown.
2. **Outside the namespace the guard permits.** `ops/docker-guard` allows
   destructive commands only when they are provably scoped to `br-*`, so even
   a human following the teardown docs has no sanctioned command for it.

Adversarial review raised exactly this as a hypothetical ("if `--rm` does not
fire, the container is invisible to the residue sweep") on the same day it
happened for real.

**Fix:** label both throwaway containers with the branch's compose project.
That makes a survivor visible to the existing residue sweep and removable
through the existing guard, with no new mechanism. It does not help *this*
container, which is already wedged at the daemon level.
