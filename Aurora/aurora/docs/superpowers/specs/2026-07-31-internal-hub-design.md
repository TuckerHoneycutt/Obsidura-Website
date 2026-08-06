# Internal Hub — Design Spec

**Date:** 2026-07-31
**Status:** Implemented
**Branch:** `feat/internal-hub`

---

## Goal

One page that is the stack's front door: Forgejo, AFFiNE, and **the caller's own
agent**. The third is why this is a feature and not a static page — the link has
to differ per developer, or it is just the agent chooser with extra steps.

## 1. What identity signals actually exist

Measured on production 2026-07-31, not assumed. This is the whole design
problem, so it is stated before any decision.

| Signal | Where the browser sends it | Usable by fjell at `/`? |
|---|---|---|
| Caddy `basic_auth` (portfolio) | everywhere under `/` | **No** — one shared credential for the whole team. It proves you are *someone*, never *which one*. |
| Forgejo session cookie | `Path=/git` — measured: `session=…; Path=/git; HttpOnly` | **No at `/`**, yes under `/git/` |
| Hermes session JWT (`__Secure-hermes_session_at`) | `Path=/agent/<user>` — the path already names the user | **No.** Reading it requires already knowing the answer. |
| Forgejo OIDC as a relying party | anywhere fjell chooses | Yes, at the cost of an OAuth2 app, a client secret, a session store and a callback route in fjell |

**There is no identity signal at the site root.** Anything rendered at `/` that
claims to know who you are would be inventing it.

## 2. Decision

**Mount the hub under `/git/` so the browser hands fjell the Forgejo session
cookie, and ask Forgejo — the actual identity provider — whose cookie it is.**

```
GET /git/.hub/   → Caddy handle_path → fjell   (Forgejo cookie included)
fjell → GET forgejo:3000/api/v1/user     (caller's Cookie replayed)
        200 + a login          → Identified
        anything else          → no verdict, ask the next one
      → GET forgejo:3000/user/settings   (caller's Cookie replayed)
        200 + the username field → Identified
        3xx / 401 / 403          → Anonymous
        anything else            → Unavailable
GET /            → 302 /git/.hub/
```

- **`/git/.hub` cannot collide with a Forgejo page.** Forgejo usernames must
  begin with an alphanumeric, so no account can ever own a path segment that
  starts with a dot. This is structural, not careful.
- **fjell never trusts the caller's claim.** The username comes from Forgejo's
  answer to a cookie the browser sent; there is no header or query parameter a
  caller can set.
- **The cookie is replayed to exactly one fixed origin** (`FORGEJO_INTERNAL_URL`,
  compose service DNS). It is never sent anywhere the caller can influence.

### 2.1 Forgejo's API does not accept session cookies

Measured 2026-07-31 in the `hub` branch stack, on Forgejo 15.0.5, with a
session the web UI accepted at the same moment:

```
GET /git/api/v1/user   Cookie: session=…  →  401 {"message":"token is required"}
GET /git/user/settings Cookie: session=…  →  200, signed in as cumshit42069
GET /git/user/settings (no cookie)        →  303 → /git/user/login
```

So the working signal is Forgejo's own profile page, which carries exactly one
`<input name="name" value="…">` — the account's username field. The API is
still tried first, and costs one LAN round trip, because it is the stable
answer anywhere it *is* accepted; it is deliberately **unable to return a
verdict**, only an identity, so an API outage can never sign anybody out.

**This is the weakest part of the feature and it is a scrape.** It is
mitigated, not excused:

- Redirects are not followed, so "not signed in" is Forgejo's 303 rather than
  an inference from a page that happens to lack a field.
- A 200 page with no username field is `Unavailable`, never `Anonymous` — a
  Forgejo template change degrades to a visible "could not confirm who you
  are", not to a login loop.
- The parser is pinned against markup captured verbatim from a running
  Forgejo, and attribute order is not assumed.
- Nothing security-relevant rests on it (§2.2).

### 2.2 The hub routes; it does not authorize

Editing the link to another developer's agent gets you the existing "this isn't
your agent" 403 page: `/agent/<user>/*` is still gated by `agent-authz`, which
verifies the Hermes JWT against Forgejo's JWKS and checks ownership. The hub is
allowed to be wrong about who you are; the gate is not. **No security decision
depends on this page.**

### 2.3 Rejected alternatives

