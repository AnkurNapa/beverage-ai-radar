from radar.scope import HORIZONTAL, NATIVE, scope_of


def test_a_brewing_product_is_native():
    assert scope_of({"name": "Tastry", "short_description": "predicts how wines perform"}) == NATIVE


def test_a_generic_manufacturing_platform_is_horizontal():
    """FuturMaster sells supply-chain planning into many industries."""
    c = {"name": "FuturMaster", "ai_use_case": "supply chain planning with AI forecasting",
         "short_description": "A supply chain planning software vendor."}
    assert scope_of(c) == HORIZONTAL


def test_a_big_drinks_group_is_native_even_without_a_product_noun():
    """'Carlsberg' carries no beverage word; the brand name has to count."""
    c = {"name": "Carlsberg India", "ai_use_case": "AI-driven pricing", "short_description": "IT centre."}
    assert scope_of(c) == NATIVE


def test_compliance_for_alcohol_is_native():
    c = {"name": "Alcohol Compliance Company", "ai_use_case": "compliance & licensing",
         "short_description": "licensing and permits"}
    assert scope_of(c) == NATIVE
