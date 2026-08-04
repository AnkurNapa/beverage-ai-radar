"""Regenerate the social share image from live counts.

The hand-made og.png sat at 110 companies / 100 people / 83 resources while the
store had grown to 407. A share card with numbers a third of the truth is worse
than no numbers, so it is generated from dashboard/data.json instead of being
maintained by hand.

Rendered with headless Chrome because there is no image toolchain on this
machine (no poppler, no wkhtmltopdf); Chrome is already the PDF path here.

Run standalone, or let `radar run` call it.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "dashboard"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# WhatsApp is the tightest consumer: it silently drops previews for large
# images, so the card stays well under 300KB. 1200x630 is the OG standard.
WIDTH, HEIGHT = 1200, 630


def counts() -> dict:
    data = json.loads((DASH / "data.json").read_text())
    companies = [r for r in data if r.get("company_type") != "individual"]
    resources = 0
    res_path = DASH / "resources.json"
    if res_path.exists():
        r = json.loads(res_path.read_text())
        resources = len(r if isinstance(r, list) else r.get("resources", []))
    return {
        "companies": len(companies),
        "people": sum(len(r.get("people") or []) for r in data),
        "resources": resources,
    }


def card_html(c: dict, today: date) -> str:
    """Deliberately no external fonts or images: Chrome must render this
    offline and deterministically, and a webfont that fails to load silently
    changes the layout."""
    return f"""<!doctype html>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: {WIDTH}px; height: {HEIGHT}px; overflow: hidden;
    font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
    color: #fff;
    background: #06101c;
    background-image:
      radial-gradient(900px 600px at 88% 14%, rgba(53,224,122,.20), transparent 62%),
      linear-gradient(135deg, #06101c 0%, #0b2038 52%, #0a2f4f 100%);
    position: relative;
  }}
  /* Concentric sweep, echoing the dashboard's radar motif. */
  .rings {{ position: absolute; right: -190px; top: -180px; width: 760px; height: 760px;
           border-radius: 50%; opacity: .16;
           background:
             repeating-radial-gradient(circle, rgba(53,224,122,.9) 0 1.5px, transparent 1.5px 86px); }}
  .wrap {{ position: relative; padding: 66px 74px; height: 100%;
           display: flex; flex-direction: column; }}
  .eyebrow {{ font-size: 21px; letter-spacing: .19em; text-transform: uppercase;
              color: #35e07a; font-weight: 700; }}
  h1 {{ font-size: 82px; line-height: 1.02; letter-spacing: -.022em; margin: 20px 0 0;
        font-weight: 800; }}
  .lede {{ font-size: 30px; line-height: 1.42; color: #c8d6e5; margin-top: 20px;
           max-width: 20ch; }}
  .stats {{ display: flex; gap: 20px; margin-top: auto; }}
  .stat {{ background: rgba(255,255,255,.055); border: 1px solid rgba(255,255,255,.12);
           border-radius: 15px; padding: 20px 30px; min-width: 214px; }}
  .n {{ font-size: 52px; font-weight: 800; letter-spacing: -.02em; }}
  .l {{ font-size: 19px; color: #a8bccd; margin-top: 5px; }}
  .foot {{ margin-top: 26px; font-size: 19px; color: #8fa6ba; }}
  .foot b {{ color: #35e07a; font-weight: 600; }}
</style>
<div class="rings"></div>
<div class="wrap">
  <div class="eyebrow">Landscape Report</div>
  <h1>Beverage&#8209;AI Radar</h1>
  <p class="lede">Who is applying AI and data to beer, whiskey and wine.</p>
  <div class="stats">
    <div class="stat"><div class="n">{c['companies']}</div><div class="l">companies &amp; ventures</div></div>
    <div class="stat"><div class="n">{c['people']}</div><div class="l">named people</div></div>
    <div class="stat"><div class="n">{c['resources']}</div><div class="l">papers, news &amp; talks</div></div>
  </div>
  <div class="foot">ankurnapa.github.io/beverage-ai-radar &nbsp;&middot;&nbsp;
    <b>every entry source-cited</b> &nbsp;&middot;&nbsp; updated {today.isoformat()}</div>
</div>
"""


def build(today: date | None = None) -> Path | None:
    today = today or date.today()
    if not Path(CHROME).exists():
        print("skip: Chrome not found, og.png left as is", file=sys.stderr)
        return None
    c = counts()
    out = DASH / "og.png"
    with tempfile.TemporaryDirectory() as tmp:
        html = Path(tmp) / "card.html"
        html.write_text(card_html(c, today))
        shot = Path(tmp) / "og.png"
        # Chrome writes the screenshot and then does not exit, so waiting on
        # the process always burns the full timeout. Wait for the FILE to
        # appear and stop growing, then stop the process ourselves.
        proc = subprocess.Popen(
            [CHROME, "--headless=old", "--disable-gpu", "--no-sandbox",
             "--no-first-run", "--no-default-browser-check", "--disable-extensions",
             "--hide-scrollbars",
             f"--screenshot={shot}",
             f"--window-size={WIDTH},{HEIGHT}",
             f"--user-data-dir={Path(tmp) / 'profile'}",
             html.as_uri()],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 60
            stable = None
            while time.monotonic() < deadline:
                if shot.exists():
                    size = shot.stat().st_size
                    if size and size == stable:
                        break
                    stable = size
                time.sleep(0.5)
            else:
                raise RuntimeError("Chrome never produced a screenshot")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        # Chrome only emits PNG, and a full-bleed gradient makes that ~440KB,
        # past the size where WhatsApp quietly drops the preview. sips ships
        # with macOS, so re-encoding to JPEG needs no new dependency; the card
        # is a flat gradient with text, which JPEG handles without visible loss.
        jpg = DASH / "og.jpg"
        try:
            subprocess.run(
                ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "82",
                 str(Path(tmp) / "og.png"), "--out", str(jpg)],
                check=True, capture_output=True, timeout=60,
            )
            out = jpg
            # Deliberately not rewriting og.png: nothing references it since
            # the tags moved to the JPEG, and regenerating a 450KB PNG on every
            # run would churn half a megabyte through git for nothing. The old
            # file stays put so any long-cached share still resolves.
        except (subprocess.SubprocessError, FileNotFoundError):
            print("sips unavailable, keeping PNG", file=sys.stderr)
            shutil.copy(Path(tmp) / "og.png", out)
    kb = out.stat().st_size / 1024
    print(f"{out.name} rebuilt: {c['companies']} companies, {c['people']} people, "
          f"{c['resources']} resources, {kb:.0f}KB")
    # Restamp the og:image URL with the new content hash. Without this the
    # card regenerates but every share still shows the cached old one, because
    # WhatsApp and friends key their preview cache on the URL, not the bytes.
    idx = DASH / "index.html"
    if idx.exists():
        v = hashlib.sha1(out.read_bytes()).hexdigest()[:8]
        html = idx.read_text()
        stamped = re.sub(
            r'(https://ankurnapa\.github\.io/beverage-ai-radar/og\.(?:jpg|png))\?v=[a-f0-9]+',
            rf'\g<1>?v={v}', html)
        if stamped != html:
            idx.write_text(stamped)
            print(f"og:image url restamped -> {v}")

    if kb > 300:
        print(f"warning: {kb:.0f}KB may exceed WhatsApp's preview limit", file=sys.stderr)
    return out
    return out


if __name__ == "__main__":
    build()
