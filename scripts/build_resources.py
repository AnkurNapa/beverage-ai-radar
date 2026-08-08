#!/usr/bin/env python3
"""Merge curated research files in data/resources/ into dashboard/resources.json.

Separate from the company pipeline: papers, news, repos, and videos are
references, not Company entities. Each source file is a hand-verified JSON array
(every item carries a real URL). This normalizes them to one shape, dedupes by
url (video_id for videos), and writes a single file the dashboard fetches.

Run: python3 scripts/build_resources.py
"""
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Reuse the company theme classifier rather than writing a second one. The rules
# already moved out of app.js once so the gap analysis and dashboard could not
# drift; a separate resource taxonomy would reintroduce exactly that problem.
sys.path.insert(0, str(ROOT / "src"))
from radar.themes import theme_of  # noqa: E402
SRC = ROOT / "data" / "resources"
OUT = ROOT / "dashboard" / "resources.json"

ANKUR_FEED = "https://ankurnapa.github.io/feed.xml"
ANKUR_BLOG = "Beer, Wine & Whiskey AI (Ankur Napa)"
ANKUR_CACHE = SRC / "_ankur_blogs.cache.json"
# The feed exposes ~25 posts; the blog itself has ~320 English posts. Taking the
# feed's full window rather than a 24 slice, but deliberately NOT ingesting all
# 320: at that point Ankur's own blog would be 40 percent of every resource on
# the site, and a landscape that is mostly its author stops being a landscape.
# The full archive is linked from his profile instead.
ANKUR_LIMIT = 50


def _vertical_from(cats, text):
    """Map a post's category tags / text to a beverage vertical."""
    blob = (" ".join(cats) + " " + text).lower()
    if re.search(r"wine|winemak|winery|vineyard", blob):
        return "wine"
    if re.search(r"distill|whisk|maturation|spirit", blob):
        return "whiskey"
    if re.search(r"brew|beer|malt", blob):
        return "beer"
    return "multiple"


def _fetch_ankur_blogs(limit=ANKUR_LIMIT):
    """Auto-pull Ankur Napa's newest posts from his blog RSS feed.

    Returns featured blog records. On any network/parse failure, falls back to
    the last good cache so a build never breaks offline. On success, refreshes
    the cache. ponytail: newest-N by feed order (feed is already reverse-chron).
    """
    try:
        req = urllib.request.Request(ANKUR_FEED, headers={"User-Agent": "beverage-ai-radar"})
        with urllib.request.urlopen(req, timeout=15) as r:
            xml = r.read(4_000_000)  # cap size
        # defend against XXE / billion-laughs without a new dep: a plain RSS feed
        # has no DTD or entity declarations, so reject any that does.
        if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
            raise ValueError("feed contains DTD/entity declarations, refusing to parse")
        items = ET.fromstring(xml).findall(".//item")
        out = []
        for it in items[:limit]:
            g = lambda tag: (it.findtext(tag) or "").strip()
            link = g("link")
            if not link:
                continue
            cats = [c.text or "" for c in it.findall("category")]
            desc = unescape(re.sub(r"<[^>]+>", "", g("description")))
            year = None
            m = re.search(r"\b(20\d\d)\b", g("pubDate"))
            if m:
                year = int(m.group(1))
            out.append({
                "title": unescape(g("title")), "blog": ANKUR_BLOG, "author": "Ankur Napa",
                "date": str(year) if year else "", "vertical": _vertical_from(cats, g("title")),
                "url": link, "summary": desc, "featured": True,
            })
        if out:
            ANKUR_CACHE.write_text(json.dumps(out, indent=2, ensure_ascii=False))
            print(f"auto-pulled {len(out)} Ankur blog posts from feed")
            return out
    except Exception as exc:
        print(f"feed pull failed ({type(exc).__name__}: {exc}); using cache")
    if ANKUR_CACHE.exists():
        return json.loads(ANKUR_CACHE.read_text())
    return []


def _load(name):
    p = SRC / name
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        print(f"skip {name}: bad JSON ({exc})")
        return []


