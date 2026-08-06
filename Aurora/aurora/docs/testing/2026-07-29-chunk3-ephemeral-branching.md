# Chunk 3 — what is proven, what is not

Companion to `docs/implementations/2026-07-29-chunk3-ephemeral-branching.md`.
This file answers one question: **which claims about ephemeral branching are
backed by something that executed, and which are not.**

Written this way because the alternative has burned this project repeatedly. At
least ten tests across Chunks 1 and 2 passed while testing nothing — a vacuous
project filter, an `inspect.getsource()` check satisfied by a docstring, a
decoy that reimplemented the logic it claimed to pin, a universal `pytest.skip`
that made a Critical-severity gate inert at every invocation its plan
contained, and a conformance test that went red exactly when a branch was
*correct*. "The suite is green" is not evidence. What follows is.

---

## Suite counts, measured

All measured 2026-07-30 at the Tier B commit. `<deployed label>` is
production's current compose project.

| Invocation | Result |
|---|---|
| `AURORA_PROJECT=<label> pytest -q` | **572 passed, 22 skipped, 1 xfailed** |
| `pytest -q` (no `AURORA_PROJECT`) | 14 failed, 544 passed, 22 skipped, 15 errors |
| `AURORA_PROJECT=<label> AURORA_ACCEPTANCE_STACK=1 pytest tests/test_branch_acceptance.py` | **17 passed, 1 xfailed** |
| `AURORA_PROJECT=<label> AURORA_EXPECT_TIER_B=1 pytest tests/test_branch_acceptance.py` | **14 passed, 12 skipped, 2 xfailed, 1 xpassed** — or 3 xfailed and no xpass. §14 is a race; both outcomes were measured. |

Row 2 is Task 0's harness working as designed, not a regression:
`production_snapshot()` refuses to snapshot a project with no containers, so
every test that touches the harness errors loudly when the label is wrong. The
two *original* failures in that row are Chunk 2's undeployed rename. Do not
"fix" them and do not remove the strict-xfail marker on
`test_declared_bind_sources_match_runtime`; see
`docs/post-implementation-steps.md`.

The 22 skips are the two opt-in tiers: 12 for Tier A1, 10 for Tier B. Neither
is silent — see each tier's section.

---

## Tier A0 — proven, unconditionally, on every run

Six tests. No branch stack, no worktree, no residue: each leaves the host
exactly as it found it.

| Property | How it is proven |
|---|---|
| A branch with no auth key is a **config-time** error | Real `docker compose -f compose.yml -f compose.branch.yml config` against the committed overlay: `required variable TS_AUTHKEY is missing a value`. Paired with a **control** that the same command succeeds once a key is supplied, so a compose that refused everything could not pass. |
| `aurora branch up` refuses before creating anything | The refusal message is asserted for all three of `$AURORA_TS_AUTHKEY`, `TS_AUTHKEY_BRANCH` and the *consequence* ("a keyless sidecar stays `Logged out.`"), and production's `.worktrees/` listing is compared either side of the refusal. |
| A sidecar given an **invalid** key **exits**, it does not linger | A real `tailscale/tailscale` container in a throwaway `br-` project, polled to `exited`, with `invalid key` **and** `failed to auth tailscale` in its logs. Torn down in the test. This **corrects** the plan's trap 9. |
| Tier B is genuinely blocked, and the remediation is written down | Three legs: fails if an operator demands Tier B without a key; fails if a key has appeared (so "blocked" cannot silently become "forgotten"); fails if the remediation leaves `docs/post-implementation-steps.md`. |
| The live-stack tier's opt-in is not a silent omission | Asserts the measured blocker is still recorded in `docs/issues/chunk3-spec-deltas.md`, by name and by symptom. |
| `dev-admin` cannot start from a clean checkout | Static assertion over `compose.yml` and the filesystem: the read-only `/app` bind, the nested mount, and the absent mountpoint. Includes a **control** that the sibling `developers.yaml` mount still has its mountpoint. |

