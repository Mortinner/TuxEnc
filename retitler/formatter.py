"""Motor de formato: convierte una plantilla + datos en un nombre de archivo seguro.

Campos disponibles en las plantillas:
    {series}    nombre de la serie
    {season}    número de temporada
    {episode}   número(s) de episodio (varios: 01-02)
    {title}     título del episodio (series) o de la película
    {year}      año (de la serie o de la película)
    {resolution} resolución estándar del vídeo: 2160p, 1080p, 720p, 480p
    {initial}   inicial del título (para carpetas por letra: B/Babel (2006)...)

Los números admiten formato Python: ``{season:02}`` -> 01.
Un ``/`` en la plantilla crea subcarpetas: ``{series}/Season {season:02}/...``
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from string import Formatter
from typing import Sequence

from .parser import MediaKind, ParsedName

__all__ = [
    "DEFAULT_MOVIE_TEMPLATE",
    "DEFAULT_SERIES_TEMPLATE",
    "NameContext",
    "SAMPLE_MOVIE_CONTEXT",
    "SAMPLE_SERIES_CONTEXT",
    "initial_of",
    "TemplateError",
    "render",
    "sanitize_component",
    "validate_template",
]

DEFAULT_SERIES_TEMPLATE = "{series} - {season}x{episode:02} - {title}"
DEFAULT_MOVIE_TEMPLATE = "{title} ({year})"

MAX_COMPONENT_BYTES = 255  # límite de nombre en BTRFS/ext4/SMB


class TemplateError(ValueError):
    """Plantilla inválida (campo desconocido, llaves sin cerrar, formato incorrecto...)."""


@dataclass
class NameContext:
    series: str = ""
    season: int | None = None
    episodes: Sequence[int] = ()
    title: str | Sequence[str] = ""  # varios títulos (doble episodio) se unen con " & "
    year: int | None = None
    resolution: str = ""             # "1080p"... ("" si no se conoce: «[{resolution}]» desaparece)
    initial: str = ""

    @classmethod
    def from_parsed(cls, parsed: ParsedName, *, title: str | Sequence[str] | None = None) -> "NameContext":
        """Contexto inicial a partir de lo que dedujo el parser.

        Para series, ``title`` es el título del episodio (viene de TMDB/TVmaze);
        para películas se usa por defecto el título detectado.
        """
        if parsed.kind is MediaKind.EPISODE:
            return cls(series=parsed.title, season=parsed.season, episodes=parsed.episodes,
                       title=title or "", year=parsed.year)
        return cls(title=title or parsed.title, year=parsed.year)


SAMPLE_SERIES_CONTEXT = NameContext("Breaking Bad", 1, (1,), "Piloto", 2008, "1080p", "B")
SAMPLE_MOVIE_CONTEXT = NameContext(title="Origen", year=2010, resolution="1080p", initial="O")

_FIELDS = ("series", "season", "episode", "title", "year", "resolution", "initial")
_FIELDS_HELP = "{series} {season} {episode} {title} {year} {resolution} {initial}"

_ARTICLES = frozenset({"the", "a", "an", "el", "la", "los", "las", "lo", "un", "una", "unos", "unas",
                       "le", "les", "il", "der", "die", "das"})


def initial_of(text: str, skip_articles: bool = True) -> str:
    """Letra para carpetas alfabéticas: «Babel» -> B, «The Batman» -> B (o T), «Ágora» -> A, «300» -> 0-9."""
    words = (text or "").split()
    if skip_articles and len(words) > 1 and words[0].casefold().strip("'’") in _ARTICLES:
        words = words[1:]
    rest = " ".join(words)
    if skip_articles and len(rest) > 2 and rest[:2].casefold() in ("l'", "l’"):
        rest = rest[2:]
    for ch in rest:
        if ch.isdigit():
            return "0-9"
        if ch.isalpha():
            base = unicodedata.normalize("NFD", ch)[0]
            return base.upper() if base.isascii() else ch.upper()
    return "#"


# --------------------------------------------------------------------------- #
# Saneado de nombres
# --------------------------------------------------------------------------- #
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_component(text: str, *, windows_safe: bool = True) -> str:
    """Quita lo que no puede ir en un nombre de archivo.

    ``/`` siempre se sustituye. Con ``windows_safe`` (por defecto) se evitan además
    los caracteres que rompen en Samba/CIFS o Windows: ``\\ : " < > | * ?``.
    """
    s = unicodedata.normalize("NFC", text)
    s = _CTRL.sub("", s)
    s = s.replace("/", "-")
    if windows_safe:
        s = s.replace("\\", "-")
        s = re.sub(r":\s+", " - ", s)  # "Star Trek: Voyager" -> "Star Trek - Voyager"
        s = s.replace(":", "-")
        s = s.replace('"', "'")
        s = re.sub(r"[<>|*?]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _tidy_component(c: str) -> str:
    """Limpia restos de campos vacíos: paréntesis vacíos, ' - - ', separadores colgando."""
    c = re.sub(r"\(\s*\)|\[\s*\]|\{\s*\}", "", c)
    c = re.sub(r"\s+", " ", c)
    c = re.sub(r"(?:\s+-){2,}(?=\s)", " -", c)
    c = re.sub(r"^[\s\-–]+|[\s\-–:,]+$", "", c)
    return c.rstrip(" .")  # un punto final da problemas en SMB/Windows


def _truncate_bytes(s: str, max_bytes: int) -> str:
    while len(s.encode("utf-8")) > max_bytes:
        s = s[:-1]
    return s.rstrip(" .-")


# --------------------------------------------------------------------------- #
# Renderizado
# --------------------------------------------------------------------------- #
_FORMATTER = Formatter()


def _canonical(field_name: str) -> str:
    key = field_name.strip().lower()
    if key not in _FIELDS:
        raise TemplateError(f"Campo desconocido «{{{field_name}}}». Disponibles: {_FIELDS_HELP}")
    return key


def _fmt(value: object, spec: str, field: str) -> str:
    try:
        return format(value, spec)
    except (ValueError, TypeError) as exc:
        raise TemplateError(f"Formato «{spec}» no válido para {{{field}}}: {exc}") from exc


def _render_field(canon: str, spec: str, ctx: NameContext, windows_safe: bool) -> str:
    if canon in ("series", "title"):
        raw = ctx.series if canon == "series" else ctx.title
        items = [raw] if isinstance(raw, str) else list(raw)
        clean = [sanitize_component(t, windows_safe=windows_safe) for t in items if t]
        return _fmt(" & ".join(clean), spec, canon)
    if canon == "season":
        return "" if ctx.season is None else _fmt(ctx.season, spec, canon)
    if canon == "year":
        return "" if ctx.year is None else _fmt(ctx.year, spec, canon)
    if canon == "resolution":
        return _fmt(sanitize_component(ctx.resolution, windows_safe=windows_safe), spec, canon)
    if canon == "initial":
        return _fmt(sanitize_component(ctx.initial, windows_safe=windows_safe), spec, canon)
    # episode: varios números se unen con "-"  (S01E01-02)
    return "-".join(_fmt(n, spec, canon) for n in ctx.episodes)


def render(template: str, ctx: NameContext, extension: str = "", *, windows_safe: bool = True) -> str:
    """Devuelve el nombre nuevo (ruta relativa con ``/`` si la plantilla crea carpetas).

    Lanza TemplateError si la plantilla es inválida o el resultado queda vacío.
    """
    try:
        pieces = list(_FORMATTER.parse(template))
    except ValueError as exc:
        raise TemplateError(f"Plantilla inválida: {exc}") from exc

    out: list[str] = []
    for literal, field_name, spec, conversion in pieces:
        out.append(literal)
        if field_name is None:
            continue
        if conversion:
            raise TemplateError("Las conversiones (!r, !s) no están soportadas")
        out.append(_render_field(_canonical(field_name), spec or "", ctx, windows_safe))

    parts = [_tidy_component(p) for p in "".join(out).split("/")]
    parts = [p for p in parts if p]
    if not parts:
        raise TemplateError("El nombre resultante está vacío")

    ext_bytes = len(extension.encode("utf-8"))
    parts[:-1] = [_truncate_bytes(p, MAX_COMPONENT_BYTES) for p in parts[:-1]]
    parts[-1] = _truncate_bytes(parts[-1], MAX_COMPONENT_BYTES - ext_bytes) + extension
    return "/".join(parts)


def validate_template(template: str) -> str | None:
    """Mensaje de error si la plantilla no es válida, o None si está bien.

    Pensado para validar en vivo la caja de formato de la ventana de configuración.
    """
    try:
        render(template, SAMPLE_SERIES_CONTEXT)
    except TemplateError as exc:
        return str(exc)
    return None
