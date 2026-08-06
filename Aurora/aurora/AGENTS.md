# Aurora — agent guide

A company-as-code stack on one host, reachable only over a Tailnet. Forgejo is
both the git host and the identity provider; every developer gets their own
agent container behind it.

**The one thing to know before you touch anything: you can mint a complete
second copy of this stack, test in it, and destroy it.** Do that instead of
testing against production. It takes about ten minutes and costs nothing.

`README.md` is the tour. `USERGUIDE.md` is for operating production.
`aurora-cli/README.md` says where the branch tooling's code lives.

## Ground rules

1. **Test in a branch, not in production.** A branch is a real stack — its own
   Forgejo, its own agents, its own Tailscale name, seeded from production's
   live state. If your change touches `compose.yml`, a service, or anything
   `dev-admin` writes, a branch is the only honest test.
2. **`ops/docker-guard` will refuse you, and it is right.** It sits ahead of
   `docker` on `PATH` and blocks destructive verbs that cannot prove they are
   scoped to a `br-*` project. Do not route around it, do not call
   `/usr/bin/docker`, do not write the deletion into the product and invoke it.
   `AURORA_ALLOW_PROD=1` exists and is a **human's** escape hatch.
3. **Verify after committing, not before.** Several gates walk `git ls-files`
   and are blind to untracked files. A green run on a dirty tree measures a
   tree that is about to stop existing.
4. **Never commit from a tree another agent is writing to.** Check `git status`
   and commit explicit paths (`git commit -- <path>`). This has already gone
   wrong: 1,126 lines of another agent's in-progress work were swept into a
   commit whose message said "README".
5. **Merging to `main` is the owner's call**, not yours. Open a PR.
6. **A fix is not pinned until a named mutation reddens it.** Break the thing
   deliberately, watch the test fail, revert, record it.

## The loop

```bash
./aurora branch up <name> --from <ref> --devs <user>   # ~10 min, full stack
./aurora branch access <name>                          # its URLs and how to reach them
./aurora branch ls                                     # what is running
./aurora branch shell <name> <service>                 # a shell inside it
./aurora branch rebuild <name> <service>               # rebuild one service in place
./aurora branch overlay <name>                          # re-render the overlay after adding a developer
./aurora branch down <name>                            # destroy it
```

`up` creates a worktree at `.worktrees/<name>`, renders it its own `.env`,
seeds it from production by **reading only**, and brings the stack up as
Compose project `br-<name>` at `https://aurora-<name>.<tailnet>/`. It writes
`BRANCH-ACCESS.md` into the worktree and refreshes `.worktrees/INDEX.md`, so
an agent with the repo mounted can discover what exists without being told.

**A branch cannot collide with production structurally, not carefully.** Every
project is forced into the `br-` namespace, the generated `compose.branch.yml`
`!reset`s every `container_name` and every `ports` entry so a branch publishes
no host port at all, and every destructive path proves its target is
branch-scoped before issuing a command.

## Three things `up` refuses to guess

| Needs | Why it refuses instead of defaulting |
|---|---|
| A tailnet key: an OAuth client in `TS_OAUTH_CLIENT_ID`/`TS_OAUTH_CLIENT_SECRET` (per-branch, tagged, ephemeral — preferred), else `TS_AUTHKEY_BRANCH`, else `$AURORA_TS_AUTHKEY` | A `tailscaled` with no key does not fail — it starts, sits `Logged out.`, and the branch reports success with a dead URL. |
| `--devs <user>` | `all` starts every developer's agent in every branch; `none` gives a branch whose `/agent/` URLs are all dead. Both are silently wrong. |
| `--from <ref>` when the branch name is new | Without it the worktree branches from the checkout's `HEAD`, which on production is a detached deploy ref. |

`--devs` must name someone in `developers.yaml`. An unknown name renders
`COMPOSE_PROFILES=agent-<typo>`, which activates nothing and is not an error
anywhere in Compose.

## Gotchas that have actually bitten

