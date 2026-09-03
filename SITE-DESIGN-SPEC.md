# GSP Recruitment: Complete Site Design Specification

> **Brand**: GSP Recruitment, faceless agency voice ("wij", never a founder name)
> **Tagline**: Tech & IT-recruitment specialist, Brainport Eindhoven
> **Region**: Brainport Eindhoven (High-Tech Corridor, Netherlands)
> **Audience**: Embedded, C++, mechatronics, OT-cybersecurity engineers and the testing roles around them; Dutch tech employers
> **Status**: As-built (WS-F.9, frozen to what runs on `main`)

---

## Table of Contents

1. [Brand & Color System](#1-brand--color-system)
2. [Information Architecture](#2-information-architecture)
3. [Public Site](#3-public-site)
4. [Registration & Auth](#4-registration--auth)
5. [Candidate Portal](#5-candidate-portal)
6. [Client Portal](#6-client-portal)
7. [Admin Panel](#7-admin-panel)
8. [Component Library](#8-component-library)
9. [Not-yet-built items](#9-not-yet-built-items)

This document describes the design system and pages as implemented in `website/`. Items that go past that implementation are named in §9 with a pointer, not described here as if they existed: the full list and its status lives in `ENTERPRISE-ARCHITECTURE-SPEC.md`, Appendix A.

---

## 1. Brand & Color System

### 1.1 Brand Identity

| Element | Value |
|---|---|
| Agency name | GSP Recruitment |
| Voice | Faceless, "wij", never a founder name or photo; NRC/FD register: plain, direct, zero hype |
| Languages | Dutch (primary), English toggle |
| Logo | Golden yellow "G" icon on dark bg; full wordmark "GSP Recruitment" |

### 1.2 Color Palette

#### Primary: Navy Dark (`colors_navy_dark`)
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

#### Accent: GOLD (`colors_gold`)
```
--gold-500:  #FAC800     (primary accent, the single primary CTA per page, active nav underline, eyebrows, arrows)
--gold-400:  #FBD74A     (hover, lighter accents)
--gold-300:  #FCE488     (subtle backgrounds, badges)
--gold-600:  #D4A800     (eyebrow/link text on light backgrounds, active/pressed states)
--gold-700:  #AD8800     (deep accent, decorative borders)
--gold-glow: rgba(250, 200, 0, 0.28)  (glow/shadow tokens)
```

> **Rule**: gold is reserved for the single primary action per page plus small accents (eyebrows, the active nav underline, arrows/chevrons). It is never used as a background fill for cards, sections, or secondary buttons; those stay navy-on-white or outline/ghost.

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

Three-family system, loaded via Google Fonts (`Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600` + `IBM+Plex+Sans:wght@400;500;600` + `IBM+Plex+Mono:wght@400;500`):

| Token | Value | Usage |
|---|---|---|
| Display / serif | `'Newsreader', Georgia, 'Times New Roman', serif` | All headings (h1–h3), hero headlines, werkwijze step numerals, portal greetings. Weight 500 (600 for the wordmark only). |
| Body / UI | `'IBM Plex Sans', 'Segoe UI', system-ui, -apple-system, sans-serif` | Body copy, nav, buttons, form fields. |
| Monospace | `'IBM Plex Mono', ui-monospace, 'SF Mono', Menlo, monospace` | Eyebrows (uppercase, letter-spacing 0.12–0.14em), salary figures, mono chips/pill tags (Hybride, Senior, location), KPI numerals, timestamps. |
| `--font-size-xs` | 0.75rem (12px) | Captions, metadata |
| `--font-size-sm` | 0.875rem (14px) | Body small, nav items |
| `--font-size-base` | 1rem (16px) | Body text |
| `--font-size-lg` | 1.125rem (18px) | Lead paragraphs |
| `--font-size-xl` | 1.25rem (20px) | Card titles |
| `--font-size-2xl` | 1.5rem (24px) | Section subtitles |
| `--font-size-3xl` | 2rem (32px) | Section headings |
| `--font-size-4xl` | 2.5rem (40px) | Page headings |
| `--font-size-5xl` | 3.25rem (52px) | Hero headline |
| `--font-size-6xl` | 4rem (64px) | Dashboard hero stats |

Radius: flat 3px on buttons and cards site-wide (`--radius`/`--radius-sm`/`--radius-xs: 3px`); `--radius-full` (999px) is reserved for pill chips/badges only.

### 1.4 Spacing System

Based on a 4px grid: `--space-xs: 4px, --space-sm: 8px, --space-md: 16px, --space-lg: 24px, --space-xl: 32px, --space-2xl: 48px, --space-3xl: 64px, --space-4xl: 96px, --space-5xl: 128px`.

---

## 2. Information Architecture

`website/` is served as static files by Cloudflare Workers Static Assets (see `ENTERPRISE-ARCHITECTURE-SPEC.md` §5). There is no build step and no client-side router library; the four surfaces below are each their own set of files, and the three portal-like surfaces navigate between sections with `window.location.hash` inside a single HTML page rather than separate URLs per section.

### 2.1 Site map (as-built)

```
gsprecruitment.nl/
│
├── PUBLIC SITE (multi-page, static HTML)
│   ├── /                     index.html      Landing page
│   ├── /werkgevers.html                      Client-facing landing, service lines (§3.5)
│   ├── /kandidaten.html                      Candidate-facing landing + registration split
│   ├── /werkwijze.html                       How-we-work steps
│   ├── /over-ons.html                        About ("wij", no founder bio)
│   ├── /contact.html
│   ├── /vacature.html, /vacatures             Job listing + detail (pulled from /api/public/jobs)
│   ├── /blog/*                               Blog articles (pulled from /api/v1/public/blog)
│   ├── /privacy.html, /cookies.html, /terms.html
│   └── /404.html
│
├── CANDIDATE PORTAL (authenticated, single page, hash-routed)
│   └── /candidate/            #dashboard #profile #salary #matches #applications #messages #settings
│
├── CLIENT PORTAL (authenticated, single page, hash-routed)
│   └── /client/               #dashboard #jobs #candidates #analytics #team #settings
│
└── ADMIN PANEL (authenticated, single page, hash-routed, vendored Tabler 1.4)
    └── /admin/                #dashboard #users #candidates #jobs #outreach #blog #analytics #audit #cms #settings
```

The API (`api.gsprecruitment.nl`) is a separate origin, described in `ENTERPRISE-ARCHITECTURE-SPEC.md`.

### 2.2 Auth model

| Role | Portal | As-built |
|---|---|---|
| anonymous | Public site | Browse, submit contact/lead forms |
| `candidate` | Candidate Portal | Profile CRUD, salary explorer, job matches, applications, messages |
| `client` | Client Portal | Job CRUD, candidate search, messages |
| `admin` | Admin Panel | Full backend access, MFA-gated (see `ENTERPRISE-ARCHITECTURE-SPEC.md` §3.2) |

Auth is JWT-based (email/password or Google sign-in). There is no `client_admin` sub-role, no session-length distinction beyond the JWT's own expiry, and no LinkedIn OAuth login today (a LinkedIn button exists in the registration UI with no backend flow behind it, see §4).

---

## 3. Public Site

### 3.1 Current State

`index.html` is a complete single-page landing (as of the August 2026 Newsreader/Plex redesign):
- Fixed dark-navy header with nav, audience quick-switch, and language toggle (EN/NL)
- Dark hero (`.page-hero`) with mono eyebrow, serif headline, two audience "choice cards" (gold/navy top border), trust strip, thin concentric-circle decoration
- Ecosystem/partner logo strip (mono pill badges)
- Expertise grid (8-card, flat bordered cards, gold line-icons)
- Live vacancies preview (mono chips + salary, pulled from `/api/public/jobs`)
- Werkwijze: numbered steps (bold navy serif numerals with a short gold underline accent, over a navy top rule, on a dedicated off-white `#process` band distinct from the sections around it), 5 steps, not the 4 shown in earlier mockup artboards. Same numeral/underline treatment on the standalone `werkwijze.html` page's step list (`.step-num`). Revised August 2026: the original gold-ochre numerals (`#8A6800`, AA-passing at 4.7:1 but visually faint per owner feedback) were replaced with navy (`#0A1628`, ~17–18:1) plus a decorative 3px gold underline; `.section-label` eyebrows went from weight 500 to 700 sitewide for the same reason.
- Case studies, "commitments" trust badges, dark CTA band, 4-column footer
- No founder bio anywhere on the site; the "About us" page speaks as "wij"

### 3.2 Redesign status (August 2026)

The visual system described in §1.2–§1.3 (Newsreader/Plex fonts, flat 3px radius, gold reserved for the primary CTA) is implemented across the homepage, vacatures/vacature, kandidaten (signup split), the candidate portal, and, as a font/token pass on top of vendored Tabler, the admin panel. Not yet built (no invented ship dates): animated hero particles/counters, an interactive salary chart component (the salary table is still static HTML), a true auto-rotating testimonial carousel, expandable case-study modals, a multi-route contact form, and PWA/service-worker support (the last of those is also listed in §9, since it's part of the shared "not before 3 billable seats" list).

### 3.3 Not-yet-built page sections (backlog, no ship date)

These are drafted UI ideas for the public site, not built and not scheduled: a blog preview strip on the homepage, a partner/client logo trust bar, and an FAQ accordion before the closing CTA. None of them require anything beyond the current static-HTML stack; they're ordinary content backlog, not architecture work, so they stay here rather than in the appendix.

### 3.4 Page template

Every content page (`werkgevers.html`, `kandidaten.html`, `werkwijze.html`, blog articles, etc.) shares the same shell: fixed header, a page hero (H1 + subtitle + optional CTA), page-specific content sections, a shared CTA strip, and the 4-column footer, via the common `.header`/`.page-hero`/`.footer` CSS classes in `styles.css`.

### 3.5 Service lines

`werkgevers.html#diensten` presents five generic service lines as plain descriptions, in the `.service-ladder-grid` (a `.prop`/`.prop-icon` card grid, 3+2 balanced so no card sits alone on a row at desktop or tablet widths, see `.service-ladder-grid` in `styles.css`): **werving & selectie** (permanent hire, client is the employer, we handle search and screening), **interim** (temporary specialist, same split), **uitzenden** (staffing, engineer employed by a backoffice partner, works under the client's day-to-day direction, flexible term), **detacheren** (fixed-term secondment, same employment split as uitzenden, but for a pre-agreed, more structural term), and **zzp-bemiddeling** (freelance placement, we introduce an independent professional, the client contracts them directly; the assignment must be suitable for independent work under the Wet DBA). `kandidaten.html` mirrors this from the engineer's side ("Hoe je bij ons aan de slag kunt"), and `werkwijze.html` step 2 ("Contractvorm kiezen") states the form is agreed before the search starts. None of the copy names a partner, states a tariff, factor or margin, or promises IND sponsorship, a processing time, or the 30%-ruling; GSP is not an IND-recognised sponsor itself (see `CLAUDE.md`) and adds partner-specific terms only once a partner offer is signed.

### 3.6 SEO: sitemap, canonical URLs, hreflang (WS-A.7)

The site is one bilingual page set per URL (`.lang-nl`/`.lang-en` spans toggled client-side by `gsp-util.js`, language stored in `localStorage`, no `?lang=`/`/en/` URLs) — there is no separate URL per language, so `<link rel="alternate" hreflang="...">` tags do not describe anything real and have been **removed sitewide**. If the site ever grows real per-language URLs, hreflang can come back then, not before.

Every page's `<link rel="canonical">`, `<meta property="og:url">`, and any JSON-LD `"url"`/`"target"` field are **extension-less** and consistent with each other (`https://gsprecruitment.nl/werkgevers`, never `.../werkgevers.html`) — Cloudflare Workers Static Assets serves both forms, but only the extension-less form is ever advertised to crawlers/social previews. `blog/post.html` and `vacature.html` build their canonical/og:url from `window.location` (or the API slug/id) at runtime since the same file serves every slug; `blog-post.js` also sets `<title>` and the JSON-LD `headline` from the post title in the viewer's *active* language (`localStorage.gsp_lang`), not a hardcoded language.

`website/sitemap.xml` is generated, not hand-maintained: `scripts/generate_sitemap.py` builds it from (1) the static page list (extension-less URLs, `lastmod` from `git log`, falling back to file mtime), (2) live vacatures from `GET /api/public/jobs` → `/vacature?id=<id>`, and (3) blog posts from `website/blog/posts.json` (falling back to `GET /api/v1/public/blog` if that file is ever removed). A jobs/blog API failure logs a warning and falls back to the static list — it never breaks the build. `.github/workflows/deploy.yml` regenerates and, if changed, commits `website/sitemap.xml` straight to `main` on every deploy (before the Cloudflare Pages auto-deploy step), so it can't drift from the live job/blog list. `robots.txt` points at `https://gsprecruitment.nl/sitemap.xml`.

---

## 4. Registration & Auth

Registration is a single modal launched from `kandidaten.html`'s signup split or the header CTA, backed by `POST /api/auth/register`; login is a matching modal backed by `POST /api/auth/login`. Both offer a Google sign-in button wired to `/api/auth/google/login` (see `ENTERPRISE-ARCHITECTURE-SPEC.md` §3.1) and a LinkedIn button that is not wired to anything yet.

Fields collected at registration: email, password, role (candidate/client), and for candidates the profile basics used elsewhere in this doc (name, current role, specialisation, CV upload, salary/preferences). There is no separate multi-step wizard with its own onboarding-confirmation screen; the form posts once and the account lands on its portal dashboard. New accounts require email verification (`ENTERPRISE-ARCHITECTURE-SPEC.md` §3.1) before the dashboard's data-fetching calls run.

### Component states

| State | Visual |
|---|---|
| Default | Clean form, all fields empty |
| Loading | Button shows spinner, fields disabled, backdrop remains |
| Validation error | Field border turns red, error message below field |
| Server error | Toast notification at top of modal |
| Success | Redirect to the relevant portal dashboard |
| Rate-limited | "Too many attempts. Please try again in X minutes." (backed by the shared rate limiter, `ENTERPRISE-ARCHITECTURE-SPEC.md` §3.1) |

---

## 5. Candidate Portal

Single page (`website/candidate/index.html` + `app.js`), hash-routed sections, sidebar nav:

| Hash | Section | As-built |
|---|---|---|
| `#dashboard` | Dashboard | Summary cards (matches, messages, saved jobs), top matches list |
| `#profile` | My Profile | Name, role, skills/experience/education/languages, CV upload, preferences |
| `#salary` | Salary Explorer (NL) | Static filterable table by role/level (Embedded, C++, Mechatronics, Cybersecurity, Motion Control), not an interactive chart; see §9 for the planned interactive version |
| `#matches` | My Matches | List of job matches with a numeric match score, sourced from `matches` |
| `#applications` | Applications | Application list with status |
| `#messages` | Messages | Messages from GSP |
| `#settings` | Settings | Preferences, notifications |

Match cards show a "Match NN" mono badge (not a percentage-circle graphic) per the August 2026 redesign (Appendix, below). Status badges on Applications use the semantic colors from §1.2: Applied/Screening/Interview (info/warning/info), Offer/Accepted (success), Declined (error).

---

## 6. Client Portal

Single page (`website/client/index.html` + `app.js`), hash-routed sections, sidebar nav:

| Hash | Section | As-built |
|---|---|---|
| `#dashboard` | Dashboard | Job Management |
| `#jobs` | Vacatures | Job posting list, create/edit |
| `#candidates` | Kandidaten Zoeken | Candidate search against matched/available candidates |
| `#analytics` | Analytics | See §9, not built today |
| `#team` | Team | See §9, not built today |
| `#settings` | Instellingen | Preferences |

The job posting form collects title, specialisation, location, work/contract type, salary range, experience level, required skills, and a description field.

---

## 7. Admin Panel

`website/admin/` is vendored Tabler 1.4, dark navy/gold reskin, hash-routed sidebar sections:

| Hash | Section | As-built |
|---|---|---|
| `#dashboard` | Dashboard | KPI cards, pending-verifications widget, "Nieuwe registraties" widget (top 5 self-registered candidates) |
| `#users` | Users | User list |
| `#candidates` | Candidates | Kind filter (Alle / Zelf geregistreerd / Gesourced), per-row type badge and verified indicator; row click opens full detail via `GET /v1/admin/candidates/{kind}/{item_id}` (contact links, skills/languages chips, salary/notice/relocation/education, CV-uploaded indicator; the CV file itself isn't downloadable from this panel yet) |
| `#jobs` | All Jobs | Cross-client job list, server-side search + status filter, paginated; "Nieuwe vacature" modal lets an admin record a job on a client's behalf (e.g. a phoned-in assignment) without the client needing a portal login |
| `#outreach` | Outreach | Draft review/approve (outreach is always draft-only; a human sends, see `CLAUDE.md`) |
| `#blog` | Blog | Blog post CRUD; publish is a separate, explicit action from save |
| `#analytics` | Analytics | Platform metrics |
| `#audit` | Audit Log | Admin actions with actor, resource, action |
| `#cms` | Content CMS | Currently limited to the Blog section above; a broader page-content/testimonial/case-study CMS is not built (see §9) |
| `#settings` | Settings | System configuration |

There is no `superadmin` role; every admin account sits behind the MFA flow in `ENTERPRISE-ARCHITECTURE-SPEC.md` §3.2. There is an `impersonate` action (Users list) that gives the admin a 15-minute token as the target user and opens their portal; the admin's own token is parked separately (`gsp_admin_token` in `localStorage`, never the normal session slot) for the length of the impersonation. Both the candidate and client portal show a persistent gold-on-navy banner ("Je bekijkt als &lt;rol&gt;. Terug naar admin") while impersonated, with a button that restores the admin session and returns to `#dashboard`.

Empty/error states across the panel use the Dutch "Kon niet laden, probeer opnieuw" retry pattern and "Nog geen …" empty-state copy.

---

## 8. Component Library

Base components used across the four surfaces: Button (primary/ghost/outline, 3px radius), Input, Select, Card, Modal, Toast, Badge (status/semantic colors from §1.2), mono pill chip (role/level/location tags), Sidebar nav item, KPI stat tile, Table (sortable header, empty/error/loading row states), Avatar.

---

## 9. Not-yet-built items

Interactive/architectural features drafted for this design but not implemented, kept here as a pointer rather than duplicated: an interactive, chart-based **Market Value Compass** salary tool (distinct from the static Salary Explorer table in §5) with PDF export, client-portal **Analytics** and **Team** management, a broader page-builder-style **Content CMS** beyond blog posts, and **PWA/service-worker** support. The authoritative list, with status and the "not before 3 billable seats" framing, is `ENTERPRISE-ARCHITECTURE-SPEC.md`, Appendix A: update it there, not here, when priorities change.

---

## Appendix: Design system implementation notes (August 2026)

The Newsreader/Plex redesign is implemented as a token-and-component-class change in the existing files, not a rebuild:

| File | What changed |
|---|---|
| `website/styles.css` | `:root` now carries the full canonical navy scale + gold scale from §1.2, plus `--font`/`--font-display`/`--font-mono` (Plex Sans / Newsreader / Plex Mono). Legacy variable names (`--gold`, `--navy`, `--text`, etc.) are kept as aliases pointing at the new values so most component rules didn't need renaming. `.header`, `.page-hero`, `.choice-card`, `.trust-strip`, `.job-card`, `.vac-card`, `.eco-badge`, `#process .story-card` (werkwijze numerals) were restyled to the artboards; radius tokens flattened to 3px. |
| `website/theme.css` | `--font-primary`/`--font-mono` updated to Plex Sans/Plex Mono, `--font-display` (Newsreader) added, read by the candidate/client portals. |
| `website/kandidaten.html` | Top `.page-hero` replaced with a `.signup-split` two-column layout (dark value-prop panel + light form card) per the Aanmelden artboard; the primary CTA (`#registerBtn`) opens the existing registration modal, no new auth logic. |
| `website/candidate/index.html`, `website/portal.css` | Match-score badges now read "Match NN" in mono instead of a percentage circle; portal header title set to the display serif. Sidebar/gold-active-state styling was already on-brand via `theme.css` tokens. |
| `website/admin/index.html` | Font tokens and the Tabler brand-color override (`--tblr-primary`) updated to the canonical gold; headings and KPI numerals set to serif/mono. The vendored Tabler theme itself was not touched. |
| `website/admin/index.html`, `website/admin/js/admin.js` (August 2026, candidates overhaul) | Candidates section gained the kind filter and detail view described in §7. Dashboard gained the "Nieuwe registraties" widget above Pending Verifications so a same-day portal sign-up is visible without opening Candidates. Empty/error states standardized across the panel. |
| `website/admin/vendor/apexcharts.min.js` (WS-B.2) | ApexCharts 4.7.0 vendored locally (was a bare CDN `<script>` with no fallback); `website/admin/index.html` now loads it from `vendor/`, no CDN entry or SRI needed. No visual change — same pinned version, same chart config in `admin.js`. |
| All other pages (werkgevers, werkwijze, over-ons, contact, blog, privacy, 404, vacature) | No page-specific CSS existed for header/hero/footer; they inherit the new look automatically via the shared `.header`/`.page-hero`/`.eyebrow`/`.footer` classes in `styles.css`. |
| Google Fonts `<link>` (all pages) | Swapped from Inter+Fraunces to `Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600` + `IBM+Plex+Sans:wght@400;500;600` + `IBM+Plex+Mono:wght@400;500`. |
| Logos | Header/preloader now use `logo.png` (light wordmark) everywhere, since the header is dark navy on every page, not `logo-dark.png` (dark wordmark, footer/print use only). |

---

*End of specification.*
