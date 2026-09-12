#!/usr/bin/env python3
"""
css_tokens_check.py — grep-based token-compliance checker for the
kaartsysteem (SITE-DESIGN-SPEC.md §8.x). Three checks, each independently
failing the build:

  1. Gray-scale text floor (§8.x.2 table): --gray-100/-200/-300 are
     hairline/non-text tokens only (1.23:1 / 1.49:1 / 2.56:1 — well under
     the 4.5:1 AA floor). Any `color: ... var(--gray-100|200|300)` in
     styles.css fails, everywhere in the file — there is no context in
     which these are valid text colors.

  2. Gold text floor on light (§8.x.0 hard rule / §8.x.2 table):
     --gold-ink is the only allowed gold text color on a LIGHT surface.
     --gold-600/-700 as text is an unconditional violation (explicitly
     rejected in §8.x's "Niet overgenomen" list, regardless of surface).
     --gold-400/-500 as text is a violation ONLY on a light surface —
     both are correct, required text colors on a DARK surface (e.g. the
     archetype-1 dark choice card's .go-link, or .page-hero's eyebrow) per
     §1.2 and the archetype-1 table itself ("link --gold-500"). A rule is
     treated as "on a dark surface" when its selector, or the nearest
     preceding rule-block comment, contains one of DARK_CONTEXT_MARKERS.
     This is a heuristic (grep has no cascade/DOM model) — a genuine false
     positive can be silenced with a trailing comment
     `/* css-tokens-check: safe on dark — <reason> */` on that line.

  3. Kaartklasse radius (§8.x.0: radius var(--radius)/3px on every card,
     var(--radius-full) reserved for chips/badges only): for each of the
     six archetype class names (loaded from
     scratchpad/ws1-css-requests/classes.md when present, else the
     built-in fallback list below), any `border-radius` value other than
     var(--radius)/var(--radius-sm)/var(--radius-xs)/3px/0/var(--radius-full)
     fails. (0 is allowed — that's the boxless chip/divider variant, e.g.
     .ts-item, not an alternate radius.)

  4. styles.css vs theme.css token parity: any `--name: value;` declared in
     both files' :root with a different value fails, unless --name is
     passed via --allow (repeatable) or a comma list in
     CSS_TOKENS_CHECK_ALLOW.

  5. website/admin/admin.css doet mee in dezelfde tokenpariteit (WS5 stap 1:
     de inline compat-shim in admin/index.html die --navy-*/--radius-* met
     eigen waarden overschreef is vervangen door dit bestand). Twee regels:
     (a) admin.css mag geen token herdeclareren dat styles.css of theme.css
         al met een andere waarde declareert;
     (b) admin.css mag geen navy- of goudwaarde hardcoderen -- elke navy/
         goudkleur gaat via var(--navy-*)/var(--gold-*). Een letterlijke
         hex/rgb uit de navy- of goudschaal faalt, in elke schrijfwijze:
         #RRGGBB, #RGB, rgb(r,g,b), de moderne rgb(r g b / a), en een kale
         triple "r, g, b" zoals Tabler die in zijn --*-rgb-variabelen wil.
         Een regel met het commentaar "css-tokens-check: rgb-triple" is
         daarvan uitgezonderd: Tabler bouwt daar zelf rgba(var(--x-rgb), a)
         mee, en een triple kan niet uit een kleur-var komen.
     Semantisch groen/rood/oranje/paars zijn geen merkkleuren en mogen wel
     als hex in admin.css staan (--admin-positive en broertjes).

Usage:
    python3 scripts/css_tokens_check.py
    python3 scripts/css_tokens_check.py --allow --font-size-3xl --allow --font-size-4xl

Exit code: 0 = clean, 1 = at least one violation (or a missing input file).
No external dependencies.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEBSITE = ROOT / "website"
STYLESHEET = WEBSITE / "styles.css"
THEME = WEBSITE / "theme.css"
ADMIN_CSS = WEBSITE / "admin" / "admin.css"
CLASSES_MD = ROOT / "scratchpad" / "ws1-css-requests" / "classes.md"

ALLOW_COMMENT = "css-tokens-check: safe on dark"

# Tokens waarvan styles.css en theme.css bewust uiteenlopen, met de reden.
# styles.css kleedt de publieke site aan (wit), theme.css de portalen
# (navy). Een schaduw is geen kleurtoken maar een elevatiesignaal: dezelfde
# rgba-waarde die op wit leest, is op navy onzichtbaar. Deze drie dus per
# oppervlak, en gerapporteerd als waarschuwing in plaats van als fout.
# Alles wat hier niet in staat, laat de check falen zoals voorheen.
SURFACE_SPECIFIC = {
    "--shadow": "elevatie op wit versus op navy",
    "--shadow-md": "elevatie op wit versus op navy",
    "--shadow-lg": "elevatie op wit versus op navy",
}

# Elke navy- en goudwaarde uit SITE-DESIGN-SPEC.md §1.2, plus de twee
# waarden die de oude inline shim in admin/index.html gebruikte
# (#142235 / #0E1B2E) -- die mogen nooit terugkeren.
BRAND_HEXES = {
    "#030812": "--navy-950", "#060d1a": "--navy-900", "#0a1628": "--navy-800",
    "#0f1d35": "--navy-700", "#152b4a": "--navy-600", "#1e3a5e": "--navy-500",
    "#2a4a75": "--navy-400", "#4a6f9f": "--navy-300", "#7fa0c9": "--navy-200",
    "#c5d6eb": "--navy-100",
    "#fac800": "--gold-500", "#fbd74a": "--gold-400", "#fce488": "--gold-300",
    "#d4a800": "--gold-600", "#ad8800": "--gold-700",
    "#142235": "de oude shim-navy", "#0e1b2e": "de oude shim-navy",
    "#18293d": "de oude shim-navy", "#1a2a42": "de oude shim-navy",
    "#24354f": "de oude shim-navy", "#8695ac": "de oude shim-navy",
    "#b8c4d6": "de oude shim-navy", "#e2e8f0": "de oude shim-navy",
}

# Dezelfde kleuren als rgb-triple, zodat rgb(10,22,40), rgb(10 22 40 / 1)
# en de kale "10, 22, 40" van een --*-rgb-variabele ook gevonden worden.
BRAND_TRIPLES = {
    tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)): name
    for h, name in BRAND_HEXES.items()
}

RGB_TRIPLE_ALLOW = "css-tokens-check: rgb-triple"
# #rgb -> #rrggbb, zodat een korte hex dezelfde treffer geeft.
SHORT_HEX_RE = re.compile(r"#([0-9a-f])([0-9a-f])([0-9a-f])(?![0-9a-f])")
# Elke groep van drie getallen, gescheiden door komma's en/of spaties, al
# dan niet met een /alpha erachter.
TRIPLE_RE = re.compile(r"(?<![\w.])(\d{1,3})\s*[, ]\s*(\d{1,3})\s*[, ]\s*(\d{1,3})(?![\d.%])")

GRAY_TEXT_BANNED = ("gray-100", "gray-200", "gray-300")
GOLD_UNCONDITIONAL_BANNED = ("gold-600", "gold-700")
GOLD_DARK_ONLY = ("gold-400", "gold-500")

# Selector/comment substrings that mark a rule as styling a dark surface,
# where --gold-400/-500 text is correct (not a violation). Deliberately
# broad — a false "this is dark" is silent (misses a real violation only
# in a context we didn't anticipate), a false "this is light" is loud (a
# failed build), so err toward recognizing dark contexts.
DARK_CONTEXT_MARKERS = (
    "card-dark", "choice-card", "choice-go", "choice-grid",
    "page-hero", "cta-band", "footer", ".header", ".nav",
    "signup-value", "signup-bullet", "signup-foot",
    "contact-rail", "modal-tab.active", "toast-",
    ".hamburger", "on-dark", "back-to-top",
)

# Fallback list if classes.md (written by the archetype-builder step) isn't
# present yet — keep in sync with the six archetypes' primary class names.
FALLBACK_CARD_CLASSES = [
    "card-dark", "choice-card",
    "card", "service-card", "path-card", "story-card",
    "card-data", "job-card", "vac-card",
    "step-rail", "step-row", "step-rail--vertical", "step-card-expanded",
    "chip", "mark", "trust-badge", "eco-badge", "ts-item",
    "contact-row", "contact-method",
    "contact-rail",
]

RADIUS_ALLOWED = re.compile(
    r"^(var\(--radius(-sm|-xs|-full)?(\s*,\s*[^)]+)?\)|0(px)?|3px)$"
)

ROOT_BLOCK_RE = re.compile(r":root\s*(?:\[[^\]]*\])?\s*\{(.*?)\}", re.DOTALL)
TOKEN_DECL_RE = re.compile(r"(--[A-Za-z0-9-]+)\s*:\s*([^;]+);")
COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def load_card_classes():
    if not CLASSES_MD.exists():
        return list(FALLBACK_CARD_CLASSES)
    text = CLASSES_MD.read_text(encoding="utf-8")
    names = sorted(set(re.findall(r"\.([A-Za-z][\w-]*)", text)))
    return names or list(FALLBACK_CARD_CLASSES)


def strip_comments_keep_lines(text):
    """Blank out /* ... */ content but keep line breaks, so line numbers in
    findings still point at the right source line."""
    def repl(m):
        return "".join(ch if ch == "\n" else " " for ch in m.group(0))
    return COMMENT_RE.sub(repl, text)


def nearest_selector(lines, lineno_idx):
    """Walk backward from lines[lineno_idx] to find the selector text for
    the rule block that line belongs to (text between the previous '}' and
    the next '{' at or before this line)."""
    depth = 0
    for i in range(lineno_idx, -1, -1):
        depth += lines[i].count("}") - lines[i].count("{")
        if "{" in lines[i] and depth <= 0:
            # This line opens the block containing lineno_idx (or is it).
            start = i
            # Walk further back to the previous '}' to capture a
            # multi-line selector list.
            j = i
            while j > 0 and "}" not in lines[j - 1]:
                j -= 1
            return "\n".join(lines[j:start + 1])
    return ""


def check_gray_gold_text(css_text, raw_lines):
    findings = []
    color_re = re.compile(r"\bcolor\s*:\s*[^;]*var\(--(" + "|".join(
        GRAY_TEXT_BANNED + GOLD_UNCONDITIONAL_BANNED + GOLD_DARK_ONLY
    ) + r")\b")
    for i, line in enumerate(raw_lines):
        if ALLOW_COMMENT in line:
            continue
        m = color_re.search(line)
        if not m:
            continue
        token = m.group(1)
        if token in GRAY_TEXT_BANNED or token in GOLD_UNCONDITIONAL_BANNED:
            findings.append((i + 1, f"color: var(--{token}) as text — never a valid text color", line.strip()))
            continue
        # gold-400 / gold-500: only a violation on a light surface.
        sel = nearest_selector(raw_lines, i)
        if any(marker in sel for marker in DARK_CONTEXT_MARKERS):
            continue
        findings.append((
            i + 1,
            f"color: var(--{token}) as text on what looks like a light surface — only --gold-ink is allowed there",
            line.strip(),
        ))
    return findings


def check_card_radius(raw_lines, card_classes):
    """Only flags a border-radius set directly ON a card class (the card
    container itself is the rightmost/targeted compound selector) — not a
    border-radius on some descendant of a card (e.g. an icon swatch inside
    .contact-method, which is decorative chrome outside the archetype
    anatomy, same as .prop-icon/.step-icon elsewhere in the file)."""
    findings = []
    class_re = re.compile(r"(?<![\w-])\.(" + "|".join(re.escape(c) for c in card_classes) + r")(?![\w-])")
    radius_re = re.compile(r"border-radius\s*:\s*([^;]+);")
    for i, line in enumerate(raw_lines):
        m = radius_re.search(line)
        if not m:
            continue
        sel = nearest_selector(raw_lines, i)
        targets_card = False
        for alt in sel.split(","):
            # Split on descendant/child/sibling combinators — the last
            # compound selector is what the declaration actually targets.
            parts = re.split(r"[\s>+~]+", alt.strip())
            last = parts[-1] if parts else ""
            if last and class_re.search(last):
                targets_card = True
                break
        if not targets_card:
            continue
        value = m.group(1).strip()
        if RADIUS_ALLOWED.match(value):
            continue
        findings.append((i + 1, f"kaartklasse border-radius: {value!r} (must be var(--radius)/3px/0/var(--radius-full))", line.strip()))
    return findings


def parse_root_tokens(path):
    if not path.exists():
        return {}
    text = strip_comments_keep_lines(path.read_text(encoding="utf-8"))
    tokens = {}
    for block in ROOT_BLOCK_RE.findall(text):
        for name, value in TOKEN_DECL_RE.findall(block):
            tokens[name] = value.strip()
    return tokens


def check_theme_parity(allowlist):
    styles_tokens = parse_root_tokens(STYLESHEET)
    theme_tokens = parse_root_tokens(THEME)
    findings = []
    allowed = []
    for name, sval in styles_tokens.items():
        if name in allowlist:
            continue
        tval = theme_tokens.get(name)
        if tval is not None and tval != sval:
            if name in SURFACE_SPECIFIC:
                allowed.append((name, sval, tval, SURFACE_SPECIFIC[name]))
            else:
                findings.append((name, sval, tval))
    return findings, allowed


def check_admin_css(allowlist):
    """(a) pariteit met styles.css/theme.css, (b) geen hardcoded merkkleur."""
    if not ADMIN_CSS.exists():
        return [f"{ADMIN_CSS} ontbreekt"], []
    parity = []
    admin_tokens = parse_root_tokens(ADMIN_CSS)
    base = {}
    base.update(parse_root_tokens(STYLESHEET))
    base.update(parse_root_tokens(THEME))
    for name, aval in admin_tokens.items():
        if name in allowlist:
            continue
        bval = base.get(name)
        if bval is not None and bval != aval:
            parity.append(f"{name}: admin.css={aval!r} maar styles/theme.css={bval!r}")

    literals = []
    raw_text = ADMIN_CSS.read_text(encoding="utf-8")
    raw_lines = raw_text.splitlines()
    clean = strip_comments_keep_lines(raw_text)
    # Een regel met het allow-commentaar erop, of met dat commentaar op de
    # regels er direct boven (een blokcommentaar dat de uitzondering
    # uitlegt), is vrijgesteld voor de triple-check.
    exempt = set()
    for i, line in enumerate(raw_lines):
        if RGB_TRIPLE_ALLOW in line:
            for j in range(i, min(i + 6, len(raw_lines))):
                exempt.add(j)
    for i, line in enumerate(clean.splitlines()):
        low = SHORT_HEX_RE.sub(r"#\1\1\2\2\3\3", line.lower())
        hit = None
        for lit, token in BRAND_HEXES.items():
            if lit in low.replace(" ", ""):
                hit = (lit, token)
                break
        if hit is None and i not in exempt:
            for m in TRIPLE_RE.finditer(low):
                triple = tuple(int(g) for g in m.groups())
                if triple in BRAND_TRIPLES:
                    hit = (m.group(0), BRAND_TRIPLES[triple])
                    break
        if hit:
            literals.append(
                f"admin.css:{i + 1}  hardcoded {hit[0]} -- gebruik var({hit[1]})\n      {line.strip()}")
    return parity, literals


def main():
    argv = sys.argv[1:]
    allowlist = set()
    i = 0
    while i < len(argv):
        if argv[i] == "--allow" and i + 1 < len(argv):
            # Token names from TOKEN_DECL_RE keep their leading "--"
            # (e.g. "--gold-glow"); normalize whatever the caller passes
            # (with or without the dashes) to that same form so --allow
            # actually matches (a bare .lstrip("-") stored "gold-glow",
            # which never matched "--gold-glow" and silently allowed
            # nothing — found while using this flag for real).
            allowlist.add("--" + argv[i + 1].lstrip("-"))
            i += 2
        else:
            i += 1

    if not STYLESHEET.exists():
        print(f"css_tokens_check: {STYLESHEET} not found", file=sys.stderr)
        return 1

    raw_text = STYLESHEET.read_text(encoding="utf-8")
    clean_text = strip_comments_keep_lines(raw_text)
    raw_lines = clean_text.splitlines()

    card_classes = load_card_classes()

    text_findings = check_gray_gold_text(clean_text, raw_lines)
    radius_findings = check_card_radius(raw_lines, card_classes)
    parity_findings, parity_allowed = check_theme_parity(allowlist)
    admin_parity, admin_literals = check_admin_css(allowlist)

    total = (len(text_findings) + len(radius_findings) + len(parity_findings)
             + len(admin_parity) + len(admin_literals))

    if text_findings:
        print(f"[1/4] Text-color floor violations in styles.css: {len(text_findings)}")
        for lineno, reason, line in text_findings:
            print(f"  styles.css:{lineno}  {reason}\n      {line}")
    else:
        print("[1/4] Text-color floor: clean.")

    if radius_findings:
        print(f"[2/4] Kaartklasse border-radius violations: {len(radius_findings)}")
        for lineno, reason, line in radius_findings:
            print(f"  styles.css:{lineno}  {reason}\n      {line}")
    else:
        print("[2/4] Kaartklasse border-radius: clean.")

    if parity_findings:
        print(f"[3/4] styles.css vs theme.css token mismatches: {len(parity_findings)}")
        for name, sval, tval in parity_findings:
            print(f"  {name}: styles.css={sval!r}  theme.css={tval!r}")
    else:
        print("[3/4] styles.css/theme.css token parity: clean.")
    for name, sval, tval, reason in parity_allowed:
        print(f"  warning: {name} divergeert bewust ({reason})")
        print(f"    styles.css={sval!r}  theme.css={tval!r}")

    if admin_parity or admin_literals:
        print(f"[4/4] admin.css: {len(admin_parity) + len(admin_literals)} overtreding(en)")
        for f in admin_parity:
            print(f"  {f}")
        for f in admin_literals:
            print(f"  {f}")
    else:
        print("[4/4] admin.css tokenpariteit en merkkleuren: clean.")

    if total:
        print(f"\ncss_tokens_check: {total} violation(s) found.")
        return 1

    print("\ncss_tokens_check: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
