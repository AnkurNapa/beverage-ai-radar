"""Country names, normalised once.

`hq_location` is free text from many sources, so the same country arrives under
several spellings. Left alone, "USA" and "United States" become two entries in
the country filter, two slices in the gap analysis and two dots on the map, each
holding half the real count. Everything that reads a country routes through
`country_of` so there is one answer.
"""

from __future__ import annotations

ALIASES = {
    "usa": "United States",
    "u.s.": "United States",
    "u.s.a.": "United States",
    "us": "United States",
    "united states of america": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "great britain": "United Kingdom",
    "england": "United Kingdom",
    "scotland": "United Kingdom",
    "wales": "United Kingdom",
    "northern ireland": "United Kingdom",
    "deutschland": "Germany",
    "holland": "Netherlands",
    "the netherlands": "Netherlands",
    "republic of ireland": "Ireland",
    "prc": "China",
    "people's republic of china": "China",
    "south korea": "Korea",
    "republic of korea": "Korea",
    "uae": "United Arab Emirates",
}

UNKNOWN = "unknown"


def normalise(name: str | None) -> str:
    n = (name or "").strip()
    if not n:
        return UNKNOWN
    return ALIASES.get(n.lower(), n)


def country_of(hq_location: str | None) -> str:
    """Last comma-separated component of an hq_location, normalised."""
    loc = (hq_location or "").strip()
    if not loc:
        return UNKNOWN
    return normalise(loc.split(",")[-1])
