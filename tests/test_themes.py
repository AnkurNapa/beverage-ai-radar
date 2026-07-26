from radar.themes import OTHER, all_themes, theme_of


def test_first_matching_rule_wins():
    """Ordering is the whole design: specific rules must precede general ones."""
    # "market data" would also match the analytics catch-all in Process & operations.
    assert theme_of("rare whisky market data and valuation") == "Market data & valuation"
    # "vineyard" beats the generic "sensor" in Process & operations.
    assert theme_of("vineyard sensor disease prediction") == "Agriculture & crop"


def test_known_use_cases_bucket_sensibly():
    assert theme_of("recipe / flavor prediction") == "Sensory & recipe"
    assert theme_of("demand forecasting") == "Demand & pricing"
    assert theme_of("compliance & licensing") == "Compliance & licensing"
    assert theme_of("process historian + predictive analytics") == "Process & operations"


def test_missing_use_case_falls_through():
    assert theme_of(None) == OTHER
    assert theme_of("") == OTHER


def test_other_is_offered_as_a_bucket():
    assert OTHER in all_themes()
    assert "Market data & valuation" in all_themes()
