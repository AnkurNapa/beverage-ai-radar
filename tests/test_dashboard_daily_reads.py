"""Paper, video and article of the day must render on the landing page.

Each slot needs its container in index.html, a paintReadPick call and a boot
call to paintReads. The pool must also skip items with no summary line: the
swept OpenAlex papers carry none, and the first build showed a card with a
title and nothing else.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "dashboard"
APP = (ROOT / "app.js").read_text()
HTML = (ROOT / "index.html").read_text()
SLOTS = ("paperoftheday", "videooftheday", "articleoftheday")


def test_each_slot_has_a_container_and_a_painter():
    for slot in SLOTS:
        assert f'id="{slot}"' in HTML
        assert f'paintReadPick("{slot}"' in APP


def test_reads_are_painted_at_boot():
    assert "try { paintReads(); }" in APP


def test_pool_requires_a_summary_line():
    assert "(r.finding || r.summary)" in APP


def test_every_slot_has_a_pool_today():
    res = json.loads((ROOT / "resources.json").read_text())
    for kinds in (["paper"], ["video"], ["news", "blog"]):
        pool = [r for r in res if r["kind"] in kinds and (r.get("finding") or r.get("summary"))]
        assert pool, f"no items with a summary for {kinds}"
