#!/usr/bin/env bash
# GSP Recruitment — Database (+ legacy uploads) backup
#
# Usage: talent-os/scripts/backup.sh
# Scheduled daily via cron (see talent-os/scripts/install-backup-cron.sh).
#
# Reads only the specific keys it needs from talent-os/.env (never sources
# or exports the whole file, so JWT_SECRET/API_KEY/etc. never leak into
# this script's or its children's environment). Dumps Postgres from the
# running `postgres` compose service over its Unix socket (the official
# postgres image trusts local-socket connections by default — no password
# needed for pg_dump/psql here), gzips, GPG-encrypts, keeps BACKUP_KEEP
# local copies, optionally pushes off-VPS via rclone, and alerts Telegram
# on any failure. On success writes a one-line status file other checks
# (backup-check.sh, backup-freshness.yml) read.
#
# NOTE on timestamps: the backup filename timestamp (TIMESTAMP below) uses
# the host's local time zone (whatever `date` resolves to on the VPS) so
# filenames read naturally next to the 03:15 Europe/Amsterdam cron job.
# The status file, by contrast, is written in UTC (`date -u`) so
# backup-check.sh's age math doesn't depend on the host's TZ setting.
#
# Dry run: BACKUP_DRY_RUN=1 talent-os/scripts/backup.sh
#   prints every docker/gpg/rclone/curl command it would run instead of
#   executing it. No secret values are ever printed, dry run or not.
set -Eeuo pipefail

# ── Locate repo + env ───────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/talent-os/.env"
COMPOSE_FILE="${REPO_ROOT}/docker-compose.yml"

if [ ! -f "$ENV_FILE" ]; then
    echo "[FATAL] $ENV_FILE not found — cannot load config." >&2
    exit 1
fi

# get_env KEY — prints the value of KEY=... from ENV_FILE (last match
# wins; surrounding double or single quotes stripped, a trailing
# " # comment" stripped, no leading/trailing whitespace), or nothing if
# absent. Reads only the one key asked for — never sources or exports the
# file, so unrelated secrets (JWT_SECRET, API_KEY, SMTP_PASS, ...) never
# enter this script's environment or get passed on to docker/gpg/rclone/
# curl. Keys this script reads must therefore be unquoted or quoted with
# no trailing inline comment on the same line (see talent-os/.env.example).
get_env() {
    # "|| true" matters here: with `set -o pipefail`, grep finding no match
    # (the common case for an unset optional key) would otherwise make the
    # whole pipeline -- and thus this function, and thus the `X="$(get_env
    # ...)"` assignment that calls it -- fail under `set -e`, aborting the
    # script before it ever logs anything.
    grep -E "^$1=" "$ENV_FILE" 2>/dev/null \
        | tail -n1 \
        | cut -d= -f2- \
        | sed -e 's/[[:space:]]*#.*$//' -e "s/^[\"']//" -e "s/[\"']$//" -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
        || true
}

DRY_RUN="${BACKUP_DRY_RUN:-0}"

WORKDIR=""
FAILED_STEP=""
DB_SIZE=""
UPLOADS_NONEMPTY=0
TELEGRAM_BOT_TOKEN=""
TELEGRAM_CHAT_ID=""

# ── Helpers (defined before config validation below so a missing
#    required var can die() through Telegram, not just echo+exit) ───────────
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

run() {
    # Executes "$@" normally, or just prints it under BACKUP_DRY_RUN=1.
    if [ "$DRY_RUN" = "1" ]; then
        printf '[DRY-RUN] '
        printf '%q ' "$@"
        printf '\n'
    else
        "$@"
    fi
}

telegram_alert() {
    local text="$1"
    if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
        log "[WARN] TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set — cannot send alert. Message was: $text"
        return 0
    fi
    if [ "$DRY_RUN" = "1" ]; then
        echo "[DRY-RUN] curl -sS -o /dev/null -X POST https://api.telegram.org/bot<REDACTED>/sendMessage -d chat_id=<REDACTED> --data-urlencode text=<REDACTED>"
        return 0
    fi
    curl -sS -o /dev/null --max-time 20 \
        -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=${text}" 2>/dev/null || \
        log "[WARN] Telegram alert itself failed to send."
}

