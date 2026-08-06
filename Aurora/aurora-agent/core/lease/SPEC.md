---
status: stub
---

# Lease SPEC

Audience: whoever implements ephemeral-environment leasing and the orchestrator that calls it. Job: pin the lease id format, the acquire/release contract, and what release is allowed to mean.

`core/lease/lease.py` is an interface stub. The argv layer is real and tested; both subcommands raise `NotImplementedError`.

## Lease id

Format: `aurora-eph-[0-9a-f]{8}` — e.g. `aurora-eph-deadbeef`.

1. One id per task. Generated at acquire, never reused, never guessed.
2. The id is the namespace prefix, the label value, and the worktree suffix. One string, so a stray resource is traceable to a task by grep alone.

## Contract

```
lease.py acquire            -> stdout: aurora-eph-<8hex>, exit 0
lease.py release <lease-id> -> exit 0 on clean release
```

| Subcommand | Must do |
|---|---|
| `acquire` | Allocate the namespace. Label **every** resource it creates with `lease: <lease-id>`. An unlabeled resource is a leak the guard cannot see. |
| `release` | Enumerate resources carrying the label, verify zero residue, then free the namespace. Nonzero exit if anything remains. |

Exit `2` on bad argv: no subcommand, unknown subcommand, `release` without a lease id.

## Release is a completion gate

A task is not done when the tests pass. It is done when the lease releases clean.

1. Release runs before the task reports success, not after.
2. Residue found → the task is blocked, not "finished with a note".
3. No auto-force. A release that cannot verify zero residue opens `G-CHECKPOINT`; it does not delete harder.

## The isomorphism

```
1 ticket = 1 brief = 1 worktree = 1 lease = 1 review package = 1 ledger line
```

Six names for one unit of work. Break the correspondence anywhere and the rest stop meaning anything: two leases per worktree and residue has no owner; two tickets per lease and the ledger cannot say what was released.

## Integration point

Provisioning lands in the `aurora` repo: `compose.branch.yml` plus `--devs`, which stands up per-branch stacks in their own namespace. Named here so the implementer builds `acquire`/`release` against it rather than inventing a second provisioning path. Not built in this repo.
