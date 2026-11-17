"""Títulos de capítulo: español de Latinoamérica antes que inglés, y el título que trae el archivo
cuando solo hay inglés (caso «Foyle's War - S01E01 - La mujer alemana»)."""
from pathlib import Path

from retitler.config import Settings
from retitler.parser import parse_filename
from retitler.pipeline import Resolution, analyze, choose, prefer_file_title
from retitler.providers import ResultKind, SearchResult, TMDBClient
from tests.rt_core.fakes import FakeFetch

FOYLE = SearchResult("tmdb", ResultKind.SERIES, 1, "Foyle's War", 2002, score=0.95)


def _season(by_lang):
    return FakeFetch({"/3/tv/1/season/1": lambda q: {"episodes": [
        {"episode_number": i + 1, "name": t} for i, t in enumerate(by_lang.get(q["language"], []))]}})


def test_parse_episode_title():
    assert parse_filename("Foyle`s War (2002) - S01E01 - La mujer alemana.mkv").episode_title == "La mujer alemana"
    assert parse_filename("Arrow (2012) - S01E02 - Honra a tu padre - [1080p].mkv").episode_title == "Honra a tu padre"
    assert parse_filename("Serie (2013) - S01E01 - Episodio 1.mp4").episode_title == ""
    assert parse_filename("Arrow.S01E02.1080p.WEB-DL.mkv").episode_title == ""
    assert parse_filename("Show - S01E01 - Pilot 1080p WEB-DL x264.mkv").episode_title == "Pilot"


def test_tmdb_tries_latin_american_spanish_before_english():
    f = _season({"es-ES": ["Episodio 1", "Episodio 2"], "es-MX": ["La mujer alemana", ""],
                 "en-US": ["The German Woman", "The White Feather"]})
    eps = TMDBClient("k" * 32, "es", fetch=f).get_season(1, 1)
    assert [(e.title, e.source) for e in eps] == [("La mujer alemana", "tmdb-mx"), ("The White Feather", "tmdb-en")]


def test_english_ui_never_asks_es_mx():
    f = _season({"en-US": ["The German Woman"]})
    TMDBClient("k" * 32, "en", fetch=f).get_season(1, 1)
    assert all("es-MX" not in url for url, _ in f.calls)


def _res(name, title, source, provisional=False):
    return Resolution(Path(name), parse_filename(name), searched=True, chosen=FOYLE,
                      titles=(title,), title_sources=(source,), provisional=provisional)


def test_prefer_file_title_only_when_english_or_missing():
    s = Settings()
    name = "Foyle`s War (2002) - S01E01 - La mujer alemana.mkv"
    r = prefer_file_title(_res(name, "The German Woman", "tmdb-en"), s)
    assert r.titles == ("La mujer alemana",) and r.title_sources == ("archivo",)
    assert prefer_file_title(_res(name, "", "tmdb"), s).titles == ("La mujer alemana",)
    assert prefer_file_title(_res(name, "Episode 1", "tmdb", provisional=True), s).titles == ("La mujer alemana",)
    assert prefer_file_title(_res(name, "The German Woman", "tvmaze"), s).titles == ("La mujer alemana",)
    # en español (de España o de Latinoamérica) manda el proveedor
    assert prefer_file_title(_res(name, "La alemana", "tmdb"), s).titles == ("La alemana",)
    assert prefer_file_title(_res(name, "La alemana", "tmdb-mx"), s).titles == ("La alemana",)
    # desactivado, o buscando en inglés
    s.keep_file_title = False
    assert prefer_file_title(_res(name, "The German Woman", "tmdb-en"), s).titles == ("The German Woman",)
    s2 = Settings(language="en")
    assert prefer_file_title(_res(name, "The German Woman", "tmdb"), s2).titles == ("The German Woman",)
    # sin título en el nombre del archivo, no cambia nada
    assert prefer_file_title(_res("Foyle.S01E01.mkv", "The German Woman", "tmdb-en"), Settings()).titles == ("The German Woman",)


class _S:
    def episode_titles_detailed(self, result, season, episodes):
        from retitler.providers import EpisodeInfo
        return [EpisodeInfo(season, n, f"Episode {n} EN", source="tmdb-en") for n in episodes]


def test_choosing_another_episode_forgets_the_file_title():
    res = analyze("Foyle`s War (2002) - S01E01 - La mujer alemana.mkv")
    same = prefer_file_title(choose(res, FOYLE, _S(), 1, (1,)), Settings())
    assert same.titles == ("La mujer alemana",)
    other = prefer_file_title(choose(res, FOYLE, _S(), 1, (3,)), Settings())
    assert other.titles == ("Episode 3 EN",)
