#!/usr/bin/env bash
# provision-host.sh — run with sudo to create directories and volumes
# needed by the Aurora stack on Bazzite Linux (read-only rootfs).
#
# Usage: sudo ./provision-host.sh
#
# Creates:
#   - Named Docker volumes for writable paths (avoids bind-mount overlay issues)
#   - Host directories for bind mounts that Docker can't create automatically
#   - SSH authorized_keys file if missing

set -euo pipefail

COMPOSE_DIR="$(cd "$(dirname "$0")" && pwd)"
HERMES_HOME="/var/home/supergoodname77/.hermes"
SSH_DIR="/var/home/supergoodname77/.ssh"

echo "=== Aurora host provisioning ==="
echo "Compose dir: $COMPOSE_DIR"

# ── Host directories ────────────────────────────────────────────────

# Caddyfile.d — Caddy reads generated route fragments from here
echo "→ Caddyfile.d"
mkdir -p "$COMPOSE_DIR/Caddyfile.d"
# Stub agents.conf so Caddy's import doesn't fail before dev-admin runs
if [ ! -f "$COMPOSE_DIR/Caddyfile.d/agents.conf" ]; then
    echo '# No agents configured yet — dev-admin reconcile will populate this' \
        > "$COMPOSE_DIR/Caddyfile.d/agents.conf"
    echo "  created stub agents.conf"
fi

# developers.yaml symlink — compose mounts this as a file, Docker
# creates a directory if it doesn't exist
echo "→ developers.yaml"
if [ ! -e "$COMPOSE_DIR/developers.yaml" ]; then
    ln -s dev-administration/developers.yaml "$COMPOSE_DIR/developers.yaml"
    echo "  created symlink → dev-administration/developers.yaml"
elif [ -d "$COMPOSE_DIR/developers.yaml" ]; then
    rmdir "$COMPOSE_DIR/developers.yaml" 2>/dev/null || true
    ln -sf dev-administration/developers.yaml "$COMPOSE_DIR/developers.yaml"
    echo "  replaced empty dir with symlink"
fi

# SSH authorized_keys — fjell and dev-admin need to write SSH entries
echo "→ authorized_keys"
mkdir -p "$SSH_DIR"
touch "$SSH_DIR/authorized_keys"
chmod 600 "$SSH_DIR/authorized_keys"
echo "  ensured $SSH_DIR/authorized_keys exists (600)"

# Hermes home — bind-mounted into the hermes container
echo "→ ~/.hermes"
mkdir -p "$HERMES_HOME/plugins"
echo "  ensured $HERMES_HOME/plugins/ exists"

echo ""
echo "=== Done. You can now: docker compose up -d ==="