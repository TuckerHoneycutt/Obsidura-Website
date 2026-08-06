# dev-administration

`dev-admin` — the Aurora orchestrator. Provisions and manages one Hermes
container per developer, each behind Forgejo single sign-on at
`https://<domain>/agent/<username>/`.

Idempotent and non-interactive: safe to run from a shell, from cron, or from
the master orchestrator Hermes.

---

## The URL pattern

Every developer gets exactly two URLs. **Send them the setup form first.**

| URL | What it is |
|---|---|
| `https://<domain>/agent/<username>/setup` | **Start here.** Form where the developer enters their own OpenRouter API key and SSH public key. |
| `https://<domain>/agent/<username>/` | Their Hermes agent. Redirects through Forgejo SSO; usable once the setup form is submitted. |

On this deployment `<domain>` is `superserver.tailc67a98.ts.net`, e.g.
`https://superserver.tailc67a98.ts.net/agent/alice/setup`.

---

## Onboarding a developer (the one-liner)

```bash
./scripts/dev-admin.sh provision alice --display-name "Alice Smith" --email alice@obsidura.local
```

That single command adds the entry to `developers.yaml`, creates the Forgejo
account, creates the OAuth2 app, creates the volume, installs the Aurora
profile, starts the container, writes the Caddy route, registers the agent's
owner for authorization, and then runs all 26 verification checks. It prints:

```
  ✓ User 'alice' ready — Forgejo account + Hermes agent provisioned.
      Forgejo login : alice
      Temp password : <generated>   (must be changed on first login)
      Setup form    : https://superserver.tailc67a98.ts.net/agent/alice/setup
      Agent         : https://superserver.tailc67a98.ts.net/agent/alice/
```

Give the developer the temp password and the **setup form** URL. They then:

1. Open the setup form, paste their OpenRouter API key and SSH public key.
2. Open the agent URL → redirected to Forgejo → log in with the temp password
   (Forgejo forces a change) → land in their dashboard.

### If the developer already made their own Forgejo account

Self-service sign-up is open (Tailnet-only), so a developer can register
themselves at `/git/user/sign_up`. Provision against that existing account:

```bash
./scripts/dev-admin.sh provision alice --forgejo-user alice
```

The account is detected rather than recreated — the summary prints
`Password: unchanged (account already existed)` and no temp password, since
they already have their own. The agent is bound to that Forgejo identity and
no other.

Registration and provisioning are deliberately separate: signing up does
**not** create an agent, so a self-registered user has nowhere to land until
you run `provision`.

Nothing else is provisioned on their behalf. There are no hand-edited `.env`
files or configs to remember: the only machine-written values are the OIDC
client id/secret, which are per-container plumbing, not user secrets.

## Everyday commands

```bash
./scripts/dev-admin.sh provision <user> [-n "Name"] [-e email]  # onboard (add+reconcile+verify)
./scripts/dev-admin.sh verify <user>                            # 26 checks, exit 0 = healthy
./scripts/dev-admin.sh verify <user> --wait 60                  # poll while a container boots
./scripts/dev-admin.sh verify <user> --json                     # machine-readable
./scripts/dev-admin.sh reset <user>                             # tear down container + OAuth2 app
./scripts/dev-admin.sh reconcile                                # converge all devs to developers.yaml
./scripts/dev-admin.sh status                                   # containers, volumes, health
./scripts/dev-admin.sh deprovision <user>                       # stop container, keep volume
./scripts/dev-admin.sh remove <user>                            # drop from developers.yaml only
```

`dev-admin access …` — the seven subcommands that give a developer scoped,
revocable Forgejo access without `FORGEJO_ADMIN_TOKEN`: `authorize`, `mint`,
`ls`, `deauthorize`, `suspend`, `restore`, `revoke`. Two of them are the
*developer's*, not yours, because Forgejo refuses token minting and deletion to
an admin token. Full table, footguns and what `suspend` does not do:
`USERGUIDE.md` §2.

