"""Análisis de nombres de archivo: extrae título, año, temporada y episodio.

Funciones principales:
    parse_filename(nombre)  -> ParsedName   (solo mira el nombre del archivo)
    parse_path(ruta)        -> ParsedName   (además usa carpetas "Temporada N" / nombre de la serie)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePath

__all__ = [
    "MediaKind",
    "ParsedName",
    "clean_title",
    "is_media_file",
    "parse_filename",
    "parse_path",
    "split_extension",
]


class MediaKind(str, Enum):
    EPISODE = "episode"
    MOVIE = "movie"
    UNKNOWN = "unknown"  # no hay pistas suficientes: la búsqueda debe probar series y películas


@dataclass(frozen=True)
class ParsedName:
    original: str
    kind: MediaKind
    title: str = ""
    year: int | None = None
    season: int | None = None
    episodes: tuple[int, ...] = ()
    extension: str = ""
    episode_title: str = ""      # el que trae el nombre: «Serie - S01E01 - La mujer alemana»

    @property
    def is_multi_episode(self) -> bool:
        return len(self.episodes) > 1


# --------------------------------------------------------------------------- #
# Extensiones
# --------------------------------------------------------------------------- #
VIDEO_EXTS = frozenset({
    ".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv", ".mpg", ".mpeg",
    ".ts", ".m2ts", ".webm", ".flv", ".ogm", ".divx",
    # además, los que acepta TuxEnc para convertir
    ".mts", ".vob", ".ogv", ".3gp", ".asf", ".f4v", ".rmvb",
})
SUBTITLE_EXTS = frozenset({".srt", ".ass", ".ssa", ".sub", ".idx", ".vtt"})
OTHER_EXTS = frozenset({".nfo", ".jpg", ".jpeg", ".png"})
KNOWN_EXTS = VIDEO_EXTS | SUBTITLE_EXTS | OTHER_EXTS

# Etiqueta de idioma que puede ir antes de la extensión de un subtítulo: ".es.srt"
_LANG_TAG = re.compile(r"^\.(?:[a-z]{2,3}|[a-z]{2}-[a-z]{2,4}|forced|sdh|default)$", re.I)


def split_extension(name: str) -> tuple[str, str]:
    """Separa (nombre_sin_extensión, extensión).

    Solo se reconocen extensiones de medios conocidas, para que un nombre como
    ``Serie.S01E02`` (sin extensión) no pierda su final. En subtítulos se conserva
    la etiqueta de idioma: ``Peli.es.srt`` -> (``Peli``, ``.es.srt``).
    """
    base, dot, last = name.rpartition(".")
    if not dot or not base:
        return name, ""
    ext = "." + last
    if ext.lower() not in KNOWN_EXTS:
        return name, ""
    if ext.lower() in SUBTITLE_EXTS:
        # Hasta dos etiquetas: ".es.srt", ".spa.forced.srt", ".en.sdh.srt"
        for _ in range(2):
            base2, dot2, tag = base.rpartition(".")
            if not (dot2 and base2):
                break
            if "." + tag.lower() in VIDEO_EXTS:      # "Serie.mkv.srt": el .mkv sobra, no es un idioma
                base = base2
                break
            if not _LANG_TAG.match("." + tag):
                break
            base, ext = base2, "." + tag + ext
    return base, ext


def is_media_file(name: str) -> bool:
    """True si es un vídeo o un subtítulo (lo único que Retitler renombra)."""
    ext = split_extension(name.replace("\\", "/").rsplit("/", 1)[-1])[1]
    return bool(ext) and "." + ext.rsplit(".", 1)[-1].lower() in (VIDEO_EXTS | SUBTITLE_EXTS)


# --------------------------------------------------------------------------- #
# Expresiones regulares
# --------------------------------------------------------------------------- #
_B = r"(?<![A-Za-z0-9])"  # no hay letra/dígito justo antes
_E = r"(?![A-Za-z0-9])"   # no hay letra/dígito justo después

# S01E02, S01E02E03, S01E02-E04, S01E02-03
_SXXEYY = re.compile(
    _B + r"S(\d{1,2})[ ._-]?E(\d{1,3})"
    r"((?:[ ._-]?E\d{1,3}|-\d{2}(?![0-9pPiIkK]))*)" + _E,
    re.I,
)
# 1x02
_NXM = re.compile(_B + r"(\d{1,2})x(\d{2,3})" + _E, re.I)
# Season 1 Episode 2 / Temporada 1 Capítulo 2
_LONG = re.compile(
    _B + r"(?:Season|Temporada|Temp|Series)[ ._]?(\d{1,2})[ ._,-]*"
    r"(?:Episode|Episodio|Ep|Cap[ií]tulo|Cap)[ ._]?(\d{1,3})" + _E,
    re.I,
)
# Episodio 1 Temporada 6 / Episode 3 Season 2 / Capítulo 5 de la temporada 2 (orden inverso)
_LONG_REV = re.compile(
    _B + r"(?:Episode|Episodio|Ep|Cap[ií]tulo|Cap)[ ._]?(\d{1,3})[ ._,-]*"
    r"(?:(?:de|of)[ ._]+(?:la[ ._]+|the[ ._]+)?)?"
    r"(?:Season|Temporada|Temp)[ ._]?(\d{1,2})" + _E,
    re.I,
)
# T6 E1 / T06E01 / T6xE1 (abreviatura española de temporada)
_TXEY = re.compile(_B + r"T(\d{1,2})[ ._-]?x?[ ._-]?E(\d{1,3})" + _E, re.I)
# [Cap.102] -> temporada 1, episodio 02 (estilo habitual de releases en español)
_CAP = re.compile(r"(?<![A-Za-z])\[?Cap(?:[ií]tulo)?[ ._]?(\d{1,2})(\d{2})(?![0-9])\]?", re.I)

_EPISODE_PATTERNS = (_SXXEYY, _NXM, _LONG, _LONG_REV, _TXEY, _CAP)

_YEAR = re.compile(r"(?<![0-9])(19\d{2}|20[0-3]\d)(?![0-9])")
_TRAILING_YEAR = re.compile(r"\s*[(\[]?(?<![0-9])(19\d{2}|20[0-3]\d)[)\]]?$")

# Marcas de calidad/códec/origen que indican "aquí acaba el título".
# Se evitan a propósito palabras ambiguas (Spanish, Extended, Dual...) porque
# pueden formar parte de un título real.
_JUNK_TOKENS = [
    r"(?:480|540|576|720|1080|1440|2160|4320)[pi]",
    r"4k", r"uhd",
    r"[xh][ ._]?26[45]", r"hevc", r"avc", r"xvid", r"divx", r"av1",
    r"web[ ._-]?(?:dl|rip)", r"blu[ ._-]?ray", r"bd[ ._-]?rip", r"br[ ._-]?rip",
    r"dvd[ ._-]?(?:rip|scr|r)", r"hd[ ._-]?(?:tv|rip|cam)", r"pdtv", r"remux",
    r"amzn", r"nf", r"dsnp", r"hmax", r"atvp", r"pcok",
    r"hdr10?\+?", r"dolby[ ._]?vision", r"10[ ._-]?bit",
    r"(?:dd|ddp|eac3|ac3|aac|dts|truehd|atmos|flac)(?:[ ._]?[257][ ._]?[01])?",
]
_JUNK = re.compile(_B + "(?:" + "|".join(_JUNK_TOKENS) + ")" + _E, re.I)

_ACRONYM = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]\.){2,}")
_SEASON_TAG = re.compile(_B + r"(?:S\d{1,2}|Season[ ._]?\d+|Temporada[ ._]?\d+)" + _E, re.I)
# "La Casa de Papel - Temporada 3 [Cap.301]": la temporada repetida no es parte del título
_TRAILING_SEASON = re.compile(r"[\s\-–—:,]*(?:(?:Temporada|Temp|Season|Series)[ ._]?\d{1,2}|T\d{1,2}|S\d{1,2})\s*$", re.I)
_SEASON_DIR = re.compile(r"^(?:season|temporada|temp|series|s)[ ._-]?(\d{1,2})$", re.I)
_LEADING_EP = re.compile(r"^(?:e|ep|episode|episodio|cap)?[ ._]?(\d{1,3})(?:[ ._-]+|$)", re.I)


# --------------------------------------------------------------------------- #
# Utilidades de limpieza
# --------------------------------------------------------------------------- #
def clean_title(raw: str) -> str:
    """Convierte ``Mi.Serie_Genial.[HDTV]`` en ``Mi Serie Genial``.

    Conserva acrónimos como ``S.H.I.E.L.D.`` y los guiones internos (``Spider-Man``).
    """
    s = re.sub(r"^\s*(?:\[[^\]]*\]\s*)+", "", raw)  # [GrupoFansub] inicial
    s = re.sub(r"\[[^\]]*\]", " ", s)               # otros [etiquetas]
    s = _ACRONYM.sub(lambda m: m.group(0).replace(".", "\0"), s)
    s = s.replace("_", " ").replace(".", " ").replace("\0", ".")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[\s\-–—:;,(\[]+$", "", s)
    s = re.sub(r"^[\s\-–—]+", "", s)
    return s.strip()


def _split_trailing_year(title: str) -> tuple[str, int | None]:
    m = _TRAILING_YEAR.search(title)
    if m and title[: m.start()].strip():
        return title[: m.start()].strip(), int(m.group(1))
    return title, None


def _title_from_dirname(dirname: str) -> tuple[str, int | None]:
    """Título (y año) a partir del nombre de la carpeta de la serie."""
    stops = [m.start() for m in (_JUNK.search(dirname), _SEASON_TAG.search(dirname)) if m]
    raw = dirname[: min(stops)] if stops else dirname
    return _split_trailing_year(clean_title(raw))


def _season_from_match(m: re.Match[str]) -> int:
    return int(m.group(2) if m.re is _LONG_REV else m.group(1))


def _episodes_from_match(m: re.Match[str]) -> tuple[int, ...]:
    if m.re is _LONG_REV:
        return (int(m.group(1)),)
    episodes = [int(m.group(2))]
    if m.re is _SXXEYY and m.group(3):
        for sign, num in re.findall(r"(-?)[ ._]?(?:E)?(\d{1,3})", m.group(3), flags=re.I):
            n = int(num)
            # "E05-E07" o "E05-07" significa rango; "E05E06" es una lista.
            if sign == "-" and 0 < n - episodes[-1] <= 12:
                episodes.extend(range(episodes[-1] + 1, n + 1))
            else:
                episodes.append(n)
    return tuple(episodes)


_EP_PLACEHOLDER = re.compile(r"^(?:episod(?:e|io)|cap[ií]tulo|cap|ep|chapter)\.?\s*#?\s*\d+$|^\d+$", re.I)


def _episode_title_after(rest: str) -> str:
    """Título del capítulo tras el marcador, solo en el estilo «… S01E01 - Título [- …]».

    Los nombres de release con puntos («S01E01.1080p.WEB») no se tocan: ahí no hay título fiable.
    """
    m = re.match(r"\s*[-–—]\s+(.+)$", rest)
    if not m:
        return ""
    t = re.split(r"\s+[-–—]\s+|\s*[\[(]", m.group(1))[0]
    junk = _JUNK.search(t)
    if junk:
        t = t[: junk.start()]
    t = t.strip(" .-_–—")
    if not t or _EP_PLACEHOLDER.match(t):
        return ""
    return t


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #
def parse_filename(name: str) -> ParsedName:
    """Analiza solo el nombre de un archivo (sin mirar carpetas)."""
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    stem, ext = split_extension(name)

    for pattern in _EPISODE_PATTERNS:
        m = pattern.search(stem)
        if m:
            raw_title = clean_title(stem[: m.start()])
            stripped = _TRAILING_SEASON.sub("", raw_title).strip()
            title, year = _split_trailing_year(stripped or raw_title)
            return ParsedName(
                original=name,
                kind=MediaKind.EPISODE,
                title=title,
                year=year,
                season=_season_from_match(m),
                episodes=_episodes_from_match(m),
                extension=ext,
                episode_title=_episode_title_after(stem[m.end():]),
            )

    # Sin marcador de episodio: película (si hay año o marcas de calidad) o desconocido.
    junk = _JUNK.search(stem)
    limit = junk.start() if junk else len(stem)
    years = [m for m in _YEAR.finditer(stem) if 0 < m.start() < limit]
    year_m = years[-1] if years else None

    if year_m:
        stop: int | None = year_m.start()
    elif junk:
        stop = junk.start()
    else:
        stop = None

    title = clean_title(stem if stop is None else stem[:stop])
    return ParsedName(
        original=name,
        kind=MediaKind.MOVIE if stop is not None else MediaKind.UNKNOWN,
        title=title,
        year=int(year_m.group(1)) if year_m else None,
        extension=ext,
    )


def parse_path(path: str | PurePath) -> ParsedName:
    """Como parse_filename, pero apoyándose en las carpetas cuando el nombre no basta.

    Casos que resuelve:
      * ``Serie/Temporada 2/E05.mkv`` o ``.../05 - Título.mkv``
      * ``Serie (2019)/S01E01.mkv``  (el título sale de la carpeta)
    """
    p = PurePath(str(path).replace("\\", "/"))
    parsed = parse_filename(p.name)
    season_dir = _SEASON_DIR.match(p.parent.name)
    series_dir = p.parent.parent.name if season_dir else p.parent.name

    if parsed.kind is MediaKind.EPISODE:
        if parsed.title or not series_dir:
            return parsed
        title, year = _title_from_dirname(series_dir)
        return _replace(parsed, title=title, year=parsed.year or year)

    if season_dir:
        stem, _ = split_extension(p.name)
        m = _LEADING_EP.match(stem)
        if m:
            title, year = _title_from_dirname(series_dir) if series_dir else ("", None)
            return ParsedName(
                original=parsed.original,
                kind=MediaKind.EPISODE,
                title=title,
                year=year,
                season=int(season_dir.group(1)),
                episodes=(int(m.group(1)),),
                extension=parsed.extension,
            )
    return parsed


def _replace(parsed: ParsedName, **changes: object) -> ParsedName:
    from dataclasses import replace

    return replace(parsed, **changes)