| Symptom | Cause and fix |
|---|---|
| `./aurora: .venv/bin/python: No such file` | A fresh checkout has no venv. `AURORA_PYTHON=/usr/bin/python3 ./aurora …` — the launcher supports it for exactly this. |
| `--from <ref> … but '<name>' already exists` | `branch down` destroys the stack and the worktree but **keeps the git branch ref**. `git branch -D <name>` first, or pick a new name. |
| `branch down` leaves the directory | The daemon creates bind sources inside it as root, so the tool cannot remove them. `sudo rm -rf .worktrees/<name> && git worktree prune`. |
| A re-run registers as `<name>-1` and hangs | An ephemeral node deregisters about an hour after teardown, not at teardown. Use a fresh name within that window. |
| Every `/agent/…` route in the branch 502s | `reconcile` intermittently fails on a *seeded* branch — it inherits production's OAuth2 apps but not their secrets, and dies before writing `agents.conf`. `docs/issues/chunk3-spec-deltas.md` §14. |
| A developer provisioned into a RUNNING branch takes a host port | `up` renders `compose.branch.yml` once, from the services that existed then, so a later `hermes-<user>` keeps the base file's `container_name` and its published `127.0.0.1:<port>:9119` -- both daemon-global, neither an error in Compose. Run `./aurora branch overlay <name>` after provisioning; `--check` exits 1 without writing. |
| A branch build changed production's image | Fixed 2026-07-31. `compose.branch.yml` now resets `image:` for services that also `build:`, so a branch gets `br-<name>-<service>` instead of sharing `agent-authz:local`. If you add a service with **both** `build:` and an explicit `image:`, regenerate the overlay or `test_every_shared_image_tag_is_reset` will say so. |

## How long `up` takes, and why

**53 seconds**, measured end to end on this host with `docker events` (not
estimated). If you have heard "several minutes", that is the Tier B acceptance
*cycle* — up, six assertions, teardown — not `up`.

| phase | cost | what |
|---|---:|---|
| worktree + `.env` render | 4 s | |
| seed | 12 s | 2.6 GB in **5.6 s** — btrfs reflink, so it is nearly free. Most of this phase is waiting for the branch's Postgres to report healthy. |
| `pg_restore` + image build | 2 s | builds are layer-cached; only the retag costs anything |
| `compose up` (13 containers) | 27 s | create and start are instant; this is `depends_on: service_healthy` |
| tailnet + HTTPS + reconcile | 7 s | node registration, certificate, Caddy config |

**About 20 s of that is healthcheck polling latency**, not work: every
healthcheck is `interval: 10s`, and Postgres and Redis are actually ready in
about a second, so each `service_healthy` edge waits for the next probe.

Dropping the interval in the branch overlay would cut it, and it is
**deliberately not done**. A branch is a test *of* production; Chunk 2 fixed a
real defect where `dev-admin` raced Forgejo's startup, and that is precisely
the class of bug that only appears at production's timings. Faster
healthchecks would buy 20 seconds and hide startup races. Seeding and
building, the two things that look expensive, are not.

## When `up` fails

**The half-built branch is left up on purpose** — it is the only artefact you
can debug from. Read the error, inspect it, then `./aurora branch down <name>`.
Nothing is rolled back for you, and nothing touches production.

Production is asserted unchanged throughout, so a failed `up` is never a
production incident. If you think it was one, measure before saying so:
`docker ps`, `/git/` should answer 200.

## Running the tests

There is no system pytest.

```bash
AURORA_PROJECT=<live project> .venv/bin/python -m pytest      # ~3 min, no containers
bash ops/guardtest.sh                                         # the docker guard, against a stub
bash ops/devspawntest.sh                                      # the developer spawn surface, against a stub
```

`AURORA_PROJECT` must name the project the **deployed** containers carry, or
two tests fail for reasons that are not yours.

| Tier | Enable with | Creates |
|---|---|---|
| default | — | nothing |
| A1 | `AURORA_ACCEPTANCE_STACK=1` | one real branch stack, measured and destroyed |
| B | `AURORA_EXPECT_TIER_B=1` | the same, plus its own tailnet identity and certificate |

Both higher tiers are `br-*` scoped, tear down after themselves, and snapshot
production before and assert it unchanged after. **Never test the guard
against the real daemon** — `ops/guardtest.sh` uses a stub, because a guard
tested against a live daemon has its failure mode as the thing it guards
against.
