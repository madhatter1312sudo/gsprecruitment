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

## 7. Admin en portalen: componentsysteem

Deze sectie is het bindende ontwerpdocument voor `website/admin/` (Tabler 1.4, dark navy/gold), `website/candidate/` en `website/client/`. Wie hierna bouwt, bouwt hiernaar; waar dit document en een oudere notitie elkaar tegenspreken, wint dit document. Wat er niet in staat, wordt niet gebouwd zonder een nieuwe ontwerpronde.

**Besluit dat vaststaat: Tabler 1.4 blijft, en wordt goed gebruikt.** Geen herbouw, geen tweede UI-framework, geen componentbibliotheek erbij. Bootstrap 5 (modal, offcanvas, tabs, dropdown, collapse) is in de gevendorde Tabler-bundel al geladen en wordt vandaag nauwelijks gebruikt; het paneel rolt in plaats daarvan een eigen overlay uit zonder focustrap en zonder ESC (`admin.js` `openModal()`/`closeModal()`). Het werk in deze sectie bestaat grotendeels uit het vervangen van dat eigen werk door het framework dat er al ligt.

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

#### 7.1.1 Laadvolgorde, en de compat-shim verdwijnt

`website/admin/index.html:27-45` draagt vandaag een compat-shim met eigen navywaarden (`--navy-900:#142235`, `--navy-800:#142235`, `--tblr-body-bg:#0E1B2E`, `--tblr-bg-surface:#142235`) en een eigen radiusschaal van 8 tot 20px. Geen van die waarden staat in §1.2, de radiusschaal spreekt de vlakke 3px van §1.3 tegen, en `--navy-900` en `--navy-800` zijn er aan elkaar gelijk gemaakt, waardoor het paneel het diepteverschil kwijt is dat de rest van de site wel heeft.

Vast:

1. `<link rel="stylesheet" href="../theme.css">` komt in `website/admin/index.html` **vóór** de Tabler-stylesheet en vóór het eigen `<style>`-blok. `theme.css` draagt al de canonieke schaal uit §1.2 plus de 3px-radiustokens en is dus de enige tokenbron voor alle drie de surfaces.
2. Het hele `:root, [data-bs-theme=dark]`-blok met navy-, radius-, spacing- en font-size-herdefinities in `index.html` gaat weg. Wat overblijft in dat blok is uitsluitend de Tabler-koppeling uit §7.1.2 en de componentregels uit §7.1.3.
3. `--gold-gradient` blijft alleen bestaan zolang de fallback-staafgrafiek in `admin.js` hem gebruikt; die fallback krijgt in dezelfde PR een vlakke `--gold-500`-vulling en daarna verdwijnt het token uit het paneel. Decoratieve gradients zijn sitebreed verboden (§8.x.6) en een grafiekbalk is decoratie, geen data.

#### 7.1.2 Tabler-variabelen op de navy-tokens

Eén blok, in `index.html`, na het laden van `theme.css` en Tabler:

```css
:root, [data-bs-theme="dark"] {
  --tblr-body-bg:              var(--navy-800);   /* #0A1628 */
  --tblr-bg-surface:           var(--navy-700);   /* #0F1D35, kaarten, tabelkop */
  --tblr-bg-surface-secondary: var(--navy-800);
  --tblr-bg-surface-tertiary:  var(--navy-600);   /* #152B4A, hover-rij, inputvulling */
  --tblr-bg-surface-dark:      var(--navy-900);   /* #060D1A, sidebar, drawer-achtergrond */
  --tblr-border-color:         var(--navy-600);
  --tblr-border-color-active:  var(--navy-400);
  --tblr-body-color:           var(--navy-100);   /* 12,4:1 op navy-800 */
  --tblr-secondary:            var(--navy-200);   /* 6,8:1, de gedempte tekstvloer */
  --tblr-primary:              var(--gold-500);
  --tblr-primary-rgb:          250, 200, 0;
  --tblr-primary-fg:           var(--navy-900);   /* tekst op een goudvlak */
  --tblr-border-radius:        var(--radius);     /* 3px */
  --tblr-border-radius-sm:     var(--radius);
  --tblr-border-radius-lg:     var(--radius);
  --tblr-font-sans-serif:      var(--font-primary);
  --tblr-font-monospace:       var(--font-mono);
  --tblr-focus-ring-color:     var(--gold-glow);
  --tblr-focus-ring-width:     2px;
}
```

