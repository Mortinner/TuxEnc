from retitler.parser import MediaKind, parse_filename
from retitler.providers import InvalidApiKey, ProviderError, ResultKind, TMDBClient, TVmazeClient
from retitler.search import Searcher, build_searcher, pick_best
from retitler.config import KeyStore, Settings
from tests.rt_core.fakes import FakeFetch

TMDB_TV = {"results": [
    {"id": 2, "name": "Breaking Bad: El Camino", "first_air_date": "2019-10-11", "popularity": 90},
    {"id": 1396, "name": "Breaking Bad", "first_air_date": "2008-01-20", "popularity": 10},
]}
TMDB_MOVIE = {"results": [{"id": 27205, "title": "Origen", "original_title": "Inception", "release_date": "2010-07-15"}]}
MAZE = [{"show": {"id": 169, "name": "Breaking Bad", "premiered": "2008-01-20"}}]


def tmdb(routes):
    return TMDBClient("k" * 32, fetch=FakeFetch(routes))


def maze(routes=None):
    return TVmazeClient(fetch=FakeFetch(routes or {"/search/shows": MAZE}))


def test_best_match_wins_over_popular_one():
    s = Searcher(tmdb({"/3/search/tv": TMDB_TV, "/3/search/movie": {"results": []}}))
    res = s.search("Breaking Bad", kind=MediaKind.EPISODE, year=2008)
    assert [r.id for r in res.results] == [1396, 2]
    assert pick_best(res.results).id == 1396


def test_pick_best_refuses_weak_matches():
    s = Searcher(tmdb({"/3/search/tv": {"results": [{"id": 1, "name": "Algo completamente distinto"}]}}))
    assert pick_best(s.search("Breaking Bad", kind=MediaKind.EPISODE).results) is None
    assert pick_best([]) is None


def test_unknown_kind_searches_series_and_movies():
    s = Searcher(tmdb({"/3/search/tv": {"results": []}, "/3/search/movie": TMDB_MOVIE}), maze({"/search/shows": []}))
    res = s.search("Inception", kind=MediaKind.UNKNOWN)
    assert [(r.kind, r.id) for r in res.results] == [(ResultKind.MOVIE, 27205)]


def test_no_key_uses_tvmaze_and_warns_only_for_explicit_movies():
    s = Searcher(None, maze())
    assert s.search("Breaking Bad", kind=MediaKind.EPISODE).results[0].provider == "tvmaze"
    r = s.search("Inception", kind=MediaKind.MOVIE)
    assert r.results == [] and "clave de TMDB" in r.warnings[0]
    assert s.search("Breaking Bad", kind=MediaKind.UNKNOWN).warnings == []


def test_invalid_key_falls_back_to_tvmaze():
    s = Searcher(tmdb({"/3/search/tv": InvalidApiKey("x")}), maze())
    r = s.search("Breaking Bad", kind=MediaKind.EPISODE)
    assert r.results[0].provider == "tvmaze" and "no es válida" in r.warnings[0]


def test_tmdb_down_and_empty_results_fall_back():
    down = Searcher(tmdb({"/3/search/tv": ProviderError("sin red")}), maze())
    assert down.search("Breaking Bad", kind=MediaKind.EPISODE).results[0].provider == "tvmaze"
    empty = Searcher(tmdb({"/3/search/tv": {"results": []}}), maze())
    assert empty.search("Breaking Bad", kind=MediaKind.EPISODE).results[0].provider == "tvmaze"


def test_everything_down_gives_warnings_not_exceptions():
    s = Searcher(tmdb({"/3/search/tv": ProviderError("a")}), maze({"/search/shows": ProviderError("b")}))
    r = s.search("x", kind=MediaKind.EPISODE)
    assert r.results == [] and len(r.warnings) == 2


def test_blank_query():
    assert Searcher(None, maze()).search("   ").results == []


def test_search_parsed_uses_title_year_and_kind():
    s = Searcher(tmdb({"/3/search/tv": TMDB_TV}))
    res = s.search_parsed(parse_filename("Breaking.Bad.2008.S01E02.mkv"))
    assert res.results[0].id == 1396


def test_episode_titles():
    s = Searcher(tmdb({"/3/search/tv": TMDB_TV,
                       "/3/tv/1396/season/1": {"episodes": [{"episode_number": 1, "name": "Piloto"},
                                                            {"episode_number": 2, "name": "El gato"}]}}))
    series = s.search("Breaking Bad", kind=MediaKind.EPISODE).results[0]
    assert s.episode_titles(series, 1, (1, 2, 9)) == ["Piloto", "El gato", ""]


def test_build_searcher_reads_key_and_language(tmp_path):
    ks = KeyStore(tmp_path / "s.json", keyring_backend=None)
    assert build_searcher(Settings(), ks).tmdb is None
    ks.set("k" * 32)
    assert build_searcher(Settings(language="en"), ks).tmdb is not None
