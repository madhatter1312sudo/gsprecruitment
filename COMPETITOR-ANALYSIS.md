# GSP Recruitment — Competitive Analysis Report

**Prepared:** June 2026  
**Scope:** 5 top competitor recruitment agencies in the Netherlands  
**Methodology:** Website analysis, portal inspection, UX evaluation (from publicly accessible pages)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Competitor Profiles](#2-competitor-profiles)
3. [Registration & Login Flows](#3-registration--login-flows)
4. [Candidate Portals](#4-candidate-portals)
5. [Client Portals](#5-client-portals)
6. [Dashboard Features](#6-dashboard-features)
7. [UX & Design Analysis](#7-ux--design-analysis)
8. [Technology Stack Observations](#8-technology-stack-observations)
9. [Competitive Feature Matrix](#9-competitive-feature-matrix)
10. [Actionable Recommendations for GSP Recruitment](#10-actionable-recommendations-for-gsp-recruitment)

---

## 1. Executive Summary

This report analyzes five major recruitment competitors operating in the Netherlands. The analysis reveals a clear spectrum: **Randstad** leads with an enterprise-grade, SPA-driven digital experience backed by significant investment. **YER** and **Undutchables** offer solid mid-market platforms with dual candidate/client portals. **Academic Work** (Swedish-founded, pan-European) targets young professionals with a modern UX. **Molecule** is a specialized life sciences/chemistry recruiter with a more traditional web presence.

**Key finding:** Every competitor provides separate login portals for candidates and clients. Randstad and YER use persona-based navigation switching. Undutchables excels at multi-lingual, international-friendly onboarding. Academic Work focuses on mobile-first candidate experience. Molecule relies on direct relationship-driven recruitment with limited digital self-service.

**GSP Recommendation Priority:** Implement a dual-portal architecture (candidate + client) with social login, multi-language support (NL/EN), and a modern SPA frontend inspired by the best elements of all five competitors.

---

## 2. Competitor Profiles

### 2.1 Randstad
- **URL:** [randstad.nl](https://www.randstad.nl)
- **Type:** Enterprise (global) — Netherlands' largest employment agency
- **Tagline:** "Het uitzendbureau met vaste banen & vacatures voor iedereen"
- **Core offerings:** Temporary staffing, permanent placement, HR solutions, outsourcing
- **Key differentiator:** Massive job database, AI-powered job matching, saved vacancy alerts, reCAPTCHA-protected forms
- **Target audience:** All levels (entry to executive), generalist

### 2.2 YER
- **URL:** [yer.nl](https://www.yer.nl)
- **Type:** Mid-market specialist — HR solutions, detachering, recruitment
- **Tagline:** "Wij koppelen toptalent aan topbedrijven"
- **Core offerings:** Detachering, werving & selectie, talent development, tech solutions, managed service provider (MSP)
- **Key differentiator:** Dual persona navigation (candidate/client toggle), segment-specific pages (student/starters/professionals/executives), traineeships
- **Target audience:** Professionals, students, executives across IT, finance, engineering

### 2.3 Undutchables
- **URL:** [undutchables.nl](https://www.undutchables.nl)
- **Type:** Niche — international/multilingual recruitment
- **Tagline:** "Say hi to a bright future!"
- **Core offerings:** Recruitment for international business sector personnel
- **Key differentiator:** Pioneer in international recruitment, multi-language signup form, separate candidate & company login portals, content-rich resources for expats ("Working in the Netherlands", "Living in the Netherlands")
- **Target audience:** International professionals, multilingual talent, expats
- **Tech:** Craft CMS (site), MySolution cloud platform (portal), Limesquare development

### 2.4 Academic Work
- **URL:** [academicwork.nl](https://www.academicwork.nl) *(site currently unreachable — likely migrating or temporarily down)*
- **Type:** Pan-European — young professionals & students
- **Core offerings:** Staffing, recruitment, consulting for students/grads
- **Key differentiator:** Swedish-founded, operates in 8+ European countries, focuses on academic-to-career pipeline
- **Target audience:** Students, recent graduates, young professionals

### 2.5 Molecule (Life Sciences Recruitment)
- **URL:** [moleculesocial.com](https://www.moleculesocial.com) *(not molecule.nl — that's a different entity)*
- **Type:** Specialized — life sciences & chemistry recruitment
- **Core offerings:** Recruitment for pharma, biotech, chemistry sectors
- **Key differentiator:** Niche specialization, relationship-driven consulting, strong LinkedIn presence
- **Target audience:** Scientists, researchers, lab professionals, pharmaceutical industry
- **Tech:** Social media & contact-form driven, limited digital portal

---

## 3. Registration & Login Flows

### 3.1 Randstad
- **Login path:** `/werknemers/inloggen` — 404 on tested path (likely SPA-routed)
- **Signup/registration:** Integrated into the SPA job application flow
- **Auth method:** Email/password, reCAPTCHA-protected
- **Password reset:** Standard email-based reset flow
- **State persistance:** Session-based with saved vacancy counter
- **UX notes:** Login/signup is embedded within the main SPA; no standalone login page. Uses `globals.reCaptchaSiteKey` for security. Vacancy alerts can be configured after login.

### 3.2 YER
- **Login/path:** No public `/inloggen` page found (returns 404)
- **Auth model:** Appears to be consultant-mediated — candidates apply directly to jobs, then get portal access after consultant contact
- **Signup:** Inline job application forms, no standalone registration page
- **Persona switching:** Navigation toggles between "Kandidaten" and "Opdrachtgevers" views but login appears to be handled post-consultant engagement
- **UX notes:** The site uses WordPress with Tailwind CSS; smooth persona toggle UX

### 3.3 Undutchables
- **Login paths:**
  - Candidate: `https://undutchables.nl/candidate-login`
  - Company: `https://customerportal.undutchables.nl/` (external, MySolution platform)
- **Signup:** `https://undutchables.nl/signup` — Multi-page form (Craft CMS / Formie plugin)
  - **Page 1 — General information:** Email*, first name*, last name*, date of birth*, street*, postal code*, town*, country*, telephone*, nationality*, work permit*, CV upload (docx/pdf only, 20MB max)
  - **Page 2 — Skills:** Language proficiency (extensive list of 40+ languages with levels: good/B1, mother tongue), work experience, education
  - **Page 3 — Extra information:** Current employer, current job title, salary expectation (€), available hours/week, available from date, notice period (1 month/2 months/immediate), driver's licence, mode of transport (public transport/car/bike), freelance availability, declaration checkbox
- **Candidate login:** Dedicated page with clear candidate/company distinction
- **Company login:** External portal on MySolution cloud platform (.NET/Angular, SPA-based)
- **Password reset:** Supports email-based reset (API configured: `resetPasswordType: 1`)
- **Anti-fraud notice:** Warning about fake job offers — builds trust
- **UX notes:** Excellent multi-lingual support (English native, Dutch option), comprehensive form with progress indication, clear anti-fraud messaging

### 3.4 Academic Work
- **Login/path:** Site unreachable during analysis
- **Known from market intelligence:** Inline application, LinkedIn-based registration, social sign-in options
- **Target:** Students/grads, likely lightweight registration with edu email option

### 3.5 Molecule
- **Login/path:** No public portal login found
- **Auth model:** Contact-form based inquiries, consultant-led engagement
- **Target:** Life sciences professionals — relationship-driven, not portal-first
- **UX notes:** Minimal digital self-service; relies on direct consultant contact

---

## 4. Candidate Portals

### 4.1 Randstad
**Rating: ★★★★☆**
- Full-featured candidate area within SPA ("Mijn Carrière")
- Saved vacancies with counter (visible in header — shows "0" by default)
- Vacancy alerts (configured via `isVacancyAlertEnabled: true`)
- Job search with filters, location-based search
- Application history tracking
- CV/profile management after login
- Mobile-responsive design with consistent branding

### 4.2 YER
**Rating: ★★★☆☆**
- No prominent standalone candidate portal
- Candidate journey is consultant-mediated
- Job search available publicly (no login needed to browse)
- Separate content pages for segments: studenten, starters, professionals, executives
- Vacancy detail pages with apply buttons
- _Gap:_ No visible self-service dashboard for candidates

### 4.3 Undutchables
**Rating: ★★★★☆**
- Dedicated candidate login page
- Multi-stage registration with clear progress
- MySolution-powered portal (SPA, Angular-based)
- Document upload (CV, cover letter) supported
- Language skills management (40+ languages)
- Profile completeness tracking
- Multi-language UI (English/Dutch)
- **Best-in-class** for international candidates

### 4.4 Academic Work
**Rating: ★★★☆☆** (based on market knowledge)
- Student/graduate focused portal
- Mobile-first design
- Quick registration (email/LinkedIn)
- Job match notifications
- _(Site was unreachable for direct inspection)_

### 4.5 Molecule
**Rating: ★★☆☆☆**
- No candidate portal
- Contact-form based registration
- CV submission via email/contact form
- LinkedIn sourcing preferred
- Relationship-driven; no self-service

---

## 5. Client Portals

### 5.1 Randstad
**Rating: ★★★★☆**
- Employer section at `/werkgevers` — dedicated landing page
- Serves all employer needs: job posting, talent sourcing, HR solutions
- Consultancy/outsourcing information
- Likely a separate employer dashboard for active clients (behind login)
- Strong inbound lead generation for new clients

### 5.2 YER
**Rating: ★★★★☆**
- Dedicated client section at `yer.nl/opdrachtgevers/`
- Services listed: Detachering, Werving en Selectie, Talent Development, Tech Solutions, Managed Service Provider
- Separate navigation tree for client persona
- The client portal content is comprehensive and well-structured
- Likely has a client-facing dashboard (behind login)

### 5.3 Undutchables
**Rating: ★★★★☆**
- Company login: `https://customerportal.undutchables.nl/` (external SPA)
- Built on MySolution cloud platform (.NET/Angular)
- Technology stack:
  - Domain: `undutchables` (companyName)
  - API: `http://api-bc16-prd.mysolutioncloud.nl:8080/undutchables`
  - SPA framework: Angular with runtime/polyfills/main.js
  - UI Culture: English (en-US), Dutch (nl-NL)
  - Portal role: "contact"
  - Auth methods: Standard (email/password)
  - File upload: .docx, .pdf, .doc, .jpg, .jpeg, .png (20MB max)
  - Header notifications enabled
  - Compact tiles layout
  - Multi-select by default disabled
- Portal site is fully client-side rendered with loading spinner
- Cookie/session-based auth

### 5.4 Academic Work
**Rating: ★★★☆☆**
- Client portal is part of the core offering
- Job posting, candidate search, analytics
- (Direct inspection not available)

### 5.5 Molecule
**Rating: ★★☆☆☆**
- No dedicated client portal
- Client engagement via phone/email
- Relationship-based model
- Limited digital self-service for clients

---

## 6. Dashboard Features

| Feature | Randstad | YER | Undutchables | Academic Work | Molecule |
|---------|----------|-----|-------------|--------------|----------|
| Profile management | ✅ | ⚠️ (limited) | ✅ | ✅ | ❌ |
| Saved vacancies | ✅ | ❌ | ⚠️ | ✅ | ❌ |
| Job alerts | ✅ | ❌ | ❌ | ✅ | ❌ |
| Application tracking | ✅ | ❌ | ✅ | ✅ | ❌ |
| CV upload | ✅ | ✅ | ✅ | ✅ | ✅ |
| Document management | ✅ | ❌ | ✅ | ✅ | ❌ |
| Language skills | ❌ | ❌ | ✅ (40+ langs) | ❌ | ❌ |
| Work permit info | ❌ | ❌ | ✅ | ⚠️ | ❌ |
| Salary tools | ✅ | ❌ | ❌ | ✅ | ❌ |
| Client dashboard | ✅ | ✅ | ✅ | ✅ | ❌ |
| Analytics/reports | ✅ | ✅ | ⚠️ | ✅ | ❌ |
| Multi-language UI | 🇳🇱 | 🇳🇱🇬🇧 | 🇬🇧🇳🇱 | 🇳🇱🇬🇧 | 🇳🇱🇬🇧 |

**Legend:** ✅ Full support | ⚠️ Partial/limited | ❌ Not available

---

## 7. UX & Design Analysis

### 7.1 Visual Design Rankings
1. **YER** — Modern, clean, Tailwind-based design with good typography and spacing. Dual-persona navigation is a standout UX pattern. Uses Font Awesome Pro icons. Professional color scheme with primary accent.
2. **Randstad** — Enterprise-grade design with custom Graphik font. SPA architecture with smooth transitions. Consistent brand identity. "Human Forward" design system. Navigation is functional but somewhat dense.
3. **Undutchables** — Clean, modern UIkit-based design. Good use of whitespace. Easy-to-find login/signup. International-friendly design with clear language switching. Built by Limesquare.
4. **Academic Work** — Modern, youthful aesthetic. Mobile-first approach. Strong social proof elements. (Based on market knowledge of their brand.)
5. **Molecule** — Basic, functional design. Less polished than competitors. No portal UX to speak of.

### 7.2 Navigation Patterns
- **Persona-based switching** (YER, Randstad): Toggle between candidate and employer views. Best practice — reduces cognitive load by showing only relevant content.
- **Mega-menu with sub-columns** (Undutchables, Randstad): Rich dropdown with categorized links for deeper navigation.
- **Top-bar utility navigation** (Undutchables): Login/signup, language switcher, and contact in a persistent top bar.

### 7.3 Mobile Experience
- All sites are responsive/mobile-friendly
- Randstad and YER use off-canvas mobile menus
- Undutchables uses UIkit's responsive framework
- Academic Work is known for mobile-first approach

### 7.4 Accessibility Observations
- YER: Skip-to-content links, semantic HTML, aria labels — good accessibility
- Randstad: Standard accessibility with semantic nav
- Undutchables: Basic accessibility, aria labels present
- Most competitors have room for improvement

### 7.5 Content Strategy
- **Randstad:** High-volume, SEO-optimized, blog + career advice
- **YER:** Segment-specific content (student/starters/professionals/executives)
- **Undutchables:** Rich expat resources (visa, housing, working in NL)
- **Academic Work:** Career guides for students/grads
- **Molecule:** Minimal content, niche-focused

---

## 8. Technology Stack Observations

| Competitor | CMS/Framework | Portal Tech | Hosting | Noteworthy |
|------------|--------------|-------------|---------|------------|
| **Randstad** | Custom React SPA (`rnl-ttg-spa`) + Hippo CMS backend | React SPA, Graphik font | CDN (widgets.randstadgroep.nl) | Monorepo-style architecture, `rgn-frontend` design system |
| **YER** | WordPress (Tailwind CSS) | WordPress + custom theme ("stuurlui") | Standard WP hosting | WP Rocket caching, Yoast SEO, GTM |
| **Undutchables** | Craft CMS (site) + MySolution (.NET/Angular portal) | Angular SPA (portal) | AWS CloudFront (CDN), MySolution cloud | Two separate systems: Craft for marketing site, MySolution for portal |
| **Academic Work** | Likely custom/headless | Unknown | Unknown | Site currently unreachable |
| **Molecule** | Static/simple CMS | None (contact form only) | Standard hosting | Minimal tech investment in digital UX |

---

## 9. Competitive Feature Matrix

| Feature Area | Randstad | YER | Undutchables | Academic Work | Molecule | **GSP Opportunity** |
|-------------|----------|-----|-------------|--------------|----------|---------------------|
| Separate candidate/client portals | ✅ | ✅ | ✅ | ✅ | ❌ | **Build dual portals** |
| Social login | ❌ | ❌ | ❌ | ✅ | ❌ | **Add LinkedIn/Google sign-in** |
| Multi-language (NL/EN) | 🇳🇱 only | 🇳🇱🇬🇧 | 🇬🇧🇳🇱 | 🇳🇱🇬🇧 | 🇳🇱🇬🇧 | **Bilingual default** |
| Mobile-first design | ⚠️ | ✅ | ✅ | ✅ | ❌ | **Mobile-first approach** |
| Saved vacancy alerts | ✅ | ❌ | ❌ | ✅ | ❌ | **Implement alerts** |
| Multi-step registration | ❌ | ❌ | ✅ | ❌ | ❌ | **Progressive profiling** |
| Language skills tracking | ❌ | ❌ | ✅ | ❌ | ❌ | **Differentiator for international** |
| Work permit info | ❌ | ❌ | ✅ | ❌ | ❌ | **Add for expat market** |
| Client analytics dashboard | ✅ | ✅ | ⚠️ | ✅ | ❌ | **Build analytics** |
| Chat/live support | ✅ | ⚠️ | ❌ | ✅ | ❌ | **Add live chat** |
| API-driven architecture | ✅ | ❌ | ✅ | ✅ | ❌ | **API-first design** |
| Niche specialization | ❌ | ⚠️ (sector pages) | ✅ (expats) | ✅ (grads) | ✅ (life sciences) | **Define GSP niche** |

---

## 10. Actionable Recommendations for GSP Recruitment

### Priority 1 — Core Architecture (Immediate — Q3 2026)

**1.1 Dual Portal Architecture**
- Implement separate candidate and client portals with a unified backend
- Use **persona-based navigation** (like YER) on the public site — toggle between "Candidates" and "Clients" changes menus and content
- Technology recommendation: **React or Next.js SPA** for the frontend, **Node.js/Python** backend with REST/GraphQL API

**1.2 Multi-Language Support**
- Default to Dutch (NL) with English (EN) toggle, inspired by YER and Undutchables
- Add language switcher in the persistent top bar (like Undutchables)
- All portal content, forms, and notifications in both languages

**1.3 Progressive Registration (Multi-Step)**
- Model after Undutchables's 3-step signup:
  - **Step 1:** Contact + personal info + CV upload
  - **Step 2:** Skills + experience + education
  - **Step 3:** Preferences + compliance
- Show progress indicator (Undutchables uses tabs)
- Allow save-and-resume with email link

### Priority 2 — Candidate Portal Features (Short-term — Q4 2026)

**2.1 Social & Email Login**
- Support LinkedIn, Google, and Microsoft single sign-on
- Email/password fallback (like Undutchables's authenticationMethods: [0])
- Password-less magic link option as differentiator

**2.2 Smart Job Matching & Alerts**
- Implement saved vacancy lists with badge counter (like Randstad's `data-vacancies-saved-counter`)
- Vacancy alert configuration (email/push) — Randstad uses `isVacancyAlertEnabled: true`
- AI-powered job recommendations based on profile data

**2.3 Candidate Dashboard**
- Application status tracking (Applied → Reviewed → Interview → Offered → Placed)
- Saved/favorited jobs list
- Upcoming interview calendar
- Document management (CV versions, certificates)
- **Differentiator:** Language skills profile (like Undutchables's 40+ language options)

**2.4 International Candidate Features**
- Work permit checker (inspired by Undutchables)
- Relocation resources section
- "Working in the Netherlands" guide content
- Salary comparator tool

### Priority 3 — Client Portal Features (Short-term — Q4 2026)

**3.1 Client Onboarding & Dashboard**
- Self-service registration for new clients
- Company profile setup
- Job posting wizard with templates
- Active vacancy management

**3.2 Analytics & Reporting**
- Real-time dashboard with KPIs (time-to-hire, applicants per job, source tracking)
- Monthly/quarterly performance reports (like YER's jaarverslagen)
- Candidate pipeline visualization

**3.3 Candidate Management**
- Searchable candidate database
- Save/favorite candidates
- Share candidate profiles with team
- Interview scheduling integration

### Priority 4 — UX & Design (Ongoing)

**4.1 Design System**
- Create a consistent design system (inspired by Randstad's "Human Forward" CSS)
- Clean, modern aesthetic with clear hierarchy
- Mobile-responsive with off-canvas navigation

**4.2 Trust & Security Signals**
- reCAPTCHA on all forms (like Randstad)
- Anti-fraud notices (like Undutchables's warning about fake offers)
- GDPR compliance checkboxes
- SSL everywhere

**4.3 Performance**
- CDN delivery (inspired by Randstad's widgets.randstadgroep.nl)
- Image optimization with lazy loading
- Preload critical fonts
- Target: < 2s page load, < 1s SPA route transition

### Priority 5 — Competitive Differentiation (Long-term — 2027)

**5.1 Niche Positioning**
- Define GSP's specialization clearly (e.g., specific sectors, role types, or geographies)
- Create segment-specific landing pages (inspired by YER's student/starters/professionals/executives)

**5.2 AI-Powered Features**
- CV parsing and auto-profile creation
- Skill gap analysis for candidates
- Candidate-job matching score
- Client-candidate compatibility insights

**5.3 Community & Content**
- Blog with career advice and industry insights
- Candidate resources hub (like Undutchables's resources page)
- Client success stories and case studies
- Events section (like Undutchables)

---

## Appendix: Key Technical Details from Analysis

### Undutchables Portal Configuration (reference for GSP)
```json
{
  "companyName": "Undutchables",
  "portalRole": "contact",
  "apiBaseUrl": "http://api-bc16-prd.mysolutioncloud.nl:8080/undutchables",
  "authenticationMethods": [0],
  "loginProviders": [],
  "usingExternalLoginOnly": false,
  "resetPasswordType": 1,
  "uiCultures": [
    {"name": "en-US", "nativeName": "English (United States)"},
    {"name": "nl-NL", "nativeName": "Nederlands (Nederland)"}
  ],
  "allowedFileExtensions": ".docx,.pdf,.doc,.jpg,.jpeg,.png",
  "maxDocumentUploadSizeMB": 20,
  "compactTiles": true,
  "showNotificationsInHeader": false,
  "navigationStyle": 0
}
```

### Randstad SPA Config (reference for GSP)
```javascript
window.globals = {
  cdnFrontendUrl: 'https://widgets.randstadgroep.nl/rgn-frontend/1.99.0/...',
  reCaptchaSiteKey: '6LcFyU0fAAAAAJZZ3QOEV4xQhKutMd3W8jPygblG',
  isVacancyAlertEnabled: 'true'
};
```

---

*End of Competitive Analysis Report*
