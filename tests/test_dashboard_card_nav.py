"""The Company of the day card must be clickable.

It renders into #pickoftheday, which for a while had no click listener, so its
data-route was dead and the card looked interactive but went nowhere. The click
handler is delegated from the document precisely so a new card container cannot
reintroduce that, and this test fails if it is narrowed back to named lists.
"""
import re
from pathlib import Path

APP = (Path(__file__).resolve().parents[1] / "dashboard" / "app.js").read_text()


def test_card_nav_is_delegated_from_document():
    assert 'document.addEventListener("click", cardNav)' in APP


def test_no_per_container_card_nav_listeners():
    stragglers = re.findall(r'\$\("[\w-]+"\)\.addEventListener\("click", cardNav\)', APP)
    assert stragglers == [], f"cardNav re-narrowed to containers: {stragglers}"


def test_pick_of_the_day_card_carries_a_route():
    potd = APP[APP.index("function paintPick"):]
    potd = potd[:potd.index("\n}")]
    assert 'data-route="c/' in potd
