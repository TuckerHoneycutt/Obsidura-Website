# Scoped Developer Access to Forgejo — Design Spec

**Date:** 2026-07-31
**Status:** Implemented (`feat/forgejo-dev-access`)

---

## Problem

Forgejo is the git host *and* the OIDC provider. One credential has power over
it: `FORGEJO_ADMIN_TOKEN` in `.env` — scope `all`, no expiry, held by
`dev-admin`. A developer who wants to clone, push or call the API has no path
that is not "borrow the admin token", and that token has already been committed
to a tracked file once (`c1d95fe`).

`forgejo-mcp` already solved this shape for agents: every caller presents its
**own** token, so there is no shared credential to leak. This extends it to
humans and to git over HTTPS.

## What Forgejo permits — measured, not assumed

The design is dictated by this table. Measured against a branch stack's own
Forgejo, 15.0.5+gitea-1.22.0:

| Route | admin bearer token | developer's password (basic) |
|---|---|---|
| `GET /users/{u}/tokens` | 200 | 200 |
| `POST /users/{u}/tokens` | **401 auth method not allowed** | 201 |
| `DELETE /users/{u}/tokens/{id}` | **401 auth method not allowed** | 204 |
| `PATCH /admin/users/{u}` | 200 | n/a |
| `PUT /repos/{o}/{r}/collaborators/{u}` | 204 | n/a |
| `PUT /teams/{id}/repos/{user-owned repo}` | **404** | n/a |

Two consequences the first draft of this spec got wrong:

1. **The admin cannot mint a developer's token, and cannot delete it.** Gitea's
   `reqBasicAuth` guards those routes and a token presented as a basic-auth
   password does not satisfy it. So minting is the developer's own act. That
   is a better outcome than the one intended — the admin never holds the
   credential — but it was arrived at by measurement, not design.
2. **The org team `reconcile` configures grants nothing.** Every shared repo is
   owned by the admin's *user* namespace (`supergoodname77/aurora`), and a
   Gitea team can only hold repos owned by its own org. The lever that works is
   repository collaborators.

## What "safe" means here

| Property | Mechanism |
|---|---|
| **Scoped** | `read:user, write:repository` — never `all`, never `*:admin`, and never `write:user`, which is what a token would need to mint itself another token. Checked against a positive allowlist, so a scope invented later is refused by default. |
| **Bounded by identity** | Refuses any account not in `developers.yaml`, any Forgejo site admin, and any password belonging to a different login than the one named. |
| **Not copied anywhere** | The secret is printed once and written to no file. Forgejo stores a hash. Nothing can show it again. |
| **The admin never holds it** | Minting authenticates as the developer. `mint` works with no `FORGEJO_ADMIN_TOKEN` in the environment at all, and a test asserts that. |
| **Access is separable from identity** | A token proves who you are and grants nothing. `authorize` grants repositories; `deauthorize` takes them back without touching the token. |
| **`write` implies main is defended** | `authorize --permission write` refuses a repo whose default branch has no protection rule. Positive: prove the rule exists, rather than trusting that one does. |
| **Revocable** | `revoke` deletes by id and re-reads to confirm. It targets only `aurora-dev-<user>`; personal tokens are untouched. |

## Interface

```
dev-admin access authorize   <user> [--repo o/n] [-p read|write] [--allow-unprotected]
dev-admin access mint        <user>            # the DEVELOPER runs this
dev-admin access ls          [<user>]
dev-admin access deauthorize <user> [--repo o/n]
dev-admin access revoke      <user>            # the DEVELOPER runs this
dev-admin access suspend     <user>            # admin, unilateral
dev-admin access restore     <user>
```

Token name is derived, not chosen: `aurora-dev-<username>`. One per developer,
so revocation needs no bookkeeping outside Forgejo, and `mint` refuses while
one is live — running it twice cannot leave a second valid credential that
`revoke` will not find.

## Suspension is not revocation

`suspend` deactivates the account: measured, the token then answers 403 and git
over HTTPS refuses. It is the admin's only unilateral lever, because Forgejo
will not let an admin token delete someone else's token. **It is reversible** —
`restore` brings the same token back to life. The CLI says so in its output,
and a test asserts that it says so.

The durable admin-side lever is `deauthorize`: it survives a `restore`, and
leaves the rest of the account alone.

## Rotation

`revoke` then `mint`, both run by the developer. There is no rotation command
and no window in which two tokens are valid.

## Explicitly NOT in scope

1. **SSH keys / git over port 222.** A branch stack publishes no host ports by
   construction, so an SSH push path cannot be exercised where it is safe to
   test. Untested is worse than absent.
2. **Closing self-service sign-up.** The tailnet is still the perimeter.
3. **Shrinking `dev-admin`'s own credential.** It still uses the admin token
   for reconcile, user creation and OAuth2 apps. This removes the reason a
   *developer* touches it.
4. **Token expiry.** Forgejo 15.0.5 tokens do not expire. Mitigated by being
   narrow and enumerable, not by a clock.
5. **Fixing `reconcile`'s org/team/branch-protection machinery.** It is inert
   (see the implementation log). Repairing it touches every deploy and is a
   change of its own.
6. **Setting branch protection.** `authorize` *requires* it for `write` and
   reports its absence; it does not create it.

## Known gap

A brand-new developer cannot use this until they have changed their password.
`reconcile` creates accounts with `must_change_password=true`, and Forgejo then
refuses basic auth — measured, `mint` exits 1. They must log into the web UI
once first. This is arguably correct (the temp password gets rotated) but it is
a prerequisite nobody would guess.
