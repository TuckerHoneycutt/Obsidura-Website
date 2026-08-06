# Internal hub — what was built, and what it is standing on

The site root is now a front door: Forgejo, AFFiNE, and **the caller's own
agent**. Design and the measurements behind it:
`docs/superpowers/specs/2026-07-31-internal-hub-design.md`.

---

## The shape of it

```
GET /                → 302 → /git/.hub/
GET /git/.hub/*      → Caddy handle_path → fjell   (Forgejo cookie arrives)
fjell → forgejo:3000/api/v1/user       → identity, or nothing
      → forgejo:3000/user/settings     → identity / 3xx signed-out / error
      → Caddyfile.d/agents.json        → is that login a provisioned agent?
```

| File | Responsibility | Lines |
|---|---|---|
| `fjell/src/identity.rs` | Ask Forgejo whose cookie this is. Two probes, one verdict. | 120 + 190 test |
| `fjell/src/routes/hub.rs` | Render the page. Pure function of (caller, roster). | 130 + 130 test |
| `fjell/src/config.rs` | The roster file and Forgejo's internal origin. | 35 |
| `fjell/static/hub.css` | The whole of the styling. No framework, no build step. | 130 |
| `Caddyfile` | Mount the hub under `/git/`, redirect `/`. | +25 |
| `compose.yml` | Give fjell the roster and Forgejo's address. | +10 |
| `tests/test_hub_conformance.py` | Everything fjell's own tests cannot see. | 190 |

`fjell/src/routes/landing.rs` is **deleted**. It was unreachable (Caddy's
`handle /agent` has redirected to the Hermes dashboard since Chunk 2) and it
read a roster file that was never mounted, so it listed nobody.

## What was proved, and how

**27 mutations, every one reddening a named test.** Tables are reproducible:
`cargo test` in a `rust:1.85` container (the host has no toolchain), and the
Python suite from a worktree venv.

| # | Mutation | Test that went red |
|---|---|---|
| M1 | link the first roster entry instead of the caller | `the_agent_link_is_the_callers_own_agent` |
| M2 | drop HTML escaping | `a_hostile_login_is_escaped` |
| M3 | case-sensitive roster match | `the_roster_spelling_wins_over_the_callers_spelling` |
| M4 | offer an agent link to an unrostered caller | `an_unrostered_login_gets_no_agent_link` |
| M5 | show the roster to an anonymous visitor | `anonymous_gets_a_sign_in_route_and_no_agent_link` |
| M6 | render a sign-in prompt during an outage | `unavailable_does_not_tell_a_signed_in_user_to_sign_in` |
| M7 | hotlink the stylesheet from a CDN | `the_stylesheet_is_vendored_not_hotlinked` |
| M8/M9 | stop forwarding the caller's cookie (each probe) | `the_callers_cookie_is_forwarded_on_both_probes` |
| M10 | read a 5xx from the profile page as signed-out | `an_outage_on_both_probes_is_unavailable_not_anonymous` |
| M10b | let an API failure decide the answer | `an_api_outage_still_identifies_via_the_profile_page` |
| M10c | accept an empty `login` from the API | `an_api_200_with_an_empty_login_is_not_taken_as_an_identity` |
| M11 | follow redirects (so the login page gets scraped) | `a_redirect_to_the_login_page_is_anonymous` |
| M12/M15 | never reach, or discard, the fallback probe | `a_session_the_api_rejects_falls_back_to_the_profile_page` |
| M13 | read a missing username field as signed-out | `a_signed_in_page_that_lost_the_field_is_not_reported_as_signed_out` |
| M14 | take any `<input>` as the username | `a_different_input_is_not_mistaken_for_the_username` |
| P1/P2 | unmount the hub from `/git/`, or use a shadowable path | `test_the_hub_is_mounted_where_the_forgejo_cookie_reaches_it` |
| P3 | stop redirecting `/` | `test_the_front_door_redirects_to_the_hub` |
| P3b | restore the ambiguous `redir` spelling | `test_no_redir_hides_its_destination_in_the_matcher_slot` |
| P4 | mount the roster somewhere fjell does not read | `test_fjell_is_given_the_roster_it_reads` |
| P5 | drift the Rust default from the compose env | `test_fjells_compiled_in_default_matches_the_mount` |
| P6 | roster entry with no Caddy route | `test_every_agent_the_hub_can_link_to_is_routable` |
| P7 | empty the roster | `test_the_roster_the_hub_reads_is_not_empty` |
| P8 | drift the roster from `developers.yaml` | `test_the_roster_matches_developers_yaml` |
| P9 | point fjell at `127.0.0.1` for Forgejo | `test_fjell_can_reach_forgejo_by_service_dns` |
| P10 | `@import` a Google font into the stylesheet | `test_hub_assets_are_vendored_into_the_repo` |

One mutation initially **failed to redden** and that was the useful one:
making the API probe report a 500 as "signed out" changed nothing, because the
fallback probe reached a stub with no route and produced the same
`Unavailable` for a different reason. The control flow was simplified until
the property was real — the API probe can now return an identity but never a
verdict — and the test was rebuilt so both stubbed routes answer.

