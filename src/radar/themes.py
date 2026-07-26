"""Bucket the free-text ai_use_case into a handful of business themes.

ai_use_case is free text (~40 distinct strings), useless as a breakdown. First
matching rule wins, so order specific before general. These rules used to live
in dashboard/app.js; they moved here so the gap analysis and the dashboard
cannot drift apart. json_export writes the computed theme into data.json and
the dashboard just reads it.

ponytail: keyword heuristic. When a new use case lands in "Other", add a rule.
"""

from __future__ import annotations

import re

THEME_RULES: list[tuple[str, str]] = [
    (
        r"vineyard|disease|yield|robot|germination|malting|barley|crop|viticultur|"
        r"vine |grape|sap flow|water status|maturation prediction",
        "Agriculture & crop",
    ),
    (r"quality|computer vision|inspection|traceability|authentic|counterfeit", "Quality & inspection"),
    (r"sensory|flavor|flavour|recipe|taste|preference|aroma|blend|formulation", "Sensory & recipe"),
    (r"consumer|trend|recommendation|personaliz|insight|sentiment|purchase intent", "Consumer & personalization"),
    # Market data is its own business: auction feeds, cask valuation and price
    # discovery are what the whiskey and fine wine lanes actually sell.
    (r"market data|auction|valuation|price data|exchange|market intelligence", "Market data & valuation"),
    (r"demand|forecast|pricing|sales|depletion|trade promotion|revenue", "Demand & pricing"),
    (r"supply chain|logistics|container|deposit return|inventory|cask management", "Supply chain"),
    (r"genai|marketing|product content|catalog", "GenAI & marketing"),
    (r"consult|advis", "Consulting"),
    # Compliance is its own business function, not a leftover: licensing,
    # excise, label approval and reporting sit on every producer and
    # distributor regardless of what they brew.
    (r"complian|licens|excise|regulat|permit|tax", "Compliance & licensing"),
    (
        r"fermentation|production|digital twin|cip\b|process|batch|maintenance|iiot|iot|line|"
        r"draft|operating system|worker|knowledge|workflow|data platform|assistant|agent|"
        r"sensor|historian|mes\b|oee|automation|analytics|bi\b|reporting|"
        r"ordering|invoice|taproom|point-of-sale|pos\b",
        "Process & operations",
    ),
]

_COMPILED = [(re.compile(pattern), name) for pattern, name in THEME_RULES]

OTHER = "Other"


def theme_of(ai_use_case: str | None) -> str:
    t = (ai_use_case or "").lower()
    for rx, name in _COMPILED:
        if rx.search(t):
            return name
    return OTHER


def all_themes() -> list[str]:
    """Every theme a company can be bucketed into, including the catch-all."""
    return [name for _, name in THEME_RULES] + [OTHER]
