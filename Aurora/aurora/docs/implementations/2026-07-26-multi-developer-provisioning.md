# Implementation Log — Multi-Developer Provisioning

Running record of what was actually built, how it diverged from
`docs/superpowers/specs/2026-07-25-multi-developer-provisioning-design.md`
and `docs/superpowers/plans/2026-07-25-multi-developer-provisioning.md`,
and why. Newest section last.

> Purpose: the spec says what we intended. This says what the running system
> actually does. Where they disagree, **this file is correct** — update the
> spec deliberately, don't silently drift.

---

## 2026-07-25 / 26 — OIDC login made to work end to end

### Outcome

`dev-admin provision <user>` onboards a developer in one command:
Forgejo account + OAuth2 app + Docker volume + container + Caddy route,
then runs 21 automated checks. Verified on three users (`testuser`,
`alicetest`, `bobtest`).

### Divergences from the spec

| # | Spec said | Reality | Why |
|---|---|---|---|
| 1 | Caddy proxies `/agent/<user>/` to the container by name | Caddy proxies to `127.0.0.1:<port>`, one port per dev from 9120 | Caddy runs `network_mode: host` and cannot resolve Docker-network DNS. Ports are assigned `BASE_PORT + index`. |
| 2 | Orchestrator writes `agents.conf` to a mounted dir | Writes via `docker exec -i` into the Caddy container | Bazzite's read-only rootfs refuses new bind-mount targets under `/app`. See pitfalls. |
| 3 | (unstated) | OAuth2 apps must be created with `confidential_client: true` | We authenticate the token exchange with a `client_secret`. A public client makes Forgejo omit the `id_token`, which surfaces as "provider unreachable". |
| 4 | (unstated) | Caddy rewrites `Location` response headers | Hermes' post-login redirect drops the reverse-proxy prefix. Upstream bug; worked around, **not** upstreamed by decision. |
| 5 | (unstated) | Caddy converts a 503 into a cookie-clearing bounce to `/login` | A stale session cookie otherwise shows an unrecoverable error page. |
| 6 | Developer secrets provisioned | Only OIDC wiring is provisioned; the developer supplies their own API key + SSH key via the fjell form | Deliberate: no magic config that's easy to forget. |

### The two real bugs, and how they were found

Both were found by **reproducing the symptom**, not by reading code.

**Bug 1 — public OAuth2 clients.** `create_oauth2_app` never sent
`confidential_client`, so Forgejo defaulted it to `false` (confirmed against
`GET /swagger.v1.json` → `CreateOAuth2ApplicationOptions`). Forgejo then
ignores the `client_secret` and returns no `id_token`; the plugin raises
`ProviderError`, rendered to the user as
`{"detail":"Auth provider 'self-hosted' unreachable"}`.

Fix: send `confidential_client: true`. `provision.py` additionally detects an
existing *public* app and rebuilds it, so old deployments self-heal on
`reconcile`.

**Bug 2 — prefix dropped on post-login redirect.** Found with a hop-by-hop
tracer (`scripts/trace_oidc.py`) after whole-chain tools reported only a
useless final 401:

```
hop 3: 303  forgejo /login/oauth/authorize  -> /agent/testuser/auth/callback?code=…
hop 4: 302  /agent/testuser/auth/callback   -> /            <-- prefix lost
hop 5: 401  /                                                 <-- basic-auth root
```

The OIDC exchange **succeeded**; only the landing redirect was wrong.
In `hermes_cli/dashboard_auth/routes.py`, line ~360 does
`RedirectResponse(url=landing)` with no prefix, while logout at line ~583
correctly uses `f"{prefix}/login"`.

Fix (workaround, by decision): `header_down Location` rewrites in the
generated Caddy config.

### Things that did not work — don't retry these

- **Assuming Caddy's default `X-Forwarded-Proto` is enough.** Caddy sends it,
  but uvicorn *discards* headers from peers outside `forwarded_allow_ips`
  (default `127.0.0.1`). Caddy arrives from the bridge gateway
  `172.18.0.1`, so the header was silently dropped and every Hermes cookie
  came back without `Secure` while Forgejo's on the same host had it — that
  side-by-side difference is what exposed it. Needs `FORWARDED_ALLOW_IPS`.
- **`handle @matcher { redir … }` for the auth rescue route.** Returns an
  empty 200 with no `Location` header. Use a top-level `redir @matcher … 302`.
- **`{uri}` in that redirect.** Resolves empty, so the redirect silently goes
  to the bare prefix and loses the query string. Use `{http.request.uri}`.
- **`header Referer *//*/agent/<user>/*` (glob matcher).** Never matched
  against a full referring URL. Use `header_regexp Referer "/agent/<user>(/|$)"`.