# die MESSAGE — every fatal exit in this script goes through here so a
# Telegram alert always fires before we give up, whatever failed.
die() {
    local msg="$1"
    log "[FATAL] $msg"
    telegram_alert "GSP backup FAILED on $(hostname 2>/dev/null || echo unknown-host): ${msg}"
    exit 1
}

on_error() {
    local line="$1"
    die "unexpected error at line ${line} (step: ${FAILED_STEP:-unknown})"
}
# -E (errtrace) makes this ERR trap fire inside functions and subshells too.
trap 'on_error $LINENO' ERR
cleanup() {
    # `if`, not `[ -n "$WORKDIR" ] && rm -rf ...`: the latter returns the
    # (non-zero) exit status of the `[ ]` test itself whenever WORKDIR is
    # still empty (e.g. a die() before main() ever sets it), and with -E
    # errtrace that would re-fire the ERR trap *from inside this EXIT
    # trap*, calling die() a second time. `if` always returns 0 when its
    # condition is false.
    if [ -n "$WORKDIR" ]; then
        rm -rf "$WORKDIR"
    fi
}
trap cleanup EXIT

# ── Config (all overridable via talent-os/.env) ─────────────────────────────
BACKUP_DIR="$(get_env BACKUP_DIR)"; BACKUP_DIR="${BACKUP_DIR:-/var/backups/gsp}"
BACKUP_KEEP="$(get_env BACKUP_KEEP)"; BACKUP_KEEP="${BACKUP_KEEP:-7}"
BACKUP_GPG_RECIPIENT="$(get_env BACKUP_GPG_RECIPIENT)"
BACKUP_PASSPHRASE_FILE="$(get_env BACKUP_PASSPHRASE_FILE)"
BACKUP_RCLONE_REMOTE="$(get_env BACKUP_RCLONE_REMOTE)"
STATUS_FILE="$(get_env BACKUP_STATUS_FILE)"; STATUS_FILE="${STATUS_FILE:-/var/lib/gsp/backup.last}"

# No silent defaults for these two: a wrong-but-plausible guess (e.g. the
# wrong DB name) would happily "back up" the wrong database. Fail loudly.
POSTGRES_DB="$(get_env POSTGRES_DB)"
[ -n "$POSTGRES_DB" ] || die "POSTGRES_DB missing from ${ENV_FILE}"
POSTGRES_USER="$(get_env POSTGRES_USER)"
[ -n "$POSTGRES_USER" ] || die "POSTGRES_USER missing from ${ENV_FILE}"
# No POSTGRES_PASSWORD is read: pg_dump runs inside the postgres container
# over its local Unix socket, which the official postgres image trusts by
# default (see pg_hba.conf's "local ... trust" line) — no password needed.

TELEGRAM_BOT_TOKEN="$(get_env TELEGRAM_BOT_TOKEN)"
TELEGRAM_CHAT_ID="$(get_env TELEGRAM_CHAT_ID)"

TIMESTAMP="$(date +%Y-%m-%d_%H%M)"
DB_FILENAME="gsp-db-${TIMESTAMP}.sql.gz.gpg"
UPLOADS_FILENAME="gsp-uploads-${TIMESTAMP}.tar.gz.gpg"
DB_PATH="${BACKUP_DIR}/${DB_FILENAME}"
UPLOADS_PATH="${BACKUP_DIR}/${UPLOADS_FILENAME}"

# A correctly-encrypted backup of an essentially-empty dump is still a
# failure worth catching: below this many bytes, something upstream (an
# auth failure inside the container, an empty database, pg_dump erroring
# out and gzip/gpg still emitting a small "valid" empty archive) almost
# certainly went wrong.
MIN_BACKUP_BYTES=4096

