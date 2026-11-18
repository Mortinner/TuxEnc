"""Búsqueda en varios motores a la vez: TMDB, TVmaze e IMDb (vía OMDb).

* Cada motor aporta sus propias coincidencias: NO se fusionan (los títulos varían de un motor a otro).
  Las que son la misma serie salen juntas, una fila por motor.
* Series: TMDB, TVmaze y OMDb (si hay clave). Películas: TMDB y OMDb (si hay clave).
* Títulos de episodio: primero el motor de la coincidencia (TMDB en tu idioma); si falta o es un
  marcador («Episodio 9») se prueba TMDB en inglés y, después, los demás motores.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from .config import KeyStore, Settings, cache_dir
from .log import log
from .matching import normalize, score_candidate
from .parser import MediaKind, ParsedName
from .providers import (
    ENGLISH_SOURCES, PROVIDER_NAMES, PROVIDER_RANK, EpisodeInfo, InvalidApiKey, JsonCache, OMDbClient, ProviderError, ResultKind,
    SearchResult, TMDBClient, TVDBClient, TVmazeClient,
)

__all__ = ["SearchResponse", "Searcher", "build_searcher", "pick_best", "parse_ref"]

_IMDB_REF = re.compile(r"(?<![a-z0-9])(tt\d{6,10})(?!\d)", re.I)
_TMDB_REF = re.compile(r"themoviedb\.org/(?:[a-z]{2}(?:-[a-z]{2})?/)?(tv|movie)/(\d+)", re.I)
_TVMAZE_REF = re.compile(r"tvmaze\.com/shows/(\d+)", re.I)
_TVDB_REF = re.compile(r"thetvdb\.com/(?:[a-z]{2,3}/)?series/([a-z0-9][a-z0-9-]*)", re.I)


def parse_ref(text: str) -> tuple[str, ResultKind | None, int | str] | None:
    """Reconoce un enlace o código de IMDb, TMDB o TVmaze pegado en el buscador.

    Devuelve (motor, tipo o None, id) o None si es un nombre normal.
    """
    text = (text or "").strip()
    if m := _TMDB_REF.search(text):
        return "tmdb", ResultKind.SERIES if m.group(1).lower() == "tv" else ResultKind.MOVIE, int(m.group(2))
    if m := _TVMAZE_REF.search(text):
        return "tvmaze", ResultKind.SERIES, int(m.group(1))
    if m := _TVDB_REF.search(text):
        slug = m.group(1).lower()
        return "tvdb", ResultKind.SERIES, int(slug) if slug.isdigit() else slug
    if m := _IMDB_REF.search(text):
        return "imdb", None, m.group(1).lower()
    return None


@dataclass
class SearchResponse:
    results: list[SearchResult] = field(default_factory=list)  # ordenados de mejor a peor
    warnings: list[str] = field(default_factory=list)          # avisos para mostrar al usuario


def _same_show(a: SearchResult, b: SearchResult) -> bool:
    names_a = {normalize(a.title), normalize(a.original_title)} - {""}
    names_b = {normalize(b.title), normalize(b.original_title)} - {""}
    if not names_a & names_b:
        return False
    return not (a.year and b.year and abs(a.year - b.year) > 1)


def _group_and_sort(results: list[SearchResult]) -> list[SearchResult]:
    """Ordena de mejor a peor dejando juntas (sin fusionarlas) las filas que son lo mismo en motores distintos.

    Dentro de cada grupo mandan TMDB, luego TVmaze y luego IMDb; los grupos se ordenan por su mejor puntuación.
    """
    groups: list[list[SearchResult]] = []
    for r in sorted(results, key=lambda r: (-r.score, PROVIDER_RANK.get(r.provider, 9))):
        for g in groups:
            if g[0].kind is r.kind and all(m.provider != r.provider for m in g) and _same_show(g[0], r):
                g.append(r)
                break
        else:
            groups.append([r])
    for g in groups:
        g.sort(key=lambda r: PROVIDER_RANK.get(r.provider, 9))
    groups.sort(key=lambda g: -max(r.score for r in g))
    return [r for g in groups for r in g]


def pick_best(results: list[SearchResult], min_score: float = 0.75) -> SearchResult | None:
    """La mejor coincidencia si es lo bastante buena para elegirla sin preguntar.

    Si varios motores la encuentran, se prefiere TMDB, luego TVmaze y luego IMDb.
    """
    if not results:
        return None
    top = results[0]
    for r in results:
        if r.kind is top.kind and _same_show(top, r) and r.score >= min_score:
            return r
    return None


class Searcher:
    def __init__(self, tmdb: TMDBClient | None = None, tvmaze: TVmazeClient | None = None,
                 cache: JsonCache | None = None, omdb: OMDbClient | None = None,
                 tvdb: TVDBClient | None = None, language: str = "es") -> None:
        self.tmdb, self.tvmaze, self.omdb, self.tvdb, self.cache = tmdb, tvmaze, omdb, tvdb, cache
        self.language = language
        # Orden = prioridad al buscar títulos de episodio que faltan.
        self._clients = {name: c for name, c in (("tmdb", tmdb), ("tvdb", tvdb), ("tvmaze", tvmaze), ("omdb", omdb))
                         if c is not None}
        self._links: dict[tuple[str, int | str], list[tuple[str, int | str]]] = {}

    def clear_cache(self) -> None:
        if self.cache is not None:
            self.cache.clear()
        self._links.clear()

    # ------------------------------------------------------------------ #
    def search(self, query: str, *, kind: MediaKind | None = None, year: int | None = None) -> SearchResponse:
        """Busca series y/o películas. ``kind`` None o UNKNOWN busca en ambos."""
        query = query.strip()
        if not query:
            return SearchResponse()
        warnings: list[str] = []
        ref = parse_ref(query)
        if ref is not None:
            return self._by_ref(ref, kind, warnings)
        results: list[SearchResult] = []
        if kind in (None, MediaKind.UNKNOWN, MediaKind.EPISODE):
            results += self._series(query, warnings)
        if kind in (None, MediaKind.UNKNOWN, MediaKind.MOVIE):
            results += self._movies(query, warnings, explicit=kind is MediaKind.MOVIE)
        scored = [
            replace(r, score=score_candidate(query, year, (r.title, r.original_title), r.year, r.popularity))
            for r in results
        ]
        scored = _group_and_sort(scored)
        log.info("búsqueda %r (%s, año %s): %d resultado(s); mejor: %s", query, kind.value if kind else "todo", year,
                 len(scored), f"{scored[0].label} [{scored[0].provider_name}] {scored[0].score:.2f}" if scored else "ninguno")
        return SearchResponse(scored, list(dict.fromkeys(warnings)))

    def _by_ref(self, ref, kind: MediaKind | None, warnings: list[str]) -> SearchResponse:
        """Búsqueda exacta por enlace o código (IMDb, TMDB, TVmaze)."""
        source, rkind, ident = ref
        found: list[SearchResult] = []

        def ask(label: str, fn, *args):
            try:
                r = fn(*args)
            except InvalidApiKey:
                warnings.append(f"La clave de {label} no es válida.")
                return
            except ProviderError as exc:
                warnings.append(f"{label} no respondió ({exc}).")
                return
            if isinstance(r, list):
                found.extend(r)
            elif r is not None:
                found.append(r)

        if source == "imdb":
            if self.tmdb:
                ask("TMDB", self.tmdb.find_imdb, ident)
            if self.tvdb:
                ask("TheTVDB", self.tvdb.lookup_imdb, ident)
            if self.tvmaze:
                ask("TVmaze", self.tvmaze.lookup, ident)
            if self.omdb:
                ask("IMDb", self.omdb.get_by_id, ident)
            if not found and not (self.tmdb or self.omdb) and not warnings:
                warnings.append("Sin clave de TMDB ni de OMDb solo se pueden buscar series por código de IMDb.")
        elif source == "tmdb":
            if self.tmdb:
                ask("TMDB", self.tmdb.get_by_id, rkind, ident)
            else:
                warnings.append("Para usar un enlace de TMDB hace falta una clave de TMDB (configúrala en Preferencias).")
        elif source == "tvmaze" and self.tvmaze:
            ask("TVmaze", self.tvmaze.get_by_id, ident)
        elif source == "tvdb":
            if self.tvdb:
                ask("TheTVDB", self.tvdb.get_by_id if isinstance(ident, int) else self.tvdb.get_by_slug, ident)
            else:
                warnings.append("Para usar un enlace de TheTVDB hace falta su clave (Ajustes → Renombrado y buscadores).")
        if kind is MediaKind.EPISODE:
            found = [r for r in found if r.kind is ResultKind.SERIES] or found
        elif kind is MediaKind.MOVIE:
            found = [r for r in found if r.kind is ResultKind.MOVIE] or found
        scored = _group_and_sort([replace(r, score=1.0) for r in found])
        log.info("búsqueda por código %s %s: %d resultado(s)", source, ident, len(scored))
        return SearchResponse(scored, list(dict.fromkeys(warnings)))

    def search_parsed(self, parsed: ParsedName) -> SearchResponse:
        return self.search(parsed.title, kind=parsed.kind, year=parsed.year)

    def _ask(self, name: str, method: str, query: str, warnings: list[str], what: str) -> list[SearchResult]:
        """Pregunta a un motor; si falla, deja un aviso y sigue con los demás."""
        client = self._clients.get(name)
        if client is None:
            return []
        label = PROVIDER_NAMES[name]
        try:
            return getattr(client, method)(query)
        except InvalidApiKey:
            warnings.append(f"La clave de {label} no es válida; no se usa {label} para {what}.")
        except ProviderError as exc:
            warnings.append(f"{label} no respondió ({exc}).")
        return []

    def _series(self, query: str, warnings: list[str]) -> list[SearchResult]:
        return [r for name in self._clients for r in self._ask(name, "search_series", query, warnings, "las series")]

    def _movies(self, query: str, warnings: list[str], explicit: bool) -> list[SearchResult]:
        if explicit and not (self.tmdb or self.omdb):
            warnings.append("Para buscar películas hace falta una clave de TMDB o de OMDb (configúrala en Configuración).")
        return [r for name in ("tmdb", "omdb") for r in self._ask(name, "search_movies", query, warnings, "las películas")]

    # ------------------------------------------------------------------ #
    # Títulos de episodio
    # ------------------------------------------------------------------ #
    def _linked(self, result: SearchResult) -> list[tuple[str, int | str]]:
        """La misma serie en los otros motores (para completar títulos que falten), con caché."""
        key = (result.provider, result.id)
        if key not in self._links:
            others = [name for name in self._clients if name != result.provider]
            ext = self._external_ids(result) if others else {}
            found = []
            for name in others:
                ident = self._find_in(name, result, ext)
                if ident is not None:
                    found.append((name, ident))
            self._links[key] = found
        return self._links[key]

    def _external_ids(self, result: SearchResult) -> dict:
        if result.provider == "omdb":
            return {"imdb_id": str(result.id)}
        if result.provider == "tvdb":
            return {"tvdb_id": result.id}
        if result.provider == "tvmaze" and self.tvmaze:
            try:
                return self.tvmaze.external_ids(int(result.id))
            except ProviderError as exc:
                log.info("no se pudieron consultar los ids externos de %s: %s", result.label, exc)
        if result.provider == "tmdb" and self.tmdb:
            try:
                return self.tmdb.external_ids(int(result.id))
            except ProviderError as exc:
                log.info("no se pudieron consultar los ids externos de %s: %s", result.label, exc)
        return {}

    def _find_in(self, name: str, result: SearchResult, ext: dict) -> int | str | None:
        """Enlaza una serie con otro motor: primero por id externo (exacto), si no, por nombre."""
        imdb = ext.get("imdb_id")
        if name == "omdb" and imdb:
            return imdb
        if name == "tvdb":
            if ext.get("tvdb_id"):
                try:
                    return int(ext["tvdb_id"])
                except (TypeError, ValueError):
                    pass
            if imdb and self.tvdb:
                try:
                    show = self.tvdb.lookup_imdb(imdb)
                except ProviderError:
                    show = None
                if show:
                    log.info("%s %s ↔ TheTVDB %s (por IMDb)", result.provider, result.id, show.id)
                    return show.id
        if name == "tvmaze":
            for kwargs in ({"imdb": imdb}, {"tvdb": ext.get("tvdb_id")}):
                if any(kwargs.values()):
                    try:
                        show = self.tvmaze.lookup(**kwargs)  # type: ignore[union-attr]
                    except ProviderError:
                        continue
                    if show:
                        log.info("%s %s ↔ TVmaze %s (por id externo)", result.provider, result.id, show.id)
                        return show.id
        client = self._clients[name]
        for query in dict.fromkeys(q for q in (result.original_title, result.title) if q):
            try:
                for r in client.search_series(query):
                    if _same_show(result, r):
                        log.info("%s %s ↔ %s %s (por nombre)", result.provider, result.id, name, r.id)
                        return r.id
            except ProviderError:
                break
        return None

    # ------------------------------------------------------------- temporadas y capítulos
    def _quality(self, e: EpisodeInfo | None) -> int:
        """0 sin título o provisional · 1 título en otro idioma · 2 título en el idioma pedido."""
        if e is None or not e.title or e.provisional:
            return 0
        if getattr(self, "language", "es") != "en" and e.source in ENGLISH_SOURCES:
            return 1
        return 2

    def _all_sources(self, result: SearchResult) -> list[tuple[str, int | str]]:
        return [(result.provider, result.id)] + list(self._linked(result))

    def seasons(self, result: SearchResult) -> list[int]:
        """Temporadas disponibles, uniendo todos los motores (alguno puede ir más al día).

        Lanza ProviderError solo si no responde ninguno.
        """
        if result.kind is not ResultKind.SERIES:
            return []
        found: set[int] = set()
        errors = []
        for provider, ident in self._all_sources(result):
            try:
                found.update(self._clients[provider].list_seasons(ident))
            except ProviderError as exc:
                errors.append(exc)
        if not found and errors:
            raise errors[0]
        nums = sorted(found)
        return [n for n in nums if n > 0] + [n for n in nums if n == 0]

    def season_episodes(self, result: SearchResult, season: int) -> list[EpisodeInfo]:
        """Todos los capítulos de una temporada: los del motor elegido, completados con los otros
        (capítulos recién estrenados o sin título). Lanza ProviderError solo si no responde ninguno."""
        by_number: dict[int, EpisodeInfo] = {}
        errors = []
        for provider, ident in self._all_sources(result):
            try:
                eps = self._clients[provider].get_season(ident, season)
            except ProviderError as exc:
                errors.append(exc)
                continue
            for e in eps:
                cur = by_number.get(e.number)
                if cur is None or self._quality(e) > self._quality(cur):
                    by_number[e.number] = e
        if not by_number and errors:
            raise errors[0]
        return [by_number[n] for n in sorted(by_number)]

    def episode_titles_detailed(self, result: SearchResult, season: int,
                                episodes: tuple[int, ...] | list[int]) -> list[EpisodeInfo]:
        """Un EpisodeInfo por episodio pedido (con título '' si no existe en ninguna fuente).

        Lanza ProviderError si falla el proveedor principal.
        """
        if result.kind is not ResultKind.SERIES:
            raise ValueError("Solo las series tienen episodios")
        by_number = {e.number: e for e in self._clients[result.provider].get_season(result.id, season)}
        # Se completan con los otros motores los que faltan, son provisionales o no están en el idioma pedido
        missing = [n for n in episodes if self._quality(by_number.get(n)) < 2]
        if missing:
            for provider, ident in self._linked(result):
                try:
                    other = {e.number: e for e in self._clients[provider].get_season(ident, season)}
                except ProviderError as exc:
                    log.info("%s no pudo completar los títulos de %s T%s: %s", provider, result.label, season, exc)
                    continue
                for n in list(missing):
                    alt = other.get(n)
                    if self._quality(alt) > self._quality(by_number.get(n)):
                        log.info("%s S%02dE%02d: título de %s: %r", result.label, season, n, provider, alt.title)
                        by_number[n] = alt
                    if self._quality(by_number.get(n)) >= 2:
                        missing.remove(n)
                if not missing:
                    break
        out = [by_number.get(n, EpisodeInfo(season, n, "")) for n in episodes]
        for e in out:
            log.info("%s S%02dE%02d → %r (fuente: %s%s)", result.label, season, e.number, e.title, e.source or "ninguna",
                     ", provisional" if e.provisional else "")
        return out

    def episode_titles(self, result: SearchResult, season: int, episodes: tuple[int, ...] | list[int]) -> list[str]:
        """Solo los títulos ('' si no existen). Lanza ProviderError si falla la red."""
        return [e.title for e in self.episode_titles_detailed(result, season, episodes)]


def build_searcher(settings: Settings | None = None, keystore: KeyStore | None = None,
                   cache: JsonCache | None = None) -> Searcher:
    """Crea el buscador con los ajustes y las claves guardadas (TMDB y OMDb son opcionales)."""
    settings = settings or Settings.load()
    keystore = keystore or KeyStore()
    tmdb_key, omdb_key = keystore.for_service("tmdb").get(), keystore.for_service("omdb").get()
    tvdb_key, tvdb_pin = keystore.for_service("tvdb").get(), keystore.for_service("tvdbpin").get()
    cache = cache or JsonCache(cache_dir() / "http")
    return Searcher(
        TMDBClient(tmdb_key, settings.language, cache=cache) if tmdb_key else None,
        TVmazeClient(cache=cache), cache,
        OMDbClient(omdb_key, cache=cache) if omdb_key else None,
        TVDBClient(tvdb_key, settings.language, pin=tvdb_pin or "", cache=cache) if tvdb_key else None,
        language=settings.language,
    )
