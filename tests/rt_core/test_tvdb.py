"""TheTVDB (API v4): sesión, búsqueda, capítulos traducidos y su papel en el buscador.

Caso real: «Foyle's War» solo tiene los títulos en español en TheTVDB; TMDB, TVmaze e IMDb los dan en inglés.
Respuestas simuladas según la documentación de la API v4 (https://thetvdb.github.io/v4-api/).
"""
from retitler.parser import MediaKind
from retitler.providers import InvalidApiKey, NotFound, ResultKind, SearchResult, TMDBClient, TVDBClient
from retitler.search import Searcher, parse_ref
from tests.rt_core.fakes import FakeFetch

B = "/v4"
EN = ["The German Woman", "The White Feather", "A Lesson in Murder", "Eagle Day"]
ES = ["La mujer alemana", "La pluma blanca", "Una lección de asesinato", ""]      # el 4 sin traducir


class FakePost:
    def __init__(self, token="tok1", fail=False):
        self.tokens = [token] if isinstance(token, str) else list(token)
        self.fail, self.calls = fail, []

    def __call__(self, url, body, headers):
        self.calls.append((url, dict(body)))
        if self.fail:
            raise InvalidApiKey("rechazada")
        return {"status": "success", "data": {"token": self.tokens.pop(0) if len(self.tokens) > 1 else self.tokens[0]}}


EN2 = ["Fifty Ships", "Among the Few"]
ES2 = ["Cincuenta naves", "Uno de los pocos"]


def _eps(by_season):
    """Como el servidor real: la serie ENTERA (todas las temporadas), pida lo que se pida."""
    return {"series": {"id": 78874}, "episodes": [
        {"id": 1000 * s + i, "seasonNumber": s, "number": i + 1, "name": n or None, "aired": f"200{s}-10-{10 + i}"}
        for s, names in by_season.items() for i, n in enumerate(names)] + [
        {"id": 1, "seasonNumber": 0, "number": 1, "name": "Especial", "aired": "2010-01-01"}]}


ROUTES = {
    f"{B}/search": {"data": [{"tvdb_id": "78874", "name": "Foyle's War", "year": "2002", "type": "series",
                              "translations": {"eng": "Foyle's War", "spa": "La guerra de Foyle"}}]},
    f"{B}/series/78874/episodes/default": {"data": _eps({1: EN, 2: EN2})},
    f"{B}/series/78874/episodes/default/spa": {"data": _eps({1: [e or en for e, en in zip(ES, EN)], 2: ES2})},
    f"{B}/search/remoteid/tt0310455": {"data": [{"series": {"id": 78874, "name": "Foyle's War"}}]},
    f"{B}/series/78874": {"data": {"id": 78874, "name": "Foyle's War", "year": "2002"}},
    f"{B}/series/78874/translations/spa": {"data": {"name": "La guerra de Foyle", "language": "spa"}},
    f"{B}/series/slug/foyles-war": {"data": {"id": 78874, "name": "Foyle's War"}},
}


def tvdb(routes=None, post=None, pin=""):
    f = FakeFetch({**ROUTES, **(routes or {})})
    return TVDBClient("k", "es", pin=pin, fetch=f, post=post or FakePost()), f


def test_login_once_and_bearer_token():
    post = FakePost()
    c, f = tvdb(post=post, pin="1234")
    c.search_series("foyle")
    c.search_series("foyle 2")
    assert len(post.calls) == 1 and post.calls[0][1] == {"apikey": "k", "pin": "1234"}
    assert all(h.get("Authorization") == "Bearer tok1" for _, h in f.calls)


def test_expired_token_is_renewed_once():
    post = FakePost(token=["viejo", "nuevo"])
    state = {"n": 0}

    def search(q):
        state["n"] += 1
        if state["n"] == 1:
            return InvalidApiKey("token caducado")
        return ROUTES[f"{B}/search"]
    c, f = tvdb({f"{B}/search": search}, post=post)
    assert c.search_series("foyle")[0].id == 78874
    assert len(post.calls) == 2 and f.calls[-1][1]["Authorization"] == "Bearer nuevo"


def test_bad_key_raises():
    c, _ = tvdb(post=FakePost(fail=True))
    try:
        c.search_series("foyle")
    except InvalidApiKey:
        pass
    else:
        raise AssertionError("debía fallar")


def test_search_uses_translated_name():
    c, _ = tvdb()
    [r] = c.search_series("foyle")
    assert (r.provider, r.id, r.title, r.original_title, r.year) == ("tvdb", 78874, "La guerra de Foyle", "Foyle's War", 2002)


def test_season_spanish_titles_and_untranslated_marked():
    c, _ = tvdb()
    eps = c.get_season(78874, 1)
    assert [(e.title, e.source) for e in eps] == [
        ("La mujer alemana", "tvdb"), ("La pluma blanca", "tvdb"), ("Una lección de asesinato", "tvdb"),
        ("Eagle Day", "tvdb-en")]
    assert c.list_seasons(78874) == [0, 1, 2]


