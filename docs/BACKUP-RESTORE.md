# Backup & restore

Covers `talent-os/scripts/backup.sh`, `restore.sh`, `install-backup-cron.sh`
and `backup-check.sh`, plus `.github/workflows/backup-freshness.yml`.

All commands below run **on the Hetzner VPS** (`gsp@188.245.254.248`,
`/home/gsp/projects/gsp-recruitment`) unless marked otherwise. This repo
cannot reach that host from the sandbox — copy-paste these over your own
SSH session.

## 1. One-time setup (owner actions)

### 1a. Passphrase file (symmetric GPG — simplest option)

```bash
ssh gsp@188.245.254.248
sudo mkdir -p /etc/gsp
sudo sh -c 'head -c 48 /dev/urandom | base64 > /etc/gsp/backup-passphrase'
sudo chmod 600 /etc/gsp/backup-passphrase
sudo chown gsp:gsp /etc/gsp/backup-passphrase
```

Then set in `talent-os/.env` on the VPS:

```
BACKUP_PASSPHRASE_FILE=/etc/gsp/backup-passphrase
```

Store a copy of that passphrase somewhere off the VPS too (password
manager) — if the VPS disk is lost, the passphrase file goes with it and
your off-VPS `.gpg` backups become unrecoverable.

**Alternative — public-key mode:** if you already run GPG with a real
keypair, set `BACKUP_GPG_RECIPIENT=you@example.com` in `talent-os/.env`
instead (leave `BACKUP_PASSPHRASE_FILE` empty). Only the private key
holder can decrypt/restore; back that private key up separately.

### 1b. rclone remote (off-VPS copy)

Pick any rclone-supported target — a Hetzner Storage Box (SFTP) or any
S3-compatible bucket (Backblaze B2, Wasabi, Cloudflare R2, AWS S3, etc.).
This repo does not choose a vendor; pick the cheapest tier you're
comfortable with.

```bash
ssh gsp@188.245.254.248
rclone config   # interactive; name the remote e.g. "gsp-backups"
```

Then set in `talent-os/.env`:

```
BACKUP_RCLONE_REMOTE=gsp-backups:gsp-db-backups
```

Leaving this empty is allowed but means backups are **local-only on the
VPS** — a lost/compromised VPS loses the backups with it. `backup.sh`
prints a `[WARN]` every run when this is unset.

**Prune the remote too — `BACKUP_KEEP` only prunes local copies.** Off-VPS
copies accumulate forever unless you set a retention rule on the remote
itself:

- **Hetzner Storage Box (or any SFTP/rclone remote without native
  lifecycle rules):** add a periodic cron line on the VPS (or wherever
  you run `rclone`) to delete anything older than your chosen window,
  e.g. 90 days:
  ```bash
  # crontab -e (weekly is plenty -- this doesn't need to run daily)
  0 4 * * 0 rclone delete --min-age 90d gsp-backups:gsp-db-backups >> /var/log/gsp-backup-prune.log 2>&1
  ```
- **S3-compatible bucket (Backblaze B2, Wasabi, Cloudflare R2, AWS S3,
  etc.):** use the provider's native bucket lifecycle rules instead of a
  cron job — e.g. "expire objects older than 90 days" on the
  `gsp-db-backups` prefix, configured once in the provider's
  dashboard/API. Prefer this over `rclone delete` on S3-compatible
  targets since it runs server-side and can't be skipped by a missed
  cron run.

Either way, pick a window at least as long as you'd ever plausibly need
to restore from (e.g. long enough to catch an issue that wasn't noticed
immediately) — this is separate from, and normally longer than,
`BACKUP_KEEP`'s local retention.

### 1c. Telegram alerting

Reuse the same bot/chat already used by `.github/workflows/uptime.yml`.
Add to `talent-os/.env` on the VPS (host-side, separate from the
GitHub Actions secrets of the same name used in CI):

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

