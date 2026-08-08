#!/usr/bin/env python3
"""Sweep YouTube for talks and case studies on AI and data in drinks.

Why scrape search rather than call the Data API: the API needs a key and a
quota, and this runs a few dozen queries a month. YouTube's search page ships
its results as a JSON blob (ytInitialData) in the HTML, so the same structured
fields the API would return are already there: video id, title, channel,
description snippet and a relative publish date.

The relevance gate is the same shape as sweep_papers.py and runs on OUR side. A
search for "fermentation machine learning" returns kombucha home videos,
biofuel lectures and generic MLOps talks. A video is kept only when a beverage
term AND a data term both appear in title or description, and no off-topic term
does.

Year is DERIVED from YouTube's relative date ("3 years ago"), so it is accurate
to about a year and no better. Anything more precise would need the API.

Writes data/resources/videos_youtube.json. build_resources.py folds it in and
dedupes by url alongside the hand-curated videos.json.

Run: python3 scripts/sweep_videos.py [--per-query 25] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "resources" / "videos_youtube.json"
CURATED = ROOT / "data" / "resources" / "videos.json"
EXISTING = ROOT / "dashboard" / "resources.json"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

QUERIES = [
    ("beer", "brewery machine learning"),
    ("beer", "brewing artificial intelligence process"),
    ("beer", "beer quality prediction data science"),
    ("beer", "brewery digital twin automation"),
    ("beer", "craft brewery data analytics"),
    ("whiskey", "distillery artificial intelligence"),
    ("whiskey", "whisky machine learning flavour"),
    ("whiskey", "spirits production data analytics"),
    ("wine", "winery machine learning"),
    ("wine", "vineyard computer vision yield"),
    ("wine", "wine quality prediction data science"),
    ("multiple", "beverage industry artificial intelligence conference talk"),
    ("multiple", "food and beverage manufacturing AI digital twin"),
    ("multiple", "fermentation monitoring machine learning"),
    ("non_alcoholic", "soft drink bottling line AI analytics"),
    ("non_alcoholic", "beverage supply chain forecasting machine learning"),
]

BEVERAGE = re.compile(
    r"\b(beer|brewing|brewery|breweries|brewer|malt|hop|hops|wort|lager|ale|"
    r"wine|winery|wineries|vineyard|viticultur|grape|grapes|oenolog|"
    r"whisky|whiskey|distill|distiller|distillery|spirits|cask|"
    r"cider|mead|sake|brandy|rum|gin|vodka|beverage|drinks|bottling|"
    r"soft drink|soda|juice|kombucha)\b", re.I)
DATA = re.compile(
    r"\b(machine learning|deep learning|neural network|artificial intelligence|\bai\b|"
    r"data science|data analytics|analytics|predictive|prediction|forecast|"
    r"computer vision|digital twin|industry 4\.?0|automation|generative|"
    r"algorithm|model|dashboard|power bi|tableau|iot|sensor)\b", re.I)
# Same maths, something nobody here makes; plus the home-brew hobby tail that
# matches every keyword and teaches a professional nothing.
OFF_TOPIC = re.compile(
    r"\b(biofuel|bioethanol|pharmaceutic|wastewater|sludge|biodiesel|biogas|"
    r"cement|semiconductor|drug discovery|crypto|forex|stock market|"
    r"minecraft|gta|gameplay|prank|mukbang)\b", re.I)

# "The App Brewery" is a coding bootcamp. "Data brewery", "code distillery" and
# friends are the same joke. The beverage word is in the CHANNEL name, not the
# subject, and the keyword gate cannot tell the difference.
FALSE_FRIEND = re.compile(
    r"\b(app brewery|data brewery|code brewery|idea brewery|"
    r"code distillery|data distillery|startup brewery)\b", re.I)

# The UCI wine-quality CSV is the standard teaching dataset. Running sklearn
# over it is a first-year exercise, and it is the single largest category of
# "wine machine learning" video on YouTube. On-topic by every keyword test and
# worthless to a winemaker: no winery, no vintage, no instrument. This mirrors
# BENCHMARK_EXERCISE in sweep_papers.py, which exists for the same reason.
BENCHMARK_EXERCISE = re.compile(
    r"(wine (quality|dataset|classification)|red wine|white wine)"
    r".{0,40}\b(prediction|predicting|analysis|classification|classifier)?"
    r".{0,40}\b(machine learning|ml project|sklearn|scikit|python project|"
    r"random forest|logistic regression|jupyter|colab)", re.I)

# Course and tutorial furniture. A conference talk about a real deployment is
# what this sweep is for; "step by step guide" and "final year project" are not.
TUTORIAL = re.compile(
    r"\b(tutorial|step[- ]by[- ]step|full course|crash course|"
    r"final year project|college project|cse project|project \d+|"
    r"lecture \d+|for beginners|from scratch in python|source code)\b", re.I)


def fetch_search(query: str) -> str:
    url = "https://www.youtube.com/results?" + urllib.parse.urlencode(
        {"search_query": query, "sp": "EgIQAQ%3D%3D"}  # sp filter: videos only
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="ignore")


def parse_results(html: str) -> list[dict]:
    """Pull videoRenderer objects out of the ytInitialData blob."""
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []

    found: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            vr = node.get("videoRenderer")
            if isinstance(vr, dict) and vr.get("videoId"):
                found.append(vr)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return found


def _text(node) -> str:
    """YouTube stores text as either {simpleText} or {runs:[{text}]}."""
    if not isinstance(node, dict):
        return ""
    if "simpleText" in node:
        return node["simpleText"]
    return "".join(r.get("text", "") for r in node.get("runs", []) if isinstance(r, dict))


_AGE = re.compile(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago", re.I)


def derive_year(published: str, today: date) -> int | None:
    """Relative age -> a year, accurate to about a year and no better."""
    m = _AGE.search(published or "")
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    if unit == "year":
        return today.year - n
    if unit == "month":
        return today.year - (n // 12)
    return today.year


def normalise(vr: dict, vertical: str, today: date) -> dict | None:
    vid = vr.get("videoId")
    title = _text(vr.get("title"))
    if not vid or not title:
        return None
    channel = _text(vr.get("ownerText")) or _text(vr.get("longBylineText"))
    desc = _text(vr.get("detailedMetadataSnippets", [{}])[0].get("snippetText")) if vr.get(
        "detailedMetadataSnippets") else _text(vr.get("descriptionSnippet"))
    published = _text(vr.get("publishedTimeText"))

    blob = f"{title} {desc}"
    haystack = f"{blob} {channel}"
    if OFF_TOPIC.search(blob) or FALSE_FRIEND.search(haystack):
        return None
    if BENCHMARK_EXERCISE.search(blob) or TUTORIAL.search(blob):
        return None
    if not (BEVERAGE.search(blob) and DATA.search(blob)):
        return None

    rec = {
        "title": title.strip(),
        "channel": channel.strip(),
        "video_id": vid,
        "url": f"https://www.youtube.com/watch?v={vid}",
        "vertical": vertical,
        "summary": (desc or "").strip()[:400],
    }
    year = derive_year(published, today)
    if year:
        rec["year"] = year
    return rec


def load_seen() -> set[str]:
    """Every video id already known, from the curated file and the built output."""
    seen: set[str] = set()
    for path in (CURATED, OUT):
        if path.exists():
            for r in json.loads(path.read_text()):
                if r.get("video_id"):
                    seen.add(r["video_id"])
    if EXISTING.exists():
        blob = EXISTING.read_text()
        seen.update(re.findall(r"youtube\.com/watch\?v=([A-Za-z0-9_-]{11})", blob))
        seen.update(re.findall(r"youtu\.be/([A-Za-z0-9_-]{11})", blob))
    return seen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-query", type=int, default=25)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    today = date.today()
    seen = load_seen()
    print("already known: %d video ids" % len(seen))

    # Reposted slop shares a title across different video ids, so id dedup alone
    # lets the same video through several times.
    # Prefix only: slop channels repost the same video under titles that differ
    # in the tail ("...You Didn't See Coming" vs "...You Didn't Expect").
    def title_key(t: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()[:60]

    seen_titles = {title_key(r["title"]) for r in json.loads(CURATED.read_text())} if CURATED.exists() else set()

    kept: list[dict] = []
    for vertical, q in QUERIES:
        try:
            html = fetch_search(q)
        except Exception as exc:
            print("  ! %-52s fetch failed: %s" % (q, exc))
            continue
        raw = parse_results(html)[: args.per_query]
        new = 0
        for vr in raw:
            rec = normalise(vr, vertical, today)
            if not rec or rec["video_id"] in seen:
                continue
            tk = title_key(rec["title"])
            if tk in seen_titles:
                continue
            seen.add(rec["video_id"])
            seen_titles.add(tk)
            kept.append(rec)
            new += 1
        print("  %-52s %3d results -> %2d kept" % (q, len(raw), new))
        time.sleep(2)  # be polite; this is a scrape, not an API

    print("\n%d new videos" % len(kept))
    if args.dry_run:
        for r in kept[:15]:
            print("  - [%s] %s (%s)" % (r["vertical"], r["title"][:70], r.get("year", "?")))
        return 0

    existing = json.loads(OUT.read_text()) if OUT.exists() else []
    existing.extend(kept)
    OUT.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n")
    print("wrote %s (%d total)" % (OUT, len(existing)))
    print("now run: .venv/bin/python scripts/build_resources.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
