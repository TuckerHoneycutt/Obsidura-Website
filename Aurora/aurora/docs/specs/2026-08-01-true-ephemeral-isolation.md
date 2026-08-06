# True ephemeral isolation — spec

**Status:** proposed, awaiting sign-off
**Branch:** `feat/true-ephemeral-isolation`
**Host facts measured 2026-08-01** (see §7; nothing below is assumed)

---

## 1. The problem, stated correctly

Isolation is an **inventory problem**, not a bug list.

Compose namespaces exactly four things: containers, volumes, networks, and the
project label. **Everything else on that daemon is a shared mutable resource.**
The image-tag escape found on 2026-07-31 was not a subtle bug — it was an
unenumerated item. Nobody had written the list.

So the first deliverable is the list, and a gate that fails when it grows.

| Shared resource | Namespaced today | Phase |
|---|---|---|
| containers, volumes, networks | yes (compose project) | — |
| `container_name`, `ports` | yes (overlay `!reset`) | — |
| image tags | yes, since PR #2 | — |
| **any future daemon-global key** | **no** | **P1** |
| memory / CPU / PIDs | no | **P2** |
| `FORGEJO_ADMIN_TOKEN` | no — valid on production | **P3** |
| the daemon socket | no — PATH wrapper only | **P4** |
| image store / build cache | no | **P4** |
| disk (`/var/lib/docker`, worktrees) | no | P5 (specced, blocked) |
| tailnet auth key | no — one reusable key | P6 (specced, blocked) |
| `.git` object store | no | out of scope |
| host kernel | no | out of scope (needs a VM) |

---

## 2. P1 — the enumeration gate

**Why first.** It addresses the unknown-unknowns rather than today's known one.
It is the difference between "we fixed the image bug" and "this class is closed".

**Behaviour.** Generalise `test_every_shared_image_tag_is_reset` into: *every key
in the resolved branch config that is daemon-global must be either reset in the
overlay or allowlisted with a written reason.* Adding a service that carries a
new global attribute fails the suite instead of silently sharing.

**Daemon-global key set** (each entry carries its reason in the allowlist file):
`container_name`, `ports`, `image` (when the service also `build:`s),
`hostname`, `mac_address`, `network_mode` when it names a non-project target,
`external: true` volumes and networks, `pid: host`, `ipc: host`,
`userns_mode: host`, `privileged`, `devices`, `cap_add`, host-path `volumes:`
sources outside the worktree.

**Acceptance.** Not "the test passes". A service is *added* to a fixture compose
file carrying each global key in turn; the gate must redden for each, naming the
key and the service. A key added to the allowlist without a reason string must
also redden.

**Mutations.** M1 delete one allowlist entry → red. M2 add a new global key to
the fixture → red. M3 make the reason string empty → red. M4 point the gate at
production's config instead of the branch's → red (wrong-identity conformance).

---

## 3. P2 — resource limits

**Measured baseline** (2026-08-01, `docker stats`, production): total ~1.1 GB
across 11 containers. Largest: `hermes` 395 MB, `affine_server` 185 MB,
`forgejo` 147 MB, `arcadedb` 161 MB. Host: 16 GB, 16 cores, **6 GB available
with one branch already up.** A `br-hubdev` agent was measured at **92.6% of a
core** with no ceiling on it.

**Behaviour.** `mem_limit`, `pids_limit` and `cpus` on **branch services only**,
written into the generated overlay. Production is never limited: a mis-sized
limit must not be able to cause a production outage.

**Three modes**, because a benchmark and a leak need opposite defaults:

| Mode | How | Meaning |
|---|---|---|
| `measured` (default) | — | per-service ceiling = measured production usage × headroom factor |
| `<profile>` | `--limits <name>` / `$AURORA_BRANCH_LIMITS` | a named profile in `branch-limits.yaml` |
| `none` | `--limits none` | **no ceilings at all** — for resource-intensive features and benchmarking |

`none` is recorded in `BRANCH-ACCESS.md`, the same way `--force` already is, so
an unlimited branch is never invisible.

**Acceptance.** Empirical, not declarative. A container is driven past its
ceiling (`stress-ng`-style allocation in a throwaway service) and must be OOM
killed **while production is measured unchanged throughout**. `docker compose
config` showing a `mem_limit` proves nothing — cgroup enforcement is the claim.

**Mutations.** M5 drop `mem_limit` from the overlay → the OOM test goes green
(i.e. the victim survives) → red. M6 set the ceiling above host RAM → red.
M7 `--limits none` still emitting a ceiling → red.

---

## 4. P3 — branch-scoped Forgejo credential

**The defect.** `branch-env.yaml` overrides 14 names; `FORGEJO_ADMIN_TOKEN` is
not among them. The branch's Forgejo is a **byte-copy of production's database**,
so the inherited token authenticates against *both*. A branch's `dev-admin`
holds a credential that is valid on production's API.

**Behaviour, in order** (the ordering is load-bearing):

1. Branch Forgejo starts, seeded from production.
2. Using the inherited token — which is valid here precisely *because* the DB is
   a copy — mint a **new** admin token via the branch's own API.
3. Write it to the branch `.env` as `FORGEJO_ADMIN_TOKEN`.
4. **Delete production's token rows from the branch's copy of the database.**

After step 4 the branch holds no credential valid against production, and
production's token is not recoverable from the branch's data at rest.

**Acceptance.** Two assertions, both empirical:
- the branch's token, presented to **production's** API → 401.
- production's token, presented to the **branch's** API → 401.

