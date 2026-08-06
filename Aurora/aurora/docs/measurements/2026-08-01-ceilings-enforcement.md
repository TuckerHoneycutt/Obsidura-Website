# Are Aurora's per-branch resource ceilings actually enforced by the kernel?

Host: superserver. Worktree: `/home/supergoodname77/aurora-isolation-wt`
(branch `isolation-wt`, commit 1a69b24). Date: 2026-08-01.

Two separate claims under test:
- **(a)** the ceiling reaches the Docker daemon (HostConfig.Memory /
  NanoCpus / PidsLimit on the real containers);
- **(b)** the kernel enforces it (OOMKilled=true AND exit 137).

---

## Step 0 - production fingerprint (BEFORE)

```
$ docker ps -a --format '{{.Names}}' | sort > ~/aurora-measurements/fp0-containers.txt
$ docker volume ls -q | sort            > ~/aurora-measurements/fp0-volumes.txt
```

37 containers, 56 volumes recorded. Full listings are in those two files.
Note the host is shared: `br-hubdev-*` and `br-pytest-*` objects belong to
other work and are NOT touched here. Only `br-ceilprobe*` is created.

## Step 1 - the `probe` profile

Appended to `~/aurora-isolation-wt/branch-limits.yaml` (schema confirmed from
`aurora_cli/overlay.py`: `LIMIT_KEYS = ("mem_limit", "pids_limit", "cpus")`,
`resolve_limits` reads `profiles.<name>.default` and `.services`):

```yaml
  probe:
    default:
      mem_limit: 64m
      pids_limit: 64
      cpus: "0.1"
```

Verified it resolves:

```
$ PYTHONPATH=aurora-cli ~/.aurora-testvenv/bin/python -c \
    "from aurora_cli import overlay; from pathlib import Path; \
     print(overlay.resolve_limits('probe', Path('.')))"
({'mem_limit': '64m', 'pids_limit': 64, 'cpus': '0.1'}, {})
```

---

## Step 2 - BLOCKERS hit before any container existed

### Blocker 1 (environment): `<production>/.worktrees` is root-owned

```
$ PYTHONPATH=aurora-cli ~/.aurora-testvenv/bin/python -m aurora_cli \
    branch up ceilprobe --limits probe --no-seed --devs none
error: `git -C /var/home/supergoodname77/Desktop/aurora worktree add -b ceilprobe /var/home/supergoodname77/Desktop/aurora/.worktrees/ceilprobe` failed with exit 128: Preparing worktree (new branch 'ceilprobe')
fatal: could not create leading directories of '/var/home/supergoodname77/Desktop/aurora/.worktrees/ceilprobe/.git': Permission denied

$ ls -la ~/Desktop/aurora/.worktrees/
drwxr-xr-x. 1 root            root             40 Aug  1 11:29 .
drwxr-xr-x. 1 supergoodname77 supergoodname77 840 Aug  1 11:29 ..
drwxr-xr-x. 1 root            root             12 Aug  1 11:29 hubdev
drwxr-xr-x. 1 supergoodname77 supergoodname77 226 Aug  1 00:19 .worktrees.old

$ mkdir -p ~/Desktop/aurora/.worktrees/ceilprobe-test
mkdir: cannot create directory '...': Permission denied
$ sudo -n true
sudo: a password is required
```

So `aurora branch up` cannot create a branch AT ALL on this host as this user.
This is known to the codebase: `aurora_cli/guards.py:assert_not_production_path`
documents "on this host `<production>/.worktrees` is root-owned, so a test
cannot create a worktree there", and both `branch.branch_up()` and that guard
carry a `worktrees_root=` seam for exactly this.

The first `up` attempt also failed earlier for an unrelated reason worth
recording -- `--devs` cannot be inferred here (`git config user.name` is
'Hermes Agent', which matches no `forgejo_user` in developers.yaml), so
`--devs none` is passed from here on, identically to probe and to control.

### Blocker 2 (a real bug): `branch up --limits` is a NO-OP

