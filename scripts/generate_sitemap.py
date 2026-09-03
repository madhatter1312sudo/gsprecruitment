#!/usr/bin/env python3
"""
WS-A.7 -- build website/sitemap.xml from three sources:

1. The static page list below (extension-less URLs -- the site serves
   clean URLs; canonical/og:url were made extension-less alongside this
   script, see SITE-DESIGN-SPEC.md). lastmod comes from `git log` for the
   backing .html file, falling back to the file's mtime if git has no
   history for it (e.g. a fresh checkout with no .git, or a new file that
   hasn't been committed yet).

2. Live vacatures from GET https://api.gsprecruitment.nl/api/public/jobs
   (User-Agent: gsp-ops -- the WAF 403s bare requests). Each job becomes
   /vacature?id=<id> (vacature.js reads ?id= or ?slug=, see website/vacature.js).

3. Blog posts from website/blog/posts.json when it exists (it does, and is
   the source of truth for the static blog list); otherwise from
   GET https://api.gsprecruitment.nl/api/v1/public/blog (note the v1).

Network failures (jobs API, blog API) must never break the build: on any
request error, log a warning to stderr and fall back to just the static
page list for that source (skip jobs, or skip blog posts beyond
posts.json).

Usage:
  python3 scripts/generate_sitemap.py             # full run (network for jobs)
  python3 scripts/generate_sitemap.py --offline    # static list + posts.json only, no network
  python3 scripts/generate_sitemap.py --out PATH   # write elsewhere (default website/sitemap.xml)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE_DIR = REPO_ROOT / "website"
BASE_URL = "https://gsprecruitment.nl"
USER_AGENT = "gsp-ops"
JOBS_API = "https://api.gsprecruitment.nl/api/public/jobs"
BLOG_API = "https://api.gsprecruitment.nl/api/v1/public/blog"
REQUEST_TIMEOUT = 10

# path (extension-less, "" = homepage) -> (backing .html file, changefreq, priority)
STATIC_PAGES = [
    ("", "index.html", "daily", "1.0"),
    ("vacatures", "vacatures.html", "daily", "0.9"),
    ("werkgevers", "werkgevers.html", "weekly", "0.8"),
    ("kandidaten", "kandidaten.html", "weekly", "0.8"),
    ("contact", "contact.html", "monthly", "0.7"),
    ("werkwijze", "werkwijze.html", "monthly", "0.7"),
    ("over-ons", "over-ons.html", "monthly", "0.7"),
    ("privacy", "privacy.html", "monthly", "0.3"),
    ("blog/", "blog/index.html", "weekly", "0.7"),
]


@dataclass
class UrlEntry:
    loc: str
    lastmod: str
    changefreq: str
    priority: str


def log_warning(message: str) -> None:
    print(f"WARNING: {message}", file=sys.stderr)


def git_lastmod(rel_path: str) -> str | None:
    """Last commit date (YYYY-MM-DD) touching rel_path, or None if git has
    no history for it (no .git, uncommitted file, etc.)."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", rel_path],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = result.stdout.strip()
    return out or None


def file_mtime(path: Path) -> str:
    return date.fromtimestamp(path.stat().st_mtime).isoformat()


def lastmod_for(rel_path: str) -> str:
    lm = git_lastmod(rel_path)
    if lm:
        return lm
    full = REPO_ROOT / rel_path
    if full.exists():
        return file_mtime(full)
    return date.today().isoformat()


