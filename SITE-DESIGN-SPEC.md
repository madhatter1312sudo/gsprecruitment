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
│   ├── /privacy.html, /privacy-kandidaten.html, /cookies.html, /terms.html
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

Auth is JWT-based (email/password or Google sign-in). There is no `client_admin` sub-role, no session-length distinction beyond the JWT's own expiry, and no LinkedIn OAuth login: the LinkedIn button that used to sit next to the Google button in the registration UI has been removed, since it never had a backend flow behind it (see §4).

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

### 3.7 Vacatures met anonieme opdrachtgever (WS4)

Sommige vacatures dienen om de volle breedte van onze disciplines te laten zien zonder een lopende opdracht bij naam te noemen. Zulke vacatures worden herkend aan `anonymous_client` (afgeleid van `clients.is_internal` op de klant achter de vacature, niet van `company_display`) in de `GET /api/public/jobs` en `GET /api/public/jobs/{job_id}` respons.

`vacature.js`'s `buildJobPostingLd()` geeft `null` terug zodra `anonymous_client === true`, en `vacature.html` plaatst dan geen `JobPosting` JSON-LD op de pagina. Een rich-result kaart in Google naast een naamloze werkgever wekt de indruk van een concrete, nu bestaande opdracht, precies het spookvacature-risico (Wet OHP, ABU/NBBU-gedragscode) dat de eigenaar alleen heeft aanvaard onder de voorwaarde dat zulke vacatures geen JobPosting-structured-data krijgen. Vacatures met een genoemde opdrachtgever behouden de volledige JSON-LD zoals voorheen.

De sollicitatieroute wijkt af voor een niet-ingelogde bezoeker: in plaats van door te linken naar het contactformulier (dat om een opdrachtgever vraagt die wij nog niet kunnen noemen) toont de pagina een paneel dat rechtstreeks aanmeldt bij de talentpool (`POST /api/public/talentpool-optin` met `source: 'vacancy_apply'` en de `job_id`), met dubbele opt-in via dezelfde bevestigingsmail en -pagina (`talentpool-confirm.html`) als een gewone talentpool-aanmelding. Een bevestigde aanmelding met een nog open, niet-demo, niet-verwijderde vacaturekoppeling registreert de sollicitatie zelf server-side (ook bij een anonieme vacature: het onderscheid dat telt is of de vacature nog geldig is, niet of de opdrachtgever wordt genoemd); er is dus geen directe, ongemodereerde "solliciteer nu bij <opdrachtgever>"-actie voor een vacature waarvan we de opdrachtgever niet noemen. Een ingelogde kandidaat solliciteert ongewijzigd met één klik, zoals bij elke andere vacature. Boven de sollicitatieknop staat bovendien altijd een korte, vaste regel in beide talen die het anonieme karakter herhaalt, kort en zichtbaar, naast de volledige toelichting die al in de vacaturetekst staat.

---

## 4. Registration & Auth

Registration is a single modal launched from `kandidaten.html`'s signup split or the header CTA, backed by `POST /api/auth/register`; login is a matching modal backed by `POST /api/auth/login`. Both offer a Google sign-in button wired to `GET /api/auth/google/login` (see `ENTERPRISE-ARCHITECTURE-SPEC.md` §3.1); there is no LinkedIn button anymore, it was never wired to anything.

The Google button carries the role the account being created or logged into is for. On the register form the account-type select (`#regRole`, candidate/client) decides it; the login form has no such select, so the role follows the page instead, `werkgevers.html` means client, every other page means candidate. The button sends `role` and a matching `next` portal path (`/candidate/` or `/client/`) as query parameters: `GET /api/auth/google/login?role=candidate|client&next=/candidate/` (or `/client/`). The backend wraps `role`, `next` and a nonce into a 10-minute state JWT, held in a `google_oauth_state` cookie during the round trip to Google.

On return, the callback redirects to `{FRONTEND_URL}{next}#google_auth=<jwt>` on success, but only reuses `next` when it matches the account's actual role, an existing user keeps their stored role regardless of what was requested; otherwise it falls back to `/` for a candidate or `/client/` for a client. On failure it redirects to `{FRONTEND_URL}/?google_auth_error=<code>` with one of: `not_configured`, `invalid_state`, `missing_code`, `token_exchange_failed`, `email_not_verified`, `account_disabled`, `admin_use_password`, `server_error`, or Google's own `access_denied` (nine codes in total). The page reads that code once, shows a short NL/EN toast for it, and strips it from the URL so a refresh does not repeat the message.

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

### 7.1 Bouwlagen (WS5, september 2026)

Tabler 1.4 blijft, geen herbouw. De schil is wel op de canonieke tokens gezet en de front-endcode is opgesplitst:

| Laag | Bestand | Verantwoordelijkheid |
|---|---|---|
| Tokens | `website/theme.css` | §1.2/§1.3/§1.4, eerste stylesheet van het paneel |
| Schil | `website/admin/admin.css` | `--tblr-*` op de merktokens, compatklassen, ~21 semantische utilityklassen (`.a-*`), gedocumenteerd bovenaan het bestand |
| Kern | `website/admin/js/admin.js` | state, laad-/foutstaten, `badge()`, paginering, dashboard, sectieregistry, één gedelegeerde click-listener |
| ui-laag | `website/admin/js/ui.js` | `ui.modal`, `ui.drawer`, `ui.tabs`, `ui.table`, `ui.confirm` op de Bootstrap 5-componenten van Tabler |
| Labels | `website/admin/js/labels.js` | alle enum→labelvertalingen, Nederlands, sleutels uit de backend |
| Secties | `website/admin/js/sections/<naam>.js` | één module per sectie, registreert zich via `Admin.registerSection({id, title, loader, skeletonHtml, filters, actions})` |
| Navigatie | `website/admin/js/nav.js` | leest de registry voor titels, loaders en filterbinding |

Twee bewuste afwijkingen van §1.2 in dit paneel:

- De inline compat-shim die `--navy-*` op eigen waarden zette (`#142235`, `#0E1B2E`) en radius 8–20px gaf, is verwijderd. Het paneel draait nu op `--navy-800 #0A1628`, `--navy-700 #0F1D35` en radius 3px.
- Gedempte tekst in het paneel is `--navy-200`, niet `--navy-300`. `--navy-300` haalt op `--navy-800` 3,3:1 en zakt onder de AA-ondergrens van 4,5:1; `--navy-200` haalt 6,6:1. `--navy-300` blijft in gebruik voor hairlines en iconen. `scripts/css_tokens_check.py` bewaakt de tokenpariteit van `admin.css` en faalt op elke hardcoded navy- of goudwaarde daarin.

Bekend openstaand punt: de gevendorde `admin/vendor/tabler/js/tabler.min.js` van Tabler 1.4 bevat Bootstrap zelf niet, dus `window.bootstrap` bestaat niet in het paneel. `ui.js` gebruikt de Bootstrap Modal/Offcanvas als die er is en valt anders terug op dezelfde markup en klassen met eigen focustrap, Escape en backdrop. Het mobiele sidebarmenu (`data-bs-toggle="collapse"`) werkt daardoor niet.

---

## 8. Component Library

