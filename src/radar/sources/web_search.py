from __future__ import annotations
from datetime import date
from html.parser import HTMLParser
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


class _DDGParser(HTMLParser):
    """Pull (title, url, snippet) triples from a DuckDuckGo HTML results page."""

    def __init__(self):
        super().__init__()
        self.results: list[dict] = []
        self._in_title = False
        self._in_snippet = False
        self._cur = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        if tag == "a" and "result__a" in cls:
            self._cur = {"title": "", "url": a.get("href", ""), "snippet": ""}
            self._in_title = True
        elif tag == "a" and "result__snippet" in cls:
            self._in_snippet = True

    def handle_endtag(self, tag):
        if tag == "a" and self._in_title:
            self._in_title = False
            if self._cur:
                self.results.append(self._cur)
        elif tag == "a" and self._in_snippet:
            self._in_snippet = False

    def handle_data(self, data):
        if self._in_title and self._cur is not None:
            self._cur["title"] += data
        elif self._in_snippet and self.results:
            self.results[-1]["snippet"] += data


def default_search_fn(query: str, today: date | None = None) -> list[dict]:
    """Best-effort keyless web search via the DuckDuckGo HTML endpoint.

    Returns {title,url,snippet,date} dicts. Web results rarely carry a
    reliable publish date, so date defaults to today (the recency filter
    then treats them as current evidence). Any network/parse failure
    returns [] so the source isolation wrapper logs and continues.
    """
    import httpx

    today = today or date.today()
    try:
        resp = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            timeout=20,
            follow_redirects=True,
        )
        parser = _DDGParser()
        parser.feed(resp.text)
    except Exception:
        return []
    out = []
    for r in parser.results:
        url = r["url"].strip()
        if not url.startswith("http"):
            continue
        out.append(
            {
                "title": r["title"].strip(),
                "url": url,
                "snippet": r["snippet"].strip(),
                "date": today.isoformat(),
            }
        )
    return out
