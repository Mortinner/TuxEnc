"""TMDB + TVmaze a la vez, marcadores de episodio («Episodio 9»), caché y registro."""
import logging

import pytest

from retitler import log as retitler_log
from retitler.config import Settings
from retitler.matching import normalize
from retitler.parser import MediaKind
from retitler.pipeline import analyze, search_for
from retitler.providers import (
    CachedFetch, EpisodeInfo, JsonCache, ProviderError, ResultKind, SearchResult, TMDBClient, TVmazeClient,
    _safe_url, is_placeholder,
)
from retitler.search import Searcher, pick_best
from tests.rt_core.fakes import FakeFetch

TMDB_SHOW = {"id": 100, "name": "Tierra de mafiosos", "original_name": "MobLand", "first_air_date": "2025-03-30", "popularity": 80}
MAZE_SHOW = {"id": 900, "name": "MobLand", "premiered": "2025-03-30", "weight": 90}


def season_es(q):
    if q["language"] == "es-ES":
        return {"episodes": [{"episode_number": 8, "name": "Ya no nos hablamos"}, {"episode_number": 9, "name": "Episodio 9"}]}
    return {"episodes": [{"episode_number": 8, "name": "We Don't Talk"}, {"episode_number": 9, "name": "Episode 9"}]}


MAZE_EPS = [{"season": 2, "number": 8, "name": "We Don't Talk"}, {"season": 2, "number": 9, "name": "Nervous Breakdown"}]


def routes(**over):
    base = {
        "/3/search/tv": {"results": [TMDB_SHOW]},
        "/3/search/movie": {"results": []},
        "/3/tv/100/season/2": season_es,
        "/3/tv/100/external_ids": {"imdb_id": "tt999", "tvdb_id": 7},
        "/search/shows": [{"score": 1, "show": MAZE_SHOW}],
        "/shows/900/episodes": MAZE_EPS,
        "/lookup/shows": lambda q: MAZE_SHOW if q.get("imdb") == "tt999" else ProviderError("no"),
    }
    base.update(over)
    return FakeFetch(base)


def searcher(fake=None, tmdb=True, maze=True):
    fake = fake or routes()
    return Searcher(TMDBClient("k" * 32, "es", fetch=fake) if tmdb else None, TVmazeClient(fetch=fake) if maze else None)


# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("title, expected", [
    ("Episodio 9", True), ("Episode 10", True), ("episodio 3 ", True), ("Épisode 2", True), ("Folge 12", True),
    ("Capítulo 4", True), ("Episodio", False), ("Episodio 9: El regreso", False), ("Crisis nerviosa", False), ("", False),
])
def test_is_placeholder(title, expected):
    assert is_placeholder(title) is expected


def test_tmdb_placeholder_triggers_english_fallback_and_flags_provisional():
    f = FakeFetch({"/3/tv/1/season/1": lambda q: {"episodes": [
        {"episode_number": 1, "name": "Episodio 1"}, {"episode_number": 2, "name": "Episodio 2"}, {"episode_number": 3, "name": "Real"}]}
        if q["language"] in ("es-ES", "es-MX") else {"episodes": [
        {"episode_number": 1, "name": "Pilot"}, {"episode_number": 2, "name": "Episode 2"}, {"episode_number": 3, "name": "Real"}]}})
    eps = {e.number: e for e in TMDBClient("k" * 32, "es", fetch=f).get_season(1, 1)}
    assert (eps[1].title, eps[1].source, eps[1].provisional) == ("Pilot", "tmdb-en", False)
    assert (eps[2].title, eps[2].provisional) == ("Episodio 2", True)
    assert (eps[3].title, eps[3].source, eps[3].provisional) == ("Real", "tmdb", False)
    assert len(f.calls) == 3          # es-ES, es-MX (sin traducir tampoco) y en-US


def test_tmdb_english_marks_placeholder_provisional():
    f = FakeFetch({"/3/tv/1/season/1": {"episodes": [{"episode_number": 1, "name": "Episode 1"}]}})
    [e] = TMDBClient("k" * 32, "en", fetch=f).get_season(1, 1)
    assert e.provisional and len(f.calls) == 1


