"""Renombrado seguro: plan previo, conflictos con sufijo, ejecución con reversión y deshacer.

Reglas:
  * Nunca se sobrescribe nada. Si el nombre nuevo ya está cogido (por otro archivo del lote o
    por uno que ya existe en la carpeta) se añade « (2)», « (3)»... antes de la extensión.
  * Los nombres se comparan sin distinguir mayúsculas (Samba/CIFS lo hace aunque el disco no).
  * Cadenas (A->B, B->C), intercambios (A<->B) y cambios solo de mayúsculas se resuelven con
    nombres temporales.
  * Si algo falla a mitad, se revierte lo ya hecho.
  * Cada lote queda en un historial (JSON Lines) para poder deshacerlo.
"""
from __future__ import annotations

import errno
import json
import os
import shutil
import threading
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Iterable

from .config import state_dir
from .parser import split_extension

__all__ = ["History", "ItemStatus", "PlanItem", "RenameError", "RenameResult", "build_plan", "execute"]

MAX_NAME_BYTES = 255


class RenameError(Exception):
    """No se pudo renombrar (y, si se hizo algo, se ha revertido)."""


class ItemStatus(str, Enum):
    READY = "ready"          # se renombrará
    SUFFIXED = "suffixed"    # se renombrará, con sufijo por nombre repetido
    UNCHANGED = "unchanged"  # ya tiene el nombre correcto
    SKIPPED = "skipped"      # sin nombre nuevo (sin coincidencia, error...)


@dataclass(frozen=True)
class PlanItem:
    source: Path
    target: Path | None
    status: ItemStatus
    note: str = ""

    @property
    def will_rename(self) -> bool:
        return self.status in (ItemStatus.READY, ItemStatus.SUFFIXED)


@dataclass
class RenameResult:
    moves: list[tuple[Path, Path]] = field(default_factory=list)  # origen -> destino final
    created_dirs: list[Path] = field(default_factory=list)
    entry_id: str | None = None


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _key(path: Path | str) -> str:
    """Clave de comparación: Unicode normalizado y sin distinguir mayúsculas."""
    return unicodedata.normalize("NFC", os.fspath(path)).casefold()


def _listing_keys(directory: Path) -> set[str]:
    try:
        with os.scandir(directory) as entries:
            return {_key(directory / e.name) for e in entries}
    except OSError:
        return set()


def _exists(path: Path) -> bool:
    return os.path.lexists(path) or _key(path) in _listing_keys(path.parent)


def _with_suffix(path: Path, n: int) -> Path:
    """«Serie - 1x01.mkv» -> «Serie - 1x01 (2).mkv» (respeta extensiones como .es.srt)."""
    stem, ext = split_extension(path.name)
    tag = f" ({n})"
    budget = MAX_NAME_BYTES - len(ext.encode("utf-8")) - len(tag.encode("utf-8"))
    while len(stem.encode("utf-8")) > budget:
        stem = stem[:-1]
    return path.with_name(stem.rstrip() + tag + ext)


# --------------------------------------------------------------------------- #
# Plan
# --------------------------------------------------------------------------- #
def build_plan(entries: Iterable[tuple[str | Path, str | None]], target_root: str | Path | None = None) -> list[PlanItem]:
    """Calcula qué pasaría con cada archivo, sin tocar nada.

    ``entries`` son pares (archivo, nombre_nuevo); el nombre nuevo puede llevar subcarpetas
    (``Serie/Temporada 01/Serie - 1x01.mkv``) y es ``None`` si no hay nombre nuevo.
    Los nombres nuevos se colocan en la carpeta de cada archivo, o bajo ``target_root``.
    """
    rows: list[tuple[Path, Path | None, str]] = []
    for source, new_name in entries:
        source = Path(source)
        if new_name is None:
            rows.append((source, None, ""))
            continue
        rel = PurePosixPath(new_name)
        if rel.is_absolute() or ".." in rel.parts or not rel.parts:
            rows.append((source, None, "nombre nuevo no válido"))
            continue
        base = Path(target_root) if target_root else source.parent
        rows.append((source, base.joinpath(*rel.parts), ""))

    moving = {i for i, (s, t, _) in enumerate(rows) if t is not None and t != s}
    moving_keys = {_key(rows[i][0]) for i in moving}
    # Nombres que seguirán ocupados: archivos que no se mueven + lo que ya hay en las carpetas destino.
    reserved = {_key(s) for i, (s, _, _) in enumerate(rows) if i not in moving}
    occupied: set[str] = set()
    for directory in {rows[i][1].parent for i in moving}:  # type: ignore[union-attr]
        occupied |= _listing_keys(directory)
    occupied -= moving_keys  # estos archivos se van, dejan su nombre libre

    plan: list[PlanItem] = []
    for i, (source, target, note) in enumerate(rows):
        if target is None:
            plan.append(PlanItem(source, None, ItemStatus.SKIPPED, note or "sin nombre nuevo"))
        elif i not in moving:
            plan.append(PlanItem(source, target, ItemStatus.UNCHANGED, "ya tiene el nombre correcto"))
        else:
            candidate, n = target, 1
            while _key(candidate) in reserved or _key(candidate) in occupied:
                n += 1
                candidate = _with_suffix(target, n)
            reserved.add(_key(candidate))
            if n > 1:
                plan.append(PlanItem(source, candidate, ItemStatus.SUFFIXED, "nombre repetido: se añade el sufijo"))
            else:
                plan.append(PlanItem(source, candidate, ItemStatus.READY))
    return plan


