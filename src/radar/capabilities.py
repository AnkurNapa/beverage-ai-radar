"""Label what KIND of solution something is: IoT, AI, ERP, BI, ESG, consultancy.

A second axis alongside `themes.py`, not a replacement. A theme says which
business problem is being solved (Quality, Demand, Supply chain); a capability
says what the thing actually is. "Quality & inspection" covers both an inline
sensor array and a consultancy that audits your QC process, and you sell to
those two very differently.

Two deliberate differences from themes.py:

1. **Multi-label, not first-match-wins.** BarTrack is IoT and ERP and BI at
   once. Forcing one label would misfile most of the corpus.
2. **AI is labelled everywhere, despite being near-universal.** 164 of 178
   tracked vendors match an AI pattern, so as a filter it separates little.
   Suppressing it was tried and was worse: it left 61 vendors (34%) with no
   label at all, because AI was the only thing they matched. An uninformative
   label beats a blank row, and the `include_ai` flag stays available for
   callers that want the narrower view.

ponytail: keyword heuristic, same as themes. When something lands with no
label, add a pattern rather than reaching for a classifier.
"""

from __future__ import annotations

import re

IOT = "IoT & sensing"
AI = "AI & ML"
ERP = "ERP & systems of record"
BI = "BI & analytics"
ESG = "ESG & sustainability"
CONSULTING = "Consultancy & services"

CAPABILITY_RULES: list[tuple[str, str]] = [
    (
        r"sensor|\biot\b|iiot|telemetr|hardware|device|probe|inline|historian|"
        r"scada|plc\b|gateway|instrument|meter|monitor(ing)? (tank|fermentation|temperature)",
        IOT,
    ),
    (
        r"\bai\b|artificial intelligence|machine learning|\bml\b|neural|deep learning|"
        r"computer vision|genai|generative|\bllm\b|predictive model|algorithm",
        AI,
    ),
    (
        r"\berp\b|inventory management|production management|batch record|"
        r"system of record|traceabilit|compliance report|excise|lot tracking|"
        r"work order|mes\b|recipe management",
        ERP,
    ),
    (
        r"\bbi\b|business intelligence|dashboard|analytics|reporting|"
        r"power ?bi|tableau|data warehouse|data platform|metrics|kpi",
        BI,
    ),
    (
        r"esg|sustainab|carbon|emission|net.?zero|decarbon|water (use|stewardship)|"
        r"energy (use|efficiency|saving)|waste|circular|scope [123]",
        ESG,
    ),
    (r"consult|advisory|\badvis|services firm|implementation partner|systems integrat", CONSULTING),
]

_COMPILED = [(re.compile(p, re.I), name) for p, name in CAPABILITY_RULES]

# Wedges map to capabilities directly: we know what we are selling, so there is
# no need to guess from prose the way the vendor side has to.
WEDGE_CAPABILITIES: list[tuple[str, list[str]]] = [
    (r"batch consistency|quality analytics", [IOT, AI, BI]),
    (r"demand forecast", [AI, BI]),
    (r"recipe|flavour|flavor", [AI]),
    (r"excise|compliance", [ERP]),
    (r"taproom|retail analytics", [BI]),
    (r"distillery process|process intelligence", [IOT, AI]),
    (r"vintage|harvest quality", [AI, BI]),
]
_WEDGE_COMPILED = [(re.compile(p, re.I), caps) for p, caps in WEDGE_CAPABILITIES]

ALL = [IOT, AI, ERP, BI, ESG, CONSULTING]


def of_text(text: str | None, include_ai: bool = True) -> list[str]:
    """Every capability the text supports, in a stable order.

    `include_ai=False` for the vendor corpus, where an AI label is true of
    almost every row and therefore carries no information.
    """
    t = text or ""
    found = [name for rx, name in _COMPILED if rx.search(t)]
    if not include_ai:
        found = [c for c in found if c != AI]
    return [c for c in ALL if c in found]


def of_company(company: dict) -> list[str]:
    """Vendor rows: read the use case plus the description."""
    text = f"{company.get('ai_use_case') or ''} {company.get('short_description') or ''}"
    return of_text(text)


def of_prospect(row: dict) -> list[str]:
    """Prospect rows: the wedge says what we would sell them.

    Falls back to reading pain and segment when a wedge does not match a known
    pattern, so a hand-written or re-verified row still gets labelled.
    """
    caps: list[str] = []
    for rx, mapped in _WEDGE_COMPILED:
        if rx.search(row.get("wedge") or ""):
            caps += mapped
    if not caps:
        # Company name is part of the fallback text: channel-partner rows carry
        # the signal in the name ("Beverage consultancies (First Key, Tulleeho)")
        # rather than in the wedge, and were coming back unlabelled.
        caps = of_text(f"{row.get('company') or ''} {row.get('wedge') or ''} "
                       f"{row.get('pain') or ''} {row.get('segment') or ''}")
    # ESG is orthogonal to the wedge: a decarbonisation mandate is a buying
    # trigger regardless of which wedge answers it. The SWA's net-zero-by-2040
    # commitment is exactly this, and it is the live opener in Scotch.
    esg_text = f"{row.get('pain') or ''} {row.get('segment') or ''}"
    if ESG not in caps and re.search(_COMPILED[4][0], esg_text):
        caps.append(ESG)
    return [c for c in ALL if c in caps]
