# Admin Asks

Things blocked on user action. Updated as implementation progresses.

## BLOCKED: No Rust/Cargo in Hermes container

Task 9 (Fjell landing page + setup form) requires `cargo build`. Source files are written and ready.

**Fix:** `docker compose build fjell` on the host (multi-stage Dockerfile builds from source).

## FIXED: Forgejo admin token in .env

`FORGEJO_ADMIN_TOKEN` is set in `.env`, so `dev-admin reconcile` can create
OAuth2 apps. The literal token that used to be written out here has been
removed — it is a live credential and this file is tracked. Read the current
value from `.env`; never paste one back into a tracked file.

## TODO: Test OIDC redirect URI

Once a developer is provisioned, test that the OIDC redirect URI works behind Caddy's `strip_prefix`. If it fails, fall back to subdomain-based routing.

## TODO: Push commits to Forgejo

Last push failed (Forgejo unreachable). Retry when server is back:
```bash
cd /opt/data/workspace/aurora && git push origin main
```

## FIXED: developers.yaml bind mount

Docker was creating an empty directory instead of mounting a file. Fixed: symlinked `developers.yaml` → `dev-administration/developers.yaml`.

## FIXED: dev-admin missing deps

`python:3.13-slim` doesn't have typer/pyyaml. Fixed: compose command runs `pip install --quiet typer pyyaml` before the CLI.

## FIXED: authorized_keys missing on host

Created `~/.ssh/authorized_keys` (Docker would create a directory otherwise).
