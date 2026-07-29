#!/usr/bin/env python3
"""Sweep the LinkedIn guest job API for beverage + AI/data roles.

Writes dashboard/jobs.json, the feed behind the dashboard's Jobs tab. Same
evidence rule as the rest of the radar: every row links to its posting.

The guest search is fuzzy, so a card is kept only if title + company carry
both a beverage signal and a data/AI signal. Cards whose employer matches a
tracked company in data/seed.json are flagged so the tab can show "hiring now"
against the landscape.

Run: python3 scripts/build_jobs.py
"""
import html
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed.json"
OUT = ROOT / "dashboard" / "jobs.json"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
TPR = "r2592000"  # 30 days: this tab refreshes on demand, not daily
QUERIES = [
    "brewery data analyst", "brewing data scientist", "beer analytics",
    "winery data analyst", "wine analytics", "vineyard machine learning",
    "distillery data analyst", "spirits analytics", "whiskey data",
    "beverage data scientist", "beverage AI", "drinks category analytics",
    "fermentation machine learning", "sensory data scientist",
]
LOCATIONS = ["", "United States", "United Kingdom", "India"]

BEV = re.compile(r"brew|beer|malt|\bhops?\b|winer|\bwine\b|vineyard|viticult|distill|whisk|"
                 r"spirits|bevera|drinks|cider|fermentat|\bbrandy\b|tequila|\brum\b", re.I)
# Big drinks employers whose name carries no beverage word. Without this the
# title+company gate drops real hits like "Data Scientist @ Diageo".
BEV_EMPLOYER = re.compile(
    r"diageo|pernod|ab inbev|anheuser|heineken|carlsberg|constellation brands|"
    r"brown-?forman|bacardi|treasury wine|e\.? ?& ?j\.? gallo|molson|asahi|kirin|"
    r"sapporo|suntory|r[eé]my cointreau|campari|william grant|edrington|duckhorn|"
    r"jackson family|boston beer|sierra nevada|moet|lvmh|thai bev|united spirits|"
    r"radico|allied blenders|sula", re.I)
AI = re.compile(r"data|analyt|machine learning|\bml\b|\bai\b|artificial intelligence|"
                r"scien|insight|business intelligence|\bbi\b|power ?bi|tableau|"
                r"forecast|sensory|digital", re.I)
BAD = re.compile(r"intern\b|internship|fresher|commission only|server\b|bartend|"
                 # "entreprise fictive" is a French training-school mock company:
                 # it posts mock vacancies, which are never real openings.
                 r"waiter|waitress|cellar hand|delivery driver|merchandis|fictive|fictitious", re.I)


# Employers whose name carries no vertical word but whose business is one.
# Keeps the vertical filter useful instead of dumping everything in "multiple".
EMPLOYER_VERTICAL = [
    (re.compile(r"ab inbev|anheuser|heineken|carlsberg|molson|asahi|kirin|sapporo|britvic", re.I), "beer"),
    (re.compile(r"diageo|pernod|brown-?forman|bacardi|suntory|william grant|edrington|"
                r"campari|r[eé]my|radico|allied blenders|united spirits", re.I), "whiskey"),
    (re.compile(r"treasury wine|gallo|duckhorn|jackson family|the wine group|sula", re.I), "wine"),
]


def vertical_of(text):
    """Tag a posting with the radar's beverage verticals (same buckets as companies)."""
    hits = set()
    if re.search(r"brew|beer|malt|\bhops?\b|cider", text, re.I):
        hits.add("beer")
    if re.search(r"winer|wine|vineyard|viticult", text, re.I):
        hits.add("wine")
    if re.search(r"distill|whisk|spirits|tequila|\brum\b|\bbrandy\b", text, re.I):
        hits.add("whiskey")
    if len(hits) == 1:
        return hits.pop()
    if not hits:
        for rx, v in EMPLOYER_VERTICAL:
            if rx.search(text):
                return v
    return "multiple"


