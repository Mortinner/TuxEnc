"""Caso real de Marcos (1.2.0): Foyle's War salía con los mismos títulos en todas las temporadas."""
from pathlib import Path

from retitler.pipeline import analyze, search_for
from retitler.providers import TMDBClient, TVDBClient
from retitler.search import Searcher
from tests.rt_core.fakes import FakeFetch
from tests.rt_core.test_tvdb import ROUTES, FakePost

EN = {1: ["The German Woman", "The White Feather"], 2: ["Fifty Ships", "Among the Few"]}


def _tmdb():
    def season(n):
        return lambda q: {"episodes": [{"episode_number": i + 1,
                                        "name": t if q["language"] == "en-US" else f"Episodio {i + 1}"}
                                       for i, t in enumerate(EN[n])]}
    return TMDBClient("a" * 32, "es", fetch=FakeFetch({
        "/3/search/tv": {"results": [{"id": 4057, "name": "Foyle's War", "original_name": "Foyle's War",
                                      "first_air_date": "2002-10-27", "popularity": 30}]},
        "/3/search/movie": {"results": []},
        "/3/tv/4057/external_ids": {"imdb_id": "tt0310455", "tvdb_id": 78874},
        "/3/tv/4057/season/1": season(1), "/3/tv/4057/season/2": season(2)}))


def test_each_file_gets_its_own_season_title(tmp_path: Path):
    tvdb = TVDBClient("k", "es", fetch=FakeFetch(ROUTES), post=FakePost())
    s = Searcher(_tmdb(), None, tvdb=tvdb, language="es")
    got = {}
    for name in ("Foyle's War (2002) - S01E01.mkv", "Foyle's War (2002) - S01E02.mkv",
                 "Foyle's War (2002) - S02E01.mkv", "Foyle's War (2002) - S02E02.mkv"):
        f = tmp_path / name
        f.write_bytes(b"x")
        res = search_for(analyze(f), s)
        got[name.split(" - ")[1][:6]] = (res.titles[0], res.title_sources[0])
    assert got == {"S01E01": ("La mujer alemana", "tvdb"), "S01E02": ("La pluma blanca", "tvdb"),
                   "S02E01": ("Cincuenta naves", "tvdb"), "S02E02": ("Uno de los pocos", "tvdb")}