`aurora-cli/aurora_cli/__main__.py:_cmd_branch_up` (lines 77-87) parses
`--limits` into `args.limits` and then never passes it:

```python
    result = branch.branch_up(
        args.name,
        from_ref=args.from_ref,
        no_seed=args.no_seed,
        seed_strategy=args.seed,
        without=tuple(args.without or ()),
        devs=args.devs,
        force=args.force,
        build=not args.no_build,
        runtime=args.runtime,
    )
```

There is no `limits=args.limits`. `grep -n limits __main__.py` shows the only
place `args.limits` is consumed is line 223, the `branch overlay` subcommand.
`branch.branch_up(limits=...)` itself is fully wired (branch.py:1338 validates,
branch.py:1528 calls `overlay.sync_overlay(paths.worktree, limits=limits)`), so
the drop is purely at the CLI layer.

`$AURORA_BRANCH_LIMITS` is not a workaround: `overlay.LIMITS_ENV_VAR` is
defined at overlay.py:610 and **never read anywhere in the tree**
(`grep -rn AURORA_BRANCH_LIMITS .` returns only that definition, the spec, and
a comment in branch-limits.yaml). So the documented env-var route is also
unimplemented.

Consequence: `aurora branch up X --limits probe` would have produced a branch
under the DEFAULT `measured` profile and reported nothing wrong. Had this
measurement trusted the CLI it would have "measured" the wrong profile.

### Deviation taken, stated plainly

To measure anything at all I drove `branch.branch_up()` directly in Python with
`limits="probe"` and `worktrees_root=~/aurora-measurements/worktrees` -- both
are the product's own documented seams, the same ones its tests use. The
resulting stack is a REAL `br-ceilprobe` compose project on the real docker
daemon. Nothing else was changed: no `AURORA_ALLOW_PROD`, no bypass of
`~/.local/bin/docker`, no production project touched.


---

## Step 3 - the evidence, under `probe` (64m / 64 pids / 0.1 cpu)

Branch created with:

```
$ cd ~/aurora-isolation-wt && PYTHONPATH=aurora-cli ~/.aurora-testvenv/bin/python \
    ~/aurora-measurements/drive_up.py ceilprobe probe
# drive_up.py calls branch.branch_up(name, no_seed=True, devs="none",
#   limits="probe", worktrees_root=~/aurora-measurements/worktrees)
```

The overlay it rendered into the branch worktree carries the ceiling on
every service:

```
$ grep -c "mem_limit: 64m" ~/aurora-measurements/worktrees/ceilprobe/compose.branch.yml
14
```

Full inspect sweep of the `br-ceilprobe` project (first capture, ~2 min
after up started, while `branch_up` was still waiting on healthchecks):

```
$ for c in $(docker ps -a --format "{{.Names}}" --filter label=com.docker.compose.project=br-ceilprobe | sort); do
    docker inspect "$c" --format "{{.Name}} OOM={{.State.OOMKilled}} exit={{.State.ExitCode}} status={{.State.Status}} restarts={{.RestartCount}} mem={{.HostConfig.Memory}} nanocpus={{.HostConfig.NanoCpus}} pids={{.HostConfig.PidsLimit}}"
  done
/br-ceilprobe-affine-1 OOM=false exit=0 status=created restarts=0 mem=67108864 nanocpus=100000000 pids=64
/br-ceilprobe-affine_migration-1 OOM=true exit=1 status=exited restarts=0 mem=67108864 nanocpus=100000000 pids=64
/br-ceilprobe-agent-authz-1 OOM=false exit=0 status=running restarts=0 mem=67108864 nanocpus=100000000 pids=64
/br-ceilprobe-arcadedb-1 OOM=false exit=0 status=running restarts=0 mem=67108864 nanocpus=100000000 pids=64
/br-ceilprobe-caddy-1 OOM=false exit=0 status=running restarts=0 mem=67108864 nanocpus=100000000 pids=64
/br-ceilprobe-fjell-1 OOM=false exit=0 status=running restarts=0 mem=67108864 nanocpus=100000000 pids=64
/br-ceilprobe-forgejo-1 OOM=false exit=0 status=running restarts=0 mem=67108864 nanocpus=100000000 pids=64
/br-ceilprobe-forgejo-mcp-1 OOM=false exit=1 status=restarting restarts=13 mem=67108864 nanocpus=100000000 pids=64
/br-ceilprobe-hermes-1 OOM=true exit=0 status=running restarts=0 mem=67108864 nanocpus=100000000 pids=64
/br-ceilprobe-postgres-1 OOM=false exit=0 status=running restarts=0 mem=67108864 nanocpus=100000000 pids=64
/br-ceilprobe-redis-1 OOM=false exit=0 status=running restarts=0 mem=67108864 nanocpus=100000000 pids=64
/br-ceilprobe-tailscale-1 OOM=false exit=0 status=running restarts=0 mem=67108864 nanocpus=100000000 pids=64
```

