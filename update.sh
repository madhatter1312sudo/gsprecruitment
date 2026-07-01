#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# GSP Recruitment — Update Stack
# =============================================================================
# Pulls latest git changes, rebuilds Docker images, and restarts services.
# =============================================================================

COMPOSE_DIR="/home/og/talent-os"

if [ ! -f "${COMPOSE_DIR}/docker-compose.yml" ]; then
    echo "[ERROR] docker-compose.yml not found at ${COMPOSE_DIR}/docker-compose.yml"
    exit 1
fi

echo "[INFO] Changing to project directory: ${COMPOSE_DIR}"
cd "$COMPOSE_DIR"

# ── Pull latest code ────────────────────────────────────────────────────────
echo "[INFO] Pulling latest git changes..."
if [ -d ".git" ]; then
    git fetch --all
    git pull
    echo "[OK] Git pull complete."
else
    echo "[WARN] Not a git repository — skipping pull. Continuing with rebuild..."
fi

# ── Rebuild images ──────────────────────────────────────────────────────────
echo ""
echo "[INFO] Rebuilding Docker images (no cache)..."
docker compose build --no-cache
echo "[OK] Build complete."

# ── Restart services ────────────────────────────────────────────────────────
echo ""
echo "[INFO] Restarting services..."
docker compose down
docker compose up -d

echo ""
echo "[INFO] Waiting for services to initialize..."
sleep 5

# ── Health check ────────────────────────────────────────────────────────────
echo "[INFO] Checking service status..."
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "[INFO] Checking backend health endpoint..."
if curl -sf http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo "[OK] Backend is healthy — update complete."
else
    echo "[WARN] Backend did not respond to health check yet."
    echo "       Check logs with: docker compose logs -f backend"
fi

echo ""
echo "[INFO] Update complete. Running services:"
docker compose ps --format "table {{.Name}}\t{{.Status}}"