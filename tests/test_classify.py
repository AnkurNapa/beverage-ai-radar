from radar.classify import classify
from radar.model import BeverageVertical, AIMaturity


def test_detects_beer_and_quality_use_case():
    r = classify("Our brewery uses computer vision for quality control on the canning line.")
    assert r["vertical"] == BeverageVertical.BEER
    assert r["ai_use_case"] == "quality control / computer vision"


def test_detects_wine_and_shipping_maturity():
    r = classify("This winery ships a GenAI marketing product to wineries today.")
    assert r["vertical"] == BeverageVertical.WINE
    assert r["ai_maturity"] == AIMaturity.SHIPPING


def test_multiple_verticals():
    r = classify("Platform serving breweries, distilleries, and wineries.")
    assert r["vertical"] == BeverageVertical.MULTIPLE
