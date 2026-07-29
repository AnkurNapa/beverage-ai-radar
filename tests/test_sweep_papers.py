import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "sweep_papers", Path(__file__).resolve().parents[1] / "scripts" / "sweep_papers.py")
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)


def work(title, abstract="", year=2024, cites=5, url="https://ex.com/p"):
    words = abstract.split()
    inv = {}
    for i, w in enumerate(words):
        inv.setdefault(w, []).append(i)
    return {"title": title, "abstract_inverted_index": inv or None,
            "publication_year": year, "cited_by_count": cites,
            "primary_location": {"landing_page_url": url, "source": {"display_name": "J. Brew"}},
            "authorships": [{"author": {"display_name": "A. Author"}}]}


def test_beverage_plus_data_is_kept():
    r = sp.to_row(work("Predicting beer flavour with machine learning"), "beer")
    assert r and r["kind"] == "paper" and r["vertical"] == "beer"


def test_beverage_without_a_data_method_is_dropped():
    """A sensory paper with no model is not what this radar tracks."""
    assert sp.to_row(work("A tasting panel study of lager bitterness"), "beer") is None


def test_data_method_without_beverage_is_dropped():
    assert sp.to_row(work("Deep learning for protein folding"), "beer") is None


def test_same_maths_on_something_nobody_here_makes_is_dropped():
    """'Fermentation + neural network' returns a lot of biofuel work."""
    w = work("Neural network control of fermentation",
             "A model for bioethanol and biofuel reactor yield optimisation")
    assert sp.to_row(w, "multiple") is None


def test_off_topic_word_in_the_abstract_survives_if_the_title_is_clearly_beverage():
    w = work("Machine learning for beer fermentation control",
             "Compared against a bioethanol baseline using gradient boosting")
    assert sp.to_row(w, "beer") is not None


def test_abstract_inverted_index_is_reassembled_in_order():
    w = work("Machine learning wine quality", "wine quality prediction using random forest")
    assert sp.abstract_of(w).startswith("wine quality prediction")


def test_open_access_landing_page_beats_the_doi():
    w = work("Machine learning beer quality")
    w["best_oa_location"] = {"landing_page_url": "https://oa.example/paper"}
    w["doi"] = "https://doi.org/10.1/x"
    assert sp.to_row(w, "beer")["url"] == "https://oa.example/paper"


def test_a_row_with_no_reachable_url_is_dropped():
    w = work("Machine learning beer quality")
    w["primary_location"] = {"source": {"display_name": "J"}}
    assert sp.to_row(w, "beer") is None


def test_uci_benchmark_exercise_is_dropped_when_uncited():
    """'Wine Quality Prediction Using Machine Learning' on the UCI CSV: a
    teaching exercise that describes no winery, vintage or instrument."""
    w = work("Wine Quality Prediction Using Machine Learning",
             "We apply random forest to the wine quality dataset", cites=2)
    assert sp.to_row(w, "wine") is None


def test_the_same_genre_survives_if_it_actually_landed():
    w = work("Wine Quality Prediction Using Machine Learning",
             "We apply random forest to the wine quality dataset", cites=140)
    assert sp.to_row(w, "wine") is not None


def test_synthetic_biology_is_out_of_scope():
    w = work("An automated recommendation tool for synthetic biology",
             "machine learning guided fermentation of engineered strains")
    assert sp.to_row(w, "beer") is None