- **Cookie-based identification of the user at `/auth/login`.** The session
  cookies are scoped `Path=/agent/<user>`, so the browser does not send them
  to an unprefixed path. `Referer` is the only available signal.
- **axum `:param` path captures.** axum 0.8 replaced `:username` with
  `{username}`, and the old form is a **hard startup panic**, not a
  deprecation warning: `Path segments must not start with ':'`. The container
  crash-looped (exit 101), so `/agent/<user>/setup` 404'd through Caddy even
  though the image was freshly built. If a route 404s, check the backing
  container is actually *running* (`docker ps` → `Restarting`) before
  suspecting the proxy.
- **`GET /api/v1/admin/users/<name>` to test user existence.** Returns
  **405 Method Not Allowed** in Forgejo v15 — the path does not exist. curl
  reports it as a generic failure, so `user_exists()` returned False for
  users that plainly existed. Provisioning then tried to create the account,
  failed, and printed a temp password that had never been set — an admin
  handing that to a developer would be handing them dead credentials. Use
  `GET /api/v1/users/<name>` (200). Caught by noticing "2 events emitted"
  alongside a printed password when a real creation emits 3.
- **Negative lookahead in a Caddy regex.** Go uses RE2:
  `error parsing regexp: invalid or unsupported Perl syntax: (?!`.
  Hence the explicit path alternation in `caddy_utils._TOP_LEVEL_PATHS`.
- **`{http.regexp.1}` as a `header_down` replacement.** Emits the literal
  string and causes an infinite redirect loop. Use `$1` / `$2`.
- **Redirecting the stale-cookie 503 back to `/agent/<user>/`.** That is the
  same URL that produced the 503 → loop. Must target `/login`.
- **Marking the probe with `X-Forwarded-For` to filter its own log lines.**
  Caddy correctly overwrites `X-Forwarded-For` with the real client IP, so
  the marker never arrives. Use a log high-water mark instead.
- **A wall-clock window for "log entries from this run".** Two runs seconds
  apart each fall inside the other's window. Anchor to the timestamp of the
  newest pre-existing entry.
- **`docker restart` after `docker build`.** Restart reuses the old image.
  A recreate (`docker compose up -d --force-recreate`) is required.

### Verification harness

`dev_administration/verify.py` holds the checks; `dev-admin verify` and
`scripts/pipeline_check.py` both call `run_checks()` so they cannot drift.
21 checks covering container/port/process, OIDC env + liveness +
confidentiality, discovery/JWKS/issuer match, Caddy route + config validity,
HTTP redirect shape, JSON-error-behind-200, and stale-cookie recovery.

The suite is **idempotent** — it deliberately triggers one stale-cookie
failure per run, and excludes prior runs' entries via a log high-water mark.
Confirmed by three consecutive passing runs with no restarts.

### Known gaps

- Branch protection / org-team wiring runs but is **not covered** by the
  verification suite.
- `dev-admin doctor` is still a stub.
- The Location-rewrite path list is hardcoded; a new top-level dashboard
  route in Hermes would need adding to `_TOP_LEVEL_PATHS`.

---

## 2026-07-26 — Sign-in UX, open registration, per-agent authorization

Three further rounds after the OIDC flow worked, each triggered by the user
hitting a real failure the suite had not covered.

### Round 1 — the sign-in button 404'd

The login page renders its provider button as a hardcoded, **unprefixed**
`<a href="/auth/login?provider=...">` (`dashboard_auth/login_page.py`), and
`render_login_html()` takes no prefix argument. Unlike the redirect
`Location` headers, that link is in the HTML **body**, so header rewriting
cannot reach it — the click escaped the `/agent/<user>` prefix and landed on
the basic-auth-protected default handler.

Worked around with a Referer-matched redirect in `agents.conf`. Session
cookies are scoped `Path=/agent/<user>` and so are *not* sent to an
unprefixed path, which is why `Referer` is the only usable signal.

### Round 2 — login succeeded, then bounced back forever

The tell was in the auth log:

```
login_start -> login_success -> session_verify_failure
login_start -> login_success -> session_verify_failure   (repeat)
```

Login worked *every time*; the session simply never verified on the next
request. Root cause: Hermes derives **both** the cookie `Secure` flag **and
the cookie name prefix** (`__Secure-`) from the forwarded scheme. uvicorn
only honours `X-Forwarded-*` from peers in `forwarded_allow_ips` (default
`127.0.0.1`), and Caddy arrives from the Docker bridge gateway
`172.18.0.1` — so the header was discarded, the scheme resolved to `http`,
and the cookie written at login was looked up under a *different name*.

Found by comparing `Set-Cookie` side by side: Forgejo's cookies on the same
host were `Secure`, every Hermes cookie was not.

Fixed with `FORWARDED_ALLOW_IPS=*` on the container (safe — the port is
published on `127.0.0.1`, so only Caddy can reach it) plus an explicit
`header_up X-Forwarded-Proto https`.

