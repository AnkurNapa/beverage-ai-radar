"""Time windows for a scout surface: what is new since the last sweep, and which
older slice to backfill next.

Without this every sweep re-reads the same recent pages and rediscovers what is
already tracked, while older case studies and past exhibitor lists are never
read at all. The fresh window comes from the ledger's last sweep date; the
backfill cursor is the oldest `back_from` a merge has recorded, and each sweep
steps it one slice further back until it reaches the radar's 10-year horizon.
"""

from __future__ import annotations

from datetime import date, timedelta

OVERLAP = timedelta(days=14)  # announcements are often indexed a week or two late
SLICE = timedelta(days=365)
HORIZON_YEARS = 10  # the dashboard drops evidence older than this
LEGACY_RECENT_YEARS = 2  # what pre-window sweeps are assumed to have covered


def _years_back(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:  # 29 February
        return d.replace(year=d.year - years, day=28)


def sweep_window(rows: list[dict], surface: str, today: date, lane: str = "companies") -> dict:
    mine = [r for r in rows if r.get("lane") == lane and r.get("surface") == surface]
    window = {"fresh_since": None, "back_from": None, "back_to": None, "complete": False}
    if not mine:
        return window

    window["fresh_since"] = max(date.fromisoformat(r["date"]) for r in mine) - OVERLAP
    cursors = [date.fromisoformat(r["back_from"]) for r in mine if r.get("back_from")]
    back_to = min(cursors) if cursors else _years_back(today, LEGACY_RECENT_YEARS)
    horizon = _years_back(today, HORIZON_YEARS)
    if back_to <= horizon:
        window["complete"] = True
        return window
    window["back_to"] = back_to
    window["back_from"] = max(back_to - SLICE, horizon)
    return window
