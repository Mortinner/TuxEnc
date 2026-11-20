"""Renombrado integrado (núcleo de Retitler) para los trabajos de TuxEnc.

Sin interfaz gráfica: la GUI llama a estas funciones desde hilos de trabajo.

* Identificar: analiza el nombre del archivo y busca en TMDB / TVmaze / IMDb.
* Nombre final: plantilla de Retitler + {resolution} (regla de Marcos) + {initial}.
* Destino: junto al original, una carpeta elegida, o la biblioteca (raíz de series / de películas).
* Al convertir: el archivo nace en su sitio; al terminar se mide la resolución REAL del resultado
  y, si hace falta, se corrige el nombre. Los subtítulos externos se copian con el nombre nuevo.
* Solo renombrar: renombrado seguro de Retitler (nunca sobrescribe, revierte si falla, deshacer).
"""

from __future__ import annotations

import os
import time
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from retitler.config import KeyStore, Settings, legacy_retitler_keys
from retitler.parser import MediaKind, split_extension
from retitler.pipeline import Resolution, analyze, choose, companions, prefer_file_title, search_for
from retitler.providers import ResultKind, SearchResult
from retitler.renamer import History, PlanItem, build_plan, execute
from retitler.search import SearchResponse, Searcher, build_searcher

from . import builtin_keys
from .catalog import CONTAINERS, resolution_label
from .paths import clean_env
from .probe import probe
from retitler.log import log as rlog

KeyStore.BUILTIN = builtin_keys.load()

# Formatos por defecto de TuxEnc (biblioteca con resolución, como la de Marcos)
LIB_SERIES = ("{series} ({year})/Season {season:02}/{series} ({year}) - S{season:02}E{episode:02}"
              " - {title} - [{resolution}]")
LIB_MOVIE = "{initial}/{title} ({year}) - [{resolution}]"

# Estados de identificación de un trabajo
OFF, PENDING, OK, AMBIGUOUS, NONE, ERROR = "off", "pending", "ok", "ambiguous", "none", "error"
EPISODE = "episode"     # serie encontrada, pero falta saber qué capítulo es


@dataclass
class Destination:
    mode: str = "source"            # source | folder | library
    folder: str = ""                # mode == folder
    series_root: str = ""           # mode == library
    movie_root: str = ""

    def base_for(self, source: Path, kind: ResultKind | None) -> Path | None:
        """Carpeta base donde se coloca el nombre nuevo (None = junto al original)."""
        if self.mode == "folder" and self.folder:
            return Path(self.folder)
        if self.mode == "library":
            root = self.series_root if kind is ResultKind.SERIES else self.movie_root
            if root:
                return Path(root)
        return None

    def library_ready(self) -> bool:
        return bool(self.series_root and self.movie_root)


