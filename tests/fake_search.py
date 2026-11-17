"""Buscador simulado (sin internet) para probar el renombrado integrado."""
from retitler.parser import MediaKind
from retitler.providers import EpisodeInfo, ResultKind, SearchResult
from retitler.search import SearchResponse

ARROW = SearchResult("tmdb", ResultKind.SERIES, 1412, "Arrow", 2012, score=0.95)
ARROW_TVM = SearchResult("tvmaze", ResultKind.SERIES, 4, "Arrow", 2012, score=0.95)
BABEL = SearchResult("tmdb", ResultKind.MOVIE, 1164, "Babel", 2006, score=0.97)
BATMAN = SearchResult("tmdb", ResultKind.MOVIE, 414906, "The Batman", 2022, score=0.6)
BATMAN2 = SearchResult("tmdb", ResultKind.MOVIE, 268, "Batman", 1989, score=0.58)
TITLES = {(1, 1): "Piloto", (1, 2): "Honra a tu padre", (1, 3): "Pistoleros solitarios"}


class FakeSearcher:
    def search(self, query, kind=None, year=None):
        _ = kind.value if kind is not None else None     # como el buscador real: exige MediaKind
        q = query.casefold()
        if "arrow" in q:
            return SearchResponse([ARROW, ARROW_TVM])
        if "babel" in q:
            return SearchResponse([BABEL])
        if "batman" in q:
            return SearchResponse([BATMAN, BATMAN2])     # dudosa: puntuación baja
        return SearchResponse([])

    def search_parsed(self, parsed):
        return self.search(parsed.title, kind=parsed.kind, year=parsed.year)

    def episode_titles_detailed(self, result, season, episodes):
        return [EpisodeInfo(season, n, TITLES.get((season, n), ""), source="tmdb") for n in episodes]


def _seasons(self, result):
    return [1, 2, 0] if result.kind is ResultKind.SERIES else []


def _season_episodes(self, result, season):
    titles = {1: ["Piloto", "Honra a tu padre", "Pistoleros solitarios", "Un error inocente"],
              2: ["La ciudad de los héroes", "Identidad"], 0: ["Especial: el origen"]}
    return [EpisodeInfo(season, i + 1, t, f"2012-10-{10 + i:02}", "tmdb") for i, t in enumerate(titles.get(season, []))]


FakeSearcher.seasons = _seasons
FakeSearcher.season_episodes = _season_episodes
