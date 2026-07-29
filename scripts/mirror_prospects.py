#!/usr/bin/env python3
"""Mirror the private prospect list into the Obsidian vault.

dashboard/prospects.json is gitignored so the buyer list never reaches the
public repo, which is correct and also means it has no backup: one file, one
machine, no history. The vault syncs, so a copy there survives this laptop.

Writes two files, because they answer different questions:

  prospects.json  an exact copy, so a restore is a straight file copy back.
  Prospects.md    a readable table, so the list is searchable in Obsidian and
                  usable on a phone away from the dashboard.

Safe to run repeatedly: both files are overwritten, and the vault is not a git
repository, so nothing here can leak into version control.

Run: python3 scripts/mirror_prospects.py
"""
from __future__ import annotations

import json
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "prospects.json"
VAULT = Path.home() / "Documents" / "obsidian" / "Beverage-AI Radar" / "_private"

TIER_LABEL = {
    1: "Best fit, will pay",
    2: "Corporate, long cycle",
    3: "Volume play",
    4: "Channel multiplier",
    5: "Adjacent buyer",
}


def markdown(rows: list[dict]) -> str:
    by_region = defaultdict(list)
    for r in rows:
        by_region[r["region"]].append(r)
    tiers = Counter(r["tier"] for r in rows)
    sourced = sum(1 for r in rows if r["tier"] <= 2 and r.get("source_urls"))
    gated = sum(1 for r in rows if r["tier"] <= 2)

    out = [
        "---",
        "type: project",
        "tags: [sales, outreach, prospects, private, beer, whisky, wine]",
        f"updated: {date.today().isoformat()}",
        "---",
        "",
        "# Prospects (private mirror)",
        "",
        "> [!warning] Private",
        "> Mirror of `dashboard/prospects.json`, which is gitignored and never",
        "> published. Do not paste this into anything public. The dashboard is",
        "> the working copy; this is the backup and the phone-readable version.",
        "",
        f"**{len(rows)} targets** across {len(by_region)} regions. "
        f"{sourced} of {gated} tier 1-2 rows carry sources.",
        "",
        "| Tier | Meaning | Count |",
        "|---|---|---|",
    ]
    for t in sorted(tiers):
        out.append(f"| {t} | {TIER_LABEL.get(t, '')} | {tiers[t]} |")
    out.append("")

    for region in sorted(by_region, key=lambda r: (-len(by_region[r]), r)):
        rs = sorted(by_region[region], key=lambda r: (r["tier"], r["company"]))
        out += [f"## {region} ({len(rs)})", "",
                "| T | Company | Segment | Pain | Wedge | Entry |",
                "|---|---|---|---|---|---|"]
        for r in rs:
            cells = [str(r["tier"]), r["company"], r.get("segment", ""),
                     r.get("pain", ""), r.get("wedge", ""), r.get("entry", "")]
            # A newline or a pipe inside a cell breaks the whole table row.
            cells = [c.replace("|", "\\|").replace("\n", " ") for c in cells]
            out.append("| " + " | ".join(cells) + " |")
        out.append("")
    return "\n".join(out) + "\n"


def main() -> int:
    if not SRC.exists():
        print(f"nothing to mirror: {SRC} does not exist")
        return 1
    rows = json.loads(SRC.read_text())
    VAULT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC, VAULT / "prospects.json")
    (VAULT / "Prospects.md").write_text(markdown(rows))
    print(f"mirrored {len(rows)} rows ->")
    for f in ("prospects.json", "Prospects.md"):
        p = VAULT / f
        print(f"  {p}  ({p.stat().st_size / 1024:.0f} kb)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
