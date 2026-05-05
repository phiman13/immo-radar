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

echo "==> docker-compose up -d --build"
ssh "$TARGET" "cd $APP_DIR && docker-compose up -d --build"

echo "==> status"
ssh "$TARGET" "cd $APP_DIR && docker-compose ps"

echo
echo "✓ Deployed."
echo "  Dashboard via Tailscale: http://100.115.184.3:8001  (admin / tutzing2026!)"
echo "  Logs: ssh $TARGET 'cd $APP_DIR && docker-compose logs -f worker'"
