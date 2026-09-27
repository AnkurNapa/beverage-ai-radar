"""The paper sweep's drinks filter must not fire on ordinary English.

SmartVille, a network intrusion detection paper, was published under whiskey
because its abstract said intrusion detection "must learn", and "must" (as in
grape must) counted as a drinks word. "hop" had the same flaw via "multi-hop".
"""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "sweep_papers", Path(__file__).resolve().parents[1] / "scripts" / "sweep_papers.py")
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)


def work(title, abstract):
    words = abstract.split()
    return {"title": title, "abstract_inverted_index": {w: [i] for i, w in enumerate(words)},
            "doi": "https://doi.org/10.0/x", "publication_year": 2026}


def test_network_paper_saying_must_is_rejected():
    w = work("SmartVille: deep learning online network intrusion detection",
             "intrusion detection must learn from traffic with deep learning over multi-hop links")
    assert sp.to_row(w, "whiskey") is None


def test_grape_must_paper_still_passes():
    w = work("Predicting fermentation of grape must", "a neural network forecasts sugar in fermenting must")
    assert sp.to_row(w, "wine") is not None


def test_hop_aroma_paper_still_passes():
    w = work("Hop aroma prediction", "machine learning predicts hop aroma in dry hopped beer")
    assert sp.to_row(w, "beer") is not None
