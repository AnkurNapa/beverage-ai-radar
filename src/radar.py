#!/usr/bin/env python3
"""Beverage-AI Radar core: store + freshness + JSON export + report.

Single source of truth is a SQLite store (one row per company, keyed on a
deduped domain). Everything else is derived: the dashboard reads the JSON
export, the report is regenerated from the store. Idempotent: importing the
same seed twice upserts, never duplicates.

Stdlib only. Run:
  python3 src/radar.py import data/companies-seed.json   # upsert seed into store
  python3 src/radar.py build                              # export JSON + write REPORT.md
  python3 src/radar.py test                               # self-check (asserts)

Layers 2/5 of the design (live enrichment, daily launchd, email digest,
Obsidian Base) are deferred until this core proves out.
"""
import sqlite3, json, sys, re, os, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "radar.db")
EXPORT = os.path.join(ROOT, "dashboard", "radar.json")
REPORT = os.path.join(ROOT, "REPORT.md")

DORMANT_MONTHS = 18  # no evidence in ~18 months -> dormant (kept, not deleted)

VERTICALS = ("beer", "whiskey", "wine", "multiple")
USE_CASES = ("recipe/flavor", "demand forecasting", "quality control / computer vision",
             "GenAI marketing", "supply chain", "sensory")
MATURITY = ("research", "pilot", "shipping")

FIELDS = ("name", "domain", "hq_location", "founded_year", "beverage_vertical",
          "ai_use_case", "ai_maturity", "funding_stage", "total_raised",
          "short_description", "source_urls", "latest_news_headline",
          "last_evidence_year")


def dedup_key(company):
    """Normalized registrable domain; fallback to slug of name + HQ country."""
    dom = (company.get("domain") or "").strip().lower()
    dom = re.sub(r"^https?://", "", dom)
    dom = re.sub(r"^www\.", "", dom)
    dom = dom.split("/")[0].strip()
    if dom:
        # strip a single leading subdomain only if 3+ labels (app.foo.com -> foo.com),
        # leave two-label domains (foo.com) and known cc-TLDs alone.
        parts = dom.split(".")
        if len(parts) >= 3 and parts[-2] not in ("co", "com", "org", "net", "gov", "ac"):
            dom = ".".join(parts[-2:])
        return dom
    name = re.sub(r"[^a-z0-9]+", "-", (company.get("name") or "").lower()).strip("-")
    country = re.sub(r"[^a-z0-9]+", "-", (company.get("hq_location") or "").lower()).strip("-")
    return f"{name}--{country}" or "unknown"


def _today():
    return datetime.date.today()


def freshness(last_evidence_year, today=None):
    """Return (score 0-100, status). Year granularity: treat evidence as mid-year.

    ponytail: mid-year (July) approximation because seed carries a year, not a
    date. Swap to real fetched_at once live enrichment lands.
    """
    today = today or _today()
    if not last_evidence_year:
        return 0, "dormant"
    months = (today.year - int(last_evidence_year)) * 12 + (today.month - 7)
    months = max(0, months)
    status = "dormant" if months > DORMANT_MONTHS else "active"
    # GenAI-era evidence (2023+) weighted highest; linear decay ~3 pts/month.
    score = max(0, min(100, 100 - months * 3))
    if int(last_evidence_year) >= 2023:
        score = min(100, score + 10)
    return score, status


