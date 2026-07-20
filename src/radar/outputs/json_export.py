from __future__ import annotations
import json
from dataclasses import fields
from datetime import date
from pathlib import Path
from radar.config import ACTIVE_MONTHS
from radar.model import compute_status, Status
from radar.store import Store


def _serialize(company, today: date) -> dict:
    row = {}
    for f in fields(company):
        v = getattr(company, f.name)
        if hasattr(v, "value"):
            row[f.name] = v.value
        elif isinstance(v, date):
            row[f.name] = v.isoformat()
        else:
            row[f.name] = v
    row["key"] = company.key
    status = compute_status(company.last_seen, today, ACTIVE_MONTHS) if company.last_seen else Status.DORMANT
    row["status"] = status.value
    return row


def export_json(store: Store, out_path: Path, today: date | None = None) -> None:
    today = today or date.today()
    rows = [_serialize(c, today) for c in store.all()]
    Path(out_path).write_text(json.dumps(rows, indent=2))
