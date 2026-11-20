"""Actualizaciones en la interfaz: aviso, novedades, descarga con progreso e instalación.

La lógica (red, SHA-256, instalar, volver atrás) está en tuxenc/updater.py; aquí solo los hilos,
los diálogos y la barra de avisos de la ventana principal.
"""

from __future__ import annotations

import os
import threading
import time

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                               QMessageBox, QProgressBar, QPushButton, QTextBrowser, QVBoxLayout)

from .. import APP_NAME, VERSION, i18n, integration, updater
from ..i18n import tr
from .dialogs import _icon_label

IDLE_POLL_MS = 3000


def error_text(err) -> str:
    code = getattr(err, "code", "bad_reply")
    detail = getattr(err, "detail", "") or ""
    return tr(f"upd_err_{code}", detail=detail) if f"upd_err_{code}" in i18n.STRINGS else str(err)


class UpdateDialog(QDialog):
    """«Hay una versión nueva»: novedades plegables y Actualizar / Saltar / Ahora no."""

    def __init__(self, info: updater.UpdateInfo, can_install: bool, parent=None):
        super().__init__(parent)
        self.choice = "later"
        rel = info.latest
        self.setWindowTitle(tr("upd_title"))
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(_icon_label(72), 0, Qt.AlignTop)
        text = tr("upd_available", v=rel.version, cur=info.current)
        installable = can_install and rel.installable
        if installable:
            mb = max(1, round(rel.zip_size / 1048576)) if rel.zip_size else 140
            text += "<br><br>" + tr("upd_how", mb=mb)
        elif not can_install:
            text += "<br><br>" + tr("upd_manual_note")
        else:
            text += "<br><br>" + tr("upd_err_no_assets")
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextFormat(Qt.RichText)
        top.addWidget(label, 1)
        lay.addLayout(top)

        self.notes_chk = QCheckBox(tr("upd_show_notes"))
        lay.addWidget(self.notes_chk)
        self.notes = QTextBrowser()
        self.notes.setOpenExternalLinks(True)
        self.notes.setMarkdown(updater.notes_markdown(info, i18n.current()))
        self.notes.setMinimumHeight(260)
        self.notes.setVisible(False)
        lay.addWidget(self.notes, 1)
        self.notes_chk.toggled.connect(self._toggle_notes)

        bb = QDialogButtonBox()
        main = bb.addButton(tr("upd_install") if installable else tr("upd_open_page"),
                            QDialogButtonBox.AcceptRole)
        main.setObjectName("Primary")
        main.clicked.connect(lambda: self._done("install" if installable else "page"))
        skip = bb.addButton(tr("upd_skip"), QDialogButtonBox.ActionRole)
        skip.clicked.connect(lambda: self._done("skip"))
        later = bb.addButton(tr("upd_later"), QDialogButtonBox.RejectRole)
        later.clicked.connect(lambda: self._done("later"))
        lay.addWidget(bb)
        main.setDefault(True)

    def _toggle_notes(self, on: bool) -> None:
        self.notes.setVisible(on)
        self.adjustSize()
        if on and self.height() < 560:
            self.resize(max(self.width(), 640), 560)

    def _done(self, choice: str) -> None:
        self.choice = choice
        self.accept() if choice != "later" else self.reject()


class DownloadDialog(QDialog):
    def __init__(self, version: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("upd_title"))
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        self.label = QLabel(tr("upd_downloading", v=version))
        lay.addWidget(self.label)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        lay.addWidget(self.bar)
        self.detail = QLabel("")
        self.detail.setObjectName("Muted")
        lay.addWidget(self.detail)
        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel_btn = QPushButton(tr("cancel"))
        self.cancel_btn.clicked.connect(self.reject)
        row.addWidget(self.cancel_btn)
        lay.addLayout(row)

    def set_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(done * 1000 / total))
            if done >= total:
                self.label.setText(tr("upd_verifying"))
                self.bar.setRange(0, 0)
                self.cancel_btn.setEnabled(False)
        self.detail.setText(tr("upd_mb", done=f"{done / 1048576:.0f}",
                               total=f"{total / 1048576:.0f}" if total else "?"))


