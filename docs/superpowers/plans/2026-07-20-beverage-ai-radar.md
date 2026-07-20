# Beverage-AI Landscape Radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a daily pipeline that discovers, enriches, and tracks companies applying AI/GenAI to beer, whiskey, and wine, feeding a market-landscape report and a static GitHub Pages dashboard, with Obsidian vault notes as the source of truth.

**Architecture:** A modular Python pipeline over one deduped SQLite store. Isolated source modules (discovery + enrichment) upsert companies through a shared repository interface; output modules (vault notes, JSON export, report) read from the store. A daily launchd job runs the sweep and pushes the dashboard.

**Tech Stack:** Python 3.11+ (venv), SQLite (stdlib `sqlite3`), `requests` + `httpx`, `pytest` + `pytest-cov`, `ruff` for lint/format, vanilla ES modules + Chart.js (CDN+SRI) for the dashboard, launchd for scheduling.

## Global Constraints

- Python 3.11+ in a project-local `.venv`; no system-Python installs.
- House writing style in all generated prose (notes, report, digest): no em dash, no en dash, no curly quotes, proper grammar and punctuation.
- Every company field that asserts a fact must carry provenance in `source_urls`; the report cites nothing it cannot link.
- All store writes are idempotent upserts keyed on the dedup key; any partial run is safe to re-run.
- Each source module is isolated: a failure logs and continues, it never aborts the whole run.
- Recency: discovery looks back up to 5 years; a company is `active` if it has evidence within 18 months, else `dormant` (never deleted).
- Dashboard hosting: GitHub Pages, static client-side only, Chart.js via CDN with SRI.
- Marketing/digest email sends from napaankur@gmail.com (Gmail/Apple Mail), never work Exchange.
- Files stay focused: target 200-400 lines, 800 max; split by responsibility.

---

## File Structure

```
beverage-ai-radar/
  pyproject.toml                 # deps, ruff, pytest config
  .venv/
  src/radar/
    __init__.py
    config.py                    # paths, constants, query terms, recency windows
    model.py                     # Company dataclass, enums, dedup-key + freshness logic
    store.py                     # SQLite repository: upsert, get, all, schema migration
    http_cache.py                # cached fetch (content-hash + fetched_at), rate limiting
    sources/
      __init__.py                # SOURCE registry + run_source() isolation wrapper
      base.py                    # Source protocol: discover() / enrich()
      web_search.py              # discovery: search/news queries
      trade_press.py             # discovery: trade publications + exhibitor lists
      crunchbase.py              # enrichment: funding/founders
      linkedin.py                # enrichment: team/positioning (Playwright hook)
      github_product.py          # enrichment: repos/product pages
    classify.py                  # rule-based vertical / use-case / maturity tagging
    outputs/
      __init__.py
      json_export.py             # store -> dashboard data.json
      vault_notes.py             # store -> one Markdown note per company + Base file
      report.py                  # store -> market-landscape report.md
      digest.py                  # new-companies/movers email body
    pipeline.py                  # orchestrates discovery -> enrich -> outputs
    cli.py                       # `radar run`, `radar report`, `radar export`
  dashboard/
    index.html
    app.js
    styles.css
    data.json                    # generated export (also mirrored)
  scripts/
    radar_daily.py               # launchd entrypoint: run + git push + digest
    com.ankur.beverage-radar.plist
  tests/
    fixtures/                    # saved HTML/JSON pages for source tests
    test_model.py
    test_store.py
    test_http_cache.py
    test_classify.py
    test_sources_*.py
    test_outputs_*.py
    test_pipeline.py
```

---

## Task 1: Project scaffold and tooling

**Files:**
- Create: `pyproject.toml`, `src/radar/__init__.py`, `src/radar/config.py`, `tests/__init__.py`, `.gitignore`

**Interfaces:**
- Produces: `radar.config` module exposing `DISCOVERY_QUERIES: list[str]`, `RECENCY_YEARS = 5`, `ACTIVE_MONTHS = 18`, `VAULT_DIR: Path`, `DB_PATH: Path`, `DASHBOARD_DIR: Path`.

- [ ] **Step 1: Create `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
*.sqlite
dashboard/data.json
.http_cache/
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "beverage-ai-radar"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["requests>=2.31", "httpx>=0.27"]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-cov>=5", "ruff>=0.5"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
```

- [ ] **Step 3: Create the venv and install**

Run:
```bash
cd ~/Documents/beverage-ai-radar
python3.11 -m venv .venv || python3 -m venv .venv
.venv/bin/pip install -q -e ".[dev]"
```
Expected: install completes without error. If `python3.11` is absent, install it (`brew install python@3.11`) before proceeding — 3.9 is too old for the type syntax used here.

- [ ] **Step 4: Create `src/radar/config.py`**

```python
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "radar.sqlite"
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"
HTTP_CACHE_DIR = PROJECT_ROOT / ".http_cache"

# Obsidian vault mirror target
VAULT_DIR = Path.home() / "Documents" / "obsidian" / "Beverage-AI Radar"

RECENCY_YEARS = 5
ACTIVE_MONTHS = 18

DISCOVERY_QUERIES = [
    "AI brewery", "GenAI winemaking", "machine learning distillery",
    "AI sensory beer", "computer vision wine quality", "AI flavor prediction beer",
    "generative AI wine marketing", "demand forecasting brewery AI",
    "whiskey distillery machine learning", "AI beverage quality control",
]
```

- [ ] **Step 5: Create empty package files and verify import**

```bash
touch src/radar/__init__.py tests/__init__.py
.venv/bin/python -c "from radar import config; print(config.RECENCY_YEARS, len(config.DISCOVERY_QUERIES))"
```
Expected: `5 10`

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "chore: project scaffold, config, tooling"
```

---

## Task 2: Data model — Company, enums, dedup key, freshness

**Files:**
- Create: `src/radar/model.py`, `tests/test_model.py`

**Interfaces:**
- Produces:
  - `class BeverageVertical(str, Enum)`: `BEER, WHISKEY, WINE, MULTIPLE`
  - `class AIMaturity(str, Enum)`: `RESEARCH, PILOT, SHIPPING`
  - `class Status(str, Enum)`: `ACTIVE, DORMANT`
  - `dedup_key(name: str, domain: str | None, hq_country: str | None) -> str`
  - `compute_status(last_seen: date, today: date, active_months: int) -> Status`
  - `@dataclass Company` with all schema fields and `.key` property.

- [ ] **Step 1: Write the failing test**

```python
from datetime import date
from radar.model import dedup_key, compute_status, Status, Company, BeverageVertical

def test_dedup_key_normalizes_domain():
    assert dedup_key("Acme AI", "https://www.Acme-AI.com/about", None) == "acme-ai.com"
    assert dedup_key("Acme AI", "http://blog.acme-ai.com", None) == "acme-ai.com"

def test_dedup_key_falls_back_to_name_country_slug():
    assert dedup_key("Brew Brain", None, "Germany") == "brew-brain::germany"

def test_compute_status_active_within_window():
    assert compute_status(date(2025, 6, 1), date(2026, 7, 20), 18) == Status.ACTIVE

