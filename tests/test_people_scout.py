from radar.scout.people import merge_people, render_people_brief


def person(**kw):
    base = {
        "name": "Ana Lima",
        "role": "Head of Data",
        "company": "Vinicola X",
        "location": "Porto Alegre, Brazil",
        "vertical": "wine",
        "short_description": "Leads the vineyard yield model at Vinicola X.",
        "source_urls": ["https://vinicolax.com.br/team", "https://news.example/ana"],
        "last_seen": "2026-09-01",
    }
    return {**base, **kw}


def test_accepts_a_well_sourced_person():
    seed, added, q = merge_people([], [person()])
    assert [p["name"] for p in added] == ["Ana Lima"] and seed == added and q == []


def test_rejects_single_source():
    _, added, q = merge_people([], [person(source_urls=["https://vinicolax.com.br/team"])])
    assert added == [] and q[0]["state"] == "rejected"


def test_linkedin_alone_is_not_independent_evidence():
    urls = ["https://www.linkedin.com/in/ana", "https://br.linkedin.com/in/ana"]
    _, added, q = merge_people([], [person(source_urls=urls)])
    assert added == [] and "linkedin" in q[0]["reason"]


def test_search_result_urls_are_not_sources():
    urls = ["https://vinicolax.com.br/team", "https://www.bing.com/search?q=ana+lima"]
    _, added, q = merge_people([], [person(source_urls=urls)])
    assert added == [] and "search" in q[0]["reason"]


def test_duplicate_by_name_and_company():
    existing = [person()]
    _, added, q = merge_people(existing, [person(name="Ana  Lima.")])
    assert added == [] and q[0]["state"] == "duplicate"


def test_duplicate_by_linkedin_url_even_if_name_spelled_differently():
    existing = [person(linkedin="https://www.linkedin.com/in/ana-lima-1/")]
    new = person(
        name="Anna Lima", company="Other Co", linkedin="https://br.linkedin.com/in/ana-lima-1"
    )
    _, added, q = merge_people(existing, [new])
    assert added == [] and q[0]["state"] == "duplicate"


def test_same_name_different_company_is_a_different_person():
    _, added, _ = merge_people([person()], [person(company="Cervejaria Y")])
    assert len(added) == 1


def test_brief_names_region_and_output_path(tmp_path):
    surface = {"id": "latam", "label": "Latin America", "hint": "Brazil, Chile, Argentina"}
    text = render_people_brief(surface, ["Ana Lima | Vinicola X"], tmp_path)
    assert "Latin America" in text and "find_latam.json" in text and "people_skip.txt" in text
