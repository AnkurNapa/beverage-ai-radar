#!/usr/bin/env python3
"""Merge curated research files in data/resources/ into dashboard/resources.json.

Separate from the company pipeline: papers, news, repos, and videos are
references, not Company entities. Each source file is a hand-verified JSON array
(every item carries a real URL). This normalizes them to one shape, dedupes by
url (video_id for videos), and writes a single file the dashboard fetches.

Run: python3 scripts/build_resources.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "resources"
OUT = ROOT / "dashboard" / "resources.json"


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
            "sort": r.get("year") or 0,
        }


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
            "sort": stars,
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
            "sort": r.get("year") or 0,
        }


def build():
    items = []
    items += list(_norm_papers(_load("papers.json")))
    items += list(_norm_news(_load("news.json")))
    items += list(_norm_repos(_load("repos.json")))
    items += list(_norm_videos(_load("videos.json")))

    # dedupe by url (case-insensitive), keep first
    seen, deduped = set(), []
    for it in items:
        k = it["url"].lower().rstrip("/")
        if k in seen:
            continue
        seen.add(k)
        deduped.append(it)

    OUT.write_text(json.dumps(deduped, indent=2, ensure_ascii=False))
    by_kind = {}
    for it in deduped:
        by_kind[it["kind"]] = by_kind.get(it["kind"], 0) + 1
    print(f"wrote {len(deduped)} resources to {OUT.relative_to(ROOT)}: {by_kind}")


if __name__ == "__main__":
    build()
