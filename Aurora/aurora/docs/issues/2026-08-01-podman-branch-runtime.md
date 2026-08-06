# Rootless podman as the branch runtime — what was measured

**Date:** 2026-08-01 · **Spec:** `docs/specs/2026-08-01-true-ephemeral-isolation.md` §5 (P4)
**Status:** shipped behind `--runtime podman`; default stays docker

## Run it

1. Unit tier (no daemon, always on):
   `python -m pytest aurora-cli/tests/test_runtime.py`
2. Live tier (two daemons, opt-in):
   `AURORA_PODMAN_LIVE=1 python -m pytest tests/test_podman_runtime.py`
3. Use it: `aurora branch up <name> --runtime podman`, or export
   `AURORA_BRANCH_RUNTIME=podman`.

`AURORA_PODMAN_LIVE` gates `tests/test_podman_runtime.py` because that module
builds an image and creates a compose project. The gate is not silent:
`test_the_podman_live_tier_is_opt_in_and_its_blocker_is_named` runs
unconditionally and asserts this file still explains it.

## Blocker 1 — SELinux is Enforcing

A bind of a `user_home_t` path into a `container_t` process is EACCES:

```
$ podman run --rm -v ~/probe:/probe debian:bookworm-slim cat /probe/sub/file.txt
cat: /probe/sub/file.txt: Permission denied
$ podman run --rm -v ~/probe:/probe:z debian:bookworm-slim cat /probe/sub/file.txt
hello-from-host
```

Same result through `docker compose` against the podman socket, so it is not a
CLI-only effect.

**Fix used: `chcon -R -t container_file_t <worktree>`, host-side, not `:z`.**
`:z` *is* a recursive chcon to that type — measured, the label it leaves is
byte-identical — so nothing is given up. What is gained is that the argument is
a PATH and can be guarded. A blanket `:z` in the compose files could not be:
`dev-admin`, `fjell` and `hermes` bind `/var/run/docker.sock` and `forgejo`
binds `/etc/localtime`, both outside the repository, and `:z` would relabel
those host objects. `relabel_worktree` refuses anything that is not a branch
worktree. It also keeps compose.yml, the overlay and the three `-f` files
byte-identical between runtimes.

Files created later inherit the directory's type — a host-created and a
container-created file under a relabelled directory both came out
`container_file_t` — so one pass before the first `up` is enough.

## Blocker 2 — rootless uid mapping

Postgres (uid 999) on a repo-relative bind, `pgvector/pgvector:pg16`:

```
before:   drwxr-xr-x supergoodname77 supergoodname77  data/postgres
in-container: healthy, stat 999:0, psql works
after:    drwx------ 525286          1000             data/postgres
```

525286 = subuid base 524288 + (999 - 1). **Postgres itself is fine** — the
directory starts empty, the entrypoint chowns it as container-root, and the
seed restores through `pg_dump`/`pg_restore` rather than byte-copying it.

What is not fine is afterwards: uid 1000 can neither read nor unlink that
directory, so `git worktree remove` fails — the leaked-worktree regression
arriving through a different door.

```
$ rm -rf .../data/postgres
rm: cannot remove '.../data/postgres': Permission denied
$ podman unshare rm -rf .../data/postgres      # no sudo
$ ls .../data/postgres
No such file or directory
```

`branch down --runtime podman` runs `podman unshare chown -R 0:0 <worktree>`
before `git worktree remove`.

## The socket, measured both ways

Three services are handed `/var/run/docker.sock`
(`docs/issues/2026-08-01-branch-services-hold-the-docker-socket.md`). Same
container, same bind, two runtimes:

```
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock python:3.14-slim
  -> CONNECTED: HTTP/1.0 200 OK  Api-Version: 1.55  Server: Docker/29.6.2
podman run --rm -v /var/run/docker.sock:/var/run/docker.sock python:3.14-slim
  -> REFUSED: PermissionError [Errno 13] Permission denied
```

Two independent layers deny it, isolated by disabling each in turn:

| flags | result |
|---|---|
| default | refused |
| `--security-opt label=disable` | refused — **DAC alone is sufficient** |
| `--group-add keep-groups` | refused — **SELinux alone is sufficient** |
| both | connected |

`keep-groups` is a podman extension the Docker API Compose speaks cannot
express, so a branch on this runtime cannot reach production's daemon even
though it is still handed the path to it.

**Not yet fixed:** the bind is still *present*. `dev-admin` genuinely needs a
daemon and under podman it now gets EACCES instead of production's socket —
safe, but not useful. Substituting `${AURORA_RUNTIME_SOCKET}` for that bind
source is the next step and needs a compose change, so it is not in this PR.

## Not done, and why

**No full `branch up` was run on this host, on either runtime.**

```
$ ls -ldn <production>/.worktrees
drwxr-xr-x 0 0 ... .worktrees
$ touch <production>/.worktrees/probe
touch: cannot touch '...': Permission denied
```

`branch up` creates its worktree at `<production>/.worktrees/<name>` (decision
D-F). That directory is root-owned — residue of the leaked-worktree defect,
left by the root docker daemon creating bind sources inside earlier branches —
so uid 1000 cannot create anything in it and `branch up` cannot run at all,
on either runtime, until a human clears it with root:

```
sudo chown -R $(id -u):$(id -g) <production>/.worktrees
```

That is the damage P4 stops happening again. It is not damage P4 can undo.

## Known limitation

`aurora branch ls` and `.worktrees/INDEX.md` cover ONE runtime per invocation
(docker unless `--runtime podman`). Merging both wants a seam per daemon
rather than the single `runner` the tests drive; until then a podman branch is
invisible to a default `ls`.
