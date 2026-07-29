import json

from radar.prospects.briefs import render_briefs

ROWS = [
    {"tier": 1, "company": "Named Co", "region": "Japan", "vertical": "whisky", "entry": "MD"},
    {"tier": 4, "company": "Some Expo", "region": "Japan", "vertical": "beer", "entry": "desk"},
    {"tier": 1, "company": "Sourced Co", "region": "Japan", "vertical": "beer", "entry": "MD",
     "source_urls": ["https://a.com/x", "https://b.com/y"]},
]


def _render(surface, tmp_path):
    render_briefs([surface], ROWS, tmp_path, today="2026-07-29")
    return (tmp_path / ".prospects" / "briefs" / f"{surface['id']}.md").read_text()


def test_regional_brief_lists_only_its_region(tmp_path):
    ROWS.append({"tier": 1, "company": "Elsewhere", "region": "Africa", "vertical": "beer", "entry": "x"})
    text = _render({"id": "s", "title": "T", "regions": ["Japan"], "scope": "sc"}, tmp_path)
    assert "Named Co" in text and "Elsewhere" not in text
    ROWS.pop()


def test_global_surface_scopes_by_tier_not_by_everything(tmp_path):
    """Regression: the events surface claimed all 61 tier 1-2 rows and
    duplicated every regional agent's re-verify work."""
    text = _render({"id": "e", "title": "Events", "regions": ["Global"], "tiers": [4],
                    "scope": "sc"}, tmp_path)
    assert "Some Expo" in text
    assert "Named Co" not in text
    assert "Re-verify" not in text  # tier 4 is curated, nothing to re-source


def test_unsourced_tier12_rows_go_to_the_reverify_section(tmp_path):
    text = _render({"id": "s", "title": "T", "regions": ["Japan"], "scope": "sc"}, tmp_path)
    assert "Re-verify these 1 existing" in text
    assert "Named Co" in text.split("Re-verify")[1]
    assert "Sourced Co" not in text.split("Re-verify")[1]


def test_brief_names_the_output_path_and_todays_date(tmp_path):
    text = _render({"id": "s", "title": "T", "regions": ["Japan"], "scope": "sc"}, tmp_path)
    assert ".prospects/finds/s.json" in text
    assert "Today is 2026-07-29" in text


def test_no_row_is_claimed_by_two_surfaces(tmp_path):
    """Regression: overlapping surfaces made two agents re-verify the same row.

    Runs against the REAL surface definitions, so adding an overlapping surface
    later fails here rather than silently doubling the sweep's token cost.
    """
    from pathlib import Path

    from radar.prospects.briefs import render_brief

    surfaces = json.loads(Path("data/prospect_surfaces.json").read_text())
    rows = [
        {"tier": 1, "company": "NA Brewer", "region": "North America", "vertical": "beer", "entry": "x"},
        {"tier": 1, "company": "NA Winery", "region": "North America", "vertical": "wine", "entry": "x"},
        {"tier": 1, "company": "Euro Co", "region": "Europe (other)", "vertical": "wine", "entry": "x"},
        {"tier": 1, "company": "DACH Co", "region": "Germany & DACH", "vertical": "beer", "entry": "x"},
        {"tier": 4, "company": "An Expo", "region": "Europe (other)", "vertical": "beer", "entry": "x"},
    ]
    out = tmp_path / "briefs"
    out.mkdir()
    seen = {}
    for s in surfaces:
        text = Path(render_brief(s, rows, out, "2026-07-29")).read_text()
        section = text.split("Re-verify")[1] if "Re-verify" in text else ""
        for r in rows:
            if f"- {r['company']} —" in section:
                assert r["company"] not in seen, (
                    f"{r['company']} claimed by both {seen.get(r['company'])} and {s['id']}"
                )
                seen[r["company"]] = s["id"]