def _norm_papers(rows):
    for r in rows:
        if not r.get("url"):
            continue
        yield {
            "kind": "paper",
            "title": r.get("title", ""),
            "url": r["url"],
            "vertical": r.get("vertical", "multiple"),
            "meta": " · ".join(x for x in (r.get("authors"), r.get("venue"), str(r.get("year") or "")) if x),
            "summary": r.get("finding", ""),
            "year": r.get("year"),
            "sort": r.get("year") or 0,
        }


def _year_from(date):
    """Pull a 4-digit year off a free-text date like '2024' or '2024-11-04'."""
    s = str(date or "")
    return int(s[:4]) if s[:4].isdigit() else None


def _norm_news(rows):
    for r in rows:
        if not r.get("url"):
            continue
        tag = r.get("kind", "news")
        yield {
            "kind": "news",
            "label": tag,
            "title": r.get("title", ""),
            "url": r["url"],
            "vertical": r.get("vertical", "multiple"),
            "meta": " · ".join(x for x in (r.get("publication"), r.get("date"), r.get("company")) if x),
            "summary": r.get("summary", ""),
            "year": _year_from(r.get("date")),
            "sort": r.get("date") or "",
        }


def _norm_repos(rows):
    for r in rows:
        url = r.get("url") or (f"https://github.com/{r['full_name']}" if r.get("full_name") else "")
        if not url:
            continue
        stars = r.get("stars") or 0
        yield {
            "kind": "repo",
            "title": r.get("full_name", ""),
            "url": url,
            "vertical": r.get("vertical", "multiple"),
            "meta": " · ".join(x for x in (f"★ {stars}", r.get("language")) if x),
            "summary": r.get("relevance") or r.get("description", ""),
            "stars": stars,
            "year": None,
            "sort": stars,
        }


def _norm_whitepapers(rows):
    """Industry white papers: vendor and trade-body long-form, no DOI.

    Distinct from `paper` (peer-reviewed, via OpenAlex) because the provenance
    and the trust level differ. A vendor white paper is evidence of what a
    supplier claims, which is useful and is not the same as a refereed result.
    """
    for r in rows:
        url = (r.get("url") or "").strip()
        if not url:
            continue
        yield {
            "kind": "whitepaper",
            "title": r.get("title", ""),
            "url": url,
            "vertical": r.get("vertical", "multiple"),
            "meta": " · ".join(x for x in (r.get("publisher"), str(r.get("year") or "")) if x),
            "summary": r.get("summary", ""),
            "year": r.get("year"),
            "sort": r.get("year") or 0,
        }


def _norm_datasets(rows):
    """Open datasets someone can actually download and model on.

    Kept separate from repos: a repo is code, a dataset is the raw material.
    Anyone starting a beverage ML project needs the second before the first.
    """
    for r in rows:
        url = (r.get("url") or "").strip()
        if not url:
            continue
        yield {
            "kind": "dataset",
            "title": r.get("title", ""),
            "url": url,
            "vertical": r.get("vertical", "multiple"),
            "meta": " · ".join(
                x for x in (r.get("publisher"), str(r.get("year") or ""), r.get("licence")) if x
            ),
            "summary": r.get("summary", ""),
            "year": r.get("year"),
            "sort": r.get("year") or 0,
        }


def _norm_videos(rows):
    for r in rows:
        vid = (r.get("video_id") or "").strip()
        url = r.get("url") or (f"https://www.youtube.com/watch?v={vid}" if vid else "")
        if not vid or len(vid) != 11 or not url:
            continue
        yield {
            "kind": "video",
            "title": r.get("title", ""),
            "url": url,
            "vertical": r.get("vertical", "multiple"),
            "meta": " · ".join(x for x in (r.get("channel"), str(r.get("year") or "")) if x),
            "summary": r.get("summary", ""),
            "thumb": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
            "channel": r.get("channel", ""),
            "featured": bool(r.get("featured")),
            "year": r.get("year"),
            "sort": r.get("year") or 0,
        }


def _norm_podcasts(rows):
    for r in rows:
        if not r.get("url"):
            continue
        yield {
            "kind": "podcast",
            "title": r.get("title", ""),
            "url": r["url"],
            "vertical": r.get("vertical", "multiple"),
            "meta": " · ".join(x for x in (r.get("show"), str(r.get("date") or "")) if x),
            "summary": r.get("summary", ""),
            "year": _year_from(r.get("date")),
            "sort": r.get("date") or "",
        }


