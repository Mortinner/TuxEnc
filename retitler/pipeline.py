"""Lógica compartida por la terminal y la interfaz: de un archivo a su nombre nuevo.

Un ``Resolution`` guarda lo que se sabe de un archivo (qué dedujo el analizador, qué
coincidencias hay, cuál está elegida y los títulos de episodio). El nombre nuevo se calcula
aparte con ``new_name(settings)``, así que cambiar las plantillas no obliga a buscar otra vez.
"""
from __future__ import annotations

import os
import threading
import time

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from .config import Settings
from .formatter import NameContext, TemplateError, initial_of, render
from .matching import normalize
from .parser import (SUBTITLE_EXTS, VIDEO_EXTS, MediaKind, ParsedName, is_media_file, numbered_episode,
                     parse_path, split_extension, trailing_number)
from .log import log
from .providers import ENGLISH_SOURCES, SOURCE_NAMES, ProviderError, ResultKind, SearchResult
from .search import SearchResponse, Searcher, pick_best

__all__ = ["Resolution", "analyze", "choose", "collect_media", "companions", "search_for"]


@dataclass(frozen=True)
class Resolution:
    path: Path
    parsed: ParsedName
    searched: bool = False                       # False mientras se espera la búsqueda
    candidates: tuple[SearchResult, ...] = ()    # coincidencias, de mejor a peor
    chosen: SearchResult | None = None
    titles: tuple[str, ...] = ()                 # títulos de episodio de la coincidencia elegida
    title_sources: tuple[str, ...] = ()          # de dónde sale cada título ("tmdb", "tmdb-en", "tvmaze")
    provisional: bool = False                    # algún título es un marcador («Episodio 9»)
    manual: bool = False                         # la coincidencia la eligió el usuario a mano
    error: str = ""                              # por qué no hay nombre (red, carpeta, no es vídeo...)
    warnings: tuple[str, ...] = ()               # avisos de los proveedores

    def new_name(self, settings: Settings, *, resolution: str = "",
                 extension: str | None = None) -> tuple[str | None, str]:
        """(nombre nuevo o None, nota para mostrar al usuario).

        ``resolution`` rellena {resolution}; ``extension`` sustituye a la del archivo original
        (al convertir, el contenedor puede cambiar).
        """
        ext = self.parsed.extension if extension is None else extension
        if self.error:
            return None, self.error
        match = self.chosen
        if match is None:
            if not self.candidates and self.warnings:      # no es que no exista: no se pudo preguntar
                return None, "no se pudo buscar: " + " ".join(self.warnings)
            return None, "sin coincidencia clara: búscala a mano"
        note = f"{match.label} [{match.provider_name}]"
        if match.kind is ResultKind.SERIES:
            season, episodes = self.parsed.season, self.parsed.episodes
            if season is None or not episodes:
                return None, f"{note}: no se detectó temporada/episodio"
            if not all(self.titles) or not self.titles:
                note += " · sin título de episodio en el proveedor"
            elif self.provisional:
                note += " · título provisional (aún sin publicar)"
            extra = sorted({SOURCE_NAMES.get(src, src) for src in self.title_sources if src and src != match.provider})
            if extra:
                note += " · títulos de " + " y ".join(extra)
            ctx = NameContext(match.title, season, episodes, [t for t in self.titles if t], match.year,
                              resolution, initial_of(match.title, settings.skip_articles))
            template = settings.series_template
        else:
            ctx = NameContext(title=match.title, year=match.year, resolution=resolution,
                              initial=initial_of(match.title, settings.skip_articles))
            template = settings.movie_template
        try:
            return render(template, ctx, ext), note
        except TemplateError as exc:
            return None, f"plantilla: {exc}"


def analyze(path: str | Path) -> Resolution:
    """Análisis sin internet (instantáneo; como mucho lista la carpeta una vez cada 30 s)."""
    p = Path(path)
    parsed = parse_path(p)
    if parsed.kind is not MediaKind.EPISODE and trailing_number(p.name):
        # «Dinosaucers 01.mp4»: capítulo solo si la carpeta muestra que es una serie
        numbered = numbered_episode(p, _names_in(p.parent))
        if numbered is not None:
            log.info("%s: capítulo %s por el número del nombre (%s)", p.name,
                     f"T{numbered.season}E{numbered.episodes[0]:02}" if not numbered.absolute
                     else f"{numbered.episodes[0]} contando desde el primero", numbered.title)
            parsed = numbered
    return Resolution(p, parsed)


