"""Group a country into the same regions the prospect list uses.

Companies carried a country and prospects carried a region, so the two tabs
could not be compared and the country dropdown ran to 31 entries. One
vocabulary for both.
"""

from __future__ import annotations

REGIONS = {
    "North America": ["United States", "Canada", "Mexico"],
    "Latin America": ["Brazil", "Chile", "Argentina", "Peru", "Colombia",
                      "Dominican Republic", "Uruguay"],
    "UK & Ireland": ["United Kingdom", "Ireland"],
    "Germany & DACH": ["Germany", "Austria", "Switzerland"],
    "Nordics": ["Sweden", "Norway", "Denmark", "Finland", "Iceland"],
    "Europe (other)": ["France", "Italy", "Spain", "Portugal", "Netherlands",
                       "Belgium", "Luxembourg", "Poland", "Czechia", "Slovakia",
                       "Greece", "Hungary", "Romania", "Estonia", "Latvia",
                       "Lithuania", "Slovenia", "Croatia", "Serbia", "Bulgaria"],
    "Africa": ["South Africa", "Kenya", "Nigeria", "Tanzania", "Namibia",
               "Morocco", "Egypt", "Ethiopia"],
    "Middle East": ["Israel", "United Arab Emirates", "Saudi Arabia", "Turkey",
                    "Lebanon", "Jordan", "Bahrain"],
    "India": ["India"],
    "Southeast Asia": ["Vietnam", "Thailand", "Singapore", "Malaysia",
                       "Indonesia", "Philippines", "Cambodia"],
    "Greater China": ["China", "Taiwan", "Hong Kong"],
    "Japan": ["Japan"],
    "Korea": ["Korea"],
    "Australia & NZ": ["Australia", "New Zealand"],
}
_LOOKUP = {c: r for r, cs in REGIONS.items() for c in cs}


def region_of(country: str | None) -> str:
    """Unmapped countries return "" rather than a catch-all bucket: a wrong
    region is worse than none, and an empty value simply drops out of filters."""
    return _LOOKUP.get((country or "").strip(), "")
