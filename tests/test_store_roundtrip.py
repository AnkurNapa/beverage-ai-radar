"""Every field must survive a write and a read unchanged.

This exists because three separate bugs in one day were all the same bug: the
sqlite mapping dispatches on hand-maintained sets (_LIST_FIELDS, _BOOL_FIELDS,
_DATE_FIELDS, _ENUM_FIELDS) and anything not listed falls through to str(v).
A new field is therefore silently corrupted rather than rejected:

  - affiliated_company_current, a bool, came back as the string "False", so the
    dashboard's `=== false` never matched and a former role rendered as current
    employment.
  - links, a list, would have come back as "[{'label': ...}]" mangled by str().
  - The same shape would hit any future field.

A per-field guard test only covers the type someone remembered to guard. This
populates every field on Company and asserts the value read back equals the
value written, so the next unregistered field fails here instead of in the
export.
"""

from dataclasses import fields
from datetime import date

import pytest

from radar.model import AIMaturity, BeverageVertical, Company, Status
from radar.store import Store

# One representative value per declared type. Deliberately not derived from the
# dataclass defaults: defaults are mostly None, which round-trips trivially and
# would prove nothing.
SAMPLES = {
    "name": "Round Trip Ltd",
    "domain": "roundtrip.co.uk",  # multi-label suffix, the earlier dedup bug
    "hq_location": "Berlin, Germany",
    "founded_year": 2019,
    "size_employees": "11-50",
    "vertical": BeverageVertical.BEER,
    "company_type": "individual",
    "ai_use_case": "fermentation forecasting",
    "ai_maturity": AIMaturity.PILOT,
    "funding_stage": "seed",
    "total_raised": "$2M",
    "key_people": "A Person (CTO)",
    "people": [{"name": "A Person", "role": "CTO", "linkedin": None}],
    "notable_customers_partners": "A Brewery",
    "short_description": "Makes no AI claim; recorded honestly.",
    "source_urls": ["https://roundtrip.co.uk/", "https://example.org/a"],
    "first_seen": date(2024, 1, 1),
    "last_seen": date(2026, 8, 4),
    "status": Status.ACTIVE,
    "linkedin_url": "https://www.linkedin.com/in/someone/",
    "github_url": "https://github.com/someone",
    "product_url": "https://roundtrip.co.uk/product",
    "latest_news_headline": "Raised a seed round",
    "why_interesting": "Named brewery customer",
    "discovered_by": "curated",
    "verified": True,
    "links": [{"label": "Talk", "url": "https://example.org/t", "kind": "video"}],
    "verticals": ["beer", "wine"],
    "affiliated_company": "Some Employer",
    "affiliated_company_current": False,  # the value that broke
}


def test_samples_cover_every_field():
    """If someone adds a field to Company, this fails until it is exercised."""
    declared = {f.name for f in fields(Company)}
    assert declared == set(SAMPLES), (
        f"unexercised fields: {sorted(declared - set(SAMPLES))}; "
        f"unknown samples: {sorted(set(SAMPLES) - declared)}"
    )


@pytest.mark.parametrize("field_name", sorted(SAMPLES))
def test_field_survives_the_sqlite_round_trip(field_name):
    store = Store(":memory:")
    written = Company(**SAMPLES)
    store.upsert(written)
    read = store.get(written.key)
    assert read is not None, "row vanished on write"
    got, want = getattr(read, field_name), SAMPLES[field_name]
    assert got == want, (
        f"{field_name}: wrote {want!r} ({type(want).__name__}), "
        f"read {got!r} ({type(got).__name__}). "
        "Unregistered types fall through to str(v) in Store._to_row."
    )


def test_falsey_bool_is_not_confused_with_absent():
    """False must survive as False, not become None or "0" or "False"."""
    store = Store(":memory:")
    c = Company(**{**SAMPLES, "verified": False, "affiliated_company_current": False})
    store.upsert(c)
    read = store.get(c.key)
    assert read.verified is False
    assert read.affiliated_company_current is False


def test_empty_list_stays_an_empty_list():
    store = Store(":memory:")
    c = Company(**{**SAMPLES, "links": [], "people": []})
    store.upsert(c)
    read = store.get(c.key)
    assert read.links == []
    assert read.people == []
