"""Rough organisation size, derived only from signals the data actually carries.

There is no employee count anywhere in this corpus, so size is inferred, and
the inference has to be honest about its own limits. funding_stage is present
on 39 of 189 rows and total_raised on 18, so funding alone would leave most of
the landscape unlabelled. Three further signals help:

  - company_type "individual", which is unambiguous: one person.
  - a curated list of groups that are multinational by public fact, not by
    guesswork. Diageo's size is not in dispute.
  - size language in the company's own description ("global leader",
    "startup"), which is weak on its own and used only as a fallback.

Anything the signals do not reach returns UNKNOWN rather than a guess. A wrong
size on a card is worse than a blank one: it invites a reader to skip a company
for a reason that was invented.
"""

from __future__ import annotations

import re

MICRO = "micro"                  # solo builders and one-person shops
SMALL = "small"                  # seed stage, early startups
MID = "mid"                      # Series A/B, established SMEs
LARGE = "large"                  # Series C+, big private firms
MULTINATIONAL = "multinational"  # global groups, listed majors
UNKNOWN = "unknown"

ORDER = [MICRO, SMALL, MID, LARGE, MULTINATIONAL, UNKNOWN]

# Multinational by public fact. Kept explicit rather than inferred: these are
# checkable claims, and a regex over "global" would sweep in every startup
# that describes its ambitions.
MULTINATIONALS = re.compile(
    r"\b(ab ?inbev|anheuser|heineken|carlsberg|diageo|pernod ricard|molson coors|"
    r"asahi|kirin|suntory|sapporo|constellation brands|brown-?forman|bacardi|"
    r"treasury wine|thai ?bev|campari|r[eé]my cointreau|william grant|edrington|"
    r"united spirits|united breweries|radico|allied blenders|ambev|grupo modelo|"
    r"siemens|microsoft|sap\b|oracle|schneider electric|honeywell|abb\b|"
    r"krones|gea\b|alfa laval|tetra pak|bosch|danfoss|endress|anton paar|"
    r"nestl[eé]|unilever|pepsi|coca[- ]cola|cargill|kerry group|dsm|givaudan|"
    r"iff\b|symrise|firmenich|antares vision|thermo fisher|agilent|shimadzu)\b",
    re.I)

BIG_LANG = re.compile(r"\b(multinational|global (leader|group|company)|worldwide operations|"
                      r"fortune 500|listed on|publicly traded|group of companies)\b", re.I)
SMALL_LANG = re.compile(r"\b(startup|start-up|early[- ]stage|founded in 20(1[89]|2\d)|"
                        r"small team|two[- ]person|indie\b|bootstrapped)\b", re.I)

_MONEY = re.compile(r"([\d.]+)\s*([MBK])", re.I)


def raised_usd_millions(total_raised: str | None) -> float | None:
    """Parse '$12.4M', 'EUR 960K', '$1.2B' to millions. Currency is ignored:
    at this resolution the euro/dollar gap does not move a company between
    size bands, and pretending to convert would imply a precision we lack."""
    if not total_raised:
        return None
    m = _MONEY.search(total_raised)
    if not m:
        return None
    v, unit = float(m.group(1)), m.group(2).upper()
    return v * {"K": 0.001, "M": 1.0, "B": 1000.0}[unit]


def size_of(company: dict) -> str:
    name = company.get("name") or ""
    desc = company.get("short_description") or ""
    ctype = (company.get("company_type") or "").lower()
    stage = (company.get("funding_stage") or "").lower()

    if MULTINATIONALS.search(name):
        return MULTINATIONAL
    if "individual" in ctype:
        return MICRO
    if BIG_LANG.search(desc):
        return MULTINATIONAL

    raised = raised_usd_millions(company.get("total_raised"))
    if raised is not None:
        if raised >= 100:
            return LARGE
        if raised >= 15:
            return MID
        if raised >= 2:
            return SMALL
        return MICRO

    if "public" in stage or "listed" in stage:
        return LARGE
    if re.search(r"series [c-z]", stage):
        return LARGE
    if re.search(r"series [ab]\b", stage):
        return MID
    if "seed" in stage or "bootstrap" in stage or "pre-seed" in stage:
        return SMALL

    if SMALL_LANG.search(desc):
        return SMALL
    return UNKNOWN