If these are absent, `backup.sh` logs a warning instead of erroring out
— a failed backup still exits non-zero and still shows up in
`/var/log/gsp-backup.log` / cron mail, it just won't reach Telegram.

### 1d. Install the cron job

```bash
cd /home/gsp/projects/gsp-recruitment
chmod +x talent-os/scripts/backup.sh talent-os/scripts/restore.sh \
  talent-os/scripts/install-backup-cron.sh talent-os/scripts/backup-check.sh
bash talent-os/scripts/install-backup-cron.sh
crontab -l   # verify
```

Needs passwordless `sudo` (or run as root) — it creates and `chown`s
`/var/backups/gsp` and `/var/lib/gsp` (mode 700, owned by the invoking
user, matching the `BACKUP_DIR` / `BACKUP_STATUS_FILE` defaults in
`.env.example`) and `/var/log/gsp-backup.log`, and installs
`/etc/logrotate.d/gsp-backup` (weekly, rotate 8, compress) so the log
doesn't grow unbounded. If `sudo` isn't available on this host, either
grant it for this one script or point `BACKUP_DIR` / `BACKUP_STATUS_FILE`
in `talent-os/.env` at paths under the cron user's own `$HOME` instead
(e.g. `BACKUP_DIR=$HOME/gsp-backups`) and create those directories
yourself — the rest of `backup.sh` doesn't care where they live.

This installs a daily `03:15 Europe/Amsterdam` job. If your cron daemon
doesn't honour `CRON_TZ` (the script warns about this), convert 03:15
Amsterdam to your server's local/UTC time yourself and edit the `15 3`
fields in the crontab line — mind that the CET/CEST offset isn't
constant across the year.

**Rollback:**
```bash
crontab -l | grep -v 'gsp-backup (managed by' | crontab -
sudo rm -f /etc/logrotate.d/gsp-backup
```

### 1e. GitHub Actions secrets

`backup-freshness.yml` reuses `VPS_SSH_PRIVATE_KEY` (already present,
used by `deploy.yml`) and `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`
(already present, used by `uptime.yml`). **No new Actions secret names
are required** if `uptime.yml` is already working. If it isn't, add
those two under repo Settings → Secrets and variables → Actions.

## 2. Running a backup manually

```bash
cd /home/gsp/projects/gsp-recruitment
talent-os/scripts/backup.sh
```

Dry run (prints the commands it would run, touches nothing):

```bash
BACKUP_DRY_RUN=1 talent-os/scripts/backup.sh
```

On success: a new `gsp-db-YYYY-MM-DD_HHMM.sql.gz.gpg` (and, if
`/app/uploads` on the backend container is non-empty, a matching
`gsp-uploads-*.tar.gz.gpg`) appears in `$BACKUP_DIR`, gets pushed to the
rclone remote if configured, and `/var/lib/gsp/backup.last` is updated.
On failure: non-zero exit, Telegram alert (if configured), and
`/var/lib/gsp/backup.last` is left untouched (so freshness checks catch
it).

## 3. Verifying a backup (restore test)

This is the documented restore test — run it **monthly**, and after any
schema migration:

```bash
talent-os/scripts/restore.sh --verify /var/backups/gsp/gsp-db-2026-09-02_0315.sql.gz.gpg
```

This spins up a throwaway `postgres:16-alpine` container with a random
one-time password and no published port (the dump is loaded and queried
via `docker exec`, entirely inside the container — nothing is exposed on
the host network), runs `SELECT count(*) FROM users` and lists tables
(`\dt`), prints both, then removes the container. Nothing in the running
stack is touched. Put the output (row count + table list) in the monthly
ops log as evidence.

## 4. Restoring for real

**Side-by-side (default, safe):** restores into a new database on the
running Postgres instance without touching the live one — good for
inspecting old data or a staged cutover.

```bash
talent-os/scripts/restore.sh --yes /var/backups/gsp/gsp-db-2026-09-02_0315.sql.gz.gpg
# restores into gsp_restore_<timestamp> — the script prints the exact name
```