Base components used across the four surfaces: Button (primary/ghost/outline, 3px radius), Input, Select, Card, Modal, Toast, Badge (status/semantic colors from §1.2), mono pill chip (role/level/location tags), Sidebar nav item, KPI stat tile, Table (sortable header, empty/error/loading row states), Avatar.

### 8.x Kaartsysteem

Op 9 september 2026 zijn drie richtingen voor één sitebreed kaartsysteem ontworpen (Editorial/typografisch, Technisch-diagram, Bewegingsgeleid) en door vier onafhankelijke jury's beoordeeld: merk/hiërarchie, toegankelijkheid, bouwbaarheid en een red-team-aanval op tien vectoren. Alle vier wijzen **Richting A — Editorial/typografisch** aan als winnaar (gemiddeld 7,9 over de vier rondes, tegen 6,4 voor Technisch-diagram en 6,9 voor Bewegingsgeleid). Deze subsectie is de bouwbare synthese: A's systeem, aangevuld met vier concrete overnames uit de andere twee richtingen en drie verplichte reparaties die de jury's als harde voorwaarde stelden voordat er gebouwd mag worden.

**Verplichte reparaties op A (niet optioneel):**
1. Elk interactief `.mark`-element (contactkanalen, niet de decoratieve cijfer- of codemarks) krijgt een tikdoel van minimaal 44×44px op alle breedtes. De bestaande 40×40 (desktop) / 32×32 (390px) haalt deze vloer niet.
2. De donkere keuzekaart krijgt een eigen achtergrond (`--navy-800`) in plaats van alleen een haarlijn op de sectiekleur (`--navy-900`) — een haarlijn van 1,37–1,69:1 is op een gelijkkleurige achtergrond geen betrouwbare kaartgrens.
3. Het cijfer in de dienstenladder wordt `--navy-300` (5,17:1), niet een lichte grijstint die de AA-tekstvloer niet haalt.