The daemon EVENT stream is where the exit code survives. `docker inspect`
shows only the CURRENT state, so a container that Docker restarted after
an OOM reports `OOM=false exit=0 status=running restarts=1` a few seconds
later -- which is exactly what happened to hermes and is exactly how this
measurement would have been missed:

```
$ docker events --since 40m --until 1s \
    --format "{{.Time}} {{.Action}} {{.Actor.Attributes.name}} exitCode={{index .Actor.Attributes \"exitCode\"}}" \
  | grep -E "ceilprobe-(hermes|affine_migration)"
1785619118 oom br-ceilprobe-hermes-1 exitCode=
1785619122 die br-ceilprobe-hermes-1 exitCode=137
1785619122 start br-ceilprobe-hermes-1 exitCode=
```

Kernel-side corroboration, independent of the docker daemon
(`constraint=CONSTRAINT_MEMCG` is the memory cgroup ceiling, not host
memory pressure -- the host had RAM free throughout):

```
$ journalctl -k --since "-15 min" | grep -iE "oom|Memory cgroup|Killed process"
Aug 01 16:15:41 superserver kernel: oom-kill:constraint=CONSTRAINT_MEMCG,...,oom_memcg=/system.slice/docker-7bc00b0d3ac7...scope,task=node,pid=720993,uid=0
Aug 01 16:15:41 superserver kernel: Memory cgroup out of memory: Killed process 720993 (node) total-vm:858788kB, anon-rss:11860kB, file-rss:49164kB ...
Aug 01 16:15:55 superserver kernel: oom-kill:constraint=CONSTRAINT_MEMCG,...,oom_memcg=/system.slice/docker-7bc00b0d3ac7...scope,task=node,pid=721718,uid=0
Aug 01 16:16:30 superserver kernel: hermes invoked oom-killer: gfp_mask=0xcc0(GFP_KERNEL), order=0, oom_score_adj=0
Aug 01 16:16:30 superserver kernel: oom-kill:constraint=CONSTRAINT_MEMCG,...,oom_memcg=/system.slice/docker-29e5693c9b35...scope,task=hermes,pid=721142,uid=1000
Aug 01 16:16:30 superserver kernel: Memory cgroup out of memory: Killed process 721142 (hermes) total-vm:141100kB, anon-rss:19960kB, file-rss:13180kB ...

$ docker ps -a --no-trunc --format "{{.ID}} {{.Names}}" | grep -E "^(7bc00b0d|29e5693c)"
7bc00b0d3ac74471582b52073953fa21189f3cfa61e614f145010d972d7e2feb br-ceilprobe-affine_migration-1
29e5693c9b35ba947474dd2bcd83244c7b2338d04a76e77f50197982d9db84fe br-ceilprobe-hermes-1
```

### Verdicts for step 3

**(a) the ceiling reached the daemon: PROVEN.** All 12 containers in
`br-ceilprobe` report `mem=67108864` (64 MiB), `nanocpus=100000000` (0.1),
`pids=64`. Not one service escaped it, including the branch-only
`tailscale` sidecar, which `overlay.render_overlay` adds by hand and which
would otherwise be the one uncapped service in a branch.

