import json
from datetime import date
from radar.model import Company, BeverageVertical
from radar.store import Store
from radar.outputs.json_export import export_json


def seed(tmp_path):
    s = Store(tmp_path / "t.sqlite")
    s.upsert(Company(name="BrewBrain", domain="brewbrain.ai",
                     vertical=BeverageVertical.BEER, ai_use_case="recipe / flavor prediction",
                     source_urls=["https://brewbrain.ai"],
                     first_seen=date(2026, 1, 1), last_seen=date(2026, 6, 1)))
    s.upsert(Company(name="OldCask", domain="oldcask.com",
                     vertical=BeverageVertical.WHISKEY,
                     source_urls=["https://oldcask.com"],
                     first_seen=date(2021, 1, 1), last_seen=date(2023, 1, 1)))
    return s


def test_export_json_sets_status(tmp_path):
    s = seed(tmp_path)
    out = tmp_path / "data.json"
    export_json(s, out, today=date(2026, 7, 20))
    rows = json.loads(out.read_text())
    by_key = {r["key"]: r for r in rows}
    assert by_key["brewbrain.ai"]["status"] == "active"
    assert by_key["oldcask.com"]["status"] == "dormant"
