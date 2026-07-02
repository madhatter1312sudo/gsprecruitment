# GSP Recruitment — Enterprise-Grade Website Architecture Specification

> **Date:** 2025-06-25  
> **Status:** Draft v1.0  
> **Scope:** Full-stack recruitment platform with user registration, candidate dashboard, salary benchmarking tool, and mobile-first responsive design

---

## Table of Contents

1. [Current State Analysis](#1-current-state-analysis)
2. [Target Architecture Overview](#2-target-architecture-overview)
3. [Registration & Auth System](#3-registration--auth-system)
4. [Full Candidate Journey](#4-full-candidate-journey)
5. [Market Value Compass — Salary Benchmarking Tool](#5-market-value-compass--salary-benchmarking-tool)
6. [Logo & Branding Concept](#6-logo--branding-concept)
7. [Frontend Architecture](#7-frontend-architecture)
8. [Backend Architecture (Augmented)](#8-backend-architecture-augmented)
9. [Mobile-First Responsive Design Plan](#9-mobile-first-responsive-design-plan)
10. [Database Schema Additions](#10-database-schema-additions)
11. [API Route Map](#11-api-route-map)
12. [Implementation Roadmap](#12-implementation-roadmap)

---

## 1. Current State Analysis

### Existing Frontend (`/website/`)
| Asset | Lines | Notes |
|-------|-------|-------|
| `index.html` | 967 | Static SPA — single page, all sections in one file. EN/NL bilingual via CSS class toggle. |
| `styles.css` | 1,767 | Mature design tokens (navy/orange palette), Inter font, CSS variables, scroll animations, responsive breakpoints at 1024px and 768px. No auth/portal styles. |
| `script.js` | 307 | Language toggle, hamburger menu, scroll animations, contact form (POSTs to `/api/contact`), lead magnet form (POSTs to `/api/lead`). No auth logic. |

### Existing Backend (`/talent-os/backend/`)
| Module | Purpose |
|--------|---------|
| `FastAPI` on port 8000 | Async API server |
| `asyncpg` pool | PostgreSQL connection, min=2 max=10 |
| 7 routers | health, candidates, jobs, matches, apollo, webhook |
| `X-API-Key` auth | API key in header for all data endpoints |
| HMAC-SHA256 | Webhook signature verification |
| Celery + Redis | Background tasks (Apollo sync, semantic matching) |
| SMTP configured (Zoho) | Email ready but no auth email flows yet |

### Existing Database (PostgreSQL 16)
7 tables already defined: `clients`, `job_orders`, `candidates`, `matches`, `outreach_campaigns`, `outreach_messages`, `hiring_signals`, `salary_benchmarks`, `skill_gaps`, `referral_graph`, `data_subject_requests`, `model_feedback`.

**MISSING:** Users table, roles, sessions, refresh tokens, email verification, password reset, candidate profiles linked to auth.

---

## 2. Target Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CLOUDFLARE                                │
│  DNS, DDoS protection, CDN (gsptalent.com, api.gsptalent.com)     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│                     REVERSE PROXY (Caddy)                           │
│  /api/* → backend:8000  │  /* → static SPA or Next.js              │
│  /ws/*  → backend:8000  │  Auto-TLS, HTTP/3                        │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
┌──────────▼──────────┐ ┌──▼──────────┐ ┌──▼──────────┐
│   PUBLIC SITE       │ │   API       │ │   DASHBOARD │
│  (static/Next.js)   │ │   backend   │ │  (Next.js)  │
│  / → Landing        │ │  :8000      │ │  /dashboard │
│  /jobs              │ │  FastAPI    │ │  /profile   │
│  /salary-compass    │ │             │ │  /matches   │
│  /register          │ │  asyncpg    │ │  /settings  │
│  /login             │ │  Celery     │ │             │
└─────────────────────┘ └──────┬──────┘ └─────────────┘
                               │
                    ┌──────────▼──────────┐
                    │     PostgreSQL       │
                    │  (asyncpg pool)      │
                    │  + Redis (Celery)    │
                    └─────────────────────┘
```

### Key Architectural Decisions

1. **SPA → Next.js migration** for SSR/SSG on public pages, client routing on dashboard
2. **JWT + refresh token auth** instead of API-key-only (reserve API keys for machine-to-machine)
3. **Dual-mode auth**: session-based (browser cookies) + JWT bearer (mobile/app)
4. **No model hosting** — all AI/LLM via OpenRouter (existing decision, maintained)
5. **Celery** for async: email sending, CV parsing, salary data refresh, Apollo sync

---

## 3. Registration & Auth System

### 3.1 User Types (Roles)

| Role | Description | Permissions |
|------|-------------|-------------|
| `candidate` | Job seeker | Register, view matches, update profile, use salary compass, apply to jobs |
| `client` | Hiring company | Post jobs, view candidate matches, manage team |
| `admin` | GSP internal | Full access, manage users, view analytics, configuration |
| `superadmin` | System owner | Everything + infra config, billing, audit logs |

### 3.2 Auth Flow (JWT + Refresh Tokens)

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Visitor │     │   API    │     │   DB     │     │   Email  │
└────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘
     │                │                │                │
     │  POST /auth/register            │                │
     │────────────────►│                │                │
     │                 │ INSERT users   │                │
     │                 │───────────────►│                │
     │                 │ (status='pending')             │
     │                 │                │                │
     │  201 Created    │                │                │
     │◄────────────────│                │                │
     │                 │                │                │
     │  ── email verification ──        │                │
     │                 │  SEND email    │                │
     │                 │────────────────────────────────►│
     │                 │                │                │
     │                 │                │    Email with  │
     │                 │                │  verify token  │
     │                 │                │◄────────────────│
     │                 │                │                │
     │  GET /auth/verify?token=xxx      │                │
     │────────────────►│                │                │
     │                 │ UPDATE status  │                │
     │                 │ = 'active'     │                │
     │                 │───────────────►│                │
     │  redirect /login │               │                │
     │◄────────────────│                │                │
     │                 │                │                │
     │  POST /auth/login (email+pass)   │                │
     │────────────────►│                │                │
     │                 │ VERIFY creds   │                │
     │                 │───────────────►│                │
     │  200 + JWT      │                │                │
     │ + refresh_token │                │                │
     │◄────────────────│                │                │
```

### 3.3 Token Structure

```json
{
  "access_token": {
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "expires_in": 1800,
    "type": "Bearer"
  },
  "refresh_token": {
    "token": "dGhpcyBpcyBh...",
    "expires_in": 604800,
    "type": "Refresh"
  },
  "user": {
    "id": 42,
    "email": "candidate@example.com",
    "role": "candidate",
    "full_name": "Jan de Vries",
    "email_verified": true,
    "profile_complete": 35
  }
}
```

### 3.4 Auth Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/auth/register` | Create account (candidate or client) |
| `POST` | `/auth/login` | Email + password → JWT pair |
| `POST` | `/auth/refresh` | Refresh token → new JWT pair |
| `POST` | `/auth/logout` | Invalidate refresh token (server-side) |
| `GET` | `/auth/verify` | Email verification (token in query) |
| `POST` | `/auth/resend-verify` | Resend verification email |
| `POST` | `/auth/forgot-password` | Send reset link |
| `POST` | `/auth/reset-password` | Reset with token |
| `GET` | `/auth/me` | Current user profile |
| `PATCH` | `/auth/me` | Update profile |
| `DELETE` | `/auth/me` | Anonymize/delete (GDPR) |

### 3.5 Registration Form Fields

**Candidate Registration:**
- Email (required, unique, verified)
- Password (min 8 chars, must have uppercase + number)
- Full name (required)
- Phone (optional)
- LinkedIn URL (optional)
- Primary skills (multi-select: Embedded, C++, Mechatronics, Cybersecurity, Motion Control, Other)
- Years of experience (optional)
- Current location (required — region filter for Brainport)
- Work authorization (EU citizen / EU work permit / Need visa)
- Consent: GDPR data processing (required)
- Consent: salary data contribution (optional)
- reCAPTCHA v3 (passive, no checkbox)

**Client Registration:**
- Company name (required)
- Company email domain (required, verified)
- Password (same rules)
- Full name (required)
- Job title (required)
- Company size (select)
- LinkedIn company URL (optional)
- Industry focus (multi-select)
- GDPR consent (required)
- reCAPTCHA v3

### 3.6 Password Policy

- Minimum 8 characters, maximum 128
- Must contain: 1 uppercase, 1 lowercase, 1 digit
- Optional: 1 special character
- Bcrypt (cost factor 12)
- Rate limit: 5 attempts per 15 min per email
- Lockout after 10 failed attempts (24h or email reset)

### 3.7 Session Management

- Access token: 30 min (short-lived, in-memory or httpOnly cookie)
- Refresh token: 7 days (httpOnly cookie, `Secure`, `SameSite=Strict`)
- Refresh token rotation: each refresh issues a new refresh token, old one invalidated
- Server-side blocklist for logout (Redis, TTL = max token lifetime)
- Concurrent sessions: limit 5 per user (enforce via session table)

---

## 4. Full Candidate Journey

```
VISITOR ──► REGISTER ──► VERIFY ──► ONBOARD ──► EXPLORE ──► GET MATCHED ──► APPLY ──► PLACED ──► ALUMNI
  │           │            │          │            │            │             │          │          │
  ▼           ▼            ▼          ▼            ▼            ▼             ▼          ▼          ▼
Landing    Create       Email     Profile    Job Board    AI Matching    Submit    Offer     Alumni
Page       Account      Verify    Wizard     + Salary    + Warm Intro   App       Accepted  Network
                                    │         Compass                                       │
                                    ▼                                                     ▼
                              CV Upload                                              Retention
                              Skill Test                                             Check-ins
                              Preferences                                           Referrals
```

### Phase 1: Visitor → Registered (`~2 min`)
1. Lands on `gsptalent.com`
2. Clicks "Register" or "Get Started" (from hero, salary CTA, or any CTAs)
3. Sees role selection screen: *"I'm a Candidate"* vs *"I'm an Employer"*
4. Fills registration form (see §3.5)
5. Submit → 201 Created → "Check your email" screen
6. Email sent with verification link (expires 24h)

### Phase 2: Verified → Onboarded (`~5 min`)
7. Clicks verification link → status becomes `active`
8. Redirected to `/onboard` (multi-step wizard):

   **Step 1 — Profile Basics**
   - Profile photo upload (optional)
   - Professional headline (e.g. "Senior Embedded Engineer at ASML")
   - Bio/summary (200-500 chars)

   **Step 2 — Skills & Experience**
   - Skill tags (from predefined list + custom)
   - Years of experience per skill domain
   - Upload CV (PDF/DOCX → AI-extracted via OpenRouter)
   - GitHub/Portfolio URL

   **Step 3 — Preferences**
   - Job type: perm / contract / both
   - Salary range (min/max slider)
   - Location preference: Eindhoven / Remote / Hybrid
   - Willing to relocate: Yes/No
   - Company size preference (startup / scale-up / enterprise)
   - Industry focus

   **Step 4 — Market Value Compass** (see §5)
   - See your estimated market value
   - Option to contribute anonymized salary data to improve benchmarks

   **Step 5 — Ready**
   - Dashboard preview
   - "Notify me about matching roles" toggle
   - WhatsApp opt-in for quick notifications

9. Welcome email with onboarding summary sent

### Phase 3: Onboarded → Matched (`ongoing`)
10. Dashboard shows:
    - **Match score** (0-100%) for active job orders
    - **Recent matches** sorted by score, with role, company, location
    - **Market Value Compass** snapshot (your value vs market)
    - **Application tracker** (applied / in review / interview / offer)
    - **Upcoming interviews** calendar
    - **Skill gap analysis** (X skill missing for Y top role)
11. AI matching runs daily (Celery task):
    - Semantic similarity between candidate profile + CV and open job orders
    - Combined score: skills match (60%) + experience (20%) + cultural indicators (10%) + location (10%)
12. High-scoring matches → Warm Introduction via Gijs (human touchpoint)
13. Candidate receives email/notification: *"Gijs knows the hiring manager at [Company] — interested?"*

### Phase 4: Matched → Applied → Interviewing
14. Candidate expresses interest → application submitted
15. GSP reviews → warm introduction made
16. Status updates in dashboard: `applied` → `intro_made` → `interview_scheduled` → `interview_complete` → `offer` → `accepted` → `placed`
17. Each status change triggers notification (email + in-app toast)

### Phase 5: Placed → Alumni
18. Candidate accepted offer → `placed` status
19. **12-month retention tracking** (check-ins at month 1, 3, 6, 12)
20. Alumni network: referral rewards, salary data contribution, mentor matching
21. GDPR data retention: candidate data kept for 2 years post-placement unless withdrawn

---

## 5. Market Value Compass — Salary Benchmarking Tool

### 5.1 Overview
An interactive salary benchmarking widget that combines GSP's proprietary data with real-time market intelligence. Serves as a **lead magnet** and **engagement driver** for registered candidates.

### 5.2 Visual Mockup

```
┌─────────────────────────────────────────────────────────────┐
│  🔶 MARKET VALUE COMPASS                                     │
│  Know your worth in Brainport Eindhoven                      │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  ROLE           │  Senior Embedded Engineer           │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │  EXPERIENCE     │  [━━━━━━━●━━━━━━━━━━] 7 years      │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │  SKILLS         │  [C++] [RTOS] [ARM] [FPGA] [+add] │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │  LOCATION       │  [▼ Eindhoven region ▼]            │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────┐ ┌──────────────────────┐  │
│  │  YOUR ESTIMATED VALUE        │ │  MARKET RANGE        │  │
│  │  €78,500 - €95,000 / year   │ │  €55K ─●──€100K      │  │
│  │                              │ │        ↑ YOU         │  │
│  │  P75 percentile             │ │  ┌──────┬──────┐     │  │
│  │  Above market median (+12%) │ │  │ P25  │ P75  │     │  │
│  └──────────────────────────────┘ │  │€55K  │€85K  │     │  │
│                                    │  ├──────┼──────┤     │  │
│                                    │  │ P50  │ P90  │     │  │
│                                    │  │€70K  │€100K │     │  │
│                                    │  └──────┴──────┘     │  │
│                                    └──────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  🔍 BREAKDOWN BY FACTOR                              │   │
│  │                                                      │   │
│  │  Base Salary      ████████████████░░░  78%  €70K     │   │
│  │  Bonus            ██████████░░░░░░░░  52%  €8K      │   │
│  │  Stock/Options    ███████░░░░░░░░░░░  38%  €5K      │   │
│  │  Benefits         ████████████░░░░░░  62%  €12K     │   │
│  │                                        ──────────    │   │
│  │  Total Estimated                          €95K       │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  📈 MARKET TRENDS                                    │   │
│  │                                                      │   │
│  │  Salary growth YoY: +5.2%  ▲                         │   │
│  │  Demand index: 78/100 (High) 🔥                      │   │
│  │  Time-to-hire avg: 42 days ⏱                        │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  📥 [Download Full Report (PDF)]  🔗 [Compare with Others]  │
│                                                              │
│  *Powered by GSP Recruitment data + aggregated anonymized   │
│   contributions from 150+ placements in Brainport*          │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 Functional Requirements

| Feature | Priority | Description |
|---------|----------|-------------|
| Role selector | P0 | Dropdown with 20+ tech roles (embedded, C++, mechatronics, cybersecurity, motion control) |
| Experience slider | P0 | 0-20+ years, updates chart in real-time |
| Skills tag input | P0 | Multi-select from domain skills, affects estimate |
| Location selector | P0 | Brainport sub-regions (Eindhoven, Veldhoven, Helmond, Best, Son, etc.) |
| Salary gauge | P0 | Animated gauge showing user's estimated value vs market percentiles |
| Breakdown chart | P0 | Bar chart showing base + bonus + equity + benefits |
| Market trends | P1 | YoY growth, demand index, time-to-hire from GSP proprietary data |
| Download PDF | P1 | Generate branded PDF report |
| Compare | P2 | Compare two roles or two experience levels side-by-side |
| Historical view | P2 | Trend line showing salary changes over past 3 years |
| Anonymized submit | P2 | Contribute your salary data to improve benchmarks (opt-in, GDPR-compliant) |

### 5.4 Data Sources

| Source | Type | Freshness |
|--------|------|-----------|
| GSP placement data (150+ placements) | Proprietary | Real-time |
| `salary_benchmarks` table | Database | Updated weekly via Celery task |
| External APIs (levels.fyi, Glassdoor) | Aggregated | Monthly refresh |
| User-contributed anonymous data | Crowdsourced | Real-time (with validation) |
| Apollo.io market intelligence | Enriched | Weekly |

### 5.5 Backend Implementation

New router: `/api/salary-compass/`

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/salary-compass/roles` | List available roles with seniority levels |
| `POST` | `/api/salary-compass/estimate` | Calculate estimate based on role/exp/skills/location |
| `POST` | `/api/salary-compass/contribute` | Anonymous salary data contribution |
| `GET` | `/api/salary-compass/trends` | Market trend data |
| `GET` | `/api/salary-compass/report` | Generate PDF report |

### 5.6 Algorithm (Pseudo)

```python
async def estimate_market_value(role, experience, skills, location):
    baseline = await fetch_baseline(role, seniority_level(experience))
    
    skill_bonus = sum(skill_premium[s] for s in skills if s in skill_premium)
    location_factor = location_multiplier[location]  # Brainport premium vs national
    experience_curve = logistic_growth(experience, midpoint=5, max_multiplier=1.4)
    
    estimated_min = baseline.p50 * experience_curve + skill_bonus * 0.7
    estimated_max = baseline.p75 * experience_curve * 1.1 + skill_bonus * 1.3
    
    return {
        "estimated_range": (round(estimated_min, -3), round(estimated_max, -3)),
        "p25": baseline.p25,
        "p50": baseline.p50,
        "p75": baseline.p75,
        "p90": baseline.p90,
        "confidence": compute_confidence(baseline.sample_size, skills_match),
        "breakdown": compute_breakdown(estimated_min, estimated_max, role),
        "trends": market_trends[role]
    }
```

---

## 6. Logo & Branding Concept

### 6.1 Challenge
Current Drive access has `drive.file` scope — can only see files created by the app, not manually uploaded logo files. Need to generate concepts that can be executed with available tools or sourced externally.

### 6.2 Brand DNA
| Attribute | Expression |
|-----------|------------|
| **Premium** | Clean, minimal, not loud |
| **Tech** | Precision-engineering aesthetic — think ASML, Prodrive |
| **Human** | Warmth through orange accent, not cold blue corporate |
| **Brainport** | Regional pride, innovation hub |
| **Founder-led** | Personal, boutique, not mass-market |

### 6.3 Logo Concept Recommendation

**Primary Concept: "The Compass G"** (Recommended)

```
         ┌─────────────┐
         │    ▲         │
         │   / \        │
         │  / G \       │
         │ /     \      │
         │└───────┘     │
         │    ▲         │
         │    █         │
         └─────────────┘
```

- A letter "G" stylized as a compass needle pointing Northeast (Brainport direction from center of Netherlands)
- Orange gradient (same as current `#f97316`) for the G/needle
- Dark navy background (current `#0a1628`)
- Clean, sans-serif "GSP Recruitment" in Inter Bold beside it
- Secondary line: "Tech Talent · Brainport"

**Why compass:**
- Aligns with "Market Value Compass" feature
- Suggests guidance, direction, career navigation
- Points to Brainport (literal geographic reference)
- Minimal, scalable to favicon size

**Alternative: "The Circuit G"**
- Letter G formed by stylized PCB trace corners (90° angles)
- Orange lines on dark background
- Appeals to embedded/IoT/electronics talent demographic

**Alternative: "The Bridge G"**
- G formed by two interlocking brackets `[ ]` suggesting connection
- Top bracket orange, bottom bracket navy
- Represents "connecting talent to opportunity"

### 6.4 Color Palette (Maintain existing)

| Token | Hex | Usage |
|-------|-----|-------|
| `--orange-500` | `#f97316` | Primary accent, CTAs, highlights |
| `--navy-900` | `#060d1a` | Hero backgrounds, footer |
| `--navy-800` | `#0a1628` | Section backgrounds |
| `--navy-700` | `#0f1d35` | Card backgrounds, alt sections |
| `--white` | `#ffffff` | Primary text |
| `--navy-200` | `#7fa0c9` | Secondary text |
| WhatsApp Green | `#25D366` | WhatsApp float (existing) |

### 6.5 Implementation Path (since Drive access is limited)

1. **Generate SVG logo programmatically** using the compass-G concept — can be done with inline SVG in code
2. **Use an SVG-to-favicon pipeline** — the existing data:image/svg+xml favicon already works
3. **Commission a designer** via Fiverr/99Designs (~€200-500) for final polished version
4. **Temporary fallback**: The current `logo-icon` with gradient "G" is clean and professional — it works as a placeholder while Drive access is resolved

---

## 7. Frontend Architecture

### 7.1 Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Framework | **Next.js 15** (App Router) | SSR for SEO, API routes, middleware for auth |
| Language | TypeScript | Type safety, better DX |
| Styling | **Tailwind CSS v4** + CSS Variables | Utility-first, consistent with existing design tokens |
| State | React Context + React Query (TanStack Query) | Server state management, caching |
| Forms | React Hook Form + Zod | Performant forms with validation |
| Auth | next-auth (Auth.js) v5 | Social + credentials, battle-tested |
| Charts | Recharts or Chart.js | Salary compass visualizations |
| Animation | Framer Motion | Page transitions, scroll animations |
| Email templates | React Email | Type-safe email components |
| PWA | next-pwa | Offline-capable, installable |

### 7.2 Page Structure

```
/ (public)
├── page.tsx                    # Landing page (from current index.html)
├── jobs/page.tsx               # Public job listings (SSR)
├── jobs/[id]/page.tsx          # Job detail (SSR)
├── salary-compass/page.tsx     # Market Value Compass (public teaser)
├── register/page.tsx           # Registration (role selection)
├── register/candidate/page.tsx # Candidate form
├── register/client/page.tsx    # Employer form
├── login/page.tsx              # Login
├── forgot-password/page.tsx    # Password reset
├── verify/page.tsx             # Email verification result
├── privacy/page.tsx            # Privacy policy
├── cookies/page.tsx            # Cookie policy

/dashboard (protected)
├── layout.tsx                  # Dashboard layout (sidebar + header)
├── page.tsx                    # Overview — match score, recent activity
├── profile/page.tsx            # View/edit profile
├── profile/cv/page.tsx         # CV upload & parsing
├── profile/skills/page.tsx     # Skills assessment
├── matches/page.tsx            # All matches with filters
├── matches/[id]/page.tsx       # Match detail
├── applications/page.tsx       # Application tracker
├── compass/page.tsx            # Full Market Value Compass (authenticated)
├── messages/page.tsx           # Messages from GSP (future)
├── settings/page.tsx           # Account, notifications, GDPR
├── settings/security/page.tsx  # Password change, 2FA
├── settings/notifications/page.tsx  # Email/SMS preferences

/admin (protected, admin only)
├── layout.tsx
├── page.tsx                    # Dashboard — KPIs
├── candidates/page.tsx         # Candidate management
├── jobs/page.tsx               # Job order management
├── matches/page.tsx            # Match review & approval
├── salary-data/page.tsx        # Salary benchmark management
├── analytics/page.tsx          # Platform analytics
├── users/page.tsx              # User management
├── settings/page.tsx           # System configuration
```

### 7.3 Component Tree (Key Components)

```
<App>
  <AuthProvider>
    <QueryClientProvider>
      <ThemeProvider>  <!-- EN/NL + dark theme -->
        <Router>
          <PublicLayout>           <!-- Landing, Jobs, etc. -->
            <Header />             <!-- Nav, lang toggle, auth state -->
            <Hero />
            <ServicesSection />
            <SalaryCompassTeaser />  <!-- Public version, limited data -->
            <Footer />
          </PublicLayout>

          <DashboardLayout>        <!-- Authenticated -->
            <DashboardSidebar />   <!-- Nav links, user info -->
            <DashboardHeader />    <!-- Search, notifications, avatar -->
            <Breadcrumbs />
            <DashboardContent />   <!-- Varies by route -->
            <NotificationToast />
          </DashboardLayout>

          <SalaryCompass>          <!-- Used in public teaser + dashboard -->
            <RoleSelector />
            <ExperienceSlider />
            <SkillTags />
            <LocationSelect />
            <SalaryGauge />        <!-- Animated SVG gauge -->
            <PercentileChart />    <!-- Bar chart with P25-P90 -->
            <BreakdownChart />     <!-- Stacked bar: base + bonus + equity -->
            <MarketTrends />       <!-- YoY growth, demand index -->
            <ContributeModal />    <!-- Optional data contribution -->
            <DownloadReportButton />
          </SalaryCompass>
        </Router>
      </ThemeProvider>
    </QueryClientProvider>
  </AuthProvider>
</App>
```

### 7.4 Frontend Auth Middleware (Next.js)

```typescript
// middleware.ts
export { auth as middleware } from "@/auth"

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/admin/:path*",
    "/api/protected/:path*",
  ]
}
```

---

## 8. Backend Architecture (Augmented)

### 8.1 New Python Modules

| Module | Purpose |
|--------|---------|
| `routers/auth.py` | Registration, login, token management |
| `routers/salary_compass.py` | Market Value Compass endpoints |
| `routers/dashboard.py` | Aggregated dashboard data |
| `routers/profile.py` | Candidate profile CRUD |
| `routers/admin.py` | Admin-only management endpoints |
| `services/auth_service.py` | JWT creation/validation, password hashing, email verification |
| `services/email_service.py` | Email sending (Zoho SMTP) with templates |
| `services/salary_service.py` | Salary estimation algorithm |
| `models/auth_models.py` | Pydantic schemas for auth |
| `core/jwt.py` | JWT encode/decode/refresh utilities |
| `tasks/email_tasks.py` | Celery tasks for async email sending |

### 8.2 Auth Router Details

```python
# routers/auth.py — Outline
router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register")
async def register(data: RegisterRequest, request: Request):
    """Create user account, send verification email."""
    # 1. Validate input (email unique, password strength)
    # 2. Hash password (bcrypt, cost=12)
    # 3. Insert into users table (status='pending')
    # 4. Generate verification token (JWT, expires 24h)
    # 5. Send verification email (async via Celery)
    # 6. Return 201 + user info (no token yet)

@router.post("/login")
async def login(data: LoginRequest, response: Response):
    """Authenticate user, set httpOnly cookies."""
    # 1. Look up user by email
    # 2. Verify password with bcrypt
    # 3. Check account status (active, locked, pending)
    # 4. Generate access + refresh tokens
    # 5. Set httpOnly cookies + return user data
    # 6. Remove old sessions if > 5 concurrent

@router.post("/refresh")
async def refresh(request: Request, response: Response):
    """Refresh access token using refresh token."""
    # 1. Extract refresh token from httpOnly cookie
    # 2. Validate and decode
    # 3. Check not on blocklist (Redis)
    # 4. Issue new access + refresh tokens
    # 5. Invalidate old refresh token (rotation)

@router.post("/logout")
async def logout(request: Request, response: Response):
    """Invalidate all tokens for user."""
    # 1. Add refresh token to Redis blocklist (TTL = remaining lifetime)
    # 2. Delete session record
    # 3. Clear cookies

@router.get("/verify")
async def verify_email(token: str):
    """Verify email address via token."""
    # 1. Decode and validate verification token
    # 2. Update user status to 'active'
    # 3. Return success page redirect

@router.post("/forgot-password")
async def forgot_password(data: ForgotPasswordRequest):
    """Send password reset email."""
    # 1. Look up user by email (don't reveal if exists)
    # 2. Generate reset token (JWT, expires 1h)
    # 3. Send reset email (async)
    # 4. Always return 200 (security: don't reveal email existence)

@router.post("/reset-password")
async def reset_password(data: ResetPasswordRequest):
    """Reset password with token."""
    # 1. Decode and validate reset token
    # 2. Hash new password
    # 3. Update user record
    # 4. Invalidate all sessions
```

### 8.3 Email Service

```python
# services/email_service.py — Outline
class EmailService:
    def __init__(self):
        self.smtp = aiosmtplib  # Async SMTP via Zoho

    async def send_verification(self, to_email: str, name: str, token: str):
        """Send email verification with link."""
        template = render_template("verify-email", {
            "name": name,
            "link": f"https://gsptalent.com/verify?token={token}",
            "expires_hours": 24
        })
        await self._send(to_email, "Verify your GSP Recruitment account", template)

    async def send_welcome(self, to_email: str, name: str):
        """Send welcome email after verification."""
        template = render_template("welcome", {
            "name": name,
            "dashboard_link": "https://gsptalent.com/dashboard"
        })
        await self._send(to_email, "Welcome to GSP Recruitment!", template)

    async def send_password_reset(self, to_email: str, name: str, token: str):
        """Send password reset link."""
        template = render_template("reset-password", {
            "name": name,
            "link": f"https://gsptalent.com/reset-password?token={token}",
            "expires_hours": 1
        })
        await self._send(to_email, "Reset your GSP Recruitment password", template)

    async def send_match_alert(self, to_email: str, name: str, matches: list):
        """Send daily/weekly match digest."""
        template = render_template("match-alert", {
            "name": name,
            "matches": matches,
            "dashboard_link": "https://gsptalent.com/dashboard/matches"
        })
        await self._send(to_email, "New job matches for you!", template)
```

### 8.4 Existing Backend Enhancement Requirements

| Current | Enhancement Needed |
|---------|-------------------|
| API key only auth | Add JWT auth middleware (dual-mode: API key OR JWT) |
| No user table | Add `users` table + role-based access control |
| Contact form POSTs to `/api/contact` | Add contact router (currently only frontend code) |
| Lead form POSTs to `/api/lead` | Add lead capture router |
| No session management | Add Redis session store + refresh token rotation |
| No email verification flow | Add verification tokens + Celery email tasks |
| Static CORS origins | Add dynamic origin checking for auth cookies |
| No rate limiting | Add `slowapi` middleware for auth endpoints |

---

## 9. Mobile-First Responsive Design Plan

### 9.1 Breakpoint Strategy (Maintain Current + Expand)

| Name | Width | Layout | Notes |
|------|-------|--------|-------|
| **Phone** | < 480px | Single column, stacked cards | Smallest screens (iPhone SE) |
| **Phone+** | 481-768px | Single column, wider cards | Most common mobile |
| **Tablet** | 769-1024px | 2-column grid, visible sidebar | iPads, small laptops |
| **Desktop** | 1025-1440px | Multi-column, full layout | Current default |
| **Wide** | > 1440px | Max-width 1200px, centered | Large monitors |

### 9.2 Responsive Dashboard Layout

```
PHONE (< 768px)                       TABLET (769-1024px)
┌─────────────────┐                  ┌──────────┬──────────────┐
│ 🔶 GSP  ☰      │  ← hamburger    │ Logo     │ 🔍  Notif  👤│
├─────────────────┤                  ├──────────┴──────────────┤
│ 📊 Dashboard    │                  │                         │
│                 │                  │ 📊 Welcome, Jan!       │
│ Match Score     │                  │ ┌─────┬─────┬─────┐    │
│ ████████░░ 82%  │                  │ │82%  │3 New│2 Int│    │
│                 │                  │ │Match│Jobs │views│    │
│ Recent Matches  │                  │ └─────┴─────┴─────┘    │
│ ┌─────────────┐ │                  │                         │
│ │ Sr. Embedded│ │                  │ Recent Matches...      │
│ │ ASML  92%   │ │                  │ ┌───────────────────┐  │
│ └─────────────┘ │                  │ │Sr. Embedded @ ASML│  │
│ ┌─────────────┐ │                  │ │Score: 92%  Apply→│  │
│ │ C++ Engineer│ │                  │ └───────────────────┘  │
│ │VDL ETG  88% │ │                  │                         │
│ └─────────────┘ │                  │ [Bottom Nav]            │
│                 │                  │ 🏠 🔍 📋 👤            │
│ [Bottom Nav]    │                  │                         │
│ 🏠 🔍 📋 👤    │                  └─────────────────────────┘
└─────────────────┘
```

### 9.3 Key Mobile UX Decisions

| Element | Implementation |
|---------|---------------|
| Navigation | Bottom tab bar (5 icons: Home, Search, Matches, Profile, Settings) on mobile |
| Sidebar | Off-canvas drawer (slide from left) on mobile, permanent on desktop |
| Tables | Horizontal scroll with sticky first column on salary table |
| Charts | Responsive SVG (viewport-aware sizing) for salary compass |
| Forms | Stacked fields (no multi-column rows on mobile) |
| Buttons | Full-width CTAs on mobile, inline on desktop |
| Filter bars | Collapsible accordion filters on mobile, inline on desktop |
| Modals | Full-screen bottom sheets on mobile, centered overlay on desktop |
| Notifications | Toast at top on mobile (not obstructing bottom nav), bottom-right on desktop |

### 9.4 Salary Compass Responsive

```
MOBILE                                          DESKTOP
┌─────────────────────────┐                    ┌─────────────────────────────────────┐
│ 🔶 Market Value Compass │                    │ 🔶 Market Value Compass              │
│                         │                    │                                     │
│ [Role ▼]                │                    │ [Role ▼]  [Exp ●━━━━━]  [Skills +]  │
│ [Exp ●━━━━━━━]          │                    │                                     │
│ [Skills: C++, RTOS +]   │                    │ ┌─────────────────┐ ┌─────────────┐ │
│                         │                    │ │ €78K - €95K     │ │  P25 P50    │ │
│ ┌─────────────────┐     │                    │ │ Your Estimate   │ │  P75  P90   │ │
│ │ €78K - €95K     │     │                    │ └─────────────────┘ └─────────────┘ │
│ │ Your Estimate   │     │                    │                                     │
│ └─────────────────┘     │                    │ ┌─── Breakdown ──────────────────┐  │
│                         │                    │ │ Base ■■■■■■■■■■░░░  €70K      │  │
│ ┌─── Breakdown ──────┐  │                    │ │ Bonus ■■■■■■░░░░░░  €8K       │  │
│ │ Base  ■■■■■■■  €70K│  │                    │ └───────────────────────────────┘  │
│ │ Bonus ■■■■    €8K  │  │                    │                                     │
│ └────────────────────┘  │                    │ 📈 Trends  📥 Download             │
│                         │                    └─────────────────────────────────────┘
│ 📥 Download Report      │
└─────────────────────────┘
```

### 9.5 CSS Architecture (Migration from current to Tailwind)

**Phase 1 (Hybrid):**
- Keep existing `styles.css` design tokens as CSS variables
- Add Tailwind utility classes for new dashboard components
- Use `@apply` in component CSS to reference existing tokens

**Phase 2 (Full Migration):**
- Migrate design tokens to `tailwind.config.ts`
- Convert section-by-section from CSS to Tailwind
- Remove `styles.css` once all sections migrated

**Critical to preserve:**
- All existing design tokens (navy palette, orange accent, spacing, radius, shadows)
- Intersection Observer scroll animations
- Language toggle mechanism (EN/NL)
- Responsive breakpoints

---

## 10. Database Schema Additions

### 10.1 New Table: `users`

```sql
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    role            VARCHAR(50) NOT NULL DEFAULT 'candidate'
                    CHECK (role IN ('candidate', 'client', 'admin', 'superadmin')),
    status          VARCHAR(50) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'active', 'suspended', 'locked', 'deleted')),
    
    -- Profile fields
    phone           VARCHAR(50),
    avatar_url      VARCHAR(500),
    linkedin_url    VARCHAR(500),
    location        VARCHAR(255),
    
    -- Candidate-specific (nullable for clients)
    headline        VARCHAR(255),
    bio             TEXT,
    years_experience DECIMAL(4,1),
    skills          TEXT[],
    languages       TEXT[],
    education       TEXT,
    cv_file_path    VARCHAR(500),
    cv_text         TEXT,
    job_type_pref   VARCHAR(50),
    salary_min      INTEGER,
    salary_max      INTEGER,
    location_pref   VARCHAR(50),
    willing_relocate BOOLEAN DEFAULT FALSE,
    
    -- Client-specific (nullable for candidates)
    company_name    VARCHAR(255),
    company_domain  VARCHAR(255),
    company_size    VARCHAR(50),
    job_title       VARCHAR(255),
    
    -- Auth & security
    email_verified  BOOLEAN DEFAULT FALSE,
    email_verified_at TIMESTAMP,
    two_factor_enabled BOOLEAN DEFAULT FALSE,
    last_login_at   TIMESTAMP,
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until    TIMESTAMP,
    
    -- Notifications
    email_notifications BOOLEAN DEFAULT TRUE,
    whatsapp_opt_in     BOOLEAN DEFAULT FALSE,
    whatsapp_number     VARCHAR(50),
    
    -- GDPR
    consent_granted_at      TIMESTAMP,
    consent_withdrawn_at    TIMESTAMP,
    data_retention_until    TIMESTAMP,
    deleted_at              TIMESTAMP,
    
    -- Timestamps
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
CREATE INDEX IF NOT EXISTS idx_users_company ON users(company_name);
CREATE INDEX IF NOT EXISTS idx_users_skills ON users USING GIN(skills);
```

### 10.2 New Table: `sessions`

```sql
CREATE TABLE IF NOT EXISTS sessions (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_token_hash VARCHAR(255) NOT NULL,
    user_agent      VARCHAR(500),
    ip_address      VARCHAR(45),
    expires_at      TIMESTAMP NOT NULL,
    revoked_at      TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(refresh_token_hash);
```

### 10.3 New Table: `email_verification_tokens`

```sql
CREATE TABLE IF NOT EXISTS email_verification_tokens (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      VARCHAR(255) NOT NULL UNIQUE,
    type            VARCHAR(50) NOT NULL
                    CHECK (type IN ('verify_email', 'reset_password', 'change_email')),
    expires_at      TIMESTAMP NOT NULL,
    used_at         TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_verification_tokens_user ON email_verification_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_verification_tokens_hash ON email_verification_tokens(token_hash);
```

### 10.4 New Table: `salary_contributions`

```sql
CREATE TABLE IF NOT EXISTS salary_contributions (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,
    role_title      VARCHAR(255) NOT NULL,
    seniority       VARCHAR(50),
    years_experience DECIMAL(4,1),
    location        VARCHAR(255),
    base_salary     INTEGER NOT NULL,
    bonus           INTEGER DEFAULT 0,
    stock_options   INTEGER DEFAULT 0,
    benefits_value  INTEGER DEFAULT 0,
    currency        VARCHAR(3) DEFAULT 'EUR',
    is_anonymous    BOOLEAN DEFAULT TRUE,
    validated       BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_salary_contrib_role ON salary_contributions(role_title);
```

### 10.5 Existing Schema Updates

| Table | Addition |
|-------|----------|
| `candidates` | Add `user_id INTEGER REFERENCES users(id)` — link to auth user |
| `clients` | Add `user_id INTEGER REFERENCES users(id)` — link to auth user |
| `candidates` | Add `profile_complete DECIMAL(3,1) DEFAULT 0` — onboarding progress % |
| `candidates` | Add `onboarding_step INTEGER DEFAULT 0` — current wizard step |
| `job_orders` | Add `created_by INTEGER REFERENCES users(id)` — who posted it |

---

## 11. API Route Map

### 11.1 Public Routes (No Auth)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | System health (existing) |
| `GET` | `/api/public/jobs` | Public job listings |
| `GET` | `/api/public/jobs/{id}` | Public job detail |
| `GET` | `/api/public/salary-compass/roles` | Available roles for compass |
| `POST` | `/api/public/salary-compass/estimate` | Public estimate (limited data) |
| `POST` | `/api/public/lead` | Lead capture (existing) |
| `POST` | `/api/public/contact` | Contact form (existing frontend code, needs backend) |

### 11.2 Auth Routes (No Auth Required)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/register` | Register |
| `POST` | `/auth/login` | Login |
| `POST` | `/auth/refresh` | Refresh tokens |
| `POST` | `/auth/logout` | Logout |
| `GET` | `/auth/verify` | Verify email |
| `POST` | `/auth/resend-verify` | Resend verification |
| `POST` | `/auth/forgot-password` | Forgot password |
| `POST` | `/auth/reset-password` | Reset password |

### 11.3 Protected Routes (JWT Required)

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/auth/me` | Any | Current user profile |
| `PATCH` | `/auth/me` | Any | Update profile |
| `DELETE` | `/auth/me` | Any | Delete account (GDPR) |
| `GET` | `/api/dashboard/overview` | Any | Dashboard aggregated data |
| `GET` | `/api/dashboard/matches` | candidate | My matches |
| `GET` | `/api/dashboard/applications` | candidate | Application tracker |
| `POST` | `/api/dashboard/apply/{job_id}` | candidate | Apply to job |
| `GET` | `/api/profile` | candidate | Full profile |
| `PATCH` | `/api/profile` | candidate | Update profile |
| `POST` | `/api/profile/cv` | candidate | Upload CV |
| `GET` | `/api/profile/onboarding` | candidate | Get onboarding step |
| `PATCH` | `/api/profile/onboarding` | candidate | Update onboarding step |
| `GET` | `/api/salary-compass/estimate` | candidate | Full estimate (authenticated) |
| `POST` | `/api/salary-compass/contribute` | candidate | Contribute salary data |
| `GET` | `/api/salary-compass/report` | candidate | Download PDF report |
| `GET` | `/api/candidates` | admin | List candidates (existing) |
| `POST` | `/api/candidates` | admin | Create candidate (existing) |
| `GET` | `/api/jobs` | client | List my jobs (existing) |
| `POST` | `/api/jobs` | client | Create job (existing) |
| `GET` | `/api/matches` | client | View matches (existing) |

### 11.4 Admin Routes (admin/superadmin Only)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/admin/users` | List all users |
| `PATCH` | `/api/admin/users/{id}` | Update user role/status |
| `DELETE` | `/api/admin/users/{id}` | Delete/suspend user |
| `GET` | `/api/admin/analytics/summary` | Platform analytics |
| `GET` | `/api/admin/analytics/registrations` | Registration trends |
| `GET` | `/api/admin/analytics/placements` | Placement metrics |
| `GET` | `/api/admin/salary-data` | Manage benchmarks |
| `PUT` | `/api/admin/salary-data` | Update benchmark |
| `POST` | `/api/admin/salary-data/refresh` | Trigger refresh |

---

## 12. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)
**Goal:** Auth system working, database migrated

- [ ] Add `users`, `sessions`, `email_verification_tokens`, `salary_contributions` tables
- [ ] Implement `core/jwt.py` — JWT encode/decode/refresh
- [ ] Implement `services/auth_service.py` — registration, login, password hashing
- [ ] Implement `routers/auth.py` — all auth endpoints
- [ ] Implement `services/email_service.py` — async SMTP via Zoho
- [ ] Implement `tasks/email_tasks.py` — Celery tasks for email sending
- [ ] Add rate limiting middleware (`slowapi`)
- [ ] Add existing candidate/client link to `user_id`

### Phase 2: Frontend Auth (Weeks 2-3)
**Goal:** Users can register, verify, login, see dashboard

- [ ] Set up Next.js 15 project with App Router
- [ ] Implement `next-auth` v5 configuration
- [ ] Build registration pages (role selection, candidate form, client form)
- [ ] Build login page
- [ ] Build email verification page
- [ ] Build forgot/reset password pages
- [ ] Build dashboard layout (sidebar, header, responsive bottom nav)
- [ ] Build dashboard overview page
- [ ] Implement auth middleware and route protection

### Phase 3: Candidate Journey (Weeks 3-5)
**Goal:** Full candidate flow from registration to matched

- [ ] Build onboarding wizard (5 steps, with progress indicator)
- [ ] Build profile page (view/edit)
- [ ] Build CV upload (PDF/DOCX parsing via OpenRouter)
- [ ] Build match display with score visualization
- [ ] Build application tracker with status badges
- [ ] Implement notification system (email + in-app)
- [ ] Build settings pages (account, security, notifications)

### Phase 4: Market Value Compass (Weeks 4-6)
**Goal:** Salary benchmarking tool fully functional

- [ ] Implement `routers/salary_compass.py` (all endpoints)
- [ ] Implement `services/salary_service.py` (estimation algorithm)
- [ ] Populate `salary_benchmarks` table with initial data (150+ placements)
- [ ] Build SalaryGauge component (animated SVG)
- [ ] Build PercentileChart component (Recharts bar chart)
- [ ] Build BreakdownChart component (stacked bar)
- [ ] Build MarketTrends component
- [ ] Build public teaser version (limited data, lead capture)
- [ ] Build full authenticated version
- [ ] Build PDF report generation
- [ ] Build data contribution modal (with GDPR consent)

### Phase 5: Admin & Polish (Weeks 5-7)
**Goal:** Admin panel, responsive optimization, launch readiness

- [ ] Build admin dashboard (user management, analytics)
- [ ] Build admin salary data management
- [ ] Responsive audit: test all pages at 320px, 480px, 768px, 1024px, 1440px
- [ ] Performance optimization (Lighthouse score > 90)
- [ ] SEO audit (meta tags, structured data, sitemap)
- [ ] Security audit (OWASP Top 10)
- [ ] Final logo integration (SVG logo component)
- [ ] GDPR compliance review
- [ ] Load testing (100 concurrent users)

### Phase 6: Launch (Week 8)
- [ ] DNS configuration (gsptalent.com, api.gsptalent.com)
- [ ] SSL/TLS via Caddy auto-cert
- [ ] Database migration on production
- [ ] Smoke tests
- [ ] Monitoring setup (Prometheus metrics exist)
- [ ] Go live

---

## Appendix A: Key Design Decisions Log

| # | Decision | Rationale | Date |
|---|----------|-----------|------|
| 1 | JWT over session-only | SPA-friendly, mobile/API support | 2025-06-25 |
| 2 | httpOnly cookies over localStorage | XSS protection for auth tokens | 2025-06-25 |
| 3 | Refresh token rotation | Mitigate token theft impact | 2025-06-25 |
| 4 | Next.js over pure SPA | SEO for public pages, middleware for auth | 2025-06-25 |
| 5 | Tailwind over pure CSS | Faster component development, consistency | 2025-06-25 |
| 6 | Phase-based CSS migration | Unblocked development, no rewrite risk | 2025-06-25 |
| 7 | SVG logo over raster | Scalable, small footprint, animatable | 2025-06-25 |
| 8 | Async email via Celery | Non-blocking during registration | 2025-06-25 |
| 9 | Salary data as lead magnet | Drives registrations, creates stickiness | 2025-06-25 |
| 10 | Bottom nav on mobile | Thumb-friendly, follows material design patterns | 2025-06-25 |

## Appendix B: Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Google Drive scope (`drive.file`) can't see uploaded logos | Medium | High | Generate SVG programmatically as fallback; commission external designer |
| Email deliverability (Zoho SMTP) for verification emails | High | Medium | SPF/DKIM/DMARC setup; monitoring via Postmark alternative |
| Slow salary compass queries on large dataset | Medium | Low | Materialized view for benchmarks; Redis caching |
| Rate limiting blocking legitimate users | Medium | Low | Tiered limits (auth: 5/min, data: 60/min, public: 120/min) |
| GDPR data export requests manual effort | Medium | Low | Automated CSV export endpoint; data_subject_requests table already exists |

---

*End of Architecture Specification v1.0*