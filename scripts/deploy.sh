#!/usr/bin/env bash
# Deploy immo-radar to the Hetzner VPS.
# Usage: bash scripts/deploy.sh
set -euo pipefail

TARGET="root@89.167.67.26"
APP_DIR="/opt/immo-radar"

echo "==> rsync project to $TARGET:$APP_DIR"
ssh "$TARGET" "mkdir -p $APP_DIR"
rsync -avz --delete \
  --exclude='.venv' --exclude='data' --exclude='__pycache__' \
  --exclude='.git' --exclude='*.pyc' --exclude='.ruff_cache' \
  --exclude='.pytest_cache' \
  ./ "$TARGET:$APP_DIR/"

echo "==> docker compose up -d --build"
ssh "$TARGET" "cd $APP_DIR && docker compose up -d --build"

echo "==> status"
ssh "$TARGET" "cd $APP_DIR && docker compose ps"

echo "==> caddy vhost: immo.herrlich.dev"
ssh "$TARGET" 'bash -s' <<'REMOTE'
CADDYFILE=/etc/caddy/Caddyfile
if grep -q "immo.herrlich.dev" "$CADDYFILE"; then
    echo "  [skip] immo.herrlich.dev already in Caddyfile"
else
    cat >> "$CADDYFILE" <<'EOF'

immo.herrlich.dev {
    basicauth {
        admin $2a$14$.dJIfNvGH1LbWupB02VuLeXBMHDzMA9BSRTbB0ceUn2rmcyv4j5N6
    }
    reverse_proxy localhost:8001
}
EOF
    systemctl reload caddy
    echo "  [done] immo.herrlich.dev vhost added and caddy reloaded"
fi
REMOTE

echo
echo "✓ Deployed."
echo "  Dashboard: https://immo.herrlich.dev  (admin / tutzing2026!)"
echo "  Logs: ssh $TARGET 'cd $APP_DIR && docker compose logs -f worker'"
