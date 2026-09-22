#!/usr/bin/env python3
"""
css_class_census.py — grep-based CSS class-usage census for website/styles.css.

Parses every class selector defined in website/styles.css (".foo", ".foo.bar",
".foo .bar", ".foo:hover" etc. all count — each individual ".name" token is
extracted) and counts how many times each class name is actually used as a
class token (word-boundary match, so ".card" does not match ".card-data")
in website/**/*.html and website/**/*.js, excluding website/admin/ and any
vendor/ directory (third-party bundles, not our markup).

This is the reusable, scriptable version of the manual census that backed
SITE-DESIGN-SPEC.md §8.x.7 ("Dode CSS die in dezelfde PR verdwijnt") — run it
again after any future migration to verify a fresh "0 usage" claim before
deleting CSS.

A class is reported as "confirmed unused" only when its word-boundary count
across ALL scanned HTML/JS is exactly 0. A class used only via
`classList.add('foo')`/`className = 'foo ...'` in script.js is still caught,
since those are plain string tokens the word-boundary regex matches directly
— no DOM parsing needed for that case.

KNOWN LIMITATION — dynamically built class names are invisible to this
script, because it only searches for each class name as a literal
substring: `` `toast-${type}` `` never contains the literal text
"toast-success", even though that's the real class a toast gets at
runtime. Confirmed by this file's own case: .toast-success/-error/-warning
report as "0 usage" here but are built by website/auth.js:495
(`` `toast toast-${type}` ``) — genuinely alive. ALWAYS grep the flagged
name by hand (including for `${...}` / string-concatenation construction)
before deleting anything this script calls unused; treat its "unused" list
as a lead to verify, not a verdict to act on directly.

Usage:
    python3 scripts/css_class_census.py                 # human-readable report
    python3 scripts/css_class_census.py --json           # machine-readable
    python3 scripts/css_class_census.py --fail-on-unused # exit 1 if any class has 0 usages

Exit code: 0 normally; 1 with --fail-on-unused and at least one unused class,
or on a fatal error (e.g. styles.css missing).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEBSITE = ROOT / "website"
STYLESHEET = WEBSITE / "styles.css"
SKIP_DIRS = {"admin", "vendor", "node_modules"}

# ── 1. Strip comments, then pull out every selector list (the text before
#      each top-level "{") from styles.css. ──────────────────────────────
COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
CLASS_TOKEN_RE = re.compile(r"\.(-?[A-Za-z_][A-Za-z0-9_-]*)")

# Skip pseudo-class/element "classes" that CLASS_TOKEN_RE's sibling patterns
# might otherwise be confused with — not actually needed since we only match
# on a literal "." prefix (pseudo-classes use ":"), kept as a safety net for
# any stray "::selection"-adjacent text that slips through.
NOT_A_CLASS = set()


def extract_selectors(css_text):
    """Yield each selector-list string that precedes a '{' block, skipping
    the contents of @media/@keyframes/@font-face etc. (their own nested
    selectors are still visited when the outer scan reaches them, since we
    just look for text-before-'{' throughout the whole file — @media's own
    "selector" text, e.g. "(max-width: 768px)", contains no "." class
    tokens so it is harmless to scan too)."""
    text = COMMENT_RE.sub(" ", css_text)
    selectors = []
    depth = 0
    buf = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "{":
            if depth == 0:
                selectors.append("".join(buf))
                buf = []
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
            if depth == 0:
                buf = []
        elif depth == 0:
            buf.append(ch)
        i += 1
    return selectors


def classes_in_stylesheet(css_text):
    """Return {class_name: set(selector_list strings it appeared in)}."""
    found = {}
    for sel in extract_selectors(css_text):
        # An @-rule's condition (e.g. "@media (max-width: 768px)") has no
        # class tokens and is harmless to scan; @keyframes step selectors
        # ("0%", "50%") likewise contain no ".".
        for m in CLASS_TOKEN_RE.finditer(sel):
            name = m.group(1)
            found.setdefault(name, set()).add(sel.strip())
    return found


# ── 2. Count word-boundary usage of each class name in website/**/*.html
#      and website/**/*.js, excluding admin/ and vendor/. ────────────────
def iter_usage_files():
    for path in WEBSITE.rglob("*"):
        if path.suffix not in (".html", ".js"):
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path == STYLESHEET:
            continue
        yield path


def count_usages(class_names):
    """Return {class_name: count} — total word-boundary matches across all
    scanned files. Word boundary so e.g. '.card' does not match '.card-data'
    or 'card-dark', and 'x-card' does not match 'card' as a substring hit
    (both sides must be a non-word-character or the class name itself)."""
    counts = {name: 0 for name in class_names}
    patterns = {name: re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])") for name in class_names}
    for path in iter_usage_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name, pat in patterns.items():
            n = len(pat.findall(text))
            if n:
                counts[name] += n
    return counts


# ── 3. Table structure check (SITE-DESIGN-SPEC.md §7.3.8d): one <th> per
#      column, and every colspan in that table equal to the <th> count.
#      A <colspan> that doesn't match is a structural fault, not a style
#      question -- it breaks the header/cell association a screen reader
#      relies on (see WS5 #142). Static, regex-based like the rest of this
#      file: no real HTML parser needed for well-formed <table> markup, and
#      any table wrote across admin/candidate/client is in scope, unlike
#      the class census above (which is styles.css-only and skips admin/).
TABLE_RE = re.compile(r"<table\b.*?</table>", re.DOTALL | re.IGNORECASE)
THEAD_RE = re.compile(r"<thead\b.*?</thead>", re.DOTALL | re.IGNORECASE)
TH_RE = re.compile(r"<th\b", re.IGNORECASE)
COLSPAN_RE = re.compile(r'colspan\s*=\s*"(\d+)"', re.IGNORECASE)


def find_table_mismatches():
    """Return a list of (file, table_index, th_count, bad_colspans) for
    every <table> whose <thead> <th> count disagrees with one or more of
    its <colspan> values. Scans every *.html file under website/ except
    vendor/ bundles (third-party markup, not ours to fix)."""
    mismatches = []
    for path in WEBSITE.rglob("*.html"):
        if any(part == "vendor" for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, table in enumerate(TABLE_RE.findall(text)):
            thead_m = THEAD_RE.search(table)
            head = thead_m.group(0) if thead_m else table
            th_count = len(TH_RE.findall(head))
            if th_count == 0:
                continue  # no static <th> here (e.g. a fully JS-rendered table)
            bad = [c for c in COLSPAN_RE.findall(table) if int(c) != th_count]
            if bad:
                mismatches.append((path, i, th_count, bad))
    return mismatches


def main():
    as_json = "--json" in sys.argv
    fail_on_unused = "--fail-on-unused" in sys.argv

    table_mismatches = find_table_mismatches()
    if table_mismatches:
        print("TABLE STRUCTURE MISMATCH: a <colspan> doesn't match its table's <th> count "
              "(SITE-DESIGN-SPEC.md §7.3.8d):")
        for path, idx, th_count, bad in table_mismatches:
            rel = path.relative_to(ROOT)
            print(f"  {rel} (table #{idx}): {th_count} <th> cells, colspan(s) {bad}")
        print()

    if not STYLESHEET.exists():
        print(f"css_class_census: {STYLESHEET} not found", file=sys.stderr)
        return 1

    css_text = STYLESHEET.read_text(encoding="utf-8")
    declared = classes_in_stylesheet(css_text)
    counts = count_usages(declared.keys())

    unused = sorted(name for name, n in counts.items() if n == 0)
    used = sorted(name for name, n in counts.items() if n > 0)

    if as_json:
        payload = {
            "stylesheet": str(STYLESHEET.relative_to(ROOT)),
            "declared_class_count": len(declared),
            "unused": unused,
            "used": {name: counts[name] for name in used},
            "table_mismatches": [
                {"file": str(p.relative_to(ROOT)), "table_index": i, "th_count": t, "bad_colspans": b}
                for p, i, t, b in table_mismatches
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(f"css_class_census: {len(declared)} class selectors declared in {STYLESHEET.relative_to(ROOT)}")
        print(f"  used (>=1 word-boundary match in website/**/*.html, **/*.js, excl. admin/vendor): {len(used)}")
        print(f"  confirmed unused (0 matches): {len(unused)}")
        if unused:
            print()
            for name in unused:
                sels = " | ".join(sorted(declared[name]))[:120]
                print(f"  .{name}   (declared in: {sels})")

    if table_mismatches:
        return 1
    if fail_on_unused and unused:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
