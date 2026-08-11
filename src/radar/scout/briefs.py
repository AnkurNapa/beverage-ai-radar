"""Render one scout brief per surface from the current coverage gaps.

The skip list and the gap section are generated from the store on every run, so
they cannot rot the way a hand-maintained prompt does. The scoring rules below
are fixed policy: they exist because real sweeps produced inconsistent calls
without them.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

SCHEMA_BLOCK = """{
  "name": "...",
  "domain": "example.com",
  "hq_location": "City, Country",
  "founded_year": 2015,
  "vertical": "beer" | "whiskey" | "wine" | "multiple" | "non_alcoholic",
  "ai_use_case": "short lowercase phrase",
  "ai_maturity": "none" | "research" | "pilot" | "shipping",
  "funding_stage": "...",
  "total_raised": "...",
  "short_description": "2-4 factual sentences. What it does, who it serves in beer/whiskey/wine, what the AI actually is.",
  "source_urls": ["https://vendor-site", "https://second-source"],
  "first_seen": "YYYY-MM-DD",
  "last_seen": "YYYY-MM-DD",
  "key_people": "Name (Role)",
  "people": [{"name": "...", "role": "...", "linkedin": "https://www.linkedin.com/in/..."}]
}"""

# Policy that exists because scouts disagreed on real sweeps. Keep it explicit.
SCOPE_RULES = """## Scope rules

1. **Operators count.** A brewer, distiller or winery that runs real AI in production is in
   scope, not just vendors selling AI. The database already tracks Carlsberg, AB InBev,
   Heineken and Kirin on exactly this basis. Include the operator when the AI is theirs and
   named; skip it when the company is merely a customer of someone else's product.
2. **Retailers and pure marketplaces are out of scope** unless the AI is their own product.
3. **No real ML is a finding, not a disqualifier.** If a company is a system of record, a
   sensor vendor or plain BI, include it when it matters to the beverage data landscape and
   say plainly in short_description that it makes no AI claim. Never inflate marketing
   language into a machine-learning claim. Inventing capability is the one unforgivable error.
   When you write that disclaimer you MUST also set `"ai_maturity": "none"`, which means
   "checked, and there is no AI claim". The other three grades all mean the company does
   claim AI, and the dashboard renders them that way: grading an honest no-AI entry
   "shipping" publishes a claim the company never made. This sweep produced 49 such
   contradictions in one pass because "none" was missing from the schema, so treat the
   description and this field as one decision, never two.
4. **Blocked is not rejected.** If a site returns 403, is Cloudflare-walled or otherwise
   unfetchable, do NOT silently drop it. Add it to the "blocked" array of your output file
   with the URL and what you could establish, so a browser-equipped pass can finish the job.
"""

VERIFY_RULES = """## Verification rules (strict)

1. Every company MUST be verified by fetching its OWN website. No entry without a working
   domain and at least 2 source_urls, one of which is the vendor's own site.
2. Quality over quantity. Eight solid entries beat twenty thin ones. Zero is an acceptable
   answer if nothing verifies.
3. Plain ASCII punctuation only. No em dashes, en dashes or curly quotes anywhere.
4. last_seen is the date of the most recent evidence you actually saw. Never invent
   precision: omit any field you could not verify rather than guessing it.
"""


def _gap_lines(gaps: list[dict]) -> str:
    if not gaps:
        return "No significant gaps detected. Prioritise fresh evidence for existing entries.\n"
    lines = []
    for g in gaps:
        lines.append(f"- **{g['axis']}: {g['value']}** ({g['count']} tracked). {g['reason']}")
        if g.get("examples"):
            lines.append(f"  - examples: {', '.join(g['examples'])}")
    return "\n".join(lines) + "\n"


def render_brief(
    surface: dict,
    gaps: list[dict],
    existing: list[str],
    out_dir: Path,
    today: date | None = None,
) -> str:
    today = today or date.today()
    skip_path = Path(out_dir) / "existing_names.txt"
    finds_path = Path(out_dir) / "finds" / f"find_{surface['id']}.json"
    return f"""# Scout brief: {surface['label']}

Generated {today.isoformat()}. You are one of several scouts growing a curated database of
companies applying AI and data to BEER, WHISKEY and WINE (the Beverage-AI Radar).

## Your assigned surface

{surface['label']}.

{surface['hint']}

{f"Note from previous sweeps: {surface['note']}" if surface.get('note') else ''}

## Current coverage gaps (what this sweep is for)

These are the thinnest slices of the database right now. Weight your search toward the ones
your surface can plausibly fill. Do not force a bad entry to fill a gap.

{_gap_lines(gaps)}
## Already tracked (skip these)

{len(existing)} companies are already in the database. Read `{skip_path}` and skip anything
there, matching on company name OR domain. Other scouts are sweeping other surfaces in
parallel, so an overlap is expected and harmless: the merge step dedupes on name and domain.

{SCOPE_RULES}
{VERIFY_RULES}
## Output

Write a JSON object to `{finds_path}`:

```json
{{
  "surface": "{surface['id']}",
  "companies": [ ... ],
  "blocked": [{{"name": "...", "url": "...", "reason": "403", "what_you_established": "..."}}],
  "rejected": [{{"name": "...", "reason": "..."}}]
}}
```

Each object in `companies` uses exactly this schema, omitting unverified fields:

```json
{SCHEMA_BLOCK}
```

Your final message: the count and a one-line list of names. Do not paste the JSON.
"""


def render_briefs(
    surfaces: list[dict],
    gaps: list[dict],
    existing: list[str],
    out_dir: Path,
    today: date | None = None,
) -> list[Path]:
    out_dir = Path(out_dir)
    (out_dir / "briefs").mkdir(parents=True, exist_ok=True)
    (out_dir / "finds").mkdir(parents=True, exist_ok=True)
    (out_dir / "existing_names.txt").write_text("\n".join(sorted(existing)) + "\n")

    written = []
    for surface in surfaces:
        path = out_dir / "briefs" / f"{surface['id']}.md"
        path.write_text(render_brief(surface, gaps, existing, out_dir, today))
        written.append(path)
    return written


def load_surfaces(path: Path) -> list[dict]:
    return json.loads(Path(path).read_text())
