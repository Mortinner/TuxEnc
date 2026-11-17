import pytest

from retitler.matching import normalize, score_candidate, similarity


def test_normalize():
    assert normalize("¡El Señor de los Anillos!") == "senor de los anillos"
    assert normalize("The Office (US)") == "office us"
    assert normalize("Tom & Jerry") == "tom and jerry"
    assert normalize("The") == "the"  # un artículo solo no se elimina


@pytest.mark.parametrize("a, b", [("Breaking Bad", "breaking bad"), ("Amélie", "Amelie"), ("The Wire", "Wire")])
def test_similarity_equal(a, b):
    assert similarity(a, b) == 1.0


def test_similarity_ordering():
    assert similarity("Breaking Bad", "Breaking Bat") > similarity("Breaking Bad", "Better Call Saul")
    assert similarity("Bad Breaking", "Breaking Bad") > 0.9  # orden de palabras distinto
    assert similarity("", "x") == 0.0


def test_year_bonus_and_penalty():
    same = score_candidate("Dune", 2021, ["Dune"], 2021)
    off_by_one = score_candidate("Dune", 2021, ["Dune"], 2020)
    wrong = score_candidate("Dune", 2021, ["Dune"], 1984)
    unknown = score_candidate("Dune", None, ["Dune"], 1984)
    assert same > off_by_one > unknown > wrong


def test_uses_best_of_titles():
    assert score_candidate("La casa de papel", None, ["Money Heist", "La Casa de Papel"], None) >= 1.0


def test_popularity_only_breaks_ties():
    assert score_candidate("X", None, ["Y Y Y"], None, 100) < score_candidate("X", None, ["X"], None, 0)
