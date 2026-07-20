"""Live network adapters wired into the pipeline at run time.

Kept thin and best-effort: each returns {} / [] on any failure so the source
isolation wrapper logs and the daily run still completes. Crunchbase and
LinkedIn are paywalled/authwalled, so they honestly degrade to {} rather than
shipping code that pretends to fetch them.
"""

from __future__ import annotations
from radar.model import Company


def gh_lookup(company: Company) -> dict:
    """Find a plausible GitHub org/repo for the company via the keyless search API."""
    import httpx

    q = company.name.strip()
    if not q:
        return {}
    try:
        resp = httpx.get(
            "https://api.github.com/search/repositories",
            params={"q": q, "per_page": 1},
            headers={"Accept": "application/vnd.github+json"},
            timeout=15,
        )
        items = resp.json().get("items") or []
    except Exception:
        return {}
    if not items:
        return {}
    top = items[0]
    out = {"github_url": top.get("html_url")}
    if top.get("homepage"):
        out["product_url"] = top["homepage"]
    return out


def cb_lookup(company: Company) -> dict:
    """Crunchbase is paywalled/JS-gated for scraping; degrade to no enrichment."""
    return {}


def li_lookup(company: Company) -> dict:
    """LinkedIn needs the interactive logged-in browser flow, not available to the
    standalone daily script; enrich LinkedIn fields manually. Degrade to {}."""
    return {}