def test_tvmaze_marks_placeholders_and_lookup_by_external_id():
    f = FakeFetch({"/shows/1/episodes": [{"season": 1, "number": 1, "name": "Episode 1"}, {"season": 1, "number": 2, "name": "Real"}],
                   "/lookup/shows": lambda q: MAZE_SHOW if q.get("imdb") == "tt1" else ProviderError("x")})
    maze = TMDBClient and TVmazeClient(fetch=f)
    assert [(e.title, e.provisional) for e in maze.get_season(1, 1)] == [("Episode 1", True), ("Real", False)]
    assert maze.lookup(imdb="tt1").id == 900
    assert maze.lookup() is None


def test_tvmaze_lookup_not_found():
    from retitler.providers import NotFound
    maze = TVmazeClient(fetch=FakeFetch({"/lookup/shows": NotFound("x")}))
    assert maze.lookup(tvdb=5) is None


# --------------------------------------------------------------------------- #
# Fusión de resultados
# --------------------------------------------------------------------------- #
def test_same_show_in_both_providers_gives_one_row_per_engine():
    res = searcher().search("mobland", kind=MediaKind.EPISODE)
    assert [(r.provider, r.id, r.title) for r in res.results] == [
        ("tmdb", 100, "Tierra de mafiosos"), ("tvmaze", 900, "MobLand")]     # sin fusionar: cada motor con su título
    assert [r.provider_name for r in res.results] == ["TMDB", "TVmaze"]


def test_pick_best_prefers_tmdb_when_engines_agree():
    res = searcher().search("mobland", kind=MediaKind.EPISODE).results
    assert pick_best(res).provider == "tmdb"
    assert pick_best([r for r in res if r.provider == "tvmaze"]).provider == "tvmaze"


def test_rows_of_the_same_show_stay_together():
    f = routes(**{"/3/search/tv": {"results": [TMDB_SHOW, {"id": 101, "name": "Otra cosa", "first_air_date": "1999-01-01", "popularity": 1}]},
                  "/search/shows": [{"show": MAZE_SHOW}, {"show": {"id": 901, "name": "Otra cosa", "premiered": "1999-01-01"}}]})
    res = searcher(f).search("mobland", kind=MediaKind.EPISODE).results
    assert [(r.provider, r.id) for r in res[:2]] == [("tmdb", 100), ("tvmaze", 900)]
    assert [(r.provider, r.id) for r in res[2:]] == [("tmdb", 101), ("tvmaze", 901)]


def test_different_shows_with_same_name_stay_separate():
    f = routes(**{"/3/search/tv": {"results": [{"id": 1, "name": "The Office", "first_air_date": "2005-03-24"}]},
                  "/search/shows": [{"show": {"id": 2, "name": "The Office", "premiered": "2001-07-09"}},
                                    {"show": {"id": 3, "name": "The Office", "premiered": "2005-03-24"}}]})
    results = searcher(f).search("The Office", kind=MediaKind.EPISODE).results
    assert sorted((r.provider, r.id) for r in results) == [("tmdb", 1), ("tvmaze", 2), ("tvmaze", 3)]


def test_one_provider_down_still_returns_the_other():
    f = routes(**{"/3/search/tv": ProviderError("sin red")})
    res = searcher(f).search("mobland", kind=MediaKind.EPISODE)
    assert [r.provider for r in res.results] == ["tvmaze"] and "TMDB no respondió" in res.warnings[0]
    f = routes(**{"/search/shows": ProviderError("caído")})
    res = searcher(f).search("mobland", kind=MediaKind.EPISODE)
    assert [r.provider for r in res.results] == ["tmdb"] and "TVmaze no respondió" in res.warnings[0]


def test_both_providers_are_queried_even_when_tmdb_has_results():
    f = routes()
    searcher(f).search("mobland", kind=MediaKind.EPISODE)
    paths = [url.split("?")[0].split(".org")[-1].split(".com")[-1] for url, _ in f.calls]
    assert any("/search/tv" in p for p in paths) and any(p.endswith("/search/shows") for p in paths)


def test_movies_only_query_tmdb():
    f = routes(**{"/3/search/movie": {"results": [{"id": 5, "title": "Origen", "original_title": "Inception", "release_date": "2010-07-15"}]}})
    res = searcher(f).search("inception", kind=MediaKind.MOVIE)
    assert [(r.kind, r.provider) for r in res.results] == [(ResultKind.MOVIE, "tmdb")]
    assert not any("/search/shows" in url for url, _ in f.calls)


