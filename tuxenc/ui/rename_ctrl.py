"""Renombrado en la interfaz: identificación en segundo plano, elegir coincidencia, renombrar y deshacer."""

from __future__ import annotations

import itertools
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                               QSpinBox, QSplitter, QVBoxLayout, QWidget)

from retitler.matching import normalize
from retitler.parser import MediaKind
from retitler.providers import ResultKind

from ..catalog import CONTAINERS
from ..engine import FINISHED, WAITING, Job
from .. import i18n
from ..i18n import tr
from retitler.providers import ENGLISH_SOURCES, PROVIDER_NAMES
from ..library import (AMBIGUOUS, EPISODE, ERROR, NONE, OK, PENDING, Destination, Library,
                       predicted_resolution)


def describe_match(res) -> str:
    """«Arrow (2012) · S01E02 · Honra a tu padre · TMDB»."""
    m = res.chosen
    if m is None:
        return ""
    parts = [m.label]
    if m.kind is ResultKind.SERIES and res.parsed.season is not None and res.parsed.episodes:
        parts.append(f"S{res.parsed.season:02}E" + "-".join(f"{e:02}" for e in res.parsed.episodes))
        titles = " & ".join(t for t in res.titles if t)
        if titles:
            srcs = set(res.title_sources or ())
            provs = {x.split("-")[0] for x in srcs if x}
            if "archivo" in srcs:
                titles += f" ({tr('title_from_file')})"
            elif srcs and srcs <= ENGLISH_SOURCES and i18n.current() == "es":
                titles += f" ({tr('title_english')})"
            elif res.chosen is not None and provs and provs != {res.chosen.provider}:
                # el título viene de otro buscador que el de la serie (p. ej. TheTVDB)
                titles += " (" + tr("title_from", src=", ".join(PROVIDER_NAMES.get(p, p) for p in sorted(provs))) + ")"
            parts.append(titles)
    else:
        parts.append(tr("kind_movie"))
    parts.append(m.provider_name)
    return " · ".join(parts)


def same_series_targets(job: Job, prev, jobs: list[Job]) -> list[Job]:
    """Capítulos a los que se aplica «Usar esta misma serie para los demás capítulos».

    Todos los que aún no han empezado y son de la misma serie, estén identificados o no
    (antes solo los no identificados, y corregir una serie mal elegida obligaba a ir uno a uno).
    Es de la misma serie si su archivo trae el mismo nombre de serie o si se identificó con la
    misma serie que tenía este capítulo antes de corregirlo. Se respetan los capítulos que el
    usuario eligió a mano uno a uno.
    """
    key = normalize(job.rt.parsed.title)
    prev_id = (prev.provider, prev.id) if prev is not None else None
    out = []
    for other in jobs:
        if other is job or other.status != WAITING or other.rt is None or other.hand_pick:
            continue
        chosen = other.rt.chosen
        same_name = bool(key) and normalize(other.rt.parsed.title) == key
        same_show = prev_id is not None and chosen is not None and (chosen.provider, chosen.id) == prev_id
        if same_name or same_show:
            out.append(other)
    return out


