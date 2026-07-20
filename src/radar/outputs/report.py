from __future__ import annotations
from collections import Counter
from datetime import date
from radar.config import ACTIVE_MONTHS
from radar.model import compute_status, Status
from radar.outputs.people_fmt import people_md
from radar.store import Store


def render_report(store: Store, today: date | None = None) -> str:
    today = today or date.today()
    companies = store.all()
    active, dormant = [], []
    for c in companies:
        bucket = (
            active
            if (c.last_seen and compute_status(c.last_seen, today, ACTIVE_MONTHS) == Status.ACTIVE)
            else dormant
        )
        bucket.append(c)

    verticals = Counter(c.vertical.value for c in active if c.vertical)
    use_cases = Counter(c.ai_use_case for c in active if c.ai_use_case)

    lines = [
        "# Beverage-AI Landscape Radar",
        "",
        f"Snapshot: {today.isoformat()}. {len(active)} active, {len(dormant)} dormant.",
        "",
    ]
    lines += ["## Active companies", ""]
    for c in sorted(active, key=lambda x: x.name.lower()):
        vertical = c.vertical.value if c.vertical else "unclassified"
        use = c.ai_use_case or "unspecified use case"
        pm = people_md(c)
        people = f" People: {pm}." if pm else ""
        lines.append(
            f"- **{c.name}** ({vertical}, {use}). {c.short_description or ''}{people}".rstrip()
        )
    lines += ["", "## Dormant companies", ""]
    for c in sorted(dormant, key=lambda x: x.name.lower()):
        lines.append(f"- {c.name} (last seen {c.last_seen})")
    lines += ["", "## By vertical (active)", ""]
    lines += [f"- {k}: {v}" for k, v in verticals.most_common()]
    lines += ["", "## By use case (active)", ""]
    lines += [f"- {k}: {v}" for k, v in use_cases.most_common()]
    return "\n".join(lines) + "\n"
