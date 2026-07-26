"""Merge scout JSON files into data/seed.json.

Each scout writes a JSON array of seed-shaped objects to a find_*.json file.
This appends the ones that are new, keyed on normalized name and on domain, so
re-running a sweep never duplicates a company.

Usage: python3 scripts/merge_finds.py <find_*.json> [...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SEED = Path(__file__).resolve().parent.parent / "data" / "seed.json"
REQUIRED = ("name", "vertical", "short_description", "source_urls", "last_seen")


def norm(s: str | None) -> str:
    return (s or "").strip().lower().removeprefix("www.")


def merge(seed: list[dict], incoming: list[dict]) -> tuple[list[dict], list[str], list[str]]:
    names = {norm(c["name"]) for c in seed}
    domains = {norm(c.get("domain")) for c in seed if c.get("domain")}
    added, skipped = [], []
    for c in incoming:
        missing = [f for f in REQUIRED if not c.get(f)]
        if missing:
            skipped.append(f"{c.get('name', '?')} (missing {', '.join(missing)})")
            continue
        if norm(c["name"]) in names or (c.get("domain") and norm(c["domain"]) in domains):
            skipped.append(f"{c['name']} (duplicate)")
            continue
        names.add(norm(c["name"]))
        if c.get("domain"):
            domains.add(norm(c["domain"]))
        seed.append(c)
        added.append(c["name"])
    return seed, added, skipped


def main(paths: list[str]) -> None:
    seed = json.loads(SEED.read_text())
    incoming = [c for p in paths for c in json.loads(Path(p).read_text())]
    seed, added, skipped = merge(seed, incoming)

    keys = [norm(c["name"]) for c in seed]
    assert len(keys) == len(set(keys)), "duplicate names in merged seed"

    SEED.write_text(json.dumps(seed, indent=2, ensure_ascii=False) + "\n")
    print(f"added {len(added)}: {', '.join(added)}")
    print(f"skipped {len(skipped)}: {'; '.join(skipped)}")
    print(f"seed now {len(seed)}")


def _self_check() -> None:
    seed = [{"name": "Tastry", "domain": "tastry.com"}]
    base = {"vertical": "wine", "short_description": "x", "source_urls": ["u"], "last_seen": "2026-01-01"}
    out, added, skipped = merge(
        list(seed),
        [
            {"name": "tastry", **base},                              # dup by name
            {"name": "Other", "domain": "TASTRY.com", **base},        # dup by domain
            {"name": "New Co", "domain": "new.co", **base},           # added
            {"name": "New Co", "domain": "new2.co", **base},          # dup within batch
            {"name": "Thin", "vertical": "beer"},                     # missing fields
        ],
    )
    assert added == ["New Co"], added
    assert len(skipped) == 4, skipped
    assert len(out) == 2, out
    print("self-check ok")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--self-check"]:
        _self_check()
    else:
        main(sys.argv[1:])