---

## Tier A1 — proven by one real branch stack, opt-in

`AURORA_ACCEPTANCE_STACK=1`. Twelve tests over one real up/down cycle: a
14-container branch stack, minted from a real `git worktree add`, seeded from
production's live state, running beside production, then destroyed.

**What was stubbed, and nothing else.** Three steps, all of which need tailnet
ingress and all of which are Tier B: `await_tailnet`, `await_https`,
`reconcile`. Plus the sidecar image, replaced with a container that holds the
network namespace open (see below). Everything else executed for real:
`git worktree add`, the rendered branch `.env`, the seed, `docker compose up
--wait postgres`, the Postgres restore, `docker compose up -d` for the whole
stack, and `aurora branch down`.

| Property | Evidence |
|---|---|
| **Isolation** | Every container carries `com.docker.compose.project=br-acceptance` *and* a name in the branch's namespace, and the set of branch names is disjoint from production's. The name leg is the one that matters: every service that declared `container_name` declares a **daemon-global** name, so a missed `!reset` would steal production's. |
| **Zero published ports** | `docker compose -p br-acceptance ps --format json`: every `Publishers` entry empty. Asserted *by name* for `agent-authz`, `arcadedb` and `fjell` — the three that publish in production and declare no `container_name`, i.e. the ones a sloppy overlay misses — so the test cannot pass by inspecting none of them. Spec §5.1: unrepresentable, not merely avoided. |
| **Seeding** | `docker exec` into the branch's own Forgejo, querying its own SQLite for the organisation `obsidura` and the repository `aurora`. Both verified present in production's live database while the plan was written; neither is a value this code could invent. |
| **Path relativity (§5.2)** | Every `hermes` bind resolves inside the branch worktree and none reaches into production's checkout, with **both sides** `Path.resolve()`d and parentage checked via `Path.parents`. Allowed external binds (`/var/run/docker.sock`) are exempted through `conftest.ALLOWED_EXTERNAL_BINDS`, and the test asserts it checked at least one real bind. |
| **Service DNS in the sidecar namespace** | `docker exec` into the branch's Caddy — which runs `network_mode: service:tailscale` — reaching `http://forgejo:3000/`. This is why `FORGEJO_UPSTREAM=forgejo:3000` works, and it is what `TS_ACCEPT_DNS=true` would break. |
| **Production availability (§10.3)** | A background thread polling production's `/git/` every 2 s for the entire up/down cycle. Zero non-200 responses, over a sample the test asserts is non-trivial. `/` is deliberately not polled: it answers 401 by design, and an assertion that tolerated 401 would tolerate an outage. |
| **The seed did not mutate production** | sha256 of production's `forgejo/gitea/gitea.db` **and** `gitea.db-wal`, before and after. `-shm` excluded, with the measurement that forces it (finding N6). |
| **Cross-wiring (§5.4)** | The worktree's `origin` names production and not the branch; the installed `pre-push` hook rejects a push aimed at a branch forge, asserted on its **marker string** — git reports the same exit 1 for a missing hook, so a non-zero exit does not prove the hook ran. Neither URL is printed: production's `origin` carries a credential. |
| **Teardown** | Zero containers, volumes **and** networks carrying the branch project afterwards, from a teardown that is asserted to have actually removed something. |
| **Production unchanged** | `assert_production_unchanged`, from a snapshot **the test captured itself** — never the one `branch_down` takes internally. If the invariant were checked only by the code under test, moving that check earlier would make it vacuous while every test stayed green. |

### The sidecar stub, stated precisely

The `tailscale` service is replaced by an `alpine` container that does nothing
but hold the network namespace open. This is honest for exactly one reason: the
property under test is spec §4.2's namespace sharing — Caddy keeps `eth0` on
the project bridge and `127.0.0.11` in `resolv.conf`, and therefore resolves
`forgejo:3000` — and a stub holds that namespace identically to the real
sidecar. What a stub **cannot** do is carry tailnet traffic or obtain a
certificate. Nothing in the suite claims it does.

