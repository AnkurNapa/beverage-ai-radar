from __future__ import annotations
from datetime import date
from pathlib import Path
from radar.config import ACTIVE_MONTHS
from radar.model import compute_status, Status
from radar.outputs.people_fmt import people_md
from radar.store import Store


def _note(company, today: date) -> str:
    status = (
        compute_status(company.last_seen, today, ACTIVE_MONTHS)
        if company.last_seen
        else Status.DORMANT
    )
    fm = [
        "---",
        f"name: {company.name}",
        f"domain: {company.domain or ''}",
        f"vertical: {company.vertical.value if company.vertical else ''}",
        f"ai_use_case: {company.ai_use_case or ''}",
        f"ai_maturity: {company.ai_maturity.value if company.ai_maturity else ''}",
        f"key_people: {company.key_people or ''}",
        f"status: {status.value}",
        f"last_seen: {company.last_seen or ''}",
        "---",
        "",
        f"# {company.name}",
        "",
        company.short_description or "",
        "",
    ]
    pm = people_md(company)
    if pm:
        fm += ["## People", pm, ""]
    fm += ["## Evidence"]
    fm += [f"- {u}" for u in company.source_urls]
    return "\n".join(fm) + "\n"


def write_vault_notes(store: Store, vault_dir: Path, today: date | None = None) -> int:
    today = today or date.today()
    vault_dir = Path(vault_dir)
    vault_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for c in store.all():
        safe = c.key.replace("/", "-").replace(":", "-")
        (vault_dir / f"{safe}.md").write_text(_note(c, today))
        count += 1
    return count
