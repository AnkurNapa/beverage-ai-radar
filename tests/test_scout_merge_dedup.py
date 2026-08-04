"""Regression tests for the two dedup bugs found in the 2026-08-04 sweep.

Both silently discarded real companies as "duplicates", which is the worst
failure mode this database has: the quarantine file made them visible, but
nothing in the pipeline flagged that the reason was wrong.
"""

from radar.scout.merge import _near_duplicate, merge, norm_domain


def _row(name, domain):
    return {
        "name": name,
        "domain": domain,
        "vertical": "beer",
        "short_description": "x",
        "source_urls": [f"https://{domain}/", "https://example.org/a"],
        "last_seen": "2026-08-04",
    }


def test_two_label_public_suffix_is_not_the_registrable_domain():
    # The bug: both collapsed to "co.uk" and collided.
    assert norm_domain("https://kegtracker.co.uk/") == "kegtracker.co.uk"
    assert norm_domain("https://node4.co.uk/") == "node4.co.uk"
    assert norm_domain("https://bioscout.com.au/") == "bioscout.com.au"
    assert norm_domain("kegtracker.co.uk") != norm_domain("node4.co.uk")
    # Ordinary domains must keep behaving.
    assert norm_domain("https://www.crafted-erp.com/x") == "crafted-erp.com"
    assert norm_domain("https://sub.example.com/") == "example.com"


def test_short_substring_is_not_a_near_duplicate():
    # "ies" sat inside "international wineries for climate action".
    assert _near_duplicate("International Wineries for Climate Action", ["ies"]) is None
    # "istill" sat inside "circumstance distillery".
    assert _near_duplicate("iStill", ["circumstance distillery"]) is None


def test_real_near_duplicates_still_collapse():
    assert _near_duplicate("Crafted ERP", ["crafted erp"]) == "crafted erp"
    # Long names that genuinely contain each other still match.
    assert _near_duplicate(
        "Encompass Technologies", ["encompass technologies inc"]
    ) is not None


def test_similar_names_on_different_domains_are_different_companies():
    """FermentIQ vs Fermentis: 0.89 name similarity, unrelated firms."""
    seed = [_row("Fermentis", "fermentis.com")]
    _, added, quarantined = merge(seed, [_row("FermentIQ", "ferment-iq.com")])
    assert [c["name"] for c in added] == ["FermentIQ"], quarantined


def test_same_company_twice_still_deduplicates():
    seed = [_row("Fermentis", "fermentis.com")]
    _, added, quarantined = merge(seed, [_row("Fermentis", "fermentis.com")])
    assert added == []
    assert quarantined and quarantined[0]["state"] == "duplicate"


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
        print("ok", fn.__name__)
