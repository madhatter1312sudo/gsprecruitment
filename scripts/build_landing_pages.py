#!/usr/bin/env python3
"""
Build the 16 city x discipline landing pages under website/vacatures/<city>/
from website/data/landing-copy.json, per design-spec-batch.md item 6.

Deterministic and idempotent: running this twice in a row must produce byte-
identical output (no timestamps, no randomness) -- the build only reads
website/data/landing-copy.json and writes the 16 HTML files.

Usage:
  python3 scripts/build_landing_pages.py
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE_DIR = REPO_ROOT / "website"
DATA_FILE = WEBSITE_DIR / "data" / "landing-copy.json"
OUT_DIR = WEBSITE_DIR / "vacatures"

# Fixed order -- matches the task and the copy file's key order.
CITY_SLUGS = ["eindhoven", "veldhoven", "helmond", "best"]
DISCIPLINE_SLUGS = [
    "embedded-software",
    "mechatronica-besturingssoftware",
    "ot-cybersecurity",
    "test-en-verificatie",
]

# discipline slug -> (department string in pool_vacancies.json / #deptFilter,
#                      short display label NL, short display label EN)
DISCIPLINE_META = {
    "embedded-software": {"dept": "Embedded software", "nl": "Embedded software", "en": "Embedded software"},
    "mechatronica-besturingssoftware": {"dept": "Mechatronica", "nl": "Mechatronica", "en": "Mechatronics"},
    "ot-cybersecurity": {"dept": "OT-security", "nl": "OT-cybersecurity", "en": "OT cybersecurity"},
    "test-en-verificatie": {"dept": "Test en verificatie", "nl": "Test en verificatie", "en": "Test and verification"},
}

# Full bilingual label as used in #deptFilter / the hero search select, for
# the crosslink lists (item 6, "Other fields" block).
DISCIPLINE_FILTER_LABEL = {
    "embedded-software": {"nl": "Embedded software / C++", "en": "Embedded software / C++"},
    "mechatronica-besturingssoftware": {"nl": "Mechatronica / FPGA", "en": "Mechatronics / FPGA"},
    "ot-cybersecurity": {"nl": "OT-Cybersecurity", "en": "OT-Cybersecurity"},
    "test-en-verificatie": {"nl": "Test en verificatie", "en": "Test and verification"},
}


def esc(s: str) -> str:
    """Minimal HTML-text escaping for values interpolated into markup
    (title/meta attribute values, copy text). All copy in landing-copy.json
    is our own authored content (§ CLAUDE.md provenance), not user input --
    this is a belt-and-suspenders pass, matching GSP.esc()'s rule set."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def header_block() -> str:
    return """<a href="#main-content" class="skip-link"><span class="lang-en">Skip to main content</span><span class="lang-nl">Ga naar hoofdinhoud</span></a>

<div id="preloader"><img src="../../logo.png" alt="GSP Recruitment"><div class="preloader-bar"><div class="preloader-fill" id="preloaderFill"></div></div></div>
<header class="header" id="header">
  <div class="header-inner">
    <a href="../../index.html" class="header-logo"><img src="../../logo.png" alt="GSP Recruitment" width="120" height="28"></a>
    <div class="audience-switch" aria-label="Werkgevers of kandidaten">
      <a href="../../werkgevers.html" class="aud-opt"><i class="fas fa-building"></i><span class="lang-en">Employers</span><span class="lang-nl">Werkgevers</span></a>
      <a href="../../kandidaten.html" class="aud-opt"><i class="fas fa-user"></i><span class="lang-en">Candidates</span><span class="lang-nl">Kandidaten</span></a>
    </div>
    <nav class="nav" id="nav">
      <ul class="nav-list">
        <li class="nav-aud"><a href="../../werkgevers.html" class="nav-link"><span class="lang-en">For employers</span><span class="lang-nl">Voor bedrijven</span></a></li>
        <li class="nav-aud"><a href="../../kandidaten.html" class="nav-link"><span class="lang-en">For candidates</span><span class="lang-nl">Voor kandidaten</span></a></li>
        <li><a href="../../vacatures.html" class="nav-link"><span class="lang-en">Vacancies</span><span class="lang-nl">Vacatures</span></a></li>
        <li><a href="../../blog/index.html" class="nav-link"><span class="lang-en">Knowledge hub</span><span class="lang-nl">Kennisbank</span></a></li>
        <li><a href="../../over-ons.html" class="nav-link"><span class="lang-en">About us</span><span class="lang-nl">Over ons</span></a></li>
        <li><a href="../../contact.html" class="nav-link"><span class="lang-en">Contact</span><span class="lang-nl">Contact</span></a></li>
      </ul>
    </nav>
    <div class="header-actions">
      <a href="../../contact.html?type=vacancy" class="btn btn-gold btn-sm"><span class="lang-en">Submit a vacancy</span><span class="lang-nl">Vacature aanmelden</span></a>
      <button class="lang-btn" id="langEn">EN</button>
      <button class="lang-btn" id="langNl">NL</button>
      <button class="btn btn-ghost btn-sm" id="loginBtn"><i class="fas fa-sign-in-alt"></i> <span class="lang-en">Sign In</span><span class="lang-nl">Inloggen</span></button>
      <button class="hamburger" id="hamburger" aria-label="Menu"><span></span><span></span><span></span></button>
    </div>
  </div>
</header>"""


