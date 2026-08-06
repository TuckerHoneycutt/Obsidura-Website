# `forgejo-mcp:v2.30.2`: the project is alive, the container image is not

**Status:** pinned and archived; cold-host reproducibility still open
**Date:** 2026-08-01
**Severity:** LOW. Corrected down from the first draft of this file — see below.

## What is actually true

The **project** is fine. `https://codeberg.org/goern/forgejo-mcp/releases` lists
v2.30.2 (2026-07-13) as the latest of 32 releases, with source archives,
multi-platform binaries, `.mcpb` bundles, SHA checksums, GPG signatures and
SBOMs.

What does not exist is a **container image**. Verified three ways rather than
inferred from one failure:

1. `docker manifest inspect codeberg.org/goern/forgejo-mcp:v2.30.2` → `manifest unknown`
2. With a valid anonymous registry token, `GET /v2/goern/forgejo-mcp/tags/list`
   → `{"errors":[{"code":"NAME_UNKNOWN"}]}`, and the manifest endpoint → 404.
   So this is not an auth artefact.
3. The releases page lists no container artefact, and `codeberg.org/goern/-/packages`
   lists ten container packages, none of them `forgejo-mcp`.

`compose.yml` nonetheless pins `codeberg.org/goern/forgejo-mcp:v2.30.2`, and it
runs — from one image in the local docker store, pulled 2026-07-13.

## Severity, corrected

The first version of this file called the situation dangerous. That was wrong,
and the correction matters more than the finding:

- **Forgejo itself is unaffected.** It is a different image
  (`codeberg.org/forgejo/forgejo:15`), still published, checked and available.
  Repositories, PRs, users, the web UI, git over ssh and https, and the CLI
  tools do not involve this container at all.
- **forgejo-mcp is a convenience layer** — an MCP server letting agents talk to
  Forgejo. It is internal-only: no published ports, not behind Caddy,
  multi-tenant HTTP mode where each Hermes client passes its own token.
- **It is demonstrably not load-bearing.** It has been crash-looping inside
  every ephemeral branch (`restarts=1136`, its own tailnet name does not
  resolve from inside a branch) while those branches worked.

Losing it costs agents a convenient path to Forgejo. It costs a human nothing.

## What was done

1. **Archived**, before anything could evict it:
   `~/aurora-image-archive/forgejo-mcp-v2.30.2.tar` (17 MB),
   sha256 `3a57698cd4f788aa17f82fc64d72e8667ac81eb1d2823cde9a067da23c34bf0e`.
   Restore with `docker load -i …`. Deliberately outside the git checkout — a
   17 MB blob in git is paid for on every clone forever.
2. **Pinned by digest** in `compose.yml`, like every other external image:
   `…forgejo-mcp:v2.30.2@sha256:207daf82da6dc3267471385da951f5730ca6428d22d3344c54f193e4f5991853`.

## The two mitigations are not independent

Adversarial review caught this and it is worth stating plainly: **pinning by
digest constrains the archive restore.** A digest reference resolves through
`RepoDigests`, and a classic graphdriver `docker load` populates none -- so on
such a host the tarball would restore the image and `compose.yml` still could
not name it.

This host survives because it runs the **containerd** image store
(`docker info` -> `io.containerd.snapshotter.v1`) and the archive is an OCI
layout carrying the manifest blob `207daf82...`, which is re-registered on
load. That has not been proven by actually restoring it. On any host without
the containerd store, `docker tag` the loaded image afterwards.

Which sharpens the sentence below that was already true: an archive nobody has
ever restored is not a backup.

## Still open

**A cold host cannot build this stack.** Pinning makes the reference exact; it
does not make an absent image obtainable. The fix is to stop depending on a
stranger's registry for the one component that has already vanished from it:

1. **Build it from the released source or binary.** The release carries
   linux/amd64 binaries with checksums and GPG signatures, which is a *better*
   supply-chain position than pulling somebody's image. A short Dockerfile that
   fetches the pinned binary and verifies its checksum makes `forgejo-mcp` as
   reproducible as `fjell` and `agent-authz` already are. Preferred.
2. **Push the archived image to the Forgejo registry we already run.** Cheapest;
   trades a stranger's uptime for our own.
3. **Keep only the tarball.** Weakest — an archive nobody has restored is not a
   backup. If this is the choice, the restore needs a test.

## The general defect this exposed

**Nothing in this repository tests that production can be obtained from
scratch.** `tests/test_build_conformance.py` proves an image is not older than
its build context — a staleness check, which *presumes the image exists*. The
property that was silently false is "a cold host can reach a running system",
and it is still false today.

See also `2026-08-01-floating-image-tags.md`, which is the same class of
problem with a much larger blast radius, found while checking this one.
