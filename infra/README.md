# Infra

What the two devops GitHub Actions workflows do, what the owner needs to set
up for them, and how to roll each one back by hand.

## `.github/workflows/deploy.yml`

Runs on every push to `main`. Order: run tests → rsync `talent-os/` + the
root `docker-compose.yml` to the VPS → rsync `website/` to the path Caddy
serves (dotfiles excluded; the resolved path is captured as
`$WEBSITE_TARGET` for the Caddyfile step) → tag the current backend image
as `previous` → `docker compose up -d --build` for **all** services
(postgres, backend, redis, worker) → poll `/health` → roll the backend
image back to `previous` on failure. **Only after that backend deploy has
concluded**, and gated on it having succeeded, does the workflow push
`infra/Caddyfile` (its `root *` line rewritten to `$WEBSITE_TARGET` on a
local copy, never the committed file) to `/etc/caddy/Caddyfile` —
validated, backed up, old backups pruned to the last 10, auto-restored on
a failed post-reload check. This ordering is deliberate: every Caddy step
is conditioned on the backend-restart step's own outcome
(`steps.restart.outcome`), never on the bare job status, so a Caddy
problem can fail the overall workflow run (visibly, for the owner to
notice) but can **never** trigger a backend rollback or block/undo an
already-successful backend deploy.

### Caddyfile deploy — sudoers requirement

The `gsp` SSH user needs passwordless sudo for exactly these commands to
manage `/etc/caddy/Caddyfile`. Add this on the VPS with `sudo visudo -f
/etc/sudoers.d/gsp-caddy`:

```
gsp ALL=(root) NOPASSWD: /usr/bin/cp /tmp/Caddyfile.new /etc/caddy/Caddyfile, \
  /usr/bin/cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak.*, \
  /usr/bin/cp /etc/caddy/Caddyfile.bak.* /etc/caddy/Caddyfile, \
  /usr/sbin/caddy validate --config /tmp/Caddyfile.new, \
  /usr/sbin/caddy version, \
  /usr/bin/systemctl reload caddy, \
  /usr/bin/rm -- /etc/caddy/Caddyfile.bak.*
```

(Adjust binary paths to match `which cp`, `which caddy`, `which
systemctl`, `which rm` on the VPS if they differ.) Every command the
workflow runs under `sudo` matches one of these lines exactly, including
the readiness probe: it runs `sudo -n /usr/sbin/caddy version` (not `sudo
-n true`, which can never succeed against a scoped grant like this one,
since `true` is not itself one of the NOPASSWD commands). Keep this list
and the workflow in sync — if you add a new `sudo` call to the Caddyfile
step, add the matching exact-command line here.

Without this sudoers entry, the deploy step detects the `caddy version`
probe failing and **skips the Caddyfile push with a loud `::warning::`**
rather than failing the whole deploy — backend/worker/website still
deploy normally. The `rm --` line only prunes old
`Caddyfile.bak.*` files (keeping the 10 most recent); pruning failing or
being unavailable is not fatal to the deploy either.

### Known risk: `website/.host` path mismatch

`website/.host` (now a pointer doc) previously described the served
website path as `/home/og/projects/gsp-recruitment/website` — note the
`og` user, not `gsp`. Every other path in this repo's tooling
(`docker-compose.yml`, `deploy.yml`, the R2 setup workflow) uses
`/home/gsp/projects/gsp-recruitment`. This discrepancy could not be
verified from the sandbox (no SSH access to production). `infra/Caddyfile`
and the website-sync step in `deploy.yml` both currently use the `og`
path, on the reasoning that a wrong path there fails **loudly** (rsync/cp
permission or path error visible in the Actions log) rather than silently
deploying the website to a directory nothing actually serves.

**Before the first run of the updated `deploy.yml`, the owner should
confirm on the VPS**:

```
ssh gsp@188.245.254.248 'cat /etc/caddy/Caddyfile'
```

and correct `infra/Caddyfile` (the `root *` line) and the "Sync website"
step in `deploy.yml` to match whatever that actually shows, if it differs
from `/home/og/projects/gsp-recruitment/website`.

### Manual rollback

Backend/worker image, if a bad deploy somehow got marked healthy:

```
ssh gsp@188.245.254.248 '
  docker tag gsp-recruitment-backend:previous gsp-recruitment-backend:latest &&
  cd /home/gsp/projects/gsp-recruitment &&
  docker compose up -d backend worker
'
```

Caddyfile, if a bad config made it live and auto-restore did not run (e.g.
you edited it by hand):

```
ssh gsp@188.245.254.248 '
  ls -t /etc/caddy/Caddyfile.bak.* | head -1
  # then, using that filename:
  sudo cp /etc/caddy/Caddyfile.bak.<timestamp> /etc/caddy/Caddyfile &&
  sudo systemctl reload caddy
'
```

