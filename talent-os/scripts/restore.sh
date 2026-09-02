#!/usr/bin/env bash
# GSP Recruitment — Restore a gsp-db-*.sql.gz.gpg backup
#
# Usage:
#   restore.sh --verify <backup-file.sql.gz.gpg>
#       Restores into a throwaway, randomly-passworded postgres:16-alpine
#       container (no port published — psql runs inside the container via
#       `docker exec`), runs `SELECT count(*) FROM users` and lists
#       tables, prints the results, then removes the container. Nothing
#       production is touched. This is the monthly restore test.
#
#   restore.sh --yes <backup-file.sql.gz.gpg> [--target-db NAME]
#       Restores into the RUNNING compose stack's postgres service.
#       Destructive — requires the literal --yes flag. Defaults to
#       restoring into a new database (gsp_restore_<timestamp>) rather
#       than overwriting POSTGRES_DB, unless --overwrite is also given
#       (which requires `docker compose stop backend` first — see
#       docs/BACKUP-RESTORE.md §4).
#
# Reads only the specific keys it needs from talent-os/.env (never sources
# or exports the whole file). No database password is read or used: both
# the live compose postgres and the throwaway verify container are
# accessed over their local Unix socket, which the official postgres
# image trusts by default.
#
# Dry run: BACKUP_DRY_RUN=1 restore.sh ...
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/talent-os/.env"
COMPOSE_FILE="${REPO_ROOT}/docker-compose.yml"

usage() {
    cat >&2 <<'EOF'
Usage:
  restore.sh --verify <backup-file.sql.gz.gpg>
  restore.sh --yes <backup-file.sql.gz.gpg> [--target-db NAME] [--overwrite]

See the header of this file for details.
EOF
    exit 1
}

[ $# -ge 1 ] || usage

MODE=""
FILE=""
TARGET_DB=""
OVERWRITE=0

while [ $# -gt 0 ]; do
    case "$1" in
        --verify) MODE="verify"; shift ;;
        --yes) MODE="live"; shift ;;
        --target-db) TARGET_DB="$2"; shift 2 ;;
        --overwrite) OVERWRITE=1; shift ;;
        -*) usage ;;
        *) FILE="$1"; shift ;;
    esac
done

[ -n "$MODE" ] && [ -n "$FILE" ] || usage
[ -f "$FILE" ] || { echo "[FATAL] Backup file not found: $FILE" >&2; exit 1; }

if [ ! -f "$ENV_FILE" ]; then
    echo "[FATAL] $ENV_FILE not found — cannot load config." >&2
    exit 1
fi

# get_env KEY — see backup.sh for the rationale: read only the one key
# asked for, never source/export the whole .env file. Strips surrounding
# double/single quotes and a trailing " # comment" (see talent-os/.env.example).
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
BACKUP_GPG_RECIPIENT="$(get_env BACKUP_GPG_RECIPIENT)"
BACKUP_PASSPHRASE_FILE="$(get_env BACKUP_PASSPHRASE_FILE)"
# No silent defaults for these two: a wrong-but-plausible guess (e.g. the
# wrong DB name) would happily restore into/over the wrong database.
POSTGRES_DB="$(get_env POSTGRES_DB)"
[ -n "$POSTGRES_DB" ] || { echo "[FATAL] POSTGRES_DB missing from ${ENV_FILE}" >&2; exit 1; }
POSTGRES_USER="$(get_env POSTGRES_USER)"
[ -n "$POSTGRES_USER" ] || { echo "[FATAL] POSTGRES_USER missing from ${ENV_FILE}" >&2; exit 1; }

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

run() {
    if [ "$DRY_RUN" = "1" ]; then
        printf '[DRY-RUN] '
        printf '%q ' "$@"
        printf '\n'
    else
        "$@"
    fi
}

WORKDIR="$(mktemp -d)"
cleanup() { rm -rf "$WORKDIR" 2>/dev/null || true; }
trap cleanup EXIT

decrypt_to() {
    # decrypt_to <input.gz.gpg> <output.sql>
    # Public-key backups (BACKUP_GPG_RECIPIENT was used to encrypt) decrypt
    # with whatever secret key is on this host's GPG keyring — no
    # passphrase needed here. Symmetric backups need BACKUP_PASSPHRASE_FILE.
    local in="$1" out="$2"
    if [ -n "$BACKUP_GPG_RECIPIENT" ]; then
        run bash -c 'gpg --decrypt --output "$1" "$2"' _ "${out}.gz" "$in"
    else
        [ -n "$BACKUP_PASSPHRASE_FILE" ] || { echo "[FATAL] BACKUP_PASSPHRASE_FILE not set — needed to decrypt a symmetric backup." >&2; exit 1; }
        run bash -c 'gpg --decrypt --batch --yes --passphrase-file "$1" --output "$2" "$3"' \
          _ "$BACKUP_PASSPHRASE_FILE" "${out}.gz" "$in"
    fi
    run gunzip -f "${out}.gz"
}

