from datetime import date

from radar.harvest import people_from_works

TODAY = date(2026, 9, 28)


def work(doi, year, authors):
    return {
        "doi": f"https://doi.org/{doi}",
        "publication_year": year,
        "authorships": [
            {
                "author_position": pos,
                "author": {"id": f"https://openalex.org/{aid}", "display_name": name},
                "institutions": [{"id": f"https://openalex.org/{iid}", "display_name": inst}],
            }
            for aid, name, pos, iid, inst in authors
        ],
    }


PLACES = {
    "https://openalex.org/I1": "Adelaide, Australia",
    "https://openalex.org/I2": "Leuven, Belgium",
}
VERT = {"https://doi.org/10.1/a": "wine", "https://doi.org/10.1/b": "wine"}


def test_lead_and_senior_authors_publish_middle_authors_of_one_paper_do_not():
    w = work(
        "10.1/a",
        2024,
        [
            ("A1", "Lead Author", "first", "I1", "Uni Adelaide"),
            ("A2", "Middle Author", "middle", "I1", "Uni Adelaide"),
            ("A3", "Senior Author", "last", "I2", "KU Leuven"),
        ],
    )
    people, candidates = people_from_works([w], VERT, PLACES, today=TODAY)
    assert sorted(p["name"] for p in people) == ["Lead Author", "Senior Author"]
    assert [c["name"] for c in candidates] == ["Middle Author"]


def test_middle_author_on_two_papers_publishes():
    a = work("10.1/a", 2023, [("A2", "Middle Author", "middle", "I1", "Uni Adelaide")])
    b = work("10.1/b", 2024, [("A2", "Middle Author", "middle", "I1", "Uni Adelaide")])
    people, _ = people_from_works([a, b], VERT, PLACES, today=TODAY)
    [p] = people
    assert len([u for u in p["source_urls"] if "doi.org" in u]) == 2


def test_row_carries_two_non_linkedin_sources_location_and_research_maturity():
    w = work("10.1/a", 2024, [("A1", "Lead Author", "first", "I1", "Uni Adelaide")])
    [p], _ = people_from_works([w], VERT, PLACES, today=TODAY)
    assert p["source_urls"] == ["https://doi.org/10.1/a", "https://openalex.org/A1"]
    assert p["location"] == "Adelaide, Australia" and p["company"] == "Uni Adelaide"
    assert p["ai_maturity"] == "research" and p["vertical"] == "wine" and p["linkedin"] is None


def test_papers_older_than_the_recency_window_are_ignored():
    w = work("10.1/a", 2010, [("A1", "Lead Author", "first", "I1", "Uni Adelaide")])
    people, candidates = people_from_works([w], VERT, PLACES, today=TODAY)
    assert people == [] and candidates == []


def test_title_gate_drops_papers_without_a_beverage_word_in_the_title():
    w = {
        **work("10.1/a", 2024, [("A1", "Lead Author", "first", "I1", "Uni")]),
        "title": "A sensor survey",
    }
    people, _ = people_from_works([w], VERT, PLACES, TODAY, title_ok=lambda t: "wine" in t)
    assert people == []


def test_cutoff_is_by_date_not_year():
    w = {
        **work("10.1/a", 2016, [("A1", "Lead Author", "first", "I1", "Uni")]),
        "publication_date": "2016-07-01",
    }
    people, _ = people_from_works([w], VERT, PLACES, today=TODAY)
    assert people == []
