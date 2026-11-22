"""Registro de actividad (archivo con rotación) para poder revisar qué se buscó y por qué.

Se guarda en ~/.local/state/retitler/retitler.log. Nunca se escribe la clave de API.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
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


class _Handler(logging.handlers.RotatingFileHandler):
    """Con rotación y, si el archivo se borra o se mueve con el programa abierto, lo vuelve a
    crear (como WatchedFileHandler). Antes se seguía escribiendo en el archivo borrado y el
    registro se perdía al cerrar (1.3.5)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ident = self._stat_ident()

    def _stat_ident(self):
        try:
            st = os.stat(self.baseFilename)
            return st.st_dev, st.st_ino
        except OSError:
            return None

    def emit(self, record: logging.LogRecord) -> None:
        if self.stream is not None and self._stat_ident() != self._ident:
            try:
                self.stream.close()
            except OSError:
                pass
            self.stream = None
        if self.stream is None:
            self.stream = self._open()
            self._ident = self._stat_ident()
        super().emit(record)

    def doRollover(self) -> None:
        super().doRollover()
        self._ident = self._stat_ident()


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
        handler = _Handler(path, maxBytes=5_000_000, backupCount=2, encoding="utf-8")
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
