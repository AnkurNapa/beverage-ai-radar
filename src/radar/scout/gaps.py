"""Rank the thin slices of coverage, so scouting targets what is missing.

Pure functions over companies already in the store. No network, no LLM: this
decides WHAT to look for, the scouts decide what is out there.
"""

from __future__ import annotations

from collections import Counter
from datetime import date

from radar.config import ACTIVE_MONTHS, GAP_MIN_COUNT, GAP_MIN_SHARE, GAP_TOP_N, STALE_MONTHS
from radar.model import BeverageVertical, _months_between
from radar.themes import all_themes, theme_of


def _country(company) -> str:
    loc = (company.hq_location or "").strip()
    return loc.split(",")[-1].strip() if loc else "unknown"


def _slice_gaps(axis: str, observed: Counter, universe, total: int) -> list[dict]:
    """A slice is a gap when it is both a small share and a small count.

    Both tests matter: share alone flags everything in a wide axis like country,
    count alone flags nothing once the corpus grows.
    """
    out = []
    for value in universe:
        count = observed.get(value, 0)
        share = count / total if total else 0.0
        if count > GAP_MIN_COUNT or share > GAP_MIN_SHARE:
            continue
        out.append(
            {
                "axis": axis,
                "value": value,
                "count": count,
                "share": round(share, 3),
                "reason": f"{count} of {total} tracked companies ({share:.0%}) are {axis} {value!r}",
            }
        )
    return out


def find_gaps(
    companies: list,
    today: date | None = None,
    top_n: int = GAP_TOP_N,
) -> list[dict]:
    """Thinnest-first list of coverage gaps.

    Axes: vertical, business theme, HQ country, plus a staleness gap for
    companies whose evidence is aging toward the dormant line.
    """
    today = today or date.today()
    total = len(companies)
    if not total:
        return []

    gaps: list[dict] = []

    gaps += _slice_gaps(
        "vertical",
        Counter(c.vertical.value for c in companies if c.vertical),
        [v.value for v in BeverageVertical],
        total,
    )
    gaps += _slice_gaps(
        "theme",
        Counter(theme_of(c.ai_use_case) for c in companies),
        all_themes(),
        total,
    )
    # Countries are open-ended, so only report ones we already touch: a gap on
    # a country with zero presence is not evidence of anything.
    countries = Counter(_country(c) for c in companies)
    gaps += _slice_gaps(
        "country",
        countries,
        [c for c in countries if c != "unknown"],
        total,
    )

    stale = [
        c
        for c in companies
        if c.last_seen and STALE_MONTHS <= _months_between(c.last_seen, today) < ACTIVE_MONTHS
    ]
    if stale:
        gaps.append(
            {
                "axis": "staleness",
                "value": "aging evidence",
                "count": len(stale),
                "share": round(len(stale) / total, 3),
                "reason": (
                    f"{len(stale)} companies last had evidence {STALE_MONTHS}+ months ago and "
                    f"go dormant at {ACTIVE_MONTHS}; they need fresh evidence, not replacing"
                ),
                "examples": sorted(c.name for c in stale)[:10],
            }
        )

    # Round-robin across axes rather than a global sort. A plain sort by count
    # lets a wide axis monopolise the list: every zero-count theme outranks a
    # vertical sitting at 1, so the thinnest vertical never reaches the brief.
    by_axis: dict[str, list[dict]] = {}
    for g in sorted(gaps, key=lambda g: (g["count"], g["value"])):
        by_axis.setdefault(g["axis"], []).append(g)

    # Cap each axis too. Country is open-ended, so without a cap a dozen
    # one-company countries crowd out the axes a scout can actually act on.
    # "Belgium has 1" is trivia; "whiskey has 9" is a brief.
    per_axis_cap = max(1, top_n // max(len(by_axis), 1))
    out: list[dict] = []
    taken: dict[str, int] = {}
    while len(out) < top_n and any(by_axis.values()):
        progressed = False
        for axis in list(by_axis):
            if by_axis[axis] and taken.get(axis, 0) < per_axis_cap and len(out) < top_n:
                out.append(by_axis[axis].pop(0))
                taken[axis] = taken.get(axis, 0) + 1
                progressed = True
        if not progressed:
            break
    return out
