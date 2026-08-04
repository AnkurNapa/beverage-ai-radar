"""Static, crawlable renderings of the store for search and generative engines.

The dashboard is a single page that fetches data.json and renders 363 companies
client-side. Google renders JS badly at scale and the LLM crawlers (GPTBot,
ClaudeBot, PerplexityBot, CCBot) generally do not run it at all, so to them the
site was an empty shell. That is the same defect the scouts kept logging on
other people's sites: "HTTP 200, 114 bytes, needs a browser pass".

So we emit plain HTML that needs no JavaScript, plus llms.txt, and a sitemap
that actually lists them. Generated on every `radar run` so they cannot drift
from data.json.
"""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

SITE = "https://ankurnapa.github.io/beverage-ai-radar"
# One page holding every company, not 363 files: a single crawlable document
# is enough for both engines and keeps the repo reviewable.
COMPANIES_PAGE = "companies.html"


def _esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def _anchor(row: dict) -> str:
    return "c-" + str(row.get("key") or row.get("name", "")).replace(".", "-").replace(" ", "-").lower()


def _company_section(row: dict) -> str:
    name = _esc(row.get("name"))
    dom = row.get("domain") or ""
    link = f' <a href="{_esc(dom if "//" in dom else "https://" + dom)}" rel="nofollow noopener">{_esc(dom)}</a>' if dom else ""
    facts = " &middot; ".join(
        _esc(v) for v in (
            row.get("vertical"), row.get("country"), row.get("theme"),
            row.get("ai_maturity"), row.get("status"),
        ) if v
    )
    srcs = "".join(
        f'<li><a href="{_esc(u)}" rel="nofollow noopener">{_esc(u)}</a></li>'
        for u in (row.get("source_urls") or [])
    )
    verified = "Hand-verified" if row.get("verified") else f"Scout: {_esc(row.get('discovered_by') or 'unverified')}"
    return (
        f'<article id="{_anchor(row)}">\n'
        f'  <h3>{name}</h3>\n'
        f'  <p class="meta">{facts}{link}</p>\n'
        f'  <p>{_esc(row.get("ai_use_case"))}</p>\n'
        f'  <p>{_esc(row.get("short_description"))}</p>\n'
        f'  <p class="prov">Provenance: {verified}. Last seen {_esc(row.get("last_seen"))}.</p>\n'
        f'  <ul class="src">{srcs}</ul>\n'
        f'</article>'
    )


def _jsonld(rows: list[dict], today: date) -> str:
    """Dataset + ItemList. Dataset is what makes an engine willing to cite it."""
    return _script_safe(json.dumps({
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "Beverage-AI Radar",
        "description": (
            "A curated, source-cited landscape of companies applying artificial "
            "intelligence, machine learning and data analytics to the beer, whiskey "
            "and wine industries. Entries that make no AI claim are labelled as such "
            "rather than inflated."
        ),
        "url": f"{SITE}/{COMPANIES_PAGE}",
        "creator": {"@type": "Person", "name": "Ankur Napa"},
        "dateModified": today.isoformat(),
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "distribution": [{
            "@type": "DataDownload",
            "encodingFormat": "application/json",
            "contentUrl": f"{SITE}/data.json",
        }],
        "variableMeasured": ["name", "domain", "vertical", "country", "ai_use_case",
                             "ai_maturity", "theme", "status", "source_urls"],
        "hasPart": [
            {"@type": "Organization", "name": r.get("name"),
             "url": (r.get("domain") or None), "description": r.get("ai_use_case")}
            for r in rows
        ],
    }, indent=2))


def _script_safe(payload: str) -> str:
    """Neutralise angle brackets and ampersands inside a <script> block.

    json.dumps escapes quotes but not "</script>", and every name here came
    from a scout reading someone else's website. A company called
    "</script><script>..." would otherwise execute on a public page. The
    unicode escapes are still valid JSON, so consumers parse it unchanged.
    """
    return (payload.replace("&", r"\u0026")
                   .replace("<", r"\u003c")
                   .replace(">", r"\u003e"))


