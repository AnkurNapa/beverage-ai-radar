import json

from radar.scout.liveness import check
from radar.scout.merge import load_finds, merge, norm_name

SEED = [{"name": "Tastry", "domain": "tastry.com"}]


def _co(name, domain="new.co", **over):
    c = {
        "name": name,
        "domain": domain,
        "vertical": "wine",
        "short_description": "does a thing",
        "source_urls": [f"https://{domain}/", "https://press.example.com/story"],
        "last_seen": "2026-07-26",
    }
    c.update(over)
    return c


def test_valid_company_is_added():
    seed, added, quarantined = merge(list(SEED), [_co("New Co")])
    assert [c["name"] for c in added] == ["New Co"]
    assert len(seed) == 2 and quarantined == []


def test_duplicate_by_name_and_by_domain():
    _, added, q = merge(list(SEED), [_co("tastry", "other.com"), _co("Other", "TASTRY.com")])
    assert added == []
    assert [x["state"] for x in q] == ["duplicate", "duplicate"]


def test_product_alias_is_a_near_duplicate():
    """Three scouts returned this company under three product names."""
    seed = [{"name": "Encompass Technologies", "domain": "encompasstech.com"}]
    _, added, q = merge(seed, [_co("Encompass Technologies (vintrace)", "vintrace.com")])
    assert added == []
    assert q[0]["state"] == "duplicate"


def test_missing_required_field_is_rejected():
    _, added, q = merge(list(SEED), [{"name": "Thin", "vertical": "beer"}])
    assert added == []
    assert "missing required fields" in q[0]["reason"]


def test_sources_must_include_the_companys_own_domain():
    """The strongest anti-hallucination gate."""
    bad = _co("Ghost Co", source_urls=["https://blog.example.com/a", "https://news.example.com/b"])
    _, added, q = merge(list(SEED), [bad])
    assert added == []
    assert "own domain" in q[0]["reason"]


def test_single_source_is_rejected():
    _, added, q = merge(list(SEED), [_co("Lonely", source_urls=["https://new.co/"])])
    assert added == [] and q[0]["state"] == "rejected"


def test_blocked_domain_is_quarantined_not_rejected():
    """403 means we could not check, not that the company is fake."""
    _, added, q = merge(list(SEED), [_co("Oculyze", "oculyze.com")], reachable=lambda d: None)
    assert added == []
    assert q[0]["state"] == "blocked" and "browser" in q[0]["reason"]


def test_dead_domain_is_rejected():
    _, added, q = merge(list(SEED), [_co("Gone", "gone.com")], reachable=lambda d: False)
    assert added == [] and q[0]["state"] == "rejected"


def test_duplicates_within_one_batch():
    _, added, q = merge(list(SEED), [_co("Twin", "a.com"), _co("Twin", "b.com")])
    assert len(added) == 1 and len(q) == 1


def test_load_finds_tags_provenance(tmp_path):
    p = tmp_path / "find_whiskey.json"
    p.write_text(json.dumps({"surface": "whiskey", "companies": [_co("Cask AI")]}))
    got = load_finds([p])
    assert got[0]["discovered_by"] == "scout:whiskey"
    assert got[0]["verified"] is False


def test_load_finds_accepts_a_bare_array(tmp_path):
    """The first hand-run sweep produced bare arrays; keep reading them."""
    p = tmp_path / "find_beer.json"
    p.write_text(json.dumps([_co("Hop AI")]))
    assert load_finds([p])[0]["discovered_by"] == "scout:beer"


def test_norm_name_strips_alias_and_punctuation():
    assert norm_name("Andavi Solutions (GreatVines)") == "andavi solutions"


def test_liveness_states():
    assert check("x.com", get=lambda u: 200) is True
    assert check("x.com", get=lambda u: 403) is None
    assert check("x.com", get=lambda u: 404) is False
    assert check("", get=lambda u: 200) is False
