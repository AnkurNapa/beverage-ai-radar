from datetime import date

from radar.model import BeverageVertical, Company
from radar.scout.gaps import find_gaps


def _c(name, vertical=None, use_case=None, hq=None, last_seen=date(2026, 7, 1)):
    return Company(
        name=name,
        domain=f"{name.lower()}.com",
        vertical=vertical,
        ai_use_case=use_case,
        hq_location=hq,
        last_seen=last_seen,
        first_seen=last_seen,
    )


def _skewed(n_beer=30):
    """A corpus shaped like the real seed: beer and multiple heavy, whiskey thin."""
    companies = [
        _c(f"Beer{i}", BeverageVertical.BEER, "demand forecasting", "Austin, United States")
        for i in range(n_beer)
    ]
    companies += [
        _c(f"Multi{i}", BeverageVertical.MULTIPLE, "quality control", "Austin, United States")
        for i in range(n_beer)
    ]
    companies += [
        _c(f"Wine{i}", BeverageVertical.WINE, "vineyard yield", "Bordeaux, France")
        for i in range(20)
    ]
    companies += [_c("Whisky1", BeverageVertical.WHISKEY, "sensory", "Speyside, Scotland")]
    return companies


def test_thinnest_vertical_ranks_first():
    gaps = find_gaps(_skewed(), date(2026, 7, 26))
    verticals = [g for g in gaps if g["axis"] == "vertical"]
    assert verticals[0]["value"] == "whiskey"
    assert verticals[0]["count"] == 1


def test_well_covered_slice_is_not_a_gap():
    gaps = find_gaps(_skewed(), date(2026, 7, 26))
    assert not [g for g in gaps if g["axis"] == "vertical" and g["value"] == "beer"]


def test_empty_corpus_returns_no_gaps():
    assert find_gaps([], date(2026, 7, 26)) == []


def test_aging_evidence_is_reported_before_it_goes_dormant():
    companies = _skewed()
    companies.append(_c("Fading", BeverageVertical.BEER, "sensory", "x, France", date(2025, 6, 1)))
    gaps = find_gaps(companies, date(2026, 7, 26))
    stale = [g for g in gaps if g["axis"] == "staleness"]
    assert stale and "Fading" in stale[0]["examples"]


def test_open_ended_country_axis_cannot_crowd_out_the_rest():
    """Without a cap, a dozen one-company countries fill every slot."""
    companies = _skewed()
    for i in range(15):
        companies.append(_c(f"Solo{i}", BeverageVertical.BEER, "sensory", f"City, Country{i}"))
    gaps = find_gaps(companies, date(2026, 7, 26), top_n=8)
    countries = [g for g in gaps if g["axis"] == "country"]
    assert len(countries) < len(gaps), "country axis monopolised the gap list"


def test_gap_reason_is_human_readable():
    gaps = find_gaps(_skewed(), date(2026, 7, 26))
    assert all(g["reason"] and g["count"] is not None for g in gaps)