# --------------------------------------------------------------------------- #
# Títulos de episodio: TMDB (es) → TMDB (en) → TVmaze
# --------------------------------------------------------------------------- #
def test_placeholder_title_is_completed_from_tvmaze():
    s = searcher()
    show = s.search("mobland", kind=MediaKind.EPISODE).results[0]
    e8, e9 = s.episode_titles_detailed(show, 2, (8, 9))
    assert (e8.title, e8.source, e8.provisional) == ("Ya no nos hablamos", "tmdb", False)
    assert (e9.title, e9.source, e9.provisional) == ("Nervous Breakdown", "tvmaze", False)


def test_link_to_tvmaze_by_external_id():
    f = routes(**{"/search/shows": []})
    s = searcher(f)
    show = SearchResult("tmdb", ResultKind.SERIES, 100, "Tierra de mafiosos", 2025, "MobLand")
    assert s.episode_titles_detailed(show, 2, (9,))[0].title == "Nervous Breakdown"
    assert any("/lookup/shows" in url and "imdb=tt999" in url for url, _ in f.calls)
    before = len(f.calls)
    s.episode_titles_detailed(show, 2, (9,))                     # el enlace se recuerda
    assert not any("/external_ids" in url for url, _ in f.calls[before:])


def test_link_to_tvmaze_by_name_when_external_ids_fail():
    f = routes(**{"/3/tv/100/external_ids": ProviderError("x"), "/lookup/shows": ProviderError("x")})
    s = searcher(f)
    show = SearchResult("tmdb", ResultKind.SERIES, 100, "Tierra de mafiosos", 2025, "MobLand")
    assert s.episode_titles_detailed(show, 2, (9,))[0].title == "Nervous Breakdown"


def test_title_stays_provisional_when_nobody_has_it():
    f = routes(**{"/shows/900/episodes": [{"season": 2, "number": 9, "name": "Episode 9"}]})
    s = searcher(f)
    show = s.search("mobland", kind=MediaKind.EPISODE).results[0]
    [e9] = s.episode_titles_detailed(show, 2, (9,))
    assert e9.title == "Episodio 9" and e9.provisional


def test_secondary_provider_failure_keeps_primary_titles():
    f = routes(**{"/shows/900/episodes": ProviderError("caído")})
    s = searcher(f)
    show = s.search("mobland", kind=MediaKind.EPISODE).results[0]
    e8, e9 = s.episode_titles_detailed(show, 2, (8, 9))
    assert e8.title == "Ya no nos hablamos" and e9.provisional


def test_tvmaze_result_completes_titles_from_tmdb_by_name():
    s = searcher()
    show = SearchResult("tvmaze", ResultKind.SERIES, 900, "MobLand", 2025, "MobLand")
    s.tvmaze = TVmazeClient(fetch=routes(**{"/shows/900/episodes": [{"season": 2, "number": 9, "name": "Episode 9"}]}))
    s._clients["tvmaze"] = s.tvmaze
    [e9] = s.episode_titles_detailed(show, 2, (9,))
    assert e9.provisional and e9.title == "Episode 9"                       # nadie tiene el título real: provisional


def test_unknown_episode_gives_empty_title():
    s = searcher()
    show = s.search("mobland", kind=MediaKind.EPISODE).results[0]
    [e] = s.episode_titles_detailed(show, 2, (77,))
    assert e == EpisodeInfo(2, 77, "")


def test_no_tmdb_key_still_works_with_tvmaze_only():
    s = searcher(tmdb=False)
    show = s.search("mobland", kind=MediaKind.EPISODE).results[0]
    assert s.episode_titles(show, 2, (9,)) == ["Nervous Breakdown"]


def test_pipeline_notes_say_where_titles_came_from(tmp_path):
    f = tmp_path / "MobLand.S02E09.mkv"
    res = search_for(analyze(f), searcher())
    name, note = res.new_name(Settings())
    assert name == "Tierra de mafiosos - 2x09 - Nervous Breakdown.mkv"
    assert "[TMDB]" in note and "títulos de TVmaze" in note and "provisional" not in note
    prov = search_for(analyze(f), searcher(routes(**{"/shows/900/episodes": []})))
    name, note = prov.new_name(Settings())
    assert name == "Tierra de mafiosos - 2x09 - Episodio 9.mkv" and "título provisional" in note