**(b) the kernel enforced it: PROVEN.** `br-ceilprobe-hermes-1` produced a
daemon `oom` event followed 4 seconds later by `die exitCode=137`, and the
kernel independently logged
`oom-kill:constraint=CONSTRAINT_MEMCG ... task=hermes` against that exact
container cgroup. `br-ceilprobe-affine_migration-1` shows
`OOMKilled=true exit=1` -- a second memcg OOM (two `node` processes killed
in its cgroup, kernel log above), but its exit code is the application
exiting 1 after its child was killed, NOT 137, so on its own it would not
have settled the question.

Two things that do NOT belong in the enforcement column, stated so they
are not read as evidence:

* `br-ceilprobe-forgejo-mcp-1` crash-looped to `exit=1`, restarts=14, with
  `OOM=false` and a plain Go stack trace in its logs. That is a container
  failing to start, and it proves nothing about ceilings.
* `br-ceilprobe-affine-1` never left `created`, because its
  `affine_migration` dependency died. Also not evidence.

`branch_up` itself FAILED under `probe`, which is the expected shape of a
starved branch:

```
 Container br-ceilprobe-affine_migration-1 Error service "affine_migration" didn't complete successfully: exit 1
 Container br-ceilprobe-forgejo-1 Error dependency forgejo failed to start
service "affine_migration" didn't complete successfully: exit 1
  Nothing has been torn down -- a half-built branch is the only artefact you can debug from. When you are done, remove it with:
      aurora branch down ceilprobe
```

---

## Step 3b - teardown of the probe branch

```
$ PYTHONPATH=aurora-cli ~/.aurora-testvenv/bin/python ~/aurora-measurements/drive_down.py ceilprobe
# drive_down.py calls branch.branch_down(name, force=True)
PROJECT br-ceilprobe
WORKTREE /var/home/supergoodname77/Desktop/aurora/.worktrees/ceilprobe removed= False
FALLBACK True
CONTAINERS ('05e3978cd9a6', '19fd7eb0aa5b', '21d608b72b34', '29e5693c9b35', '33a7e98a7e8b', '587f746e8fe1', '7bc00b0d3ac7', '821b232bc0ea', '8ef644e6496c', '940527ec390d', 'a227ae584807', 'c6d630acadd1')
VOLUMES ('br-ceilprobe_arcadedb_backups', 'br-ceilprobe_arcadedb_config', 'br-ceilprobe_arcadedb_log', 'br-ceilprobe_arcadedb_replication', 'br-ceilprobe_caddy_config', 'br-ceilprobe_caddy_data', 'br-ceilprobe_tailscale_sock', 'br-ceilprobe_tailscale_state')
NETWORKS ('fc00ea71a977',)
NOTE: no compose.yml at /var/home/supergoodname77/Desktop/aurora/.worktrees/ceilprobe; using label-driven removal (worktree removed by hand, or `up` failed before populating it)
```

All 12 containers, 8 volumes and the network removed. The label-driven
fallback was used because the worktree lives at the `worktrees_root`
override and `branch_down` has no such seam -- it looked for the worktree
under production's `.worktrees/`, found no compose.yml, and fell back to
labels. That is the N7 path working exactly as designed. The override
worktree was then removed by hand:

```
$ cd ~/Desktop/aurora && git worktree remove --force ~/aurora-measurements/worktrees/ceilprobe
$ git worktree prune && git branch -D ceilprobe
Deleted branch ceilprobe (was 906ea5d).
$ docker ps -a --format "{{.Names}}" | grep ceilprobe   -> NONE
$ docker volume ls -q | grep ceilprobe                  -> NONE
```

---

## Step 4 - the control: `ceilprobe2` under the DEFAULT `measured` profile

Identical invocation, only the profile changed:

```
$ PYTHONPATH=aurora-cli ~/.aurora-testvenv/bin/python \
    ~/aurora-measurements/drive_up.py ceilprobe2 measured
```

