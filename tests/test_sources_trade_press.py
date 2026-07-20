from pathlib import Path
from datetime import date
from radar.sources.trade_press import TradePressSource
from radar.model import BeverageVertical

HTML = (Path(__file__).parent / "fixtures/trade_page.html").read_text()


def parse_fn(html):
    # trivial fixture parser for the test
    return [{"title": "CaskML brings machine learning to whiskey distilling",
             "url": "https://caskml.com",
             "snippet": "machine learning to whiskey distilling",
             "date": "2025-11-02"}]


class StubFetcher:
    def fetch(self, url, ttl_hours=24):
        return HTML


def test_parses_feed_into_company():
    src = TradePressSource(feed_urls=["https://trade.example/list"],
                           parse_fn=parse_fn, today=date(2026, 7, 20))
    companies = src.discover(StubFetcher())
    c = companies[0]
    assert c.key == "caskml.com"
    assert c.vertical == BeverageVertical.WHISKEY
