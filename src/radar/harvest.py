"""Turn the author lists of the radar's own paper library into people.

Scouts start from web search, which runs out and only ever returns a top slice.
A paper's author list is a complete list with no search in it: every paper here
already passed the beverage-and-AI gate in scripts/sweep_papers.py, so its
authors are people doing exactly the work the People view tracks.

Who publishes: a lead (first) or senior (last) author, or anyone on two or more
papers. A middle author of a single paper is a candidate, not a row: the first
people sweep rejected exactly that profile ("only a co-author on one phenology
paper") and the rule keeps the view about people who drive the work.

Pure: the network half is scripts/harvest_authors.py.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from radar.config import RECENCY_YEARS

LEAD_POSITIONS = {"first", "last"}
# Titles and names arrive with typographic punctuation the house style bans.
_ASCII = str.maketrans(
    {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-"}
)


def _clean(s: str) -> str:
    return " ".join((s or "").translate(_ASCII).split())


def _affiliation(authorship: dict) -> tuple[str, str]:
    inst = (authorship.get("institutions") or [{}])[0]
    return _clean(inst.get("display_name")), inst.get("id") or ""


def people_from_works(
    works: list[dict],
    vertical_by_doi: dict,
    place_by_institution: dict,
    today: date,
    title_ok=None,
) -> tuple[list[dict], list[dict]]:
    """Returns (people rows in people_seed schema, middle-author candidates).

    title_ok: the library admits a paper when a beverage word appears anywhere in
    it, which let a general e-nose survey and a coffee paper in. A person row is a
    stronger claim, so the caller can demand the beverage word in the title."""
    by_author: dict[str, dict] = defaultdict(lambda: {"papers": [], "lead": False})
    for w in works:
        year = w.get("publication_year") or 0
        date_str = w.get("publication_date") or f"{year}-01-01"
        # Same date cutoff as CuratedPeopleSource; a year-only check let July 2016
        # papers through in September 2026 and the pipeline then hid those people.
        if date_str < today.replace(year=today.year - RECENCY_YEARS).isoformat():
            continue
        if title_ok and not title_ok(w.get("title") or ""):
            continue
        doi = w.get("doi") or ""
        for a in w.get("authorships") or []:
            author = a.get("author") or {}
            if not author.get("id") or not author.get("display_name"):
                continue
            inst, inst_id = _affiliation(a)
            entry = by_author[author["id"]]
            entry["name"] = _clean(author["display_name"])
            entry["papers"].append(
                {
                    "doi": doi,
                    "year": year,
                    "date": date_str,
                    "title": _clean(w.get("title")),
                    "inst": inst,
                    "inst_id": inst_id,
                }
            )
            entry["lead"] |= a.get("author_position") in LEAD_POSITIONS

    people, candidates = [], []
    for author_id, e in by_author.items():
        papers = sorted(e["papers"], key=lambda p: p["date"], reverse=True)
        latest = papers[0]
        if not latest["inst"]:
            continue  # nothing to call an employer, so nothing to dedupe on
        verticals = sorted({vertical_by_doi.get(p["doi"]) for p in papers} - {None})
        row = {
            "name": e["name"],
            "role": f"Published researcher, {latest['inst']}",
            "company": latest["inst"],
            "company_is_current": None,
            "location": place_by_institution.get(latest["inst_id"]),
            "linkedin": None,
            "vertical": verticals[0] if len(verticals) == 1 else "multiple",
            "verticals": verticals,
            "ai_use_case": "peer-reviewed ai and data research",
            "ai_maturity": "research",
            "short_description": _describe(e["name"], papers, e["lead"]),
            "source_urls": [p["doi"] for p in papers] + [author_id],
            "first_seen": papers[-1]["date"],
            "last_seen": latest["date"],
            "discovered_by": "harvest:openalex",
        }
        (people if e["lead"] or len(papers) >= 2 else candidates).append(row)
    return people, candidates


def _describe(name: str, papers: list[dict], lead: bool) -> str:
    latest = papers[0]
    title = latest["title"].rstrip(".")
    lead_note = " as a lead or senior author" if lead else ""
    n = len(papers)
    return (
        f"{name} has {n} peer-reviewed paper{'s' if n > 1 else ''} in the radar's research "
        f"library applying AI or data to beverages{lead_note}. Most recent"
        f"{': ' + title if title else ''} ({latest['year']}), affiliated with {latest['inst']}."
    )
