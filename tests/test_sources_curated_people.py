import json
from datetime import date
from radar.sources.curated_people import CuratedPeopleSource
from radar.model import BeverageVertical, AIMaturity

PEOPLE = [
    {
        "name": "Ada Brewer",
        "role": "Independent ML consultant, breweries",
        "linkedin": "https://www.linkedin.com/in/ada-brewer/",
        "location": "Berlin, Germany",
        "vertical": "beer",
        "ai_use_case": "sensory analytics",
        "ai_maturity": "shipping",
        "source_urls": ["https://example.com/ada"],
        "first_seen": "2023-01-01",
        "last_seen": "2026-06-01",
    },
    {
        "name": "Stale Sam",
        "role": "Researcher",
        "location": "Nowhere",
        "source_urls": [],
        "last_seen": "2010-01-01",
    },
]


def test_people_lane_parses_flags_individual_and_drops_stale(tmp_path):
    p = tmp_path / "people_seed.json"
    p.write_text(json.dumps(PEOPLE))
    people = CuratedPeopleSource(p, today=date(2026, 7, 22)).discover(fetcher=None)
    names = {c.name for c in people}
    assert "Ada Brewer" in names  # recent, kept
    assert "Stale Sam" not in names  # 2010 last_seen older than 10 years

    ada = next(c for c in people if c.name == "Ada Brewer")
    assert ada.company_type == "individual"
    assert ada.vertical == BeverageVertical.BEER
    assert ada.ai_maturity == AIMaturity.SHIPPING
    assert ada.key_people == "Ada Brewer (Independent ML consultant, breweries)"
    assert ada.people == [
        {
            "name": "Ada Brewer",
            "role": "Independent ML consultant, breweries",
            "linkedin": "https://www.linkedin.com/in/ada-brewer/",
        }
    ]
    assert ada.linkedin_url == "https://www.linkedin.com/in/ada-brewer/"


def test_missing_people_seed_returns_empty(tmp_path):
    assert CuratedPeopleSource(tmp_path / "nope.json").discover(fetcher=None) == []
