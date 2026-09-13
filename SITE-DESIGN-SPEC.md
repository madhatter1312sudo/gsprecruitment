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
7. [Admin en portalen: componentsysteem](#7-admin-en-portalen-componentsysteem)
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
    └── /admin/                #dashboard #users #candidates #jobs #clients #leads #outreach #blog
                               #analytics #reporting #audit #cms #settings
                               (+ #retention #placements #gdpr, ontworpen in §7.3, nog niet gebouwd)
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

## 7. Admin en portalen: componentsysteem

Deze sectie is het bindende ontwerpdocument voor `website/admin/` (Tabler 1.4, dark navy/gold), `website/candidate/` en `website/client/`. Wie hierna bouwt, bouwt hiernaar; waar dit document en een oudere notitie elkaar tegenspreken, wint dit document. Wat er niet in staat, wordt niet gebouwd zonder een nieuwe ontwerpronde.

**Besluit dat vaststaat: Tabler 1.4 blijft, en wordt goed gebruikt.** Geen herbouw, geen tweede UI-framework, geen componentbibliotheek erbij. De Bootstrap 5-componenten (modal, offcanvas, tabs, dropdown, collapse) zitten in de gevendorde Tabler-bundel en zijn daar bereikbaar als `window.bootstrap.Modal`, `window.bootstrap.Offcanvas` enzovoort (zie §7.2b: de bundel exporteert `window.tabler.bootstrap`, en `js/vendor-fallback-tabler-js.js` zet die na het laden door naar `window.bootstrap`). Ze worden vandaag nauwelijks gebruikt; het paneel rolt in plaats daarvan een eigen overlay uit zonder focustrap en zonder ESC (`admin.js` `openModal()`/`closeModal()`). Het werk in deze sectie bestaat grotendeels uit het vervangen van dat eigen werk door het framework dat er al ligt.

### 7.0 Bestaande bouwstenen die blijven

Deze vijf zijn getest of in gebruik en worden niet vervangen, alleen uitgebreid:

| Bouwsteen | Waar | Rol in dit systeem |
|---|---|---|
| `GSP.html` / `GSP.raw` / `GSP.mount` | `website/admin/js/render.js`, getest door `scripts/test_render_js.mjs` | De enige manier waarop markup ontstaat. Elke component hieronder wordt als `html\`\`` geschreven. `raw()` alleen voor eigen, statische fragmenten. |
| `setLoading` / `setEmpty` / `setLoadError` / `setContainerLoadError` | `admin.js` | De laad-, lege- en foutstaten van de datatabel (§7.2a) en van elke niet-tabelcontainer. Hun markup verandert (utilityklassen in plaats van inline `style=`), hun aanroepen niet. |
| `badge(status)` | `admin.js` | Kleurkeuze van een statusbadge. Blijft; de kleurenmap wordt uitgebreid en de tekst komt voortaan uit één enum-naar-labelmap (§7.2e). |
| `renderPagination(elId, total, limit, page, key)` | `admin.js` | De enige pagineercomponent, ook voor de nieuwe schermen. |
| `data-action`-delegatie | `admin.js` | De enige manier om gedrag aan markup te hangen. Er komt geen inline `onclick` bij: de CSP verbiedt dat. |

---

### 7.1 Tokens en schil

> **Status, september 2026.** §7.1.1 en §7.1.2 zijn gebouwd (WS5 stap 1 t/m 3), met twee afwijkingen die hieronder ter plekke staan: het tokenblok woont in `website/admin/admin.css` in plaats van in een `<style>`-blok in `index.html`, en `--tblr-border-color` staat op `--navy-500`. §7.1.3 is deels gebouwd: de inline-styles zijn weg, maar met een andere, kleinere klassenset (`.a-*`) dan de `gsp-`-set hieronder; de vier `.text-*-ink`-klassen bestaan wel al met precies deze namen. De census-getallen in §7.1.3 zijn de meting op main van vóór die opruiming en blijven staan als vertrekpunt. §7.1.4 is nog niet gebouwd. Wat er nu daadwerkelijk staat, met bestandsnamen, is §7.9.

#### 7.1.1 Laadvolgorde, en de compat-shim verdwijnt

`website/admin/index.html:27-45` draagt vandaag een compat-shim met eigen navywaarden (`--navy-900:#142235`, `--navy-800:#142235`, `--tblr-body-bg:#0E1B2E`, `--tblr-bg-surface:#142235`) en een eigen radiusschaal van 8 tot 20px. Geen van die waarden staat in §1.2, de radiusschaal spreekt de vlakke 3px van §1.3 tegen, en `--navy-900` en `--navy-800` zijn er aan elkaar gelijk gemaakt, waardoor het paneel het diepteverschil kwijt is dat de rest van de site wel heeft.

Vast:

1. **Laadvolgorde, precies.** De Tabler- en Font-Awesome-stylesheets zijn geen statische `<link>`-elementen: `js/vendor-fallback-css.js` (`index.html:18`) injecteert ze met `document.head.appendChild()` op het moment dat dat script draait, dus ze landen in de cascade direct ná dat `<script>`-element. `<link rel="stylesheet" href="../theme.css">` komt daarom **direct onder regel 18**, dus ná de injectie, zodat de basisregels van `theme.css` (`body`-achtergrond en -kleur, scrollbar, `::selection`) van Tabler winnen bij gelijke specificiteit. De `--tblr-*`-koppeling (§7.1.2) en de utilityklassen (§7.1.3) komen daarna en winnen van allebei. *Gebouwd als:* die twee staan niet in een `<style>`-blok maar in `website/admin/admin.css`, als tweede `<link>` direct onder `theme.css`. Zelfde cascadepositie, één bestand minder inline, en de tokencheck kan het bestand lezen.
2. **`theme.css` is de tokenbron, maar niet compleet.** Het draagt de navy- en goudschaal uit §1.2 en de 3px-radiustokens, maar mist `--space-4xl`, `--space-5xl`, `--font-size-base`, `--font-size-6xl` en `--gold-ink`. Die vijf worden in `theme.css` toegevoegd met exact de waarden uit §1.3 en §8.x.2, zodat er precies één tokenbron voor de drie surfaces is en het paneel geen eigen aanvulling nodig heeft. *Nog niet gebouwd:* de schilpass had ze niet nodig omdat geen enkele regel in `admin.css` ernaar verwijst. Ze komen in de eerste §7.2-pass die ze wel gebruikt.
3. Het hele `:root, [data-bs-theme=dark]`-blok met navy-, radius-, spacing- en font-size-herdefinities in `index.html` gaat weg. Wat overblijft is uitsluitend de Tabler-koppeling uit §7.1.2 en de componentregels uit §7.1.3. *Gebouwd:* het blok is weg, de rest staat in `admin.css`.
4. `--gold-gradient` blijft alleen bestaan zolang de fallback-staafgrafiek in `admin.js` hem gebruikt; die fallback krijgt in dezelfde PR een vlakke `--gold-500`-vulling en daarna verdwijnt het token uit het paneel. Decoratieve gradients zijn sitebreed verboden (§8.x.6) en een grafiekbalk is decoratie, geen data. *Gebouwd:* `.a-barchart__bar` vult vlak met `--gold-500`; het paneel noemt `--gold-gradient` nergens meer.

#### 7.1.2 Tabler-variabelen op de navy-tokens

Eén blok, na het laden van `theme.css` en Tabler. *Gebouwd in* `website/admin/admin.css`, niet in een `<style>`-blok in `index.html`:

```css
:root, [data-bs-theme="dark"] {
  --tblr-body-bg:              var(--navy-800);   /* #0A1628 */
  --tblr-bg-surface:           var(--navy-700);   /* #0F1D35, kaarten, tabelkop */
  --tblr-bg-surface-secondary: var(--navy-800);
  --tblr-bg-surface-tertiary:  var(--navy-600);   /* #152B4A, hover-rij, inputvulling */
  --tblr-bg-surface-dark:      var(--navy-900);   /* #060D1A, sidebar, drawer-achtergrond */
  --tblr-border-color:         var(--navy-500);   /* dragende rand, zie de noot hieronder */
  --tblr-body-color:           var(--navy-100);   /* 12,25:1 op navy-800 */
  --tblr-secondary:            var(--navy-200);   /*  6,71:1, de gedempte tekstvloer */
  --tblr-primary:              var(--gold-500);
  --tblr-primary-rgb:          250, 200, 0;
  --tblr-primary-fg:           var(--navy-900);   /* tekst op een goudvlak */
  --tblr-border-radius:        var(--radius);     /* 3px */
  --tblr-border-radius-sm:     var(--radius);
  --tblr-border-radius-lg:     var(--radius);
  --tblr-font-sans-serif:      var(--font-primary);
  --tblr-font-monospace:       var(--font-mono);
  --tblr-focus-ring-color:     var(--gold-500);   /* niet --gold-glow: 28% dekking geeft 1,9:1 */
  --tblr-focus-ring-width:     2px;

  /* De vier kleuren waar Tabler zijn badge-, alert- en tekstvarianten uit
     afleidt. Zonder deze regels blijven .bg-blue-lt en .bg-red-lt op hun
     lichte-thema-waarden staan en halen ze de tekstvloer niet op navy. */
  --tblr-blue:                 var(--ink-info);
  --tblr-red:                  var(--ink-error);
  --tblr-green:                var(--ink-success);
  --tblr-yellow:               var(--ink-warning);
}
```

`--tblr-border-color-active` bestaat niet in Tabler 1.4 (nul treffers in `vendor/tabler/css/tabler.min.css`) en staat daarom niet in dit blok; een actieve rand wordt per component gezet.

**Noot bij `--tblr-border-color`.** Dit stond eerst op `--navy-600` en spreekt dan de contrastvloertabel hieronder tegen: die zegt dat een dragende rand op `--navy-700` minstens `--navy-500` moet zijn. De kaartrand is dragend, want op navy dragen de schaduwen nauwelijks en is de rand het enige dat een kaart van de achtergrond scheidt. `--navy-600` op `--navy-700` haalt circa 1,3:1 en leest niet als rand. Het codeblok hierboven staat daarom op `--navy-500`, net als `--tblr-card-border-color` en `--tblr-border-color-translucent`, en zo is het gebouwd.

**Contrastvloeren op donker, harde eis.** Berekend volgens WCAG 2.1 (sRGB-linearisatie, `(L1+0,05)/(L2+0,05)`) tegen de twee vlakken waar tekst in dit paneel op staat: `--navy-800` (#0A1628, paginafond) en `--navy-700` (#0F1D35, kaart- en tabelvlak). Deze tabel is de reden dat er hierboven geen `--navy-300` als tekstkleur staat:

| Token | Hex | op `--navy-800` | op `--navy-700` | Toegestaan gebruik |
|---|---|---|---|---|
| `--white` | `#FFFFFF` | 18,13:1 | 16,83:1 | koppen, primaire waarden |
| `--navy-100` | `#C5D6EB` | 12,25:1 | 11,38:1 | body, tabelcellen (`--tblr-body-color`) |
| `--navy-200` | `#7FA0C9` | 6,71:1 | 6,23:1 | **de gedempte-tekstvloer**: labels, meta, tijdstempels |
| `--navy-300` | `#4A6F9F` | 3,51:1 | 3,26:1 | **nooit tekst.** Randen en scheidingslijnen op `--navy-800` (>3:1); op `--navy-700` zakt ook dat onder de niet-tekstvloer, dus daar `--navy-500` of zwaarder |
| `--navy-400` | `#2A4A75` | 2,02:1 | 1,87:1 | alleen vlakken, nooit tekst en nooit een dragende rand |
| `--gold-500` | `#FAC800` | 11,51:1 | 10,68:1 | accenttekst, actieve nav, primaire knopvulling met `--navy-900` erop |
| `--gold-ink` | `#8A6800` | 3,51:1 | 3,26:1 | **verboden als tekst op donker.** Het is de goudtekstkleur voor lichte vlakken (§8.x.2) en haalt op navy de 4,5:1-vloer niet |

`admin.js` zet vandaag 63 keer `color:var(--navy-300)` op tekst. Dat is de grootste toegankelijkheidsschuld in het paneel en die wordt in dezelfde PR ingelost: elk van die 63 gevallen wordt `.a-soft` (§7.1.3), dat op `--navy-200` uitkomt.

**Semantische inkt op donker.** De semantische tokens uit §1.2 (`--success`, `--warning`, `--error`, `--info` en hun `-bg`-varianten) zijn voor lichte vlakken gekozen en staan bovendien in geen enkele stylesheet: nul treffers in `website/styles.css` en `website/theme.css`. Ze zijn dus geen bestaande laag om op voort te bouwen. Het paneel krijgt daarom vier eigen inkttokens, waarvan er twee al feitelijk in `admin.js` staan als losse hexwaarde en hier alleen een naam krijgen. De vlakken eronder zijn geen aparte tokens maar `color-mix` op dezelfde inkt, zodat er geen tweede kleurenrij ontstaat die kan gaan afwijken:

```css
--ink-success: #4ADE80;  /* 10,41:1 op navy-800, 9,66:1 op navy-700; vervangt de losse #4ade80 (8x) */
--ink-error:   #F87171;  /*  6,56:1 op navy-800, 6,09:1 op navy-700; vervangt de losse #f87171 (8x) */
--ink-warning: #FBBF24;  /* 10,86:1 op navy-800, 10,08:1 op navy-700 */
--ink-info:    #7DD3FC;  /* 10,87:1 op navy-800, 10,10:1 op navy-700 */
```

Alle vier zijn op beide vlakken boven de 4,5:1-vloer gerekend; de neutrale familie gebruikt `--navy-200` (6,71 respectievelijk 6,23:1). Dat is wat "getest" hier betekent: berekend contrast op de twee achtergronden die daadwerkelijk voorkomen, niet een steekproef op één.

#### 7.1.3 De utilityklassen die de 202 inline `style=`-attributen vervangen

> **Status.** De opruiming is gedaan: van de 202 inline `style=`-attributen staan er nog drie (een staafhoogte als custom property, één kolombreedte, en de `display:none` die JS op een actiemenu zet). De census-getallen hieronder zijn de meting op main van vóór die opruiming en blijven staan als vertrekpunt; het CSS-blok verderop is bijgewerkt naar de klassen zoals ze nu in `website/admin/admin.css` staan, met daarachter een tabel van wat er niet gebouwd is en waarom. De zes stukken eigen CSS onderaan deze subsectie zijn nog niet gebouwd en horen bij de componentpassen van §7.2.

`admin.js` draagt 202 inline `style="…"`-attributen. Die mogen blijven staan (de CSP blokkeert alleen inline *scripts*, niet inline stijl), maar ze worden uitgefaseerd omdat ze de tokenlaag omzeilen en elke kleurcorrectie in 63 losse strings moeten laten landen. De vervanging is grotendeels **Bootstrap 5, dat al in de Tabler-bundel geladen is**; alleen waar Tabler niets passends heeft komt een nieuwe klasse. Alle nieuwe klassen krijgen een eigen prefix of zijn een expliciete tekstkleur en staan in één blok. *Gebouwd als:* prefix `.a-`, in `website/admin/admin.css`.

De census is reproduceerbaar, niet geschat. De getallen hieronder komen uit:

```
grep -o 'style="[^"]*"' website/admin/js/admin.js | sed 's/style="//;s/"$//' \
  | tr ';' '\n' | sed 's/^ *//;s/ *$//' | grep -v '^$' | sort | uniq -c | sort -rn
```

Bestaande utilityklassen uit de bundel die de meerderheid opruimen, één op één:

| Inline (aantal) | Wordt |
|---|---|
| `display:flex` (25) | `.d-flex` |
| `color:var(--white)` (40) | `.text-white` |
| `gap:var(--space-md)` (17) | `.gap-3` (16px) |
| `text-align:center` (13) | `.text-center` |
| `width:100%` (12) | `.w-100` |
| `margin-bottom:4px` (12) | `.mb-1` |
| `margin-top:var(--space-lg)` (11) | `.mt-4` (24px) |
| `margin-bottom:var(--space-md)` (11) | `.mb-3` |
| `margin-bottom:var(--space-lg)` (11) | `.mb-4` |
| `flex:1` (9) | `.flex-fill` |
| `padding:1rem 0` (7) | `.py-3` |
| `font-weight:600` (6) | `.fw-semibold` |
| `flex-wrap:wrap` (5) | `.flex-wrap` |
| `padding:2rem` / `padding:3rem` (5) | `.p-4` / `.p-5` |
| `flex-shrink:0`, `justify-content:space-between`, `align-items:center` | `.flex-shrink-0`, `.justify-content-between`, `.align-items-center` |
| `font-family:var(--font-primary)` (9), `box-sizing:border-box` (8), `border-radius:var(--radius-md)` (13) | **vervallen zonder vervanging**: font erft van `body`, `box-sizing` staat in de reset, radius komt uit `--tblr-border-radius` |
| `padding:0.75rem` (9) | `.p-3` (16px, bewuste normalisatie naar het 4px-raster) |

**Gebouwd (WS5 stap 1).** Negenentwintig klassen met prefix `.a-` (waarvan vijf de panelen van `ui.js` dragen: `.a-modal`, `.a-drawer`, `.a-sortable`, `.a-confirm-hint`, `.a-nav-caption`), plus de vier `.text-*-ink`. Dit is wat er in `website/admin/admin.css` staat en wat een sectiepass overneemt; de klassenamen hieronder zijn de namen die de code gebruikt. Waar deze subsectie eerder een `gsp-`-naam voorstelde, staat die tussen haakjes erachter. **De prefix is `.a-`.** Elke `gsp-`-naam die verderop in §7.1 of §7.2 nog voorkomt is een nog niet gebouwde klasse; wie hem bouwt, geeft hem de `.a-`-prefix en voegt hem toe aan de kop van `admin.css`. Er bestaat geen tweede klassenstelsel.

```css
/* Tekst. .a-soft is de gedempte-tekstvloer (was: de losse text-muted-navy-klasse) en
   vervangt elke color:var(--navy-300) op tekst. Op een <td> zetten deze
   vier ook --tblr-table-color, want Tablers celregel is specifieker dan
   een losse klasse. */
.a-cell-name   { font-weight: 600; color: var(--white); --tblr-table-color: var(--white); }
.a-cell-strong { color: var(--white); --tblr-table-color: var(--white); }
.a-soft        { color: var(--admin-muted); --tblr-table-color: var(--admin-muted); }
.a-meta        { font-size: var(--font-size-xs); color: var(--admin-muted);
                 --tblr-table-color: var(--admin-muted); }   /* was: .fs-xs + de gedempte-tekstklasse */
.a-field-label { font-size: var(--font-size-xs); color: var(--admin-muted); margin-bottom: 4px; }

/* Semantische inkt (§7.1.2). De eerste twee heetten hier al zo; de andere
   twee zijn er in dezelfde vorm bij voor de overige twee inkttokens. */
.text-success-ink { color: var(--ink-success); }
.text-danger-ink  { color: var(--ink-error); }
.text-warning-ink { color: var(--ink-warning); }
.text-info-ink    { color: var(--ink-info); }
.a-accent         { color: var(--gold-400); }   /* goudaccent, geen semantische familie */

/* Toestanden. Laden, leeg en fout, in een tabelcel en daarbuiten. */
.a-state-cell  { text-align: center; padding: var(--space-xl) var(--space-md);
                 color: var(--admin-muted); --tblr-table-color: var(--admin-muted); }
.a-state-block { color: var(--admin-muted); font-size: var(--font-size-sm); padding: var(--space-md) 0; }

/* Vlakken en groepen. */
.a-panel    { border: 1px solid var(--admin-hairline); border-radius: var(--radius);
              padding: var(--space-md); margin-bottom: var(--space-md);
              background: color-mix(in srgb, var(--navy-300) 8%, transparent); }  /* was: .gsp-panel */
.a-actions  { display: flex; flex-wrap: wrap; gap: var(--space-md); margin-top: var(--space-lg); }
.a-listrow  { display: flex; align-items: center; gap: var(--space-md);
              padding: var(--space-md) 0; border-bottom: 1px solid var(--admin-hairline); }
.a-metric-row { display: flex; justify-content: space-between; padding: 6px 0;
                border-bottom: 1px solid var(--admin-hairline); }
.a-inline-list { margin: 0; padding-left: 1.1em; }

/* Chips en telkaartjes. */
.a-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.a-chip  { color: var(--white); font-weight: 500; }
.a-chip--skill { background: color-mix(in srgb, var(--gold-500) 18%, transparent); }
.a-chip--lang  { background: color-mix(in srgb, var(--navy-300) 25%, transparent); }
.a-stat  { flex: 1; text-align: center; padding: var(--space-md) var(--space-lg);
           border: 1px solid var(--admin-hairline); border-radius: var(--radius);
           background: color-mix(in srgb, var(--navy-300) 10%, transparent); }
.a-stat__value { font-size: var(--font-size-xl); font-weight: 700;
                 font-family: var(--font-mono); color: var(--gold-500); }
.a-stat__value--positive { color: var(--ink-success); }
.a-stat__label { font-size: var(--font-size-xs); color: var(--admin-muted); }

/* Invoer en voorgevormde tekst. .a-textarea bevat de resize-y uit het oude
   voorstel; .a-scrollbox bevat gsp-prewrap en gsp-scroll-y. */
.a-textarea  { width: 100%; background: var(--navy-900); border: 1px solid var(--tblr-border-color);
               border-radius: var(--radius); color: var(--white); padding: .75rem;
               font-family: var(--font-primary); font-size: var(--font-size-sm);
               resize: vertical; box-sizing: border-box; }
.a-scrollbox { max-height: 160px; overflow-y: auto; font-size: var(--font-size-sm);
               color: var(--navy-100); white-space: pre-wrap; word-break: break-word;
               background: var(--navy-900); border-radius: var(--radius-sm);
               padding: 10px; margin: 4px 0 0; }

/* Rijen, tabs en het fallback-diagram. */
.a-clickable    { cursor: pointer; }                    /* was: .gsp-clickable */
.a-row-unread   { font-weight: 600; }
.a-truncate-col { flex: 1; min-width: 0; }              /* was: .min-w-0 */
.a-tabbar       { display: flex; gap: 4px; flex-wrap: wrap;
                  border-bottom: 1px solid var(--admin-hairline);
                  margin-bottom: var(--space-md); padding-bottom: var(--space-sm); }
.a-tabbar .btn  { min-height: 44px; display: inline-flex; align-items: center; }
.a-tabpane      { min-height: 120px; }
.a-barchart     { display: flex; align-items: flex-end; gap: 6px; height: 120px; width: 100%; }
.a-barchart__col { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px; }
.a-barchart__cap { font-size: 9px; color: var(--admin-muted); }
.a-barchart__bar { width: 100%; border-radius: var(--radius-sm) var(--radius-sm) 0 0;
                   background: var(--gold-500); height: var(--a-bar-h, 0); }

/* Sidebarkopje boven een groep navigatielinks. */
.a-nav-caption { font-size: var(--font-size-xs); letter-spacing: .1em; }
```

**Nog niet gebouwd.** Deze zes stonden in het oorspronkelijke voorstel en zijn er niet gekomen, elk met de reden. Ze horen bij de componentpassen van §7.2, niet bij de schil.

| Voorgestelde klasse | Status en reden |
|---|---|
| `.text-body-navy` | Overbodig: `--tblr-body-color` staat al op `--navy-100`, dus dat is de standaardtekstkleur van het paneel. Alleen nodig als er ooit een vlak komt waar de body-erving niet klopt. |
| `.fs-xs`, `.fs-sm` | Niet als losse schaalklassen gebouwd. De twee plekken die ze nodig hadden zijn `.a-meta` en `.a-state-block`, die de maat meenemen. Een losse schaal komt pas als een component hem los nodig heeft. |
| `.gsp-num` | Mono cijferwaarde. Zit nu alleen in `.a-stat__value` en in de KPI-regel in `admin.css`. Wordt een eigen klasse zodra §7.2a de datatabel aanpakt, want daar komen bedragen en scores in kolommen. |
| `.gsp-eyebrow` | Mono, uppercase, gespatieerd. `.a-field-label` is de huidige benadering maar staat in Plex Sans. Hangt samen met §7.1.4: pas als `.text-uppercase` losgekoppeld is van mono kan dit erin, anders krijgt elke hoofdletterregel twee keer mono. |
| `.gsp-table-dense` | Tabeldichtheid hoort bij §7.2a en verandert de hoogte van elke rij; niet iets om los in de schil te zetten. |
| Hover- en focusstaat op `.a-clickable` | Gebouwd is alleen `cursor: pointer`. De hover-/focusachtergrond uit het voorstel vraagt dat rijen toetsenbordbereikbaar zijn, en dat zijn ze nog niet (§7.4). Beide komen samen in de datatabelpass. |

**Wat Tabler wél levert en dus niet nagebouwd wordt.** Gecontroleerd in `vendor/tabler/css/tabler.min.css`: `.offcanvas-end`, `.offcanvas-bottom`, `.modal-fullscreen-sm-down`, `.table-responsive`, `.nav-tabs`, `.form-switch`, `.is-invalid`, `.invalid-feedback`, `.alert-*`, `.badge` en de `-lt`-varianten bestaan allemaal. Voor geen daarvan komt eigen CSS.

**Wat Tabler niet levert, en dus wél eigen CSS is.** Deze zes staan naast de negenentwintig utilityklassen hierboven en horen in dezelfde begroting:

| Nodig voor | Eigen CSS |
|---|---|
| Kolomkop-sorteerknop (§7.2a) | `.btn-unstyled` (nul treffers in Tabler): `background:none;border:0;padding:0;font:inherit;color:inherit;cursor:pointer` plus de gedeelde `:focus-visible`-outline |
| Horizontaal scrollende tabsrij op 390px (§7.2b) | `.gsp-tabs-scroll { overflow-x:auto; scroll-snap-type:x mandatory; }` plus `scroll-snap-align:start` op elke tab |
| Sleepgreep-affordance boven de bottom-drawer (§7.2b) | `.gsp-drawer-grip`, 36x4px, `--navy-500`, `--radius-full`, `aria-hidden="true"` |
| Sticky voetbalk in drawer en modal (§7.2b, §7.2c) | `.gsp-sticky-foot { position:sticky; bottom:0; background:var(--navy-900); border-top:1px solid var(--navy-600); }` |
| 44px-tikdoel op elke knop en elk selectievakje op 390px (§8.x.0) | `@media (max-width:600px) { .btn, .form-check-input, .action-menu button { min-height:44px; min-width:44px; } }` |
| Tabel wordt kaartlijst onder 768px (§7.2a) | `.gsp-cardlist`, dat de `<table>` op `display:block` zet en `<tr>` als kaart tekent |

**`--tblr-primary` op goud raakt 23 knoppen.** `.btn-primary` komt 23 keer voor in `index.html` en `admin.js`, `.btn-outline-secondary` 10 keer. Zodra `--tblr-primary` goud is, wordt elk van die 23 een gouden vlak, en §1.2 staat één primaire actie per scherm toe. Regel: per scherm blijft hoogstens één `.btn-primary` staan; elke andere knop in een filterbalk, kaartkop of rij wordt `.btn-outline-secondary` (sectieniveau) of `.btn-ghost-secondary` (rijniveau). De destructieve knop is `.btn-danger` en telt niet als de primaire.

Uitfasering is meetbaar: `scripts/css_class_census.py` (§8.x.8) krijgt een tweede modus die (a) het aantal `style="`-treffers in `website/admin/js/admin.js` telt en faalt zodra dat stijgt, en (b) faalt zodra één `.portal-section` meer dan één `.btn-primary` bevat. Het eerste getal daalt per PR; het mag nooit omhoog.

#### 7.1.4 Lettertypen

De site gebruikt drie families (§1.3): Newsreader voor koppen, IBM Plex Sans voor body en UI, IBM Plex Mono voor eyebrows, bedragen, chips en tijdstempels. Het paneel laadt vandaag dezelfde drie via Google Fonts en zet Newsreader op `h1`-`h4`, `.navbar-brand`, `.page-title` en `.card-title`, en mono op `.text-uppercase` en de KPI-waarden. Dat blijft, met drie verscherpingen omdat een paneel geen leespagina is:

- **Newsreader blijft beperkt tot identiteit en paginakop**: `.navbar-brand`, `#pageTitle`, `.card-title`, en de kop van drawer en modal. Nooit op een tabelkop, een veldlabel, een knop of een badge. Een serif in een tabelkop kost leesbaarheid en levert niets op.
- **IBM Plex Sans is de UI-body**, ook in de tabel, de formulieren, de knoppen en de nav. Dit is de standaard en hoeft nergens apart gezet te worden, want `--tblr-font-sans-serif` wijst er al naar.
- **IBM Plex Mono is de datastijl**: KPI-cijfers, bedragen, matchscores, ID's, datums en tijdstempels, statuscodes en de `.gsp-eyebrow`. Altijd via `.gsp-num` of `.gsp-eyebrow`, nooit via een losse `font-family`. `.text-uppercase` blijft niet langer de mono-haak: die klasse betekent "hoofdletters", niet "mono", en zet vandaag ongewild mono op elke hoofdletterregel in het paneel. Die koppeling vervalt; wat mono moet zijn, krijgt `.gsp-eyebrow`.

De drie portalen delen deze regels. Er komt geen vierde familie en geen extra gewicht bij de al geladen set (Newsreader 400/500/600, Plex Sans 400/500/600, Plex Mono 400/500).

---

### 7.2 Zeven componenten

Elke component geldt gelijk voor het adminpaneel en beide portalen. Waar een portaal afwijkt, staat dat er expliciet bij. De opgegeven breekpunten zijn 1440px (werkbreedte) en 390px (telefoon): het paneel wordt op een telefoon gebruikt voor snelle acties (een draft afkeuren, een gebruiker deblokkeren, een lijst nalopen) en die acties moeten daar volledig werken, niet half.

#### 7.2a Datatabel

*Vervangt*: de losse `<table class="table table-vcenter card-table">`-blokken in `index.html` en de tbody-rendering in `admin.js`.

**Anatomie.** Kaart (`.card`) met, van boven naar beneden: (1) filterbalk (`.card-body.border-bottom.py-3`) met zoekveld links en maximaal drie selects rechts; (2) bulkbalk, alleen zichtbaar bij selectie, in dezelfde ruimte als de filterbalk; (3) `.table-responsive` met de tabel; (4) `.card-footer` met links de resultaattelling en rechts `renderPagination`.

**Kolommen.** Eerste kolom is de selectievakjeskolom (`width:36px`) als de tabel bulkacties heeft, anders vervalt hij. Laatste kolom is de actiekolom (`width:60px`, rechts uitgelijnd), altijd zonder koptekst. Daartussen maximaal zes gegevenskolommen op 1440.

**Sorteren.** De sorteerbare `<th>` is een `<button type="button" class="btn-unstyled" data-action="sort" data-field="…">` met de kolomnaam plus een chevron. `aria-sort` staat op de `<th>`: `none`, `ascending` of `descending`; precies één kolom draagt een andere waarde dan `none`. Sorteren gebeurt server-side over de hele verzameling: elke sorteerbare lijstroute neemt `sort` en `order` (BV10, geleverd). Een klik zet die twee in de querystring en herlaadt pagina 1 met dezelfde filters; de footer zegt gewoon "NN van MMM" zonder voorbehoud.

Alleen kolommen uit de allowlist van de route zijn sorteerbaar en de kolomkop is voor de rest een gewone `<th>` zonder knop. Een `sort` buiten die lijst geeft 422 met `detail.code = "invalid_sort_column"` en een `detail.allowed`-array, een `order` anders dan `asc` of `desc` geeft 422 met `invalid_order_direction`. Beide zijn programmeerfouten, geen gebruikersfouten: het scherm toont dan de generieke foutmelding en logt `detail.allowed` naar de console, en de knop verdwijnt niet stilzwijgend. Sorteren op een kolom die de route niet kent valt nooit terug op de standaardsortering, dus wat de kop zegt is altijd wat de query doet.

**Rijselectie.** Kop-selectievakje is drietoestandig: leeg, `indeterminate` bij een deelselectie, aangevinkt bij alles op deze pagina. Het selecteert nooit meer dan de zichtbare pagina. Het kopvakje draagt `aria-label="Alles op deze pagina selecteren"`; een rijvakje draagt `aria-label` met de rij-identiteit (naam of e-mail), nooit alleen "Selecteren". Een geselecteerde rij krijgt `background: var(--navy-600)`. Geen `aria-selected` op de `<tr>`: dat attribuut is alleen geldig binnen `role="grid"`, en dit is een gewone `<table>`. De selectiestaat wordt gedragen door het `checked`-attribuut van het rijvakje, dat een schermlezer al voorleest.

**Bulkbalk.** Verschijnt zodra er één selectie is, in de filterbalkruimte, `background: var(--navy-700)`, `border-bottom: 1px solid var(--navy-600)`. Inhoud: links "NN geselecteerd" in `.gsp-num`, daarnaast een tekstknop "Selectie wissen", rechts de acties. Destructieve bulkacties staan uiterst rechts en zijn `.btn-outline-danger`. De balk is `role="region"` met `aria-live="polite"` op de telling, zodat een schermlezer de selectiewijziging hoort. Bij nul selectie verdwijnt de balk en komt de filterbalk terug; de scrollpositie verandert daarbij niet.

**Dichtheid.** Twee standen, opgeslagen per gebruiker in `localStorage` onder `gsp_admin_density`: **ruim** (Tabler-standaard, rijhoogte 48px) en **compact** (`.gsp-table-dense`, rijhoogte 34px). De schakelaar is één icoonknop rechtsboven in de filterbalk met `aria-pressed`. Standaard is ruim op 1440 en compact niet beschikbaar onder 768px (daar is de tabel al een kaartlijst, zie hieronder).

**Staten.**

| Staat | Weergave |
|---|---|
| Rust | Rijtekst `--navy-100`, meta-kolommen `.a-soft`, kolomkop `.gsp-eyebrow` |
| Hover (rij) | `background: var(--navy-600)`, 150ms; alleen op een klikbare rij (`.a-clickable`) |
| Focus-visible (rij) | Identiek aan hover, plus `outline: 2px solid var(--gold-500); outline-offset: -2px` |
| Actief (geselecteerd) | `background: var(--navy-600)`, plus 2px `--gold-500` linkerrand op de eerste cel |
| Disabled (rij zonder toegestane actie) | Tekst blijft `--navy-100`; alleen de actieknoppen krijgen `disabled` plus `title` met de reden. Een rij wordt nooit gedimd, want dat kost leesbaarheid zonder iets uit te leggen |
| Laden | `setLoading(tbodyId, cols)`: één rij over de volle breedte, gecentreerd, spinner plus "Laden…". Kop- en filterbalk blijven staan (§8.x.0) |
| Leeg | `setEmpty(tbodyId, cols, msg)`: "Nog geen &lt;meervoud&gt;." plus, waar er een zinnige vervolgstap is, één tekstlink ernaar. Nooit een generiek "No results" |
| Fout | `setLoadError(tbodyId, cols, retryFn)`: waarschuwingsicoon plus "Kon niet laden, probeer opnieuw" met de retrylink. De retry roept precies dezelfde loader met dezelfde filters aan (`_lastParams`) |

**Toetsenbord.** Tab loopt door: dichtheidsschakelaar, zoekveld, filters, kopselectievakje, per rij het rijvakje en daarna de actieknoppen, en tenslotte de paginering. De rij zelf is geen tab-stop; de rijactie is altijd ook als knop in de actiekolom bereikbaar. `Enter` en `Space` op een sorteerknop wisselen de sorteerrichting. Bulkbalk-acties zijn gewone knoppen in de tabvolgorde.

**1440.** Volle tabel, alle kolommen, dichtheidsschakelaar zichtbaar.

**390.** Onder 768px is dit geen tabel meer maar een kaartlijst: per record één `.card.mb-2` met bovenin naam plus statusbadge, daaronder maximaal drie meta-regels in `.fs-xs.a-soft`, en onderin één rij knoppen op volle breedte. Elk tikdoel is minimaal 44x44px (§8.x.0). Het selectievakje staat linksboven in de kaart. De filterbalk stapelt tot één kolom en de selects worden volle breedte. De bulkbalk plakt onderaan het scherm met `position: sticky; bottom: 0`, zonder marge en zonder `--fixed-stack-offset`: dat token wordt door `website/script.js` gezet en het adminpaneel laadt dat bestand niet, dus daar is het altijd leeg. De toast schuift daarom omhoog zolang de bulkbalk zichtbaar is (`bottom: calc(var(--space-md) + var(--gsp-bulkbar-h, 0px))`, waarbij `--gsp-bulkbar-h` door de bulkbalk zelf op zijn eigen `offsetHeight` wordt gezet en op `0px` bij verdwijnen). Zo dekken de twee elkaar op geen enkele breedte af. Horizontaal scrollen komt in geen enkele breedte voor; de enige uitzondering blijft `.table-responsive` op tablets tussen 768 en 1024px.

#### 7.2b Drawer (offcanvas uit de Tabler-bundel)

*Vervangt*: `openModal('viewCandidateModal', …)` en `openModal('clientDrawer', …)`, die vandaag allebei de gecentreerde overlay gebruiken.

**Waarom offcanvas en niet modal.** Detail van een kandidaat of klant is lezen en navigeren, geen beslissing met één uitkomst. Een offcanvas houdt de lijst zichtbaar, verdraagt veel inhoud met tabs, en de Tabler-bundel levert focustrap, ESC en scroll-lock kant-en-klaar. De modal (§7.2c) blijft gereserveerd voor beslissingen.

**De namespace is `window.bootstrap`, doorgezet vanuit `window.tabler.bootstrap`.** `vendor/tabler/js/tabler.min.js` (v1.4.0) is een UMD-bundel die zichzelf als `tabler` op `globalThis` zet, met daarin de volledige Bootstrap-namespace (`tabler.bootstrap.Modal`, `Offcanvas`, `Tab`, `Dropdown`, `Collapse`, `Toast`, `Alert`, `Tooltip`, `Popover`). De bundel zet `window.bootstrap` zelf niet; `js/vendor-fallback-tabler-js.js` doet dat na het laden, voor de lokale kopie en voor de CDN-fallback. Alle code in het paneel leest `window.bootstrap`, nooit `window.tabler` rechtstreeks. De data-api zit in dezelfde bundel: `data-bs-toggle`, `data-bs-target` en `data-bs-dismiss` werken zonder JavaScript van onze kant, en de pijltoetsbediening van `.nav-tabs` zit er ook in.

**De bundel bestaat pas op aanroeptijd.** `js/vendor-fallback-tabler-js.js` staat in `index.html` ná `js/admin.js` en hangt het `<script>` met `document.body.appendChild()` aan de body, dus de bundel wordt asynchroon geladen en `window.bootstrap` bestaat niet wanneer `admin.js` wordt geparseerd. Elke aanroep leest de namespace daarom pas op het moment van gebruik (`const B = window.bootstrap; if (!B) { … }`, zoals `ui.js` doet), nooit in een module-scope constante bovenaan het bestand. Ontbreekt de bundel alsnog, dan valt de aanroep terug op een inline-melding "Kon dit venster niet openen, ververs de pagina" in plaats van een stille `undefined`-fout.

**Anatomie.** `<div class="offcanvas offcanvas-end" tabindex="-1" id="gspDrawer" aria-labelledby="gspDrawerTitle">`, breedte 560px op 1440. Kop (`.offcanvas-header`, `background: var(--navy-900)`, sticky): links `h2#gspDrawerTitle` in Newsreader `--font-size-2xl` met daaronder een `.gsp-eyebrow`-regel (type plus ID, bijvoorbeeld "KANDIDAAT · #1482"), rechts de statusbadge en de sluitknop. Direct onder de kop een tabsrij (`.nav.nav-tabs`, aangestuurd door `window.bootstrap.Tab`, `role="tablist"`). Daaronder `.offcanvas-body.gsp-scroll-y` met de actieve tabpaneel-inhoud. Onderaan een sticky voetbalk (`background: var(--navy-900)`, `border-top: 1px solid var(--navy-600)`) met maximaal twee acties: rechts de primaire, links de secundaire. Destructieve acties staan niet in de voetbalk maar in de tab waar ze thuishoren, achter de modal van §7.2c.

**Tabs.** Elke tab is een `<button role="tab" aria-selected aria-controls>`; het paneel is `role="tabpanel"` met `tabindex="0"`. Pijl-links/rechts wisselt van tab, `Home`/`End` springt naar de eerste of laatste. De actieve tab draagt een 2px `--gold-500`-onderrand; inactieve tabs zijn `.a-soft`. Elke tab laadt zijn eigen data pas bij eerste opening (lui) en houdt daarna zijn eigen laad-, lege- en foutstaat via `setContainerLoadError`.

**Staten.** Rust en hover als hierboven. Focus-visible op tab en op sluitknop: 2px `--gold-500`, offset 2px. Laden per tab: drie vlakke `--navy-700`-blokken op de plaats van de velden, geen shimmer (§8.x.6). Leeg per tab: "Nog geen …" plus, waar van toepassing, de knop die de eerste zou aanmaken. Fout per tab: `setContainerLoadError` op de tabcontainer, zodat een kapotte tab de rest van de drawer niet meesleurt. Disabled tab: alleen wanneer de rol de inhoud niet mag zien; dan `aria-disabled="true"` plus een korte reden in het paneel, nooit een tab die stilzwijgend verdwijnt.

**Toetsenbord en aria.** De offcanvas van de bundel doet de focustrap; bij openen gaat de focus naar de kop, bij sluiten terug naar het element dat hem opende (de rijactieknop). ESC sluit. De backdrop-klik sluit ook, behalve wanneer er een onopgeslagen formulier in de actieve tab staat; dan verschijnt eerst de bevestigingsmodal "Wijzigingen weggooien?".

**1440.** 560px breed, rechts, met backdrop; de lijst eronder blijft leesbaar.

**390.** Volle breedte, van onder naar boven (`offcanvas-bottom`), maximaal 92vh hoog, met een sleepgreep-affordance bovenin (visueel; slepen zelf is niet vereist). De tabsrij scrollt horizontaal met `scroll-snap-type: x mandatory`, nooit met een verborgen "meer"-menu. De voetbalk blijft sticky en de knoppen worden volle breedte, gestapeld, primaire actie bovenaan.

#### 7.2c Modal

*Vervangt*: `Admin.openModal()`/`closeModal()` volledig. Die eigen overlay heeft geen focustrap, geen ESC, geen `role="dialog"`, geen `aria-modal`, en zet de focus na sluiten niet terug. Dat is niet te repareren met een pleister; hij gaat weg en `<div class="modal" tabindex="-1">` plus `window.bootstrap.Modal` neemt het over (zie §7.2b over de namespace en het feit dat die pas op aanroeptijd bestaat). De aanroeperkant blijft gelijk van vorm (`Admin.openModal(id, bodyHtml, opts)` blijft bestaan als dunne wrapper rond `ui.modal`, dat `bootstrap.Modal` gebruikt), zodat de circa twaalf bestaande aanroepen niet herschreven hoeven te worden.

**Anatomie.** `.modal-dialog.modal-dialog-centered` (`.modal-lg` bij `opts.wide`), `.modal-content` op `--navy-900` met 1px `--navy-600`-rand en `--radius`. Kop: `h2.modal-title` in Newsreader `--font-size-xl`, plus sluitknop. Body: `--space-lg` padding. Voet: rechts de primaire actie, links daarvan de secundaire (`.btn-ghost-secondary`, tekst "Annuleren"). Precies één primaire actie per modal.

**Staten.** Rust, hover en focus-visible als elders. Laden: de primaire knop krijgt een spinner en `disabled`, de velden krijgen `disabled`, de modal blijft staan en de backdrop blijft. Fout: een inline-melding (§7.2f) bovenaan de body, niet een toast, want de fout hoort bij het formulier dat je voor je hebt. Succes: modal sluit en er verschijnt een toast; de onderliggende lijst herlaadt met dezelfde filters.

**Destructieve variant.** Voor AVG-wissen (§7.3.5) en de goedkeuringslijst bewaartermijnen (§7.3.1). Verschillen met de gewone modal:

- Kop krijgt een waarschuwingsicoon in `--ink-error` en een kopregel die het gevolg noemt, niet de handeling: "Deze gegevens worden onomkeerbaar gewist", niet "Weet je het zeker?".
- Body noemt in een `.a-panel` exact wat er gebeurt: welke tabellen, hoeveel rijen, en of het anonimiseren of hard verwijderen is. Bij een bulkactie staat het aantal er als `.gsp-num` en wordt het bij openen opnieuw opgehaald, niet uit de lijstweergave overgenomen.
- **Getypte bevestiging.** Eén tekstveld met een label dat de exact te typen tekenreeks noemt. De primaire knop blijft `disabled` tot de invoer letterlijk klopt (hoofdlettergevoelig, na `trim()`). De verwachte tekenreeks staat in het label als `<code>`, is selecteerbaar maar wordt nooit voorgevuld. Onder het veld staat, zodra er iets fout getypt is, "Komt niet overeen" in `.text-danger-ink`, met `aria-live="polite"`.
- De primaire knop is `.btn-danger`, staat rechts, en heeft als tekst het werkwoord plus het object ("Wissen (3 items)"), nooit "OK".
- ESC en backdrop-klik sluiten wel, want sluiten is de veilige uitkomst.

De te typen tekenreeksen zijn niet vrij te kiezen: ze komen overeen met wat de backend zelf eist, zodat de UI geen tweede, afwijkende waarheid introduceert. Zie §7.3.1 en §7.3.5.

**Toetsenbord en aria.** `role="dialog" aria-modal="true" aria-labelledby` op de kop, `aria-describedby` op de eerste bodyalinea. Focus gaat bij openen naar het eerste interactieve element (bij de destructieve variant: het bevestigingsveld), Tab loopt rond binnen de modal, ESC sluit, focus keert terug naar de openende knop. `Enter` in het bevestigingsveld voert de primaire actie alleen uit als die niet meer `disabled` is.

**390.** `.modal-fullscreen-sm-down`: volle breedte en hoogte, voetbalk sticky onderaan, knoppen volle breedte en gestapeld met de primaire bovenaan. Het bevestigingsveld krijgt `inputmode="text"` en `autocapitalize="off"`, zodat een mobiel toetsenbord de getypte bevestiging niet stuk maakt met een automatische hoofdletter.

#### 7.2d Formulierpatroon

*Vervangt*: de `.form-group`-regels in `index.html` en de handmatige veldopbouw in `admin.js`.

**Anatomie per veld.** `<div class="mb-3">` met daarin, in deze volgorde: `<label class="form-label">` (Plex Sans, `--font-size-sm`, gewicht 500, kleur `--navy-100`; niet meer de huidige uppercase mono, die maakt lange labels slecht leesbaar), optioneel een `.form-hint.fs-xs.a-soft` **boven** het veld wanneer de hint bepaalt hoe je invult, het veld zelf (`.form-control` / `.form-select` / `.form-check`), en daaronder de foutregel `.invalid-feedback`. Verplichte velden krijgen `required` plus een `*` in het label; optionele velden krijgen niets. Er wordt niet met "(optioneel)" gewerkt naast "*": één van de twee conventies, en dat is de asterisk.

**Validatie.** Inline, op `blur` van een veld dat de gebruiker heeft aangeraakt, en opnieuw bij `submit`. Nooit op `input` tijdens het eerste typen: een e-mailadres dat halverwege rood wordt is ruis. Een ongeldig veld krijgt `.is-invalid` (1px `--ink-error`-rand plus `aria-invalid="true"`) en `aria-describedby` naar de foutregel. Een veld dat na correctie geldig is verliest de foutstaat direct op `input`. Er wordt geen groene vinkstaat gebruikt: correct is de norm en verdient geen kleur.

**Foutsamenvatting.** Bij een mislukte `submit` verschijnt bovenaan het formulier (in een modal: bovenaan de body; in een drawertab: bovenaan het paneel) een blok met `role="alert"` en `tabindex="-1"`, dat direct focus krijgt. Inhoud: kop "Er zijn NN velden die aandacht nodig hebben", en daaronder een `<ul>` met per fout een link naar het veld (`href="#veldId"`, klik zet focus op het veld). De samenvatting wordt bij elke nieuwe `submit` opnieuw opgebouwd, nooit aangevuld. Bij een serverfout (422 met veldnamen) worden de velden op dezelfde manier gemarkeerd en verschijnt dezelfde samenvatting; een 5xx zonder veldinformatie verschijnt als één inline-melding (§7.2f) met de retryknop.

**Staten.** Rust: veldvulling `--navy-800`, rand `--navy-600`, tekst `--white`, placeholder `.a-soft`. Hover: rand `--navy-400`. Focus-visible: rand `--gold-500` plus `box-shadow: 0 0 0 3px var(--gold-glow)`; identiek aan focus, want een tekstveld heeft geen hoverbetekenis. Disabled: rand `--navy-600`, tekst `--navy-200`, `background: var(--navy-900)`, plus een korte reden als `.form-hint` eronder wanneer de reden niet uit de context blijkt. Laden (formulier wordt verzonden): alle velden `disabled`, primaire knop met spinner. Leeg is geen formulierstaat. Fout: hierboven beschreven.

**Toetsenbord.** Tabvolgorde volgt de leesvolgorde; er wordt nergens een `tabindex` groter dan 0 gebruikt. `Enter` in een enkelregelig veld verzendt het formulier; `Ctrl+Enter` doet dat vanuit een `<textarea>`. Een fieldset met een groep radio's of checkboxes krijgt `<legend>`, geen los `<div>` met labeltekst.

**390.** Eén kolom, altijd. `.detail-grid` schakelt al onder 576px naar één kolom; die grens gaat naar 768px, want twee kolommen formulier op een tablet in staand gebruik zijn te smal. Velden zijn volle breedte, minimale hoogte 44px. De knoppenrij is sticky onderaan het formuliervlak.

#### 7.2e Statusbadges en één enum-naar-labelmap

*Uitbreiding van*: `Admin.badge()` en `Admin.statusLabel()`.

**Anatomie.** `<span class="badge">` met `--radius-full` (de bewuste uitzondering uit §8.x.0), `--font-size-xs`, gewicht 500, padding 2px 8px, Plex Sans (geen mono: dit is een label, geen datawaarde). Nooit alleen kleur als drager: de tekst staat er altijd bij. Een badge is nooit klikbaar; wie moet filteren gebruikt de filterbalk.

**Kleur.** Vijf families, met de Tabler-klassen die er al zijn: neutraal (`bg-secondary-lt`), informatief (`bg-blue-lt`), aandacht (`bg-yellow-lt`), positief (`bg-green-lt`), negatief (`bg-red-lt`). Een `-lt`-badge zet zijn tekstkleur op de bijbehorende Tabler-basiskleur en zijn vlak op diezelfde kleur met lage dekking. Met Tablers eigen basiskleuren zakt dat op donker onder de vloer: `.bg-blue-lt` haalt op `--navy-700` circa 3,4:1 en `.bg-red-lt` circa 3,1:1, allebei onder de 4,5:1. Daarom worden `--tblr-blue`, `--tblr-red`, `--tblr-green` en `--tblr-yellow` in §7.1.2 op de vier inkttokens gezet; met die remap komen de vier gekleurde families op 10,10, 6,09, 9,66 en 10,08:1 op `--navy-700` uit, en de neutrale familie op 6,23:1 (`--navy-200`). Dat zijn berekende waarden op het vlak waar badges in dit paneel daadwerkelijk staan, niet een aanname dat Tablers standaardpalet op donker wel goed zal zitten.

Goud is geen badgekleur: goud is de primaire actie op een scherm en mag niet met een statuslabel concurreren. De enige uitzondering blijft de rolbadge "kandidaat", die vandaag al `gold` is; die gaat naar neutraal in dezelfde PR.

**Eén map, Nederlandstalige chrome.** Vandaag staat de kleurmap in `badge()` en een halve labelmap in `statusLabel()`, met alleen kandidaatstatussen erin. Er komt één module, `website/admin/js/status-map.js`, geladen na `render.js`, die per domein een `{ waarde: { label, tone } }`-map exporteert plus één functie `GSP.status(domein, waarde)` die `{ label, tone, className }` teruggeeft. Een onbekende waarde geeft de waarde zelf terug in de neutrale familie: nooit verbergen, nooit raden. Beide portalen laden dezelfde module, zodat "Geplaatst" in het adminpaneel en in het klantportaal hetzelfde woord is.

De waarden hieronder zijn uit de backend gelezen, niet bedacht. Bron per rij staat erbij.

**Kandidaat** (`candidates.status`, VARCHAR(50) DEFAULT `sourced`, `migrations/000_baseline.py`; de waarden die `admin.js` vandaag al herkent):

| Waarde | Label | Familie |
|---|---|---|
| `sourced` | Gesourced | neutraal |
| `new` | Nieuw | aandacht |
| `contacted` | Benaderd | informatief |
| `screening` | Screening | aandacht |
| `active` | Actief | positief |
| `placed` | Geplaatst | positief |
| `inactive` | Inactief | neutraal |

**Kandidaatherkomst** (`candidates.source`, de vijf literals uit `core/sources.py`; getoond als neutrale chip naast de status, niet als statusbadge):

| Waarde | Label |
|---|---|
| `portal_registration` | Zelf geregistreerd |
| `talentpool_optin` | Talentpool-aanmelding |
| `apollo` | Apollo |
| `apollo_bulk` | Apollo (bulk) |
| `agent` | Externe agent |

Een waarde buiten deze vijf is toegestaan (een API-aanroeper mag `source` vrij zetten) en wordt ongewijzigd getoond.

**Klant** (`clients.account_status`, VARCHAR(50) DEFAULT `active`, `migrations/000_baseline.py`; het toegestane patroon in `models/schemas.py` is `lead|active|inactive`):

| Waarde | Label | Familie |
|---|---|---|
| `lead` | Lead | informatief |
| `active` | Actief | positief |
| `inactive` | Inactief | neutraal |

**Vacature** (`JobOrderStatus`, `models/schemas.py`, de zes literals die het model valideert):

| Waarde | Label | Familie |
|---|---|---|
| `draft` | Concept | neutraal |
| `open` | Open | positief |
| `paused` | Gepauzeerd | aandacht |
| `closed` | Gesloten | neutraal |
| `filled` | Vervuld | positief |
| `deleted` | Verwijderd | negatief |

**Match** (`matches.status`, VARCHAR(50) DEFAULT `suggested`; de vijf vervolgwaarden komen uit `routers/candidate.py`'s applicatiefilter):

| Waarde | Label | Familie |
|---|---|---|
| `suggested` | Voorgesteld | informatief |
| `applied` | Gesolliciteerd | informatief |
| `interviewing` | In gesprek | aandacht |
| `offered` | Aanbod gedaan | aandacht |
| `placed` | Geplaatst | positief |
| `rejected` | Afgewezen | negatief |

**Outreach-draft** (`outreach_drafts.status`, VARCHAR(20) DEFAULT `draft`; de waarden die dit backend schrijft):

| Waarde | Label | Familie |
|---|---|---|
| `draft` | Concept | informatief |
| `sent` | Verzonden | positief |
| `rejected` | Afgekeurd | neutraal |
| `failed` | Mislukt | negatief |

**Plaatsing** (`_PLACEMENT_STATUSES`, `models/schemas.py`, patroon `concept|actief|beeindigd|geannuleerd`):

| Waarde | Label | Familie |
|---|---|---|
| `concept` | Concept | neutraal |
| `actief` | Actief | positief |
| `beeindigd` | Beëindigd | neutraal |
| `geannuleerd` | Geannuleerd | negatief |

**Retentie-beoordelingsitem** (`retention_review_items.status`, de waarden die `routers/retention_admin.py` schrijft en leest):

| Waarde | Label | Familie |
|---|---|---|
| `pending` | Te beoordelen | aandacht |
| `rejected` | Afgewezen (bewaard) | neutraal |
| `purging` | Wordt verwerkt | informatief |
| `purged` | Verwerkt | positief |
| `no_longer_eligible` | Niet meer van toepassing | neutraal |

**Retentiecategorie** (`retention_review_items.category`, de sleutels uit `RETENTION_TABLE` in `core/retention.py`; label is de `categorie` uit diezelfde rij, verbatim, want die tekst staat ook in het verwerkingsregister en op `privacy.html` en mag niet uiteenlopen):

| Sleutel | Label | Actie |
|---|---|---|
| `rejected_applicant` | Afgewezen sollicitant | anonimiseren |
| `talentpool_consent` | Talentpool met expliciete toestemming | anonimiseren |
| `sourced_no_response` | Gesourcete persoon zonder reactie | anonimiseren |
| `prospect_no_response` | Prospect zonder reactie | hard verwijderen |
| `prospect_responding` | Prospect die wel reageert (relatie) | anonimiseren |
| `portal_account_inactive` | Actief portalaccount zonder sollicitatie | anonimiseren |
| `referral` | Referral | anonimiseren |
| `leads_quiz` | Leads/quiz | hard verwijderen |
| `apollo_pool_purge` | Apollo-bulkpool | anonimiseren of hard verwijderen, per rij |

`apollo_pool_purge` is de enige categorie die **geen** `RETENTION_TABLE`-rij is: `services/scheduler.py` zet hem rechtstreeks in `retention_review_items` (regel 1265 en verder) en `core/retention.py` zegt op regel 655 expliciet dat hij er niet in staat. Gevolg voor de UI: `GET /retention/review` levert wel items met deze categorie, maar `GET /retention/table` bevat hem niet en er is dus geen backendlabel. "Apollo-bulkpool" is daarom een UI-eigen label in `status-map.js`, en de referentiekaart (§7.3.1) bevat deze categorie niet, want die kaart toont uitsluitend wat de tabel-endpoint teruggeeft.

`placed_candidate` (Geplaatste kandidaat, 7 jaar, `action=retain`) en `logs` (`action=infra_only`) komen nooit in de beoordelingslijst en krijgen daarom geen badge, maar staan wel in de referentietabel op het scherm (§7.3.1), zodat zichtbaar is dat ze bestaan en waarom ze er niet in staan.

**Grondslag** (`candidates.lawful_basis` en `client_prospects.lawful_basis`; de prospectwaarden zijn het gevalideerde patroon uit `routers/prospects.py`, de kandidaatwaarden komen uit `core/privacy.py` en de referral-route):

| Waarde | Label | Komt voor op |
|---|---|---|
| `portal_registratie` | Eigen portalaccount (art. 13) | kandidaat |
| `opt_in_talentpool` | Toestemming talentpool | kandidaat |
| `toestemming_referral` | Toestemming via referral | kandidaat |
| `gerechtvaardigd_belang` | Gerechtvaardigd belang | kandidaat |
| `zakelijk_functioneel_adres` | Zakelijk functioneel adres | prospect |
| `opt_in` | Opt-in | prospect |
| `bestaande_relatie` | Bestaande relatie | prospect |

De eerste vier zijn vrije-tekstwaarden op `candidates.lawful_basis` zonder CHECK-constraint; de laatste drie zijn het gevalideerde patroon van `ProspectCreate`/`ProspectUpdate`. De kandidaatselect biedt alleen de vier kandidaatwaarden aan, de prospectselect alleen de drie prospectwaarden.

**Toestemmingsomvang** (`TALENTPOOL_CONSENT_SCOPES`, `models/schemas.py`): `matching_only` = "Alleen matching", `matching_and_contact` = "Matching en contact".

**Staten van de badge zelf.** Statisch. Geen hover, geen focus, geen disabled: een badge is geen bedieningselement. Op 390px verandert er niets aan de badge; hij staat alleen op een andere plek in de kaartlijst (§7.2a).

#### 7.2f Toast en inline-melding

**Wanneer welke.** Een **toast** bevestigt iets dat gelukt is en dat je niet hoeft te lezen om verder te kunnen. Een **inline-melding** hoort bij een plek op het scherm en blijft staan tot de oorzaak weg is. Een fout die een handeling blokkeert is altijd inline, nooit alleen een toast: een toast die je mist is een fout die je mist.

**Toast.** De bestaande `Auth.toast()`-implementatie en de `.toast-container` in `index.html` blijven, met vier correcties. (1) De container krijgt `role="status" aria-live="polite" aria-atomic="true"`, zodat een schermlezer de melding hoort; een foutmelding krijgt in plaats daarvan `role="alert"`. (2) De vier varianten krijgen de tokens in plaats van losse hexwaarden: succes `--navy-900`-vlak met 3px linkerrand `--ink-success`, fout idem met `--ink-error`, waarschuwing `--ink-warning`, informatie `--navy-400`. De huidige volvlakke `#065f46`/`#991b1b`/`#78350f` verdwijnen: een gekleurd vlak van 360px trekt meer aandacht dan de mededeling waard is en botst met de navy schil. (3) Radius naar `--radius` (3px), niet `--radius-sm` uit de shim. (4) Duur 4 seconden, met pauze op hover en op focus; een toast met een actielink (bijvoorbeeld "Ongedaan maken") blijft 10 seconden staan en is tab-bereikbaar. Bij `prefers-reduced-motion` vervalt de intreebeweging en verschijnt de toast direct op zijn eindpositie.

Positie: rechtsonder, `--space-lg` van de rand. Op 390px volle breedte min 2x16px, onderaan, met `bottom: calc(var(--space-md) + var(--gsp-bulkbar-h, 0px))`. **Niet** `--fixed-stack-offset`: dat token wordt alleen door `website/script.js` gezet en geen van de drie surfaces laadt dat bestand, dus het is hier altijd leeg. De enige vaste elementen die op deze drie pagina's met de toast kunnen botsen zijn de bulkbalk van de datatabel (§7.2a) en de sticky voetbalk van een geopende drawer; de bulkbalk publiceert zijn hoogte als `--gsp-bulkbar-h` en de drawer neemt de toast bij openen mee omhoog. Maximaal drie tegelijk zichtbaar; een vierde vervangt de oudste.

**Inline-melding.** `<div class="alert" role="alert">` in de Tabler-vorm, altijd binnen het blok waar hij over gaat (formulier, kaart, drawertab), nooit zwevend. Anatomie: icoon links, tekst, en rechts optioneel één actie (meestal "Opnieuw proberen"). Vier tonen met dezelfde inkttokens als de toast. Vlak `--navy-900`, 1px rand in de bijbehorende inktkleur op 40% dekking, 3px linkerrand in de volle inktkleur.

De bestaande MFA-banner (`#mfaBanner`) is een inline-melding van het type waarschuwing en blijft precies waar hij staat; hij krijgt alleen de nieuwe styling en een `aria-live="polite"`, want hij verschijnt pas na het ophalen van de MFA-status.

**Staten.** Toast: intredend (200ms), zichtbaar, uittredend (200ms), gepauzeerd bij hover of focus. Inline: rust, en, waar er een actie in zit, hover en focus-visible op die actie (identiek). Een inline-melding heeft geen laad- of lege staat.

**Een 4xx-`detail` is een object, geen zin.** Elk endpoint dat dit systeem aanroept en dat een verwachte fout kent, geeft `detail` als object met minstens `code` en `message`, soms met een extra veld (`candidate_id` bij `referral_candidate_exists`, `allowed` bij `invalid_sort_column` en `invalid_order_direction`). De regels voor elke foutafhandeling in dit document:

1. **Vertak op `detail.code`, nooit op `detail.message`.** De tekst is Engels, is voor een ontwikkelaar geschreven en mag veranderen zonder dat dat een gedragswijziging heet.
2. **Toon een eigen Nederlandse zin** voor elke code die het scherm kent. Die zinnen staan per scherm in §7.3.
3. **Val terug op `detail.message`** voor een code die het scherm niet kent, in een generieke melding van de juiste toon. Beter een Engelse zin die klopt dan een Nederlandse die raadt.
4. `detail` kan ook nog een gewone string zijn (oudere endpoints); behandel die dan als `message` met een lege `code`. Eén helper doet die normalisatie, niet elk aanroeppunt apart.

**Copy.** Nederlands, één zin, zegt wat er gebeurd is en zo nodig wat je nu kunt doen. "Kon niet laden, probeer opnieuw" is de vaste foutzin bij een mislukte fetch (dat is al de conventie in het paneel). Geen uitroeptekens, geen "Oeps", geen technische code in de zichtbare tekst; een `detail.code` uit de API hoort in de console, niet op het scherm.

#### 7.2g KPI-tegel en lege dashboardstaat

**Anatomie.** `.card.card-sm` met `.card-body`: bovenin een `.gsp-eyebrow`-label (bijvoorbeeld "OPEN VACATURES"), daaronder de waarde in `.gsp-num` op `--font-size-3xl` (32px) in `--white`, en daaronder optioneel één regel context in `.fs-xs.a-soft`. Geen icoon in de tegel: de vijf iconen die er nu staan voegen niets toe dat het label niet al zegt. Geen sparkline, geen percentageverandering, geen kleurvlak.

**Geen verzonnen cijfers.** Een KPI-tegel toont uitsluitend een getal dat een API-veld letterlijk teruggeeft. Er wordt niets afgeleid, geen trend berekend uit twee metingen, geen doel of benchmark getoond. Waar de API `null` teruggeeft (bijvoorbeeld `cost_per_hire_avg` zonder gevulde `fee_value`), toont de tegel **"n.v.t."** in `.a-soft` met daaronder in `.fs-xs` de reden ("nog geen vervulde vacature met een vastgelegd tarief"). Nooit een 0 waar `null` bedoeld is: 0 is een meting, `null` is de afwezigheid van een meting, en dat verschil is op een dashboard het hele punt.

**Staten.**

| Staat | Weergave |
|---|---|
| Rust | Label, waarde, contextregel |
| Laden | Label blijft staan; de waardepositie wordt een vlak `--navy-700`-blok van 3ch breed en de hoogte van de regel. Geen shimmer, geen spinner, geen "0" die daarna verspringt |
| Leeg (`null`) | "n.v.t." plus reden, zoals hierboven |
| Fout | Label blijft staan; op de waardepositie een streepje plus, eronder, "Kon niet laden" met een tekstlinkretry via `setContainerLoadError` op het waardeblok. De andere tegels blijven werken: elke tegel faalt op zichzelf |
| Hover of focus | Geen: een tegel is geen bedieningselement. Waar een tegel toch naar een lijst leidt, is dat een expliciete tekstlink onderin de tegel, die wel hover en focus-visible krijgt |

**Lege dashboardstaat.** Wanneer alle vijf de tegels leeg zijn (een vers systeem, of een klantportaal zonder vacatures) worden de tegels niet getoond. In hun plaats komt één kaart over de volle breedte met: een `.gsp-eyebrow` "DASHBOARD", een kop in Newsreader `--font-size-2xl` ("Er zijn nog geen gegevens om te tonen"), één regel uitleg ("Zodra er vacatures, kandidaten of plaatsingen zijn vastgelegd, verschijnen de kerncijfers hier."), en precies één primaire actie, afhankelijk van de surface: adminpaneel "Nieuwe vacature vastleggen", klantportaal "Vacature plaatsen", kandidaatportaal "Profiel afmaken". Eén actie, niet drie. De widgets eronder (recente activiteit, nieuwe registraties, openstaande verificaties) houden hun eigen lege staat en verdwijnen niet.

**1440.** Vijf tegels op één rij (`.col-sm-6 .col-lg`, zoals nu). **390.** Twee kolommen, want vijf gestapelde tegels duwen alles wat eronder staat van het scherm; de vijfde tegel neemt de volle breedte van de laatste rij. Label blijft 12px en de waarde blijft `--font-size-3xl` (32px), met één uitzondering: **een tegel met een geldbedrag** past bij twee kolommen op 390px niet ("€ 12.450,00" is elf tekens in mono en loopt over). Onder 576px zakt zo'n tegel naar `--font-size-2xl` (24px), of, wanneer het bedrag ook dan niet past, naar een tegel over de volle rijbreedte op 32px. Nooit afkappen, nooit afronden naar duizendtallen: een bedrag dat je moet kunnen controleren, toon je heel.

---

### 7.3 De schermen die nog geen UI hebben

Per scherm: het wireframe in tekst, de componenten die het gebruikt, en de endpoints en velden die het leest of schrijft. Alles wat hier als veld genoemd wordt, bestaat in de backend; waar een aanname is gedaan, staat dat er letterlijk bij.

#### 7.3.1 Goedkeuringslijst bewaartermijnen

> **Status, september 2026: gebouwd**, als `website/admin/js/sections/retention.js` plus een lege `<section id="section-retention">` en het sidebar-item in `website/admin/index.html`. Alles hieronder staat er, met elf afwijkingen die hier ter plekke genoemd worden:
> 1. **"Laatst gegenereerd" heeft geen eigen API-veld.** `GET /review/summary` kent er geen. De tegel leest daarom de nieuwste `last_seen_at` over de hele verzameling (`GET /review?status=all&sort=last_seen_at&order=desc&limit=1`), en dat is precies het moment van de laatste generatierun, want `_upsert_review_item()` zet die kolom op `NOW()`. Is de lijst leeg, dan toont de tegel "n.v.t." met de reden (§7.2g). Er wordt niets afgeleid uit een pagina.
> 2. **De sorteerbare kolomkop is geen `<button class="btn-unstyled">`** maar de `<th>` zelf met `tabindex="0"`, `role="columnheader"` en `aria-sort`, zoals `ui.table` die sinds WS5 stap 3 al tekent (`.a-sortable`). Toetsenbordbediening (Enter en Space) en `aria-sort` zijn er wel; `btn-unstyled` is daarmee niet meer nodig en is niet gebouwd.
> 3. **`.gsp-cardlist`, `.gsp-num` en `.gsp-eyebrow` zijn gebouwd als `.a-cardlist`, `.a-num` en `.a-eyebrow`**, met de `.a-`-prefix die §7.1.3 voorschrijft. De kaartlijst is één CSS-mediaregel op dezelfde tabelmarkup (`data-label` per cel), geen tweede renderer. Het token `--gsp-bulkbar-h` heet om dezelfde reden `--a-bulkbar-h`.
> 4. **De rijacties zijn beide `.btn-ghost-secondary`**, ook op 390px, waar ze volle breedte worden en hun tekstlabel tonen. Niet één primaire gouden knop per rij: §7.1.3 staat één primaire actie per scherm toe, en drie gouden knoppen onder elkaar in een lijst zijn dat niet. De onomkeerbare stap zit achter de destructieve modal, waar de knop wel `.btn-danger`-gedrag heeft.
> 5. **Het 44px-tikdoel is gebouwd voor deze sectie**, niet paneelbreed (`#section-retention .btn` onder 600px). Een selectievakje wordt niet zelf 44px: het krijgt zijn tikdoel van een `<label class="a-tap">` eromheen, want een vakje van 44x44 is een vlak, geen vakje.
> 6. **De in- en uitklapbare kaarten zijn `<details>`**, niet een Bootstrap Collapse: dat werkt zonder JavaScript, is uit zichzelf toetsenbordbereikbaar en is niet afhankelijk van het moment waarop de Tabler-bundel binnen is. De bewaartabel laadt pas bij het openen.
> 7. **De dichtheidsschakelaar uit §7.2a (`gsp_admin_density`, `.gsp-table-dense`) is niet gebouwd.** Er is één dichtheid. De rijhoogte is met de kolommen zelf teruggebracht naar circa 65px op 1440 (categorie op één regel met de volledige naam in `title`, het ontbrekende signaal naast zijn uitklapknop in plaats van erboven, en die knop alleen op een rij waar de tekst daadwerkelijk is ingekort). Een schakelaar met twee standen hoort bij de datatabelpass van §7.2a, niet bij dit scherm.
> 8. **"Laatst gegenereerd" heeft drie staten, niet twee**: een datum, "n.v.t." met de reden wanneer de lijst leeg is, en een streepje met "Kon niet laden, probeer opnieuw" wanneer die ene meting mislukt. Een mislukte meting is geen "n.v.t.": dat zou een reden verzinnen voor iets wat gewoon niet geladen is.
> 9. **De lege staat volgt het actieve filter.** Alleen in de standaardweergave (status `pending`, geen categorie) staat er dat de lijst maandelijks wordt aangevuld en waar de knop "Lijst genereren" zit; onder een filter staat er dat er niets aan dat filter voldoet. Er staat maar één knop "Lijst genereren" op het scherm, in de kop van de samenvatting.
> 10. **De toast van het paneel was onzichtbaar.** Tabler draagt `.toast:not(.show){display:none}` (specificiteit 0,2,0) en dat won van de losse `.toast`-regel in `admin.css` (0,1,0); `Auth.toast()` zet `.toast-visible`, niet Bootstraps `.show`. Elke toast in het hele paneel stond dus op `display:none`. Opgelost met `.toast-container .toast { display: flex; }` in `admin.css`. In dezelfde ronde is de toast ook herstyled zoals §7.2f voorschrijft: één `--navy-900`-vlak voor alle vier de varianten, een 1px rand `--navy-500` en een 3px linkerrand plus pictogram in `--ink-success`/`--ink-error`/`--ink-warning`/`--ink-info`, tekst `--white`, radius `--radius`. De volvlakke `#065f46`/`#991b1b`/`#78350f` zijn weg. De container draagt `role="status"` met `aria-atomic="true"`; alleen de foutvariant draagt `role="alert"`. Nog open uit §7.2f: de duur van vier seconden met pauze op hover en focus, en de tien seconden voor een toast met een actielink.
> 11. **Geen rechten is een eigen staat.** Een 401 of 403 geeft geen retrylink maar de zin dat je geen rechten hebt, en zet "Lijst genereren" en de twee droogloopknoppen uit.
>
> Meegegroeid met deze eerste afnemer: `ui.table` kreeg `serverSort`, een lege staat (ook als functie, want die hangt hier van het filter af) en een foutstaat met retry; `ui.confirm` kreeg `body` en `onConfirm`; `ui.modal` kreeg `handle.button(rol)`, `handle.setBusy()`, `handle.syncGate()`, `modal-fullscreen-sm-down`, focus bij openen op het bevestigingsveld, de regel "Komt niet overeen" met `aria-live`, Enter in dat veld, en een waarschuwingsicoon in `--ink-error` bij de destructieve variant. Een knop die de aanroeper bewust heeft uitgeschakeld draagt `data-gsp-lock="1"` en wordt door de getypte bevestiging niet meer aangezet; dat slot draagt de cap van 200, de afgeronde bulk en de categorie waarvan de telling niet geladen kon worden. De normalisatie van een `detail`-string uit §7.2f punt 4 staat als `Admin.errorDetail()` in `js/admin.js`; deze sectie is de eerste afnemer, de andere secties migreren later. Bewaakt door `scripts/admin_sections_check.py` (de hele sectie tegen gestubde routes) en `scripts/admin_ui_check.py` (de nieuwe ui-opties), beide in CI (§7.9).

*Nieuwe sectie*, hash `#retention`, in de sidebargroep System, boven Settings. Menu-item: "Bewaartermijnen". Alleen zichtbaar voor rol `admin` (dat is elke gebruiker van dit paneel).

**Endpoints.** `GET /api/v1/admin/retention/table` (de referentietabel), `GET /api/v1/admin/retention/review?status=&category=`, `GET /api/v1/admin/retention/review/summary`, `POST /api/v1/admin/retention/review/generate`, `POST /api/v1/admin/retention/review/{item_id}/approve`, `POST /api/v1/admin/retention/review/{item_id}/reject`, `POST /api/v1/admin/retention/review/bulk`, en `POST /api/v1/admin/retention/run` (uitsluitend `dry_run: true`).

**Wireframe.**

```
┌ Bewaartermijnen ────────────────────────────────────────────────┐
│ [ Samenvatting ]  KPI-rij, 3 tegels (§7.2g)                     │
│   TE BEOORDELEN 14   CATEGORIEEN MET ITEMS 4   LAATST GEGENEREERD 3 sep │
│   rechts in de kaartkop: [ Lijst genereren ]  (secundair)       │
├─────────────────────────────────────────────────────────────────┤
│ [ Per categorie ]  kaart, tabel zonder selectie                 │
│   Categorie | Te beoordelen | Afgewezen | Verwerkt | Actie      │
│   Afgewezen sollicitant | 6 | 1 | 12 | [Bekijken] [Alles goedkeuren] │
│   ...                                                            │
├─────────────────────────────────────────────────────────────────┤
│ [ Filterbalk ]  status-select (Te beoordelen | Alle | ...)      │
│                 categorie-select                                 │
│ [ Bulkbalk ]    "3 geselecteerd"  [Afwijzen] [Goedkeuren...]    │
│ [ Datatabel §7.2a, selectie aan ]                               │
│   ☐ | Categorie | Onderwerp | Termijn verlopen | Ontbrekend      │
│       signaal | Actie | Status | ⋯                              │
│   ☐ | Afgewezen sollicitant | kandidaat #1482 | 12 aug 2026 (31 d)│
│       | geen nieuwe match, pipeline-activiteit of plaatsing      │
│       sinds de afwijzing | Anonimiseren | Te beoordelen | [✓][✕] │
│   ⟳ | Referral | kandidaat #903 | ... | Eerder afgewezen op 4 aug│
├─────────────────────────────────────────────────────────────────┤
│ [ Droogloop ]  kaart, ingeklapt                                 │
│   "Toon wat een volledige telling nu zou vinden"  [Uitvoeren]   │
└─────────────────────────────────────────────────────────────────┘
```

**Paginering, en waarom het scherm hem niet altijd gebruikt.** `GET /api/v1/admin/retention/review` neemt `limit` (1 tot 1000), `offset`, `sort` en `order`, en geeft `total` terug (BV6, geleverd). `limit` heeft bewust **geen default**: wie niets meegeeft krijgt de volledige set voor het gevraagde filter, en `total` is altijd de volle telling, nooit de paginalengte.

Het scherm gebruikt dat verschil bewust op twee manieren. De **lijstweergave** vraagt `limit=50` en tekent `renderPagination` uit `total`. De **bevestigingsmodal van een categoriebrede goedkeuring** vraagt juist zonder `limit`, want dat aantal gaat als `expected_count` mee: een paginagrootte zou daar "de hele categorie" stilzwijgend veranderen in "de eerste pagina ervan", en de mismatch zou pas als een geweigerde bulkaanroep terugkomen in plaats van als iets waar de beheerder wat mee kan.

**Kolommen en velden.** `category` (label uit §7.2e), `subject_table` plus `subject_id` samengevoegd tot "kandidaat #1482" of "prospect #77" (de `email` uit de respons wordt **niet** in de lijst getoond: hij staat wel in de API-respons maar hoort niet in een overzicht dat over een schouder meegelezen wordt; het adres is alleen in de bevestigingsmodal zichtbaar, en daar gemaskeerd tot `j••••@voorbeeld.nl`), `term_expired_at` als datum plus het aantal dagen erachter in `.fs-xs.a-soft`, `signal_missing_nl` verbatim (die tekst is door de backend geschreven om precies zo getoond te worden; niet inkorten, wel afbreken na twee regels met een uitklap), `action` als "Anonimiseren" of "Hard verwijderen", en `status` als badge (§7.2e).

**"Eerder overgeslagen" moet zichtbaar zijn, en staat gewoon in de standaardlijst.** Wanneer de generator een eerder afgewezen onderwerp opnieuw tegenkomt, zet hij het item terug op `status='pending'` en stempelt hij `reappeared_after_rejection_at` (`services/scheduler.py:1172-1180`: `status = CASE WHEN … IN ('rejected','no_longer_eligible') THEN 'pending' …`). Een heropend item staat dus **wel** in de standaardweergave (`status=pending`), niet erbuiten.

Weergave: zo'n rij krijgt links een pictogram en, in de kolom Status, onder de badge "Te beoordelen" een regel `.fs-xs.a-soft`: "Eerder afgewezen, opnieuw verschenen op &lt;`reappeared_after_rejection_at`&gt;". Dat is een zichtbaar ander signaal dan een item dat voor het eerst verschijnt, en dat is precies het punt: dit onderwerp is al eens bewust bewaard en verdient een tweede blik, geen routineklik.

De statusfilter krijgt daarnaast de optie **"Afgewezen (bewaard)"** die `status=rejected` opvraagt, zodat wat destijds is afgewezen en sindsdien niet is teruggekomen ook opvraagbaar blijft. De samenvattingskaart telt de heropende items **client-side** uit de geladen `pending`-lijst (aantal rijen met een gevulde `reappeared_after_rejection_at`) en toont die tegel alleen wanneer het aantal groter dan nul is; `GET /review/summary` groepeert op `category` en `status` en kent dat onderscheid niet.

**Goedkeuren, per item.** De `[✓]`-knop opent de destructieve modal (§7.2c). Kop: "Deze gegevens worden onomkeerbaar verwerkt". Body: categorie, onderwerp, verlopen termijn, ontbrekend signaal, de handeling (anonimiseren of hard verwijderen) en het gemaskeerde e-mailadres, in een `.gsp-panel`. Getypte bevestiging: **`APPROVE`**, letterlijk, want dat is wat `REVIEW_APPROVE_CONFIRM` in `routers/retention_admin.py` eist en de UI mag daar geen tweede, vriendelijker waarheid naast zetten. Het label boven het veld: "Typ <code>APPROVE</code> om te bevestigen". Primaire knop: "Goedkeuren en verwerken". Optioneel veld "Notitie" (`note`), vrije tekst, gaat mee in de aanroep.

**Afwijzen, per item.** De `[✕]`-knop opent een gewone modal, geen destructieve: afwijzen verwijdert niets en is de veilige uitkomst. Eén optioneel notitieveld en de knop "Afwijzen (bewaren)". Geen getypte bevestiging, want de backend eist die daar ook niet.

**Bulk.** Twee routes, met verschillende risico's, en het scherm laat dat verschil zien.

- *Expliciete selectie* (`ids`): de bulkbalk uit §7.2a. "Goedkeuren…" opent de destructieve modal met het aantal en de categorieën die in de selectie zitten; getypte bevestiging `APPROVE`; de aanroep stuurt `{ decision: "approved", ids: [...], confirm: "APPROVE", note }`. "Afwijzen" is één klik zonder modal, met een toast en een undo-loze bevestiging (er is niets ongedaan te maken, want er is niets vernietigd).
- *Categoriebreed* (`category`): de knop "Alles goedkeuren" in de categorie-tabel. De modal haalt bij openen **opnieuw** `GET .../review?status=pending&category=…` op en toont **de rijen die geraakt worden** in een scrollbare lijst (`.gsp-scroll-y`, maximaal 40vh) met per rij onderwerp, verlopen termijn en handeling, met daarboven het aantal als `.gsp-num`; dat getal gaat als `expected_count` mee. De lijst is er omdat "goedkeuren voor een hele categorie" anders een getal zonder gezicht is: wie op deze knop drukt, moet hebben kunnen zien wát hij goedkeurt. Zo komt de waarde uit de meting die de beheerder op dat moment ziet, niet uit een tabel die tien minuten oud is. Bij een 409 `retention_review_bulk_expected_count_mismatch` blijft de modal open, verschijnt de inline-melding "De lijst is veranderd sinds je hem bekeek. Ververs en probeer opnieuw." met de knop "Verversen", en wordt het aantal opnieuw opgehaald. Er wordt nooit stilzwijgend opnieuw geprobeerd met het nieuwe getal.
- Boven de bulkcap (`MAX_BULK_REVIEW_ITEMS`) geeft de backend een 422. De UI voorkomt dat vooraf: de knop is `disabled` met een `title` zodra de selectie de cap overschrijdt, en de tekst eronder zegt "Maximaal NN per keer".
- Het antwoord van een bulkaanroep is een lijst met per item een uitkomst, inclusief `status: "error"`. Het scherm toont die uitkomst als een resultaatlijst in dezelfde modal (niet als toast): "12 verwerkt, 2 mislukt", met de mislukte item-ID's en de mogelijkheid ze opnieuw te proberen. De lijst eronder herlaadt daarna.

**Droogloop.** Ingeklapte kaart onderaan. `POST /api/v1/admin/retention/run` met `{ dry_run: true }` geeft per categorie `{ key, status, count }` met `status` in `counted`, `not_applicable`, `schema_not_ready` of `error`. Weergave: tabel met categorie, telling en een leesbare toelichting per status ("telt niet mee: bewaren", "kolom bestaat nog niet", "kon niet tellen"). **Geen bevestiging, ook geen getypte.** De aanroep is read-only en verandert niets; hem dezelfde drempel geven als een onomkeerbare verwijdering leert een beheerder juist dat een typebevestiging niets betekent. Eén knop "Uitvoeren", meer niet. `dry_run: false` bestaat niet meer aan de backendkant (410) en komt in de UI ook niet voor; er is geen schakelaar.

**Tweede droogloopkaart: de Apollo-bulkpool.** `POST /api/v1/admin/apollo-pool/purge` met `{ dry_run: true }` geeft `{ total, would_anonymise, would_hard_delete, skipped }` voor de bulk-geharveste Apollo-rijen. Dat is de veertiende en laatste route van dit scherm en hij hoort hier, niet ergens anders, want hij telt dezelfde pool die als `category=apollo_pool_purge` in de beoordelingslijst staat. Eigen ingeklapte kaart naast de droogloop, met dezelfde vorm: knop "Uitvoeren", vier getallen in `.gsp-num`, en één regel uitleg bij `skipped` ("rijen die een beschermend signaal hebben opgepikt en daarom buiten de selectie vallen"). `dry_run: false` geeft 410 en zit niet in de UI; de kaart zegt er in `.fs-xs.a-soft` bij: "Verwijderen gebeurt uitsluitend via de beoordelingslijst hierboven, categorie Apollo-bulkpool."

**Referentietabel.** Onderaan de sectie, in een uitklapbare kaart: `GET /api/v1/admin/retention/table`, alle rijen uit `RETENTION_TABLE`, met categorie, bewaartermijn, bron of opmerking, en actie. `placed_candidate` (bewaren, 7 jaar) en `logs` (alleen infrastructuur) staan hier met een neutrale badge "Komt niet in de beoordelingslijst", zodat zichtbaar is dat ze bestaan.

**Staten van het scherm.** Laden: KPI-tegels in laadstaat, tabel met `setLoading`. Leeg: "Er staat op dit moment niets te beoordelen." plus, eronder in `.fs-xs`, "De lijst wordt maandelijks automatisch aangevuld." en de knop "Lijst genereren". Fout: `setLoadError` op de tabel, `setContainerLoadError` op de samenvatting; ze falen los van elkaar.

**390.** Kaartlijst in plaats van tabel (§7.2a): per item één kaart met bovenin de categoriebadge plus de statusbadge, daaronder onderwerp en verlopen termijn, daaronder het ontbrekende signaal ingekort tot twee regels met "meer", en onderin twee knoppen van volle breedte: "Afwijzen" (secundair) en "Goedkeuren" (primair, opent de destructieve modal, die fullscreen wordt). Bulk is op 390px beschikbaar maar categoriebreed goedkeuren niet: die knop staat alleen in de categorie-tabel, en die tabel toont op 390px alleen tellingen plus "Bekijken". Een categoriebrede, onomkeerbare goedkeuring hoort niet op een telefoon thuis.

#### 7.3.2 Toestemmingen in de kandidaatdrawer

> **Status, september 2026: gebouwd**, als `website/admin/js/sections/candidates.js`. De kandidaatdrawer zelf (Profiel, Matches, Activiteit, Toestemmingen) is met deze PR gebouwd, niet alleen de tab Toestemmingen: er bestond voordien geen drawer, alleen een brede modal met één paneel. Alles hieronder staat er, met de afwijkingen die hier ter plekke genoemd worden. Drie reviewrondes (security-auditor, code-reviewer, design-reviewer) gingen over dit scherm voordat het als klaar gold; security-auditor en code-reviewer vonden onafhankelijk dezelfde HIGH, en verder losten de rondes samen een reeks MEDIUM/LOW-punten op. Die punten zitten in de nummering hieronder, niet in een aparte lijst.
> 1. **Toestemmingen (en de twee wijzigmodals) werken op `candidates.id`, niet op het kind/id-paar waarmee de lijst en de drawer een kandidaat aanspreken, en voor kind `self-registered` is dat een tweede aanroep.** `GET /candidates/self-registered/{id}` (routers/admin.py:861-906) draagt geen enkele consentkolom terug, ook al staat er een gekoppelde `candidates`-rij achter (alleen `.candidate_id` staat erin); alleen `GET /candidates/sourced/{id}` doet dat (`SELECT c.*`). `resolveConsentDetail()` haalt daarom bij kind `self-registered` altijd een tweede keer op via kind `sourced` met dat `candidate_id`, en cachet dat apart onder de sleutel `sourced:<candidateId>` (nooit gemengd met de cache van de eerste, kind-eigen respons, want die twee objecten hebben een verschillende betekenis van `id`). Voor kind `sourced` is dat dezelfde aanroep als de tab Profiel, dus kost dit niets extra. Ontbreekt `candidate_id`/`id` helemaal (geen gekoppelde `candidates`-rij), dan toont de tab één zin ("Deze kandidaat heeft nog geen kandidaatrecord; toestemmingen zijn hier niet beschikbaar.") in plaats van de drie kaarten. Dit was de HIGH-bevinding van de eerste reviewronde (security-auditor en code-reviewer, onafhankelijk van elkaar): zonder deze reparatie toonde de tab voor elke self-registered kandidaat altijd "Geen toestemming" en job-alerts "Nee", en kon een beheerder daarmee een bestaande grondslag ongezien overschrijven. `scripts/admin_sections_check.py` heeft een tweede kandidaat (self-registered, gekoppeld aan een `candidates`-rij met actieve toestemming) juist om deze route te bewijzen.
> 2. **Een geslaagde PATCH dwingt een verse `GET /candidates/sourced/{candidateId}` af (`force: true`) in plaats van de PATCH-respons te vertrouwen.** De RETURNING-kolommen van beide consentendpoints (admin.py:945-946 en 962-963) dragen `consent_withdrawn_at` nooit mee, terwijl de intrek-tak die wel stempelt. Een cache die de PATCH-respons zou mergen, zou een eerdere intrekking na een latere vastlegging stilzwijgend kunnen verbergen: de talentpoolkaart zou "actief" tonen terwijl job-alerts, die `consent_withdrawn_at` wel meeweegt (`JOB_ALERT_ELIGIBILITY_SQL`), nog op de oude, foute waarde stond. MEDIUM-bevinding, security-auditor.
> 3. **De disabled-staat van "Vastleggen" (presentatie) meldt vooraf waarom, zichtbaar en niet alleen als `title`.** Zodra `consent_withdrawn_at` staat, geeft de backend op de presentatieroute gegarandeerd een 409 met een Engelse zin (admin.py:1171-1176). De knop staat dan `disabled`, met de reden "Deze kandidaat heeft toestemming ingetrokken; presentatie kan niet worden vastgelegd." zowel als `title` als in een `.a-meta`-regel eronder: op 390 is er geen hover, dus `title` alleen zou daar onzichtbaar blijven. Een eerdere tekst beloofde "pas na een nieuwe talentpooltoestemming", maar de vastleg-tak van talentpool-consent (admin.py:938-948) raakt `consent_withdrawn_at` nooit aan, dus die belofte kwam nooit uit; de huidige tekst belooft niets meer dan dat het nu niet kan. De talentpoolkaart zelf toont, zodra `consent_withdrawn_at` gezet is, een `.a-meta`-regel "Ingetrokken op `<retentionDate(consent_withdrawn_at)>`".
> 4. **Matches en Activiteit hergebruiken bestaande, gedeelde routes** in plaats van een eigen matcheslijst: Matches leest `GET /api/v1/admin/pipeline?candidate_id=` (BV1, §7.3.4) en toont vacature, fase en laatst gewijzigd; Activiteit leest `GET /api/v1/admin/activities?subject_type=candidate&subject_id=` zoals §7.3.6(b) voor de klantdrawer al doet. Er is geen aparte "matches"-route voor één kandidaat en de pipeline-rijvorm is inhoudelijk hetzelfde ding.
> 5. **De titel bij een actieve presentatietoestemming ("`<titel>` · Vacature #`<id>`") is best effort.** Er is geen admin-route voor één losse vacature. De tab haalt bij het openen, alleen wanneer er een `consent_spec_presentation_job_id` is, eenmalig de volledige (ongefilterde) vacaturelijst op (`GET /api/v1/admin/jobs?limit=200`) om de titel te vinden; staat de vacature daar niet in (verwijderd, of buiten de eerste 200), dan toont de tab alleen "Vacature #`<id>`" zonder titel.
> 6. **Onder de job-alerts-kaart staat één zin, `.fs-xs.a-soft`**: "De suppressielijst wordt bij verzending apart gecontroleerd." `JOB_ALERT_ELIGIBILITY_SQL` kent geen suppressieclausule; `services/scheduler.py` filtert die apart, buiten deze voorwaarde om, en zonder deze zin zou de kaart de indruk wekken dat "komt in aanmerking: ja" de volledige garantie is.
>
> De radiogroep in beide wijzigmodals staat bij openen altijd op "Vastleggen", ook wanneer de toestemming al actief is: de spec schrijft geen standaardkeuze voor, en "vastleggen/vernieuwen" is de handeling waarvoor een beheerder de knop "Wijzigen" (talentpool) of "Vastleggen" (presentatie) klikt. De datums en het bewijsveld gebruiken `Admin.retentionDate()` uit §7.3.1 (Nederlandse maandafkortingen) in plaats van `Admin.formatDate()` (en-GB), zodat de wireframe-datum "3 sep 2026" ook zo op het scherm staat.
>
> **Twee reparaties uit de design-review, allebei blokkerend.** (a) De radiogroep Vastleggen/Intrekken rendde als twee liggende ellipsen van de volle modalbreedte, met de labeltekst als losse hoofdletterregel eronder: `.form-group input, select, textarea { width:100% }` en `.form-group label { display:block; text-transform:uppercase }` in `admin.css` sloten `type="radio"`/`type="checkbox"` en `.form-check-label` niet uit. Twee `:not()`-uitsluitingen lossen dat op; gemeten na reparatie: `#tpConsentGrant` 20px breed op 1440 (was 390px). (b) Op 390px stond de inline 409-melding in de referral-modal buiten beeld na "Vastleggen" (de modalbody was al gescrolld door het formulier erboven): `candidateModalAlert()` roept sindsdien `scrollIntoView({block:'start'})` aan op het net gerenderde alert-element, in alle drie de modals. Gemeten na reparatie: de melding staat op `top: 1px` (binnen beeld).
>
> **44px-tikdoel op 390 (§8.x.0).** De bestaande regel (`#section-retention .btn`) is uitgebreid met `#section-candidates .btn` en, breder, `.offcanvas .btn, .modal .btn, .modal .form-select, .modal .form-control`: elke drawer en elke modal in het paneel deelt dezelfde knop- en veldmaten (§7.2b/§7.2c), dus die twee horen bij de gedeelde componentklasse. Deze pas dekt daarmee twee secties plus alle modals/drawers; de rest van het paneel volgt bij zijn eigen §8.x.0-pas. Gemeten op 390: "Wijzigen"/"Vastleggen" in de tab 44px, "Opslaan" in beide modals 44px, de vacaturekiezer 44px.
>
> **Teller op het bewijsveld, spec-conform.** `maxlength="2000"` op de drie bewijsvelden maakte de `>2000`-tak van `_validateEvidence` onbereikbaar: een browser laat een gebruiker dan nooit voorbij de grens typen. `maxlength` is weg; een aparte, live tellerregel (`_wireEvidenceCounter()`) toont pas iets, in `.text-danger-ink`, zodra de 2000 tekens overschreden zijn. De daadwerkelijke blokkade bij opslaan blijft `_validateEvidence`, bij blur en bij submit.
>
> **Drawerkop.** De titel en het onderschrift van de drawer komen bij openen uit de al geladen rosterrij (best effort) en worden bijgewerkt zodra het echte profieldetail binnen is (`updateCandidateDrawerHeader()`) -- zonder die correctie bleef de kop "Kandidaat" met een streepje als e-mail wanneer de drawer buiten de kandidatenlijst om opende (het dashboardwidget "Nieuwe registraties", en "Kandidaat openen" vanuit de referral-409). De naamregel bovenaan de tab Profiel (die de oude, brede modal ook had) staat er om dezelfde reden weer in.
>
> Bewaakt door `scripts/admin_sections_check.py`: de drie modals, de drie referral-uitkomsten, de self-registered route (afwijking 1), de force-refetch na intrekken-en-opnieuw-vastleggen (afwijking 2), de disabled presentatieknop (afwijking 3), de escaping van het informatieblok (een `<b>`-tag in "Aangedragen door" moet als platte tekst verschijnen, nooit als element), en de vier metingen hierboven (radiobreedte, alerttop, knophoogtes op 390) tegen gestubde routes.

*Nieuwe tab* "Toestemmingen" in de kandidaatdrawer (§7.2b), naast Profiel, Matches en Activiteit. Plus één knop "Referral vastleggen" bovenaan de kandidatenlijst.

**Endpoints.** `PATCH /api/v1/admin/candidates/{candidate_id}/talentpool-consent`, `PATCH /api/v1/admin/candidates/{candidate_id}/spec-presentation-consent`, `POST /api/v1/admin/candidates/referral`.

**Wireframe van de tab.**

```
TOESTEMMINGEN
┌ Talentpool ─────────────────────────────────────────────┐
│ Status: Toestemming actief   (badge)                    │
│ Omvang: Matching en contact                             │
│ Vastgelegd: 3 sep 2026 · Geldig tot: 3 sep 2027         │
│ Bron: admin · Grondslag: Toestemming talentpool          │
│                                     [ Wijzigen ]         │
└─────────────────────────────────────────────────────────┘
┌ Presentatie bij een opdrachtgever ──────────────────────┐
│ Status: Geen toestemming   (badge, neutraal)            │
│ (bij toestemming: "Voor: Senior Embedded Engineer,      │
│  Vacature #218 · vastgelegd 3 sep 2026")                │
│                                     [ Vastleggen ]       │
└─────────────────────────────────────────────────────────┘
┌ Job-alerts (alleen lezen hier) ─────────────────────────┐
│ Aangezet: ja · Komt in aanmerking: nee                  │
│ Reden: geen geldige toestemmingsomvang                  │
└─────────────────────────────────────────────────────────┘
```

**Talentpool wijzigen.** Modal (niet destructief), met: een radiogroep "Toestemming" met "Vastleggen" en "Intrekken"; bij "Vastleggen" een select "Omvang" met de twee waarden uit `TALENTPOOL_CONSENT_SCOPES` (verplicht, want de backend geeft 422 op `consent=true` zonder `scope`); en een verplicht `<textarea>` **"Bewijs van toestemming"** (`evidence`, 1 tot 2000 tekens) met de hint boven het veld: "Waar blijkt de toestemming uit? Bijvoorbeeld: ondertekend formulier van 2 september, of e-mail in het dossier." Het veld is verplicht in beide richtingen (ook bij intrekken), omdat de backend het zo eist. Inline validatie: leeg veld geeft "Vul kort in waar de toestemming uit blijkt"; boven 2000 tekens een teller in `.text-danger-ink`. Onder de modal een `.fs-xs.a-soft`-regel: "Bij het vastleggen geldt een termijn van 12 maanden. Deze notitie komt in het auditlog; e-mailadressen erin worden automatisch onleesbaar gemaakt." Dat laatste is waar: `privacy.redact_emails()` doet dat.

**Presentatie vastleggen.** Zelfde modal-vorm, met één extra en verplicht veld: **een vacaturekiezer**. Dit is een `<select>` (geen vrij tekstveld met ID) gevuld uit `GET /api/v1/admin/jobs?status=open&limit=200`, met per optie "&lt;titel&gt; · &lt;opdrachtgever&gt; · #&lt;id&gt;". Verplicht zodra "Vastleggen" gekozen is (`job_id` is dan verplicht in `AdminSpecPresentationConsentUpdate`); bij "Intrekken" is de kiezer `disabled` en wordt hij niet meegestuurd. `evidence` is ook hier verplicht. De hint boven de kiezer: "Toestemming voor presentatie geldt per rol, niet in het algemeen."

**Referral-intake.** Eigen modal, geopend vanuit de kandidatenlijst, want er is nog geen kandidaat om een drawer voor te openen. Velden, in deze volgorde: "Volledige naam" (verplicht, max 200), "E-mailadres" (verplicht), "Aangedragen door" (`referred_by`, verplicht, max 200) met de hint "Deze naam staat in de kennisgeving die deze persoon ontvangt", **"Bewijs van toestemming"** (`evidence`, verplicht) met de hint "Wat heeft de aandrager verteld, en wanneer? Bijvoorbeeld: mondeling bevestigd door X op 3 september, hij heeft haar gevraagd.", en "Interne notitie" (`note`, optioneel).

Boven de knoppenrij staat een **niet-inklapbaar informatieblok** met precies wat er gebeurt. Dit is geen juridische disclaimer maar het art. 14-blok als voorbeeld, want de beheerder moet weten wat hij verstuurt. De tekst is letterlijk gecontroleerd tegen `_REFERRAL_ART14_NL` en `_REFERRAL_TEXT` (`talent-os/backend/services/email_templates.py:524-568`), niet verzonnen: de eerdere versie noemde een opsomming van gegevens en een gebruiksdoel die de mail niet geeft, en zei "vervalt de invoer na drie maanden" terwijl de rij na drie maanden juist op de beoordelingslijst komt (`REFERRAL_NO_RESPONSE_SQL`), niet verdwijnt (chief-of-staff, na 3c8f690):

> Deze persoon ontvangt eenmalig een kennisgeving met een bevestigingslink, geldig 24 uur. Daarin staat: dat wij zijn of haar gegevens op de datum van vandaag hebben ontvangen via een aanbeveling van &lt;aangedragen door&gt;, met toestemming; dat wij ze drie maanden bewaren als er geen reactie komt; en het recht op inzage, bezwaar (art. 21) en afmelden met STOP. De kennisgeving bevat geen vacature en geen wervende tekst. Zonder bevestiging doen wij niets met de gegevens; na drie maanden komt de invoer op de beoordelingslijst in Bewaartermijnen.

De naam uit het veld "Aangedragen door" wordt live in dat blok ingevuld, zodat zichtbaar is wat de ontvanger straks leest.

Twee foutgevallen krijgen elk hun eigen Nederlandstalige inline-melding in plaats van een generieke: het adres staat op de suppressielijst ("Dit adres staat op de suppressielijst. Er mag geen bericht naar dit adres, op geen enkele grondslag.") en er bestaat al een kandidaat met dit adres ("Er is al een kandidaat met dit adres. Open dat dossier; een referral-invoer mag een bestaande grondslag niet overschrijven.", met een knop "Kandidaat openen" die de drawer van die kandidaat opent).

Het scherm onderscheidt die twee op `detail.code` (BV3, geleverd), nooit op de zinstekst: `referral_email_suppressed` respectievelijk `referral_candidate_exists`. Dat tweede antwoord draagt ook `detail.candidate_id`, en dat is wat de knop "Kandidaat openen" gebruikt om de drawer van die kandidaat te openen. Een code die het scherm niet kent, valt terug op `detail.message` in een generieke 409-melding zonder knop (§7.2f).

**Staten.** Tab-laden: drie vlakke blokken. Fout: `setContainerLoadError` op de tab. Leeg bestaat niet: er is altijd een toestemmingsstatus, ook als die "geen" is. Alle drie de modals: primaire knop met spinner tijdens verzenden, inline-melding bij 4xx, toast plus drawerherlading bij succes.

**390.** De drawer is `offcanvas-bottom`; de drie kaarten stapelen; de modals worden fullscreen. De vacaturekiezer blijft een native `<select>`, want dat is op mobiel het beste bedienbare element dat er is.

#### 7.3.3 Plaatsingen

> **Status, september 2026: gebouwd**, als `website/admin/js/sections/placements.js`. Payloads nagelezen tegen `talent-os/backend/routers/placements.py` en `models/schemas.py` (`_PLACEMENT_TYPES`, `_BILLING_BASES`, `_FEE_TYPES`, `_PLACEMENT_STATUSES`, `_money_field()`, `_eor_cost_factor_field()`, `_fee_percentage_field()`, `_expected_billable_hours_field()`, `OneOffCost`), niet tegen deze spec alleen. Vijf as-builtafwijkingen:
> 1. **Geen vrij zoekveld op de backend.** `list_placements` kent alleen `candidate_id` als exacte match, geen ILIKE op naam. Het zoekveld "Kandidaat" lost daarom eerst op: een numerieke invoer gaat direct als `candidate_id` mee; een naam of e-mailadres wordt opgezocht via `GET /v1/admin/candidates?limit=200` (client-side gefilterd) en alleen bij precies één treffer toegepast. Bij nul of meerdere treffers blijft de lijst ongefilterd op dit veld en verschijnt een toelichting onder het veld ("Geen kandidaat gevonden met deze naam." respectievelijk "Meerdere kandidaten gevonden. Verfijn de zoekopdracht of gebruik het kandidaat-ID.").
> 2. **De lijst toont "Kandidaat #`<id>`"** (zoals de bewaartermijnenlijst §7.3.1 al doet voor kandidaten), geen naam: er is geen join op de lijstroute en er bestaat geen goedkope naamslijst om lokaal op te slaan. Opdrachtgever en vacature worden wel met naam getoond, via de al bestaande `GET /v1/admin/clients` (hergebruikt via `Admin.fetchClientOptions`, jobs.js) en `GET /v1/admin/jobs?limit=200` (dezelfde aanpak als de vacaturetitel-opzoeking in candidates.js §7.3.2 afwijking 5).
> 3. **Alleen kandidaat en opdrachtgever hebben een eigen drawer om naar te linken.** `placements.candidate_id` is een `candidates.id` (`_validate_references` SELECTeert rechtstreeks uit `candidates`), dus de kandidaatlink opent altijd kind `sourced`, zonder de ambiguïteit die de kandidatenlijst zelf wel kent. Er bestaat geen vacaturedrawer in dit paneel; de vacature staat in de Overzichttab als platte tekst.
> 4. **`PlacementUpdate` (PATCH) draagt geen `candidate_id`/`job_id`/`client_id`/`placement_type`.** Die drie relaties en het type zijn dus alleen bij aanmaken in te stellen. Het bewerkmodal toont ze bij bewerken als alleen-lezen samenvatting (met de zin "Kandidaat, opdrachtgever, vacature en type zijn na het aanmaken niet meer te wijzigen."), niet als selects, en de PATCH-payload bevat die vier velden nooit.
> 5. **`.modal-lg` is hier `wide: true` op `ui.modal`**, dezelfde 760px breedte (`a-modal--wide`, admin.css) die het Opdrachtgevers-detailpaneel al gebruikt. Functioneel hetzelfde component als de spec bedoelt; er bestaat geen letterlijke `.modal-lg`-klasse in dit paneel.
>
> Verwijderen bewijst het contract van §7.2f ook waar de echte backend het niet doet: `DELETE /{id}` geeft zelf alleen 404 met een platte string, maar `Admin.errorDetail()` behandelt zowel die vorm als een `{code, message}`-object generiek, en `scripts/admin_sections_check.py` toetst dat pad met een gestubde 409 (`placement_delete_conflict`) die de modal open houdt tot de tweede, juiste poging slaagt.
>
> Bewaakt door `scripts/admin_sections_check.py` (lijst met 60 rijen naast de paginagrootte, server-side sortering en filters, drawer met de drie tabs, statuswisseling gewoon en destructief naar geannuleerd, marge met null-invoer/herberekenen/ongeldig bedrag, aanmaken en bewerken met komma-decimalen en de onwijzigbare FK-set, verwijderen met een 409 en het juiste ID, 500 met retry) en `scripts/admin_pagination_check.py` (60 rijen, page 1 versus page 2).

*Nieuwe sectie*, hash `#placements`, in de sidebargroep Jobs, onder Opdrachtgevers. Menu-item "Plaatsingen".

**Endpoints.** `GET /api/v1/admin/placements?status=&candidate_id=&job_id=&client_id=&limit=&offset=`, `GET .../{id}`, `POST .../` , `PATCH .../{id}`, `POST .../{id}/status`, `DELETE .../{id}`, plus `GET .../{id}/margin?gross_monthly_salary=&annual_salary=`.

**Wireframe (lijst).** Datatabel (§7.2a), zonder rijselectie (er zijn geen bulkacties op plaatsingen).

```
[ Filterbalk ]  status-select (Alle | Concept | Actief | Beëindigd | Geannuleerd)
                opdrachtgever-select · zoekveld op kandidaat
                                                   [ Nieuwe plaatsing ]
Kandidaat | Opdrachtgever | Vacature | Type | Start | Einde | Status | ⋯
Kandidaat #1482 | Vectron Systems | Senior Embedded | Detachering | 1 okt 2026 | — | Actief | ⋯
```

`placement_type` wordt getoond als "Werving & selectie" of "Detachering" (de twee waarden uit `_PLACEMENT_TYPES`). Datums in `.gsp-num`. Een ontbrekende `end_date` is een streepje, geen "onbekend".

**Wireframe (detail).** Drawer (§7.2b) met drie tabs.

- **Overzicht**: kandidaat, vacature en opdrachtgever elk als link naar hun eigen drawer; type; start- en einddatum; status met de statuswisselaar; `notes`.
- **Financieel**: `billing_basis` ("Vast maandbedrag" of "Per uur"), `hourly_bill_rate`, `expected_billable_hours`, `monthly_purchase_price`, `eor_partner`, `eor_cost_factor`, `fee_type` ("Percentage" of "Vast bedrag"), `fee_percentage`, `fee_amount`, en `one_off_costs` als lijst van label plus bedrag met een totaalregel. Alle bedragen in `.gsp-num`, met het euroteken, twee decimalen, en `font-variant-numeric: tabular-nums` zodat kolommen uitlijnen. Lege velden tonen "n.v.t.", niet 0.
- **Marge**: de uitkomst van `GET .../{id}/margin`, met bovenaan een niet-weg-te-klikken inline-melding van het type waarschuwing: **"Voorlopig. Deze berekening is nog niet door de eigenaar vastgesteld en mag niet naar buiten."** De backend zet zelf `provisional: true` op elk antwoord; het scherm herhaalt dat zichtbaar. Twee invoervelden boven de uitkomst (`gross_monthly_salary` bij detachering, `annual_salary` bij werving & selectie), met een "Herberekenen"-knop; de uitkomst (`revenue`, `cost`, `margin`, `margin_pct`, `fee`) verschijnt eronder in een `.gsp-panel`. `null` is hier "n.v.t. (invoer ontbreekt)", nooit 0.

**Aanmaken en bewerken.** Formulierpatroon (§7.2d) in een modal (`.modal-lg`). Verplicht bij aanmaken: `candidate_id`, `job_id`, `client_id` (drie selects, elk gevuld uit de bestaande lijst-endpoints) en `placement_type`. De rest is optioneel. De geldbedragen zijn `type="text"` met `inputmode="decimal"` (niet `type="number"`: dat verminkt decimalen en scrollt met het muiswiel), en worden client-side gevalideerd tegen dezelfde grenzen als de backend: niet-negatief, twee decimalen, maximaal 99.999.999,99; `eor_cost_factor` vier decimalen, maximaal 99,9999; `fee_percentage` maximaal 100; `expected_billable_hours` maximaal 9999,99. Overschrijding geeft de inline foutregel, geen 422 die pas na verzenden komt. `one_off_costs` is een repeater met per regel "Omschrijving" (verplicht, max 120) en "Bedrag", plus "Regel toevoegen" en per regel een verwijderknop.

**Statuswisseling.** `POST .../{id}/status`. Uit een `<select>` in de overzichtstab, gevolgd door een bevestigingsmodal (gewoon, niet destructief) die de oude en nieuwe status naast elkaar zet. Uitzondering: de overgang naar `geannuleerd` gebruikt de destructieve variant zonder getypte bevestiging (een annulering is administratief omkeerbaar, dus geen typebevestiging, maar wel de rode primaire knop).

**Verwijderen.** `DELETE .../{id}` is een soft-delete, maar haalt de plaatsing wel uit elk overzicht. Destructieve modal met getypte bevestiging: het **plaatsings-ID** als cijferreeks. Reden dat het niet `VERWIJDER` is: een ID typen dwingt je te kijken naar wélke plaatsing je verwijdert.

**Staten.** Lijst: laad-, lege- en foutstaat volgens §7.2a; leeg is "Nog geen plaatsingen vastgelegd." plus de knop "Nieuwe plaatsing". Drawer per tab volgens §7.2b.

**390.** Kaartlijst; per kaart kandidaat, opdrachtgever, type en status, plus één knop "Openen". De marge-tab toont op 390px de uitkomst als gestapelde label-waarde-paren, niet als tabel.

#### 7.3.4 Pipeline-stage en -historie in de drawers

*Nieuwe tab* "Pipeline" in zowel de kandidaat- als de klantdrawer.

**Endpoints.** `PATCH /api/v1/admin/pipeline/{entry_id}/stage`, `GET /api/v1/admin/pipeline/{entry_id}/history`.

**De entries komen uit `GET /api/v1/admin/pipeline`** (BV1, geleverd), met `?candidate_id=`, `?client_id=`, `?job_id=` en `?stage=` als filters plus `limit` (1 tot 200, standaard 50), `offset` en `total`. De kandidaatdrawer vraagt `?candidate_id=`, de klantdrawer `?client_id=`. De rijvorm is letterlijk dezelfde als die van `GET /api/v1/client/pipeline` (één gedeelde SELECT en projectie), dus `id`, `client_id`, `candidate_id`, `job_id`, `stage`, `notes`, de tijdstempels, `full_name`, `current_title`, `current_company`, `location`, `skills` en `job_title`. Het `id` uit die rij is het `entry_id` voor `PATCH .../{entry_id}/stage` en `GET .../{entry_id}/history`.

**De naam staat er wel, en dat is een verschil met het klantportaal.** De presentatietoestemmingspoort op `full_name` staat **uit** voor de adminroute en **aan** voor de klantroute (besluit van de chief-of-staff, nog te bevestigen door de eigenaar; zie §7.6). De poort is een openbaarmakingsbeperking richting een werkgever, geen interne toegangsbeperking: hetzelfde beheerderstoken leest `full_name` onvoorwaardelijk uit `GET /admin/candidates`, één klik verderop. In de admindrawer staat de naam er dus altijd; in de kanban van het klantportaal (§7.3.8a) blijft de poort staan en toont een entry zonder toestemming het geanonimiseerde label.

Nodig: `GET /api/v1/admin/pipeline?candidate_id=&client_id=&job_id=&limit=&offset=`, admin-JWT, dezelfde rijvorm als de klantroute plus `client_id`. **Tot die route bestaat, wordt deze tab alleen in het klantportaal gebouwd** (waar `GET /client/pipeline` de entries wel levert) en blijft hij in de admindrawer achterwege. Er wordt geen tab getoond die zijn eigen inhoud niet kan ophalen.

**Wireframe.**

```
PIPELINE
┌ Vacature: Senior Embedded Engineer (#218) ──────────────┐
│ Huidige fase:  [ Screening        ▾ ]   [ Fase wijzigen ]│
│ Laatst gewijzigd: 3 sep 2026 door Sanne de Wit           │
│ ── Historie ───────────────────────────────────────────  │
│ ● 3 sep 2026 14:20  Benaderd → Screening   Sanne de Wit  │
│ ● 28 aug 2026 09:05  (nieuw) → Benaderd    Gebruiker #12 │
└──────────────────────────────────────────────────────────┘
(één kaart per pipeline-entry; bij meer dan drie entries een
 accordeon met alleen de nieuwste opengeklapt)
```

**De canonieke faselijst.** `pipeline_entries.stage` is `VARCHAR(50)` met default `sourced` en zonder CHECK-constraint; het klantportaal tekent vandaag vier vaste kolommen (`new`, `screening`, `interview`, `offer`) en stopt alles wat daarbuiten valt stil in `new`. De vastgestelde lijst is (§7.6, besluit 2):

| Waarde | Label |
|---|---|
| `sourced` | Gesourced |
| `new` | Nieuw |
| `screening` | Screening |
| `interview` | Gesprek |
| `offer` | Aanbod |
| `placed` | Geplaatst |
| `rejected` | Afgewezen |

Die zeven zijn de enige waarden die de `<select>` aanbiedt, in deze volgorde, in het paneel en in beide portalen.

Migratie 043 (BV8, geleverd) legt ze vast: eerst normaliseren (trim en lowercase, de bekende afwijkers naar hun juiste fase, en daarna een vangnet-UPDATE die alles wat dan nog buiten de zeven valt op `sourced` zet), dan de CHECK-constraint als `NOT VALID`. `NOT VALID` slaat alleen de tabelscan bij het toevoegen over; de constraint geldt vanaf dat moment wel voor elke INSERT en elke UPDATE. `VALIDATE CONSTRAINT` is een aparte eigenaarsstap, met een eigen lock en een eigen venster.

**De "(bestaande waarde)"-ontsnappingsklep blijft staan tot `VALIDATE` op productie is gedraaid.** Reden: pas dan is bewezen dat elke rij aan de zeven voldoet. Zolang de constraint `NOT VALID` is, wordt een fase buiten de zeven toegevoegd als geselecteerde optie met dat achtervoegsel, en schrijft de UI nooit stilzwijgend een fase weg die zij niet kent. Na `VALIDATE` vervalt de optie en is de select gesloten. Dat is één regel in de UI-code, achter één vlag; het draaiboek voor de eigenaarsstap staat onderaan `migrations/043_pipeline_stage_check.py`.

De historie toont elke `from_stage` en `to_stage` door dezelfde labelmap, met de ruwe waarde als er geen label is.

**Fase wijzigen.** Select plus knop, geen automatische opslag bij het wisselen van de select: een fasewijziging schrijft een onomkeerbare regel in `pipeline_stage_history` en verdient één bewuste klik. Optimistische update met terugdraaien bij fout: de nieuwe fase verschijnt direct, en bij een 4xx of 5xx springt hij terug met een inline-melding boven de kaart. Na succes wordt de historie opnieuw opgehaald, niet lokaal aangevuld, zodat wat er staat uit de database komt.

**Historie.** Verticale tijdlijn: 2px `--navy-600`-lijn links, per item een 8px stip in `--navy-300` (`--gold-500` voor het nieuwste), tijdstempel in `.gsp-num.fs-xs`, dan "&lt;van&gt; → &lt;naar&gt;", dan de actor. `from_stage: null` toont als "(nieuw)". Maximaal tien items zichtbaar, daarna "Toon alles".

**De actor krijgt een naam.** `GET .../history` levert `changed_by_name` naast `changed_by` (BV7, geleverd), via een `LEFT JOIN` op `users`. Het scherm toont die naam. De join is bewust `LEFT`: een historieregel is append-only en overleeft het account dat hem schreef, dus `changed_by_name` kan `null` zijn voor een gewiste of verwijderde beheerder. In dat geval toont de tijdlijn "Gebruiker #&lt;changed_by&gt;", en wanneer `changed_by` zelf ook leeg is "Onbekend". Nooit een lege plek waar een actor hoort te staan.

**Staten.** Laden: drie vlakke blokken op de tijdlijnposities. Leeg (entry zonder historie, kan niet voorkomen maar wordt afgevangen): "Nog geen fasewijzigingen vastgelegd." Fout: `setContainerLoadError` op de historie alleen; de huidige fase en de wisselaar blijven bruikbaar.

**390.** Eén kaart per entry op volle breedte, select en knop gestapeld, de tijdlijn behoudt zijn vorm (die werkt smal beter dan een tabel).

#### 7.3.5 AVG: wissen en suppressielijst

*Nieuwe sectie*, hash `#gdpr`, in de sidebargroep System, onder Bewaartermijnen. Menu-item "AVG".

**Endpoints.** `POST /api/v1/admin/gdpr/erase`, `POST /api/v1/admin/suppression`, `GET /api/v1/admin/suppression?limit=&offset=`.

**Wireframe.**

```
┌ Persoon wissen (art. 17) ───────────────────────────────┐
│ Waarschuwing (inline, permanent):                        │
│  "Dit wist alle persoonsgegevens van dit adres uit alle  │
│   tabellen. Dit is niet ongedaan te maken."              │
│ E-mailadres  [                              ]            │
│                                    [ Zoeken en wissen ]  │
└─────────────────────────────────────────────────────────┘
┌ Suppressielijst ────────────────────────────────────────┐
│ [ Adres toevoegen ]      zoekveld op domein              │
│ Domein | Reden | Toegevoegd op | Hash (ingekort)         │
│ voorbeeld.nl | STOP | 3 sep 2026 | a3f9…21c              │
│ [ paginering ]                                           │
└─────────────────────────────────────────────────────────┘
```

**Wissen.** Eén tekstveld en één knop. De knop opent de destructieve modal (§7.2c). Body: het ingevoerde adres, en een `.gsp-panel` met de opsomming van wat er gebeurt (kandidaatgegevens, prospectgegevens, portalaccount, sollicitaties, berichten; anonimiseren dan wel verwijderen per tabel). **Getypte bevestiging: het volledige e-mailadres**, letterlijk zoals ingevoerd, hoofdletterongevoelig na `trim()` en `toLowerCase()`. Dit is de enige plek in dit systeem waar de te typen tekenreeks geen vaste tekst is, en dat is bewust: het adres is precies wat je niet mag verwisselen.

**De backend eist die getypte bevestiging zelf** (BV9, geleverd). `AdminEraseRequest.confirm` is het e-mailadres, geen booleaan: het endpoint vergelijkt `confirm` met `email` na strip en lowercase, en weigert met 422 en `detail.code = "erase_confirm_must_match_email"` wanneer ze niet gelijk zijn. Die controle draait vóór elke opzoeking, dus een mismatch verraadt niet of het adres bestaat. Het scherm stuurt daarom wat de beheerder heeft getypt door als `confirm` en blokkeert de knop al client-side; de 422 is het vangnet, niet het eerste signaal. Zo is elke cliënt aan dezelfde drempel gebonden, ook een routine, en herhaalt de UI de regel in plaats van hem in zijn eentje te dragen.

De beheerders- en zelfbevestiging is een aparte vraag met een apart veld, **`confirm_admin_or_self`** (booleaan). Twee vragen, twee antwoorden.

`confirm_admin_or_self: true` wordt **niet** standaard meegestuurd. De eerste aanroep gaat zonder. Geeft de backend 409 met `detail.code = "erase_admin_or_self_requires_confirm"`, dan verschijnt in de modal een tweede, aparte bevestiging: een inline-melding van het type waarschuwing met de tekst "Dit adres hoort bij een beheerdersaccount of bij je eigen account. Wissen verwijdert die toegang." plus een aan te vinken checkbox "Ik begrijp dat hiermee beheerderstoegang verdwijnt" en pas dan een tweede knop die de aanroep herhaalt met `confirm_admin_or_self: true`. Twee stappen, niet één vinkje vooraf.

**Suppressielijst.** Datatabel zonder selectie, met gewone paginering: `GET /api/v1/admin/suppression` geeft `items`, `total`, `limit` (standaard 100, maximaal 500) en `offset` (BV5, geleverd), dezelfde vorm als elke andere adminlijstroute, dus `renderPagination` werkt hier zoals overal. Boven de tabel staat "NN van MMM".

De API geeft bewust **geen** plaintext-adressen terug, alleen `email_hash`, `email_domain`, `reason` en `created_at`. Het scherm toont dus domein en een ingekorte hash (eerste vier en laatste drie tekens, met de volledige hash in een `title` en een kopieerknop). Er staat boven de tabel één regel uitleg: "Deze lijst bewaart geen volledige e-mailadressen; alleen een onomkeerbare hash en het domein." Dat voorkomt de terugkerende vraag waarom je hier niet op adres kunt zoeken.

**Toevoegen.** Modal met "E-mailadres" (verplicht) en "Reden" (standaard `STOP`, vrij tekstveld). Het is geen destructieve modal, maar wel met een prominente `.gsp-panel` die zegt wat er verder gebeurt, want de backend doet meer dan één ding: de openstaande concept-outreach naar dit adres wordt afgekeurd, de kandidaatrij krijgt `consent_withdrawn_at`, en de prospectrij krijgt `opt_out_at`. Die drie gevolgen staan er woordelijk, want een beheerder die "toevoegen aan lijst" leest verwacht ze niet.

**Staten.** Wisformulier: rust, validatie op e-mailvorm bij `blur`, laadstaat op de knop, inline-melding bij fout, en bij succes een toast plus een resultaatblok dat toont wat er is geraakt (de respons van `erase_person()`). Suppressielijst: standaard laad-, lege- ("Nog geen adressen op de suppressielijst.") en foutstaat.

**390.** Beide kaarten op volle breedte gestapeld. De suppressietabel wordt een kaartlijst met domein groot en hash klein. De wismodal is fullscreen; het bevestigingsveld krijgt `type="email"`, `autocapitalize="off"`, `autocorrect="off"` en `spellcheck="false"`, want een mobiel toetsenbord dat een adres corrigeert maakt de bevestiging onmogelijk te typen.

#### 7.3.6 Users: deblokkeren, activiteitentab, prospects bewerken, healthwidget

Vier kleinere toevoegingen aan bestaande secties.

**(a) Deblokkeren.** `POST /api/v1/admin/users/{user_id}/unlock`. In het rijactiemenu van de gebruikerslijst komt een item "Deblokkeren", direct boven "Impersonate". Het is alleen ingeschakeld wanneer de gebruiker daadwerkelijk vergrendeld is; de gebruikerslijst moet dus `locked_until` en `failed_login_count` tonen.

`GET /api/v1/admin/users` geeft `failed_login_count` en `locked_until` mee (BV2, geleverd), dus de lijst ziet de vergrendeling zonder een tweede aanroep en de rijactie kan correct in- of uitgeschakeld staan. Beide kolommen zijn ook sorteerbaar (`sort=locked_until`, `sort=failed_login_count`), zodat een beheerder de vergrendelde accounts bovenaan kan zetten in plaats van ze te zoeken. Een vergrendelde gebruiker krijgt in de statuskolom een tweede badge "Vergrendeld" (familie negatief) met in `.fs-xs.a-soft` eronder "tot &lt;tijdstip&gt;". Deblokkeren gaat via een gewone bevestigingsmodal, geen typebevestiging: het is een herstellende handeling. De modal zegt er wel bij wat het niet doet: "Dit reset geen wachtwoord en beëindigt geen bestaande sessie."

**(b) Activiteitentab.** Nieuwe tab "Activiteit" in de kandidaat- en klantdrawer, gevoed door `GET /api/v1/admin/activities?subject_type=&subject_id=`. Weergave: dezelfde verticale tijdlijn als §7.3.4, met per item het type als chip (de zes waarden uit `ACTIVITY_TYPES`: `note` = Notitie, `call` = Telefoongesprek, `email` = E-mail, `meeting` = Afspraak, `task` = Taak, `status_change` = Statuswijziging), het tijdstempel in `.gsp-num.fs-xs`, de tekst, en de actor. Bovenaan de tab een compact formulier "Activiteit toevoegen" met typeselect, een `<textarea>` en één knop; het klapt uit vanaf een tekstknop en staat niet permanent open. Een taak (`type: "task"`) toont daarnaast zijn afgerond-staat als checkbox die `PATCH /activities/{id}` aanroept. Leeg: "Nog geen activiteiten vastgelegd." plus de knop die het formulier opent.

**(c) Prospects bewerken.** De prospectlijst (sectie Leads) krijgt een bewerkactie die `PUT /api/v1/admin/prospects/{id}` aanroept, in een modal met het formulierpatroon. Bewerkbaar: `status` (vrije tekst met een `<datalist>` van de waarden die in de huidige lijst voorkomen, want de kolom kent geen CHECK en er is geen canonieke lijst; het scherm verzint er geen), `notes` (schrijft naar `client_prospects.intent_signal`, er is geen aparte notitiekolom), `source_url` en `lawful_basis`.

**Een statuswijziging verzet een bewaaranker, en dat staat op het scherm.** `PUT /prospects/{id}` stempelt bij elke `status`-wijziging ook `last_contacted_at = NOW()`, en dat is precies het anker waarop de retentiecategorie "Prospect die wel reageert (relatie)" rekent. Onder het statusveld staat daarom vast: "Een statuswijziging legt vast dat er vandaag contact was. Dat verzet de bewaartermijn van dit contact met twaalf maanden." Geen bijzin, geen tooltip.

**Geen lege optie in de selects.** De backend doet `model_dump(exclude_none=True)`: een veld dat als `null` wordt meegestuurd valt uit de update en een leeg formulier geeft 400 "No fields to update". Het formulier stuurt daarom alleen de velden die daadwerkelijk zijn gewijzigd, en de `lawful_basis`-select heeft geen lege optie: leeglaten is geen handeling die dit endpoint kent. `lawful_basis` is een `<select>` met de drie gevalideerde waarden uit §7.2e, verplicht, met de hint boven het veld: "Zonder vastgelegde grondslag mag er geen outreach naar dit contact (Telecommunicatiewet art. 11.7)." `source_url` valideert client-side op `http://` of `https://`, dezelfde eis als de backend, met de foutregel "Vul een publieke http- of https-URL in".

**(d) Healthwidget.** Nieuwe kaart op het dashboard, rechterkolom, onder Quick Actions. Bron: `GET /api/v1/admin/health`. Vier regels, elk met een statusstip en een waarde: database, OpenRouter, Apollo, en **dubbele profielkoppelingen** (`duplicate_profile_links`). Die laatste is de reden dat de kaart bestaat: hij hoort altijd 0 te zijn, en elke andere waarde betekent dat een kandidaat vanuit meer dan één profielrij gekoppeld is, iets wat de deduplicatie in de kandidatenlijst niet zelf repareert. Weergave: bij 0 een groene stip en "0 dubbele profielkoppelingen", zonder nadruk. Bij een waarde groter dan 0 wordt de hele kaart een inline-melding van het type fout met de tekst "NN dubbele profielkoppelingen. Dit hoort 0 te zijn." plus de knop "Kandidaten openen". Bij `null` (de query kon niet draaien): "Onbekend" in `.a-soft`, niet 0. `candidates_count` en `open_jobs` uit dezelfde respons horen niet in deze kaart: die staan al in de KPI-rij en twee keer hetzelfde getal op één scherm nodigt uit tot vergelijken van dingen die gelijk zijn.

#### 7.3.7 Job-alertschakelaar in het kandidatenportaal

*Uitbreiding van* `#settings` in `website/candidate/`.

**Endpoint.** `PUT /api/v1/candidate/job-alerts`, met respons `{ enabled, eligible, job_alert_optin_at, job_alert_unsubscribed_at }`.

**Wireframe.**

```
┌ Vacature-alerts ────────────────────────────────────────┐
│ [ (o) ]  Stuur mij een bericht bij een passende vacature  │
│         Aangezet op 3 september 2026                     │
│                                                          │
│ ⚠ Er gaan op dit moment geen alerts uit                  │
│   Je toestemming voor de talentpool is verlopen. Verleng │
│   die hieronder, dan starten de alerts weer.             │
│                                    [ Toestemming verlengen ] │
└─────────────────────────────────────────────────────────┘
```

**De twee velden zijn niet hetzelfde en het scherm behandelt ze niet hetzelfde.** `enabled` is wat deze persoon heeft gevraagd; `eligible` is of wij het vandaag ook kunnen doen. De schakelaar toont `enabled` en niets anders: hij springt nooit terug omdat `eligible` false is, want dan zou de UI de wens van de gebruiker overschrijven. Wanneer `enabled === true && eligible === false` verschijnt onder de schakelaar een inline-melding van het type waarschuwing met de kop "Er gaan op dit moment geen alerts uit" en één regel uitleg plus, waar mogelijk, de knop die het oplost.

De backend geeft geen reden mee, alleen de booleaan, maar `GET /api/v1/candidate/profile` levert nu wel de zes velden waaruit de reden af te leiden is: `consent_talentpool_at`, `consent_talentpool_until`, `consent_scope`, `consent_source` en, sinds BV4 (geleverd), `consent_withdrawn_at` en `lawful_basis`. Daarmee zijn alle drie de oorzaken benoembaar.

`JOB_ALERT_ELIGIBILITY_SQL` (`core/retention.py`) eist vier dingen tegelijk: geen ingetrokken toestemming, een niet-verwijderde rij met e-mailadres, en dan `consent_scope = 'matching_and_contact' OR lawful_basis = 'portal_registratie'`, plus `lawful_basis = 'portal_registratie' OR consent_talentpool_until > NOW()`. Het scherm loopt die voorwaarden in dezelfde volgorde na en toont precies één regel:

1. Toestemming ingetrokken (`consent_withdrawn_at` gevuld): "Je hebt je toestemming ingetrokken. Zonder toestemming kunnen wij geen vacatures sturen." Knop: "Toestemming opnieuw geven".
2. Toestemming verlopen (`lawful_basis !== 'portal_registratie'` en `consent_talentpool_until` gevuld en in het verleden): "Je toestemming voor de talentpool is verlopen." Knop: "Toestemming verlengen".
3. Omvang beperkt tot matching (`lawful_basis !== 'portal_registratie'` en `consent_scope !== 'matching_and_contact'`): "Je toestemming staat op alleen matching. Voor alerts is ook toestemming voor contact nodig." Knop: "Omvang aanpassen".
4. Geen van drieën: "Wij kunnen op dit moment geen alerts sturen. Neem contact op als dit onverwacht is." Geen knop, wel de contactlink.

De `lawful_basis`-controle in geval 2 en 3 hoort erbij: wie op zijn eigen portalaccount staat (`portal_registratie`, art. 13) voldoet altijd aan die twee clausules, dus een verlopen of beperkte talentpooltoestemming is voor die persoon niet de oorzaak. Geval 4 blijft bestaan als eerlijke terugval voor alles wat het portaal niet kan zien, bijvoorbeeld een ontbrekend e-mailadres op de kandidaatrij.

**Staten.** Rust: schakelaar aan of uit. Wisselen: de schakelaar gaat direct om (optimistisch) en krijgt `aria-busy="true"`; bij een fout springt hij terug met een inline-melding "Kon de instelling niet opslaan, probeer opnieuw" en een retryknop. De schakelaar is nooit `disabled` tijdens het verzenden (dan verliest hij focus), alleen `aria-busy`. Laden bij binnenkomst: schakelaar in laadstaat als vlak blok, label blijft staan. Fout bij binnenkomst: `setContainerLoadError` op de kaart.

**Toetsenbord en aria.** De schakelaar is een `<input type="checkbox" role="switch">` met een echt `<label>`, niet een gestileerde `<div>`. Space wisselt. De waarschuwing eronder is `aria-live="polite"` zodat een schermlezer hoort dat de alerts niet uitgaan, ook als de gebruiker zojuist zelf de schakelaar omzette.

**390.** Schakelaar en label op één rij met het label rechts, minimaal 44px hoog; de waarschuwing eronder op volle breedte, de knop erin volle breedte.

#### 7.3.8 Klantportaal: kanban, analytics, contacten, activiteiten, team

**(a) Kanban met stagewijziging.** `GET /api/v1/client/pipeline`, `PATCH /api/v1/client/pipeline/{entry_id}/stage`. Vandaag tekent `app.js` vier vaste kolommen (`new`, `screening`, `interview`, `offer`) en dumpt elke onbekende fase stil in `new`. Dat blijft niet zo. De kanban krijgt de zeven kolommen van de canonieke faselijst uit §7.3.4, in die volgorde: Gesourced, Nieuw, Screening, Gesprek, Aanbod, Geplaatst, Afgewezen. Een entry met een fase daarbuiten krijgt een eigen kolom achteraan met de ruwe waarde als kop en een `title` "Fase buiten het standaardoverzicht"; die kolom verdwijnt zodra `VALIDATE CONSTRAINT` op de CHECK uit migratie 043 is gedraaid, om dezelfde reden als de "(bestaande waarde)"-optie in §7.3.4. Niets wordt stilzwijgend verplaatst.

Kolomkop: fasenaam plus telling in `.gsp-num`. Kaart per entry: kandidaatnaam of, zonder presentatietoestemming, het geanonimiseerde label (de poort staat hier **aan**, anders dan op de adminroute, zie §7.3.4 en §7.6), daaronder de vacaturetitel in `.fs-xs.a-soft`, daaronder de laatste wijzigingsdatum. **Stagewijziging gaat niet via slepen.** Elke kaart heeft rechtsboven een `<select>` met de zeven fasen plus, zolang `VALIDATE` niet is gedraaid, de bestaande waarde bij een fase daarbuiten (dezelfde ontsnappingsklep als §7.3.4). Slepen is op een telefoon onbruikbaar, met een toetsenbord onbereikbaar zonder een tweede, parallelle bediening, en het is hier geen frequente handeling. Optimistische verplaatsing met terugdraaien bij fout, toast bij succes.

Staten: laden = zeven kolomkoppen met elk twee vlakke kaartblokken; leeg per kolom = "Geen kandidaten in deze fase" in `.fs-xs.a-soft`; leeg over de hele kanban = één kaart "Er staan nog geen kandidaten in de pipeline." plus de knop "Vacature plaatsen"; fout = `setContainerLoadError` over de hele kanban, want een halve kanban is misleidend. Op 390px worden de kolommen een verticale accordeon met de fasenaam plus telling als kop, de eerste fase met inhoud opengeklapt.

Zeven kolommen passen op 1440 niet naast elkaar zonder onleesbaar te worden: de rij scrollt daarom horizontaal (`overflow-x: auto`, kolombreedte 260px, `scroll-snap-type: x proximity`), met de kolomkoppen sticky bovenaan. Dat is de enige plek in dit document waar horizontaal scrollen bewust is, en het is een kanban, dus dat leest als het patroon dat het is.

**(b) Analytics: alleen velden met een bron.** `GET /api/v1/client/analytics` geeft vijf velden. Het scherm toont er precies vijf, elk met een KPI-tegel (§7.2g) of een klein staafoverzicht, en niets erbij:

| Veld | Weergave | Bij `null` of leeg |
|---|---|---|
| `time_to_hire_avg_days` | Tegel, "NN,N dagen" | "n.v.t. (nog geen vervulde vacature)" |
| `pipeline_funnel` | Horizontale staven per fase, label uit dezelfde fasemap als de kanban | "Nog geen kandidaten in de pipeline" |
| `source_breakdown` | Horizontale staven per herkomst, labels uit §7.2e (de backend groepeert al op `SOURCE_FAMILY`) | "Nog geen herkomstgegevens" |
| `offer_rate` | Tegel, "NN,N%" | Bij nul sollicitaties geeft de backend 0; het scherm toont dan "n.v.t. (nog geen sollicitaties)", want 0% uit nul metingen is geen percentage |
| `cost_per_hire_avg` | Tegel, bedrag | **"n.v.t."**, met eronder in `.fs-xs.a-soft`: "Wordt pas getoond zodra er kostengegevens per plaatsing zijn vastgelegd." |

`cost_per_hire_avg` is in de backend expliciet een placeholder (gemiddelde `fee_value` van vervulde vacatures) en is bij ontbrekende gegevens `null`. Er wordt geen schatting, geen branchegemiddelde en geen 0 getoond. Geen enkel getal op dit scherm wordt afgeleid of geëxtrapoleerd; wat de API niet teruggeeft, staat er niet.

**(c) Contacten en activiteiten.** Twee nieuwe kaarten in `#settings` van het klantportaal. Contacten leest en schrijft via de bestaande `client_contacts`-routes; per contact naam, functie, e-mail en telefoon, met bewerken en verwijderen in een modal. Activiteiten gebruikt `GET`/`POST /api/v1/client/activities`, met dezelfde tijdlijn en dezelfde zes typechips als §7.3.6(b), en toont uitsluitend de activiteiten van de eigen klantorganisatie. Beide kaarten: standaard laad-, lege- en foutstaat.

**(d) De teamtabel met dubbele kolomkoppen.** `website/client/index.html:359-370` heeft acht `<th>`-cellen voor vijf kolommen, omdat Naam, Rol en Status elk twee koppen hebben (`.lang-en` en `.lang-nl`) en de laadrij `colspan="5"` gebruikt. Beide talen staan altijd in de DOM en worden per taal op `display` gezet, dus in de kop staan visueel vijf cellen, maar de tabelstructuur telt er acht. Voor een schermlezer betekent dat acht kolomkoppen boven vijf datacellen: de koppeling tussen cel en kop klopt niet meer.

Vast: één `<th>` per kolom, met de twee taalspans **binnen** die ene cel:

```html
<th scope="col"><span class="lang-nl">Naam</span><span class="lang-en">Name</span></th>
```

Dat is de conventie die §8.x.0 al voorschrijft (beide spans altijd in de DOM, `initLang()` toggelt `display`), alleen nu op het juiste niveau toegepast. Elke `<th>` krijgt `scope="col"`; de laadrij, lege rij en foutrij krijgen `colspan="5"`, wat dan ook klopt. Dezelfde controle geldt voor elke andere tabel in beide portalen: een `colspan` die niet gelijk is aan het aantal `<th>`-cellen is een fout, geen stijlkwestie. `scripts/css_class_census.py` krijgt hiervoor een controle die faalt bij een mismatch.

---

### 7.4 Toegankelijkheid en toetsenbord: harde eisen

Deze zes zijn geen streven. Een PR die er een breekt, gaat terug.

1. **Focustrap in modal en drawer.** `window.bootstrap.Modal` en `window.bootstrap.Offcanvas` (doorgezet vanuit de gevendorde Tabler 1.4-bundel) leveren die; de eigen overlay in `admin.js` niet, en die verdwijnt daarom (§7.2c). Tab loopt rond binnen het geopende element en bereikt niets erachter.
2. **ESC sluit** elke modal, elke drawer en elk actiemenu (`.action-menu`, dat vandaag alleen op een klik buiten zichzelf reageert). Bij een openstaand formulier met wijzigingen komt eerst de bevestiging "Wijzigingen weggooien?"; ESC op die bevestiging annuleert het sluiten, niet het formulier.
3. **Focus keert terug.** Bij het sluiten van een modal, drawer of menu gaat de focus terug naar het element dat het opende. Een lijst die na een actie herlaadt, herstelt de focus op de rijactie van dezelfde record; is die record weg (verwijderd, verwerkt), dan gaat de focus naar de tabelkop en kondigt een `aria-live="polite"`-regio aan wat er gebeurd is.
4. **Tabvolgorde volgt de leesvolgorde.** Nergens een `tabindex` groter dan 0. Geen element dat er klikbaar uitziet zonder tab-bereikbaar te zijn, en geen tab-stop zonder zichtbare focusstaat. Elke `:hover`-staat in dit document heeft een identieke `:focus-visible`-staat (§8.x.0); dat wordt met tab-navigatie geverifieerd, niet visueel geschat.
5. **Contrast op donker.** De vloeren uit §7.1.2 gelden zonder uitzondering: tekst minimaal 4,5:1 (grote tekst 3:1), niet-tekstuele grenzen en icoonvormen minimaal 3:1. `--navy-300` is geen tekstkleur. `--gold-ink` is op donker verboden. `scripts/css_tokens_check.py` (§8.x.8) krijgt een tweede tabel met de donkere achtergrond als referentie, zodat een tokencombinatie die op wit slaagt en op navy zakt de build laat falen.
6. **`prefers-reduced-motion`.** Elke overgang in dit document is 150 tot 200ms en betreft uitsluitend kleur, positie of dekking van al zichtbare elementen. Bij `reduce` gaan alle duren naar 0,01ms en blijft elke eindtoestand functioneel en visueel compleet: geen skeleton met shimmer, geen toast die zonder animatie onzichtbaar blijft, geen drawer die alleen ingeschoven bestaat. De globale regel staat in `website/styles.css` (het `@media (prefers-reduced-motion: reduce)`-blok vanaf regel 1652). Het adminpaneel laadt `styles.css` niet en heeft daarom een eigen kopie; *gebouwd in* `website/admin/admin.css`, niet in `theme.css`. Dat is bewust: `theme.css` is de tokenlaag die de drie portalen delen, en een `*`-regel met `!important` is geen token. Zodra het kandidaat- en klantportaal dezelfde regel nodig hebben, verhuist hij naar één gedeeld bestand.

Daarnaast: elke tabel heeft `<caption>` of een `aria-label` die zegt waar hij over gaat; elke `<th>` heeft `scope`; elk pictogram is `aria-hidden="true"` met de betekenis in de tekst ernaast; elk formulierveld heeft een echt gekoppeld `<label>`, nooit alleen een `placeholder`.

---

### 7.5 Wat niet verandert

1. **Hash-routing en één SPA per surface.** `website/admin/`, `website/candidate/` en `website/client/` blijven elk één HTML-bestand met secties die op `window.location.hash` wisselen. De nieuwe secties (`#retention`, `#placements`, `#gdpr`) zijn nieuwe `.portal-section`-blokken in hetzelfde bestand, geen nieuwe pagina's en geen router.
2. **CSP zonder `unsafe-inline` voor scripts.** Geen inline `<script>`, geen `onclick`, geen `javascript:`-URL, geen `new Function` of `eval`. Gedrag hangt uitsluitend aan `data-action` plus gedelegeerde listeners. Inline `style=` is toegestaan (de CSP staat dat toe) maar wordt uitgefaseerd volgens §7.1.3; het aantal mag per PR alleen dalen.
3. **Geen nieuwe externe origins.** Geen extra CDN, geen extra lettertypeleverancier, geen icoonservice, geen analytics. Wat er nodig is, wordt gevendord onder `website/admin/vendor/` zoals ApexCharts en Tabler dat al zijn. De bestaande Google-Fonts-verbinding blijft, ongewijzigd.
4. **Alles uit de API gaat door `GSP.esc`.** In de praktijk: elke waarde die uit een respons komt, wordt geïnterpoleerd in een `html\`\``-template, nooit met stringconcatenatie in `innerHTML` gezet. `raw()` uitsluitend voor markup die volledig uit eigen, statische strings bestaat. Elke URL uit een respons gaat door `GSP.safeUrl`. Dat geldt ook voor de nieuwe schermen, inclusief `signal_missing_nl`, `evidence`, `notes` en elke andere vrije tekst die een beheerder ooit heeft ingetypt.
5. **Outreach blijft draft-only** en blog-publiceren blijft een tweede, expliciete handeling. Geen enkel scherm in dit document introduceert een verzendknop die zonder mens verstuurt.
6. **De gevendorde Tabler-bestanden worden niet bewerkt.** Elke aanpassing loopt via `--tblr-*`-variabelen of via een eigen klasse met hogere specificiteit in `index.html`. Wie een Tabler-bestand aanpast, maakt de volgende versieverhoging onmogelijk.

---

### 7.6 Drie besluiten

Deze drie stonden open. Ze zijn genomen door de design-reviewer namens de eigenaar, onder voorbehoud van diens tegenbericht, en zijn hierboven al verwerkt. Ze staan hier bij elkaar omdat ze de bouw sturen en niet in één scherm thuishoren.

1. **Categoriebreed goedkeuren van bewaartermijnen blijft uitgesloten op ≤600px.** Elke andere actie in de goedkeuringslijst werkt daar wel. Op desktop toont de bevestigingsmodal niet alleen het aantal maar ook de rijen die geraakt worden, opgehaald met `GET .../review?status=pending&category=…` op het moment van openen (§7.3.1). Wie een hele categorie goedkeurt, moet hebben kunnen zien wát hij goedkeurt.
2. **De canonieke faselijst is `sourced, new, screening, interview, offer, placed, rejected`** (§7.3.4). Migratie 043 normaliseert de bestaande waarden en zet de CHECK-constraint als `NOT VALID`; `VALIDATE CONSTRAINT` is een aparte eigenaarsstap met een eigen lock. De "(bestaande waarde)"-ontsnappingsklep in de select blijft staan tot `VALIDATE` op productie is gedraaid, en vervalt daarna.
3. **Getypte bevestiging: bij AVG-wissen behouden, bij de droogloop schrappen.** Het adres typen bij een onomkeerbare wissing is een echte waarborg; dezelfde handeling vragen bij een read-only telling leert alleen af dat de handeling iets betekent. Omdat een UI-maatregel alleen deze UI bindt, draagt de backend hem sinds BV9 zelf: `AdminEraseRequest.confirm` is het e-mailadres, en de beheerders- en zelfbevestiging heeft een eigen veld `confirm_admin_or_self` (§7.3.5).

Daar is er één bijgekomen, genomen door de chief-of-staff bij het bouwen van BV1 en **nog te bevestigen door de eigenaar**:

4. **De presentatietoestemmingspoort op `full_name` staat uit voor `GET /api/v1/admin/pipeline` en aan voor `GET /api/v1/client/pipeline`.** `consent_spec_presentation_at` legt vast dat een kandidaat ermee instemt bij een werkgever met naam genoemd te worden voor een specifieke rol; het is een openbaarmakingsbeperking richting die werkgever, geen interne toegangsbeperking. Hetzelfde beheerderstoken leest `full_name` onvoorwaardelijk uit `GET /admin/candidates`, dus de poort op de adminroute hield niemand iets achter en liet alleen de pipelinetab een lege plek tonen waar een naam hoort. Het klantportaal houdt de poort ongewijzigd.

---

### 7.7 Backendvoorwaarden voor WS5: geleverd

De tien backendvoorwaarden die dit ontwerp stelde zijn alle tien gebouwd. Deze sectie is daarmee geen opdracht meer aan `backend-dev` maar een naslagtabel voor de UI-bouwers: per regel wat er nu is, met de exacte parameternamen, veldnamen en foutcodes zoals ze in de code staan. Wat hier niet staat, bestaat niet.

| # | Endpoint | Wat er nu is | Gebruikt door |
|---|---|---|---|
| BV1 | `GET /api/v1/admin/pipeline` | Nieuwe route, admin-JWT. Filters `candidate_id`, `client_id`, `job_id`, `stage` (exacte match); `limit` 1 tot 200 (standaard 50), `offset`; respons `{items, total, limit, offset}`. Rijvorm gedeeld met `GET /client/pipeline` via `core/pipeline.py`, dus `pe.*` plus `full_name`, `current_title`, `current_company`, `location`, `skills`, `job_title`. De presentatietoestemmingspoort op `full_name` staat hier uit (`gate_name=False`), op de klantroute aan; de twee consentkolommen verlaten de respons nooit | §7.3.4, pipelinetab in beide drawers |
| BV2 | `GET /api/v1/admin/users` | `failed_login_count` en `locked_until` in de respons, en allebei sorteerbaar | §7.3.6(a), badge "Vergrendeld" en rijactie "Deblokkeren" |
| BV3 | `POST /api/v1/admin/candidates/referral` | 409 met een object-`detail`: `{code: "referral_email_suppressed", message}` en `{code: "referral_candidate_exists", candidate_id, message}` | §7.3.2, twee eigen meldingen plus de knop "Kandidaat openen" |
| BV4 | `GET /api/v1/candidate/profile` | `consent_withdrawn_at` en `lawful_basis` naast de vier bestaande consentvelden | §7.3.7, alle drie de redenen onder de alertschakelaar |
| BV5 | `GET /api/v1/admin/suppression` | `{items, total, limit, offset}`; `limit` standaard 100, maximaal 500 | §7.3.5, gewone paginering |
| BV6 | `GET /api/v1/admin/retention/review` | `limit` (1 tot 1000, **zonder default**: niets meegeven levert de volledige set), `offset`, `sort`, `order`, en `total` als volle telling. De ontbrekende default is opzet: de categoriebrede goedkeuring stuurt dat aantal als `expected_count` mee | §7.3.1, lijst met pager en modal zonder |
| BV7 | `GET /api/v1/admin/pipeline/{entry_id}/history` | `changed_by_name` naast `changed_by`, via `LEFT JOIN users`. Kan `null` zijn wanneer het account weg is; alleen `full_name` wordt gejoind, geen e-mail en geen rol | §7.3.4, actor in de tijdlijn |
| BV8 | `pipeline_entries.stage` | Migratie 043: normaliseren (trim, lowercase, bekende afwijkers naar hun fase, vangnet naar `sourced`) en daarna de CHECK op de zeven waarden als `NOT VALID`. `NOT VALID` geldt wel voor elke INSERT en UPDATE; `VALIDATE CONSTRAINT` is een aparte eigenaarsstap met eigen draaiboek in het migratiebestand | §7.3.4 en §7.3.8(a); de ontsnappingsklep vervalt pas na `VALIDATE` |
| BV9 | `POST /api/v1/admin/gdpr/erase` | `confirm` is het e-mailadres (string, lege standaardwaarde), vergeleken met `email` na strip en lowercase, vóór elke opzoeking; mismatch geeft 422 `erase_confirm_must_match_email`. De beheerders- en zelfbevestiging heet nu `confirm_admin_or_self` (booleaan) en geeft bij ontbreken 409 `erase_admin_or_self_requires_confirm` | §7.3.5, §7.6 besluit 3 |
| BV10 | `/users`, `/candidates`, `/jobs`, `/placements`, `/retention/review` | `sort` en `order` op elk van de vijf, met per route een allowlist van kolomnamen (`core/listing.py`). Buiten de lijst: 422 `invalid_sort_column`; `order` anders dan `asc`/`desc`: 422 `invalid_order_direction`. Beide `detail`-objecten dragen `allowed`. Er is geen stille terugval op de standaardsortering | §7.2a, sorteren over de hele verzameling |

Alle 4xx-`detail`-waarden in deze tabel zijn objecten met `code` en `message`. Lees `detail.code` om te vertakken en `detail.message` als terugval voor een code die het scherm niet kent (§7.2f).

Twee dingen die géén backendvoorwaarde waren en dat ook niet worden: `apollo_pool_purge` krijgt geen `RETENTION_TABLE`-rij (het label blijft UI-eigen, §7.2e), en `client_prospects.status` krijgt geen enum (er is geen canonieke lijst en het scherm verzint er geen, §7.3.6(c)).

Eén ding staat nog open, en het is geen backendwerk: **`VALIDATE CONSTRAINT` op de CHECK uit migratie 043** is een eigenaarsstap op productie. Zolang die niet is gedraaid, houden §7.3.4 en §7.3.8(a) hun ontsnappingsklep voor een fase buiten de zeven.

---

### 7.8 Adminpaneel: secties zoals ze nu draaien

`website/admin/` is gevendorde Tabler 1.4 met een dark navy/gold reskin en hash-geroute sidebarsecties:

| Hash | Sectie | Zoals gebouwd |
|---|---|---|
| `#dashboard` | Dashboard | KPI-tegels, widget openstaande verificaties, widget "Nieuwe registraties" (top 5 zelf geregistreerde kandidaten) |
| `#users` | Users | Gebruikerslijst |
| `#candidates` | Candidates | Soortfilter (Alle / Zelf geregistreerd / Gesourced), typebadge en verificatie-indicator per rij; rijklik opent het volledige detail via `GET /v1/admin/candidates/{kind}/{item_id}` (contactlinks, chips voor vaardigheden en talen, salaris, opzegtermijn, verhuisbereidheid, opleiding, CV-geüpload-indicator; het CV-bestand zelf is nog niet vanuit dit paneel te downloaden) |
| `#jobs` | All Jobs | Vacaturelijst over alle klanten heen, zoeken en statusfilter server-side, gepagineerd; de modal "Nieuwe vacature" laat een beheerder een vacature namens een klant vastleggen zonder dat die klant hoeft in te loggen |
| `#clients` | Opdrachtgevers | Klantenoverzicht |
| `#leads` | Leads | Binnengekomen leads en prospects |
| `#outreach` | Outreach | Concepten beoordelen en goedkeuren (outreach is altijd draft-only; een mens verstuurt, zie `CLAUDE.md`) |
| `#blog` | Blog | Blogbeheer; publiceren is een aparte, expliciete handeling naast opslaan |
| `#analytics` | Analytics | Platformcijfers |
| `#reporting` | Rapportage | Rapportageoverzicht |
| `#audit` | Audit Log | Beheerdershandelingen met actor, resource en actie |
| `#cms` | Content CMS | Vandaag beperkt tot de Blog-sectie hierboven; een bredere paginacontent-, testimonial- en case-study-CMS is niet gebouwd (zie §9) |
| `#settings` | Settings | Systeemconfiguratie |

`#retention` (Bewaartermijnen, §7.3.1) is gebouwd en staat in de sidebargroep System, boven Settings. Nieuw in dit document en nog te bouwen: `#placements` (§7.3.3) en `#gdpr` (§7.3.5).

Er is geen `superadmin`-rol; elk beheerdersaccount valt onder de MFA-flow uit `ENTERPRISE-ARCHITECTURE-SPEC.md` §3.2. Er is een `impersonate`-actie (gebruikerslijst) die de beheerder een token van 15 minuten als de doelgebruiker geeft en diens portaal opent; het eigen token van de beheerder wordt apart geparkeerd (`gsp_admin_token` in `localStorage`, nooit de normale sessieplek) voor de duur van de impersonatie. Zowel het kandidaat- als het klantportaal toont dan een blijvende goud-op-navy banner ("Je bekijkt als &lt;rol&gt;. Terug naar admin") met een knop die de beheerderssessie herstelt en terugkeert naar `#dashboard`.

Lege en foutstaten in het hele paneel volgen de Nederlandse conventie: "Kon niet laden, probeer opnieuw" bij een fout, "Nog geen …" bij leeg.

### 7.9 Bouwlagen zoals gebouwd (WS5 stap 1 t/m 3)

Tabler 1.4 blijft, geen herbouw. De schil staat op de canonieke tokens en de front-endcode is opgesplitst:

| Laag | Bestand | Verantwoordelijkheid |
|---|---|---|
| Tokens | `website/theme.css` | §1.2/§1.3/§1.4, gedeeld met de andere portalen |
| Schil | `website/admin/admin.css` | het `--tblr-*`-blok uit §7.1.2, de vier `--ink-*`-tokens, compatklassen, 29 `.a-*`-utilityklassen plus de vier `.text-*-ink`, gedocumenteerd bovenaan het bestand |
| Kern | `website/admin/js/admin.js` | state, laad-/foutstaten, `badge()`, paginering, dashboard, sectieregistry, één gedelegeerde click-listener |
| ui-laag | `website/admin/js/ui.js` | `ui.modal`, `ui.drawer`, `ui.tabs`, `ui.table`, `ui.confirm` op de Bootstrap 5-componenten uit de Tabler-bundel |
| Labels | `website/admin/js/labels.js` | twaalf enum→labelmaps (geteld in het bestand: kandidaatstatus, erkendReferent, contactRol, activiteit, leadCategorie, dienstlijn, retentiestatus, retentiecategorie, retentieactie, retentieonderwerp, grondslag, toestemmingsomvang), Nederlands, sleutels uit de backend. Wordt in de §7.2e-pass vervangen door `js/status-map.js` met `{label, tone}` per waarde |
| Secties | `website/admin/js/sections/<naam>.js` | één module per sectie, registreert zich via `Admin.registerSection({id, title, loader, skeletonHtml, filters, actions})` |
| Navigatie | `website/admin/js/nav.js` | leest de registry voor titels, loaders en filterbinding |

**Semantische inkt.** De vier tokens uit §7.1.2 staan in `admin.css` met exact die namen en waarden: `--ink-success #4ADE80`, `--ink-error #F87171`, `--ink-warning #FBBF24`, `--ink-info #7DD3FC`. `--tblr-blue/red/green/yellow` wijzen ernaar, dus de `-lt`-badgefamilies uit §7.2e halen hun contrastvloer op navy. De vier bijbehorende tekstklassen zijn `.text-success-ink`, `.text-danger-ink`, `.text-warning-ink` en `.text-info-ink`; §7.1.3 noemt de eerste twee, de andere twee zijn er in dezelfde vorm bij gekomen voor de audit-logkolom. Goud is geen semantische familie: `.a-accent` is het accent, en de gele badgefamilie staat op `--ink-warning`, niet op goud (§7.2e).

**Vijf bewuste tokencorrecties.**

- De inline compat-shim die `--navy-*` op eigen waarden zette (`#142235`, `#0E1B2E`) en radius 8–20px gaf, is weg. Het paneel draait op `--navy-800 #0A1628`, `--navy-700 #0F1D35` en radius 3px.
- Gedempte tekst is `--navy-200`, niet `--navy-300` (3,51:1 op `--navy-800`, 3,26:1 op `--navy-700`), conform de contrastvloertabel in §7.1.2.
- De kaartrand is `--navy-500` in plaats van Tablers doorschijnende default en in plaats van de `--navy-600` uit het codeblok van §7.1.2. Zie de noot daar.
- Knoptekst op goud is `--navy-900` (1,51:1 naar 12,3:1) en de focusring staat op volle `--gold-500` in plaats van 25% dekking.
- `--tblr-font-sans-serif` staat op `--font-primary`. Dat zet de UI-letter van Tablers eigen Inter naar IBM Plex Sans op 134 knooppunten: de tabel, de formulieren, de knoppen, de nav en de badges. Het is de grootste zichtbare verandering van de schilpass en de reden dat knoppen 6 tot 14px breder zijn geworden. Gewenst en merkconform (§1.3 en §7.1.4: Plex Sans is de UI-body), maar hij verdient het om benoemd te worden in plaats van als bijvangst van een tokenregel te verschijnen.

**Bewaakt door.** `scripts/css_tokens_check.py` doet `admin.css` mee in de tokenpariteit en faalt op elke hardcoded navy- of goudwaarde daarin, in elke schrijfwijze (hex, `rgb()`, `rgb(r g b / a)` en kale triples). De zes `--tblr-*-rgb`-regels zijn vrijgesteld met een `css-tokens-check: rgb-triple`-commentaar: Tabler bouwt daar zelf `rgba(var(--x-rgb), a)` mee en een triple kan niet uit een kleur-var komen. `scripts/admin_ui_check.py` test de paneelcomponenten (focus, focustrap, stapeling, Escape, klik-buiten, getypte bevestiging, sorteren met `aria-sort`) op twee paden: met en zonder Bootstrap. Beide draaien in de job "Website (static checks + CSP)" van `.github/workflows/ci.yml`, samen met `scripts/admin_sections_check.py` en `scripts/admin_pagination_check.py`.

**Bootstrap.** De gevendorde `admin/vendor/tabler/js/tabler.min.js` is een UMD die `window.tabler` exporteert met daarin de volledige `bootstrap`-namespace (Modal, Offcanvas, Collapse, Tab, Toast), maar zet `window.bootstrap` zelf niet. `js/vendor-fallback-tabler-js.js` zet die na het laden door, voor de lokale kopie en voor de CDN-fallback. Zonder die doorzet draait `ui.js` permanent op zijn vangnet en sluit het mobiele sidebarmenu niet na een navigatie. Het vangnet (dezelfde markup en klassen, eigen backdrop, focustrap en Escape) blijft staan voor een ontbrekende bundel.

**Engelse resten.** De chrome van het paneel wordt Nederlands, maar dat is een kopijpass per sectie en geen onderdeel van deze refactor. Wat er in stap 1 t/m 3 nog Engels staat: de sectietitels in de registry en de sidebar (User Management, All Jobs, All Candidates, Outreach, Blog, Analytics, Audit Log, Content CMS, Settings), de kolomkoppen van de tabellen in `index.html`, en de toasts en knoplabels in `users.js`, `jobs.js`, `blog.js`, `outreach.js`, `cms.js` en `settings.js` ("Settings saved", "Failed to save settings", "Network error"). Sinds de toastfix (§7.3.1, punt 10) staan die Engelse toasts ook echt in beeld: ze stonden tot dan op `display:none` en vielen dus niet op. Het gaat om veertien meldingen, verspreid over `users.js`, `jobs.js`, `blog.js`, `outreach.js`, `cms.js` en `settings.js`: "Settings saved", "Failed to save settings", "Network error", "Content updated", "Draft saved", "Draft rejected", "Email sent", "Post published", "Post archived", "Job deleted", "User updated", "User verified", "Update failed" en "Impersonation failed". Die kopijpass is een eigen kleine PR en hoort niet bij de sectie Bewaartermijnen.

**Sectie Bewaartermijnen (§7.3.1).** `website/admin/js/sections/retention.js` registreert `#retention` met zijn eigen `skeletonHtml()`; `index.html` draagt alleen het lege `<section>` en het sidebar-item. De sectie bracht veertien `.a-`-klassen mee (`.a-eyebrow`, `.a-num`, `.a-wide-only`, `.a-bulkbar`, `.a-cardlist`, `.a-clamp`, `.a-disclosure`, `.a-col-check`, `.a-col-actions`, `.a-col-cat`, `.a-col-status`, `.a-row-selected`, `.a-tap`, `.a-confirm-mismatch`) plus zeven modifiers, allemaal gedocumenteerd in de kop van `admin.css`, en vier labelmaps in `js/labels.js` (`retentiestatus`, `retentiecategorie` met álle `RETENTION_TABLE`-sleutels, `retentieactie` en `retentieonderwerp`) met `AdminLabels.badgeClass()` als voorloper van de `{label, tone}`-vorm uit §7.2e. `scripts/admin_sections_check.py` legt die categoriemap statisch naast `core/retention.py`, zodat een nieuwe categorie niet als ruwe sleutel op het scherm belandt.

De bulkbalk publiceert zijn hoogte vanaf de balk zelf, niet vanaf zijn wrapper: die wrapper is 0px hoog zodra de balk op een telefoon `fixed` staat, en met die 0px schoof de toast niet omhoog. Dezelfde waarde staat als `padding-bottom` op `#section-retention`, zodat de vaste balk de laatste rij en de pagineerfooter niet afdekt. Gemeten op 390px: token 138px, balk 138px, toast van 640 tot 690 met de balk vanaf 706.

De destructieve outline-knop staat sindsdien paneelbreed op `--ink-error` (`.portal-section .btn-outline-danger`, naast `.a-modal` en `.a-drawer`): Tablers eigen danger-outline haalt 4,17:1 op `--navy-900` en zakt daarmee onder de tekstvloer van §7.1.2, en dat geldt in elke sectie. De bulkbalk staat op een telefoon `position: fixed` in plaats van `sticky`: sticky binnen een lange tabelkaart scrollt met die kaart het beeld uit.

**Kandidaatdrawer en Toestemmingen (§7.3.2).** `website/admin/js/sections/candidates.js` registreert de kandidaatdrawer (Profiel, Matches, Activiteit, Toestemmingen) op `ui.drawer`/`ui.tabs`, en de referral-intake en de twee wijzigmodals op `ui.modal`, zoals het Opdrachtgevers-detailpaneel dat al deed. Verschillende dingen zijn paneelbreed, niet alleen voor deze sectie: `.a-skel-block` (een nieuwe `.a-`-klasse, een vlak `--navy-600`-blok voor de "drie vlakke blokken"-laadstaat van een drawertab uit §7.2b, die er nog nergens stond), de twee `--tblr-form-invalid-*`-tokens in `admin.css`, die `.invalid-feedback`/`.is-invalid` van Tablers hardcoded `#d63939` naar `var(--ink-error)` zetten, en twee reparaties uit de review op deze sectie die eveneens paneelbreed gelden: `.form-group label:not(.form-check-label)`/`.form-group input:not([type="checkbox"]):not([type="radio"])` (zodat een radiogroep of checkbox in een `<fieldset class="form-group">` niet de volle breedte en de hoofdletterstijl van een gewoon tekstveld krijgt), en de uitbreiding van de 44px-tikdoelregel op 390px met `#section-candidates .btn` en `.offcanvas .btn, .modal .btn, .modal .form-select, .modal .form-control`. Twee nieuwe labelmaps in `js/labels.js` (`grondslag`, `toestemmingsomvang`), letterlijk uit de tabellen in §7.2e.

**Sectie Plaatsingen (§7.3.3).** `website/admin/js/sections/placements.js` registreert `#placements` met zijn eigen `skeletonHtml()`, zoals Bewaartermijnen dat deed; `index.html` draagt alleen het lege `<section>` en het sidebar-item. Drie dingen zijn paneelbreed, niet alleen voor deze sectie: `.a-num--tab` (`font-variant-numeric: tabular-nums`, apart van `.a-num--date`, voor elke tabel- of paneelwaarde die op zijn cijfers moet uitlijnen zonder de leesmaat van een datum te delen), `.a-notes` (`white-space: pre-wrap`, voor elk paneel dat vrije tekst met regeleindes toont zonder inline `style=`) en de uitbreiding van de 44px-tikdoelregel op 390px met `#section-placements .btn` naast de al bestaande `#section-retention`/`#section-candidates`. `.a-hide-cardlist` is sectie-eigen (alleen deze kaartlijst toont op 390px minder kolommen dan op desktop) en staat daarom niet in die paneelbrede lijst. Vier labelmaps in `js/labels.js` (`plaatsingstype`, `plaatsingstatus`, `afrekenbasis`, `kostentype`), letterlijk uit `_PLACEMENT_TYPES`/`_PLACEMENT_STATUSES`/`_BILLING_BASES`/`_FEE_TYPES` in `models/schemas.py`.

**Nog niet gebouwd uit §7.1.** De vijf ontbrekende tokens in `theme.css` (§7.1.1 punt 2: `--space-4xl`, `--space-5xl`, `--font-size-base`, `--font-size-6xl`, `--gold-ink`), de nog niet gebouwde utilityklassen uit §7.1.3 (krijgen bij de bouw de `.a-`-prefix) en de zes stukken eigen CSS uit §7.1.3, en de lettertypeverscherpingen uit §7.1.4, waaronder het loskoppelen van `.text-uppercase` van mono. Die horen bij de componentpassen van §7.2.

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