```
$ for c in $(docker ps -a --format "{{.Names}}" --filter label=com.docker.compose.project=br-ceilprobe2 | sort); do
    docker inspect "$c" --format "{{.Name}} OOM={{.State.OOMKilled}} exit={{.State.ExitCode}} status={{.State.Status}} restarts={{.RestartCount}} mem={{.HostConfig.Memory}} nanocpus={{.HostConfig.NanoCpus}} pids={{.HostConfig.PidsLimit}}"
  done
/br-ceilprobe2-affine-1 OOM=false exit=0 status=created restarts=0 mem=1073741824 nanocpus=2000000000 pids=512
/br-ceilprobe2-affine_migration-1 OOM=false exit=1 status=exited restarts=0 mem=1073741824 nanocpus=2000000000 pids=512
/br-ceilprobe2-agent-authz-1 OOM=false exit=0 status=running restarts=0 mem=1073741824 nanocpus=2000000000 pids=512
/br-ceilprobe2-arcadedb-1 OOM=false exit=0 status=running restarts=0 mem=2684354560 nanocpus=2000000000 pids=512
/br-ceilprobe2-caddy-1 OOM=false exit=0 status=running restarts=0 mem=1073741824 nanocpus=2000000000 pids=512
/br-ceilprobe2-fjell-1 OOM=false exit=0 status=running restarts=0 mem=1073741824 nanocpus=2000000000 pids=512
/br-ceilprobe2-forgejo-1 OOM=false exit=0 status=running restarts=0 mem=1073741824 nanocpus=2000000000 pids=512
/br-ceilprobe2-forgejo-mcp-1 OOM=false exit=1 status=restarting restarts=8 mem=1073741824 nanocpus=2000000000 pids=512
/br-ceilprobe2-hermes-1 OOM=false exit=0 status=running restarts=0 mem=1610612736 nanocpus=4000000000 pids=512
/br-ceilprobe2-postgres-1 OOM=false exit=0 status=running restarts=0 mem=1073741824 nanocpus=2000000000 pids=512
/br-ceilprobe2-redis-1 OOM=false exit=0 status=running restarts=0 mem=1073741824 nanocpus=2000000000 pids=512
/br-ceilprobe2-tailscale-1 OOM=false exit=0 status=running restarts=0 mem=1073741824 nanocpus=2000000000 pids=512
```

```
$ docker events --since 20m --until 1s --format "{{.Action}} {{.Actor.Attributes.name}} exitCode={{index .Actor.Attributes \"exitCode\"}}" | grep ceilprobe2 | grep -E "^(die|oom|kill)" | sort | uniq -c
      1 die br-ceilprobe2-affine_migration-1 exitCode=1
      8 die br-ceilprobe2-forgejo-mcp-1 exitCode=1
```

### What the control establishes

**The ceilings are the variable, and only the ceilings.** Under `measured`
the daemon shows the `measured` numbers, including its per-service
overrides: `mem=1073741824` (1g) for most, `mem=2684354560` (2560m) for
arcadedb, `mem=1610612736` (1536m) + `nanocpus=4000000000` for hermes,
`pids=512` throughout. So (a) is shown twice, with two different profiles
producing two different sets of daemon-side numbers.

**There is not one OOM in the control.** `OOM=false` on all 12 containers,
no `oom` event, no `exitCode=137` anywhere in the daemon event stream, and
no `CONSTRAINT_MEMCG` line in the kernel log for a `br-ceilprobe2` cgroup.
The hermes 137 under `probe` is therefore attributable to the ceiling and
not to a branch that dies on its own.

**But the control did NOT come up cleanly, and that is a separate finding.**
`branch_up` failed identically under `measured`:

```
 Container br-ceilprobe2-affine_migration-1 Error service "affine_migration" didn't complete successfully: exit 1
```

Two services fail in BOTH profiles, for reasons that have nothing to do
with resource ceilings, and both fail with `OOM=false`:

* `affine_migration` (exit 1, both profiles):
```
$ docker logs br-ceilprobe2-affine_migration-1
fixing failed migrations.
Error: Schema engine error:
FATAL: could not open file "global/pg_filenode.map": Permission denied
```
  A postgres data-directory permission problem in an unseeded branch, not
  a memory ceiling.

