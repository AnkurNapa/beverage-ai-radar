#!/usr/bin/env python3
"""Harvest people from the author lists of the radar's paper library.

Every paper in dashboard/resources.json already passed the beverage-and-AI gate,
so this needs no web search at all: OpenAlex returns each paper's full author
list with affiliations, 50 DOIs per request. The selection rule and row shape
live in src/radar/harvest.py; this file is only the network half.

Writes .scout/people_finds/find_harvest_openalex.json, which goes through the
same gate as a scout's finds:

    PYTHONPATH=src .venv/bin/python -m radar.cli people-merge \
        .scout/people_finds/find_harvest_openalex.json

Middle authors of a single paper land in .scout/harvest_candidates.json.

Run: python3 scripts/harvest_authors.py
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from radar.harvest import people_from_works  # noqa: E402
from sweep_papers import BEVERAGE, MAILTO  # noqa: E402

RESOURCES = ROOT / "dashboard" / "resources.json"
OUT = ROOT / ".scout" / "people_finds" / "find_harvest_openalex.json"
CANDIDATES = ROOT / ".scout" / "harvest_candidates.json"
BATCH = 50  # OpenAlex caps an OR filter at 50 values
PAUSE = 0.2  # polite pool allows 10/s; stay well under
OFF_SCOPE = re.compile(r"\b(coffee|tea|cocoa|kombucha)\b", re.I)


def beverage_title(title: str) -> bool:
    return bool(BEVERAGE.search(title)) and not OFF_SCOPE.search(title)


def get(path: str, params: dict) -> list[dict]:
    params = {**params, "mailto": MAILTO, "per-page": BATCH}
    url = f"https://api.openalex.org/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": f"beverage-ai-radar ({MAILTO})"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()).get("results", [])


def batched(items):
    for i in range(0, len(items), BATCH):
        yield items[i : i + BATCH]


def main() -> int:
    papers = [r for r in json.loads(RESOURCES.read_text()) if r.get("kind") == "paper"]
    vertical_by_doi = {
        "https://doi.org/" + r["url"].split("doi.org/", 1)[1].lower(): r.get("vertical")
        for r in papers
        if "doi.org/" in r.get("url", "")
    }
    dois = sorted(d.removeprefix("https://doi.org/") for d in vertical_by_doi)
    works = []
    for chunk in batched(dois):
        works += get(
            "works",
            {
                "filter": "doi:" + "|".join(chunk),
                "select": "doi,title,publication_year,publication_date,authorships",
            },
        )
        time.sleep(PAUSE)
    for w in works:
        w["doi"] = (w.get("doi") or "").lower()
    print(f"{len(works)} of {len(dois)} DOIs resolved on OpenAlex")

    inst_ids = sorted(
        {
            (a.get("institutions") or [{}])[0].get("id")
            for w in works
            for a in w.get("authorships") or []
            if (a.get("institutions") or [{}])[0].get("id")
        }
    )
    place = {}
    for chunk in batched([i.rsplit("/", 1)[1] for i in inst_ids]):
        for inst in get(
            "institutions", {"filter": "openalex:" + "|".join(chunk), "select": "id,geo"}
        ):
            geo = inst.get("geo") or {}
            place[inst["id"]] = (
                ", ".join(x for x in (geo.get("city"), geo.get("country")) if x) or None
            )
        time.sleep(PAUSE)

    people, candidates = people_from_works(
        works, vertical_by_doi, place, date.today(), beverage_title
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"surface": "harvest_openalex", "people": people}, indent=1, ensure_ascii=False)
        + "\n"
    )
    CANDIDATES.write_text(json.dumps(candidates, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(people)} people (lead, senior or 2+ papers) -> {OUT.relative_to(ROOT)}")
    print(f"{len(candidates)} single-paper middle authors -> {CANDIDATES.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
