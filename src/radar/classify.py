from __future__ import annotations
from radar.model import BeverageVertical, AIMaturity

_VERTICAL_TERMS = {
    BeverageVertical.BEER: ["brewery", "brewing", "beer", "brewer"],
    BeverageVertical.WHISKEY: ["distillery", "distilling", "whiskey", "whisky", "spirits"],
    BeverageVertical.WINE: ["winery", "winemaking", "wine", "vineyard"],
    BeverageVertical.NON_ALCOHOLIC: [
        "soft drink",
        "soda",
        "carbonated",
        "juice",
        "bottled water",
        "energy drink",
        "sports drink",
        "non-alcoholic",
        "nonalcoholic",
    ],
    BeverageVertical.FOOD: [
        "food processing",
        "food manufacturing",
        "food and beverage",
        "dairy",
        "bakery",
        "confectionery",
        "snack",
        "agrifood",
    ],
}

_USE_CASES = [
    (
        "quality control / computer vision",
        ["computer vision", "quality control", "defect", "inspection"],
    ),
    ("recipe / flavor prediction", ["flavor", "recipe", "aroma", "taste prediction"]),
    ("demand forecasting", ["demand forecast", "forecasting", "inventory"]),
    ("sensory", ["sensory", "tasting panel"]),
    ("supply chain", ["supply chain", "logistics"]),
    (
        "GenAI marketing",
        ["genai marketing", "generative ai marketing", "content generation", "marketing product"],
    ),
]

_MATURITY = [
    (AIMaturity.SHIPPING, ["ships", "shipping", "launched", "in production", "customers use"]),
    (AIMaturity.PILOT, ["pilot", "beta", "trial", "proof of concept", "poc"]),
    (AIMaturity.RESEARCH, ["research", "prototype", "exploring", "r&d"]),
]


def classify(text: str) -> dict:
    t = text.lower()
    matched = [v for v, terms in _VERTICAL_TERMS.items() if any(term in t for term in terms)]
    if len(matched) > 1:
        vertical = BeverageVertical.MULTIPLE
    elif matched:
        vertical = matched[0]
    else:
        vertical = None

    use_case = next(
        (label for label, terms in _USE_CASES if any(term in t for term in terms)), None
    )
    maturity = next((m for m, terms in _MATURITY if any(term in t for term in terms)), None)
    return {"vertical": vertical, "ai_use_case": use_case, "ai_maturity": maturity}
