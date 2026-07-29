"""Collapse the free-text wedge into the six things we actually sell.

Each sweep wrote the wedge in its own words, so 288 rows carry 80 distinct
strings: "Demand forecasting", "demand forecasting (SKU x region)", "Demand
forecasting with festival calendar" and so on. As a filter that is useless.
The canonical six are the offer ladder itself, so a row that matches none of
them is a row whose wedge nobody could act on.
"""

from __future__ import annotations

import re

BATCH = "Batch consistency"
DEMAND = "Demand forecasting"
RECIPE = "Recipe & flavour"
EXCISE = "Excise & compliance"
RETAIL = "Taproom & retail"
PROCESS = "Distillery process"
VINTAGE = "Vintage & harvest"
OTHER = "Other"

ORDER = [BATCH, DEMAND, RECIPE, EXCISE, RETAIL, PROCESS, VINTAGE, OTHER]

# First match wins, so the order IS the priority. Specific before general:
# many rows read "distillery process intelligence, then recipe", and the wedge
# is what you lead with, not what you mention second. "flavour" and "sensory"
# appear as a secondary note in a great many rows, so recipe sits last of the
# real wedges rather than claiming them all.
RULES = [
    (r"distillery process|process intelligence|cut point|cask|maturation", PROCESS),
    (r"vintage|harvest|viticultur|yield", VINTAGE),
    (r"excise|complian|regulat|licen", EXCISE),
    (r"taproom|retail analytic|pour|venue", RETAIL),
    (r"batch consistency|quality analytic|batch drift", BATCH),
    (r"demand forecast|forecasting", DEMAND),
    (r"recipe|flavour|flavor|aroma|sensory", RECIPE),
]
_C = [(re.compile(p, re.I), name) for p, name in RULES]


def wedge_of(text: str | None) -> str:
    t = text or ""
    for rx, name in _C:
        if rx.search(t):
            return name
    return OTHER
