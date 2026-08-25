# GSP Recruitment — monorepo

Faceless recruitment agency (Brainport/Eindhoven, NL) placing embedded software / C++ / mechatronics / OT-cybersecurity engineers. This repo is the whole business: API, website, admin panel, mobile app, infra, and strategy docs.

## Map
- `talent-os/backend` — FastAPI + PostgreSQL API (production: api.gsprecruitment.nl). Routers per domain, SQL migrations in `migrations/`.
- `website/` — public site + blog + candidate/client portals; `website/admin/` is the Tabler 1.4 admin panel (dark navy/gold).
- `app/` — Expo SDK 57 / React Native candidate app (see `app/CLAUDE.md`).
- `talent-os/docker-compose.yml`, `nginx.conf`, `scripts/deploy.sh` — infra.
- `SITE-DESIGN-SPEC.md`, `ENTERPRISE-ARCHITECTURE-SPEC.md`, `GSP-PROFITABILITY-PLAN-2026.md` — living specs.

## API facts that bite
- Every request to *.gsprecruitment.nl needs `User-Agent: gsp-ops` (WAF 403s bare curl).
- Auth: `/api/candidates*`, `/api/jobs`, `/api/matches*` → `X-API-Key` header; `/api/v1/admin/*` → Bearer JWT from `POST /api/auth/login`. Public: `/api/public/jobs`, `/api/v1/public/blog` (note the v1 — there is no `/api/public/blog`).
- jsonb columns need `json.dumps`; NULL array columns must be coerced to `[]` on read.
- Outreach is DRAFT-ONLY (a human sends); blog publish is an explicit second endpoint call.

## House rules
- Faceless brand: never a founder name, "wij" not "ik", Dutch-first + English.
- Register: NRC/FD — plain, direct, zero hype, no AI-tell phrases, no invented statistics.
- Free/organic growth only; GDPR: public data only, provenance URL per person, opt-out lines in outreach.
- Secrets stay in env vars — never commit or print them.

## The agent team (`.claude/agents/`)
Delegate work to the specialist, don't do it inline: `backend-dev`, `frontend-dev`, `mobile-dev`, `devops-engineer`, `qa-engineer`, `security-auditor`, `code-reviewer`, `ui-designer`, `design-reviewer`, `growth-marketer`. Typical flow for a feature: ui-designer (if visual) → the right dev agent → qa-engineer → code-reviewer; security-auditor before releases touching auth or personal data.

Scheduled business ops run as Claude Routines (not in this repo): gsp-morning-brief, gsp-draft-qa, gsp-match-and-draft, gsp-client-leads, gsp-candidate-scout, gsp-blog-weekly, gsp-weekly-review — all report to Telegram.