_NAMES_CACHE: dict[str, tuple[float, list[str]]] = {}


def _names_in(folder: Path) -> list[str]:
    """Nombres de una carpeta, listándola una sola vez cada 30 s (como los subtítulos)."""
    key = str(folder)
    now = time.monotonic()
    with _SUBS_LOCK:
        hit = _NAMES_CACHE.get(key)
        if hit and now - hit[0] < _SUBS_TTL:
            return hit[1]
    try:
        with os.scandir(folder) as it:
            names = [e.name for e in it]
    except OSError:
        names = []
    with _SUBS_LOCK:
        _NAMES_CACHE[key] = (now, names)
    return names


def _absolute_to_season(res: Resolution, searcher: Searcher, memo: dict | None = None) -> Resolution:
    """«Serie 37» con numeración absoluta → temporada y capítulo reales, con la lista del buscador.

    Si la temporada 1 tiene al menos 37 capítulos, se queda en T1E37. Si no, se cuentan los de
    cada temporada (sin especiales) hasta llegar al 37.
    """
    p, match = res.parsed, res.chosen
    if not p.absolute or match is None or match.kind is not ResultKind.SERIES or not p.episodes:
        return res
    n = p.episodes[0]
    memo = {} if memo is None else memo
    total = 0
    try:
        key = ("seasons", match.provider, match.id)
        seasons = memo.get(key)
        if seasons is None:
            seasons = memo[key] = [x for x in searcher.seasons(match) if x > 0]
        for season in sorted(seasons):
            key = ("count", match.provider, match.id, season)
            count = memo.get(key)
            if count is None:
                count = memo[key] = len(searcher.season_episodes(match, season))
            if n <= total + count:
                if (season, n - total) != (p.season, n):
                    log.info("%s: capítulo %d contando desde el primero = T%dE%02d de %s", res.path.name,
                             n, season, n - total, match.label)
                return replace(res, parsed=replace(p, season=season, episodes=(n - total,)))
            total += count
    except ProviderError as exc:
        log.warning("%s: no se pudo convertir la numeración absoluta: %s", res.path.name, exc)
    return res


def _with_titles(res: Resolution, searcher: Searcher) -> Resolution:
    match = res.chosen
    season, episodes = res.parsed.season, res.parsed.episodes
    if match is None or match.kind is not ResultKind.SERIES or season is None or not episodes:
        return replace(res, titles=(), title_sources=(), provisional=False, error="")
    try:
        infos = searcher.episode_titles_detailed(match, season, episodes)
        return replace(res, titles=tuple(e.title for e in infos), title_sources=tuple(e.source for e in infos),
                       provisional=any(e.provisional for e in infos), error="")
    except ProviderError as exc:
        log.warning("%s: error al obtener episodios de %s: %s", res.path.name, match.label, exc)
        return replace(res, titles=(), title_sources=(), provisional=False, error=f"{match.label}: error de red ({exc})")


def search_for(res: Resolution, searcher: Searcher,
               memo: dict[tuple, SearchResponse] | None = None) -> Resolution:
    """Busca la mejor coincidencia y los títulos de episodio (usa internet)."""
    if res.path.is_dir():
        return replace(res, searched=True, error="es una carpeta")
    if not is_media_file(res.path.name):
        return replace(res, searched=True, error="no es un vídeo ni un subtítulo")
    memo = {} if memo is None else memo
    key = (res.parsed.title.casefold(), res.parsed.year, res.parsed.kind)
    response = memo.get(key)
    if response is None:
        response = memo[key] = searcher.search_parsed(res.parsed)
    out = replace(res, searched=True, candidates=tuple(response.results[:10]),
                  warnings=tuple(response.warnings), chosen=pick_best(response.results), error="", manual=False)
    log.info("%s → %s", res.path.name, f"{out.chosen.label} [{out.chosen.provider_name}]" if out.chosen else "sin coincidencia clara")
    return _with_titles(_absolute_to_season(out, searcher, memo), searcher)


def prefer_file_title(res: Resolution, settings: Settings) -> Resolution:
    """Si el capítulo solo tiene título en inglés (o ninguno) y el nombre del archivo ya trae uno
    («Serie - S01E01 - La mujer alemana»), se queda el del archivo. Solo con los buscadores en español."""
    if not (settings.keep_file_title and settings.language == "es"):
        return res
    ft = res.parsed.episode_title
    m = res.chosen
    if not ft or m is None or m.kind is not ResultKind.SERIES or len(res.parsed.episodes) != 1 or len(res.titles) != 1:
        return res
    src = res.title_sources[0] if res.title_sources else ""
    if res.titles[0] and not res.provisional and src not in ENGLISH_SOURCES:
        return res
    log.info("%s: se conserva el título del archivo %r (el proveedor da %r, fuente %s)",
             res.path.name, ft, res.titles[0], src or "ninguna")
    return replace(res, titles=(ft,), title_sources=("archivo",), provisional=False)


