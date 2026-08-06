# btrfs: `mv` across a subvolume boundary is a copy, and it wedged the host

**Status:** host needs a reboot to clear; production unaffected throughout
**Date:** 2026-08-01

## What was attempted

Per §6 of the isolation spec, `.worktrees` was to become its own btrfs
subvolume so a qgroup could cap the disk all branches share. The migration
given to the operator was:

```bash
mv .worktrees .worktrees.old
btrfs subvolume create .worktrees
mv .worktrees.old/* .worktrees/          # <-- the defect
```

## Why that is wrong

**A `mv` across a subvolume boundary is not a rename, it is a full byte
copy.** `.worktrees` was now a *different* subvolume, so every file was
physically copied rather than relinked — and the copy **dereferences
reflinks**, so each branch worktree's ~2.6 GB of extents *shared with
production* became ~2.6 GB of real, exclusive data.

The correct command reflinks across subvolumes on the same filesystem and is
near-instant:

```bash
cp -a --reflink=always .worktrees.old/. .worktrees/ && rm -rf .worktrees.old
```

## What happened

The copy was interrupted after 4 of 16 worktrees had moved and 2 more were
partially copied. Rolling back meant deleting the partial copies, `rmdir`ing
the empty subvolume and renaming the originals back — but the delete never
finished. Measured over 43 minutes:

| process | elapsed | CPU consumed |
|---|---|---|
| `mv` (SIGKILLed, kill pending) | 1:30:02 | 0:00:06 |
| `rm -rf` | 1:22:51 | **0:00:04, unchanged for 43 min** |
| `du`, `find` (diagnostics) | — | 0:00:00 |

All four sit in uninterruptible `D` state on `btrfs_opendir`. Zero CPU and no
change in free space is a **deadlock, not slow progress**. They cannot be
killed; a reboot is required.

The rest of the filesystem is healthy — write, read, delete and `git` all
succeed outside `.worktrees`, and production ran untouched throughout
(11 containers, `/git/` 200, disk steady at 42%). Only the `.worktrees*`
subtrees are held.

## Three lessons

1. **`mv` between subvolumes is `cp` + `rm`.** Same filesystem is not the same
   thing as same subvolume. Reflink-seeded trees make this far worse than it
   looks, because the copy destroys the sharing the design depends on.
2. **Do not sample a tree another process is writing to.** Two of the four
   wedged processes are `du` and `find` — diagnostics run *against the tree
   being deleted*. Practices note Part 4.4 says exactly this, and it was
   ignored while debugging the very incident it describes.
3. **Per-branch qgroups were already ruled out**, for a reason this incident
   reinforces: an unprivileged user on this host can `btrfs subvolume create`
   but **not** `btrfs subvolume delete` (no `user_subvol_rm_allowed`), so every
   `branch down` would leak a subvolume.

## What to do instead

Prefer the no-root option first: extend the existing resource guard in
`branch up` to refuse when free disk is below a threshold. It costs no root,
no filesystem metadata, and catches the runaway-branch case *before* it starts.
Treat qgroups as the hard backstop only if that proves insufficient.

If the subvolume migration is still wanted, do it with **no branches up**, with
`cp -a --reflink=always`, and verify with `btrfs filesystem du -s` that sharing
survived the move before deleting the source.
