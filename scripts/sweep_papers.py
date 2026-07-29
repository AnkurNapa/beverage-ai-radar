#!/usr/bin/env python3
"""Sweep OpenAlex for peer-reviewed work on AI and data in beer, whisky and wine.

Why an API and not a web search: the radar's whole promise is that every row
links to real evidence. OpenAlex returns a DOI, a venue, an author list and an
open-access link per record, so a row can be built from structured fields
rather than from prose that has to be trusted. It also needs no key.

The relevance gate is deliberately strict and runs on OUR side, not theirs. A
scholarly search for "fermentation machine learning" happily returns
bioreactor, biofuel and pharmaceutical papers, which are the same maths applied
to something nobody here makes. A paper is kept only when a beverage term and a
data/AI term BOTH appear, and when the beverage term is not an obvious
homograph ("spirits" in a psychology paper, "wine" as a surname).

Writes data/resources/papers_openalex.json, which build_resources.py then folds
in and dedupes by url alongside the hand-curated files.

Run: python3 scripts/sweep_papers.py [--per-query 50]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "resources" / "papers_openalex.json"
EXISTING = ROOT / "dashboard" / "resources.json"

# A contact address is how OpenAlex's polite pool works; it buys a higher rate
# limit and is the documented way to identify a client.
MAILTO = "napaankur@gmail.com"
API = "https://api.openalex.org/works"

QUERIES = [
    ("beer", "machine learning beer brewing quality"),
    ("beer", "beer flavour prediction sensory model"),
    ("beer", "brewing process fermentation neural network"),
    ("beer", "hop aroma compounds chemometrics prediction"),
    ("beer", "brewery demand forecasting supply chain analytics"),
    ("beer", "beer spoilage detection computer vision"),
    ("whiskey", "whisky spirit maturation machine learning"),
    ("whiskey", "distillation process optimisation neural network spirit"),
    ("whiskey", "whiskey classification spectroscopy chemometrics"),
    ("whiskey", "cask maturation prediction model spirits"),
    ("wine", "wine quality prediction machine learning"),
    ("wine", "viticulture remote sensing yield prediction"),
    ("wine", "grape ripeness computer vision vineyard"),
    ("wine", "wine authentication chemometrics classification"),
    ("wine", "terroir modelling climate wine analytics"),
    ("multiple", "beverage sensory analysis artificial intelligence"),
    ("multiple", "electronic nose tongue beverage classification"),
    ("multiple", "fermentation monitoring soft sensor prediction"),
]

BEVERAGE = re.compile(
    r"\b(beer|brewing|brewery|breweries|brewer|malt|malting|hop|hops|wort|lager|ale|"
    r"wine|wines|winery|wineries|vineyard|viticultur|grape|grapes|must|oenolog|enolog|"
    r"whisky|whiskey|distill|distiller|spirit drink|cask|barrel-aged|"
    r"cider|mead|sake|brandy|tequila|rum|gin|vodka|beverage|alcoholic drink)\b", re.I)
DATA = re.compile(
    r"\b(machine learning|deep learning|neural network|artificial intelligence|"
    r"random forest|gradient boosting|support vector|chemometric|regression model|"
    r"classification model|predictive model|computer vision|remote sensing|"
    r"data.driven|soft sensor|electronic nose|electronic tongue|"
    r"convolutional|transformer|clustering|forecast)\b", re.I)
# Words that mean this is the same maths applied to something nobody here makes.
OFF_TOPIC = re.compile(
    r"\b(biofuel|bioethanol|pharmaceutic|wastewater|sludge|antibiotic|"
    r"petroleum|biodiesel|methane|biogas|cement|semiconductor|"
    r"synthetic biology|metabolic engineering|drug discovery)\b", re.I)

# The UCI "wine quality" CSV is a standard teaching dataset, and running a
# classifier over it is a common undergraduate exercise. Those papers are
# on-topic by every keyword test and worthless to a winemaker: they describe
# no winery, no vintage and no instrument. They arrive in near-identical
# batches, so they are matched by shape rather than by any single word.
BENCHMARK_EXERCISE = re.compile(
    r"^(red |white )?wine quality (prediction|analysis|classification)"
    r"( using| with| via| based on)? (machine learning|ml|different|various|"
    r"5 machine|multiple)", re.I)


def fetch(query: str, per_page: int) -> list[dict]:
    params = urllib.parse.urlencode({
        "search": query,
        "per-page": per_page,
        "mailto": MAILTO,
        "filter": "type:article",
        "sort": "relevance_score:desc",
    })
    req = urllib.request.Request(f"{API}?{params}", headers={"User-Agent": f"beverage-ai-radar ({MAILTO})"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()).get("results", [])


def abstract_of(work: dict) -> str:
    """OpenAlex ships abstracts as an inverted index, for licensing reasons."""
    inv = work.get("abstract_inverted_index")
    if not inv:
        return ""
    words = [(pos, w) for w, ps in inv.items() for pos in ps]
    return " ".join(w for _, w in sorted(words))[:1200]


def best_url(work: dict) -> str:
    """Prefer a landing page a human can actually read; fall back to the DOI."""
    oa = (work.get("best_oa_location") or {}).get("landing_page_url")
    prim = (work.get("primary_location") or {}).get("landing_page_url")
    return oa or prim or work.get("doi") or ""


def to_row(work: dict, vertical: str) -> dict | None:
    title = (work.get("title") or "").strip()
    if not title:
        return None
    abstract = abstract_of(work)
    blob = f"{title} {abstract}"
    if not BEVERAGE.search(blob) or not DATA.search(blob):
        return None
    if OFF_TOPIC.search(blob) and not BEVERAGE.search(title):
        return None
    # Only screen out the benchmark-exercise genre when it has made no impact:
    # a well-cited paper using the same dataset may still have said something.
    if BENCHMARK_EXERCISE.search(title) and (work.get("cited_by_count") or 0) < 25:
        return None
    url = best_url(work)
    if not url:
        return None
    authors = [a["author"]["display_name"] for a in (work.get("authorships") or [])[:1]]
    venue = ((work.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
    year = work.get("publication_year")
    cites = work.get("cited_by_count") or 0
    meta = " · ".join(x for x in [
        (authors[0] + ", et al." if len(work.get("authorships") or []) > 1 else (authors[0] if authors else "")),
        venue, str(year) if year else "", f"{cites} citations" if cites else "",
    ] if x)
    # First two sentences of the abstract: enough to judge relevance, short
    # enough to scan in a card.
    summary = " ".join(re.split(r"(?<=[.!?])\s+", abstract)[:2])[:340] if abstract else ""
    return {
        "kind": "paper", "title": title, "url": url, "vertical": vertical,
        "meta": meta, "summary": summary, "year": year, "sort": year or 0,
        "cited_by": cites,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-query", type=int, default=50)
    args = ap.parse_args()

    try:
        seen_urls = {r.get("url", "").lower().rstrip("/") for r in json.loads(EXISTING.read_text())}
        seen_titles = {re.sub(r"[^a-z0-9]+", " ", (r.get("title") or "").lower()).strip()
                       for r in json.loads(EXISTING.read_text())}
    except OSError:
        seen_urls, seen_titles = set(), set()

    rows, kept_urls = [], set()
    stats = {"fetched": 0, "off_topic": 0, "duplicate": 0, "kept": 0}
    for vertical, q in QUERIES:
        try:
            works = fetch(q, args.per_query)
        except Exception as e:
            print(f"  ! {q}: {e}")
            continue
        stats["fetched"] += len(works)
        for w in works:
            row = to_row(w, vertical)
            if not row:
                stats["off_topic"] += 1
                continue
            u = row["url"].lower().rstrip("/")
            tkey = re.sub(r"[^a-z0-9]+", " ", row["title"].lower()).strip()
            if u in seen_urls or u in kept_urls or tkey in seen_titles:
                stats["duplicate"] += 1
                continue
            kept_urls.add(u)
            rows.append(row)
            stats["kept"] += 1
        print(f"  {vertical:9} {q[:44]:46} +{stats['kept'] - len(rows) + len(rows)}")
        time.sleep(0.3)                     # be polite to a free service

    # Near-duplicate titles: several groups publish the same study under almost
    # the same name. Keep the most-cited of each cluster rather than all of them.
    rows.sort(key=lambda r: (-(r.get("cited_by") or 0), -(r.get("year") or 0)))
    deduped, shapes = [], set()
    for r in rows:
        shape = " ".join(sorted(set(re.sub(r"[^a-z0-9 ]", " ", r["title"].lower()).split())))[:120]
        if shape in shapes:
            stats["duplicate"] += 1
            continue
        shapes.add(shape)
        deduped.append(r)
    rows = deduped
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")

    print(f"\n{stats['fetched']} fetched · {stats['off_topic']} failed the relevance gate · "
          f"{stats['duplicate']} already tracked · {stats['kept']} new")
    by_v = {}
    for r in rows:
        by_v[r["vertical"]] = by_v.get(r["vertical"], 0) + 1
    print("new papers by vertical:", by_v)
    print("->", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
