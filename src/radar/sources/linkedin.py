from __future__ import annotations
from dataclasses import replace
from typing import Callable
from radar.model import Company


class LinkedInSource:
    """Enrichment via the existing logged-in Playwright browser flow.

    lookup_fn wraps that flow and returns {linkedin_url, key_people,
    size_employees, hq_location, source_url}. Injected so tests never
    drive a real browser.
    """
    name = "linkedin"
    kind = "enrichment"

    def __init__(self, lookup_fn: Callable[[Company], dict]):
        self.lookup_fn = lookup_fn

    def enrich(self, company: Company, fetcher) -> Company:
        data = self.lookup_fn(company) or {}
        if not data:
            return company
        urls = sorted(set(company.source_urls) | ({data["source_url"]} if data.get("source_url") else set()))
        return replace(company,
                       linkedin_url=data.get("linkedin_url") or company.linkedin_url,
                       key_people=data.get("key_people") or company.key_people,
                       size_employees=data.get("size_employees") or company.size_employees,
                       hq_location=data.get("hq_location") or company.hq_location,
                       source_urls=urls)
