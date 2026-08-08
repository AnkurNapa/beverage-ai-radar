#!/usr/bin/env python3
"""Build dashboard/events.json from the curated data/events.json.

Two kinds of row share one file on purpose: industry events (trade fairs,
technical conferences) and Ankur's own speaking. Keeping them together is the
point, because the question a reader actually has is "where does this field
gather, and where has he stood up in front of it", and splitting that across
two tabs answers neither well. The `speaking` flag separates them on demand.

Derived here rather than in the browser: `state` (upcoming / past / undated)
and `sort`. Dates are optional by design. An event whose organiser has not
published dates is recorded with none rather than a guess, and it stays
visible under "undated" instead of silently vanishing from an upcoming filter.

Run: python3 scripts/build_events.py
"""
from __future__ import annotations  # repo runs Python 3.9; `date | None` needs this

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "events.json"
OUT = ROOT / "dashboard" / "events.json"

VALID_MODES = {"in-person", "online", "hybrid"}


def _parse(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def build(today: date | None = None) -> list[dict]:
    today = today or date.today()
    rows = json.loads(SRC.read_text())
    out = []
    for r in rows:
        if not r.get("url") or not r.get("title"):
            continue
        mode = r.get("mode") or "in-person"
        if mode not in VALID_MODES:
            print(f"skip {r['title']}: unknown mode {mode!r}")
            continue
        start, end = _parse(r.get("start")), _parse(r.get("end"))
        # An event runs until its end date, so it is still "upcoming" on day two
        # of a three day fair. Using the start date would drop it mid-event.
        finish = end or start
        if finish is None:
            state = "undated"
        elif finish >= today:
            state = "upcoming"
        else:
            state = "past"
        out.append({
            **{k: r.get(k) for k in
               ("title", "url", "organiser", "location", "country", "vertical", "summary")},
            # Named speakers, so an event says WHO is talking, not just that it
            # exists. Empty for trade fairs, which publish exhibitors not speakers.
            "speakers": [x for x in (r.get("speakers") or []) if x],
            "mode": mode,
            "speaking": bool(r.get("speaking")),
            "start": r.get("start") or "",
            "end": r.get("end") or "",
            "state": state,
            # Upcoming sorts soonest-first; past sorts most-recent-first. One
            # numeric key can express both: negate for past.
            "sort": (start or finish or date(1900, 1, 1)).isoformat(),
        })

    order = {"upcoming": 0, "undated": 1, "past": 2}
    out.sort(key=lambda e: (order[e["state"]],
                            e["sort"] if e["state"] != "past" else "",
                            e["sort"] if e["state"] == "past" else ""), reverse=False)
    # past should read newest-first within its block
    past = [e for e in out if e["state"] == "past"]
    past.sort(key=lambda e: e["sort"], reverse=True)
    out = [e for e in out if e["state"] != "past"] + past
    return out


def main() -> int:
    rows = build()
    OUT.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    counts = {}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    speaking = sum(1 for r in rows if r["speaking"])
    print("wrote %d events to %s: %s, %d speaking" % (len(rows), OUT, counts, speaking))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