# --------------------------------------------------------------------------- #
# Ejecución
# --------------------------------------------------------------------------- #
def _copy_across(src: Path, dst: Path) -> None:
    """Mueve entre discos distintos (p. ej. de Descargas al NAS): copia a un temporal, lo pone en
    su sitio sin pisar nada y solo entonces borra el original."""
    tmp = dst.with_name(f".{uuid.uuid4().hex[:8]}.retitler-tmp")
    try:
        shutil.copyfile(src, tmp)
        try:
            shutil.copystat(src, tmp)
        except OSError:
            pass                       # Samba/CIFS a veces no deja copiar fechas o permisos
        if os.path.lexists(dst):
            raise FileExistsError(f"ya existe {dst}")
        os.rename(tmp, dst)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    os.unlink(src)


def _rename_noclobber(src: Path, dst: Path, on_copy=None) -> None:
    if os.path.lexists(dst):
        raise FileExistsError(f"ya existe {dst}")
    try:
        os.rename(src, dst)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        if on_copy is not None:
            on_copy(src)              # otro disco u otro montaje: hay que copiar el archivo entero
        _copy_across(src, dst)


def _mkdirs(directory: Path) -> list[Path]:
    missing: list[Path] = []
    p = directory
    while not p.exists():
        missing.append(p)
        if p.parent == p:
            break
        p = p.parent
    created = []
    for d in reversed(missing):
        d.mkdir()
        created.append(d)
    return created


MOVE_WORKERS = 8          # movimientos a la vez: en un NAS casi todo el tiempo es esperar a la red


