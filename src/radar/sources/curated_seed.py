from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from radar.config import RECENCY_YEARS
from radar.model import Company, BeverageVertical, AIMaturity


def _enum(cls, value):
    """Coerce a seed string to an enum member, tolerating unknowns/None."""
    if not value:
        return None
    try:
        return cls(str(value).strip().lower())
    except ValueError:
        return None


def _parse_date(value):
    return date.fromisoformat(value) if value else None


class CuratedSeedSource:
    """Discovery from a hand-verified JSON seed (data/seed.json).

    The most reliable source: every company is human-checked with real
    source_urls, so it never depends on a live surface being up. Live web
    sources augment and refresh on top of it.
    """

    name = "curated_seed"
    kind = "discovery"

    def __init__(self, seed_path: Path, today: date | None = None):
        self.seed_path = Path(seed_path)
        self.today = today or date.today()

    def discover(self, fetcher) -> list[Company]:
        if not self.seed_path.exists():
            return []
        cutoff = self.today.replace(year=self.today.year - RECENCY_YEARS)
        out: list[Company] = []
        for r in json.loads(self.seed_path.read_text()):
            last_seen = _parse_date(r.get("last_seen"))
            if last_seen and last_seen < cutoff:
                continue
            out.append(
                Company(
                    name=r["name"],
                    domain=r.get("domain"),
                    hq_location=r.get("hq_location"),
                    founded_year=r.get("founded_year"),
                    vertical=_enum(BeverageVertical, r.get("vertical")),
                    company_type=r.get("company_type"),
                    ai_use_case=r.get("ai_use_case"),
                    ai_maturity=_enum(AIMaturity, r.get("ai_maturity")),
                    key_people=r.get("key_people"),
                    people=r.get("people") or [],
                    funding_stage=r.get("funding_stage"),
                    total_raised=r.get("total_raised"),
                    short_description=r.get("short_description"),
                    source_urls=r.get("source_urls") or [],
                    first_seen=_parse_date(r.get("first_seen")) or last_seen,
                    last_seen=last_seen,
                    latest_news_headline=r.get("latest_news_headline"),
                )
            )
        return out
