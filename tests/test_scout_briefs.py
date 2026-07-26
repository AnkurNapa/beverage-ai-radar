from datetime import date

from radar.scout.briefs import render_briefs

SURFACES = [
    {"id": "whiskey", "label": "Whiskey and spirits", "hint": "distilleries, casks"},
    {"id": "aws", "label": "AWS Marketplace", "hint": "listings", "note": "thin on SaaS"},
]
GAPS = [
    {"axis": "vertical", "value": "whiskey", "count": 9, "share": 0.08, "reason": "9 of 109"},
]
EXISTING = ["Tastry | tastry.com", "Vivino | vivino.com"]


def test_one_brief_per_surface(tmp_path):
    written = render_briefs(SURFACES, GAPS, EXISTING, tmp_path, date(2026, 7, 26))
    assert [p.name for p in written] == ["whiskey.md", "aws.md"]


def test_brief_carries_surface_gaps_and_schema(tmp_path):
    written = render_briefs(SURFACES, GAPS, EXISTING, tmp_path, date(2026, 7, 26))
    text = written[0].read_text()
    assert "Whiskey and spirits" in text
    assert "whiskey" in text and "9 of 109" in text
    assert '"source_urls"' in text
    assert "find_whiskey.json" in text


def test_skip_list_is_generated_not_pasted(tmp_path):
    render_briefs(SURFACES, GAPS, EXISTING, tmp_path, date(2026, 7, 26))
    names = (tmp_path / "existing_names.txt").read_text()
    assert "Tastry | tastry.com" in names
    assert "Vivino | vivino.com" in names


def test_scope_and_verification_rules_are_present(tmp_path):
    """These exist because real sweeps disagreed without them."""
    written = render_briefs(SURFACES, GAPS, EXISTING, tmp_path, date(2026, 7, 26))
    text = written[0].read_text()
    assert "Operators count" in text
    assert "Blocked is not rejected" in text
    assert "No real ML is a finding" in text


def test_surface_note_is_passed_through(tmp_path):
    written = render_briefs(SURFACES, GAPS, EXISTING, tmp_path, date(2026, 7, 26))
    assert "thin on SaaS" in written[1].read_text()
