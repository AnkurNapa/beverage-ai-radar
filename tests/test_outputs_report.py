from datetime import date
from radar.model import Company, BeverageVertical
from radar.store import Store
from radar.outputs.report import render_report


def seed(tmp_path):
    s = Store(tmp_path / "t.sqlite")
    s.upsert(
        Company(
            name="BrewBrain",
            domain="brewbrain.ai",
            vertical=BeverageVertical.BEER,
            ai_use_case="recipe / flavor prediction",
            source_urls=["https://brewbrain.ai"],
            first_seen=date(2026, 1, 1),
            last_seen=date(2026, 6, 1),
        )
    )
    s.upsert(
        Company(
            name="OldCask",
            domain="oldcask.com",
            vertical=BeverageVertical.WHISKEY,
            source_urls=["https://oldcask.com"],
            first_seen=date(2021, 1, 1),
            last_seen=date(2023, 1, 1),
        )
    )
    return s


def test_report_has_sections_and_no_em_dash(tmp_path):
    s = seed(tmp_path)
    text = render_report(s, today=date(2026, 7, 20))
    assert "Active" in text and "Dormant" in text
    assert "BrewBrain" in text
    assert "—" not in text and "–" not in text  # no em/en dash
