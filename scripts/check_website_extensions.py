#!/usr/bin/env python3
"""
WS-E.9: fail CI if a non-web file type lands under website/.

website/ is deployed as-is (Cloudflare Workers Static Assets); it should
only ever contain files a browser needs (HTML/JS/CSS/images/fonts/etc.)
plus a short, explicit allowlist of special filenames Cloudflare or the
repo itself needs (CNAME, _headers, .gitignore, ...). A stray .py, .md,
.env, .pdf, or .eps in here is either a mistake (source notes that should
live elsewhere) or a leak (a real .env file) -- either way it should never
ship.

Usage: python3 scripts/check_website_extensions.py
Exits non-zero and lists every offending path if any is found.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE_DIR = REPO_ROOT / "website"

# Extensions a deployed static site legitimately needs.
ALLOWED_EXTENSIONS = {
    ".html", ".js", ".mjs", ".css", ".json", ".xml", ".txt", ".webmanifest",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif", ".ico",
    ".woff", ".woff2", ".ttf",
}

# Extensionless / special filenames that are not "web extensions" but are
# legitimate to ship or to keep tracked-but-unserved (reuses
# website/.assetsignore's own list for the latter -- see that file).
ALLOWED_EXACT_NAMES = {"CNAME", "_headers", ".gitignore", ".assetsignore", ".host"}

# Explicitly never allowed, regardless of ALLOWED_EXTENSIONS above missing
# them by omission -- named here so the check's intent is unambiguous even
# if the allowlist above is edited later.
FORBIDDEN_EXTENSIONS = {".py", ".md", ".env", ".pdf", ".eps"}


def main() -> int:
    offenders = []
    for path in sorted(WEBSITE_DIR.rglob("*")):
        if path.is_dir():
            continue
        name = path.name
        if name in ALLOWED_EXACT_NAMES:
            continue
        suffix = path.suffix.lower()
        if suffix in ALLOWED_EXTENSIONS and suffix not in FORBIDDEN_EXTENSIONS:
            continue
        offenders.append(path.relative_to(REPO_ROOT))

    if offenders:
        print("FAIL: non-web file type(s) found under website/:")
        for p in offenders:
            print(f"  {p}")
        print(
            "\nOnly web asset extensions "
            f"({', '.join(sorted(ALLOWED_EXTENSIONS))}) and the explicit "
            f"exact-name allowlist ({', '.join(sorted(ALLOWED_EXACT_NAMES))}) "
            "may live under website/. Move source/doc files elsewhere, or "
            "add a narrowly-scoped exact-name exception here if this file "
            "genuinely belongs (never widen ALLOWED_EXTENSIONS to include "
            "Forbidden ones)."
        )
        return 1

    print(f"OK: every file under website/ is a recognised web asset type ({len(list(WEBSITE_DIR.rglob('*')))} entries scanned).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
