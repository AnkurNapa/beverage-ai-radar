"""Beverage-native vendors versus horizontal vendors that also serve beverage.

Both belong on the radar: a brewery evaluating a manufacturing data platform
needs to know FuturMaster and Factbird exist. But a reader asking "who builds
AI *for drinks*" is asking a narrower question, and mixing the two answers
makes the landscape look bigger and less specific than it is.

So they are labelled, not removed. The judgement is whether the company's
product is BUILT for beverage or merely SOLD into it.
"""

from __future__ import annotations

import re

NATIVE = "beverage-native"
HORIZONTAL = "horizontal"

BEVERAGE = re.compile(
    # Plurals matter: \bwine\b does not match "wines", which is how most of
    # these words actually appear in a description.
    r"brew|beer|malt|\bhops?\b|winer|\bwines?\b|vine|viticult|distill|whisk|spirit|"
    r"bevera|drink|cider|ferment|barrel|cask|\bkegs?\b|taproom|sake|tequila|\brums?\b|"
    r"\bgins?\b|vodka|grape|harvest|cellar|vintage|sommelier|alcohol|abv|"
    r"carlsberg|heineken|diageo|pernod|ab ?inbev|anheuser|molson|constellation",
    re.I,
)


def scope_of(company: dict) -> str:
    """Native when the beverage signal appears in what the product IS."""
    text = f"{company.get('name') or ''} {company.get('ai_use_case') or ''} " \
           f"{company.get('short_description') or ''}"
    return NATIVE if BEVERAGE.search(text) else HORIZONTAL
