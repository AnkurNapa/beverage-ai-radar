from __future__ import annotations
from dataclasses import replace
from typing import Callable
from radar.model import Company


class GithubProductSource:
    name = "github_product"
    kind = "enrichment"

    def __init__(self, lookup_fn: Callable[[Company], dict]):
        self.lookup_fn = lookup_fn

    def enrich(self, company: Company, fetcher) -> Company:
        data = self.lookup_fn(company) or {}
        if not data:
            return company
        urls = sorted(
            set(company.source_urls)
            | {u for u in (data.get("github_url"), data.get("product_url")) if u}
        )
        return replace(
            company,
            github_url=data.get("github_url") or company.github_url,
            product_url=data.get("product_url") or company.product_url,
            source_urls=urls,
        )
