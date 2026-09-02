#!/usr/bin/env python3
"""
xss_static_check.py — grep-based DOM-XSS sink checker for website/.

Finds `.innerHTML = ...` / `.insertAdjacentHTML(...)` sinks and, within the
statement that follows, flags every `ident.field` access that is not one of
our own namespaces/builtins (TRUSTED_BASES) — whether it appears inside a
`${...}` template-literal expression or as plain string concatenation
(`'<b>' + job.title + '</b>'`) — unless it is routed through one of the
shared escaping helpers (GSP.esc, GSP.safeUrl, GSP.sanitizeHtml, or the
admin panel's this.esc/this.safeUrl/local `esc`/`safeUrl` aliases).

Base rule: an `ident.field` access is risky UNLESS `ident` is in
TRUSTED_BASES (our own code, JS/DOM builtins). There is no separate
allow-list of "risky" loop-variable names to keep in sync — anything that
isn't clearly our own namespace is treated as untrusted API/user data by
default.

A handful of patterns are safe by construction even though they touch a
non-trusted base, and are excluded automatically:
  - numeric fields that are only ever used arithmetically in this codebase
    (salary_min/max, percentile fields, counts) and id/_id fields — a
    hostile value there becomes NaN or a plain digit string, never markup;
  - method CALLS on a field (`d.toLocaleDateString()`, `x.toFixed(0)`) —
    the call's return value is what actually reaches the sink;
  - a field used only as `.length`, or only in a `===`/`!==`/`==`/`!=`
    comparison — both yield a boolean/number, never the field's own text;
  - a whole `${...}` expression that is entirely one call to a
    sanitizing/own-code function (this.xxx(...), GSP.xxx(...),
    encodeURIComponent(...), Number(...), String(...), JSON.stringify(...));
  - a bracket lookup into a fixed local map (`icons[e.action]`), optionally
    with a literal `||`/`??` fallback — always yields one of the map's own
    values;
  - a ternary whose both branches are simple string literals — can only
    ever render one of those two literals;
  - a short, curated list of local flag/class-name variables that hold a
    value computed from a fixed lookup, not raw field text
    (SAFE_LOCAL_NAMES below).

A genuine false positive can be silenced inline with a trailing comment
`// xss-static-check: safe — <reason>` on the same source line.

Usage:
    python3 scripts/xss_static_check.py            # scan website/
    python3 scripts/xss_static_check.py --verbose   # also list sinks scanned
    python3 scripts/xss_static_check.py --selftest  # verify the checker itself
                                                     # still catches known-bad
                                                     # patterns; does not scan
                                                     # website/
Exit code 0 = clean, 1 = at least one unescaped sink (or a failed selftest).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEBSITE = ROOT / "website"
SKIP_DIRS = {"vendor", "node_modules"}

SINK_PATTERN = re.compile(r"\.innerHTML\s*=|\.insertAdjacentHTML\s*\(")

SAFE_MARKERS = (
    "GSP.esc(", "GSP.sanitizeHtml(", "GSP.safeUrl(",
    "this.esc(", "this.safeUrl(",
    "esc(", "safeUrl(",
)

# Base identifiers whose `.member` access is our own code (methods,
# namespaces, JS/DOM builtins) rather than API/user data. This is the ONLY
# gate on the base identifier — anything not listed here is untrusted.
TRUSTED_BASES = {
    "this", "GSP", "Auth", "Math", "Number", "String", "Object", "Array",
    "JSON", "console", "window", "document", "location", "localStorage",
    "sessionStorage", "Date", "URL", "URLSearchParams",
}

NUMERIC_SAFE_FIELDS = {
    "salary_min", "salary_max", "p25", "p50", "p75",
    "match_count", "placement_count", "read_time_min",
    "cost_per_hire_avg", "years_experience", "match_score",
    "application_count",
}

BOOLEAN_SAFE_FIELDS = {
    "is_verified", "is_published", "is_active", "opened_at",
}

# `${expr}` where expr is exactly one of these is a local flag/class-name
# variable already computed from a fixed lookup table or boolean, not a
# fresh unescaped read of API text.
SAFE_LOCAL_NAMES = {
    "isUnread", "statusBadge", "roleBadge", "statusClass",
    "kb.cls", "kb.label", "dots", "pct", "lang",
}

SAFE_WHOLE_EXPR = re.compile(
    r"^(?:this|GSP|Auth)\.[A-Za-z_$][\w$]*\(.*\)$"
    r"|^encodeURIComponent\(.*\)$"
    r"|^Number\(.*\)$"
    r"|^String\(.*\)$"
    r"|^JSON\.stringify\(.*\)$"
    , re.DOTALL,
)

SAFE_LOOKUP_EXPR = re.compile(
    r"^[A-Za-z_$][\w$]*\[[^\]]+\](\s*\?\?\s*'[^']*'|\s*\|\|\s*'[^']*')?$",
    re.DOTALL,
)

SAFE_LITERAL_TERNARY = re.compile(
    r"\?\s*(['\"])(?:(?!\1).)*\1\s*:\s*(['\"])(?:(?!\2).)*\2\s*$", re.DOTALL
)

DOTTED = re.compile(r"\b([A-Za-z_$][\w$]*)\.([A-Za-z_$][\w$]*)")

# Plain string-concatenation form: `... + ident.field + ...` or
# `... + ident.field)` / `... + ident.field;` — not inside a template
# literal at all.
CONCAT_DOTTED = re.compile(
    r"\+\s*([A-Za-z_$][\w$]*\.[A-Za-z_$][\w$]*)\s*(?=\+|\)|;|,|$)"
)

ALLOW_COMMENT = "xss-static-check: safe"


def iter_files():
    for path in WEBSITE.rglob("*"):
        if path.suffix not in (".js", ".html"):
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def extract_dollar_groups(text):
    """Yield each top-level ${...} expression's inner text, brace-balanced."""
    groups = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "$" and i + 1 < n and text[i + 1] == "{":
            depth = 1
            j = i + 2
            start = j
            while j < n and depth > 0:
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            groups.append(text[start:j])
            i = j + 1
        else:
            i += 1
    return groups


