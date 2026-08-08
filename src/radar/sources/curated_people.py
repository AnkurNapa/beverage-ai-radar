from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from radar.config import RECENCY_YEARS
from radar.model import Company, BeverageVertical, AIMaturity


def _enum(cls, value):
    if not value:
        return None
    try:
        return cls(str(value).strip().lower())
    except ValueError:
        return None


def _parse_date(value):
    return date.fromisoformat(value) if value else None


class CuratedPeopleSource:
    """Discovery lane for independent individuals applying AI to beer/whiskey/wine.

    Mirrors CuratedSeedSource but tracks *people* who are not captured as a
    seeded company's founder: solo builders, consultants, researchers, creators.
    Each person becomes a first-class tracked entity flagged
    company_type="individual", so it flows through the same store/export/report/
    vault machinery and shows up in the dashboard People view for free.

    Growth: add hand-verified individuals to data/people_seed.json and re-run.
    Provenance rule holds: every entry carries source_urls; never invent a
    person or a LinkedIn slug (use null instead).
    """

    name = "curated_people"
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
            role = r.get("role")
            out.append(
                Company(
                    name=r["name"],
                    hq_location=r.get("location"),
                    company_type="individual",
                    vertical=_enum(BeverageVertical, r.get("vertical")),
                    ai_use_case=r.get("ai_use_case"),
                    discovered_by="curated",
                    verified=True,
                    ai_maturity=_enum(AIMaturity, r.get("ai_maturity")),
                    key_people=f"{r['name']} ({role})" if role else r["name"],
                    people=[
                        {
                            "name": r["name"],
                            "role": role,
                            "linkedin": r.get("linkedin"),
                        }
                    ],
                    short_description=r.get("short_description"),
                    source_urls=r.get("source_urls") or [],
                    linkedin_url=r.get("linkedin"),
                    first_seen=_parse_date(r.get("first_seen")) or last_seen,
                    last_seen=last_seen,
                    links=r.get("links") or [],
                    verticals=[v for v in (r.get("verticals") or []) if v],
                    affiliated_company=r.get("company"),
                    affiliated_company_current=r.get("company_is_current"),
                )
            )
        return out
