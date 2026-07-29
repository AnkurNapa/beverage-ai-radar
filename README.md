# Beverage-AI Landscape Radar

A daily pipeline that discovers, enriches, and tracks companies applying AI and
GenAI to beer, whiskey, and wine. One deduped SQLite store feeds three outputs:
a market-landscape report, a static GitHub Pages dashboard, and one Obsidian
vault note per company.

## Setup

```bash
cd ~/Documents/beverage-ai-radar
python3 -m venv .venv
.venv/bin/pip install pytest pytest-cov ruff httpx requests
```

Imports resolve via `pythonpath = ["src"]` in `pyproject.toml`; no editable
install needed. Run the package with `PYTHONPATH=src`.

## Commands

```bash
PYTHONPATH=src .venv/bin/python -m radar.cli run       # discover + enrich + regenerate all outputs
PYTHONPATH=src .venv/bin/python -m radar.cli export     # rewrite dashboard/data.json from the store
PYTHONPATH=src .venv/bin/python -m radar.cli report     # print the market-landscape report

PYTHONPATH=src .venv/bin/python -m radar.cli gaps           # what coverage is thin right now
PYTHONPATH=src .venv/bin/python -m radar.cli scout-brief    # write one scout brief per surface
PYTHONPATH=src .venv/bin/python -m radar.cli scout-merge .scout/finds/*.json
PYTHONPATH=src .venv/bin/python -m radar.cli scout-liveness # find dead/blocked domains

.venv/bin/python scripts/build_jobs.py   # refresh the Jobs tab (dashboard/jobs.json)
```

## Jobs tab

`scripts/build_jobs.py` writes `dashboard/jobs.json` from the keyless LinkedIn
guest search, in two passes:

1. **Keyword sweep**, the field at large: beverage x data queries across four
   locations. The search is fuzzy, so a card is kept only if title and employer
   carry both a beverage signal and a data/AI signal. Big drinks employers whose
   name contains no beverage word (Diageo, Pernod, AB InBev) are recognised from
   a list, otherwise their data roles are dropped.
2. **Company sweep**, the radar itself: every tracked company in `data/seed.json`
   is asked directly whether it is hiring. The beverage gate is already satisfied
   by the employer match, but the data/AI gate stays, or the feed fills with
   welders and accountants from the large industrial vendors.

Rows carry `tracked_company` when the employer is on the radar, which drives the
"on the radar" chip and the "Tracked on the radar" filter. Nothing is inferred:
every row links to its posting.

## Agentic scouting

The seed is the only real growth lever (the live discovery sources return
nothing in practice), so growing the radar means adding verified companies to
`data/seed.json`. That loop is now semi-automated:

1. `scout-brief` computes coverage gaps from the store and renders one brief per
   surface in `data/scout_surfaces.json` (marketplaces, industrial automation,
   whiskey, wine, beer and route to market). Gaps and the skip list are
   generated every run, never hand-maintained.
2. One agent per brief runs in parallel, each verifying every company against
   the vendor's own site. Claude Code drives this; there is no API key in the
   pipeline. The `beverage-radar-scout` skill orchestrates it.
3. `scout-merge` validates and merges: required fields, dedupe on normalized
   name and domain, near-duplicate detection (three scouts returned Encompass
   Technologies under three product names), and a two-source rule requiring one
   source on the company's own domain. Rejects go to `.scout/quarantine.json`.

**Blocked is not rejected.** A 403 or Cloudflare wall means the check failed,
not that the company is fake, so those quarantine as `blocked` for a later pass
with a real browser. The first sweep lost Oculyze, ProLeiT/brewmaxx and Anton
Paar that way, all genuinely in scope.

**Honesty over volume.** Roughly a third of found companies have no real ML.
They stay in, labelled plainly as systems of record, sensor vendors or plain BI.
Inflating marketing language into an AI claim is the one unforgivable error.

**Provenance.** Every company carries `discovered_by` (`curated` or
`scout:<surface>`) and `verified`. Agent-found entries are `verified: false`
until a human confirms them, and the dashboard filters on it, so a bad sweep can
be identified and undone rather than quietly contaminating the set.

## Data sources

Discovery and enrichment are isolated modules; one failing source logs and the
run continues (nothing aborts the whole sweep).

| Source | Kind | Status |
|---|---|---|
| Curated seed (`data/seed.json`) | discovery | Reliable, human-verified. The authoritative source. |
| Web search (DuckDuckGo) | discovery | Best-effort, keyless. Returns nothing when the endpoint blocks the request. |
| Trade press | discovery | No-op until per-site listing URLs and parsers are added (a generic parser only produces junk). |
| GitHub | enrichment | Keyless search API. Fills github/product URLs. |
| Crunchbase | enrichment | Paywalled; degrades to no enrichment. |
| LinkedIn | enrichment | Needs the interactive logged-in browser; enrich manually. Degrades to no enrichment. |

To grow coverage, add verified companies to `data/seed.json` (see the schema in
`src/radar/sources/curated_seed.py`).

## Recency

Discovery keeps evidence up to 5 years old. A company with evidence in the last
18 months is `active`; older is `dormant` (kept, not deleted). Both the report
and dashboard separate the two.

## Dashboard (GitHub Pages)

The `dashboard/` folder is a static, dependency-free page (vanilla ES modules,
CSS-bar charts, no CDN) that reads `dashboard/data.json`.

Local preview:

```bash
PYTHONPATH=src .venv/bin/python -m radar.cli export
cd dashboard && python3 -m http.server 8099   # open http://localhost:8099
```

Publish: create a GitHub repo, push, and set Pages to serve the `dashboard/`
folder. `data.json` is committed on purpose (not gitignored) so Pages can read it.

## Daily automation (launchd, macOS)

```bash
cp scripts/com.ankur.beverage-radar.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.ankur.beverage-radar.plist
```

Runs `scripts/radar_daily.py` at 07:30 daily: pipeline run, mirror the report
into the vault, commit + push `dashboard/`, print the digest. Logs to
`radar.log` / `radar.err.log`. The digest email is sent manually from
napaankur@gmail.com (never the work Exchange account).

## Tests

```bash
.venv/bin/pytest -q
.venv/bin/ruff check src tests
```

## House style

All generated prose (report, notes, digest) uses plain punctuation: no em dash,
no en dash, no curly quotes. Every asserted fact carries a source URL.
