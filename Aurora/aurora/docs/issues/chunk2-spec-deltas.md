# Chunk 2 spec deltas and the rename mapping

Written 2026-07-29, at the end of Chunk 2.

Two things a reader of the older documents needs: what the project used to be
called, and which claims in the design spec turned out to be false when
someone tried to implement them.

## 1. The rename

The stack was called **`tai-review`** until Chunk 2. That name was an artefact
of the directory the repo happened to be cloned into — `COMPOSE_PROJECT_NAME`
was never set, so Compose derived the project from the directory basename —
and it referred to an unrelated earlier project on the same machine.

| Was | Is |
|---|---|
| `tai-review` (compose project) | `aurora` |
| `tai-review_default` (network) | `aurora_default` |
| `tai-review-caddy-1`, `tai-review-fjell-1`, `tai-review-agent-authz-1`, `tai-review-arcadedb-1` | `aurora-caddy-1`, `aurora-fjell-1`, `aurora-agent-authz-1`, `aurora-arcadedb-1` |
| `tai-review_caddy_data`, `tai-review_arcadedb_*` (volumes) | `aurora_*` |
| `~/Desktop/tai-review` (host path) | `~/Desktop/aurora` |
| `/opt/data/workspace/tai-review` (in-container) | `/opt/data/workspace/aurora` |

Everything under `docs/` written before 2026-07-28 uses the old name and is
left **verbatim**. Those files are dated records of what was observed at the
time; rewriting them would falsify them. The two forward-looking design specs
are the exception — they describe how the system is meant to work *next*, are
read by Chunk 3, and were renamed.

`dev-administration/tests/test_guard_coverage.py` also still contains the old
literals, deliberately: it asserts they are *absent* from the source, so it
has to name them. It now bans the new names too — a regression test that only
forbids a name nobody would type any more is a museum piece.

## 2. Spec claims that were false as written

These were found by trying to implement the spec, and the spec has been
corrected in place. Recorded here because the corrections are easy to miss in
a diff.

### D3: "a branch runs the unmodified production Caddyfile"

**False as written.** Every `reverse_proxy` target in the Caddyfile was a
literal `127.0.0.1` port. Production's Caddy is `network_mode: host`, so those
work; a branch's Caddy is `network_mode: service:tailscale` and shares the
sidecar's network namespace, where no localhost port of the stack exists.
Every route would have been dead.

Fixed in Task 7 by parameterising the upstreams as
`{$AFFINE_UPSTREAM:127.0.0.1:3010}` and so on, with production's values as
defaults. Verified byte-identical `caddy adapt` output before and after with
the variables unset.

### §4.1: the branch `.env` override list was incomplete

The spec enumerates what a branch overrides when rendering its `.env` *from
production's*. `COMPOSE_PROFILES` was missing. Because the branch file is
rendered from production's, anything not explicitly overridden is
**inherited** — so a branch would have started **every** developer's agent,
contradicting D7's "only the requesting developer".

The same hazard as `COMPOSE_PROJECT_NAME`, one variable over. Added to the
list. There is still no machine-readable version of that list; Chunk 3 should
add one, because a blockquote in a spec cannot fail a build.

### §5.2: two absolute bind mounts

`~/.hermes:/opt/data` made every branch share production's agent state, and
`~/Desktop/tai-review:/opt/data/workspace/tai-review` made a branch's Hermes
see production's tree rather than its own worktree. Both are now
repo-relative (M6, Task 8), and the container-side workspace target is
`/opt/data/workspace/aurora` — a stable path that does not encode which
checkout it is.

### F2: `dev-admin` raced Forgejo on every deploy

Not a spec claim, but a standing defect the spec did not anticipate.
`dev-admin` declared `depends_on: [forgejo]` with no condition, so `reconcile`
ran the instant Forgejo's *container* started rather than when Forgejo was
*serving*, and died with `curl` exit 22. It had been failing on every deploy.
Because `dev-admin` reaches Forgejo *through Caddy*, a healthcheck alone
cannot close the window, so `_curl` also retries connection-class failures.

One consequence worth knowing: when Forgejo is genuinely unreachable,
`reconcile` now takes roughly 30 seconds per call to fail rather than failing
fast. That is the right trade for a startup race, but it is a real change in
outage behaviour.
