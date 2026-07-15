# GSP Recruitment Mobile App — Execution Build Plan v2.1

**Date:** 2026-07-15 (v2.1) — original v2.0: 2026-07-08
**Status:** AUTHORITATIVE — supersedes the technical sections of `GSP_Mobile_App_MASTERPLAN.md` and `~/GSP_App_Architecture_Plan.md` wherever they conflict with this document.
**Audience:** An AI coding agent (or developer) executing this plan step by step.

## v2.1 changes (2026-07-15)

1. **GO/NO-GO gate added:** do NOT start M1+ until **2 placements have closed**. The app multiplies a working funnel; it cannot create one. Until then the only permitted app work is M0 backend additions (they benefit the website too). See `GSP-PROFITABILITY-PLAN-2026.md`.
2. **Backend gap #3 is DONE** (2026-07-15): GDPR self-service deletion now exists as `DELETE /api/v1/gdpr/account`, plus `GET /api/v1/gdpr/export` and `POST /api/v1/gdpr/withdraw-consent`. The app's settings screen must call these — do not build `/api/v1/candidate/account`.
3. **Matching is now reachable over HTTP:** `POST /api/matches/run?job_id=<id>` (X-API-Key, backgrounds the embedding match). The app never calls this directly (it's operator-side), but "Mijn matches" data now actually populates.
4. **Candidate identity bug fixed:** self-registered users now get a `candidates` row automatically, so matches/applications/saved-jobs return real data. Migration `007_cv_file_path.py` must be applied before CV upload works.
5. **Faceless brand rule:** the app contains NO founder name, photo, or bio anywhere — including the App Store listing, "about" screen, and push notification sender name. Sender/author is always "GSP Recruitment". This mirrors the website (anonymized 2026-07-15).
6. **Financial baseline corrected:** business-case references use €354/mo operating costs, €18k average commission, 55% partner split (per finance review) — not the older €179/€16.5k figures.
7. **Guarantee copy standardized:** "no cure, no pay + 30 dagen vervangingsgarantie" — the app must use the same wording as the website if it ever shows employer-facing copy.

---

## 0. HOW TO USE THIS DOCUMENT (read first, builder)

You are building a React Native (Expo) mobile app for GSP Recruitment on top of an **existing, working FastAPI backend**. This plan is ordered into milestones **M0–M11**. Execute them **in order**. Do not skip ahead, do not reorder, do not add features not listed here.

### Hard rules (guardrails)

1. **NEVER invent API endpoints.** Every endpoint you call must exist in `talent-os/backend/routers/`. Before wiring any screen, verify the endpoint's exact path, method, request and response schema by reading the router file, or better: start the backend locally and fetch `http://127.0.0.1:8000/openapi.json` and generate/verify types from that.
2. **Do not refactor the backend.** Only the additive changes in Milestone M0 are permitted. Do not rename existing routes, do not change existing schemas, do not touch `core/security.py` logic.
3. **Do not modify the website** (`website/`) except where M0 explicitly says so.
4. **Verify every milestone** with its Acceptance Checklist before moving to the next. If a check fails, fix it before continuing.
5. **Brand colors are NAVY + GOLD** (see §3). The masterplan says cyan `#00B4D8` / orange `#FF6B35` — that is **wrong**, ignore it. The single source of truth is `website/theme.css`.
6. **All user-facing strings are Dutch** (see string table in §4.7). Code, comments, commit messages: English.
7. Commit after every milestone with message `feat(app): M<n> — <milestone name>`.
8. If the backend is unreachable or a schema surprises you, **stop and report** — do not stub around it silently.

### Existing system map (verified 2026-07-08)

| Piece | Location | Stack | Status |
|---|---|---|---|
| Website (static) | `website/` | HTML/CSS/JS, served via Cloudflare Workers static assets (`wrangler.jsonc`) | Live at gsp-recruitment.nl |
| Web portals | `website/candidate/`, `website/client/`, `website/admin/` | Static JS SPAs against the API | Live |
| Backend API | `talent-os/backend/` | FastAPI + PostgreSQL 16 | Deployed on Hetzner VPS via `docker-compose.yml` (postgres + backend only, behind Caddy, bound to 127.0.0.1) |
| Auth | `routers/auth.py` → `/api/auth/*` | JWT bearer (access + refresh), Google OAuth | Working |
| Candidate portal API | `routers/candidate.py` → `/api/v1/candidate/*` | JWT-protected | Working — **this is the app's main API surface** |
| Matching | `services/matcher.py` | Skill-fit scoring | Works synchronously; Celery variant NOT deployed |
| DB schema | `talent-os/scripts/init_db.sql` + `talent-os/backend/migrations/` | candidates, job_orders, matches, clients, salary_benchmarks, data_subject_requests, … | Working |

### Endpoints the app will use (ALL ALREADY EXIST — reuse, don't rebuild)

| App feature | Method + path |
|---|---|
| Register | `POST /api/auth/register` |
| Login | `POST /api/auth/login` |
| Refresh token | `POST /api/auth/refresh` |
| Forgot / reset password | `POST /api/auth/forgot-password`, `POST /api/auth/reset-password` |
| Current user | `GET /api/auth/me`, `PATCH /api/auth/me` |
| Google sign-in | `GET /api/auth/google/login` → `/api/auth/google/callback` |
| Public job list (pre-login browse) | `GET /api/public/jobs` |
| Job detail | `GET /api/public/jobs/{id}` (verify in `routers/jobs.py`; the public router starts at line 76) |
| My profile | `GET /api/v1/candidate/profile`, `PUT /api/v1/candidate/profile` |
| CV upload | `POST /api/v1/candidate/cv` (multipart) |
| My matches | `GET /api/v1/candidate/matches` |
| My applications | `GET /api/v1/candidate/applications` |
| **1-click apply** | `POST /api/v1/candidate/applications` |
| Saved jobs | `GET/POST /api/v1/candidate/saved-jobs`, `DELETE /api/v1/candidate/saved-jobs/{job_id}` |
| Messages (read) | `GET /api/v1/candidate/messages` |
| Salary benchmarks | `GET /api/v1/candidate/salary-benchmark` (public variant: `GET /api/v1/public/salary-data`) |
| Dashboard summary | `GET /api/v1/candidate/dashboard` |

**Passive mode:** the `candidates` table already has `is_passive` and `availability` fields — the toggle is a profile `PUT`, not a new endpoint.

### The ONLY backend gaps (built in M0)

1. Push notification device-token registration + a send helper (nothing push-related exists today).
2. `POST /api/v1/candidate/messages` — messaging is currently read-only for candidates.
3. ~~`DELETE /api/v1/candidate/account` — GDPR self-service deletion~~ **DONE (v2.1):** use the existing `DELETE /api/v1/gdpr/account` (plus `GET /api/v1/gdpr/export`, `POST /api/v1/gdpr/withdraw-consent`) in `routers/gdpr.py`. Do not build a duplicate.

---

## 1. Corrections to the previous plans (what changed and why)

| Old plan said | This plan says | Why |
|---|---|---|
| Backend: Firebase (Auth, Firestore) | **Reuse existing FastAPI + Postgres.** No Firebase at all. | Backend already has auth, jobs, matching, portals. Firebase would mean duplicate auth and data sync hell. Saves €0–25/mo and weeks of work. |
| Build 16 new `/api/app/*` endpoints | Build **3** endpoints (push token, send message, delete account) | The other 13 already exist under `/api/auth` and `/api/v1/candidate`. Verified against the code on 2026-07-08. |
| 26 screens, 11 Zustand stores, SQLite chat, cert pinning, jailbreak detection in MVP | **12 screens, 2 stores** (auth + settings), React Query for all server state, chat = simple polling thread, security hardening deferred to Phase 2 | A solo founder needs shipping speed. Every cut item is additive later. |
| Colors: Navy + Cyan #00B4D8 + Orange #FF6B35 | **Navy scale + Gold #FAC800** per `website/theme.css` | That's the actual live brand. App must match the site. |
| €5.000–8.000 freelance developer, 4 weeks | AI-assisted build, ~1–2 weeks calendar time, ~€0 dev cost + €99 Apple + €25 Google + ~€15/mo EAS | This document exists so the build needs no freelancer. |
| Match Quiz + Salary Calculator in MVP | Salary insights screen stays (endpoint exists, cheap win). Match Quiz **cut to Phase 2**. | Quiz needs new backend logic; salary data is already served. |
| Client portal in-app (MVP/F2) | **Cut from the app entirely for now.** Hiring managers use the existing web portal at gsp-recruitment.nl/client. | Tiny audience (~10 people), web portal already exists, doubles app scope for no download growth. |

The product/marketing/GTM/KPI sections of `GSP_Recruitment_App_Plan.md` remain valid and are not repeated here.

---

## 2. MVP scope — exactly 12 screens

```
(auth)                          (tabs)
├── welcome (onboarding, 3     ├── jobs/index        — Vacature feed (list + filter chips)
│   swipe panels + skills)     ├── jobs/[id]         — Vacature detail + Solliciteer button
├── login                      ├── matches/index     — Mijn matches (score ring) + applications
├── register                   ├── insights/index    — Salaris-inzichten (benchmarks, simple)
└── forgot-password            └── profile/index     — Profiel
                               modals/pushed:
                               ├── profile/edit      — Profiel bewerken + CV upload + passive toggle
                               ├── applications/[id] — Sollicitatie status detail
                               └── settings          — Instellingen, notificaties, privacy, delete account
```

**Explicitly OUT of MVP** (do not build, even partially): chat UI beyond a read-only messages list, match quiz, employer branding pages, referral program, interview prep, client portal, admin screens, biometric unlock, certificate pinning, offline mutation queue, LinkedIn import, calendar integration, dark/light toggle (app ships **dark-only** — matches the premium navy brand and halves the styling work).

---

## 3. Design system (single source of truth)

Derive all tokens from `website/theme.css`. Core values:

```ts
// src/theme/tokens.ts
export const colors = {
  navy950: '#030812', navy900: '#060D1A', navy800: '#0A1628',
  navy700: '#0F1D35', navy600: '#152B4A', navy500: '#1E3A5E',
  navy400: '#2A4A75', navy300: '#4A6F9F', navy200: '#7FA0C9', navy100: '#C5D6EB',
  gold500: '#FAC800', gold400: '#FBD74A', gold600: '#D4A800',
  white: '#FFFFFF', offWhite: '#F1F5F9',
  success: '#22C55E', danger: '#EF4444', warning: '#F59E0B',
};
// Background: navy950. Cards: navy800 with 1px navy600 border, radius 12.
// Primary CTA: gold500 bg, navy900 text, radius 12, height 52.
// Body text: offWhite. Secondary text: navy200. Font: Inter (expo-google-fonts), scores/salary: JetBrains Mono.
export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32, xxl: 48 };
export const radius = { sm: 8, md: 12, lg: 16, full: 9999 };
```

Reusable components to build once in M2 and reuse everywhere: `Button` (primary gold / secondary outline / ghost), `Card`, `Chip` (skill tags, selectable), `MatchRing` (SVG circular progress showing %, gold arc), `EmptyState` (icon + Dutch copy + optional CTA), `Screen` (SafeArea + padded ScrollView wrapper), `Field` (label + TextInput + error), `Badge` (status colors), `Skeleton` (loading shimmer). Touch targets ≥ 48pt. All interactive elements get `accessibilityLabel`.

---

## 4. Milestones

### M0 — Backend additions (do this FIRST, in `talent-os/backend/`)

**M0.1 — Migration `007_device_tokens.py`** (follow the exact pattern of `migrations/005_performance_indexes.py` and register it the same way the others are registered in `_runner.py`):

```sql
CREATE TABLE IF NOT EXISTS device_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,            -- FK to the users table (check exact name in migrations/001_users.py)
    token TEXT NOT NULL UNIQUE,          -- Expo push token: ExponentPushToken[...]
    platform VARCHAR(10) NOT NULL CHECK (platform IN ('ios','android')),
    created_at TIMESTAMPTZ DEFAULT now(),
    last_seen_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_device_tokens_user ON device_tokens(user_id);
```

**M0.2 — Router additions in `routers/candidate.py`** (same auth dependency `get_current_user` as the existing routes):

- `POST /api/v1/candidate/device-token` — body `{token: str, platform: 'ios'|'android'}`. Upsert on token (update user_id + last_seen_at if exists). 201.
- `DELETE /api/v1/candidate/device-token` — body `{token: str}`. Removes it (called on logout). 204.
- `POST /api/v1/candidate/messages` — body `{body: str}` (max 2000 chars). Inserts into the same table `GET /messages` reads (read `routers/candidate.py:370` to find the table/columns and mirror them; sender = candidate). 201, returns the created message in the same shape GET returns.
- `DELETE /api/v1/candidate/account` — no body. Inserts a row into `data_subject_requests` (type `deletion`), anonymizes the candidate row (null out name/email/phone/cv fields, keep id for referential integrity), deletes the user's auth record and device tokens. 204. **Look at the `data_subject_requests` columns in `scripts/init_db.sql:245` first and match them.**

**M0.3 — Push service `services/push_service.py`:** a function `send_push(user_ids: list[int], title: str, body: str, data: dict)` that looks up tokens and POSTs to `https://exp.host/--/api/v2/push/send` (Expo push API, no FCM server key needed; batch max 100 per request; use `httpx` which is already a FastAPI dependency). Remove tokens that come back `DeviceNotRegistered`. **No PII in title/body** — e.g. "Nieuwe match gevonden 🎯", never a candidate or company name.

**M0.4 — Wire two triggers** (minimal, synchronous, wrapped in try/except so a push failure never breaks the request):
- When a new match row is created for a candidate (find where matches are inserted — check `services/matcher.py` and the admin/client routers) → push "Nieuwe match gevonden 🎯 / Bekijk je match-score in de app" with `data={"screen":"matches"}`.
- When an application's status is updated (admin router, `PUT /api/v1/admin/...` or wherever application status changes — grep for the applications table update) → push "Update over je sollicitatie / Open de app voor de status" with `data={"screen":"application","id":<id>}`.

**M0.5 — Tests:** extend the existing test pattern (`test_auth_primitives.py`) with tests for the 4 new endpoints (auth required → 401 without token; happy path with a token). Run the backend's existing test command (check for pytest in `requirements.txt`).

**Acceptance M0:** `docker compose up` locally → `curl http://127.0.0.1:8000/openapi.json | python3 -m json.tool | grep device-token` shows the new routes; pytest green; existing routes unchanged (diff shows only additions).

---

### M1 — App scaffold

Create the app at **`app/` inside the repo root** (`/home/og/projects/gsp-recruitment/app/`).

```bash
npx create-expo-app@latest app --template default   # Expo SDK latest, TypeScript, expo-router
cd app
npx expo install expo-secure-store expo-notifications expo-device expo-constants \
  expo-document-picker expo-linking expo-splash-screen expo-status-bar \
  @expo-google-fonts/inter @expo-google-fonts/jetbrains-mono expo-font \
  react-native-svg
npm i @tanstack/react-query axios zustand zod
npm i -D @types/react eslint prettier
```

Folder structure (expo-router):

```
app/
├── app/                      # routes
│   ├── _layout.tsx           # root: fonts, QueryClientProvider, auth gate, push handler
│   ├── (auth)/  login.tsx  register.tsx  forgot-password.tsx  welcome.tsx
│   ├── (tabs)/  _layout.tsx  jobs/index.tsx  jobs/[id].tsx
│   │            matches/index.tsx  insights/index.tsx  profile/index.tsx
│   ├── profile/edit.tsx      applications/[id].tsx      settings.tsx
├── src/
│   ├── api/ client.ts  auth.ts  jobs.ts  candidate.ts  types.ts
│   ├── stores/ authStore.ts  settingsStore.ts
│   ├── theme/ tokens.ts
│   ├── components/ (from §3)
│   ├── hooks/ usePushNotifications.ts
│   └── i18n/ nl.ts           # ALL user-facing strings live here
├── app.json  eas.json  .env.example
```

`app.json` essentials: name `GSP Recruitment`, slug `gsp-recruitment`, scheme `gsprecruitment`, iOS bundleId + Android package `nl.gsprecruitment.app`, dark UI style, splash + icon from `website/logo-icon.png` / `logo@2x.png` (resize to 1024×1024; keep navy background `#060D1A`).

API base URL: `https://gsp-recruitment.nl` in prod builds, overridable via `EXPO_PUBLIC_API_URL` for local dev (`http://<LAN-IP>:8000`). **Builder: confirm the production API is reachable at `https://gsp-recruitment.nl/api/health` — if the API lives on a different domain/subdomain, check the Caddy config on the VPS or ask the owner.**

**Acceptance M1:** `npx expo start` boots to a placeholder tab navigator with GSP navy background and Inter font loaded; TypeScript + ESLint pass.

---

### M2 — Design system components

Build every component in §3 with a small gallery route `app/dev/components.tsx` (dev-only) rendering all states. MatchRing: `react-native-svg` circle, stroke gold, animated with `Animated.timing` on mount.

**Acceptance M2:** gallery screen shows all components in all states; no console warnings.

---

### M3 — API client + auth

`src/api/client.ts` — the one tricky file; implement exactly this behavior:

```ts
// axios instance, baseURL from env.
// Request interceptor: attach `Authorization: Bearer <access>` from authStore.
// Response interceptor on 401: 
//   - single-flight refresh (module-level promise so concurrent 401s trigger ONE refresh)
//   - POST /api/auth/refresh with { refresh_token }  ← verify exact body/field names in routers/auth.py:136
//   - on success: store new tokens (SecureStore), retry original request once
//   - on refresh failure: authStore.logout() → router.replace('/(auth)/login')
```

Tokens in `expo-secure-store` (keys `gsp_access`, `gsp_refresh`). `authStore` (zustand): `{status: 'loading'|'authed'|'anon', user, login(), register(), logout(), bootstrap()}`. `bootstrap()` runs in root layout: read tokens → `GET /api/auth/me` → authed/anon. Root layout redirects: anon → `(auth)/welcome`, authed → `(tabs)/jobs`.

Screens: welcome (3 horizontally paged panels: value prop → skills multi-select chips (C, C++, Rust, Python, Embedded Linux, FreeRTOS, Zephyr, ARM/MCU, QNX, Yocto) → notification permission prompt), login, register (skills from welcome are submitted with profile after register), forgot-password. Google sign-in button: open `GET /api/auth/google/login` in a browser session via `expo-web-browser` + deep-link callback — **verify the callback redirect in `routers/auth.py:330` supports a mobile redirect URI; if it's web-only, ship email/password MVP and log Google as a Phase-2 TODO rather than modifying the OAuth flow.**

**Acceptance M3:** register → land on jobs tab; kill app → reopen → still logged in; expire access token manually (set a 10-second expiry in local backend config for one test) → request transparently refreshes; logout → welcome screen; wrong password shows Dutch error, not a crash.

---

### M4 — Jobs feed + detail

- Feed: React Query `['jobs', filters]` → `GET /api/public/jobs` (works pre-login too — allow browsing without an account, but applying requires login). Card: title, client region (Eindhoven/Veldhoven/Helmond), skill chips (max 4 + "+n"), salary range if present, posted-ago. Filter chips above list: skill, ervaring (junior/medior/senior), type (vast/detachering). Pull-to-refresh. Skeletons while loading. EmptyState: "Geen vacatures gevonden — pas je filters aan."
- Detail `jobs/[id]`: full description, tech stack chips, salary, location, duration; sticky bottom bar with gold **"Solliciteer in 1 tap"** button + bookmark icon (saved-jobs endpoints).
- **Builder: fetch one real job from the API first and match the actual field names from `models/schemas.py` — do not guess field names.**

**Acceptance M4:** real vacancies from prod (or seeded local DB) render; filters change results; detail deep-linkable via `gsprecruitment://jobs/<id>`.

---

### M5 — 1-click apply + applications

- Apply button → if profile lacks a CV: bottom sheet "Voeg eerst je CV toe" → CV picker (`expo-document-picker`, PDF only, ≤10 MB) → `POST /api/v1/candidate/cv` → then apply. Otherwise: `POST /api/v1/candidate/applications` with job id → confetti-free success state (simple gold checkmark animation) "Sollicitatie verstuurd ✓ — GSP neemt binnen 24 uur contact op."
- Applications list lives as a segment control on the Matches tab ("Matches | Sollicitaties"). Status timeline on `applications/[id]`: Verstuurd → In review → Voorgesteld bij client → Gesprek → Aanbod (map from the actual status enum in the backend — read it, don't invent).
- Duplicate apply → backend will 4xx; show "Je hebt al gesolliciteerd op deze vacature."

**Acceptance M5:** end-to-end apply against local backend creates a row visible in the admin web portal; re-apply blocked gracefully; CV upload works from Files app.

---

### M6 — Matches tab + profile

- Matches: `GET /api/v1/candidate/matches` → cards with MatchRing (%), job title, top-3 overlapping skills, CTA to job detail. Sort by score desc. EmptyState: "Nog geen matches — vul je skills aan voor betere matches" + button to profile edit.
- Profile view: avatar initials on navy, name, headline, skills chips, CV status (filename or "Geen CV"), **passive-mode card**: switch "Ik sta open voor kansen" + optional "Beschikbaar vanaf" (month picker) → `PUT /api/v1/candidate/profile` mapping to `is_passive` / `availability`.
- Profile edit: fields per the profile schema (read `CandidatePortalProfile` in `models/schemas.py`), skills multi-select, CV replace.

**Acceptance M6:** toggling passive mode persists (verify via GET after app restart); profile edits reflect in web admin portal.

---

### M7 — Salary insights tab

`GET /api/v1/candidate/salary-benchmark` (fallback to the public endpoint pre-login). Simple, no chart library: for each role/level row render P25/P50/P75 as a horizontal bar (plain Views) with a gold marker, JetBrains Mono figures. One picker: ervaring (junior/medior/senior). Footer: "Gebaseerd op geanonimiseerde Brainport-data." If the table is empty in prod, show a tasteful "Binnenkort beschikbaar" EmptyState — **check first whether `salary_benchmarks` has data.**

**Acceptance M7:** renders real or empty state without crashing; numbers formatted as €-thousands (€72.000).

---

### M8 — Push notifications end-to-end

`usePushNotifications.ts`: request permission (after login, or from welcome step 3) → `expo-notifications` `getExpoPushTokenAsync` (needs `projectId` from EAS, see M10) → `POST /api/v1/candidate/device-token`. On logout → DELETE it. Foreground notifications: show in-app banner. Tap handling: read `data.screen`/`data.id` → `router.push` to matches or application detail. Android: create a notification channel `default` (importance high, gold accent color).

**Acceptance M8:** using Expo's push tool (send to the printed token) a test push arrives on a physical device and deep-links to the right screen; triggering a match in the local backend fires a real push.

---

### M9 — Settings, GDPR, polish

- Settings: notificatie-toggles (nieuwe matches / status updates — store locally, filter client-side for MVP), taal (NL only, disabled row), links: privacybeleid (`https://gsp-recruitment.nl/privacy.html` via in-app browser), contact, app-versie.
- "Account verwijderen" → double confirm (type-DELETE-style: hold-to-confirm button) → `DELETE /api/v1/candidate/account` → logout → welcome. Dutch copy: "Dit verwijdert je profiel, CV en sollicitaties permanent."
- Polish pass: every screen gets loading skeleton + error state ("Er ging iets mis — probeer opnieuw" + retry) + empty state; check all touch targets; `accessibilityLabel` audit; test on a small screen (iPhone SE size) and Android.

**Acceptance M9:** delete-account e2e works locally (row anonymized, login afterwards fails); airplane-mode on every tab shows cached data or a graceful error, never a white screen.

---

### M10 — Build & store delivery

```bash
npm i -g eas-cli && eas login        # needs the owner's Expo account
eas init                              # writes projectId into app.json
eas build --profile preview --platform android   # APK for direct device testing FIRST
eas build --profile production --platform all
eas submit --platform ios            # needs Apple Developer account (€99/yr) + app record in App Store Connect
eas submit --platform android        # needs Play Console (€25 once)
```

`eas.json`: `preview` (internal distribution APK) + `production` profiles; set `EXPO_PUBLIC_API_URL=https://gsp-recruitment.nl` in production env.

Store listing (owner provides screenshots from the finished app):
- **Title:** "GSP Recruitment — Embedded vacatures Brainport"
- **Subtitle/short:** "Embedded software jobs in regio Eindhoven. Solliciteer in 1 tap."
- **Keywords:** embedded, C++, vacature, Eindhoven, Brainport, RTOS, firmware, engineer
- **Privacy labels (Apple):** Contact Info, User Content (CV), Identifiers (push token) — all "linked to you", none used for tracking. **Google Data Safety** equivalently.
- Apple: because Google sign-in may be offered, **Sign in with Apple becomes mandatory** — if Google login shipped in M3, add `expo-apple-authentication` now; if Google was deferred, this is deferred too.
- Age rating 4+. Category: Business / Zaken.

**Acceptance M10:** preview APK runs the full flow against production API on a real device; production builds submitted to TestFlight + Play internal track.

---

### M11 — Launch integration (website + ops)

1. Website: add a "Download de app" section on `index.html` + `kandidaten.html` (App Store / Play badges, QR code). Add App Banner meta tag (`apple-itunes-app`) once the App Store ID exists.
2. Backend: add the app's deep-link association files to the website for universal links (optional, Phase 2 if time-boxed).
3. Monitoring: add `expo-updates` for OTA fixes (production profile), and Sentry (`sentry-expo`) free tier for crash reporting — 30 min, high value.
4. Update `.github/workflows/deploy.yml` awareness: backend changes from M0 deploy through the existing pipeline; confirm migration 007 ran in prod (`schema_migrations` table).

**Acceptance M11 / final QA script:** on a physical phone with the production API: register fresh account → onboarding skills → browse jobs → save one → upload CV → apply → see application → toggle passive mode → receive a push (trigger via admin) → tap push → land on the right screen → delete account. Every step in Dutch, no crash, no English leakage.

---

## 5. Phase 2 backlog (do NOT build now — parked)

Chat (needs WebSocket or polling + the M0 POST endpoint gives a head start), Match Quiz, biometric app-lock, certificate pinning + jailbreak detection, LinkedIn profile import, client portal in-app, employer branding pages, referral program, calendar/interview scheduling, offline mutation queue, light mode.

---

## 6. Website & backend findings (separate from the app — prioritized)

Found while auditing on 2026-07-08. None block the app; fix in this order when there's budget.

1. **HIGH — Deployment ambiguity:** `wrangler.jsonc` serves `website/` via Cloudflare Workers, but `website/CNAME` suggests a GitHub Pages history. Confirm which one actually serves gsp-recruitment.nl and delete the dead path (likely the CNAME) to avoid a stale copy of the site resurfacing.
2. **HIGH — Candidate messaging is write-disabled:** candidates and clients can `GET` messages but there is no candidate `POST` endpoint, so any "stuur bericht" UI on the web portal is dead or missing. M0.2 fixes the API; afterwards check `website/candidate/index.html` actually offers sending.
3. **MEDIUM — Matching/sourcing tasks don't run in prod:** production compose runs only postgres + backend (no Redis/Celery), so anything in `talent-os/backend/tasks/` (auto-sourcing, screening) is inert — the compose file itself documents this. Either accept it (matching still works synchronously via `services/matcher.py`) or add a simple `cron` + management script instead of Celery; don't deploy Celery for a one-person shop.
4. **MEDIUM — Push triggers (M0.4) should also notify on new jobs matching saved skill filters** — deferred: needs a job→candidates fan-out query; add after MVP proves retention.
5. **LOW — `backend/` directory at repo root is empty** — delete it; it confuses tooling and humans (the real backend is `talent-os/backend/`).
6. **LOW — `.env` sits in the repo working tree** (`projects/gsp-recruitment/.env`): confirm it's gitignored (`.gitignore` exists) and contains no live secrets; rotate anything that ever got committed.
7. **LOW — Website has no app landing page yet** — covered by M11.

---

## 7. Cost summary (corrected)

| Item | One-time | Monthly |
|---|---|---|
| Development (AI-assisted via this plan) | ~€0 | — |
| Apple Developer Program | €99/yr | €8.25 |
| Google Play Console | €25 | — |
| EAS (build credits, free tier likely sufficient at this cadence) | — | €0–15 |
| Push (Expo push service) | — | €0 |
| Backend delta (reuses existing VPS) | — | €0 |
| **Total** | **~€124** | **~€8–23** |

Break-even remains: **1 placement (€16.5k) covers ~60+ years of app costs.**

---

*GSP Recruitment — Embedded Software Engineers voor Brainport. Altijd gratis voor engineers.*
