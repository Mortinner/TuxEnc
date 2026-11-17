"""Lógica compartida por la terminal y la interfaz: de un archivo a su nombre nuevo.

Un ``Resolution`` guarda lo que se sabe de un archivo (qué dedujo el analizador, qué
coincidencias hay, cuál está elegida y los títulos de episodio). El nombre nuevo se calcula
aparte con ``new_name(settings)``, así que cambiar las plantillas no obliga a buscar otra vez.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from .config import Settings
from .formatter import NameContext, TemplateError, initial_of, render
from .matching import normalize
from .parser import SUBTITLE_EXTS, VIDEO_EXTS, MediaKind, ParsedName, is_media_file, parse_path, split_extension
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
    """Análisis sin internet (instantáneo)."""
    p = Path(path)
    return Resolution(p, parse_path(p))


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
    return _with_titles(out, searcher)


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
           season: int | None = None, episodes: tuple[int, ...] | None = None) -> Resolution:
    """El usuario elige a mano una coincidencia (y, en series, opcionalmente el capítulo)."""
    if season is not None and episodes:
        same = season == res.parsed.season and tuple(episodes) == tuple(res.parsed.episodes)
        res = replace(res, parsed=replace(res.parsed, kind=MediaKind.EPISODE, season=season,
                                          episodes=tuple(episodes),
                                          episode_title=res.parsed.episode_title if same else ""))
    return _with_titles(replace(res, searched=True, chosen=match, error="", manual=True), searcher)


def _is_video(p: Path) -> bool:
    return split_extension(p.name)[1].lower() in VIDEO_EXTS


def companions(video: Path) -> list[Path]:
    """Subtítulos que acompañan a un vídeo en su carpeta: mismo nombre base («Serie.S01E01.es.srt»)
    o el mismo episodio de la misma serie («Serie S01E01 Spanish.srt» junto a «Serie.S01E01.1080p.mkv»)."""
    stem = split_extension(video.name)[0]
    me = parse_path(video)
    out = []
    try:
        siblings = sorted(video.parent.iterdir(), key=lambda c: c.name.casefold())
    except OSError:
        return []
    for sib in siblings:
        if sib == video or not sib.is_file():
            continue
        sub_stem, ext = split_extension(sib.name)
        if "." + ext.rsplit(".", 1)[-1].lower() not in SUBTITLE_EXTS:
            continue
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
