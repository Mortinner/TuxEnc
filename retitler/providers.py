"""Clientes de TMDB, TVmaze y OMDb/IMDb (solo biblioteca estándar) con caché.

Las peticiones HTTP pasan por una función ``fetch(url, headers) -> JSON`` que se puede
sustituir (los tests usan una falsa), y los mensajes de error nunca incluyen la URL
para no filtrar la clave de API.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections import deque
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .log import log

__all__ = [
    "CachedFetch", "EpisodeInfo", "RATE_LIMITER", "RateLimiter", "InvalidApiKey", "JsonCache", "NotFound", "ProviderError",
    "ENGLISH_SOURCES", "OMDbClient", "PROVIDER_NAMES", "PROVIDER_RANK", "ResultKind", "SOURCE_NAMES", "SearchResult", "TMDBClient",
    "TVDBClient", "TVmazeClient", "is_placeholder", "urllib_fetch", "urllib_post",
]

USER_AGENT = "Retitler/0.1 (+renombrador de series y peliculas)"
Fetch = Callable[[str, Mapping[str, str]], Any]


class ProviderError(Exception):
    """Fallo al hablar con un proveedor (sin conexión, error del servidor...)."""


class InvalidApiKey(ProviderError):
    """El proveedor rechazó la clave de API."""


class NotFound(ProviderError):
    """El recurso pedido no existe."""


class ResultKind(str, Enum):
    SERIES = "series"
    MOVIE = "movie"


# Nombre de cada motor para mostrar, y su prioridad cuando dos coinciden igual de bien.
PROVIDER_NAMES = {"tmdb": "TMDB", "tvdb": "TheTVDB", "tvmaze": "TVmaze", "omdb": "IMDb"}
PROVIDER_RANK = {"tmdb": 0, "tvdb": 1, "tvmaze": 2, "omdb": 3}


@dataclass(frozen=True)
class SearchResult:
    provider: str            # "tmdb" | "tvmaze" | "omdb"
    kind: ResultKind
    id: int | str            # número en TMDB y TVmaze; «tt1234567» en IMDb
    title: str
    year: int | None = None
    original_title: str = ""
    overview: str = ""
    popularity: float = 0.0
    score: float = 0.0       # lo rellena Searcher

    @property
    def provider_name(self) -> str:
        """El motor que lo encontró, para mostrar: «TMDB», «TVmaze» o «IMDb»."""
        return PROVIDER_NAMES.get(self.provider, self.provider)

    @property
    def label(self) -> str:
        """Texto para la lista de coincidencias: «Breaking Bad (2008)»."""
        return f"{self.title} ({self.year})" if self.year else self.title


@dataclass(frozen=True)
class EpisodeInfo:
    season: int
    number: int
    title: str
    air_date: str = ""
    source: str = ""            # de dónde sale el título: "tmdb", "tmdb-en" o "tvmaze"
    provisional: bool = False   # el título es un marcador («Episodio 9»): aún no hay título real


SOURCE_NAMES = {"tmdb": "TMDB", "tmdb-mx": "TMDB (español de Latinoamérica)", "tmdb-en": "TMDB (inglés)",
                "tvdb": "TheTVDB", "tvdb-en": "TheTVDB (idioma original)",
                "tvmaze": "TVmaze", "omdb": "IMDb", "archivo": "tu archivo"}
# Fuentes cuyos títulos no están en el idioma pedido (TVmaze e IMDb solo tienen inglés)
ENGLISH_SOURCES = frozenset({"tmdb-en", "tvdb-en", "tvmaze", "omdb"})

# TMDB y TVmaze devuelven «Episodio 9» / «Episode 9» cuando el episodio aún no tiene título.
# «Episodio 9» en varios idiomas, también con el número delante («1.Bölüm», «1. Folge») y en
# japonés, chino y coreano («第1話», «第1集», «1화»): aún no hay título real.
_EP_WORDS = (r"episode|episodio|épisode|episódio|episodi|episod|folge|capítulo|capitulo|capitolo|puntata|"
             r"afl\.?|aflevering|avsnitt|jakso|epizód|epizoda|odcinek|bölüm|серия|эпизод|επεισόδιο|tập")
_PLACEHOLDER = re.compile(
    rf"^\s*(?:(?:{_EP_WORDS})\s*#?\s*\d+|\d+\s*\.?\s*(?:{_EP_WORDS})|第\s*\d+\s*[話话集回]|제?\s*\d+\s*화)\s*$",
    re.I)


def is_placeholder(title: str) -> bool:
    return bool(_PLACEHOLDER.match(title or ""))


def _safe_url(url: str) -> str:
    """La URL sin la clave de API, para poder escribirla en el registro."""
    parts = urlsplit(url)
    query = [(k, "***" if k.lower() in ("api_key", "apikey") else v) for k, v in parse_qsl(parts.query)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


# --------------------------------------------------------------------------- #
# HTTP y caché
# --------------------------------------------------------------------------- #
class RateLimiter:
    """Como mucho ``n`` peticiones cada ``per`` segundos por servidor (compartido entre hilos).

    TVmaze admite unas 20 cada 10 s y TMDB unas 50 por segundo; si se superan responden 429.
    """

    LIMITS = {"api.tvmaze.com": (18, 10.0), "api.themoviedb.org": (40, 1.0), "www.omdbapi.com": (10, 1.0)}

    def __init__(self, limits: Mapping[str, tuple[int, float]] | None = None,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> None:
        self._limits = dict(self.LIMITS if limits is None else limits)
        self._clock, self._sleep = clock, sleep
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def wait(self, host: str) -> None:
        limit = self._limits.get(host)
        if limit is None:
            return
        n, per = limit
        while True:
            with self._lock:
                now = self._clock()
                hits = self._hits.setdefault(host, deque())
                while hits and now - hits[0] >= per:
                    hits.popleft()
                if len(hits) < n:
                    hits.append(now)
                    return
                delay = per - (now - hits[0])
            self._sleep(max(delay, 0.01))


RATE_LIMITER = RateLimiter()


def urllib_fetch(url: str, headers: Mapping[str, str], timeout: float = 10.0) -> Any:
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": USER_AGENT, **dict(headers)}
    )
    host = urlsplit(url).netloc
    for attempt in (1, 2, 3):
        RATE_LIMITER.wait(host)
        try:
            log.debug("GET %s", _safe_url(url))
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            log.warning("HTTP %s en %s", exc.code, _safe_url(url))
            if exc.code == 401:
                # OMDb responde 401 tanto a una clave mala como al agotar el límite diario.
                try:
                    detail = str(json.loads(exc.read().decode("utf-8")).get("Error", ""))
                except (OSError, ValueError, AttributeError):
                    detail = ""
                if "limit" in detail.lower():
                    raise ProviderError("Se agotó el límite diario de peticiones") from None
                raise InvalidApiKey("El servidor rechazó la clave de API") from None
            if exc.code == 404:
                raise NotFound("No encontrado") from None
            if exc.code == 429 and attempt < 3:  # límite de peticiones: se espera y se reintenta
                try:
                    wait = float(exc.headers.get("Retry-After", 2 * attempt))
                except (TypeError, ValueError, AttributeError):
                    wait = 2.0 * attempt
                time.sleep(min(max(wait, 0.5), 10.0))
                continue
            raise ProviderError(f"El servidor respondió con error HTTP {exc.code}") from None
        except urllib.error.URLError as exc:
            log.warning("Sin conexión con %s: %s", urlsplit(url).netloc, exc.reason)
            raise ProviderError("No se pudo conectar con el servidor") from None
        except (OSError, ValueError):
            raise ProviderError("Respuesta no válida del servidor") from None
    raise ProviderError("Demasiadas peticiones; inténtalo de nuevo en unos segundos")


def urllib_post(url: str, body: Mapping[str, Any], headers: Mapping[str, str] | None = None,
                timeout: float = 10.0) -> Any:
    """POST con cuerpo JSON (solo lo usa el inicio de sesión de TheTVDB). Nunca se cachea."""
    request = urllib.request.Request(
        url, data=json.dumps(dict(body)).encode("utf-8"), method="POST",
        headers={"Accept": "application/json", "Content-Type": "application/json",
                 "User-Agent": USER_AGENT, **dict(headers or {})})
    RATE_LIMITER.wait(urlsplit(url).netloc)
    try:
        log.debug("POST %s", _safe_url(url))
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        log.warning("HTTP %s en %s", exc.code, _safe_url(url))
        if exc.code in (401, 403):
            raise InvalidApiKey("El servidor rechazó la clave de API") from None
        raise ProviderError(f"El servidor respondió con error HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        log.warning("Sin conexión con %s: %s", urlsplit(url).netloc, exc.reason)
        raise ProviderError("No se pudo conectar con el servidor") from None
    except (OSError, ValueError):
        raise ProviderError("Respuesta no válida del servidor") from None


class JsonCache:
    """Caché con caducidad, en memoria y opcionalmente en disco (un JSON por petición).

    La clave de búsqueda se guarda como hash, así que no queda ninguna clave de API en claro.
    """

    def __init__(self, directory: str | Path | None = None, ttl: float = 24 * 3600.0,
                 clock: Callable[[], float] = time.time) -> None:
        self._dir = Path(directory) if directory else None
        self._ttl = ttl
        self._clock = clock
        self._mem: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _key(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def get(self, url: str, ttl: float | None = None) -> tuple[bool, Any]:
        k = self._key(url)
        max_age = self._ttl if ttl is None else ttl
        entry = self._mem.get(k)
        if entry is None and self._dir:
            try:
                entry = json.loads((self._dir / f"{k}.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                entry = None
        try:
            if entry is not None and self._clock() - float(entry["t"]) <= max_age:
                self._mem[k] = entry
                return True, entry["v"]
        except (KeyError, TypeError, ValueError):
            pass
        return False, None

    def set(self, url: str, value: Any) -> None:
        k = self._key(url)
        entry = {"t": self._clock(), "v": value}
        self._mem[k] = entry
        if self._dir:
            try:
                self._dir.mkdir(parents=True, exist_ok=True)
                tmp = self._dir / f"{k}.json.{os.getpid()}-{threading.get_ident()}.tmp"   # único por hilo
                tmp.write_text(json.dumps(entry), encoding="utf-8")
                os.replace(tmp, self._dir / f"{k}.json")
            except OSError:
                pass  # la caché es opcional


    def clear(self) -> None:
        """Borra todo lo guardado (memoria y disco)."""
        self._mem.clear()
        if self._dir:
            for f in self._dir.glob("*.json*"):
                try:
                    f.unlink()
                except OSError:
                    pass


# Las listas de episodios cambian (se publican títulos nuevos y traducciones): caducan antes.
SEASON_TTL = 2 * 3600.0


class CachedFetch:
    # Un «no existe» (HTTP 404) se recuerda un rato solo en memoria: en una tanda grande, una
    # temporada que TMDB no tiene se pedía una vez por capítulo (hasta 12 veces la misma).
    NOT_FOUND_TTL = 30 * 60.0

    def __init__(self, fetch: Fetch, cache: JsonCache, clock: Callable[[], float] = time.monotonic) -> None:
        self._fetch, self._cache, self._clock = fetch, cache, clock
        self._missing: dict[str, float] = {}

    def __call__(self, url: str, headers: Mapping[str, str]) -> Any:
        short = "/season/" in url or "/episodes" in url or "Season=" in url
        hit, value = self._cache.get(url, SEASON_TTL if short else None)
        if hit:
            return value
        seen = self._missing.get(url)
        if seen is not None and self._clock() - seen < self.NOT_FOUND_TTL:
            raise NotFound("No encontrado")
        try:
            value = self._fetch(url, headers)
        except NotFound:
            self._missing[url] = self._clock()
            raise
        self._cache.set(url, value)
        return value


def _year(date: Any) -> int | None:
    text = str(date or "")
    return int(text[:4]) if len(text) >= 4 and text[:4].isdigit() else None


def _items(data: Any, key: str | None = None) -> list[dict[str, Any]]:
    rows = data.get(key, []) if key and isinstance(data, dict) else data
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


# --------------------------------------------------------------------------- #
# TMDB
# --------------------------------------------------------------------------- #
class TMDBClient:
    BASE = "https://api.themoviedb.org/3"
    LANGS = {"es": "es-ES", "en": "en-US"}

    def __init__(self, api_key: str, language: str = "es", fetch: Fetch | None = None,
                 cache: JsonCache | None = None) -> None:
        self._key = api_key.strip()
        self._lang = self.LANGS.get(language, "es-ES")
        self._raw_fetch: Fetch = fetch or urllib_fetch
        self._fetch: Fetch = CachedFetch(self._raw_fetch, cache) if cache else self._raw_fetch

    def _request(self, path: str, language: str | None = None, **params: Any) -> tuple[str, dict[str, str]]:
        query = {k: v for k, v in params.items() if v is not None}
        query["language"] = language or self._lang
        headers: dict[str, str] = {}
        # Token de acceso de lectura (v4, empieza por "eyJ") o clave v3 (32 caracteres).
        if self._key.startswith("eyJ") or len(self._key) > 40:
            headers["Authorization"] = f"Bearer {self._key}"
        else:
            query["api_key"] = self._key
        return f"{self.BASE}{path}?{urlencode(query)}", headers

    def _get(self, path: str, language: str | None = None, **params: Any) -> Any:
        url, headers = self._request(path, language, **params)
        return self._fetch(url, headers)

    def validate_key(self) -> bool:
        """True si TMDB acepta la clave. Lanza ProviderError si no hay conexión."""
        url, headers = self._request("/configuration")
        try:
            self._raw_fetch(url, headers)  # sin caché: hay que preguntar de verdad
        except InvalidApiKey:
            return False
        return True

    def search_series(self, query: str) -> list[SearchResult]:
        data = self._get("/search/tv", query=query, include_adult="false")
        return [
            SearchResult("tmdb", ResultKind.SERIES, int(r["id"]), r.get("name") or "",
                         _year(r.get("first_air_date")), r.get("original_name") or "",
                         r.get("overview") or "", float(r.get("popularity") or 0))
            for r in _items(data, "results") if "id" in r
        ]

    def search_movies(self, query: str) -> list[SearchResult]:
        data = self._get("/search/movie", query=query, include_adult="false")
        return [
            SearchResult("tmdb", ResultKind.MOVIE, int(r["id"]), r.get("title") or "",
                         _year(r.get("release_date")), r.get("original_title") or "",
                         r.get("overview") or "", float(r.get("popularity") or 0))
            for r in _items(data, "results") if "id" in r
        ]

    def find_imdb(self, imdb_id: str) -> list[SearchResult]:
        """Series y películas de TMDB que corresponden a un id de IMDb («tt1234567»)."""
        data = self._get(f"/find/{imdb_id}", external_source="imdb_id")
        out = [SearchResult("tmdb", ResultKind.SERIES, int(r["id"]), r.get("name") or "",
                            _year(r.get("first_air_date")), r.get("original_name") or "",
                            r.get("overview") or "", float(r.get("popularity") or 0))
               for r in _items(data, "tv_results") if "id" in r]
        out += [SearchResult("tmdb", ResultKind.MOVIE, int(r["id"]), r.get("title") or "",
                             _year(r.get("release_date")), r.get("original_title") or "",
                             r.get("overview") or "", float(r.get("popularity") or 0))
                for r in _items(data, "movie_results") if "id" in r]
        return out

    def get_by_id(self, kind: ResultKind, ident: int) -> SearchResult | None:
        try:
            r = self._get(f"/{'tv' if kind is ResultKind.SERIES else 'movie'}/{int(ident)}")
        except NotFound:
            return None
        if not isinstance(r, dict) or "id" not in r:
            return None
        if kind is ResultKind.SERIES:
            return SearchResult("tmdb", kind, int(r["id"]), r.get("name") or "", _year(r.get("first_air_date")),
                                r.get("original_name") or "", r.get("overview") or "",
                                float(r.get("popularity") or 0))
        return SearchResult("tmdb", kind, int(r["id"]), r.get("title") or "", _year(r.get("release_date")),
                            r.get("original_title") or "", r.get("overview") or "", float(r.get("popularity") or 0))

    def _season(self, series_id: int, season: int, language: str | None) -> list[EpisodeInfo]:
        data = self._get(f"/tv/{series_id}/season/{season}", language)
        return [
            EpisodeInfo(season, int(e["episode_number"]), e.get("name") or "", e.get("air_date") or "")
            for e in _items(data, "episodes") if "episode_number" in e
        ]

    def get_season(self, series_id: int, season: int) -> list[EpisodeInfo]:
        """Episodios de una temporada. Si el título no está traducido (vacío o un marcador como
        «Episodio 9») se completa con el título en inglés; si tampoco existe, queda como provisional."""
        try:
            episodes = self._season(series_id, season, None)
        except NotFound:
            return []
        if self._lang == "en-US":
            return [replace(e, source="tmdb", provisional=bool(e.title) and is_placeholder(e.title)) for e in episodes]
        # Sin traducir: primero el español de Latinoamérica (si se pidió español) y luego el inglés
        fallbacks = ([("es-MX", "tmdb-mx")] if self._lang == "es-ES" else []) + [("en-US", "tmdb-en")]
        alt: dict[str, dict[int, EpisodeInfo]] = {}

        def bad(t: str) -> bool:
            return not t or is_placeholder(t)

        out = []
        for e in episodes:
            if not bad(e.title):
                out.append(replace(e, source="tmdb"))
                continue
            found = None
            for lang, src in fallbacks:
                if lang not in alt:
                    try:
                        alt[lang] = {x.number: x for x in self._season(series_id, season, lang)}
                    except NotFound:
                        alt[lang] = {}
                cand = alt[lang].get(e.number)
                if cand and not bad(cand.title):
                    found = (cand.title, src)
                    break
            if found:
                log.info("TMDB: S%02dE%02d sin título en %s (%r); se usa %s: %r",
                         season, e.number, self._lang, e.title, found[1], found[0])
                out.append(replace(e, title=found[0], source=found[1]))
            else:
                en = alt.get("en-US", {}).get(e.number)
                title = e.title or (en.title if en else "")
                log.info("TMDB: S%02dE%02d solo tiene un título provisional: %r", season, e.number, title)
                out.append(replace(e, title=title, source="tmdb", provisional=bool(title)))
        return out

    def list_seasons(self, series_id: int) -> list[int]:
        """Temporadas con capítulos (0 = especiales, al final)."""
        data = self._get(f"/tv/{series_id}")
        nums = sorted({int(x["season_number"]) for x in (data.get("seasons") or [])
                       if isinstance(x, dict) and x.get("season_number") is not None
                       and int(x.get("episode_count") or 0) > 0})
        return [n for n in nums if n > 0] + [n for n in nums if n == 0]

    def external_ids(self, series_id: int) -> dict[str, Any]:
        """Identificadores externos (imdb_id, tvdb_id...) para enlazar con TVmaze sin adivinar."""
        data = self._get(f"/tv/{series_id}/external_ids")
        return data if isinstance(data, dict) else {}


# --------------------------------------------------------------------------- #
# TVmaze (sin clave; solo series; títulos en inglés)
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# TheTVDB (API v4)
# --------------------------------------------------------------------------- #
Post = Callable[[str, Mapping[str, Any], Mapping[str, str]], Any]


class TVDBClient:
    """Series en TheTVDB. Suele ser el único con los títulos de capítulo traducidos.

    Inicio de sesión: POST /login con la clave (y el PIN de suscriptor si la clave lo exige) →
    token de un mes, que se guarda en memoria y se renueva si el servidor lo rechaza.
    Las películas se dejan a TMDB/IMDb.
    """

    BASE = "https://api4.thetvdb.com/v4"
    LANGS = {"es": "spa", "en": "eng", "fr": "fra", "de": "deu", "it": "ita", "pt": "por"}

    def __init__(self, api_key: str, language: str = "es", pin: str = "", fetch: Fetch | None = None,
                 post: Post | None = None, cache: JsonCache | None = None) -> None:
        if not api_key:
            raise InvalidApiKey("Falta la clave de TheTVDB")
        self._key, self._pin = api_key, pin
        self._lang = self.LANGS.get(language, language if len(language) == 3 else "eng")
        raw: Fetch = fetch or urllib_fetch
        self._raw = raw
        self._fetch: Fetch = CachedFetch(raw, cache) if cache else raw
        self._post: Post = post or urllib_post
        self._token: str | None = None
        self._lock = threading.Lock()

    # -- sesión ------------------------------------------------------------ #
    def _login(self) -> str:
        body = {"apikey": self._key}
        if self._pin:
            body["pin"] = self._pin
        data = self._post(f"{self.BASE}/login", body, {})
        token = (data.get("data") or {}).get("token") if isinstance(data, dict) else None
        if not token:
            raise InvalidApiKey("TheTVDB no aceptó la clave")
        return str(token)

    def _get(self, path: str, **params: Any) -> Any:
        url = f"{self.BASE}{path}" + (f"?{urlencode(params)}" if params else "")
        for attempt in (1, 2):
            with self._lock:
                if self._token is None:
                    self._token = self._login()
                token = self._token
            try:
                data = self._fetch(url, {"Authorization": f"Bearer {token}"})
            except InvalidApiKey:
                if attempt == 1:                 # token caducado: se pide otro una vez
                    with self._lock:
                        self._token = None
                    continue
                raise
            return data.get("data") if isinstance(data, dict) else None
        return None

    # -- búsqueda ---------------------------------------------------------- #
    def _result(self, row: Mapping[str, Any]) -> SearchResult | None:
        ident = row.get("tvdb_id") or row.get("id")
        try:
            ident = int(str(ident).replace("series-", ""))
        except (TypeError, ValueError):
            return None
        trans = row.get("translations") if isinstance(row.get("translations"), dict) else {}
        original = row.get("name") or ""
        title = trans.get(self._lang) or original
        year = row.get("year")
        year = int(year) if str(year or "").isdigit() else _year(row.get("first_air_time") or row.get("firstAired"))
        return SearchResult("tvdb", ResultKind.SERIES, ident, title, year, original,
                            str(row.get("overview") or ""), float(row.get("score") or 0) / 100000)

    def search_series(self, query: str) -> list[SearchResult]:
        rows = self._get("/search", query=query, type="series", limit=20)
        return [r for r in (self._result(x) for x in _items(rows)) if r is not None]

    def lookup_imdb(self, imdb_id: str) -> SearchResult | None:
        try:
            rows = self._get(f"/search/remoteid/{imdb_id}")
        except NotFound:
            return None
        for row in _items(rows):
            series = row.get("series")
            if isinstance(series, dict) and series.get("id"):
                return self.get_by_id(int(series["id"]))
        return None

    def get_by_id(self, ident: int) -> SearchResult | None:
        try:
            row = self._get(f"/series/{int(ident)}")
        except NotFound:
            return None
        if not isinstance(row, dict):
            return None
        res = self._result({**row, "tvdb_id": row.get("id")})
        if res is None:
            return None
        try:
            tr = self._get(f"/series/{int(ident)}/translations/{self._lang}")
            if isinstance(tr, dict) and tr.get("name"):
                res = replace(res, title=str(tr["name"]))
        except (NotFound, InvalidApiKey):
            pass
        return res

    def get_by_slug(self, slug: str) -> SearchResult | None:
        try:
            row = self._get(f"/series/slug/{slug}")
        except NotFound:
            return None
        return self.get_by_id(int(row["id"])) if isinstance(row, dict) and row.get("id") else None

    # -- temporadas y capítulos -------------------------------------------- #
    def _episodes(self, series_id: int, lang: str | None) -> list[dict]:
        """Todos los capítulos de la serie (orden de emisión), página a página.

        OJO: la variante con idioma (/episodes/default/{lang}) NO filtra por temporada aunque se le
        pida; devuelve la serie entera. Por eso no se confía en el filtro del servidor: se piden
        todos y se filtra aquí por seasonNumber (antes, el E01 de cada temporada pisaba al de las
        demás y todas salían con los títulos de la última).
        """
        path = f"/series/{series_id}/episodes/default" + (f"/{lang}" if lang else "")
        out: list[dict] = []
        for page in range(50):
            data = self._get(path, page=page)
            eps = _items(data, "episodes") if isinstance(data, dict) else []
            out += eps
            if len(eps) < 500:                   # TheTVDB pagina de 500 en 500
                break
        return out

    @staticmethod
    def _by_number(eps: list[dict], season: int) -> dict[int, dict]:
        out: dict[int, dict] = {}
        for e in eps:
            try:
                s, n = int(e.get("seasonNumber")), int(e.get("number"))
            except (TypeError, ValueError):
                continue
            if s == season:
                out[n] = e
        return out

    def list_seasons(self, series_id: int) -> list[int]:
        nums = set()
        for e in self._episodes(series_id, None):
            try:
                nums.add(int(e.get("seasonNumber")))
            except (TypeError, ValueError):
                continue
        return sorted(nums)

    def get_season(self, series_id: int, season: int) -> list[EpisodeInfo]:
        """Capítulos de una temporada con el título en el idioma pedido.

        Las traducciones se emparejan por el **id del capítulo**, no por temporada/número: la lista
        traducida de TheTVDB puede numerar distinto que la normal (caso real: Foyle's War).
        """
        orig = self._by_number(self._episodes(series_id, None), season)
        local: dict[int, dict] = {}
        if self._lang != "eng":
            try:
                local = {e["id"]: e for e in self._episodes(series_id, self._lang) if e.get("id") is not None}
            except NotFound:
                local = {}
        out = []
        for n in sorted(orig):
            o = orig[n]
            t = local.get(o.get("id"), {})
            name_o, name_t = str(o.get("name") or "").strip(), str(t.get("name") or "").strip()
            date = str(o.get("aired") or t.get("aired") or "")
            if self._lang == "eng":
                title, source = name_o, "tvdb"
            elif name_t and name_t != name_o:
                title, source = name_t, "tvdb"
            else:                                 # sin traducción: nombre original
                title, source = name_o, "tvdb-en"
            out.append(EpisodeInfo(season, n, title, date, source=source,
                                   provisional=bool(title) and is_placeholder(title)))
        return out


class TVmazeClient:
    BASE = "https://api.tvmaze.com"

    def __init__(self, fetch: Fetch | None = None, cache: JsonCache | None = None) -> None:
        raw: Fetch = fetch or urllib_fetch
        self._fetch: Fetch = CachedFetch(raw, cache) if cache else raw

    def _get(self, path: str, **params: Any) -> Any:
        url = f"{self.BASE}{path}" + (f"?{urlencode(params)}" if params else "")
        return self._fetch(url, {})

    def search_series(self, query: str) -> list[SearchResult]:
        out = []
        for row in _items(self._get("/search/shows", q=query)):
            show = row.get("show")
            if not isinstance(show, dict) or "id" not in show:
                continue
            out.append(SearchResult(
                "tvmaze", ResultKind.SERIES, int(show["id"]), show.get("name") or "",
                _year(show.get("premiered")), show.get("name") or "",
                show.get("summary") or "", float(show.get("weight") or 0),
            ))
        return out

    def lookup(self, imdb: str | None = None, tvdb: int | str | None = None) -> SearchResult | None:
        """Busca la serie por identificador externo exacto (más fiable que el nombre)."""
        params = {"imdb": imdb} if imdb else {"thetvdb": tvdb} if tvdb else None
        if params is None:
            return None
        try:
            show = self._get("/lookup/shows", **params)
        except NotFound:
            return None
        if not isinstance(show, dict) or "id" not in show:
            return None
        return SearchResult("tvmaze", ResultKind.SERIES, int(show["id"]), show.get("name") or "",
                            _year(show.get("premiered")), show.get("name") or "",
                            show.get("summary") or "", float(show.get("weight") or 0))

    def external_ids(self, ident: int) -> dict:
        try:
            show = self._get(f"/shows/{int(ident)}")
        except NotFound:
            return {}
        ext = show.get("externals") if isinstance(show, dict) else None
        if not isinstance(ext, dict):
            return {}
        return {"imdb_id": ext.get("imdb"), "tvdb_id": ext.get("thetvdb")}

    def get_by_id(self, ident: int) -> SearchResult | None:
        try:
            show = self._get(f"/shows/{int(ident)}")
        except NotFound:
            return None
        if not isinstance(show, dict) or "id" not in show:
            return None
        return SearchResult("tvmaze", ResultKind.SERIES, int(show["id"]), show.get("name") or "",
                            _year(show.get("premiered")), show.get("name") or "",
                            show.get("summary") or "", float(show.get("weight") or 0))

    def list_seasons(self, series_id: int) -> list[int]:
        try:
            data = self._get(f"/shows/{series_id}/episodes")
        except NotFound:
            return []
        return sorted({int(e["season"]) for e in _items(data)
                       if e.get("season") is not None and e.get("number") is not None})

    def get_season(self, series_id: int, season: int) -> list[EpisodeInfo]:
        try:
            data = self._get(f"/shows/{series_id}/episodes")
        except NotFound:
            return []
        return [
            EpisodeInfo(int(e["season"]), int(e["number"]), e.get("name") or "", e.get("airdate") or "",
                        "tvmaze", is_placeholder(e.get("name") or ""))
            for e in _items(data)
            if e.get("season") == season and e.get("number") is not None
        ]


# --------------------------------------------------------------------------- #
# OMDb: datos de IMDb con una clave gratuita (títulos en inglés)
# --------------------------------------------------------------------------- #
class OMDbClient:
    """IMDb no tiene API pública gratuita; OMDb (omdbapi.com) sirve sus datos con una clave gratuita
    (1.000 peticiones al día, uso personal)."""

    BASE = "https://www.omdbapi.com/"
    _EMPTY = ("not found", "too many results", "incorrect imdb id")

    def __init__(self, api_key: str, fetch: Fetch | None = None, cache: JsonCache | None = None) -> None:
        self._key = api_key.strip()
        self._raw_fetch: Fetch = fetch or urllib_fetch
        self._fetch: Fetch = CachedFetch(self._raw_fetch, cache) if cache else self._raw_fetch

    def _url(self, **params: Any) -> str:
        return f"{self.BASE}?{urlencode({'apikey': self._key, **params})}"

    @classmethod
    def _check(cls, data: Any) -> dict[str, Any]:
        """Convierte las respuestas «Response: False» en excepciones (o en datos vacíos)."""
        if not isinstance(data, dict):
            raise ProviderError("Respuesta no válida del servidor")
        if str(data.get("Response", "True")).lower() == "false":
            error = str(data.get("Error", ""))
            low = error.lower()
            if "invalid api key" in low or "no api key" in low:
                raise InvalidApiKey("OMDb rechazó la clave de API")
            if "limit" in low:
                raise ProviderError("Se agotó el límite diario de peticiones de OMDb")
            if any(token in low for token in cls._EMPTY):
                return {}
            raise ProviderError(f"OMDb: {error or 'error desconocido'}")
        return data

    def validate_key(self) -> bool:
        """True si OMDb acepta la clave. Lanza ProviderError si no hay conexión."""
        try:
            self._check(self._raw_fetch(self._url(i="tt0111161"), {}))
        except InvalidApiKey:
            return False
        return True

    def _search(self, query: str, kind: ResultKind) -> list[SearchResult]:
        data = self._check(self._fetch(self._url(s=query, type=kind.value), {}))
        out = []
        for r in _items(data, "Search"):
            ident = str(r.get("imdbID") or "")
            if not ident.startswith("tt"):
                continue
            title = r.get("Title") or ""
            out.append(SearchResult("omdb", kind, ident, title, _year(r.get("Year")), title))
        return out

    def get_by_id(self, imdb_id: str) -> SearchResult | None:
        data = self._check(self._fetch(self._url(i=imdb_id), {}))
        kind = {"series": ResultKind.SERIES, "movie": ResultKind.MOVIE}.get(str(data.get("Type", "")).lower())
        if not data or kind is None:
            return None
        title = data.get("Title") or ""
        return SearchResult("omdb", kind, str(data.get("imdbID") or imdb_id), title, _year(data.get("Year")), title)

    def search_series(self, query: str) -> list[SearchResult]:
        return self._search(query, ResultKind.SERIES)

    def search_movies(self, query: str) -> list[SearchResult]:
        return self._search(query, ResultKind.MOVIE)

    def list_seasons(self, series_id: int | str) -> list[int]:
        data = self._check(self._fetch(self._url(i=series_id), {}))
        total = str(data.get("totalSeasons") or "")
        return list(range(1, int(total) + 1)) if total.isdigit() else []

    def get_season(self, series_id: int | str, season: int) -> list[EpisodeInfo]:
        data = self._check(self._fetch(self._url(i=series_id, Season=season), {}))
        out = []
        for e in _items(data, "Episodes"):
            number = str(e.get("Episode", ""))
            title = e.get("Title") or ""
            if number.isdigit() and title and title != "N/A":
                out.append(EpisodeInfo(season, int(number), title, e.get("Released") or "", "omdb", is_placeholder(title)))
        return out