**Rebuild a broken developer from scratch** (keeps their `developers.yaml`
entry and their data volume, rotates the OAuth2 app):

```bash
./scripts/dev-admin.sh reset alice && ./scripts/dev-admin.sh reconcile
```

`verify` exits non-zero on failure, so it composes:

```bash
until ./scripts/dev-admin.sh verify alice; do sleep 5; done
```

### Running without the wrapper

`scripts/dev-admin.sh` just wraps `docker run` with the right mounts and env.
Inside the stack you can equivalently use:

```bash
docker compose run --rm dev-admin <command>
```

The wrapper exists because `docker compose` isn't available from inside the
Hermes container, and because bind mounts must use **host** paths.

---

## How it fits together

```
browser ──► Caddy (host network, TLS)
              │  handle_path /agent/<user>/*
              │  header_up   X-Forwarded-Prefix: /agent/<user>
              │  header_down Location  (re-adds the prefix)
              ├──► 127.0.0.1:<port>  hermes-<user>   (dashboard :9119)
              └──► 127.0.0.1:9080    fjell           (/agent/<user>/setup)

Forgejo ── OIDC issuer, one confidential OAuth2 app per developer
```

- One container per developer: `hermes-<user>`, volume `hermes-<user>-home`.
- Host ports are assigned from `BASE_PORT` (9120), in `developers.yaml` order.
- Caddy is on the **host network**, so it cannot resolve Docker DNS names —
  routes must use `127.0.0.1:<port>`.
- Volumes are **never** deleted automatically; `reset`/`deprovision` preserve
  them and emit a `volume.orphaned` warning.

## Configuration

`developers.yaml` is the desired state:

```yaml
developers:
  - username: alice
    display_name: Alice Smith
    forgejo_user: alice
    email: alice@obsidura.local     # required to auto-create the Forgejo account
```