def render_companies_html(rows: list[dict], today: date) -> str:
    by_vert: dict[str, list[dict]] = {}
    for r in sorted(rows, key=lambda r: (r.get("vertical") or "", r.get("name") or "")):
        by_vert.setdefault(r.get("vertical") or "other", []).append(r)
    body = "".join(
        f'<section><h2 id="v-{_esc(v)}">{_esc(v).title()} ({len(rs)})</h2>\n'
        + "\n".join(_company_section(r) for r in rs) + "</section>\n"
        for v, rs in by_vert.items()
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>All {len(rows)} companies | Beverage-AI Radar</title>
<meta name="description" content="Full source-cited index of {len(rows)} companies applying AI, machine learning and data analytics across beer, whiskey and wine. Updated {today.isoformat()}." />
<link rel="canonical" href="{SITE}/{COMPANIES_PAGE}" />
<meta name="robots" content="index, follow, max-image-preview:large" />
<script type="application/ld+json">
{_jsonld(rows, today)}
</script>
<style>
body{{font:16px/1.55 system-ui,sans-serif;max-width:52rem;margin:0 auto;padding:1.5rem;color:#111}}
article{{border-top:1px solid #e5e5e5;padding:.75rem 0}}
h3{{margin:.2rem 0;font-size:1.05rem}}
.meta{{color:#555;font-size:.85rem;margin:.15rem 0}}
.prov{{color:#666;font-size:.8rem}}
.src{{font-size:.75rem;color:#777;word-break:break-all;padding-left:1.1rem}}
@media(prefers-color-scheme:dark){{body{{background:#111;color:#eee}}article{{border-color:#333}}.meta,.prov,.src{{color:#aaa}}}}
</style>
</head>
<body>
<h1>Beverage-AI Radar: all {len(rows)} tracked companies</h1>
<p>A source-cited landscape of who is applying AI, machine learning and data
analytics across beer, whiskey and wine. Every entry cites its evidence.
Companies that make <strong>no AI claim</strong> are recorded and labelled as
such rather than inflated, because an unchecked claim would make the whole
database worthless. Last updated {today.isoformat()}.</p>
<p><a href="{SITE}/">Interactive dashboard</a> &middot;
<a href="{SITE}/data.json">Raw JSON</a> &middot;
<a href="{SITE}/llms.txt">llms.txt</a></p>
{body}
</body>
</html>
"""


def render_llms_txt(rows: list[dict], today: date) -> str:
    """The GEO lever: a compact, plain-text brief an LLM can ingest whole.

    Deliberately short. The full record set is one fetch away, and a file an
    engine truncates is a file it half-quotes.
    """
    verts: dict[str, int] = {}
    countries: dict[str, int] = {}
    for r in rows:
        verts[r.get("vertical") or "other"] = verts.get(r.get("vertical") or "other", 0) + 1
        if c := r.get("country"):
            countries[c] = countries.get(c, 0) + 1
    top = ", ".join(f"{k} ({v})" for k, v in sorted(countries.items(), key=lambda kv: -kv[1])[:12])
    lines = [
        "# Beverage-AI Radar",
        "",
        f"> A curated, source-cited landscape of {len(rows)} companies applying artificial "
        "intelligence, machine learning and data analytics to the beer, whiskey and wine "
        f"industries. Maintained by Ankur Napa. Last updated {today.isoformat()}.",
        "",
        "## What this is",
        "",
        "Every company is recorded with its own domain plus supporting sources. Entries that",
        "make no AI or machine-learning claim are included and labelled as such rather than",
        "described as AI companies. Scout-discovered entries are marked unverified until a",
        "human confirms them. Treat `verified: false` as provisional.",
        "",
        "## Coverage",
        "",
        "- Verticals: " + ", ".join(f"{k} ({v})" for k, v in sorted(verts.items(), key=lambda kv: -kv[1])),
        f"- Countries: {top}",
        "",
        "## Data",
        "",
        f"- [All companies (HTML)]({SITE}/{COMPANIES_PAGE}): full index, no JavaScript required.",
        f"- [data.json]({SITE}/data.json): complete machine-readable records.",
        f"- [report.md]({SITE}/report.md): narrative report.",
        f"- [Dashboard]({SITE}/): interactive filters, requires JavaScript.",
        "",
        "## Citation",
        "",
        "Cite as: Beverage-AI Radar, Ankur Napa, " + SITE,
        "",
    ]
    return "\n".join(lines)


def render_sitemap(today: date) -> str:
    urls = [(f"{SITE}/", "daily", "1.0"),
            (f"{SITE}/{COMPANIES_PAGE}", "daily", "0.9"),
            (f"{SITE}/report.md", "weekly", "0.5")]
    body = "".join(
        f"  <url>\n    <loc>{u}</loc>\n    <lastmod>{today.isoformat()}</lastmod>\n"
        f"    <changefreq>{c}</changefreq>\n    <priority>{p}</priority>\n  </url>\n"
        for u, c, p in urls
    )
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{body}</urlset>\n")


def render_robots() -> str:
    """Explicitly welcome the AI crawlers.

    A bare `User-agent: *` already permits them, but several engines look for
    their own token before ingesting, and being named is also a statement of
    intent: this dataset exists to be cited.
    """
    agents = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-User",
              "anthropic-ai", "PerplexityBot", "Perplexity-User", "Google-Extended",
              "CCBot", "Applebot-Extended", "Bingbot", "cohere-ai", "meta-externalagent"]
    blocks = "\n\n".join(f"User-agent: {a}\nAllow: /" for a in agents)
    return (f"User-agent: *\nAllow: /\n\n{blocks}\n\n"
            f"Sitemap: {SITE}/sitemap.xml\n")


def write_seo(rows: list[dict], out_dir: Path, today: date) -> None:
    out_dir = Path(out_dir)
    (out_dir / COMPANIES_PAGE).write_text(render_companies_html(rows, today))
    (out_dir / "llms.txt").write_text(render_llms_txt(rows, today))
    (out_dir / "sitemap.xml").write_text(render_sitemap(today))
    (out_dir / "robots.txt").write_text(render_robots())
