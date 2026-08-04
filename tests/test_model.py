from datetime import date
from radar.model import dedup_key, compute_status, Status, Company, BeverageVertical


def test_dedup_key_normalizes_domain():
    assert dedup_key("Acme AI", "https://www.Acme-AI.com/about", None) == "acme-ai.com"
    assert dedup_key("Acme AI", "http://blog.acme-ai.com", None) == "acme-ai.com"


def test_dedup_key_falls_back_to_name_country_slug():
    assert dedup_key("Brew Brain", None, "Germany") == "brew-brain::germany"


def test_compute_status_active_within_window():
    assert compute_status(date(2025, 6, 1), date(2026, 7, 20), 18) == Status.ACTIVE


def test_compute_status_dormant_past_window():
    assert compute_status(date(2024, 1, 1), date(2026, 7, 20), 18) == Status.DORMANT


def test_company_key_uses_dedup_key():
    c = Company(
        name="Acme AI",
        domain="https://acme-ai.com",
        vertical=BeverageVertical.BEER,
        last_seen=date(2026, 1, 1),
    )
    assert c.key == "acme-ai.com"


def test_every_bool_field_is_registered_for_the_sqlite_round_trip():
    """An unregistered bool becomes the string "True"/"False" in the export.

    That is not cosmetic: the dashboard tests `=== false`, so a stringified
    flag made a former role render as current employment.
    """
    from dataclasses import fields
    from radar.model import Company
    from radar.store import _BOOL_FIELDS

    declared = {
        f.name for f in fields(Company)
        if "bool" in str(f.type).lower()
    }
    missing = declared - set(_BOOL_FIELDS)
    assert not missing, f"bool fields missing from _BOOL_FIELDS: {sorted(missing)}"