def take_statement(lines, start_idx, start_col, max_lines=60):
    """Grab source from the sink assignment up to a plausible statement end
    (a line ending in `;` at low nesting, or max_lines reached)."""
    out = [lines[start_idx][start_col:]]
    depth = out[0].count("`") % 2  # crude backtick-parity tracker
    for i in range(start_idx + 1, min(start_idx + max_lines, len(lines))):
        out.append(lines[i])
        depth ^= lines[i].count("`") % 2
        stripped = lines[i].rstrip()
        if depth == 0 and (stripped.endswith(";") or stripped.endswith("`);")):
            break
    return "\n".join(out)


def _dotted_match_is_safe(expr, match):
    """Given one `base.field` regex match inside `expr`, decide whether
    THIS occurrence is safe regardless of the rest of the expression."""
    base, field = match.group(1), match.group(2)
    if base in TRUSTED_BASES:
        return True
    if field in NUMERIC_SAFE_FIELDS or field in BOOLEAN_SAFE_FIELDS:
        return True
    if field == "id" or field.endswith("_id"):
        return True
    after = expr[match.end(): match.end() + 1]
    if after == "(":
        return True  # method call — its return value reaches the sink
    tail = expr[match.end(): match.end() + 12]
    if tail.startswith(".length"):
        return True  # only the numeric length is used
    if re.match(r"\s*(===|!==|==|!=)", tail):
        return True  # used only as a comparison -> yields a boolean
    return False


def is_risky_group(expr):
    """Check one ${...} template-literal expression."""
    if any(marker in expr for marker in SAFE_MARKERS):
        return False
    expr_stripped = expr.strip()
    if expr_stripped in SAFE_LOCAL_NAMES:
        return False
    if SAFE_WHOLE_EXPR.match(expr_stripped):
        return False
    if SAFE_LOOKUP_EXPR.match(expr_stripped):
        return False
    if SAFE_LITERAL_TERNARY.search(expr_stripped):
        return False

    for match in DOTTED.finditer(expr):
        if not _dotted_match_is_safe(expr, match):
            return True
    return False


