#!/usr/bin/env python3
"""Collect named leadership from prospects' own leadership and team pages.

A company that publishes a leadership page is telling you who runs what. That
is the useful half of prospecting and it is entirely public: a name and a title
is what you need to find someone on LinkedIn, and looking them up there is what
LinkedIn is for.

What this deliberately does NOT do:

  - construct an email from a name. firstname.lastname@ guesses either bounce
    or land on the wrong person, and a lead list that does this quietly poisons
    every address in it.
  - read anything from a social profile. Bulk profile harvesting breaks
    LinkedIn's terms, and the block is aggressive enough that the data would be
    unreliable even if it did not.
  - record anything personal. Work role, work company, published page. Nothing
    about where someone lives or how to reach them privately.

Names are matched near a job title, since a page full of prose has plenty of
capitalised words that are not people. Both are kept only when they appear
together.

Run: python3 scripts/harvest_people.py [--limit N] [--region India]
"""
from __future__ import annotations

import argparse
import html as htmllib
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "prospects.json"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
PATHS = ["/leadership", "/our-team", "/team", "/about/team", "/about-us/team",
         "/management", "/board", "/who-we-are", "/people", "/about/leadership",
         "/company/leadership", "/about-us", "/about"]

TITLE = (r"(?:chief\s+\w+\s+officer|c[eotf]o\b|managing\s+director|founder|co-?founder|"
         r"president|vice\s+president|head\s+of\s+[\w\s]{3,28}|director\s+of\s+[\w\s]{3,28}|"
         r"general\s+manager|master\s+(?:distiller|blender|brewer)|"
         r"chief\s+winemaker|head\s+(?:brewer|distiller|winemaker)|"
         r"technical\s+director|operations\s+director|commercial\s+director)")
NAME = r"[A-Z][a-z'’]+(?:\s+[A-Z][a-z'’.]+){1,3}"

# Name then title, or title then name. Both orders appear on real team pages.
PATTERNS = [
    re.compile(rf"({NAME})\s*[,–—\-|:]\s*({TITLE}[^.<\n]{{0,40}})", re.I),
    re.compile(rf"({TITLE}[^.<\n]{{0,40}})\s*[,–—\-|:]\s*({NAME})", re.I),
]
# A capitalised-words regex over prose finds plenty that is not a person:
# "Maharashtra", "With", and "he provides the overall" all came back as names
# on the first run. A real name is 2-4 capitalised tokens, every one of them
# alphabetic, and contains no sentence machinery.
STOPWORD = re.compile(r"\b(the|and|with|for|from|that|this|has|have|his|her|its|"
                      r"he|she|they|our|your|their|of|in|on|at|to|is|was|were|"
                      r"provides|assumes|manages|leads|joined|brings|holds|"
                      r"responsibility|overall|experience|years|team|group|"
                      r"limited|ltd|pvt|inc|company|winery|brewery|distillery)\b", re.I)
PLACE = re.compile(r"\b(maharashtra|karnataka|punjab|haryana|gujarat|kerala|goa|nashik|"
                   r"bengaluru|bangalore|mumbai|delhi|london|scotland|england|ireland|"
                   r"california|napa|sonoma|new york|united states|united kingdom|"
                   r"south africa|new zealand|new delhi)\b", re.I)
NOT_A_NAME = re.compile(r"\b(privacy|cookie|terms|policy|contact|about|home|read more|"
                        r"our team|the team|learn more|sign up|log in|all rights)\b", re.I)


# Team pages often stack the title above the name, so a capture reaches back
# through the role and returns "International Business Sanjeev Banga". The
# name is the trailing part; these are the words that mean the rest is title.
ROLE_WORD = re.compile(r"^(international|business|operations|marketing|sales|technical|"
                       r"finance|corporate|commercial|global|regional|executive|senior|"
                       r"deputy|assistant|joint|group|chief|head|vice|managing)$", re.I)


def trim_role_prefix(s: str) -> str:
    parts = " ".join(s.split()).split()
    while len(parts) > 2 and ROLE_WORD.fullmatch(parts[0]):
        parts.pop(0)
    return " ".join(parts)


def looks_like_a_name(s: str) -> bool:
    s = " ".join(s.split()).strip()
    if NOT_A_NAME.search(s) or STOPWORD.search(s) or PLACE.search(s):
        return False
    parts = s.split()
    if not 2 <= len(parts) <= 4:
        return False
    # Every token capitalised and alphabetic; initials such as "N.R." allowed.
    return all(re.fullmatch(r"(?:[A-Z][a-z'’]{1,}|[A-Z]\.?){1}", p) for p in parts)


def fetch(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(500_000).decode("utf-8", "ignore")


def text_of(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<br\s*/?>|</(p|div|li|h\d|td)>", "\n", html, flags=re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    return htmllib.unescape(re.sub(r"[ \t]+", " ", html))


def people_from(text: str) -> list[dict]:
    out, seen = [], set()
    for i, rx in enumerate(PATTERNS):
        for m in rx.finditer(text):
            name, role = (m.group(1), m.group(2)) if i == 0 else (m.group(2), m.group(1))
            name = trim_role_prefix(name.strip(" ,-–—|:"))
            role = " ".join(role.split()).strip(" ,-–—|:")
            if not looks_like_a_name(name) or len(role) > 60:
                continue
            if STOPWORD.search(role) and not re.match(TITLE, role, re.I):
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append({"name": name, "role": role})
    return out[:8]


def harvest(url: str) -> dict:
    base = url.rstrip("/")
    for path in PATHS:
        try:
            people = people_from(text_of(fetch(base + path)))
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError):
            continue
        if people:
            return {"people": people, "source": base + path}
    return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--region")
    ap.add_argument("--max-tier", type=int, default=2)
    args = ap.parse_args()

    rows = json.loads(SRC.read_text())
    todo = [r for r in rows
            if r.get("url") and r["tier"] <= args.max_tier and not r.get("site_people")
            and (not args.region or r["region"] == args.region)]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(todo)} companies to check\n")

    today, hit = date.today().isoformat(), 0
    for r in todo:
        got = harvest(r["url"])
        if got:
            r["site_people"] = got["people"]
            r["site_people_source"] = got["source"]
            r["site_people_checked"] = today
            hit += 1
            who = "; ".join(f"{p['name']} ({p['role'][:26]})" for p in got["people"][:2])
            print(f"  + {r['company'][:34]:36} {who}")
        else:
            r["site_people_checked"] = today
    SRC.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
    print(f"\n{hit} companies with named leadership, {len(todo) - hit} without")
    return 0


if __name__ == "__main__":
    sys.exit(main())
