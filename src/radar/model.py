from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from urllib.parse import urlparse
import re


class BeverageVertical(str, Enum):
    BEER = "beer"
    WHISKEY = "whiskey"
    WINE = "wine"
    MULTIPLE = "multiple"


class AIMaturity(str, Enum):
    RESEARCH = "research"
    PILOT = "pilot"
    SHIPPING = "shipping"


class Status(str, Enum):
    ACTIVE = "active"
    DORMANT = "dormant"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


def dedup_key(name: str, domain: str | None, hq_country: str | None) -> str:
    if domain:
        host = urlparse(domain if "//" in domain else f"//{domain}", scheme="http").hostname or ""
        host = host.lower()
        if host.startswith("www."):
            host = host[4:]
        parts = host.split(".")
        if len(parts) > 2:
            host = ".".join(parts[-2:])
        if host:
            return host
    country = _slug(hq_country) if hq_country else "unknown"
    return f"{_slug(name)}::{country}"


def _months_between(earlier: date, later: date) -> int:
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


def compute_status(last_seen: date, today: date, active_months: int) -> Status:
    return Status.ACTIVE if _months_between(last_seen, today) < active_months else Status.DORMANT


@dataclass
class Company:
    name: str
    domain: str | None = None
    hq_location: str | None = None
    founded_year: int | None = None
    size_employees: str | None = None
    vertical: BeverageVertical | None = None
    company_type: str | None = None  # "product" (default) | "service"
    ai_use_case: str | None = None
    ai_maturity: AIMaturity | None = None
    funding_stage: str | None = None
    total_raised: str | None = None
    key_people: str | None = None
    people: list = field(default_factory=list)  # [{name, role, linkedin}]
    notable_customers_partners: str | None = None
    short_description: str | None = None
    source_urls: list[str] = field(default_factory=list)
    first_seen: date | None = None
    last_seen: date | None = None
    status: Status | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    product_url: str | None = None
    latest_news_headline: str | None = None
    why_interesting: str | None = None
    # Provenance: "curated" for hand-checked entries, "scout:<surface>" for
    # agent-found ones. verified stays False until a human confirms, so one bad
    # sweep can be identified and undone instead of quietly contaminating the set.
    discovered_by: str | None = None
    verified: bool | None = None

    @property
    def key(self) -> str:
        country = self.hq_location.split(",")[-1].strip() if self.hq_location else None
        return dedup_key(self.name, self.domain, country)
