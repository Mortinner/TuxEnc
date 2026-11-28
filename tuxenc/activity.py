"""Historial legible de lo que TuxEnc ha hecho con los archivos (1.3.7).

Junta dos fuentes:

- los lotes de renombrado del historial de deshacer (``History``), marcados si se deshicieron;
- las conversiones, que se apuntan aquí al terminar cada una (``actividad.jsonl``).

La pestaña «Historial» de los ajustes enseña una tarjeta por vídeo: nombre final, de dónde
salió, adónde fue y qué se hizo.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from retitler.parser import SUBTITLE_EXTS
from retitler.renamer import History

from .paths import STATE_DIR

ACTIVITY_FILE = STATE_DIR / "actividad.jsonl"
MAX_LINES = 3000                 # al pasar de aquí se recorta a la mitad (lo más reciente)
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
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) > MAX_LINES:
        tmp = path.with_suffix(".tmp")
        tmp.write_text("\n".join(lines[-MAX_LINES // 2:]) + "\n", encoding="utf-8")
        os.replace(tmp, path)


def _when(text: str) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _renames(history: History) -> list[Entry]:
    """Una tarjeta por vídeo de cada lote; los subtítulos se cuentan en la de su vídeo."""
    out: list[Entry] = []
    for batch in history.entries():
        when = _when(batch.get("time", ""))
        if when is None:
            continue
        videos: list[Entry] = []
        subs: list[str] = []
        for move in batch.get("moves", []):
            try:
                src, dst = str(move[0]), str(move[1])
            except (TypeError, IndexError):
                continue
            if Path(dst).suffix.lower() in SUBTITLE_EXTS:
                subs.append(dst)
            else:
                videos.append(Entry(when, "rename", src, dst, undone="undone" in batch))
        for v in videos:        # «Peli (2000) - [1080p].es.srt» va con «Peli (2000) - [1080p].mkv»
            stem = Path(v.dst).with_suffix("").name
            v.subs = sum(1 for s in subs if Path(s).parent == Path(v.dst).parent
                         and Path(s).name.startswith(stem))
        out.extend(videos)
    return out


def _conversions(path: Path) -> list[Entry]:
    out: list[Entry] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            row = json.loads(line)
            when = _when(row["time"])
            if when is None:
                continue
            out.append(Entry(when, str(row.get("kind", "convert")), str(row["src"]), str(row["dst"]),
                             subs=int(row.get("subs", 0)), original=str(row.get("original", ""))))
        except (ValueError, KeyError, TypeError):
            continue
    return out


def load(limit: int = 300, history: History | None = None, path: Path | None = None) -> list[Entry]:
    """Lo más reciente primero."""
    items = _renames(history or History()) + _conversions(path or ACTIVITY_FILE)
    items.sort(key=lambda e: e.time, reverse=True)
    return items[:limit]
