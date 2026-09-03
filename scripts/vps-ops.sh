#!/usr/bin/env bash
# Server-side helper for .github/workflows/ops.yml. Runs ON the VPS as the
# compose user. Usage: bash vps-ops.sh <action> <repo-path>
# Never prints secret values: .env is only grepped for key names.
set -euo pipefail

ACTION="${1:?action}"
ROOT="${2:?repo path}"
ENVFILE="$ROOT/talent-os/.env"

envkey() { # envkey KEY -> value from .env (paths only, never echoed); strips quotes and trailing comments like backup.sh
    local v
    v="$(grep -E "^$1=" "$ENVFILE" 2>/dev/null | tail -1 | cut -d= -f2- || true)"
    v="${v%%#*}"; v="${v%"${v##*[![:space:]]}"}"
    v="${v#\"}"; v="${v%\"}"; v="${v#\'}"; v="${v%\'}"
    printf '%s' "$v"
}
setkey() { # setkey KEY VALUE (idempotent: replace or append)
    sed -i "/^$1=/d" "$ENVFILE"
    printf '%s=%s\n' "$1" "$2" >> "$ENVFILE"
}

case "$ACTION" in
status)
    echo "== host"; hostname; uptime; id -un
    if sudo -n true 2>/dev/null; then echo "sudo: passwordless OK"; else echo "sudo: NOT available without password"; fi
    echo "== disk"; df -h / | tail -1
    echo "== docker"; docker ps --format '{{.Names}}  {{.Status}}  {{.Image}}'
    echo "== compose"; (cd "$ROOT" && docker compose ps --format '{{.Name}} {{.State}}') || true
    echo "== .env key names (values never shown)"
    grep -oE '^[A-Za-z_][A-Za-z0-9_]*=' "$ENVFILE" 2>/dev/null | tr -d '=' | sort | tr '\n' ' '; echo
    echo "== backup"
    ls -la /etc/gsp 2>/dev/null || echo "no /etc/gsp"
    crontab -l 2>/dev/null | grep -i gsp || echo "no gsp cron line"
    du -sh "$(envkey BACKUP_DIR)" /var/backups/gsp "$HOME/gsp-backups" 2>/dev/null || echo "no backup dir yet"
    SF="$(envkey BACKUP_STATUS_FILE)"; cat "${SF:-/var/lib/gsp/backup.last}" 2>/dev/null || echo "no backup status file"
    echo "== legacy CV dir (count only)"
    (cd "$ROOT" && docker compose exec -T backend sh -c 'ls /app/uploads/cv 2>/dev/null | wc -l') || echo "n/a"
    echo "== scripts"; ls -la "$ROOT/talent-os/scripts" 2>/dev/null || echo "no talent-os/scripts on VPS"
    ;;
schema-dump)
    cd "$ROOT"
    docker compose exec -T postgres sh -c 'pg_dump --schema-only --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB"'
    ;;
setup-backup)
    cd "$ROOT"
    for f in backup.sh restore.sh install-backup-cron.sh backup-check.sh; do
        [ -f "talent-os/scripts/$f" ] || { echo "missing talent-os/scripts/$f on the VPS (deploy syncs talent-os/backend only?)" >&2; exit 2; }
        chmod +x "talent-os/scripts/$f"
    done
    touch "$ENVFILE"; chmod 600 "$ENVFILE"
    if sudo -n true 2>/dev/null; then
        PF=/etc/gsp/backup-passphrase
        sudo mkdir -p /etc/gsp
        if [ ! -s "$PF" ]; then
            sudo sh -c "head -c 48 /dev/urandom | base64 > $PF"
            echo "passphrase file created at $PF (copy it to the owner's password manager: it is NOT in any backup)"
        else
            echo "passphrase file already present at $PF"
        fi
        sudo chown "$(id -un):$(id -gn)" "$PF"; sudo chmod 600 "$PF"
    else
        PF="$HOME/.gsp/backup-passphrase"
        mkdir -p "$HOME/.gsp" "$HOME/gsp-backups"; chmod 700 "$HOME/.gsp" "$HOME/gsp-backups"
        if [ ! -s "$PF" ]; then
            head -c 48 /dev/urandom | base64 > "$PF"
            echo "passphrase file created at $PF (no sudo: under HOME; copy it to the owner's password manager)"
        else
            echo "passphrase file already present at $PF"
        fi
        chmod 600 "$PF"
        setkey BACKUP_DIR "$HOME/gsp-backups"
        setkey BACKUP_STATUS_FILE "$HOME/.gsp/backup.last"
    fi
    setkey BACKUP_PASSPHRASE_FILE "$PF"
    grep -q '^BACKUP_KEEP=' "$ENVFILE" || setkey BACKUP_KEEP 14
    echo "== install cron"
    if sudo -n true 2>/dev/null; then
        bash talent-os/scripts/install-backup-cron.sh
    else
        # install-backup-cron.sh needs sudo (dirs under /var, logrotate).
        # Without it: same schedule and marker, log under HOME, no logrotate.
        LOG="$HOME/.gsp/backup.log"
        MARKER="# gsp-backup (managed by install-backup-cron.sh)"
        LINE="15 3 * * * $ROOT/talent-os/scripts/backup.sh >> $LOG 2>&1 $MARKER"
        { echo "CRON_TZ=Europe/Amsterdam"; crontab -l 2>/dev/null | grep -v 'gsp-backup (managed by' | grep -v '^CRON_TZ='; echo "$LINE"; } | crontab -
        echo "cron installed without sudo (log: $LOG, no logrotate)"
    fi
    crontab -l | grep -i gsp
    echo "== first backup (local only until BACKUP_RCLONE_REMOTE is set)"
    bash talent-os/scripts/backup.sh
    echo "== freshness"
    SF="$(envkey BACKUP_STATUS_FILE)"; [ -n "$SF" ] && export BACKUP_STATUS_FILE="$SF"
    bash talent-os/scripts/backup-check.sh
    ;;
backup-now)
    cd "$ROOT"
    bash talent-os/scripts/backup.sh
    SF="$(envkey BACKUP_STATUS_FILE)"; [ -n "$SF" ] && export BACKUP_STATUS_FILE="$SF"
    bash talent-os/scripts/backup-check.sh
    ;;
backup-check)
    cd "$ROOT"
    SF="$(envkey BACKUP_STATUS_FILE)"; [ -n "$SF" ] && export BACKUP_STATUS_FILE="$SF"
    bash talent-os/scripts/backup-check.sh
    ;;
*)
    echo "unknown action: $ACTION" >&2; exit 64
    ;;
esac