def _norm_blogs(rows):
    for r in rows:
        if not r.get("url"):
            continue
        yield {
            "kind": "blog",
            "title": r.get("title", ""),
            "url": r["url"],
            "vertical": r.get("vertical", "multiple"),
            "meta": " · ".join(x for x in (r.get("blog"), r.get("author"), str(r.get("date") or "")) if x),
            "summary": r.get("summary", ""),
            "featured": bool(r.get("featured")),
            "year": _year_from(r.get("date")),
            "sort": r.get("date") or "",
        }


def build():
    items = []
    items += list(_norm_papers(_load("papers.json")))
    # Swept from OpenAlex by scripts/sweep_papers.py. Kept in its own file so a
    # re-sweep never overwrites the hand-verified papers.json, and so the
    # provenance of any given row is obvious from where it lives.
    items += list(_norm_papers(_load("papers_openalex.json")))
    items += list(_norm_news(_load("news.json")))
    items += list(_norm_blogs(_fetch_ankur_blogs()))  # auto-pulled newest, featured
    items += list(_norm_blogs(_load("blogs.json")))  # other curated blogs
    items += list(_norm_repos(_load("repos.json")))
    items += list(_norm_whitepapers(_load("whitepapers.json")))
    # sweep output; the file may not exist until scripts/sweep_whitepapers.py runs
    swept = _load("whitepapers_swept.json")
    items += list(_norm_whitepapers(swept.get("whitepapers", []) if isinstance(swept, dict) else swept))
    items += list(_norm_datasets(_load("datasets.json")))
    items += list(_norm_videos(_load("videos.json")))
    # Swept from YouTube search by scripts/sweep_videos.py; deduped by url below
    # alongside the hand-curated file above.
    items += list(_norm_videos(_load("videos_youtube.json")))
    items += list(_norm_podcasts(_load("podcasts.json")))

    # dedupe by url (case-insensitive), keep first
    seen, deduped = set(), []
    for it in items:
        k = it["url"].lower().rstrip("/")
        if k in seen:
            continue
        seen.add(k)
        deduped.append(it)

    # Resources carry no ai_use_case field, so classify on the text that exists.
    # meta holds venue/author/repo owner, which is weak signal, so title and
    # summary lead and meta only breaks ties.
    for it in deduped:
        it["theme"] = theme_of(f"{it.get('title', '')} {it.get('summary', '')} {it.get('meta', '')}")

    OUT.write_text(json.dumps(deduped, indent=2, ensure_ascii=False))
    by_kind = {}
    for it in deduped:
        by_kind[it["kind"]] = by_kind.get(it["kind"], 0) + 1
    print(f"wrote {len(deduped)} resources to {OUT.relative_to(ROOT)}: {by_kind}")
    stamp_assets()


def stamp_assets():
    """Rewrite the ?v= on styles.css and app.js to a hash of their contents.

    GitHub Pages serves these with cache-control: max-age=600 and no
    fingerprint, so a returning visitor keeps the old file. Hand-bumping a
    version string failed twice: once shipping a restyle nobody could see, and
    once pairing new JS with stale CSS, which rendered "43" and "38%" as
    "4338%". Deriving it from the bytes removes the step a human forgets.
    """
    import hashlib

    html_path = ROOT / "dashboard" / "index.html"
    html = html_path.read_text()
    before = html
    for asset in ("styles.css", "app.js"):
        f = ROOT / "dashboard" / asset
        if not f.exists():
            continue
        digest = hashlib.md5(f.read_bytes()).hexdigest()[:10]
        html = re.sub(
            rf'(["\']){re.escape(asset)}(\?v=[^"\']*)?\1',
            lambda m, d=digest, a=asset: f"{m.group(1)}{a}?v={d}{m.group(1)}",
            html,
        )
    if html != before:
        html_path.write_text(html)
        print("stamped asset versions in dashboard/index.html")


if __name__ == "__main__":
    build()
