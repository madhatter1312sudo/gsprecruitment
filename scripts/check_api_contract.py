#!/usr/bin/env python3
"""
Deploy-time contract check: does every API path the frontend calls actually
exist as a backend route?

This exists because the frontend (Cloudflare Pages, deploys on every push to
main) and the backend (this repo's talent-os/, deployed by this same CI run)
are two independently-deploying halves of one contract. On 2026-07-07 a
backend route-prefix change silently broke the live contact form and salary
calculator because nothing checked the two sides agreed with each other.

Static analysis only -- no server needs to be running. False positives are
possible for very dynamic paths; if this ever blocks a legitimate deploy,
check the printed mismatch by hand rather than just deleting this check.
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROUTERS_DIR = REPO_ROOT / "talent-os" / "backend" / "routers"
WEBSITE_DIR = REPO_ROOT / "website"

ROUTE_METHOD_RE = re.compile(r'@(\w+)\.(get|post|put|patch|delete)\(\s*["\']([^"\']*)["\']')
ROUTER_DEF_RE = re.compile(r'(\w+)\s*=\s*APIRouter\([^)]*prefix\s*=\s*["\']([^"\']*)["\']')

# Frontend call patterns:
#  - Auth.fetch('/v1/candidate/dashboard')   -> relative to Auth.API ("https://api.../api")
#  - fetch(`${API}/api/v1/public/lead`)      -> API is the bare origin ("https://api...")
#  - fetch(`${this.API}/auth/login`)         -> this.API === Auth.API (includes "/api")
#
# Backtick strings are matched whole (`([^`]*)`) since ${...} expressions
# inside them can contain nested single/double quotes that would otherwise
# truncate a naive [^`'"]* capture early (e.g. `/x${q ? '?' + q : ''}`).
AUTH_FETCH_RE = re.compile(r"Auth\.fetch\(\s*(?:`([^`]*)`|'([^']*)'|\"([^\"]*)\")")
RAW_FETCH_API_RE = re.compile(r"`\$\{API\}([^`]*)`")
RAW_FETCH_THISAPI_RE = re.compile(r"`\$\{this\.API\}([^`]*)`")


def get_backend_routes():
    """Return a set of (method, full_path_regex) for every declared route."""
    routers = {}  # var name -> prefix
    routes = []
    for f in ROUTERS_DIR.glob("*.py"):
        text = f.read_text(encoding="utf-8")
        for m in ROUTER_DEF_RE.finditer(text):
            routers[m.group(1)] = m.group(2)
        for m in ROUTE_METHOD_RE.finditer(text):
            var, method, path = m.group(1), m.group(2), m.group(3)
            prefix = routers.get(var, "")
            full = prefix + path
            routes.append((method.upper(), full))
    return routes


def path_to_regex(path):
    # FastAPI {param} -> wildcard; also collapse trailing slash variance
    pattern = re.sub(r"\{[^}]+\}", r"[^/]+", path)
    return re.compile("^" + pattern.rstrip("/") + "/?$")


def has_literal_path(path):
    """False for purely-dynamic strings like '${cleanUrl}' with no literal segment."""
    stripped = re.sub(r"\$\{[^}]*\}", "", path)
    return "/" in stripped


def get_frontend_calls():
    """Return a set of full '/api/...' paths the frontend actually calls."""
    calls = set()
    for f in list(WEBSITE_DIR.rglob("*.js")) + list(WEBSITE_DIR.rglob("*.html")):
        text = f.read_text(encoding="utf-8", errors="ignore")

        for m in AUTH_FETCH_RE.finditer(text):
            rel = next(g for g in m.groups() if g is not None)
            if not rel.startswith("/") or not has_literal_path(rel):
                continue
            # Auth.fetch paths are relative to Auth.API, which already ends in /api
            full = "/api" + rel
            calls.add((f, full))

        for m in RAW_FETCH_API_RE.finditer(text):
            if has_literal_path(m.group(1)):
                calls.add((f, m.group(1)))

        for m in RAW_FETCH_THISAPI_RE.finditer(text):
            if has_literal_path(m.group(1)):
                calls.add((f, "/api" + m.group(1)))

    return calls


DOLLAR_BRACE_RE = re.compile(r"\$\{")


def normalize_dynamic_segments(path):
    """
    /client/jobs/${jobId}          -> /client/jobs/{param}   (real path param, preceded by /)
    /admin/jobs${query ? ... : ''} -> /admin/jobs             (query-string suffix, not preceded
                                                                 by /, so truncate here instead)
    """
    search_from = 0
    while True:
        m = DOLLAR_BRACE_RE.search(path, search_from)
        if not m:
            break
        preceding_char = path[m.start() - 1] if m.start() > 0 else "/"
        if preceding_char == "/":
            end = path.index("}", m.end())
            path = path[: m.start()] + "{param}" + path[end + 1 :]
            search_from = m.start() + len("{param}")
        else:
            # Not a path segment -- everything from here is a query-string suffix
            path = path[: m.start()]
            break
    return path


def main():
    backend_routes = get_backend_routes()
    compiled = [(method, path, path_to_regex(path)) for method, path in backend_routes]

    frontend_calls = get_frontend_calls()

    mismatches = []
    for src_file, raw_path in sorted(frontend_calls, key=lambda x: str(x[0])):
        path = normalize_dynamic_segments(raw_path)
        path_for_match = re.sub(r"\{param\}", "placeholder", path)
        # Strip query string if present
        path_for_match = path_for_match.split("?")[0]

        if not any(rx.match(path_for_match) for _, _, rx in compiled):
            mismatches.append((src_file.relative_to(REPO_ROOT), raw_path, path))

    print(f"Backend routes found: {len(backend_routes)}")
    print(f"Frontend API calls found: {len(frontend_calls)}")
    print()

    if mismatches:
        print("MISMATCH: frontend calls a path with no matching backend route:")
        for src, raw, normalized in mismatches:
            print(f"  {src}: {raw}")
        print()
        print(f"{len(mismatches)} mismatch(es) found. Fix the frontend call or add the "
              f"backend route before deploying, or update this script if it's a false positive.")
        return 1

    print("OK: every frontend API call matches a declared backend route.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