def footer_block() -> str:
    return """<footer class="footer">
  <div class="container">
    <div class="footer-grid footer-grid-5">
      <div class="footer-brand">
        <img src="../../logo.png" alt="GSP Recruitment">
        <p class="lang-en">Specialist tech &amp; IT recruitment across the Netherlands.</p>
        <p class="lang-nl">Gespecialiseerde tech &amp; IT-recruitment in heel Nederland.</p>
        <p class="lang-en">Specialist, personal, and honest.</p>
        <p class="lang-nl">Specialistisch, persoonlijk en eerlijk.</p>
      </div>
      <div><h4><span class="lang-en">Sectors</span><span class="lang-nl">Sectoren</span></h4>
        <ul class="footer-links">
          <li><a href="../../werkgevers.html#specialisms"><span class="lang-en">Embedded software</span><span class="lang-nl">Embedded software</span></a></li>
          <li><a href="../../werkgevers.html#specialisms"><span class="lang-en">C++ development</span><span class="lang-nl">C++ development</span></a></li>
          <li><a href="../../werkgevers.html#specialisms"><span class="lang-en">Mechatronics</span><span class="lang-nl">Mechatronica</span></a></li>
          <li><a href="../../werkgevers.html#specialisms"><span class="lang-en">Cybersecurity</span><span class="lang-nl">Cybersecurity</span></a></li>
        </ul></div>
      <div><h4><span class="lang-en">For employers</span><span class="lang-nl">Voor werkgevers</span></h4>
        <ul class="footer-links">
          <li><a href="../../werkgevers.html"><span class="lang-en">How we work</span><span class="lang-nl">Werkwijze</span></a></li>
          <li><a href="../../werkgevers.html#specialisms"><span class="lang-en">Specialisms</span><span class="lang-nl">Vakgebieden</span></a></li>
          <li><a href="../../contact.html"><span class="lang-en">Share a vacancy</span><span class="lang-nl">Deel een vacature</span></a></li>
          <li><a href="../../werkwijze.html"><span class="lang-en">Our way of working</span><span class="lang-nl">Onze werkwijze</span></a></li>
        </ul></div>
      <div><h4><span class="lang-en">For candidates</span><span class="lang-nl">Voor kandidaten</span></h4>
        <ul class="footer-links">
          <li><a href="../../vacatures.html"><span class="lang-en">Vacancies</span><span class="lang-nl">Vacatures</span></a></li>
          <li><a href="../../kandidaten.html#salary"><span class="lang-en">Salary data</span><span class="lang-nl">Salarisdata</span></a></li>
          <li><a href="../../salarisgids.html"><span class="lang-en">Salary guide</span><span class="lang-nl">Salarisgids</span></a></li>
          <li><a href="../../kandidaten.html#quiz"><span class="lang-en">Match quiz</span><span class="lang-nl">Match quiz</span></a></li>
        </ul></div>
      <div><h4><span class="lang-en">Company</span><span class="lang-nl">Bedrijf</span></h4>
        <ul class="footer-links">
          <li><a href="../../over-ons.html"><span class="lang-en">About us</span><span class="lang-nl">Over ons</span></a></li>
          <li><a href="../../werkwijze.html"><span class="lang-en">Our way of working</span><span class="lang-nl">Werkwijze</span></a></li>
          <li><a href="../../blog/index.html"><span class="lang-en">Knowledge hub</span><span class="lang-nl">Kennisbank</span></a></li>
          <li><a href="../../contact.html"><span class="lang-en">Contact</span><span class="lang-nl">Contact</span></a></li>
        </ul></div>
      <div><h4><span class="lang-en">Legal</span><span class="lang-nl">Juridisch</span></h4>
        <ul class="footer-links">
          <li><a href="../../privacy.html"><span class="lang-en">Privacy Policy</span><span class="lang-nl">Privacybeleid</span></a></li>
          <li><span class="lang-en">Terms and conditions, available on request</span><span class="lang-nl">Algemene voorwaarden, op aanvraag</span></li>
          <li><span class="lang-en">We process personal data in compliance with GDPR.</span><span class="lang-nl">Wij verwerken persoonsgegevens conform de AVG.</span></li>
        </ul></div>
    </div>
    <div class="footer-bottom">
      <span>&copy; 2026 GSP Recruitment &middot; KvK 75545586 &middot; Brainport Eindhoven &middot; <a href="mailto:info@gsprecruitment.nl">info@gsprecruitment.nl</a></span>
    </div>
  </div>
</footer>

<div class="modal-overlay" id="jobModal">
  <div class="modal">
    <button class="modal-close" id="jobModalClose">&times;</button>
    <div id="jobModalBody"></div>
  </div>
</div>
<script src="../../gsp-util.js"></script>
<script src="../../auth.js"></script>
<script src="../../script.js"></script>"""


