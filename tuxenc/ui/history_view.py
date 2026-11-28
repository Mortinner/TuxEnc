"""Pestaña «Historial»: una tarjeta por vídeo renombrado o convertido (1.3.7).

Las tarjetas siguen el diseño de las filas de la cola: recuadro, punto de color, nombre en negrita,
etiqueta con lo que se hizo y, a la derecha, «Abrir carpeta».
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QToolButton,
                               QVBoxLayout, QWidget)

from .. import activity
from ..i18n import tr
from ..paths import HOME
from . import theme
from .queue_view import ElidedLabel

_KIND = {   # clave de texto y color de la etiqueta
    "rename": ("hist_kind_rename", theme.ACCENT),
    "convert": ("hist_kind_convert", theme.OK),
    "convert_rename": ("hist_kind_convert_rename", theme.OK),
}


def _short(path: str) -> str:
    """Rutas de la carpeta personal con «~», que se leen mejor."""
    home = str(HOME)
    return "~" + path[len(home):] if path == home or path.startswith(home + "/") else path


def _open(folder: Path) -> None:
    from .main_window import _open_path
    _open_path(str(folder))


class HistoryCard(QFrame):
    def __init__(self, e: activity.Entry, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 10, 10)
        lay.setSpacing(12)

        key, color = _KIND.get(e.kind, _KIND["rename"])
        if e.undone:
            key, color = "hist_undone", theme.MUTED
        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background: {color}; border-radius: 5px;")
        lay.addWidget(dot, 0, Qt.AlignVCenter)

        dst, src = Path(e.dst), Path(e.src)
        mid = QVBoxLayout()
        mid.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(8)
        name = ElidedLabel(dst.name)
        name.setStyleSheet("font-weight: 600;" + (f" color: {theme.MUTED};" if e.undone else ""))
        top.addWidget(name, 1)
        pill = QLabel(tr(key))
        pill.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {color}; border: 1px solid {color};"
                           " border-radius: 8px; padding: 1px 8px;")
        top.addWidget(pill, 0)
        mid.addLayout(top)

        local = e.time.astimezone()
        bits = [local.strftime("%d/%m/%Y %H:%M")]
        if e.subs:
            bits.append(tr("hist_subs", n=e.subs))
        if e.original == "trash":
            bits.append(tr("hist_trashed"))
        when = QLabel(" · ".join(bits))
        when.setObjectName("Muted")
        mid.addWidget(when)
        if e.renamed:
            before = ElidedLabel(tr("hist_before", name=src.name))
            before.setObjectName("Muted")
            mid.addWidget(before)
        for text in (tr("hist_from", path=_short(str(src.parent))), tr("hist_to", path=_short(str(dst.parent)))):
            line = ElidedLabel(text)
            line.setObjectName("Muted")
            line.setToolTip(text)
            mid.addWidget(line)
        lay.addLayout(mid, 1)

        # Deshecho: el archivo volvió a su origen
        self.folder = src.parent if e.undone else dst.parent
        here = (src if e.undone else dst).exists()
        btn = QToolButton()
        btn.setObjectName("Flat")
        btn.setText(tr("open_folder"))
        btn.setEnabled(self.folder.is_dir())
        btn.setToolTip(tr("open_folder") if here else tr("hist_missing"))
        btn.clicked.connect(lambda: _open(self.folder))
        lay.addWidget(btn, 0, Qt.AlignVCenter)

    def mouseDoubleClickEvent(self, ev):  # noqa: N802
        if self.folder.is_dir():
            _open(self.folder)


class HistoryView(QWidget):
    """Lista de tarjetas, lo más reciente arriba. Se carga al abrir la pestaña."""

    LIMIT = 300

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(8)
        head = QHBoxLayout()
        self.summary = QLabel()
        self.summary.setObjectName("Muted")
        self.summary.setWordWrap(True)
        head.addWidget(self.summary, 1)
        self.refresh_btn = QPushButton(tr("hist_refresh"))
        self.refresh_btn.clicked.connect(self.reload)
        head.addWidget(self.refresh_btn, 0)
        outer.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.box = QWidget()
        self.cards = QVBoxLayout(self.box)
        self.cards.setContentsMargins(0, 0, 4, 0)
        self.cards.setSpacing(8)
        self.cards.addStretch(1)
        self.scroll.setWidget(self.box)
        outer.addWidget(self.scroll, 1)

    def reload(self) -> None:
        while self.cards.count() > 1:
            w = self.cards.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        entries = activity.load(self.LIMIT)
        if not entries:
            self.summary.setText(tr("hist_empty"))
            return
        self.summary.setText(tr("hist_summary", n=len(entries)))
        for i, e in enumerate(entries):
            self.cards.insertWidget(i, HistoryCard(e))
