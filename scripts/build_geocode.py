#!/usr/bin/env python3
"""Geocode every place string the dashboard maps into dashboard/geo.json.

The map pins companies, events and jobs at their city, but the data only
carries text like "Dortmund, Germany". This turns each distinct string (and
each country, the fallback when a city will not resolve) into [lat, lng] via
Photon (komoot's geocoder over OpenStreetMap data; Nominatim rate-limits this
machine to 429 on sight). The file is a cache: only strings missing from it are
looked up, so a rerun after a sweep costs seconds, not the minutes of the first
build. The sleep keeps us a polite client of a free service.

Run: python3 scripts/build_geocode.py   (after a sweep adds companies)
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

DASH = Path(__file__).resolve().parents[1] / "dashboard"
OUT = DASH / "geo.json"
UA = "beverage-ai-radar/1.0 (github.com/AnkurNapa/beverage-ai-radar)"
RATE_S = 0.5


def places() -> set[str]:
    rows = json.loads((DASH / "data.json").read_text())
    for name in ("events", "jobs"):
        rows += json.loads((DASH / f"{name}.json").read_text())
    found = set()
    for r in rows:
        for k in ("hq_location", "location", "country"):
            if r.get(k):
                found.add(r[k].strip())
        if r.get("hq_location"):
            found.add(r["hq_location"].split(",")[-1].strip())  # countryOf() fallback
    # "unknown", "Online", "Remote" are not places, but a geocoder will still
    # find a town by that name. Leave them out so the row pins at its country.
    return {p for p in found if not PLACEHOLDER.match(p)}


PLACEHOLDER = re.compile(r"^(unknown|n/?a|none|remote|global|worldwide|online|virtual|hybrid|"
                         r"various|tbd|tba|anywhere)$", re.I)


# Photon reads bare "USA" as a town in Japan, "UK" as one in Russia and "Korea"
# as one in Poland, and "Napa, CA" as Napa, Alabama. Spell them out.
ALIASES = {"USA": "United States", "US": "United States", "U.S.": "United States",
           "UK": "United Kingdom", "Korea": "South Korea"}
US_STATES = dict(s.split("=") for s in (
    "AL=Alabama AK=Alaska AZ=Arizona AR=Arkansas CA=California CO=Colorado CT=Connecticut "
    "DE=Delaware FL=Florida GA=Georgia HI=Hawaii ID=Idaho IL=Illinois IN=Indiana IA=Iowa "
    "KS=Kansas KY=Kentucky LA=Louisiana ME=Maine MD=Maryland MA=Massachusetts MI=Michigan "
    "MN=Minnesota MS=Mississippi MO=Missouri MT=Montana NE=Nebraska NV=Nevada NH=New_Hampshire "
    "NJ=New_Jersey NM=New_Mexico NY=New_York NC=North_Carolina ND=North_Dakota OH=Ohio "
    "OK=Oklahoma OR=Oregon PA=Pennsylvania RI=Rhode_Island SC=South_Carolina SD=South_Dakota "
    "TN=Tennessee TX=Texas UT=Utah VT=Vermont VA=Virginia WA=Washington WV=West_Virginia "
    "WI=Wisconsin WY=Wyoming").split())


def query_for(place: str) -> str:
    # "Reno, NV, USA and Bonaduz, Switzerland" and "A; B" name two sites. Pin the
    # last: its country is the one the dashboard files the row under (countryOf).
    # "(delivery centre in Bengaluru)" asides confuse the geocoder, so drop them.
    place = re.sub(r"\([^)]*\)", "", place)
    sites = [s.strip() for s in re.split(r"\s+(?:and|&)\s+|;|/", place)]
    place = [s for s in sites if not PLACEHOLDER.match(s)][-1]
    parts = [x.strip() for x in place.split(",")]
    parts = [ALIASES.get(x, x) for x in parts]
    # ponytail: "City, XX" is read as a US state; a future "Cologne, DE" would land
    # in Delaware. Fine while every two-part place in the data is a US job posting.
    if parts[-1] == "United States" or len(parts) == 2:
        parts = [US_STATES.get(x, x).replace("_", " ") if i else x for i, x in enumerate(parts)]
    return ", ".join(parts)


def lookup(place: str):
    url = "https://photon.komoot.io/api/?" + urllib.parse.urlencode(
        {"q": query_for(place), "limit": 1, "lang": "en"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        hits = json.load(r)["features"]
    if not hits:
        return None
    lng, lat = hits[0]["geometry"]["coordinates"]
    return [round(lat, 4), round(lng, 4)]


def main() -> int:
    cache = json.loads(OUT.read_text()) if OUT.exists() else {}
    if "--refresh" in sys.argv:          # re-look-up everything whose query normalises differently
        cache = {k: v for k, v in cache.items() if query_for(k) == k}
    todo = sorted(p for p in places() if p not in cache)
    print(f"{len(cache)} cached, {len(todo)} to look up")
    misses = []
    for i, place in enumerate(todo, 1):
        try:
            cache[place] = lookup(place)
        except Exception as e:  # network blip: leave it out so the next run retries
            print(f"  error {place!r}: {e}", file=sys.stderr)
            continue
        if cache[place] is None:
            misses.append(place)  # cached as null so it is not retried every run
        if i % 25 == 0:
            OUT.write_text(json.dumps(cache, sort_keys=True, ensure_ascii=False))
            print(f"  {i}/{len(todo)}")
        time.sleep(RATE_S)
    OUT.write_text(json.dumps(cache, sort_keys=True, ensure_ascii=False))
    print(f"done, {len(misses)} unresolved (they fall back to their country): {misses[:20]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
