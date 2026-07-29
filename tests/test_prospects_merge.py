import pytest

from radar.prospects.merge import GRANDFATHER_MAX_TIER, merge


def _p(company, region="North America", tier=1, **over):
    p = {
        "tier": tier,
        "company": company,
        "region": region,
        "vertical": "beer",
        "hq": "Somewhere, Country",
        "segment": "Craft",
        "pain": "They cannot see batch drift across sites.",
        "wedge": "Batch consistency",
        "entry": "Head brewer",
        "url": "https://example.com",
        "source_urls": ["https://example.com/about", "https://press.example.com/story"],
        "last_seen": "2026-07-29",
    }
    p.update(over)
    return p


SEED = [_p("Existing Co", tier=1)]


def test_valid_prospect_is_added():
    rows, added, q = merge(list(SEED), [_p("New Co")])
    assert [r["company"] for r in added] == ["New Co"]
    assert len(rows) == 2 and q == []


def test_duplicate_within_same_region_is_rejected():
    _, added, q = merge(list(SEED), [_p("existing co")])
    assert added == []
    assert q[0]["state"] == "duplicate"


def test_same_company_in_a_different_region_is_allowed():
    """Diageo is a real target in both UK and Africa; region is part of identity."""
    _, added, q = merge(list(SEED), [_p("Existing Co", region="Africa")])
    assert [r["company"] for r in added] == ["Existing Co"]
    assert q == []


def test_parenthetical_alias_is_a_near_duplicate():
    seed = [_p("Piccadily Agro Industries", region="India")]
    _, added, q = merge(seed, [_p("Piccadily Agro Industries (Indri)", region="India")])
    assert added == []
    assert q[0]["state"] == "duplicate"


def test_missing_required_field_is_rejected():
    _, added, q = merge(list(SEED), [{"company": "Thin", "region": "Japan", "tier": 1}])
    assert added == []
    assert "missing required fields" in q[0]["reason"]


def test_tier_1_needs_two_sources():
    _, added, q = merge(list(SEED), [_p("Thin Sourced", source_urls=["https://only.one/"])])
    assert added == []
    assert "two sources" in q[0]["reason"]


def test_tier_1_sources_must_include_the_claimed_domain():
    """The anti-hallucination check: a made-up target rarely cites its own site."""
    bad = _p("Elsewhere Co", url="https://elsewhere.com",
             source_urls=["https://blog.example.com/a", "https://news.example.com/b"])
    _, added, q = merge(list(SEED), [bad])
    assert added == []
    assert "domain" in q[0]["reason"]


@pytest.mark.parametrize("tier", [3, 4, 5])
def test_grandfathered_tiers_skip_the_source_gate(tier):
    """Option C: tiers 3-5 are curated judgement calls, not sourced claims."""
    assert tier > GRANDFATHER_MAX_TIER
    row = _p("Volume Chain", tier=tier, source_urls=[], url="")
    _, added, q = merge(list(SEED), [row])
    assert [r["company"] for r in added] == ["Volume Chain"]
    assert added[0]["discovered_by"] == "curated"
    assert q == []


@pytest.mark.parametrize("tier", [1, 2])
def test_ungrandfathered_tiers_are_gated(tier):
    row = _p("Named Target", tier=tier, source_urls=[])
    _, added, q = merge(list(SEED), [row])
    assert added == [] and q[0]["state"] == "rejected"


def test_named_person_without_a_source_is_rejected():
    """Emailing a person who left the job is the expensive failure. Cite or use a role."""
    row = _p("Person Co", entry="Jane Doe (CEO)", source_urls=["https://example.com/about"])
    _, added, q = merge(list(SEED), [row])
    assert added == []
    assert "two sources" in q[0]["reason"]


def test_bad_tier_is_rejected():
    _, added, q = merge(list(SEED), [_p("Weird", tier=9)])
    assert added == []
    assert "tier" in q[0]["reason"]


def test_incoming_batch_dedupes_against_itself():
    """Two agents covering adjacent surfaces both return the same company."""
    _, added, q = merge(list(SEED), [_p("Overlap Co"), _p("Overlap Co")])
    assert len(added) == 1
    assert q[0]["state"] == "duplicate"


def test_rejects_always_carry_a_reason():
    _, _, q = merge(list(SEED), [{"company": "X", "region": "Japan", "tier": 1}, _p("existing co")])
    assert all(x.get("reason") and x.get("state") for x in q)


# --- re-verification: a sourced row must UPDATE its unsourced predecessor ----
# Regression: the first real sweep returned 26 re-verified rows and the gate
# rejected every one as a duplicate, silently discarding corrections including
# "this company is in administration". Dedup must not eat re-verification.

def test_reverified_row_replaces_the_unsourced_original():
    seed = [_p("Ardnamurchan", region="UK & Ireland", source_urls=[], pain="old pain")]
    fresh = _p("Ardnamurchan", region="UK & Ireland", pain="new sourced pain",
               url="https://adelphidistillery.com",
               source_urls=["https://adelphidistillery.com/a", "https://press.com/b"])
    rows, added, q = merge(seed, [fresh])
    assert len(rows) == 1, "must replace, not append a second copy"
    assert rows[0]["pain"] == "new sourced pain"
    assert rows[0]["source_urls"]
    assert added == [] and [x["state"] for x in q] == ["updated"]


def test_reverification_can_change_tier_and_wedge():
    """Diageo moved wedge because it had already built what we were selling."""
    seed = [_p("Diageo", region="UK & Ireland", tier=1, wedge="Distillery process intelligence",
               source_urls=[])]
    fresh = _p("Diageo", region="UK & Ireland", tier=2, wedge="Batch consistency",
               url="https://diageo.com",
               source_urls=["https://diageo.com/x", "https://thedrinksbusiness.com/y"])
    rows, _, _ = merge(seed, [fresh])
    assert rows[0]["tier"] == 2 and rows[0]["wedge"] == "Batch consistency"


def test_an_already_sourced_row_is_left_alone():
    """Only unsourced rows are up for replacement; a second sweep must not churn."""
    seed = [_p("Sourced Co", source_urls=["https://example.com/a", "https://x.com/b"],
               pain="original")]
    rows, added, q = merge(seed, [_p("Sourced Co", pain="different")])
    assert rows[0]["pain"] == "original"
    assert added == [] and q[0]["state"] == "duplicate"


def test_unsourced_incoming_cannot_overwrite_anything():
    seed = [_p("Co", source_urls=[], pain="original")]
    rows, added, q = merge(seed, [_p("Co", tier=3, source_urls=[], pain="junk")])
    assert rows[0]["pain"] == "original"
    assert q[0]["state"] == "duplicate"


def test_reverification_works_through_a_near_duplicate_match():
    """The renamed-company case: the sweep returns the full legal name.

    'BrewDog plc' vs 'BrewDog', 'Heineken Beverages SA (Pty) Ltd' vs
    'Heineken Beverages (Distell + Namibia Breweries)'. These match fuzzily,
    not exactly, and the administration finding arrived on this path.
    """
    seed = [_p("BrewDog", region="UK & Ireland", source_urls=[], pain="old")]
    fresh = _p("BrewDog plc", region="UK & Ireland", pain="in administration",
               url="https://brewdog.com",
               source_urls=["https://brewdog.com/uk/", "https://brewdog.com/uk/about"])
    rows, added, q = merge(seed, [fresh])
    assert len(rows) == 1
    assert rows[0]["pain"] == "in administration"
    assert rows[0]["company"] == "BrewDog plc", "adopt the verified legal name"
    assert q[0]["state"] == "updated"
