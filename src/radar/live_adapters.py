"""Live network adapters wired into the pipeline at run time.

Kept thin and best-effort: each returns {} / [] on any failure so the source
isolation wrapper logs and the daily run still completes. Crunchbase and
LinkedIn are paywalled/authwalled, so they honestly degrade to {} rather than
shipping code that pretends to fetch them.
"""

from __future__ import annotations
from radar.model import Company


def gh_lookup(company: Company) -> dict:
    """Attach a GitHub repo ONLY when its homepage domain matches the company's.

    Provenance guarantee: a wrong citation is worse than none, so an unrelated
    top hit for a common name is rejected. Needs a known domain to match on.
    """
    import httpx

    q = company.name.strip()
    dom = (company.domain or "").lower().replace("www.", "")
    if not q or not dom:
        return {}
    try:
        resp = httpx.get(
            "https://api.github.com/search/repositories",
            params={"q": q, "per_page": 5},
            headers={"Accept": "application/vnd.github+json"},
            timeout=15,
        )
        items = resp.json().get("items") or []
    except Exception:
        return {}
    for repo in items:
        home = (repo.get("homepage") or "").lower()
        if dom and dom in home:
            return {"github_url": repo.get("html_url"), "product_url": repo.get("homepage")}
    return {}


def cb_lookup(company: Company) -> dict:
    """Crunchbase is paywalled/JS-gated for scraping; degrade to no enrichment."""
    return {}


def li_lookup(company: Company) -> dict:
    """LinkedIn needs the interactive logged-in browser flow, not available to the
    standalone daily script; enrich LinkedIn fields manually. Degrade to {}."""
    return {}
