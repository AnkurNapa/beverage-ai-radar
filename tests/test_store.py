from datetime import date
from radar.model import Company, BeverageVertical
from radar.store import Store


def make_store(tmp_path):
    return Store(tmp_path / "t.sqlite")


def test_upsert_then_get(tmp_path):
    s = make_store(tmp_path)
    s.upsert(Company(name="Acme AI", domain="acme-ai.com",
                     vertical=BeverageVertical.BEER,
                     source_urls=["https://a.com"],
                     first_seen=date(2026, 1, 1), last_seen=date(2026, 1, 1)))
    got = s.get("acme-ai.com")
    assert got.name == "Acme AI"
    assert got.vertical == BeverageVertical.BEER


def test_upsert_merges_evidence_and_dates(tmp_path):
    s = make_store(tmp_path)
    s.upsert(Company(name="Acme", domain="acme-ai.com",
                     source_urls=["https://a.com"],
                     first_seen=date(2026, 1, 1), last_seen=date(2026, 1, 1)))
    s.upsert(Company(name="Acme", domain="acme-ai.com",
                     hq_location="Berlin, Germany",
                     source_urls=["https://b.com"],
                     first_seen=date(2025, 6, 1), last_seen=date(2026, 7, 1)))
    got = s.get("acme-ai.com")
    assert set(got.source_urls) == {"https://a.com", "https://b.com"}
    assert got.first_seen == date(2025, 6, 1)
    assert got.last_seen == date(2026, 7, 1)
    assert got.hq_location == "Berlin, Germany"  # null filled


def test_all_returns_every_company(tmp_path):
    s = make_store(tmp_path)
    s.upsert(Company(name="A", domain="a.com", last_seen=date(2026, 1, 1)))
    s.upsert(Company(name="B", domain="b.com", last_seen=date(2026, 1, 1)))
    assert len(s.all()) == 2
