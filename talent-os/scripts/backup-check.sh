#!/usr/bin/env bash
# GSP Recruitment — backup freshness check.
#
# Run on the VPS (locally, or over SSH from the backup-freshness GitHub
# Actions workflow — see .github/workflows/backup-freshness.yml). Exits
# non-zero if talent-os/scripts/backup.sh has not succeeded in the last
# BACKUP_MAX_AGE_HOURS hours (default 26, i.e. one missed daily run plus
# slack).
set -euo pipefail

STATUS_FILE="${BACKUP_STATUS_FILE:-/var/lib/gsp/backup.last}"
MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-26}"

if [ ! -f "$STATUS_FILE" ]; then
    echo "[FAIL] ${STATUS_FILE} does not exist — backup.sh has never succeeded on this host."
    exit 1
fi

STAMP_LINE="$(head -n1 "$STATUS_FILE")"
STAMP="$(echo "$STAMP_LINE" | awk '{print $1}')"

if [ -z "$STAMP" ]; then
    echo "[FAIL] ${STATUS_FILE} is present but empty/unparseable: '${STAMP_LINE}'"
    exit 1
fi

STAMP_EPOCH="$(date -u -d "$STAMP" +%s 2>/dev/null || date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$STAMP" +%s 2>/dev/null || echo 0)"
NOW_EPOCH="$(date -u +%s)"

if [ "$STAMP_EPOCH" = "0" ]; then
    echo "[FAIL] Could not parse timestamp '${STAMP}' from ${STATUS_FILE}."
    exit 1
fi

AGE_HOURS=$(( (NOW_EPOCH - STAMP_EPOCH) / 3600 ))

echo "Last successful backup: ${STAMP_LINE}"
echo "Age: ${AGE_HOURS}h (max allowed: ${MAX_AGE_HOURS}h)"

if [ "$AGE_HOURS" -gt "$MAX_AGE_HOURS" ]; then
    echo "[FAIL] Backup is stale."
    exit 1
fi

echo "[OK] Backup is fresh."
