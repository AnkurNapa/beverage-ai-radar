from radar.themes import OTHER, all_themes, theme_of


def test_first_matching_rule_wins():
    """Ordering is the whole design: specific rules must precede general ones."""
    # "market data" would also match the analytics catch-all in Process & operations.
    assert theme_of("rare whisky market data and valuation") == "Market data & valuation"
    # "vineyard" beats the generic "sensor" in Process & operations.
    assert theme_of("vineyard sensor disease prediction") == "Agriculture & crop"


def test_known_use_cases_bucket_sensibly():
    assert theme_of("recipe / flavor prediction") == "Sensory & recipe"
    assert theme_of("demand forecasting") == "Sales, demand & pricing"
    assert theme_of("compliance & licensing") == "Compliance & licensing"
    assert theme_of("process historian + predictive analytics") == "Process & operations"


def test_missing_use_case_falls_through():
    assert theme_of(None) == OTHER
    assert theme_of("") == OTHER


def test_other_is_offered_as_a_bucket():
    assert OTHER in all_themes()
    assert "Market data & valuation" in all_themes()


def test_esg_theme():
    assert theme_of("carbon footprint accounting for drinks producers") == "ESG & sustainability"
    assert theme_of("automated scope 3 emission factor matching") == "ESG & sustainability"
    assert theme_of("remote monitoring of brewery wastewater treatment") == "ESG & sustainability"
    assert theme_of("winery greenhouse gas inventory and carbon accounting") == "ESG & sustainability"


def test_engineering_theme():
    assert theme_of("mash filtration and brewhouse technology") == "Engineering & equipment"
    assert theme_of("automated still control and fraction data acquisition") == "Engineering & equipment"
    assert theme_of("connected winery press monitoring") == "Engineering & equipment"


def test_keg_and_route_are_supply_chain():
    assert theme_of("cellular smart keg trackers") == "Supply chain"
    assert theme_of("ai route optimisation for delivery fleets") == "Supply chain"
    assert theme_of("serialised bottle track and trace") == "Supply chain"


def test_retail_execution_is_sales():
    assert theme_of("shelf image recognition for retail execution") == "Sales, demand & pricing"
    assert theme_of("ai territory planning for beverage field teams") == "Sales, demand & pricing"


def test_overbroad_keywords_do_not_steal():
    # "historian delivery" must not read as logistics, and "drinks brands" must
    # not read as marketing. Both were real misfires when the rules were widened.
    assert theme_of("distillery engineering, automation and controls with historian delivery") == "Engineering & equipment"
    assert theme_of("retail bi dashboards and category management for drinks brands") == "Process & operations"
    # A quality product that merely mentions a sustainability report stays quality.
    assert theme_of("applied AI for quality anomaly detection and sustainability reporting") == "Quality & inspection"


def test_recommendation_needs_a_consumer_object():
    # A brewery digital twin makes "process recommendations". That is not
    # consumer personalization, and it filed Ziemann Holvrieka wrongly for months.
    assert theme_of("brewery digital twin with ai-supported process recommendations") == "Process & operations"
    assert theme_of("route-to-market sales force recommendations") == "Sales, demand & pricing"
    assert theme_of("dtc ecommerce inventory and purchase order recommendations") == "Supply chain"
    # Genuine consumer recommendation still lands where it should.
    assert theme_of("consumer taste profiling and wine recommendation") == "Sensory & recipe"
    assert theme_of("marketplace search and product recommendations") == "Consumer & personalization"
