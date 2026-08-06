# Implementation Log — Scoped Developer Access to Forgejo

Running record of what was built, how it diverged from
`docs/superpowers/specs/2026-07-31-forgejo-dev-access-design.md`, and why.

> The spec says what was intended. This says what the running system actually
> is. Where they disagree, **this file is correct**.

---

## Outcome

`dev-admin access` — seven subcommands giving a developer scoped, enumerable,
revocable Forgejo access without ever handing them `FORGEJO_ADMIN_TOKEN`.
174 tests in `dev-administration/tests` (up from 141), 48 named mutations all
red, and 57 observations recorded against a real branch stack's own Forgejo.

Production was not touched. Every write went to `br-devaccess1`.

---

## The design changed twice, both times because a measurement contradicted it

**Draft 1 — admin mints the token.** `dev-admin access grant <user>` using the
admin token. Written, tested (26 tests, 15 mutations, all red), committed as
`8b32b3c`.

Then it was run against the branch stack and `POST /users/{u}/tokens` answered
**401 auth method not allowed**. A read-only probe against production before
writing any code had shown `GET` on that same route answering 200 to a bearer
token, and I generalised from the GET. Gitea guards these routes with
`reqBasicAuth`, and a token presented as a basic-auth password does not satisfy
it — verified across four auth forms (bearer, basic, basic+Sudo, bearer+Sudo),
all 401, including for the admin's own account.

**The probe was right and the inference was wrong.** "Measure, do not cite"
does not cover generalising one verb to another on the same route.

Draft 2 moved minting to the developer, authenticated with their own password.
That is strictly better — the admin never holds the credential — but it was
forced, not chosen. `DELETE` is 401 for the admin too, so revocation moved with
it, and `suspend` was added as the admin's only unilateral lever.

**Draft 2 — acceptance found the token could reach nothing.** 28/31
observations. `GET /repos/supergoodname77/aurora` with a freshly minted token
answered 404 and `git clone` said "Repository not found".

The cause is a pre-existing defect, not a new one (see below). The fix was to
add the repository half — `authorize` / `deauthorize` via the collaborator
route — which is what makes a token mean anything.

---

## Defects found in existing code, NOT fixed

Each of these predates this branch. All were found by measurement against the
branch stack, all are reported rather than repaired, because repairing them
changes what `reconcile` does on every deploy.

**D1. `reconcile`'s org/team machinery is inert.** `FORGEJO_ORG=obsidura` and
`FORGEJO_DEV_TEAM=developers` exist and the org and team exist — with **zero
repositories**. `forgejo_org.add_team_repo` calls
`PUT /teams/{id}/repos/obsidura/aurora`, but the repos live at
`supergoodname77/aurora`. Gitea teams can only hold repos owned by their own
org, so it 404s, and the handler is:

```python
except subprocess.CalledProcessError:
    pass  # Already added
```

Every failure has been read as "already done" since it was written. Measured:
`PUT /teams/2/repos/supergoodname77/aurora` → 404.

**D2. No shared repo has branch protection.**
`GET /repos/supergoodname77/aurora/branch_protections` → `[]`.
`ensure_branch_protection` is called with the org name for the same reason and
swallows the same 404 in the same way. Consequence, observed directly: with
`write` collaborator access, `git push origin HEAD:main` **succeeded**. That is
why `authorize` now refuses `write` on an unprotected default branch — the
guard exists because the acceptance run proved it was needed.

**D3. The `developers` team's members are retired test accounts.**
`alicetest`, `bobtest` — removed from `developers.yaml` in `7dd7cae`, still in
the team. `cumshit42069`, the only real developer, is not in it. Nothing
removes a member when a developer leaves `developers.yaml`.

**D4. `forgejo_utils._curl` puts the admin token in `argv`.** It is therefore
readable by any user on the host via `ps`, and `subprocess` copies it into
`CalledProcessError.cmd` — so it is reproduced verbatim in any traceback. This
was observed happening during draft 1's failed acceptance run. The new
basic-auth branch of `_curl` sends credentials through a stdin config file
(`curl -K -`) and is pinned by
`test_curl_sends_basic_credentials_through_stdin_not_argv`. **The bearer branch
was deliberately left alone** — changing it alters every existing caller, and
the blast radius did not belong in this change.

**D5. `must_change_password` blocks the whole flow.** `reconcile` creates
accounts with `must_change_password=true`; Forgejo then refuses basic auth, so
`access mint` exits 1 for a brand-new developer until they log into the web UI
and change it. Measured both ways.

---

## Mutation record

48 mutations, applied one at a time, suite run, reverted, suite green after.
Full table in the PR. Two found real defects in the tests rather than
confirming them:

**M11 — `POST` sends `DEFAULT_SCOPES` instead of the caller's argument.**
Green. `test_grant_posts_..._the_requested_scopes` had passed exactly
`DEFAULT_SCOPES`, so substituting them was invisible. A `--scope` flag silently
discarded is the worst failure this feature has. The test now asserts it is
requesting something *other* than the defaults before it asserts anything else.

**M46 — an unreadable `branch_protections` route reads as protected.** Green.
Nothing covered the `except CalledProcessError` path, so the guard could have
been made to fail *open* — hand out push access whenever the check errors —
without a single test noticing. Two fail-closed tests added.

**M33** was a non-mutation on the first attempt: it swapped two adjacent local
checks with no HTTP call between them, so nothing observable changed. Rewritten
to move the permission check *after* the Forgejo round-trip, which does.

---

## Branch stack

One stack, `br-devaccess1`, from `feat/forgejo-dev-access`, `--devs
cumshit42069`. 14 containers, `dev-admin` exited 0. Every acceptance script
carries a positive scope guard — the Forgejo host must equal
`aurora-devaccess1.tailc67a98.ts.net` **and** the Compose project must equal
`br-devaccess1`, or it exits before its first call. `!= production` would pass
on a typo, on an empty string and on an IP.

Observations: 45/45 on the main path, 11/12 on the branch-protection path (the
twelfth was an assertion error in the acceptance script — it asserted no repo
was flagged UNPROTECTED after protecting one of four; the other three correctly
still were).

State restored after each run: token list back to its baseline, collaborators
emptied, protection rules deleted, `must_change_password` and `active` restored.
