#!/usr/bin/env bash
# GSP Recruitment — Stop Stack
set -euo pipefail

cd "$(dirname "$0")"

echo "🛑 GSP Recruitment — stack stoppen..."
docker compose down
echo "✅ Stack gestopt"