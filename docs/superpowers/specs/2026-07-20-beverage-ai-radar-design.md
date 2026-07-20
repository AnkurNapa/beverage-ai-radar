# Beverage-AI Landscape Radar — Design

**Date:** 2026-07-20
**Status:** Approved (design), pending implementation plan
**Owner:** Ankur

## Goal

A standing daily pipeline that discovers, enriches, and tracks companies applying
AI / GenAI to beer, whiskey, and wine. It produces two outputs from one shared data
store: a written **market-landscape report** and a **live GitHub Pages dashboard**.
The Obsidian vault is the source of truth (one note per company plus a Base view).

## Non-Goals (YAGNI)

- No CRM, no outreach automation, no contact scraping for sales. This is a landscape
  radar, not a lead engine.
- No full job-queue / worker infrastructure. A single daily run is enough.
- No paid data subscriptions assumed. We use public/free surfaces and degrade
  gracefully when a source is paywalled or rate-limited.

## Architecture

Three layers over one shared, deduped store:

```
DISCOVERY  ->  ENRICHMENT  ->  OUTPUTS
(find companies)  (deepen each)   (report + dashboard + vault)
```

Chosen approach: **modular pipeline with a shared company store**. Each source is an
isolated module that reads/writes the store through a well-defined interface, so a
single source can be added, retried, or disabled without touching the others.
(Rejected: one mega-script — brittle, hard to rate-limit per source. Rejected: full
job-queue system — overkill for a solo daily run.)

### Layer 1 — Discovery (finds new companies)

- **Web search + news**: queries such as "AI brewery", "GenAI winemaking",
  "machine learning distillery", "AI sensory beer", "computer vision wine quality".
- **Trade press**: brewing / wine / spirits publications, conference exhibitor lists,
  awards lists.
- Every hit is normalized to a **dedup key** and upserted into the store.
  - Dedup key: normalized registrable domain (strip scheme/www/subdomain/path,
    lowercase). Fallback when no domain: slug of `name + HQ country`.

### Layer 2 — Enrichment (deepens known companies)

- **Crunchbase / funding surfaces**: funding stage, total raised, founders, HQ.
- **LinkedIn**: team, positioning, recent activity. Uses the existing logged-in
  Playwright browser flow (never headless authwall).
- **GitHub / product surfaces**: actual shipping AI tools / repos / product pages.
- **Rate-limit safe + cached**: each fetched page is cached with an ETag/last-modified
  or content hash and a `fetched_at` timestamp. On a daily run, a company is skipped
  if its cache is fresh and nothing signaled a change. This is what makes daily runs
  cheap — most days are "nothing new".

### Layer 3 — Data model (the store)

Store: SQLite (canonical) with a JSON export for the dashboard. One row per company.

| Group | Fields |
|---|---|
| Identity | name, domain, hq_location, founded_year, size_employees |
| Classification | beverage_vertical (beer/whiskey/wine/multiple), ai_use_case (recipe/flavor, demand forecasting, quality control / computer vision, GenAI marketing, supply chain, sensory), ai_maturity (research / pilot / shipping) |
| Business signals | funding_stage, total_raised, key_people, notable_customers_partners |
| Evidence | source_urls[], short_description, first_seen, last_seen |
| Freshness | freshness_score, status (`active` if evidence < 18 months, else `dormant`) |
| Optional | linkedin_url, github_url, product_url, latest_news_headline, why_interesting |

**Recency policy (two-tier):** discovery looks back up to **5 years** so we miss
nobody. Each company gets a freshness signal; anything with no evidence in the last
**~18 months** is flagged `dormant` (not deleted) and separated from `active` in both
the report and the dashboard. GenAI-era evidence (2023+) is weighted highest.

### Layer 4 — Outputs

- **Vault notes** (source of truth): one Markdown note per company under a
  `Beverage-AI Radar/` folder in the vault, plus an Obsidian **Base** (table + card
  view) filtered by vertical / use-case / maturity / status. House style: no em dash,
  proper punctuation.
- **Dashboard** (GitHub Pages): static, client-side, BrewLens/Aroma Forge pattern —
  vanilla ES modules + a charting lib via CDN+SRI. Filters by vertical, use-case,
  maturity, active-vs-dormant; charts (counts by vertical / use-case / maturity over
  time); company cards linking to evidence. Reads the JSON export.
- **Report** (Markdown): auto-generated market-landscape write-up in house style —
  who is doing what, trends, gaps, active vs dormant, notable funding/movers.

### Layer 5 — Recurring wiring

- **Daily** launchd job (pattern of `devendra_daily.py`):
  1. Discovery sweep -> upsert into store
  2. Enrichment pass (cache-gated; only stale/changed companies fetched)
  3. Recompute freshness/status
  4. Regenerate JSON export + report + vault notes
  5. Commit and push -> GitHub Pages redeploys
  6. Optional digest email (new companies, movers) to napaankur@gmail.com from the
     Gmail/Apple Mail sender, not work Exchange.

## Error Handling

- Each source module is isolated: a failure in one source logs and continues; the run
  never aborts wholly because one surface is down or rate-limited.
- Paywall / authwall / rate-limit responses degrade gracefully — the company keeps its
  last known enrichment and is retried next run.
- All writes to the store are upserts keyed on the dedup key; a partial run is safe to
  re-run (idempotent).
- Every field carries provenance (`source_urls`) so the report never asserts anything
  without a citation.

## Testing

- **Unit**: dedup-key normalization, freshness/status computation, classification
  mapping, report-section rendering. Target 80%+ on pure logic.
- **Integration**: each source module against a saved fixture page (no live network in
  tests); store upsert/idempotency.
- **Output smoke**: dashboard loads the JSON export and renders; report generates from
  a fixture store with no placeholders.

## Reused Assets

LinkedIn Playwright flow; guest-API search engine (repurposed for company discovery);
BrewLens dashboard scaffold; launchd cron pattern; vault + Obsidian Base tooling.

## Open Risks

- **Source access**: Crunchbase/LinkedIn paywalls and rate limits may thin enrichment;
  mitigated by caching + graceful degradation.
- **Classification accuracy**: beverage-vertical and AI-use-case tagging need tuning
  over the first few daily runs; start rule-based, refine.
- **Daily cadence cost**: acceptable because caching makes unchanged-company days cheap.