# --------------------------------------------------------------------------- #
# Caché y registro
# --------------------------------------------------------------------------- #
def test_season_cache_expires_sooner_than_searches():
    now, calls = [0.0], []

    def fetch(url, headers):
        calls.append(url)
        return {"x": 1}

    cached = CachedFetch(fetch, JsonCache(ttl=24 * 3600, clock=lambda: now[0]))
    for url in ("http://x/3/search/tv?q=a", "http://x/3/tv/1/season/2?l=es", "http://x/shows/9/episodes"):
        cached(url, {})
    now[0] = 3 * 3600                                   # pasan 3 horas
    for url in ("http://x/3/search/tv?q=a", "http://x/3/tv/1/season/2?l=es", "http://x/shows/9/episodes"):
        cached(url, {})
    assert len(calls) == 5                              # solo los dos de episodios se repiten


def test_cache_clear_removes_memory_and_disk(tmp_path):
    cache = JsonCache(tmp_path)
    cache.set("a", {"x": 1})
    cache.clear()
    assert cache.get("a") == (False, None) and not list(tmp_path.iterdir())
    assert JsonCache(tmp_path).get("a") == (False, None)


def test_searcher_clear_cache(tmp_path):
    cache = JsonCache()
    cache.set("a", 1)
    s = Searcher(None, None, cache)
    s.clear_cache()
    assert cache.get("a") == (False, None)


def test_safe_url_hides_the_api_key():
    url = _safe_url("https://api.themoviedb.org/3/search/tv?query=x&api_key=SECRETO&language=es-ES")
    assert "SECRETO" not in url and "query=x" in url


def test_logging_goes_to_a_file_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(retitler_log, "_configured", False)
    before = list(retitler_log.log.handlers)
    try:
        path = retitler_log.setup_logging()
        assert path == tmp_path / "tuxenc" / "renombrado" / "retitler.log"
        searcher().search("mobland", kind=MediaKind.EPISODE)
        for h in retitler_log.log.handlers:
            h.flush()
        text = path.read_text(encoding="utf-8")
        assert "búsqueda 'mobland'" in text and "k" * 32 not in text
    finally:
        for h in list(retitler_log.log.handlers):
            if h not in before:
                retitler_log.log.removeHandler(h)
                h.close()


# --------------------------------------------------------------------------- #
# IMDb (vía OMDb)
# --------------------------------------------------------------------------- #
from retitler.providers import InvalidApiKey, OMDbClient   # noqa: E402

OMDB_SHOW = {"Title": "MobLand", "Year": "2025–", "imdbID": "tt13621746", "Type": "series"}


def omdb_routes(**over):
    base = routes(**{"/3/tv/100/external_ids": {"imdb_id": "tt13621746"}})
    base.routes["/"] = lambda q: omdb_answer(q, over)
    return base


def omdb_answer(q, over):
    if "Season" in q:
        return over.get("season", {"Response": "True", "Episodes": [
            {"Title": "We Don't Talk", "Released": "2025-04-06", "Episode": "8"},
            {"Title": "Nervous Breakdown", "Released": "2025-04-13", "Episode": "9"}]})
    if q.get("s"):
        return over.get("search", {"Response": "True", "Search": [OMDB_SHOW]})
    return over.get("other", {"Response": "True"})


def omdb_searcher(fake):
    return Searcher(TMDBClient("k" * 32, "es", fetch=fake), TVmazeClient(fetch=fake), omdb=OMDbClient("o" * 8, fetch=fake))


def test_omdb_adds_its_own_row_per_series():
    res = omdb_searcher(omdb_routes()).search("mobland", kind=MediaKind.EPISODE).results
    assert [(r.provider, r.id) for r in res] == [("tmdb", 100), ("tvmaze", 900), ("omdb", "tt13621746")]
    assert res[2].year == 2025 and res[2].provider_name == "IMDb"


def test_omdb_searches_movies_too_and_tmdb_wins_ties():
    f = omdb_routes(search={"Response": "True", "Search": [{"Title": "Inception", "Year": "2010", "imdbID": "tt1375666", "Type": "movie"}]},
                    **{})
    f.routes["/3/search/movie"] = {"results": [{"id": 5, "title": "Origen", "original_title": "Inception", "release_date": "2010-07-15"}]}
    res = omdb_searcher(f).search("inception", kind=MediaKind.MOVIE)
    assert [(r.provider, r.kind) for r in res.results] == [("tmdb", ResultKind.MOVIE), ("omdb", ResultKind.MOVIE)]
    assert pick_best(res.results).provider == "tmdb"


