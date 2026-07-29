"""Rank the thin slices of prospect coverage, so a sweep targets what is missing.

Pure functions over the current prospect list. No network, no LLM: this decides
WHAT to look for, the scouts decide who is out there.

Same both-tests rule as `radar.scout.gaps`: a slice counts as a gap only when it
is both a small share and a small count. Share alone flags every slice of a wide
axis like region; count alone stops flagging anything once the list grows.
"""

from __future__ import annotations

from collections import Counter

# Deliberately lower than the vendor thresholds: a region with 8 good targets is
# workable for outreach, whereas 8 tracked vendors is a thin landscape.
GAP_MIN_COUNT = 8
GAP_MIN_SHARE = 0.06
VERTICALS = ("beer", "whisky", "wine", "multiple")


def _slice_gaps(axis: str, observed: Counter, universe, total: int) -> list[dict]:
    out = []
    for value in universe:
        count = observed.get(value, 0)
        share = count / total if total else 0.0
        if count > GAP_MIN_COUNT or share > GAP_MIN_SHARE:
            continue
        out.append({"axis": axis, "value": value, "count": count, "share": round(share, 3)})
    return sorted(out, key=lambda g: (g["count"], g["value"]))


def compute(rows: list[dict], regions=None) -> dict:
    """Gaps by region, by vertical, and by region x actionable-tier.

    Tier 1-2 coverage is reported separately because a region full of tier-4
    conference rows is not a region you can actually sell into.
    """
    total = len(rows)
    regions = list(regions) if regions else sorted({r["region"] for r in rows})

    by_region = Counter(r["region"] for r in rows)
    by_vertical = Counter(r.get("vertical") for r in rows)
    actionable = Counter(r["region"] for r in rows if r.get("tier", 9) <= 2)

    thin_actionable = sorted(
        (
            {"axis": "region_tier12", "value": rg, "count": actionable.get(rg, 0),
             "share": round(actionable.get(rg, 0) / total, 3) if total else 0.0}
            for rg in regions
            if actionable.get(rg, 0) <= 4
        ),
        key=lambda g: (g["count"], g["value"]),
    )

    return {
        "total": total,
        "regions": _slice_gaps("region", by_region, regions, total),
        "verticals": _slice_gaps("vertical", by_vertical, VERTICALS, total),
        "actionable": thin_actionable,
    }


def format_gaps(g: dict) -> str:
    lines = [f"{g['total']} prospects tracked.", ""]
    for title, key in (("Thin regions", "regions"),
                       ("Thin verticals", "verticals"),
                       ("Regions with <=4 actionable (tier 1-2) targets", "actionable")):
        lines.append(f"## {title}")
        if not g[key]:
            lines.append("  (none)")
        for row in g[key]:
            lines.append(f"  {row['count']:4d}  {row['value']}")
        lines.append("")
    return "\n".join(lines)