def _apply_moves(moves: list[tuple[Path, Path]], progress=None, workers: int = MOVE_WORKERS) -> list[Path]:
    """Aplica todos los movimientos o ninguno. Devuelve las carpetas creadas.

    progress(evento, origen): «copy» antes de copiar un archivo a otro disco y «done» cuando un
    archivo ya está en su sitio. Sirve para mostrar el avance de lotes grandes.

    En un NAS cada consulta al disco cuesta lo que tarda la red (unos 10-20 ms). Por eso las
    comprobaciones previas usan un listado por carpeta (no por archivo), las carpetas de destino se
    crean una vez antes de empezar y los renombrados se hacen varios a la vez. Las copias entre
    discos (cuando no se puede renombrar) van de una en una.
    """
    if not moves:
        return []
    keys_src = [_key(s) for s, _ in moves]
    keys_dst = [_key(d) for _, d in moves]
    if len(set(keys_src)) != len(keys_src):
        raise RenameError("El mismo archivo aparece dos veces en el lote")
    if len(set(keys_dst)) != len(keys_dst):
        raise RenameError("Dos archivos acabarían con el mismo nombre")
    all_src = set(keys_src)
    listings: dict[Path, set[str]] = {}

    def listing(directory: Path) -> set[str]:
        if directory not in listings:
            listings[directory] = _listing_keys(directory)
        return listings[directory]

    for (s, d), ks, kd in zip(moves, keys_src, keys_dst):
        if ks not in listing(s.parent) and not os.path.lexists(s):
            raise RenameError(f"No existe el archivo: {s}")
        if kd not in all_src and kd in listing(d.parent):
            raise RenameError(f"Ya existe un archivo con el nombre de destino: {d}")

    # Los que necesitan paso por nombre temporal: su destino es el nombre de otro archivo
    # del lote, o es un cambio solo de mayúsculas.
    temp = {i for i, (ks, kd) in enumerate(zip(keys_src, keys_dst)) if kd == ks or kd in all_src}
    done: list[tuple[Path, Path]] = []
    created: list[Path] = []
    lock = threading.Lock()
    copy_lock = threading.Lock()          # copiar archivos enteros al NAS: de uno en uno

    def report(event: str, src: Path) -> None:
        if progress is not None:
            try:
                progress(event, src)
            except Exception:  # noqa: BLE001 — el aviso nunca debe romper el renombrado
                pass

    def step(a: Path, b: Path, original: Path | None = None) -> None:
        if os.path.lexists(b):            # nunca se pisa nada, aunque haya aparecido después del plan
            raise FileExistsError(f"ya existe {b}")
        try:
            os.rename(a, b)
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
            if original is not None:
                report("copy", original)  # otro disco u otro montaje: hay que copiar el archivo entero
            with copy_lock:
                _copy_across(a, b)
        with lock:
            done.append((a, b))
        if original is not None:
            report("done", original)

    def run_parallel(jobs: list[tuple[Path, Path, Path | None]]) -> None:
        if workers <= 1 or len(jobs) < 2:
            for a, b, o in jobs:
                step(a, b, o)
            return
        failed = threading.Event()

        def guarded(a, b, o):
            if failed.is_set():
                return
            try:
                step(a, b, o)
            except BaseException:
                failed.set()
                raise

        with ThreadPoolExecutor(max_workers=min(workers, len(jobs)), thread_name_prefix="retitler-mv") as pool:
            futures = [pool.submit(guarded, a, b, o) for a, b, o in jobs]
        errors = [f.exception() for f in futures if f.exception() is not None]
        if errors:
            raise errors[0]

    try:
        for directory in sorted({d.parent for _, d in moves}, key=lambda p: len(p.parts)):
            created += _mkdirs(directory)
        hops: dict[int, Path] = {i: moves[i][0].with_name(f".{uuid.uuid4().hex[:8]}.retitler-tmp")
                                 for i in sorted(temp)}
        run_parallel([(moves[i][0], hops[i], None) for i in sorted(temp)])
        run_parallel([(s, d, s) for i, (s, d) in enumerate(moves) if i not in temp])
        run_parallel([(hops[i], moves[i][1], moves[i][0]) for i in sorted(temp)])
    except BaseException as exc:
        failures = []
        for a, b in reversed(done):
            try:
                _rename_noclobber(b, a)
            except OSError:
                failures.append(f"{b} (debería llamarse {a})")
        for d in reversed(created):
            try:
                d.rmdir()
            except OSError:
                pass
        detail = f"No se pudo renombrar: {exc}"
        if failures:
            detail += ". Además NO se pudo revertir: " + "; ".join(failures)
        else:
            detail += ". No se ha cambiado nada."
        if isinstance(exc, RenameError) and not failures:
            raise RenameError(f"{exc}. No se ha cambiado nada.") from exc
        raise RenameError(detail) from exc
    return created


# --------------------------------------------------------------------------- #
# Historial y deshacer
# --------------------------------------------------------------------------- #
class History:
    """Registro de lotes renombrados (JSON Lines) para poder deshacerlos."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else state_dir() / "history.jsonl"

    def _append(self, row: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def entries(self) -> list[dict]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        by_id: dict[str, dict] = {}
        order: list[str] = []
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                continue
            if "undone" in row:
                if row["id"] in by_id:
                    by_id[row["id"]]["undone"] = row["undone"]
            elif isinstance(row.get("moves"), list):
                by_id[row["id"]] = row
                order.append(row["id"])
        return [by_id[i] for i in order]

    def last_undoable(self) -> dict | None:
        return next((e for e in reversed(self.entries()) if "undone" not in e), None)

    def record(self, result: RenameResult) -> str:
        entry_id = uuid.uuid4().hex[:12]
        self._append({
            "id": entry_id,
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "moves": [[str(s), str(d)] for s, d in result.moves],
            "created_dirs": [str(d) for d in result.created_dirs],
        })
        return entry_id

    def undo_last(self) -> RenameResult:
        entry = self.last_undoable()
        if entry is None:
            raise RenameError("No hay nada que deshacer")
        try:
            back = [(Path(d), Path(s)) for s, d in entry["moves"]]
        except (TypeError, ValueError) as exc:
            raise RenameError("El historial está dañado") from exc
        _apply_moves(back)
        for d in reversed(entry.get("created_dirs", [])):
            try:
                Path(d).rmdir()  # solo si ha quedado vacía
            except OSError:
                pass
        self._append({"id": entry["id"], "undone": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        return RenameResult(moves=back, entry_id=entry["id"])


def execute(plan: list[PlanItem], history: History | None = None, progress=None) -> RenameResult:
    """Aplica el plan (solo los elementos que se renombran) y lo anota en el historial."""
    moves = [(i.source, i.target) for i in plan if i.will_rename and i.target is not None]
    created = _apply_moves(moves, progress)
    result = RenameResult(moves=moves, created_dirs=created)
    if history is not None and moves:
        result.entry_id = history.record(result)
    return result
