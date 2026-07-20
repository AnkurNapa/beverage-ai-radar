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
    c = Company(name="Acme AI", domain="https://acme-ai.com",
                vertical=BeverageVertical.BEER, last_seen=date(2026, 1, 1))
    assert c.key == "acme-ai.com"