def crosslinks_block(city_slug: str, disc_slug: str, data: dict) -> str:
    other_disciplines = [d for d in DISCIPLINE_SLUGS if d != disc_slug]
    other_cities = [c for c in CITY_SLUGS if c != city_slug]
    city_name = data[city_slug][disc_slug]["city"]

    disc_items = "\n".join(
        f'          <li><a href="../{city_slug}/{d}.html">{esc(DISCIPLINE_FILTER_LABEL[d]["nl"])}</a></li>'
        for d in other_disciplines
    )
    city_items = "\n".join(
        f'          <li><a href="../{c}/{disc_slug}.html">{esc(data[c][disc_slug]["city"])}</a></li>'
        for c in other_cities
    )
    disc_label = DISCIPLINE_META[disc_slug]

    return f"""<section style="background:var(--bg-alt)">
  <div class="container">
    <div class="section-header">
      <div class="section-label"><span class="lang-en">Other regions and fields</span><span class="lang-nl">Andere regio's en vakgebieden</span></div>
    </div>
    <div class="landing-crosslinks">
      <div>
        <h4><span class="lang-nl">Andere vakgebieden in {esc(city_name)}</span><span class="lang-en">Other fields in {esc(city_name)}</span></h4>
        <ul class="footer-links">
{disc_items}
        </ul>
      </div>
      <div>
        <h4><span class="lang-nl">{esc(disc_label['nl'])} in andere steden</span><span class="lang-en">{esc(disc_label['en'])} in other cities</span></h4>
        <ul class="footer-links">
{city_items}
        </ul>
      </div>
    </div>
  </div>
</section>"""