def test_each_season_gets_its_own_titles():
    """Regresión 1.2.0: todas las temporadas salían con los títulos de la última."""
    c, f = tvdb()
    s1, s2 = c.get_season(78874, 1), c.get_season(78874, 2)
    assert [e.title for e in s1][:2] == ["La mujer alemana", "La pluma blanca"]
    assert [(e.season, e.number, e.title) for e in s2] == [(2, 1, "Cincuenta naves"), (2, 2, "Uno de los pocos")]
    assert [e.title for e in c.get_season(78874, 0)] == ["Especial"]
    assert c.get_season(78874, 9) == []


def test_translations_matched_by_episode_id_not_number():
    """La lista traducida de TheTVDB puede numerar distinto: se empareja por id (caso Foyle's War)."""
    norm = {"episodes": [{"id": 501, "seasonNumber": 5, "number": 1, "name": "Plan of Attack"},
                         {"id": 601, "seasonNumber": 6, "number": 1, "name": "The Russian House"}]}
    spa = {"episodes": [{"id": 601, "seasonNumber": 7, "number": 1, "name": "La casa rusa"},       # otra numeración
                        {"id": 999, "seasonNumber": 6, "number": 1, "name": "Plan de ataque"}]}    # id que no existe
    c, _ = tvdb({f"{B}/series/78874/episodes/default": {"data": norm},
                 f"{B}/series/78874/episodes/default/spa": {"data": spa}})
    assert [(e.title, e.source) for e in c.get_season(78874, 6)] == [("La casa rusa", "tvdb")]
    assert [(e.title, e.source) for e in c.get_season(78874, 5)] == [("Plan of Attack", "tvdb-en")]


def test_lookup_imdb_and_slug():
    c, _ = tvdb()
    assert c.lookup_imdb("tt0310455").title == "La guerra de Foyle"
    assert c.get_by_slug("foyles-war").id == 78874
    c2, _ = tvdb({f"{B}/search/remoteid/tt0000001": NotFound("x")})
    assert c2.lookup_imdb("tt0000001") is None


def test_parse_ref_tvdb_links():
    assert parse_ref("https://thetvdb.com/series/foyles-war") == ("tvdb", ResultKind.SERIES, "foyles-war")
    assert parse_ref("https://www.thetvdb.com/series/foyles-war/seasons/official/1") == ("tvdb", ResultKind.SERIES, "foyles-war")


# ---- en el buscador: TMDB elegido, con los capítulos solo en inglés → TheTVDB los da en español

def _tmdb():
    def season(q):
        return {"episodes": [{"episode_number": i + 1, "name": (t if q["language"] == "en-US" else f"Episodio {i + 1}")}
                             for i, t in enumerate(EN)]}
    f = FakeFetch({"/3/tv/4057/season/1": season,
                   "/3/tv/4057/external_ids": {"imdb_id": "tt0310455", "tvdb_id": 78874},
                   "/3/search/tv": {"results": []}, "/3/search/movie": {"results": []}})
    return TMDBClient("a" * 32, "es", fetch=f)


def test_searcher_prefers_spanish_titles_from_tvdb():
    c, _ = tvdb()
    s = Searcher(_tmdb(), None, tvdb=c, language="es")
    show = SearchResult("tmdb", ResultKind.SERIES, 4057, "Foyle's War", 2002, "Foyle's War")
    eps = s.episode_titles_detailed(show, 1, (1, 2, 4))
    assert [(e.title, e.source) for e in eps] == [
        ("La mujer alemana", "tvdb"), ("La pluma blanca", "tvdb"), ("Eagle Day", "tmdb-en")]
    listed = s.season_episodes(show, 1)
    assert [e.title for e in listed] == ["La mujer alemana", "La pluma blanca", "Una lección de asesinato", "Eagle Day"]


def test_english_searcher_keeps_tmdb_titles():
    c, f = tvdb()
    tm = _tmdb()
    tm._lang = "en-US"
    s = Searcher(tm, None, tvdb=c, language="en")
    show = SearchResult("tmdb", ResultKind.SERIES, 4057, "Foyle's War", 2002)
    assert [e.title for e in s.episode_titles_detailed(show, 1, (1,))] == ["The German Woman"]
    assert not any("/episodes/" in u for u, _ in f.calls)             # ni se pregunta a TheTVDB


def test_imdb_link_also_finds_tvdb_and_search_includes_it():
    c, _ = tvdb()
    s = Searcher(None, None, tvdb=c, language="es")
    res = s.search("https://www.imdb.com/title/tt0310455/")
    assert [(r.provider, r.id) for r in res.results] == [("tvdb", 78874)]
    res = s.search("foyle", kind=MediaKind.EPISODE)
    assert res.results[0].provider == "tvdb" and res.results[0].title == "La guerra de Foyle"
