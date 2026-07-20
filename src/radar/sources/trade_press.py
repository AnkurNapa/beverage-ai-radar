from __future__ import annotations
from datetime import date
from typing import Callable
from radar.config import RECENCY_YEARS
from radar.classify import classify
from radar.model import Company

DEFAULT_FEEDS: list[str] = [
    # Fill real trade-press listing URLs during integration (Task 12).
]


class TradePressSource:
    name = "trade_press"
    kind = "discovery"

    def __init__(
        self, feed_urls: list[str], parse_fn: Callable[[str], list[dict]], today: date | None = None
    ):
        self.feed_urls = feed_urls
        self.parse_fn = parse_fn
        self.today = today or date.today()

    def discover(self, fetcher) -> list[Company]:
        cutoff = self.today.replace(year=self.today.year - RECENCY_YEARS)
        out: dict[str, Company] = {}
        for url in self.feed_urls:
            html = fetcher.fetch(url)
            for r in self.parse_fn(html):
                seen = date.fromisoformat(r["date"])
                if seen < cutoff:
                    continue
                tags = classify(f"{r['title']} {r['snippet']}")
                c = Company(
                    name=r["title"],
                    domain=r["url"],
                    short_description=r["snippet"],
                    source_urls=[r["url"]],
                    first_seen=seen,
                    last_seen=seen,
                    latest_news_headline=r["title"],
                    **tags,
                )
                out[c.key] = c
        return list(out.values())
