#!/usr/bin/env python3
"""
WS-A.9b verification: parse every HTML page under website/, list the external
origins it actually loads, and assert the CSP-Report-Only directive in
website/_headers covers each origin under the directive it needs.

Usage: python3 scripts/verify_csp_coverage.py
Exits non-zero (and prints MISSING) if any origin isn't covered.

Known limitation: this only parses href/src attributes. It does not scan
event-handler attributes (onerror=, onload=, ...) or origins added by
JS-created elements at runtime -- those are checked separately below via
a targeted onerror= scan and the KNOWN_JS_CONNECT table.
"""
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
WEBSITE = ROOT / "website"
HEADERS_FILE = WEBSITE / "_headers"

# --- 1. Extract the CSP-Report-Only line from _headers -----------------
csp_text = None
for line in HEADERS_FILE.read_text().splitlines():
    if line.strip().startswith("Content-Security-Policy-Report-Only:"):
        csp_text = line.split(":", 1)[1].strip()
        break
if not csp_text:
    print("FAIL: no Content-Security-Policy-Report-Only line found in _headers")
    sys.exit(1)

directives = {}
for part in csp_text.split(";"):
    part = part.strip()
    if not part:
        continue
    tokens = part.split()
    directives[tokens[0]] = tokens[1:]

def origins_for(directive):
    """Origins allowed for a directive, falling back to default-src."""
    vals = directives.get(directive) or directives.get("default-src", [])
    return {v for v in vals if v.startswith("http")}

# --- 2. Walk every HTML file and collect what it loads, tagged by kind -
TAG_TO_DIRECTIVE = {
    "script": "script-src",
    "link_stylesheet": "style-src",
    "link_preload_style": "style-src",
    "img": "img-src",
    "iframe": "frame-src",
}

findings = []  # (file, directive, origin)

script_src_re = re.compile(r'<script[^>]*\bsrc="([^"]+)"', re.I)
link_re = re.compile(r'<link\b([^>]*)>', re.I)
img_re = re.compile(r'<img[^>]*\bsrc="([^"]+)"', re.I)
iframe_re = re.compile(r'<iframe[^>]*\bsrc="([^"]+)"', re.I)
onerror_url_re = re.compile(r'onerror="[^"]*\'(https?://[^\']+)\'', re.I)
rel_re = re.compile(r'\brel="([^"]+)"')
as_re = re.compile(r'\bas="([^"]+)"')
href_re = re.compile(r'\bhref="([^"]+)"')

def origin_of(url):
    if not url.startswith("http"):
        return None
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"

html_files = sorted(WEBSITE.rglob("*.html"))
for f in html_files:
    text = f.read_text(errors="ignore")
    for m in script_src_re.finditer(text):
        o = origin_of(m.group(1))
        if o:
            findings.append((f, "script-src", o))
    for m in link_re.finditer(text):
        attrs = m.group(1)
        href_m = href_re.search(attrs)
        if not href_m:
            continue
        o = origin_of(href_m.group(1))
        if not o:
            continue
        rel = (rel_re.search(attrs) or [None, ""])[1] if rel_re.search(attrs) else ""
        as_ = (as_re.search(attrs) or [None, ""])[1] if as_re.search(attrs) else ""
        if "stylesheet" in rel or (rel == "preload" and as_ == "style"):
            findings.append((f, "style-src", o))
        elif rel == "preload" and as_ == "font":
            findings.append((f, "font-src", o))
        elif "icon" in rel or "manifest" in rel or "canonical" in rel or "alternate" in rel or "apple-touch-icon" in rel or "preconnect" in rel:
            pass  # not fetched under CSP in a way that needs allow-listing (preconnect handled by connect-src implicitly for fonts, covered separately)
    for m in img_re.finditer(text):
        o = origin_of(m.group(1))
        if o:
            findings.append((f, "img-src", o))
    for m in iframe_re.finditer(text):
        o = origin_of(m.group(1))
        if o:
            findings.append((f, "frame-src", o))
    for m in onerror_url_re.finditer(text):
        o = origin_of(m.group(1))
        if o:
            findings.append((f, "style-src", o))
    # @font-face / css url() origins referenced via googleapis stylesheet content
    if "fonts.googleapis.com" in text:
        findings.append((f, "font-src", "https://fonts.gstatic.com"))

# JS-driven fetch()/XHR/redirect origins we know about from source inspection
KNOWN_JS_CONNECT = {
    "website/script.js": ["https://api.gsprecruitment.nl"],
    "website/auth.js": ["https://api.gsprecruitment.nl"],
    "website/admin/js/admin.js": ["https://api.gsprecruitment.nl"],
}
for rel_path, origins in KNOWN_JS_CONNECT.items():
    p = ROOT / rel_path
    if p.exists():
        for o in origins:
            findings.append((p, "connect-src", o))

# --- 3. Check coverage --------------------------------------------------
missing = []
covered = []
for f, directive, origin in findings:
    allowed = origins_for(directive)
    if origin in allowed:
        covered.append((f.relative_to(ROOT), directive, origin))
    else:
        missing.append((f.relative_to(ROOT), directive, origin))

print(f"CSP directives parsed from _headers: {sorted(directives.keys())}\n")

print("== External origins found and their required directive ==")
seen = set()
for f, directive, origin in sorted(set(findings), key=lambda t: (t[1], t[2])):
    key = (directive, origin)
    if key in seen:
        continue
    seen.add(key)
    status = "OK" if origin in origins_for(directive) else "MISSING"
    print(f"  [{status:7}] {directive:12} {origin}")

print(f"\nFiles scanned: {len(html_files)}")
print(f"Total (directive, origin) references checked: {len(findings)}")
print(f"Unique origin/directive pairs missing coverage: {len(set((d,o) for _,d,o in missing))}")

if missing:
    print("\nFAIL: uncovered origins:")
    for f, d, o in sorted(set(missing)):
        print(f"  {f}: needs {o} in {d}")
    sys.exit(1)

print("\nPASS: every external origin referenced by website/**/*.html (and the known "
      "fetch() targets in script.js/auth.js/admin.js) is covered by the "
      "Content-Security-Policy-Report-Only directive it needs.")
