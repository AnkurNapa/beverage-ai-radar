#!/usr/bin/env python3
"""Stamp app.js and styles.css cache-bust versions from their content hashes.

GitHub Pages caches both for ~10 minutes, and the browser caches them longer,
so index.html carries a ?v= query on each. Bumping that by hand fails the way
it just did: styles.css was updated six times while app.js kept a stale hash,
so the browser ran old JavaScript and none of the new UI appeared. Deriving
both from the file contents removes the chance to forget.

Run: python3 scripts/stamp_assets.py   (after editing app.js or styles.css)
"""
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "dashboard" / "index.html"
ASSETS = ("app.js", "styles.css")
# ES module imports carry their own cache-bust query. app.js imports ux.js, and
# a stale cached module is exactly as invisible as a stale cached app.js was.
MODULE_IMPORTS = {"dashboard/app.js": ("ux.js",)}


def main() -> int:
    html = INDEX.read_text()
    changed = []
    for name in ASSETS:
        path = ROOT / "dashboard" / name
        digest = hashlib.sha1(path.read_bytes()).hexdigest()[:10]
        pattern = re.compile(rf"({re.escape(name)}\?v=)([0-9a-f]+)")
        match = pattern.search(html)
        if not match:
            print(f"  ! {name} has no ?v= query in index.html")
            continue
        if match.group(2) != digest:
            changed.append(f"{name}: {match.group(2)} -> {digest}")
        html = pattern.sub(rf"\g<1>{digest}", html)
    INDEX.write_text(html)

    for importer, mods in MODULE_IMPORTS.items():
        src = ROOT / importer
        text = src.read_text()
        for mod in mods:
            digest = hashlib.sha1((ROOT / "dashboard" / mod).read_bytes()).hexdigest()[:10]
            pattern = re.compile(rf"({re.escape(mod)}\?v=)([0-9a-f]+)")
            m = pattern.search(text)
            if m and m.group(2) != digest:
                changed.append(f"{importer} -> {mod}: {m.group(2)} -> {digest}")
            text = pattern.sub(rf"\g<1>{digest}", text)
        src.write_text(text)
        # app.js just changed, so its own stamp in index.html is now stale.
        d2 = hashlib.sha1(src.read_bytes()).hexdigest()[:10]
        html2 = INDEX.read_text()
        name = Path(importer).name
        html2 = re.sub(rf"({re.escape(name)}\?v=)([0-9a-f]+)", rf"\g<1>{d2}", html2)
        INDEX.write_text(html2)
    print("\n".join(f"  {c}" for c in changed) if changed else "  already current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