def build_static_entries() -> list[UrlEntry]:
    entries = []
    for url_path, html_rel, changefreq, priority in STATIC_PAGES:
        rel = f"website/{html_rel}"
        loc = f"{BASE_URL}/{url_path}" if url_path else f"{BASE_URL}/"
        entries.append(UrlEntry(loc, lastmod_for(rel), changefreq, priority))
    return entries


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build_job_entries(offline: bool) -> list[UrlEntry]:
    if offline:
        return []
    try:
        data = fetch_json(JOBS_API)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError) as exc:
        log_warning(f"could not fetch {JOBS_API} ({exc}) -- skipping job URLs in sitemap")
        return []

    jobs = data.get("jobs", data) if isinstance(data, dict) else data
    if not isinstance(jobs, list):
        log_warning(f"unexpected shape from {JOBS_API} -- skipping job URLs in sitemap")
        return []

    today = date.today().isoformat()
    entries = []
    for job in jobs:
        try:
            if not isinstance(job, dict):
                continue
            job_id = job.get("id") or job.get("slug")
            if not job_id:
                continue
            raw_lastmod = job.get("updated_at") or job.get("created_at") or today
            lastmod = str(raw_lastmod)[:10]
            entries.append(UrlEntry(
                f"{BASE_URL}/vacature?id={job_id}",
                lastmod,
                "weekly",
                "0.6",
            ))
        except Exception as exc:  # a single malformed job must not sink the whole sitemap
            log_warning(f"skipping malformed job entry from {JOBS_API} ({exc}): {job!r}")
    return entries


def build_blog_entries(offline: bool) -> list[UrlEntry]:
    posts_json = WEBSITE_DIR / "blog" / "posts.json"
    today = date.today().isoformat()

    if posts_json.exists():
        try:
            data = json.loads(posts_json.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log_warning(f"could not read {posts_json} ({exc}) -- skipping blog post URLs")
            return []

        if not isinstance(data, dict):
            log_warning(f"{posts_json} is not a JSON object -- skipping blog post URLs")
            return []

        posts = data.get("posts", [])
        if not isinstance(posts, list):
            log_warning(f"{posts_json} has a non-list 'posts' field -- skipping blog post URLs")
            return []

        lastmod = lastmod_for("website/blog/posts.json")
        entries = []
        for post in posts:
            try:
                if not isinstance(post, dict):
                    continue
                slug = post.get("id") or post.get("slug")
                if not slug:
                    continue
                entries.append(UrlEntry(
                    f"{BASE_URL}/blog/post?slug={slug}",
                    lastmod,
                    "monthly",
                    "0.6",
                ))
            except Exception as exc:  # a single malformed post must not sink the whole sitemap
                log_warning(f"skipping malformed post entry from {posts_json} ({exc}): {post!r}")
        return entries

    if offline:
        return []

    try:
        data = fetch_json(BLOG_API)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError) as exc:
        log_warning(f"could not fetch {BLOG_API} ({exc}) -- skipping blog post URLs in sitemap")
        return []

    posts = data.get("posts", data) if isinstance(data, dict) else data
    if not isinstance(posts, list):
        log_warning(f"unexpected shape from {BLOG_API} -- skipping blog post URLs in sitemap")
        return []

    entries = []
    for post in posts:
        try:
            if not isinstance(post, dict):
                continue
            slug = post.get("slug") or post.get("id")
            if not slug:
                continue
            raw_lastmod = post.get("published_at") or post.get("updated_at") or today
            lastmod = str(raw_lastmod)[:10]
            entries.append(UrlEntry(
                f"{BASE_URL}/blog/post?slug={slug}",
                lastmod,
                "monthly",
                "0.6",
            ))
        except Exception as exc:  # a single malformed post must not sink the whole sitemap
            log_warning(f"skipping malformed post entry from {BLOG_API} ({exc}): {post!r}")
    return entries


def render_xml(entries: list[UrlEntry]) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for e in entries:
        lines.append("  <url>")
        lines.append(f"    <loc>{escape(e.loc)}</loc>")
        lines.append(f"    <lastmod>{e.lastmod}</lastmod>")
        lines.append(f"    <changefreq>{e.changefreq}</changefreq>")
        lines.append(f"    <priority>{e.priority}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true",
                         help="skip all network calls (static pages + posts.json only)")
    parser.add_argument("--out", default=str(WEBSITE_DIR / "sitemap.xml"),
                         help="output path (default website/sitemap.xml)")
    args = parser.parse_args()

    entries = build_static_entries()
    entries += build_job_entries(args.offline)
    entries += build_blog_entries(args.offline)

    xml = render_xml(entries)
    out_path = Path(args.out)
    out_path.write_text(xml, encoding="utf-8")
    print(f"Wrote {out_path} with {len(entries)} URLs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
