from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
import re

from radar.scout.merge import norm_domain


class BeverageVertical(str, Enum):
    BEER = "beer"
    WHISKEY = "whiskey"
    WINE = "wine"
    MULTIPLE = "multiple"
    # Adjacent lane, not the headline. Soft drinks, water, juice, energy and the
    # food-and-beverage majors that run AI across a portfolio which includes
    # drinks. The radar still leads on beer, whiskey and wine; this exists so a
    # PepsiCo or a Coca-Cola can be tracked without being mislabelled as one of
    # the three core verticals.
    NON_ALCOHOLIC = "non_alcoholic"
    # Food groups whose AI work is worth tracking because the same models,
    # vendors and people cross over into drinks. Also adjacent, never the lead.
    FOOD = "food"


class AIMaturity(str, Enum):
    # NONE is not "unknown" - it means the entry was checked and the vendor
    # makes no AI or ML claim. Without it the enum cannot express a checked
    # negative, and such entries get filed as SHIPPING, which the dashboard
    # renders as shipping AI. That is how 114 honestly-recorded non-AI
    # companies came to be published as AI vendors.
    NONE = "none"
    RESEARCH = "research"
    PILOT = "pilot"
    SHIPPING = "shipping"


class Status(str, Enum):
    ACTIVE = "active"
    DORMANT = "dormant"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


def dedup_key(name: str, domain: str | None, hq_country: str | None) -> str:
    """Stable identity for a company. The registrable domain is the natural key.

    Delegates to scout.merge.norm_domain rather than reimplementing the suffix
    rules: this function used to carry its own copy that truncated
    kegtracker.co.uk to "co.uk", so every British company shared one identity.
    One implementation, one place to fix.
    """
    if domain:
        host = norm_domain(domain)
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
    # Affiliation edge for company_type="individual" rows. Without this the
    # people roster and the company list were two disconnected tables: a
    # tracked person could name their employer and the employer's page would
    # never know. current=False means the link is historical (a former role),
    # which must never render as present-tense employment.
    # Outward links a person or company wants surfaced: talks, podcast
    # episodes, articles. Kept separate from source_urls, which is evidence
    # for the record rather than things a reader is invited to go and watch.
    links: list = field(default_factory=list)  # [{label, url, kind}]
    affiliated_company: str | None = None
    affiliated_company_current: bool | None = None

    @property
    def key(self) -> str:
        country = self.hq_location.split(",")[-1].strip() if self.hq_location else None
        return dedup_key(self.name, self.domain, country)
