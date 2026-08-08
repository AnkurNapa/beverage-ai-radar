"""The static renderings exist so engines that do not run JavaScript can read
the store. These tests guard the properties that actually deliver that."""

from datetime import date

from radar.outputs.seo import (
    GA_SNIPPET,
    render_companies_html,
    render_llms_txt,
    render_robots,
    render_sitemap,
)

TODAY = date(2026, 8, 4)
ROWS = [
    {
        "name": "Coopers Brewery", "domain": "coopers.com.au", "vertical": "beer",
        "country": "Australia", "theme": "Analytics", "ai_maturity": "shipping",
        "status": "active", "ai_use_case": "visual analytics on production data",
        "short_description": "No AI claim; Tableau visual analytics.",
        "verified": True, "last_seen": "2026-08-04",
        "source_urls": ["https://coopers.com.au/", "https://example.org/a"],
        "key": "coopers.com.au",
    },
    {
        "name": "Ampersand & Co <script>", "domain": "amp.co.uk", "vertical": "wine",
        "country": "United Kingdom", "ai_use_case": "x", "short_description": "y",
        "verified": False, "discovered_by": "scout:wine", "last_seen": "2026-08-04",
        "source_urls": [], "key": "amp.co.uk",
    },
]


def test_company_names_appear_without_javascript():
    out = render_companies_html(ROWS, TODAY)
    assert "Coopers Brewery" in out
    assert "visual analytics on production data" in out
    assert "<script" in out.split("</head>")[0]  # only the JSON-LD, in head
    assert "fetch(" not in out


def test_untrusted_text_is_escaped():
    """Company names come from scouts; a raw <script> must never render.

    Two script blocks are legitimate and known-constant: the JSON-LD block and
    the analytics snippet. Both are stripped by exact match, so the assertion
    below still catches any script that row data managed to produce.
    """
    out = render_companies_html(ROWS, TODAY)
    assert "Ampersand &amp; Co &lt;script&gt;" in out
    assert GA_SNIPPET in out, "analytics snippet missing from the crawlable page"
    # GA_SNIPPET is a module constant with no row interpolation, so removing it
    # cannot mask an injected script.
    assert "{" not in GA_SNIPPET.split("window.GA_MEASUREMENT_ID")[0]
    residue = out.replace('<script type="application/ld+json">', "").replace(GA_SNIPPET, "")
    assert "<script>" not in residue


def test_provenance_is_stated_not_hidden():
    out = render_companies_html(ROWS, TODAY)
    assert "Hand-verified" in out
    assert "Scout: scout:wine" in out


def test_jsonld_declares_a_dataset():
    head = render_companies_html(ROWS, TODAY).split("</head>")[0]
    assert '"@type": "Dataset"' in head
    assert "data.json" in head


def test_llms_txt_leads_with_what_it_is_and_counts_verticals():
    out = render_llms_txt(ROWS, TODAY)
    assert out.startswith("# Beverage-AI Radar")
    assert "beer (1)" in out and "wine (1)" in out
    assert "verified: false" in out  # the provisional caveat must survive


def test_sitemap_lists_the_static_index():
    out = render_sitemap(TODAY)
    assert "companies.html" in out
    assert out.count("<url>") >= 3


def test_robots_names_the_ai_crawlers_and_blocks_nothing():
    out = render_robots()
    for bot in ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended"):
        assert bot in out
    assert "Disallow: /" not in out
    assert "sitemap.xml" in out.lower()


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
        print("ok", fn.__name__)