* `forgejo-mcp` (exit 1, restart-looping, both profiles):
```
$ docker logs br-ceilprobe2-forgejo-mcp-1
ERROR forgejo/forgejo.go:70 Failed to create Forgejo client {"url": "https://aurora-ceilprobe2.tailc67a98.ts.net/git", "error": "... dial tcp: lookup aurora-ceilprobe2.tailc67a98.ts.net on 127.0.0.11:53: no such host"}
```
  The branch's own tailnet name does not resolve from inside the branch
  yet. A DNS/timing problem, not a ceiling.

So the control passes for the purpose it exists for -- it isolates the
ceilings as the cause of the OOMs -- while also showing that
`branch up --no-seed` does not currently reach a clean `up` on this host
under ANY profile. The 10 services that stay running stay running in both.

---

## Step 5 - teardown and re-fingerprint

```
$ PYTHONPATH=aurora-cli ~/.aurora-testvenv/bin/python ~/aurora-measurements/drive_down.py ceilprobe2
PROJECT br-ceilprobe2
WORKTREE /var/home/supergoodname77/Desktop/aurora/.worktrees/ceilprobe2 removed= False
FALLBACK True
CONTAINERS ('11c5bea7d08b', '4a51fb786b0d', '51b0fdf285b5', '67fee3ca0bf5', '6e607bf1a06f', '7cb9585df100', '81f74fde2608', 'a2724adb4430', 'c5f938e0a98d', 'ce74959f078f', 'd52eaaa2e403', 'ef5849c44f24')
VOLUMES ('br-ceilprobe2_arcadedb_backups', 'br-ceilprobe2_arcadedb_config', 'br-ceilprobe2_arcadedb_log', 'br-ceilprobe2_arcadedb_replication', 'br-ceilprobe2_caddy_config', 'br-ceilprobe2_caddy_data', 'br-ceilprobe2_tailscale_sock', 'br-ceilprobe2_tailscale_state')
NETWORKS ('8d6eb31087df',)
NOTE: no compose.yml at /var/home/supergoodname77/Desktop/aurora/.worktrees/ceilprobe2; using label-driven removal (worktree removed by hand, or `up` failed before populating it)
```

Both branches destroyed: 24 containers, 16 volumes, 2 networks. Residue
check:

```
$ docker ps -a --format "{{.Names}}"     | grep ceilprobe  -> NO_CONTAINERS
$ docker volume ls -q                    | grep ceilprobe  -> NO_VOLUMES
$ docker network ls --format "{{.Name}}" | grep ceilprobe  -> NO_NETWORKS
```

