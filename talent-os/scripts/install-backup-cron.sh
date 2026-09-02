#!/usr/bin/env bash
# GSP Recruitment — install the daily backup cron job on the VPS.
#
# Run this ONCE on the Hetzner VPS, as the user that owns the compose
# stack (the same user deploy.yml SSHes in as):
#   bash talent-os/scripts/install-backup-cron.sh
#
# Idempotent: re-running it replaces any existing GSP-backup line rather
# than duplicating it. Schedules daily 03:15 Europe/Amsterdam. Needs
# passwordless sudo (or run as root) to create /var/backups/gsp,
# /var/lib/gsp, the log file, and /etc/logrotate.d/gsp-backup with the
# right ownership -- see docs/BACKUP-RESTORE.md §1 if that's not
# available and you'd rather point BACKUP_DIR/BACKUP_STATUS_FILE at
# $HOME instead.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="${SCRIPT_DIR}/backup.sh"
LOG_FILE="/var/log/gsp-backup.log"
MARKER="# gsp-backup (managed by install-backup-cron.sh)"
OWNER_USER="${USER:-$(id -un)}"

if [ ! -x "$BACKUP_SCRIPT" ]; then
    echo "[FATAL] ${BACKUP_SCRIPT} is not executable. chmod +x it first." >&2
    exit 1
fi

# ── Directories the cron user needs to be able to write to. These match
#    the BACKUP_DIR / BACKUP_STATUS_FILE defaults in .env.example -- if
#    you've overridden either in talent-os/.env, create/own those paths
#    yourself instead. mode 700: backups may contain decrypted material
#    transiently and the status file's contents are operational, not
#    secret, but there's no reason to make either world-readable. ──────
sudo install -d -o "$OWNER_USER" -g "$OWNER_USER" -m 700 /var/backups/gsp /var/lib/gsp
sudo touch "$LOG_FILE"
sudo chown "$OWNER_USER":"$OWNER_USER" "$LOG_FILE"

# ── Log rotation, so $LOG_FILE doesn't grow unbounded ──────────────────
sudo tee /etc/logrotate.d/gsp-backup > /dev/null <<EOF
${LOG_FILE} {
    weekly
    rotate 8
    compress
    missingok
    notifempty
    copytruncate
}
EOF
echo "Installed /etc/logrotate.d/gsp-backup (weekly, rotate 8, compress)."

CRON_LINE="15 3 * * * ${BACKUP_SCRIPT} >> ${LOG_FILE} 2>&1 ${MARKER}"
TZ_LINE="CRON_TZ=Europe/Amsterdam"

existing="$(crontab -l 2>/dev/null || true)"

# Drop any previous gsp-backup line(s), keep everything else.
filtered="$(printf '%s\n' "$existing" | grep -v "$MARKER" || true)"

# Make sure CRON_TZ=Europe/Amsterdam is set once, at the top. Not every
# cron implementation honours CRON_TZ (Vixie cron / cronie do; some
# minimal cron daemons don't) -- if the timestamps in $LOG_FILE come out
# an hour off after installing this, your cron daemon ignores CRON_TZ:
# convert 03:15 Europe/Amsterdam to the server's local/UTC time by hand
# and edit the "15 3" fields below (mind CET/CEST — the offset is not
# constant across the year). Note backup.sh's own filename timestamps use
# whatever TZ `date` resolves to on this host, while its status file is
# always written in UTC -- see the comment at the top of backup.sh.
if ! printf '%s\n' "$filtered" | grep -qx "$TZ_LINE"; then
    filtered="$(printf '%s\n%s\n' "$TZ_LINE" "$filtered")"
fi

new_crontab="$(printf '%s\n%s\n' "$filtered" "$CRON_LINE" | sed '/^$/d')"

echo "$new_crontab" | crontab -
echo "Installed cron job:"
echo "  $CRON_LINE"
echo "Verify with: crontab -l"
echo "Logs go to: $LOG_FILE"
echo ""
echo "Rollback: crontab -l | grep -v '$MARKER' | crontab -"
echo "          sudo rm -f /etc/logrotate.d/gsp-backup"
