from radar.wedge import DEMAND, OTHER, PROCESS, wedge_of


def test_variants_of_one_wedge_collapse_to_it():
    """Each sweep wrote the wedge in its own words; 288 rows held 80 strings."""
    for s in ["Demand forecasting",
              "Demand forecasting (SKU x region x month, calendar-aware)",
              "Demand forecasting with festival calendar awareness"]:
        assert wedge_of(s) == DEMAND


def test_first_match_wins_in_rule_order():
    assert wedge_of("Distillery process intelligence, then recipe") == PROCESS


def test_an_unactionable_wedge_is_not_forced_into_a_bucket():
    assert wedge_of("Subcontract the AI scope") == OTHER
    assert wedge_of(None) == OTHER
