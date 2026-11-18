"""Panel de ajustes avanzados: Vídeo · Imagen · Audio · Subtítulos."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFormLayout, QFrame,
                               QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QSlider, QSpinBox, QTabWidget, QToolButton,
                               QVBoxLayout, QWidget)

from .. import i18n
from ..catalog import (AUDIO_BITRATES, AUDIO_CODECS, CONTAINERS, FRAMERATES, LANGUAGES,
                       RES_BOX, RESOLUTIONS, SPEED_HINTS, VIDEO_ENCODERS, EncodeSettings,
                       encoder, lang_name, speed_family)
from ..i18n import tr


def _combo(items: list[tuple[str, object]]) -> QComboBox:
    c = QComboBox()
    for label, data in items:
        c.addItem(label, data)
    return c


def _set_combo(c: QComboBox, data) -> None:
    i = c.findData(data)
    if i >= 0:
        c.setCurrentIndex(i)


class WrapLabel(QLabel):
    """QLabel multilínea que reserva siempre la altura que necesita (QFormLayout a veces la recorta)."""

    def _fix_height(self) -> None:
        if self.width() > 0:
            h = self.heightForWidth(self.width())
            if h > 0 and h != self.minimumHeight():
                self.setMinimumHeight(h)

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self._fix_height()

    def setText(self, text):  # noqa: N802
        super().setText(text)
        self._fix_height()


def _hint(text: str) -> QLabel:
    lb = WrapLabel(text)
    lb.setObjectName("Muted")
    lb.setWordWrap(True)
    return lb


class LangList(QWidget):
    """Lista ordenada de idiomas preferidos (arrastrar para ordenar)."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.list = QListWidget()
        self.list.setObjectName("LangList")
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setFixedHeight(110)
        self.list.model().rowsMoved.connect(lambda *a: self.changed.emit())
        lay.addWidget(self.list)
        row = QHBoxLayout()
        self.add = QComboBox()
        self.add.addItem(tr("lang_add"), None)
        ui = i18n.current()
        for code, _es, _en in sorted(LANGUAGES, key=lambda x: lang_name(x[0], ui)):
            self.add.addItem(lang_name(code, ui), code)
        self.add.activated.connect(self._on_add)
        row.addWidget(self.add, 1)
        for text, tip, fn in (("▲", tr("move_up"), lambda: self._move(-1)),
                              ("▼", tr("move_down"), lambda: self._move(1)),
                              ("✕", tr("remove"), self._remove)):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)

    def _on_add(self, idx: int) -> None:
        code = self.add.itemData(idx)
        self.add.setCurrentIndex(0)
        if code and code not in self.value():
            self._append(code)
            self.changed.emit()

    def _append(self, code: str) -> None:
        it = QListWidgetItem(f"{lang_name(code, i18n.current())}  ·  {code}")
        it.setData(Qt.UserRole, code)
        self.list.addItem(it)

    def _move(self, d: int) -> None:
        r = self.list.currentRow()
        if r < 0:
            return
        n = r + d
        if 0 <= n < self.list.count():
            it = self.list.takeItem(r)
            self.list.insertItem(n, it)
            self.list.setCurrentRow(n)
            self.changed.emit()

    def _remove(self) -> None:
        r = self.list.currentRow()
        if r >= 0:
            self.list.takeItem(r)
            self.changed.emit()

    def value(self) -> list[str]:
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]

    def set_value(self, codes: list[str]) -> None:
        self.list.clear()
        for c in codes:
            self._append(c)


