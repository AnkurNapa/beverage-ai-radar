from radar.coverage import country_grid, frontier, record_sweep, rotate_locations


def co(name, hq="Munich, Germany", people=None, key_people=None):
    return {"name": name, "hq_location": hq, "people": people or [], "key_people": key_people}


def test_company_with_no_people_anywhere_is_on_the_people_frontier():
    f = frontier([co("Brauerei A"), co("Wine B", key_people="Jo (CEO)")], people=[], jobs=[])
    assert f["companies_without_people"] == ["Brauerei A"]


def test_person_seed_employer_counts_as_people_coverage():
    people = [{"name": "Kai", "company": "Brauerei A GmbH"}]
    f = frontier([co("Brauerei A")], people=people, jobs=[])
    assert f["companies_without_people"] == []


def test_untracked_employers_from_people_and_jobs_are_listed_once_with_evidence():
    people = [{"name": "Ana", "company": "Vinicola X"}]
    jobs = [
        {"company": "Vinicola X", "title": "Data Lead", "url": "https://j/1"},
        {"company": "Tracked Brew Co", "title": "Analyst", "url": "https://j/2"},
    ]
    f = frontier([co("Tracked Brew Co")], people=people, jobs=jobs)
    [row] = f["untracked_employers"]
    assert row["name"] == "Vinicola X" and len(row["evidence"]) == 2


def test_grid_flags_countries_with_companies_but_no_people_or_jobs():
    grid = country_grid(
        [co("A", "Munich, Germany"), co("B", "Lyon, France")],
        people=[{"name": "P", "location": "Paris, France"}],
        jobs=[{"company": "X", "country": "France"}],
    )
    assert grid["Germany"] == {"companies": 1, "people": 0, "jobs": 0, "thin": True}
    assert grid["France"]["thin"] is False


def test_rotate_locations_keeps_base_and_walks_the_rest():
    extra = ["Germany", "France", "Chile", "Japan"]
    first, cur = rotate_locations(["", "India"], extra, per_run=3, cursor=0)
    assert first == ["", "India", "Germany", "France", "Chile"] and cur == 3
    second, cur = rotate_locations(["", "India"], extra, per_run=3, cursor=cur)
    assert second == ["", "India", "Japan", "Germany", "France"] and cur == 2


def test_record_sweep_appends_to_ledger(tmp_path):
    path = tmp_path / "ledger.json"
    record_sweep(path, "people", "latam", found=10, added=8, today="2026-09-28")
    record_sweep(path, "people", "latam", found=3, added=0, today="2026-10-05")
    import json

    rows = json.loads(path.read_text())
    assert [r["added"] for r in rows] == [8, 0] and rows[1]["date"] == "2026-10-05"


def test_alias_matches_trading_name():
    abi = {**co("Anheuser-Busch InBev"), "aliases": ["AB InBev"]}
    f = frontier([abi], people=[{"name": "X", "company": "AB InBev APAC"}], jobs=[])
    assert f["untracked_employers"] == []


def test_briefed_items_are_skipped_until_the_window_passes(tmp_path):
    from radar.coverage import recently_briefed, record_briefed

    path = tmp_path / "ledger.json"
    record_briefed(path, "frontier", "people_1", ["Brauerei A"], today="2026-09-01")
    assert recently_briefed(path, "2026-09-28", days=60) == {"Brauerei A"}
    assert recently_briefed(path, "2026-12-01", days=60) == set()


def test_prospect_frontier_lists_hiring_and_employing_operators_not_yet_prospects():
    from radar.coverage import prospect_frontier

    prospects = [{"company": "Known Brewery Ltd"}]
    jobs = [
        {"company": "Known Brewery", "title": "Data Analyst", "url": "https://j/1"},
        {"company": "New Winery", "title": "BI Lead", "url": "https://j/2"},
    ]
    people = [
        {"name": "A", "company": "New Winery"},
        {"name": "B", "company": "Stellenbosch University"},
    ]
    [row] = prospect_frontier(prospects, people, jobs)
    assert row["name"] == "New Winery" and row["hiring"] is True and len(row["evidence"]) == 2


def test_universities_are_not_company_frontier_items():
    f = frontier([], people=[{"name": "R", "company": "University of Adelaide"}], jobs=[])
    assert f["untracked_employers"] == []
