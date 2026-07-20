from datetime import date
from radar.model import Company, BeverageVertical
from radar.store import Store
from radar.pipeline import run


class DiscA:
    name = "a"
    kind = "discovery"

    def discover(self, fetcher):
        return [
            Company(
                name="BrewBrain",
                domain="brewbrain.ai",
                vertical=BeverageVertical.BEER,
                source_urls=["https://brewbrain.ai"],
                first_seen=date(2026, 1, 1),
                last_seen=date(2026, 6, 1),
            )
        ]

    def enrich(self, c, fetcher):
        return c


class EnrichA:
    name = "e"
    kind = "enrichment"

    def discover(self, fetcher):
        return []

    def enrich(self, c, fetcher):
        from dataclasses import replace

        return replace(c, funding_stage="Seed")


def test_run_discovers_enriches_and_exports(tmp_path):
    store = Store(tmp_path / "t.sqlite")
    summary = run(
        store,
        fetcher=None,
        sources=[DiscA(), EnrichA()],
        outputs_dir=tmp_path,
        vault_dir=tmp_path / "vault",
        today=date(2026, 7, 20),
    )
    assert summary["total_companies"] == 1
    assert store.get("brewbrain.ai").funding_stage == "Seed"
    assert (tmp_path / "data.json").exists()
    assert (tmp_path / "report.md").exists()
