"""Ventana principal de TuxEnc."""

from __future__ import annotations

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
                               QInputDialog, QLabel, QMainWindow, QMenu, QMessageBox,
                               QProgressBar, QPushButton, QSizePolicy, QSplitter, QStackedWidget,
                               QToolButton, QVBoxLayout, QWidget)

from .. import APP_NAME, VERSION, i18n, integration
from ..catalog import (AUDIO_CODECS, CONTAINERS, VIDEO_ENCODERS, EncodeSettings,
                       encoder, lang_name)
from ..config import Config
from ..engine import (ACTIVE, DONE, FAILED, FINISHED, WAITING, Job, QueueEngine,
                      auto_parallel, cpu_count, default_output)
from ..hw import detect_available
from ..i18n import current as ui_lang, tr, tr_in
from ..paths import ASSETS_DIR, clean_env
from ..presets import (Preset, builtin_presets, import_handbrake, load_user_presets,
                       save_user_presets)
from ..probe import VIDEO_EXTENSIONS, ProbeError, probe
from . import theme
from .dialogs import (CountdownDialog, LogDialog, PreferencesDialog,
                      TracksDialog)
from .queue_view import DropZone, QueueList, job_menu
from .rename_ctrl import RenameController
from .settings_panel import SettingsPanel
from ..library import OK as ID_OK, free_name, predicted_resolution


class Bridge(QObject):
    job_updated = Signal(object)
    queue_done = Signal(object)
    probed = Signal(str, object)
    hw_ready = Signal(object)
    decided = Signal(int, object)


def _open_path(path: str) -> None:
    """Abre con la aplicación predeterminada, con el entorno limpio (fuera del AppImage)."""
    try:
        subprocess.Popen(["xdg-open", path], env=clean_env(), start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))