def test_compute_status_dormant_past_window():
    assert compute_status(date(2024, 1, 1), date(2026, 7, 20), 18) == Status.DORMANT

def test_company_key_uses_dedup_key():
    c = Company(name="Acme AI", domain="https://acme-ai.com",
                vertical=BeverageVertical.BEER, last_seen=date(2026, 1, 1))
    assert c.key == "acme-ai.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_model.py -v`
Expected: FAIL, `ModuleNotFoundError` / attributes undefined.

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from urllib.parse import urlparse
import re


class BeverageVertical(str, Enum):
    BEER = "beer"; WHISKEY = "whiskey"; WINE = "wine"; MULTIPLE = "multiple"


class AIMaturity(str, Enum):
    RESEARCH = "research"; PILOT = "pilot"; SHIPPING = "shipping"


class Status(str, Enum):
    ACTIVE = "active"; DORMANT = "dormant"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


def dedup_key(name: str, domain: str | None, hq_country: str | None) -> str:
    if domain:
        host = urlparse(domain if "//" in domain else f"//{domain}", scheme="http").hostname or ""
        host = host.lower().removeprefix("www.")
        parts = host.split(".")
        if len(parts) > 2:
            host = ".".join(parts[-2:])
        if host:
            return host
    country = _slug(hq_country) if hq_country else "unknown"
    return f"{_slug(name)}::{country}"


def _months_between(earlier: date, later: date) -> int:
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


def compute_status(last_seen: date, today: date, active_months: int) -> Status:
    return Status.ACTIVE if _months_between(last_seen, today) < active_months else Status.DORMANT


@dataclass
class Company:
    name: str
    domain: str | None = None
    hq_location: str | None = None
    founded_year: int | None = None
    size_employees: str | None = None
    vertical: BeverageVertical | None = None
    ai_use_case: str | None = None
    ai_maturity: AIMaturity | None = None
    funding_stage: str | None = None
    total_raised: str | None = None
    key_people: str | None = None
    notable_customers_partners: str | None = None
    short_description: str | None = None
    source_urls: list[str] = field(default_factory=list)
    first_seen: date | None = None
    last_seen: date | None = None
    status: Status | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    product_url: str | None = None
    latest_news_headline: str | None = None
    why_interesting: str | None = None

    @property
    def key(self) -> str:
        country = self.hq_location.split(",")[-1].strip() if self.hq_location else None
        return dedup_key(self.name, self.domain, country)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_model.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/radar/model.py tests/test_model.py
git commit -m "feat: company data model, dedup key, freshness logic"
```

---

## Task 3: SQLite store with idempotent upsert

**Files:**
- Create: `src/radar/store.py`, `tests/test_store.py`

**Interfaces:**
- Consumes: `radar.model.Company`, `dedup_key`.
- Produces: `class Store` with `__init__(path)`, `upsert(company: Company) -> None`, `get(key: str) -> Company | None`, `all() -> list[Company]`, `close()`. Upsert merges: `source_urls` union, `first_seen` = min, `last_seen` = max, non-null incoming fields overwrite null existing fields.

- [ ] **Step 1: Write the failing test**

```python
from datetime import date
from radar.model import Company, BeverageVertical
from radar.store import Store

def make_store(tmp_path):
    return Store(tmp_path / "t.sqlite")

def test_upsert_then_get(tmp_path):
    s = make_store(tmp_path)
    s.upsert(Company(name="Acme AI", domain="acme-ai.com",
                     vertical=BeverageVertical.BEER,
                     source_urls=["https://a.com"],
                     first_seen=date(2026,1,1), last_seen=date(2026,1,1)))
    got = s.get("acme-ai.com")
    assert got.name == "Acme AI"
    assert got.vertical == BeverageVertical.BEER

def test_upsert_merges_evidence_and_dates(tmp_path):
    s = make_store(tmp_path)
    s.upsert(Company(name="Acme", domain="acme-ai.com",
                     source_urls=["https://a.com"],
                     first_seen=date(2026,1,1), last_seen=date(2026,1,1)))
    s.upsert(Company(name="Acme", domain="acme-ai.com",
                     hq_location="Berlin, Germany",
                     source_urls=["https://b.com"],
                     first_seen=date(2025,6,1), last_seen=date(2026,7,1)))
    got = s.get("acme-ai.com")
    assert set(got.source_urls) == {"https://a.com", "https://b.com"}
    assert got.first_seen == date(2025,6,1)
    assert got.last_seen == date(2026,7,1)
    assert got.hq_location == "Berlin, Germany"  # null filled

def test_all_returns_every_company(tmp_path):
    s = make_store(tmp_path)
    s.upsert(Company(name="A", domain="a.com", last_seen=date(2026,1,1)))
    s.upsert(Company(name="B", domain="b.com", last_seen=date(2026,1,1)))
    assert len(s.all()) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_store.py -v`
Expected: FAIL, `ModuleNotFoundError: radar.store`.

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations
import json
import sqlite3
from datetime import date
from pathlib import Path
from dataclasses import fields
from radar.model import Company, BeverageVertical, AIMaturity, Status

_ENUM_FIELDS = {"vertical": BeverageVertical, "ai_maturity": AIMaturity, "status": Status}
_DATE_FIELDS = {"first_seen", "last_seen"}
_LIST_FIELDS = {"source_urls"}


class Store:
    def __init__(self, path: Path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        cols = ", ".join(f"{f.name} TEXT" for f in fields(Company) if f.name != "name")
        self.conn.execute(
            f"CREATE TABLE IF NOT EXISTS companies (key TEXT PRIMARY KEY, name TEXT, {cols})"
        )
        self.conn.commit()

    def _to_row(self, c: Company) -> dict:
        row = {"key": c.key}
        for f in fields(Company):
            v = getattr(c, f.name)
            if v is None:
                row[f.name] = None
            elif f.name in _LIST_FIELDS:
                row[f.name] = json.dumps(v)
            elif f.name in _DATE_FIELDS:
                row[f.name] = v.isoformat()
            elif isinstance(v, (BeverageVertical, AIMaturity, Status)):
                row[f.name] = v.value
            else:
                row[f.name] = str(v) if not isinstance(v, str) else v
        return row

    def _from_row(self, row: sqlite3.Row) -> Company:
        data = {}
        for f in fields(Company):
            v = row[f.name]
            if v is None:
                data[f.name] = None
            elif f.name in _LIST_FIELDS:
                data[f.name] = json.loads(v)
            elif f.name in _DATE_FIELDS:
                data[f.name] = date.fromisoformat(v)
            elif f.name in _ENUM_FIELDS:
                data[f.name] = _ENUM_FIELDS[f.name](v)
            elif f.name in {"founded_year"}:
                data[f.name] = int(v)
            else:
                data[f.name] = v
        return Company(**data)

    def get(self, key: str) -> Company | None:
        r = self.conn.execute("SELECT * FROM companies WHERE key=?", (key,)).fetchone()
        return self._from_row(r) if r else None

    def all(self) -> list[Company]:
        return [self._from_row(r) for r in self.conn.execute("SELECT * FROM companies")]

    def upsert(self, company: Company) -> None:
        existing = self.get(company.key)
        merged = self._merge(existing, company) if existing else company
        row = self._to_row(merged)
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        updates = ", ".join(f"{k}=excluded.{k}" for k in row if k != "key")
        self.conn.execute(
            f"INSERT INTO companies ({cols}) VALUES ({placeholders}) "
            f"ON CONFLICT(key) DO UPDATE SET {updates}",
            list(row.values()),
        )
        self.conn.commit()

    @staticmethod
    def _merge(old: Company, new: Company) -> Company:
        merged = Company(**{f.name: getattr(old, f.name) for f in fields(Company)})
        for f in fields(Company):
            nv = getattr(new, f.name)
            if nv is None:
                continue
            if f.name == "source_urls":
                merged.source_urls = sorted(set(old.source_urls) | set(nv))
            elif f.name == "first_seen":
                merged.first_seen = min(x for x in (old.first_seen, nv) if x)
            elif f.name == "last_seen":
                merged.last_seen = max(x for x in (old.last_seen, nv) if x)
            elif getattr(old, f.name) is None:
                setattr(merged, f.name, nv)
        return merged

    def close(self) -> None:
        self.conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_store.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/radar/store.py tests/test_store.py
git commit -m "feat: SQLite store with idempotent merging upsert"
```

