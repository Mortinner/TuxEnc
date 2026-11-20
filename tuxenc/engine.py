"""Cola de trabajos con ejecución en paralelo. Independiente de la interfaz gráfica."""

from __future__ import annotations

import itertools
import os
import shutil
import signal
import subprocess
import threading
from fractions import Fraction
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .catalog import CONTAINERS, EncodeSettings
from .command import Plan, build_plan, detect_crop
from .paths import CACHE_DIR, LOG_DIR, clean_env
from .probe import MediaInfo, ensure_audio_measured

WAITING, PREPARING, RUNNING, PAUSED, DONE, FAILED, CANCELLED = (
    "waiting", "preparing", "running", "paused", "done", "failed", "cancelled")
ACTIVE = (PREPARING, RUNNING, PAUSED)
FINISHED = (DONE, FAILED, CANCELLED)

_ids = itertools.count(1)
LOW_NICE = 10


def cpu_count() -> int:
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return os.cpu_count() or 2


def auto_parallel() -> int:
    """Trabajos simultáneos recomendados para este equipo."""
    return max(1, min(6, cpu_count() // 8))


@dataclass
class Job:
    input: str
    info: MediaInfo
    id: int = field(default_factory=lambda: next(_ids))
    settings: EncodeSettings | None = None      # se fija al empezar o al añadir con la cola en marcha
    output: str = ""
    status: str = WAITING
    progress: float = 0.0
    fps: float = 0.0
    speed: float = 0.0
    eta: float = -1.0
    elapsed: float = 0.0
    pass_no: int = 0
    pass_total: int = 1
    error: str = ""
    log_path: str = ""
    out_size: int = 0
    audio_override: list | None = None
    sub_override: list | None = None
    burn_override: int | None = None
    plan: Plan | None = None
    order: float = 0.0
    # --- renombrado (Retitler) ---
    hold: bool = False             # esperando a que el usuario elija la coincidencia
    hand_pick: bool = False        # el usuario eligió a mano su capítulo en «Identificar…»
    staged: bool = False           # en «Preparar» (izquierda): aún no está en la cola
    task_convert: bool = True      # tarea fijada al añadirlo a la cola
    task_rename: bool = False
    out_mode: str = ""             # destino fijado al añadirlo («source», «folder», «library»)
    out_folder: str = ""
    metadata: dict = field(default_factory=dict)   # etiquetas que se escriben en el archivo
    ident: str = "off"             # off | pending | ok | ambiguous | none | error
    rt: object = None              # retitler.pipeline.Resolution
    companions: list = field(default_factory=list)  # subtítulos externos que acompañan al vídeo
    note: str = ""                 # explicación de la identificación / del renombrado
    warning: str = ""              # aviso no fatal tras terminar (p. ej. no se pudo mover el original)
    bigger: bool = False           # el convertido ocupa más que el original: decide el usuario
    decision: str = ""             # "" | original | converted | both  (respuesta del usuario)
    copied_subs: list = field(default_factory=list)  # subtítulos copiados junto al convertido
    renamed_to: str = ""           # destino final cuando solo se renombra
    preview: str = ""              # cómo quedará el nombre (ruta relativa al destino)
    dest: object = None            # library.Destination fijado al empezar
    rename: bool = False           # este trabajo renombra al terminar (fijado al empezar)

    @property
    def name(self) -> str:
        return os.path.basename(self.input)


def _output_fps(job: "Job") -> float:
    """Fotogramas por segundo del vídeo de salida (para calcular el avance por fotogramas)."""
    st = job.settings
    if st is not None and st.framerate not in ("", "source"):
        try:
            return float(Fraction(st.framerate))
        except (ValueError, ZeroDivisionError):
            pass
    v = job.info.main_video if job.info else None
    return float(v.fps) if v and v.fps else 0.0


class _Runner(threading.Thread):
    def __init__(self, engine: "QueueEngine", job: Job, threads: int):
        super().__init__(daemon=True, name=f"tuxenc-job-{job.id}")
        self.engine = engine
        self.job = job
        self.threads = threads
        self.proc: subprocess.Popen | None = None
        self._cancel = threading.Event()
        self._paused = False
        self._pause_started = 0.0
        self._paused_total = 0.0
        self.tmp_output = ""

    # ---- control
    def pause(self) -> None:
        if self.proc and self.proc.poll() is None and not self._paused:
            try:
                os.killpg(self.proc.pid, signal.SIGSTOP)
            except OSError:
                return
            self._paused = True
            self._pause_started = time.monotonic()
            self.job.status = PAUSED
            self.engine._notify(self.job)

    def resume(self) -> None:
        if self.proc and self._paused:
            try:
                os.killpg(self.proc.pid, signal.SIGCONT)
            except OSError:
                pass
            self._paused = False
            self._paused_total += time.monotonic() - self._pause_started
            self.job.status = RUNNING
            self.engine._notify(self.job)

    def cancel(self) -> None:
        self._cancel.set()
        proc = self.proc
        if proc and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGCONT)
                os.killpg(proc.pid, signal.SIGTERM)
            except OSError:
                pass

    # ---- ejecución
    def run(self) -> None:
        job = self.job
        try:
            self._run()
        except Exception as exc:  # noqa: BLE001 — cualquier fallo se muestra en la GUI
            job.status = FAILED
            job.error = str(exc)
        finally:
            if job.status != DONE and self.tmp_output and os.path.exists(self.tmp_output):
                try:
                    os.remove(self.tmp_output)
                except OSError:
                    pass
            if job.status != DONE and self.engine.cleanup is not None:
                try:
                    self.engine.cleanup(job)       # p. ej. carpetas vacías creadas en la biblioteca
                except Exception:  # noqa: BLE001
                    pass
            self._cleanup_passlogs()
            self.engine._job_finished(self)

    def _cleanup_passlogs(self) -> None:
        for p in CACHE_DIR.glob(f"pass-{self.job.id}*"):
            try:
                p.unlink()
            except OSError:
                pass
        link_dir = CACHE_DIR
        for p in link_dir.glob(f"sub-{self.job.id}.*"):
            try:
                p.unlink()
            except OSError:
                pass

    def _run(self) -> None:
        job = self.job
        st = job.settings
        assert st is not None
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        job.status = PREPARING
        self.engine._notify(job)
        ensure_audio_measured(job.info)        # se dejó para ahora: al añadir solo se lee la cabecera

        crop = detect_crop(job.info) if st.autocrop else None
        if self._cancel.is_set():
            job.status = CANCELLED
            return

        out = Path(job.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        self.tmp_output = str(out.with_name(f".{out.stem}.tuxenc-part{out.suffix}"))
        plan = build_plan(job.info, st, self.tmp_output, threads=self.threads, crop=crop,
                          job_id=job.id, work_dir=str(CACHE_DIR),
                          audio_override=job.audio_override, sub_override=job.sub_override,
                          burn_override=job.burn_override, metadata=job.metadata)
        job.plan = plan
        job.pass_total = len(plan.passes)
        job.log_path = str(LOG_DIR / f"job-{job.id}.log")
        start = time.monotonic()
        duration = max(job.info.duration, 0.001)
        out_fps = _output_fps(job)

        with open(job.log_path, "w", encoding="utf-8", errors="replace") as log:
            log.write(f"TuxEnc — {job.input}\n-> {job.output}\n\n")
            for n, args in enumerate(plan.passes, 1):
                job.pass_no = n
                log.write("$ " + " ".join(_q(a) for a in args) + "\n\n")
                log.flush()
                job.status = RUNNING
                self.engine._notify(job)
                if self.engine.low_priority and shutil.which("nice"):
                    args = ["nice", "-n", str(LOW_NICE)] + args
                self.proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=log,
                                             stdin=subprocess.DEVNULL, env=clean_env(),
                                             start_new_session=True, text=True, bufsize=1)
                if self.engine.paused:
                    self.pause()
                last_emit = 0.0
                t_time = t_frames = 0.0
                assert self.proc.stdout is not None
                for line in self.proc.stdout:
                    key, _, val = line.strip().partition("=")
                    if key in ("out_time_us", "out_time_ms", "frame"):
                        # FFmpeg da out_time como el de la pista MÁS ATRASADA: una pista de subtítulos
                        # con pocos textos lo deja clavado (p. ej. en 0:02) mientras el vídeo avanza.
                        # Los fotogramas de vídeo ya escritos / fps dicen por dónde va de verdad.
                        try:
                            num = int(val)
                        except ValueError:
                            continue
                        if key == "frame":
                            if out_fps > 0:
                                t_frames = num / out_fps
                        else:
                            t_time = num / 1_000_000
                        frac = min(1.0, max(0.0, max(t_time, t_frames) / duration))
                        job.progress = ((n - 1) + frac) / job.pass_total
                    elif key == "fps":
                        try:
                            job.fps = float(val)
                        except ValueError:
                            pass
                    elif key == "speed":
                        try:
                            job.speed = float(val.rstrip("x"))
                        except ValueError:
                            pass
                    elif key == "progress":
                        now = time.monotonic()
                        job.elapsed = now - start - self._paused_total
                        if job.progress > 0.01:
                            job.eta = job.elapsed / job.progress - job.elapsed
                        if now - last_emit > 0.4 or val == "end":
                            last_emit = now
                            try:
                                job.out_size = os.path.getsize(self.tmp_output)
                            except OSError:
                                pass
                            self.engine._notify(job)
                rc = self.proc.wait()
                if self._cancel.is_set():
                    job.status = CANCELLED
                    return
                if rc != 0:
                    job.status = FAILED
                    job.error = _last_error(job.log_path) or f"ffmpeg rc={rc}"
                    return

        # Todo bien: mover el temporal a su nombre definitivo
        os.replace(self.tmp_output, job.output)
        if self.engine.post_process is not None:
            try:
                self.engine.post_process(job)      # puede cambiar job.output (nombre final exacto)
            except Exception as exc:  # noqa: BLE001 — el vídeo ya está bien; solo se avisa
                job.warning = str(exc)
        job.out_size = os.path.getsize(job.output)
        copied = bool(job.plan and job.plan.video_copied)   # la imagen no se tocó: no hay dilema
        if job.info.size and job.out_size > job.info.size and not copied:
            job.bigger = True          # no se toca el original: la fila pregunta con cuál quedarse
        job.progress = 1.0
        job.eta = 0
        job.elapsed = time.monotonic() - start - self._paused_total
        job.status = DONE


def _q(a: str) -> str:
    return a if a and all(c.isalnum() or c in "-_./:=,+" for c in a) else "'" + a.replace("'", "'\\''") + "'"


def _last_error(log_path: str) -> str:
    try:
        lines = Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    lines = [ln for ln in lines if ln.strip() and not ln.startswith("$ ")]
    return lines[-1].strip() if lines else ""


class QueueEngine:
    """Gestiona la cola y lanza hasta `max_parallel` trabajos a la vez.

    Los callbacks se llaman desde hilos de trabajo: la GUI los convierte en señales Qt.
    """

    def __init__(self, on_update: Callable[[Job], None] | None = None,
                 on_queue_done: Callable[[list[Job]], None] | None = None):
        self.jobs: list[Job] = []
        self.max_parallel = auto_parallel()
        self.low_priority = True
        self.running: dict[int, _Runner] = {}
        self.active = False          # la cola está "en marcha"
        self.paused = False
        self._lock = threading.RLock()
        self.on_update = on_update or (lambda j: None)
        self.on_queue_done = on_queue_done or (lambda jobs: None)
        self.settings_provider: Callable[[], EncodeSettings] = EncodeSettings
        self.output_resolver: Callable[[Job, EncodeSettings], str] = default_output
        self.post_process: Callable[[Job], None] | None = None
        self.cleanup: Callable[[Job], None] | None = None

    # ---- notificaciones internas
    def _notify(self, job: Job) -> None:
        self.on_update(job)

    def _job_finished(self, runner: _Runner) -> None:
        with self._lock:
            self.running.pop(runner.job.id, None)
        self._notify(runner.job)
        self._schedule()

    # ---- gestión de la cola
    def add(self, job: Job) -> None:
        with self._lock:
            if self.active and self.queued(job):
                self._lock_settings(job)
            if not job.order:
                job.order = float(job.id) + 1e9
            pos = len(self.jobs)
            while pos > 0 and self.jobs[pos - 1].order > job.order:
                pos -= 1
            self.jobs.insert(pos, job)
        self._notify(job)
        self._schedule()

    def remove(self, job_id: int) -> None:
        with self._lock:
            runner = self.running.get(job_id)
            if runner:
                runner.cancel()
            self.jobs = [j for j in self.jobs if j.id != job_id]
        self._schedule()      # quitar el último retenido puede dar la cola por terminada

    def move(self, job_id: int, delta: int) -> None:
        with self._lock:
            idx = next((i for i, j in enumerate(self.jobs) if j.id == job_id), None)
            if idx is None:
                return
            new = max(0, min(len(self.jobs) - 1, idx + delta))
            job = self.jobs.pop(idx)
            self.jobs.insert(new, job)
            for i, j in enumerate(self.jobs):
                j.order = float(i)

    def remove_many(self, job_ids) -> None:
        """Quita varios trabajos a la vez; los que estén en marcha se cancelan."""
        ids = set(job_ids)
        with self._lock:
            for jid in ids:
                runner = self.running.get(jid)
                if runner:
                    runner.cancel()
            self.jobs = [j for j in self.jobs if j.id not in ids]
        self._schedule()

    def clear_finished(self) -> None:
        with self._lock:
            self.jobs = [j for j in self.jobs if j.status not in FINISHED]

    def retry(self, job_id: int) -> None:
        with self._lock:
            for j in self.jobs:
                if j.id == job_id and j.status in (FAILED, CANCELLED):
                    j.status, j.progress, j.error, j.eta = WAITING, 0.0, "", -1
                    j.output = ""
        self._schedule()

    def queued(self, j: Job) -> bool:
        """¿Está en la cola (no en preparación) y es algo que el motor tiene que convertir?"""
        return not j.staged and j.task_convert

    def _lock_settings(self, job: Job) -> None:
        if job.settings is None:
            job.settings = self.settings_provider().copy()

    def start(self) -> None:
        with self._lock:
            self.active = True
            self.paused = False
            for j in self.jobs:
                if j.status == WAITING and self.queued(j):
                    self._lock_settings(j)
            for r in self.running.values():
                r.resume()
        self._schedule()

    def pause(self) -> None:
        with self._lock:
            self.paused = True
            for r in list(self.running.values()):
                r.pause()

    def resume(self) -> None:
        self.start()

    def stop(self) -> None:
        """Cancela lo que está en marcha. Los pendientes se quedan en la cola."""
        with self._lock:
            self.active = False
            self.paused = False
            for r in list(self.running.values()):
                r.cancel()
            for j in self.jobs:
                if j.status == WAITING and self.queued(j):
                    j.hold = False

    def cancel_job(self, job_id: int) -> None:
        with self._lock:
            r = self.running.get(job_id)
            if r:
                r.cancel()

    def set_parallel(self, n: int) -> None:
        with self._lock:
            self.max_parallel = max(1, int(n))
        self._schedule()

    def set_low_priority(self, on: bool) -> None:
        """Cambia la prioridad. A los trabajos en curso se les aplica si el sistema lo permite
        (bajar prioridad siempre; volver a subirla normalmente requiere ser administrador)."""
        with self._lock:
            self.low_priority = bool(on)
            pids = [r.proc.pid for r in self.running.values() if r.proc and r.proc.poll() is None]
        nice = LOW_NICE if on else 0
        for pid in pids:
            for task_dir in (f"/proc/{pid}/task",):
                try:
                    tids = [int(t) for t in os.listdir(task_dir)]
                except OSError:
                    continue
                for tid in tids:
                    try:
                        os.setpriority(os.PRIO_PROCESS, tid, nice)
                    except OSError:
                        pass
            # ffmpeg es hijo de `nice`: aplicar también a los hijos
            try:
                with open(f"/proc/{pid}/task/{pid}/children", encoding="utf-8") as fh:
                    children = [int(c) for c in fh.read().split()]
            except OSError:
                children = []
            for child in children:
                try:
                    for tid in os.listdir(f"/proc/{child}/task"):
                        try:
                            os.setpriority(os.PRIO_PROCESS, int(tid), nice)
                        except OSError:
                            pass
                except OSError:
                    pass

    def counts(self) -> dict:
        with self._lock:
            c = {k: 0 for k in (WAITING, PREPARING, RUNNING, PAUSED, DONE, FAILED, CANCELLED)}
            c["staged"] = 0
            for j in self.jobs:
                if j.staged:
                    c["staged"] += 1
                else:
                    c[j.status] += 1
            return c

    def overall_progress(self) -> float:
        """Progreso global del lote en marcha (trabajos con ajustes fijados)."""
        with self._lock:
            batch = [j for j in self.jobs if not j.staged and j.task_convert
                     and (j.settings is not None or j.status in FINISHED)]
            if not batch:
                return 0.0
            total = sum(max(j.info.duration, 1) for j in batch)
            done = sum(max(j.info.duration, 1) * (1.0 if j.status in FINISHED else j.progress)
                       for j in batch)
            return done / total

    def is_busy(self) -> bool:
        with self._lock:
            return bool(self.running)

    def _schedule(self) -> None:
        finished_batch = None
        with self._lock:
            if self.active and not self.paused:
                waiting = [j for j in self.jobs if j.status == WAITING and not j.hold and self.queued(j)]
                while waiting and len(self.running) < self.max_parallel:
                    job = waiting.pop(0)
                    self._lock_settings(job)
                    job.output = self.output_resolver(job, job.settings)
                    threads = max(1, cpu_count() // max(1, self.max_parallel))
                    runner = _Runner(self, job, threads)
                    self.running[job.id] = runner
                    job.status = PREPARING
                    runner.start()
            # Los retenidos (esperando coincidencia) mantienen la cola abierta: no se da por
            # terminada (ni se apaga el equipo) mientras queden vídeos por decidir.
            if self.active and not self.running and not any(j.status == WAITING and self.queued(j)
                                                            for j in self.jobs):
                self.active = False
                finished_batch = [j for j in self.jobs if j.status in FINISHED]
        if finished_batch is not None:
            self.on_queue_done(finished_batch)

    def release(self, job_id: int) -> None:
        """Quita la retención de un trabajo (ya tiene coincidencia) y lo pone en marcha si toca."""
        with self._lock:
            for j in self.jobs:
                if j.id == job_id:
                    j.hold = False
        self._schedule()

    def kick(self) -> None:
        self._schedule()

    def shutdown(self) -> None:
        """Mata todo (al cerrar la aplicación)."""
        with self._lock:
            runners = list(self.running.values())
            self.active = False
        for r in runners:
            r.cancel()
        for r in runners:
            r.join(timeout=5)

    # ---- nombres de salida
    def reserved_outputs(self, exclude: int) -> set[str]:
        with self._lock:
            return {j.output for j in self.jobs if j.output and j.id != exclude
                    and j.status not in FINISHED}


def default_output(job: Job, st: EncodeSettings, folder: str | None = None,
                   reserved: set[str] | None = None) -> str:
    """Nombre de salida sin pisar nunca el original ni otro archivo existente."""
    src = Path(job.input)
    out_dir = Path(folder) if folder else src.parent
    ext = CONTAINERS[st.container]["ext"]
    reserved = reserved or set()
    candidate = out_dir / f"{src.stem}{ext}"

    def taken(p: Path) -> bool:
        return p.exists() or str(p) in reserved or p.resolve() == src.resolve()

    if not taken(candidate):
        return str(candidate)
    candidate = out_dir / f"{src.stem} (TuxEnc){ext}"
    n = 2
    while taken(candidate):
        candidate = out_dir / f"{src.stem} (TuxEnc {n}){ext}"
        n += 1
    return str(candidate)