**Contrastvloeren op donker, gemeten op `--navy-800` (#0A1628), harde eis.** Deze tabel is de reden dat er hierboven geen `--navy-300` als tekstkleur staat:

| Token | Hex | Contrast op `--navy-800` | Toegestaan gebruik |
|---|---|---|---|
| `--white` | `#FFFFFF` | 18,4:1 | koppen, primaire waarden |
| `--navy-100` | `#C5D6EB` | 12,4:1 | body, tabelcellen (`--tblr-body-color`) |
| `--navy-200` | `#7FA0C9` | 6,8:1 | **de gedempte-tekstvloer**: labels, meta, tijdstempels |
| `--navy-300` | `#4A6F9F` | 3,6:1 | **nooit tekst.** Randen, scheidingslijnen, uitgeschakelde iconen (>3:1, dus wel geldig als niet-tekst) |
| `--navy-400` | `#2A4A75` | 1,9:1 | alleen vlakken, nooit tekst en nooit een dragende rand |
| `--gold-500` | `#FAC800` | 11,7:1 | accenttekst, actieve nav, primaire knopvulling met `--navy-900` erop |

`admin.js` zet vandaag 63 keer `color:var(--navy-300)` op tekst. Dat is de grootste toegankelijkheidsschuld in het paneel en die wordt in dezelfde PR ingelost: elk van die 63 gevallen wordt `.text-muted-navy` (§7.1.3), dat op `--navy-200` uitkomt. `--gold-ink` (#8A6800) uit §8.x.2 geldt uitsluitend op licht; op de navy panelen is `--gold-500` de juiste goudtekstkleur en `--gold-ink` verboden (2,4:1 op navy-800).

**Semantische inkt op donker.** De site-semantiek uit §1.2 is voor licht gekozen; `--error` (#EF4444) haalt op navy-800 4,9:1 en `--info` (#3B82F6) 5,0:1, allebei krap. Het paneel krijgt daarom vier eigen inkttokens, waarvan er twee al feitelijk in `admin.js` staan als losse hexwaarde en hier alleen een naam krijgen:

```css
--ink-success: #4ADE80;  /* 10,5:1, vervangt de losse #4ade80 (8x) */
--ink-error:   #F87171;  /*  6,6:1, vervangt de losse #f87171 (8x) */
--ink-warning: #FBBF24;  /* 11,0:1 */
--ink-info:    #7DD3FC;  /* 13,1:1 */
```

De vlakken (`--success-bg` en verwanten uit §1.2) blijven ongewijzigd; alleen de tekst- en icoonkleur op donker komt uit deze vier.

#### 7.1.3 Vijftien utilityklassen die de 202 inline `style=`-attributen vervangen

`admin.js` draagt 202 inline `style="…"`-attributen. Die mogen blijven staan (de CSP blokkeert alleen inline *scripts*, niet inline stijl), maar ze worden uitgefaseerd omdat ze de tokenlaag omzeilen en elke kleurcorrectie in 63 losse strings moeten laten landen. De vervanging is grotendeels **Bootstrap 5, dat al geladen is**; alleen waar Bootstrap niets passends heeft komt een nieuwe klasse. Alle nieuwe klassen krijgen het prefix `gsp-` of zijn een expliciete tekstkleur, staan in één blok in `index.html`, en zijn de enige nieuwe CSS die dit werkpakket toevoegt.

Bestaande Bootstrap-utilities die de meerderheid opruimen, één op één:

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

De vijftien nieuwe klassen, met hun CSS:

```css
/* 1-2. Tekstvloeren op donker. Vervangen color:var(--navy-300) (63x) en
        color:var(--navy-200) (22x). navy-300 haalt de AA-vloer niet. */
.text-muted-navy  { color: var(--navy-200); }
.text-body-navy   { color: var(--navy-100); }

/* 3-4. Typeschaal. Bootstrap's .fs-* is een eigen schaal en botst met §1.3. */
.fs-xs            { font-size: var(--font-size-xs); line-height: 1.45; }
.fs-sm            { font-size: var(--font-size-sm); line-height: 1.5; }

/* 5-6. Semantische inkt (§7.1.2). Vervangen de losse hexwaarden. */
.text-danger-ink  { color: var(--ink-error); }
.text-success-ink { color: var(--ink-success); }

/* 7. Genest paneel binnen een kaart of drawer. Vervangt het paar
      background:rgba(6,13,26,.6) + border:1px solid rgba(74,111,159,.3) (9x). */
.gsp-panel        { background: var(--navy-900); border: 1px solid var(--navy-600);
                    border-radius: var(--radius); padding: var(--space-md); }

/* 8. Mono cijferwaarde: KPI's, bedragen, scores, tijdstempels (§1.3). */
.gsp-num          { font-family: var(--font-mono); font-weight: 500;
                    font-variant-numeric: tabular-nums; }

/* 9. Eyebrow: mono, uppercase, gespatieerd. Kaartkopjes en veldlabels. */
.gsp-eyebrow      { font-family: var(--font-mono); font-size: var(--font-size-xs);
                    text-transform: uppercase; letter-spacing: .12em;
                    color: var(--navy-200); }

/* 10. Klikbare rij of tegel. Hover en focus-visible zijn identiek (§8.x.0). */
.gsp-clickable    { cursor: pointer; transition: background-color .15s ease; }
.gsp-clickable:hover,
.gsp-clickable:focus-visible { background: var(--navy-600); }
.gsp-clickable:focus-visible { outline: 2px solid var(--gold-500); outline-offset: -2px; }

/* 11. Voorgevormde tekst (draftbody, notitie). Vervangt white-space:pre-wrap. */
.gsp-prewrap      { white-space: pre-wrap; overflow-wrap: anywhere; }

/* 12. Verticaal schaalbare textarea. Vervangt resize:vertical (9x). */
.resize-y         { resize: vertical; }

/* 13. Scrollbaar deelvlak binnen een drawer of modal. */
.gsp-scroll-y     { overflow-y: auto; overscroll-behavior: contain; }

/* 14. Vangnet tegen tekstoverloop in een flexkolom (e-mailadres in een rij). */
.min-w-0          { min-width: 0; }

/* 15. Compacte tabeldichtheid (§7.2a). Zet alleen padding en regelhoogte. */
.gsp-table-dense > :not(caption) > * > * { padding: .375rem .5rem; }
.gsp-table-dense                          { font-size: var(--font-size-sm); }
```

Uitfasering is meetbaar: `scripts/css_class_census.py` (§8.x.8) krijgt een tweede modus die het aantal `style="`-treffers in `website/admin/js/admin.js` telt en faalt zodra dat aantal stijgt. Het getal daalt per PR; het mag nooit omhoog.

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

**Sorteren.** De sorteerbare `<th>` is een `<button type="button" class="btn-unstyled" data-action="sort" data-field="…">` met de kolomnaam plus een chevron. `aria-sort` staat op de `<th>`: `none`, `ascending` of `descending`; precies één kolom draagt een andere waarde dan `none`. **Belangrijk en zichtbaar te maken:** geen enkel adminlijst-endpoint accepteert vandaag een sorteerparameter, dus sorteren werkt op de geladen pagina en niet op de hele verzameling. De resultaatregel in de footer zegt dat dan ook letterlijk: "Gesorteerd binnen deze pagina (NN van MMM)". Zodra de backend een `sort`-parameter krijgt, vervalt die toevoeging; tot dan liegt de kolomkop niet.

**Rijselectie.** Kop-selectievakje is drietoestandig: leeg, `indeterminate` bij een deelselectie, aangevinkt bij alles op deze pagina. Het selecteert nooit meer dan de zichtbare pagina. Het kopvakje draagt `aria-label="Alles op deze pagina selecteren"`; een rijvakje draagt `aria-label` met de rij-identiteit (naam of e-mail), nooit alleen "Selecteren". Een geselecteerde rij krijgt `background: var(--navy-600)` en `aria-selected="true"`.

**Bulkbalk.** Verschijnt zodra er één selectie is, in de filterbalkruimte, `background: var(--navy-700)`, `border-bottom: 1px solid var(--navy-600)`. Inhoud: links "NN geselecteerd" in `.gsp-num`, daarnaast een tekstknop "Selectie wissen", rechts de acties. Destructieve bulkacties staan uiterst rechts en zijn `.btn-outline-danger`. De balk is `role="region"` met `aria-live="polite"` op de telling, zodat een schermlezer de selectiewijziging hoort. Bij nul selectie verdwijnt de balk en komt de filterbalk terug; de scrollpositie verandert daarbij niet.

**Dichtheid.** Twee standen, opgeslagen per gebruiker in `localStorage` onder `gsp_admin_density`: **ruim** (Tabler-standaard, rijhoogte 48px) en **compact** (`.gsp-table-dense`, rijhoogte 34px). De schakelaar is één icoonknop rechtsboven in de filterbalk met `aria-pressed`. Standaard is ruim op 1440 en compact niet beschikbaar onder 768px (daar is de tabel al een kaartlijst, zie hieronder).

**Staten.**

| Staat | Weergave |
|---|---|
| Rust | Rijtekst `--navy-100`, meta-kolommen `.text-muted-navy`, kolomkop `.gsp-eyebrow` |
| Hover (rij) | `background: var(--navy-600)`, 150ms; alleen op een klikbare rij (`.gsp-clickable`) |
| Focus-visible (rij) | Identiek aan hover, plus `outline: 2px solid var(--gold-500); outline-offset: -2px` |
| Actief (geselecteerd) | `background: var(--navy-600)`, plus 2px `--gold-500` linkerrand op de eerste cel |
| Disabled (rij zonder toegestane actie) | Tekst blijft `--navy-100`; alleen de actieknoppen krijgen `disabled` plus `title` met de reden. Een rij wordt nooit gedimd, want dat kost leesbaarheid zonder iets uit te leggen |
| Laden | `setLoading(tbodyId, cols)`: één rij over de volle breedte, gecentreerd, spinner plus "Laden…". Kop- en filterbalk blijven staan (§8.x.0) |
| Leeg | `setEmpty(tbodyId, cols, msg)`: "Nog geen &lt;meervoud&gt;." plus, waar er een zinnige vervolgstap is, één tekstlink ernaar. Nooit een generiek "No results" |
| Fout | `setLoadError(tbodyId, cols, retryFn)`: waarschuwingsicoon plus "Kon niet laden, probeer opnieuw" met de retrylink. De retry roept precies dezelfde loader met dezelfde filters aan (`_lastParams`) |

**Toetsenbord.** Tab loopt door: dichtheidsschakelaar, zoekveld, filters, kopselectievakje, per rij het rijvakje en daarna de actieknoppen, en tenslotte de paginering. De rij zelf is geen tab-stop; de rijactie is altijd ook als knop in de actiekolom bereikbaar. `Enter` en `Space` op een sorteerknop wisselen de sorteerrichting. Bulkbalk-acties zijn gewone knoppen in de tabvolgorde.

**1440.** Volle tabel, alle kolommen, dichtheidsschakelaar zichtbaar.

**390.** Onder 768px is dit geen tabel meer maar een kaartlijst: per record één `.card.mb-2` met bovenin naam plus statusbadge, daaronder maximaal drie meta-regels in `.fs-xs.text-muted-navy`, en onderin één rij knoppen op volle breedte. Elk tikdoel is minimaal 44x44px (§8.x.0). Het selectievakje staat linksboven in de kaart. De filterbalk stapelt tot één kolom en de selects worden volle breedte. De bulkbalk plakt onderaan het scherm (`position: sticky; bottom: 0`) met `bottom: calc(var(--space-md) + var(--fixed-stack-offset, 0px))`, zodat hij in dezelfde vaste-elementenstapel valt als §8.x.4 beschrijft. Horizontaal scrollen komt in geen enkele breedte voor; de enige uitzondering blijft `.table-responsive` op tablets tussen 768 en 1024px.

#### 7.2b Drawer (Bootstrap offcanvas)

*Vervangt*: `openModal('viewCandidateModal', …)` en `openModal('clientDrawer', …)`, die vandaag allebei de gecentreerde overlay gebruiken.

**Waarom offcanvas en niet modal.** Detail van een kandidaat of klant is lezen en navigeren, geen beslissing met één uitkomst. Een offcanvas houdt de lijst zichtbaar, verdraagt veel inhoud met tabs, en Bootstrap levert focustrap, ESC en scroll-lock kant-en-klaar. De modal (§7.2c) blijft gereserveerd voor beslissingen.

**Anatomie.** `<div class="offcanvas offcanvas-end" tabindex="-1" id="gspDrawer" aria-labelledby="gspDrawerTitle">`, breedte 560px op 1440. Kop (`.offcanvas-header`, `background: var(--navy-900)`, sticky): links `h2#gspDrawerTitle` in Newsreader `--font-size-2xl` met daaronder een `.gsp-eyebrow`-regel (type plus ID, bijvoorbeeld "KANDIDAAT · #1482"), rechts de statusbadge en de sluitknop. Direct onder de kop een tabsrij (`.nav.nav-tabs`, Bootstrap-tabs, `role="tablist"`). Daaronder `.offcanvas-body.gsp-scroll-y` met de actieve tabpaneel-inhoud. Onderaan een sticky voetbalk (`background: var(--navy-900)`, `border-top: 1px solid var(--navy-600)`) met maximaal twee acties: rechts de primaire, links de secundaire. Destructieve acties staan niet in de voetbalk maar in de tab waar ze thuishoren, achter de modal van §7.2c.

**Tabs.** Elke tab is een `<button role="tab" aria-selected aria-controls>`; het paneel is `role="tabpanel"` met `tabindex="0"`. Pijl-links/rechts wisselt van tab, `Home`/`End` springt naar de eerste of laatste. De actieve tab draagt een 2px `--gold-500`-onderrand; inactieve tabs zijn `.text-muted-navy`. Elke tab laadt zijn eigen data pas bij eerste opening (lui) en houdt daarna zijn eigen laad-, lege- en foutstaat via `setContainerLoadError`.

**Staten.** Rust en hover als hierboven. Focus-visible op tab en op sluitknop: 2px `--gold-500`, offset 2px. Laden per tab: drie vlakke `--navy-700`-blokken op de plaats van de velden, geen shimmer (§8.x.6). Leeg per tab: "Nog geen …" plus, waar van toepassing, de knop die de eerste zou aanmaken. Fout per tab: `setContainerLoadError` op de tabcontainer, zodat een kapotte tab de rest van de drawer niet meesleurt. Disabled tab: alleen wanneer de rol de inhoud niet mag zien; dan `aria-disabled="true"` plus een korte reden in het paneel, nooit een tab die stilzwijgend verdwijnt.

**Toetsenbord en aria.** Bootstrap's offcanvas doet de focustrap; bij openen gaat de focus naar de kop, bij sluiten terug naar het element dat hem opende (de rijactieknop). ESC sluit. De backdrop-klik sluit ook, behalve wanneer er een onopgeslagen formulier in de actieve tab staat; dan verschijnt eerst de bevestigingsmodal "Wijzigingen weggooien?".

**1440.** 560px breed, rechts, met backdrop; de lijst eronder blijft leesbaar.

**390.** Volle breedte, van onder naar boven (`offcanvas-bottom`), maximaal 92vh hoog, met een sleepgreep-affordance bovenin (visueel; slepen zelf is niet vereist). De tabsrij scrollt horizontaal met `scroll-snap-type: x mandatory`, nooit met een verborgen "meer"-menu. De voetbalk blijft sticky en de knoppen worden volle breedte, gestapeld, primaire actie bovenaan.

#### 7.2c Modal

*Vervangt*: `Admin.openModal()`/`closeModal()` volledig. Die eigen overlay heeft geen focustrap, geen ESC, geen `role="dialog"`, geen `aria-modal`, en zet de focus na sluiten niet terug. Dat is niet te repareren met een pleister; hij gaat weg en Bootstrap's `<div class="modal" tabindex="-1">` plus `bootstrap.Modal` neemt het over. De aanroeperkant blijft gelijk van vorm (`Admin.openModal(id, bodyHtml, opts)` blijft bestaan als dunne wrapper rond `bootstrap.Modal`), zodat de circa twaalf bestaande aanroepen niet herschreven hoeven te worden.

**Anatomie.** `.modal-dialog.modal-dialog-centered` (`.modal-lg` bij `opts.wide`), `.modal-content` op `--navy-900` met 1px `--navy-600`-rand en `--radius`. Kop: `h2.modal-title` in Newsreader `--font-size-xl`, plus sluitknop. Body: `--space-lg` padding. Voet: rechts de primaire actie, links daarvan de secundaire (`.btn-ghost-secondary`, tekst "Annuleren"). Precies één primaire actie per modal.

**Staten.** Rust, hover en focus-visible als elders. Laden: de primaire knop krijgt een spinner en `disabled`, de velden krijgen `disabled`, de modal blijft staan en de backdrop blijft. Fout: een inline-melding (§7.2f) bovenaan de body, niet een toast, want de fout hoort bij het formulier dat je voor je hebt. Succes: modal sluit en er verschijnt een toast; de onderliggende lijst herlaadt met dezelfde filters.

**Destructieve variant.** Voor AVG-wissen (§7.3.5) en de goedkeuringslijst bewaartermijnen (§7.3.1). Verschillen met de gewone modal:

- Kop krijgt een waarschuwingsicoon in `--ink-error` en een kopregel die het gevolg noemt, niet de handeling: "Deze gegevens worden onomkeerbaar gewist", niet "Weet je het zeker?".
- Body noemt in een `.gsp-panel` exact wat er gebeurt: welke tabellen, hoeveel rijen, en of het anonimiseren of hard verwijderen is. Bij een bulkactie staat het aantal er als `.gsp-num` en wordt het bij openen opnieuw opgehaald, niet uit de lijstweergave overgenomen.
- **Getypte bevestiging.** Eén tekstveld met een label dat de exact te typen tekenreeks noemt. De primaire knop blijft `disabled` tot de invoer letterlijk klopt (hoofdlettergevoelig, na `trim()`). De verwachte tekenreeks staat in het label als `<code>`, is selecteerbaar maar wordt nooit voorgevuld. Onder het veld staat, zodra er iets fout getypt is, "Komt niet overeen" in `.text-danger-ink`, met `aria-live="polite"`.
- De primaire knop is `.btn-danger`, staat rechts, en heeft als tekst het werkwoord plus het object ("Wissen (3 items)"), nooit "OK".
- ESC en backdrop-klik sluiten wel, want sluiten is de veilige uitkomst.

De te typen tekenreeksen zijn niet vrij te kiezen: ze komen overeen met wat de backend zelf eist, zodat de UI geen tweede, afwijkende waarheid introduceert. Zie §7.3.1 en §7.3.5.

**Toetsenbord en aria.** `role="dialog" aria-modal="true" aria-labelledby` op de kop, `aria-describedby` op de eerste bodyalinea. Focus gaat bij openen naar het eerste interactieve element (bij de destructieve variant: het bevestigingsveld), Tab loopt rond binnen de modal, ESC sluit, focus keert terug naar de openende knop. `Enter` in het bevestigingsveld voert de primaire actie alleen uit als die niet meer `disabled` is.

**390.** `.modal-fullscreen-sm-down`: volle breedte en hoogte, voetbalk sticky onderaan, knoppen volle breedte en gestapeld met de primaire bovenaan. Het bevestigingsveld krijgt `inputmode="text"` en `autocapitalize="off"`, zodat een mobiel toetsenbord de getypte bevestiging niet stuk maakt met een automatische hoofdletter.

#### 7.2d Formulierpatroon

*Vervangt*: de `.form-group`-regels in `index.html` en de handmatige veldopbouw in `admin.js`.

**Anatomie per veld.** `<div class="mb-3">` met daarin, in deze volgorde: `<label class="form-label">` (Plex Sans, `--font-size-sm`, gewicht 500, kleur `--navy-100`; niet meer de huidige uppercase mono, die maakt lange labels slecht leesbaar), optioneel een `.form-hint.fs-xs.text-muted-navy` **boven** het veld wanneer de hint bepaalt hoe je invult, het veld zelf (`.form-control` / `.form-select` / `.form-check`), en daaronder de foutregel `.invalid-feedback`. Verplichte velden krijgen `required` plus een `*` in het label; optionele velden krijgen niets. Er wordt niet met "(optioneel)" gewerkt naast "*": één van de twee conventies, en dat is de asterisk.

**Validatie.** Inline, op `blur` van een veld dat de gebruiker heeft aangeraakt, en opnieuw bij `submit`. Nooit op `input` tijdens het eerste typen: een e-mailadres dat halverwege rood wordt is ruis. Een ongeldig veld krijgt `.is-invalid` (1px `--ink-error`-rand plus `aria-invalid="true"`) en `aria-describedby` naar de foutregel. Een veld dat na correctie geldig is verliest de foutstaat direct op `input`. Er wordt geen groene vinkstaat gebruikt: correct is de norm en verdient geen kleur.

**Foutsamenvatting.** Bij een mislukte `submit` verschijnt bovenaan het formulier (in een modal: bovenaan de body; in een drawertab: bovenaan het paneel) een blok met `role="alert"` en `tabindex="-1"`, dat direct focus krijgt. Inhoud: kop "Er zijn NN velden die aandacht nodig hebben", en daaronder een `<ul>` met per fout een link naar het veld (`href="#veldId"`, klik zet focus op het veld). De samenvatting wordt bij elke nieuwe `submit` opnieuw opgebouwd, nooit aangevuld. Bij een serverfout (422 met veldnamen) worden de velden op dezelfde manier gemarkeerd en verschijnt dezelfde samenvatting; een 5xx zonder veldinformatie verschijnt als één inline-melding (§7.2f) met de retryknop.

**Staten.** Rust: veldvulling `--navy-800`, rand `--navy-600`, tekst `--white`, placeholder `.text-muted-navy`. Hover: rand `--navy-400`. Focus-visible: rand `--gold-500` plus `box-shadow: 0 0 0 3px var(--gold-glow)`; identiek aan focus, want een tekstveld heeft geen hoverbetekenis. Disabled: rand `--navy-600`, tekst `--navy-200`, `background: var(--navy-900)`, plus een korte reden als `.form-hint` eronder wanneer de reden niet uit de context blijkt. Laden (formulier wordt verzonden): alle velden `disabled`, primaire knop met spinner. Leeg is geen formulierstaat. Fout: hierboven beschreven.

**Toetsenbord.** Tabvolgorde volgt de leesvolgorde; er wordt nergens een `tabindex` groter dan 0 gebruikt. `Enter` in een enkelregelig veld verzendt het formulier; `Ctrl+Enter` doet dat vanuit een `<textarea>`. Een fieldset met een groep radio's of checkboxes krijgt `<legend>`, geen los `<div>` met labeltekst.

**390.** Eén kolom, altijd. `.detail-grid` schakelt al onder 576px naar één kolom; die grens gaat naar 768px, want twee kolommen formulier op een tablet in staand gebruik zijn te smal. Velden zijn volle breedte, minimale hoogte 44px. De knoppenrij is sticky onderaan het formuliervlak.

#### 7.2e Statusbadges en één enum-naar-labelmap

*Uitbreiding van*: `Admin.badge()` en `Admin.statusLabel()`.

**Anatomie.** `<span class="badge">` met `--radius-full` (de bewuste uitzondering uit §8.x.0), `--font-size-xs`, gewicht 500, padding 2px 8px, Plex Sans (geen mono: dit is een label, geen datawaarde). Nooit alleen kleur als drager: de tekst staat er altijd bij. Een badge is nooit klikbaar; wie moet filteren gebruikt de filterbalk.

**Kleur.** Vijf families, alle vijf getest op `--navy-700` (de kaartachtergrond waar badges meestal op staan): neutraal (`bg-secondary-lt`), informatief (`bg-blue-lt`), aandacht (`bg-yellow-lt`), positief (`bg-green-lt`), negatief (`bg-red-lt`). Goud is geen badgekleur: goud is de primaire actie op een scherm en mag niet met een statuslabel concurreren. De enige uitzondering blijft de rolbadge "kandidaat", die vandaag al `gold` is; die gaat naar neutraal in dezelfde PR.

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
| `rejected` | Afgewezen (bewaren) | neutraal |
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

`placed_candidate` (Geplaatste kandidaat, 7 jaar, `action=retain`) en `logs` (`action=infra_only`) komen nooit in de beoordelingslijst en krijgen daarom geen badge, maar staan wel in de referentietabel op het scherm (§7.3.1), zodat zichtbaar is dat ze bestaan en waarom ze er niet in staan.

**Grondslag** (`candidates.lawful_basis` en `client_prospects.lawful_basis`; de prospectwaarden zijn het gevalideerde patroon uit `routers/prospects.py`, de kandidaatwaarden komen uit `core/privacy.py` en de referral-route):

| Waarde | Label |
|---|---|
| `opt_in_talentpool` | Toestemming talentpool |
| `toestemming_referral` | Toestemming via referral |
| `zakelijk_functioneel_adres` | Zakelijk functioneel adres |
| `opt_in` | Opt-in |
| `bestaande_relatie` | Bestaande relatie |

**Toestemmingsomvang** (`TALENTPOOL_CONSENT_SCOPES`, `models/schemas.py`): `matching_only` = "Alleen matching", `matching_and_contact` = "Matching en contact".

**Staten van de badge zelf.** Statisch. Geen hover, geen focus, geen disabled: een badge is geen bedieningselement. Op 390px verandert er niets aan de badge; hij staat alleen op een andere plek in de kaartlijst (§7.2a).

#### 7.2f Toast en inline-melding

**Wanneer welke.** Een **toast** bevestigt iets dat gelukt is en dat je niet hoeft te lezen om verder te kunnen. Een **inline-melding** hoort bij een plek op het scherm en blijft staan tot de oorzaak weg is. Een fout die een handeling blokkeert is altijd inline, nooit alleen een toast: een toast die je mist is een fout die je mist.

**Toast.** De bestaande `Auth.toast()`-implementatie en de `.toast-container` in `index.html` blijven, met vier correcties. (1) De container krijgt `role="status" aria-live="polite" aria-atomic="true"`, zodat een schermlezer de melding hoort; een foutmelding krijgt in plaats daarvan `role="alert"`. (2) De vier varianten krijgen de tokens in plaats van losse hexwaarden: succes `--navy-900`-vlak met 3px linkerrand `--ink-success`, fout idem met `--ink-error`, waarschuwing `--ink-warning`, informatie `--navy-400`. De huidige volvlakke `#065f46`/`#991b1b`/`#78350f` verdwijnen: een gekleurd vlak van 360px trekt meer aandacht dan de mededeling waard is en botst met de navy schil. (3) Radius naar `--radius` (3px), niet `--radius-sm` uit de shim. (4) Duur 4 seconden, met pauze op hover en op focus; een toast met een actielink (bijvoorbeeld "Ongedaan maken") blijft 10 seconden staan en is tab-bereikbaar. Bij `prefers-reduced-motion` vervalt de intreebeweging en verschijnt de toast direct op zijn eindpositie.

Positie: rechtsonder, `--space-lg` van de rand. Op 390px volle breedte min 2x16px, onderaan, in de vaste-elementenstapel met `bottom: calc(var(--space-md) + var(--fixed-stack-offset, 0px))`. Maximaal drie tegelijk zichtbaar; een vierde vervangt de oudste.

**Inline-melding.** `<div class="alert" role="alert">` in de Tabler-vorm, altijd binnen het blok waar hij over gaat (formulier, kaart, drawertab), nooit zwevend. Anatomie: icoon links, tekst, en rechts optioneel één actie (meestal "Opnieuw proberen"). Vier tonen met dezelfde inkttokens als de toast. Vlak `--navy-900`, 1px rand in de bijbehorende inktkleur op 40% dekking, 3px linkerrand in de volle inktkleur.

De bestaande MFA-banner (`#mfaBanner`) is een inline-melding van het type waarschuwing en blijft precies waar hij staat; hij krijgt alleen de nieuwe styling en een `aria-live="polite"`, want hij verschijnt pas na het ophalen van de MFA-status.

**Staten.** Toast: intredend (200ms), zichtbaar, uittredend (200ms), gepauzeerd bij hover of focus. Inline: rust, en, waar er een actie in zit, hover en focus-visible op die actie (identiek). Een inline-melding heeft geen laad- of lege staat.

**Copy.** Nederlands, één zin, zegt wat er gebeurd is en zo nodig wat je nu kunt doen. "Kon niet laden, probeer opnieuw" is de vaste foutzin bij een mislukte fetch (dat is al de conventie in het paneel). Geen uitroeptekens, geen "Oeps", geen technische code in de zichtbare tekst; een `detail.code` uit de API hoort in de console, niet op het scherm.

#### 7.2g KPI-tegel en lege dashboardstaat

**Anatomie.** `.card.card-sm` met `.card-body`: bovenin een `.gsp-eyebrow`-label (bijvoorbeeld "OPEN VACATURES"), daaronder de waarde in `.gsp-num` op `--font-size-3xl` (32px) in `--white`, en daaronder optioneel één regel context in `.fs-xs.text-muted-navy`. Geen icoon in de tegel: de vijf iconen die er nu staan voegen niets toe dat het label niet al zegt. Geen sparkline, geen percentageverandering, geen kleurvlak.

**Geen verzonnen cijfers.** Een KPI-tegel toont uitsluitend een getal dat een API-veld letterlijk teruggeeft. Er wordt niets afgeleid, geen trend berekend uit twee metingen, geen doel of benchmark getoond. Waar de API `null` teruggeeft (bijvoorbeeld `cost_per_hire_avg` zonder gevulde `fee_value`), toont de tegel **"n.v.t."** in `.text-muted-navy` met daaronder in `.fs-xs` de reden ("nog geen vervulde vacature met een vastgelegd tarief"). Nooit een 0 waar `null` bedoeld is: 0 is een meting, `null` is de afwezigheid van een meting, en dat verschil is op een dashboard het hele punt.

**Staten.**

| Staat | Weergave |
|---|---|
| Rust | Label, waarde, contextregel |
| Laden | Label blijft staan; de waardepositie wordt een vlak `--navy-700`-blok van 3ch breed en de hoogte van de regel. Geen shimmer, geen spinner, geen "0" die daarna verspringt |
| Leeg (`null`) | "n.v.t." plus reden, zoals hierboven |
| Fout | Label blijft staan; op de waardepositie een streepje plus, eronder, "Kon niet laden" met een tekstlinkretry via `setContainerLoadError` op het waardeblok. De andere tegels blijven werken: elke tegel faalt op zichzelf |
| Hover of focus | Geen: een tegel is geen bedieningselement. Waar een tegel toch naar een lijst leidt, is dat een expliciete tekstlink onderin de tegel, die wel hover en focus-visible krijgt |

**Lege dashboardstaat.** Wanneer alle vijf de tegels leeg zijn (een vers systeem, of een klantportaal zonder vacatures) worden de tegels niet getoond. In hun plaats komt één kaart over de volle breedte met: een `.gsp-eyebrow` "DASHBOARD", een kop in Newsreader `--font-size-2xl` ("Er zijn nog geen gegevens om te tonen"), één regel uitleg ("Zodra er vacatures, kandidaten of plaatsingen zijn vastgelegd, verschijnen de kerncijfers hier."), en precies één primaire actie, afhankelijk van de surface: adminpaneel "Nieuwe vacature vastleggen", klantportaal "Vacature plaatsen", kandidaatportaal "Profiel afmaken". Eén actie, niet drie. De widgets eronder (recente activiteit, nieuwe registraties, openstaande verificaties) houden hun eigen lege staat en verdwijnen niet.

**1440.** Vijf tegels op één rij (`.col-sm-6 .col-lg`, zoals nu). **390.** Twee kolommen, want vijf gestapelde tegels duwen alles wat eronder staat van het scherm; de vijfde tegel neemt de volle breedte van de laatste rij. Waarde blijft 32px, label blijft 12px.

---

### 7.3 De schermen die nog geen UI hebben

Per scherm: het wireframe in tekst, de componenten die het gebruikt, en de endpoints en velden die het leest of schrijft. Alles wat hier als veld genoemd wordt, bestaat in de backend; waar een aanname is gedaan, staat dat er letterlijk bij.

#### 7.3.1 Goedkeuringslijst bewaartermijnen

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

**Kolommen en velden.** `category` (label uit §7.2e), `subject_table` plus `subject_id` samengevoegd tot "kandidaat #1482" of "prospect #77" (de `email` uit de respons wordt **niet** in de lijst getoond: hij staat wel in de API-respons maar hoort niet in een overzicht dat over een schouder meegelezen wordt; het adres is alleen in de bevestigingsmodal zichtbaar, en daar gemaskeerd tot `j••••@voorbeeld.nl`), `term_expired_at` als datum plus het aantal dagen erachter in `.fs-xs.text-muted-navy`, `signal_missing_nl` verbatim (die tekst is door de backend geschreven om precies zo getoond te worden; niet inkorten, wel afbreken na twee regels met een uitklap), `action` als "Anonimiseren" of "Hard verwijderen", en `status` als badge (§7.2e).

**"Eerder overgeslagen" moet zichtbaar zijn.** Een item met een gevulde `reappeared_after_rejection_at` krijgt links in de rij een pictogram plus, in de kolom Status, onder de badge een regel `.fs-xs.text-muted-navy`: "Eerder afgewezen op &lt;datum&gt;, opnieuw verschenen". Datzelfde item heeft `status = 'rejected'` en verschijnt dus **niet** in de standaardweergave (`status=pending`); daarom krijgt de statusfilter een expliciete optie "Eerder afgewezen" die `status=rejected` opvraagt, en toont de samenvattingskaart het aantal daarvan als aparte tegel zodra het groter dan nul is. Een lijst die alleen `pending` toont en zwijgt over wat eerder is overgeslagen, verbergt precies de gevallen die aandacht verdienen.

**Goedkeuren, per item.** De `[✓]`-knop opent de destructieve modal (§7.2c). Kop: "Deze gegevens worden onomkeerbaar verwerkt". Body: categorie, onderwerp, verlopen termijn, ontbrekend signaal, de handeling (anonimiseren of hard verwijderen) en het gemaskeerde e-mailadres, in een `.gsp-panel`. Getypte bevestiging: **`APPROVE`**, letterlijk, want dat is wat `REVIEW_APPROVE_CONFIRM` in `routers/retention_admin.py` eist en de UI mag daar geen tweede, vriendelijker waarheid naast zetten. Het label boven het veld: "Typ <code>APPROVE</code> om te bevestigen". Primaire knop: "Goedkeuren en verwerken". Optioneel veld "Notitie" (`note`), vrije tekst, gaat mee in de aanroep.

**Afwijzen, per item.** De `[✕]`-knop opent een gewone modal, geen destructieve: afwijzen verwijdert niets en is de veilige uitkomst. Eén optioneel notitieveld en de knop "Afwijzen (bewaren)". Geen getypte bevestiging, want de backend eist die daar ook niet.

**Bulk.** Twee routes, met verschillende risico's, en het scherm laat dat verschil zien.

- *Expliciete selectie* (`ids`): de bulkbalk uit §7.2a. "Goedkeuren…" opent de destructieve modal met het aantal en de categorieën die in de selectie zitten; getypte bevestiging `APPROVE`; de aanroep stuurt `{ decision: "approved", ids: [...], confirm: "APPROVE", note }`. "Afwijzen" is één klik zonder modal, met een toast en een undo-loze bevestiging (er is niets ongedaan te maken, want er is niets vernietigd).
- *Categoriebreed* (`category`): de knop "Alles goedkeuren" in de categorie-tabel. De modal haalt bij openen **opnieuw** `GET .../review?status=pending&category=…` op en toont dat aantal als `.gsp-num`; dat getal gaat als `expected_count` mee. Zo komt de waarde uit de meting die de beheerder op dat moment ziet, niet uit een tabel die tien minuten oud is. Bij een 409 `retention_review_bulk_expected_count_mismatch` blijft de modal open, verschijnt de inline-melding "De lijst is veranderd sinds je hem bekeek. Ververs en probeer opnieuw." met de knop "Verversen", en wordt het aantal opnieuw opgehaald. Er wordt nooit stilzwijgend opnieuw geprobeerd met het nieuwe getal.
- Boven de bulkcap (`MAX_BULK_REVIEW_ITEMS`) geeft de backend een 422. De UI voorkomt dat vooraf: de knop is `disabled` met een `title` zodra de selectie de cap overschrijdt, en de tekst eronder zegt "Maximaal NN per keer".
- Het antwoord van een bulkaanroep is een lijst met per item een uitkomst, inclusief `status: "error"`. Het scherm toont die uitkomst als een resultaatlijst in dezelfde modal (niet als toast): "12 verwerkt, 2 mislukt", met de mislukte item-ID's en de mogelijkheid ze opnieuw te proberen. De lijst eronder herlaadt daarna.

**Droogloop.** Ingeklapte kaart onderaan. `POST /api/v1/admin/retention/run` met `{ dry_run: true }` geeft per categorie `{ key, status, count }` met `status` in `counted`, `not_applicable`, `schema_not_ready` of `error`. Weergave: tabel met categorie, telling en een leesbare toelichting per status ("telt niet mee: bewaren", "kolom bestaat nog niet", "kon niet tellen"). **Getypte bevestiging ook hier**, ondanks dat de aanroep read-only is: de knop heet "Uitvoeren" en de bevestiging is `DRY RUN`. Reden: dit is het enige scherm waar een beheerder gewend raakt aan een knop die naast een echte verwijdering staat, en het is beter dat de droogloop dezelfde handeling vraagt dan dat de echte actie ooit als de lichtere van twee voelt. `dry_run: false` bestaat niet meer aan de backendkant (410) en komt in de UI ook niet voor; er is geen schakelaar.

**Referentietabel.** Onderaan de sectie, in een uitklapbare kaart: `GET /api/v1/admin/retention/table`, alle rijen uit `RETENTION_TABLE`, met categorie, bewaartermijn, bron of opmerking, en actie. `placed_candidate` (bewaren, 7 jaar) en `logs` (alleen infrastructuur) staan hier met een neutrale badge "Komt niet in de beoordelingslijst", zodat zichtbaar is dat ze bestaan.

**Staten van het scherm.** Laden: KPI-tegels in laadstaat, tabel met `setLoading`. Leeg: "Er staat op dit moment niets te beoordelen." plus, eronder in `.fs-xs`, "De lijst wordt maandelijks automatisch aangevuld." en de knop "Lijst genereren". Fout: `setLoadError` op de tabel, `setContainerLoadError` op de samenvatting; ze falen los van elkaar.

**390.** Kaartlijst in plaats van tabel (§7.2a): per item één kaart met bovenin de categoriebadge plus de statusbadge, daaronder onderwerp en verlopen termijn, daaronder het ontbrekende signaal ingekort tot twee regels met "meer", en onderin twee knoppen van volle breedte: "Afwijzen" (secundair) en "Goedkeuren" (primair, opent de destructieve modal, die fullscreen wordt). Bulk is op 390px beschikbaar maar categoriebreed goedkeuren niet: die knop staat alleen in de categorie-tabel, en die tabel toont op 390px alleen tellingen plus "Bekijken". Een categoriebrede, onomkeerbare goedkeuring hoort niet op een telefoon thuis.

#### 7.3.2 Toestemmingen in de kandidaatdrawer

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

**Talentpool wijzigen.** Modal (niet destructief), met: een radiogroep "Toestemming" met "Vastleggen" en "Intrekken"; bij "Vastleggen" een select "Omvang" met de twee waarden uit `TALENTPOOL_CONSENT_SCOPES` (verplicht, want de backend geeft 422 op `consent=true` zonder `scope`); en een verplicht `<textarea>` **"Bewijs van toestemming"** (`evidence`, 1 tot 2000 tekens) met de hint boven het veld: "Waar blijkt de toestemming uit? Bijvoorbeeld: ondertekend formulier van 2 september, of e-mail in het dossier." Het veld is verplicht in beide richtingen (ook bij intrekken), omdat de backend het zo eist. Inline validatie: leeg veld geeft "Vul kort in waar de toestemming uit blijkt"; boven 2000 tekens een teller in `.text-danger-ink`. Onder de modal een `.fs-xs.text-muted-navy`-regel: "Bij het vastleggen geldt een termijn van 12 maanden. Deze notitie komt in het auditlog; e-mailadressen erin worden automatisch onleesbaar gemaakt." Dat laatste is waar: `privacy.redact_emails()` doet dat.

**Presentatie vastleggen.** Zelfde modal-vorm, met één extra en verplicht veld: **een vacaturekiezer**. Dit is een `<select>` (geen vrij tekstveld met ID) gevuld uit `GET /api/v1/admin/jobs?status=open&limit=200`, met per optie "&lt;titel&gt; · &lt;opdrachtgever&gt; · #&lt;id&gt;". Verplicht zodra "Vastleggen" gekozen is (`job_id` is dan verplicht in `AdminSpecPresentationConsentUpdate`); bij "Intrekken" is de kiezer `disabled` en wordt hij niet meegestuurd. `evidence` is ook hier verplicht. De hint boven de kiezer: "Toestemming voor presentatie geldt per rol, niet in het algemeen."

**Referral-intake.** Eigen modal, geopend vanuit de kandidatenlijst, want er is nog geen kandidaat om een drawer voor te openen. Velden, in deze volgorde: "Volledige naam" (verplicht, max 200), "E-mailadres" (verplicht), "Aangedragen door" (`referred_by`, verplicht, max 200) met de hint "Deze naam staat in de kennisgeving die deze persoon ontvangt", **"Bewijs van toestemming"** (`evidence`, verplicht) met de hint "Wat heeft de aandrager verteld, en wanneer? Bijvoorbeeld: mondeling bevestigd door X op 3 september, hij heeft haar gevraagd.", en "Interne notitie" (`note`, optioneel).

Boven de knoppenrij staat een **niet-inklapbaar informatieblok** met precies wat er gebeurt. Dit is geen juridische disclaimer maar het art. 14-blok als voorbeeld, want de beheerder moet weten wat hij verstuurt:

> Deze persoon ontvangt eenmalig een kennisgeving met een bevestigingslink, geldig 24 uur. Daarin staat: dat wij zijn of haar gegevens hebben ontvangen via een aanbeveling van &lt;aangedragen door&gt;, welke gegevens dat zijn, waarvoor wij ze willen gebruiken, hoe lang wij ze bewaren en hoe hij of zij bezwaar kan maken. De kennisgeving bevat geen vacature en geen wervende tekst. Zonder bevestiging gebeurt er niets en vervalt de invoer na drie maanden.

De naam uit het veld "Aangedragen door" wordt live in dat blok ingevuld, zodat zichtbaar is wat de ontvanger straks leest.

Twee foutgevallen die de backend expliciet teruggeeft, krijgen elk hun eigen inline-melding in plaats van een generieke: het adres staat op de suppressielijst ("Dit adres staat op de suppressielijst. Er mag geen bericht naar dit adres, op geen enkele grondslag.") en er bestaat al een kandidaat met dit adres ("Er is al een kandidaat met dit adres. Open dat dossier; een referral-invoer mag een bestaande grondslag niet overschrijven.", met een link naar die kandidaat als de respons het ID meegeeft; **aanname**: de respons geeft dat ID mee. Als hij dat niet doet, vervalt de link en blijft de zin staan.)

**Staten.** Tab-laden: drie vlakke blokken. Fout: `setContainerLoadError` op de tab. Leeg bestaat niet: er is altijd een toestemmingsstatus, ook als die "geen" is. Alle drie de modals: primaire knop met spinner tijdens verzenden, inline-melding bij 4xx, toast plus drawerherlading bij succes.

**390.** De drawer is `offcanvas-bottom`; de drie kaarten stapelen; de modals worden fullscreen. De vacaturekiezer blijft een native `<select>`, want dat is op mobiel het beste bedienbare element dat er is.

#### 7.3.3 Plaatsingen

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

**Endpoints.** `PATCH /api/v1/admin/pipeline/{entry_id}/stage`, `GET /api/v1/admin/pipeline/{entry_id}/history`. De lijst met entries komt uit de bestaande klant- en kandidaatdetailrespons.

**Wireframe.**

```
PIPELINE
┌ Vacature: Senior Embedded Engineer (#218) ──────────────┐
│ Huidige fase:  [ Screening        ▾ ]   [ Fase wijzigen ]│
│ Laatst gewijzigd: 3 sep 2026 door Beheerder              │
│ ── Historie ───────────────────────────────────────────  │
│ ● 3 sep 2026 14:20  Benaderd → Screening   Beheerder     │
│ ● 28 aug 2026 09:05  (nieuw) → Benaderd    Beheerder     │
└──────────────────────────────────────────────────────────┘
(één kaart per pipeline-entry; bij meer dan drie entries een
 accordeon met alleen de nieuwste opengeklapt)
```

**De faselijst is een open punt, en het scherm doet er niet alsof.** `pipeline_entries.stage` is `VARCHAR(50)` met default `sourced` en zonder CHECK-constraint; het klantportaal tekent vandaag een kanban met vier vaste kolommen (`new`, `screening`, `interview`, `offer`) en stopt alles wat daarbuiten valt in `new`. Dat zijn twee onverenigbare waarheden. Tot de eigenaar de canonieke lijst vaststelt (zie §7.6, beslissing 2) geldt: de `<select>` bevat de vijf waarden die vandaag daadwerkelijk voorkomen (`sourced` = Gesourced, `new` = Nieuw, `screening` = Screening, `interview` = Gesprek, `offer` = Aanbod) **plus** de huidige waarde van de entry als die er niet bij staat, als geselecteerde optie met het achtervoegsel "(bestaande waarde)". Zo kan de UI nooit een fase stilzwijgend wegschrijven die zij niet kent. De historie toont elke `from_stage` en `to_stage` verbatim door dezelfde labelmap, met de ruwe waarde als er geen label is.

**Fase wijzigen.** Select plus knop, geen automatische opslag bij het wisselen van de select: een fasewijziging schrijft een onomkeerbare regel in `pipeline_stage_history` en verdient één bewuste klik. Optimistische update met terugdraaien bij fout: de nieuwe fase verschijnt direct, en bij een 4xx of 5xx springt hij terug met een inline-melding boven de kaart. Na succes wordt de historie opnieuw opgehaald, niet lokaal aangevuld, zodat wat er staat uit de database komt.

**Historie.** Verticale tijdlijn: 2px `--navy-600`-lijn links, per item een 8px stip in `--navy-300` (`--gold-500` voor het nieuwste), tijdstempel in `.gsp-num.fs-xs`, dan "&lt;van&gt; → &lt;naar&gt;", dan de actor. `from_stage: null` toont als "(nieuw)". Maximaal tien items zichtbaar, daarna "Toon alles".

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

De backend eist deze getypte bevestiging **niet**; `AdminEraseRequest` kent alleen `email` en een booleaanse `confirm`. De getypte bevestiging is dus een UI-maatregel bovenop de API, geen weerspiegeling ervan. Dat is aanvaardbaar (de UI mag strenger zijn dan de API, nooit soepeler) en staat hier expliciet zodat een latere bouwer niet denkt dat hij een backendveld mist.

`confirm: true` wordt **niet** standaard meegestuurd. De eerste aanroep gaat zonder. Geeft de backend 409 `erase_admin_or_self_requires_confirm`, dan verschijnt in de modal een tweede, aparte bevestiging: een inline-melding van het type waarschuwing met de tekst "Dit adres hoort bij een beheerdersaccount of bij je eigen account. Wissen verwijdert die toegang." plus een aangevinkt-moet-worden checkbox "Ik begrijp dat hiermee beheerderstoegang verdwijnt" en pas dan een tweede knop die de aanroep herhaalt met `confirm: true`. Twee stappen, niet één vinkje vooraf.

**Suppressielijst.** Datatabel zonder selectie. De API geeft bewust **geen** plaintext-adressen terug, alleen `email_hash`, `email_domain`, `reason` en `created_at`. Het scherm toont dus domein en een ingekorte hash (eerste vier en laatste drie tekens, met de volledige hash in een `title` en een kopieerknop). Er staat boven de tabel één regel uitleg: "Deze lijst bewaart geen volledige e-mailadressen; alleen een onomkeerbare hash en het domein." Dat voorkomt de terugkerende vraag waarom je hier niet op adres kunt zoeken.

**Toevoegen.** Modal met "E-mailadres" (verplicht) en "Reden" (standaard `STOP`, vrij tekstveld). Het is geen destructieve modal, maar wel met een prominente `.gsp-panel` die zegt wat er verder gebeurt, want de backend doet meer dan één ding: de openstaande concept-outreach naar dit adres wordt afgekeurd, de kandidaatrij krijgt `consent_withdrawn_at`, en de prospectrij krijgt `opt_out_at`. Die drie gevolgen staan er woordelijk, want een beheerder die "toevoegen aan lijst" leest verwacht ze niet.

**Staten.** Wisformulier: rust, validatie op e-mailvorm bij `blur`, laadstaat op de knop, inline-melding bij fout, en bij succes een toast plus een resultaatblok dat toont wat er is geraakt (de respons van `erase_person()`). Suppressielijst: standaard laad-, lege- ("Nog geen adressen op de suppressielijst.") en foutstaat.

**390.** Beide kaarten op volle breedte gestapeld. De suppressietabel wordt een kaartlijst met domein groot en hash klein. De wismodal is fullscreen; het bevestigingsveld krijgt `type="email"`, `autocapitalize="off"`, `autocorrect="off"` en `spellcheck="false"`, want een mobiel toetsenbord dat een adres corrigeert maakt de bevestiging onmogelijk te typen.

#### 7.3.6 Users: deblokkeren, activiteitentab, prospects bewerken, healthwidget

Vier kleinere toevoegingen aan bestaande secties.

**(a) Deblokkeren.** `POST /api/v1/admin/users/{user_id}/unlock`. In het rijactiemenu van de gebruikerslijst komt een item "Deblokkeren", direct boven "Impersonate". Het is alleen ingeschakeld wanneer de gebruiker daadwerkelijk vergrendeld is; de gebruikerslijst moet dus `locked_until` en `failed_login_count` tonen. **Aanname**: `GET /api/v1/admin/users` geeft die twee velden mee (`GET /users/{id}` doet dat aantoonbaar). Zo niet, dan haalt de rij ze bij het openen van het menu op via het detail-endpoint, en blijft het item tot dat moment in laadstaat. Een vergrendelde gebruiker krijgt in de statuskolom een tweede badge "Vergrendeld" (familie negatief) met in `.fs-xs.text-muted-navy` eronder "tot &lt;tijdstip&gt;". Deblokkeren gaat via een gewone bevestigingsmodal, geen typebevestiging: het is een herstellende handeling. De modal zegt er wel bij wat het niet doet: "Dit reset geen wachtwoord en beëindigt geen bestaande sessie."

**(b) Activiteitentab.** Nieuwe tab "Activiteit" in de kandidaat- en klantdrawer, gevoed door `GET /api/v1/admin/activities?subject_type=&subject_id=`. Weergave: dezelfde verticale tijdlijn als §7.3.4, met per item het type als chip (de zes waarden uit `ACTIVITY_TYPES`: `note` = Notitie, `call` = Telefoongesprek, `email` = E-mail, `meeting` = Afspraak, `task` = Taak, `status_change` = Statuswijziging), het tijdstempel in `.gsp-num.fs-xs`, de tekst, en de actor. Bovenaan de tab een compact formulier "Activiteit toevoegen" met typeselect, een `<textarea>` en één knop; het klapt uit vanaf een tekstknop en staat niet permanent open. Een taak (`type: "task"`) toont daarnaast zijn afgerond-staat als checkbox die `PATCH /activities/{id}` aanroept. Leeg: "Nog geen activiteiten vastgelegd." plus de knop die het formulier opent.

**(c) Prospects bewerken.** De prospectlijst (sectie Leads) krijgt een bewerkactie die `PUT /api/v1/admin/prospects/{id}` aanroept, in een modal met het formulierpatroon. Bewerkbaar: `status` (vrije tekst met datalist van de waarden die in de huidige lijst voorkomen, want de kolom kent geen CHECK; **aanname**: er is geen canonieke prospectstatuslijst, en het scherm verzint er geen), `notes`, `source_url` en `lawful_basis`. `lawful_basis` is een `<select>` met de drie gevalideerde waarden uit §7.2e, verplicht, met de hint boven het veld: "Zonder vastgelegde grondslag mag er geen outreach naar dit contact (Telecommunicatiewet art. 11.7)." `source_url` valideert client-side op `http://` of `https://`, dezelfde eis als de backend, met de foutregel "Vul een publieke http- of https-URL in".

**(d) Healthwidget.** Nieuwe kaart op het dashboard, rechterkolom, onder Quick Actions. Bron: `GET /api/v1/admin/health`. Vier regels, elk met een statusstip en een waarde: database, OpenRouter, Apollo, en **dubbele profielkoppelingen** (`duplicate_profile_links`). Die laatste is de reden dat de kaart bestaat: hij hoort altijd 0 te zijn, en elke andere waarde betekent dat een kandidaat vanuit meer dan één profielrij gekoppeld is, iets wat de deduplicatie in de kandidatenlijst niet zelf repareert. Weergave: bij 0 een groene stip en "0 dubbele profielkoppelingen", zonder nadruk. Bij een waarde groter dan 0 wordt de hele kaart een inline-melding van het type fout met de tekst "NN dubbele profielkoppelingen. Dit hoort 0 te zijn." plus de knop "Kandidaten openen". Bij `null` (de query kon niet draaien): "Onbekend" in `.text-muted-navy`, niet 0. `candidates_count` en `open_jobs` uit dezelfde respons horen niet in deze kaart: die staan al in de KPI-rij en twee keer hetzelfde getal op één scherm nodigt uit tot vergelijken van dingen die gelijk zijn.

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

De backend geeft geen reden mee, alleen de booleaan. De uitlegregel wordt daarom afgeleid uit gegevens die het portaal al heeft, in deze volgorde, en er wordt precies één getoond:

1. Toestemming ingetrokken (`consent_withdrawn_at` gevuld): "Je hebt je toestemming ingetrokken. Zonder toestemming kunnen wij geen vacatures sturen." Knop: "Toestemming opnieuw geven".
2. Toestemming verlopen (`consent_talentpool_until` in het verleden): "Je toestemming voor de talentpool is verlopen." Knop: "Toestemming verlengen".
3. Toestemmingsomvang beperkt tot matching (`consent_scope === 'matching_only'`): "Je toestemming staat op alleen matching. Voor alerts is ook toestemming voor contact nodig." Knop: "Omvang aanpassen".
4. Geen van bovenstaande: "Wij kunnen op dit moment geen alerts sturen. Neem contact op als dit onverwacht is." Geen knop, wel de contactlink.

**Aanname, expliciet**: het portaal beschikt over `consent_withdrawn_at`, `consent_talentpool_until` en `consent_scope` via `GET /api/v1/candidate/profile`. Als een van die velden er niet in zit, valt de uitleg terug op geval 4. De regel is: liever één eerlijke, algemene zin dan een specifieke die kan liegen.

**Staten.** Rust: schakelaar aan of uit. Wisselen: de schakelaar gaat direct om (optimistisch) en krijgt `aria-busy="true"`; bij een fout springt hij terug met een inline-melding "Kon de instelling niet opslaan, probeer opnieuw" en een retryknop. De schakelaar is nooit `disabled` tijdens het verzenden (dan verliest hij focus), alleen `aria-busy`. Laden bij binnenkomst: schakelaar in laadstaat als vlak blok, label blijft staan. Fout bij binnenkomst: `setContainerLoadError` op de kaart.

**Toetsenbord en aria.** De schakelaar is een `<input type="checkbox" role="switch">` met een echt `<label>`, niet een gestileerde `<div>`. Space wisselt. De waarschuwing eronder is `aria-live="polite"` zodat een schermlezer hoort dat de alerts niet uitgaan, ook als de gebruiker zojuist zelf de schakelaar omzette.

**390.** Schakelaar en label op één rij met het label rechts, minimaal 44px hoog; de waarschuwing eronder op volle breedte, de knop erin volle breedte.

#### 7.3.8 Klantportaal: kanban, analytics, contacten, activiteiten, team

**(a) Kanban met stagewijziging.** `GET /api/v1/client/pipeline`, `PATCH /api/v1/client/pipeline/{entry_id}/stage`. Vandaag tekent `app.js` vier vaste kolommen en dumpt elke onbekende fase in `new`, stil. Dat blijft niet zo: een entry met een fase buiten de vier krijgt een eigen kolom achteraan met de ruwe waarde als kop en een `title` "Fase buiten het standaardoverzicht". Niets wordt stilzwijgend verplaatst.

Kolomkop: fasenaam plus telling in `.gsp-num`. Kaart per entry: kandidaatnaam of, zonder presentatietoestemming, het geanonimiseerde label, daaronder de vacaturetitel in `.fs-xs.text-muted-navy`, daaronder de laatste wijzigingsdatum. **Stagewijziging gaat niet via slepen.** Elke kaart heeft rechtsboven een `<select>` met de fasen plus, bij een fase buiten de vier, de bestaande waarde. Slepen is op een telefoon onbruikbaar, met een toetsenbord onbereikbaar zonder een tweede, parallelle bediening, en het is hier geen frequente handeling. Optimistische verplaatsing met terugdraaien bij fout, toast bij succes.

Staten: laden = vier kolomkoppen met elk twee vlakke kaartblokken; leeg per kolom = "Geen kandidaten in deze fase" in `.fs-xs.text-muted-navy`; leeg over de hele kanban = één kaart "Er staan nog geen kandidaten in de pipeline." plus de knop "Vacature plaatsen"; fout = `setContainerLoadError` over de hele kanban, want een halve kanban is misleidend. Op 390px worden de kolommen een verticale accordeon met de fasenaam plus telling als kop, de eerste fase met inhoud opengeklapt.

**(b) Analytics: alleen velden met een bron.** `GET /api/v1/client/analytics` geeft vijf velden. Het scherm toont er precies vijf, elk met een KPI-tegel (§7.2g) of een klein staafoverzicht, en niets erbij:

| Veld | Weergave | Bij `null` of leeg |
|---|---|---|
| `time_to_hire_avg_days` | Tegel, "NN,N dagen" | "n.v.t. (nog geen vervulde vacature)" |
| `pipeline_funnel` | Horizontale staven per fase, label uit dezelfde fasemap als de kanban | "Nog geen kandidaten in de pipeline" |
| `source_breakdown` | Horizontale staven per herkomst, labels uit §7.2e (de backend groepeert al op `SOURCE_FAMILY`) | "Nog geen herkomstgegevens" |
| `offer_rate` | Tegel, "NN,N%" | Bij nul sollicitaties geeft de backend 0; het scherm toont dan "n.v.t. (nog geen sollicitaties)", want 0% uit nul metingen is geen percentage |
| `cost_per_hire_avg` | Tegel, bedrag | **"n.v.t."**, met eronder in `.fs-xs.text-muted-navy`: "Wordt pas getoond zodra er kostengegevens per plaatsing zijn vastgelegd." |

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

1. **Focustrap in modal en drawer.** Bootstrap's `Modal` en `Offcanvas` leveren die; de eigen overlay in `admin.js` niet, en die verdwijnt daarom (§7.2c). Tab loopt rond binnen het geopende element en bereikt niets erachter.
2. **ESC sluit** elke modal, elke drawer en elk actiemenu (`.action-menu`, dat vandaag alleen op een klik buiten zichzelf reageert). Bij een openstaand formulier met wijzigingen komt eerst de bevestiging "Wijzigingen weggooien?"; ESC op die bevestiging annuleert het sluiten, niet het formulier.
3. **Focus keert terug.** Bij het sluiten van een modal, drawer of menu gaat de focus terug naar het element dat het opende. Een lijst die na een actie herlaadt, herstelt de focus op de rijactie van dezelfde record; is die record weg (verwijderd, verwerkt), dan gaat de focus naar de tabelkop en kondigt een `aria-live="polite"`-regio aan wat er gebeurd is.
4. **Tabvolgorde volgt de leesvolgorde.** Nergens een `tabindex` groter dan 0. Geen element dat er klikbaar uitziet zonder tab-bereikbaar te zijn, en geen tab-stop zonder zichtbare focusstaat. Elke `:hover`-staat in dit document heeft een identieke `:focus-visible`-staat (§8.x.0); dat wordt met tab-navigatie geverifieerd, niet visueel geschat.
5. **Contrast op donker.** De vloeren uit §7.1.2 gelden zonder uitzondering: tekst minimaal 4,5:1 (grote tekst 3:1), niet-tekstuele grenzen en icoonvormen minimaal 3:1. `--navy-300` is geen tekstkleur. `--gold-ink` is op donker verboden. `scripts/css_tokens_check.py` (§8.x.8) krijgt een tweede tabel met de donkere achtergrond als referentie, zodat een tokencombinatie die op wit slaagt en op navy zakt de build laat falen.
6. **`prefers-reduced-motion`.** Elke overgang in dit document is 150 tot 200ms en betreft uitsluitend kleur, positie of dekking van al zichtbare elementen. Bij `reduce` gaan alle duren naar 0,01ms en blijft elke eindtoestand functioneel en visueel compleet: geen skeleton met shimmer, geen toast die zonder animatie onzichtbaar blijft, geen drawer die alleen ingeschoven bestaat. De globale regel uit `website/styles.css:1281-1290` wordt in de portalen en het paneel overgenomen, want die pagina's laden dat bestand niet allemaal.

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

### 7.6 Drie beslissingen voor de eigenaar

Deze drie zijn in dit document voorlopig ingevuld zodat er gebouwd kan worden, maar ze zijn geen ontwerpkeuze en horen bij de eigenaar.

1. **Categoriebreed goedkeuren van bewaartermijnen op een telefoon.** Dit document sluit die ene actie uit op 390px (§7.3.1), terwijl elke andere actie daar wel werkt. Dat is een oordeel over risico, niet over techniek.
2. **De canonieke faselijst van de pipeline.** `pipeline_entries.stage` is vrij tekstveld met default `sourced`; het klantportaal tekent vier vaste kolommen. Tot er één lijst is vastgesteld, toont het scherm vijf waarden plus de bestaande waarde van de rij (§7.3.4). Een vastgestelde lijst hoort een CHECK-constraint in de database te krijgen, niet alleen een select in de UI.
3. **Getypte bevestiging waar de backend die niet eist.** Bij AVG-wissen (§7.3.5) en bij de droogloop (§7.3.1) legt de UI een zwaardere handeling op dan de API vraagt. Dat is bewust, maar het betekent ook dat een toekomstige API-cliënt (of een routine) die stap overslaat. Als de eigenaar dit als een echte waarborg beschouwt en niet als een wrijvingsmaatregel, hoort hij in de backend, niet in de UI.

---

### 7.7 Adminpaneel: secties zoals ze nu draaien

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

Nieuw in dit document en nog te bouwen: `#retention` (§7.3.1), `#placements` (§7.3.3) en `#gdpr` (§7.3.5).

Er is geen `superadmin`-rol; elk beheerdersaccount valt onder de MFA-flow uit `ENTERPRISE-ARCHITECTURE-SPEC.md` §3.2. Er is een `impersonate`-actie (gebruikerslijst) die de beheerder een token van 15 minuten als de doelgebruiker geeft en diens portaal opent; het eigen token van de beheerder wordt apart geparkeerd (`gsp_admin_token` in `localStorage`, nooit de normale sessieplek) voor de duur van de impersonatie. Zowel het kandidaat- als het klantportaal toont dan een blijvende goud-op-navy banner ("Je bekijkt als &lt;rol&gt;. Terug naar admin") met een knop die de beheerderssessie herstelt en terugkeert naar `#dashboard`.

Lege en foutstaten in het hele paneel volgen de Nederlandse conventie: "Kon niet laden, probeer opnieuw" bij een fout, "Nog geen …" bij leeg.

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
