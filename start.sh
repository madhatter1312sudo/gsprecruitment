#!/usr/bin/env bash
# GSP Recruitment — Start Stack
set -euo pipefail

cd "$(dirname "$0")"

echo "🚀 GSP Recruitment — stack starten..."
docker compose up -d

echo "⏳ Wachten op PostgreSQL healthcheck..."
for i in $(seq 1 30); do
  if docker compose exec -T postgres pg_isready -U talentos_admin -d recruitment_db &>/dev/null; then
    echo "✅ PostgreSQL is gezond"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "❌ PostgreSQL healthcheck tijd verstreken"
    exit 1
  fi
  sleep 2
done

echo "⏳ Wachten op backend healthcheck..."
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo "✅ Backend is gezond op http://127.0.0.1:8000"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "❌ Backend healthcheck tijd verstreken"
    exit 1
  fi
  sleep 2
done

echo "✅ GSP Recruitment stack is volledig operationeel"