class UpdateController(QObject):
    checked = Signal(object, object, bool)       # UpdateInfo | None, UpdateError | None, manual
    progress = Signal(int, int)
    prepared = Signal(object, object)            # versión instalada | None, error | "cancelled" | None

    def __init__(self, window):
        super().__init__(window)
        self.w = window
        self.cfg = window.cfg
        self.info: updater.UpdateInfo | None = None
        self.last_error = None
        self.checking = False
        self.downloading = False
        self.ready_version = ""                  # instalada, pendiente de reiniciar
        self.listeners: list = []                # p. ej. la pestaña Preferencias abierta
        self._cancel: threading.Event | None = None
        self._dl_dialog: DownloadDialog | None = None
        self._dl_result = None
        self.checked.connect(self._on_checked)
        self.prepared.connect(self._on_prepared)
        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(IDLE_POLL_MS)
        self.idle_timer.timeout.connect(self._restart_if_idle)
        if updater.can_self_update():
            updater.cleanup_staging()            # restos de una descarga interrumpida

    # ------------------------------------------------------------------ comprobar
    def can_install(self) -> bool:
        return updater.can_self_update()

    def auto_check(self) -> None:
        if not self.cfg.update_check:
            return
        if not (updater.can_self_update() or os.environ.get(updater.API_OVERRIDE_ENV)):
            return                               # desarrollo o AppImage suelto: solo a mano
        self.check(manual=False)                 # en cada arranque (1.3.1): una consulta, no se nota

    def check(self, manual: bool = True) -> None:
        if self.checking:
            return
        self.checking = True
        self._notify()
        threading.Thread(target=self._run_check, args=(manual,), daemon=True,
                         name="tuxenc-update-check").start()

    def _run_check(self, manual: bool) -> None:
        info, err = None, None
        try:
            info = updater.check()
        except updater.UpdateError as exc:
            err = exc
        except Exception as exc:  # noqa: BLE001
            err = updater.UpdateError("bad_reply", str(exc))
        if err is not None:
            updater.log(f"comprobación fallida: {err}")
        self.checked.emit(info, err, manual)

    def _on_checked(self, info, err, manual: bool) -> None:
        self.checking = False
        self.last_error = err
        if err is None:
            self.info = info
            self.cfg.update_last_check = time.time()
            self.cfg.save()
        self._notify()
        self.w._update_bar()

    def _notify(self) -> None:
        for cb in list(self.listeners):
            try:
                cb()
            except RuntimeError:                 # el widget ya no existe
                self.listeners.remove(cb)

    # ------------------------------------------------------------------ barra de avisos
    def bar_state(self) -> tuple[str, str, str] | None:
        if self.ready_version:
            return "update_ready", tr("bar_update_ready", v=self.ready_version), tr("bar_restart")
        if self.info and self.info.latest.version != self.cfg.update_skip:
            return ("update", tr("bar_update", v=self.info.latest.version, cur=self.info.current),
                    tr("bar_update_btn"))
        return None

    def bar_action(self, kind: str) -> None:
        if kind == "update_ready":
            self.restart()
        else:
            self.open_dialog()

    # ------------------------------------------------------------------ diálogo y descarga
    def open_dialog(self, parent=None) -> None:
        if not self.info or self.downloading:
            return
        parent = parent or self.w
        dlg = UpdateDialog(self.info, self.can_install(), parent)
        dlg.exec()
        rel = self.info.latest
        if dlg.choice == "skip":
            self.cfg.update_skip = rel.version
            self.cfg.save()
            updater.log(f"el usuario salta la {rel.version}")
            self.w._update_bar()
        elif dlg.choice == "page":
            QDesktopServices.openUrl(QUrl(rel.page or updater.RELEASES_PAGE))
        elif dlg.choice == "install":
            self.start_download(parent)

    def start_download(self, parent=None) -> None:
        if not self.info or self.downloading:
            return
        rel = self.info.latest
        self.downloading = True
        self._cancel = threading.Event()
        self._dl_result = None
        dlg = DownloadDialog(rel.version, parent or self.w)
        self._dl_dialog = dlg
        self.progress.connect(dlg.set_progress)
        threading.Thread(target=self._run_prepare, args=(rel,), daemon=True,
                         name="tuxenc-update-download").start()
        accepted = dlg.exec()
        self.progress.disconnect(dlg.set_progress)
        self._dl_dialog = None
        if not accepted and self._dl_result is None:
            self._cancel.set()                  # el resultado llegará después y se atenderá sin diálogo
            return
        self._handle_result(*self._dl_result, parent=parent or self.w)

    def _run_prepare(self, rel: updater.Release) -> None:
        last = [0.0]

        def progress(done: int, total: int) -> None:
            now = time.monotonic()
            if now - last[0] >= 0.1 or done >= total:
                last[0] = now
                self.progress.emit(done, total)

        try:
            path = updater.prepare(rel, progress, self._cancel)
            if self._cancel.is_set():
                raise updater.Cancelled()
            updater.install(path, rel.version)
            self.prepared.emit(rel.version, None)
        except updater.Cancelled:
            self.prepared.emit(None, "cancelled")
        except updater.UpdateError as exc:
            self.prepared.emit(None, exc)
        except Exception as exc:  # noqa: BLE001
            updater.log(f"error inesperado al actualizar: {exc!r}")
            updater.cleanup_staging()
            self.prepared.emit(None, updater.UpdateError("install", str(exc)))

    def _on_prepared(self, version, err) -> None:
        self.downloading = False
        if self._dl_dialog is not None:          # el diálogo sigue abierto: lo cierra y sigue arriba
            self._dl_result = (version, err)
            self._dl_dialog.accept()
            return
        if version:                              # se canceló tarde, pero ya estaba instalada
            self._installed(version)

    def _handle_result(self, version, err, parent) -> None:
        if err == "cancelled":
            return
        if err is not None:
            box = QMessageBox(QMessageBox.Warning, tr("upd_failed_title"),
                              error_text(err) + tr("upd_err_suffix"), parent=parent)
            box.setTextFormat(Qt.RichText)
            box.exec()
            return
        self._installed(version)
        self._ask_restart(parent)

    def _installed(self, version: str) -> None:
        self.ready_version = version
        self.info = None
        self._notify()
        self.w._update_bar()

    # ------------------------------------------------------------------ reiniciar
    def busy(self) -> bool:
        eng = self.w.engine
        return bool(eng.is_busy() or eng.active or getattr(self.w.rename, "busy", 0))

    def _ask_restart(self, parent) -> None:
        busy = self.busy()
        text = tr("upd_installed", v=self.ready_version, cur=VERSION)
        if busy:
            text += tr("upd_installed_busy")
        box = QMessageBox(QMessageBox.Information, APP_NAME, text, parent=parent)
        box.setTextFormat(Qt.RichText)
        when_done = None
        if not busy:
            now = box.addButton(tr("upd_restart_now"), QMessageBox.AcceptRole)
        else:
            now = None
            if self.cfg.end_action in ("nothing", "notify"):
                when_done = box.addButton(tr("upd_restart_when_done"), QMessageBox.AcceptRole)
        later = box.addButton(tr("restart_later"), QMessageBox.RejectRole)
        box.setDefaultButton(now or when_done or later)
        box.exec()
        clicked = box.clickedButton()
        if now is not None and clicked is now:
            self.restart()
        elif when_done is not None and clicked is when_done:
            self.idle_timer.start()

    def _restart_if_idle(self) -> None:
        if not self.ready_version:
            self.idle_timer.stop()
            return
        if self.busy() or self.cfg.end_action not in ("nothing", "notify"):
            return
        self.idle_timer.stop()
        self.restart()

    def restart(self) -> None:
        self.idle_timer.stop()
        self.w.request_restart(integration.INSTALLED_APPIMAGE)
