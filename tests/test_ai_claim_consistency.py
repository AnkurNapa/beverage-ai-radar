"""An entry that says it makes no AI claim must not be published as an AI vendor.

The radar's whole value is that its claims are checked, so the one thing it
must never do is assert AI a vendor does not. That used to be possible by
accident rather than by intent: AIMaturity had no member meaning "checked, and
there is no AI claim", so honestly-written no-AI entries were filed under
SHIPPING - which the dashboard renders, and the About page describes, as
shipping AI. 114 companies were published that way, AB InBev and Ekos among
them, while their own descriptions said the opposite.

AIMaturity.NONE now expresses that state. This test keeps the description and
the field agreeing, so a future seed edit or scout merge cannot reopen the gap.
"""

import json
import re
from pathlib import Path

SEED = Path(__file__).resolve().parents[1] / "data" / "seed.json"

# The vendor was checked and claims no AI/ML.
NO_CLAIM = re.compile(
    r"\b(no|makes no|carries no|with no)\s+"
    r"(substantiated\s+|explicit\s+|public\s+|verifiable\s+|specific\s+)?"
    r"(ai|a\.i\.|machine[- ]learning|ml)\b[^.]{0,40}\bclaim"
    r"|\bno ai claim"
    r"|\bdoes not claim (any )?(ai|machine learning)"
    r"|\bnot an ai (company|vendor)"
    r"|\bno substantiated (ml|ai)"
    r"|no ai or data[- ]product claim",
    re.I,
)

# Strip the denial itself before looking for an asserted technique, so
# ai_use_case "no ai claim; brewery ERP" is not read as claiming AI.
DENIAL = re.compile(
    r"no (substantiated |explicit |public |verifiable )?"
    r"(ai|machine[- ]learning|ml)\b[^;,]*",
    re.I,
)
TECHNIQUE = re.compile(
    r"\b(ai|machine learning|computer vision|neural|llm|genai|predictive"
    r"|forecast(ing)?|agentic|recommendation engine|anomaly detection)\b",
    re.I,
)

AI_GRADES = {"research", "pilot", "shipping"}

# Entries whose ai_use_case asserts a real technique while the description
# disclaims one. Each is a genuine contradiction needing a human read, not a
# mechanical flip, so they are listed rather than silently coerced.
KNOWN_CONFLICTS = {
    "Anheuser-Busch InBev",
    "Buhler Group",
    "Suntory Global Spirits",
    "CFT Group",
    "Whiskey House of Kentucky",
    "Yakima Chief Hops",
    "eoStar",
    "Linc (WineLINC)",
    "Weather Trends International (weathertrends360)",
}


def _rows():
    return json.loads(SEED.read_text())


def test_no_ai_claim_entries_are_not_graded_as_ai():
    offenders = []
    for row in _rows():
        name = row.get("name", "?")
        if name in KNOWN_CONFLICTS:
            continue
        if not NO_CLAIM.search(str(row.get("short_description", ""))):
            continue
        if TECHNIQUE.search(DENIAL.sub("", str(row.get("ai_use_case") or ""))):
            continue
        if row.get("ai_maturity") in AI_GRADES:
            offenders.append(f"{name} -> ai_maturity={row.get('ai_maturity')}")

    assert not offenders, (
        "These entries state they make no AI claim but are published with an "
        "AI maturity grade, so the dashboard presents them as AI vendors. Set "
        'ai_maturity to "none", or correct the description if the entry really '
        "does claim AI:\n  " + "\n  ".join(sorted(offenders))
    )


def test_known_conflicts_still_conflict():
    """Keep the exemption list honest.

    A name here is a promise that the entry still contradicts itself. Once one
    is resolved it must leave the list, or the list quietly becomes a place
    where real problems hide.
    """
    by_name = {r.get("name"): r for r in _rows()}
    stale = []
    for name in KNOWN_CONFLICTS:
        row = by_name.get(name)
        if row is None:
            stale.append(f"{name} (no longer in seed)")
            continue
        disclaims = NO_CLAIM.search(str(row.get("short_description", "")))
        asserts = TECHNIQUE.search(DENIAL.sub("", str(row.get("ai_use_case") or "")))
        if not (disclaims and asserts):
            stale.append(f"{name} (resolved)")

    assert not stale, (
        "KNOWN_CONFLICTS entries that no longer conflict - remove them from "
        "the list:\n  " + "\n  ".join(sorted(stale))
    )