class SettingsPanel(QWidget):
    """Edita un EncodeSettings. Emite `changed` cuando el usuario toca algo."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False
        self.available: list[str] = [e.id for e in VIDEO_ENCODERS if not e.hw]
        self.hw_detected = False
        self.settings = EncodeSettings()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self.tabs.addTab(self._scroll(self._build_video()), tr("tab_video"))
        self.tabs.addTab(self._scroll(self._build_picture()), tr("tab_picture"))
        self.tabs.addTab(self._scroll(self._build_audio()), tr("tab_audio"))
        self.tabs.addTab(self._scroll(self._build_subs()), tr("tab_subs"))

    @staticmethod
    def _scroll(w: QWidget) -> QScrollArea:
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(w)
        hl.addStretch(1)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(holder)
        sa.setFrameShape(QScrollArea.NoFrame)
        return sa

    @staticmethod
    def _form(parent: QWidget) -> QFormLayout:
        f = QFormLayout(parent)
        f.setContentsMargins(14, 14, 14, 14)
        f.setVerticalSpacing(12)
        f.setHorizontalSpacing(14)
        f.setRowWrapPolicy(QFormLayout.WrapLongRows)
        f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        return f

    # ------------------------------------------------------------------ pestañas
    def _build_video(self) -> QWidget:
        w = QWidget()
        f = self._form(w)
        self.container = _combo([(v["label"], k) for k, v in CONTAINERS.items()])
        self.codec = QComboBox()
        self.rate = _combo([(tr("rate_cq"), "cq"), (tr("rate_abr"), "abr"), (tr("rate_cbr"), "cbr")])

        qrow = QWidget()
        ql = QVBoxLayout(qrow)
        ql.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.q_slider = QSlider(Qt.Horizontal)
        self.q_spin = QSpinBox()
        self.q_spin.setFixedWidth(80)
        top.addWidget(self.q_slider, 1)
        top.addWidget(self.q_spin)
        ql.addLayout(top)
        self.q_hint = QWidget()
        hh = QHBoxLayout(self.q_hint)
        hh.setContentsMargins(0, 0, 0, 0)
        for key, align in (("quality_better", Qt.AlignLeft), ("quality_smaller", Qt.AlignRight)):
            lb = _hint(tr(key))
            lb.setWordWrap(False)
            lb.setStyleSheet("font-size: 8pt;")
            lb.setAlignment(align)
            hh.addWidget(lb, 1)
        hh.addSpacing(88)
        ql.addWidget(self.q_hint)
        self.q_slider.valueChanged.connect(self.q_spin.setValue)
        self.q_spin.valueChanged.connect(self.q_slider.setValue)

        self.bitrate = QSpinBox()
        self.bitrate.setRange(100, 200000)
        self.bitrate.setSingleStep(250)
        self.bitrate.setSuffix(" kbps")
        self.two_pass = QCheckBox(tr("two_pass"))
        self.copy_lower = QCheckBox(tr("copy_if_lower"))
        self.copy_lower.setToolTip(tr("copy_if_lower_tip"))
        self.speed = QComboBox()
        self.depth = _combo([(tr("bits8"), 8), (tr("bits10"), 10)])
        self.chapters = QCheckBox(tr("keep_chapters"))

        self.q_label = QLabel(tr("quality"))
        self.br_label = QLabel(tr("bitrate"))
        # Aviso cuando se elige un códec de CPU teniendo GPU disponible
        self.gpu_tip = QFrame()
        self.gpu_tip.setObjectName("Tip")
        self.gpu_tip.setStyleSheet("QFrame#Tip { background: #2a2a1c; border: 1px solid #5a5328;"
                                   " border-radius: 8px; }")
        tl = QVBoxLayout(self.gpu_tip)
        tl.setContentsMargins(10, 8, 10, 8)
        tip_lbl = QLabel("💡 " + tr("cpu_hint"))
        tip_lbl.setWordWrap(True)
        tl.addWidget(tip_lbl)
        self.gpu_btn = QPushButton()
        self.gpu_btn.clicked.connect(self._switch_to_gpu)
        tl.addWidget(self.gpu_btn, 0, Qt.AlignLeft)
        self.gpu_tip.setVisible(False)

        f.addRow(tr("container"), self.container)
        f.addRow(tr("codec"), self.codec)
        f.addRow(self.gpu_tip)
        self.rate_hint = _hint("")
        self.br_size = _hint("")
        self.speed.setToolTip(tr("speed_hint"))
        f.addRow(tr("rate_mode"), self.rate)
        f.addRow(self.rate_hint)
        f.addRow(self.q_label, qrow)
        f.addRow(self.br_label, self.bitrate)
        f.addRow(self.br_size)
        f.addRow("", self.two_pass)
        f.addRow("", self.copy_lower)
        self.speed_hint = _hint("")
        f.addRow(tr("speed"), self.speed)
        f.addRow(self.speed_hint)
        f.addRow(tr("bit_depth"), self.depth)
        f.addRow("", self.chapters)

        self.container.currentIndexChanged.connect(self._on_container)
        self.codec.currentIndexChanged.connect(self._on_codec)
        self.rate.currentIndexChanged.connect(self._on_any)
        self.q_spin.valueChanged.connect(self._on_any)
        self.bitrate.valueChanged.connect(self._on_any)
        self.two_pass.toggled.connect(self._on_any)
        self.copy_lower.toggled.connect(self._on_any)
        self.speed.currentIndexChanged.connect(self._on_any)
        self.depth.currentIndexChanged.connect(self._on_any)
        self.chapters.toggled.connect(self._on_any)
        return w

    def _build_picture(self) -> QWidget:
        w = QWidget()
        f = self._form(w)
        self.res = _combo([(tr("res_source") if r == 0
                            else f"{r}p  ({RES_BOX[r][0]}×{RES_BOX[r][1]})", r)
                           for r in RESOLUTIONS])
        self.upscale = QCheckBox(tr("upscale"))
        self.fps = _combo([(tr("fps_source") if x == "source" else x, x) for x in FRAMERATES])
        self.autocrop = QCheckBox(tr("autocrop"))
        self.deint = _combo([(tr("deint_off"), "off"), (tr("deint_yadif"), "yadif"),
                             (tr("deint_bwdif"), "bwdif")])
        self.denoise = _combo([(tr("dn_off"), "off"), (tr("dn_light"), "light"),
                               (tr("dn_medium"), "medium"), (tr("dn_strong"), "strong")])
        f.addRow(tr("resolution"), self.res)
        f.addRow("", self.upscale)
        f.addRow(_hint(tr("upscale_hint")))
        f.addRow(tr("framerate"), self.fps)
        f.addRow("", self.autocrop)
        f.addRow(tr("deinterlace"), self.deint)
        f.addRow("", _hint(tr("deint_hint")))
        f.addRow(tr("denoise"), self.denoise)
        for c in (self.res, self.fps, self.deint, self.denoise):
            c.currentIndexChanged.connect(self._on_any)
        self.autocrop.toggled.connect(self._on_any)
        self.upscale.toggled.connect(self._on_any)
        return w

    def _build_audio(self) -> QWidget:
        w = QWidget()
        f = self._form(w)
        self.a_mode = _combo([(tr("a_lang_all"), "lang_all"), (tr("a_first"), "first"),
                              (tr("a_all"), "all"), (tr("a_none"), "none")])
        self.a_langs = LangList()
        self.a_codec = QComboBox()
        self.a_br = _combo([(tr("a_br_auto"), 0)] + [(f"{b} kbps", b) for b in AUDIO_BITRATES])
        self.a_mix = _combo([(tr("mix_keep"), "keep"), (tr("mix_stereo"), "stereo"),
                             (tr("mix_51"), "5.1")])
        f.addRow(tr("a_tracks"), self.a_mode)
        f.addRow(QLabel(tr("langs")))
        f.addRow(self.a_langs)
        f.addRow(_hint(tr("lang_hint")))
        f.addRow(tr("a_codec"), self.a_codec)
        f.addRow(tr("a_bitrate"), self.a_br)
        f.addRow(tr("a_mix"), self.a_mix)
        self.a_copy_lower = QCheckBox(tr("a_copy_if_lower"))
        self.a_copy_lower.setToolTip(tr("a_copy_if_lower_tip"))
        f.addRow("", self.a_copy_lower)
        self.a_copy_lower.toggled.connect(self._on_any)
        for c in (self.a_mode, self.a_codec, self.a_br, self.a_mix):
            c.currentIndexChanged.connect(self._on_any)
        self.a_langs.changed.connect(self._on_any)
        return w

    def _build_subs(self) -> QWidget:
        w = QWidget()
        f = self._form(w)
        self.s_mode = _combo([(tr("s_lang_all"), "lang_all"), (tr("s_first"), "first"),
                              (tr("s_forced"), "forced"), (tr("s_all"), "all"),
                              (tr("s_none"), "none")])
        self.s_langs = LangList()
        self.s_burn = _combo([(tr("burn_none"), "none"), (tr("burn_forced"), "forced"),
                              (tr("burn_first"), "first")])
        f.addRow(tr("s_tracks"), self.s_mode)
        f.addRow(QLabel(tr("langs")))
        f.addRow(self.s_langs)
        f.addRow(tr("s_burn"), self.s_burn)
        f.addRow(_hint(tr("subs_hint")))
        self.s_mode.currentIndexChanged.connect(self._on_any)
        self.s_burn.currentIndexChanged.connect(self._on_any)
        self.s_langs.changed.connect(self._on_any)
        return w

    # ------------------------------------------------------------------ datos
    def set_available(self, encoders: list[str]) -> None:
        self.available = encoders
        self.hw_detected = True
        self.load(self.settings)

    def _add_header(self, text: str) -> None:
        self.codec.addItem(text, None)
        model = self.codec.model()
        if isinstance(model, QStandardItemModel):
            item = model.item(self.codec.count() - 1)
            item.setEnabled(False)
            item.setSelectable(False)

    def _gpu_equivalent(self, enc_id: str):
        """Encoder de GPU disponible para el mismo códec (NVENC > QSV > VAAPI)."""
        codec = encoder(enc_id).codec
        for hw in ("nvenc", "qsv", "vaapi"):
            for e in VIDEO_ENCODERS:
                if e.hw == hw and e.codec == codec and e.id in self.available:
                    return e
        return None

    def _switch_to_gpu(self) -> None:
        alt = self._gpu_equivalent(self.settings.video_encoder)
        if alt:
            i = self.codec.findData(alt.id)
            if i >= 0:
                self.codec.setCurrentIndex(i)

    def _fill_codecs(self) -> None:
        self.codec.blockSignals(True)
        self.codec.clear()
        cpu = [e for e in VIDEO_ENCODERS if not e.hw and e.id in self.available]
        gpu = [e for e in VIDEO_ENCODERS if e.hw and e.id in self.available]
        self._add_header(tr("grp_cpu"))
        for e in cpu:
            self.codec.addItem("   " + e.label, e.id)
        if gpu:
            self._add_header(tr("grp_gpu"))
            for e in gpu:
                self.codec.addItem("   " + e.label, e.id)
        else:
            self._add_header(tr("grp_gpu_none") if self.hw_detected else tr("grp_gpu_wait"))
        cur = self.settings.video_encoder
        if self.codec.findData(cur) < 0:
            self.codec.addItem(encoder(cur).label + " ⚠", cur)
        _set_combo(self.codec, cur)
        self.codec.blockSignals(False)

    def _fill_speed(self) -> None:
        enc = encoder(self.settings.video_encoder)
        self.speed.blockSignals(True)
        self.speed.clear()
        n = len(enc.presets)
        hints = SPEED_HINTS.get(speed_family(enc.id), {})
        for p in enc.presets:
            label = p
            if p in hints:
                label += f"  ·  {tr(hints[p])}"
            self.speed.addItem(label, p)
        _set_combo(self.speed, self.settings.speed_preset)
        self.speed.setEnabled(n > 0)
        self.speed.blockSignals(False)

    def _fill_audio_codecs(self) -> None:
        self.a_codec.blockSignals(True)
        self.a_codec.clear()
        for k, v in AUDIO_CODECS.items():
            if self.settings.container in v["containers"]:
                self.a_codec.addItem(tr(v["label"]) if k == "copy" else v["label"], k)
        _set_combo(self.a_codec, self.settings.audio_codec)
        self.a_codec.blockSignals(False)

    def load(self, s: EncodeSettings) -> None:
        self._loading = True
        self.settings = s.copy()
        s = self.settings
        enc = encoder(s.video_encoder)
        widgets = self.findChildren(QWidget)
        for w in widgets:
            w.blockSignals(True)
        _set_combo(self.container, s.container)
        self._fill_codecs()
        self._fill_speed()
        self._fill_audio_codecs()
        _set_combo(self.rate, s.rate_mode)
        self.q_slider.setRange(enc.q_min, enc.q_max)
        self.q_spin.setRange(enc.q_min, enc.q_max)
        self.q_spin.setPrefix(f"{enc.q_label} ")
        self.q_slider.setValue(s.quality)
        self.q_spin.setValue(s.quality)
        self.bitrate.setValue(s.bitrate)
        self.two_pass.setChecked(s.two_pass)
        self.copy_lower.setChecked(s.copy_if_lower)
        _set_combo(self.depth, s.bit_depth)
        self.chapters.setChecked(s.keep_chapters)
        _set_combo(self.res, s.max_height)
        self.upscale.setChecked(s.allow_upscale)
        _set_combo(self.fps, s.framerate)
        self.autocrop.setChecked(s.autocrop)
        _set_combo(self.deint, s.deinterlace)
        _set_combo(self.denoise, s.denoise)
        _set_combo(self.a_mode, s.audio_mode)
        self.a_langs.set_value(s.audio_langs)
        _set_combo(self.a_br, s.audio_bitrate)
        _set_combo(self.a_mix, s.audio_mixdown)
        self.a_copy_lower.setChecked(s.audio_copy_if_lower)
        _set_combo(self.s_mode, s.sub_mode)
        self.s_langs.set_value(s.sub_langs)
        _set_combo(self.s_burn, s.sub_burn)
        for w in widgets:
            w.blockSignals(False)
        self._update_enabled()
        self._loading = False

    def _update_enabled(self) -> None:
        s = self.settings
        enc = encoder(s.video_encoder)
        cq = s.rate_mode == "cq"
        self.q_slider.setEnabled(cq)
        self.q_spin.setEnabled(cq)
        self.q_hint.setEnabled(cq)
        self.bitrate.setEnabled(not cq)
        self.copy_lower.setEnabled(not cq)
        self.rate_hint.setText(tr(f"hint_{s.rate_mode}"))
        self.speed_hint.setText(tr("speed_hint"))
        self.br_size.setVisible(not cq)
        mb = s.bitrate * 3600 / 8 / 1000
        size = f"{mb / 1000:.1f} GB" if mb >= 1000 else f"{mb:.0f} MB"
        self.br_size.setText(tr("size_per_hour", mb=size))
        self.upscale.setEnabled(bool(s.max_height))
        self.two_pass.setEnabled(not cq and (enc.supports_2pass or enc.hw == "nvenc"))
        self.depth.setEnabled(enc.supports_10bit)
        alt = self._gpu_equivalent(s.video_encoder) if not enc.hw else None
        self.gpu_tip.setVisible(alt is not None)
        if alt is not None:
            self.gpu_btn.setText("⚡ " + tr("use_gpu", name=alt.label))
        no_audio = s.audio_mode == "none"
        copy = s.audio_codec == "copy"
        self.a_langs.setEnabled(s.audio_mode in ("first", "lang_all"))
        self.a_codec.setEnabled(not no_audio)
        self.a_br.setEnabled(not no_audio and not copy and s.audio_codec != "flac")
        self.a_mix.setEnabled(not no_audio and not copy)
        self.a_copy_lower.setEnabled(not no_audio and not copy)
        self.s_langs.setEnabled(s.sub_mode in ("first", "lang_all", "forced")
                                or s.sub_burn != "none")

    def _read(self) -> EncodeSettings:
        s = self.settings.copy()
        s.container = self.container.currentData()
        s.video_encoder = self.codec.currentData() or s.video_encoder
        s.rate_mode = self.rate.currentData()
        s.quality = self.q_spin.value()
        s.bitrate = self.bitrate.value()
        s.two_pass = self.two_pass.isChecked()
        s.copy_if_lower = self.copy_lower.isChecked()
        if self.speed.count():
            s.speed_preset = self.speed.currentData()
        s.bit_depth = self.depth.currentData()
        s.keep_chapters = self.chapters.isChecked()
        s.max_height = self.res.currentData()
        s.allow_upscale = self.upscale.isChecked()
        s.framerate = self.fps.currentData()
        s.autocrop = self.autocrop.isChecked()
        s.deinterlace = self.deint.currentData()
        s.denoise = self.denoise.currentData()
        s.audio_mode = self.a_mode.currentData()
        s.audio_langs = self.a_langs.value()
        if self.a_codec.count():
            s.audio_codec = self.a_codec.currentData()
        s.audio_bitrate = self.a_br.currentData()
        s.audio_mixdown = self.a_mix.currentData()
        s.audio_copy_if_lower = self.a_copy_lower.isChecked()
        s.sub_mode = self.s_mode.currentData()
        s.sub_langs = self.s_langs.value()
        s.sub_burn = self.s_burn.currentData()
        return s

    # ------------------------------------------------------------------ eventos
    def _on_any(self, *_):
        if self._loading:
            return
        s = self._read()
        s.validate()
        self.settings = s
        self._update_enabled()
        self.changed.emit()

    def _on_container(self, *_):
        if self._loading:
            return
        s = self._read()
        enc = encoder(s.video_encoder)
        if s.container not in enc.containers:
            # El códec no cabe en ese formato: elegir uno compatible
            for e in VIDEO_ENCODERS:
                if e.id in self.available and s.container in e.containers:
                    s.video_encoder = e.id
                    s.quality = e.q_default
                    s.speed_preset = e.preset_default
                    break
        if s.container not in AUDIO_CODECS[s.audio_codec]["containers"]:
            s.audio_codec = "opus" if s.container == "webm" else "aac"
        container = s.container
        s.validate()
        s.container = container if container in encoder(s.video_encoder).containers else s.container
        self.load(s)
        self.changed.emit()

    def _on_codec(self, *_):
        if self._loading:
            return
        s = self._read()
        enc = encoder(s.video_encoder)
        s.quality = enc.q_default
        s.speed_preset = enc.preset_default
        if s.container not in enc.containers:
            s.container = "mkv"
        if enc.supports_10bit and enc.codec in ("hevc", "av1") and not enc.hw == "qsv":
            s.bit_depth = 10
        s.validate()
        self.load(s)
        self.changed.emit()