class Library:
    """Estado del renombrado: ajustes, claves y buscador."""

    def __init__(self) -> None:
        first_run = not Settings.default_path().exists()
        self.settings = Settings.load()
        if first_run:
            self.settings.series_template, self.settings.movie_template = LIB_SERIES, LIB_MOVIE
            try:
                self.settings.save()
            except OSError:
                pass
        self.keys = KeyStore()
        self.searcher: Searcher = build_searcher(self.settings, self.keys)
        self.memo: dict = {}
        self.history = History()

    # ---- configuración
    def reload(self) -> None:
        """Tras cambiar claves o idioma: buscador nuevo (la caché HTTP se conserva)."""
        self.searcher = build_searcher(self.settings, self.keys)
        self.memo = {}

    def has_key(self, service: str) -> bool:
        return bool(self.keys.for_service(service).get())

    def import_retitler_keys(self) -> list[str]:
        """Copia las claves que tuviera Retitler independiente. Devuelve qué servicios importó."""
        done = []
        for service, value in legacy_retitler_keys().items():
            if not self.has_key(service):
                self.keys.for_service(service).set(value)
                done.append(service)
        if done:
            self.reload()
        return done

    # ---- identificar
    def identify(self, path: str) -> tuple[str, Resolution, list[Path]]:
        """(estado, Resolution, subtítulos acompañantes). Usa internet."""
        res = analyze(path)
        subs = companions(Path(path))
        res = prefer_file_title(search_for(res, self.searcher, self.memo), self.settings)
        return state_of(res), res, subs

    def choose(self, res: Resolution, match: SearchResult, season: int | None = None,
               episodes: tuple[int, ...] | None = None) -> tuple[str, Resolution]:
        res = choose(res, match, self.searcher, season, episodes)
        # Si el usuario ha elegido el capítulo en la lista, manda su elección (con el título que vio).
        # El título del archivo solo se conserva cuando no eligió capítulo (p. ej. «misma serie»).
        if not (season is not None and episodes):
            res = prefer_file_title(res, self.settings)
        return state_of(res), res

    def seasons(self, match: SearchResult) -> list[int]:
        return self.searcher.seasons(match)

    def season_episodes(self, match: SearchResult, season: int):
        return self.searcher.season_episodes(match, season)

    def search(self, query: str, kind: MediaKind | str | None, year: int | None) -> SearchResponse:
        # Qt devuelve el dato de un desplegable como texto («episode»), no como MediaKind
        if kind is not None and not isinstance(kind, MediaKind):
            kind = MediaKind(str(kind))
        return self.searcher.search(query, kind=kind, year=year)

    # ---- nombres
    def relative_name(self, res: Resolution, resolution: str, extension: str) -> tuple[str | None, str]:
        return res.new_name(self.settings, resolution=resolution, extension=extension)

    def target(self, source: Path, res: Resolution, dest: Destination, resolution: str,
               extension: str) -> tuple[Path | None, str]:
        """Ruta absoluta final (sin resolver choques) o (None, motivo)."""
        name, note = self.relative_name(res, resolution, extension)
        if not name:
            return None, note
        rel = PurePosixPath(name)
        if rel.is_absolute() or ".." in rel.parts:
            return None, "nombre nuevo no válido"
        kind = res.chosen.kind if res.chosen else None
        base = dest.base_for(source, kind) or source.parent
        return base.joinpath(*rel.parts), note

    @staticmethod
    def metadata(res: Resolution) -> dict:
        """Etiquetas para el archivo convertido (Jellyfin, Plex y los reproductores las leen)."""
        m = res.chosen
        if not m:
            return {}
        if m.kind is ResultKind.SERIES and res.parsed.season is not None and res.parsed.episodes:
            title = " & ".join(t for t in res.titles if t)
            ep = res.parsed.episodes[0]
            return {"title": title or f"{m.title} S{res.parsed.season:02}E{ep:02}",
                    "show": m.title, "season_number": res.parsed.season,
                    "episode_sort": ep, "episode_id": f"S{res.parsed.season:02}E{ep:02}",
                    "date": m.year or ""}
        return {"title": m.title, "date": m.year or ""}

    # ---- solo renombrar
    def rename_batch(self, items: list[tuple], dest: Destination, progress=None
                     ) -> tuple[list[PlanItem], list[tuple[Path, Path]]]:
        """Renombra (y mueve) vídeos y sus subtítulos. Un único lote en el historial (deshacer).

        Devuelve (plan, movimientos hechos). Lanza RenameError si falla (y ya se ha revertido).
        """
        t0 = time.monotonic()
        rlog.info("Renombrado: lote de %d vídeo(s), destino «%s»", len(items), dest.mode)
        groups: dict[str | None, list[tuple[Path, str | None]]] = {}
        for item in items:
            video, res, subs = item[:3]
            # La resolución ya se conoce desde que se añadió el vídeo: no se vuelve a analizar
            # (antes, 279 capítulos de un NAS = ~2 s cada uno, uno detrás de otro).
            info_res = item[3] if len(item) > 3 and item[3] else ""
            if not info_res:
                try:
                    info_res = probe(str(video), measure_audio=False).std_resolution
                except Exception:  # noqa: BLE001 — sin resolución el nombre sale sin ella
                    pass
            name, _note = self.relative_name(res, info_res, res.parsed.extension)
            kind = res.chosen.kind if res.chosen else None
            base = dest.base_for(video, kind)
            key = str(base) if base else None
            groups.setdefault(key, []).append((video, name))
            if name:
                stem = name[: len(name) - len(res.parsed.extension)] if res.parsed.extension else name
                for sub in subs:
                    groups[key].append((sub, stem + split_extension(sub.name)[1]))
        plan: list[PlanItem] = []
        for root, entries in groups.items():
            plan += build_plan(entries, root)
        t1 = time.monotonic()
        copies = []

        def on_progress(event, src):
            if event == "copy":
                copies.append(src)
                if len(copies) == 1:
                    rlog.info("Renombrado: el destino está en otro disco o montaje: los archivos se "
                              "copian enteros (más lento). Primero: %s", src)
            if progress is not None:
                progress(event, src)
        result = execute(plan, self.history, on_progress)
        rlog.info("Renombrado: %d archivo(s) movidos (%d copiados entre discos). Plan %.1f s, "
                  "movimientos %.1f s", len(result.moves), len(copies), t1 - t0, time.monotonic() - t1)
        return plan, result.moves

    def undo_last(self):
        return self.history.undo_last()

    def can_undo(self) -> bool:
        return self.history.last_undoable() is not None

    # ---- tras convertir
    def finalize_converted(self, job, res: Resolution, dest: Destination, container: str,
                           original_after: str) -> list[str]:
        """Ajusta el nombre a la resolución real, copia subtítulos y gestiona el original.

        Devuelve avisos (no fatales). Cambia ``job.output`` si mueve el archivo.
        """
        warnings: list[str] = []
        out = Path(job.output)
        try:
            real = probe(str(out)).std_resolution
        except Exception:  # noqa: BLE001
            real = ""
        ext = CONTAINERS[container]["ext"]
        target, note = self.target(Path(job.input), res, dest, real, ext)
        if target is not None and target != out:
            target.parent.mkdir(parents=True, exist_ok=True)
            final = free_name(target, exclude=out)
            _move_noclobber(out, final)
            _remove_empty_dirs(out.parent, stop_at=target.parent)
            job.output = str(final)
            out = final
        # Subtítulos externos: copia con el nombre nuevo (los .srt de dentro ya van en el MKV)
        stem = out.name[: -len(ext)] if out.name.endswith(ext) else out.stem
        for sub in job.companions:
            sub = Path(sub)
            dst = free_name(out.with_name(stem + split_extension(sub.name)[1]))
            try:
                shutil.copy2(sub, dst)
                job.copied_subs.append(str(dst))
            except OSError as exc:
                warnings.append(f"no se pudo copiar {sub.name}: {exc}")
        # Si el convertido ocupa más que el original, el original NUNCA se borra solo:
        # la fila pregunta al usuario con cuál quedarse.
        try:
            copied = bool(getattr(job, "plan", None) and job.plan.video_copied)
            bigger = bool(job.info.size) and out.stat().st_size > job.info.size and not copied
        except OSError:
            bigger = False
        job.bigger = bigger
        if original_after == "trash" and not bigger:
            for p in [Path(job.input), *map(Path, job.companions)]:
                if not trash(p):
                    warnings.append(f"no se pudo enviar a la papelera: {p.name}")
        return warnings

    # ---- el convertido ocupa más: decide el usuario
    def use_converted(self, job) -> list[str]:
        """Se queda con el convertido: el original (y sus subtítulos) a la papelera."""
        failed = [p.name for p in [Path(job.input), *map(Path, job.companions)] if not trash(p)]
        return [f"no se pudo enviar a la papelera: {n}" for n in failed]

    def use_original(self, job, dest: Destination | None) -> list[str]:
        """Se queda con el original: el convertido a la papelera y, si se renombraba, el original
        ocupa su lugar en la biblioteca con el nombre final (con su extensión de siempre)."""
        out = Path(job.output)
        failed = [p.name for p in [out, *map(Path, job.copied_subs)] if not trash(p)]
        if failed:
            return [f"no se pudo enviar a la papelera: {n}" for n in failed]
        if getattr(job, "rename", False) and job.rt is not None and dest is not None:
            # Solo se limpian carpetas vacías DENTRO de la biblioteca, nunca su raíz
            kind = job.rt.chosen.kind if job.rt.chosen else None
            base = dest.base_for(Path(job.input), kind) or Path(job.input).parent
            _remove_empty_dirs(out.parent, stop_at=base)
            items = [(Path(job.input), job.rt, [Path(s) for s in job.companions])]
            plan, _moves = self.rename_batch(items, dest)
            for item in plan:
                if str(item.source) == job.input and item.target is not None:
                    job.output = str(item.target)
        else:
            job.output = job.input
        return []


