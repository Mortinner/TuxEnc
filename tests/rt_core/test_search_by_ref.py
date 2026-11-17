"""Buscar pegando un enlace o código de IMDb, TMDB o TVmaze (caso «Aeropuerto de Dubái»)."""
from retitler.parser import MediaKind
from retitler.providers import NotFound, OMDbClient, ResultKind, TMDBClient, TVmazeClient
from retitler.search import Searcher, parse_ref
from tests.rt_core.fakes import FakeFetch

FIND = {"tv_results": [{"id": 61234, "name": "Aeropuerto de Dubái", "original_name": "Ultimate Airport Dubai",
                        "first_air_date": "2013-11-06", "popularity": 3.1}],
        "movie_results": []}
TVM_SHOW = {"id": 8001, "name": "Ultimate Airport Dubai", "premiered": "2013-11-06", "weight": 40}
OMDB = {"Response": "True", "Title": "Ultimate Airport Dubai", "Year": "2013–2015", "imdbID": "tt3324124",
        "Type": "series", "totalSeasons": "3"}


def test_parse_ref_variants():
    assert parse_ref("https://www.imdb.com/es-es/title/tt3324124/") == ("imdb", None, "tt3324124")
    assert parse_ref("tt3324124") == ("imdb", None, "tt3324124")
    assert parse_ref("  TT3324124 ") == ("imdb", None, "tt3324124")
    assert parse_ref("https://www.themoviedb.org/tv/1396-breaking-bad") == ("tmdb", ResultKind.SERIES, 1396)
    assert parse_ref("https://www.themoviedb.org/es/movie/27205-inception?x=1") == ("tmdb", ResultKind.MOVIE, 27205)
    assert parse_ref("https://www.tvmaze.com/shows/8001/ultimate-airport-dubai") == ("tvmaze", ResultKind.SERIES, 8001)
    for name in ("Aeropuerto de Dubai", "Matt 2013", "Scott Pilgrim", "watt12345678"):
        assert parse_ref(name) is None, name


def _searcher(omdb=True, tmdb=True):
    t = TMDBClient("a" * 32, "es", fetch=FakeFetch({"/3/find/tt3324124": FIND,
                                                    "/3/tv/61234": {**FIND["tv_results"][0]}})) if tmdb else None
    v = TVmazeClient(fetch=FakeFetch({"/lookup/shows": TVM_SHOW, "/shows/8001": TVM_SHOW}))
    o = OMDbClient("k", fetch=FakeFetch({"/": OMDB})) if omdb else None
    return Searcher(t, v, omdb=o)


def test_imdb_link_finds_the_show_in_every_engine():
    res = _searcher().search("https://www.imdb.com/es-es/title/tt3324124/", kind=MediaKind.EPISODE)
    assert [r.provider for r in res.results] == ["tmdb", "tvmaze", "omdb"]
    assert res.results[0].title == "Aeropuerto de Dubái" and res.results[0].year == 2013
    assert all(r.score == 1.0 and r.kind is ResultKind.SERIES for r in res.results)
    assert not res.warnings


def test_imdb_code_without_keys_still_uses_tvmaze():
    res = _searcher(omdb=False, tmdb=False).search("tt3324124")
    assert [(r.provider, r.id) for r in res.results] == [("tvmaze", 8001)]


def test_tmdb_and_tvmaze_links():
    s = _searcher()
    assert [(r.provider, r.id) for r in s.search("https://www.themoviedb.org/tv/61234").results] == [("tmdb", 61234)]
    assert [(r.provider, r.id) for r in s.search("tvmaze.com/shows/8001").results] == [("tvmaze", 8001)]


def test_tmdb_link_without_key_warns():
    res = _searcher(tmdb=False).search("https://www.themoviedb.org/tv/61234")
    assert not res.results and "clave de TMDB" in res.warnings[0]


def test_unknown_tvmaze_id_is_empty_not_error():
    v = TVmazeClient(fetch=FakeFetch({"/shows/999": NotFound("x")}))
    res = Searcher(None, v).search("tvmaze.com/shows/999")
    assert res.results == [] and res.warnings == []
