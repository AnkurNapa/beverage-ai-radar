import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "build_jobs", Path(__file__).resolve().parents[1] / "scripts" / "build_jobs.py")
build_jobs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_jobs)


def card(title, company=""):
    return {"title": title, "company": company}


def test_keep_requires_both_signals():
    assert build_jobs.keep(card("Data Analyst", "Sierra Nevada Brewing"))
    assert build_jobs.keep(card("Machine Learning Engineer, Winery Ops"))
    assert not build_jobs.keep(card("Data Analyst", "Acme Insurance"))
    assert not build_jobs.keep(card("Cellar Operator", "Sierra Nevada Brewing"))


def test_keep_drops_noise():
    assert not build_jobs.keep(card("Data Analyst Intern", "Diageo Whisky"))


def test_vertical_of():
    assert build_jobs.vertical_of("Brewery Data Analyst") == "beer"
    assert build_jobs.vertical_of("Vineyard ML Scientist") == "wine"
    assert build_jobs.vertical_of("Distillery Data Lead") == "whiskey"
    assert build_jobs.vertical_of("Beer and wine analytics") == "multiple"
    assert build_jobs.vertical_of("Beverage Data Scientist") == "multiple"


def test_word_boundaries_dont_leak():
    # "Spect-rum" and "S-hop" used to read as beverage signals
    assert not build_jobs.keep(card("Sensory Scientist", "Sensory Spectrum Inc"))
    assert not build_jobs.keep(card("Shop Insights Analyst", "PepsiCo"))
    assert build_jobs.vertical_of("Sensory Spectrum Inc") == "multiple"


def test_known_drinks_employer_passes_without_beverage_word():
    assert build_jobs.keep(card("Data Scientist", "Diageo"))
    assert build_jobs.keep(card("Analytics Manager", "Treasury Wine Estates"))
    assert not build_jobs.keep(card("Data Scientist", "Stripe"))


def test_parse_extracts_card():
    page = """<li><div data-entity-urn="urn:li:jobPosting:4012345678">
      <h3 class="base-search-card__title"> Senior Data Scientist </h3>
      <h4 class="base-search-card__subtitle"><a href="#"> Treasury Wine Estates </a></h4>
      <span class="job-search-card__location"> Melbourne, Australia </span>
      <time datetime="2026-07-20"></time></div></li>"""
    (job,) = build_jobs.parse(page)
    assert job["title"] == "Senior Data Scientist"
    assert job["company"] == "Treasury Wine Estates"
    assert job["location"] == "Melbourne, Australia"
    assert job["posted"] == "2026-07-20"
    assert job["url"].endswith("/jobs/view/4012345678")


def test_vertical_falls_back_to_employer():
    assert build_jobs.vertical_of("Data Scientist AB InBev APAC") == "beer"
    assert build_jobs.vertical_of("Analytics Manager Pernod Ricard") == "whiskey"
    assert build_jobs.vertical_of("Insights Manager The Wine Group") == "wine"


def test_company_sweep_keeps_data_roles_only(monkeypatch):
    """A tracked employer's welding vacancy is not radar material; its data
    roles are. Also proves a loose name match alone cannot let a job through."""
    page = """<li><div data-entity-urn="urn:li:jobPosting:4000000001">
        <h3 class="base-search-card__title">Senior Data Scientist</h3>
        <h4 class="base-search-card__subtitle"><a href="#">The HEINEKEN Company</a></h4></div></li>
      <li><div data-entity-urn="urn:li:jobPosting:4000000002">
        <h3 class="base-search-card__title">TIG Welder</h3>
        <h4 class="base-search-card__subtitle"><a href="#">The HEINEKEN Company</a></h4></div></li>"""
    monkeypatch.setattr(build_jobs, "fetch", lambda *a, **k: page)
    monkeypatch.setattr(build_jobs.time, "sleep", lambda s: None)
    jobs = {}
    build_jobs.company_sweep({"heineken": "Heineken"}, jobs)
    assert [j["title"] for j in jobs.values()] == ["Senior Data Scientist"]
    assert next(iter(jobs.values()))["tracked_company"] == "Heineken"


def test_fetch_pages_stops_when_a_page_repeats(monkeypatch):
    """The endpoint has no end-of-results flag: it just replays the last page."""
    page = lambda i: f"""<li><div data-entity-urn="urn:li:jobPosting:400000000{i}">
        <h3 class="base-search-card__title">Role {i}</h3></div></li>"""
    calls = []
    def fake_fetch(kw, loc, start=0):
        calls.append(start)
        return page(0 if start >= 20 else start // 10)  # page 3 repeats page 1
    monkeypatch.setattr(build_jobs, "fetch", fake_fetch)
    monkeypatch.setattr(build_jobs.time, "sleep", lambda s: None)
    got = list(build_jobs.fetch_pages("x"))
    assert [c["title"] for c in got] == ["Role 0", "Role 1"]
    assert calls == [0, 10, 20]


def test_trading_name_strips_editorial_and_legal_noise():
    """A seed name is written for a human reader; a job card is not."""
    assert build_jobs.trading_name("Molson Coors (Atwater Brewery)") == "Molson Coors"
    assert build_jobs.trading_name("Analytical Flavor Systems (Gastrograph AI)") == "Analytical Flavor Systems"
    assert build_jobs.trading_name("Solera Holdings, LLC.") == "Solera Holdings"
    assert build_jobs.trading_name("Tastry") == "Tastry"


def test_mock_company_postings_are_dropped():
    assert not build_jobs.keep(card("Data Analyst", "EFESC Entreprise fictive Chouette"))


def test_country_of_handles_all_three_location_shapes():
    assert build_jobs.country_of("Boston, MA") == "United States"
    assert build_jobs.country_of("London, England, United Kingdom") == "United Kingdom"
    assert build_jobs.country_of("Bengaluru, Karnataka, India") == "India"
    assert build_jobs.country_of("Greater Kolkata Area") == "India"
    assert build_jobs.country_of("New York City Metropolitan Area") == "United States"
    assert build_jobs.country_of("United States") == "United States"


def test_country_of_refuses_to_guess():
    """A wrong country is worse than a missing one: the filter can omit blanks."""
    assert build_jobs.country_of("") == ""
    assert build_jobs.country_of("Greater Nowhereville Area") == ""
