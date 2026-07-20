from datetime import date
from radar.model import Company
from radar.store import Store
from radar.sources import run_source


class GoodSource:
    name = "good"
    kind = "discovery"

    def discover(self, fetcher):
        return [
            Company(
                name="X", domain="x.com", last_seen=date(2026, 1, 1), first_seen=date(2026, 1, 1)
            )
        ]

    def enrich(self, company, fetcher):
        return company


class BadSource:
    name = "bad"
    kind = "discovery"

    def discover(self, fetcher):
        raise RuntimeError("boom")

    def enrich(self, company, fetcher):
        return company


def test_good_source_upserts(tmp_path):
    store = Store(tmp_path / "t.sqlite")
    res = run_source(GoodSource(), store, fetcher=None)
    assert res["found"] == 1
    assert store.get("x.com") is not None


def test_bad_source_is_isolated(tmp_path):
    store = Store(tmp_path / "t.sqlite")
    res = run_source(BadSource(), store, fetcher=None)
    assert res["found"] == 0
    assert res["errors"] and "boom" in res["errors"][0]
