"""The curated seed must meet the same evidence bar the scout gate enforces.

The scout merge gate rejects a finding that lacks two sources with one on its
own domain, and calls that "the single strongest anti-hallucination check".
Nothing applied that check to the curated lane, so hand-added rows bypassed it
and 42 entries sit in the seed marked verified=true on a single self-published
source. The check that defines this database's value did not apply to the lane
a human uses.

Ratchet, not a wall: the existing 42 are recorded in
tests/seed_integrity_baseline.json and tolerated, but a NEW under-sourced entry
fails. Fixing one means deleting its line from the baseline, so the number can
only go down.
"""

import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEED = json.loads((ROOT / "data" / "seed.json").read_text())
PEOPLE = json.loads((ROOT / "data" / "people_seed.json").read_text())
BASELINE = set(json.loads((ROOT / "tests" / "seed_integrity_baseline.json").read_text()))

REQUIRED = ("name", "short_description", "vertical", "source_urls", "last_seen")


def _host(url: str) -> str:
    return (urlparse(url).netloc or "").lower().replace("www.", "")


def _cites_own_domain(row: dict) -> bool:
    domain = (row.get("domain") or "").lower().replace("www.", "")
    if not domain:
        return True  # nothing to check against
    return any(domain in _host(u) for u in (row.get("source_urls") or []))


def _under_sourced(row: dict) -> bool:
    return len(row.get("source_urls") or []) < 2 or not _cites_own_domain(row)


def test_no_new_under_sourced_entries():
    offenders = {r["name"] for r in SEED if _under_sourced(r)}
    new = offenders - BASELINE
    assert not new, (
        f"{len(new)} new entries lack two sources with one on their own domain: "
        f"{sorted(new)}. That is the check the scout gate calls the strongest "
        "anti-hallucination test; the curated lane must meet it too."
    )


def test_baseline_only_shrinks():
    """A fixed entry must be removed from the baseline, so it cannot regress."""
    offenders = {r["name"] for r in SEED if _under_sourced(r)}
    stale = BASELINE - offenders - {r["name"] for r in SEED} - {
        p["name"] for p in PEOPLE
    }
    assert not stale, (
        f"baseline lists entries that no longer exist: {sorted(stale)}. "
        "Delete them so the ratchet stays honest."
    )


@pytest.mark.parametrize("field", REQUIRED)
def test_every_company_carries_the_required_field(field):
    missing = [r.get("name", "?") for r in SEED if not r.get(field)]
    assert not missing, f"{len(missing)} companies missing {field}: {missing[:5]}"


def test_no_duplicate_names_or_domains():
    names = [r["name"].strip().lower() for r in SEED]
    domains = [(r.get("domain") or "").lower() for r in SEED if r.get("domain")]
    dupe_names = {n for n in names if names.count(n) > 1}
    dupe_domains = {d for d in domains if domains.count(d) > 1}
    assert not dupe_names, f"duplicate names: {sorted(dupe_names)}"
    assert not dupe_domains, f"duplicate domains: {sorted(dupe_domains)}"


def test_people_never_assert_an_unevidenced_current_employer():
    """company_is_current=False prints "(former)" against a real person's name.

    It may only be set where the record actually evidences a former role;
    anything merely unconfirmed must be null.
    """
    wrong = [
        p["name"] for p in PEOPLE
        if p.get("company_is_current") is False
        and "former" not in (p.get("role") or "").lower()
        and "ex-" not in (p.get("role") or "").lower()
    ]
    assert not wrong, (
        f"marked former without evidence in the role: {wrong}. "
        "Use null for unconfirmed, not False."
    )


def test_people_linkedin_ids_match_their_urls():
    """A wrong slug points at a different real human."""
    for p in PEOPLE:
        url, slug = p.get("linkedin"), p.get("linkedin_id")
        if not slug:
            continue
        assert url and slug in url, f"{p['name']}: linkedin_id {slug!r} not in {url!r}"
