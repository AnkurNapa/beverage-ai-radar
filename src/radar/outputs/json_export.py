from __future__ import annotations
import json
from dataclasses import fields
from datetime import date
from pathlib import Path
from radar.config import ACTIVE_MONTHS
from radar.model import compute_status, Status
from radar.store import Store
from radar.capabilities import of_company as capabilities_of
from radar.geo import country_of
from radar.scope import scope_of
from radar.themes import theme_of


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
    # Computed here so the dashboard does not carry a second copy of the rules.
    row["theme"] = theme_of(company.ai_use_case)
    # Second axis: theme is the business problem, capabilities are what the
    # solution IS (IoT, AI, ERP, BI, ESG, consultancy). Multi-valued on purpose.
    row["capabilities"] = capabilities_of(row)
    # Normalised once here so the filter, the map and the gap analysis
    # cannot disagree about how many companies a country has.
    row["country"] = country_of(company.hq_location)
    # beverage-native vs a horizontal vendor that also sells into drinks
    row["scope"] = scope_of(row)
    status = (
        compute_status(company.last_seen, today, ACTIVE_MONTHS)
        if company.last_seen
        else Status.DORMANT
    )
    row["status"] = status.value
    return row


def export_json(store: Store, out_path: Path, today: date | None = None) -> None:
    today = today or date.today()
    rows = [_serialize(c, today) for c in store.all()]
    Path(out_path).write_text(json.dumps(rows, indent=2))