A real sidecar with a fabricated key was tried first and does not work: it
exits, taking the namespace with it (Tier A0 records that measurement).

---

## Tier B — proven by one real tailnet node, opt-in

`AURORA_EXPECT_TIER_B=1`. One real branch, `tierb`, run 2026-07-30 against the
ephemeral auth key the user supplied in production's `.env`.

**What Tier B changes, and it changes nothing else.** The `tailscale` service
is the real image with a real key, instead of Tier A1's `alpine`
namespace-holder — so `await_tailnet`, `await_https` and `reconcile` **run**
instead of being replaced by recorders. Same `branch_up`, same overlay, same
seed, same teardown. Tier B therefore does **not** re-prove isolation,
published ports, seeding, path relativity, service DNS, non-mutation or
cross-wiring: Tier A1 owns those, and duplicating them would only mean two
tests reddening for one cause. It re-measures exactly two invariants, because
a real sidecar with `NET_ADMIN`/`NET_RAW`/`/dev/net/tun` is the configuration
most able to disturb them: production's availability, and zero `br-*` residue.

| # | The six assertions | Result |
|---|---|---|
| 1 | node reaches `Running` in `tailscale status` | **PROVEN** |
| 2 | Caddy obtains the branch's own certificate from the branch's tailscaled | **PROVEN** |
| 3 | `https://aurora-<name>.<suffix>/git/` serves the branch's own forge | **PROVEN, one substitution** |
| 4 | `/agent/<user>/` proves `AGENT_UPSTREAM_MODE=service` reached the branch `.env` | **NOT PROVEN** — `xfail`, §14 |
| 5 | reachable from inside production's Hermes container (§10.3) | **PROVEN** |
| 6 | ephemeral node deregisters after teardown | **NOT PROVEN IN-TEST** — it happens ~1 h later, not on teardown; `xfail`, §15 |

Run **five** times on 2026-07-30 — `tierb`, `tierb2`, `tierb3`, `tierb4`,
`tierb5`, a new name each time because §15 means the previous run's node still
held the old one. Assertions 1, 2, 3 and 5 passed on every run that reached
them. Assertion 4 failed on every run. Assertion 6 failed on every run.
`branch up` itself failed on two of the four runs that reached it, which is
§14's race.

### How the proven ones are proven

| # | Evidence |
|---|---|
| 1 | Two independent vantage points. The branch's own tailscaled over its own socket reports `BackendState == "Running"` and `Self.DNSName == aurora-tierb.<suffix>`; production's tailscaled lists that DNS name as a peer. Matched on `DNSName`, not `HostName` — this tailnet already holds a peer whose `HostName` is `localhost`. The peer list is also asserted NOT to contain the name *before* the branch existed, so presence is a measured transition. `await_tailnet` — a shipped function never executed before this run — is the same check inside `branch up`. |
| 2 | A TLS handshake from the host using the **system trust store**, so obtaining the certificate at all means chain and hostname verification passed. Its SANs name the branch and not production; its serial differs from production's, fetched in the same run. It can only have come from the branch's tailscaled: Tailscale's certificate API issues only for the requesting node's own name, and the branch's Caddy is asserted to reach `/var/run/tailscale` through the project-scoped `tailscale_sock` **volume** rather than a host bind — production's Caddy uses the same path for the host's socket, so the difference is invisible from inside the container and has to be asserted from outside. |
| 3 | See the substitution below. |
| 5 | `docker exec` into **production's** Hermes container, `curl` to `https://aurora-tierb.<suffix>/git/` → 200. Not asked from the host: the host *is* production's tailnet node, so a request from here says nothing about a bridge-networked container's reach. Paired with a control — the same probe against production's own URL — so a failure could not be confused with "that container has no HTTPS egress". |

### Assertion 3: the substitution, and why it is not a weakening