---

## Task 4: Cached, rate-limited HTTP fetch

**Files:**
- Create: `src/radar/http_cache.py`, `tests/test_http_cache.py`

**Interfaces:**
- Produces: `class CachedFetcher(cache_dir, min_interval_s=1.0)` with `fetch(url: str, ttl_hours: int = 24) -> str`. Returns cached body when a cache entry is younger than `ttl_hours`; otherwise fetches, stores body + `fetched_at`, and returns it. Uses an injected `transport(url) -> str` so tests never hit the network.

- [ ] **Step 1: Write the failing test**

```python
from radar.http_cache import CachedFetcher

def test_second_fetch_uses_cache(tmp_path):
    calls = []
    def transport(url):
        calls.append(url); return f"body:{url}"
    f = CachedFetcher(tmp_path, min_interval_s=0, transport=transport)
    assert f.fetch("https://x.com") == "body:https://x.com"
    assert f.fetch("https://x.com") == "body:https://x.com"
    assert calls == ["https://x.com"]  # only fetched once

def test_expired_cache_refetches(tmp_path):
    calls = []
    def transport(url):
        calls.append(url); return "b"
    f = CachedFetcher(tmp_path, min_interval_s=0, transport=transport)
    f.fetch("https://x.com", ttl_hours=0)
    f.fetch("https://x.com", ttl_hours=0)
    assert len(calls) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_http_cache.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations
import hashlib
import json
import time
from pathlib import Path
from typing import Callable


def _default_transport(url: str) -> str:
    import httpx
    return httpx.get(url, timeout=20, follow_redirects=True).text


class CachedFetcher:
    def __init__(self, cache_dir: Path, min_interval_s: float = 1.0,
                 transport: Callable[[str], str] | None = None):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval_s = min_interval_s
        self.transport = transport or _default_transport
        self._last_fetch = 0.0

    def _path(self, url: str) -> Path:
        return self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json")

    def fetch(self, url: str, ttl_hours: int = 24) -> str:
        p = self._path(url)
        if p.exists():
            entry = json.loads(p.read_text())
            age_h = (time.time() - entry["fetched_at"]) / 3600
            if age_h < ttl_hours:
                return entry["body"]
        gap = self.min_interval_s - (time.time() - self._last_fetch)
        if gap > 0:
            time.sleep(gap)
        body = self.transport(url)
        self._last_fetch = time.time()
        p.write_text(json.dumps({"fetched_at": time.time(), "body": body}))
        return body
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_http_cache.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/radar/http_cache.py tests/test_http_cache.py
git commit -m "feat: content-cached, rate-limited HTTP fetcher"
```

---

## Task 5: Rule-based classifier

**Files:**
- Create: `src/radar/classify.py`, `tests/test_classify.py`

**Interfaces:**
- Consumes: `radar.model.BeverageVertical`, `AIMaturity`.
- Produces: `classify(text: str) -> dict` returning `{"vertical": BeverageVertical|None, "ai_use_case": str|None, "ai_maturity": AIMaturity|None}` from keyword rules.

- [ ] **Step 1: Write the failing test**

```python
from radar.classify import classify
from radar.model import BeverageVertical, AIMaturity

def test_detects_beer_and_quality_use_case():
    r = classify("Our brewery uses computer vision for quality control on the canning line.")
    assert r["vertical"] == BeverageVertical.BEER
    assert r["ai_use_case"] == "quality control / computer vision"

def test_detects_wine_and_shipping_maturity():
    r = classify("This winery ships a GenAI marketing product to wineries today.")
    assert r["vertical"] == BeverageVertical.WINE
    assert r["ai_maturity"] == AIMaturity.SHIPPING

def test_multiple_verticals():
    r = classify("Platform serving breweries, distilleries, and wineries.")
    assert r["vertical"] == BeverageVertical.MULTIPLE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_classify.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations
from radar.model import BeverageVertical, AIMaturity

_VERTICAL_TERMS = {
    BeverageVertical.BEER: ["brewery", "brewing", "beer", "brewer"],
    BeverageVertical.WHISKEY: ["distillery", "distilling", "whiskey", "whisky", "spirits"],
    BeverageVertical.WINE: ["winery", "winemaking", "wine", "vineyard"],
}

_USE_CASES = [
    ("quality control / computer vision", ["computer vision", "quality control", "defect", "inspection"]),
    ("recipe / flavor prediction", ["flavor", "recipe", "aroma", "taste prediction"]),
    ("demand forecasting", ["demand forecast", "forecasting", "inventory"]),
    ("sensory", ["sensory", "tasting panel"]),
    ("supply chain", ["supply chain", "logistics"]),
    ("GenAI marketing", ["genai marketing", "generative ai marketing", "content generation", "marketing product"]),
]

_MATURITY = [
    (AIMaturity.SHIPPING, ["ships", "shipping", "launched", "in production", "customers use"]),
    (AIMaturity.PILOT, ["pilot", "beta", "trial", "proof of concept", "poc"]),
    (AIMaturity.RESEARCH, ["research", "prototype", "exploring", "r&d"]),
]


def classify(text: str) -> dict:
    t = text.lower()
    matched = [v for v, terms in _VERTICAL_TERMS.items() if any(term in t for term in terms)]
    if len(matched) > 1:
        vertical = BeverageVertical.MULTIPLE
    elif matched:
        vertical = matched[0]
    else:
        vertical = None

    use_case = next((label for label, terms in _USE_CASES if any(term in t for term in terms)), None)
    maturity = next((m for m, terms in _MATURITY if any(term in t for term in terms)), None)
    return {"vertical": vertical, "ai_use_case": use_case, "ai_maturity": maturity}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_classify.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/radar/classify.py tests/test_classify.py
git commit -m "feat: rule-based vertical/use-case/maturity classifier"
```

---

## Task 6: Source protocol and isolation wrapper

**Files:**
- Create: `src/radar/sources/__init__.py`, `src/radar/sources/base.py`, `tests/test_sources_base.py`

