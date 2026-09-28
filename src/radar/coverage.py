"""Coverage across all four lanes (companies, people, jobs, prospects feed off
these three), so a sweep targets what is missing instead of what search returns.

The lanes used to be islands: a company found by the company scout never led to
its people, and a person's employer never got checked as a company. The
frontier here is that cross-feed. Pure functions, no network: this decides what
to look for, the agents decide what is out there.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from radar.geo import country_of
from radar.scout.merge import norm_name

# Shorter names match half the internet ("Vin", "Oak"); same floor as the jobs lane.
MIN_MATCH_CHARS = 5


def _same_employer(a: str, b: str) -> bool:
    a, b = norm_name(a), norm_name(b)
    if not a or not b:
        return False
    short, long_ = sorted((a, b), key=len)
    # whole-word containment: "brauerei a" matches "brauerei a gmbh", "vin" never matches "vinicola"
    return short == long_ or (len(short) >= MIN_MATCH_CHARS and f" {short} " in f" {long_} ")


def _tracked_match(employer: str, tracked: list[str]) -> bool:
    return any(_same_employer(employer, t) for t in tracked)


def frontier(companies: list[dict], people: list[dict], jobs: list[dict]) -> dict:
    """What the lanes know about each other but have not followed up.

    companies_without_people: tracked companies with no named person anywhere,
    queue for a people sweep. untracked_employers: employers named by a tracked
    person or an open job that the company seed does not hold, queue for a
    company check. Evidence rides along so a brief can cite why each is listed.
    """
    orgs = [c for c in companies if c.get("company_type") != "individual"]
    # aliases: the name an org trades under when the seed holds its legal name
    names = [n for c in orgs for n in [c["name"], *(c.get("aliases") or [])]]
    employers = [p.get("company") or "" for p in people]

    without = [
        c["name"]
        for c in orgs
        if not c.get("people")
        and not c.get("key_people")
        and not any(_same_employer(e, c["name"]) for e in employers)
    ]

    untracked: dict[str, dict] = {}
    for p in people:
        emp = p.get("company")
        if emp and not _tracked_match(emp, names):
            row = untracked.setdefault(norm_name(emp), {"name": emp, "evidence": []})
            row["evidence"].append(f"employs {p['name']}")
    for j in jobs:
        emp = j.get("company")
        if emp and not _tracked_match(emp, names):
            row = untracked.setdefault(norm_name(emp), {"name": emp, "evidence": []})
            row["evidence"].append(f"hiring: {j.get('title')} {j.get('url') or ''}".strip())

    return {
        "companies_without_people": sorted(without),
        "untracked_employers": sorted(
            untracked.values(), key=lambda r: (-len(r["evidence"]), r["name"])
        ),
    }


def country_grid(companies: list[dict], people: list[dict], jobs: list[dict]) -> dict:
    """country -> counts per lane. thin = companies tracked there but no people or no jobs."""
    grid: dict[str, dict] = defaultdict(lambda: {"companies": 0, "people": 0, "jobs": 0})
    for c in companies:
        if c.get("company_type") != "individual":
            grid[country_of(c.get("hq_location")) or "unknown"]["companies"] += 1
    for p in people:
        grid[country_of(p.get("location")) or "unknown"]["people"] += 1
    for j in jobs:
        grid[j.get("country") or "unknown"]["jobs"] += 1
    return {
        k: {**v, "thin": v["companies"] > 0 and (v["people"] == 0 or v["jobs"] == 0)}
        for k, v in grid.items()
    }


def rotate_locations(
    base: list[str], extra: list[str], per_run: int, cursor: int
) -> tuple[list[str], int]:
    """Base locations every run, plus a rotating window over the rest.

    Same trick as the jobs company sweep: a bounded run that resumes where the
    last one stopped reaches every country without multiplying the run time.
    """
    extra = [e for e in extra if e not in base]
    if not extra:
        return list(base), 0
    start = cursor % len(extra)
    window = [extra[(start + i) % len(extra)] for i in range(min(per_run, len(extra)))]
    return list(base) + window, (start + len(window)) % len(extra)


def record_sweep(path: Path, lane: str, surface: str, found: int, added: int, today: str) -> None:
    rows = _rows(path)
    rows.append({"date": today, "lane": lane, "surface": surface, "found": found, "added": added})
    path.write_text(json.dumps(rows, indent=1) + "\n")


def last_sweeps(path: Path) -> dict:
    """(lane, surface) -> most recent ledger row."""
    return {(r["lane"], r["surface"]): r for r in _rows(path)}


def _rows(path: Path) -> list[dict]:
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else []


def recently_briefed(path: Path, today: str, days: int) -> set[str]:
    """Items handed to a frontier brief within `days`, so a company where the
    scouts find nobody does not sit at the head of the queue forever."""
    cutoff = date.fromisoformat(today).toordinal() - days
    return {
        item
        for r in _rows(path)
        if date.fromisoformat(r["date"]).toordinal() >= cutoff
        for item in r.get("items", [])
    }


def record_briefed(path: Path, lane: str, surface: str, items: list[str], today: str) -> None:
    rows = _rows(path)
    rows.append({"date": today, "lane": lane, "surface": surface, "items": items})
    path.write_text(json.dumps(rows, indent=1) + "\n")
