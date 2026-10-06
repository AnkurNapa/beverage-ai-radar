from datetime import date

from radar.coverage import record_sweep
from radar.scout.briefs import render_briefs
from radar.scout.windows import sweep_window

TODAY = date(2026, 10, 7)


def row(d, surface="wine", lane="companies", **extra):
    return {"date": d, "lane": lane, "surface": surface, "found": 1, "added": 1, **extra}


def test_never_swept_surface_is_open():
    w = sweep_window([], "wine", TODAY)
    assert w["fresh_since"] is None
    assert w["back_from"] is None and w["back_to"] is None
    assert w["complete"] is False


def test_fresh_window_starts_at_last_sweep_minus_overlap():
    w = sweep_window([row("2026-09-21")], "wine", TODAY)
    assert w["fresh_since"] == date(2026, 9, 7)


def test_legacy_sweep_backfills_from_two_years_back():
    """Sweeps before windows existed covered recent material, not history."""
    w = sweep_window([row("2026-09-21")], "wine", TODAY)
    assert w["back_to"] == date(2024, 10, 7)
    assert w["back_from"] == date(2023, 10, 8)


def test_backfill_cursor_steps_back_one_slice_per_sweep():
    rows = [row("2026-09-21"), row("2026-10-07", back_from="2023-10-08")]
    w = sweep_window(rows, "wine", TODAY)
    assert w["back_to"] == date(2023, 10, 8)
    assert w["back_from"] == date(2022, 10, 8)


def test_backfill_stops_at_the_horizon():
    rows = [row("2026-10-01", back_from="2016-10-07")]
    w = sweep_window(rows, "wine", TODAY)
    assert w["complete"] is True
    assert w["back_from"] is None and w["back_to"] is None


def test_last_slice_is_clamped_to_the_horizon():
    rows = [row("2026-10-01", back_from="2017-03-01")]
    w = sweep_window(rows, "wine", TODAY)
    assert w["back_from"] == date(2016, 10, 7)
    assert w["complete"] is False


def test_other_surfaces_and_lanes_are_ignored():
    rows = [row("2026-10-01", surface="beer"), row("2026-10-01", lane="people")]
    assert sweep_window(rows, "wine", TODAY)["fresh_since"] is None


def test_brief_carries_both_windows(tmp_path):
    surfaces = [{"id": "wine", "label": "Wine", "hint": "wineries"}]
    windows = {"wine": sweep_window([row("2026-09-21")], "wine", TODAY)}
    text = render_briefs(surfaces, [], [], tmp_path, TODAY, windows)[0].read_text()
    assert "2026-09-07" in text
    assert "2023-10-08" in text and "2024-10-07" in text
    assert "enrich_wine.json" in text


def test_brief_without_window_has_no_time_section(tmp_path):
    surfaces = [{"id": "wine", "label": "Wine", "hint": "wineries"}]
    text = render_briefs(surfaces, [], [], tmp_path, TODAY)[0].read_text()
    assert "## Time window" not in text


def test_record_sweep_stores_the_backfill_cursor(tmp_path):
    ledger = tmp_path / "ledger.json"
    record_sweep(ledger, "companies", "wine", 3, 2, "2026-10-07", window={"back_from": "2023-10-08"})
    w = sweep_window(__import__("json").loads(ledger.read_text()), "wine", TODAY)
    assert w["back_to"] == date(2023, 10, 8)
