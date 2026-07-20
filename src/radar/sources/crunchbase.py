from __future__ import annotations
from dataclasses import replace
from datetime import date
from typing import Callable
from radar.model import Company


class CrunchbaseSource:
    name = "crunchbase"
    kind = "enrichment"

    def __init__(self, lookup_fn: Callable[[Company], dict]):
        self.lookup_fn = lookup_fn

    def enrich(self, company: Company, fetcher) -> Company:
        data = self.lookup_fn(company) or {}
        if not data:
            return company
        urls = sorted(set(company.source_urls) | ({data["source_url"]} if data.get("source_url") else set()))
        return replace(
            company,
            funding_stage=data.get("funding_stage") or company.funding_stage,
            total_raised=data.get("total_raised") or company.total_raised,
            key_people=data.get("key_people") or company.key_people,
            source_urls=urls,
            last_seen=max(x for x in (company.last_seen, date.today()) if x),
        )