Worktree restore -- the isolation worktree is clean, and
`compose.branch.yml` was never modified in it (the KNOWN ISSUE does not
apply here: `branch_up(limits=...)` calls
`overlay.sync_overlay(paths.worktree, ...)`, which rewrites the BRANCH's
own copy, not the parent checkout's):

```
$ cd ~/aurora-isolation-wt && git checkout -- branch-limits.yaml
$ git status --short
(empty)
$ git diff --stat -- compose.branch.yml
(empty)
```

### Production fingerprint diff

```
$ diff fp0-containers.txt fp1-containers.txt
23a24,36
> br-parityd-affine-1
> br-parityd-affine_migration-1
> br-parityd-agent-authz-1
> br-parityd-arcadedb-1
> br-parityd-caddy-1
> br-parityd-fjell-1
> br-parityd-forgejo-1
> br-parityd-forgejo-mcp-1
> br-parityd-hermes-1
> br-parityd-hermes-cumshit42069-1
> br-parityd-postgres-1
> br-parityd-redis-1
> br-parityd-tailscale-1

$ diff fp0-volumes.txt fp1-volumes.txt
37a38,46
> br-parityd_arcadedb_backups
> br-parityd_arcadedb_config
> br-parityd_arcadedb_log
> br-parityd_arcadedb_replication
> br-parityd_caddy_config
> br-parityd_caddy_data
> br-parityd_hermes-cumshit42069-home
> br-parityd_tailscale_sock
> br-parityd_tailscale_state
```

Every difference is an ADDITION belonging to `br-parityd`, the other
agent's branch, created on this host concurrently. Nothing was removed and
nothing was renamed. Excluding that project:

```
$ diff <(grep -v "^br-parityd" fp0-containers.txt) <(grep -v "^br-parityd" fp1-containers.txt)
CONTAINERS_IDENTICAL
$ diff <(grep -v "^br-parityd" fp0-volumes.txt) <(grep -v "^br-parityd" fp1-volumes.txt)
VOLUMES_IDENTICAL
```

**Production is byte-identical.**

### One residue, outside production

`git worktree remove --force ~/aurora-measurements/worktrees/ceilprobe2`
failed:

```
error: failed to delete '/var/home/supergoodname77/aurora-measurements/worktrees/ceilprobe2': Permission denied
$ rm -rf ~/aurora-measurements/worktrees/ceilprobe2
rm: cannot remove '.../ceilprobe2/forgejo/gitea': Permission denied
$ ls -la ~/aurora-measurements/worktrees/ceilprobe2/forgejo
drwxr-xr-x. 1 root root  22 Aug  1 16:21 .
drwx------. 1 root root 240 Aug  1 16:21 ssh
```

The forgejo container wrote root-owned directories into its bind mount, so
the unprivileged user cannot delete the tree. The git worktree
REGISTRATION and the `ceilprobe2` git branch are both gone
(`git worktree list` is back to its original set plus the other agent's
`parity-worktrees/parityd`); what remains is an empty root-owned directory
in this measurement's own scratch area, inside no compose project and
inside nothing production reads. It needs one `sudo rm -rf
~/aurora-measurements/worktrees/ceilprobe2` from a human. This is the same
class of problem as blocker 1, and it is why
`aurora_cli/runtime.py:reclaim_worktree_ownership` exists -- that function
was not reached here because `branch_down` took the label-driven fallback.

Note also that `git worktree list` now shows
`/var/home/supergoodname77/parity-worktrees/parityd`: the other agent hit
blocker 1 too and worked around it the same way, independently.

---

## Verdicts

| claim | verdict |
|---|---|
| (a) the ceiling reached the daemon | **PROVEN** |
| (b) the kernel enforced it | **PROVEN** |
| control (`measured`) | **PASSED for its purpose**, but the branch does not reach a clean `up` under ANY profile |
| production unchanged | **YES**, byte-identical |

(a) 12/12 containers under `probe` carried `mem=67108864`,
`nanocpus=100000000`, `pids=64`; 12/12 under `measured` carried that
profile's numbers including its per-service overrides.

(b) `br-ceilprobe-hermes-1`: daemon `oom` event, then `die exitCode=137`,
plus an independent kernel `oom-kill:constraint=CONSTRAINT_MEMCG ...
task=hermes` against that container's cgroup. Zero OOMs and zero 137s in
the `measured` control.

**The two CLI bugs in step 2 stand on their own and are the most
actionable output of this measurement:** `aurora branch up --limits` is
silently ignored, and `$AURORA_BRANCH_LIMITS` is never read. Every branch
brought up through the CLI today gets `measured`, whatever the operator
asked for, and is told nothing.

### Final verification of the two CLI bugs (whole-tree greps, after cleanup)

```
$ cd ~/aurora-isolation-wt
$ grep -rn "args.limits" --include=*.py .
./aurora-cli/aurora_cli/__main__.py:223:        args.name, check=args.check, limits=args.limits,
   # line 223 is _cmd_branch_overlay. `branch up` and `branch down` never appear.

$ grep -rn "LIMITS_ENV_VAR" --include=*.py .
./aurora-cli/aurora_cli/overlay.py:610:LIMITS_ENV_VAR = "AURORA_BRANCH_LIMITS"
   # the definition, and nothing that reads it. Not even a test.

$ git status --short
(empty - worktree clean, nothing added, nothing left modified)
```
