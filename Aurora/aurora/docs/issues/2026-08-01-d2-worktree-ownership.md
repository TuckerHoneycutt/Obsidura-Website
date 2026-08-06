# D2: the docker path leaked worktrees it could not delete

**Status:** FIXED
**Date:** 2026-08-01
**Found by:** the docker/podman parity measurement
(`docs/measurements/2026-08-01-docker-podman-parity.md`)

## The defect

Tearing a branch down on the **docker** runtime left its worktree behind,
root-owned, and the user who created the branch could not delete it. Measured
at 2.5 GB of undeletable files after a single teardown. On **podman** the same
teardown cleaned up completely.

Cause: the rootful docker daemon runs container `root` as host uid 0, so every
file a container writes into a bind-mounted worktree comes back owned by root.
`git worktree remove` then fails, and the residue accumulates one branch at a
time.

## Why it survived review

`runtime.reclaim_worktree_ownership` already existed and already solved this —
for podman only, where the problem takes a different shape (a container's
NON-root uid maps into the subuid range; Postgres at uid 999 leaves
`data/postgres` owned by 525286, mode 0700).

Its own docstring said, of the docker daemon, that `git worktree remove` fails
*"exactly as it did when the root daemon left root-owned directories behind"* —
**describing in the past tense a bug that was still live on the path without
the fix.** The call site was guarded by `if resolved_runtime.is_podman:`, so
the one runtime that had the remedy was the one that did not need it as badly.

This is worth remembering as a review failure mode: a comment that accurately
describes a defect is not a fix, and reads like one.

## Second-order damage

This is very likely the origin of the root-owned paths that have repeatedly
blocked work in `<production>/.worktrees` — including during the btrfs
subvolume migration, where a root-owned `hubdev` directory made `rmdir` fail
and turned a rollback into a wedged host. Treating those as one-off cleanups
was treating the symptom.

## The fix

`reclaim_worktree_ownership` now takes the resolved `runtime` and reclaims on
**both** paths. Docker borrows root from the daemon that created the problem:

```
docker run --rm --network=none -v <worktree>:/worktree \
    <RECLAIM_IMAGE> chown -R <uid>:<gid> /worktree
```

No `sudo`, no `AURORA_ALLOW_PROD`, and no new dependency: `RECLAIM_IMAGE` is
the same pinned image `seed.VOLUME_SEED_IMAGE` already requires, with a test
asserting the two cannot drift. A teardown that cannot run because an image is
unreachable would be a worse failure than the leak it prevents.

Two properties the tests pin down, because a recursive chown driven by a root
daemon deserves them:

- **The mount is the worktree alone**, never its parent — so a bug here cannot
  walk into a sibling branch or toward production.
- **`guards.assert_not_production_path` holds on both branches**, not only the
  one it was written for.

Both were verified by mutation: making the docker path emit the podman argv
again turns exactly those tests red.

## Verified live, not just in argv

Every early test of this drove a fake runner and asserted the command line.
That is exactly how the defect shipped: `tests/test_podman_runtime.py` records
that the podman reclaim was once "tested" by re-spelling `podman unshare chown`
in the test rather than invoking the product function, so replacing the body
with `return True` reddened nothing.

`tests/test_docker_reclaim_live.py` is the outcome test. It makes a tree
root-owned the way the defect does -- a real container writing through a bind
mount -- calls the real function, and asserts `st_uid` afterwards. It names no
command, asserts its own precondition (a tree that was never root-owned would
make it vacuous), and was verified by mutation: a reclaim that returns True
without running turns it red.

Confirmed end to end on a real branch as well: 6 root-owned files before
teardown, 0 of 33,996 after, then `git worktree remove` succeeded.

## Still open

Not the `branch up` failure path, which the first draft of this file named.
That path is covered: `record_runtime` is written before the first `up`, so any
worktree with container-written files has a runtime record, and the
`BranchUpFailed` message directs the operator to `aurora branch down`, which
now reclaims on both runtimes.

Nor is it a stack whose worktree was deleted by hand. Measured 2026-08-01 on
three stale `pytest-*` stacks: `branch down` found no `compose.yml`, said so,
fell back to LABEL-DRIVEN removal and cleaned all three completely (3
containers and 1 network each).

**The real gap is narrower than either: the leftover DIRECTORY.**
`<production>/.worktrees/hubdev` is in no `git worktree list` and holds only
container-created state. Step (5) of the teardown only ever runs `git worktree
remove`, which fails for a directory git no longer tracks; the failure becomes
a note and the directory stays. The reclaim makes it *deletable*, which is the
win, but nothing removes it automatically.

Confirmed through the developer spawn path as well: a stack spawned and
destroyed entirely from inside a developer's container left **0 root-owned
paths of 2,274**, with no operator involvement at any point.

Manual reclaim for anything already stranded, which needs no sudo:

```bash
docker run --rm --mount type=bind,src=/absolute/path,dst=/w \
    python:3.13-slim@sha256:6771159cd4fa5d9bba1258caf0b82e6b73458c694d178ad97c5e925c2d0e1a91 \
    chown -R $(id -u):$(id -g) /w
```

(The digest is `runtime.RECLAIM_IMAGE`. An unpinned command in the change whose
thesis is that unpinned images are the defect would be its own counterexample.)
