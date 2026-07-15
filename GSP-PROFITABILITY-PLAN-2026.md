# GSP Recruitment — Profitability Plan (July 2026)

**Supersedes:** GSP_Mobile_App_MASTERPLAN.md, GSP_Recruitment_App_Plan.md financial sections where they conflict.
**Adopts:** BUILD_PLAN v2.0 app approach, Finance-review corrected numbers.

---

## 0. The One Sentence That Matters

The platform is live, the API works (55 endpoints), the site is indexed — and there are **0 candidates, 0 jobs, 0 revenue**. Every hour spent on features before there is inventory and outreach is an hour spent polishing an empty store.

**North star: first placement within 90 days.** One placement (€16.5–18k) = ~4 years of operating costs.

---

## 1. Corrected Business Numbers (adopt these, stop using the old ones)

| Item | Old (plans) | **Adopted (finance review)** |
|---|---|---|
| Monthly costs | €174–179 | **€354** (€480 with AOV insurance) |
| Fee split (partner deals) | 45–50% | **55%** |
| Avg commission | €16,500 | **€18,000** (25% of €72k senior salary) |
| Extra revenue line | — | **€2,000/mo retainer** for exclusive search |
| Self-sourced deals | — | 100% GSP (no split) |
| Break-even | 1 placement | 1 placement (unchanged, still true) |
| Year-1 target | 3 placements = €15.9k net | **3 placements = ~€21.4k net** at corrected pricing |

**Positioning unchanged:** embedded software engineers, Brainport Eindhoven only (ASML, NXP, Prodrive, Sioux, VDL ETG, Neways, NTS, KMWE supply chain). The niche is the moat.

**One strategy reversal to accept:** drop the "anonymous founder" idea. Put Gijs on the site — photo, bio, direct phone. In a relationship business serving a small market, a faceless agency loses to a named specialist every time.

---

## 2. Week 1 — Truth & Trust (blockers, mostly frontend, ~2 days of work)

These actively lose you every visitor who checks:

1. **Fake phone number** — `+31-6-12345678` is in the Organization JSON-LD and every WhatsApp float on every page. Replace with the real number. *Leads literally cannot contact you.*
2. **Placeholder JobPosting JSON-LD** on index.html ("Job Title", "Job description goes here") — invalid structured data shipped to Google. Remove or make dynamic.
3. **Fabricated social proof** — "150+ placements, 40+ partners, 92%" stats, attribute-less testimonials ("CTO, Prodrive"), and ASML/VDL/Prodrive logos as "trusted by" — for a 2026-founded eenmanszaak this is a legal risk (misleading advertising) and destroys trust with the exact engineers you target. Replace with honest positioning: "Founded 2026. Specialist, not generalist. Here's my background."
4. **Founder section** — add Gijs: photo, embedded-industry credibility, direct contact. This *is* the product at this stage.
5. **Google Search Console** — verification meta is still commented out. Verify and submit sitemap.
6. **Remove dead social-login buttons** — "LinkedIn login coming soon!" toast on the auth modal erodes confidence at the most sensitive moment. Remove until real.
7. **Password mismatch** — register modal `minlength="6"` vs auth.js requiring 8+; and the AVG consent checkbox auth.js requires isn't in the modal HTML → registrations can silently fail. Fix both.

## 3. Week 1–2 — Backend Funnel Bugs (the funnel is broken end-to-end)

Priority order:

1. **Candidate identity bug (CRITICAL):** registration creates `candidate_profiles` but never a `candidates` row; portal joins on email string → every self-registered candidate sees an empty portal (no matches, applications, saved jobs). Create the `candidates` row at registration + backfill. Without this, every candidate you win bounces.
2. **Fake Apply buttons:** candidate portal "Apply" is `onclick="Auth.toast('Applied successfully!')"` — no API call. Wire to `POST /api/v1/candidate/applications`. Same for public `vacature.html`: add real apply + CV upload instead of routing to the contact form.
3. **CORS missing PUT** — client/admin portals use PUT endpoints; cross-origin preflight blocks them. One-line fix in main.py.
4. **CV upload not served** — StaticFiles imported, never mounted. Mount it (auth-gated) so you can actually read the CVs candidates upload.
5. **`update_candidate_profile` overwrites `users.full_name` with job title** — data-destroying bug, fix.
6. **Make AI matching reachable:** `EmbeddingMatcher` (OpenRouter embeddings + cosine) only exists in dead Celery code — Celery isn't deployed and won't even import (`celery_result_backend` missing from config). Don't deploy Celery. Expose matching via FastAPI `BackgroundTasks`: `POST /api/matches/run` triggered on new job / new CV. This unlocks the core value prop with zero new infrastructure.
7. **GDPR endpoints (cheap win):** consent columns + `data_subject_requests` table already exist, zero endpoints. Add export (Art. 15), erasure (Art. 17), consent withdrawal. Low effort, and "GDPR-compliant" is a real selling point to Dutch corporates.
8. **Rate limiter** is per-worker in-memory (4 workers → 4× configured limits, resets on restart). Acceptable for now; note for later Redis move.

