#!/usr/bin/env bash
# Run the dev-admin CLI against the live stack from anywhere (including from
# inside the Hermes container, where `docker compose` isn't available).
#
#   scripts/dev-admin.sh reconcile
#   scripts/dev-admin.sh reset testuser
#   scripts/dev-admin.sh status
#
# Env overrides: HOST_REPO, FORGEJO_ADMIN_TOKEN, DOMAIN_NAME, FORGEJO_ORG
set -euo pipefail

# Path to the repo ON THE DOCKER HOST (bind mounts resolve host-side, not
# relative to whatever container this script runs in).
HOST_REPO="${HOST_REPO:-/home/supergoodname77/Desktop/aurora}"
DOMAIN="${DOMAIN_NAME:-superserver.tailc67a98.ts.net}"

# Token precedence: explicit env var, else the stack's .env. Never hardcode it
# here — it gets rotated, and a stale literal fails in confusing ways (the
# admin-scoped endpoints 404 rather than 401).
if [ -z "${FORGEJO_ADMIN_TOKEN:-}" ]; then
  ENV_FILE="${ENV_FILE:-$(dirname "$(dirname "$(readlink -f "$0")")")/../.env}"
  if [ -f "$ENV_FILE" ]; then
    FORGEJO_ADMIN_TOKEN="$(grep -E '^FORGEJO_ADMIN_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"'"'"'')"
  fi
fi
if [ -z "${FORGEJO_ADMIN_TOKEN:-}" ]; then
  echo "error: FORGEJO_ADMIN_TOKEN not set and not found in $ENV_FILE" >&2
  exit 1
fi
TOKEN="$FORGEJO_ADMIN_TOKEN"

exec docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$HOST_REPO/dev-administration:/app:ro" \
  -v "$HOST_REPO/agent-authz/data:/output/agent-authz-data" \
  -v "${HOST_REPO}/dev-administration/developers.yaml:/app/developers.yaml" \
  -e "FORGEJO_URL=https://${DOMAIN}/git" \
  -e "FORGEJO_ADMIN_TOKEN=${TOKEN}" \
  -e "AURORA_PROFILE_URL=https://${DOMAIN}/git/supergoodname77/aurora-agent.git" \
  -e "DOMAIN_NAME=${DOMAIN}" \
  -e "CADDY_CONTAINER=${CADDY_CONTAINER:-aurora-caddy-1}" \
  -e "FORGEJO_ORG=${FORGEJO_ORG:-obsidura}" \
  -e "FORGEJO_DEV_TEAM=${FORGEJO_DEV_TEAM:-developers}" \
  -e PYTHONPATH=/app \
  --network aurora_default \
  dev-admin:local "$@"
