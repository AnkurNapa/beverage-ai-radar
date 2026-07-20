from datetime import date
from radar.model import Company, BeverageVertical
from radar.store import Store
from radar.outputs.digest import build_digest


def test_digest_lists_companies_first_seen_today(tmp_path):
    s = Store(tmp_path / "t.sqlite")
    s.upsert(
        Company(
            name="NewCo",
            domain="newco.ai",
            vertical=BeverageVertical.BEER,
            source_urls=["https://newco.ai"],
            first_seen=date(2026, 7, 20),
            last_seen=date(2026, 7, 20),
        )
    )
    s.upsert(
        Company(
            name="OldCo",
            domain="oldco.ai",
            first_seen=date(2026, 1, 1),
            last_seen=date(2026, 7, 20),
        )
    )
    text = build_digest(s, today=date(2026, 7, 20))
    assert "NewCo" in text and "OldCo" not in text
    assert "—" not in text