class MainWindow(QMainWindow):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.restart_request: tuple[str | None, list[str]] | None = None
        self.available: list[str] | None = None
        self.bridge = Bridge()
        self.engine = QueueEngine(on_update=self.bridge.job_updated.emit,
                                  on_queue_done=self.bridge.queue_done.emit)
        self.engine.settings_provider = lambda: self.panel.settings
        self.engine.output_resolver = self._resolve_output
        self.engine.post_process = self._post_process
        self.engine.cleanup = self._cleanup_failed
        self.engine.set_parallel(cfg.parallel or auto_parallel())
        self.engine.low_priority = cfg.low_priority
        self.prober = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tuxenc-probe")
        self.pending_probes = 0
        self._order_seq = 1e9
        self.failed_probes: list[str] = []
        self.user_stopped = False
        self.presets: list[Preset] = []
        self.current_key = cfg.last_preset

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(ASSETS_DIR / "tuxenc-256.png")))
        self.setAcceptDrops(True)
        self.resize(1180, 720)
        self.setMinimumSize(820, 520)

        self._build()
        self.rename = RenameController(self)
        self.rename.renamed.connect(self._on_renamed)
        self.rename.undone.connect(self._on_undone)
        self.bridge.job_updated.connect(self._on_job_updated)
        self.bridge.queue_done.connect(self._on_queue_done)
        self.bridge.probed.connect(self._on_probed)
        self.bridge.hw_ready.connect(self._on_hw_ready)
        self.bridge.decided.connect(self._on_decided)

        self._reload_presets()
        self.panel.load(cfg.encode_settings())
        self._select_preset_key(self.current_key, apply=not cfg.settings)
        self._refresh_summary()
        self._refresh_controls()

        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._refresh_controls)
        self.ui_timer.start(700)

        if cfg.geometry:
            try:
                self.restoreGeometry(bytes.fromhex(cfg.geometry))
            except ValueError:
                pass
        self.set_advanced_visible(cfg.advanced_open)
        self._apply_modes()
        self._start_hw_detection()

    # ================================================================== construcción
    def _build(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- cabecera
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 12, 16, 8)
        hl.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(QPixmap(str(ASSETS_DIR / "tuxenc-64.png")).scaled(
            36, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        title = QLabel(APP_NAME)
        title.setObjectName("Title")
        hl.addWidget(logo)
        hl.addWidget(title)
        hl.addSpacing(8)

        self.add_btn = QToolButton()
        self.add_btn.setText("＋ " + tr("add"))
        self.add_btn.setPopupMode(QToolButton.InstantPopup)
        add_menu = QMenu(self.add_btn)
        add_menu.addAction(tr("add_files"), self.add_files_dialog)
        add_menu.addAction(tr("add_folder"), self.add_folder_dialog)
        self.add_btn.setMenu(add_menu)
        hl.addWidget(self.add_btn)
        self.clear_btn = QToolButton()
        self.clear_btn.setText("🧹 " + tr("clear_menu"))
        self.clear_btn.setToolTip(tr("clear_menu_tip"))
        self.clear_btn.setPopupMode(QToolButton.InstantPopup)
        self.clear_menu = QMenu(self.clear_btn)
        self.clear_menu.aboutToShow.connect(self._fill_clear_menu)
        self.clear_btn.setMenu(self.clear_menu)
        hl.addWidget(self.clear_btn)
        hl.addStretch(1)

        self.preset_combo = QComboBox()
        self.preset_combo.setObjectName("PresetCombo")
        self.preset_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.preset_combo.setMinimumContentsLength(18)
        self.preset_combo.setMinimumWidth(200)
        self.preset_combo.setMaximumWidth(380)
        self.preset_combo.setToolTip(tr("preset"))
        self.preset_combo.activated.connect(self._on_preset_chosen)
        hl.addWidget(self.preset_combo, 1)
        self.preset_menu_btn = QToolButton()
        self.preset_menu_btn.setText("⋯")
        self.preset_menu_btn.setPopupMode(QToolButton.InstantPopup)
        pm = QMenu(self.preset_menu_btn)
        pm.addAction(tr("preset_save"), self._save_preset)
        self.delete_preset_act = pm.addAction(tr("preset_delete"), self._delete_preset)
        pm.addSeparator()
        pm.addAction(tr("preset_import"), self._import_handbrake)
        pm.addAction(tr("preset_export"), self._export_presets)
        self.preset_menu_btn.setMenu(pm)
        hl.addWidget(self.preset_menu_btn)

        self.adv_btn = QToolButton()
        self.adv_btn.setText("⚙ " + tr("settings"))
        self.adv_btn.setCheckable(True)
        self.adv_btn.toggled.connect(self.set_advanced_visible)
        hl.addWidget(self.adv_btn)
        prefs = QToolButton()
        prefs.setText("☰")
        prefs.setToolTip(tr("preferences"))
        prefs.clicked.connect(self._open_prefs)
        hl.addWidget(prefs)
        root.addWidget(header)

        # ---- resumen de ajustes (clic = abrir panel)
        self.summary = QPushButton()
        self.summary.setObjectName("SummaryBtn")
        self.summary.setFlat(True)
        self.summary.setCursor(Qt.PointingHandCursor)
        self.summary.setStyleSheet(
            f"QPushButton#SummaryBtn {{ background: transparent; border: none; color: {theme.MUTED};"
            " text-align: left; padding: 0 16px 8px 62px; }"
            f"QPushButton#SummaryBtn:hover {{ color: {theme.TEXT}; }}")
        self.summary.clicked.connect(lambda: self.adv_btn.setChecked(not self.adv_btn.isChecked()))
        self.summary.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.summary.setStyleSheet(self.summary.styleSheet().replace("padding: 0 16px 8px 62px",
                                                                     "padding: 0 8px 0 4px"))
        modes = QHBoxLayout()
        modes.setContentsMargins(16, 0, 16, 8)
        modes.setSpacing(6)
        self.conv_btn = QToolButton()
        self.conv_btn.setText("🎞  " + tr("mode_convert"))
        self.conv_btn.setToolTip(tr("mode_convert_tip"))
        self.conv_btn.setCheckable(True)
        self.ren_btn = QToolButton()
        self.ren_btn.setText("🏷  " + tr("mode_rename"))
        self.ren_btn.setToolTip(tr("mode_rename_tip"))
        self.ren_btn.setCheckable(True)
        for b in (self.conv_btn, self.ren_btn):
            b.setObjectName("Mode")
        self.conv_btn.setChecked(self.cfg.convert_on)
        self.ren_btn.setChecked(self.cfg.rename_on)
        self.conv_btn.toggled.connect(self._on_mode_convert)
        self.ren_btn.toggled.connect(self._on_mode_rename)
        self.undo_btn = QToolButton()
        self.undo_btn.setText("↶ " + tr("undo_rename"))
        self.undo_btn.setToolTip(tr("undo_rename_tip"))
        self.undo_btn.clicked.connect(self._undo_rename)
        modes.addWidget(self.conv_btn)
        modes.addWidget(self.ren_btn)
        modes.addWidget(self.undo_btn)
        modes.addSpacing(8)
        modes.addWidget(self.summary, 1)
        root.addLayout(modes)

        # Barra de avisos (claves, biblioteca…)
        self.bar = QFrame()
        self.bar.setObjectName("InfoBar")
        self.bar.setStyleSheet("QFrame#InfoBar { background: #2a2a1c; border: 1px solid #5a5328;"
                               " border-radius: 8px; }")
        bl = QHBoxLayout(self.bar)
        bl.setContentsMargins(12, 6, 8, 6)
        self.bar_lbl = QLabel()
        self.bar_lbl.setWordWrap(True)
        self.bar_btn = QPushButton()
        self.bar_btn.clicked.connect(self._on_bar_action)
        self.bar_close = QToolButton()
        self.bar_close.setObjectName("Flat")
        self.bar_close.setText(tr("bar_dismiss"))
        self.bar_close.clicked.connect(self._dismiss_bar)
        bl.addWidget(self.bar_lbl, 1)
        bl.addWidget(self.bar_btn)
        bl.addWidget(self.bar_close)
        bar_wrap = QHBoxLayout()
        bar_wrap.setContentsMargins(16, 0, 16, 8)
        bar_wrap.addWidget(self.bar)
        root.addLayout(bar_wrap)
        self.bar.setVisible(False)
        self._bar_kind = ""
        self._bar_dismissed: set[str] = set()

        # ---- cuerpo: cola + panel
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, 4, 8, 12)
        self.stack = QStackedWidget()
        self.drop = DropZone()
        self.drop.add_files.connect(self.add_files_dialog)
        self.drop.add_folder.connect(self.add_folder_dialog)
        self.queue = QueueList()
        self.queue.row_action.connect(self._on_row_action)
        self.stack.addWidget(self.drop)
        self.stack.addWidget(self.queue)
        ll.addWidget(self.stack)
        self.splitter.addWidget(left)

        self.panel_wrap = QFrame()
        self.panel_wrap.setObjectName("Card")
        pw = QVBoxLayout(self.panel_wrap)
        pw.setContentsMargins(4, 4, 4, 4)
        self.panel = SettingsPanel()
        self.panel.changed.connect(self._on_settings_changed)
        pw.addWidget(self.panel)
        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(8, 4, 16, 12)
        sl.addWidget(self.panel_wrap)
        self.side = side
        self.side.setMinimumWidth(400)
        self.splitter.addWidget(side)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        root.addWidget(self.splitter, 1)

        # ---- pie
        footer = QFrame()
        footer.setObjectName("Footer")
        fl = QVBoxLayout(footer)
        fl.setContentsMargins(16, 10, 16, 12)
        fl.setSpacing(8)
        prog_row = QHBoxLayout()
        prog_row.setSpacing(8)
        self.status_lbl = QLabel()
        self.status_lbl.setObjectName("Muted")
        self.total_bar = QProgressBar()
        self.total_bar.setRange(0, 1000)
        self.total_bar.setTextVisible(False)
        self.total_bar.setFixedHeight(8)
        self.stop_btn = QPushButton("■  " + tr("stop"))
        self.stop_btn.clicked.connect(self._stop)
        self.pause_btn = QPushButton("⏸  " + tr("pause"))
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.start_btn = QPushButton("▶  " + tr("start"))
        self.start_btn.setObjectName("Primary")
        self.start_btn.clicked.connect(self._start)
        prog_row.addWidget(self.status_lbl)
        prog_row.addWidget(self.total_bar, 1)
        prog_row.addSpacing(8)
        prog_row.addWidget(self.stop_btn)
        prog_row.addWidget(self.pause_btn)
        prog_row.addWidget(self.start_btn)
        fl.addLayout(prog_row)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel(tr("output")))
        self.out_combo = QComboBox()
        self.out_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.out_combo.setMinimumContentsLength(16)
        self.out_combo.setMinimumWidth(180)
        self.out_combo.activated.connect(self._on_output_chosen)
        row.addWidget(self.out_combo, 1)
        row.addSpacing(12)
        row.addWidget(QLabel(tr("parallel")))
        self.par_combo = QComboBox()
        self.par_combo.addItem(tr("parallel_auto", n=auto_parallel()), 0)
        for n in range(1, max(8, min(16, cpu_count() // 2)) + 1):
            self.par_combo.addItem(str(n), n)
        idx = self.par_combo.findData(self.cfg.parallel)
        self.par_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.par_combo.setToolTip(tr("parallel_tip", cores=cpu_count()))
        self.par_combo.currentIndexChanged.connect(
            lambda _i: self._on_parallel(self.par_combo.currentData()))
        row.addWidget(self.par_combo)
        self.prio_chk = QCheckBox(tr("low_prio"))
        self.prio_chk.setChecked(self.cfg.low_priority)
        self.prio_chk.setToolTip(tr("low_prio_tip"))
        self.prio_chk.toggled.connect(self._on_priority)
        row.addSpacing(6)
        row.addWidget(self.prio_chk)
        row.addSpacing(12)
        row.addWidget(QLabel(tr("when_done")))
        self.end_combo = QComboBox()
        for k in ("nothing", "notify", "quit", "suspend", "shutdown"):
            self.end_combo.addItem(tr(f"end_{k}"), k)
        self.end_combo.setCurrentIndex(max(0, self.end_combo.findData(self.cfg.end_action)))
        self.end_combo.currentIndexChanged.connect(self._on_end_action)
        row.addWidget(self.end_combo)
        row.addStretch(2)
        fl.addLayout(row)
        root.addWidget(footer)
        self._fill_output_combo()

    # ================================================================== presets
    def _reload_presets(self) -> None:
        self.presets = builtin_presets(ui_lang(), self.available) + load_user_presets()
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        builtin = [p for p in self.presets if p.builtin]
        user = [p for p in self.presets if not p.builtin]
        for p in builtin:
            self.preset_combo.addItem(p.name, p.key)
        if user:
            self.preset_combo.insertSeparator(self.preset_combo.count())
            for p in user:
                self.preset_combo.addItem("★ " + p.name, p.key)
        self.preset_combo.blockSignals(False)
        self._select_preset_key(self.current_key, apply=False)

    def _preset(self, key: str) -> Preset | None:
        return next((p for p in self.presets if p.key == key), None)

    def _select_preset_key(self, key: str, apply: bool) -> None:
        i = self.preset_combo.findData(key)
        if i < 0:
            return
        self.preset_combo.setCurrentIndex(i)
        self.current_key = key
        if apply:
            p = self._preset(key)
            if p:
                self.panel.load(self._adapt(p.settings))
        self._refresh_summary()

    def _adapt(self, s: EncodeSettings) -> EncodeSettings:
        """Si el preset pide una GPU que no hay, usar el equivalente por CPU."""
        s = s.copy()
        if self.available is None or s.video_encoder in self.available:
            return s
        wanted = encoder(s.video_encoder)
        alt = next((e for e in VIDEO_ENCODERS if not e.hw and e.codec == wanted.codec
                    and e.id in self.available), encoder("libx264"))
        from ..hw import REASONS
        why = REASONS.get(wanted.id) or tr("why_unknown")
        QMessageBox.information(self, APP_NAME, tr("preset_hw_missing", enc=wanted.label,
                                                   alt=alt.label, why=why))
        s.video_encoder = alt.id
        s.quality = alt.q_default
        s.speed_preset = alt.preset_default
        s.validate()
        return s

    def _on_preset_chosen(self, idx: int) -> None:
        key = self.preset_combo.itemData(idx)
        if key:
            self.current_key = key
            self.cfg.last_preset = key
            p = self._preset(key)
            if p:
                self.panel.load(self._adapt(p.settings))
            self._on_settings_changed()

    def _is_modified(self) -> bool:
        p = self._preset(self.current_key)
        return p is None or p.settings.to_dict() != self.panel.settings.to_dict()

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(self, tr("preset_save"), tr("preset_name"))
        name = name.strip()
        if not ok or not name:
            return
        users = load_user_presets()
        if any(p.name == name for p in users):
            if QMessageBox.question(self, APP_NAME, tr("preset_exists")) != QMessageBox.Yes:
                return
            users = [p for p in users if p.name != name]
        users.append(Preset(f"user:{name}", name, self.panel.settings.copy()))
        save_user_presets(users)
        self.current_key = f"user:{name}"
        self.cfg.last_preset = self.current_key
        self._reload_presets()
        self._refresh_summary()

    def _delete_preset(self) -> None:
        p = self._preset(self.current_key)
        if not p or p.builtin:
            return
        if QMessageBox.question(self, APP_NAME, tr("preset_delete_q", name=p.name)) != QMessageBox.Yes:
            return
        save_user_presets([u for u in load_user_presets() if u.name != p.name])
        self.current_key = "builtin:hevc_quality"
        self._reload_presets()
        self._refresh_summary()

    def _import_handbrake(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("preset_import"), str(Path.home()),
                                              "HandBrake (*.json);;" + tr("all_files") + " (*)")
        if not path:
            return
        try:
            imported = import_handbrake(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, APP_NAME, tr("preset_import_fail", err=str(exc)))
            return
        users = load_user_presets()
        names = {p.name for p in imported}
        users = [u for u in users if u.name not in names] + imported
        save_user_presets(users)
        if imported:
            self.current_key = imported[0].key
        self._reload_presets()
        if imported:
            self._select_preset_key(imported[0].key, apply=True)
            self._on_settings_changed()
        QMessageBox.information(self, APP_NAME, tr("preset_imported", n=len(imported)))

    def _export_presets(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, tr("preset_export"),
                                              str(Path.home() / "tuxenc-presets.json"),
                                              "JSON (*.json)")
        if not path:
            return
        import json
        data = [{"name": p.name, "settings": p.settings.to_dict()} for p in load_user_presets()]
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # ================================================================== ajustes
    def _on_settings_changed(self) -> None:
        self.cfg.settings = self.panel.settings.to_dict()
        self._refresh_summary()
        if self.cfg.rename_on and hasattr(self, "rename"):
            self.rename.refresh_previews()

    def _refresh_summary(self) -> None:
        s = self.panel.settings
        enc = encoder(s.video_encoder)
        if s.rate_mode == "cq":
            q = f"{enc.q_label} {s.quality}"
        else:
            q = f"{s.bitrate} kbps" + (" · 2p" if s.two_pass else "")
            q = ("ABR " if s.rate_mode == "abr" else "CBR ") + q
        where = tr("uses_gpu") if enc.hw else tr("uses_cpu")
        parts = [CONTAINERS[s.container]["label"], f"{enc.label} [{where}]", q]
        if s.bit_depth == 10:
            parts.append("10 bit")
        if s.max_height:
            parts.append(f"≤{s.max_height}p" + (" ↑" if s.allow_upscale else ""))
        ui = ui_lang()
        if s.audio_mode == "none":
            parts.append("♪ —")
        else:
            a = tr("audio_copy").split(" (")[0] if s.audio_codec == "copy" else \
                AUDIO_CODECS[s.audio_codec]["label"].split(" ")[0]
            langs = ", ".join(lang_name(x, ui) for x in s.audio_langs[:3]) \
                if s.audio_mode in ("first", "lang_all") else tr("a_all")
            parts.append(f"♪ {a} ({langs})")
        if s.sub_mode != "none":
            langs = ", ".join(s.sub_langs[:3]) if s.sub_mode != "all" else tr("s_all")
            parts.append(f"CC {langs}")
        modified = self._is_modified()
        tail = f"    ✎ ({tr('modified')})" if modified else "    ✎"
        self.summary.setText("   ·   ".join(parts) + tail)
        p = self._preset(self.current_key)
        self.delete_preset_act.setEnabled(bool(p and not p.builtin))

    def set_advanced_visible(self, on: bool) -> None:
        self.side.setVisible(on)
        self.adv_btn.blockSignals(True)
        self.adv_btn.setChecked(on)
        self.adv_btn.blockSignals(False)
        self.cfg.advanced_open = on

    # ================================================================== salida / opciones
    def _fill_output_combo(self) -> None:
        self.out_combo.blockSignals(True)
        self.out_combo.clear()
        self.out_combo.addItem(tr("out_source"), "source")
        if self.cfg.output_folder:
            parts = Path(self.cfg.output_folder).parts
            short = os.path.join("…", *parts[-2:]) if len(parts) > 3 else self.cfg.output_folder
            self.out_combo.addItem("📁 " + short, "folder")
            self.out_combo.setToolTip(self.cfg.output_folder)
            self.out_combo.setItemData(self.out_combo.count() - 1, self.cfg.output_folder,
                                       Qt.ToolTipRole)
        if self.cfg.rename_on:
            self.out_combo.addItem(tr("out_library"), "library")
        self.out_combo.addItem(tr("out_choose"), "choose")
        self.out_combo.setCurrentIndex(max(0, self.out_combo.findData(self.cfg.output_mode)))
        self.out_combo.blockSignals(False)

    def _on_output_chosen(self, idx: int) -> None:
        data = self.out_combo.itemData(idx)
        if data == "choose":
            start = self.cfg.output_folder or str(Path.home())
            folder = QFileDialog.getExistingDirectory(self, tr("choose_folder"), start)
            if folder:
                self.cfg.output_folder = folder
                self.cfg.output_mode = "folder"
        elif data == "library" and not (self.cfg.series_root and self.cfg.movie_root):
            self.cfg.output_mode = "library"
            self._open_prefs(tab="rename")
            if not (self.cfg.series_root and self.cfg.movie_root):
                self.cfg.output_mode = "source"
        else:
            self.cfg.output_mode = data
        self._fill_output_combo()
        self._after_rename_settings()

    def _resolve_output(self, job: Job, st: EncodeSettings) -> str:
        job.rename = False
        if self.cfg.rename_on and job.ident == ID_OK and job.rt is not None:
            dest = self.rename.destination()
            ext = CONTAINERS[st.container]["ext"]
            target, _note = self.rename.lib.target(Path(job.input), job.rt, dest,
                                                   predicted_resolution(job.info, st), ext)
            if target is not None:
                reserved = self.engine.reserved_outputs(job.id)
                cand = free_name(target)
                n = 2
                while str(cand) in reserved:
                    n += 1
                    cand = free_name(target.with_name(f"{target.stem} ({n}){target.suffix}"))
                job.rename, job.dest = True, dest
                job.metadata = self.rename.lib.metadata(job.rt)
                return str(cand)
        folder = self.cfg.output_folder if self.cfg.output_mode == "folder" else None
        if folder and not os.access(folder, os.W_OK):
            folder = None
        if folder is None and not os.access(os.path.dirname(job.input) or ".", os.W_OK):
            from ..paths import videos_dir
            folder = str(videos_dir())
        return default_output(job, st, folder, self.engine.reserved_outputs(job.id))

    def _post_process(self, job: Job) -> None:
        """Hilo del trabajo: nombre final exacto, subtítulos externos y original (si se renombra)."""
        if not job.rename or job.rt is None or job.dest is None:
            return
        warns = self.rename.lib.finalize_converted(job, job.rt, job.dest, job.settings.container,
                                                   self.cfg.original_after)
        if warns:
            job.warning = "; ".join(warns)

    def _decide_bigger(self, job: Job, action: str) -> None:
        """El convertido ocupa más que el original: el usuario elige con cuál quedarse."""
        if action == "keep_both":
            job.decision = "both"
            self.queue.sync(self.engine.jobs)
            return
        lib, dest = self.rename.lib, job.dest

        def task():
            try:
                if action == "use_conv":
                    warns = lib.use_converted(job)
                else:
                    warns = lib.use_original(job, dest)
            except Exception as exc:  # noqa: BLE001
                warns = [str(exc)]
            self.bridge.decided.emit(job.id, (action, warns))
        self.rename._submit(task)

    def _on_decided(self, job_id: int, payload) -> None:
        job = self._job(job_id)
        if job is None:
            return
        action, warns = payload
        if warns:
            QMessageBox.warning(self, APP_NAME, tr("bigger_fail", err="\n".join(warns)))
        else:
            job.decision = "original" if action == "use_orig" else "converted"
            if action == "use_orig":
                job.out_size = job.info.size
                if job.rename:
                    job.renamed_to = job.output
        self.queue.sync(self.engine.jobs)

    def _cleanup_failed(self, job: Job) -> None:
        """Tras un fallo o cancelación: quitar las carpetas vacías que se crearon para el resultado."""
        if not job.rename or job.dest is None or not job.output or job.rt is None:
            return
        from ..library import _remove_empty_dirs
        kind = job.rt.chosen.kind if job.rt.chosen else None
        base = job.dest.base_for(Path(job.input), kind) or Path(job.input).parent
        _remove_empty_dirs(Path(job.output).parent, stop_at=base)

    def _on_priority(self, on: bool) -> None:
        self.cfg.low_priority = on
        self.engine.set_low_priority(on)

    def _on_parallel(self, v: int) -> None:
        self.cfg.parallel = v
        self.engine.set_parallel(v or auto_parallel())

    def _on_end_action(self, *_):
        self.cfg.end_action = self.end_combo.currentData()

    # ================================================================== añadir vídeos
    def add_files_dialog(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(VIDEO_EXTENSIONS))
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("add_files"), self.cfg.last_dir or str(Path.home()),
            f"{tr('video_files')} ({exts} {exts.upper()});;{tr('all_files')} (*)")
        if files:
            self.cfg.last_dir = os.path.dirname(files[0])
            self.add_paths(files)

    def add_folder_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("add_folder"),
                                                  self.cfg.last_dir or str(Path.home()))
        if folder:
            self.cfg.last_dir = folder
            self.add_paths([folder])

    def add_paths(self, paths: list[str]) -> None:
        files: list[str] = []
        folder_given = False
        for p in paths:
            if os.path.isdir(p):
                folder_given = True
                for dirpath, dirnames, filenames in os.walk(p):
                    dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
                    for fn in sorted(filenames):
                        if (os.path.splitext(fn)[1].lower() in VIDEO_EXTENSIONS
                                and ".tuxenc-part" not in fn and not fn.startswith(".")):
                            files.append(os.path.join(dirpath, fn))
            elif os.path.isfile(p):
                files.append(p)
        queued = {j.input for j in self.engine.jobs if j.status not in FINISHED}
        files = [f for f in dict.fromkeys(os.path.abspath(f) for f in files) if f not in queued]
        if not files:
            if folder_given:
                QMessageBox.information(self, APP_NAME, tr("no_videos_found"))
            return
        self.pending_probes += len(files)
        for f in files:
            self._order_seq += 1
            self.prober.submit(self._probe_task, f, self._order_seq)
        self._refresh_controls()

    def _probe_task(self, path: str, order: float) -> None:
        try:
            info = probe(path)
        except ProbeError as exc:
            info = exc
        except Exception as exc:  # noqa: BLE001
            info = ProbeError(str(exc))
        self.bridge.probed.emit(path, (info, order))

    def _on_probed(self, path: str, payload) -> None:
        info, order = payload
        self.pending_probes = max(0, self.pending_probes - 1)
        if isinstance(info, Exception):
            self.failed_probes.append(os.path.basename(path))
        else:
            job = Job(input=path, info=info, order=order)
            self.engine.add(job)
            self.queue.sync(self.engine.jobs)
            if self.cfg.rename_on:
                self.rename.identify([job])
        if self.pending_probes == 0 and self.failed_probes:
            names = "\n".join(self.failed_probes[:15])
            if len(self.failed_probes) > 15:
                names += "\n…"
            self.failed_probes = []
            QMessageBox.warning(self, APP_NAME, tr("not_video", names=names))
        self._refresh_controls()

    # ================================================================== cola
    def _job(self, jid: int) -> Job | None:
        return next((j for j in self.engine.jobs if j.id == jid), None)

    def _on_row_action(self, action: str, jid: int) -> None:
        job = self._job(jid)
        if job is None:
            return
        if action == "menu":
            m = job_menu(self, job)
            from PySide6.QtGui import QCursor
            chosen = m.exec(QCursor.pos())
            if chosen is None:
                return
            action = chosen.data()
        if action == "double":
            needs_id = (self.cfg.rename_on and job.status == WAITING
                        and job.ident not in ("ok", "off", "pending"))
            action = "match" if needs_id else {DONE: "play", WAITING: "tracks"}.get(job.status, "")
        if action in ("use_conv", "use_orig", "keep_both"):
            self._decide_bigger(job, action)
            return
        if action == "match":
            self.rename.open_match(job)
        elif action == "tracks":
            settings = job.settings or self.panel.settings
            dlg = TracksDialog(job, settings, self)
            if dlg.exec():
                job.audio_override, job.sub_override, job.burn_override = dlg.result_overrides()
        elif action in ("up", "down"):
            self.engine.move(jid, -1 if action == "up" else 1)
        elif action == "remove":
            self.engine.remove(jid)
        elif action == "cancel":
            self.engine.cancel_job(jid)
        elif action == "retry":
            self.engine.retry(jid)
        elif action == "folder":
            _open_path(os.path.dirname(job.output))
        elif action == "play":
            _open_path(job.output)
        elif action == "log" and job.log_path:
            LogDialog(tr("error_log_title", name=job.name), job.log_path, self).exec()
        self.queue.sync(self.engine.jobs)
        self._refresh_controls()

    def _on_job_updated(self, job: Job) -> None:
        self.queue.update_job(job)

    def _fill_clear_menu(self) -> None:
        m = self.clear_menu
        m.clear()
        jobs = self.engine.jobs
        finished = [j for j in jobs if j.status in FINISHED]
        pending = [j for j in jobs if j.status == WAITING]
        for key, group, slot in (("clear_finished_n", finished, self._clear_finished),
                                 ("clear_pending_n", pending, self._clear_pending)):
            a = m.addAction(tr(key, n=len(group)), slot)
            a.setEnabled(bool(group))
        m.addSeparator()
        a = m.addAction(tr("clear_all_n", n=len(jobs)), self._clear_all)
        a.setEnabled(bool(jobs))

    def _clear_finished(self) -> None:
        self.engine.clear_finished()
        self.queue.sync(self.engine.jobs)
        self._refresh_controls()

    def _clear_pending(self) -> None:
        self.engine.remove_many(j.id for j in self.engine.jobs if j.status == WAITING)
        self.queue.sync(self.engine.jobs)
        self._refresh_controls()

    def _clear_all(self) -> None:
        running = [j for j in self.engine.jobs if j.status in ACTIVE]
        if running and QMessageBox.question(
                self, APP_NAME, tr("clear_all_running_q", n=len(running))) != QMessageBox.Yes:
            return
        if running or self.engine.active:
            self.user_stopped = True       # que no salte la acción final («Al terminar»)
            self.engine.stop()
        self.engine.remove_many([j.id for j in self.engine.jobs])
        self.queue.sync(self.engine.jobs)
        self._refresh_controls()

    def _start(self) -> None:
        self.user_stopped = False
        convert, rename = self.cfg.convert_on, self.cfg.rename_on
        waiting = [j for j in self.engine.jobs if j.status == WAITING]
        if not convert and not rename:
            QMessageBox.information(self, APP_NAME, tr("need_a_mode"))
            return
        if rename and not convert:
            ready = [j for j in waiting if j.ident == ID_OK and j.rt is not None]
            if not ready:
                QMessageBox.information(self, APP_NAME, tr("nothing_to_rename"))
                return
            missing = len(waiting) - len(ready)
            if missing and QMessageBox.question(
                    self, APP_NAME, tr("unidentified_rename", n=missing)) != QMessageBox.Yes:
                return
            self.rename.rename_jobs(ready)
            self._refresh_controls()
            return
        for j in waiting:
            j.hold = rename and j.ident != ID_OK
        held = sum(1 for j in waiting if j.hold)
        if held and QMessageBox.question(
                self, APP_NAME, tr("unidentified_convert", n=held)) != QMessageBox.Yes:
            for j in waiting:
                j.hold = False
            return
        self.engine.start()
        self.queue.sync(self.engine.jobs)
        self._refresh_controls()

    def _toggle_pause(self) -> None:
        if self.engine.paused:
            self.engine.resume()
        else:
            self.engine.pause()
        self._refresh_controls()

    def _stop(self) -> None:
        if self.engine.is_busy():
            if QMessageBox.question(self, APP_NAME, tr("stop_q")) != QMessageBox.Yes:
                return
        self.user_stopped = True
        self.engine.stop()
        self._refresh_controls()

    def _refresh_controls(self) -> None:
        jobs = self.engine.jobs
        self.stack.setCurrentWidget(self.queue if jobs else self.drop)
        c = self.engine.counts()
        running = c["running"] + c["preparing"] + c["paused"]
        waiting = c["waiting"]
        finished = c["done"] + c["failed"] + c["cancelled"]
        busy = self.engine.active or running > 0
        modes_ok = self.cfg.convert_on or self.cfg.rename_on
        self.start_btn.setEnabled(waiting > 0 and not self.engine.active and modes_ok
                                  and c["running"] == 0)
        self.undo_btn.setVisible(self.cfg.rename_on and not self.cfg.convert_on
                                 and self.rename.can_undo())
        self.pause_btn.setEnabled(busy)
        self.pause_btn.setText(("▶  " + tr("resume")) if self.engine.paused
                               else ("⏸  " + tr("pause")))
        self.stop_btn.setEnabled(busy)
        self.clear_btn.setEnabled(bool(jobs))
        if self.pending_probes:
            self.status_lbl.setText(tr("analyzing", n=self.pending_probes))
        elif self.engine.paused:
            self.status_lbl.setText(tr("status_paused"))
        elif busy:
            self.status_lbl.setText(tr("status_run", run=running, wait=waiting, done=c["done"]))
        elif jobs and finished == len(jobs):
            text = tr("queue_done_msg", ok=c["done"])
            if c["failed"]:
                text += tr("queue_done_fail", n=c["failed"])
            self.status_lbl.setText(text)
        elif jobs:
            self.status_lbl.setText(tr("status_idle", n=waiting))
        else:
            self.status_lbl.setText(tr("status_empty"))
        self.total_bar.setValue(int(self.engine.overall_progress() * 1000) if (busy or finished)
                                else 0)
        if busy:
            pct = self.engine.overall_progress() * 100
            self.setWindowTitle(f"{pct:.0f}% · {APP_NAME}")
        else:
            self.setWindowTitle(APP_NAME)

    # ================================================================== fin de la cola
    def _on_queue_done(self, jobs: list[Job]) -> None:
        self.queue.sync(self.engine.jobs)
        self._refresh_controls()
        if self.user_stopped:
            return
        ok = sum(1 for j in jobs if j.status == DONE)
        bad = sum(1 for j in jobs if j.status == FAILED)
        if ok + bad == 0:
            return
        action = self.cfg.end_action
        msg = tr("queue_done_msg", ok=ok) + (tr("queue_done_fail", n=bad) if bad else "")
        if action != "nothing":
            self._notify(tr("queue_done_title"), msg)
        if action == "quit":
            QTimer.singleShot(1500, self.close)
        elif action in ("suspend", "shutdown"):
            dlg = CountdownDialog(action, 60, self)
            if dlg.exec():
                self.cfg.save()
                cmd = ["systemctl", "suspend" if action == "suspend" else "poweroff"]
                try:
                    subprocess.Popen(cmd, env=clean_env(), start_new_session=True)
                except OSError:
                    pass

    def _notify(self, title: str, body: str) -> None:
        icon = str(ASSETS_DIR / "tuxenc-256.png")
        try:
            subprocess.Popen(["notify-send", "-a", APP_NAME, "-i", icon, title, body],
                             env=clean_env(), start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except OSError:
            pass
        try:
            from PySide6.QtDBus import QDBusInterface
            iface = QDBusInterface("org.freedesktop.Notifications",
                                   "/org/freedesktop/Notifications",
                                   "org.freedesktop.Notifications")
            iface.call("Notify", APP_NAME, 0, icon, title, body, [], {}, 8000)
        except Exception:  # noqa: BLE001
            pass
        from PySide6.QtWidgets import QApplication
        QApplication.alert(self)

    # ================================================================== modos y renombrado
    def _apply_modes(self) -> None:
        conv = self.cfg.convert_on
        from .queue_view import MODE
        MODE["convert"] = conv
        self.queue.sync(self.engine.jobs)
        for w in (self.preset_combo, self.preset_menu_btn, self.adv_btn, self.summary):
            w.setEnabled(conv)
        if not conv and self.adv_btn.isChecked():
            self.set_advanced_visible(False)
        self._fill_output_combo()
        self._update_bar()
        self._refresh_controls()

    def _on_mode_convert(self, on: bool) -> None:
        self.cfg.convert_on = on
        self._apply_modes()
        if self.cfg.rename_on:
            self.rename.refresh_previews()

    def _on_mode_rename(self, on: bool) -> None:
        self.cfg.rename_on = on
        waiting = [j for j in self.engine.jobs if j.status == WAITING]
        if on:
            self._offer_retitler_import()
            self.rename.identify(waiting)
        else:
            for j in waiting:
                j.ident, j.preview, j.note, j.hold = "off", "", "", False
            if self.cfg.output_mode == "library":
                self.cfg.output_mode = "source"
            self.queue.sync(self.engine.jobs)
            self.engine.kick()
        self._apply_modes()

    def _offer_retitler_import(self) -> None:
        """Si Retitler tenía claves y aquí no hay, se ofrece usarlas (una sola vez)."""
        if self.cfg.retitler_import_offered:
            return
        from retitler.config import legacy_retitler_keys
        try:
            legacy = legacy_retitler_keys()
        except Exception:  # noqa: BLE001
            legacy = {}
        if not legacy or self.rename.lib.has_key("tmdb"):
            return
        self.cfg.retitler_import_offered = True
        names = ", ".join(n.upper() for n in legacy)
        if QMessageBox.question(self, APP_NAME, tr("bar_import") + f"\n\n({names})") == QMessageBox.Yes:
            done = self.rename.lib.import_retitler_keys()
            if done:
                QMessageBox.information(self, APP_NAME, tr("imported_keys",
                                                           names=", ".join(d.upper() for d in done)))

    def _after_rename_settings(self, reidentify: bool = False) -> None:
        """Tras cambiar claves, idioma, formatos o destino."""
        if not self.cfg.rename_on:
            self._update_bar()
            return
        if reidentify:
            self.rename.lib.reload()
            waiting = [j for j in self.engine.jobs if j.status == WAITING
                       and not getattr(j.rt, "manual", False)]
            self.rename.identify(waiting, force=True)
        self.rename.refresh_previews()
        self._update_bar()

    def _update_bar(self) -> None:
        kind, text, btn = "", "", ""
        if self.cfg.rename_on:
            try:
                has_tmdb = self.rename.lib.has_key("tmdb")
            except Exception:  # noqa: BLE001
                has_tmdb = False
            if self.cfg.output_mode == "library" and not (self.cfg.series_root and self.cfg.movie_root):
                kind, text, btn = "library", tr("bar_library"), tr("bar_configure")
            elif not has_tmdb:
                kind, text, btn = "tmdb", tr("bar_tmdb"), tr("bar_configure")
        if kind and kind not in self._bar_dismissed:
            self._bar_kind = kind
            self.bar_lbl.setText("💡 " + text)
            self.bar_btn.setText(btn)
            self.bar.setVisible(True)
        else:
            self.bar.setVisible(False)

    def _on_bar_action(self) -> None:
        self._open_prefs(tab="rename")

    def _dismiss_bar(self) -> None:
        self._bar_dismissed.add(self._bar_kind)
        self.bar.setVisible(False)

    def _undo_rename(self) -> None:
        self.undo_btn.setEnabled(False)
        self.rename.undo()

    def _on_renamed(self, ids, payload) -> None:
        jobs = [j for j in self.engine.jobs if j.id in ids]
        if isinstance(payload, Exception):
            for j in jobs:
                j.status = WAITING
            self.rename.refresh_previews()
            QMessageBox.warning(self, APP_NAME, tr("rename_fail", err=str(payload)))
            self._refresh_controls()
            return
        plan, _moves = payload
        by_src = {str(item.source): item for item in plan}
        done = 0
        for j in jobs:
            item = by_src.get(j.input)
            if item is not None and item.target is not None and (item.will_rename
                                                                 or item.status.value == "unchanged"):
                j.status, j.renamed_to, j.output, j.progress = DONE, str(item.target), str(item.target), 1.0
                try:
                    j.out_size = os.path.getsize(item.target)
                except OSError:
                    pass
                done += 1
            else:
                j.status = WAITING
        self.queue.sync(self.engine.jobs)
        self._refresh_controls()
        if self.cfg.end_action != "nothing" and done:
            self._notify(tr("queue_done_title"), tr("rename_done_msg", n=done))

    def _on_undone(self, payload) -> None:
        self.undo_btn.setEnabled(True)
        if isinstance(payload, Exception):
            QMessageBox.warning(self, APP_NAME, tr("undo_fail", err=str(payload)))
            return
        back_from = {str(src) for src, _dst in payload.moves}   # src = ruta renombrada
        for j in self.engine.jobs:
            if j.renamed_to and j.renamed_to in back_from:
                j.status, j.renamed_to, j.output, j.progress = WAITING, "", "", 0.0
        self.rename.refresh_previews()
        self._refresh_controls()
        QMessageBox.information(self, APP_NAME, tr("undo_done", n=len(payload.moves)))

    # ================================================================== GPU
    def _start_hw_detection(self) -> None:
        import threading

        def work():
            try:
                avail = detect_available()
            except Exception:  # noqa: BLE001
                avail = [e.id for e in VIDEO_ENCODERS if not e.hw]
            self.bridge.hw_ready.emit(avail)

        threading.Thread(target=work, daemon=True, name="tuxenc-hw").start()

    def _on_hw_ready(self, avail: list[str]) -> None:
        self.available = avail or ["libx264"]
        current = self.panel.settings
        self.panel.available = self.available
        self.panel.hw_detected = True
        self._reload_presets()
        if current.video_encoder not in self.available:
            self.panel.load(self._adapt(current))
        else:
            self.panel.load(current)
        self._refresh_summary()

    # ================================================================== otros
    def _open_prefs(self, tab: str = "") -> None:
        dlg = PreferencesDialog(self.cfg, self.available, integration, self, rename=self.rename,
                                tab=tab)
        dlg.exec()
        new_lang = dlg.chosen_lang()
        lang_changed = i18n.effective(new_lang) != i18n.current()
        self.cfg.ui_lang = new_lang
        self.cfg.save()
        self._fill_output_combo()
        self._after_rename_settings(reidentify=dlg.search_changed)
        if dlg.integrated_now:
            self._after_integrate(dlg.integrated_update, dlg.integrated_old)
            return
        if lang_changed:
            waiting = any(j.status == WAITING for j in self.engine.jobs)
            text = tr_in(new_lang, "lang_restart_q") + (tr_in(new_lang, "lang_restart_queue") if waiting else "")
            if self._restart_box(text, lang=new_lang, ask=True):
                self.request_restart()

    def request_restart(self, exe: str | None = None) -> bool:
        """Cierra TuxEnc y lo vuelve a abrir. Los vídeos que esperan en la cola se vuelven a añadir.
        Si hay conversiones en marcha, closeEvent pregunta como siempre (y se puede cancelar)."""
        files = [j.input for j in self.engine.jobs if j.status == WAITING]
        self.restart_request = (str(exe) if exe else None, files)
        if not self.close():
            self.restart_request = None
            return False
        return True

    def _restart_box(self, text: str, lang: str | None = None, ask: bool = False) -> bool:
        t = (lambda k: tr_in(lang, k)) if lang else tr
        box = QMessageBox(QMessageBox.Question if ask else QMessageBox.Information, APP_NAME, text, parent=self)
        box.setTextFormat(Qt.RichText)
        yes = box.addButton(t("restart_btn"), QMessageBox.AcceptRole)
        if ask:
            box.addButton(t("restart_later"), QMessageBox.RejectRole)
        box.setDefaultButton(yes)
        box.exec()
        return box.clickedButton() is yes

    def _after_integrate(self, update: bool, old: str) -> None:
        """Tras integrar o actualizar: avisa y reabre desde la copia instalada."""
        if update:
            text = tr("update_ok_restart", new=VERSION,
                      old=tr("update_from", v=old) if old and old != VERSION else "")
        else:
            text = tr("integrate_ok_restart")
        self._restart_box(text)
        self.request_restart(integration.INSTALLED_APPIMAGE)

    def show_just_installed(self, old: str) -> None:
        """Aviso en la versión recién instalada (la abre el proceso que integró o actualizó)."""
        if old == "first":
            text = tr("just_integrated")
        else:
            text = tr("just_updated", v=VERSION,
                      old=tr("update_from", v=old) if old not in ("", "?", VERSION) else "")
        box = QMessageBox(QMessageBox.Information, APP_NAME, text, parent=self)
        box.setTextFormat(Qt.RichText)
        box.exec()

    # ---- arrastrar y soltar
    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.drop.set_hover(True)

    def dragLeaveEvent(self, e):  # noqa: N802
        self.drop.set_hover(False)

    def dropEvent(self, e):  # noqa: N802
        self.drop.set_hover(False)
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.add_paths(paths)

    def closeEvent(self, e):  # noqa: N802
        if self.engine.is_busy():
            box = QMessageBox(QMessageBox.Warning, APP_NAME, tr("quit_running"), parent=self)
            quit_btn = box.addButton(tr("quit_anyway"), QMessageBox.AcceptRole)
            box.addButton(tr("cancel"), QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is not quit_btn:
                e.ignore()
                return
        self.engine.shutdown()
        self.rename.shutdown()
        self.prober.shutdown(wait=False, cancel_futures=True)
        self.cfg.geometry = bytes(self.saveGeometry()).hex()
        self.cfg.settings = self.panel.settings.to_dict()
        self.cfg.save()
        e.accept()