Also in this round: a Referer-less `/auth/*` (browsers strip `Referer` on
cross-origin navigations) fell through to the **portfolio's** basic_auth,
prompting for credentials the developer does not have. Fixed with an
`@auth_orphan` route. That prompt was alarming but never a breach —
verified at the time that the agent API still 401s without a session.

### Round 3 — open registration + per-agent authorization

`DISABLE_REGISTRATION = true` meant no way to self-serve an account. Set
declaratively via `FORGEJO__service__*` in `compose.yml` rather than editing
`app.ini`, so it survives a container recreate. Note the inverted sense:
the key is `DISABLE_REGISTRATION`, so `false` = sign-up **open**. Email
confirmation stays off because no SMTP is configured — requiring it would
leave every new account unactivated.

That immediately exposed a real hole: **any** valid Forgejo account could
open **any** developer's agent. Neither upstream component authorizes —
Hermes' OIDC plugin has no user allowlist ("the IDP's own allowlist is
authoritative") and Forgejo has no per-OAuth2-app user restriction.

Closed with a new `agent-authz` service (`agent-authz/authz.py`) called from
Caddy via `forward_auth`:

| Status | Meaning |
|---|---|
| 204 | caller owns this agent |
| 401 | no session — **passed through** so Hermes can start OIDC |
| 403 | valid session, wrong user — blocked |

Design notes worth keeping:

- Matches the Forgejo numeric user id (`sub`), not the username — usernames
  can be renamed, ids cannot.
- Pins `aud` to the agent's own OAuth2 `client_id`, so a token minted for a
  different agent cannot be replayed.
- Fails closed: unknown agent, unreachable JWKS or missing map all deny.
- The owners map is written by `reconcile` under `/output/...`, **not**
  `/app/...` — the repo is mounted read-only and Bazzite's rootfs refuses a
  new mountpoint inside it (this failed once before the path was moved).

### Things that did not work — round 2 and 3

- **Intercepting the authz 401 in Caddy.** Redirecting it to `/login` broke
  first-time sign-in: nobody has a session before authenticating, so the
  OIDC round trip never started. The 401 must fall through to Hermes.
- **Leaving stale-cookie recovery only on the outer proxy.** `forward_auth`
  routes the 401 case through an inner `reverse_proxy`, which shadowed the
  `@stale_session` handler and resurrected the opaque 503. The recovery
  block has to be repeated on the inner proxy.
- **`file_server` for the 403 denial page.** It answers **200**, so
  `api/sessions` looked like it succeeded while returning the denial HTML —
  a false pass in my own isolation test. Use `respond "..." 403`.
- **A nested bind mount under a `:ro` mount** (`/app/agent-authz-data`).
  Same Bazzite read-only rootfs failure as the original Caddyfile.d attempt.
  Mount under `/output` instead.

### Verification harness (updated)

Now **26 checks**. Added since the first round:

| Check | Catches |
|---|---|
| `http.login_button` | the sign-in button escaping the prefix |
| `http.secure_cookies` | `X-Forwarded-Proto` not reaching uvicorn |
| `http.auth_orphan` | refererless `/auth/*` hitting the portfolio basic_auth |
| `http.api_guarded` | the agent API answering without a session |
| `authz.gate` | authz service down, or an agent with no registered owner |

Each was added *after* reproducing the failure, and `http.login_button` has
a dedicated negative test (`scripts/negative_test_login_button.py`) that
strips the fix, confirms the check reports FAIL, and restores the config —
because a check that cannot fail is worthless.

### Known gaps (current)

- **Self-registered users get no agent.** Registration and provisioning are
  separate: a new Forgejo account has nowhere to land until an admin runs
  `dev-admin provision <user>`. Accepted deliberately.
- `agent-authz` is declared in `compose.yml`. Bring it up with
  `docker compose up -d agent-authz`; nothing else is needed.
- The bare `handle /agent` block in the main `Caddyfile` is **not** dead —
  it redirects to `HERMES_SERVE_PORT` (:7444), the admin's own personal
  Hermes dashboard via Tailscale Serve. Only the `/agent/*` wildcard variant
  was stale (now removed). Don't point developer-facing pages at `/agent`;
  use `/auth/login`, which resolves to their own agent or the chooser.
- Isolation is enforced at the proxy. Anyone who can reach a container's
  published port directly bypasses it — mitigated by binding to
  `127.0.0.1`, but worth knowing.
- Fjell's setup form needed an image **rebuild** (the running image was a
  "Hello World" stub predating the Rust source) and then a second fix for
  axum 0.8's `{param}` path syntax. Both are in; recreating a Compose
  container by hand detaches it from Compose, so applying image rebuilds is
  left to the operator via `docker compose up -d --force-recreate <svc>`.
