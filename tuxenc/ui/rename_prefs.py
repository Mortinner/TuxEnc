"""Pestaña «Renombrado» de Preferencias (lo que antes era la configuración de Retitler)."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout, QWidget)

from retitler.formatter import (SAMPLE_MOVIE_CONTEXT, SAMPLE_SERIES_CONTEXT, TemplateError,
                                initial_of, render)
from retitler.config import KeyStore
from retitler.providers import InvalidApiKey, OMDbClient, ProviderError, TMDBClient, TVDBClient

from . import theme
from ..i18n import tr

from ..library import LIB_MOVIE, LIB_SERIES

SERIES_PRESETS = [
    ("fmt_s_library", LIB_SERIES),
    ("fmt_s_jellyfin", "{series} ({year})/Season {season:02}/{series} ({year}) - S{season:02}E{episode:02} - {title}"),
    ("fmt_s_1x01", "{series} - {season}x{episode:02} - {title}"),
    ("fmt_s_s01e01", "{series} - S{season:02}E{episode:02} - {title}"),
    ("fmt_s_year", "{series} ({year}) - S{season:02}E{episode:02} - {title}"),
    ("fmt_s_folders", "{series}/Temporada {season:02}/{series} - S{season:02}E{episode:02} - {title}"),
]
MOVIE_PRESETS = [
    ("fmt_m_library", LIB_MOVIE),
    ("fmt_m_plain", "{title} ({year})"),
    ("fmt_m_res", "{title} ({year}) - [{resolution}]"),
    ("fmt_m_folder", "{title} ({year})/{title} ({year})"),
]


def _muted(text: str) -> QLabel:
    lb = QLabel(text)
    lb.setObjectName("Muted")
    lb.setWordWrap(True)
    return lb


def _section(text: str) -> QLabel:
    lb = QLabel(text)
    lb.setObjectName("SectionTitle")
    return lb


class RenamePrefs(QWidget):
    def __init__(self, cfg, ctrl, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.ctrl = ctrl
        self.lib = ctrl.lib
        self.search_changed = False
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        # ---------------------------------------------------------------- buscadores (pestaña propia)
        self.engines_page = QWidget()
        elay = QVBoxLayout(self.engines_page)
        elay.setSpacing(10)
        elay.addWidget(_section(tr("rp_keys")))
        elay.addWidget(_muted(tr("rp_keys_hint") if KeyStore.BUILTIN else tr("rp_keys_hint_nobuiltin")))
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        self.key_rows = {}
        for service, label, url in (("tmdb", "TMDB", "https://www.themoviedb.org/settings/api"),
                                    ("tvdb", "TheTVDB", "https://thetvdb.com/api-information"),
                                    ("tvmaze", "TVmaze", ""),
                                    ("omdb", "IMDb (OMDb)", "https://www.omdbapi.com/apikey.aspx")):
            status = QLabel()
            status.setWordWrap(True)
            box = QVBoxLayout()
            box.setSpacing(4)
            box.addWidget(status)
            edit = pin = clear = None
            if service != "tvmaze":
                row = QHBoxLayout()
                edit = QLineEdit()
                edit.setEchoMode(QLineEdit.Password)
                edit.setPlaceholderText(tr("rp_key_placeholder"))
                save = QPushButton(tr("rp_key_save"))
                clear = QPushButton(tr("rp_key_clear_mine"))
                get = QPushButton(tr("rp_key_get"))
                get.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
                save.clicked.connect(lambda _=False, s=service: self._save_key(s))
                clear.clicked.connect(lambda _=False, s=service: self._clear_key(s))
                edit.returnPressed.connect(lambda s=service: self._save_key(s))
                for w in (edit, save, clear, get):
                    row.addWidget(w, 1 if w is edit else 0)
                box.addLayout(row)
                if service == "tvdb":
                    pin = QLineEdit()
                    pin.setEchoMode(QLineEdit.Password)
                    pin.setPlaceholderText(tr("rp_pin_placeholder"))
                    box.addWidget(pin)
            form.addRow(label, box)
            self.key_rows[service] = (edit, status, clear, pin)
        elay.addLayout(form)
        self.import_btn = QPushButton(tr("rp_import_retitler"))
        self.import_btn.clicked.connect(self._import)
        ir = QHBoxLayout()
        ir.addWidget(self.import_btn)
        ir.addStretch(1)
        elay.addLayout(ir)
        self._refresh_keys()

        # ---------------------------------------------------------------- idioma de los títulos
        elay.addWidget(_section(tr("rp_titles")))
        f2 = QFormLayout()
        self.lang = QComboBox()
        self.lang.addItem("Español", "es")
        self.lang.addItem("English", "en")
        self.lang.setCurrentIndex(max(0, self.lang.findData(self.lib.settings.language)))
        self.lang.currentIndexChanged.connect(self._on_lang)
        f2.addRow(tr("rp_title_lang"), self.lang)
        elay.addLayout(f2)
        elay.addStretch(1)

        # ---------------------------------------------------------------- formatos
        lay.addWidget(_section(tr("rp_formats")))
        self.series_combo, self.series_edit, self.series_prev = self._format_block(
            lay, tr("rp_series"), SERIES_PRESETS, self.lib.settings.series_template, series=True)
        self.movie_combo, self.movie_edit, self.movie_prev = self._format_block(
            lay, tr("rp_movies"), MOVIE_PRESETS, self.lib.settings.movie_template, series=False)
        lay.addWidget(_muted(tr("rp_vars")))
        self.skip = QCheckBox(tr("rp_skip_articles"))
        self.skip.setChecked(self.lib.settings.skip_articles)
        self.skip.toggled.connect(self._on_skip)
        lay.addWidget(self.skip)
        self.keep_title = QCheckBox(tr("rp_keep_file_title"))
        self.keep_title.setToolTip(tr("rp_keep_file_title_tip"))
        self.keep_title.setChecked(self.lib.settings.keep_file_title)
        self.keep_title.toggled.connect(self._on_keep_title)
        lay.addWidget(self.keep_title)

        # ---------------------------------------------------------------- biblioteca
        lay.addWidget(_section(tr("rp_library")))
        lay.addWidget(_muted(tr("rp_library_hint")))
        f3 = QFormLayout()
        self.series_root = self._folder_row(f3, tr("rp_series_root"), "series_root")
        self.movie_root = self._folder_row(f3, tr("rp_movie_root"), "movie_root")
        lay.addLayout(f3)

        # ---------------------------------------------------------------- original
        lay.addWidget(_section(tr("rp_original")))
        self.orig = QComboBox()
        self.orig.addItem(tr("rp_orig_keep"), "keep")
        self.orig.addItem(tr("rp_orig_trash"), "trash")
        self.orig.setCurrentIndex(max(0, self.orig.findData(cfg.original_after)))
        self.orig.currentIndexChanged.connect(
            lambda *_: setattr(self.cfg, "original_after", self.orig.currentData()))
        lay.addWidget(self.orig)
        lay.addWidget(_muted(tr("rp_orig_hint")))
        lay.addWidget(_muted(tr("rp_orig_hint_bigger")))
        lay.addStretch(1)

    # ------------------------------------------------------------------ claves
    def _refresh_keys(self) -> None:
        for service, (edit, status, clear, pin) in self.key_rows.items():
            if service == "tvmaze":
                text, ok = tr("rp_key_free"), True
            else:
                src = self.lib.keys.for_service(service).source()
                ok = src is not None
                text = {"env": tr("rp_key_env"), "keyring": tr("rp_key_keyring"), "file": tr("rp_key_file"),
                        "builtin": tr("rp_key_builtin")}.get(
                    src, tr("rp_key_none_omdb") if service == "omdb" else tr("rp_key_none"))
                clear.setVisible(src in ("keyring", "file"))
                edit.clear()
                if pin is not None:
                    pin.clear()
            status.setText(text)
            status.setStyleSheet(f"color: {theme.OK if ok else theme.AMBER};")
        try:
            from retitler.config import legacy_retitler_keys
            legacy = legacy_retitler_keys()
        except Exception:  # noqa: BLE001
            legacy = {}
        self.import_btn.setVisible(any(not self.lib.has_key(s) for s in legacy))

    def _save_key(self, service: str) -> None:
        edit, status, _clear, pin = self.key_rows[service]
        key = edit.text().strip()
        pin_value = pin.text().strip() if pin is not None else ""
        if not key:
            return
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            note = ""
            if service == "tvdb":
                try:
                    TVDBClient(key, pin=pin_value)._login()
                    ok = True
                except InvalidApiKey:
                    ok = False
            else:
                ok = (TMDBClient(key) if service == "tmdb" else OMDbClient(key)).validate_key()
        except ProviderError as exc:
            ok, note = True, tr("rp_key_unchecked", err=str(exc))
        finally:
            QGuiApplication.restoreOverrideCursor()
        if not ok:
            status.setText("⚠ " + tr("rp_key_invalid"))
            status.setStyleSheet(f"color: {theme.BAD};")
            return
        self.lib.keys.for_service(service).set(key)
        if service == "tvdb":
            if pin_value:
                self.lib.keys.for_service("tvdbpin").set(pin_value)
            else:
                self.lib.keys.for_service("tvdbpin").clear()
        self.search_changed = True
        self._refresh_keys()
        if note:
            status.setText(status.text() + " · " + note)

    def _clear_key(self, service: str) -> None:
        self.lib.keys.for_service(service).clear()
        if service == "tvdb":
            self.lib.keys.for_service("tvdbpin").clear()
        self.search_changed = True
        self._refresh_keys()

    def _import(self) -> None:
        if self.lib.import_retitler_keys():
            self.search_changed = True
        self._refresh_keys()

    def _on_lang(self, *_):
        self.lib.settings.language = self.lang.currentData()
        self.lib.settings.save()
        self.search_changed = True

    # ------------------------------------------------------------------ formatos
    def _format_block(self, lay, title, presets, current, series):
        lay.addWidget(QLabel(title))
        combo = QComboBox()
        for key, tpl in presets:
            combo.addItem(tr(key), tpl)
        combo.addItem(tr("rp_custom"), None)
        edit = QLineEdit(current)
        prev = _muted("")
        lay.addWidget(combo)
        lay.addWidget(edit)
        lay.addWidget(prev)

        def sync_combo():
            i = combo.findData(edit.text())
            combo.blockSignals(True)
            combo.setCurrentIndex(i if i >= 0 else combo.count() - 1)
            combo.blockSignals(False)

        def on_combo(idx):
            tpl = combo.itemData(idx)
            if tpl:
                edit.setText(tpl)

        def on_edit(text):
            sync_combo()
            self._validate(edit, prev, series)

        combo.currentIndexChanged.connect(on_combo)
        edit.textChanged.connect(on_edit)
        sync_combo()
        self._validate(edit, prev, series)
        return combo, edit, prev

    def _validate(self, edit: QLineEdit, prev: QLabel, series: bool) -> None:
        tpl = edit.text()
        base = SAMPLE_SERIES_CONTEXT if series else SAMPLE_MOVIE_CONTEXT
        ctx = replace(base, initial=initial_of(base.series if series else base.title,
                                               self.lib.settings.skip_articles))
        try:
            out = render(tpl, ctx, ".mkv")
        except TemplateError as exc:
            prev.setText("⚠ " + str(exc))
            prev.setStyleSheet("color: #ffc24b;")
            return
        prev.setStyleSheet("")
        prev.setText(tr("rp_example", ex=out))
        if series:
            self.lib.settings.series_template = tpl
        else:
            self.lib.settings.movie_template = tpl
        self.lib.settings.save()

    def _on_keep_title(self, on: bool) -> None:
        self.lib.settings.keep_file_title = on
        self.lib.settings.save()
        self.search_changed = True          # vuelve a identificar lo que haya en la cola

    def _on_skip(self, on: bool) -> None:
        self.lib.settings.skip_articles = on
        self.lib.settings.save()
        self._validate(self.movie_edit, self.movie_prev, False)
        self._validate(self.series_edit, self.series_prev, True)

    # ------------------------------------------------------------------ carpetas
    def _folder_row(self, form: QFormLayout, label: str, attr: str) -> QLineEdit:
        row = QHBoxLayout()
        edit = QLineEdit(getattr(self.cfg, attr))
        edit.setPlaceholderText(tr("rp_not_set"))
        edit.textChanged.connect(lambda t: setattr(self.cfg, attr, t.strip()))
        btn = QPushButton(tr("choose_folder") + "…")

        def pick():
            folder = QFileDialog.getExistingDirectory(self, label, edit.text() or "")
            if folder:
                edit.setText(folder)
        btn.clicked.connect(pick)
        row.addWidget(edit, 1)
        row.addWidget(btn)
        form.addRow(label, row)
        return edit
