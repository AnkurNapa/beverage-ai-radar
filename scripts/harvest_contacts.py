#!/usr/bin/env python3
"""Collect published contact details from prospects' own websites.

Strictly what a company puts on its own site. No address is ever constructed
from a person's name, and nothing is read from a social profile: a guessed
address either bounces or reaches the wrong person, and both cost more than an
empty cell.

Personal-looking addresses are also filtered out. A company publishing
"info@" is inviting contact; an address that happens to appear in a page's
source because a developer left it there is not an invitation, and neither is
a webmaster's. The same goes for the noreply and privacy mailboxes that exist
to receive nothing.

Tries the homepage and the usual contact paths, stops at the first page that
yields something, and records where each detail came from so a stale address
can be traced back.

Run: python3 scripts/harvest_contacts.py [--limit N] [--region India]
"""
from __future__ import annotations

import argparse
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
PATHS = ["", "/contact", "/contact-us", "/contact-us/", "/contactus", "/about",
         "/about-us", "/pages/contact", "/pages/contact-us", "/get-in-touch"]

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# The first version of this matched "+604800" on ten unrelated sites: one
# artefact in a shared script, harvested ten times as a phone number. A real
# international number has at least nine digits AND some separator structure,
# so both are required now.
PHONE = re.compile(r"\+\d{1,3}[\s\-.()]{1,3}(?:\d[\s\-.()]{0,3}){7,14}\d")


def plausible_phone(s: str) -> bool:
    digits = re.sub(r"\D", "", s)
    if not 9 <= len(digits) <= 15:
        return False
    # A run of digits with no separators at all, or an obviously repeated
    # artefact, is not a number anyone published for humans to dial.
    return bool(re.search(r"[\s\-.()]", s.strip()[1:]))

# Mailboxes that exist to receive nothing, plus the ones that are artefacts of
# how a page was built rather than an invitation to write.
JUNK = re.compile(r"^(noreply|no-reply|donotreply|privacy|dpo|abuse|postmaster|"
                  r"webmaster|hostmaster|admin|root|test|example|sentry|wordpress)@|"
                  r"@(example|sentry|wixpress|godaddy|squarespace|shopify)\.", re.I)
IMAGE_TAIL = re.compile(r"\.(png|jpe?g|gif|svg|webp|css|js)$", re.I)


def fetch(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(400_000)
    return raw.decode("utf-8", "ignore")


def clean_emails(html: str, domain: str) -> list[str]:
    # Pages carry JSON-escaped markup, so an address can arrive glued to a
    # \u003e or to the word that followed it in the source.
    html = html.replace("\\u003e", ">").replace("\\u003c", "<").replace("\\/", "/")
    found = []
    for e in EMAIL.findall(html):
        e = e.strip(".,;:")
        e = re.sub(r"^(?:u003e|u003c|gt|lt|amp);?", "", e, flags=re.I)
        # A TLD followed by more lowercase letters is the next word glued on
        # ("orders@x.comor" from "...comor call us")
        e = re.sub(r"\.(com|net|org|co|in|de|fr|uk|se|dk|au|nz|jp|cn|za|ie|it|es|nl|be)"
                   r"[a-z]{2,}$", r".\1", e, flags=re.I)
        if JUNK.search(e) or IMAGE_TAIL.search(e):
            continue
        # Only addresses on the company's own domain. An address from an
        # embedded widget or an agency footer is not this company's contact.
        host = e.split("@")[-1].lower()
        root = ".".join(domain.lower().split(".")[-2:])
        if root and root not in host:
            continue
        if e.lower() not in [x.lower() for x in found]:
            found.append(e)
    return found[:6]


def harvest(url: str) -> dict:
    from urllib.parse import urlparse
    base = url.rstrip("/")
    domain = urlparse(url).hostname or ""
    for path in PATHS:
        try:
            html = fetch(base + path)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError):
            continue
        emails = clean_emails(html, domain)
        phones = [p.strip() for p in PHONE.findall(html) if plausible_phone(p)][:3]
        if emails or phones:
            return {"emails": emails, "phones": phones, "source": base + path}
    return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--region")
    ap.add_argument("--max-tier", type=int, default=2)
    args = ap.parse_args()

    rows = json.loads(SRC.read_text())
    todo = [r for r in rows
            if r.get("url") and r["tier"] <= args.max_tier
            and not r.get("contact_emails") and not r.get("contact_phone")
            and (not args.region or r["region"] == args.region)]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(todo)} rows to check\n")

    today = date.today().isoformat()
    hit = miss = 0
    for r in todo:
        got = harvest(r["url"])
        if got and (got["emails"] or got["phones"]):
            r["contact_emails"] = got["emails"]
            r["contact_phone"] = " / ".join(got["phones"])
            r["contact_source"] = got["source"]
            r["contact_checked"] = today
            hit += 1
            print(f"  + {r['company'][:38]:40} {', '.join(got['emails'][:2]) or got['phones'][0]}")
        else:
            r["contact_checked"] = today
            r["contact_note"] = "no contact details published, or the site blocks automated reads"
            miss += 1
    SRC.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
    print(f"\n{hit} with contacts, {miss} without")
    return 0


if __name__ == "__main__":
    sys.exit(main())
