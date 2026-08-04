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


def test_curated_upsert_corrects_an_existing_value():
    """The seed is the source of truth; editing it must actually change things.

    Before this, _merge only filled nulls, so correcting a location or an
    employer in the seed silently did nothing.
    """
    from datetime import date
    from radar.model import Company
    from radar.store import Store

    store = Store(":memory:")
    store.upsert(Company(name="X", domain="x.com", hq_location="Bangalore, India",
                         last_seen=date(2026, 1, 1)))
    store.upsert(Company(name="X", domain="x.com", hq_location="Australia",
                         last_seen=date(2026, 8, 4)), authoritative=True)
    assert store.get("x.com").hq_location == "Australia"

def test_relocating_a_person_drops_the_superseded_row():
    """Domainless rows are keyed slug(name)::country, so a location fix mints a
    new key and used to leave the old row in the export."""
    from radar.store import Store
    from radar.model import Company
    from datetime import date
    store = Store(":memory:")
    old = Company(name="P", hq_location="India", company_type="individual",
                  discovered_by="curated", last_seen=date(2026, 1, 1))
    new = Company(name="P", hq_location="Australia", company_type="individual",
                  discovered_by="curated", last_seen=date(2026, 8, 4))
    store.upsert(old)
    store.upsert(new, authoritative=True)
    assert len(store.all()) == 2
    assert store.drop_renamed([new]) == ["p::india"]
    assert [c.key for c in store.all()] == ["p::australia"]


def test_dedup_never_touches_rows_it_did_not_supersede():
    """The first attempt deleted everything the source did not emit this run,
    which removed 130 legitimate companies. Only same-name siblings go."""
    from radar.store import Store
    from radar.model import Company
    from datetime import date
    store = Store(":memory:")
    keep = Company(name="AVEVA", domain="aveva.com", discovered_by="curated",
                   last_seen=date(2026, 8, 4))
    moved = Company(name="P", hq_location="Australia", company_type="individual",
                    discovered_by="curated", last_seen=date(2026, 8, 4))
    store.upsert(keep)
    store.upsert(moved)
    assert store.drop_renamed([moved]) == []
    assert {c.key for c in store.all()} == {"aveva.com", "p::australia"}