def state_of(res: Resolution) -> str:
    if res.error:
        return ERROR
    if res.chosen is None and not res.candidates and res.warnings:
        return ERROR          # no es que no exista: no se pudo preguntar (red, clave…)
    if res.chosen is None:
        return NONE if not res.candidates else AMBIGUOUS
    if res.chosen.kind is ResultKind.SERIES and (res.parsed.season is None or not res.parsed.episodes):
        return EPISODE
    return OK


def predicted_resolution(info, settings) -> str:
    """Resolución estándar que tendrá el resultado (antes de convertir; la definitiva se mide al final)."""
    from .catalog import fit_size
    v = info.main_video
    if not v:
        return ""
    size = fit_size(v.width, v.height, settings.max_height, settings.allow_upscale)
    w, h = size if size else (v.width, v.height)
    return resolution_label(w, h, v.sar)


def free_name(path: Path, exclude: Path | None = None) -> Path:
    """La ruta si está libre; si no, «Nombre (2).ext», «(3)»… (como Retitler)."""
    def taken(p: Path) -> bool:
        return (os.path.lexists(p) and (exclude is None or p != exclude))
    if not taken(path):
        return path
    stem, ext = split_extension(path.name)
    if not ext:
        stem, ext = path.stem, path.suffix
    n = 2
    while True:
        cand = path.with_name(f"{stem} ({n}){ext}")
        if not taken(cand):
            return cand
        n += 1


def _move_noclobber(src: Path, dst: Path) -> None:
    if os.path.lexists(dst):
        raise FileExistsError(str(dst))
    try:
        os.link(src, dst)          # atómico y sin pisar nada en el mismo disco
        os.unlink(src)
    except OSError:
        shutil.move(str(src), str(dst))


def _remove_empty_dirs(directory: Path, stop_at: Path) -> None:
    """Borra carpetas que se quedaron vacías por un cambio de nombre de último momento."""
    d = directory
    try:
        while d != stop_at and d != d.parent and not any(d.iterdir()):
            d.rmdir()
            d = d.parent
    except OSError:
        pass


def trash(path: Path) -> bool:
    """Envía a la papelera del escritorio (recuperable). False si no se pudo."""
    if not path.exists():
        return True
    for cmd in (["gio", "trash", str(path)], ["kioclient6", "move", str(path), "trash:/"],
                ["kioclient5", "move", str(path), "trash:/"], ["trash-put", str(path)]):
        if not shutil.which(cmd[0]):
            continue
        try:
            r = subprocess.run(cmd, env=clean_env(), capture_output=True, timeout=60, check=False)
        except (OSError, subprocess.SubprocessError):
            continue
        if r.returncode == 0 and not path.exists():
            return True
    return False
