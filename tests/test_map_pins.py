"""Every map pin must sit in the country the dashboard files it under.

dashboard/geo.json is built by scripts/build_geocode.py from free-text places,
and a geocoder will happily find a town for anything: "unknown" landed 174
companies in India, "USA" went to Japan, "UK" to Russia, "Napa, CA" to Alabama
and "Online" to wherever a town of that name is. This keeps those out.
"""

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_geocode import ALIASES, PLACEHOLDER  # noqa: E402

DASH = ROOT / "dashboard"
GEO = json.loads((DASH / "geo.json").read_text())
# Big countries legitimately put a city far from their centre.
LIMIT_KM = {"United States": 4500, "Canada": 4500, "Russia": 6000, "Australia": 3500,
            "Brazil": 3500, "China": 3500, "India": 2500, "Chile": 2500,
            "Argentina": 2500, "Mexico": 2000, "Japan": 2500}  # Okinawa


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, [*a, *b])
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def country_of(r):  # mirrors countryOf() in dashboard/app.js
    return r.get("country") or (r.get("hq_location") or "").split(",")[-1].strip()


def rows():
    for r in json.loads((DASH / "data.json").read_text()):
        yield r.get("hq_location"), country_of(r)
    for name in ("events", "jobs"):
        for r in json.loads((DASH / f"{name}.json").read_text()):
            yield r.get("location"), r.get("country")


def test_no_placeholder_is_geocoded():
    assert not [k for k in GEO if PLACEHOLDER.match(k)]


def test_every_pin_is_in_its_own_country():
    wrong = []
    for loc, country in rows():
        country = ALIASES.get(country, country)
        if not loc or not country or country == "unknown" or not GEO.get(loc) or not GEO.get(country):
            continue
        d = km(GEO[loc], GEO[country])
        if d > LIMIT_KM.get(country, 1500):
            wrong.append((loc, country, round(d)))
    assert not wrong, wrong
