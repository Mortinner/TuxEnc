"""Registro de actividad (archivo con rotación) para poder revisar qué se buscó y por qué.

Se guarda en ~/.local/state/retitler/retitler.log. Nunca se escribe la clave de API.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from .config import state_dir

__all__ = ["log", "log_path", "setup_logging"]

log = logging.getLogger("retitler")
log.addHandler(logging.NullHandler())  # sin configurar no se imprime nada
_configured = False


def log_path() -> Path:
    return state_dir() / "retitler.log"


_path: Path | None = None


def setup_logging(verbose: bool = False, path: Path | None = None) -> Path | None:
    """Activa el registro en archivo (y en la terminal si ``verbose``). Devuelve la ruta del archivo."""
    global _configured, _path
    if _configured:
        return _path
    _configured = True
    log.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    path = path or log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        handler.setLevel(logging.DEBUG if verbose else logging.INFO)
        handler.setFormatter(fmt)
        log.addHandler(handler)
    except OSError:
        path = None  # sin registro en archivo; la aplicación sigue funcionando
    _path = path
    if verbose:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(fmt)
        log.addHandler(console)
    return path
