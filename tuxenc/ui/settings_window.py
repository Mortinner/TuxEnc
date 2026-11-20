"""Ventana única de ajustes: Conversión · Renombrado · Buscadores · Presets · Preferencias · Acerca de.

Se crea una sola vez (la conserva la ventana principal) y se abre desde el menú ☰ en la pestaña
pedida. Todo se puede configurar siempre, estén activados o no la conversión y el renombrado.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTabWidget,
                               QVBoxLayout, QWidget)

from .. import APP_NAME, VERSION
from ..catalog import ENCODERS_BY_ID
from ..i18n import tr
from ..paths import LOG_DIR
from ..presets import load_user_presets, save_user_presets
from .dialogs import LogDialog, _icon_label, _scrolled, _section

TABS = ("conversion", "rename", "engines", "presets", "prefs", "about")
AUTHOR = "Mortinner"
CONTACT = "mortinner@gmail.com"


def _muted(text: str) -> QLabel:
    lb = QLabel(text)
    lb.setObjectName("Muted")
    lb.setWordWrap(True)
    return lb


def _row(*widgets) -> QHBoxLayout:
    r = QHBoxLayout()
    for w in widgets:
        r.addWidget(w)
    r.addStretch(1)
    return r


class SettingsWindow(QDialog):
    rolled_back = False             # se volvió a la versión anterior: la ventana principal reinicia
    update_requested = False        # «Ver novedades» de una versión nueva: lo abre la ventana principal

    def __init__(self, main) -> None:
        super().__init__(main)
        self.main = main
        self.cfg = main.cfg
        self.setWindowTitle(tr("settings") + " · " + APP_NAME)
        self.setMinimumSize(760, 620)
        self.resize(900, 820)
        outer = QVBoxLayout(self)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs)

        # 🎞 Conversión: el mismo panel de siempre (vive aquí)
        conv = QWidget()
        cl = QVBoxLayout(conv)
        cl.setContentsMargins(4, 8, 4, 4)
        self.conv_info = _muted("")
        cl.addWidget(self.conv_info)
        card = QFrame()
        card.setObjectName("Card")
        kl = QVBoxLayout(card)
        kl.setContentsMargins(4, 4, 4, 4)
        kl.addWidget(main.panel)
        cl.addWidget(card, 1)
        self.tabs.addTab(conv, "🎞  " + tr("tab_conversion"))

        # 🏷 Renombrado y 🔎 Buscadores
        from .rename_prefs import RenamePrefs
        self.rename_prefs = RenamePrefs(self.cfg, main.rename)
        self.tabs.addTab(_scrolled(self.rename_prefs), "🏷  " + tr("tab_rename"))
        self.tabs.addTab(_scrolled(self.rename_prefs.engines_page), "🔎  " + tr("tab_engines"))

        # ★ Presets
        self.tabs.addTab(self._build_presets(), "★  " + tr("tab_presets"))
        # 🔧 Preferencias
        self.tabs.addTab(_scrolled(self._build_prefs()), "🔧  " + tr("tab_prefs"))
        # ℹ Acerca de
        self.tabs.addTab(_scrolled(self._build_about()), "ℹ  " + tr("tab_about"))

        bb = QDialogButtonBox()
        bb.addButton(tr("close"), QDialogButtonBox.AcceptRole)
        bb.accepted.connect(self.accept)
        outer.addWidget(bb)
        self.integrated_now = self.integrated_update = False
        self.integrated_old = ""
        self.rolled_back = self.update_requested = False

    # ------------------------------------------------------------------ abrir
    def open_tab(self, tab: str = "conversion") -> None:
        """Refresca lo que puede haber cambiado y se abre en la pestaña pedida (modal)."""
        self.integrated_now = self.integrated_update = False
        self.integrated_old = ""
        self.rename_prefs.search_changed = False
        self.rename_prefs._refresh_keys()
        self._refresh_conv_info()
        self._refresh_presets()
        self._refresh_integration()
        self._refresh_updates()
        self._refresh_encoders()
        self.lang.blockSignals(True)
        self.lang.setCurrentIndex(max(0, self.lang.findData(self.cfg.ui_lang)))
        self.lang.blockSignals(False)
        self.lang_note.setVisible(False)
        self.tabs.setCurrentIndex(TABS.index(tab) if tab in TABS else 0)
        self.exec()

    @property
    def search_changed(self) -> bool:
        return self.rename_prefs.search_changed

    def chosen_lang(self) -> str:
        return self.lang.currentData()

    def _refresh_conv_info(self) -> None:
        m = self.main
        p = m._preset(m.current_key)
        name = p.name if p else "—"
        text = tr("conv_info", preset=name) + (f" ({tr('modified')})" if m._is_modified() else "")
        if not self.cfg.convert_on:
            text += "  ·  " + tr("conv_info_off")
        self.conv_info.setText(text)

    # ------------------------------------------------------------------ presets
    def _build_presets(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 10, 8, 8)
        lay.addWidget(_muted(tr("presets_hint")))
        self.preset_list = QListWidget()
        self.preset_list.itemDoubleClicked.connect(lambda *_: self._use_preset())
        self.preset_list.currentItemChanged.connect(lambda *_: self._preset_buttons())
        lay.addWidget(self.preset_list, 1)
        self.p_use = QPushButton(tr("preset_use"))
        self.p_use.clicked.connect(self._use_preset)
        self.p_save = QPushButton(tr("preset_save"))
        self.p_save.clicked.connect(self._save_preset)
        self.p_del = QPushButton(tr("preset_delete"))
        self.p_del.clicked.connect(self._delete_preset)
        lay.addLayout(_row(self.p_use, self.p_save, self.p_del))
        p_imp = QPushButton(tr("preset_import"))
        p_imp.clicked.connect(self._import_presets)
        p_exp = QPushButton(tr("preset_export"))
        p_exp.clicked.connect(self.main._export_presets)
        lay.addLayout(_row(p_imp, p_exp))
        return w

    def _refresh_presets(self) -> None:
        m = self.main
        self.preset_list.blockSignals(True)
        self.preset_list.clear()
        for p in m.presets:
            label = p.name if p.builtin else "★ " + p.name
            if p.key == m.current_key:
                label += "   ✓ " + tr("preset_current") + (f" ({tr('modified')})" if m._is_modified() else "")
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, p.key)
            it.setToolTip(tr("preset_builtin") if p.builtin else tr("preset_user"))
            self.preset_list.addItem(it)
            if p.key == m.current_key:
                self.preset_list.setCurrentItem(it)
        self.preset_list.blockSignals(False)
        self._preset_buttons()

    def _selected_preset(self):
        it = self.preset_list.currentItem()
        return self.main._preset(it.data(Qt.UserRole)) if it else None

    def _preset_buttons(self) -> None:
        p = self._selected_preset()
        self.p_use.setEnabled(p is not None)
        self.p_del.setEnabled(bool(p and not p.builtin))

    def _use_preset(self) -> None:
        p = self._selected_preset()
        if p is None:
            return
        m = self.main
        m._select_preset_key(p.key, apply=True)
        m.cfg.last_preset = p.key
        m._on_settings_changed()
        self._refresh_presets()
        self._refresh_conv_info()

    def _save_preset(self) -> None:
        self.main._save_preset()
        self._refresh_presets()
        self._refresh_conv_info()

    def _delete_preset(self) -> None:
        p = self._selected_preset()
        if not p or p.builtin:
            return
        if QMessageBox.question(self, APP_NAME, tr("preset_delete_q", name=p.name)) != QMessageBox.Yes:
            return
        m = self.main
        save_user_presets([u for u in load_user_presets() if u.name != p.name])
        if m.current_key == p.key:                 # se quedan los ajustes; ya no tienen preset
            m.current_key = "builtin:hevc_quality"
        m._reload_presets()
        m._refresh_summary()
        self._refresh_presets()
        self._refresh_conv_info()

    def _import_presets(self) -> None:
        self.main._import_handbrake()
        self._refresh_presets()
        self._refresh_conv_info()

    # ------------------------------------------------------------------ preferencias
    def _build_prefs(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        lay.addWidget(_section(tr("ui_language")))
        self.lang = QComboBox()
        for label, data in ((tr("lang_auto"), "auto"), ("Español", "es"), ("English", "en")):
            self.lang.addItem(label, data)
        lay.addWidget(self.lang)
        self.lang_note = _muted(tr("restart_needed"))
        self.lang_note.setVisible(False)
        lay.addWidget(self.lang_note)
        self.lang.currentIndexChanged.connect(lambda *_: self.lang_note.setVisible(True))

        lay.addWidget(_section(tr("integration")))
        self.int_label = QLabel()
        self.int_label.setWordWrap(True)
        lay.addWidget(self.int_label)
        self.int_btn = QPushButton()
        self.int_btn.clicked.connect(self._integrate)
        self.shortcut_btn = QPushButton(tr("shortcut_again"))
        self.shortcut_btn.clicked.connect(self._integrate)
        lay.addLayout(_row(self.int_btn, self.shortcut_btn))

        lay.addWidget(_section(tr("upd_section")))
        self.upd_auto = QCheckBox(tr("upd_auto"))
        self.upd_auto.toggled.connect(self._set_update_check)
        lay.addWidget(self.upd_auto)
        self.upd_label = _muted("")
        lay.addWidget(self.upd_label)
        self.upd_check_btn = QPushButton(tr("upd_check_now"))
        self.upd_check_btn.clicked.connect(lambda: self.main.updater.check(manual=True))
        self.upd_view_btn = QPushButton(tr("bar_update_btn"))
        self.upd_view_btn.clicked.connect(self._view_update)
        self.upd_back_btn = QPushButton()
        self.upd_back_btn.clicked.connect(self._rollback)
        lay.addLayout(_row(self.upd_check_btn, self.upd_view_btn, self.upd_back_btn))
        self.main.updater.listeners.append(self._refresh_updates)

        lay.addWidget(_section(tr("encoders_found")))
        self.enc_label = _muted("")
        lay.addWidget(self.enc_label)
        diag = QPushButton(tr("gpu_diag"))
        diag.clicked.connect(lambda: LogDialog(tr("gpu_diag_title"), str(LOG_DIR / "gpu-detect.log"), self).exec())
        lay.addLayout(_row(diag))

        lay.addWidget(_section(tr("logs")))
        logs = QPushButton(tr("open_logs"))
        logs.clicked.connect(lambda: (LOG_DIR.mkdir(parents=True, exist_ok=True),
                                      QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOG_DIR)))))
        lay.addLayout(_row(logs))
        lay.addStretch(1)
        return w

    def _refresh_encoders(self) -> None:
        available = self.main.available
        if available is None:
            self.enc_label.setText(tr("detecting"))
            return
        cpu = [ENCODERS_BY_ID[e].label for e in available if not ENCODERS_BY_ID[e].hw]
        gpu = [ENCODERS_BY_ID[e].label for e in available if ENCODERS_BY_ID[e].hw]
        self.enc_label.setText("CPU: " + ", ".join(cpu) + "\nGPU: " + (", ".join(gpu) if gpu else tr("gpu_none")))

    def _refresh_integration(self) -> None:
        from .. import integration as api
        if not api.running_from_appimage():
            self.int_label.setText(tr("integrated_dev"))
            self.int_btn.setVisible(False)
            self.shortcut_btn.setVisible(False)
            return
        if api.is_integrated():
            self.int_label.setText(tr("integrated_yes"))
            self.int_btn.setText(tr("integrate_update"))
            self.int_btn.setVisible(not api.running_installed_copy())
            self.shortcut_btn.setVisible(True)
        else:
            self.int_label.setText(tr("integrated_no"))
            self.int_btn.setText(tr("integrate_now"))
            self.int_btn.setVisible(True)
            self.shortcut_btn.setVisible(False)

    def _integrate(self) -> None:
        from .. import integration as api
        update, old = api.is_integrated(), api.installed_version()
        try:
            api.integrate(True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, APP_NAME, tr("integrate_fail", err=str(exc)))
            self._refresh_integration()
            return
        # La ventana principal avisa y reinicia desde la copia instalada al cerrar los ajustes
        self.integrated_now, self.integrated_update, self.integrated_old = True, update, old
        self.accept()

    # ------------------------------------------------------------------ actualizaciones
    def _set_update_check(self, on: bool) -> None:
        self.cfg.update_check = bool(on)
        self.cfg.save()

    def _refresh_updates(self) -> None:
        import time as _time
        from .. import updater as api
        from .update_ctrl import error_text
        upd = self.main.updater
        self.upd_auto.blockSignals(True)
        self.upd_auto.setChecked(bool(self.cfg.update_check))
        self.upd_auto.blockSignals(False)
        if upd.checking:
            text = tr("upd_checking")
        elif upd.ready_version:
            text = tr("bar_update_ready", v=upd.ready_version)
        elif upd.info:
            text = tr("upd_found_short", v=upd.info.latest.version)
        elif upd.last_error is not None:
            text = error_text(upd.last_error)
        elif self.cfg.update_last_check:
            when = _time.strftime("%d/%m/%Y %H:%M", _time.localtime(self.cfg.update_last_check))
            text = tr("upd_uptodate", v=VERSION) + " " + tr("upd_last_check", when=when)
        else:
            text = tr("upd_never")
        if not api.can_self_update():
            text += "\n" + tr("upd_dev_note")
        self.upd_label.setText(text)
        self.upd_check_btn.setEnabled(not upd.checking and not upd.downloading)
        self.upd_view_btn.setVisible(bool(upd.info) and not upd.ready_version)
        prev = api.previous_version() if api.can_self_update() else ""
        self.upd_back_btn.setVisible(bool(prev) and prev != VERSION and not upd.ready_version)
        self.upd_back_btn.setText(tr("upd_rollback", v=prev))

    def _view_update(self) -> None:
        self.update_requested = True
        self.accept()

    def _rollback(self) -> None:
        from .. import updater as api
        from ..integration import version_key
        from .update_ctrl import error_text
        prev = api.previous_version()
        box = QMessageBox(QMessageBox.Question, APP_NAME, tr("upd_rollback_q", prev=prev, cur=VERSION),
                          parent=self)
        box.setTextFormat(Qt.RichText)
        yes = box.addButton(tr("upd_rollback", v=prev), QMessageBox.AcceptRole)
        box.addButton(tr("cancel"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not yes:
            return
        try:
            api.rollback()
        except api.UpdateError as exc:
            QMessageBox.warning(self, APP_NAME, error_text(exc))
            self._refresh_updates()
            return
        if version_key(VERSION) > version_key(prev):
            self.cfg.update_skip = VERSION        # que no vuelva a ofrecer justo la que se deja
            self.cfg.save()
        self.rolled_back = True
        self.accept()

    # ------------------------------------------------------------------ acerca de
    @staticmethod
    def _provenance_label() -> QLabel:
        from .. import build_info
        from ..updater import RELEASES_PAGE, REPO
        info = build_info.load()
        releases = RELEASES_PAGE.rsplit("/", 1)[0]
        if info["kind"] == "official":
            text = tr("prov_official", commit_url=info["commit_url"], short=info["commit"][:7],
                      repo=info["repo"], run_url=info["run_url"], built=info["built"],
                      release_url=info["release_url"], v=VERSION)
            text += "<br><br>" + tr("prov_verify", zip=f"{APP_NAME}-{VERSION}-linux-x86_64.zip", repo=REPO)
        elif info["kind"] == "local":
            text = tr("prov_local", built=info.get("built", ""), releases=releases)
        else:
            text = tr("prov_source", releases=releases)
        lb = QLabel(tr("prov_title") + "<br>" + text)
        lb.setObjectName("Provenance")
        lb.setTextFormat(Qt.RichText)
        lb.setOpenExternalLinks(True)
        lb.setWordWrap(True)
        lb.setTextInteractionFlags(Qt.TextBrowserInteraction)
        return lb

    def _build_about(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(12)
        top = QHBoxLayout()
        top.addWidget(_icon_label(96), 0, Qt.AlignTop)
        about = QLabel(tr("about_text", v=VERSION))
        about.setWordWrap(True)
        about.setTextFormat(Qt.RichText)
        top.addWidget(about, 1)
        lay.addLayout(top)
        author = QLabel(tr("about_author", author=AUTHOR, mail=CONTACT))
        author.setTextFormat(Qt.RichText)
        author.setOpenExternalLinks(True)
        author.setWordWrap(True)
        lay.addWidget(author)
        lay.addWidget(self._provenance_label())
        lic = QLabel(tr("about_license"))
        lic.setTextFormat(Qt.RichText)
        lic.setOpenExternalLinks(True)
        lic.setWordWrap(True)
        lay.addWidget(lic)
        credits = QLabel(tr("credits_text"))
        credits.setWordWrap(True)
        credits.setTextFormat(Qt.RichText)
        credits.setOpenExternalLinks(True)
        credits.setObjectName("Muted")
        lay.addWidget(credits)
        lay.addStretch(1)
        return w
