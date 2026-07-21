import json
from datetime import date
from radar.sources.curated_seed import CuratedSeedSource
from radar.model import BeverageVertical, AIMaturity

SEED = [
    {
        "name": "Tastry",
        "domain": "tastry.com",
        "hq_location": "San Luis Obispo, USA",
        "vertical": "wine",
        "ai_use_case": "sensory",
        "ai_maturity": "shipping",
        "key_people": "Katerina Axelsson (CEO)",
        "source_urls": ["https://tastry.com"],
        "first_seen": "2019-01-01",
        "last_seen": "2025-06-01",
    },
    {
        "name": "OldCask",
        "domain": "oldcask.com",
        "vertical": "whiskey",
        "ai_maturity": "pilot",
        "source_urls": ["https://oldcask.com"],
        "first_seen": "2010-01-01",
        "last_seen": "2012-01-01",
    },
    {
        "name": "Weird",
        "domain": "weird.io",
        "vertical": "banana",
        "source_urls": [],
        "last_seen": "2026-01-01",
    },
]


def test_curated_seed_parses_and_drops_stale(tmp_path):
    p = tmp_path / "seed.json"
    p.write_text(json.dumps(SEED))
    companies = CuratedSeedSource(p, today=date(2026, 7, 20)).discover(fetcher=None)
    keys = {c.key for c in companies}
    assert "tastry.com" in keys  # recent, kept
    assert "oldcask.com" not in keys  # 2012 last_seen is older than 10 years
    tastry = next(c for c in companies if c.key == "tastry.com")
    assert tastry.vertical == BeverageVertical.WINE
    assert tastry.ai_maturity == AIMaturity.SHIPPING
    assert tastry.key_people == "Katerina Axelsson (CEO)"
    # unknown vertical string coerces to None instead of crashing
    weird = next(c for c in companies if c.key == "weird.io")
    assert weird.vertical is None


def test_missing_seed_file_returns_empty(tmp_path):
    assert CuratedSeedSource(tmp_path / "nope.json").discover(fetcher=None) == []