The specification asked for `/git/` returning HTML containing `obsidura` and
`aurora`. **Measured against PRODUCTION on 2026-07-30: its own `/git/`
contains neither string**, nor does `/git/explore/repos` (anonymous, renders
"Sign in") and `/git/obsidura` is a 404 to a logged-out client. Both are
private and reachable only behind an OIDC session, which is deferred (§10).
Tier A1 already proves they are in the branch's own database.

What is asserted instead is harder to satisfy by accident and is the property
`/git/` was chosen to demonstrate — that the branch's URL reaches the
**branch's** forge:

* the page's `appUrl`, rendered by Forgejo from its own ROOT_URL, is the
  branch's URL — a branch that inherited `FORGEJO_URL` would render
  production's here, which is exactly finding N1;
* production's domain appears nowhere in the body;
* the title carries `[BRANCH: tierb]` from `FORGEJO_APP_NAME` (spec §5.4
  layer 3), and production's identical page does not.

All three are compared against production's live page fetched in the same run,
so none can pass by matching something both forges emit.

### Why Tier B is opt-in, and why that is not the Chunk 2 skip

Same reason as Tier A1 and no other: every run leaves a branch worktree only
root can remove (§1). It also registers a real node on the tailnet, and §15 is
about what that costs. The opt-in is not silent:
`test_tier_b_has_its_credential_and_a_written_way_to_run_it` runs
unconditionally and reddens if the credential or the run instructions
disappear, the two blocked assertions are `xfail` rather than
skips, and the Tier B fixture **raises** rather than skipping if the tier is
demanded and cannot run. Neither marker is strict, and each says why in its own
`reason`: assertion 4's blocker is an intermittent race, assertion 6's is a
control-plane timer, and a strict marker on either makes the suite flap between
FAILED and XPASS. `docs/issues/chunk3-spec-deltas.md` §14 carries the
instruction to restore strictness once the race is fixed.

---

## NOT proven — blocked on the teardown defect

* **The second full up/down cycle.** The plan asks for two, because a teardown
  that leaves residue only shows up on the second one. It cannot run: the first
  cycle's worktree cannot be removed (`docs/issues/chunk3-spec-deltas.md` §1),
  and `branch up` refuses to build on top of an existing worktree. Docker-object
  residue *is* proven clean after one cycle, by three independent enumerations
  (containers, volumes, networks). Filesystem and volume **adoption** on a
  second `up` is not.
* **`branch up --build`.** Every acceptance run used `build=False`; Compose
  still built `br-acceptance-fjell` because that image did not exist, so the
  build path is partly exercised, but a forced rebuild of all three build
  services is not.
* **`branch up` completing successfully**, because `dev-admin` cannot start
  (`docs/issues/chunk3-spec-deltas.md` §13, inherited). Marked
  `xfail(strict=True)` so it fails loudly when fixed.

---

## NOT proven — deliberately out of scope

Both need an interactive browser session, which Tier B does not supply, and
both are recorded in `docs/issues/chunk3-spec-deltas.md` §10 rather than left
to quietly not happen:

* full OIDC login as a seeded user (§10.3);
* the merge-back test.

---

## How the earlier tasks' claims are backed

Task 12 did not re-verify Tasks 0–11; each carries its own mutation table in
`.superpowers/sdd/2026-07-29-chunk3-ephemeral-branching/progress.md`, and the
rule throughout was that **a change is not "pinned" until a named mutation
reddens a named test**. Totals recorded there: 30 mutations for Task 8, 27 for
Task 10, 26 for Task 11 (26 red, zero survivors), with three survivors in Task
9 each *measured* rather than assumed — most importantly that Compose v5.3.1's
`down` is profile-agnostic, which makes the plan's trap 3 stale and moves the
no-residue guarantee onto the label-and-name sweep.

What Task 12 adds is the other half of the artifact-vs-generator pair: those
tables were run against injected runners and fabricated doubles, and this file
is the first time the same code met a real daemon, a real seed and a live
production stack.