main() {
    mkdir -p "$BACKUP_DIR" || die "could not create BACKUP_DIR ${BACKUP_DIR}"
    WORKDIR="$(mktemp -d)"

    if [ -n "$BACKUP_GPG_RECIPIENT" ]; then
        log "GPG mode: --recipient ${BACKUP_GPG_RECIPIENT}"
    elif [ -n "$BACKUP_PASSPHRASE_FILE" ]; then
        if [ "$DRY_RUN" != "1" ] && [ ! -f "$BACKUP_PASSPHRASE_FILE" ]; then
            die "BACKUP_PASSPHRASE_FILE=${BACKUP_PASSPHRASE_FILE} does not exist."
        fi
        if [ "$DRY_RUN" != "1" ]; then
            local perms
            perms="$(stat -c '%a' "$BACKUP_PASSPHRASE_FILE" 2>/dev/null || stat -f '%Lp' "$BACKUP_PASSPHRASE_FILE" 2>/dev/null || echo '??')"
            if [ "$perms" != "600" ]; then
                log "[WARN] ${BACKUP_PASSPHRASE_FILE} is mode ${perms}, expected 600. chmod 600 it."
            fi
        fi
        log "GPG mode: --symmetric via passphrase file"
    else
        die "Neither BACKUP_GPG_RECIPIENT nor BACKUP_PASSPHRASE_FILE is set — refusing to write an unencrypted backup."
    fi

    # ── Step 1: dump + gzip + gpg the database ──────────────────────────
    FAILED_STEP="pg_dump"
    log "Dumping ${POSTGRES_DB} as ${POSTGRES_USER} ..."
    # `bash -o pipefail -c` matters here: without it, a failing pg_dump
    # (auth error, container not running, ...) still lets gzip/gpg exit 0
    # on the empty stream they were handed, producing a small but
    # "successful" backup. The size floor below is the second line of
    # defense in case pipefail itself isn't enough (e.g. pg_dump printing
    # a partial dump before erroring outside strict mode).
    if [ -n "$BACKUP_GPG_RECIPIENT" ]; then
        run bash -o pipefail -c \
          'docker compose -f "$1" --env-file "$2" exec -T postgres \
             pg_dump -U "$3" -d "$4" --no-owner --no-acl \
           | gzip \
           | gpg --encrypt --recipient "$5" --trust-model always --output "$6"' \
          _ "$COMPOSE_FILE" "$ENV_FILE" "$POSTGRES_USER" "$POSTGRES_DB" \
          "$BACKUP_GPG_RECIPIENT" "$DB_PATH"
    else
        run bash -o pipefail -c \
          'docker compose -f "$1" --env-file "$2" exec -T postgres \
             pg_dump -U "$3" -d "$4" --no-owner --no-acl \
           | gzip \
           | gpg --symmetric --batch --yes --cipher-algo AES256 --passphrase-file "$5" --output "$6"' \
          _ "$COMPOSE_FILE" "$ENV_FILE" "$POSTGRES_USER" "$POSTGRES_DB" \
          "$BACKUP_PASSPHRASE_FILE" "$DB_PATH"
    fi

    if [ "$DRY_RUN" != "1" ]; then
        local db_bytes
        db_bytes="$(stat -c %s "$DB_PATH" 2>/dev/null || stat -f %z "$DB_PATH" 2>/dev/null || echo 0)"
        DB_SIZE="$(du -h "$DB_PATH" 2>/dev/null | cut -f1)"
        [ "$db_bytes" -gt "$MIN_BACKUP_BYTES" ] || \
            die "database dump is suspiciously small (${DB_SIZE}, ${db_bytes} bytes); refusing to mark backup successful"
        log "Database backup written: ${DB_PATH} (${DB_SIZE})"
    else
        DB_SIZE="(dry-run, no file written)"
    fi

    # ── Step 2: legacy uploads dir (transitional — CVs are moving to R2
    #    per PR #13; once that's fully rolled out this whole step becomes
    #    a no-op because /app/uploads will be empty) ────────────────────
    FAILED_STEP="uploads-archive"
    log "Checking legacy uploads dir on backend container ..."
    UPLOADS_STAGE="${WORKDIR}/uploads"
    mkdir -p "$UPLOADS_STAGE"
    if [ "$DRY_RUN" = "1" ]; then
        run docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" cp backend:/app/uploads "$UPLOADS_STAGE"
        log "[DRY-RUN] would check whether ${UPLOADS_STAGE}/uploads has any files, then tar+gzip+gpg it to ${UPLOADS_PATH}"
    else
        if docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" cp backend:/app/uploads "$UPLOADS_STAGE" 2>/dev/null; then
            if [ -n "$(find "$UPLOADS_STAGE" -type f -print -quit 2>/dev/null)" ]; then
                UPLOADS_NONEMPTY=1
            fi
        else
            log "No /app/uploads on backend container (already migrated to R2, or container not running) — skipping."
        fi

        if [ "$UPLOADS_NONEMPTY" = "1" ]; then
            log "Archiving legacy uploads ..."
            # (No child `bash -o pipefail -c` needed here, unlike the dump
            # step above: this pipeline runs directly in the current shell,
            # which already has `set -Eeuo pipefail` from the top of the
            # script.)
            if [ -n "$BACKUP_GPG_RECIPIENT" ]; then
                tar -C "$UPLOADS_STAGE" -czf - . \
                    | gpg --encrypt --recipient "$BACKUP_GPG_RECIPIENT" --trust-model always --output "$UPLOADS_PATH"
            else
                tar -C "$UPLOADS_STAGE" -czf - . \
                    | gpg --symmetric --batch --yes --cipher-algo AES256 --passphrase-file "$BACKUP_PASSPHRASE_FILE" --output "$UPLOADS_PATH"
            fi
            local uploads_bytes
            uploads_bytes="$(stat -c %s "$UPLOADS_PATH" 2>/dev/null || stat -f %z "$UPLOADS_PATH" 2>/dev/null || echo 0)"
            # No size floor here beyond ">0": unlike the DB dump, a small
            # uploads archive (a handful of small CVs) is entirely normal.
            [ "$uploads_bytes" -gt 0 ] || \
                die "uploads archive is empty despite a non-empty source directory; refusing to mark backup successful"
            log "Uploads archive written: ${UPLOADS_PATH} ($(du -h "$UPLOADS_PATH" 2>/dev/null | cut -f1))"
        else
            log "Legacy uploads dir is empty — skipping (CVs likely already on R2)."
        fi
    fi

    # ── Step 3: off-VPS copy via rclone (runs BEFORE local retention
    #    prune, so a delayed/slow upload never races a delete of the very
    #    file it's trying to send) ────────────────────────────────────────
    if [ -n "$BACKUP_RCLONE_REMOTE" ]; then
        FAILED_STEP="rclone"
        log "Uploading to ${BACKUP_RCLONE_REMOTE} via rclone ..."
        run rclone copy "$DB_PATH" "$BACKUP_RCLONE_REMOTE"
        if [ "$UPLOADS_NONEMPTY" = "1" ] || [ "$DRY_RUN" = "1" ]; then
            run rclone copy "$UPLOADS_PATH" "$BACKUP_RCLONE_REMOTE"
        fi
    else
        log "[WARN] BACKUP_RCLONE_REMOTE not set — backup stays local-only on this VPS. Not off-VPS-safe."
    fi

    # ── Step 4: retention (keep BACKUP_KEEP local copies of each kind) ──
    FAILED_STEP="retention"
    if [ "$BACKUP_KEEP" -ge 1 ] 2>/dev/null; then
        log "Enforcing local retention: keep ${BACKUP_KEEP} copies."
        for pattern in 'gsp-db-*.sql.gz.gpg' 'gsp-uploads-*.tar.gz.gpg'; do
            run bash -c \
              'cd "$1" && ls -1t $2 2>/dev/null | tail -n "+$(( $3 + 1 ))" | xargs -r rm -f --' \
              _ "$BACKUP_DIR" "$pattern" "$BACKUP_KEEP"
        done
    else
        log "[WARN] BACKUP_KEEP=${BACKUP_KEEP} is not a positive integer — skipping retention prune entirely (nothing deleted)."
    fi

    # ── Step 5: status file ──────────────────────────────────────────────
    FAILED_STEP="status-file"
    if [ "$DRY_RUN" = "1" ]; then
        log "[DRY-RUN] would write status line to ${STATUS_FILE}"
    else
        mkdir -p "$(dirname "$STATUS_FILE")" || die "could not create $(dirname "$STATUS_FILE") for the status file"
        echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') db_size=${DB_SIZE} file=${DB_FILENAME}" > "$STATUS_FILE"
        log "Status written to ${STATUS_FILE}"
    fi

    log "Backup complete."
}

main "$@"
