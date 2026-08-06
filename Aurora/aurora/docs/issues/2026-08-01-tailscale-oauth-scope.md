# Tailscale OAuth client — wrong scope, and where the tag selector lives

**Status:** blocked on a one-minute console action
**Measured:** 2026-08-01, against the live Tailscale API with the credentials in production's `.env`

## What was tried

`TS_OAUTH_CLIENT_ID` / `TS_OAUTH_CLIENT_SECRET` are present in production's
`.env` and the client **works** — the token exchange succeeds:

```
POST https://api.tailscale.com/api/v2/oauth/token   -> 200
     scope: oauth_keys        expires_in: 3600
GET  /api/v2/tailnet/-/keys                          -> 200  (1 existing key)
GET  /api/v2/tailnet/-/acl                           -> 403
POST /api/v2/tailnet/-/keys  (tagged, 4 tag spellings)-> 403
POST /api/v2/tailnet/-/keys  (untagged control)       -> 403
```

Every create is refused, tagged and untagged alike, with
`calling actor does not have enough permissions to perform this function`.
Listing works. So this is not a tag-name problem and not a request-body
problem — it is the **scope**.

## The cause

The client carries the **`oauth_keys`** scope. That governs OAuth keys
themselves. Minting a *device auth key* needs the **`auth_keys`** scope with
**write**.

This also explains why no tag selector appeared during creation: the console
only demands tags when `auth_keys` write is granted, because a key minted by
an OAuth client is always tagged and the tags come from the client. Choosing a
different scope means never being asked.

## Fix

1. Tailscale admin console -> **Settings -> Keys**.
2. **Generate OAuth client** (a new one; scopes cannot be widened in place).
3. Grant **`auth_keys`** with **write**.
4. The **tag selector now appears** — select `tag:aurora-branch`.
5. Replace `TS_OAUTH_CLIENT_ID` / `TS_OAUTH_CLIENT_SECRET` in production's `.env`.
6. Revoke the old `oauth_keys` client.

The policy entry is already correct and needs no autogroup — a single user is a
valid owner, and admins implicitly own every tag:

```json
"tagOwners": { "tag:aurora-branch": ["epsmurf@gmail.com"] }
```

## RESOLVED 2026-08-01 — and the contract is now measured

The client was given `auth_keys` and the tag. Verified against the live API:

```
POST /api/v2/oauth/token                  -> 200   scope: auth_keys oauth_keys
POST /api/v2/tailnet/-/keys  (tagged)     -> 200   id=kwvib8hiNB11CNTRL
DELETE /api/v2/tailnet/-/keys/{id}        -> 200
```

The request body, no longer a guess — this exact shape minted a real key:

```json
{"capabilities": {"devices": {"create": {
    "reusable": false, "ephemeral": true, "preauthorized": true,
    "tags": ["tag:aurora-branch"]}}},
 "expirySeconds": 300, "description": "aurora branch <name>"}
```

`-` is accepted as the tailnet identifier. Reading the ACL still 403s,
which does not matter: minting needs neither the policy nor the tag list.

**This unblocks P6.** `branch up` can mint a per-branch, tagged, ephemeral
key instead of every branch sharing one reusable key from `.env`. Keep the
supplied-key path as the fallback for when no OAuth client is configured —
decision D-D said the key is supplied because minting needed a credential
that did not exist; it exists now, so the reason expired rather than the
decision being wrong.

## Still unverified

The exact request body remains unconfirmed, because every create returned 403
before the body could be exercised. Once the scope is fixed, confirm with one
live call before writing code against it — do not assume this shape:

```json
{"capabilities": {"devices": {"create": {
    "reusable": false, "ephemeral": true, "preauthorized": true,
    "tags": ["tag:aurora-branch"]}}},
 "expirySeconds": 300, "description": "aurora branch <name>"}
```

`-` was accepted as the tailnet identifier on the calls that did succeed.

## Why this matters beyond hygiene

Per-branch **ephemeral** keys make a branch node deregister at teardown rather
than roughly an hour later. That is the exact trap that wedged a branch on
2026-07-31: `aurora-hubdemo` was still registered, the replacement sidecar came
back as `aurora-hubdemo-1`, and Caddy could not obtain a certificate for its
own configured hostname. Ephemeral keys close that failure mode, not just the
shared-credential one.
