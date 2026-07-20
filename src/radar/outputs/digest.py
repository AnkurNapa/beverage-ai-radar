from __future__ import annotations
from datetime import date
from radar.store import Store


def build_digest(store: Store, today: date | None = None) -> str:
    today = today or date.today()
    new = [c for c in store.all() if c.first_seen == today]
    if not new:
        return f"Beverage-AI Radar {today.isoformat()}: no new companies today.\n"
    lines = [f"Beverage-AI Radar {today.isoformat()}: {len(new)} new companies.", ""]
    for c in sorted(new, key=lambda x: x.name.lower()):
        v = c.vertical.value if c.vertical else "unclassified"
        lines.append(f"- {c.name} ({v}): {c.short_description or ''}".rstrip())
    return "\n".join(lines) + "\n"
