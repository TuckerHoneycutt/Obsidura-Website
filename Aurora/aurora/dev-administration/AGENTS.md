# dev-administration — agent guide

`dev-admin` provisions one Hermes container per developer behind Forgejo SSO.

**Read `README.md` first.** It has the URL pattern, the command list, and a
Pitfalls section where every entry cost real debugging time. This file is the
short orientation for an agent with no prior context.

## Ground rules

1. **Run `verify` before and after any change.**
   `./scripts/dev-admin.sh verify <user>` — 26 checks, exit 0 = healthy. It
   names the broken component instead of "the site is down". Never declare
   something fixed without a passing run.
2. **Reproduce before theorising.** Both real bugs in this system were found
   by reproducing the symptom, not by reading code. The whole-chain tools
   report a useless final status; `scripts/trace_oidc.py` shows the exact
   failing hop.
3. **Check the docs of the thing you're integrating.** Forgejo publishes
   `GET /swagger.v1.json`; Caddy has `caddy list-modules` and
   `caddy validate`. The `confidential_client` bug existed because a field
   was assumed absent rather than looked up.
4. **Don't hardcode the admin token.** It gets rotated. Read it from the
   stack's `.env` (the wrapper already does).
5. **Never delete developer volumes.** `reset` and `deprovision` preserve
   them by design.

## Commands

```bash
./scripts/dev-admin.sh provision <user> -n "Name" -e email   # onboard, one-liner
./scripts/dev-admin.sh verify <user> [--wait 60] [--json]    # health, exit 0 = ok
./scripts/dev-admin.sh reset <user>                          # teardown, keeps volume+entry
./scripts/dev-admin.sh reconcile                             # converge to developers.yaml
./scripts/dev-admin.sh status
```

Rebuild a broken developer: `reset <user> && reconcile`.

`scripts/dev-admin.sh` wraps `docker run` with the correct host paths and env,
and works from inside the Hermes container (where `docker compose` does not).
Inside the stack, `docker compose run --rm dev-admin <cmd>` is equivalent.

## What is and isn't provisioned

Provisioned automatically: Forgejo account, OAuth2 app, volume, container,
Caddy route, and the OIDC client id/secret written to the container's `.env`.

**Supplied by the developer** through `https://<domain>/agent/<user>/setup`:
their OpenRouter API key and SSH public key. This split is deliberate — do not
"helpfully" add machine-written user secrets or extra config files.

## Architecture facts that constrain changes

- Caddy runs on the **host network** → cannot resolve Docker DNS. Routes must
  use `127.0.0.1:<port>`; ports are `9120 + index` in `developers.yaml` order.
- Caddy regexes are **RE2** — no negative lookahead.
- Host rootfs is read-only (Bazzite) → new bind mounts under `/app` fail. Use
  `docker exec` or named volumes. The owners map is written under `/output`
  for exactly this reason.
- Hermes drops the reverse-proxy prefix on its post-login redirect, and its
  login page hardcodes an unprefixed `/auth/login` href; Caddy compensates
  for both. Deliberate workarounds, not upstreamed.
- Hermes derives the cookie `Secure` flag **and the cookie name prefix**
  from the forwarded scheme, so `FORWARDED_ALLOW_IPS` + `X-Forwarded-Proto`
  are load-bearing, not cosmetic. Get them wrong and login silently loops.
- After `docker build`, you must **recreate** (not restart) the container.

## Authorization — read before touching Caddy routes

Each agent is locked to one Forgejo account by the `agent-authz` service,
called from Caddy via `forward_auth`. **Neither Hermes nor Forgejo does this
for you**: Hermes' OIDC plugin authenticates but has no user allowlist, and
Forgejo has no per-OAuth2-app restriction. Remove or bypass the gate and
every agent becomes reachable by every account.

Rules that are easy to break while editing `caddy_utils.py`:

- A **401 must fall through** to Hermes so it can start the OIDC flow.
  Intercepting it breaks first-time sign-in — nobody has a session yet.
- Only **403** is blocked (valid session, wrong user).
- Stale-cookie recovery must exist on **both** the outer proxy and the
  inner `handle_response` proxy, or a garbage cookie resurfaces as a 503.
- Use `respond "..." 403` for the denial, never `file_server` — that
  answers 200 and makes denials look like successes.

Verify with `scripts/isolation_test.py` (needs two accounts), and note that
`verify` → `authz.gate` fails if the service is down or an agent has no
registered owner.

## Layout

| Path | Purpose |
|---|---|
| `dev_administration/cli.py` | typer CLI — all commands |
| `dev_administration/provision.py` | provision / reconcile / deprovision |
| `dev_administration/verify.py` | the 26 checks (`run_checks()`) |
| `dev_administration/caddy_utils.py` | generates `agents.conf`, owners map, chooser/denied pages |
| `dev_administration/forgejo_utils.py` | OAuth2 app CRUD |
| `dev_administration/forgejo_org.py` | users, orgs, teams, branch protection |
| `scripts/` | wrapper + debugging tools |
| `developers.yaml` | desired state |
| `../agent-authz/authz.py` | per-agent authorization gate (separate service) |
| `../agent-authz/data/owners.json` | agent → owner map, written by `reconcile` |

`verify.py` is the single source of the checks; `scripts/pipeline_check.py`
imports `run_checks()` so the CLI and the script cannot drift. Add new checks
in `verify.py` only.

## Debugging a login problem

Start with `verify`, then escalate:

| Tool | Use |
|---|---|
| `scripts/trace_oidc.py <user> <pass>` | hop-by-hop trace — **best first tool** |
| `scripts/e2e_login.py <user> <pass>` | real login through the whole chain |
| `scripts/spa_check.py <user> <pass>` | catches "200 but broken page" |
| `scripts/cookie_probe.py <user> <pass>` | cookie names the real flow sets |

`{"detail":"Auth provider 'self-hosted' unreachable"}` has three different
causes — see README → Pitfalls. Don't guess between them; `verify` tells you
which one it is.

Expected noise: `verify` deliberately triggers one stale-cookie failure per
run, so one `provider_unreachable` line per run in the auth log is normal and
the suite accounts for it.

## Composability

Non-interactive and idempotent by design:

- Cron: `0 * * * * cd /app && python -m dev_administration.cli reconcile`
- Master Hermes: `terminal("dev-admin status")`, `terminal("dev-admin verify alice --json")`
- Events go through the `Notifier` protocol for future alerting.

## History

`docs/implementations/2026-07-26-multi-developer-provisioning.md` in the
`aurora` repo records what was built, how it diverged from the spec, and a
list of approaches that **did not work** — check it before retrying something
that looks obvious.
