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
```

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
