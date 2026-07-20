"""RSS signals watcher: pulls beverage-AI news items from trade-press feeds as
LEADS to mine, kept separate from the company store (a headline is not a company
and must not pollute the deduped store). Stdlib XML + httpx; robust to a dead feed.

Run: python3 -m radar.signals   (or called from scripts/radar_daily.py)
"""

from __future__ import annotations
import json
import re
import xml.etree.ElementTree as ET
from radar.config import DASHBOARD_DIR, PROJECT_ROOT

SIGNALS_JSON = DASHBOARD_DIR / "signals.json"
SIGNALS_MD = PROJECT_ROOT / "SIGNALS.md"
MAX_SIGNALS = 400  # ponytail: hard cap so the file does not grow forever

# (url, beverage_specific). Non-beverage-specific feeds (AgFunder is agtech-broad)
# also require a beverage term, not just an AI term.
FEEDS = [
    ("https://agfundernews.com/feed", False),
    ("https://www.brewbound.com/feed", True),
    ("https://www.craftbrewingbusiness.com/feed/", True),
    ("https://www.thedrinksbusiness.com/feed/", True),
    ("https://wineindustryadvisor.com/feed", True),
    ("https://www.just-drinks.com/feed/", True),
]

_AI = re.compile(
    r"\b(ai|a\.i\.|artificial intelligence|machine learning|\bml\b|genai|generative ai|"
    r"computer vision|deep learning|algorithm|neural|predictive|data[- ]driven)\b",
    re.I,
)
_BEV = re.compile(
    r"\b(beer|brew|brewery|brewing|wine|winer|vine|vineyard|grape|distill|whisk|"
    r"spirit|beverage|cider|malt|hop)\w*",
    re.I,
)


def _default_fetch(url: str) -> str:
    import httpx

    return httpx.get(
        url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20, follow_redirects=True
    ).text


def _text(item, tag):
    el = item.find(tag)
    return (el.text or "").strip() if el is not None else ""


def parse_feed(xml_text: str, source: str, beverage_specific: bool) -> list[dict]:
    """Return matching {title, link, source, date} dicts from one RSS feed."""
    # Reject any feed declaring a DTD/entities: stdlib ElementTree does not fetch
    # external entities, and real RSS never needs a DOCTYPE, so a DOCTYPE here is
    # only ever a billion-laughs/entity-expansion attempt. Refuse it.
    if re.search(r"<!DOCTYPE|<!ENTITY", xml_text[:4000], re.I):
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out = []
    for item in root.iter("item"):
        title = _text(item, "title")
        desc = _text(item, "description")
        blob = f"{title} {desc}"
        if not _AI.search(blob):
            continue
        if not beverage_specific and not _BEV.search(blob):
            continue
        out.append(
            {
                "title": title,
                "link": _text(item, "link"),
                "source": source,
                "date": _text(item, "pubDate"),
            }
        )
    return out


def _load_existing() -> list[dict]:
    if SIGNALS_JSON.exists():
        try:
            return json.loads(SIGNALS_JSON.read_text())
        except json.JSONDecodeError:
            return []
    return []


def collect(feeds=FEEDS, fetch=_default_fetch) -> dict:
    """Fetch all feeds, keep new (unseen link) beverage-AI items. Returns
    {"new": int, "total": int}. Isolated per feed: one dead feed is skipped."""
    existing = _load_existing()
    seen = {s["link"] for s in existing}
    fresh = []
    for url, bev in feeds:
        try:
            items = parse_feed(fetch(url), _source_name(url), bev)
        except Exception:
            continue
        for it in items:
            if it["link"] and it["link"] not in seen:
                seen.add(it["link"])
                fresh.append(it)
    merged = (fresh + existing)[:MAX_SIGNALS]
    SIGNALS_JSON.parent.mkdir(parents=True, exist_ok=True)
    SIGNALS_JSON.write_text(json.dumps(merged, indent=2))
    _write_md(merged)
    return {"new": len(fresh), "total": len(merged)}


def _source_name(url: str) -> str:
    host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    return host


def _write_md(signals: list[dict]) -> None:
    lines = [
        "# Beverage-AI signals",
        "",
        f"Leads pulled from trade-press RSS. {len(signals)} items. "
        "Not companies; review and promote real ones into data/seed.json.",
        "",
    ]
    for s in signals[:120]:
        lines.append(f"- [{s['title']}]({s['link']}) ({s['source']}, {s['date']})")
    SIGNALS_MD.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    print(collect())
