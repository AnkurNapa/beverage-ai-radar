"""Render one scout brief per surface from current prospect coverage.

The gap section and the skip list are generated from the live list on every run,
so they cannot rot the way a hand-maintained prompt does. Everything an agent
needs is in the brief; the dispatch prompt stays a single line. That separation
is the whole point, and is why `radar.scout.briefs` does the same thing.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from radar.prospects.gaps import compute, format_gaps

SCHEMA_BLOCK = """{
  "tier": 1 | 2 | 3 | 4 | 5,
  "company": "Exact legal or trading name",
  "region": "one of the regions named in this brief",
  "vertical": "beer" | "whisky" | "wine" | "multiple",
  "hq": "City, Country",
  "segment": "Short label, e.g. 'Single malt' or 'Microbrewery chain'",
  "pain": "2-3 factual sentences. The problem THEY already have, in their language, with a concrete number or event where possible.",
  "wedge": "One item from the wedge menu below. One only.",
  "entry": "Who to approach. A named person ONLY if a source URL proves they hold that role today, otherwise the role title.",
  "url": "https://their-own-site.com",
  "source_urls": ["https://their-own-site.com/about", "https://second-independent-source"],
  "last_seen": "YYYY-MM-DD"
}"""

WEDGE_MENU = """1. Batch consistency / quality analytics
2. Demand forecasting (SKU x region x month, calendar-aware)
3. Recipe and flavour prediction
4. Excise / compliance reporting automation
5. Taproom / retail analytics
6. Distillery process intelligence (cut points, yield, cask maturation)
7. Vintage / harvest quality analytics (wine)"""

TIER_RULES = """1  Best fit, will pay. A named company with a real, current, evidenced problem. GATED: needs two sources, one on its own domain.
2  Corporate, long cycle. Large group with an internal data team. GATED the same way. Entry must be a role, never a guessed name.
3  Volume play. A category of small buyer (chains, independents). Curated, not gated.
4  Channel multiplier. Conference, association, institute, vendor, press, investor. Curated. Conferences MUST carry a real future date.
5  Adjacent buyer. Retail, hospitality, suppliers, non-alc. Curated."""

RULES = """## Verification rules

- **Two sources for tier 1-2, one of them on the company's own domain.** A row that
  cannot cite its own website will be rejected at merge. This is the anti-fabrication
  gate and it is not negotiable.
- **Never invent a person.** Name an individual only when a source URL shows they hold
  that role now. Otherwise give the role ("Head of Supply Chain"). A wrong name burns
  the one cold email you get.
- **No dates in the past.** Today is {today}. A conference row must name a future
  edition; if the 2026 edition has passed, give the 2027 one.
- **Pain must be specific.** "Wants to be more data-driven" is worthless. "Expanding
  past 1.2M litres and needs to hold house character" is a row worth having.
- **One wedge per row.** If two fit, pick the one they would pay for first.
- **Skip anything already on the list below.** Re-finding a known target wastes the
  merge gate's time and yours.

## Output

Write a JSON array to `{out_path}`. No prose, no markdown fence, just the array.
Your final message: the count and a one-line list of company names. Do not paste the JSON."""


def render_brief(surface: dict, rows: list[dict], out_dir: Path, today: str) -> str:
    regions = surface["regions"]
    # A "Global" surface has no region to filter on, so it must scope by tier
    # instead. Without this it claims every row in the list, and its re-verify
    # section duplicates work that the regional agents are already doing.
    tiers = surface.get("tiers")
    # Two surfaces can share a region (North America is split beer/spirits vs
    # wine), so vertical narrows ownership. Without it both briefs claim the
    # same rows and two agents re-verify the same targets.
    verticals = surface.get("verticals")

    def owned(r):
        if tiers and r.get("tier") not in tiers:
            return False
        if verticals and r.get("vertical") not in verticals:
            return False
        return "Global" in regions or r["region"] in regions

    scoped = [r for r in rows if owned(r)]
    known = sorted({r["company"] for r in scoped})
    g = compute(rows, regions=None)

    reverify = [r for r in scoped if r.get("tier", 9) <= 2 and not r.get("source_urls")]

    out_path = f".prospects/finds/{surface['id']}.json"
    parts = [
        f"# Prospect brief: {surface['title']}",
        "",
        f"Generated {today}. Regions in scope: {', '.join(regions)}.",
        "",
        "## What you are looking for",
        "",
        "Organisations to PITCH AI, data and analytics services to across beer, whisky",
        "and wine. These are potential CUSTOMERS and CHANNEL PARTNERS, not companies that",
        "sell beverage AI themselves. If a company's business IS selling AI to drinks",
        "producers, it belongs on the public vendor radar, not here, unless you are",
        "listing it explicitly as a partner or incumbent to work with.",
        "",
        f"### Scope\n\n{surface['scope']}",
        "",
        f"## Tiers\n\n```\n{TIER_RULES}\n```",
        "",
        f"## Wedge menu (pick exactly one per row)\n\n```\n{WEDGE_MENU}\n```",
        "",
        f"## Row schema\n\n```json\n{SCHEMA_BLOCK}\n```",
        "",
        RULES.format(today=today, out_path=out_path),
        "",
        "## Current coverage gaps (whole list)",
        "",
        "```",
        format_gaps(g),
        "```",
        "",
        f"## Already tracked in your regions ({len(known)}) - do not return these again",
        "",
    ]
    parts += [f"- {n}" for n in known] or ["(nothing yet: this surface is empty)"]

    if reverify:
        parts += [
            "",
            f"## Re-verify these {len(reverify)} existing tier 1-2 rows",
            "",
            "They were written without sources. Return each one again as a full row WITH",
            "source_urls, correcting anything that is now wrong (people move, capacity",
            "changes). If you cannot source one, say so in your final message and leave",
            "it out rather than inventing a citation.",
            "",
        ]
        parts += [f"- {r['company']} — currently: {r.get('entry', '')[:80]}" for r in reverify]

    text = "\n".join(parts) + "\n"
    path = out_dir / f"{surface['id']}.md"
    path.write_text(text)
    return str(path)


def render_briefs(surfaces: list[dict], rows: list[dict], root: Path, today: str = None) -> list[str]:
    today = today or date.today().isoformat()
    out_dir = root / ".prospects" / "briefs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (root / ".prospects" / "finds").mkdir(parents=True, exist_ok=True)
    return [render_brief(s, rows, out_dir, today) for s in surfaces]


def load_surfaces(path: Path) -> list[dict]:
    return json.loads(Path(path).read_text())
