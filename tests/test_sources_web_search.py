import json
from pathlib import Path
from datetime import date
from radar.sources.web_search import WebSearchSource
from radar.model import BeverageVertical

FIX = json.loads((Path(__file__).parent / "fixtures/search_results.json").read_text())


def test_converts_recent_results_and_drops_stale():
    src = WebSearchSource(search_fn=lambda q: FIX, today=date(2026, 7, 20))
    companies = src.discover(fetcher=None)
    keys = {c.key for c in companies}
    assert "brewbrain.ai" in keys
    assert "oldwine.com" not in keys  # 2012 is older than 10 years
    bb = next(c for c in companies if c.key == "brewbrain.ai")
    assert bb.vertical == BeverageVertical.BEER
    assert "https://brewbrain.ai/news" in bb.source_urls
