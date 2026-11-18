"""Diálogos: pistas por archivo, preferencias, integración, cuenta atrás y registro."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QPixmap, QTextCursor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QScrollArea, QTabWidget, QVBoxLayout,
                               QWidget)

from .. import VERSION, i18n
from ..catalog import CONTAINERS, ENCODERS_BY_ID, EncodeSettings, lang_name
from ..command import _sub_fits_container, select_audio, select_subtitles
from ..i18n import tr
from ..paths import LOG_DIR, ASSETS_DIR
from ..probe import MediaInfo, Stream


def _icon_label(size: int = 64) -> QLabel:
    lb = QLabel()
    pm = QPixmap(str(ASSETS_DIR / "tuxenc-256.png"))
    if not pm.isNull():
        lb.setPixmap(pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    lb.setFixedSize(size, size)
    return lb


def _scrolled(w: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QScrollArea.NoFrame)
    w.setContentsMargins(6, 6, 6, 6)
    sa.setWidget(w)
    return sa


def _section(text: str) -> QLabel:
    lb = QLabel(text)
    lb.setObjectName("SectionTitle")
    return lb


def describe_stream(s: Stream) -> str:
    ui = i18n.current()
    parts = [lang_name(s.lang, ui) if s.lang != "und" else "—", s.codec.upper()]
    if s.kind == "audio" and s.channels:
        parts.append({1: "mono", 2: "2.0", 6: "5.1", 8: "7.1"}.get(s.channels, f"{s.channels}ch"))
    if s.kind == "subtitle" and s.bitmap:
        parts.append(tr("image_sub"))
    if s.title:
        parts.append(f"«{s.title}»")
    flags = []
    if s.default:
        flags.append(tr("default"))
    if s.forced:
        flags.append(tr("forced"))
    text = f"#{s.index}  " + " · ".join(parts)
    if flags:
        text += "  [" + ", ".join(flags) + "]"
    return text


class TracksDialog(QDialog):
    """Elegir a mano las pistas de un vídeo concreto."""

    def __init__(self, job, settings: EncodeSettings, parent=None):
        super().__init__(parent)
        self.job = job
        info: MediaInfo = job.info
        self.setWindowTitle(tr("tracks_title", name=job.name))
        self.setMinimumWidth(560)
        self.reset_to_auto = False
        lay = QVBoxLayout(self)

        # Selección actual: la manual si existe, si no la de las reglas
        auto_audio = [s.index for s in select_audio(info, settings)]
        auto_subs, auto_burn = select_subtitles(info, settings)
        sel_audio = job.audio_override if job.audio_override is not None else auto_audio
        sel_subs = (job.sub_override if job.sub_override is not None
                    else [s.index for s in auto_subs])
        burn = job.burn_override if job.burn_override is not None else (
            auto_burn.index if auto_burn else -1)

        lay.addWidget(_section(tr("tracks_audio")))
        self.audio = QListWidget()
        self.audio.setObjectName("TrackList")
        for s in info.audio:
            it = QListWidgetItem(describe_stream(s))
            it.setData(Qt.UserRole, s.index)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if s.index in sel_audio else Qt.Unchecked)
            self.audio.addItem(it)
        if not info.audio:
            self.audio.addItem(tr("no_tracks"))
        self.audio.setMaximumHeight(max(60, min(200, 30 * max(1, len(info.audio)) + 12)))
        lay.addWidget(self.audio)

        lay.addWidget(_section(tr("tracks_subs")))
        self.subs = QListWidget()
        self.subs.setObjectName("TrackList")
        for s in info.subtitles:
            text = describe_stream(s)
            fits = _sub_fits_container(s, settings.container)
            if not fits:
                text += "  — " + tr("not_in_container", c=CONTAINERS[settings.container]["label"])
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, s.index)
            if fits:
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if s.index in sel_subs else Qt.Unchecked)
            else:
                it.setFlags(it.flags() & ~Qt.ItemIsEnabled)
            self.subs.addItem(it)
        if not info.subtitles:
            self.subs.addItem(tr("no_tracks"))
        self.subs.setMaximumHeight(max(60, min(200, 30 * max(1, len(info.subtitles)) + 12)))
        lay.addWidget(self.subs)

        form = QFormLayout()
        self.burn = QComboBox()
        self.burn.addItem(tr("burn_none"), -1)
        for s in info.subtitles:
            self.burn.addItem(describe_stream(s), s.index)
        i = self.burn.findData(burn)
        self.burn.setCurrentIndex(max(0, i))
        form.addRow(tr("tracks_burn"), self.burn)
        lay.addLayout(form)

        bb = QDialogButtonBox()
        auto = bb.addButton(tr("tracks_auto"), QDialogButtonBox.ResetRole)
        bb.addButton(tr("accept"), QDialogButtonBox.AcceptRole)
        bb.addButton(tr("cancel"), QDialogButtonBox.RejectRole)
        auto.clicked.connect(self._auto)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _auto(self):
        self.reset_to_auto = True
        self.accept()

    @staticmethod
    def _checked(lw: QListWidget) -> list[int]:
        out = []
        for i in range(lw.count()):
            it = lw.item(i)
            if it.flags() & Qt.ItemIsUserCheckable and it.checkState() == Qt.Checked:
                out.append(it.data(Qt.UserRole))
        return out

    def result_overrides(self) -> tuple[list | None, list | None, int | None]:
        if self.reset_to_auto:
            return None, None, None
        burn = self.burn.currentData()
        subs = [i for i in self._checked(self.subs) if i != burn]
        return self._checked(self.audio), subs, burn


class PreferencesDialog(QDialog):
    def __init__(self, cfg, available: list[str] | None, integration_api, parent=None,
                 rename=None, tab: str = ""):
        super().__init__(parent)
        self.integrated_now, self.integrated_update, self.integrated_old = False, False, ""
        self.cfg = cfg
        self.api = integration_api
        self.setWindowTitle(tr("settings") + " · TuxEnc")
        self.setMinimumWidth(640)
        self.resize(700, 760)
        outer = QVBoxLayout(self)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs)
        general = QWidget()
        lay = QVBoxLayout(general)
        lay.setSpacing(10)

        lay.addWidget(_section(tr("ui_language")))
        self.lang = QComboBox()
        for label, data in ((tr("lang_auto"), "auto"), ("Español", "es"), ("English", "en")):
            self.lang.addItem(label, data)
        self.lang.setCurrentIndex(max(0, self.lang.findData(cfg.ui_lang)))
        lay.addWidget(self.lang)
        self.lang_note = QLabel(tr("restart_needed"))
        self.lang_note.setObjectName("Muted")
        self.lang_note.setVisible(False)
        lay.addWidget(self.lang_note)
        self.lang.currentIndexChanged.connect(lambda *_: self.lang_note.setVisible(True))

        lay.addWidget(_section(tr("integration")))
        self.int_label = QLabel()
        self.int_label.setWordWrap(True)
        lay.addWidget(self.int_label)
        row = QHBoxLayout()
        self.int_btn = QPushButton()
        self.int_btn.clicked.connect(self._integrate)
        self.shortcut_btn = QPushButton(tr("shortcut_again"))
        self.shortcut_btn.clicked.connect(self._integrate)
        row.addWidget(self.int_btn)
        row.addWidget(self.shortcut_btn)
        row.addStretch(1)
        lay.addLayout(row)
        self._refresh_integration()

        lay.addWidget(_section(tr("encoders_found")))
        if available is None:
            enc_text = tr("detecting")
        else:
            cpu = [ENCODERS_BY_ID[e].label for e in available if not ENCODERS_BY_ID[e].hw]
            gpu = [ENCODERS_BY_ID[e].label for e in available if ENCODERS_BY_ID[e].hw]
            enc_text = "CPU: " + ", ".join(cpu)
            enc_text += "\nGPU: " + (", ".join(gpu) if gpu else tr("gpu_none"))
        enc = QLabel(enc_text)
        enc.setWordWrap(True)
        enc.setObjectName("Muted")
        lay.addWidget(enc)
        diag = QPushButton(tr("gpu_diag"))
        diag.clicked.connect(lambda: LogDialog(tr("gpu_diag_title"),
                                               str(LOG_DIR / "gpu-detect.log"), self).exec())
        row_d = QHBoxLayout()
        row_d.addWidget(diag)
        row_d.addStretch(1)
        lay.addLayout(row_d)

        lay.addWidget(_section(tr("logs")))
        logs = QPushButton(tr("open_logs"))
        logs.clicked.connect(lambda: (LOG_DIR.mkdir(parents=True, exist_ok=True),
                                      QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOG_DIR)))))
        row2 = QHBoxLayout()
        row2.addWidget(logs)
        row2.addStretch(1)
        lay.addLayout(row2)

        lay.addWidget(_section(tr("about")))
        about_row = QHBoxLayout()
        about_row.addWidget(_icon_label(56), 0, Qt.AlignTop)
        about = QLabel(tr("about_text", v=VERSION))
        about.setWordWrap(True)
        about.setTextFormat(Qt.RichText)
        about_row.addWidget(about, 1)
        lay.addLayout(about_row)
        credits = QLabel(tr("credits_text"))
        credits.setWordWrap(True)
        credits.setTextFormat(Qt.RichText)
        credits.setOpenExternalLinks(True)
        credits.setObjectName("Muted")
        lay.addWidget(credits)

        lay.addStretch(1)
        self.tabs.addTab(_scrolled(general), tr("tab_general"))
        self.rename_tab = None
        if rename is not None:
            from .rename_prefs import RenamePrefs
            self.rename_tab = RenamePrefs(cfg, rename)
            self.tabs.addTab(_scrolled(self.rename_tab), tr("tab_rename"))
            if tab == "rename":
                self.tabs.setCurrentIndex(1)

        bb = QDialogButtonBox()
        bb.addButton(tr("close"), QDialogButtonBox.AcceptRole)
        bb.accepted.connect(self.accept)
        outer.addWidget(bb)

    @property
    def search_changed(self) -> bool:
        return bool(self.rename_tab and self.rename_tab.search_changed)

    def _refresh_integration(self):
        api = self.api
        if not api.running_from_appimage():
            self.int_label.setText(tr("integrated_dev"))
            self.int_btn.setVisible(False)
            self.shortcut_btn.setVisible(False)
            return
        if api.is_integrated():
            self.int_label.setText(tr("integrated_yes"))
            if api.running_installed_copy():
                self.int_btn.setVisible(False)
            else:
                self.int_btn.setText(tr("integrate_update"))
                self.int_btn.setVisible(True)
            self.shortcut_btn.setVisible(True)
        else:
            self.int_label.setText(tr("integrated_no"))
            self.int_btn.setText(tr("integrate_now"))
            self.int_btn.setVisible(True)
            self.shortcut_btn.setVisible(False)

    def _integrate(self):
        from PySide6.QtWidgets import QMessageBox
        update, old = self.api.is_integrated(), self.api.installed_version()
        try:
            self.api.integrate(True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "TuxEnc", tr("integrate_fail", err=str(exc)))
            self._refresh_integration()
            return
        # La ventana principal avisa y reinicia desde la copia instalada al cerrar Preferencias
        self.integrated_now, self.integrated_update, self.integrated_old = True, update, old
        self.accept()

    def chosen_lang(self) -> str:
        return self.lang.currentData()


class IntegrationDialog(QDialog):
    """Pregunta del primer arranque (o de actualización)."""

    def __init__(self, update: bool = False, parent=None, old: str = "", running: bool = False):
        super().__init__(parent)
        self.setWindowTitle(tr("integrate_q_title") if not update else "TuxEnc")
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(_icon_label(80), 0, Qt.AlignTop)
        from ..integration import version_key
        older = bool(update and old and version_key(old) and version_key(VERSION) < version_key(old))
        if not update:
            msg = tr("integrate_q")
        elif older:
            msg = tr("update_older_q", v=VERSION, old=old)
        elif old:
            msg = tr("update_newer_q", v=VERSION, old=old)
        else:
            msg = tr("update_q", v=VERSION)
        if running:
            msg += tr("update_running_note")
        text = QLabel(msg)
        text.setWordWrap(True)
        text.setTextFormat(Qt.RichText)
        top.addWidget(text, 1)
        lay.addLayout(top)
        self.shortcut = QCheckBox(tr("with_shortcut"))
        self.shortcut.setChecked(True)
        self.shortcut.setVisible(not update)
        lay.addWidget(self.shortcut)
        bb = QDialogButtonBox()
        ok = bb.addButton(tr("install_this") if older else tr("update_yes") if update else tr("integrate_yes"),
                          QDialogButtonBox.AcceptRole)
        ok.setObjectName("Primary")
        bb.addButton(tr("integrate_later"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class CountdownDialog(QDialog):
    """Cuenta atrás antes de suspender o apagar (siempre se puede cancelar)."""

    def __init__(self, action: str, seconds: int = 60, parent=None):
        super().__init__(parent)
        self.action = action
        self.left = seconds
        self.setWindowTitle("TuxEnc")
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        self.label = QLabel()
        f = QFont()
        f.setPointSize(12)
        self.label.setFont(f)
        self.label.setWordWrap(True)
        lay.addWidget(self.label)
        bb = QDialogButtonBox()
        now = bb.addButton(tr("do_it_now"), QDialogButtonBox.AcceptRole)
        now.setObjectName("Primary")
        bb.addButton(tr("cancel"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        self._update()

    def _update(self):
        key = "countdown_suspend" if self.action == "suspend" else "countdown_shutdown"
        self.label.setText(tr(key, s=self.left))

    def _tick(self):
        self.left -= 1
        if self.left <= 0:
            self.timer.stop()
            self.accept()
        else:
            self._update()


class LogDialog(QDialog):
    def __init__(self, title: str, path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(820, 480)
        lay = QVBoxLayout(self)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        mono = QFont("monospace")
        mono.setStyleHint(QFont.Monospace)
        view.setFont(mono)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                view.setPlainText(fh.read()[-200_000:])
        except OSError as exc:
            view.setPlainText(str(exc))
        view.moveCursor(QTextCursor.End)
        lay.addWidget(view)
        row = QHBoxLayout()
        open_btn = QPushButton(tr("open_logs"))
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOG_DIR))))
        close = QPushButton(tr("close"))
        close.clicked.connect(self.accept)
        row.addWidget(open_btn)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)


def separator() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet("color: #2c3658;")
    return f