US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}
# LinkedIn also emits metro strings with no country at all ("Greater Kolkata
# Area"). Only the cities that actually turn up need mapping; anything unknown
# stays blank rather than being guessed into the wrong country.
METRO_COUNTRY = {
    "kolkata": "India", "mumbai": "India", "delhi": "India", "bengaluru": "India",
    "bangalore": "India", "hyderabad": "India", "chennai": "India", "pune": "India",
    "new york city": "United States", "chicago": "United States",
    "san francisco bay": "United States", "los angeles": "United States",
    "boston": "United States", "seattle": "United States",
    "london": "United Kingdom", "manchester": "United Kingdom",
    "dublin": "Ireland", "sydney": "Australia", "melbourne": "Australia",
    "amsterdam": "Netherlands", "paris": "France", "toronto": "Canada",
}


def country_of(location):
    """Best-effort country for a LinkedIn location string.

    Three shapes turn up: "Boston, MA", "London, England, United Kingdom" and
    bare metro strings like "Greater Kolkata Area". Returns "" when the string
    supports no honest answer, so the filter can omit it instead of inventing
    a country.
    """
    loc = (location or "").strip()
    if not loc:
        return ""
    parts = [p.strip() for p in loc.split(",") if p.strip()]
    last = parts[-1] if parts else ""
    if last.upper() in US_STATES:
        return "United States"
    if len(parts) > 1:
        return last
    stripped = re.sub(r"\b(greater|metropolitan|area|region)\b", " ", last, flags=re.I)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    if stripped == last:
        return last  # a plain single-segment string, e.g. "United States"
    return METRO_COUNTRY.get(stripped.lower(), "")  # a metro form we cannot place


def keep(card, tracked=()):
    """Guest search is fuzzy; demand a beverage AND a data signal, drop obvious noise."""
    blob = f"{card['title']} {card['company']}"
    company = card["company"].lower()
    beverage = (BEV.search(blob) or BEV_EMPLOYER.search(company)
                or any(t in company for t in tracked))
    return bool(beverage and AI.search(blob) and not BAD.search(blob))


def fetch(kw, loc, start=0):
    p = {"keywords": kw, "location": loc, "f_TPR": TPR, "start": start}
    url = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
           + urllib.parse.urlencode(p))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return ""


PAGES = 3  # the guest endpoint returns 10 cards a page; 3 covers most employers


def fetch_pages(query, loc="", pages=PAGES):
    """Walk the guest endpoint page by page.

    One request only ever returns 10 cards, so a single call per employer sees
    a near-random tenth of its openings. Stops early on an empty page or when a
    page adds nothing new, which is how the endpoint signals the end.
    """
    seen = set()
    for start in range(0, pages * 10, 10):
        cards = parse(fetch(query, loc, start))
        fresh = [c for c in cards if c["id"] not in seen]
        if not fresh:
            return
        seen.update(c["id"] for c in fresh)
        yield from fresh
        time.sleep(1.2)  # ponytail: fixed pause, back off properly if LinkedIn starts 429ing


def parse(page):
    out = []
    for c in re.split(r"<li>", page):
        m = (re.search(r'data-entity-urn="urn:li:jobPosting:(\d+)"', c)
             or re.search(r'/jobs/view/(?:[^/?"]*-)?(\d{10})', c))
        if not m:
            continue
        d = {"id": m.group(1), "title": "", "company": "", "location": "",
             "posted": "", "url": f"https://www.linkedin.com/jobs/view/{m.group(1)}"}
        mt = re.search(r'class="base-search-card__title">\s*(.*?)\s*</h3>', c, re.S)
        if mt:
            d["title"] = html.unescape(re.sub(r"\s+", " ", mt.group(1))).strip()
        mc = (re.search(r'class="base-search-card__subtitle">.*?>\s*(.*?)\s*</a>', c, re.S)
              or re.search(r'class="base-search-card__subtitle">\s*(.*?)\s*</h4>', c, re.S))
        if mc:
            d["company"] = html.unescape(re.sub(r"<[^>]+>", "", mc.group(1))).strip()
        ml = re.search(r'class="job-search-card__location">\s*(.*?)\s*</span>', c, re.S)
        if ml:
            d["location"] = html.unescape(re.sub(r"\s+", " ", ml.group(1))).strip()
        md = re.search(r'datetime="(\d{4}-\d{2}-\d{2})"', c)
        if md:
            d["posted"] = md.group(1)
        out.append(d)
    return out