| Option | Why not |
|---|---|
| Render the hub at `/`, list every developer, let them pick | That is `write_agent_chooser`, which already exists for the case where identity is genuinely unknowable. Re-shipping it as the front door means the feature does nothing. Also leaks the roster to anyone on the tailnet. |
| fjell as an OIDC relying party | The honest maximal answer, and the right one if the hub ever needs to *enforce* anything. Costs an OAuth2 app in provisioning, a client secret in `.env`, a callback route, a session store and cookie handling — for a page whose security posture is "none". Revisit if the hub grows a write. |
| Widen the Hermes cookie's `Path` to `/` | Deliberately not done. Path scoping is what keeps one browser's agent sessions separate; widening it to render a link trades a real isolation property for a cosmetic one. |
| Derive identity from `basic_auth` | Shared credential. Would report every developer as the same person. |
| Client-side `fetch('/git/api/v1/user')` from a page at `/` | Same information, but the identity logic moves into untested JavaScript and the page needs JS at all. Server-rendering keeps it in Rust where the unit tests are. |
| Scrape the navbar's "Signed in as <strong>X</strong>" | Locale-dependent string. The profile form's field is not. |

## 3. Render states

Four, and the distinction between the last two is load-bearing.

| Caller | Card |
|---|---|
| Identified, in the roster | Link to `/agent/<roster spelling>/` |
| Identified, not in the roster | "No agent yet" — named, no link |
| Anonymous | Sign-in link to `/git/user/login` |
| Unavailable (Forgejo unreachable / 5xx / unparseable) | Says so. **Not** a sign-in prompt — telling a signed-in developer to sign in during a Forgejo outage sends them round a loop that cannot succeed. |

The roster is `Caddyfile.d/agents.json`, written by `dev-admin reconcile`, read
per request (same contract as `agent-authz`'s `owners.json`: provisioning a
developer takes effect without a restart). The **roster's** spelling of the
username is what gets linked, never the caller's — Caddy's routes are literal
paths generated from `developers.yaml`, so `/agent/Alice/` is a 404 even when
Forgejo will answer to `Alice`.

## 4. Look

No build step, no CDN, no npm. One hand-written stylesheet
(`fjell/static/hub.css`, ~3 KB, `include_str!`-ed into the binary and served at
`/git/.hub/hub.css`), light and dark via `prefers-color-scheme`.

**No htmx and no JavaScript at all.** The page has no interactivity: it is three
links, rendered once, server-side. A classless CSS framework was considered and
rejected for the same reason — this is a card grid, not prose, so a prose
stylesheet is an order of magnitude more bytes for rules nothing here uses.
`test_hub_assets_are_vendored_into_the_repo` and
`the_stylesheet_is_vendored_not_hotlinked` keep it that way.

## 5. Consequences

- **`/` no longer prompts for the portfolio's `basic_auth`.** It 302s to the
  hub, which is outside that handler. An anonymous visitor now sees two public
  links and a sign-in prompt without a password. This is deliberate: the trust
  boundary for the whole stack is the tailnet, the hub discloses nothing beyond
  the fact that Forgejo and AFFiNE exist, and prompting a developer for a shared
  portfolio password before they can reach *their own agent* is exactly the
  friction this page exists to remove. Everything else under `/` is unchanged
  and still behind `basic_auth`. **If the owner disagrees, deleting the
  `handle /` block restores the old behaviour and costs one redirect.**
- The old `/agent` landing page in fjell is deleted. It was unreachable —
  Caddy's `handle /agent` has redirected to the Hermes dashboard since Chunk 2 —
  and it read a roster file that was never mounted, so it listed nobody.
- `compose.yml` now mounts `./Caddyfile.d` into fjell read-only. Without it
  `load_agents()` returns `[]` and every caller sees "no agent yet".

## 6. Known limits

- **Identity depends on Forgejo's profile page keeping its username field.**
  A template change breaks it. The failure mode is a visible "could not
  confirm who you are", not a wrong identity and not a login loop — but it is
  a real coupling to a page Forgejo does not consider an interface.
  `docs/implementations/2026-07-31-internal-hub.md` records what to do when it
  fires. The durable fix is making fjell an OIDC relying party (§2.3); that is
  the right call the moment the hub needs to enforce anything.
- **Nothing detects the breakage automatically.** The unit tests pin the
  parser against captured markup, so they keep passing across a Forgejo
  upgrade that changes the template. Only loading the page notices.
- The hub does not surface Hermes' admin dashboard (`:7444`), ArcadeDB, or
  anything else on the host. Three doors was the ask.
