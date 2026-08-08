#!/usr/bin/env python3
"""Pull Ankur Napa's FULL blog archive from his sitemap into a resources file.

The RSS feed only exposes about 25 posts. The blog itself carries roughly 320
English posts, and build_resources.py already ingests the feed window; this
covers the rest.

Two deliberate choices:

- ENGLISH ONLY. The sitemap also lists /de/, /hi/ and /mr/ translations of the
  same articles, which would treble the count and add nothing: same argument,
  same evidence, different language. One canonical post per idea.
- featured=False for everything here. The feed window stays featured so the
  newest work still leads; 320 featured posts by one author would bury every
  other blog on the site under a single byline.

Titles and summaries come from each post's own og:title and description, not
from the URL slug, because a slug makes a poor headline and no summary at all.

Run: python3 scripts/build_ankur_archive.py [--limit N] [--workers 8]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "resources" / "ankur_archive.json"
SITEMAP = "https://ankurnapa.github.io/sitemap.xml"
BLOG = "Beer, Wine & Whiskey AI (Ankur Napa)"
UA = "beverage-ai-radar (+https://github.com/AnkurNapa/beverage-ai-radar)"

# Dated post URLs only, and only the English tree: a /de/, /hi/ or /mr/ segment
# before the year marks a translation.
POST = re.compile(r"^https://ankurnapa\.github\.io/(20\d\d)/[^/]+/?$")


def fetch(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def _meta(html: str, *patterns: str) -> str:
    for p in patterns:
        m = re.search(p, html, re.S | re.I)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return ""


def _vertical(text: str) -> str:
    t = text.lower()
    if re.search(r"wine|winemak|winery|vineyard|grape", t):
        return "wine"
    if re.search(r"whisk|distill|maturation|spirit|cask", t):
        return "whiskey"
    if re.search(r"brew|beer|malt|hop|wort|lager|ferment", t):
        return "beer"
    return "multiple"


def scrape(url: str) -> dict | None:
    try:
        html = fetch(url)
    except Exception:
        return None
    title = _meta(html,
                  r'<meta property="og:title" content="(.*?)"',
                  r'<meta name="twitter:title" content="(.*?)"')
    summary = _meta(html,
                    r'<meta name="description" content="(.*?)"',
                    r'<meta property="og:description" content="(.*?)"')
    if not title:
        return None
    year = int(POST.match(url).group(1))
    return {
        "title": title, "blog": BLOG, "author": "Ankur Napa",
        "date": str(year), "vertical": _vertical(title + " " + summary),
        "url": url, "summary": summary,
        # The feed window carries featured=True in build_resources. Everything
        # here is archive, so it sits below rather than burying other authors.
        "featured": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    print("reading sitemap...")
    xml = fetch(SITEMAP, timeout=40)
    urls = re.findall(r"<loc>(.*?)</loc>", xml)
    posts = [u for u in urls if POST.match(u)]
    posts = sorted(set(posts), reverse=True)
    if args.limit:
        posts = posts[: args.limit]
    print("%d English posts found" % len(posts))

    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, rec in enumerate(pool.map(scrape, posts), 1):
            if rec:
                rows.append(rec)
            if i % 50 == 0:
                print("  %d/%d fetched, %d usable" % (i, len(posts), len(rows)))

    OUT.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    verts = {}
    for r in rows:
        verts[r["vertical"]] = verts.get(r["vertical"], 0) + 1
    print("wrote %d posts to %s" % (len(rows), OUT))
    print("by vertical: %s" % verts)
    print("skipped %d that returned no title" % (len(posts) - len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
