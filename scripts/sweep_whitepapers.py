#!/usr/bin/env python3
"""Sweep vendor and trade-body sites for white papers on AI and data in drinks.

Why this exists alongside sweep_papers.py: that script covers PEER-REVIEWED work
via OpenAlex. Industry white papers are a different literature. They are where
vendors publish the deployment detail a brewer actually argues with, they never
carry a DOI, and they are invisible to a scholarly index.

Why hub crawling and not a search engine: the search APIs are keyed or blocked
from this host, and a vendor's own resource hub is the authoritative list of
what that vendor published. Each hub is fetched once, its links are read, and
anything that looks like a paper is gated the same way the other sweeps gate.

Blocked hubs are RECORDED, not dropped. Krones and ASBC sit behind Cloudflare
and return 403 to any plain client; silently losing them would make the output
look like those vendors publish nothing, which is false. They land in the
"blocked" array for a browser-equipped pass, per the repo's scope rules.

Writes data/resources/whitepapers.json. build_resources.py folds it in.

Run: python3 scripts/sweep_whitepapers.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Curated papers live in whitepapers.json; the sweep never overwrites them.
OUT = ROOT / "data" / "resources" / "whitepapers_swept.json"
EXISTING = ROOT / "dashboard" / "resources.json"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")

# (publisher, vertical, hub url). Verified reachable 2026-08-09; the ones that
# 403 are listed in BLOCKED_KNOWN below rather than being quietly missing.
HUBS = [
    # Point at LISTING pages, not homepages. A homepage is navigation: the first
    # version of this script crawled seven of them and found nothing, because
    # the documents all live a level down.
    ("ProLeiT", "beer", "https://www.proleit.com/news-events/press/"),
    ("ProLeiT", "beer", "https://www.proleit.com/media-center/"),
    ("MBAA", "beer", "https://www.mbaa.com/publications"),
    ("MBAA", "beer", "https://www.mbaa.com/brewing-resources"),
    ("GEA Group", "multiple", "https://www.gea.com/en/insights/"),  # measured: 251 links, 0 drinks+AI
    ("First Key Consulting", "beer", "https://firstkey.com/insights/"),
    ("Databricks", "multiple", "https://www.databricks.com/resources?filter=Whitepaper"),
    ("Snowflake", "multiple", "https://www.snowflake.com/en/resources/?_sft_resource-type=white-paper"),
]

# Hubs known to refuse a plain client. Carried into the output so the gap is
# visible in the data rather than only in someone's memory.
BLOCKED_KNOWN = [
    # Measured 2026-08-09 with a real browser, not assumed.
    {"publisher": "Krones", "url": "https://www.krones.com/en/company/press/magazine/",
     "reason": "403 to any plain client, and the magazine index builds its article list in JS, "
               "so it is not enumerable even rendered. Individual article URLs DO load in a "
               "browser; four are hand-curated in whitepapers.json."},
    {"publisher": "ASBC", "url": "https://www.asbcnet.org/",
     "reason": "403 to plain client; browser navigation times out at 45s"},
    {"publisher": "MBAA", "url": "https://www.mbaa.com/technical-quarterly",
     "reason": "Technical Quarterly is member-gated, so the papers are not openly linkable"},
    {"publisher": "Endress+Hauser", "url": "https://www.endress.com/en/field-instruments-overview/beverage-industry",
     "reason": "returns a 1.8KB JS shell with no links to a plain client"},
]

# A link is a candidate if it looks like a document rather than navigation.
DOCLIKE = re.compile(
    r"(\.pdf($|\?)|white[- ]?paper|whitepaper|/insights?/|/resources?/|"
    r"case[- ]study|/report|technical[- ]paper|application[- ]note|/library/)", re.I)

BEVERAGE = re.compile(
    r"\b(beer|brewing|brewery|breweries|brewer|malt|hop|hops|wort|lager|ale|"
    r"wine|winery|vineyard|viticultur|grape|"
    r"whisky|whiskey|distill|distiller|distillery|spirits|cask|"
    r"cider|beverage|beverages|drinks|bottling|brewhouse|fermentation|"
    r"soft drink|dairy|food and beverage)\b", re.I)
DATA = re.compile(
    r"\b(machine learning|deep learning|neural|artificial intelligence|\bai\b|"
    r"data science|analytics|data|predictive|prediction|forecast|"
    r"computer vision|digital twin|industry 4\.?0|digitali[sz]ation|automation|"
    r"generative|algorithm|dashboard|iot|sensor|mes|scada|optimi[sz]ation)\b", re.I)
# Navigation furniture that matches DOCLIKE but is not a document.
NAV_NOISE = re.compile(
    r"^(insights|resources|library|reports|all |view all|learn more|read more|"
    r"contact|careers|privacy|cookie|imprint|terms|login|sign in|search)\b", re.I)


class LinkParser(HTMLParser):
    """Collect (href, visible text) pairs. stdlib only, like the other sweeps."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self._href = href
                self._buf = []

    def handle_data(self, data):
        if self._href is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            self.links.append((self._href, text))
            self._href = None
            self._buf = []


def fetch(url: str) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="ignore")