def find_risky_concat(line):
    """Check one line of plain (non-template-literal) string concatenation
    for an unescaped `ident.field` operand. Returns the risky expression
    text, or None."""
    if any(marker in line for marker in SAFE_MARKERS):
        # Still check operands the marker doesn't wrap, but skip lines
        # where the whole concatenation is trivially the marker's call —
        # good enough for this codebase's actual patterns.
        pass
    for m in CONCAT_DOTTED.finditer(line):
        expr = m.group(1)
        dm = DOTTED.search(expr)
        if dm is None:
            continue
        # Was this specific occurrence preceded by a safe marker on the
        # same line, close enough that it's plausibly the wrapping call?
        window = line[max(0, m.start() - 40): m.start()]
        if any(marker in window for marker in SAFE_MARKERS):
            continue
        if _dotted_match_is_safe(expr, dm):
            continue
        return expr
    return None


def check_file(path, verbose=False):
    findings = []
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return findings
    lines = raw.splitlines()

    for lineno, line in enumerate(lines, start=1):
        m = SINK_PATTERN.search(line)
        if not m or ALLOW_COMMENT in line:
            continue
        if verbose:
            print(f"  scanning sink {path.relative_to(ROOT)}:{lineno}")

        stmt = take_statement(lines, lineno - 1, m.end())
        stmt_lines = stmt.splitlines()
        for i, sline in enumerate(stmt_lines):
            if ALLOW_COMMENT in sline:
                continue
            for grp in extract_dollar_groups(sline):
                if is_risky_group(grp):
                    findings.append((path, lineno + i, grp.strip()))
            concat = find_risky_concat(sline)
            if concat is not None:
                findings.append((path, lineno + i, concat))

    return findings


# ── selftest ────────────────────────────────────────────────────────────
SELFTEST_CASES = [
    (
        "template-literal interpolation",
        "el.innerHTML = `<h3>${x.title}</h3>`;",
    ),
    (
        "string concatenation",
        "el.innerHTML = '<b>' + job.title + '</b>';",
    ),
]


def run_selftest():
    ok = True
    for name, snippet in SELFTEST_CASES:
        tmp = Path("/tmp/xss_static_check_selftest.js")
        tmp.write_text(snippet + "\n")
        try:
            findings = check_file(tmp)
        finally:
            tmp.unlink(missing_ok=True)
        if findings:
            print(f"  PASS  {name}: flagged {[f[2] for f in findings]}")
        else:
            ok = False
            print(f"  FAIL  {name}: NOT flagged — checker regressed on: {snippet!r}")
    return ok


def main():
    if "--selftest" in sys.argv:
        print("XSS static check selftest:")
        ok = run_selftest()
        print("selftest: PASS" if ok else "selftest: FAIL")
        return 0 if ok else 1

    verbose = "--verbose" in sys.argv
    all_findings = []
    for path in sorted(iter_files()):
        all_findings.extend(check_file(path, verbose=verbose))

    if all_findings:
        print(f"XSS static check: {len(all_findings)} possibly-unescaped sink expression(s) found\n")
        for path, lineno, expr in all_findings:
            rel = path.relative_to(ROOT)
            print(f"  {rel}:{lineno}  {expr}")
        print(
            "\nEach flagged expression must go through GSP.esc(...) / this.esc(...) "
            "/ GSP.safeUrl(...) / GSP.sanitizeHtml(...), or be annotated "
            "`// xss-static-check: safe — <reason>` on that line if it is safe "
            "by construction (e.g. a numeric field used only arithmetically)."
        )
        return 1

    print("XSS static check: clean — no unescaped innerHTML/insertAdjacentHTML sink expressions found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