Neither is a config assertion; both are HTTP calls with recorded responses.

**Mutations.** M8 skip step 4 → the second assertion goes green → red. M9 mint
but do not write to `.env` → reconcile fails loudly rather than silently reusing
the inherited token. M10 run step 4 before step 2 → minting fails, and the
failure must name the ordering.

---

## 5. P4 — rootless podman as the branch runtime (opt-in)

**This is the structural fix.** It collapses the socket, the image store and the
build cache in one move: a branch cannot see production's images or containers
because they are in a different daemon, not because a guard says no. The
existing `ops/docker-guard` is a `PATH` wrapper and is bypassed by anything that
opens the socket directly; this makes that irrelevant for branch work.

**Everything needed is already installed** (§7). No package installs, no root.

**Behaviour.** `--runtime podman` / `$AURORA_BRANCH_RUNTIME` points branch
compose at `unix:///run/user/1000/podman/podman.sock` via `DOCKER_HOST`.
Production keeps the root docker daemon. Compose semantics are unchanged: the
same `docker compose` binary, the same overlay, the same three `-f` files.

**Why this is cheap here specifically:**
- The 5.5 s CoW seed is `cp --reflink=auto` run **host-side by the CLI**, not by
  the daemon, so a second runtime does not touch the fast path.
- Rootless maps container `root` to uid 1000, so the daemon stops creating
  root-owned bind sources — which is the leaked-worktree defect, fixed for free.

**Two blockers to prove, not assume** — and they are exactly what a branch is for:

1. **SELinux is Enforcing.** Bind mounts need `:z` relabelling or the container
   gets EACCES. Safe *only because* every bind is repo-relative — there is
   already a conformance test asserting no service binds a path outside the
   repo. **If that stops being true, this phase halts.** Relabelling touches the
   branch's own disposable copy, never production's files.
2. **Rootless UID mapping.** Container `root` → uid 1000, but a container
   running as a non-root uid (Postgres as 999) maps into the subuid range
   (524288+) and cannot read seeded files owned by 1000. The seed already
   avoids the worst case by `pg_dump`/`pg_restore`ing rather than byte-copying
   Postgres. `--userns=keep-id` and idmapped mounts are the fixes if it bites.

**Acceptance.** A full `branch up` on podman that passes the *existing* branch
acceptance suite unmodified — same URLs, same 200s, same seeded Forgejo, same
per-developer agent route — plus:
- `podman images` in the branch shows the branch's images; `docker images` on
  the root daemon is **unchanged** (recorded before/after).
- production is fingerprinted before and after and is byte-identical.
- `branch down` removes its own worktree **without sudo** (the leaked-worktree
  regression, now a positive assertion).

**Default stays docker.** Both runtimes stay exercised in CI so neither rots.

**Mutations.** M11 unset `DOCKER_HOST` mid-run → the branch lands on the root
daemon → the "production images unchanged" assertion must redden. M12 remove
`:z` → EACCES, named. M13 run the podman path against production's project name
→ refused by the existing guard.

---

## 6. Specced, not built (blocked on you)

| Item | Blocker | Command you would run |
|---|---|---|
| **P5 btrfs qgroup per branch worktree** | needs root | `sudo btrfs quota enable /` then a qgroup per `.worktrees/<name>` |
| **P6 per-branch tailnet auth key** | needs a Tailscale OAuth client | create in the admin console; `branch up` then mints a per-branch **tagged, ephemeral** key instead of every branch sharing one reusable key from `.env` |
| **P7 build cache isolation** | costs a full rebuild per branch | podman (P4) already gives a separate cache; this entry exists only for the docker path |

P5 has a real metadata-performance cost on a large btrfs filesystem — worth
measuring before enabling, not worth guessing about.

---

## 7. Host facts (measured 2026-08-01, not assumed)

```
Bazzite 44 (bazzite-dx-nvidia:stable), rpm-ostree, Kinoite
16 cores / 15.5 GiB RAM / 6 GiB available with one branch up
podman 5.8.4        rootless: true
  graphRoot  /home/supergoodname77/.local/share/containers/storage
  driver     overlay      cgroups v2 / systemd      netavark
podman.socket (user)  enabled + active
  /run/user/1000/podman/podman.sock  srw-rw----  supergoodname77
SELinux             Enforcing
/dev/net/tun        crw-rw-rw-           <- sidecar can open it rootless
cgroup delegation   cpu io memory pids   <- mem/cpu/pids limits work rootless
docker compose      v5.3.1
docker (root)       29.6.2, overlayfs, cgroupns, NO userns-remap
subuid/subgid       supergoodname77:524288:65536
```

---

## 8. Explicitly out of scope

- **A VPS or remote host.** It buys kernel-level blast-radius protection and
  costs the property that makes this system good: a branch is seeded from
  production's *live* state by sharing btrfs extents on the same filesystem
  (2.6 GB in 5.5 s). Across a network that becomes a ≥21 s transfer plus either
  continuous replication or a stale snapshot — and a branch seeded from last
  night's snapshot is a test of a copy, not of production. Revisit a *local*
  microVM only after P1–P4 land and something still escapes.
- **The shared `.git` object store.** Worktrees share `.git`; `gc`, hooks and
  force-push are shared. Real, but a different problem.
- **The host kernel.** Unavoidable without a VM.

---

## 9. Delivery

Each phase is its own PR, in order, each with: spec → plan → TDD → two
adversarial reviewers → fixer → regression suite. **Nothing merges without
review.** P1–P3 need no root and land first; P4 ships behind a flag with the
suite green on both runtimes.