# Seed names carry an editorial parenthetical ("Molson Coors (Atwater Brewery)",
# "Watgrid (WINEGRID)"). No job card ever says that, so both the search and the
# employer match have to run on the trading name alone. 28 of 175 companies were
# unmatchable until this was stripped.
LEGAL_SUFFIX = re.compile(r"[,\s]+(inc|llc|ltd|limited|plc|gmbh|s\.?a\.?|b\.?v\.?|"
                          r"pty|pvt|corp|corporation|co|group|holdings)\.?$", re.I)


def trading_name(name):
    """The name an employer actually posts jobs under."""
    return LEGAL_SUFFIX.sub("", re.sub(r"\s*\(.*?\)", "", name)).strip()


def tracked_names():
    """Map searchable trading name -> the radar's display name.

    Short names ("Vin", "Oak") would match half of LinkedIn, so require 5+
    chars. Individuals are people, not employers: searching their name finds
    nothing but noise.
    """
    seed = json.loads(SEED.read_text())
    out = {}
    for c in seed:
        if c.get("company_type") == "individual":
            continue
        short = trading_name(c.get("name", ""))
        if len(short) >= 5:
            out.setdefault(short.lower(), c["name"])
    return out


def tag(card, tracked, query, company=""):
    blob = f"{card['title']} {card['company']}"
    card["vertical"] = vertical_of(blob)
    card["country"] = country_of(card["location"])
    card["query"] = query
    card["tracked_company"] = company or next(
        (n for k, n in tracked.items() if k in card["company"].lower()), "")
    return card


def keyword_sweep(tracked, jobs):
    """Pass 1: the field at large. Fuzzy search, so both gates apply."""
    for kw in QUERIES:
        for loc in LOCATIONS:
            for card in fetch_pages(kw, loc):
                if card["id"] in jobs or not keep(card, tracked):
                    continue
                jobs[card["id"]] = tag(card, tracked, kw)


def company_sweep(tracked, jobs):
    """Pass 2: ask each tracked company directly whether it is hiring.

    The employer is already verified as beverage-AI, so the beverage gate is
    satisfied by the match itself, but the data/AI gate stays: this is a radar
    of AI work, not a general job board, and these employers are large enough
    that dropping it buries the data roles under welders and accountants.

    The name match is a substring so "Heineken" still catches "The HEINEKEN
    Company", which lets a generic tracked name pull an unrelated employer
    ("Solera" matched a senior-living chain). The data gate is what filters
    those out in practice, since the mismatches are rarely data roles.
    """
    for lower, name in tracked.items():
        for card in fetch_pages(lower):
            if card["id"] in jobs or lower not in card["company"].lower():
                continue
            blob = f"{card['title']} {card['company']}"
            if BAD.search(blob) or not AI.search(blob):
                continue
            jobs[card["id"]] = tag(card, tracked, name, company=name)


def build():
    tracked = tracked_names()
    jobs = {}
    keyword_sweep(tracked, jobs)
    print(f"keyword sweep: {len(jobs)} jobs")
    company_sweep(tracked, jobs)
    rows = sorted(jobs.values(), key=lambda j: (j["posted"] or "", j["company"]), reverse=True)
    OUT.write_text(json.dumps(rows, indent=2) + "\n")
    at_tracked = sum(1 for j in rows if j["tracked_company"])
    print(f"wrote {len(rows)} jobs ({at_tracked} at tracked companies) to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    build()
