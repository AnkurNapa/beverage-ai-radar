"""Validate and merge scout findings into the human-verified seed.

The seed's whole value is that a human checked it, so everything an LLM found
passes these gates first. Anything rejected goes to a quarantine file with a
reason: silently dropping a finding is how you lose a real company to a 403.
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

REQUIRED = ("name", "vertical", "short_description", "source_urls", "last_seen")
NEAR_DUPLICATE_RATIO = 0.87
# Enough of the public suffix list to cover where beverage companies actually
# register. Not exhaustive by design: a missing entry costs a false duplicate,
# which the quarantine file makes visible, so this can grow as sweeps hit them.
_MULTI_SUFFIXES = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk", "ltd.uk", "plc.uk",
    "com.au", "net.au", "org.au", "co.nz", "com.br", "com.ar", "com.mx",
    "co.za", "co.jp", "ne.jp", "or.jp", "co.in", "net.in", "org.in",
    "com.cn", "com.sg", "co.kr", "com.tr", "com.pl", "co.il", "com.hk",
    "com.tw", "com.my", "co.th", "com.ua", "com.ph", "co.id", "com.vn",
    "co.at", "com.es", "com.pt", "com.pe", "com.co", "com.uy", "com.ec",
}
# Below this, one name being a substring of another is coincidence, not
# identity: "ies" sits inside "international wineries for climate action".
CONTAINMENT_MIN_OVERLAP = 0.6


def norm_name(s: str | None) -> str:
    """Lowercase, strip punctuation and any parenthetical product alias.

    Scouts return the same company under its product name ("Encompass
    Technologies (vintrace)"), so the alias has to come off before comparing.
    """
    s = re.sub(r"\(.*?\)", " ", s or "")
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def norm_domain(s: str | None) -> str:
    if not s:
        return ""
    host = urlparse(s if "//" in s else f"//{s}", scheme="http").hostname or s
    host = host.lower().removeprefix("www.")
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    # Two-label public suffixes: without this, kegtracker.co.uk and node4.co.uk
    # both reduce to "co.uk" and every British company collides with every
    # other. That silently ate 4 real companies in the 2026-08-04 sweep.
    if ".".join(parts[-2:]) in _MULTI_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _sources_support_domain(company: dict) -> bool:
    """At least 2 sources, one of them on the claimed domain.

    The single strongest anti-hallucination check: a fabricated company rarely
    survives having to name its own site among its evidence.
    """
    urls = company.get("source_urls") or []
    if len(urls) < 2:
        return False
    domain = norm_domain(company.get("domain"))
    if not domain:
        return False
    return any(norm_domain(u) == domain for u in urls)


def _near_duplicate(name: str, known: list[str]) -> str | None:
    n = norm_name(name)
    for other in known:
        if not n or not other:
            continue
        if n == other:
            return other
        short, long_ = (n, other) if len(n) <= len(other) else (other, n)
        # Bare containment is far too eager on short names. "istill" is a
        # substring of "circumstance distillery"; they are unrelated firms.
        if short in long_ and len(short) / len(long_) >= CONTAINMENT_MIN_OVERLAP:
            return other
        if SequenceMatcher(None, n, other).ratio() >= NEAR_DUPLICATE_RATIO:
            return other
    return None


def _distinct_domains(company: dict, hit_name: str, seed: list[dict]) -> bool:
    """True when a name-similar row is provably a different company.

    Names one edit apart are not evidence of identity when the two rows name
    different websites: FermentIQ (ferment-iq.com) is brewery software and
    Fermentis (fermentis.com) is a Lesaffre yeast brand, and a 0.89 name
    similarity nearly merged them.
    """
    mine = norm_domain(company.get("domain"))
    if not mine:
        return False
    theirs = {
        norm_domain(r.get("domain"))
        for r in seed
        if norm_name(r.get("name")) == hit_name and r.get("domain")
    }
    return bool(theirs) and mine not in theirs


def merge(
    seed: list[dict],
    incoming: list[dict],
    reachable=None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Returns (seed, added, quarantined).

    reachable(domain) -> True | False | None. None means blocked rather than
    dead, which is quarantined for a browser pass instead of being rejected.
    """
    names = [norm_name(c["name"]) for c in seed]
    domains = {norm_domain(c.get("domain")) for c in seed if c.get("domain")}
    added, quarantined = [], []

    def reject(company, reason, state="rejected"):
        quarantined.append({"name": company.get("name", "?"), "reason": reason, "state": state})

    for c in incoming:
        missing = [f for f in REQUIRED if not c.get(f)]
        if missing:
            reject(c, f"missing required fields: {', '.join(missing)}")
            continue
        if norm_name(c["name"]) in names:
            reject(c, "duplicate name", "duplicate")
            continue
        if c.get("domain") and norm_domain(c["domain"]) in domains:
            reject(c, f"duplicate domain {norm_domain(c['domain'])}", "duplicate")
            continue
        if not _sources_support_domain(c):
            reject(c, "needs 2+ sources with one on its own domain")
            continue
        hit = _near_duplicate(c["name"], names)
        if hit and _distinct_domains(c, hit, seed):
            hit = None
        if hit:
            reject(c, f"near-duplicate of {hit!r}", "duplicate")
            continue
        if reachable is not None:
            state = reachable(c["domain"])
            if state is None:
                reject(c, "domain blocked (403/Cloudflare); needs a browser pass", "blocked")
                continue
            if state is False:
                reject(c, "domain unreachable")
                continue

        names.append(norm_name(c["name"]))
        if c.get("domain"):
            domains.add(norm_domain(c["domain"]))
        seed.append(c)
        added.append(c)

    return seed, added, quarantined


def load_finds(paths: list[str | Path]) -> list[dict]:
    """Read scout output files, tagging each company with the surface that found it.

    Accepts both shapes: the {surface, companies, blocked} object the briefs ask
    for, and a bare array (what the first hand-run sweep produced).
    """
    out = []
    for p in paths:
        data = json.loads(Path(p).read_text())
        if isinstance(data, dict):
            surface = data.get("surface") or Path(p).stem.removeprefix("find_")
            companies = data.get("companies", [])
        else:
            surface = Path(p).stem.removeprefix("find_")
            companies = data
        for c in companies:
            c.setdefault("discovered_by", f"scout:{surface}")
            c.setdefault("verified", False)
            out.append(c)
    return out
