from radar.region import region_of


def test_countries_map_to_the_same_regions_the_prospects_use():
    assert region_of("United States") == "North America"
    assert region_of("Sweden") == "Nordics"
    assert region_of("India") == "India"


def test_an_unmapped_country_returns_empty_not_a_catch_all():
    """A wrong region is worse than none; empty simply drops out of filters."""
    assert region_of("Atlantis") == ""
    assert region_of(None) == ""
