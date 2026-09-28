"""People scout: find individuals applying AI and data to beer, whiskey and wine,
one region per agent, and gate what comes back before it reaches people_seed.json.

Mirrors the company scout (briefs.py + merge.py) but the evidence rule differs:
a person has no "own domain", so the check is two sources of which at least one
is NOT LinkedIn. A profile page is a claim the person makes about themselves;
a team page, a talk listing or a paper is somebody else confirming it.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from radar.scout.merge import norm_name

REQUIRED = ("name", "role", "company", "vertical", "short_description", "source_urls", "last_seen")
# Scouts have cited a search query as a source before; it proves nothing.
_SEARCH_HOSTS = ("bing.com", "google.", "duckduckgo.com", "search.brave.com", "yahoo.com")

SCHEMA_BLOCK = """{
  "name": "Full Name",
  "role": "Current title, Employer",
  "company": "Employer or own practice",
  "company_is_current": true,
  "location": "City, Country",
  "linkedin": "https://www.linkedin.com/in/<real-slug>" or null,
  "vertical": "beer" | "whiskey" | "wine" | "multiple",
  "verticals": ["beer", "wine"],
  "ai_use_case": "short lowercase phrase",
  "ai_maturity": "none" | "research" | "pilot" | "shipping",
  "short_description": "2-4 factual sentences: who they are, what AI or data work they did in beverages, where.",
  "source_urls": ["https://employer-team-page", "https://talk-or-paper-or-press"],
  "first_seen": "YYYY-MM-DD",
  "last_seen": "YYYY-MM-DD"
}"""

RULES = """## Who counts

1. A named individual doing AI, ML, data science, analytics or digital transformation work
   FOR beer, whiskey/spirits or wine: data leads at brewers, distillers and wineries,
   founders of beverage-AI startups, academics publishing ML on fermentation, grapes or
   sensory, consultants with a named beverage client, conference speakers on the topic.
2. The beverage link must be concrete and sourced. "Works in F&B tech" is not enough.
3. Senior or visible over junior: prefer people who lead, publish, speak or found.
4. Never invent a person, a role or a LinkedIn slug. Unknown LinkedIn is null.

## Evidence (the merge gate enforces this; entries that fail are thrown away)

1. At least 2 source_urls, and at least one must NOT be linkedin.com. Good independent
   sources: employer team or leadership page, conference speaker page, paper author list,
   press article, podcast episode page.
2. A search-results URL (bing, google, duckduckgo) is never a source.
3. short_description states only what the sources say. If the role may be past tense, say so
   there and set company_is_current to null. false prints "(former)" on the site, so use it
   only when a source says the person has left, and then put "Former" in the role.
4. Plain ASCII punctuation only. No em dashes, en dashes or curly quotes.
"""


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _linkedin_slug(url: str | None) -> str:
    m = re.search(r"linkedin\.com/in/([^/?#]+)", url or "")
    return m.group(1).lower() if m else ""


def _key(p: dict) -> tuple[str, str]:
    return norm_name(p.get("name")), norm_name(p.get("company"))


def _evidence_problem(p: dict) -> str | None:
    urls = p.get("source_urls") or []
    if any(any(s in _host(u) for s in _SEARCH_HOSTS) for u in urls):
        return "a search-results URL is not a source"
    if len(urls) < 2:
        return "needs 2+ sources"
    if all("linkedin.com" in _host(u) for u in urls):
        return "needs one source that is not linkedin"
    return None


def merge_people(
    seed: list[dict], incoming: list[dict]
) -> tuple[list[dict], list[dict], list[dict]]:
    """Returns (seed, added, quarantined). Dedupes on (name, company) and on LinkedIn slug."""
    keys = {_key(p) for p in seed}
    names = {k[0] for k in keys}
    slugs = {_linkedin_slug(p.get("linkedin")) for p in seed} - {""}
    added, quarantined = [], []

    def reject(p, reason, state="rejected"):
        quarantined.append({"name": p.get("name", "?"), "reason": reason, "state": state})

    for p in incoming:
        missing = [f for f in REQUIRED if not p.get(f)]
        if missing:
            reject(p, f"missing required fields: {', '.join(missing)}")
            continue
        slug = _linkedin_slug(p.get("linkedin"))
        if _key(p) in keys or (slug and slug in slugs):
            reject(p, "already tracked", "duplicate")
            continue
        if _key(p)[0] in names:
            reject(p, "same name as a tracked person, different employer", "review")
            continue
        problem = _evidence_problem(p)
        if problem:
            reject(p, problem)
            continue
        # false renders "(former)"; unless the role says so it is only "unconfirmed"
        role = (p.get("role") or "").lower()
        if p.get("company_is_current") is False and "former" not in role and "ex-" not in role:
            p = {**p, "company_is_current": None}
        keys.add(_key(p))
        names.add(_key(p)[0])
        if slug:
            slugs.add(slug)
        added.append(p)

    return seed + added, added, quarantined


def render_people_brief(
    surface: dict, existing: list[str], out_dir: Path, today: date | None = None
) -> str:
    today = today or date.today()
    out_dir = Path(out_dir)
    skip_path = out_dir / "people_skip.txt"
    finds_path = out_dir / "people_finds" / f"find_{surface['id']}.json"
    note = f"Note from previous sweeps: {surface['note']}\n" if surface.get("note") else ""
    return f"""# People scout brief: {surface["label"]}

Generated {today.isoformat()}. You are one of several scouts, each covering one region,
growing the People view of the Beverage-AI Radar: individuals applying AI and data to
BEER, WHISKEY and WINE.

## Your region

{surface["label"]}. {surface["hint"]}
{note}
## Already tracked (skip these)

{len(existing)} people are tracked. Read `{skip_path}` ("Name | Employer") and skip them.

{RULES}
## Output

Write a JSON object to `{finds_path}`:

```json
{{"surface": "{surface["id"]}", "people": [ ... ], "rejected": [{{"name": "...", "reason": "..."}}]}}
```

Each object in `people` uses this schema, omitting fields you could not verify:

```json
{SCHEMA_BLOCK}
```

Aim for 8 to 15 solid people. Zero is acceptable if nothing verifies.
Your final message: the count and a one-line list of names. Do not paste the JSON.
"""


def render_people_briefs(
    surfaces: list[dict], seed: list[dict], out_dir: Path, today: date | None = None
) -> list[Path]:
    out_dir = Path(out_dir)
    (out_dir / "people_briefs").mkdir(parents=True, exist_ok=True)
    (out_dir / "people_finds").mkdir(parents=True, exist_ok=True)
    existing = sorted(f"{p['name']} | {p.get('company') or ''}" for p in seed)
    (out_dir / "people_skip.txt").write_text("\n".join(existing) + "\n")
    written = []
    for s in surfaces:
        path = out_dir / "people_briefs" / f"{s['id']}.md"
        path.write_text(render_people_brief(s, existing, out_dir, today))
        written.append(path)
    return written