**Interfaces:**
- Consumes: `radar.model.Company`, `radar.store.Store`, `radar.http_cache.CachedFetcher`.
- Produces:
  - `class Source(Protocol)`: `name: str`; `kind: str` (`"discovery"|"enrichment"`); `discover(fetcher) -> list[Company]`; `enrich(company, fetcher) -> Company`.
  - `run_source(source, store, fetcher) -> dict` catches any exception, logs it, returns `{"source": name, "found": int, "errors": list[str]}`. A raising source never propagates.

- [ ] **Step 1: Write the failing test**

```python
from datetime import date
from radar.model import Company
from radar.store import Store
from radar.sources import run_source

class GoodSource:
    name = "good"; kind = "discovery"
    def discover(self, fetcher):
        return [Company(name="X", domain="x.com", last_seen=date(2026,1,1),
                        first_seen=date(2026,1,1))]
    def enrich(self, company, fetcher):
        return company

class BadSource:
    name = "bad"; kind = "discovery"
    def discover(self, fetcher):
        raise RuntimeError("boom")
    def enrich(self, company, fetcher):
        return company

def test_good_source_upserts(tmp_path):
    store = Store(tmp_path / "t.sqlite")
    res = run_source(GoodSource(), store, fetcher=None)
    assert res["found"] == 1
    assert store.get("x.com") is not None

def test_bad_source_is_isolated(tmp_path):
    store = Store(tmp_path / "t.sqlite")
    res = run_source(BadSource(), store, fetcher=None)
    assert res["found"] == 0
    assert res["errors"] and "boom" in res["errors"][0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_sources_base.py -v`
Expected: FAIL, `ImportError: run_source`.

- [ ] **Step 3: Write minimal implementation**

`src/radar/sources/base.py`:
```python
from __future__ import annotations
from typing import Protocol
from radar.model import Company


class Source(Protocol):
    name: str
    kind: str
    def discover(self, fetcher) -> list[Company]: ...
    def enrich(self, company: Company, fetcher) -> Company: ...
```

`src/radar/sources/__init__.py`:
```python
from __future__ import annotations
import logging
from radar.store import Store
from radar.sources.base import Source

log = logging.getLogger("radar.sources")


def run_source(source: Source, store: Store, fetcher) -> dict:
    found, errors = 0, []
    try:
        if source.kind == "discovery":
            for company in source.discover(fetcher):
                store.upsert(company)
                found += 1
        else:
            for company in store.all():
                store.upsert(source.enrich(company, fetcher))
                found += 1
    except Exception as exc:  # isolation: one source never aborts the run
        log.exception("source %s failed", source.name)
        errors.append(f"{type(exc).__name__}: {exc}")
    return {"source": source.name, "found": found, "errors": errors}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_sources_base.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/radar/sources/ tests/test_sources_base.py
git commit -m "feat: source protocol and failure-isolating run_source"
```

---

## Task 7: Web-search discovery source

**Files:**
- Create: `src/radar/sources/web_search.py`, `tests/test_sources_web_search.py`, `tests/fixtures/search_results.json`

**Interfaces:**
- Consumes: `CachedFetcher`, `radar.config.DISCOVERY_QUERIES`, `radar.classify.classify`, `radar.model.Company`.
- Produces: `class WebSearchSource(kind="discovery")`. `discover(fetcher)` runs each query through an injected `search_fn(query) -> list[dict]` (keys: `title`, `url`, `snippet`, `date`), converts results to `Company` with `source_urls=[url]`, `first_seen`/`last_seen` parsed from `date`, classification from title+snippet. Results older than `RECENCY_YEARS` are dropped.

- [ ] **Step 1: Create fixture `tests/fixtures/search_results.json`**

```json
[
  {"title": "BrewBrain launches AI flavor prediction", "url": "https://brewbrain.ai/news",
   "snippet": "The brewery uses machine learning for recipe and flavor prediction.",
   "date": "2026-03-01"},
  {"title": "Ancient winery blog", "url": "https://oldwine.com",
   "snippet": "A winery with no AI.", "date": "2019-01-01"}
]
```

- [ ] **Step 2: Write the failing test**

```python
import json
from pathlib import Path
from datetime import date
from radar.sources.web_search import WebSearchSource
from radar.model import BeverageVertical

FIX = json.loads((Path(__file__).parent / "fixtures/search_results.json").read_text())

def test_converts_recent_results_and_drops_stale():
    src = WebSearchSource(search_fn=lambda q: FIX, today=date(2026,7,20))
    companies = src.discover(fetcher=None)
    keys = {c.key for c in companies}
    assert "brewbrain.ai" in keys
    assert "oldwine.com" not in keys  # 2019 is older than 5 years
    bb = next(c for c in companies if c.key == "brewbrain.ai")
    assert bb.vertical == BeverageVertical.BEER
    assert "https://brewbrain.ai/news" in bb.source_urls
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_sources_web_search.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 4: Write minimal implementation**

```python
from __future__ import annotations
from datetime import date
from typing import Callable
from radar.config import DISCOVERY_QUERIES, RECENCY_YEARS
from radar.classify import classify
from radar.model import Company


class WebSearchSource:
    name = "web_search"
    kind = "discovery"

    def __init__(self, search_fn: Callable[[str], list[dict]],
                 queries: list[str] | None = None, today: date | None = None):
        self.search_fn = search_fn
        self.queries = queries or DISCOVERY_QUERIES
        self.today = today or date.today()

    def discover(self, fetcher) -> list[Company]:
        cutoff = self.today.replace(year=self.today.year - RECENCY_YEARS)
        out: dict[str, Company] = {}
        for query in self.queries:
            for r in self.search_fn(query):
                seen = date.fromisoformat(r["date"])
                if seen < cutoff:
                    continue
                text = f"{r['title']} {r['snippet']}"
                tags = classify(text)
                c = Company(
                    name=r["title"], domain=r["url"],
                    short_description=r["snippet"],
                    source_urls=[r["url"]], first_seen=seen, last_seen=seen,
                    latest_news_headline=r["title"], **tags,
                )
                out[c.key] = c  # de-dupe within the sweep
        return list(out.values())
```

Note: `**tags` spreads `vertical`, `ai_use_case`, `ai_maturity` into the `Company` constructor.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_sources_web_search.py -v`
Expected: PASS.

- [ ] **Step 6: Wire the live `search_fn`**

Add to `web_search.py` a module-level default that calls the existing guest-API / web-search engine used by the job-search flows. Keep it thin and injected so tests never call it:

```python
def default_search_fn(query: str) -> list[dict]:
    """Adapter over the existing web-search engine. Returns title/url/snippet/date dicts."""
    raise NotImplementedError("wire to the reused search engine during integration")
```

Leave `NotImplementedError` until Task 12 (integration), where the real adapter is filled from the reused engine. Tests inject a fake, so the suite stays green.

- [ ] **Step 7: Commit**

```bash
git add src/radar/sources/web_search.py tests/test_sources_web_search.py tests/fixtures/search_results.json
git commit -m "feat: web-search discovery source with recency cutoff"
```

---

## Task 8: Trade-press discovery source

