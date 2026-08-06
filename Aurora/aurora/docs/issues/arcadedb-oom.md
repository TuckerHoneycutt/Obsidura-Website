# arcadedb exited 137

`tai-core-arcadedb` exited with code 137 (SIGKILL) on 2026-07-23. The most
likely cause is the OOM killer: the image ships
`ARCADEDB_OPTS_MEMORY=-Xms2G -Xmx2G` and the host has 15.5GiB total with
roughly 7.7GiB free while the rest of the stack runs.

The service declaration sets `JAVA_OPTS=-Xms512m -Xmx2g`, matching what the
container was actually started with — but this only lowers the **initial**
heap (2G -> 512m). The **maximum** heap is unchanged: `-Xmx2g` and the image
default `-Xmx2G` are the same value (Java heap suffixes are case-insensitive).
Since the maximum is what determines OOM risk, not the initial size, this
declaration does **not** reduce the OOM ceiling. Whether `ARCADEDB_OPTS_MEMORY`
or `JAVA_OPTS` wins when both are present is therefore moot for this
question — either way the max heap arrives at the same 2G figure. The actual
cause of the SIGKILL has **not** been confirmed. Before relying on arcadedb
for anything:

1. Start it and watch `docker events --filter event=oom`.
2. If a lower ceiling is desired, `JAVA_OPTS` must actually be lowered (e.g.
   `-Xmx1g`) rather than left at a value equal to the default, and it must be
   confirmed which of `ARCADEDB_OPTS_MEMORY` / `JAVA_OPTS` the image honors
   when both are set.

## The exited container gets recreated, not adopted — it does not survive as an orphan

The exited container is named `tai-core-arcadedb`. An earlier version of this
doc claimed it "was started outside of this compose project" and that
"Compose has no way to adopt it." **That is backwards — verified:**

```
$ docker inspect tai-core-arcadedb --format '{{index .Config.Labels "com.docker.compose.project"}}'
tai-review
```

It already carries the `tai-review` project label (and
`com.docker.compose.service=arcadedb`). Compose matches existing containers
to services by label, not by name, so it *will* find this container the
moment anyone runs `docker compose up` against the merged file — the old
container does not sit there un-adopted and untouched. What Compose finds,
though, no longer matches what's declared: `tai-core-arcadedb`'s four
non-bind volumes are anonymous, hash-named volumes, not the named volumes
(`arcadedb_backups`, `arcadedb_config`, `arcadedb_log`,
`arcadedb_replication`) declared in `compose.yml` for the `arcadedb`
service, so the computed config hash differs from what the running
container was created with. Compose's response to a config-hash mismatch on
a matched container is to **delete it and recreate it** under the
compose-generated name (`tai-review-arcadedb-1`), backed by the new named
volumes — not to reuse the old container, and not to leave it running
untouched beside the new one.

The predicted **end state is still correct** — new named volumes, old
anonymous volumes orphaned — the mechanism was described wrong: the old
container is deleted as part of an ordinary recreate (matched by label,
rejected by config hash), not left behind because Compose couldn't find it.

Practical impact is low: the old container's full lifetime was
2026-07-23T04:47:33Z to 2026-07-23T04:48:23Z (~50 seconds) before it was
killed, so little to no data could have accumulated in those volumes.
Still, whoever starts the service should expect to start with **empty**
volumes, not to find any prior state.

## No longer "not blocking" — the merge deploy starts this service

`arcadedb` carries `restart: unless-stopped` and no `profiles:` key. That
means it is not opt-in the way a profiled service would be: the deploy step
required at merge time (`docker compose up -d`, no service list — see
`docs/post-implementation-steps.md` §A) starts *every* non-profiled service,
arcadedb included, whether or not anyone has decided to rely on it yet. A
`profiles: ["manual"]` declaration was considered as the honest
declare-without-running fix, but it breaks
`tests/test_repo_conformance.py::test_no_undeclared_containers_in_project`:
that test compares `docker compose config`'s declared services (profiled
services are omitted by default) against every container carrying the
`tai-review` project label — and the exited `tai-core-arcadedb` already
carries that label, so profiling arcadedb out makes it look undeclared.
Verified by making the change locally and re-running
`.venv/bin/python -m pytest tests/ -v`: 1 failed (that test), 5 passed. The
change was reverted; this is a documentation-only fix.

Concretely: the recreation described above, the unconfirmed SIGKILL cause,
and the unlowered heap ceiling are not hypothetical future events contingent
on someone later deciding to "start arcadedb" — they all happen at the
`docker compose up -d` required by the merge itself. Watch
`docker events --filter event=oom` starting from that deploy, and rotate
`ARCADEDB_ROOT_PASSWORD` (`docs/post-implementation-steps.md` §B2) before,
not after, treating the resulting instance as real.
