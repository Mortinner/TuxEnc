"""Retitler: renombrador de series y películas."""
__version__ = "1.0.1"

from .formatter import (
    DEFAULT_MOVIE_TEMPLATE,
    DEFAULT_SERIES_TEMPLATE,
    NameContext,
    TemplateError,
    render,
    validate_template,
)
from .parser import MediaKind, ParsedName, parse_filename, parse_path

__all__ = [
    "__version__",
    "DEFAULT_MOVIE_TEMPLATE", "DEFAULT_SERIES_TEMPLATE", "MediaKind", "NameContext",
    "ParsedName", "TemplateError", "parse_filename", "parse_path", "render", "validate_template",
]
