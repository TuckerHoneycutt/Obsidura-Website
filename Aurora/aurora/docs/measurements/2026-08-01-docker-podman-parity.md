# Aurora docker/podman branch parity check

Worktree: `/home/supergoodname77/wt-parity` @ 1a69b24 (detached)
CLI invocation used throughout:

    cd ~/wt-parity && PYTHONPATH=aurora-cli ~/.aurora-testvenv/bin/python -m aurora_cli branch <sub>

Branch names used: parityseed, parityd, parityp, parityrefuse.

## Step 0 - production fingerprint (before)

Captured to:
- `~/aurora-measurements/parity-fp0-containers.txt`  (37 docker containers)
- `~/aurora-measurements/parity-fp0-volumes.txt`     (56 docker volumes)
- `~/aurora-measurements/parity-fp0-networks.txt`    (9 docker networks)
- `~/aurora-measurements/parity-fp0-pcontainers.txt` (0 podman containers)
- `~/aurora-measurements/parity-fp0-pvolumes.txt`    (8 podman volumes)

    $ docker ps -a --format '{{.Names}}' | sort
    affine_migration_job
    affine_postgres
    affine_redis
    affine_server
    aurora-agent-authz-1
    aurora-arcadedb-1
    aurora-caddy-1
    aurora-fjell-1
    br-hubdev-affine-1
    br-hubdev-affine_migration-1
    br-hubdev-agent-authz-1
    br-hubdev-arcadedb-1
    br-hubdev-caddy-1
    br-hubdev-dev-admin-1
    br-hubdev-fjell-1
    br-hubdev-forgejo-1
    br-hubdev-forgejo-mcp-1
    br-hubdev-hermes-1
    br-hubdev-hermes-atestuser-1
    br-hubdev-hermes-cumshit42069-1
    br-hubdev-postgres-1
    br-hubdev-redis-1
    br-hubdev-tailscale-1
    br-pytest-373957-1-alpha-1
    br-pytest-373957-1-beta-1
    br-pytest-373957-1-beta-2
    br-pytest-559444-1-alpha-1
    br-pytest-559444-1-beta-1
    br-pytest-559444-1-beta-2
    br-pytest-653272-1-alpha-1
    br-pytest-653272-1-beta-1
    br-pytest-653272-1-beta-2
    dev-admin
    forgejo
    forgejo-mcp
    hermes
    hermes-cumshit42069

    $ podman ps -a --format '{{.Names}}' | sort
    (empty)
    $ podman volume ls -q | sort
    38b8eda883e55a0711154d1cdc617c987e29208d6d21ed5550b7008561c2e3c7
    b786a7cd728eb1d11e24e62e3fdbe80d5181673f6913b6d1667cf4d48e5ce8b4
    tai_caddy_config
    tai_caddy_data
    tai_chromadb-data
    tai_model-cache
    tai_ntfy-cache
    tai_searxng-data

Note: `br-hubdev-*` and `br-pytest-*` objects pre-existed and belong to
another agent / prior pytest runs. They are not mine and are not touched.

## BLOCKER B1 - `branch up` cannot run at all on this host (pre-existing, NOT a podman regression)

First attempt, exactly the command in the task brief:

    $ cd ~/wt-parity && PYTHONPATH=aurora-cli ~/.aurora-testvenv/bin/python \
        -m aurora_cli branch up parityseed
    error: cannot tell which developer this branch is for, and refusing to guess.
    Resolution was attempted two ways: $AURORA_DEV is unset, and `git config
    user.name` is 'Hermes Agent', which matches no `forgejo_user` in
    developers.yaml (cumshit42069). Pass --devs <user>, --devs all or --devs none
    explicitly. [...]

developers.yaml has exactly one entry, `cumshit42069`, so every run below adds
`--devs cumshit42069`. That is a deliberate documented deviation from the brief's
literal command line; it is a refusal-to-guess, not a defect.

Second attempt, with `--devs cumshit42069`:

    EXIT=1 ELAPSED=1s
    error: `git -C /var/home/supergoodname77/Desktop/aurora worktree add -b parityseed
    /var/home/supergoodname77/Desktop/aurora/.worktrees/parityseed` failed with exit 128:
    Preparing worktree (new branch 'parityseed')
    fatal: could not create leading directories of
    '/var/home/supergoodname77/Desktop/aurora/.worktrees/parityseed/.git': Permission denied