if [ "$MODE" = "verify" ]; then
    CONTAINER="gsp-restore-verify-$$"
    # Random one-time password for the throwaway container. Passed to
    # `docker run` by *name only* (`-e POSTGRES_PASSWORD`, no `=value`) so
    # the value is picked up from this shell's exported environment and
    # never appears as a literal in argv or in dry-run output.
    VERIFY_PW="$(head -c 24 /dev/urandom | base64)"

    # Tear the container down no matter how this branch exits (success,
    # failure, or the ERR trap firing partway through).
    trap 'docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; cleanup' EXIT

    log "Decrypting ${FILE} ..."
    SQL_FILE="${WORKDIR}/restore.sql"
    decrypt_to "$FILE" "$SQL_FILE"

    log "Starting throwaway postgres:16-alpine (container ${CONTAINER}, no port published) ..."
    (
        export POSTGRES_PASSWORD="$VERIFY_PW"
        run docker run -d --name "$CONTAINER" \
            -e POSTGRES_PASSWORD -e POSTGRES_USER=verify -e POSTGRES_DB=verify \
            postgres:16-alpine
    )

    if [ "$DRY_RUN" != "1" ]; then
        log "Waiting for it to accept connections ..."
        # -h 127.0.0.1 forces a TCP check against the *final* postgres
        # server: the entrypoint briefly runs a temporary server over the
        # Unix socket only while it does first-time setup, so a socket-only
        # `pg_isready -U verify` (no -h) can report ready before the real
        # server is actually listening. TCP is only served once that setup
        # is done.
        ready=0
        for _ in $(seq 1 30); do
            if docker exec "$CONTAINER" pg_isready -h 127.0.0.1 -U verify >/dev/null 2>&1; then
                ready=1
                break
            fi
            sleep 1
        done
        if [ "$ready" != "1" ]; then
            echo "[FATAL] ${CONTAINER} never became ready within 30s." >&2
            exit 1
        fi
    fi

    log "Loading dump ..."
    run bash -c 'docker exec -i "$1" psql -v ON_ERROR_STOP=1 -U verify -d verify < "$2"' _ "$CONTAINER" "$SQL_FILE"

    log "Verification query results:"
    run bash -c 'docker exec -i "$1" psql -U verify -d verify -c "SELECT count(*) FROM users;"' _ "$CONTAINER"
    run bash -c 'docker exec -i "$1" psql -U verify -d verify -c "\dt"' _ "$CONTAINER"

    log "Tearing down ${CONTAINER} ..."
    run docker rm -f "$CONTAINER"
    trap cleanup EXIT
    log "Restore verification complete."
    exit 0
fi

# ── live restore ─────────────────────────────────────────────────────────
if [ "$OVERWRITE" = "1" ]; then
    if [ -z "$TARGET_DB" ]; then
        TARGET_DB="$POSTGRES_DB"
    fi
    echo "!!! --overwrite will DROP AND REPLACE database '${TARGET_DB}' on the running stack. !!!" >&2
    echo "!!! Run 'docker compose stop backend' first — see docs/BACKUP-RESTORE.md §4. !!!" >&2
else
    TARGET_DB="${TARGET_DB:-gsp_restore_$(date +%Y%m%d_%H%M%S)}"
fi

log "Restoring ${FILE} into database '${TARGET_DB}' on the running compose stack."
SQL_FILE="${WORKDIR}/restore.sql"
decrypt_to "$FILE" "$SQL_FILE"

if [ "$OVERWRITE" = "1" ]; then
    run bash -c \
      'docker compose -f "$1" --env-file "$2" exec -T postgres \
         psql -U "$3" -d postgres -c "DROP DATABASE IF EXISTS \"$4\" WITH (FORCE);" && \
       docker compose -f "$1" --env-file "$2" exec -T postgres \
         psql -U "$3" -d postgres -c "CREATE DATABASE \"$4\";"' \
      _ "$COMPOSE_FILE" "$ENV_FILE" "$POSTGRES_USER" "$TARGET_DB"
else
    run bash -c \
      'docker compose -f "$1" --env-file "$2" exec -T postgres \
         psql -U "$3" -d postgres -c "CREATE DATABASE \"$4\";"' \
      _ "$COMPOSE_FILE" "$ENV_FILE" "$POSTGRES_USER" "$TARGET_DB"
fi

# SQL is fed over stdin on the host side — the container never sees a host
# file path (there is nothing at that path inside the container).
# -v ON_ERROR_STOP=1 makes psql abort on the first SQL error instead of
# plowing on and reporting success anyway; --single-transaction wraps the
# whole load in one transaction so a failed/aborted restore leaves the
# target database exactly as it was (nothing partially applied), even for
# --overwrite's freshly (re)created database.
run bash -c \
  'docker compose -f "$1" --env-file "$2" exec -T postgres \
     psql -v ON_ERROR_STOP=1 --single-transaction -U "$3" -d "$4" < "$5"' \
  _ "$COMPOSE_FILE" "$ENV_FILE" "$POSTGRES_USER" "$TARGET_DB" "$SQL_FILE"

log "Restore complete into database '${TARGET_DB}'."
[ "$OVERWRITE" = "1" ] || log "This was a side-by-side restore, not an overwrite. Point the app at '${TARGET_DB}' manually if that was the intent, or rerun with --overwrite."
