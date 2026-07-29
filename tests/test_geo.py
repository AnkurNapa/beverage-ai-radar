from radar.geo import UNKNOWN, country_of, normalise


def test_usa_and_united_states_collapse():
    """They were two entries in the country filter, each with half the count."""
    assert normalise("USA") == normalise("United States") == "United States"


def test_uk_constituent_countries_collapse():
    for n in ("Scotland", "England", "UK", "Great Britain"):
        assert normalise(n) == "United Kingdom"


def test_country_is_the_last_component_of_hq_location():
    assert country_of("San Luis Obispo, United States") == "United States"
    assert country_of("Bengaluru, India") == "India"


def test_alias_applies_after_splitting():
    assert country_of("Louisville, USA") == "United States"


def test_blank_is_unknown_not_empty_string():
    assert country_of(None) == country_of("") == UNKNOWN


def test_unrecognised_country_passes_through_unchanged():
    """Do not silently rewrite something just because it is not in the map."""
    assert normalise("Sri Lanka") == "Sri Lanka"