**Overwrite the live database (destructive):** stop the backend
**first, every time** — it drops `$POSTGRES_DB` with `DROP DATABASE ...
WITH (FORCE)` (force-disconnecting any live sessions from it, e.g. the
backend's own connection pool) and recreates it, so the backend must not
be writing to it mid-restore:

```bash
docker compose stop backend
talent-os/scripts/restore.sh --yes --overwrite /var/backups/gsp/gsp-db-2026-09-02_0315.sql.gz.gpg
docker compose start backend
```

`restore.sh` itself prints a warning to do this but does not enforce it
— stopping the backend is the operator's responsibility every time this
flag is used.

**Rollback if a live restore goes wrong:** every backup file is
immutable — restore the previous `.sql.gz.gpg` the same way. Nothing is
deleted by `restore.sh` itself.

## 5. CV files / R2 note (owner action)

CVs are transitional: `backup.sh` still archives the legacy
`backend:/app/uploads` directory (step 2) because until R2 is configured
in production, that's where CVs actually live — and it disappears on
every deploy (container filesystem). Once PR #13's R2 setup is run
(`R2_ENDPOINT` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET`
set in `talent-os/.env`), new CVs go to R2 instead and the uploads-archive
step in `backup.sh` naturally becomes a no-op (it already skips silently
when the directory is empty — no script change needed then).

**R2 has its own durability, but not its own history** — a bucket alone
has no protection against accidental/malicious deletion or overwrite.
**Owner action once R2 is live:** enable bucket versioning so deleted/
overwritten objects stay recoverable:

1. Cloudflare dashboard → R2 → the CV bucket → Settings → **Object
   versioning** → enable.
2. Optionally add a lifecycle rule to expire noncurrent versions after
   e.g. 90 days, so old versions don't accumulate cost indefinitely.

This is a dashboard/API action outside this repo's `wrangler.jsonc`
scope — document it here rather than scripting it, since it's a one-time
bucket setting.

## 6. Freshness monitoring

`.github/workflows/backup-freshness.yml` runs daily (08:00 UTC), SSHes
to the VPS the same way `deploy.yml` does, and runs
`talent-os/scripts/backup-check.sh` there, which fails if
`/var/lib/gsp/backup.last` is missing or older than 26 hours. On failure
it sends the same Telegram alert pattern as `uptime.yml`.

## Known limitations

- Both restore paths feed plain-SQL `pg_dump` output through `psql` over
  stdin (no `--format=custom` / `pg_restore -j`), so restores run
  serially — fine at current DB size, would need a custom-format dump
  and `pg_restore -j` for a much larger database.
- The overwrite-restore path stops nothing on its own; the operator must
  remember to `docker compose stop backend` first, every time — see §4.
- `BACKUP_RCLONE_REMOTE` is optional — a fresh install with only the
  passphrase file configured is still local-only until rclone is set up
  (step 1b).
- Cron's `CRON_TZ` support varies by distro/cron implementation; see the
  warning in `install-backup-cron.sh`.
- Neither `pg_dump` nor `psql` here is ever given a password: both the
  live compose `postgres` service and the throwaway `--verify` container
  are reached over their local Unix socket, which the official
  `postgres` image trusts by default (`pg_hba.conf`'s `local ... trust`
  line). If that default is ever hardened (e.g.
  `POSTGRES_HOST_AUTH_METHOD` changed), both scripts will need a password
  passed via `-e PGPASSWORD` (name-only, value exported, never as an
  argv literal) again.
- `VPS_HOST`/`VPS_USER` (`188.245.254.248` / `gsp`) are duplicated across
  `scripts/deploy.sh`, `.github/workflows/deploy.yml`, and
  `.github/workflows/backup-freshness.yml` — tracked as follow-up
  WS-E.6 to hoist them into shared variables instead of copy-pasting the
  literal.