**Files:**
- Create: `src/radar/sources/trade_press.py`, `tests/test_sources_trade_press.py`, `tests/fixtures/trade_page.html`

**Interfaces:**
- Consumes: `CachedFetcher`, `classify`, `Company`.
- Produces: `class TradePressSource(kind="discovery")` with `discover(fetcher)`. Takes a `parse_fn(html) -> list[dict]` (same dict shape as Task 7) and a list of `feed_urls`; fetches each via `fetcher.fetch`, parses, applies the same recency cutoff and classification. Same output contract as `WebSearchSource`.

- [ ] **Step 1: Create fixture `tests/fixtures/trade_page.html`**

```html
<ul><li><a href="https://caskml.com">CaskML brings machine learning to whiskey distilling</a>
<span class="date">2025-11-02</span></li></ul>
```

- [ ] **Step 2: Write the failing test**

```python
from pathlib import Path
from datetime import date
from radar.sources.trade_press import TradePressSource
from radar.model import BeverageVertical

HTML = (Path(__file__).parent / "fixtures/trade_page.html").read_text()

def parse_fn(html):
    # trivial fixture parser for the test
    return [{"title": "CaskML brings machine learning to whiskey distilling",
             "url": "https://caskml.com",
             "snippet": "machine learning to whiskey distilling",
             "date": "2025-11-02"}]

class StubFetcher:
    def fetch(self, url, ttl_hours=24): return HTML

def test_parses_feed_into_company():
    src = TradePressSource(feed_urls=["https://trade.example/list"],
                           parse_fn=parse_fn, today=date(2026,7,20))
    companies = src.discover(StubFetcher())
    c = companies[0]
    assert c.key == "caskml.com"
    assert c.vertical == BeverageVertical.WHISKEY
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_sources_trade_press.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 4: Write minimal implementation**

```python
from __future__ import annotations
from datetime import date
from typing import Callable
from radar.config import RECENCY_YEARS
from radar.classify import classify
from radar.model import Company

DEFAULT_FEEDS = [
    # Fill real trade-press listing URLs during integration (Task 12).
]


class TradePressSource:
    name = "trade_press"
    kind = "discovery"

    def __init__(self, feed_urls: list[str], parse_fn: Callable[[str], list[dict]],
                 today: date | None = None):
        self.feed_urls = feed_urls
        self.parse_fn = parse_fn
        self.today = today or date.today()

    def discover(self, fetcher) -> list[Company]:
        cutoff = self.today.replace(year=self.today.year - RECENCY_YEARS)
        out: dict[str, Company] = {}
        for url in self.feed_urls:
            html = fetcher.fetch(url)
            for r in self.parse_fn(html):
                seen = date.fromisoformat(r["date"])
                if seen < cutoff:
                    continue
                tags = classify(f"{r['title']} {r['snippet']}")
                c = Company(name=r["title"], domain=r["url"],
                            short_description=r["snippet"], source_urls=[r["url"]],
                            first_seen=seen, last_seen=seen,
                            latest_news_headline=r["title"], **tags)
                out[c.key] = c
        return list(out.values())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_sources_trade_press.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/radar/sources/trade_press.py tests/test_sources_trade_press.py tests/fixtures/trade_page.html
git commit -m "feat: trade-press discovery source"
```

---

## Task 9: Enrichment sources (Crunchbase, LinkedIn, GitHub/product)

**Files:**
- Create: `src/radar/sources/crunchbase.py`, `src/radar/sources/linkedin.py`, `src/radar/sources/github_product.py`, `tests/test_sources_enrichment.py`

**Interfaces:**
- Consumes: `Company`, `CachedFetcher`.
- Produces three `kind="enrichment"` sources, each with `enrich(company, fetcher) -> Company`. Each returns a NEW `Company` (immutable update via `dataclasses.replace`) filling only fields it can source, updating `source_urls` and `last_seen`. Each takes an injected `lookup_fn(company) -> dict` so tests never hit the network. A lookup returning `{}` leaves the company unchanged.

- [ ] **Step 1: Write the failing test**

```python
from datetime import date
from radar.model import Company
from radar.sources.crunchbase import CrunchbaseSource
from radar.sources.github_product import GithubProductSource

def test_crunchbase_fills_funding_only():
    src = CrunchbaseSource(lookup_fn=lambda c: {
        "funding_stage": "Seed", "total_raised": "$2M",
        "key_people": "Jane Doe (CEO)", "source_url": "https://cb.com/x"})
    c = Company(name="X", domain="x.com", last_seen=date(2026,1,1),
                first_seen=date(2026,1,1))
    out = src.enrich(c, fetcher=None)
    assert out.funding_stage == "Seed"
    assert out.total_raised == "$2M"
    assert "https://cb.com/x" in out.source_urls
    assert out is not c  # immutable update

def test_empty_lookup_leaves_company_unchanged():
    src = GithubProductSource(lookup_fn=lambda c: {})
    c = Company(name="X", domain="x.com", last_seen=date(2026,1,1))
    out = src.enrich(c, fetcher=None)
    assert out.github_url is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_sources_enrichment.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`src/radar/sources/crunchbase.py`:
```python
from __future__ import annotations
from dataclasses import replace
from datetime import date
from typing import Callable
from radar.model import Company


class CrunchbaseSource:
    name = "crunchbase"
    kind = "enrichment"

    def __init__(self, lookup_fn: Callable[[Company], dict]):
        self.lookup_fn = lookup_fn

    def enrich(self, company: Company, fetcher) -> Company:
        data = self.lookup_fn(company) or {}
        if not data:
            return company
        urls = sorted(set(company.source_urls) | ({data["source_url"]} if data.get("source_url") else set()))
        return replace(
            company,
            funding_stage=data.get("funding_stage") or company.funding_stage,
            total_raised=data.get("total_raised") or company.total_raised,
            key_people=data.get("key_people") or company.key_people,
            source_urls=urls,
            last_seen=max(x for x in (company.last_seen, date.today()) if x),
        )
```

`src/radar/sources/github_product.py`:
```python
from __future__ import annotations
from dataclasses import replace
from typing import Callable
from radar.model import Company


class GithubProductSource:
    name = "github_product"
    kind = "enrichment"

    def __init__(self, lookup_fn: Callable[[Company], dict]):
        self.lookup_fn = lookup_fn

    def enrich(self, company: Company, fetcher) -> Company:
        data = self.lookup_fn(company) or {}
        if not data:
            return company
        urls = sorted(set(company.source_urls) |
                      {u for u in (data.get("github_url"), data.get("product_url")) if u})
        return replace(company,
                       github_url=data.get("github_url") or company.github_url,
                       product_url=data.get("product_url") or company.product_url,
                       source_urls=urls)
```

