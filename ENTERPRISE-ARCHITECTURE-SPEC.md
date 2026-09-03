# GSP Recruitment: Enterprise Architecture Specification

> **Status:** As-built (WS-F.9, frozen to what runs on `main`)
> **Scope:** Infrastructure, backend, database, frontend delivery and data protection for gsprecruitment.nl / api.gsprecruitment.nl

---

## Table of Contents

1. [Overview](#1-overview)
2. [Infrastructure](#2-infrastructure)
3. [Backend (FastAPI)](#3-backend-fastapi)
4. [Database](#4-database-postgresql-16)
5. [Frontend delivery](#5-frontend-delivery)
6. [Mobile app](#6-mobile-app)
7. [Security posture](#7-security-posture)
8. [GDPR & data protection](#8-gdpr--data-protection)
9. [Decision log](#9-decision-log)
10. [Appendix A: Niet vóór 3 factureerbare zetels](#appendix-a--niet-vóór-3-factureerbare-zetels)

This document describes the stack as it runs today. Work that goes beyond it lives in Appendix A, not in the body: nothing in sections 1–9 below is a proposal.

---

## 1. Overview

GSP Recruitment is a faceless recruitment agency (Brainport/Eindhoven, NL) placing embedded software / C++ / mechatronics / OT-cybersecurity engineers and the testing roles around those four disciplines. The whole business runs on:

| Layer | What it is |
|---|---|
| API | FastAPI + asyncpg, single process group, one PostgreSQL 16 instance |
| Public site + portals | Static HTML/CSS/JS, no client framework, served by Cloudflare Workers Static Assets |
| Admin panel | Vendored Tabler 1.4, dark navy/gold reskin, same static hosting as the site |
| Mobile app | Expo SDK 57 / React Native (candidate app; see `app/CLAUDE.md`) |
| Host | One Hetzner VPS running Docker Compose (postgres + backend) |
| CDN/DNS/WAF | Cloudflare (also hosts the static site) |
| Object storage | Cloudflare R2 (candidate CVs) |
| CI/CD | GitHub Actions: `ci.yml` (tests, contract check, OpenAPI snapshot), `deploy.yml` (rsync + SSH deploy to the VPS on push to `main`) |

There is no background task queue, no server-side rendering framework, and no second application server. One backend process serves every router; one Postgres instance holds every table.

---

## 2. Infrastructure

### 2.1 What's actually deployed

The **root `docker-compose.yml`** is the file GitHub Actions rsyncs to the VPS and the file that runs in production. It defines exactly two services:

- `postgres` (`postgres:16-alpine`), bound to `127.0.0.1:5432`, credentials from `talent-os/.env` + `talent-os/postgres.env` (both gitignored, `postgres.env` layered on top so DB credentials can be rotated/audited independently of the rest of `.env`)
- `backend` (built from `talent-os/backend` via `talent-os/Dockerfile`), bound to `127.0.0.1:8000`

Both carry JSON-file log rotation (5 × 20 MB) and a memory limit (`postgres` 4G, `backend` 2G). There is no reverse-proxy, task-queue, or cache service in this file: nothing beyond postgres and the API process runs in production.

**`talent-os/docker-compose.yml`, `talent-os/nginx.conf`** describe a fuller reference stack (postgres, backend, a reverse proxy, and the task-queue/cache pair named in Appendix A) that predates the current setup. It is kept in the repo for reference but **is not deployed**: no host runs it, no workflow syncs it. Do not treat its presence as evidence that those extra services exist in production; the root `docker-compose.yml` above is the source of truth for what's live. Reconciling or removing the unused reference file is a housekeeping item, not a spec change.

TLS termination and the public-facing reverse proxy in front of `127.0.0.1:8000` for `api.gsprecruitment.nl` are configured directly on the VPS host, outside this repo (no Caddyfile or nginx config for it is checked in). An operator changing that layer works on the VPS itself, not from a file in this repository.

### 2.2 Deploy pipeline (`.github/workflows/deploy.yml`)

On every push to `main`, after `ci.yml`'s test job passes:

1. `rsync` syncs `talent-os/` (excluding `.env`, `__pycache__`, `*.pyc`) and the root `docker-compose.yml` to the VPS over SSH (key: repo secret `VPS_SSH_PRIVATE_KEY`; host/user/path: repo variables `VPS_HOST`/`VPS_USER`/`VPS_PATH`, falling back to the current production values if unset).
2. `postgres.env` is generated from `.env` on the VPS if it doesn't already exist (idempotent, never overwrites, never prints a secret).
3. The current `backend` image is tagged `:previous` for rollback, then `docker compose up -d --build backend` rebuilds and restarts it.
4. Every file in `migrations/0*.py` (000 first, then in filename order) runs via `docker compose run --rm --no-deps backend`, i.e. a fresh one-off container from the just-built image: not `exec` against the restarted service, so a broken image fails the deploy here instead of silently skipping migrations. Each migration is self-tracking (`schema_migrations`, see §4.2) and a no-op if already applied.
5. A health check hits `GET /health` on the VPS (`127.0.0.1:8000`, no WAF in the way at that hop).
6. On success, the image is also tagged with the deploy's git SHA and old SHA-tagged images beyond the 5 most recent are pruned.
7. On failure, the backend is rolled back to the `:previous` image tag and restarted automatically.

Concurrency is serialized (`group: deploy-production, cancel-in-progress: false`) so two merges in quick succession queue instead of racing on the VPS.

The site ("frontend") is not part of this SSH deploy: Cloudflare auto-deploys `website/` from the repo per `wrangler.jsonc` (§5). `deploy.yml`'s "Sync website" step is a no-op comment left in place as a marker of that split, not a real deploy step.

`scripts/deploy.sh` is the same rsync-and-SSH sequence runnable by hand from an operator machine that already has `VPS_SSH_PRIVATE_KEY`'s private half at a local path; it is a manual fallback for the same pipeline, not a second, different deploy path. `start.sh` / `stop.sh` / `update.sh` are VPS-local convenience wrappers around `docker compose up -d` / `down` / `pull && up -d --build`.

### 2.3 Object storage: R2

CVs are stored in a Cloudflare R2 bucket (`gsp`), configured via `R2_ENDPOINT`/`R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY`/`R2_BUCKET` env vars written onto the VPS by the one-off, re-runnable `r2-setup.yml` workflow. `talent-os/scripts/migrate_cv_to_r2.py` moved surviving local CV files into the bucket (dry-run by default). CV files are not stored on the backend container's local disk in normal operation.

---

## 3. Backend (FastAPI)

`talent-os/backend/main.py` builds one FastAPI app and mounts these routers (all under `/api` unless noted):

`health`, `auth`, `mfa`, `candidates`, `jobs` (+ `public_jobs_router`), `matches`, `apollo`, `webhook`, `candidate` (candidate portal), `client` (client portal), `admin` (admin portal), `public`, `gdpr` (+ `admin_router`, `suppression_router`), `outreach`, `blog_admin`, `retention_admin` (+ `apollo_pool_router`), `mobile`, `prospects`.

Runs as `settings.backend_workers` (4) separate uvicorn worker processes: relevant to §3.2 below, since in-memory state is per-process, not shared.

### 3.1 Auth model

Two schemes, matching the existing house rule (`X-API-Key` for machine endpoints, Bearer JWT for the admin surface), extended with real user auth:

| Surface | Auth |
|---|---|
| `/api/candidates*`, `/api/jobs`, `/api/matches*` | `X-API-Key` header |
| `/api/v1/admin/*` | Bearer JWT, obtained from `POST /api/auth/login` |
| `/api/public/jobs`, `/api/v1/public/blog` | none (public) |
| Candidate / client portals | Bearer JWT issued at registration or login |

Auth router (`routers/auth.py`) covers: register, login, JWT refresh, email verification (tokens: `secrets.token_urlsafe`, only their SHA-256 hash stored, 24h TTL), password reset/forgot, change/set password, profile read/update, and Google sign-in (`/api/auth/google/login` + `/api/auth/google/callback`, reusing the same Google Cloud OAuth client already configured for transactional email). There is no LinkedIn OAuth backend flow: the LinkedIn button present in the registration UI is not wired to a token exchange.

Every auth-adjacent route is rate-limited through a single shared `slowapi` `Limiter` (`core/ratelimit.py`): one instance imported everywhere, so a client can't dodge the cap by mixing endpoints. That limiter's storage is in-memory per worker process (no shared external backend), so a nominal "10/minute" limit is enforced as up to "10 × 4 workers per minute" in the worst case today; this is a known, documented ceiling, not a bug to silently work around.

Failed logins are tracked and lock the account after repeated failures (`migrations/020_login_lockout.py`).

### 3.2 Admin MFA (WS-E.12)

`routers/mfa.py` adds TOTP-based multi-factor auth **for the `admin` role only** (`migrations/021_admin_mfa.py`): setup (provisions a secret + QR payload), enable, disable, status, verify (second factor at login), and single-use recovery codes. Every enable/disable/recovery action is written to the audit log. This is built and live today: it is not a future item and does not belong in Appendix A.

A separate origin for the admin panel (WS-E.13) is planned but not yet built; the admin panel is currently served from the same static site as the public pages, gated by the JWT + MFA login flow above, not by network separation. Like MFA, this is a near-term, scoped item and is not filed under Appendix A.

---

## 4. Database (PostgreSQL 16)

One instance, one schema, `asyncpg` connection pool (min 2 / max 10).

### 4.1 Core tables

`users`, `clients`, `job_orders`, `candidates`, `matches`, `outreach_campaigns`, `outreach_messages`, `hiring_signals`, `salary_benchmarks`, `skill_gaps`, `referral_graph`, `data_subject_requests`, `model_feedback`, `client_prospects`, plus the portal/blog/audit tables added along the way (see §4.2).

### 4.2 Migrations

`talent-os/backend/migrations/` holds `000_baseline.py` through `022_apollo_pool_flag.py`, run via `_runner.py`'s pattern: every migration records itself in `schema_migrations` and is a no-op on re-run, so the full sequence executes unconditionally on every deploy (§2.2 step 4): there is no separate "pending migrations" check to get out of sync with.

| Range | What it added |
|---|---|
| 000 | Baseline schema |
| 001–002 | Users, portal tables |
| 003 | `schema_migrations` self-tracking |
| 004–006 | Token expiry fix, performance indexes, redundant-index cleanup |
| 007–009 | CV file path, outreach subject, salary benchmark seed data |
| 010–012 | Outreach drafts, blog posts, mobile/growth tables |
| 013–016 | Email null-distinctness, prospect/company index, salary benchmark natural key, job order columns |
| 017 | Email verification |
| 018 | GDPR provenance + opt-out columns |
| 019 | Production schema alignment |
| 020 | Login lockout |
| 021 | Admin MFA |
| 022 | Apollo pool flag |

CI (`ci.yml`) regenerates `openapi.snapshot.json` from the live FastAPI app on every push and fails if it drifts from the committed copy, and runs `scripts/check_api_contract.py` (static regex check of frontend calls against backend routes): both catch a router/schema change without a matching doc update before it reaches `main`.

---

## 5. Frontend delivery

`wrangler.jsonc` configures Cloudflare **Workers Static Assets** (not Cloudflare Pages, not a framework build) to serve the `website/` directory as-is:

```jsonc
{
  "name": "gsprecruitment",
  "assets": { "directory": "website" }
}
```

No bundler, no SSR/SSG, no client framework: every page is hand-authored HTML/CSS/JS. `website/_headers` sets security headers (HSTS, `X-Content-Type-Options`, `X-Frame-Options`, `Permissions-Policy`, and an enforced Content-Security-Policy) for every path, per the [Workers Static Assets `_headers` convention](https://developers.cloudflare.com/workers/static-assets/headers/). The CSP is enforced (not report-only) as of the M1 inline-script/attribute cleanup; a matching `Content-Security-Policy-Report-Only` header is kept one release longer as a safety net.

The public site, candidate portal, client portal and admin panel are four separate static surfaces under `website/`, each with its own hash-routed single-page navigation (`window.location.hash`, no client-side router library): see `SITE-DESIGN-SPEC.md` for the page-by-page breakdown.

---

## 6. Mobile app

`app/` is an Expo SDK 57 / React Native candidate app; see `app/CLAUDE.md` for its own architecture notes. It talks to the same FastAPI backend via the `mobile` router.

---

## 7. Security posture

- **Secrets**: API key, JWT secret, DB credentials, SMTP, R2, Google OAuth, webhook secret: all environment variables (`talent-os/.env`, `talent-os/postgres.env`, both gitignored), never committed, never logged.
- **WAF**: production rejects requests without a real `User-Agent` in front of `api.gsprecruitment.nl`: probes and scripts must send one (`curl -H "User-Agent: gsp-ops" ...`).
- **Rate limiting**: shared `slowapi` limiter (§3.1) on auth-adjacent routes.
- **Login lockout**: account lock after repeated failed logins (§3.1).
- **Admin MFA**: TOTP + recovery codes, admin role only (§3.2).
- **Webhook verification**: HMAC-SHA256 signature check on inbound webhooks.
- **CSP**: enforced, `script-src`/`style-src` restricted to `'self'` plus a short CDN allowlist; no inline script anywhere in `website/**/*.html`.
- **Transport**: HSTS with `includeSubDomains` on the static site; Postgres and the backend port are bound to `127.0.0.1` on the VPS, not exposed publicly except through whatever reverse proxy/TLS termination the host runs (§2.1).

---

## 8. GDPR & data protection

Full detail lives in `docs/VERWERKINGSREGISTER.md` (processing register, LIA, DPIA-light) and `docs/SOURCING-SOP.md`; this section is the pointer, not a duplicate.

- **Processing register (art. 30 AVG)**: `docs/VERWERKINGSREGISTER.md` §1: activities, legal basis, recipients, retention, security measures.
- **Data subject rights**: `routers/gdpr.py`: `GET /api/gdpr/export` (self-service export), `POST /api/gdpr/withdraw-consent`, `DELETE /api/gdpr/account` (self-service erasure), `POST` on `admin_router` for an admin-initiated erasure of a person across every table (`erase_person`), all logged to `data_subject_requests`.
- **Suppression list**: `suppression_router` (`POST`/`GET`): an opt-out/do-not-contact list separate from deletion, so a "STOP" reply keeps someone off future outreach even after their active record is gone.
- **Retention table**: single source of truth is `talent-os/backend/core/retention.py`; `docs/VERWERKINGSREGISTER.md` §1.4 and `docs/SOURCING-SOP.md` are generated copies of the same table, checked against the code by `tests/test_retention.py`. A daily purge job (`services/scheduler.py::run_retention_purge()`, apscheduler, 04:00 Europe/Amsterdam) applies it, using the same `erase_person` logic as a manual request. The purge job exists but defaults to **off** (`RETENTION_PURGE_ENABLED=false`); a real run can also be triggered by hand via `POST /api/v1/admin/retention/run` (a non-dry-run requires `confirm:"PURGE"`).
- **Sourced-data safeguards**: Art. 14 notice text, source-URL provenance requirement, and the 3-month no-response retention window for sourced prospects are enforced in the outreach draft flow (`docs/SOURCING-SOP.md`, `docs/VERWERKINGSREGISTER.md` §2–4): outreach stays draft-only, a human sends.

---

## 9. Decision log

| # | Decision | Why | Status |
|---|---|---|---|
| 1 | Static site, no frontend framework | Four hand-authored surfaces (site/candidate/client/admin), no build step, ships on Cloudflare Workers Static Assets with zero server cost | As-built |
| 2 | JWT auth for portals, `X-API-Key` kept for machine endpoints | Matches existing API-key contract for integrations while adding real user sessions | As-built |
| 3 | No task queue or cache service | Nothing today needs async background processing; the fuller reference compose file (Appendix A names the services it adds) was never brought up in production | As-built |
| 4 | Single VPS, Docker Compose, no orchestrator | Two services (postgres, backend), rsync+SSH deploy is simple and reversible | As-built |
| 5 | Migrations self-track and re-run unconditionally on every deploy | No separate "pending migrations" state to drift from what's actually applied | As-built |
| 6 | R2 for CV storage, not local disk | Survives container/VPS rebuilds; no local-disk backup gap | As-built |
| 7 | Admin MFA (TOTP), admin role only | Highest-privilege accounts get a second factor first (WS-E.12) | As-built |
| 8 | Separate admin origin | Reduces blast radius of a static-site compromise on the admin surface | Planned (WS-E.13), not yet built |
| 9 | Outreach is draft-only | A human sends every message; nothing auto-sends | As-built |

---

## Appendix A: Niet vóór 3 factureerbare zetels

The items below go beyond what's described in sections 1–9. None of them run in production, and none are scheduled. They stay here as a record of ideas that were drafted before the stack above was frozen to as-built, not as a commitment or a roadmap with dates. Building any of them is a decision the owner makes once revenue supports it: not before 3 billable seats (contractors placed and invoiced).

- **Next.js** (or any SSR/SSG framework) for the public site or portals, replacing the current static HTML/CSS/JS
- **Celery + Redis** for background/async work (AI matching runs, CV parsing, salary data refresh, Apollo sync)
- **PWA / service worker / offline support** for the site or portals
- **Page builder / CMS** for non-blog page content, testimonials, or case studies
- **`superadmin` role** and separate infra/billing/audit-config surface beyond the current `admin` role
- **Market Value Compass**: an interactive, authenticated salary-benchmarking tool with chart visualisation and PDF export, distinct from the static salary table that exists today
- **Retained search** as a service line/workflow
- **ML-based match scoring** (as opposed to the existing rule/keyword matching)
- **Multilingual CMS** beyond the current hand-maintained EN/NL toggle on static pages
- LinkedIn OAuth login (a LinkedIn button exists in the registration UI today with no backend flow behind it: wiring it up, or removing the button, is an open item but not itself part of this list's scope)
- Client-portal analytics/reporting, team/sub-user management, and billing self-service
- A dedicated candidate/client mobile experience beyond the current Expo app's scope

---

*End of specification.*
