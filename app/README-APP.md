# GSP Recruitment — mobile app

Expo (SDK 57) + TypeScript (strict) + expo-router + React Query + Zustand.
Dark navy/gold theme matching the public website (`website/styles.css`).
Faceless brand: no founder name/photo anywhere in the app, GDPR self-service
built in, Dutch/English toggle for every user-visible string.

## Requirements

- Node v22 (already satisfied in this environment)
- An Expo account (free) — only needed for EAS builds, not for local dev
- A phone with the **Expo Go** app (iOS App Store / Google Play), or an
  iOS Simulator / Android emulator

## Run it locally

```sh
cd app
npm install
npx expo start
```

This prints a QR code in the terminal. Scan it with the Camera app (iOS) or
the Expo Go app (Android) — the app opens on your phone, live-reloading as
you edit. Press `w` in the terminal to also open the web version in a
browser, `i`/`a` for the iOS/Android simulator if you have Xcode/Android
Studio installed.

The API base URL is set in `app.json` under `expo.extra.apiBaseUrl`
(`https://api.gsprecruitment.nl/api`). Change it there (or override via an
EAS build profile's `env`) to point at a local backend during development.

## Testing / quality gates

These are the checks that must pass before shipping a change (all
non-interactive, safe to run in CI):

```sh
npm install                        # dependency resolution
npx tsc --noEmit                   # strict TypeScript, zero errors (npm run typecheck)
npm test                           # Jest unit + component tests (offline, mocked API)
npm run test:integration           # hits the REAL production API — needs network
npm run test:e2e                   # Playwright against the static web export
npx expo export --platform web     # static web build → dist/
```

### Unit / component suite (`npm test`)

Jest + `jest-expo` + `@testing-library/react-native`, fully offline (no
network calls — every `lib/api.ts` call is mocked). Config: `jest.config.js`,
specs in `__tests__/unit/`. Covers `lib/validation.ts`, `lib/format.ts`,
`lib/i18n.ts`, the offline quiz-scoring fallback (`lib/quiz-data.ts`), the
auth store (login/logout/hydrate), `JobCard`, `MatchRing`, the login screen's
validation states, and the full quiz flow (fetch → 12 questions → server
result, plus the offline-fallback and authenticated-email paths) with the
API mocked via `jest.mock('../../lib/api')`.

### API integration suite (`npm run test:integration`)

`__tests__/integration/api.test.ts`, run via `jest.integration.config.js`
(plain Node + Babel-TypeScript transform, no RN environment). Hits
`https://api.gsprecruitment.nl/api` for real: registers a throwaway
`app-tester+{timestamp}@gsprecruitment.nl` candidate, logs in, checks
`GET /public/jobs` (6+ jobs), `GET /v1/public/quiz` (12 items, no
`correct_index`/`answer` leaked), `POST /v1/public/quiz/submit` (score/tier/
feedback), `GET /v1/candidate/matches` (authed), `GET /v1/gdpr/export`, then
`DELETE /v1/gdpr/account` to soft-delete the test account again. Kept out of
`npm test` on purpose so the unit suite never needs network access.

### E2E suite (`npm run test:e2e`)

Playwright (Chromium, headless) driving the real static web export
(`npx expo export --platform web` → `dist/`, served locally via `npx serve`
— see `playwright.config.ts`'s `webServer`). The app still talks to the real
production API; since its CORS allow-list covers the real site origins and
not `localhost`, `e2e/fixtures.ts` intercepts `api.gsprecruitment.nl`
requests and re-fulfills them with an `access-control-allow-origin` header
(a test-harness shim only — it doesn't change what the app sends). Covers:
the jobs feed rendering 6 jobs and opening a job detail screen, the quiz
flow from start through all 12 (randomized-pool) questions to a rendered
tier badge, and login-screen validation states. Install the browser once
with `npx playwright install chromium` if it isn't cached yet.

Manual smoke test checklist for anything the automated suites don't cover
(native-only flows — CV upload, share sheet, push, EAS builds):

1. Jobs feed loads, pull-to-refresh works, tapping a card opens detail.
2. Job detail: logged out → prompted to log in; logged in without a CV →
   prompted to upload one; logged in with a CV → "Solliciteer direct"
   posts the application and shows the success state.
3. Register → login → logout round-trip.
4. Matches tab: empty state when no matches; MatchRing renders the score
   once matches exist.
5. Quiz: all 12 questions navigate correctly, result screen shows tier,
   domain bars, per-question feedback and a growth tip.
6. Career tab: salary picker returns data for "Software Engineer" /
   "Senior" / "Eindhoven" (a combination that exists in the seeded
   `salary_benchmarks` table); pipeline view shows applications once
   logged in.
7. Profile: edit + save a field, upload/replace a CV, toggle NL/EN (every
   screen's text should switch), export data (opens the native share
   sheet with the JSON), delete account (double confirmation, then logs
   out).

## EAS builds (App Store / Play Store)

EAS builds require **your own Expo account** — this repo does not and
should not contain any Expo/EAS credentials.

```sh
npm install -g eas-cli
eas login                 # your Expo account
cd app
eas build:configure       # links this project to your Expo account/project id
```

Build profiles are defined in `eas.json`:

- `development` — internal dev-client build (installs alongside Expo Go)
- `preview` — internal distribution build for TestFlight-style ad-hoc testing
- `production` — store-ready build (Android App Bundle / iOS build), auto
  increments the build number

```sh
eas build --platform ios --profile preview
eas build --platform android --profile preview
eas build --platform all --profile production
eas submit --platform ios       # after a production build
eas submit --platform android
```

iOS builds need an Apple Developer account (€99/yr) and Android release
builds need a Google Play Console account (one-off €25) — both are set up
interactively the first time `eas build`/`eas submit` asks for them.

## API adjustments made against the real backend

The brief specified a candidate API surface; before wiring screens to it,
the actual routers in `talent-os/backend/routers/*.py` were read directly
(per the existing `GSP_APP_BUILD_PLAN.md` guardrail: never invent
endpoints). Differences between the brief and what the backend actually
exposes, and how this app resolves them:

| Brief said | Backend actually has | What the app does |
|---|---|---|
| `GET /v1/mobile/me/matches`, `GET /v1/mobile/me/applications` | Both now exist, but so do `GET /api/v1/candidate/matches`, `GET /api/v1/candidate/applications` (`routers/candidate.py`), which is what this app was originally wired to | Keeps calling `/v1/candidate/...` — both work, no reason to churn a working call site. |
| `GET/POST` job detail at some `/public/jobs/{id}` | Only `GET /api/public/jobs` (list) exists — `routers/jobs.py`'s `public_jobs_router` has no `{job_id}` route | `job/[id].tsx` resolves the job from the same React Query cache the feed populated (`lib/queries.ts` `useJob`), refetching the list if needed instead of calling a route that would 404. |
| `POST /v1/mobile/push-token` | **Now live** in production | `lib/api.ts`'s `registerPushToken()` points at the real endpoint, but it is still **never called** from any screen — wiring it up would also require `expo-notifications`, which isn't in the approved minimal dependency list. Left as a documented no-op for when that dependency is added. |

### Quiz: now server-graded (`GET /v1/public/quiz`, `POST /v1/public/quiz/submit`)

These endpoints were not built when the app's first version shipped, so the
quiz was fully client-side. They are **now live** in production and
`app/(tabs)/quiz.tsx` fetches real questions and submits answers for
server-side grading by default — the local question bank in
`lib/quiz-data.ts` is kept only as an **offline fallback** (clearly labelled
"Offline versie" in the UI) for when the fetch fails.

Two mismatches between the original brief/local design and what the live
endpoints actually return, both handled in the app:

- **Different domain taxonomy.** The server's questions are tagged with
  `general_swe` | `security` | `cloud_devops` | `embedded_cpp` — a
  completely different set from the original local 6-domain bank
  (`frontend`/`backend`/`devops_cloud`/`data_ai`/`security`/`softskills`).
  `lib/quiz-data.ts` exports `SERVER_GROWTH_TIPS` (growth-tip copy keyed by
  the real server domains, with a generic fallback for any domain value
  added later) separately from the original `GROWTH_TIPS` (kept for the
  offline fallback's own domain set).
- **`tier` is an opaque, pre-formatted string.** `POST .../quiz/submit`
  returns `tier` as e.g. `"Senior-indicatie"` — the same text regardless of
  the `lang` query param (verified: submitting with `lang=en` still returns
  `"Junior-indicatie"`, not an English string). The app renders this value
  directly rather than trying to re-translate it.

The quiz-email flow: if the user is logged in, their account email is sent
with the submission automatically; if not, an optional one-field "link this
result to your email?" screen appears after the last question (skippable)
before the answers are POSTed. This is separate from the existing "email me
this result" card on the results screen, which still uses `POST
/v1/public/lead` for marketing capture exactly as the website's own quiz
does.
| Salary seniority values implied `"Medior"` etc. | `salary_benchmarks.seniority` is seeded lowercase (`junior`/`mid`/`senior`/`lead` — see `migrations/009_salary_benchmarks_seed.py`) and the query filter is an exact match | `lib/career-tips.ts` maps the Dutch/English "Medior" label to the query value `mid` (not `medior`), and other labels to their lowercase equivalents, so lookups actually hit seeded rows. |
| — | — | Password rule ("≥8 chars, upper+lower+digit") is enforced client-side only (`lib/validation.ts`) — the backend (`models/schemas.py UserRegister`) only enforces `min_length=8`. Any password passing the client check also passes the backend, so this is a strictly additive UX guard, not a mismatch. |
| — | — | `POST /api/auth/refresh` doesn't issue a distinct refresh token — login/register return a single `access_token` and refresh just re-validates whatever token you send it. `lib/auth.ts`/`lib/api.ts` treat the access token as the refresh candidate and fall back to logging the user out if refresh fails (expired token). |

Everything else (`/api/auth/register`, `/login`, `/forgot-password`,
`/api/public/jobs`, `/api/v1/public/salary-data`, `/api/v1/candidate/profile`
(GET/PUT), `/api/v1/candidate/cv`, `/api/v1/candidate/applications` (POST),
`/api/v1/gdpr/export`, `DELETE /api/v1/gdpr/account`) matched the brief
exactly once the `/api` base prefix is applied and was wired as specified.

## Brand assets

`assets/icon.png`, `splash-icon.png` and the Android adaptive-icon layers
were generated from `website/logo-icon.png` / `website/favicon-64.png` —
the gold interlocking mark that the **live site's own** `<link rel="icon">`
and `apple-touch-icon` tags actually reference (verified in
`website/index.html`). Note: `website/assets/` also contains an unrelated
"SR Engineering" branded asset bundle (a colourful hexagon mark with that
name baked into some of the PNGs/SVGs) that is **not** GSP Recruitment's
identity — it was deliberately not used for anything.