### In a real stack

One ephemeral branch (`br-hub2`, built from this branch's final commit, torn
down after). Production was fingerprinted before and after: 11 containers both
times, `/` 401, `/git/` 200, `/affine/` 302, `/agent/cumshit42069/` 302
unchanged. Zero `br-*` containers or volumes remain.

```
GET /                          302 → /git/.hub/
GET /git/.hub                  302 → /git/.hub/
GET /git/.hub/hub.css          200 text/css 2912B
GET /git/                      200        (Forgejo, unshadowed)
GET /git/cumshit42069          200        (a user's page, unshadowed)
GET /nonexistent               401        (basic_auth still guards the rest of /)

anonymous              → "Not signed in" + /git/user/login
as cumshit42069        → "Signed in as cumshit42069" + href="/agent/cumshit42069/"
as hubprobe (no agent) → "Signed in as hubprobe" + "No agent yet", no link
hubprobe editing the URL to /agent/cumshit42069/ → 403 "This isn't your agent"
```

`hubprobe` was created through the branch's own Forgejo admin API and
`cumshit42069`'s password was reset there; both writes landed in the branch's
seeded forge and were destroyed with it.

## What was NOT proved

- **No browser ever loaded the page.** Every observation is `curl`. The HTML
  and CSS are asserted; the *rendering* is not, in either colour scheme.
- **Production was never exercised.** Deploying is `docker compose up -d
  fjell caddy` in production, which nobody has run. Caddy's config is a
  **file** bind mount, so a `caddy reload` alone will not pick the new
  Caddyfile up — the container must be recreated. That cost one wasted cycle
  in the branch; do not repeat it in production.
- **Only two identities were tested**, and only one of them owned an agent —
  `developers.yaml` has exactly one developer. The "wrong developer's agent"
  case is covered by `agent-authz` (403 observed) but not by two developers
  who *both* own agents.
- **The scrape is not monitored.** The unit tests pin the parser against
  captured markup, so a Forgejo upgrade that changes the profile template will
  leave the suite green and the page saying "could not confirm who you are".
  When that fires: recapture `<input name="name" …>` from
  `/git/user/settings`, update `REAL_SETTINGS_INPUT` in `identity.rs`, and if
  the field is gone for good, make fjell an OIDC relying party (spec §2.3).
- **`aurora branch up` could not be run from this branch's own tooling.** See
  below.

## Defects found and NOT fixed here

1. **`assert_seedable` refuses every legitimate branch worktree** —
   `aurora-cli/aurora_cli/seed.py:493` on `main`. The clause `prod in
   dst_root.parents` contradicts the function's own docstring: branch
   worktrees live at `<production>/.worktrees/<name>`, so every real `branch
   up` is refused. **Already fixed on `fix/owners-map-bind`**; that worktree's
   tooling was used to build the branch stack for this work, so the fix is
   not duplicated here. It must reach `main` or `branch up` is dead there.
2. **`agent-authz/data/owners.json` is committed for a roster retired three
   commits ago** (`jaun`, `johndear`, `testuser`; not `cumshit42069`). The
   seeder deliberately skips it and reconcile is meant to rewrite it, but in
   the branch it did not — so **every** `/agent/cumshit42069/` request in a
   branch stack answers 403 "no registered owner", where production answers
   302 to the OIDC login. Not touched here: unlike `agents.json`, this file's
   `client_id`/`owner_sub` cannot be derived from `developers.yaml`, and
   `fix/owners-map-bind` is already about exactly this.
3. **Two branch worktrees leaked**, `~/Desktop/aurora/.worktrees/hub` and
   `…/hub2`, 2.5 GB each. Known cause (root/polkitd-owned bind sources the
   daemon created inside them), documented in `AGENTS.md`. Not removed — a
   permission refusal is a defect to report, not to route around. A human:
   ```
   sudo rm -rf ~/Desktop/aurora/.worktrees/hub ~/Desktop/aurora/.worktrees/hub2
   git -C ~/Desktop/aurora worktree prune && git -C ~/Desktop/aurora branch -D hub2
   ```
   `.worktrees/ownersbind` (2.5 GB) is the same leak from an earlier run and
   predates this work.

## Fixed here, incidentally

- **`/affine` answered an empty 200 in production.** `redir /affine/ 302`
  inside a `handle` block parses the destination as a *matcher* — Caddy reads
  the first token after `redir` as an optional matcher and a leading `/` makes
  it one, so the directive means "for requests under /affine/, redirect to
  `302`". `caddy validate` accepts it. Found by the hub's own front-door
  redirect doing the same thing, fixed in both places with `redir *`, and
  pinned by `test_no_redir_hides_its_destination_in_the_matcher_slot`, which
  scans every `redir` in the Caddyfile and the generated `agents.conf`.
- **`Caddyfile.d/agents.{conf,json}` were committed for the retired roster.**
  Regenerated from `developers.yaml`; the result is **byte-identical** to what
  `reconcile` has written in production, which is how the regeneration was
  checked rather than trusted.
- **fjell never had a mount for the roster it reads**, so `load_agents()`
  returned `[]` in production.