class RenameController(QObject):
    identified = Signal(int, object)     # job_id, (estado, Resolution, subtítulos) | Exception
    chosen = Signal(int, object)         # job_id, (estado, Resolution) | Exception
    searched = Signal(int, object)       # token, SearchResponse | Exception
    renamed = Signal(object, object)     # job_ids, (plan, moves) | Exception
    rename_step = Signal(str, str)       # «copy» | «done», ruta original (avance de un lote)
    undone = Signal(object)              # RenameResult | Exception
    loaded = Signal(int, object)         # token, temporadas o capítulos | Exception

    def __init__(self, window):
        super().__init__(window)
        self.w = window
        self._lib: Library | None = None
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tuxenc-rename")
        # El diálogo de identificar usa su propio hilo: no espera detrás de la cola
        self.ui_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tuxenc-identify")
        self._tokens = itertools.count(1)
        self.busy = 0
        self.identified.connect(self._on_identified)
        self.rename_step.connect(self._on_rename_step)
        self.batch_total = 0               # avance del lote de renombrado en curso
        self.batch_done = 0
        self.batch_copying = False
        self._batch_jobs: dict[str, Job] = {}
        self.chosen.connect(self._on_chosen)

    # ------------------------------------------------------------------ básicos
    @property
    def lib(self) -> Library:
        if self._lib is None:
            self._lib = Library()
        return self._lib

    def destination(self) -> Destination:
        cfg = self.w.cfg
        mode = cfg.output_mode if cfg.output_mode in ("source", "folder", "library") else "source"
        return Destination(mode, cfg.output_folder, cfg.series_root, cfg.movie_root)

    def _submit(self, fn, *args):
        self.busy += 1

        def run():
            try:
                return fn(*args)
            finally:
                self.busy -= 1
        return self.pool.submit(run)

    # ------------------------------------------------------------------ identificar
    def identify(self, jobs: list[Job], force: bool = False) -> None:
        for job in jobs:
            if job.status != WAITING:
                continue
            if not force and job.ident in (OK, PENDING, AMBIGUOUS, NONE, ERROR, EPISODE):
                continue
            if job.rt is not None and getattr(job.rt, "manual", False) and not force:
                continue
            job.ident, job.note = PENDING, tr("id_pending")
            self._submit(self._identify_task, job.id, job.input)
            self.w.queue.update_job(job)

    def _identify_task(self, job_id: int, path: str) -> None:
        try:
            payload = self.lib.identify(path)
        except Exception as exc:  # noqa: BLE001
            payload = exc
        self.identified.emit(job_id, payload)

    def _apply(self, job: Job, state: str, res) -> None:
        self._apply_inner(job, state, res)
        self.w._refresh_controls()

    def _apply_inner(self, job: Job, state: str, res) -> None:
        job.ident, job.rt = state, res
        if state == OK:
            job.note = "✓ " + describe_match(res)
            if job.hold:
                self.w.engine.release(job.id)
        elif state == EPISODE:
            job.note = tr("id_episode", show=res.chosen.label)
        elif state == AMBIGUOUS:
            job.note = tr("id_ambiguous")
        elif state == NONE:
            job.note = tr("id_none")
        else:
            job.note = tr("id_error", err=res.new_name(self.lib.settings)[1] if res else "")
        self.update_preview(job)
        self.w.queue.update_job(job)

    def _on_identified(self, job_id: int, payload) -> None:
        job = self.w._job(job_id)
        if job is None:
            return
        if isinstance(payload, Exception):
            job.ident, job.note = ERROR, tr("id_error", err=str(payload))
            self.w.queue.update_job(job)
            return
        state, res, subs = payload
        job.companions = [str(s) for s in subs]
        self._apply(job, state, res)

    def _on_chosen(self, job_id: int, payload) -> None:
        job = self.w._job(job_id)
        if job is None:
            return
        if isinstance(payload, Exception):
            job.ident, job.note = ERROR, tr("id_error", err=str(payload))
            self.w.queue.update_job(job)
            return
        state, res = payload
        self._apply(job, state, res)

    # ------------------------------------------------------------------ vista previa
    def update_preview(self, job: Job) -> None:
        if job.ident != OK or job.rt is None or job.status in FINISHED:
            job.preview = ""
            return
        cfg = self.w.cfg
        if not job.staged and not job.task_rename:
            job.preview = ""
            return
        if (cfg.convert_on if job.staged else job.task_convert):
            st = job.settings or self.w.panel.settings
            resolution = predicted_resolution(job.info, st)
            ext = CONTAINERS[st.container]["ext"]
        else:
            resolution = job.info.std_resolution
            ext = job.rt.parsed.extension
        name, note = self.lib.relative_name(job.rt, resolution, ext)
        job.preview = name or ""
        if not name:
            job.note = "⚠ " + note

    def refresh_previews(self) -> None:
        for job in self.w.engine.jobs:
            self.update_preview(job)
        self.w.queue.sync(self.w.engine.jobs)

    # ------------------------------------------------------------------ elegir coincidencia
    def open_match(self, job: Job) -> None:
        if job.rt is None:
            from retitler.pipeline import analyze
            job.rt = analyze(job.input)
        dlg = MatchDialog(self, job, self.w)
        accepted = dlg.exec()
        match, same = dlg.result_match, dlg.same.isChecked() and not dlg.same.isHidden()  # ya cerrada: isVisible() sería False
        season, episodes = dlg.result_season, dlg.result_episodes
        self.searched.disconnect(dlg._on_searched)
        self.loaded.disconnect(dlg._on_loaded)
        dlg.deleteLater()
        if not accepted or match is None:
            return
        # Este vídeo: serie + capítulo elegido. Los demás de la misma serie: solo la serie
        # (cada uno conserva el capítulo de su nombre).
        prev = job.rt.chosen                       # la serie que tenía antes de corregirla
        job.hand_pick = bool(season is not None and episodes)
        job.ident, job.note = PENDING, tr("id_pending")
        self._submit(self._choose_task, job.id, job.rt, match, season, episodes)
        targets = [] if not same else same_series_targets(job, prev, self.w.engine.jobs)
        for t in targets:
            t.ident, t.note = PENDING, tr("id_pending")
            self._submit(self._choose_task, t.id, t.rt, match, None, None)
        self.w.queue.sync(self.w.engine.jobs)

    def _choose_task(self, job_id: int, res, match, season=None, episodes=None) -> None:
        try:
            payload = self.lib.choose(res, match, season, episodes)
        except Exception as exc:  # noqa: BLE001
            payload = exc
        self.chosen.emit(job_id, payload)

    def search(self, query: str, kind, year) -> int:
        token = next(self._tokens)

        def task():
            try:
                payload = self.lib.search(query, kind, year)
            except Exception as exc:  # noqa: BLE001
                payload = exc
            self.searched.emit(token, payload)
        self.ui_pool.submit(task)
        return token

    def _load(self, fn, *args) -> int:
        token = next(self._tokens)

        def task():
            try:
                payload = fn(*args)
            except Exception as exc:  # noqa: BLE001
                payload = exc
            self.loaded.emit(token, payload)
        self.ui_pool.submit(task)
        return token

    def load_seasons(self, match) -> int:
        return self._load(self.lib.seasons, match)

    def load_episodes(self, match, season: int) -> int:
        return self._load(self.lib.season_episodes, match, season)

    # ------------------------------------------------------------------ solo renombrar
    def rename_jobs(self, jobs: list[Job]) -> None:
        dest = self.destination()
        # La resolución ya se conoce desde que se añadió: no se vuelve a analizar cada vídeo
        items = [(Path(j.input), j.rt, [Path(s) for s in j.companions], j.info.std_resolution)
                 for j in jobs]
        ids = [j.id for j in jobs]
        for j in jobs:
            j.status = "preparing"
            j.rename_state = ""
        self._batch_jobs = {str(Path(j.input)): j for j in jobs}
        self.batch_total, self.batch_done, self.batch_copying = len(jobs), 0, False
        self.w.queue.sync(self.w.engine.jobs)
        self.w._refresh_controls()

        def task():
            try:
                payload = self.lib.rename_batch(
                    items, dest, progress=lambda ev, src: self.rename_step.emit(ev, str(src)))
            except Exception as exc:  # noqa: BLE001
                payload = exc
            self.renamed.emit(ids, payload)
        self._submit(task)

    def _on_rename_step(self, event: str, src: str) -> None:
        job = self._batch_jobs.get(src)
        if job is None:                      # un subtítulo acompañante: no tiene fila
            return
        if event == "copy":
            job.rename_state = "copying"
            self.batch_copying = True
        elif event == "done":
            job.rename_state = "moved"
            self.batch_done += 1
        self.w.queue.update_job(job)
        self.w._refresh_controls()

    def batch_finished(self) -> None:
        for j in self._batch_jobs.values():
            j.rename_state = ""
        self._batch_jobs = {}
        self.batch_total = self.batch_done = 0
        self.batch_copying = False

    def undo(self) -> None:
        def task():
            try:
                payload = self.lib.undo_last()
            except Exception as exc:  # noqa: BLE001
                payload = exc
            self.undone.emit(payload)
        self._submit(task)

    def can_undo(self) -> bool:
        try:
            return self.lib.can_undo()
        except Exception:  # noqa: BLE001
            return False

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.ui_pool.shutdown(wait=False, cancel_futures=True)


