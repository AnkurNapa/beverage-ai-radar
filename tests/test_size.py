from radar.size import (LARGE, MICRO, MID, MULTINATIONAL, SMALL, UNKNOWN,
                        raised_usd_millions, size_of)


def c(**kw):
    base = {"name": "X", "short_description": "", "company_type": "", "funding_stage": ""}
    base.update(kw)
    return base


def test_a_named_group_is_multinational_by_fact_not_by_adjective():
    assert size_of(c(name="Diageo")) == MULTINATIONAL
    assert size_of(c(name="Krones AG")) == MULTINATIONAL


def test_an_individual_is_micro():
    assert size_of(c(company_type="individual")) == MICRO


def test_funding_amount_beats_stage_when_both_are_present():
    """A stage label is vaguer than a number."""
    assert size_of(c(total_raised="$120M", funding_stage="seed")) == LARGE


def test_money_parses_across_units_and_currencies():
    assert raised_usd_millions("$12.4M") == 12.4
    assert raised_usd_millions("EUR 960K") == 0.96
    assert raised_usd_millions("$1.2B") == 1200
    assert raised_usd_millions(None) is None
    assert raised_usd_millions("undisclosed") is None


def test_stages_map_to_bands():
    assert size_of(c(funding_stage="Series A")) == MID
    assert size_of(c(funding_stage="Series C")) == LARGE
    assert size_of(c(funding_stage="Seed")) == SMALL
    assert size_of(c(funding_stage="public")) == LARGE


def test_nothing_to_go_on_returns_unknown_rather_than_a_guess():
    """A wrong size invites a reader to skip a company for an invented reason."""
    assert size_of(c(name="Some Co", short_description="Builds software.")) == UNKNOWN


def test_global_ambition_language_does_not_make_a_startup_multinational():
    assert size_of(c(short_description="Our goal is to go global.")) == UNKNOWN
