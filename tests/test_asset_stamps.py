"""The ?v= stamps in index.html must match the files they point at.

A push that edits app.js or styles.css without running
scripts/stamp_assets.py ships new HTML against a cached old stylesheet and
script, and nothing fails: two home-page pushes on 2026-09-27 did exactly
that. This makes the forgotten step a red test instead of a stale site.
"""
import hashlib
import re
from pathlib import Path

DASH = Path(__file__).resolve().parents[1] / "dashboard"
INDEX = (DASH / "index.html").read_text()


def test_stamps_match_file_contents():
    for name in ("app.js", "styles.css"):
        m = re.search(re.escape(name) + r"\?v=([0-9a-f]+)", INDEX)
        assert m, f"{name} has no ?v= stamp in index.html"
        want = hashlib.sha1((DASH / name).read_bytes()).hexdigest()[:10]
        assert m.group(1) == want, f"{name} stamp is stale: run python3 scripts/stamp_assets.py"
