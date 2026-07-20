from datetime import date
from radar.model import Company
from radar.sources.crunchbase import CrunchbaseSource
from radar.sources.github_product import GithubProductSource


def test_crunchbase_fills_funding_only():
    src = CrunchbaseSource(lookup_fn=lambda c: {
        "funding_stage": "Seed", "total_raised": "$2M",
        "key_people": "Jane Doe (CEO)", "source_url": "https://cb.com/x"})
    c = Company(name="X", domain="x.com", last_seen=date(2026, 1, 1),
                first_seen=date(2026, 1, 1))
    out = src.enrich(c, fetcher=None)
    assert out.funding_stage == "Seed"
    assert out.total_raised == "$2M"
    assert "https://cb.com/x" in out.source_urls
    assert out is not c  # immutable update


def test_empty_lookup_leaves_company_unchanged():
    src = GithubProductSource(lookup_fn=lambda c: {})
    c = Company(name="X", domain="x.com", last_seen=date(2026, 1, 1))
    out = src.enrich(c, fetcher=None)
    assert out.github_url is None
