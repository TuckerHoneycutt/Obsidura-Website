# End-to-end verification of a real branch: pages, content, and teardown

**Date:** 2026-08-01
**Runtime:** docker (rootful), seeded
**Branch:** `pinverify`, created and destroyed through the REAL CLI
**Production:** unchanged throughout — 11 containers up, `/git/` 200 before and after

This is the check that was missing from both earlier measurements. Each of
those went through `branch_up(worktrees_root=...)`, a test seam, because both
concluded the real CLI could not create a worktree on this host. **That
conclusion was wrong**, and it is worth recording why, because it was believed
twice and acted on twice.

## The premise both measurements got wrong

Both reported `<production>/.worktrees` as `root:root 0755` and therefore
unusable by uid 1000. Measured directly:

```
$ ls -ld ~/Desktop/aurora/.worktrees
drwxr-xr-x. 1 supergoodname77 root 40 .../.worktrees

$ find ~/Desktop/aurora/.worktrees ! -user supergoodname77 | wc -l
0                       # of 175,992 paths
```

The directory is owned by **the user**; only the GROUP is root, which grants
nothing and takes nothing away. `touch` succeeds, `git worktree add` succeeds,
and `aurora branch up` succeeds. A human was told to run a `sudo chown` that
was never needed.

The lesson is not "the agents were careless" — it is that **`root:root` and
`user:root` differ by one field in `ls -ld` output**, and the conclusion drawn
from the misreading (a blocked CLI) was consistent with an unrelated real
failure, so nothing contradicted it.

## `branch up`, for real

```
aurora branch up pinverify --devs none --no-build
```

Created at `<production>/.worktrees/pinverify` — production's own worktree
root, not a seam. Seeded **2,576,576,182 bytes in 6.311 s**, including
`VACUUM INTO` snapshots of nine SQLite databases and a `pg_dump`/`pg_restore`
of AFFiNE's Postgres.

13 services: **11 running, 2 correct one-shot exits** (`dev-admin`,
`affine_migration`, both `Exited (0)`).

`affine_migration` exiting **0** here is itself a result: defect D3 — the
Postgres data directory created `1000:1000` while backends run as uid 999 — is
confirmed to be an **unseeded-only** failure. Seeding supplies production's
already-initialised cluster and the migration runs clean.

## Pages: accessible, and carrying real content

| path | result |
|---|---|
| `/` | 302 → `/git/.hub/` → 200, `<title>Aurora</title>` |
| `/git/` | 200, 14,913 bytes, `<title>null-hub [BRANCH: pinverify]</title>` |
| `/affine/` | 200, 2,689 bytes, `<title>AFFiNE</title>` |

A title and a 200 are not content, so the underlying data was checked directly:

```
$ ls <branch>/forgejo/git/repositories/*/
aurora-agent.git   aurora.git   dev-administration.git   superpowers.git

$ sqlite3 /data/gitea/gitea.db 'select count(*) from user, ...'
9 users | 4 repositories

$ psql -d affine -tAc 'select count(*) from users, workspaces'
1 user | 0 workspaces
```

Four real repositories, nine real accounts, and AFFiNE's Postgres restored.
The `0 workspaces` is faithful rather than a failure: production has no AFFiNE
documents yet, and a seed that invented some would be the bug.

## Teardown, and defect D2 proven fixed

D2 was "the docker path leaks root-owned worktrees it cannot delete" — measured
previously as 2.5 GB of undeletable files. On this branch, before teardown:

```
root-owned files in the worktree: 6
```

`branch down` now reclaims on the docker path (`docker run --rm --network=none
-v <worktree>:/worktree <image> chown -R <uid>:<gid>`), and after it:

```
root-owned files: 0        (of 33,996 paths)
```

The first `branch down` still stopped at `git worktree remove exited 128:
contains modified or untracked files, use --force`. That is the **right**
refusal and a different one: a permission error would have meant the reclaim
failed, and this is git protecting a seeded working tree. `branch down
--force` then removed it completely:

```
br-pinverify: removed 0 containers, 0 volumes, 0 networks; worktree removed
$ ls -d <production>/.worktrees/pinverify
No such file or directory
```

13 containers, 9 volumes and 1 network removed across the two passes. No sudo
at any point.

## What this does NOT establish

- **Nothing about podman.** This was the docker path. Podman still cannot seed.
- **Nothing about a cold host.** Every image was already local. The stack's
  cold-host reproducibility is still unproven and still blocked on
  `forgejo-mcp` having no published container image.
- **`branch up` on the FAILURE path.** This branch came up cleanly. A branch
  that dies half-built still leaves whatever its containers wrote; the D2 fix
  covers teardown only.