class MatchDialog(QDialog):
    """Identificar un vídeo: elegir serie o película y, en las series, el capítulo con un clic."""

    def __init__(self, ctrl: RenameController, job: Job, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.job = job
        self.result_match = None
        self.result_season: int | None = None
        self.result_episodes: tuple[int, ...] | None = None
        self._search_token = self._season_token = self._eps_token = 0
        self._current = None
        res = job.rt
        p = res.parsed
        self.want_season = p.season
        self.want_eps = tuple(p.episodes)
        self.setWindowTitle(tr("match_title", name=job.name))
        self.resize(1180, 720)
        self.setMinimumSize(900, 560)
        lay = QVBoxLayout(self)

        guess = p.title or "?"
        if p.year:
            guess += f" ({p.year})"
        if p.season is not None and p.episodes:
            guess += f" · S{p.season:02}E" + "-".join(f"{e:02}" for e in p.episodes)
        head = QLabel(f"<b>{job.name}</b><br>" + tr("match_guess", guess=guess))
        head.setTextFormat(Qt.RichText)
        head.setWordWrap(True)
        lay.addWidget(head)

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        lay.addWidget(split, 1)

        # ------------------------------------------------ izquierda: ¿qué es?
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 6, 0)
        ll.addWidget(_section_label(tr("match_step1")))
        row = QHBoxLayout()
        self.query = QLineEdit(p.title)
        self.query.setPlaceholderText(tr("match_query_ph"))
        self.query.setToolTip(tr("match_query_tip"))
        self.query.returnPressed.connect(self._search)
        self.kind = QComboBox()
        self.kind.addItem(tr("match_kind_auto"), None)
        self.kind.addItem(tr("match_kind_series"), MediaKind.EPISODE)
        self.kind.addItem(tr("match_kind_movie"), MediaKind.MOVIE)
        if p.kind is MediaKind.EPISODE:
            self.kind.setCurrentIndex(1)
        elif p.kind is MediaKind.MOVIE:
            self.kind.setCurrentIndex(2)
        self.year = QSpinBox()
        self.year.setRange(0, 2100)
        self.year.setSpecialValueText(tr("match_any_year"))
        self.year.setValue(p.year or 0)
        self.year.setToolTip(tr("match_year_tip"))
        btn = QPushButton("🔎 " + tr("match_search"))
        btn.clicked.connect(self._search)
        row.addWidget(self.query, 1)
        row.addWidget(self.kind)
        row.addWidget(self.year)
        row.addWidget(btn)
        ll.addLayout(row)
        self.list = QListWidget()
        self.list.setObjectName("TrackList")
        self.list.currentItemChanged.connect(self._on_result)
        self.list.itemDoubleClicked.connect(lambda *_: self._accept())
        ll.addWidget(self.list, 1)
        self.status = QLabel()
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        ll.addWidget(self.status)
        credit = QLabel(tr("match_credits"))
        credit.setObjectName("Muted")
        credit.setStyleSheet("font-size: 11px;")
        ll.addWidget(credit)
        split.addWidget(left)

        # ------------------------------------------------ derecha: ¿qué capítulo?
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 0, 0, 0)
        rl.addWidget(_section_label(tr("match_step2")))
        srow = QHBoxLayout()
        srow.addWidget(QLabel(tr("match_season")))
        self.season = QComboBox()
        self.season.setMinimumWidth(160)
        self.season.currentIndexChanged.connect(self._on_season)
        srow.addWidget(self.season)
        srow.addStretch(1)
        rl.addLayout(srow)
        self.eps = QListWidget()
        self.eps.setObjectName("TrackList")
        self.eps.setSelectionMode(QListWidget.ExtendedSelection)
        self.eps.itemSelectionChanged.connect(self._update_choice)
        self.eps.itemDoubleClicked.connect(lambda *_: self._accept())
        rl.addWidget(self.eps, 1)
        hint = QLabel(tr("match_eps_hint"))
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        rl.addWidget(hint)
        man = QHBoxLayout()
        self.manual = QCheckBox(tr("match_manual"))
        self.manual.toggled.connect(self._update_choice)
        self.m_season = QSpinBox()
        self.m_season.setRange(0, 99)
        self.m_season.setPrefix(tr("match_s_prefix"))
        self.m_ep = QSpinBox()
        self.m_ep.setRange(1, 999)
        self.m_ep.setPrefix(tr("match_e_prefix"))
        self.m_season.setValue(p.season if p.season is not None else 1)
        self.m_ep.setValue(p.episodes[0] if p.episodes else 1)
        for w in (self.m_season, self.m_ep):
            w.valueChanged.connect(self._update_choice)
        man.addWidget(self.manual)
        man.addWidget(self.m_season)
        man.addWidget(self.m_ep)
        man.addStretch(1)
        rl.addLayout(man)
        self.movie_note = QLabel(tr("match_movie_note"))
        self.movie_note.setObjectName("Muted")
        self.movie_note.setWordWrap(True)
        self.movie_note.setAlignment(Qt.AlignCenter)
        rl.addWidget(self.movie_note)
        self.right = right
        split.addWidget(right)
        split.setSizes([560, 560])

        # ------------------------------------------------ abajo
        self.choice = QLabel()
        self.choice.setWordWrap(True)
        self.choice.setStyleSheet("font-weight: 600;")
        lay.addWidget(self.choice)
        self.same = QCheckBox(tr("match_same"))
        self.same.setChecked(True)
        self.same.setVisible(False)
        lay.addWidget(self.same)
        bb = QDialogButtonBox()
        self.ok = bb.addButton(tr("match_use"), QDialogButtonBox.AcceptRole)
        self.ok.setObjectName("Primary")
        bb.addButton(tr("cancel"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        ctrl.searched.connect(self._on_searched)
        ctrl.loaded.connect(self._on_loaded)
        candidates = list(res.candidates)
        if res.chosen is not None and res.chosen not in candidates:
            candidates.insert(0, res.chosen)
        self._fill(candidates, select=res.chosen)
        if not candidates:
            self._search()
        self._update_choice()

    # ------------------------------------------------------------------ resultados
    def _fill(self, results, select=None) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for r in results:
            kind = tr("kind_series") if r.kind is ResultKind.SERIES else tr("kind_movie")
            text = f"{r.label}   ·   {kind}   ·   {r.provider_name}"
            if r.score:
                text += f"   ·   {min(r.score, 1.0) * 100:.0f}%"
            if r.original_title and r.original_title != r.title:
                text += f"\n      {r.original_title}"
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, r)
            if r.overview:
                it.setToolTip(r.overview[:500])
            self.list.addItem(it)
        self.list.blockSignals(False)
        if results:
            idx = results.index(select) if select in results else 0
            self.list.setCurrentRow(idx)
            self.status.setText("")
        else:
            self._on_result(None, None)
            self.status.setText(tr("match_none"))

    def _search(self) -> None:
        q = self.query.text().strip()
        if not q:
            return
        self.status.setText(tr("match_searching"))
        self.list.clear()
        self._search_token = self.ctrl.search(q, self.kind.currentData(), self.year.value() or None)

    def _on_searched(self, token: int, payload) -> None:
        if token != self._search_token:
            return
        if isinstance(payload, Exception):
            self.status.setText("⚠ " + str(payload))
            return
        self._fill(payload.results)
        if payload.warnings:
            self.status.setText("⚠ " + " ".join(payload.warnings))

    def _on_result(self, item, _prev=None) -> None:
        r = item.data(Qt.UserRole) if item is not None else None
        self._current = r
        series = r is not None and r.kind is ResultKind.SERIES
        for w in (self.season, self.eps, self.manual, self.m_season, self.m_ep):
            w.setEnabled(series)
        self.movie_note.setVisible(r is not None and not series)
        self.same.setVisible(series)
        self.season.blockSignals(True)
        self.season.clear()
        self.season.blockSignals(False)
        self.eps.clear()
        if series:
            self.season.addItem(tr("match_loading"), None)
            self._season_token = self.ctrl.load_seasons(r)
        self._update_choice()

    # ------------------------------------------------------------------ temporadas y capítulos
    def _on_loaded(self, token: int, payload) -> None:
        if token == self._season_token:
            self._seasons_ready(payload)
        elif token == self._eps_token:
            self._episodes_ready(payload)

    def _seasons_ready(self, payload) -> None:
        self.season.blockSignals(True)
        self.season.clear()
        if isinstance(payload, Exception) or not payload:
            self.season.addItem(tr("match_no_seasons"), None)
            self.season.blockSignals(False)
            self.manual.setChecked(True)
            if isinstance(payload, Exception):
                self.status.setText("⚠ " + str(payload))
            self._update_choice()
            return
        for n in payload:
            self.season.addItem(tr("match_specials") if n == 0 else tr("match_season_n", n=n), n)
        # La temporada del nombre del archivo; si no hay, la más reciente (lo normal en estrenos)
        regular = [n for n in payload if n > 0]
        want = self.want_season if self.want_season in payload else (regular[-1] if regular
                                                                      else payload[0])
        self.season.setCurrentIndex(max(0, self.season.findData(want)))
        self.season.blockSignals(False)
        self._on_season()

    def _on_season(self, *_):
        n = self.season.currentData()
        self.eps.clear()
        if n is None or self._current is None:
            return
        it = QListWidgetItem(tr("match_loading"))
        it.setFlags(Qt.NoItemFlags)
        self.eps.addItem(it)
        self._eps_token = self.ctrl.load_episodes(self._current, n)

    def _episodes_ready(self, payload) -> None:
        self.eps.blockSignals(True)
        self.eps.clear()
        if isinstance(payload, Exception) or not payload:
            it = QListWidgetItem("⚠ " + (str(payload) if isinstance(payload, Exception)
                                         else tr("match_no_eps")))
            it.setFlags(Qt.NoItemFlags)
            self.eps.addItem(it)
            self.eps.blockSignals(False)
            self._update_choice()
            return
        season = self.season.currentData()
        for e in payload:
            title = e.title if e.title and not e.provisional else tr("match_no_title")
            text = f"E{e.number:02}   {title}"
            if e.air_date:
                text += f"   ·   {e.air_date}"
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, e.number)
            self.eps.addItem(it)
            if season == self.want_season and e.number in self.want_eps:
                it.setSelected(True)
                self.eps.scrollToItem(it)
        self.eps.blockSignals(False)
        self._update_choice()

    # ------------------------------------------------------------------ resumen y aceptar
    def _picked(self) -> tuple[int | None, tuple[int, ...]]:
        if self.manual.isChecked():
            return self.m_season.value(), (self.m_ep.value(),)
        eps = tuple(sorted(i.data(Qt.UserRole) for i in self.eps.selectedItems()
                           if i.data(Qt.UserRole) is not None))
        return self.season.currentData(), eps

    def _update_choice(self, *_):
        r = self._current
        for w in (self.m_season, self.m_ep):
            w.setEnabled(self.manual.isChecked() and r is not None and r.kind is ResultKind.SERIES)
        self.eps.setEnabled(not self.manual.isChecked() and r is not None
                            and r.kind is ResultKind.SERIES)
        if r is None:
            self.choice.setText(tr("match_pick_first"))
            self.ok.setEnabled(False)
            return
        if r.kind is not ResultKind.SERIES:
            self.choice.setText("→ " + f"{r.label} · {tr('kind_movie')}")
            self.ok.setEnabled(True)
            return
        season, eps = self._picked()
        if season is None or not eps:
            self.choice.setText(tr("match_pick_episode", show=r.label))
            self.ok.setEnabled(False)
            return
        code = f"S{season:02}E" + "-".join(f"{e:02}" for e in eps)
        self.choice.setText("→ " + f"{r.label} · {code}")
        self.ok.setEnabled(True)

    def _accept(self) -> None:
        if not self.ok.isEnabled() or self._current is None:
            return
        self.result_match = self._current
        if self._current.kind is ResultKind.SERIES:
            self.result_season, self.result_episodes = self._picked()
        self.accept()


def _section_label(text: str) -> QLabel:
    lb = QLabel(text)
    lb.setObjectName("SectionTitle")
    return lb


def env_has_keys() -> bool:
    return bool(os.environ.get("TMDB_API_KEY") or os.environ.get("OMDB_API_KEY"))