`src/radar/sources/linkedin.py`:
```python
from __future__ import annotations
from dataclasses import replace
from typing import Callable
from radar.model import Company


class LinkedInSource:
    """Enrichment via the existing logged-in Playwright browser flow.

    lookup_fn wraps that flow and returns {linkedin_url, key_people,
    size_employees, hq_location, source_url}. Injected so tests never
    drive a real browser.
    """
    name = "linkedin"
    kind = "enrichment"

    def __init__(self, lookup_fn: Callable[[Company], dict]):
        self.lookup_fn = lookup_fn

    def enrich(self, company: Company, fetcher) -> Company:
        data = self.lookup_fn(company) or {}
        if not data:
            return company
        urls = sorted(set(company.source_urls) | ({data["source_url"]} if data.get("source_url") else set()))
        return replace(company,
                       linkedin_url=data.get("linkedin_url") or company.linkedin_url,
                       key_people=data.get("key_people") or company.key_people,
                       size_employees=data.get("size_employees") or company.size_employees,
                       hq_location=data.get("hq_location") or company.hq_location,
                       source_urls=urls)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_sources_enrichment.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/radar/sources/crunchbase.py src/radar/sources/github_product.py src/radar/sources/linkedin.py tests/test_sources_enrichment.py
git commit -m "feat: crunchbase/linkedin/github enrichment sources (immutable updates)"
```

---

## Task 10: Outputs — JSON export, vault notes, report

**Files:**
- Create: `src/radar/outputs/__init__.py`, `src/radar/outputs/json_export.py`, `src/radar/outputs/vault_notes.py`, `src/radar/outputs/report.py`, `tests/test_outputs_json.py`, `tests/test_outputs_report.py`

**Interfaces:**
- Consumes: `Store`, `Company`, `Status`, `compute_status`, `config.ACTIVE_MONTHS`.
- Produces:
  - `export_json(store, out_path, today) -> None`: writes `[{...company, status}]`, recomputing `status` from `last_seen`.
  - `write_vault_notes(store, vault_dir, today) -> int`: one `.md` note per company, returns count.
  - `render_report(store, today) -> str`: house-style Markdown; sections for Active vs Dormant, counts by vertical/use-case, notable funding. No em dash/en dash/curly quotes.

- [ ] **Step 1: Write the failing tests**

```python
import json
from datetime import date
from radar.model import Company, BeverageVertical
from radar.store import Store
from radar.outputs.json_export import export_json
from radar.outputs.report import render_report

def seed(tmp_path):
    s = Store(tmp_path / "t.sqlite")
    s.upsert(Company(name="BrewBrain", domain="brewbrain.ai",
                     vertical=BeverageVertical.BEER, ai_use_case="recipe / flavor prediction",
                     source_urls=["https://brewbrain.ai"],
                     first_seen=date(2026,1,1), last_seen=date(2026,6,1)))
    s.upsert(Company(name="OldCask", domain="oldcask.com",
                     vertical=BeverageVertical.WHISKEY,
                     source_urls=["https://oldcask.com"],
                     first_seen=date(2021,1,1), last_seen=date(2023,1,1)))
    return s

def test_export_json_sets_status(tmp_path):
    s = seed(tmp_path)
    out = tmp_path / "data.json"
    export_json(s, out, today=date(2026,7,20))
    rows = json.loads(out.read_text())
    by_key = {r["key"]: r for r in rows}
    assert by_key["brewbrain.ai"]["status"] == "active"
    assert by_key["oldcask.com"]["status"] == "dormant"

def test_report_has_sections_and_no_em_dash(tmp_path):
    s = seed(tmp_path)
    text = render_report(s, today=date(2026,7,20))
    assert "Active" in text and "Dormant" in text
    assert "BrewBrain" in text
    assert "—" not in text and "–" not in text  # no em/en dash
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_outputs_json.py tests/test_outputs_report.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`src/radar/outputs/__init__.py`: empty.

`src/radar/outputs/json_export.py`:
```python
from __future__ import annotations
import json
from dataclasses import fields, asdict
from datetime import date
from pathlib import Path
from radar.config import ACTIVE_MONTHS
from radar.model import compute_status, Status
from radar.store import Store


def _serialize(company, today: date) -> dict:
    row = {}
    for f in fields(company):
        v = getattr(company, f.name)
        if hasattr(v, "value"):
            row[f.name] = v.value
        elif isinstance(v, date):
            row[f.name] = v.isoformat()
        else:
            row[f.name] = v
    row["key"] = company.key
    status = compute_status(company.last_seen, today, ACTIVE_MONTHS) if company.last_seen else Status.DORMANT
    row["status"] = status.value
    return row


def export_json(store: Store, out_path: Path, today: date | None = None) -> None:
    today = today or date.today()
    rows = [_serialize(c, today) for c in store.all()]
    Path(out_path).write_text(json.dumps(rows, indent=2))
```

`src/radar/outputs/report.py`:
```python
from __future__ import annotations
from collections import Counter
from datetime import date
from radar.config import ACTIVE_MONTHS
from radar.model import compute_status, Status
from radar.store import Store


def render_report(store: Store, today: date | None = None) -> str:
    today = today or date.today()
    companies = store.all()
    active, dormant = [], []
    for c in companies:
        bucket = active if (c.last_seen and compute_status(c.last_seen, today, ACTIVE_MONTHS) == Status.ACTIVE) else dormant
        bucket.append(c)

    verticals = Counter(c.vertical.value for c in active if c.vertical)
    use_cases = Counter(c.ai_use_case for c in active if c.ai_use_case)

    lines = [f"# Beverage-AI Landscape Radar", "",
             f"Snapshot: {today.isoformat()}. {len(active)} active, {len(dormant)} dormant.", ""]
    lines += ["## Active companies", ""]
    for c in sorted(active, key=lambda x: x.name.lower()):
        vertical = c.vertical.value if c.vertical else "unclassified"
        use = c.ai_use_case or "unspecified use case"
        lines.append(f"- **{c.name}** ({vertical}, {use}). {c.short_description or ''}".rstrip())
    lines += ["", "## Dormant companies", ""]
    for c in sorted(dormant, key=lambda x: x.name.lower()):
        lines.append(f"- {c.name} (last seen {c.last_seen})")
    lines += ["", "## By vertical (active)", ""]
    lines += [f"- {k}: {v}" for k, v in verticals.most_common()]
    lines += ["", "## By use case (active)", ""]
    lines += [f"- {k}: {v}" for k, v in use_cases.most_common()]
    return "\n".join(lines) + "\n"
```

`src/radar/outputs/vault_notes.py`:
```python
from __future__ import annotations
from datetime import date
from pathlib import Path
from radar.config import ACTIVE_MONTHS
from radar.model import compute_status, Status
from radar.store import Store


def _note(company, today: date) -> str:
    status = compute_status(company.last_seen, today, ACTIVE_MONTHS) if company.last_seen else Status.DORMANT
    fm = [
        "---",
        f"name: {company.name}",
        f"domain: {company.domain or ''}",
        f"vertical: {company.vertical.value if company.vertical else ''}",
        f"ai_use_case: {company.ai_use_case or ''}",
        f"ai_maturity: {company.ai_maturity.value if company.ai_maturity else ''}",
        f"status: {status.value}",
        f"last_seen: {company.last_seen or ''}",
        "---", "",
        f"# {company.name}", "",
        company.short_description or "", "",
        "## Evidence",
    ]
    fm += [f"- {u}" for u in company.source_urls]
    return "\n".join(fm) + "\n"