def choose(res: Resolution, match: SearchResult, searcher: Searcher,
           season: int | None = None, episodes: tuple[int, ...] | None = None,
           memo: dict | None = None) -> Resolution:
    """El usuario elige a mano una coincidencia (y, en series, opcionalmente el capítulo)."""
    if season is not None and episodes:
        same = season == res.parsed.season and tuple(episodes) == tuple(res.parsed.episodes)
        res = replace(res, parsed=replace(res.parsed, kind=MediaKind.EPISODE, season=season,
                                          episodes=tuple(episodes), absolute=False,
                                          episode_title=res.parsed.episode_title if same else ""))
    out = replace(res, searched=True, chosen=match, error="", manual=True)
    return _with_titles(_absolute_to_season(out, searcher, memo), searcher)


def _is_video(p: Path) -> bool:
    return split_extension(p.name)[1].lower() in VIDEO_EXTS


_SUBS_CACHE: dict[str, tuple[float, list[Path]]] = {}
_SUBS_TTL = 30.0
_SUBS_LOCK = threading.Lock()


def _subtitles_in(folder: Path) -> list[Path]:
    """Los subtítulos de una carpeta, listándola **una sola vez** cada 30 s.

    Antes, para cada vídeo se recorría la carpeta entera preguntando al disco por cada archivo:
    con 229 capítulos en un NAS eran ~52.000 consultas (minutos). Ahora se lista con scandir
    (el tipo viene en el propio listado, sin consulta extra) y solo se miran los subtítulos.
    """
    key = str(folder)
    now = time.monotonic()
    with _SUBS_LOCK:
        hit = _SUBS_CACHE.get(key)
        if hit and now - hit[0] < _SUBS_TTL:
            return hit[1]
    subs: list[Path] = []
    try:
        with os.scandir(folder) as it:
            for entry in it:
                ext = split_extension(entry.name)[1]
                if "." + ext.rsplit(".", 1)[-1].lower() not in SUBTITLE_EXTS:
                    continue
                try:
                    if entry.is_file():
                        subs.append(Path(entry.path))
                except OSError:
                    continue
    except OSError:
        return []
    subs.sort(key=lambda c: c.name.casefold())
    with _SUBS_LOCK:
        _SUBS_CACHE[key] = (now, subs)
    return subs


def companions(video: Path) -> list[Path]:
    """Subtítulos que acompañan a un vídeo en su carpeta: mismo nombre base («Serie.S01E01.es.srt»)
    o el mismo episodio de la misma serie («Serie S01E01 Spanish.srt» junto a «Serie.S01E01.1080p.mkv»)."""
    stem = split_extension(video.name)[0]
    me = parse_path(video)
    out = []
    for sib in _subtitles_in(video.parent):
        if sib == video:
            continue
        sub_stem = split_extension(sib.name)[0]
        if sub_stem == stem:
            out.append(sib)
            continue
        other = parse_path(sib)
        if (me.season is not None and me.episodes and (other.season, other.episodes) == (me.season, me.episodes)
                and normalize(other.title) == normalize(me.title)):
            out.append(sib)
    return out


def collect_media(paths: Iterable[str | Path], with_companions: bool = True) -> tuple[list[Path], int]:
    """Expande carpetas (recursivo) y filtra: devuelve (vídeos/subtítulos sin repetir, nº ignorados).

    Con ``with_companions`` cada vídeo arrastra sus subtítulos, para que no se queden con el nombre viejo.
    """
    found: list[Path] = []
    seen: set[Path] = set()
    ignored = 0

    def add(p: Path) -> None:
        nonlocal ignored
        if p.name.endswith(".retitler-tmp") or not is_media_file(p.name):
            ignored += 1
        elif p not in seen:
            seen.add(p)
            found.append(p)

    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for child in sorted(p.rglob("*"), key=lambda c: str(c).casefold()):
                if child.is_file():
                    add(child)
        elif p.is_file():
            add(p)
            if with_companions and _is_video(p):
                for sub in companions(p):
                    if sub not in seen:
                        seen.add(sub)
                        found.append(sub)
        else:
            ignored += 1
    return found, ignored
