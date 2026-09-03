#!/bin/bash
# GSP Recruitment — Manual Deploy Script
# Runs from this machine (Zaphosting VPS) to deploy to Hetzner VPS
# Usage: ./scripts/deploy.sh

set -euo pipefail

VPS_USER="gsp"
VPS_HOST="188.245.254.248"
VPS_PATH="/home/gsp/projects/gsp-recruitment"
SSH_KEY="/home/og/.ssh/id_hermes"

echo "🚀 Deploying GSP Recruitment to Hetzner VPS..."
echo ""

# 1. Sync backend code
echo "📦 Syncing backend code..."
rsync -avz -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new" \
  --exclude='.env' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  "$(dirname "$0")/../talent-os/" \
  "${VPS_USER}@${VPS_HOST}:${VPS_PATH}/talent-os/"

# 2. Sync docker-compose.yml
echo "📦 Syncing docker-compose.yml..."
rsync -avz -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new" \
  "$(dirname "$0")/../docker-compose.yml" \
  "${VPS_USER}@${VPS_HOST}:${VPS_PATH}/docker-compose.yml"

# 3. Ensure postgres.env exists (WS-E.6: postgres credentials now live in
#    talent-os/postgres.env, separate from talent-os/.env). Idempotent --
#    a no-op after the first run, and never prints a secret value.
echo "🔐 Checking talent-os/postgres.env..."
ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_HOST}" "
  cd ${VPS_PATH}/talent-os && \
  if [ ! -f postgres.env ]; then
    echo 'postgres.env missing -- generating it from .env (first run only)' && \
    grep -E '^(POSTGRES_DB|POSTGRES_USER|POSTGRES_PASSWORD)=' .env > postgres.env && \
    chmod 600 postgres.env
  else
    echo 'postgres.env already present -- leaving it as-is'
  fi
"

# 4. SSH and restart containers
echo "🔄 Restarting Docker containers..."
ssh -i "$SSH_KEY" "${VPS_USER}@${VPS_HOST}" "
  cd ${VPS_PATH} && \
  docker compose up -d --build backend && \
  sleep 5 && \
  echo '=== Health Check ===' && \
  curl -s http://127.0.0.1:8000/health | python3 -m json.tool
"

echo ""
echo "✅ Deploy complete! Backend updated on Hetzner VPS."
echo "🌐 Frontend auto-deploys via Cloudflare Pages from GitHub."
echo ""
echo "To check logs: ssh -i $SSH_KEY ${VPS_USER}@${VPS_HOST} 'docker logs gsp-backend --tail 50'"