**Overgenomen uit de andere twee richtingen** (met bron):
- Van B: hover- en focus-visible-styling op interactieve decoratie zijn **identiek**, geschreven als regel, niet als aanname — voorkomt een muis-only signaal.
- Van B: elk klikbaar/tikbaar element krijgt de 44px-aanraakdoel-eis expliciet benoemd, niet alleen de contactrail.
- Van C: touch-fallback voor labels zonder hover — icoon/mark altijd zichtbaar, label alleen als progressive enhancement, betekenis draagt via `aria-label`, geen tooltip-mechaniek.
- Van C en B: `margin-top: auto` op elke kaart-CTA, zodat een link altijd op dezelfde hoogte landt, ongeacht taallengte — geschreven als harde regel, niet als belofte in proza (de red-team-jury wees terecht op A's onterechte claim "geen layoutsprong bij taalwissel": de kaarthoogte volgt de langste taal, dat is en blijft Nederlands; dat is geen bug, maar de spec zegt het nu eerlijk).
- Van B en C: laadstaten houden vaste structuurelementen (eyebrow, mark-kader) zichtbaar en vervangen alleen tekst door vlakke placeholder-blokken, voor het schoonste CLS-verhaal.

**Niet overgenomen (harde overtreding in de bron):** B's radial-gradient-stipraster (botst met het gradient-verbod), B en C's `--gold-600`/`--gold-700`/gevulde `--gold-300` als tekst- of chipkleur (breekt de bevochten `--gold-ink`-vloer), de verzonnen trustclaim "NBBU-conform" (komt nergens in de codebase voor), C's mouse-only `:focus-within`-only stapkaart, en elke vorm van een LinkedIn-logo-SVG (merkreproductie van een derde partij; LinkedIn blijft een tekstcode, "IN", zoals nu al in A).

---

#### 8.x.0 Systeemregels (gelden voor alle zes archetypen)

- **Radius**: `var(--radius)` (3px) op elke kaart, elke chip-rand, elke contactrij. `--radius-full` uitsluitend op `.chip`/`.pill`-badges — nooit op een kaart, nooit op de contactrail.
- **Geen drop-shadow als default**: 1px haarlijn (`--gray-100`, hexwaarde `#E2E8F0` — zie §8.x.2 over de naamgeving) op licht, `--navy-600` op donker vervangt `--shadow*`. **Uitzondering, verplicht**: waar een kaart op een even lichte paginakleur staat (wit kaart op wit vlak, of `--off-white` kaart op `--off-white` sectie) is de haarlijn alleen (≈1,2:1 non-tekst-contrast) onvoldoende als grens. In dat geval krijgt de kaart **`--shadow-sm`** (bestaand token, `0 1px 2px rgba(10,22,40,.05)`) naast de haarlijn. Dit is geen decoratieve schaduw maar een elevatie-signaal en blijft binnen de "geen drop-shadow tenzij functioneel"-regel. Structurele voorkeur: waar mogelijk staat een kaart op `--gray-50`/`--off-white` terwijl de kaart zelf wit is (expertise, blog, vacature), zodat deze uitzondering niet nodig is; alleen de donkere keuzekaart (die op `--navy-900` staat) en losse dienstenladder-panelen op wit vallen terug op `--shadow-sm`.
- **Hover = focus-visible, altijd identiek.** Elke nieuwe hoverstaat in dit systeem (randkleur, mark-kleur, onderstreping) krijgt exact dezelfde `:focus-visible`-declaratie. Dit is een schrijfregel voor de bouwer, geen aanname: een kaart mag nooit een hoverkleur hebben die het toetsenbord niet ook krijgt. QA verifieert dit met tab-navigatie op alle zes archetypen, niet alleen visueel.
- **44px-aanraakdoel, expliciet per element.** Elk element dat een `<a>` of `<button>` is (dus daadwerkelijk klikbaar/tikbaar) heeft een hit-area van minimaal 44×44px, ongeacht de visuele grootte van de mark/het icoon erin — via padding op het omhullende element, nooit door de zichtbare vorm zelf te vergroten. Decoratieve marks (cijfers, classificatiecodes die geen link zijn) hebben geen aanraakdoel-eis.
- **`margin-top: auto` op elke kaart-CTA** (`.go-link`, footer-link) binnen een `display:flex; flex-direction:column` kaart, zodat de link altijd onderaan landt ongeacht de hoogte van de tekst erboven. Dit lost het bestaande "Lees meer zweeft op wisselende hoogte"-probleem structureel op, in plaats van per kaart een vaste hoogte te forceren.
- **`box-sizing: border-box; width: 100%`** op elke kaart-container, als vangnet tegen horizontale overflow op 390px.
- **Taalspans**: elke tekstnode die `initLang()` (`website/script.js:30`, `initLang` toggelt inline `display`) toggelt, staat als twee sibling-`<span class="lang-nl">`/`<span class="lang-en">`-elementen, beide altijd in de DOM. Geen enkele nieuwe CSS-regel in dit systeem zet `display` op deze spans en er wordt niet op `:nth-child`/`:last-child` over taalspans gebouwd. Kaarten forceren geen vaste hoogte op tekstcontainers; alleen waar een clamp actief is (vacaturebeschrijving, blogexcerpt) staat een `min-height` zodat een kortere taalversie de rij niet doet inzakken. Kaartbreedtes zijn altijd flexibel (`flex:1`/grid), nooit een vaste px-breedte.
- **Reduced motion en no-JS**: zie §8.x.6.
- **`aria-hidden="true"`** op elk decoratief `.mark`-element en elk sprite-icoon; het label ernaast draagt de betekenis, nooit het symbool alleen.

---

#### 8.x.1 De zes archetypen

##### 1. Donkere keuzekaart

*Gebruikt op*: hero-keuzekaarten (index.html, "Ik zoek talent" / "Ik zoek werk").

| | |
|---|---|
| Anatomie | eyebrow (mono) → h3 (Newsreader) → body (Plex Sans) → `.go-link` (`margin-top:auto`) |
| Spacing | kaart-padding `--space-xl` (390: `--space-lg`); eyebrow→kop `--space-md`; kop→body `--space-sm`; body→link `--space-lg`; kaart-tot-kaart gap `--space-lg` |
| Typescale | eyebrow `--font-size-xs` mono; kop `--font-size-2xl` Newsreader; body `--font-size-base` |
| Kleur | **achtergrond `--navy-800`** (reparatie 2 — niet meer gelijk aan de `--navy-900`-sectie); rand `--navy-600`; top-accent **2px** (reparatie 2, was 1px) `--gold-500` (kaart 1) / `--navy-300` (kaart 2); kop/body wit / `--navy-100`; link `--gold-500` |
| Hover/focus-visible | rand → `--navy-400`, top-accent intensiveert (`--gold-400` / `--navy-200`), `translateY(-2px)`, 150ms ease. Focus-visible: identiek + 2px `--gold-500`-outline, offset 2px, geen `overflow:hidden` op de kaart. |
| Leeg/laden/fout | n.v.t. (statische content) |
| <=600px | 1 kolom, kaart volledige breedte, padding `--space-lg`, geen verkleining van kop/body |
| Taalspans | kop, body, linktekst elk een `.lang-nl`/`.lang-en`-paar; kaarthoogte volgt de langere (Nederlandse) versie, geen vaste hoogte |

##### 2. Lichte inhoudskaart met rand

*Gebruikt op*: expertisegrid (4 disciplines, inclusief nieuwe vierde discipline **Testrollen**), blogkaart.

| | |
|---|---|
| Anatomie | `.mark` of kicker-regel → h3 → body (geclampt op blog) → `.go-link` |
| Spacing | kaart-padding `--space-lg`; mark/kicker→kop `--space-md`; kop→body `--space-sm`; body→link `--space-lg`; grid-gap `--space-lg` |
| Typescale | kop `--font-size-xl` Newsreader; body `--font-size-sm`; meta/kicker `--font-size-xs` mono |
| Kleur | kaart wit, rand `--gray-100` (`#E2E8F0`), sectie/paginafond `--gray-50`/`--off-white` (nooit wit-op-wit, zie §8.x.0); kop `--navy-900`; body `--gray-500` (7,58:1, ruime marge boven de 4,5:1-vloer); link `--gold-ink` |
| Hover/focus-visible | rand → `--gold-ink`, `translateY(-2px)`, 150ms. Focus-visible identiek. |
| Leeg/laden/fout | n.v.t. voor expertise (statisch); blog: laden = vlakke `--gray-50`-blokken op kop/meta/excerpt-posities, structuur (kader) blijft staan; fout = "Kon artikelen niet laden, probeer opnieuw" met tekstlink-retry |
| <=600px | 1 kolom, geen verkleining van kaartpadding onder `--space-lg` |
| Taalspans | kop/body/link eigen paar; API-gerenderde blogvelden (titel/excerpt) komen al in actieve taal via `GSP.esc()`, geen span nodig; alleen de statische UI-tekst (kicker, "Lees meer") krijgt het paar |

##### 3. Datakaart (vacature/job)

*Gebruikt op*: `#jobsGrid` (vacatures.html) én `#homeVacanciesGrid` (index.html) — één kaart, twee contexten, sluit het huidige `.job-card`/`.vac-card`-verschil.

| | |
|---|---|
| Anatomie | mono meta-regel (discipline · niveau · locatie) → haarlijn → Newsreader-titel → beschrijving (3-regel clamp, `min-height:4.65em` zodat taalwissel de rijhoogte niet laat springen) → haarlijn → footer (mono salaris links, `.go-link` rechts, `margin-top:auto`) |
| Spacing | kaart-padding `--space-lg`; secties gescheiden door `--space-md` + haarlijn |
| Typescale | meta `--font-size-xs` mono; titel `--font-size-xl` Newsreader; beschrijving `--font-size-sm`; salaris `--font-size-base` mono |
| Kleur | kaart wit op `--gray-50`-sectie, rand `--gray-100`; discipline-label `--gold-ink` (enige kleur in de kaart); overige meta `--navy-300`; salaris `--navy-900` |
| Hover/focus-visible | rand → `--gold-ink`, schaduw-toename via `--shadow-sm` (geen `translateY`, want de kaart bevat een geneste link, zie hieronder), 150ms. Focus-visible identiek. |
| Nested-link-regel | de kaart is een klikbare `<div>` met een geneste `.go-link` (bestaand patroon, `script.js:688`, `stopPropagation`); deze structuur blijft ongewijzigd. De kaart krijgt daarom **`:focus-within`** als staat (niet `:focus`) zodat toetsenbordgebruikers die de geneste link met Tab bereiken hetzelfde randsignaal zien als bij hover — dit blijft één tab-stop, geen tweede focus-doelwit toegevoegd. |
| Lege staat | eigen kaart, gecentreerd, `.mark`-cijfer "00", eyebrow "Vacatures", kop NL "Er staan nu geen vacatures open; nieuwe rollen zijn in voorbereiding" / EN "New roles are being opened right now" (`script.js:689`, herzien: de eerdere NL/EN-koppen spraken elkaar tegen), body "Meld je aan voor de talentpool, dan nemen wij contact op zodra een passende rol binnenkomt." CTA **"Meld je aan voor de talentpool →"** naar `kandidaten.html#talentpoolOptin` (wijziging t.o.v. vandaag: niet langer naar `contact.html`, maar naar het bestaande dubbele-opt-in-formulier op die pagina — een concretere en al bestaande actie dan een generiek contactverzoek). |
| Laadstaat | skeleton: meta-balk en het lege kader blijven zichtbaar op hun plek, titel/beschrijving/footer worden vlakke `--gray-50`-blokken, geen shimmer |
| Foutstaat | linker haarlijn-accent in `--error` (`#dc2626`, bestaande `.form-error`-kleur, alleen als randkleur, nooit als tekstkleur), kop "Kon vacatures niet laden", CTA "Opnieuw proberen →" |
| <=600px | kaart volledige breedte gestapeld, `overflow-wrap:anywhere` niet nodig (geen lang e-mailadres hier), beschrijving blijft 3 regels |
| Homepage-vacatureband bij nul vacatures | **gedragswijziging t.o.v. vandaag.** Vandaag verbergt `initHomeVacancies()` (`script.js:791-793`) de hele sectie zowel bij een lege lijst als bij een fetch-fout — twee verschillende situaties met hetzelfde (niets tonende) gedrag. Nieuw: bij een **lege lijst** (API antwoordt, nul jobs) toont de sectie één compacte lege-staat-kaart (dezelfde component als hierboven, talentpool-CTA), zodat de homepage nooit stilzwijgend een conversiekans laat liggen. Bij een **fetch-fout** (netwerk/5xx) blijft het huidige gedrag: sectie verbergen — de homepage-band is aanvullend, niet de primaire vacaturelijst (dat is `vacatures.html`, waar de foutstaat wel zichtbaar moet zijn), dus een kapotte sectie op de homepage verbergen blijft de juiste, eerlijke keuze. |
| Taalspans | API-velden (titel/beschrijving) komen al in actieve taal via `GSP.esc()`; lege/laad/foutstaat-tekst en CTA's krijgen het standaardpaar |

##### 4. Genummerde stap

*Gebruikt op*: dienstenladder (werkgevers.html, 5 dienstvormen, compacte rijvariant) en werkwijzestap (werkwijze.html, 6 stappen, uitgeklapte railvariant). Eén onderliggend patroon (cijfer + kop + copy + rand-scheiding), twee dichtheden.

**Compact — dienstenladder:**

| | |
|---|---|
| Anatomie | genummerde rij in één paneel, geen kaartengrid. Rij: cijfer · kop + mono-classificatietag rechts · leidende zin · verantwoordelijkheidsverdeling (gedempt) · CTA. Vijf gelijke rijen lost de bestaande 3+2-asymmetrie (twee dubbelbrede kaarten in de onderste rij) structureel op. |
| Kolomraster | overgenomen van B, letterlijk als CSS-grid zodat de bouwer geen interpretatieruimte heeft: `grid-template-columns: 48px 220px 1fr 140px; gap: var(--space-lg); padding: var(--space-md) var(--space-lg); border-bottom: 1px solid var(--gray-100)` (laatste rij zonder onderrand). Kolommen: cijfer, kop, leidende zin + verantwoordelijkheidsverdeling gestapeld, classificatietag. |
| Spacing | rij-padding-block `--space-md` (1440) / `--space-lg` (390, gestapeld); cijfer→content-gap `--space-lg` |
| Typescale | cijfer `--font-size-xl` Newsreader; kop `--font-size-lg`; classificatietag `--font-size-xs` mono; leidende zin `--font-size-sm`; verantwoordelijkheidsverdeling `--font-size-xs` |
| Kleur | paneel wit op `--off-white`-sectie (of `--shadow-sm` als het paneel zelf op wit staat, zie §8.x.0); **cijfer `--navy-300`** (reparatie 3, was een grijstint onder AA); classificatietag `--gold-ink`; CTA `.go-link` |
| Hover/focus-visible | alleen op de CTA-link, niet op de hele rij — voorkomt "welke rij is de link"-verwarring (overgenomen van B) |
| <=767px | cijfer + kop + tag in een header-regel, content eronder met `padding-left:48px` voor uitlijning met de rij erboven; geen vaste px-breedtes op kindelementen, dus geen horizontale scroll. Deze rij schakelt op 767px en niet op 600px zoals de andere archetypen: het raster `48px 220px minmax(0,1fr) 140px` heeft plus gaps en padding circa 768px nodig voordat de bodykolom leesbaar wordt, en de bodykolom staat op `minmax(0, 1fr)` zodat hij wikkelt in plaats van de rij te verbreden. |
| Taalspans | standaardpaar per kop/zin/CTA; classificatietag is taalneutraal en per rij uniek: VAST, INTERIM, FLEX, DETACHERING, ZZP (de vijf contractvormen op werkgevers.html, in die volgorde) |

**Uitgeklapt — werkwijze:**

| | |
|---|---|
| Anatomie | verticale rail: 1440 horizontaal met alle 6 stapnummers compact, onder 601px verticaal langs de linkerkant. De rail is een statisch overzicht, geen voortgangs- of navigatie-element: alle zes de stappen staan tegelijk uitgeklapt als `.step-card-expanded` met volledige copy. Er is dus geen actieve of inactieve staat. |
| Spacing | rail-item `flex:1` (1440) / `padding-block:--space-sm` (<=600px); rail naar kaart `--space-2xl` (1440) / `--space-lg` (<=600px); kaart-padding `--space-xl` (1440) / `--space-lg` (<=600px) |
| Typescale | railcijfers `--font-size-lg`; kaartkop `--font-size-2xl`; labels `--font-size-xs` mono |
| Kleur | railcijfer en -label `--navy-900`; geen onderstreping en geen tweede staat, want er is geen stap om als actief aan te wijzen; kaart-topaccent `--gold-500` |
| <=600px | verticale rail voorkomt de bestaande botsing tussen stapnummer en icoonkader; er is geen icoonkader meer in dit systeem |
| Staten | statisch overzicht, geen leeg/laden/fout |
| Taalspans | standaardpaar per stap-label en kaart-copy |

##### 5. Chip/badge

*Gebruikt op*: discipline-/classificatiecodes (`.mark.code`: C++/MT/OT/QA), contractvorm-tags (VAST/INTERIM/FLEX/DETACHERING/ZZP), trust-badges (KvK, AVG, no cure no pay, garantietermijn, Brainport, reactietijd).

| | |
|---|---|
| Anatomie | mono uppercase tekst, letter-spacing 0,13em, in een rand-kader zonder vulling (`.mark.code`) of als losse tekst met een dunne scheidingslijn (trust-badges) |
| Spacing | interne padding klein (7-8px verticaal, 12-16px horizontaal — geen `--space`-token nodig, dit is de enige bewuste sub-tokenwaarde in het systeem); rij-gap `--space-sm`–`--space-lg` |
| Typescale | `--font-size-xs` mono, uitzonderloos — **nooit** kleiner dan 12px vast (dat was een fout in een van de verworpen richtingen) |
| Kleur | **op licht**: altijd `--gold-ink` als tekstkleur op wit/rand, **nooit** `--gold-600`/`--gold-700` als tekst (breekt de bevochten 5,17:1-vloer) en **nooit** een gevulde `--gold-300`-achtergrond (herintroduceert het "gele pil"-patroon dat deze migratie juist opheft). Neutrale chips (niveau/locatie): rand `--gray-100`, tekst `--gray-500`. **Op donker** (trust-strip in de navy-hero-context): rand `--navy-500`, tekst `--navy-100`. |
| Radius | `--radius-full` toegestaan hier — dit is de bewuste uitzondering op de sitebrede 3px-regel |
| Staten | statisch, geen interactie (chips zijn label, geen link) |
| <=600px | trust-badges: `display:grid; grid-template-columns:1fr 1fr`, twee gelijke kolommen in plaats van een links-uitgelijnde, ongelijk brede pillen-wrap. Het media-blok staat in `styles.css` achter de ongeconditioneerde `.trust-badges`-regel, anders wint `display:flex` daarvan op gelijke specificiteit en doet het niets. |
| Taalspans | standaardpaar behalve taalneutrale waarden ("KVK 75545586", disciplinecodes) |

##### 6. Contactmethode

*Gebruikt op*: contact.html — volledige-breedte rijen (E-MAIL, WHATSAPP, LINKEDIN). Dit is de pagina-eigen, **niet-zwevende** component; de sitebrede zwevende variant staat los beschreven in §8.x.4.

| | |
|---|---|
| Anatomie | hele rij is `.go-link`: mono-label (vaste kolombreedte 140px desktop / 84px mobiel) + waarde in Newsreader |
| Spacing | rij-padding `--space-lg`; label→waarde-gap `--space-lg` |
| Typescale | label `--font-size-xs` mono; waarde `--font-size-lg` Newsreader |
| Kleur | label `--gold-ink`; waarde `--navy-900`; haarlijn `--gray-100` |
| Overflow-fix | `overflow-wrap: anywhere` op de waarde-kolom (lost het bestaande "e-mailadres loopt tot de kaartrand"-probleem op 1440 op, waar `info@gsprecruitment.nl` nu tegen de rand kan lopen) |
| Hover/focus-visible | hele rij onderstreept de waarde in `--gold-ink`, identiek op focus-visible |
| <=600px | rijen volledige breedte gestapeld, geen vaste px-veldbreedte meer, dus geen horizontale scroll |
| Taalspans | labels taalneutraal; reactietijd-tekst krijgt het standaardpaar |

---

#### 8.x.2 Nieuwe tokens in `:root`

**Spacing en typescale** (waarden uit §1.3/§1.4 van dit document, nu ook daadwerkelijk in `website/styles.css` in plaats van alleen hier gedocumenteerd):

```css
--space-xs: 4px;   --space-sm: 8px;   --space-md: 16px;  --space-lg: 24px;
--space-xl: 32px;  --space-2xl: 48px; --space-3xl: 64px; --space-4xl: 96px; --space-5xl: 128px;

--font-size-xs: 0.75rem;  --font-size-sm: 0.875rem; --font-size-base: 1rem;
--font-size-lg: 1.125rem; --font-size-xl: 1.25rem;  --font-size-2xl: 1.5rem;
--font-size-3xl: 2rem;    --font-size-4xl: 2.5rem;  --font-size-5xl: 3.25rem; --font-size-6xl: 4rem;

--section-pad: var(--space-4xl); /* 1440 sectie-padding, --space-2xl + --space-lg op 390 */
--gold-ink: #8A6800; /* nieuw: enige toegestane goud-tekstkleur op licht, 5,17:1 op wit */
```

**`--gray-*`, een correctie op de canvas-specs, niet een nieuwe introductie.** Alle drie de ontworpen richtingen gebruikten een eigen `--gray-50…--gray-500`-schaal in hun canvas en spec-tekst, maar geen ervan komt overeen met de schaal die **al in §1.2 van dit document staat** (`colors_neutral`, regel 66-77) — en die schaal bestaat evenmin nog in `website/styles.css` (nul treffers op `gray-` bij controle). Om verwarring bij de bouwer te voorkomen: **dit systeem gebruikt uitsluitend de namen en waarden uit §1.2**, niet de afwijkende nummering uit de drie canvassen.

| Token (dit document, §1.2) | Hex | Contrast op wit | Toegestaan gebruik |
|---|---|---|---|
| `--gray-50` | `#F8FAFC` | — | paginafond onder een witte kaart |
| `--gray-100` | `#E2E8F0` | 1,23:1 (non-tekst) | hairline/kaartrand — **nooit tekst** |
| `--gray-200` | `#CBD5E1` | 1,49:1 (non-tekst) | zwaardere hairline waar meer nadruk nodig is; nog steeds geen tekst |
| `--gray-300` | `#94A3B8` | 2,56:1 | **nooit tekst** (faalt AA ruim); alleen niet-tekst decoratie |
| `--gray-400` | `#64748B` | 4,76:1 (net AA) | kleine mono meta-tekst waar geen krappere marge gewenst is dan strikt nodig |
| `--gray-500` | `#475569` | 7,58:1 | de standaardkeuze voor gedempte body-tekst in kaarten (ruime marge boven AA) |
| `--gray-600` | `#334155` | 12,63:1 | zwaardere secundaire tekst, weinig gebruikt in dit systeem |

Praktische regel voor de bouwer: **onder `--gray-400` mag nooit tekst staan.** Waar een van de drie canvassen "gray-400" of "gray-200" als tekstkleur voorschreef, is in deze synthese gecontroleerd of de bedoelde hexwaarde tekst-AA haalt volgens bovenstaande tabel — en zo niet, vervangen (zie reparatie 3, dienstenladder-cijfer naar `--navy-300`, niet naar een grijstint).

**Vervangen hardcoded CSS-blokken** (regelbereiken uit de CSS-census tegen deze worktree, `website/styles.css`, 1886 regels):

| Bestaand blok | Regels | Vervangen door |
|---|---|---|
| `.choice-card` | 1587-1611 | Archetype 1 (donkere keuzekaart) |
| `.service-card` (+ tweede-rij-variant) | 399-425, 952-957 | Archetype 2 (lichte inhoudskaart) |
| `.prop` / `.service-ladder-grid .prop` | 1604-1642 | Archetype 4, compacte variant |
| `.path-card` | 1778-1789 | Archetype 2 (lichte inhoudskaart, waar nog gebruikt) |
| `.story-card` (incl. werkwijze-hergebruik) | 643-698 | Archetype 4, uitgeklapte variant, of archetype 2 waar het geen stap is |
| `.step-card` (+ `.step-icon`/`.step-num`) | 953-987 | Archetype 4, uitgeklapte variant |
| `.job-card` | 487-499 | Archetype 3 (datakaart) |
| `.vac-card` (+ `.vac-ref`/`.vac-meta`, al dood) | 989-999 | Archetype 3 (datakaart), dezelfde component als `.job-card` |
| `.trust-badge` | 940-950 | Archetype 5 (chip/badge, trust-variant) |
| `.ts-item` / `.trust-strip` (dubbele definitie, zie §8.x.7) | 1713-1716, 1763-1765 | Archetype 5, één definitie |
| `.eco-badge` | 442-456 | Archetype 5 (chip/badge) |
| `.contact-method` | 1795-1804 | Archetype 6 |
| `.contact-detail` | 859-876 | Archetype 6 |
| `.signup-card` | 1650-1711 | Archetype 2, waar de kaartvorm zelf hergebruikt wordt (formulierstructuur blijft eigen) |
| `.blog-card` (page-local, `blog/index.html:29-40`) | n.v.t. (buiten `styles.css`) | Archetype 2, verplaatst naar het gedeelde systeem in `styles.css` |
| `.whatsapp-float` / `.mail-float` | 1826-1885 | §8.x.4 (nieuwe contactrail) |

---

#### 8.x.3 Icoonsysteem

De zes kaartarchetypen zelf zijn **icoonloos** (A's kernprincipe: Newsreader-cijfers of Plex Mono 2-lettercodes in een `.mark`-kader in plaats van een pictogram; dit lost het bestaande "drie icoonstijlen door elkaar"-probleem op zonder een vierde stijl toe te voegen, en is immuun voor icon-blokkerende adblockers). Dat deel is gebouwd en staat in deze branch.

**Herscoping (chief-of-staff review):** deze kaartmigratie levert alleen de icoonloze kaarten. Alle iconen buiten de kaarten (filters, formuliervalidatie, footer-links, statusmeldingen, CTA-knoppen, kandidaten.html-bullets) blijven in deze PR gewoon Font Awesome, precies zoals vandaag; dat is geen sluipende scope-inperking maar een expliciete keuze. Een eerdere versie van deze sectie beschreef ook al een same-origin SVG-sprite (`website/icons.svg`, ~24 symbolen, aangeroepen via `<use href="#icon-*">`) voor die resterende iconen; dat bestand is uit deze PR gehaald omdat geen enkele pagina of script er ooit naar verwees (0 treffers op `#icon-`) en een dood, ongebruikt bestand niet meegaat. De sprite-migratie zelf is een apart, eigenstandig werkpakket (fase 2, geen shipdatum), niet iets wat impliciet meelift met de kaartmigratie: het raakt zo goed als elke pagina (CTA-knoppen, kandidaten.html-bullets, script.js-templates) en verdient zijn eigen ui-designer/code-reviewer/qa-ronde in plaats van een losse toevoeging aan deze PR. De onderstaande tabel blijft staan als vastgelegd ontwerp voor wanneer dat werkpakket wordt opgepakt, niet als iets dat al gebouwd is.

**Uitzondering, ook in fase 2**: Font Awesome blijft in gebruik voor **header, login/registratie-modal en back-to-top-knop**; deze drie zijn chrome-elementen buiten de scope van zowel deze kaartmigratie als de toekomstige sprite-migratie en worden apart gepland.

Ontwerp voor de toekomstige sprite (fase 2, nog niet gebouwd): een verborgen `<svg style="display:none">` met een `<symbol id="icon-*">` per pictogram, 24×24-raster, `stroke-width:1.5`, `stroke:currentColor`, `fill:none`, `stroke-linecap/linejoin:round`, aangeroepen via `<use href="#icon-*">`. Elk icoon krijgt `aria-hidden="true"`; het label ernaast draagt de betekenis. ~24 iconen gepland:

| Icoon | Gebruik |
|---|---|
| `search` | vacature-/kandidaatfilters |
| `filter` | filterbalk vacatures.html/kandidaten.html |
| `chevron-down` | select-velden, uitklapbare filters |
| `chevron-right` | breadcrumb, generieke inline-verwijzing (niet de kaart-CTA-pijl, die blijft het letterlijke "→"-teken uit A's spec) |
| `check` | formuliervalidatie (geslaagd veld) |
| `check-circle` | succesmelding (bv. talentpool-opt-in bevestigd) |
| `alert-circle` | waarschuwingsmelding |
| `info-circle` | informatieve toast |
| `x-circle` | foutmelding, sluiten van een validatiestaat |
| `mail` | footer-contactlink, formulierveld-icoon |
| `phone` | footer-contactlink |
| `map-pin` | locatiefilter, footer-adres |
| `external-link` | uitgaande links in blogartikelen |
| `download` | CV-download in de portalen |
| `upload` | CV-upload (registratie, profiel) |
| `eye` / `eye-off` | wachtwoordveld-toggle buiten de login-modal (bv. wachtwoord-resetpagina) |
| `lock` | beveiligde-sectie-indicatie in de portalen |
| `arrow-right` | generieke inline tekstlink buiten het kaartsysteem |
| `arrow-left` | terugnavigatie (bv. vacature.html terug naar vacatures.html) |
| `plus` / `minus` | uitklapbare FAQ/accordeon-elementen indien aanwezig |
| `spinner` | knop-laadstaat buiten de kaartskeletons |
| `paper-plane` | vervangt `fa-paper-plane` op de verzend-/CTA-knoppen sitebreed (contactformulier, CV-uploads, "Deel je vacature", "Neem contact op" e.d.; circa 15 plekken in de huidige HTML, zie `grep -rn "fa-paper-plane" website/`), niet meer op de kaarten zelf (die zijn icoonloos, zie boven) |

---

#### 8.x.4 Contactrail (sitebreed, vervangt `.whatsapp-float` en `.mail-float`)

Vervangt de groene pulserende WhatsApp-bubbel (`#25D366`, `website/styles.css:1826-1858`) en de losse navy mail-knop (`1860-1885`) die vandaag op elke pagina zweven. Nieuw: één navy pil, radius `var(--radius)` (3px; ondanks de naam "pil" géén `--radius-full`, dat blijft gereserveerd voor chips), opgebouwd uit items van 48×48px met een mono-glyph wit op navy (`WA` / `@`, consistent met A's `.mark.code`-systeem; geen icoon, geen kleur buiten navy/wit, geen puls-animatie, nooit `#25D366`). Boven 600px twee items (WhatsApp, e-mail) gestapeld linksonder; op ≤600px één item (alleen WhatsApp) rechtsonder, zie "390px" hieronder. **Rand + schaduw:** `border: 1px solid var(--navy-600)` plus `box-shadow: var(--shadow-md)`. De pil staat op de navy hero/footer op precies dezelfde kleur als de achtergrond erachter. De rand alleen lost dat niet op: `--navy-600` op `--navy-900` is 1,35:1, ruim onder de 3:1 voor een niet-tekstueel onderscheid. De zichtbare scheiding komt van `--shadow-md`; de rand tekent alleen de vorm af. Tegen de lichte secties draagt de rand wel, daar is het contrast ruim voldoende.

- **Positie**: `position:fixed; z-index:9995`, met `bottom:var(--space-lg)` als basiswaarde. Op >600px linksonder (`left:var(--space-lg)`), op ≤600px rechtsonder met een inset van 16px (`right:16px; left:auto`, en dezelfde 16px in de `bottom`-calc). 16px in plaats van de 24px van `var(--space-lg)`: dichter in de hoek betekent meetbaar minder tekst onder de pil, en het is de inset die `.whatsapp-float` in productie al gebruikt. De hoekkeuze op ≤600px is geen botsingsvrije oplossing en wordt hier ook niet als zodanig geclaimd: alleen de laatste regel van een alinea eindigt rafelig, binnenregels lopen op 390px tot de rechtermarge. Een vast element in een onderhoek dekt dus in beide hoeken tekst af zodra je scrollt. Wat de hoek wél doet is de kans verkleinen dat het afgedekte deel het begin van een regel is, waar het verlies aan leesbaarheid het grootst is.
- **<=600px: één tikdoel**. Op ≤600px toont de rail alleen het WhatsApp-item (48×48, geen verkleining); het e-mailitem is verborgen met `.contact-rail__item--mail { display:none }` in het media-block, dus op de rail zelf en niet via `.lang-nl`/`.lang-en` (die klassen sturen uitsluitend taal). Dat halveert de afdekkende breedte van 96px naar 48px. **E-mail blijft op mobiel bereikbaar**: het adres in de onderste footerregel is op elke publieke pagina een echte `mailto:`-link (`.footer-bottom a`, kleur van de regel eromheen plus onderstreping, hover/focus naar goud), en `contact.html` heeft de niet-zwevende `.contact-row`-rij E-MAIL.
- **Gemeten afdekking van lopende tekst, hele scrollrange.** Chromium, acht pagina's (index, kandidaten, werkgevers, werkwijze, over-ons, vacatures, contact, blogindex), 390×844 en 390×664, NL en EN, in stappen van viewport/3 van boven tot onder, per frame de doorsnede van tekstregelrechthoeken met de pil, met `elementFromPoint`-controle dat de pil er ook echt bovenop ligt. 32 combinaties, 808-844 frames per opstelling. Voor elke veeg staat `scroll-behavior` op `auto` en zijn de `.fade-in`-klassen vooraf doorgezet, zodat elk gemeten frame uitgeregeld is en de bijbehorende screenshot hetzelfde frame toont als de meting. Alle drie de rijen zijn met dit harnas gemeten; de regel voor deze versie op de tip van deze branch, dus inclusief de `.signup-split`- en `.signup-panel`-reparaties.

  | Opstelling | Totaal over alle frames | Ergste frame | Combinaties met overlap | Frames met overlap |
  |---|---|---|---|---|
  | `.whatsapp-float` + `.mail-float` (huidige productie) | 119.487 px2 | 2.309 px2 | 32/32 | 269/808 |
  | Tweedelige pil rechtsonder (eerdere ronde) | 347.289 px2 | 4.925 px2 | 31/32 | 296/840 |
  | Eén item rechtsonder, inset 16px (deze versie) | 71.654 px2 | 1.401 px2 | 31/32 | 206/844 |

  Eerdere metingen op alleen scrollpositie 0 en onderaan de pagina waren een artefact: onderaan de pagina staat de pil boven de extra `padding-bottom` van de footer en meet je per definitie nul.
- **Restrisico, eerlijk benoemd.** Nul is dit niet en wordt het met een vast element in een onderhoek ook niet. In 31 van de 32 combinaties raakt de pil ergens in de scrollrange tekst, in 206 van de 844 gemeten frames; productie raakt in 32 van de 32 combinaties en in 269 frames. Het ergste frame is 1.401 px2: het woord "not" in de gecentreerde kop over de kandidaat die voorop staat, op over-ons EN 390×844, circa 13% van de regelbreedte. Daarna volgen twee regels van dezelfde alinea op over-ons NL (1.382 px2) en EN (1.297 px2). Het gaat steeds om het einde van een regel, of om een gecentreerde regel die tot in de rechtermarge loopt, nooit om het begin van een regel. Ten opzichte van productie is dat 40% minder totale afdekking en een 39% lager ergste frame, bij één in plaats van twee zwevende knoppen. Verdere reductie vraagt om iets anders dan een hoekkeuze (bijvoorbeeld de pil pas tonen na een scroll-drempel, of hem helemaal weglaten op mobiel); dat is een ui-designer-beslissing, geen implementatiedetail.
- **Vaste-elementenstapel op ≤600px.** Afstanden vanaf de onderrand, gemeten op 390×844 met zichtbare toast en zichtbare back-to-top, in beide back-to-top-varianten (de CSS-variant op index/over-ons/werkwijze/404, en de variant die `script.js` injecteert op de overige pagina's). Zonder cookiebanner: rail 16-66px, back-to-top 80-122px (CSS) respectievelijk 80-124px (JS), toastcontainer vanaf 132px; onderlinge overlap 0 px2 in alle vier de combinaties.
- **Cookiebanner in dezelfde stapel.** `#cookieConsentBanner` (`script.js`, `bottom:16px; z-index:10000; width:calc(100% - 32px)`) is op 390px geen enkele regel maar drie, gemeten 358×144. Zonder maatregel legt hij zich bij elk eerste mobiel bezoek over de hele rail (4.900 px2, beide items niet aantikbaar: `elementFromPoint` geeft `#cookieConsentAccept`) en over de toast (9.800 px2). `applyBodyOffset()` zet daarom naast de bestaande `padding-bottom` op `body` ook `--fixed-stack-offset` op de gemeten `offsetHeight` van de banner, en bij accepteren weer op `0px`; dezelfde functie loopt al op `resize`, zodat de waarde meeschuift als de banner van hoogte verandert. `.contact-rail`, `.back-to-top` (CSS-variant) en `.toast-container` krijgen in hun ≤600px-blok `bottom: calc(<waarde> + var(--fixed-stack-offset, 0px))`; de JS-variant zet dezelfde `calc()` in zijn eigen `style.cssText`. Gemeten met zichtbare banner: offset 144px, rail 160-210px, back-to-top 224-266px (CSS) respectievelijk 224-268px (JS), toast vanaf 276px, alle onderlinge overlappen 0 px2 en het WhatsApp-item aantikbaar. Na accepteren staat de offset op 0px en zit de stapel terug op 16/80/132px. Geen scroll-afhankelijke logica, geen extra elementen.
- **Verklapping op hover/focus**: in rust toont elk item alleen het mono-glyph; op hover/focus-visible (identiek, zie §8.x.0) schuift een tekstlabel ("WhatsApp" / "E-mail") uit naast het glyph, `max-width:0→120px`, 200ms ease. Op touch werkt dit niet (geen hover); het glyph blijft dus altijd zelfstandig leesbaar en elk item heeft een `aria-label` ("Stuur een WhatsApp-bericht" / "Stuur een e-mail") zodat de betekenis nooit alleen van de uitklap-tekst afhangt.
- **Toetsenbordbediening**: de pil is een `<nav aria-label="Direct contact">` met echte `<a href="https://wa.me/...">`/`<a href="mailto:...">`-elementen erin, elk een natuurlijke tab-stop. Focus-visible toont dezelfde uitgeklapte tekst als hover, dus geen apart, onzichtbaar toetsenbordpad. Het op ≤600px verborgen mail-item staat op `display:none` en valt dus ook uit de tabvolgorde; de footer-mailtolink neemt die rol daar over.
- **Footer-botsing**: `.footer` heeft op ≤600px `padding-bottom: var(--space-5xl)` (128px), zodat de laatste footerregel (copyright/KvK/AVG, inclusief de mailtolink) bij elke scrollpositie boven de pil blijft. Dit geldt voor elke pagina met de gedeelde footer. In de scrollsweep hierboven komt op geen enkele pagina een footerregel in de lijst afgedekte tekst voor.
- **Reduced motion**: de uitklap-transitie volgt de globale regel (`website/styles.css:1281-1290`), duur naar 0,01ms; de eindtoestand (glyph zichtbaar, tekst wel/niet uitgeklapt) blijft functioneel gelijk.

---

#### 8.x.5 Lege-vacaturestaat

Zie archetype 3 hierboven voor de volledige kaartspecificatie. Samengevat:

- **Status**: dit is een reële, actuele staat (`script.js:681`), geen hypothetische placeholder.
- **NL**: kop "Er staan nu geen vacatures open; nieuwe rollen zijn in voorbereiding", body "Meld je aan voor de talentpool, dan nemen wij contact op zodra een passende rol binnenkomt.", CTA "Meld je aan voor de talentpool →".
- **EN**: kop "New roles are being opened right now", body "Join the talent pool and we will reach out as soon as a suitable role comes in.", CTA "Join the talent pool →".
- **Doel**: `kandidaten.html#talentpoolOptin` (bestaand element, dubbele opt-in-formulier — een concretere actie dan de huidige `contact.html`-link).
- **Homepage-vacatureband** (`#homeVacancies`/`#homeVacanciesGrid`): bij nul vacatures toont de sectie voortaan deze compacte lege-staat-kaart in plaats van zichzelf volledig te verbergen (gedragswijziging, zie archetype 3-tabel); bij een fetch-fout blijft de sectie verborgen, ongewijzigd.

---

#### 8.x.6 Bewegingsregels

**Wel**: één overgang per interactief element — `border-color` (of `background-color` op de chip/contactrail) plus `translateY(-2px)` waar de kaart geen geneste link bevat (dus niet op de datakaart, zie archetype 3), 150ms ease. Focus-visible krijgt exact dezelfde overgang als hover (§8.x.0). De bestaande paginabrede fade-in (`initScrollAnimations`, `website/script.js:258-`, klassen `.fade-in`/`.fade-in-left`/`.fade-in-right`, met een 1,5s-fallbacktimer) mag op kaarten blijven staan als puur decoratief intrede-effect — nooit inhoudsdragend: elke kaart in dit systeem is compleet en leesbaar met alle duraties op 0.

**Niet**: geen shimmer op skeletons (vlakke `--gray-50`-blokken volstaan en zijn reduced-motion-neutraal), geen pulse (de contactrail vervangt juist de pulserende WhatsApp-bubbel), geen decoratieve gradients, geen `.fade-in-stagger` (bestaat in CSS, `styles.css:1462-1478`, maar wordt in geen enkel HTML-bestand gebruikt — blijft ongebruikt, zie §8.x.7 voor de opschoning van dat blok en de rest van de dode animatie-utilities).

**Reduced motion**: de bestaande globale regel (`website/styles.css:1281-1290`) zet alle animatie-/transitieduur op 0,01ms voor `prefers-reduced-motion: reduce`, ongewijzigd van toepassing op elk nieuw element in dit systeem. Omdat geen enkele hierboven beschreven staat content toont of verbergt (alleen kleur/positie van al-zichtbare elementen), is de eindtoestand met reduced motion functioneel en visueel compleet.

**No-JS-vangnet, nieuw**: een `<noscript><style>.fade-in,.fade-in-left,.fade-in-right{opacity:1!important;transform:none!important}</style></noscript>`-blok in de `<head>` van elke pagina die deze klassen gebruikt, naast de bestaande 1,5s-fallbacktimer in `initScrollAnimations`. Dit voorkomt dat een sessie zonder JavaScript kaarten permanent op `opacity:0` laat staan; het gebruikt de bestaande klassenamen (`fade-in`, niet een nieuwe `is-visible`/`reveal-group`-naam) zodat er geen wijziging aan `script.js`'s `SELECTOR` (`website/script.js:259`) nodig is.

---

#### 8.x.7 Dode CSS die in dezelfde PR verdwijnt

Bevestigd nul gebruik in HTML/JS (CSS-census, deze worktree, `website/styles.css`, 1886 regels):

| Blok | Regels | Omvang |
|---|---|---|
| Testimonials-carousel (`.testimonial-card` en varianten; `initTestimonials()` vindt nooit een `#testimonials`-element) | 700-812 (CSS) + `script.js` `initTestimonials()` | 113 regels CSS |
| Cookie-banner (`.cookie-banner` en subklassen; hele cookie-UI bestaat niet meer in HTML/JS) | 1305-1367 | 63 regels |
| `.hero` (los van het levende `.page-hero`) | 354-387 | 34 regels |
| Animatie-utilities: `.animate-float`, `.animate-pulse`, `.animate-shimmer`, `.animate-gradient`, `.animate-slide-up`, `.animate-scale-in`, `.fade-in-stagger`, `.floating-shape` | 1441-1495 | 55 regels |
| Losse dode selectors: `.sr-only`, `.btn-lg`, `.hero-content`, `.on-dark`, `.story-result`, `.vac-ref`, `.vac-meta`, `.stat-number` | verspreid | — |
| `.whatsapp-float`, `.mail-float` (vervangen door §8.x.4) | 1826-1885 | 60 regels |
| Dubbele `.trust-strip`/`.ts-item`-definitie (1713-1716 is al dood voor kleur, specificiteit van 1763-1765 wint; wordt met de archetype-5-migratie tot één definitie samengevoegd) | 1713-1716 | 4 regels |

Totaal circa 330 regels aantoonbaar dode of te consolideren CSS, te verwijderen in dezelfde PR als de archetype-migratie (niet erna, om te voorkomen dat de census meteen weer verouderd raakt).

---

#### 8.x.8 Bouwvolgorde en verificatie

1. **`website/styles.css` eerst, één bouwer.** Tokens toevoegen (§8.x.2), de zes archetype-klassen bouwen, dode CSS verwijderen (§8.x.7), `--gray-*` corrigeren naar de §1.2-namen. Niets aan HTML raken in deze stap.
2. **`website/script.js`-templates, één bouwer, na stap 1.** De drie template-strings (`script.js:681` lege staat, `job-card`-template, `vac-card`-template) migreren naar archetype 3; nieuwe contactrail-markup (§8.x.4) toevoegen aan het gedeelde `<footer>`/shell-include; `<noscript>`-vangnet (§8.x.6) toevoegen. Alle API-velden blijven door `GSP.esc`/`GSP.safeUrl`.
3. **Pagina's per cluster, parallel, na stap 1 en 2.** Cluster A: index.html + vacatures.html + vacature.html (archetypen 1, 2, 3). Cluster B: werkgevers.html + werkwijze.html (archetype 4, twee varianten). Cluster C: over-ons.html + contact.html (archetype 5, 6, §8.x.4). Cluster D: blog/index.html + blog/post.html (archetype 2, blogvariant). Elke cluster is onafhankelijk van de andere drie zodra stap 1-2 klaar zijn.
4. **Verificatie, verplicht vóór PR:**
   - Playwright-screenshots op 1440 en 390, beide talen (NL/EN), voor elk van de zes archetypen in situ.
   - `scripts/csp_violation_check.py --warnings`
   - `scripts/xss_static_check.py`
   - `scripts/verify_csp_coverage.py`
   - `scripts/check_website_extensions.py`
   - `node --check` op `website/script.js` en `website/blog/blog-index.js`
   - Toetsenbord-QA: tab door alle zes archetypen, bevestig dat elke `:focus-visible`-staat zichtbaar identiek is aan de bijbehorende `:hover`-staat (§8.x.0), en dat de datakaart één tab-stop blijft ondanks de geneste link.
   - **Nieuw, twee scripts te schrijven als onderdeel van deze PR**: `scripts/css_class_census.py` (herbruikbare versie van de handmatige census hierboven, zodat "0 gebruik"-claims bij een volgende migratie automatisch geverifieerd worden) en `scripts/css_tokens_check.py` (faalt de build als een `--gray-*`/`--gold-*`-waarde als tekstkleur onder de 4,5:1-vloer wordt gebruikt, of als een kaartklasse een `border-radius` anders dan 3px/`--radius-full` zet).

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