Environment (from the stack's `.env`):

| Var | Default | Notes |
|---|---|---|
| `FORGEJO_URL` | — | e.g. `https://<domain>/git` |
| `FORGEJO_ADMIN_TOKEN` | — | **must have admin scope** (see pitfalls) |
| `AURORA_PROFILE_URL` | — | git URL of the `aurora-agent` profile repo |
| `DOMAIN_NAME` | — | public hostname |
| `FORGEJO_ORG` | `obsidura` | org that owns shared repos |
| `FORGEJO_DEV_TEAM` | `developers` | read-only team for shared repos |
| `CADDY_CONTAINER` | `aurora-caddy-1` | where `agents.conf` is written |
| `FORGEJO_DEV_PASSWORD` | — | `access mint`/`revoke` only, and never yours: the developer's own password, so a non-interactive run does not prompt. There is no flag for it |
| `DEVELOPERS_YAML` | `developers.yaml` | the roster every command reads |

---

## Per-agent authorization

Each agent is locked to **one** Forgejo account — the one it was
provisioned for. This is enforced by the `agent-authz` service, which Caddy
calls via `forward_auth` before proxying.

It exists because neither upstream component does it:

- Hermes' OIDC plugin **authenticates but does not authorize** — it has no
  user allowlist ("the IDP's own allowlist is authoritative").
- Forgejo has no per-OAuth2-app user restriction.

So without this gate, *any* valid Forgejo account could open *any*
developer's agent. That matters especially with open registration enabled.

How it decides:

| Result | Meaning |
|---|---|
| `204` | caller owns this agent — request proceeds |
| `401` | no/invalid session — passed through so Hermes can start OIDC |
| `403` | valid session, **wrong user** — request blocked |

Matching is on the Forgejo numeric user id (`sub`), not the username, since
usernames can be renamed. The JWT is fully verified (signature via the
issuer JWKS, plus `iss`/`aud`/`exp`), and `aud` is pinned to the agent's own
OAuth2 `client_id` so a token minted for another agent cannot be replayed.

The map lives in `agent-authz/data/owners.json`, written by `reconcile` and
reloaded on change — no restart needed. It **fails closed**: an unknown
agent, an unreachable JWKS, or a missing map denies access.

```bash
# prove isolation holds end to end (needs two Forgejo accounts)
python3 scripts/isolation_test.py <agent> <owner> <owner_pw> <other> <other_pw>
# owner -> 200, non-owner -> 403 on both the dashboard and the API
```

Onboarding a self-registered user: they create their own Forgejo account,
then you run `dev-admin provision <their-forgejo-username>`. The agent is
bound to that account and no other.

---

## Pitfalls

Every item here cost real debugging time. Read before changing anything.

### `{"detail":"Auth provider 'self-hosted' unreachable"}`

This message has **three** distinct causes. Run `verify` first — it
distinguishes them.

1. **Stale browser cookie** (most common after a `reset`). The old session
   cookie holds a value that is no longer a valid JWT; PyJWT raises
   `DecodeError('Not enough segments')` and the plugin reports it as
   "unreachable". Caddy now converts this into a cookie-clearing bounce to
   `/login`, so it self-heals — but a cached page can still show it.
   *Confirm:* `verify` → `http.stale_cookie`. *User fix:* reload, or clear
   cookies for the domain.
2. **OAuth2 app is a public client.** Forgejo omits the `id_token` when a
   `client_secret` is sent to a non-confidential client.
   *Confirm:* `verify` → `oidc.confidential`. *Fix:* `reset` + `reconcile`.
3. **Credential drift** — the container's `client_id` no longer exists in
   Forgejo (app deleted/rotated).
   *Confirm:* `verify` → `oidc.app_live` reports `STALE`. *Fix:* `reset` +
   `reconcile`.

### The admin token needs admin scope

A token without it returns **404** (not 401) on `/api/v1/admin/*`, which
looks like a wrong URL rather than a permissions problem. Symptom: provisioning
prints `⚠ Skipping Forgejo user creation`. Everything else still works, so it
is easy to miss.

*Confirm:*
```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  "$FORGEJO_URL/api/v1/admin/users?limit=1" -H "Authorization: token $TOKEN"
```
200 = good, 404 = missing scope. Generate a new token with `admin:write`.

### OAuth2 secrets cannot be re-read

Forgejo returns `client_secret` **only at creation**. If the container's
`.env` is lost but the app still exists, the secret is unrecoverable —
`provision.py` therefore deletes and recreates the app. Never assume you can
fetch an existing secret back.

### Caddy specifics

- Caddy is on the **host network**: it cannot resolve `hermes-alice` or
  `fjell`. Use `127.0.0.1:<port>`.
- Go uses **RE2** — no negative lookahead. `(?!…)` fails to load the config.
  Hence the explicit path list in `caddy_utils._TOP_LEVEL_PATHS`; add to it if
  Hermes gains a new top-level route.
- Use `$1`, not `{http.regexp.1}`, in `header_down` replacements — the latter
  is emitted literally and causes a redirect loop.
- Always `docker exec <caddy> caddy validate --config /etc/caddy/Caddyfile`
  after changing the generator. `verify` does this as `caddy.config_valid`.

### Bazzite read-only rootfs

New bind-mount targets under `/app` fail with
`read-only file system`. That is why `agents.conf` is written with
`docker exec -i` into the Caddy container rather than through a mount. Prefer
`docker exec` or named volumes over new bind mounts.

### No "Register" link on the Forgejo login page

Forgejo ships with `DISABLE_REGISTRATION = true`, so the OIDC login page
offers no way to create an account and a new developer is stuck.

Registration is a **server config setting**, not an API-reachable one — the
Forgejo MCP tools cannot change it. It is declared in `compose.yml`:

```yaml
- FORGEJO__service__DISABLE_REGISTRATION=${FORGEJO_DISABLE_REGISTRATION:-false}
- FORGEJO__service__REGISTER_EMAIL_CONFIRM=false
```

Mind the sense: the key is `DISABLE_REGISTRATION`, so `false` means sign-up
is **open**. To close it, set `FORGEJO_DISABLE_REGISTRATION=true` in `.env`
and recreate the container.

Email confirmation is off deliberately — no SMTP is configured, so requiring
it would leave every new account permanently unactivated.

Forgejo maps `FORGEJO__section__KEY` env vars onto `app.ini` **at boot**, so
the change needs a restart (`docker compose up -d --force-recreate forgejo`).
Editing `forgejo/conf/app.ini` by hand also works but is not reproducible
from the repo — prefer the compose variable.

*Confirm:* `python3 scripts/signup_test.py <newuser> <password>` registers
through the real web form and logs in as that user.

### A basic-auth prompt appears during sign-in

Symptom: partway through signing in, the browser pops a username/password
box you have no credentials for. Dismissing it and clicking "Sign in" again
appears to work.

That prompt belongs to the **portfolio site**, not Hermes. Unprefixed
`/auth/login` fell through to the default handler's `basic_auth`. It happens
because browsers strip `Referer` on cross-origin navigations, so returning
from the Forgejo consent screen loses the signal the rescue route matches on.

**It is not a security hole.** Dismissing the prompt grants no agent access —
it "works" only because a valid Hermes session cookie is already present.
Verify that for yourself:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://<domain>/agent/<user>/api/sessions
# 401 — the agent API rejects anything without a verified OIDC session
```

Fixed by an `@auth_orphan` route that catches Referer-less `/auth/*` and
redirects it into the agent prefix (single developer) or shows a chooser
page (multiple). Covered by `verify` → `http.auth_orphan` and
`http.api_guarded`.

### Login succeeds, then immediately bounces back to the sign-in page

Symptom: you sign in, Forgejo authorizes, and you land back on
"Sign in with Self-Hosted OIDC". Clicking it again just repeats. The auth
log shows the giveaway pattern:

```
login_start → login_success → session_verify_failure (provider_unreachable)
login_start → login_success → session_verify_failure          ← repeats
```

Cause: Hermes derives **both** the cookie `Secure` flag **and the cookie
name prefix** (`__Secure-`) from the forwarded scheme. uvicorn only honours
`X-Forwarded-*` from peers listed in `forwarded_allow_ips`, which defaults to
`127.0.0.1`. Caddy runs on the host network and reaches the published port
from the Docker bridge gateway (`172.18.0.1`), so the header was discarded,
scheme resolved to `http`, and the cookie written at login was looked up
under a *different name* on the next request — so the session never verified.

Fix: `FORWARDED_ALLOW_IPS=*` on the developer container (only Caddy can reach
that port — it's published on `127.0.0.1`) plus an explicit
`header_up X-Forwarded-Proto https` in the generated route. Both are applied
by `reconcile`.

*Confirm:* `verify` → `http.secure_cookies`, or directly —

```bash
curl -sS -o /dev/null -D - https://<domain>/agent/<user>/ | grep -i set-cookie
# want: __Secure-hermes_sso_attempt=...; Secure
# bad:  hermes_sso_attempt=...            (no Secure, no prefix)
```

### The "Sign in" button 404s at `/auth/login`

Symptom: `/agent/<user>/login` renders fine, but clicking **Sign in with
Self-Hosted OIDC** lands on `https://<domain>/auth/login?provider=self-hosted`
→ 404.

Cause: Hermes renders the button with a hardcoded, unprefixed
`href="/auth/login?..."` (`dashboard_auth/login_page.py`), and
`render_login_html()` accepts no prefix argument. Because the link lives in
the HTML **body**, the `header_down Location` rewrites cannot reach it. The
unprefixed path falls through to the default handler (basic-auth → fjell) and
404s.

Fix (in the generated `agents.conf`): a Referer-matched rescue redirect. The
session cookies are scoped to `Path=/agent/<user>`, so they are *not* sent to
`/auth/login` — the `Referer` header is the only signal identifying the user.

Covered by `verify` → `http.login_button`, which follows the real button.
Two syntax traps when editing that rule:

- Use top-level `redir @matcher …`, **not** `handle @matcher { redir … }` —
  inside a `handle` it returned an empty 200 with no `Location`.
- Use `{http.request.uri}`, **not** `{uri}` — the short form resolves empty
  there, silently dropping the query string.

### A 404 may be a crashed backend, not a routing problem

Caddy returns 404/502 when the upstream isn't listening, which looks
identical to a bad route. Check the container is actually *up* first:

```bash
docker ps -a --filter name=fjell --format '{{.Names}}\t{{.Status}}'   # "Restarting" = crash loop
docker logs aurora-fjell-1 --tail 20
```

Real example: fjell used axum's old `:username` path syntax. axum 0.8
requires `{username}` and **panics at startup** on the old form
(`Path segments must not start with ':'`), so the container crash-looped and
`/agent/<user>/setup` 404'd through Caddy despite a freshly built image.

### Rebuilt an image? Recreate, don't restart

`docker restart` reuses the **old** image. After `docker build` you must
`docker compose up -d --force-recreate <service>`. This silently wasted a
debugging cycle on fjell.

### Hermes drops the proxy prefix (upstream bug, worked around)

`hermes_cli/dashboard_auth/routes.py` (~line 360) issues the post-login
redirect without the `X-Forwarded-Prefix`, sending users to `/` instead of
`/agent/<user>/`. We rewrite `Location` in Caddy. **Decision: not upstreamed.**
If a login lands on a basic-auth 401 at the site root, this is why.

---

## Verification

```bash
./scripts/dev-admin.sh verify alice
```

26 checks across container, OIDC, Caddy, authz and HTTP layers. Exit 0 only when all
pass. Each failure names the broken component rather than "the site is down".

Deeper tools, for when `verify` says something is wrong and you need to see
the actual traffic:

| Script | Use |
|---|---|
| `scripts/trace_oidc.py <user> <pass>` | Hop-by-hop redirect trace. **Best first tool for any login problem** — it shows precisely which hop breaks. |
| `scripts/e2e_login.py <user> <pass>` | Real cookie-jar login through the whole chain. |
| `scripts/spa_check.py <user> <pass>` | Catches "HTTP 200 but broken page" by fetching JS/CSS and checking MIME types. |
| `scripts/isolation_test.py <agent> <owner> <pw> <other> <pw>` | Proves agent isolation end to end: owner 200, non-owner 403 on dashboard **and** API. |
| `scripts/authz_test.py <agent> <owner> <pw> <other> <pw>` | Hits the authz gate directly (204 / 403 / 401) without going through Caddy. |
| `scripts/signup_test.py <newuser> <pw>` | Registers through the real web form and logs in — proves self-service sign-up works. |
| `scripts/loop_repro.py <agent> <fjuser> <pw>` | Walks the login flow hop by hop with a cookie jar, submitting consent. Use when login succeeds but the session doesn't stick. |
| `scripts/session_probe.py <user> <pass>` | Dumps session cookie names, paths and JWT segment counts. Catches `Secure`/`__Secure-` mismatches. |
| `scripts/cookie_probe.py <user> <pass>` | Prints the cookie names the real flow sets. |
| `scripts/negative_test_login_button.py` | Strips the login-button fix, confirms `verify` reports FAIL, then restores. Proves that check can actually fail. |

Most take a password because they drive a **real** login rather than
asserting against mocked state — that is what made the session bugs
findable. Two accounts are needed for the isolation tests; create a
throwaway with `gitea admin user create` and purge it afterwards.

Note: `verify` deliberately triggers one stale-cookie failure per run, so a
single `provider_unreachable` line in the auth log per run is **expected**.
The suite accounts for this and is safe to run repeatedly.
