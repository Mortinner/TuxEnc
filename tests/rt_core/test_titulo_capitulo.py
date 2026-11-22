"""1.3.6: si el título que trae el archivo es el de otro capítulo, se pregunta en vez de renombrar.

Caso de Marcos: sus «SeaQuest DSV - S001E01 - La ventana del diablo» son el S01E03 en TheTVDB,
que cuenta el piloto doble como capítulos 1 y 2. Renombrar por el número le ponía el título del
piloto a «La ventana del diablo».
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from retitler.parser import parse_path  # noqa: E402
from retitler.pipeline import Resolution, check_episode_title, choose  # noqa: E402
from retitler.providers import EpisodeInfo, ProviderError, ResultKind, SearchResult  # noqa: E402

SEAQUEST = SearchResult("tmdb", ResultKind.SERIES, 2289, "SeaQuest DSV", 1993, score=1.0)
SEASON1 = ["A ser o no ser (1)", "A ser o no ser (2)", "La ventana del diablo", "Tesoros de la mente", "Juegos"]


class Searcher:
    def __init__(self, fail=False):
        self.calls, self.fail = 0, fail

    def season_episodes(self, result, season):
        self.calls += 1
        if self.fail:
            raise ProviderError("sin red")
        return [EpisodeInfo(season, i + 1, t, source="tvdb") for i, t in enumerate(SEASON1)]

    def episode_titles_detailed(self, result, season, episodes):
        return [EpisodeInfo(season, n, SEASON1[n - 1], source="tvdb") for n in episodes]

    def seasons(self, result):
        return [1]


def res_for(name, titles):
    p = parse_path(f"/nas/Series/SeaQuest DSV (1993)/Season 01/{name}")
    return Resolution(Path(name), p, searched=True, chosen=SEAQUEST, titles=titles, title_sources=("tvdb",))


def test_titulo_de_otro_capitulo():
    s = Searcher()
    r = check_episode_title(res_for("SeaQuest DSV (1993) - S001E01 - La ventana del diablo.mkv",
                                    ("A ser o no ser (1)",)), s, {})
    assert r.suggested == (1, 3, "La ventana del diablo")


def test_titulo_que_cuadra_no_pregunta_ni_consulta():
    s = Searcher()
    r = check_episode_title(res_for("SeaQuest DSV (1993) - S001E03 - La ventana del Diablo.mkv",
                                    ("La ventana del diablo",)), s, {})
    assert r.suggested is None and s.calls == 0


def test_titulo_en_otro_idioma_no_pregunta():
    # El proveedor solo tiene el título en inglés y ningún capítulo se parece al del archivo
    s = Searcher()
    r = check_episode_title(res_for("SeaQuest DSV (1993) - S001E04 - El tesoro perdido.mkv",
                                    ("Treasures of the Mind",)), s, {})
    assert r.suggested is None and s.calls == 1


def test_temporada_se_pide_una_vez():
    s, memo = Searcher(), {}
    for n, t in ((1, "La ventana del diablo"), (2, "Tesoros de la mente"), (3, "Juegos")):
        r = check_episode_title(res_for(f"SeaQuest DSV (1993) - S001E{n:02} - {t}.mkv", (SEASON1[n - 1],)), s, memo)
        assert r.suggested == (1, n + 2, t)
    assert s.calls == 1


def test_sin_red_no_pregunta():
    r = check_episode_title(res_for("SeaQuest DSV (1993) - S001E01 - La ventana del diablo.mkv",
                                    ("A ser o no ser (1)",)), Searcher(fail=True), {})
    assert r.suggested is None


def test_elegir_el_capitulo_a_mano_lo_resuelve():
    s = Searcher()
    r = check_episode_title(res_for("SeaQuest DSV (1993) - S001E01 - La ventana del diablo.mkv",
                                    ("A ser o no ser (1)",)), s, {})
    r = choose(r, SEAQUEST, s, 1, (3,))
    assert r.suggested is None and r.parsed.episodes == (3,) and r.titles == ("La ventana del diablo",)