def load_seen() -> set[str]:
    seen: set[str] = set()
    if OUT.exists():
        seen.update(r["url"] for r in json.loads(OUT.read_text()) if r.get("url"))
    if EXISTING.exists():
        for r in json.loads(EXISTING.read_text()):
            if r.get("url"):
                seen.add(r["url"].rstrip("/"))
    return seen


def harvest(publisher: str, vertical: str, hub: str, seen: set[str]) -> list[dict]:
    html = fetch(hub)
    parser = LinkParser()
    parser.feed(html)

    return _gate_links(parser.links, publisher, vertical, hub, seen)


def _gate_links(links, publisher: str, vertical: str, base: str, seen: set[str]) -> list[dict]:
    """Shared relevance gate. Both the HTTP and the rendered path use this, so
    the two cannot drift into disagreeing about what counts as a white paper."""
    out: list[dict] = []
    for href, text in links:
        # Same-page and empty anchors resolve to the base itself, which then
        # inherits its path and matches DOCLIKE. That is how "Skip to content"
        # passed as a document on the first run.
        if not href or href.startswith("#") or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        url = urllib.parse.urljoin(base, href).split("#")[0].rstrip("/")
        if not url.startswith("http") or url in seen or url == base.rstrip("/"):
            continue
        # Match the HREF, not the resolved URL: resolution grafts the base path
        # onto every relative link, so every link would look doc-like.
        if not DOCLIKE.search(href + " " + text):
            continue
        title = re.sub(r"\s+", " ", text).strip()
        # A link with no text is usually an image or icon wrapper; the URL slug
        # is a poor title and would publish something unreadable.
        if len(title) < 15 or NAV_NOISE.match(title):
            continue
        blob = f"{title} {url}"
        if not (BEVERAGE.search(blob) and DATA.search(blob)):
            continue
        seen.add(url)
        out.append({
            "title": title[:180],
            "url": url,
            "vertical": vertical,
            "publisher": publisher,
            "summary": "",  # filled by hand on review; never invented here
            "is_pdf": bool(re.search(r"\.pdf($|\?)", url, re.I)),
        })
    return out


def harvest_capture(capture: Path, seen: set[str]) -> tuple[list[dict], list[dict]]:
    """Gate links a browser already rendered.

    Most vendor resource listings are JavaScript-rendered: a plain fetch returns
    navigation and nothing else, which is why the pure-HTTP pass finds almost
    nothing on them. So the fetching moves to a browser and only the link list
    comes back here. The gate is the SAME function the HTTP path uses, so the
    two can never drift apart on what counts as a white paper.

    Input is a JSON array of
      {"publisher": .., "vertical": .., "url": .., "links": [[href, text], ..]}
    or, for a page the browser also could not reach, {"error": ".."}.
    """
    entries = json.loads(capture.read_text())
    kept: list[dict] = []
    blocked: list[dict] = []
    for entry in entries:
        if entry.get("error") or not entry.get("links"):
            blocked.append({"publisher": entry.get("publisher", "?"),
                            "url": entry.get("url", ""),
                            "reason": entry.get("error") or "no links returned"})
            continue
        found = _gate_links([tuple(x) for x in entry["links"]], entry["publisher"],
                            entry.get("vertical", "multiple"), entry["url"], seen)
        print("  %-22s %3d links -> %2d candidates (rendered)"
              % (entry["publisher"], len(entry["links"]), len(found)))
        kept.extend(found)
    return kept, blocked


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--from-capture", metavar="FILE",
                    help="JSON of browser-rendered links from a Playwright pass")
    args = ap.parse_args()

    seen = load_seen()
    print("already known: %d urls" % len(seen))

    kept: list[dict] = []
    blocked = list(BLOCKED_KNOWN)

    if args.from_capture:
        k, b = harvest_capture(Path(args.from_capture), seen)
        kept.extend(k)
        blocked.extend(b)
        return _finish(kept, blocked, args)

    for publisher, vertical, hub in HUBS:
        try:
            found = harvest(publisher, vertical, hub, seen)
        except urllib.error.HTTPError as exc:
            print("  ! %-22s %s -> HTTP %s (recorded as blocked)" % (publisher, hub, exc.code))
            blocked.append({"publisher": publisher, "url": hub, "reason": "HTTP %s" % exc.code})
            continue
        except Exception as exc:
            print("  ! %-22s %s -> %s (recorded as blocked)" % (publisher, hub, exc))
            blocked.append({"publisher": publisher, "url": hub, "reason": str(exc)[:120]})
            continue
        print("  %-22s %2d candidates" % (publisher, len(found)))
        kept.extend(found)
        time.sleep(2)

    return _finish(kept, blocked, args)


def _finish(kept: list[dict], blocked: list[dict], args) -> int:
    print("\n%d candidate white papers, %d hubs blocked" % (len(kept), len(blocked)))
    for r in kept[:25]:
        print("  - [%s] %s" % (r["publisher"], r["title"][:80]))
    if blocked:
        print("\nblocked (need a browser pass):")
        for b in blocked:
            print("  - %s: %s" % (b["publisher"], b["reason"]))

    if args.dry_run:
        return 0

    OUT.write_text(json.dumps({"whitepapers": kept, "blocked": blocked},
                              indent=2, ensure_ascii=False) + "\n")
    print("\nwrote %s" % OUT)
    print("REVIEW IT: summaries are intentionally empty and titles come from link")
    print("text, so check them before running build_resources.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
