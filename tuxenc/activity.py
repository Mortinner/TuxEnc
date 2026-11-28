"""Historial legible de lo que TuxEnc ha hecho con los archivos (1.3.7).

Junta dos fuentes:

- los lotes de renombrado del historial de deshacer (``History``), marcados si se deshicieron;
- las conversiones, que se apuntan aquí al terminar cada una (``actividad.jsonl``).

La pestaña «Historial» de los ajustes enseña una tarjeta por vídeo: nombre final, de dónde
salió, adónde fue y qué se hizo.
"""
from __future__ import annotations

import heapq
import json
import os
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path

from retitler.parser import SUBTITLE_EXTS
from retitler.renamer import History

from .paths import STATE_DIR

ACTIVITY_FILE = STATE_DIR / "actividad.jsonl"
MAX_BYTES = 8 << 20              # unos 30 000 vídeos convertidos; al pasar se queda la mitad más reciente
_lock = threading.Lock()


@dataclass
class Entry:
    time: datetime               # con zona horaria (UTC en el archivo)
    kind: str                    # "rename", "convert" o "convert_rename"
    src: str                     # ruta de origen
    dst: str                     # ruta final
    subs: int = 0                # subtítulos que acompañaron al vídeo
    undone: bool = False         # renombrado deshecho
    original: str = ""           # conversión: "trash" si el original se mandó a la papelera

    @property
    def renamed(self) -> bool:
        return Path(self.src).name != Path(self.dst).name


def record_conversion(src: str, dst: str, *, renamed: bool, original: str = "",
                      subs: int = 0, path: Path | None = None) -> None:
    """Apunta una conversión terminada. Nunca falla: es solo un registro."""
    row = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "kind": "convert_rename" if renamed else "convert",
           "src": str(src), "dst": str(dst), "subs": int(subs), "original": original}
    target = path or ACTIVITY_FILE
    try:
        with _lock:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            _trim(target)
    except OSError:
        pass


def _trim(path: Path) -> None:
    """Solo mira el tamaño: no lee el archivo salvo cuando hay que recortarlo."""
    try:
        if path.stat().st_size <= MAX_BYTES:
            return
        with open(path, "rb") as fh:
            fh.seek(-(MAX_BYTES // 2), os.SEEK_END)
            tail = fh.read()
    except OSError:
        return
    tail = tail[tail.find(b"\n") + 1:]          # sin la primera línea, que puede estar cortada
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(tail)
    os.replace(tmp, path)


def _when(text: str) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _reverse_lines(path: Path, chunk: int = 1 << 16) -> Iterator[str]:
    """Líneas de un archivo de la última a la primera, leyendo solo lo necesario.

    Así la primera página del historial cuesta lo mismo con un mes de uso que con cinco años.
    """
    try:
        fh = open(path, "rb")
    except OSError:
        return
    with fh:
        fh.seek(0, os.SEEK_END)
        pos = fh.tell()
        rest = b""
        while pos > 0:
            step = min(chunk, pos)
            pos -= step
            fh.seek(pos)
            block = fh.read(step) + rest
            lines = block.split(b"\n")
            rest = lines.pop(0)          # puede ser el final de una línea más larga: espera al bloque anterior
            for raw in reversed(lines):
                if raw.strip():
                    yield raw.decode("utf-8", "replace")
        if rest.strip():
            yield rest.decode("utf-8", "replace")


def _iter_renames(path: Path) -> Iterator[Entry]:
    """Lotes de renombrado, del más nuevo al más viejo; una tarjeta por vídeo.

    Las marcas de «deshecho» van después de su lote en el archivo, así que al leer al revés
    se ven antes que el lote.
    """
    undone: set[str] = set()
    for line in _reverse_lines(path):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        if "undone" in row:
            undone.add(row["id"])
            continue
        when = _when(row.get("time", ""))
        if when is None or not isinstance(row.get("moves"), list):
            continue
        videos: list[Entry] = []
        subs: list[str] = []
        for move in row["moves"]:
            try:
                src, dst = str(move[0]), str(move[1])
            except (TypeError, IndexError):
                continue
            if Path(dst).suffix.lower() in SUBTITLE_EXTS:
                subs.append(dst)
            else:
                videos.append(Entry(when, "rename", src, dst, undone=row["id"] in undone))
        for v in videos:        # «Peli (2000) - [1080p].es.srt» va con «Peli (2000) - [1080p].mkv»
            stem = Path(v.dst).with_suffix("").name
            v.subs = sum(1 for s in subs if Path(s).parent == Path(v.dst).parent
                         and Path(s).name.startswith(stem))
        yield from videos


def _iter_conversions(path: Path) -> Iterator[Entry]:
    for line in _reverse_lines(path):
        try:
            row = json.loads(line)
            when = _when(row["time"])
            if when is None:
                continue
            yield Entry(when, str(row.get("kind", "convert")), str(row["src"]), str(row["dst"]),
                        subs=int(row.get("subs", 0)), original=str(row.get("original", "")))
        except (ValueError, KeyError, TypeError):
            continue


def iter_entries(history_path: Path | None = None, path: Path | None = None) -> Iterator[Entry]:
    """Todo el historial, lo más reciente primero, leído a medida que se pide."""
    return heapq.merge(_iter_renames(history_path or History().path), _iter_conversions(path or ACTIVITY_FILE),
                       key=lambda e: e.time, reverse=True)


def page(number: int, size: int = 20, history_path: Path | None = None,
         path: Path | None = None) -> tuple[list[Entry], bool]:
    """Página ``number`` (desde 0) de ``size`` tarjetas, y si hay más antiguas detrás."""
    start = max(0, number) * size
    items = list(islice(iter_entries(history_path, path), start, start + size + 1))
    return items[:size], len(items) > size


def load(limit: int = 300, history: History | None = None, path: Path | None = None) -> list[Entry]:
    """Lo más reciente primero, hasta ``limit``."""
    return list(islice(iter_entries(history.path if history else None, path), limit))