Cause:

    $ stat -c '%n %U:%G %a' ~/Desktop/aurora/.worktrees ~/Desktop/aurora/.worktrees/*
    /home/supergoodname77/Desktop/aurora/.worktrees        root:root 755
    /home/supergoodname77/Desktop/aurora/.worktrees/hubdev root:root 755
    $ touch ~/Desktop/aurora/.worktrees/.probe
    touch: cannot touch '...': Permission denied
    $ sudo -n true
    sudo: a password is required

`identity.py` hardcodes the branch worktree location (`_WORKTREE_DIRNAME =
".worktrees"`, decision D-F: `<production checkout>/.worktrees/<name>`). There is
no environment override. The directory and the pre-existing `hubdev` worktree in
it are owned by root:root 0755, so uid 1000 cannot create a worktree there.

Consequences and scope:
  * This blocks EVERY `aurora branch up`, on BOTH runtimes, before either
    daemon is contacted. It is not caused by the podman refactor and it is not
    caused by anything this task did - it predates the first command run here
    (mtime Aug 1 11:29).
  * Repairing it needs `sudo chown` inside production's checkout. That is both
    (a) touching production and (b) impossible without a password here. NOT
    attempted. Reported instead.
  * `branch up` failed CLEANLY: exit 1, no `br-parityseed` object on either
    daemon, no worktree. Verified below.

Because of B1 the docker-vs-podman comparison cannot be run through the real
CLI. It is run instead through `branch.branch_up(worktrees_root=...)`, which
`aurora-cli/aurora_cli/runtime.py:366` and `guards.py:109` document as the
supported seam for exactly this ("the same seam the suite uses"), and which
`tests/test_branch_acceptance.py:349` uses to drive real end-to-end branches.
Every other argument is the real one and both daemons are the real ones.

## Step 5 - the documented seeded-podman refusal  [PASS, run through the REAL CLI]

Run before the other steps because it creates nothing and so cannot perturb them.

    $ cd ~/wt-parity && PYTHONPATH=aurora-cli ~/.aurora-testvenv/bin/python \
        -m aurora_cli branch up parityrefuse --runtime podman
    error: --runtime podman cannot seed. Seeding runs `docker volume create` and
    `docker run` against the ROOT docker daemon (aurora_cli.seed has no runtime
    seam), and one container cannot mount production's agent-home volume from the
    root daemon alongside this branch's volume in the rootless podman store.
    Without this refusal the seed would plant labelled `br-` volumes full of
    production's agent homes inside PRODUCTION's daemon and then fail anyway,
    after the branch was already running.
          aurora branch up parityrefuse --runtime podman --no-seed
      gives an unseeded branch on podman, which works today. Seeded branches stay
      on docker until aurora_cli.seed learns to stream between daemons.
    EXIT=1

Identical output with `--devs cumshit42069` added (EXIT=1). Note the refusal
fires BEFORE the `--devs` resolution error that blocked step 1, which is
independent evidence that it sits early in `branch_up` - source order confirms
it: `branch.py:1364` vs `resolve_devs` at ~1418.

Residue check, BOTH daemons:

    $ docker ps -a --format '{{.Names}}'      | grep -i parityrefuse -> no match
    $ docker volume ls -q                     | grep -i parityrefuse -> no match
    $ docker network ls --format '{{.Name}}'  | grep -i parityrefuse -> no match
    $ podman ps -a --format '{{.Names}}'      | grep -i parityrefuse -> no match
    $ podman volume ls -q                     | grep -i parityrefuse -> no match
    $ podman network ls --format '{{.Name}}'  | grep -i parityrefuse -> no match
    $ ls -d ~/Desktop/aurora/.worktrees/parityrefuse
    ls: cannot access '...': No such file or directory
    $ git -C ~/Desktop/aurora branch --list 'parity*'
      parityseed        <- from the step-1 FAILURE, not from parityrefuse
    $ git -C ~/Desktop/aurora worktree list | grep -i parity
    /var/home/supergoodname77/wt-parity  1a69b24 (detached HEAD)   <- mine, pre-existing

VERDICT: the refusal fires, and it fires EARLY - nothing at all was created, on
either daemon, in the filesystem, or in git's ref namespace. Both halves hold.

Sharpening contrast worth recording: the docker path in step 1 failed LATER, at
`git worktree add`, and it DID leave a git ref `parityseed` behind pointing at
production HEAD 906ea5d. So `branch_up`'s "everything that can refuse does so
before anything is created" claim holds for the podman-seed refusal specifically,
while a non-refusal failure (B1) still leaks a ref. `git branch -D parityseed`
was attempted and is BLOCKED by this harness's permission classifier, so that
one ref is left behind and is reported rather than silently cleaned.

## Step 1 - SEEDED, DEFAULT (docker) runtime  [PASS - no regression]

Driven through `branch.branch_up(worktrees_root=~/parity-worktrees)` because of
blocker B1. `runtime=None` (i.e. the default is exercised, not `runtime="docker"`),
`no_seed=False`, `from_ref=None` (reuses the existing `parityseed` ref at
production HEAD 906ea5d, which does contain `compose.branch.yml`), `build=True`
(the default), `devs="cumshit42069"`.

    $ ~/.aurora-testvenv/bin/python ~/aurora-measurements/parity_drive.py \
          parityseed - seed -
    {
      "name": "parityseed",
      "runtime_requested": null,
      "no_seed": false,
      "from_ref": null,
      "ok": true,
      "runtime_used": "docker",
      "project": "br-parityseed",
      "worktree": "/home/supergoodname77/parity-worktrees/parityseed",
      "notes": [
        "The pre-push hook is installed at .../parityseed/hooks/pre-push but git
         will NOT run it: git resolves hooks to .../Desktop/aurora/.git/hooks.
         Arm this repository once with:
             git -C /var/home/supergoodname77/Desktop/aurora config core.hooksPath hooks"
      ],
      "seeded": true,
      "url": null,
      "elapsed_s": 55.0
    }

RESULT: SUCCESS. 55.0 s wall clock. `seeded: true`. `runtime_used: "docker"`.

    $ docker compose -p br-parityseed ps -a --format '{{.Service}} {{.State}} {{.Health}} {{.ExitCode}}'
    affine_migration     exited            0
    affine               running           0
    agent-authz          running           0
    arcadedb             running           0
    caddy                running           0
    dev-admin            exited            0
    fjell                running           0
    forgejo-mcp          running           0
    forgejo              running  healthy  0
    hermes-cumshit42069  running           0
    hermes               running           0
    postgres             running  healthy  0
    redis                running  healthy  0
    tailscale            running           0

14 compose services. 12 running, 2 exited(0). The two exits are the one-shot
services and are correct: `affine_migration` is AFFiNE's migration job and
`dev-admin` declares `command: [reconcile]` (branch.py holds it back from the
first `up` precisely because it is a run-to-completion reconcile). Three services
declare healthchecks and all three are `healthy`; the other eleven declare none,
so a blank Health column is absent-by-design, not unknown.

    $ docker volume ls -q | grep parityseed
    br-parityseed_arcadedb_backups      br-parityseed_caddy_config
    br-parityseed_arcadedb_config       br-parityseed_caddy_data
    br-parityseed_arcadedb_log          br-parityseed_hermes-cumshit42069-home
    br-parityseed_arcadedb_replication  br-parityseed_tailscale_sock
                                        br-parityseed_tailscale_state
    (9 volumes)
    $ docker network ls --format '{{.Name}}' | grep parityseed
    br-parityseed_default
    $ cat ~/parity-worktrees/parityseed/.aurora-runtime
    docker

VERDICT ON THE HEADLINE QUESTION: the seam `runtime.py` inserted into every
daemon call did NOT regress the ordinary seeded docker path. It builds, seeds,
starts all 14 services and records its runtime, in 55 s.

Only anomaly: `url: null` on a successful seeded up. Recorded; see step 4.

### Step 1 teardown

    $ cd ~/wt-parity && PYTHONPATH=aurora-cli ~/.aurora-testvenv/bin/python \
        -m aurora_cli branch down parityseed
    DOWN_EXIT=1 ELAPSED=7s
    Traceback (most recent call last):
      ...
      File ".../aurora_cli/__main__.py", line 136, in _cmd_branch_down
        index = branch.write_index()
      File ".../aurora_cli/branch.py", line 2437, in write_index
      File ".../aurora_cli/branch.py", line 2389, in _write_document
        path.write_text(text, encoding="utf-8")
    PermissionError: [Errno 13] Permission denied:
        '/var/home/supergoodname77/Desktop/aurora/.worktrees/INDEX.md'

DEFECT D1 (consequence of B1, but its own bug): `branch down` tore the stack down
correctly and THEN died with a bare `PermissionError` traceback while writing
`INDEX.md`. Two things are wrong independently of B1: the index write is not
guarded the way every other refusal in this codebase is, and it turns a
successful teardown into a non-zero exit with a stack trace, which a caller
cannot distinguish from "teardown failed". Not podman-related.

The teardown ITSELF was clean on the daemon:

    $ docker ps -a --format '{{.Names}}'     | grep parityseed -> no match
    $ docker volume ls -q                    | grep parityseed -> no match
    $ docker network ls --format '{{.Name}}' | grep parityseed -> no match

DEFECT D2 - the docker path leaks an UNDELETABLE worktree (2.5 GB):

    $ git -C ~/Desktop/aurora worktree remove --force ~/parity-worktrees/parityseed
    error: failed to delete '/var/home/supergoodname77/parity-worktrees/parityseed':
           Permission denied
    RC=255
    $ du -sh ~/parity-worktrees/parityseed
    2.5G
    $ find ~/parity-worktrees/parityseed ! -user supergoodname77 -printf '%u:%g %m %p\n'
    root:root     755 .../affine/data
    polkitd:root  700 .../affine/data/postgres
    root:root     755 .../affine/data/storage
    root:root     644 .../agent-authz/data/owners.json
    root:root     700 .../forgejo/ssh
    root:root     755 .../arcadedb
    root:root     755 .../.agent-env

The ROOT docker daemon's containers write as real uid 0, so uid 1000 cannot
delete the tree afterwards. git removed its administrative entry but left the
directory. This is a KNOWN, PRE-EXISTING defect - `tests/test_branch_acceptance.py`
documents it verbatim ("until the teardown defect is fixed, a test that used the
real location would leave an undeletable directory inside production's checkout
on every run") and keeps its scratch OUT of `.worktrees` because of it.

This is almost certainly the ORIGIN of blocker B1: `<production>/.worktrees` and
the `hubdev` worktree inside it are root:root today for the same reason.

Note the asymmetry that matters for this task: the PODMAN path has a fix for
exactly this (`runtime.reclaim_worktree_ownership`, `podman unshare chown -R 0:0`,
called BEFORE the worktree removal at branch.py:1938) and the docker path has
none. On this axis podman is BETTER than docker, not merely equivalent.

Reclaimed here with a root container (`docker run --rm -v ...:/w alpine rm -rf`),
which is not a guarded verb and touches only my own scratch directory.

### GUARD REFUSAL G1 - reclaim attempt refused, NOT routed around

The reclaim described above was attempted and the guard wrapper refused it:

    $ docker run --rm -v /var/home/supergoodname77/parity-worktrees:/w \
          alpine:latest rm -rf /w/parityseed

    docker-guard: REFUSED a destructive docker command that is not
                  provably scoped to a branch (br-*) project.
      command: docker run --rm -v /var/home/supergoodname77/parity-worktrees:/w
               alpine:latest rm -rf /w/parityseed
      project: (none declared)
      [...]
      If you are a human and you mean it:
          AURORA_ALLOW_PROD=1 docker run --rm -v ... rm -rf /w/parityseed
    RC=13

Why it fired: `positional()` flattens the argv to
`['run', 'alpine:latest', 'rm', '-rf', '/w/parityseed']` and `is_destructive()`
is a CONTAINMENT check, so the container's OWN `rm` argument matches the
`("rm",)` entry. The command is not a docker `rm` at all - it is `docker run`.
This is the guard's documented and deliberate failure direction
("Over-matching here costs a human one environment variable; under-matching
costs a production stack"), so it is working as designed, not broken.

Per this task's hard constraint 3 the refusal was NOT worked around: no
`AURORA_ALLOW_PROD`, and no substitute tool was tried to achieve the same
deletion. STOPPED and reported.

CONSEQUENCE / RESIDUE R1: `~/parity-worktrees/parityseed` (2.5 GB, root-owned
subdirectories) still exists and I cannot remove it. Its git administrative
entry IS gone (`git worktree prune` run; `git worktree list` shows no parity
entry). No container, volume or network survives. A human can clear it with:

    AURORA_ALLOW_PROD=1 docker run --rm \
        -v /var/home/supergoodname77/parity-worktrees:/w alpine rm -rf /w/parityseed

or `sudo rm -rf ~/parity-worktrees/parityseed`.

## Step 2 - UNSEEDED, docker  [FAIL - and NOT a podman regression]

    $ ~/.aurora-testvenv/bin/python ~/aurora-measurements/parity_drive.py \
          parityd - noseed -
    { "name": "parityd", "runtime_requested": null, "no_seed": true,
      "ok": false, "error_type": "BranchUpFailed", "elapsed_s": 27.1,
      "error": "branch 'parityd' was not completed: `docker compose -p br-parityd
        -f compose.yml -f compose.branch.yml -f compose.exclude.yml --env-file .env
        up -d --build --scale dev-admin=0` failed with exit 1 in
        /home/supergoodname77/parity-worktrees/parityd:
        [...all images Built, all volumes Created, all containers Created/Started...]
        Container br-parityd-affine_migration-1 Error
        service \"affine_migration\" didn't complete successfully: exit 1
        Nothing has been torn down -- a half-built branch is the only artefact you
        can debug from. When you are done, remove it with:
              aurora branch down parityd" }

    $ docker compose -p br-parityd ps -a --format '{{.Service}} {{.State}} {{.Health}} {{.ExitCode}}'
    affine               created               0
    affine_migration     exited                1     <-- FAILED
    agent-authz          running               0
    arcadedb             running               0
    caddy                running               0
    fjell                running               0
    forgejo-mcp          restarting            0     <-- crashlooping
    forgejo              running     healthy   0
    hermes-cumshit42069  running               0
    hermes               running               0
    postgres             running     healthy   0     <-- healthy but BROKEN
    redis                running     healthy   0
    tailscale            running               0
    (13 services; `dev-admin` is absent because `up` runs with --scale dev-admin=0
     and the run died before it was brought back)

CAUSE - DEFECT D3, `--no-seed` produces an unusable AFFiNE Postgres:

    $ docker logs br-parityd-affine_migration-1
    Datasource "db": PostgreSQL database "affine", schema "public" at "postgres:5432"
    Error: Schema engine error:
    FATAL: could not open file "global/pg_filenode.map": Permission denied
    error Command failed with exit code 1.
    ... at runPrismaMigrations (file:///app/scripts/self-host-predeploy.js:43:3)

    $ docker logs br-parityd-postgres-1 | tail
    ... FATAL:  could not open file "global/pg_filenode.map": Permission denied
    ... LOG:  could not open file "postmaster.pid": Permission denied; continuing anyway
    (repeating every ~10 s - every single backend fails)

The ownership of the bind-mounted data directory is the difference, and it is
visible side by side against the SEEDED tree from step 1:

    $ ls -Zln ~/parity-worktrees/parityd/affine/data/        # step 2, UNSEEDED, failed
    drwx------. 1 1000 1000 system_u:object_r:user_home_t:s0 512 postgres
    $ ls -Zln ~/parity-worktrees/parityseed/affine/data/     # step 1, SEEDED, worked
    drwx------. 1  999    0 system_u:object_r:user_home_t:s0 512 postgres

    $ ls -Zln ~/parity-worktrees/parityd/affine/data/postgres/ | head
    drwx------. 1 1000 1000 ... base
    drwx------. 1 1000 1000 ... global
    -rw-------. 1 1000 1000 ... pg_hba.conf

Seeded, the directory is a copy of production's already-initialised cluster and
carries postgres's own uid 999. Unseeded, the directory is created empty at uid
1000 and the resulting cluster is owned 1000:1000 while the server's backends run
as 999, so every backend gets EACCES. SELinux is not the cause: both trees carry
the same `user_home_t` label and the seeded one works.

`postgres` reports `healthy` throughout, because the healthcheck is
`pg_isready -U affine -d affine` (rendered config above), which only proves the
postmaster is accepting connections - it never opens a relation file. So the
branch's own health signal does NOT catch this.

IS THIS A PODMAN REGRESSION? No, and the evidence is specific:
  * it is a file-ownership property of a bind mount, and `runtime.py` does not
    touch ownership or labels on the docker path at all - `relabel_worktree` and
    `reclaim_worktree_ownership` are both behind `if resolved_runtime.is_podman`
    (branch.py:1570, branch.py:1938);
  * `runtime_used` is `docker` and `Runtime.environ` for docker merely STRIPS
    `DOCKER_HOST`, so these compose calls are byte-identical to pre-refactor ones;
  * step 1 proves the same seam seeds and starts all 14 services fine.
It is a genuine, separate `--no-seed` defect.

CONSEQUENCE FOR THIS TASK: step 2 is the intended fair baseline for step 3,
because `--no-seed` is the only configuration podman supports. It is broken on
docker BEFORE podman is considered.

## Step 3 - UNSEEDED, podman  (attempt 1: blocked by a cold image store)

    $ ~/.aurora-testvenv/bin/python ~/aurora-measurements/parity_drive.py \
          parityp podman noseed -
    { "name": "parityp", "runtime_requested": "podman", "no_seed": true,
      "ok": false, "error_type": "BranchUpFailed",
      "error": "... `docker compose -p br-parityp ... up -d --build --scale dev-admin=0`
        failed with exit 1 ...
        Image arcadedata/arcadedb:26.7.3 Pulling
        Image codeberg.org/goern/forgejo-mcp:v2.30.2 Pulling
        Image ghcr.io/toeverything/affine:stable Pulling
        Image redis Pulling
        Image tailscale/tailscale:latest Pulling
        ...
        Image codeberg.org/goern/forgejo-mcp:v2.30.2 Error manifest unknown
        Image arcadedata/arcadedb:26.7.3 Interrupted
        Error response from daemon: manifest unknown" }

Note the compose command is spelled `docker compose` on BOTH runtimes - the podman
seam is `DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock`, not a different
binary (runtime.py:`DOCKER_HOST_VAR`, `podman_socket`). That is working: the
containers and network below landed in the ROOTLESS PODMAN store, and `docker ps`
shows none of them.

NOT A PODMAN DEFECT - the tag is gone upstream and docker fails identically:

    $ podman pull codeberg.org/goern/forgejo-mcp:v2.30.2
    Error: ... reading manifest v2.30.2 in codeberg.org/goern/forgejo-mcp:
    manifest unknown
    $ docker manifest inspect codeberg.org/goern/forgejo-mcp:v2.30.2
    manifest unknown
    $ docker image inspect codeberg.org/goern/forgejo-mcp:v2.30.2 --format '{{.Id}} {{.Created}}'
    sha256:207daf82da6dc... 2026-07-13T09:54:09Z

So production's docker daemon only has that image because it PULLED IT ON
2026-07-13, before the tag was withdrawn. Any cold store - podman here, or a
rebuilt docker host tomorrow - cannot reproduce it. That is a real supply-chain
exposure for the project, and it is the reason podman fails where docker does
not; it is not the runtime seam.

Partial state left by the failed attempt, on PODMAN only:

    $ podman ps -a --format '{{.Names}} {{.Status}}' | grep parityp
    br-parityp-postgres-1   Up 2 minutes (healthy)
    $ podman network ls --format '{{.Name}}' | grep parityp
    br-parityp_default
    $ podman volume ls -q | grep parityp          -> no match
    $ docker ps -a --format '{{.Names}}' | grep parityp   -> no match  (correct isolation)

Retried below after copying the withdrawn image from docker's cache into the
podman store with `docker save | podman load` (neither verb is destructive;
the guard did not refuse it).

## Step 3 - UNSEEDED, podman  (attempt 2, after seeding podman's image store)

    $ docker save codeberg.org/goern/forgejo-mcp:v2.30.2 | podman load
    Loaded image: codeberg.org/goern/forgejo-mcp:v2.30.2
    $ ~/.aurora-testvenv/bin/python ~/aurora-measurements/parity_drive.py \
          parityp podman noseed -
    { "name": "parityp", "runtime_requested": "podman", "no_seed": true,
      "ok": false, "error_type": "BranchUpFailed", "elapsed_s": 116.6,
      "error": "... up -d --build --scale dev-admin=0 failed with exit 1 ...
        Container br-parityp-affine_migration-1 Error
        service \"affine_migration\" didn't complete successfully: exit 1" }

116.6 s (vs 27.1 s for docker) - the extra time is image PULLS into a cold
rootless store, not the runtime seam.

    $ podman ps -a --format '{{.Names}} {{.State}} {{.Status}} {{.ExitCode}}' | grep parityp
    br-parityp-affine-1               created  Created                    0
    br-parityp-affine_migration-1     exited   Exited (1)                 1
    br-parityp-agent-authz-1          running  Up 2 minutes               0
    br-parityp-arcadedb-1             running  Up 2 minutes               0
    br-parityp-caddy-1                running  Up 2 minutes               0
    br-parityp-fjell-1                running  Up 2 minutes               0
    br-parityp-forgejo-1              running  Up 2 minutes (healthy)     0
    br-parityp-forgejo-mcp-1          stopped  Exited (1)                 1
    br-parityp-hermes-1               running  Up 2 minutes               0
    br-parityp-hermes-cumshit42069-1  running  Up 2 minutes               0
    br-parityp-postgres-1             running  Up 3 minutes (healthy)     0
    br-parityp-redis-1                running  Up 3 minutes (healthy)     0
    br-parityp-tailscale-1            running  Up 2 seconds               0

    $ podman logs br-parityp-postgres-1 | tail
    FATAL:  could not open file "global/pg_filenode.map": Permission denied   (x N)

    $ docker ps -a --format '{{.Names}}' | grep parityp   -> NO MATCH
      (the branch is entirely in the rootless store; the root daemon never saw it)

## Step 4 - DOCKER vs PODMAN, same inputs (`--no-seed`), side by side

Both from the same worktree content, same `--devs`, same `--no-seed`, same
production HEAD ref. Docker = step 2 (`parityd`), podman = step 3 (`parityp`).

  service              docker(state/health/rc)   podman(state/health/rc)   same?
  -------------------  ------------------------  ------------------------  -----
  affine               created            0       created            0      yes
  affine_migration     exited             1       exited             1      yes
  agent-authz          running            0       running            0      yes
  arcadedb             running            0       running            0      yes
  caddy                running            0       running            0      yes
  fjell                running            0       running            0      yes
  forgejo              running  healthy   0       running  healthy   0      yes
  forgejo-mcp          restarting         0       stopped/Up cycling 1      yes*
  hermes               running            0       running            0      yes
  hermes-cumshit42069  running            0       running            0      yes
  postgres             running  healthy   0       running  healthy   0      yes
  redis                running  healthy   0       running  healthy   0      yes
  tailscale            running            0       running            0      yes
  dev-admin            absent (--scale dev-admin=0, run died before restore)  yes

SAME SET OF SERVICES: 13 on both, and the same 13. SAME STATES. SAME HEALTH
(the same three services healthy, the same ten declaring no healthcheck).
SAME OVERALL OUTCOME: `BranchUpFailed`, same cause, same service.

* `forgejo-mcp` looked different only because of WHEN it was sampled. It
  crashloops on both; measured on podman:

    $ podman inspect br-parityp-forgejo-mcp-1 --format '{{.HostConfig.RestartPolicy.Name}} restarts={{.RestartCount}}'
    unless-stopped restarts=1136
    $ for i in 1 2 3; do podman ps -a | grep forgejo-mcp; sleep 6; done
    Exited (1) Less than a second ago
    Exited (1) Less than a second ago
    Up Less than a second

  Docker's `restarting` and podman's alternating `Exited (1)`/`Up` are the same
  crashloop reported by two different formatters. NOT a difference.
  (Cause is unrelated to either runtime: a Go panic in forgejo-mcp, `cmd.go:254`.)

### Every difference found, and its verdict

D-1  TIME: 27.1 s (docker) vs 116.6 s (podman).
     EXPECTED. Cold rootless image store: podman pulled arcadedb, affine,
     redis, tailscale; docker had them cached. Not a seam cost.

D-2  A pull that only docker can satisfy: `codeberg.org/goern/forgejo-mcp:v2.30.2`
     is WITHDRAWN UPSTREAM (`manifest unknown` from podman AND from
     `docker manifest inspect`). Docker succeeds solely from a 2026-07-13 cache
     entry. EXPECTED as a docker/podman difference, but a REAL PROJECT DEFECT in
     its own right: the stack is not reproducible on any cold host.

D-3  WORKTREE OWNERSHIP AFTER `up` - the one genuine podman DEFECT found.
       $ find ~/parity-worktrees/parityp -maxdepth 2 -printf '%u\n' | sort | uniq -c
            94 525287
             1 supergoodname77
       $ ls -Zln ~/parity-worktrees/parityp/.env
       -rw-------. 1 525287 525287 unconfined_u:object_r:container_file_t:s0 3026 .env
       $ ls -ln ~/parity-worktrees/parityseed/.env        # docker, for contrast
       -rw-------. 1 1000 1000 3046 .env
     After a podman `up`, essentially the WHOLE worktree is owned by subuid
     525287 (524288 + 1000 - 1, i.e. container uid 1000), not by the invoking
     user. `.env` is mode 0600, so uid 1000 can no longer read it, and any
     further compose call from the worktree dies:
       $ docker compose -p br-parityp ps
       open /home/supergoodname77/parity-worktrees/parityp/.env: permission denied
     `branch down --runtime podman` therefore cannot use its worktree compose
     path and must fall back to the label-driven teardown. It DOES fall back and
     the teardown is clean (below), so the branch is recoverable - but the
     primary path is broken and the branch is un-inspectable by its own owner.
     DEFECT, podman-specific. Not covered by `reclaim_worktree_ownership`, which
     runs only at `down`, i.e. far too late to help anyone debugging a live branch.

D-4  WORKTREE REMOVAL AT `down` - podman is BETTER than docker.
     docker (step 1): `git worktree remove --force` -> "Permission denied",
       2.5 GB tree left behind, root-owned, unremovable without sudo.
     podman: the same reclaim primitive works and leaves nothing:
       $ podman unshare chown -R 0:0 ~/parity-worktrees/parityp
       chown rc=0
       $ find ~/parity-worktrees/parityp ! -user supergoodname77   -> empty
       $ rm -rf ~/parity-worktrees/parityp                          -> rc=0
     EXPECTED and by design (`runtime.reclaim_worktree_ownership`). Docker has
     no equivalent, which is why blocker B1 exists.

D-5  `affine_migration` / postgres EACCES: IDENTICAL on both runtimes. Defect D3
     of this document, a `--no-seed` defect, NOT a runtime difference.

CONCLUSION FOR STEP 4: for the same inputs docker and podman are EQUIVALENT in
the set of services, their states, their health and their outcome. The only
behavioural differences are (a) timing from a cold image store, (b) an upstream
image withdrawal, (c) podman-only worktree subuid ownership after `up` (defect),
and (d) podman-only worktree reclaim at `down` (improvement).

### Step 3 teardown - DEFECT D4: `branch down --runtime podman` is not complete in one pass

    $ PYTHONPATH=aurora-cli python -m aurora_cli branch down parityp --runtime podman
    DOWN_EXIT=1     (the D1 INDEX.md PermissionError again - and note this
                     traceback SWALLOWS the DownResult report, so the residue
                     notes branch_down computes are never printed to the user)

    $ podman ps -a --format '{{.Names}}' | grep parityp
    br-parityp-tailscale-1                      <-- SURVIVED, and "Up 17 seconds"
    $ podman volume ls -q | grep parityp
    br-parityp_tailscale_state                  <-- SURVIVED
    br-parityp_tailscale_sock                   <-- SURVIVED
    $ podman network ls --format '{{.Name}}' | grep parityp   -> gone (correct)
    $ docker ps -a / volume ls / network ls | grep parity     -> nothing (correct)

The surviving container still carries `com.docker.compose.project: br-parityp`
and was UP 17 seconds after a teardown that ran minutes earlier - it restarted
itself. Its policy is `restart: unless-stopped`, and the two volumes could not be
removed because a running container held them.

Chain: D-3 leaves `.env` owned by subuid 525287 mode 0600 -> the worktree compose
path cannot be used -> `branch down` falls back to the label-driven teardown ->
that fallback stops/removes by name and loses the race against the restart
policy -> container survives -> its volumes survive.

A SECOND invocation cleaned it completely:

    $ PYTHONPATH=aurora-cli python -m aurora_cli branch down parityp --runtime podman
    $ podman ps -a | grep parityp     -> no match
    $ podman volume ls -q | grep parityp -> no match

VERDICT: DEFECT, podman path. Teardown is eventually-correct but not
single-pass, and because D1 hides the report the user is not told what survived.

## Step 6 - teardown and re-fingerprint

    $ diff parity-fp0-containers.txt <(docker ps -a --format '{{.Names}}' | sort)
    IDENTICAL
    $ diff parity-fp0-volumes.txt    <(docker volume ls -q | sort)
    IDENTICAL
    $ diff parity-fp0-networks.txt   <(docker network ls --format '{{.Name}}' | sort)
    IDENTICAL
    $ diff parity-fp0-pcontainers.txt <(podman ps -a --format '{{.Names}}' | sort)
    0a1
    > buildx_buildkit_default
    $ diff parity-fp0-pvolumes.txt   <(podman volume ls -q | sort)
    2a3
    > buildx_buildkit_default_state

PRODUCTION (root docker daemon) IS BYTE-IDENTICAL TO THE STEP 0 FINGERPRINT.
All 37 containers, all 56 volumes, all 9 networks unchanged. `aurora branch ls`
lists only the pre-existing `hubdev` and `pytest-*` branches - none of mine.

Branch images removed from both daemons afterwards (`branch down` does not
remove them; the host is full of stale `br-hubdemo-*`, `br-perf1-*` images from
earlier work, so this is existing behaviour, not a new defect):

    $ docker rmi br-parityseed-fjell br-parityd-fjell br-parityseed-agent-authz \
                 br-parityd-agent-authz br-parityd-dev-admin br-parityseed-dev-admin
    $ podman rmi br-parityp-dev-admin br-parityp-fjell br-parityp-agent-authz
    $ docker images | grep br-parity   -> none
    $ podman images | grep br-parity   -> none

    $ cd ~/wt-parity && git status --short     -> clean
    $ git log --oneline -1                      -> 1a69b24
    $ git -C ~/Desktop/aurora worktree list     -> no parity entries (all pruned)
    $ df -h /var/home                           -> 105G used (was 100G)

### RESIDUE I COULD NOT REMOVE (reported, not hidden)

R1  `~/parity-worktrees/parityseed`  2.5 GB, and `~/parity-worktrees/parityd`
    (now near-empty but undeletable). Root-owned directories written by the ROOT
    docker daemon's containers (defect D2). `rm` fails; the container-based
    reclaim was REFUSED by docker-guard (G1) and was NOT worked around.
    A human clears them with:
        sudo rm -rf ~/parity-worktrees/parityseed ~/parity-worktrees/parityd
    Note `~/parity-worktrees` is MY scratch directory, outside production's
    checkout. Nothing was left in `<production>/.worktrees/`.

R2  git refs `parityd`, `parityp`, `parityseed` in production's repository.
    `branch down` does not delete the ref `up` creates (a defect the acceptance
    suite already records and cleans up by hand). `git branch -D` was attempted
    and is BLOCKED by this harness's permission classifier, so they remain.
    A human clears them with:
        git -C ~/Desktop/aurora branch -D parityd parityp parityseed
    They are refs only: no worktree, no container, no volume, no effect on the
    running production stack.

R3  podman `buildx_buildkit_default` container + `buildx_buildkit_default_state`
    volume. Created by compose's buildx builder during the podman build; not
    present at step 0. Deliberately LEFT: the name is shared infrastructure and
    another agent is concurrently active on this host, so removing it could kill
    an in-flight build. Auto-recreated on demand; safe for a human to drop with
    `podman rm -f buildx_buildkit_default`.

R4  `codeberg.org/goern/forgejo-mcp:v2.30.2` added to the podman image store
    (`docker save | podman load`) so step 3 could run at all. Intentional; see
    step 3. It is the only copy reachable on a cold store, so removing it is
    probably a bad idea.

## CONCLUSIONS

1. DOES THE SEEDED DOCKER PATH STILL WORK?  YES. `branch up parityseed` (default
   runtime, seeded) built, seeded and started all 14 compose services in 55.0 s;
   12 running, 2 correct one-shot exits, all 3 healthchecked services healthy.
   NO REGRESSION from the podman refactor.

2. DOES THE UNSEEDED DOCKER PATH WORK?  NO - `BranchUpFailed`. AFFiNE's
   `affine_migration` exits 1 because the freshly created Postgres data
   directory is owned by uid 1000 while the server's backends run as uid 999,
   so every backend gets EACCES on `global/pg_filenode.map`. Defect D3. It is a
   `--no-seed` defect, not a runtime-seam defect: `runtime.py` touches no
   ownership on the docker path, and step 1 proves the same seam works seeded.
   `postgres` still reports `healthy` because the healthcheck is `pg_isready`.

3. DOES THE PODMAN PATH WORK?  It reaches exactly the same place docker does and
   fails in exactly the same way, for the same reason - so "as well as docker
   does, and no better". It is genuinely running on the rootless daemon
   (`docker ps` never saw any of it). Two podman-only problems on top: the
   worktree ends up owned by subuid 525287 after `up` (D-3, `.env` unreadable),
   and `branch down` needed two passes (D4).

4. ARE DOCKER AND PODMAN EQUIVALENT FOR THE SAME INPUTS?  YES on the thing
   asked: same 13 services, same states, same health, same outcome, same cause.
   Differences: timing (cold store, expected); a withdrawn upstream image only
   docker's cache still holds (expected as a difference, but a real project
   defect); podman-only subuid worktree ownership after `up` (DEFECT);
   podman-only successful worktree reclaim at `down` (IMPROVEMENT over docker);
   `forgejo-mcp` "restarting" vs "Exited(1)" is the SAME crashloop, not a
   difference. Full table in step 4.

5. DOES THE SEEDED-PODMAN REFUSAL FIRE CLEANLY AND EARLY?  YES, both halves.
   The `BranchError` appears with its full explanation, and nothing whatsoever
   was created - no container, volume or network on EITHER daemon, no worktree,
   not even a git ref (which the docker path's later failure DID leave).

6. WAS PRODUCTION UNCHANGED?  YES. The step 0 and step 6 fingerprints of the
   root docker daemon are byte-identical: 37 containers, 56 volumes, 9 networks.

NOT COMPLETED, PLAINLY: the real CLI `aurora branch up` was never able to run,
on either runtime, because `<production>/.worktrees` is root-owned (blocker B1).
Every `up` above went through `branch_up(worktrees_root=...)`, the documented
test seam. Everything downstream of worktree creation is therefore real and
measured; the claim "the real CLI command works end to end on this host" is NOT
established for either runtime, and cannot be until B1 is fixed by a human.
