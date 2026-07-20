import sqlite3
from datetime import date
from radar.model import Company
from radar.store import Store


def test_missing_columns_are_added_on_open(tmp_path):
    # simulate an older DB created before a field existed
    p = tmp_path / "old.sqlite"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE companies (key TEXT PRIMARY KEY, name TEXT, domain TEXT)")
    con.commit()
    con.close()

    # opening with the current Store must add the new columns, not crash
    s = Store(p)
    s.upsert(Company(name="X", domain="x.com", company_type="service", last_seen=date(2026, 1, 1)))
    got = s.get("x.com")
    assert got.company_type == "service"
