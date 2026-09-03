#!/usr/bin/env bash
# WS-C.1 — proof that `docker compose up` on an empty volume produces a
# working schema. Spins up a throwaway, disposable postgres:16-alpine
# container (NOT the production one -- separate container name, random
# host port, tmpfs-backed data dir so nothing persists), runs every
# talent-os/backend/migrations/0*.py against it in filename order (the
# same order .github/workflows/deploy.yml now runs them in, 000_baseline
# first), and prints `\dt` / `\d` so the result is visible, not just
# "exit 0".
#
# Usage (from anywhere, self-locates the repo root from this file):
#   scripts/verify_schema_baseline.sh
#
# Requires docker and python3 with asyncpg installed (venv is fine --
# override PYTHON=/path/to/python if the default `python3` on $PATH isn't
# the one with asyncpg).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MIGRATIONS_DIR="$REPO_ROOT/talent-os/backend/migrations"
PYTHON="${PYTHON:-python3}"

CONTAINER_NAME="gsp-schema-verify-$$"
PGPORT="${PGPORT:-15432}"
PGUSER="talentos_write"     # matches talent-os/.env.example / core/config.py's default
PGPASSWORD="verify-throwaway-$$"
PGDB="recruitment_db"

cleanup() {
  echo "=== Cleaning up throwaway container ${CONTAINER_NAME} ==="
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "=== Starting throwaway postgres:16-alpine (container: ${CONTAINER_NAME}, port: ${PGPORT}) ==="
docker run -d \
  --name "$CONTAINER_NAME" \
  --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_USER="$PGUSER" \
  -e POSTGRES_PASSWORD="$PGPASSWORD" \
  -e POSTGRES_DB="$PGDB" \
  -p "127.0.0.1:${PGPORT}:5432" \
  postgres:16-alpine >/dev/null

echo "=== Waiting for postgres to accept connections ==="
for _ in $(seq 1 30); do
  if docker exec "$CONTAINER_NAME" pg_isready -U "$PGUSER" -d "$PGDB" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec "$CONTAINER_NAME" pg_isready -U "$PGUSER" -d "$PGDB"

export POSTGRES_HOST=localhost
export POSTGRES_PORT="$PGPORT"
export POSTGRES_DB="$PGDB"
export POSTGRES_USER="$PGUSER"
export POSTGRES_PASSWORD="$PGPASSWORD"

echo "=== Running every migrations/0*.py in filename order (000_baseline.py first) ==="
FAILED=0
for f in "$MIGRATIONS_DIR"/0*.py; do
  echo "--- $(basename "$f") ---"
  if ! "$PYTHON" "$f"; then
    echo "FAILED: $(basename "$f")"
    FAILED=1
    break
  fi
done

echo "=== Re-running the full set a second time (idempotency check) ==="
if [ "$FAILED" -eq 0 ]; then
  for f in "$MIGRATIONS_DIR"/0*.py; do
    if ! "$PYTHON" "$f"; then
      echo "FAILED on second run (not idempotent): $(basename "$f")"
      FAILED=1
      break
    fi
  done
fi

echo "=== \\dt (all tables) ==="
docker exec "$CONTAINER_NAME" psql -U "$PGUSER" -d "$PGDB" -c '\dt'

echo "=== \\d job_orders (the fee_percentage / fee_value disagreement -- WS-C.1) ==="
docker exec "$CONTAINER_NAME" psql -U "$PGUSER" -d "$PGDB" -c '\d job_orders'

echo "=== \\d candidates ==="
docker exec "$CONTAINER_NAME" psql -U "$PGUSER" -d "$PGDB" -c '\d candidates'

echo "=== \\d matches ==="
docker exec "$CONTAINER_NAME" psql -U "$PGUSER" -d "$PGDB" -c '\d matches'

if [ "$FAILED" -ne 0 ]; then
  echo "=== FAILED -- see output above ==="
  exit 1
fi

echo "=== OK: all migrations applied cleanly on an empty volume, twice (idempotent) ==="