def write_vault_notes(store: Store, vault_dir: Path, today: date | None = None) -> int:
    today = today or date.today()
    vault_dir = Path(vault_dir)
    vault_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for c in store.all():
        safe = c.key.replace("/", "-").replace(":", "-")
        (vault_dir / f"{safe}.md").write_text(_note(c, today))
        count += 1
    return count
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_outputs_json.py tests/test_outputs_report.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/radar/outputs/ tests/test_outputs_json.py tests/test_outputs_report.py
git commit -m "feat: JSON export, vault notes, and market-landscape report"
```

---

## Task 11: Pipeline orchestrator and CLI

**Files:**
- Create: `src/radar/pipeline.py`, `src/radar/cli.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `Store`, `CachedFetcher`, `run_source`, all sources, all outputs.
- Produces:
  - `run(store, fetcher, sources, outputs_dir, vault_dir, today) -> dict`: runs discovery sources first, then enrichment sources, then regenerates all outputs; returns a summary `{"per_source": [...], "total_companies": int}`.
  - `cli.py` with `radar run` / `radar export` / `radar report` argparse subcommands.

- [ ] **Step 1: Write the failing test**

```python
from datetime import date
from radar.model import Company, BeverageVertical
from radar.store import Store
from radar.pipeline import run

class DiscA:
    name = "a"; kind = "discovery"
    def discover(self, fetcher):
        return [Company(name="BrewBrain", domain="brewbrain.ai",
                        vertical=BeverageVertical.BEER, source_urls=["https://brewbrain.ai"],
                        first_seen=date(2026,1,1), last_seen=date(2026,6,1))]
    def enrich(self, c, fetcher): return c

class EnrichA:
    name = "e"; kind = "enrichment"
    def discover(self, fetcher): return []
    def enrich(self, c, fetcher):
        from dataclasses import replace
        return replace(c, funding_stage="Seed")

def test_run_discovers_enriches_and_exports(tmp_path):
    store = Store(tmp_path / "t.sqlite")
    summary = run(store, fetcher=None, sources=[DiscA(), EnrichA()],
                  outputs_dir=tmp_path, vault_dir=tmp_path / "vault",
                  today=date(2026,7,20))
    assert summary["total_companies"] == 1
    assert store.get("brewbrain.ai").funding_stage == "Seed"
    assert (tmp_path / "data.json").exists()
    assert (tmp_path / "report.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_pipeline.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`src/radar/pipeline.py`:
```python
from __future__ import annotations
from datetime import date
from pathlib import Path
from radar.store import Store
from radar.sources import run_source
from radar.outputs.json_export import export_json
from radar.outputs.report import render_report
from radar.outputs.vault_notes import write_vault_notes


def run(store: Store, fetcher, sources: list, outputs_dir: Path,
        vault_dir: Path, today: date | None = None) -> dict:
    today = today or date.today()
    outputs_dir = Path(outputs_dir)
    per_source = []
    for src in [s for s in sources if s.kind == "discovery"]:
        per_source.append(run_source(src, store, fetcher))
    for src in [s for s in sources if s.kind == "enrichment"]:
        per_source.append(run_source(src, store, fetcher))

    export_json(store, outputs_dir / "data.json", today)
    (outputs_dir / "report.md").write_text(render_report(store, today))
    write_vault_notes(store, vault_dir, today)
    return {"per_source": per_source, "total_companies": len(store.all())}
```

`src/radar/cli.py`:
```python
from __future__ import annotations
import argparse
from datetime import date
from radar import config
from radar.store import Store
from radar.http_cache import CachedFetcher
from radar.pipeline import run
from radar.outputs.json_export import export_json
from radar.outputs.report import render_report


def _live_sources():
    """Assembled in Task 12 integration. Empty here keeps CLI importable."""
    return []


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="radar")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("export")
    sub.add_parser("report")
    args = parser.parse_args(argv)

    store = Store(config.DB_PATH)
    if args.cmd == "run":
        fetcher = CachedFetcher(config.HTTP_CACHE_DIR)
        summary = run(store, fetcher, _live_sources(),
                      config.DASHBOARD_DIR, config.VAULT_DIR, date.today())
        print(summary)
    elif args.cmd == "export":
        export_json(store, config.DASHBOARD_DIR / "data.json")
        print("exported")
    elif args.cmd == "report":
        print(render_report(store))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_pipeline.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite and lint**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check src tests`
Expected: all tests pass, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add src/radar/pipeline.py src/radar/cli.py tests/test_pipeline.py
git commit -m "feat: pipeline orchestrator and radar CLI"
```

---

## Task 12: Live source adapters (integration)

**Files:**
- Modify: `src/radar/sources/web_search.py`, `src/radar/sources/trade_press.py`, `src/radar/sources/crunchbase.py`, `src/radar/sources/linkedin.py`, `src/radar/sources/github_product.py`, `src/radar/cli.py`

**Interfaces:**
- Consumes: reused web-search engine, existing LinkedIn Playwright flow.
- Produces: real `default_search_fn`, real trade-press `parse_fn` + `DEFAULT_FEEDS`, real `lookup_fn`s, and `_live_sources()` returning the assembled source list. No new public signatures.

> This task connects to external systems that vary by environment, so it is validated by a live smoke run rather than unit fixtures. Keep every adapter thin: it only maps external data into the dict shapes the tested modules already expect.

- [ ] **Step 1: Implement `default_search_fn`** in `web_search.py` by calling the same web-search engine the job-search flows use, mapping each result to `{title, url, snippet, date}`. Where a result lacks a date, default to today.

- [ ] **Step 2: Implement trade-press `parse_fn` and `DEFAULT_FEEDS`** in `trade_press.py`. Pick 3-5 real listing/exhibitor/awards URLs for brewing, wine, and spirits. Parse with `selectolax` or stdlib `html.parser` into `{title, url, snippet, date}`.

- [ ] **Step 3: Implement `lookup_fn`s** for Crunchbase (public company page fetch via `fetcher`), GitHub/product (GitHub search API + homepage sniff), and LinkedIn (wrap the existing logged-in Playwright flow; return `{}` on authwall so the run degrades gracefully).

- [ ] **Step 4: Assemble `_live_sources()`** in `cli.py` returning `[WebSearchSource(default_search_fn), TradePressSource(DEFAULT_FEEDS, parse_fn), CrunchbaseSource(cb_lookup), GithubProductSource(gh_lookup), LinkedInSource(li_lookup)]`.

- [ ] **Step 5: Live smoke run**

Run: `.venv/bin/python -m radar.cli run`
Expected: completes without traceback; prints a summary with `total_companies >= 1`; `dashboard/data.json` and `dashboard/report.md` written. If a source authwalls or rate-limits, its entry in `per_source` shows an error but the run still finishes (isolation working).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: wire live source adapters and assemble pipeline"
```

---

## Task 13: Static dashboard

**Files:**
- Create: `dashboard/index.html`, `dashboard/app.js`, `dashboard/styles.css`

**Interfaces:**
- Consumes: `dashboard/data.json` (from `export_json`).
- Produces: a static page that loads `data.json`, renders filterable company cards and charts. Chart.js via CDN with SRI. Light theme matching the brewing-calculator family. No build step.

- [ ] **Step 1: Write `index.html`** with a header, filter bar (vertical, use-case, maturity, active/dormant), a charts row (`<canvas>` for counts by vertical and by use-case), and a `#cards` container. Load Chart.js from CDN with an `integrity` + `crossorigin` attribute, and `app.js` as `type="module"`.

