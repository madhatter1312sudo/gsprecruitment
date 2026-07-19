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

These are the three checks that must pass before shipping a change (all
non-interactive, safe to run in CI):

```sh
npm install                        # dependency resolution
npx tsc --noEmit                   # strict TypeScript, zero errors
npx expo export --platform web     # static web build → dist/
```

There is no automated test suite yet (no Jest/Testing Library configured —
out of scope for this build to keep the dependency list minimal). Manual
smoke test checklist before a release:

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
| `GET /v1/mobile/me/matches`, `GET /v1/mobile/me/applications` | `GET /api/v1/candidate/matches`, `GET /api/v1/candidate/applications` (`routers/candidate.py`) | Calls the real `/v1/candidate/...` paths. |
| `GET/POST` job detail at some `/public/jobs/{id}` | Only `GET /api/public/jobs` (list) exists — `routers/jobs.py`'s `public_jobs_router` has no `{job_id}` route | `job/[id].tsx` resolves the job from the same React Query cache the feed populated (`lib/queries.ts` `useJob`), refetching the list if needed instead of calling a route that would 404. |
| `GET /v1/public/quiz`, `POST /v1/public/quiz/submit` | Neither exists in `routers/public.py` (only `site-content`, `salary-data`, `blog`, `lead`) | The quiz is fully client-side (`lib/quiz-data.ts`) — the same approach the **existing website** uses for its own match quiz (`website/script.js` `initQuiz()`, also purely local). On submit, if the user leaves an email, the app posts the result to the real `POST /v1/public/lead` (`interest_type: 'candidate'`), mirroring exactly what the website's quiz does today for email capture. |
| `POST /v1/mobile/push-token` | Doesn't exist; the backend build plan (`GSP_APP_BUILD_PLAN.md`) lists push-token registration as a not-yet-built backend gap | `lib/api.ts` has `registerPushToken()` typed and ready, but it is **never called** — wiring it up would also require `expo-notifications`, which isn't in the approved minimal dependency list. Left as a documented no-op for when both sides exist. |
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