**Explicitly do NOT build now:** Celery deployment, messaging send-flows, interview/offer entities, admin CMS persistence, dashboards with real charts, team invites. Dormant tables (`referral_graph`, `skill_gaps`, `model_feedback`) stay dormant.

## 4. Week 2–6 — Inventory & Outreach Engine (this is the actual business)

The tech supports this; it doesn't replace it.

1. **Jobs side (supply):** Get 5–10 real vacancies listed. Path: Brainport supply-chain companies (Zone C: Prodrive, Sioux, Neways, NTS, KMWE) — call/email hiring managers, offer no-cure-no-pay with the 6-month guarantee. Even "represented" roles (with permission) beat an empty board.
2. **Candidate side (demand):** Apollo integration already works live (`/api/apollo/search/candidates`, enrich, intent). Run structured weekly sourcing: 25–30 personalised outreach/day from outreach@, Tue–Thu 08:00–11:00 CET (per existing plan). Log into `candidates` table via the existing X-API-Key CRUD.
3. **Founder-led LinkedIn:** 2–3 posts/week on Brainport embedded market (salary data you already have in `salary_benchmarks`, C++/Rust trends, company deep-dives). The blog has 3 good posts — repurpose them.
4. **Referral program** (from gamification review — the one gamification idea worth doing): transparent tiered rewards €500–1,500 per successful referral placement, paid after 6-month retention. A page + a form; no leaderboards, no badges.
5. **No paid ads until month 3–4** and only after 1–2 organic placements (LinkedIn Ads €500/mo then). Pre-install GTM + LinkedIn Insight Tag + UTM structure now so data accumulates.
6. **Salary calculator as lead magnet:** it already works and it's genuinely good — put it above the fold on kandidaten.html and gate the P90 breakdown behind email.

## 5. SEO Fix With Real Impact

Job pages are client-rendered only (`vacatures.html` renders into an empty div; `vacature.html` fetches on load, no meta description in initial HTML). Your highest-intent SEO pages are invisible to crawlers without JS.

**Cheapest robust fix given static Caddy/Cloudflare Pages hosting:** a build step (or small cron on the VPS) that pre-renders one static HTML page per live vacancy from `GET /api/public/jobs` — real meta description + JobPosting JSON-LD per job, regenerated on job changes, listed in sitemap.xml. Also gets you Google for Jobs eligibility, which is free traffic for exactly your queries.

## 6. Mobile App — Decision

**Defer until 2 placements are closed.** Then follow **BUILD_PLAN v2.0** exactly:

- React Native/Expo, 12 screens, dark-mode navy+gold (#FAC800), React Query, reuse existing FastAPI (13/16 endpoints exist; only push-token, send-message, GDPR-delete are new)
- AI-assisted build, ~1–2 weeks, **~€124 one-time** (store fees), €8–23/mo
- Reject the €6–10k freelancer Masterplan and the €81–114k native TCO scenario — both are dead documents; keep only the €11.5k PWA figure as fallback if React Native stalls

Rationale: the app's job is candidate engagement and you currently have 0 candidates. It multiplies a working funnel; it cannot create one.

## 7. 90-Day Timeline

| Phase | When | Outcome |
|---|---|---|
| Truth & trust fixes (frontend) | Week 1 | Site is honest, contactable, verifiable |
| Funnel bugs (backend) | Week 1–2 | Register → profile → CV → apply → match works end-to-end |
| Matching endpoint + GDPR | Week 2–3 | Core value prop live, compliance story real |
| Job pre-rendering + Google for Jobs | Week 3 | Vacancies indexed, free traffic |
| Inventory: 5–10 jobs, 100+ sourced candidates | Week 2–6 | A store with stock |
| Outreach cadence + LinkedIn content + referral page | Week 2–ongoing | Pipeline building |
| First interviews brokered | Week 6–10 | Proof of function |
| **First placement** | **Week 8–13** | **Break-even for the year** |
| Paid ads decision, mobile app kickoff | After placement #2 | Scale what works |

## 8. Success Metrics (weekly)

- Vacancies live on site (target: 5+ by week 4)
- Candidates in DB with CV (target: 100 by week 6)
- Outreach sent / reply rate (target: 125/wk, >8% replies)
- Candidate registrations that see a non-empty portal (currently: 0% by bug — target 100%)
- Client conversations started (target: 3/wk)
- Interviews brokered (leading indicator of placement)
