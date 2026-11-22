"""Análisis de nombres de archivo: extrae título, año, temporada y episodio.

Funciones principales:
    parse_filename(nombre)  -> ParsedName   (solo mira el nombre del archivo)
    parse_path(ruta)        -> ParsedName   (además usa carpetas "Temporada N" / nombre de la serie)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
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
    absolute: bool = False       # «Serie 37»: capítulo 37 contando desde el primero (sin temporada)

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

# S01E02, S01E02E03, S01E02-E04, S01E02-03, S001E02 (temporada con tres cifras y cero delante),
# S01E01x02 (capítulo doble: 1 y 2) y S01E01x01 (el número repetido: un capítulo)
_SXXEYY = re.compile(
    _B + r"S(0\d{2}|\d{1,2})[ ._-]?E(\d{1,3})"
    r"((?:[ ._-]?E\d{1,3}|-\d{2}(?![0-9pPiIkK])|x\d{1,3})*)" + _E,
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
_SEASON_DIR = re.compile(r"^(?:season|temporada|temp|series|s)[ ._-]?(0\d{2}|\d{1,2})$", re.I)
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
        for sign, num in re.findall(r"([-x]?)[ ._]?(?:E)?(\d{1,3})", m.group(3), flags=re.I):
            n = int(num)
            if sign.lower() == "x" and n == episodes[-1]:
                continue                                   # «E01x01»: el mismo capítulo
            # "E05-E07", "E05-07" o "E05x07" significa rango; "E05E06" es una lista.
            if sign.lower() in ("-", "x") and 0 < n - episodes[-1] <= 12:
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


def is_season_folder(name: str) -> bool:
    """«Season 01», «Temporada 2», «S03»…"""
    return bool(_SEASON_DIR.match(name))


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
        # Dentro de «Season 01» nunca es una película (1.3.5): es un capítulo que no se ha sabido
        # leer. Se busca la serie y queda «sin capítulo», para elegirlo a mano.
        title, year = _title_from_dirname(series_dir) if series_dir else ("", None)
        return ParsedName(
            original=parsed.original,
            kind=MediaKind.EPISODE,
            title=title or parsed.title,
            year=year or parsed.year,
            season=int(season_dir.group(1)),
            episodes=(),
            extension=parsed.extension,
        )
    return parsed


# --------------------------------------------------------------------------- #
# Capítulos numerados solo con un número: «Dinosaucers 01.mp4»
# --------------------------------------------------------------------------- #
# Título, separador, marca opcional (Ep, Episodio, Cap, E, #) y 1-3 cifras al final del nombre
_TRAILING_NUM = re.compile(
    r"^(?P<title>.*?[^\W\d_].*?)(?:[ ._]*[-–—][ ._]*|[ ._]+)"
    r"(?:(?:ep(?:isodio|isode)?|cap(?:[ií]tulo)?|e|#)[ ._]?)?(?P<num>\d{1,3})$", re.I)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def trailing_number(name: str) -> tuple[str, str] | None:
    """(título, número tal cual) si el nombre acaba en un número suelto: «Dinosaucers 01» → («Dinosaucers», «01»).

    Se quitan antes las [etiquetas] y las marcas de calidad del final. No reconoce años (4 cifras)
    ni números pegados al título («Room101»).
    """
    stem, _ = split_extension(name.replace("\\", "/").rsplit("/", 1)[-1])
    stem = re.sub(r"(?:\s*\[[^\]]*\])+\s*$", "", stem)
    junk = _JUNK.search(stem)
    if junk and junk.start() > 0:
        stem = stem[: junk.start()]
    m = _TRAILING_NUM.match(stem.strip(" ._-"))
    if not m:
        return None
    title = clean_title(m.group("title"))
    return (title, m.group("num")) if title else None


def numbered_episode(path: str | PurePath, sibling_names: Iterable[str]) -> ParsedName | None:
    """«Serie 01.mp4» como capítulo, solo si hay indicios claros de que es una serie.

    Indicios (para no confundir películas como «Rocky 2», «Ocean's 11» o «2012»):
      * números con cero delante («01»), o que pasan de una cifra a dos («1»…«12»), y
      * al menos otro archivo en la misma carpeta con el mismo título y otro número, o la carpeta
        se llama como el título (``Dinosaucers/Dinosaucers 05.mp4``).
    Una saga de películas («Rocky 2», «Rocky 3»…) no cumple lo de las cifras.
    Con tres cifras («Serie 101», «Serie 214») es temporada + capítulo si todo el grupo encaja así
    (como «Cap.102»); si no, el número se cuenta desde el primer capítulo (numeración absoluta).
    """
    p = PurePath(str(path).replace("\\", "/"))
    mine = trailing_number(p.name)
    if mine is None:
        return None
    key = _norm(mine[0])
    numbers = {mine[1]}
    for name in sibling_names:
        if name == p.name or split_extension(name)[1].lower() not in VIDEO_EXTS:
            continue
        other = trailing_number(name)
        if other and _norm(other[0]) == key:
            numbers.add(other[1])
    values = {int(n) for n in numbers}
    # «01» con cero delante, o una serie sin ceros que pasa de un dígito a dos («1»…«12»).
    # Así no cuentan «Rocky 2, 3, 4» ni «Ocean's 11, 12, 13».
    three = all(len(x) == 3 for x in numbers) and all(1 <= v % 100 <= 99 for v in values)
    padded = any(len(n) >= 2 and n.startswith("0") for n in numbers) or (
        min(values) < 10 <= max(values)) or (three and len(values) >= 2)
    folder_title = _title_from_dirname(p.parent.name)[0] if p.parent.name else ""
    same_folder = bool(folder_title) and _norm(folder_title) == key
    if not padded or not (len(values) >= 2 or same_folder):
        return None
    title, year = _split_trailing_year(mine[0])
    n = int(mine[1])
    if three:
        season, episodes, absolute = n // 100, (n % 100,), False
    else:
        season, episodes, absolute = 1, (n,), True
    if not episodes[0]:
        return None
    _, ext = split_extension(p.name)
    return ParsedName(original=p.name, kind=MediaKind.EPISODE, title=title, year=year, season=season,
                      episodes=episodes, extension=ext, absolute=absolute)


def _replace(parsed: ParsedName, **changes: object) -> ParsedName:
    from dataclasses import replace

    return replace(parsed, **changes)
