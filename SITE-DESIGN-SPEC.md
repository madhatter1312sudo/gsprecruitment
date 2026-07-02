# GSP Recruitment — Complete Site Architecture & Design Specification

> **Brand**: GSP Recruitment  
> **Tagline**: Founder-Led Recruitment — Built by Engineers, for Engineers  
> **Region**: Brainport Eindhoven (High-Tech Corridor, Netherlands)  
> **Audience**: Mid–Senior Embedded, C++, Mechatronics, FPGA & Cybersecurity Engineers; High-Tech Hiring Managers  
> **Version**: 1.0 — Enterprise-Grade Specification  
> **Date**: June 2026

---

## Table of Contents

1. [Brand & Color System](#1-brand--color-system)
2. [Information Architecture](#2-information-architecture)
3. [Public Site (Landing Page)](#3-public-site-landing-page)
4. [Registration & Auth Modal](#4-registration--auth-modal)
5. [Candidate Dashboard](#5-candidate-dashboard)
6. [Client Portal (Hiring Managers)](#6-client-portal-hiring-managers)
7. [Admin Dashboard](#7-admin-dashboard)
8. [Component Library](#8-component-library)
9. [UX Flow Diagrams](#9-ux-flow-diagrams)
10. [API Data Model](#10-api-data-model)
11. [Implementation Roadmap](#11-implementation-roadmap)

---

## 1. Brand & Color System

### 1.1 Brand Identity

| Element | Value |
|---|---|
| Agency name | GSP Recruitment |
| Founder | Gijs van den Berg |
| Voice | Technical, warm, direct, founder-led |
| Languages | English (primary), Dutch (NL) |
| Logo | Golden yellow "G" icon on dark bg; full wordmark "GSP Recruitment" |

### 1.2 Color Palette

#### Primary — Navy Dark (`colors_navy_dark`)
```
--navy-950:  #030812     (deepest, reserved for modals overlays)
--navy-900:  #060D1A     (footer, hero bg)
--navy-800:  #0A1628     (main body background)
--navy-700:  #0F1D35     (section alt, card backgrounds)
--navy-600:  #152B4A     (card borders, subtle surfaces)
--navy-500:  #1E3A5E     (hover states, medium emphasis)
--navy-400:  #2A4A75     (inactive UI, low emphasis)
--navy-300:  #4A6F9F     (muted text, secondary labels)
--navy-200:  #7FA0C9     (body text, paragraph color)
--navy-100:  #C5D6EB     (headings, high-emphasis text)
```

#### Accent — GOLD (`colors_gold`)
```
--gold-500:  #FAC800     (primary accent — buttons, highlights, links)
--gold-400:  #FBD74A     (hover, lighter accents)
--gold-300:  #FCE488     (subtle backgrounds, badges)
--gold-600:  #D4A800     (active, pressed states)
--gold-700:  #AD8800     (deep accent, decorative borders)
--gold-glow: rgba(250, 200, 0, 0.35)  (glow/shadow tokens)
```

> **Note**: The current codebase uses orange (`#f97316`). All orange tokens in the existing CSS must be replaced with the gold equivalents above. The gradient in the existing hero highlight (`#fbbf24`) is retained as a secondary highlight but gold becomes the primary brand color.

#### Neutrals (`colors_neutral`)
```
--white:        #FFFFFF
--off-white:    #F1F5F9
--gray-50:      #F8FAFC
--gray-100:     #E2E8F0
--gray-200:     #CBD5E1
--gray-300:     #94A3B8
--gray-400:     #64748B
--gray-500:     #475569
--gray-600:     #334155
```

#### Semantic (`colors_semantic`)
```
--success:      #22C55E
--warning:      #F59E0B
--error:        #EF4444
--info:         #3B82F6
--success-bg:   rgba(34, 197, 94, 0.1)
--warning-bg:   rgba(245, 158, 11, 0.1)
--error-bg:     rgba(239, 68, 68, 0.1)
--info-bg:      rgba(59, 130, 246, 0.1)
```

### 1.3 Typography

| Token | Value | Usage |
|---|---|---|
| Font family | `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif` | All UI |
| Monospace (code) | `'JetBrains Mono', 'Fira Code', monospace` | Salary tables, technical data |
| --font-size-xs | 0.75rem (12px) | Captions, metadata |
| --font-size-sm | 0.875rem (14px) | Body small, nav items |
| --font-size-base | 1rem (16px) | Body text |
| --font-size-lg | 1.125rem (18px) | Lead paragraphs |
| --font-size-xl | 1.25rem (20px) | Card titles |
| --font-size-2xl | 1.5rem (24px) | Section subtitles |
| --font-size-3xl | 2rem (32px) | Section headings |
| --font-size-4xl | 2.5rem (40px) | Page headings |
| --font-size-5xl | 3.25rem (52px) | Hero headline |
| --font-size-6xl | 4rem (64px) | Dashboard hero stats |

### 1.4 Spacing System

Based on a 4px grid: `--space-xs: 4px, --space-sm: 8px, --space-md: 16px, --space-lg: 24px, --space-xl: 32px, --space-2xl: 48px, --space-3xl: 64px, --space-4xl: 96px, --space-5xl: 128px`.

---

## 2. Information Architecture

### 2.1 Site Map

```
gsptalent.com/
│
├── PUBLIC SITE
│   ├── /                          # Landing page (hero, services, about, salary, cases, testimonials, CTA, contact, footer)
│   ├── /salary-guide              # Deep-dive salary page (SEO-optimized)
│   ├── /for-candidates            # Candidate-focused landing
│   ├── /for-clients               # Client-focused landing
│   ├── /blog/*                    # Blog articles (embedded, C++, mechatronics, career)
│   ├── /privacy                   # Privacy policy
│   ├── /cookies                   # Cookie policy
│   └── /terms                     # Terms of service
│
├── CANDIDATE PORTAL (authenticated)
│   ├── /candidate/dashboard       # Main dashboard hub
│   ├── /candidate/profile         # Profile & CV management
│   ├── /candidate/salary-tool     # Market Value Compass
│   ├── /candidate/matches         # AI job matches
│   ├── /candidate/applications    # Application history & status
│   ├── /candidate/saved           # Saved jobs
│   ├── /candidate/messages        # Messages from GSP recruiters
│   └── /candidate/settings        # Preferences, notifications
│
├── CLIENT PORTAL (authenticated)
│   ├── /client/dashboard          # Main dashboard hub
│   ├── /client/jobs               # Job posting management
│   ├── /client/jobs/new           # Create job posting
│   ├── /client/jobs/:id           # Job detail & applicants
│   ├── /client/candidates         # Candidate discovery & search
│   ├── /client/candidates/:id     # Candidate profile view
│   ├── /client/analytics          # Hiring analytics & reports
│   ├── /client/messages           # Messages with GSP
│   ├── /client/team               # Team management (sub-users)
│   └── /client/settings           # Billing, preferences
│
├── ADMIN PORTAL (authenticated)
│   ├── /admin/dashboard           # System overview (KPIs)
│   ├── /admin/users               # User management
│   ├── /admin/jobs                # All jobs (cross-client)
│   ├── /admin/candidates          # All candidates
│   ├── /admin/matches             # AI matching engine admin
│   ├── /admin/content             # CMS (blog, pages, salary data)
│   ├── /admin/analytics           # Platform-wide analytics
│   ├── /admin/settings            # System configuration
│   └── /admin/logs                # Audit trail & activity log
│
├── AUTHENTICATION
│   ├── /auth/login                # Login page
│   ├── /auth/register             # Registration (links to modal)
│   ├── /auth/reset-password       # Password reset
│   └── /auth/verify               # Email verification
│
└── API
    ├── /api/v1/*                  # RESTful API endpoints
    └── /api/v1/webhooks/*         # Webhook receivers
```

### 2.2 Authentication Model

| Role | Portal | Capabilities |
|---|---|---|
| `anonymous` | Public site | Browse all public pages, submit contact form, download salary guide |
| `candidate` | Candidate Portal | Profile CRUD, salary tool, job matches, applications, messaging |
| `client` | Client Portal | Job CRUD, candidate search, analytics, team management |
| `client_admin` | Client Portal | Same as client + can manage billing and sub-users |
| `admin` | Admin Portal | Full system access, user/job/content/analytics management |

Auth flow: Email + password, Google OAuth, LinkedIn OAuth. JWT-based with refresh tokens. Session duration: 24h (access) / 7d (refresh).

---

## 3. Public Site (Landing Page)

### 3.1 Current State

The existing `index.html` already has a complete single-page landing with:
- Fixed header with nav + language toggle (EN/NL)
- Hero with badge, headline, subtext, dual CTA, stats counter, specialisation card
- Services (6-card grid)
- About (founder bio, values)
- Salary data table + lead magnet form
- Case studies (3 cards)
- Testimonials (3 cards)
- CTA section
- Contact form + info
- Footer + WhatsApp floating button

### 3.2 Required Upgrades

| Component | Current | Upgrade |
|---|---|---|
| **Color accent** | Orange (`#f97316`) | GOLD (`#FAC800`) — replace all orange tokens |
| **Hero animation** | Static | Particle grid + animated gold gradient orbs |
| **Stats** | Static numbers | Animated counter on scroll |
| **Specialisation card** | Static grid | Interactive hover with tech-stack tags |
| **Salary table** | Static HTML | Interactive chart (Chart.js/Recharts) with role/level filters |
| **Lead magnet** | Simple email form | Registration modal trigger (see §4) |
| **Case studies** | 3 cards | Expandable with modal detail view |
| **Testimonials** | Carousel (grid) | True carousel with navigation dots + auto-rotate |
| **Contact form** | Basic POST | Multi-route: candidate / client / general |
| **Blog preview** | Missing | Latest 3 articles from CMS |
| **SEO** | Basic meta | JSON-LD structured data (Organization, JobPosting, FAQ) |
| **PWA** | None | Service worker for offline-capable loading |

### 3.3 New Sections to Add

#### 3.3.1 Blog Preview Strip (after Testimonials)
```
┌─────────────────────────────────────────────┐
│  From the Blog                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│  │ Card 1   │ │ Card 2   │ │ Card 3   │    │
│  │ "C++23   │ │ "Embedded│ │ "Salary  │    │
│  │  Features"│ │  RTOS"   │ │  Trends" │    │
│  └──────────┘ └──────────┘ └──────────┘    │
│  [View all articles →]                      │
└─────────────────────────────────────────────┘
```

#### 3.3.2 Trust Bar (Logos strip)
```
[ASML logo] [VDL ETG] [Prodrive] [NTS] [Neways] [Simac] [KMWE]
```

#### 3.3.3 FAQ Section (before CTA)
```
┌─────────────────────────────────────────────┐
│  Frequently Asked Questions                 │
│  ▼ How does GSP differ from other agencies? │
│    (answer expands)                          │
│  ▼ What roles do you specialise in?         │
│  ▼ How long does a typical placement take?  │
│  ▼ What is the warm introduction process?   │
│  ▼ Do you work with non-EU candidates?      │
└─────────────────────────────────────────────┘
```

### 3.4 Page Template Architecture (for `/for-candidates`, `/for-clients`, `/blog/*`)

```
┌──────────────────────────┐
│ HEADER (shared)          │  → Fixed, glass-blur nav
├──────────────────────────┤
│ PAGE HERO                │  → H1, subtitle, optional CTA
├──────────────────────────┤
│ CONTENT (page-specific)  │  → Sections as defined per page
├──────────────────────────┤
│ CTA STRIP                │  → Shared CTA banner (templated)
├──────────────────────────┤
│ FOOTER (shared)          │  → 4-column footer
└──────────────────────────┘
```

---

## 4. Registration & Auth Modal

### 4.1 Modal Architecture

A universal modal component used for:
1. **Registration** (candidate sign-up)
2. **Login** (all roles)
3. **Lead magnet capture** (salary guide download → creates candidate profile)
4. **Password reset**

### 4.2 Multi-Step Registration Flow (Candidate)

**Step 1: Account Creation**
```
┌─────────────────────────────────────┐
│  Create your free account           │
│                                     │
│  [Email]                            │
│  [Password]                         │
│  [Confirm Password]                 │
│                                     │
│  ○ I'm a candidate looking for work │
│  ○ I'm a client hiring talent       │
│                                     │
│  [Create Account →]                 │
│  or continue with                   │
│  [Google] [LinkedIn]                │
│                                     │
│  Already have an account? Log in    │
└─────────────────────────────────────┘
```

**Step 2: Profile Setup (Candidate)**
```
┌─────────────────────────────────────┐
│  Tell us about yourself             │
│                                     │
│  [Full Name]                        │
│  [Phone (optional)]                 │
│  [Current Role / Title]             │
│  [Years of Experience]              │
│                                     │
│  Primary Specialisation:            │
│  [Embedded] [C++/Software]          │
│  [Mechatronics] [Cybersecurity]     │
│  [FPGA] [Motion Control]            │
│                                     │
│  Work Authorization:                │
│  [EU Citizen] [Work Visa] [Other]   │
│                                     │
│  [Upload CV (.pdf, .docx)]          │
│                                     │
│  [Save & Continue →]                │
└─────────────────────────────────────┘
```

**Step 3: Preferences & Salary**
```
┌─────────────────────────────────────┐
│  Your job preferences               │
│                                     │
│  Desired Roles (multi-select):      │
│  [Embedded] [C++/Software]          │
│  [Mechatronics] [Cybersecurity]     │
│                                     │
│  Current Salary:     [€___]         │
│  Expected Salary:    [€___]         │
│                                     │
│  Preferred Contract:                │
│  [Permanent] [Contract] [Both]      │
│                                     │
│  Open to:                           │
│  [✓] Full-time   [✓] Hybrid        │
│  [ ] Remote      [✓] On-site       │
│                                     │
│  Notice Period: [dropdown]          │
│                                     │
│  [Complete Registration →]          │
└─────────────────────────────────────┘
```

**Step 4: Onboarding Confirmation**
```
┌─────────────────────────────────────┐
│  🎉 You're all set!                 │
│                                     │
│  Welcome to GSP Talent Network      │
│                                     │
│  Here's what happens next:          │
│  • We'll match you against live jobs│
│  • Gijs will review your profile    │
│  • You'll get warm intros — no spam │
│                                     │
│  [Go to Dashboard →]                │
└─────────────────────────────────────┘
```

### 4.3 Client Registration Flow (Simplified)

**Step 1**: Account creation (same as Step 1 above, "I'm a client")
**Step 2**: Company info (Company name, website, industry, location in Brainport)
**Step 3**: Hiring needs (roles they typically hire, volume, timeline)
**Step 4**: Confirmation → redirect to Client Dashboard

### 4.4 Login Modal
```
┌─────────────────────────────────────┐
│  Welcome back                       │
│                                     │
│  [Email]                            │
│  [Password]                         │
│                                     │
│  [Log In]                           │
│  or continue with                   │
│  [Google] [LinkedIn]                │
│                                     │
│  Forgot password?                   │
│  Don't have an account? Register    │
└─────────────────────────────────────┘
```

### 4.5 Component States

| State | Visual |
|---|---|
| **Default** | Clean form, all fields empty |
| **Loading** | Button shows spinner, fields disabled, backdrop remains |
| **Validation error** | Field border turns red, error message below field |
| **Server error** | Toast notification at top of modal |
| **Success** | Green checkmark, auto-transition to next step or dashboard redirect |
| **Rate-limited** | "Too many attempts. Please try again in X minutes." |

---

## 5. Candidate Dashboard

### 5.1 Dashboard Layout

```
┌──────────────────────────────────────────────────────┐
│ [GSP Logo]  [Dashboard] [Profile] [Matches]          │
│             [Applications] [Saved] [Messages]         │
│                                  [Avatar ▼] [🔔 2]   │
├──────────────────────────────────────────────────────┤
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │ Welcome back, Marijn!                            │ │
│  │ Your profile is 80% complete  [Complete Now →]   │ │
│  └──────────────────────────────────────────────────┘ │
│                                                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────┐  │
│  │ Job      │  │ Profile  │  │ Messages │  │ Saved│  │
│  │ Matches  │  │ Views    │  │ Unread   │  │ Jobs │  │
│  │ 12 new   │  │ 8 this wk│  │ 3        │  │ 5    │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────┘  │
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │ Market Value Compass — Your Salary Benchmark     │ │
│  │ ┌──────────────────────────────────────────────┐ │ │
│  │ │ Salary Range Chart (bar chart)                │ │ │
│  │ │                                              │ │ │
│  │ │ Current: €72K  │  Market: €65K-€95K          │ │ │
│  │ │ Your Role: Senior Embedded C++ Engineer       │ │ │
│  │ │ Location: Brainport Eindhoven                 │ │ │
│  │ └──────────────────────────────────────────────┘ │ │
│  │ [Adjust parameters →]                            │ │
│  └──────────────────────────────────────────────────┘ │
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │ Top Matches for You                               │ │
│  │ ┌──────────────┐ ┌──────────────┐ ┌────────────┐ │ │
│  │ │ Senior       │ │ Embedded C++ │ │ Mechatronic│ │ │
│  │ │ Embedded     │ │ Engineer     │ │ Architect  │ │ │
│  │ │ Engineer     │ │ ASML         │ │ VDL ETG    │ │ │
│  │ │ Prodrive     │ │ Match: 94%   │ │ Match: 88% │ │ │
│  │ │ Match: 96%   │ │ [View →]     │ │ [View →]   │ │ │
│  │ │ [Apply Now]  │ │              │ │            │ │ │
│  │ └──────────────┘ └──────────────┘ └────────────┘ │ │
│  │ [View all 12 matches →]                           │ │
│  └──────────────────────────────────────────────────┘ │
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │ Recent Activity                                   │ │
│  │ • Mar 15 — Profile viewed by ASML hiring team     │ │
│  │ • Mar 14 — Gijs sent you a message                │ │
│  │ • Mar 12 — New match: C++ Engineer at NTS         │ │
│  │ • Mar 10 — Application status updated: Interview  │ │
│  └──────────────────────────────────────────────────┘ │
│                                                        │
└──────────────────────────────────────────────────────┘
```

### 5.2 Profile Page

```
┌──────────────────────────────────────────────────────┐
│  My Profile                    [Edit] [Preview]      │
├──────────────────────────────────────────────────────┤
│                                                        │
│  ┌──────┐                                              │
│  │Avatar│  Marijn Jansen                               │
│  │  MJ  │  Senior Embedded C++ Engineer                │
│  └──────┘  Eindhoven, Netherlands                      │
│            Member since March 2025                     │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Professional Summary                              │  │
│  │ [Multi-line text area — "7+ years experience..."] │  │
│  └──────────────────────────────────────────────────┘  │
│                                                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ Skills   │ │Experience│ │Education │ │Languages │ │
│  │ C++, C   │ │ Prodrive │ │ TU/e     │ │ Dutch (NL)│ │
│  │ RTOS     │ │ 2021-25  │ │ MSc      │ │ English   │ │
│  │ ARM      │ │ NTS      │ │ Embedded │ │ (fluent)  │ │
│  │ Qt       │ │ 2018-21  │ │ Systems  │ │           │ │
│  │ [Add +]  │ │ [Add +]  │ │ [Add +]  │ │ [Add +]   │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │ CV / Resume                                       │  │
│  │ [Marijn_Jansen_CV_2025.pdf] [Upload new]          │  │
│  └──────────────────────────────────────────────────┘  │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Preferences                                       │  │
│  │ Desired: Embedded, C++  |  Salary: €75K-€95K     │  │
│  │ Type: Permanent  |  Hybrid  |  Notice: 1 month   │  │
│  │ Authorization: EU Citizen                         │  │
│  │ [Edit Preferences]                                 │  │
│  └──────────────────────────────────────────────────┘  │
│                                                        │
└──────────────────────────────────────────────────────┘
```

### 5.3 Market Value Compass (Salary Tool)

This is the flagship candidate-facing tool. It replaces/extends the current static salary table with an interactive benchmarking engine.

**UI Components:**
1. **Role selector** — dropdown with all GSP specialisations (Embedded, C++, Mechatronics, FPGA, Cybersecurity, Motion Control)
2. **Level slider** — Junior ↔ Mid ↔ Senior ↔ Lead ↔ Architect
3. **Experience slider** — 0–20+ years
4. **Location toggle** — Brainport Eindhoven / Rest of NL / Remote
5. **Output** — animated bar chart showing:
   - Your input salary (if provided)
   - Market 25th percentile
   - Market median (50th)
   - Market 75th percentile
   - Market 90th percentile
6. **Breakdown card** — base salary, bonus range, stock/options, benefits (pension, car, etc.)
7. **Download PDF** — generates a branded salary report

**Data Source**: Aggregated from GSP placements, partner surveys, and public benchmarks — updated quarterly.

### 5.4 Job Matches Page

```
┌──────────────────────────────────────────────────────┐
│  Your Job Matches           [Filter ▼] [Sort ▼]      │
├──────────────────────────────────────────────────────┤
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │ Match Score: 96%    Senior Embedded Engineer     │ │
│  │ Prodrive Technologies                             │ │
│  │ Eindhoven  |  €75K-€95K  |  Permanent           │ │
│  │ C++, RTOS, ARM, FPGA · Hybrid · 2+ years exp     │ │
│  │ [Save] [Hide] [View Details →]                   │ │
│  └──────────────────────────────────────────────────┘ │
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │ Match Score: 94%    Embedded C++ Engineer        │ │
│  │ ASML Netherlands BV                               │ │
│  │ Veldhoven  |  €70K-€90K  |  Permanent            │ │
│  │ Modern C++, RTOS, Linux · On-site · 3+ years     │ │
│  │ [Save] [Hide] [View Details →]                   │ │
│  └──────────────────────────────────────────────────┘ │
│                                                        │
│  (12 total matches — paginated, 5 per page)           │
│                                                        │
└──────────────────────────────────────────────────────┘
```

### 5.5 Application History

| Column | Data |
|---|---|
| Job Title | Linked to job detail |
| Company | Company name + logo |
| Applied Date | Date |
| Status | Applied / Screening / Interview / Offer / Accepted / Declined |
| Last Update | Relative timestamp |
| Actions | View details, withdraw |

Status badges use semantic colors: Applied (info/blue), Screening (warning/amber), Interview (info/blue), Offer (success/green), Accepted (success/green), Declined (error/red).

---

## 6. Client Portal (Hiring Managers)

### 6.1 Dashboard Layout

```
┌──────────────────────────────────────────────────────┐
│ [GSP Logo]  [Dashboard] [Jobs] [Candidates]          │
│             [Analytics] [Team] [Messages]             │
│                                  [Company ▼] [🔔 3]  │
├──────────────────────────────────────────────────────┤
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │ Good morning, ASML Engineering Team!             │ │
│  │ Your active job posts: 4  |  Candidates: 18      │ │
│  └──────────────────────────────────────────────────┘ │
│                                                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────┐  │
│  │ Active   │  │ New      │  │ In       │  │ Offers│  │
│  │ Jobs     │  │ Matches  │  │ Interview│  │ Out   │  │
│  │ 4        │  │ 7 this wk│  │ 5        │  │ 2     │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────┘  │
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │ Pipeline Overview (Kanban)                        │ │
│  │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────┐ │ │
│  │ │New (8)   │ │Screen(5) │ │Interview │ │Offer │ │ │
│  │ │CandidateA│ │CandidateD│ │(3)       │ │(2)   │ │ │
│  │ │CandidateB│ │CandidateE│ │CandidateG│ │CandX │ │ │
│  │ │CandidateC│ │...       │ │CandidateH│ │CandY │ │ │
│  │ └──────────┘ └──────────┘ └──────────┘ └──────┘ │ │
│  │ [View Full Pipeline →]                            │ │
│  └──────────────────────────────────────────────────┘ │
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │ Top Recommended Candidates                        │ │
│  │ ┌──────────────┐ ┌──────────────┐ ┌────────────┐ │ │
│  │ │ Marijn J.    │ │ Sophie K.    │ │ Thomas B.  │ │ │
│  │ │ Sr Embedded  │ │ C++ Engineer │ │ Mechatronic│ │ │
│  │ │ Match: 96%   │ │ Match: 92%   │ │ Match: 89% │ │ │
│  │ │ [View →]     │ │ [View →]     │ │ [View →]   │ │ │
│  │ └──────────────┘ └──────────────┘ └────────────┘ │ │
│  │ [Browse All Candidates →]                          │ │
│  └──────────────────────────────────────────────────┘ │
│                                                        │
└──────────────────────────────────────────────────────┘
```

### 6.2 Job Posting Form

```
┌──────────────────────────────────────────────────────┐
│  Create New Job Posting                              │
├──────────────────────────────────────────────────────┤
│                                                        │
│  Job Title *       [e.g. Senior Embedded C++ Eng.]    │
│  Department        [dropdown or free-text]            │
│                                                        │
│  Specialisation *  [Embedded] [C++] [Mechatronics]    │
│                    [Cybersecurity] [FPGA] [Motion]    │
│                                                        │
│  Location *        [Eindhoven] [Veldhoven] [Helmond]  │
│                    [Best] [Other...]                   │
│                                                        │
│  Work Type         [On-site] [Hybrid] [Remote]        │
│  Contract Type     [Permanent] [Contract] [Both]      │
│                                                        │
│  Salary Range      €[min] — €[max]  per year          │
│  Bonus Range       [0-50]%  (percentage of base)      │
│                                                        │
│  Experience Level  [Junior] [Mid] [Senior] [Lead]     │
│  Years Exp. Req.   [0-2] [2-5] [5-8] [8+]            │
│                                                        │
│  Required Skills *  [C++] [RTOS] [ARM] [Qt]           │
│                     (type to search / add tags)        │
│                                                        │
│  Description *     [Rich text editor]                  │
│                                                        │
│  Responsibilities  [Rich text editor]                  │
│  Requirements      [Rich text editor]                  │
│  Offer / Benefits  [Rich text editor]                  │
│                                                        │
│  [Save Draft]  [Publish Now]  [Cancel]                 │
│                                                        │
└──────────────────────────────────────────────────────┘
```

### 6.3 Candidate Discovery & Search

```
┌──────────────────────────────────────────────────────┐
│  Find Candidates              [Search...] [🔍]       │
├──────────────────────────────────────────────────────┤
│                                                        │
│  Filters:                                              │
│  Specialisation: [All] [Embedded] [C++] [Mech...]     │
│  Level:          [All] [Junior] [Mid] [Senior] [Lead] │
│  Location:       [Brainport] [Remote] [Relocation]    │
│  Salary:         €[min] - €[max]                      │
│  Availability:   [Immediate] [1 month] [3 months]     │
│  Experience:     [0-2] [2-5] [5-8] [8+] years         │
│  [Reset Filters]  [Save Search]                        │
│                                                        │
│  Results: 24 candidates match your filters              │
│  ┌──────────────────────────────────────────────────┐ │
│  │ Marijn Jansen              Match: 96%    ★ Saved│ │
│  │ Senior Embedded Engineer  |  Eindhoven           │ │
│  │ C++, RTOS, ARM, Qt  |  Available: 1 month       │ │
│  │ €72K current  |  Seeks €75K-€95K                 │ │
│  │ [Quick View] [Send Message] [Add to Pipeline]    │ │
│  └──────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────┐ │
│  │ Sophie Klaassen            Match: 92%            │ │
│  │ C++ Software Engineer  |  Veldhoven              │ │
│  │ Modern C++, Python, Linux  |  Available: now     │ │
│  │ €65K current  |  Seeks €70K-€85K                 │ │
│  │ [Quick View] [Send Message] [Add to Pipeline]    │ │
│  └──────────────────────────────────────────────────┘ │
│                                                        │
│  < 1 2 3 ... 5 >                                       │
│                                                        │
└──────────────────────────────────────────────────────┘
```

### 6.4 Analytics Page

| Metric | Chart Type | Description |
|---|---|---|
| Time-to-hire trend | Line chart (30/60/90d) | Average days to fill |
| Candidate pipeline | Funnel chart | New → Screened → Interview → Offer → Hired |
| Source breakdown | Donut chart | Where candidates come from (warm intro, LinkedIn, referral, etc.) |
| Job views vs applies | Bar chart | Per job posting |
| Offer acceptance rate | Single metric + trend | Percentage + change arrow |
| Cost-per-hire | Single metric | Average cost across all roles |
| Hiring velocity | Heatmap | Day-of-week / month patterns |

---

## 7. Admin Dashboard

### 7.1 Layout & Navigation

```
┌──────────────────────────────────────────────────────────┐
│ GSP ADMIN                  [🔔] [Avatar ▼]               │
├──────┬───────────────────────────────────────────────────┤
│      │                                                     │
│ 📊   │  Dashboard Overview                                 │
│ 👥   │                                                     │
│ 💼   │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────┐ │
│ 🧑   │  │Total     │ │Active    │ │Registered│ │Active│ │
│ 🔗   │  │Users     │ │Jobs      │ │Candidates│ │Clients│ │
│ 📝   │  │342       │ │28        │ │210       │ │18    │ │
│ 📈   │  │↑12%     │ │↑5%       │ │↑18%     │ │=     │ │
│ ⚙️   │  └──────────┘ └──────────┘ └──────────┘ └──────┘ │
│ 📋   │                                                     │
│      │  ┌──────────────────────────────────────────────┐  │
│      │  │ Platform Activity (last 30 days)              │  │
│      │  │ [Line chart — new users, job posts, matches]  │  │
│      │  └──────────────────────────────────────────────┘  │
│      │                                                     │
│      │  ┌─────────────┐  ┌────────────────────────────┐  │
│      │  │ Recent      │  │ Recent Registrations        │  │
│      │  │ Placements  │  │ Marijn Jansen — Candidate   │  │
│      │  │ 3 this week │  │ Sophie K.   — Candidate    │  │
│      │  └─────────────┘  │ ASML BV     — Client        │  │
│      │                    └────────────────────────────┘  │
│      │                                                     │
└──────┴───────────────────────────────────────────────────┘
```

### 7.2 Admin Sections

| Section | Key Features |
|---|---|
| **Dashboard** | KPIs, activity chart, recent placements, pending actions |
| **Users** | Table of all users (candidate, client, admin). Filter by role, status. Actions: verify, suspend, delete, impersonate |
| **Jobs** | All cross-client jobs. Filter by client, status, date. Bulk actions. |
| **Candidates** | All registered candidates. Full profile view, match simulation, manual matching |
| **Matching Engine** | AI match rules, threshold settings, manual override, match quality review |
| **Content CMS** | Blog editor (Markdown/WYSIWYG), page builder, salary data editor, case study CRUD, testimonial CRUD |
| **Analytics** | Platform-wide: user growth, job fill rate, client retention, candidate satisfaction, revenue tracking |
| **Settings** | SMTP config, API keys, OAuth providers, feature flags, terms/legal versions, email templates |
| **Audit Log** | All admin actions with timestamp, actor, resource, action, IP address |

### 7.3 Content Management System (CMS)

The CMS powers all dynamic text content on the public site:

**Content Types:**
- `blog_article` — title, slug, author, publish date, body (markdown), tags, featured image, SEO meta
- `page_section` — key-value pairs for hero text, section headers, CTAs (used for A/B testing)
- `salary_data` — role, level, min/max salary, source, last updated
- `case_study` — company, role tag, timeline, description, result metric, featured
- `testimonial` — author name, role, company, quote, avatar, rating, featured
- `faq` — question, answer, category, sort order

### 7.4 Admin User Management

```
┌──────────────────────────────────────────────────────────┐
│  User Management                    [+ Add User]         │
│  [Search by name, email...] [Filter ▼]                   │
├──────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────┐  │
│  │ Name            │ Email           │ Role     │ Status│  │
│  ├────────────────────────────────────────────────────┤  │
│  │ Gijs vd Berg    │ gijs@gsptalent  │ admin    │ ●    │  │
│  │ Marijn Jansen   │ marijn@...      │ candidate│ ●    │  │
│  │ Sophie Klaassen │ sophie@...      │ candidate│ ●    │  │
│  │ HR ASML         │ hr@asml.com     │ client   │ ●    │  │
│  │ ...             │                 │          │      │  │
│  └────────────────────────────────────────────────────┘  │
│  < 1 2 3 ... 12 >                                        │
│                                                          │
│  Click row to expand:                                    │
│  ┌────────────────────────────────────────────────────┐  │
│  │ User Detail                                        │  │
│  │ Profile | Activity | Jobs | Messages | Notes       │  │
│  │ [Suspend] [Verify Email] [Impersonate] [Delete]    │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

---

## 8. Component Library

### 8.1 Shared UI Components

All components follow the GOLD + Navy design system. These are the reusable building blocks.

| Component | Variants | States |
|---|---|---|
| **Button** | Primary (gold), Secondary (outline), Ghost, Danger, Icon-only | Default, Hover, Active, Disabled, Loading |
| **Input** | Text, Email, Password, Number, Search, Phone | Default, Focus, Error, Disabled, Read-only |
| **Select** | Single, Multi-tag, Country, Level | Default, Focus, Error, Disabled |
| **Textarea** | Small (3 rows), Medium (6 rows), Large (12 rows) | Default, Focus, Error |
| **Badge / Tag** | Role, Level, Status, Skill, Match-score | Gold, Blue, Green, Amber, Red, Gray |
| **Card** | Default, Hoverable, Selected, Detail | Static, Hover (translateY -4px), Active |
| **Modal** | Small (400px), Medium (600px), Large (800px), Full-screen | Open (backdrop + slide-up), Closing (fade-out) |
| **Toast** | Success, Error, Warning, Info | Enter (slide-in), Visible, Exit (slide-out) |
| **Tooltip** | Top, Bottom, Left, Right | Hidden, Visible on hover |
| **Pagination** | Numbered, Prev/Next, Load-more | Active page, Disabled edge |
| **Spinner** | Small (16px), Medium (24px), Large (40px) | Spinning |
| **Progress bar** | Determinate, Indeterminate, With label | Empty → Percent → Complete |
| **Tabs** | Horizontal, Vertical, Pill-style, Underline | Active, Hover, Disabled |
| **Accordion** | Single-expand, Multi-expand | Collapsed, Expanded |
| **Avatar** | Initials (small/med/large), Image, Badged | Default, Online, Away |
| **Skeleton** | Text, Card, Table, Avatar | Shimmer animation |
| **Empty state** | Icon + Title + Description + CTA | Static |
| **Table** | Sortable, Filterable, Selectable, Responsive | Header, Row hover, Selected row |
| **File upload** | Single, Multiple, Drag-drop, With preview | Empty, Selected, Uploading, Error, Complete |
| **Rich text editor** | Toolbar: bold/italic/h2/h3/list/link | Default, Focus |
| **Chart** | Bar, Line, Donut, Funnel, Heatmap | Responsive, Animated |

### 8.2 Component Design Patterns (Gold/Navy Theming)

**Primary Button Example:**
```css
.btn-gold {
  background: linear-gradient(135deg, var(--gold-500), var(--gold-600));
  color: var(--navy-900);              /* dark text on gold bg */
  border: 2px solid var(--gold-500);
  box-shadow: 0 4px 15px var(--gold-glow);
}
.btn-gold:hover {
  background: linear-gradient(135deg, var(--gold-400), var(--gold-500));
  box-shadow: 0 6px 25px var(--gold-glow);
  transform: translateY(-2px);
}
.btn-gold:active {
  background: var(--gold-600);
  box-shadow: 0 2px 8px var(--gold-glow);
  transform: translateY(0);
}
.btn-gold:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}
```

**Card Pattern (Dashboard):**
```css
.dashboard-card {
  background: linear-gradient(145deg, var(--navy-700), var(--navy-800));
  border: 1px solid rgba(74, 111, 159, 0.15);
  border-radius: var(--radius-xl);
  padding: var(--space-xl);
  transition: all var(--transition-base);
}
.dashboard-card:hover {
  border-color: rgba(250, 200, 0, 0.2);
  box-shadow: 0 8px 30px rgba(6, 13, 26, 0.3);
}
```

### 8.3 Responsive Breakpoints

| Breakpoint | Name | Layout |
|---|---|---|
| < 480px | Mobile S | Single column, stacked navigation, small cards |
| 480–767px | Mobile L | Single column, larger tap targets |
| 768–1023px | Tablet | 2-column grids, sidebar hidden (hamburger) |
| 1024–1279px | Desktop | Full layout, sidebar visible |
| 1280px+ | Wide | Max-width container, extra whitespace |

---

## 9. UX Flow Diagrams

### 9.1 Public Visitor → Candidate Conversion

```
PUBLIC VISITOR
    │
    ├──→ Browses landing page
    │       │
    │       ├──→ Clicks "Free Salary Guide"
    │       │       │
    │       │       └──→ REGISTRATION MODAL (Step 1)
    │       │               │
    │       │               ├──→ Provides email + password
    │       │               │       │
    │       │               │       └──→ Step 2: Profile (name, role, specialisation)
    │       │               │               │
    │       │               │               └──→ Step 3: Preferences (salary, contract)
    │       │               │                       │
    │       │               │                       └──→ Redirect to salary guide PDF
    │       │               │                               │
    │       │               │                               └──→ CANDIDATE DASHBOARD
    │       │               │
    │       │               └──→ Cancels → Returns to page
    │       │
    │       ├──→ Clicks "Get in touch"
    │       │       │
    │       │       └──→ Scrolls to contact form
    │       │
    │       ├──→ Clicks "Start the conversation" (CTA)
    │       │       │
    │       │       └──→ Scrolls to contact form
    │       │
    │       └──→ Clicks "Candidate" in nav
    │               │
    │               └──→ /for-candidates page
    │                       │
    │                       └──→ "Register" CTA → REGISTRATION MODAL
    │
    └──→ Directly navigates to /auth/login or /auth/register
            │
            └──→ AUTH FLOW
```

### 9.2 Client User Journey

```
CLIENT VISITOR
    │
    ├──→ Browses landing page
    │       │
    │       ├──→ Clicks "I need talent" or "For Clients"
    │       │       │
    │       │       └──→ /for-clients page
    │       │               │
    │       │               └──→ "Get started" → REGISTRATION MODAL (client flow)
    │       │                       │
    │       │                       ├──→ Account + company info
    │       │                       │       │
    │       │                       │       └──→ Hiring needs → DASHBOARD
    │       │                       │
    │       │                       └──→ Cancels → Returns to page
    │       │
    │       └──→ Clicks "Book a call" → Contact form with "hiring" interest
    │
    └──→ Already a client → /auth/login → CLIENT DASHBOARD
            │
            ├──→ "Post a job" → JOB FORM → Publish
            ├──→ "Find candidates" → SEARCH → View → Add to pipeline
            ├──→ "View pipeline" → PIPELINE KANBAN → Drag candidates
            └──→ "Analytics" → CHARTS + REPORTS
```

### 9.3 Admin Daily Workflow

```
ADMIN LOGIN → ADMIN DASHBOARD
    │
    ├──→ Review pending registrations
    │       │
    │       └──→ Approve / Reject / Verify
    │
    ├──→ Review flagged job postings
    │       │
    │       └──→ Approve / Request edits / Reject
    │
    ├──→ Review AI match quality
    │       │
    │       └──→ Adjust threshold / Manual override
    │
    ├──→ Update salary data in CMS
    │       │
    │       └──→ Form → Preview → Publish
    │
    ├──→ Write/publish blog article
    │       │
    │       └──→ Editor → Schedule → Publish
    │
    └──→ Check audit log for suspicious activity
```

### 9.4 Application Lifecycle

```
CANDIDATE APPLIES
    │
    ▼
STATUS: Applied (blue)
    │
    ▼
GSP reviews (┐
    │         ├── Auto-match AI screening
    │         └── Manual GSP screening
    ▼
STATUS: Screening (amber)
    │
    ├──→ Candidate no-show / decline → STATUS: Withdrawn (gray)
    │
    ▼
STATUS: Interview (blue)
    │
    ├──→ Multiple rounds
    │
    ▼
STATUS: Offer (green)
    │
    ├──→ Candidate accepts → STATUS: Accepted (green)
    │
    ├──→ Candidate declines → STATUS: Declined (red)
    │
    └──→ Offer expires → STATUS: Expired (gray)
```

---

## 10. API Data Model

### 10.1 Core Entities

```typescript
// ============= USER =============
interface User {
  id: UUID;
  email: string;
  passwordHash: string;
  role: 'candidate' | 'client' | 'client_admin' | 'admin';
  status: 'pending' | 'active' | 'suspended' | 'deleted';
  emailVerified: boolean;
  authProvider: 'email' | 'google' | 'linkedin';
  createdAt: timestamp;
  lastLoginAt: timestamp;
  preferences: UserPreferences;
}

// ============= CANDIDATE =============
interface Candidate extends User {
  role: 'candidate';
  profile: CandidateProfile;
  cvUrl?: string;
  parsedSkills: string[];
  salaryExpectations: SalaryRange;
  availability: 'immediate' | '1month' | '3months' | 'negotiable';
  workAuthorization: 'eu_citizen' | 'work_visa' | 'other';
  preferredContract: 'permanent' | 'contract' | 'both';
  preferredWorkType: 'on_site' | 'hybrid' | 'remote';
  noticePeriod: string;
  // AI-generated
  matchScore?: number;          // computed per job
  profileCompleteness: number;  // 0-100%
}

interface CandidateProfile {
  fullName: string;
  headline: string;              // e.g. "Senior Embedded C++ Engineer"
  summary: string;               // multi-line bio
  phone?: string;
  location: string;
  photoUrl?: string;
  experience: Experience[];
  education: Education[];
  skills: Skill[];
  languages: Language[];
  certifications: string[];
  linkedinUrl?: string;
  githubUrl?: string;
  portfolioUrl?: string;
}

interface Experience {
  company: string;
  title: string;
  startDate: string;
  endDate?: string;              // null = current
  description: string;
  skillsUsed: string[];
}

interface Education {
  institution: string;
  degree: string;
  field: string;
  startYear: number;
  endYear: number;
}

interface Skill {
  name: string;
  category: 'programming_language' | 'framework' | 'tool' | 'domain' | 'soft_skill';
  proficiency: 'beginner' | 'intermediate' | 'advanced' | 'expert';
  yearsExperience: number;
}

// ============= CLIENT =============
interface Client extends User {
  role: 'client' | 'client_admin';
  company: Company;
  teamMembers?: ClientTeamMember[];
}

interface Company {
  name: string;
  logo?: string;
  website: string;
  industry: string;
  location: string;              // Brainport city
  size: '1-10' | '11-50' | '51-200' | '201-1000' | '1000+';
  description: string;
  techStack: string[];           // ["C++", "Python", "Qt", "Linux"]
}

// ============= JOB =============
interface Job {
  id: UUID;
  clientId: UUID;
  title: string;
  specialisation: Specialisation;
  level: 'junior' | 'mid' | 'senior' | 'lead' | 'architect';
  location: string;
  workType: 'on_site' | 'hybrid' | 'remote';
  contractType: 'permanent' | 'contract' | 'both';
  salaryMin: number;
  salaryMax: number;
  currency: 'EUR';
  bonusRange?: string;           // "0-30%"
  description: string;           // rich text / markdown
  responsibilities: string;
  requirements: string;
  benefits: string;
  requiredSkills: string[];
  niceToHaveSkills: string[];
  experienceYearsMin: number;
  experienceYearsMax?: number;
  status: 'draft' | 'published' | 'paused' | 'filled' | 'expired' | 'archived';
  visibility: 'public' | 'private' | 'gsp_only';
  createdAt: timestamp;
  expiresAt: timestamp;
  filledAt?: timestamp;
  viewCount: number;
  applicationCount: number;
}

type Specialisation = 'embedded' | 'cpp_software' | 'mechatronics' | 'cybersecurity' | 'fpga' | 'motion_control';

// ============= APPLICATION =============
interface Application {
  id: UUID;
  jobId: UUID;
  candidateId: UUID;
  status: 'applied' | 'screening' | 'interview' | 'offer' | 'accepted' | 'declined' | 'withdrawn';
  matchScore: number;            // 0-100% AI score at time of application
  appliedAt: timestamp;
  updatedAt: timestamp;
  notes?: string;                // GSP internal notes
  interviews?: Interview[];
  offerDetails?: OfferDetails;
}

// ============= MATCH =============
interface Match {
  id: UUID;
  jobId: UUID;
  candidateId: UUID;
  score: number;                 // 0-100%
  breakdown: MatchBreakdown;     // skill match, experience, location, salary
  createdBy: 'ai' | 'admin' | 'client';
  status: 'pending' | 'viewed' | 'shortlisted' | 'rejected';
  createdAt: timestamp;
}

interface MatchBreakdown {
  skillMatch: number;            // 0-100%
  experienceMatch: number;
  locationMatch: number;
  salaryFit: number;
  levelFit: number;
}

// ============= MESSAGE =============
interface Message {
  id: UUID;
  senderId: UUID;
  recipientId: UUID;
  relatedEntityId?: UUID;        // jobId, applicationId, etc.
  subject: string;
  body: string;
  readAt?: timestamp;
  createdAt: timestamp;
  type: 'direct' | 'system' | 'notification';
}

// ============= SALARY DATA =============
interface SalaryDatum {
  id: UUID;
  specialisation: Specialisation;
  level: string;
  percentile25: number;
  percentile50: number;
  percentile75: number;
  percentile90: number;
  currency: 'EUR';
  region: 'brainport' | 'netherlands' | 'remote';
  source: string;
  sampleSize: number;
  lastUpdated: timestamp;
}
```

### 10.2 API Endpoints (RESTful, versioned)

```
PUBLIC
  GET  /api/v1/public/site-content?section=hero    → SiteContent
  GET  /api/v1/public/salary-data?role=&level=     → SalaryDatum[]
  POST /api/v1/public/lead                         → { success }
  POST /api/v1/public/contact                      → { success }

AUTH
  POST /api/v1/auth/register                       → { user, token }
  POST /api/v1/auth/login                          → { user, token }
  POST /api/v1/auth/oauth                          → { user, token }
  POST /api/v1/auth/refresh                        → { token }
  POST /api/v1/auth/reset-password                 → { success }
  POST /api/v1/auth/verify-email                   → { success }

CANDIDATE
  GET  /api/v1/candidate/profile                   → Candidate
  PUT  /api/v1/candidate/profile                   → Candidate
  POST /api/v1/candidate/cv                        → { cvUrl }
  GET  /api/v1/candidate/matches?page=&limit=      → Match[]
  GET  /api/v1/candidate/applications              → Application[]
  POST /api/v1/candidate/applications              → Application
  GET  /api/v1/candidate/saved-jobs                → SavedJob[]
  POST /api/v1/candidate/saved-jobs                → SavedJob
  GET  /api/v1/candidate/messages                  → Message[]
  GET  /api/v1/candidate/salary-benchmark          → SalaryDatum

CLIENT
  GET  /api/v1/client/jobs                         → Job[]
  POST /api/v1/client/jobs                         → Job
  GET  /api/v1/client/jobs/:id                     → Job
  PUT  /api/v1/client/jobs/:id                     → Job
  DELETE  /api/v1/client/jobs/:id                  → { success }
  GET  /api/v1/client/candidates?filters           → Candidate[]
  GET  /api/v1/client/candidates/:id               → Candidate
  POST /api/v1/client/pipeline                     → PipelineEntry
  GET  /api/v1/client/pipeline                     → PipelineEntry[]
  GET  /api/v1/client/analytics                    → Analytics
  GET  /api/v1/client/messages                     → Message[]
  GET  /api/v1/client/team                         → TeamMember[]
  POST /api/v1/client/team                         → TeamMember

ADMIN
  GET  /api/v1/admin/users                         → User[]
  GET  /api/v1/admin/users/:id                     → User
  PUT  /api/v1/admin/users/:id                     → User
  DELETE  /api/v1/admin/users/:id                  → { success }
  POST /api/v1/admin/users/:id/impersonate         → { token }
  GET  /api/v1/admin/jobs                          → Job[]
  PUT  /api/v1/admin/jobs/:id                      → Job
  GET  /api/v1/admin/candidates                    → Candidate[]
  GET  /api/v1/admin/analytics                     → Analytics
  GET  /api/v1/admin/audit-log                     → LogEntry[]
  GET  /api/v1/admin/content                       → Content[]
  PUT  /api/v1/admin/content/:id                   → Content
  GET  /api/v1/admin/settings                      → Settings
  PUT  /api/v1/admin/settings                      → Settings
```

---

## 11. Implementation Roadmap

### Phase 1 — Foundation (Weeks 1–3)

| Task | Deliverables |
|---|---|
| Rebrand orange → gold in existing codebase | Updated CSS variables, button classes, gradient tokens |
| Setup project structure | Monorepo: `/web` (SvelteKit/Next.js), `/api` (FastAPI/NestJS), `/admin` (separate SPA) |
| Core component library | 20 base components (Button, Input, Card, Modal, Toast, etc.) |
| Auth system | JWT + refresh tokens, Google/LinkedIn OAuth, email verification flow |
| Registration modal | Multi-step flow (candidate & client) |
| Responsive layout shell | Dashboard sidebar, header, grid system |

### Phase 2 — Portals (Weeks 4–7)

| Task | Deliverables |
|---|---|
| Candidate Dashboard | Profile page, settings, notification preferences |
| Market Value Compass | Interactive salary tool with Chart.js visualisation, PDF export |
| Job Matches | Match list, filter/sort, detail view, apply flow |
| Application History | Status tracking with pipeline visualisation |
| Client Dashboard | Job management, candidate search, pipeline kanban |
| Analytics (client) | Charts, exportable reports, trend data |

### Phase 3 — Admin & Intelligence (Weeks 8–10)

| Task | Deliverables |
|---|---|
| Admin Dashboard | All KPI widgets, activity feed, system health |
| User Management | CRUD, verification, suspend, impersonate |
| CMS | Blog editor, page content management, salary data editor |
| AI Matching Engine | Skill parsing, scoring algorithm, match breakdown UI |
| Audit Log | Full event logging with search and export |
| Platform Analytics | User growth, job trends, revenue metrics, retention |

### Phase 4 — Polish & Launch (Weeks 11–12)

| Task | Deliverables |
|---|---|
| SEO audit + JSON-LD | Structured data for all public pages |
| PWA support | Service worker, manifest, offline fallback |
| i18n audit | Complete EN/NL coverage across all portals |
| Performance optimisation | LCP < 2s, CLS < 0.1, bundle splitting |
| Security audit | OWASP Top 10, rate limiting, CSRF, XSS |
| Documentation | README, API docs (OpenAPI), deployment guide |

---

## Appendix A: Key UX Principles

1. **Dark-first**: Every interface is designed dark-mode-first. Light mode is not supported.
2. **Gold highlights, never floods**: Gold is used sparingly — CTAs, active states, match scores, and data highlights. Never as a background fill.
3. **Data density scales with role**: Candidates see simple, warm cards. Clients see richer data tables. Admins get maximum density.
4. **Progressive disclosure**: Dashboards show summary cards first; drill-down is one click away. Never overwhelm on first load.
5. **Optimistic UI**: Form submissions show instant feedback before server confirms. Errors are non-destructive.
6. **Keyboard accessibility**: All portal features work without a mouse. Tab order, aria labels, focus management.
7. **Zero cold outreach promise**: The warm introduction ethos is reflected in every touchpoint — no aggressive popups, no spam.

## Appendix B: Existing Code Migration Requirements

When upgrading the current `index.html` / `styles.css` / `script.js`:

| File | Required Changes |
|---|---|
| `styles.css` | Replace all `--orange-*` tokens with `--gold-*` tokens (see §1.2). Update `.btn-primary`, `.section-label`, `.hero h1 .highlight`, `.nav-link::after`, `.lang-btn.active`, `.hero-badge`, `.service-icon`, `.service-card::before` etc. |
| `styles.css` | Add dashboard/portal layout styles (sidebar, kanban, metric cards, data tables, charts) |
| `index.html` | Add auth modal markup, dashboard page templates, client portal templates |
| `script.js` | Add dashboard interactivity (drag-drop pipeline, chart rendering, match score display), registration modal logic (multi-step wizard), client-side routing for portal pages |

---

*End of Design Specification — GSP Recruitment Enterprise Site Architecture*