def render_page(city_slug: str, disc_slug: str, data: dict) -> str:
    entry = data[city_slug][disc_slug]
    city = entry["city"]
    dept = DISCIPLINE_META[disc_slug]["dept"]
    h1_nl = f"{DISCIPLINE_META[disc_slug]['nl']} vacatures in {city}"
    h1_en = f"{DISCIPLINE_META[disc_slug]['en']} vacancies in {city}"
    eyebrow_nl = f"{DISCIPLINE_META[disc_slug]['nl']} &middot; {city}"
    eyebrow_en = f"{DISCIPLINE_META[disc_slug]['en']} &middot; {city}"
    canonical = f"https://gsprecruitment.nl/vacatures/{city_slug}/{disc_slug}"
    title = esc(entry["title_nl"])
    description = esc(entry["meta_nl"])
    og_description = esc(entry["meta_en"])

    head = f"""<!DOCTYPE html>
<html lang="nl" data-lang="nl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#0E1B2E">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{canonical}">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="googlebot" content="index, follow, max-snippet:-1, max-image-preview:large">
<meta name="author" content="GSP Recruitment">
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="https://gsprecruitment.nl/og-image.png">
<meta property="og:locale" content="nl_NL">
<meta property="og:locale:alternate" content="en_US">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:site" content="@gsprecruitment">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{og_description}">
<!-- No hreflang tags: per SITE-DESIGN-SPEC.md §3.6, this site has no
     separate per-language URLs (.lang-nl/.lang-en toggle client-side, no
     /en/ path), so hreflang would describe a URL structure that doesn't
     exist -- same rule as every other page on the site. -->
<link rel="icon" type="image/png" sizes="32x32" href="../../favicon-32.png">
<link rel="icon" type="image/png" sizes="16x16" href="../../favicon-16.png">
<link rel="apple-touch-icon" href="../../apple-touch-icon.png">
<link rel="manifest" href="../../site.webmanifest">
<link rel="preload" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" as="style" crossorigin>
<link rel="preload" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css" as="style" crossorigin>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet" crossorigin>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css" crossorigin>
<link rel="stylesheet" href="../../styles.css">
</head>
<body>"""

    hero = f"""<main id="main-content">
<section class="page-hero">
  <div class="container">
    <div class="eyebrow"><span class="lang-en">{eyebrow_en}</span><span class="lang-nl">{eyebrow_nl}</span></div>
    <h1 class="lang-en">{h1_en}</h1>
    <h1 class="lang-nl">{h1_nl}</h1>
    <p class="lang-nl">{esc(entry['intro_nl'])}</p>
    <p class="lang-en">{esc(entry['intro_en'])}</p>
  </div>
</section>"""

    jobs = f"""<section id="jobs">
  <div class="container">
    <div class="section-header">
      <div class="section-label"><span class="lang-en">Open roles</span><span class="lang-nl">Openstaande rollen</span></div>
      <h2 class="lang-en">{h1_en}, right now.</h2>
      <h2 class="lang-nl">{h1_nl}, nu open.</h2>
    </div>
    <div class="jobs-grid" id="jobsGrid" data-landing-city="{esc(city)}" data-landing-dept="{esc(dept)}"></div>
  </div>
</section>"""

    proof = """<section style="background:var(--bg-alt)">
  <div class="container">
    <div class="section-header">
      <div class="section-label"><span class="lang-en">Why apply via GSP</span><span class="lang-nl">Waarom via GSP solliciteren</span></div>
      <h2 class="lang-en">More than just a job board.</h2>
      <h2 class="lang-nl">Meer dan alleen een vacaturesite.</h2>
    </div>
    <div class="proof-strip proof-strip--on-light" role="list" aria-label="Voorwaarden" style="justify-content:center;margin-top:var(--space-lg)">
      <div class="proof-strip__item" role="listitem"><span class="proof-strip__fact"><span class="lang-nl">No cure, no pay</span><span class="lang-en">No cure, no pay</span></span></div>
      <div class="proof-strip__item" role="listitem"><span class="proof-strip__fact"><span class="lang-nl">30 dagen vervangingsgarantie</span><span class="lang-en">30-day replacement guarantee</span></span></div>
      <div class="proof-strip__item" role="listitem"><span class="proof-strip__fact"><span class="lang-nl">Reactie binnen 24 uur</span><span class="lang-en">Response within 24 hours</span></span></div>
      <div class="proof-strip__item" role="listitem"><span class="proof-strip__fact"><span class="lang-nl">20% korting op je eerste plaatsing</span><span class="lang-en">20% discount on your first placement</span></span></div>
    </div>
  </div>
</section>"""

    cta = """<section>
  <div class="container">
    <div class="cta-band">
      <h2 class="lang-en">Not the right role yet?</h2>
      <h2 class="lang-nl">Nog niet de juiste rol?</h2>
      <p class="lang-en">Send your CV. We'll keep you in mind and reach out the moment something fits, no spam, no pressure.</p>
      <p class="lang-nl">Stuur je CV in. We houden je in gedachten en nemen contact op zodra er iets past, geen spam, geen druk.</p>
      <div class="hero-actions">
        <a href="../../contact.html" class="btn btn-gold"><i class="fas fa-paper-plane"></i> <span class="lang-en">Submit your CV</span><span class="lang-nl">Stuur je CV in</span></a>
      </div>
    </div>
  </div>
</section>"""

    body = "\n".join([
        header_block(),
        hero,
        jobs,
        proof,
        crosslinks_block(city_slug, disc_slug, data),
        cta,
        "</main>",
        footer_block(),
        "</body>\n</html>\n",
    ])

    return head + "\n" + body


def main() -> int:
    if not DATA_FILE.exists():
        print(f"ERROR: {DATA_FILE} not found", flush=True)
        return 1
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    written = []
    for city_slug in CITY_SLUGS:
        if city_slug not in data:
            raise SystemExit(f"missing city in landing-copy.json: {city_slug}")
        for disc_slug in DISCIPLINE_SLUGS:
            if disc_slug not in data[city_slug]:
                raise SystemExit(f"missing discipline for {city_slug}: {disc_slug}")
            html = render_page(city_slug, disc_slug, data)
            out_path = OUT_DIR / city_slug / f"{disc_slug}.html"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            existing = out_path.read_text(encoding="utf-8") if out_path.exists() else None
            if existing != html:
                out_path.write_text(html, encoding="utf-8")
            written.append(out_path)

    print(f"Wrote/verified {len(written)} landing pages under {OUT_DIR.relative_to(REPO_ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
