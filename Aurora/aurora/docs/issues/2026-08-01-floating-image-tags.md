# Five of the stack's images floated, and all five had already drifted

**Status:** FIXED — every external image is pinned by digest, with a
conformance test
**Date:** 2026-08-01
**Severity:** HIGH. This is the finding; the withdrawn `forgejo-mcp` image that
led here (`2026-08-01-forgejo-mcp-image-withdrawn.md`) is the footnote.

## What was found

Checking whether any *other* image had been withdrawn turned up something
worse. Five of the stack's images were not pinned at all:

```
ghcr.io/toeverything/affine:stable
caddy:latest
nousresearch/hermes-agent:latest
redis                     # no tag at all, i.e. redis:latest
tailscale/tailscale:latest # the branch sidecar, in overlay.py
```

And **every one of them had already drifted.** Comparing the digest production
was running against the digest the tag resolved to that day:

| image | running | tag resolved to |
|---|---|---|
| `affine:stable` | `d9d145f9…` | `03df0ac8…` |
| `caddy:latest` | `844f60b6…` | `98eb57d8…` |
| `hermes-agent:latest` | `bbe5076a…` | `9caf0ed8…` |
| `redis:latest` | `c88d347e…` | `3cdb04fc…` |
| `tailscale:latest` | `cdf5612d…` | `747ac040…` |

Five for five. Not a hypothetical.

## Why this is worse than a withdrawn image

**A withdrawn tag fails loudly. A floating tag succeeds quietly with different
software.**

`ops/rebuild.sh` runs `docker compose up -d --build`. On any host that had to
pull — a cold host, a pruned cache, a new machine — production would have come
back up running five services nobody chose, with no diff, no commit, and
nothing to roll back to. The symptom would arrive as "AFFiNE broke and nobody
touched it", which is exactly the kind of failure that costs days.

AFFiNE and Hermes are the two that would hurt most, and AFFiNE is already the
service that has consumed the most debugging time on this stack.

## The fix, and the one subtlety in it

Every external image is now `name:tag@sha256:<digest>` — the tag kept for
human legibility, the digest deciding what actually runs.

**The digests were taken from the images production was ALREADY RUNNING, not
from what the tags resolved to that day.** This is the whole subtlety: pinning
to "current" would itself have been a five-service upgrade, performed silently,
in a commit whose stated purpose was to stop exactly that. Verified afterwards
that every pinned reference resolves in the local image store, so a rebuild
pulls nothing and changes nothing.

Also pinned, because they start real containers and appear in no compose file —
which is how the first survey of "every external image" missed them:

- `overlay.py`, the branch tailscale sidecar
- `seed.py`'s `VOLUME_SEED_IMAGE`
- `runtime.py`'s `RECLAIM_IMAGE` (new; see `2026-08-01-d2-worktree-ownership.md`)

## What keeps it fixed

`tests/test_image_pinning.py`. It parses the compose YAML and the Python image
constants directly — no `.env`, no daemon, no network — and fails on any
external image without a digest. Verified by mutation: unpinning one compose
image and one Python constant makes exactly the right tests red.

It also closes the obvious hole: `:local` is exempt because those services are
built here, so the test additionally asserts that anything claiming `:local`
really does declare a `build:`. Otherwise pinning could be defeated by naming
an external image `something:local`.

## Two classes the first version of the test could not see

Adversarial review found both, and both were live:

**Dockerfile base images.** `agent-authz:local` and `dev-admin:local` are exempt
from the digest rule because this repository builds them -- and what it built
them FROM was floating: `FROM python:3.13-slim` in three Dockerfiles, plus
`FROM rust:1.85` and `FROM debian:bookworm-slim` in fjell. So `ops/rebuild.sh`
on a cold host rebuilt four production services on whatever those resolved to
that day. **Exempting the output while ignoring the input is not an exemption,
it is a gap.** The test could not see it for a dull reason: `Dockerfile` has no
suffix, and the scan filtered on suffixes.

**Untagged references.** `provision.py` passed `image="alpine"` -- no tag at
all -- straight to `run_temp_container`, twice. A matcher requiring `repo:tag`
is structurally blind to that, and `redis` (the example this file opens with)
is the same shape.

The test is now three checks rather than one, split by what each can prove: a
single `repo:tag@sha256:<64 hex>` validator, a scan of tagged references in
shipped code including Dockerfiles, and an AST check that identifies images by
ROLE (`image=` arguments and `*IMAGE*` constants) so an untagged one is caught
without any list of repository names.

## Podman branches will re-pull three images once

The digests were taken from the root docker store. The rootless podman store
holds different digests for `redis`, `pgvector/pgvector:pg16` and
`nousresearch/hermes-agent`, and no `python:3.13-slim` at all. All are
registry-reachable, so this works -- but the first `branch up --runtime podman`
after this lands pulls them, on a path guarded by tailnet and HTTPS timeouts.
Expect one slow branch, not a failure.

## Upgrading, from now on

Changing a digest is now a commit, which is the point. To move an image
deliberately:

```bash
docker pull <name>:<tag>
docker image inspect <name>:<tag> --format '{{index .RepoDigests 0}}'
# put that digest in the compose file, then:
bash ops/rebuild.sh
```

The cost is that security updates no longer arrive on their own. That is the
trade being made deliberately: an unreviewed update to production is not a
security posture, it is an outage with better intentions.
