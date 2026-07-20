from __future__ import annotations
from datetime import date
from typing import Callable
from radar.config import DISCOVERY_QUERIES, RECENCY_YEARS
from radar.classify import classify
from radar.model import Company


class WebSearchSource:
    name = "web_search"
    kind = "discovery"

    def __init__(
        self,
        search_fn: Callable[[str], list[dict]],
        queries: list[str] | None = None,
        today: date | None = None,
    ):
        self.search_fn = search_fn
        self.queries = queries or DISCOVERY_QUERIES
        self.today = today or date.today()

    def discover(self, fetcher) -> list[Company]:
        cutoff = self.today.replace(year=self.today.year - RECENCY_YEARS)
        out: dict[str, Company] = {}
        for query in self.queries:
            for r in self.search_fn(query):
                seen = date.fromisoformat(r["date"])
                if seen < cutoff:
                    continue
                text = f"{r['title']} {r['snippet']}"
                tags = classify(text)
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
                out[c.key] = c  # de-dupe within the sweep
        return list(out.values())


def default_search_fn(query: str) -> list[dict]:
    """Adapter over the existing web-search engine. Returns title/url/snippet/date dicts."""
    raise NotImplementedError("wire to the reused search engine during integration")