- [ ] **Step 2: Write `app.js`**

```js
const state = { data: [], filters: { vertical: "", useCase: "", maturity: "", status: "" } };

async function load() {
  const res = await fetch("./data.json");
  state.data = await res.json();
  render();
}

function filtered() {
  const f = state.filters;
  return state.data.filter(c =>
    (!f.vertical || c.vertical === f.vertical) &&
    (!f.useCase || c.ai_use_case === f.useCase) &&
    (!f.maturity || c.ai_maturity === f.maturity) &&
    (!f.status || c.status === f.status));
}

function render() {
  const rows = filtered();
  renderCards(rows);
  renderCharts(rows);
}
// renderCards: build a card per company with name, vertical, use-case,
//   status badge (active/dormant), and links from source_urls.
// renderCharts: two Chart.js bar charts (by vertical, by use-case),
//   destroying prior chart instances before re-drawing.
load();
```

- [ ] **Step 3: Write `styles.css`** — light theme, teal/cream accents matching the brewing-calculator family, a responsive card grid, and a distinct dormant-badge style. Use CSS custom properties for tokens (color, spacing, radius). Animate only `transform`/`opacity` on card hover.

- [ ] **Step 4: Manual verification**

Run: `.venv/bin/python -m radar.cli export && cd dashboard && python3 -m http.server 8099`
Open `http://localhost:8099`. Expected: cards render from real data, filters narrow the set, both charts draw, dormant companies show the dormant badge. No console errors.

- [ ] **Step 5: Commit**

```bash
git add dashboard/index.html dashboard/app.js dashboard/styles.css
git commit -m "feat: static filterable dashboard with charts"
```

---

## Task 14: Daily automation and GitHub Pages

**Files:**
- Create: `scripts/radar_daily.py`, `scripts/com.ankur.beverage-radar.plist`, `src/radar/outputs/digest.py`, `README.md`
- Modify: repo remote / Pages settings (manual)

**Interfaces:**
- Consumes: `radar.cli.main`, `render_report`, `Store`.
- Produces: `radar_daily.py` that runs the pipeline, mirrors `report.md` into the vault, commits + pushes `dashboard/` (Pages source), and builds a digest of companies first seen today. `digest.py` exposes `build_digest(store, today) -> str` (new companies + status changes), house style.

- [ ] **Step 1: Write `build_digest` + test**

`tests/test_outputs_digest.py`:
```python
from datetime import date
from radar.model import Company, BeverageVertical
from radar.store import Store
from radar.outputs.digest import build_digest

def test_digest_lists_companies_first_seen_today(tmp_path):
    s = Store(tmp_path / "t.sqlite")
    s.upsert(Company(name="NewCo", domain="newco.ai", vertical=BeverageVertical.BEER,
                     source_urls=["https://newco.ai"],
                     first_seen=date(2026,7,20), last_seen=date(2026,7,20)))
    s.upsert(Company(name="OldCo", domain="oldco.ai",
                     first_seen=date(2026,1,1), last_seen=date(2026,7,20)))
    text = build_digest(s, today=date(2026,7,20))
    assert "NewCo" in text and "OldCo" not in text
    assert "—" not in text
```

`src/radar/outputs/digest.py`:
```python
from __future__ import annotations
from datetime import date
from radar.store import Store


def build_digest(store: Store, today: date | None = None) -> str:
    today = today or date.today()
    new = [c for c in store.all() if c.first_seen == today]
    if not new:
        return f"Beverage-AI Radar {today.isoformat()}: no new companies today.\n"
    lines = [f"Beverage-AI Radar {today.isoformat()}: {len(new)} new companies.", ""]
    for c in sorted(new, key=lambda x: x.name.lower()):
        v = c.vertical.value if c.vertical else "unclassified"
        lines.append(f"- {c.name} ({v}): {c.short_description or ''}".rstrip())
    return "\n".join(lines) + "\n"
```

Run: `.venv/bin/pytest tests/test_outputs_digest.py -v`
Expected: PASS.

- [ ] **Step 2: Write `scripts/radar_daily.py`**

```python
#!/usr/bin/env python3
import subprocess
from datetime import date
from pathlib import Path
from radar import config
from radar.cli import main as radar_main
from radar.store import Store
from radar.outputs.digest import build_digest

ROOT = config.PROJECT_ROOT


def _git(*args):
    subprocess.run(["git", "-C", str(ROOT), *args], check=False)


def main() -> None:
    radar_main(["run"])
    # mirror report into the vault
    report = (config.DASHBOARD_DIR / "report.md")
    if report.exists():
        (config.VAULT_DIR).mkdir(parents=True, exist_ok=True)
        (config.VAULT_DIR / "Landscape Report.md").write_text(report.read_text())
    # publish dashboard
    _git("add", "dashboard")
    _git("commit", "-m", f"data: daily refresh {date.today().isoformat()}")
    _git("push")
    # digest to stdout (email wiring is manual/optional)
    print(build_digest(Store(config.DB_PATH), date.today()))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write the launchd plist** `scripts/com.ankur.beverage-radar.plist` scheduling `radar_daily.py` daily (e.g., 07:30) using the project `.venv/bin/python`, with `PYTHONPATH` set to `src` and stdout/stderr to a log file in the project. Document `launchctl load` in the README.

- [ ] **Step 4: Write `README.md`** — setup (venv, install), `radar run`, dashboard serve, enabling the launchd job, GitHub Pages setup (branch/folder = `dashboard/` or a `docs/` publish), and how sources degrade under rate limits.

- [ ] **Step 5: Configure GitHub Pages (manual)** — create the GitHub repo, push, set Pages to serve the `dashboard/` folder, confirm the URL renders `data.json`.

- [ ] **Step 6: Commit**

```bash
git add scripts/ src/radar/outputs/digest.py tests/test_outputs_digest.py README.md
git commit -m "feat: daily launchd automation, digest, docs, Pages publish"
```

---

## Self-Review Notes

- **Spec coverage:** discovery (Tasks 7-8), enrichment (Task 9), data model + dedup + freshness (Tasks 2-3), rate-limit/caching (Task 4), classification (Task 5), source isolation (Task 6), outputs report+dashboard+vault+Base (Tasks 10, 13; Base file generation folded into `write_vault_notes` — add a `.base` alongside notes during Task 10 if desired), daily cron + digest (Task 14), recency two-tier (Tasks 2, 7, 8, 10). All spec sections map to a task.
- **Placeholder policy:** live-network adapters (Task 12) and Pages setup (Task 14) are genuinely environment-specific and are validated by smoke runs, not left as vague code TODOs. All pure logic ships with real code + tests.
- **Type consistency:** `Company`, `dedup_key`, `compute_status`, `Status`, `run_source`, `export_json`, `render_report`, `run` signatures are consistent across tasks that consume them.