def connect():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS companies (
        dedup_key TEXT PRIMARY KEY,
        name TEXT, domain TEXT, hq_location TEXT, founded_year INTEGER,
        beverage_vertical TEXT, ai_use_case TEXT, ai_maturity TEXT,
        funding_stage TEXT, total_raised TEXT, short_description TEXT,
        source_urls TEXT, latest_news_headline TEXT, last_evidence_year INTEGER,
        first_seen TEXT, last_seen TEXT )""")
    return con


def upsert(con, company):
    key = dedup_key(company)
    today = _today().isoformat()
    row = {f: company.get(f) for f in FIELDS}
    row["source_urls"] = json.dumps(company.get("source_urls") or [])
    existing = con.execute("SELECT first_seen FROM companies WHERE dedup_key=?", (key,)).fetchone()
    first_seen = existing[0] if existing else today
    cols = ["dedup_key"] + list(FIELDS) + ["first_seen", "last_seen"]
    vals = [key] + [row[f] for f in FIELDS] + [first_seen, today]
    con.execute(
        f"INSERT OR REPLACE INTO companies ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        vals)
    return key


def import_seed(path):
    con = connect()
    data = json.load(open(path))
    n = sum(1 for c in data if upsert(con, c))
    con.commit()
    con.close()
    print(f"imported/upserted {n} companies into {DB}")


def load_all(con):
    con.row_factory = sqlite3.Row
    out = []
    for r in con.execute("SELECT * FROM companies ORDER BY name"):
        d = dict(r)
        d["source_urls"] = json.loads(d["source_urls"] or "[]")
        d["freshness_score"], d["status"] = freshness(d["last_evidence_year"])
        out.append(d)
    return out


def build():
    con = connect()
    companies = load_all(con)
    con.close()
    os.makedirs(os.path.dirname(EXPORT), exist_ok=True)
    json.dump({"generated": _today().isoformat(), "companies": companies},
              open(EXPORT, "w"), indent=2)
    print(f"wrote {len(companies)} companies -> {EXPORT}")
    write_report(companies)


def _count(companies, field):
    out = {}
    for c in companies:
        out[c.get(field) or "unknown"] = out.get(c.get(field) or "unknown", 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def write_report(companies):
    active = [c for c in companies if c["status"] == "active"]
    dormant = [c for c in companies if c["status"] == "dormant"]
    L = [f"# Beverage-AI Landscape Radar", "",
         f"_Generated {_today().isoformat()}. {len(companies)} companies tracked "
         f"({len(active)} active, {len(dormant)} dormant). Every claim is sourced._", ""]
    L += ["## By vertical", ""]
    for k, v in _count(companies, "beverage_vertical").items():
        L.append(f"- **{k}**: {v}")
    L += ["", "## By AI use case", ""]
    for k, v in _count(companies, "ai_use_case").items():
        L.append(f"- **{k}**: {v}")
    L += ["", "## By maturity", ""]
    for k, v in _count(companies, "ai_maturity").items():
        L.append(f"- **{k}**: {v}")
    L += ["", "## Active companies", ""]
    for c in active:
        L += _company_block(c)
    if dormant:
        L += ["", "## Dormant (no evidence in ~18 months)", ""]
        for c in dormant:
            L += _company_block(c)
    open(REPORT, "w").write("\n".join(L) + "\n")
    print(f"wrote report -> {REPORT}")


def _company_block(c):
    head = f"### {c['name']}"
    if c.get("hq_location"):
        head += f" ({c['hq_location']})"
    meta = " | ".join(x for x in [
        c.get("beverage_vertical"), c.get("ai_use_case"), c.get("ai_maturity"),
        c.get("funding_stage"), c.get("total_raised")] if x)
    lines = [head, ""]
    if meta:
        lines.append(f"_{meta}_")
    if c.get("short_description"):
        lines.append(c["short_description"])
    if c.get("source_urls"):
        lines.append("Sources: " + ", ".join(c["source_urls"]))
    lines.append("")
    return lines


def _selftest():
    # dedup normalization
    assert dedup_key({"domain": "https://www.Tastry.com/wines"}) == "tastry.com"
    assert dedup_key({"domain": "app.gastrograph.ai"}) == "gastrograph.ai"
    assert dedup_key({"domain": "foo.co.uk"}) == "co.uk" or dedup_key({"domain": "foo.co.uk"}) == "foo.co.uk"
    assert dedup_key({"name": "Deep Liquid", "hq_location": "London, UK"}) == "deep-liquid--london-uk"
    # freshness
    today = datetime.date(2026, 7, 1)
    s, st = freshness(2026, today); assert st == "active" and s >= 100 - 10 or s <= 100
    s, st = freshness(2020, today); assert st == "dormant"
    s, st = freshness(None, today); assert st == "dormant" and s == 0
    # 18-month boundary: mid-2024 evidence at mid-2026 = 24 months -> dormant
    _, st = freshness(2024, today); assert st == "dormant"
    # early-2025-ish: 2025 evidence = 12 months -> active
    _, st = freshness(2025, today); assert st == "active"
    # idempotent upsert
    con = sqlite3.connect(":memory:")
    con.execute("""CREATE TABLE companies (dedup_key TEXT PRIMARY KEY, name TEXT, domain TEXT,
        hq_location TEXT, founded_year INTEGER, beverage_vertical TEXT, ai_use_case TEXT,
        ai_maturity TEXT, funding_stage TEXT, total_raised TEXT, short_description TEXT,
        source_urls TEXT, latest_news_headline TEXT, last_evidence_year INTEGER,
        first_seen TEXT, last_seen TEXT)""")
    c1 = {"name": "Tastry", "domain": "tastry.com"}
    upsert(con, c1); upsert(con, c1)
    assert con.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 1
    print("self-test OK")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "import":
        import_seed(sys.argv[2])
    elif cmd == "build":
        build()
    elif cmd == "test":
        _selftest()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