def test_omdb_is_used_for_missing_titles_after_tvmaze():
    f = omdb_routes()
    f.routes["/shows/900/episodes"] = [{"season": 2, "number": 9, "name": "Episode 9"}]     # TVmaze tampoco lo tiene
    s = omdb_searcher(f)
    show = SearchResult("tmdb", ResultKind.SERIES, 100, "Tierra de mafiosos", 2025, "MobLand")
    [e9] = s.episode_titles_detailed(show, 2, (9,))
    assert (e9.title, e9.source, e9.provisional) == ("Nervous Breakdown", "omdb", False)
    assert any("i=tt13621746" in url and "Season=2" in url for url, _ in f.calls)


def test_omdb_episodes_ignore_na_and_missing_numbers():
    f = omdb_routes(season={"Response": "True", "Episodes": [
        {"Title": "N/A", "Episode": "1"}, {"Title": "Bien", "Episode": "2"}, {"Title": "Sin número", "Episode": "N/A"}]})
    eps = OMDbClient("o" * 8, fetch=f).get_season("tt1", 1)
    assert [(e.number, e.title) for e in eps] == [(2, "Bien")]


def test_omdb_errors_become_provider_errors():
    for payload, exc, text in (
        ({"Response": "False", "Error": "Invalid API key!"}, InvalidApiKey, None),
        ({"Response": "False", "Error": "Request limit reached!"}, ProviderError, "límite"),
        ({"Response": "False", "Error": "Something odd"}, ProviderError, "OMDb"),
    ):
        client = OMDbClient("o" * 8, fetch=FakeFetch({"/": payload}))
        with pytest.raises(exc, match=text):
            client.search_series("x")
    empty = OMDbClient("o" * 8, fetch=FakeFetch({"/": {"Response": "False", "Error": "Series not found!"}}))
    assert empty.search_series("x") == [] and empty.get_season("tt1", 1) == []


def test_omdb_validate_key():
    ok = OMDbClient("o" * 8, fetch=FakeFetch({"/": {"Response": "True", "Title": "x"}}))
    bad = OMDbClient("o" * 8, fetch=FakeFetch({"/": {"Response": "False", "Error": "Invalid API key!"}}))
    assert ok.validate_key() is True and bad.validate_key() is False


def test_omdb_key_never_reaches_the_log_url():
    assert "SECRETA" not in _safe_url("https://www.omdbapi.com/?apikey=SECRETA&s=x") and "s=x" in _safe_url("https://www.omdbapi.com/?apikey=SECRETA&s=x")


def test_omdb_season_cache_is_short():
    now, calls = [0.0], []
    cached = CachedFetch(lambda u, h: calls.append(u) or {"x": 1}, JsonCache(ttl=24 * 3600, clock=lambda: now[0]))
    for url in ("https://www.omdbapi.com/?s=a", "https://www.omdbapi.com/?i=tt1&Season=2"):
        cached(url, {})
    now[0] = 3 * 3600
    for url in ("https://www.omdbapi.com/?s=a", "https://www.omdbapi.com/?i=tt1&Season=2"):
        cached(url, {})
    assert len(calls) == 3


def test_omdb_401_limit_body_is_reported_as_limit(monkeypatch):
    import io
    import urllib.error
    from retitler import providers

    def boom(request, timeout=0):
        raise urllib.error.HTTPError("https://www.omdbapi.com/?apikey=x", 401, "Unauthorized", {}, io.BytesIO(b'{"Response":"False","Error":"Request limit reached!"}'))

    monkeypatch.setattr(providers.urllib.request, "urlopen", boom)
    with pytest.raises(ProviderError, match="límite") as info:
        providers.urllib_fetch("https://www.omdbapi.com/?apikey=x", {})
    assert not isinstance(info.value, InvalidApiKey)
    def bad(request, timeout=0):
        raise urllib.error.HTTPError("https://www.omdbapi.com/?apikey=x", 401, "Unauthorized", {}, io.BytesIO(b'{"Response":"False","Error":"Invalid API key!"}'))
    monkeypatch.setattr(providers.urllib.request, "urlopen", bad)
    with pytest.raises(InvalidApiKey):
        providers.urllib_fetch("https://www.omdbapi.com/?apikey=x", {})