Website files: re-run the "Sync website" rsync step from a known-good
commit (`git checkout <sha> -- website && rsync -avz --delete website/
gsp@188.245.254.248:<served-path>/`), or re-run the whole workflow from
the previous successful commit via Actions → Re-run jobs.

## `.github/workflows/backup.yml`

Nightly at 03:15 UTC (`workflow_dispatch` also available, with a
`restore_test` checkbox). Dumps `recruitment_db` (`pg_dump -Fc`) and
Postgres globals (`pg_dumpall --globals-only`) from the VPS over SSH,
encrypts both locally on the runner with `openssl enc -aes-256-cbc
-pbkdf2 -pass env:BACKUP_PASSPHRASE`, and uploads to R2:

- `backups/pg/YYYY-MM-DD.dump.enc`
- `backups/globals/YYYY-MM-DD.sql.enc`
- `backups/env/YYYY-MM-DD.env.enc` (`talent-os/.env` from the VPS)

`backups/pg/` objects older than 30 days are deleted after each successful
upload. On the 1st of the month (or on-demand with `restore_test: true`),
a second job downloads the latest dump, decrypts it, restores it into a
throwaway `postgres:16-alpine` container, and checks `SELECT COUNT(*) FROM
candidates` / `FROM users` are non-zero. Telegram gets a message on any
job failure; the restore-test job also sends a short success line (the
nightly dump/upload/prune job stays silent on success).

Nothing in this workflow is run against the VPS from this sandbox session
— it has not been tested end-to-end. Run it once by hand via Actions →
"Offsite Backups" → Run workflow before trusting the cron schedule.

The workflow sets `AWS_REQUEST_CHECKSUM_CALCULATION: WHEN_REQUIRED` for
every `aws s3`/`s3api` call — recent aws-cli v2 defaults to always sending
a checksum header that R2 (S3-compatible, not S3-identical) has been
known to reject; this restores the older, R2-safe default.

### Secrets to create (owner, one time)

Already exist (reused from other workflows): `VPS_SSH_PRIVATE_KEY`,
`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`.

New, must be created under Settings → Secrets and variables → Actions:

- **`BACKUP_PASSPHRASE`** — a long, random passphrase (treat it like a
  root key). Generate one with e.g. `openssl rand -base64 48`, store it in
  a password manager immediately. **There is no recovery if this is
  lost** — every encrypted backup becomes permanently unreadable. It is
  used only inside the GitHub Actions runner's environment (`openssl enc
  -pass env:...`); it is never written to the VPS or echoed in any log.

If a required secret is missing, the workflow fails fast on its first
step with an `::error::` naming exactly which one, before touching the
VPS.

### Manual restore (disaster recovery)

```
# 1. Download + decrypt the backup you want (replace YYYY-MM-DD):
aws --endpoint-url https://4ca99d2b194e26fee99a8916bb53942b.r2.cloudflarestorage.com \
  s3 cp s3://gsp/backups/pg/YYYY-MM-DD.dump.enc ./db.dump.enc
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass pass:'<BACKUP_PASSPHRASE>' \
  -in db.dump.enc -out db.dump

# 2. Restore into a running postgres (adjust host/user/db as needed):
pg_restore -h 127.0.0.1 -U talentos_admin -d recruitment_db --clean --if-exists db.dump

# 3. Globals (roles/grants), if needed, from backups/globals/YYYY-MM-DD.sql.enc:
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass pass:'<BACKUP_PASSPHRASE>' \
  -in globals.sql.enc -out globals.sql
psql -h 127.0.0.1 -U talentos_admin -f globals.sql
```

Run this on a host you trust with the passphrase in hand — never paste
`BACKUP_PASSPHRASE` into a shared shell history; prefer `read -s
BACKUP_PASSPHRASE` and `-pass env:BACKUP_PASSPHRASE` over `-pass pass:...`
on argv where anything else on the box can read `/proc/*/cmdline`.

## Hardening backlog (niet-blokkerend)

- De sudoers-regel `/usr/bin/rm -- /etc/caddy/Caddyfile.bak.*` matcht in
  sudoers-semantiek over argumentgrenzen heen en is daarmee breder dan één
  bestand. De workflow roept hem netjes aan (`xargs -n1`), maar de nette
  oplossing is een root-owned helperscript (bv.
  `/usr/local/sbin/prune-caddy-baks` dat zelf `ls -t | tail -n +11 |
  xargs rm` doet) met één argumentloze NOPASSWD-regel. Oppakken bij de
  productie-hardening samen met de geplande secret-rotatie.
