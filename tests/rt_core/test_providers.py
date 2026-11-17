import pytest

from retitler.providers import (
    InvalidApiKey, JsonCache, NotFound, ProviderError, ResultKind, TMDBClient, TVmazeClient,
)
from tests.rt_core.fakes import FakeFetch

TV = {"results": [
    {"id": 1396, "name": "Breaking Bad", "original_name": "Breaking Bad", "first_air_date": "2008-01-20",
     "overview": "x", "popularity": 120.5},
    {"id": 5, "name": "Sin fecha", "first_air_date": ""},
    {"name": "sin id"},
]}
MOVIES = {"results": [{"id": 27205, "title": "Origen", "original_title": "Inception",
                       "release_date": "2010-07-15", "popularity": 80}]}


def test_tmdb_search_series_url_and_parsing():
    f = FakeFetch({"/3/search/tv": TV})
    results = TMDBClient("a" * 32, "es", fetch=f).search_series("breaking bad")
    assert [r.id for r in results] == [1396, 5]  # el que no tiene id se descarta
    assert results[0].kind is ResultKind.SERIES and results[0].year == 2008 and results[1].year is None
    url, headers = f.calls[0]
    assert "api_key=" + "a" * 32 in url and "language=es-ES" in url and "query=breaking+bad" in url
    assert "Authorization" not in headers


def test_tmdb_bearer_token_goes_in_header_not_url():
    token = "eyJ" + "x" * 100
    f = FakeFetch({"/3/search/movie": MOVIES})
    TMDBClient(token, "en", fetch=f).search_movies("inception")
    url, headers = f.calls[0]
    assert headers["Authorization"] == f"Bearer {token}"
    assert "api_key" not in url and "language=en-US" in url


def test_tmdb_movies():
    r = TMDBClient("k" * 32, fetch=FakeFetch({"/3/search/movie": MOVIES})).search_movies("origen")[0]
    assert (r.kind, r.title, r.original_title, r.year) == (ResultKind.MOVIE, "Origen", "Inception", 2010)


def test_validate_key():
    ok = TMDBClient("k" * 32, fetch=FakeFetch({"/3/configuration": {"images": {}}}))
    bad = TMDBClient("k" * 32, fetch=FakeFetch({"/3/configuration": InvalidApiKey("no")}))
    down = TMDBClient("k" * 32, fetch=FakeFetch({"/3/configuration": ProviderError("sin red")}))
    assert ok.validate_key() is True and bad.validate_key() is False
    with pytest.raises(ProviderError):
        down.validate_key()


def test_season_falls_back_to_english_for_untranslated_titles():
    def season(q):
        if q["language"] == "es-ES":
            return {"episodes": [{"episode_number": 1, "name": "Piloto"}, {"episode_number": 2, "name": ""}]}
        return {"episodes": [{"episode_number": 1, "name": "Pilot"}, {"episode_number": 2, "name": "Cat's in the Bag..."}]}

    f = FakeFetch({"/3/tv/1396/season/1": season})
    eps = TMDBClient("k" * 32, "es", fetch=f).get_season(1396, 1)
    assert [e.title for e in eps] == ["Piloto", "Cat's in the Bag..."]
    assert len(f.calls) == 2


def test_season_not_found_is_empty():
    f = FakeFetch({"/3/tv/1/season/9": NotFound("x")})
    assert TMDBClient("k" * 32, fetch=f).get_season(1, 9) == []


def test_tvmaze():
    f = FakeFetch({
        "/search/shows": [{"score": 9, "show": {"id": 169, "name": "Breaking Bad", "premiered": "2008-01-20", "weight": 98}},
                          {"score": 1, "show": {"name": "roto"}}],
        "/shows/169/episodes": [
            {"season": 1, "number": 1, "name": "Pilot", "airdate": "2008-01-20"},
            {"season": 1, "number": None, "name": "Especial"},
            {"season": 2, "number": 1, "name": "Seven Thirty-Seven"},
        ],
    })
    client = TVmazeClient(fetch=f)
    [r] = client.search_series("breaking bad")
    assert (r.provider, r.id, r.year, r.popularity) == ("tvmaze", 169, 2008, 98.0)
    assert [(e.number, e.title) for e in client.get_season(169, 1)] == [(1, "Pilot")]


def test_memory_cache_avoids_second_request():
    f = FakeFetch({"/3/search/tv": TV})
    client = TMDBClient("k" * 32, fetch=f, cache=JsonCache())
    client.search_series("a")
    client.search_series("a")
    client.search_series("b")
    assert len(f.calls) == 2


def test_disk_cache_persists_and_expires(tmp_path):
    now = [1000.0]
    f = FakeFetch({"/3/search/tv": TV})
    mk = lambda: TMDBClient("k" * 32, fetch=f, cache=JsonCache(tmp_path, ttl=60, clock=lambda: now[0]))
    mk().search_series("a")
    mk().search_series("a")          # otra instancia: lee del disco
    assert len(f.calls) == 1
    now[0] += 61                       # caducada
    mk().search_series("a")
    assert len(f.calls) == 2
    assert "k" * 32 not in "".join(p.read_text() for p in tmp_path.iterdir())  # la clave no queda en la caché


def test_corrupt_cache_file_is_ignored(tmp_path):
    cache = JsonCache(tmp_path)
    cache.set("u", {"a": 1})
    (next(tmp_path.glob("*.json"))).write_text("{{{ no es json")
    assert JsonCache(tmp_path).get("u") == (False, None)


def test_rate_limiter_spaces_requests_per_host():
    from retitler.providers import RateLimiter
    now, slept = [0.0], []

    def sleep(d):
        slept.append(d)
        now[0] += d

    rl = RateLimiter({"api.tvmaze.com": (2, 10.0)}, clock=lambda: now[0], sleep=sleep)
    for _ in range(3):
        rl.wait("api.tvmaze.com")
    rl.wait("otro.host")                                  # sin límite configurado
    assert slept == [10.0]                                # la tercera esperó a que pasara la ventana


def test_429_is_retried_with_backoff(monkeypatch):
    import io
    import urllib.error
    from retitler import providers
    calls, sleeps = [], []

    class Ok:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"ok": 1}'

    def urlopen(request, timeout=0):
        calls.append(1)
        if len(calls) < 3:
            raise urllib.error.HTTPError("https://api.tvmaze.com/x", 429, "Too Many", {}, io.BytesIO(b""))
        return Ok()

    monkeypatch.setattr(providers.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(providers.time, "sleep", lambda d: sleeps.append(d))
    assert providers.urllib_fetch("https://api.tvmaze.com/x", {}) == {"ok": 1}
    assert len(calls) == 3 and sleeps == [2.0, 4.0]
