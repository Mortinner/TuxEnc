"""Interruptor deslizante (estilo móvil) con su texto al lado: pulsar en cualquier parte lo cambia."""
from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QAbstractButton

from . import theme


class Switch(QAbstractButton):
    TRACK_W, TRACK_H, GAP = 40, 22, 10

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self.toggled.connect(self._animate)

    # posición de la bola: 0 apagado … 1 encendido
    def _get_knob(self) -> float:
        return self._pos

    def _set_knob(self, v: float) -> None:
        self._pos = v
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        if not self.isVisible():
            self._pos = 1.0 if on else 0.0
            self.update()
            return
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def setChecked(self, on: bool) -> None:  # noqa: N802 (API de Qt)
        super().setChecked(on)
        if not self._anim.state():
            self._pos = 1.0 if on else 0.0
            self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = QFontMetrics(self.font())
        w = self.TRACK_W + (self.GAP + fm.horizontalAdvance(self.text()) if self.text() else 0)
        return QSize(w + 4, max(self.TRACK_H, fm.height()) + 8)

    def hitButton(self, pos) -> bool:  # noqa: N802
        return self.rect().contains(pos)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        enabled = self.isEnabled()
        y = (self.height() - self.TRACK_H) / 2
        track = QRectF(1, y, self.TRACK_W, self.TRACK_H)
        off, on = QColor(theme.BORDER), QColor(theme.ACCENT)
        col = QColor(
            int(off.red() + (on.red() - off.red()) * self._pos),
            int(off.green() + (on.green() - off.green()) * self._pos),
            int(off.blue() + (on.blue() - off.blue()) * self._pos))
        if not enabled:
            col.setAlpha(110)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(track, self.TRACK_H / 2, self.TRACK_H / 2)
        d = self.TRACK_H - 6
        x = track.left() + 3 + (self.TRACK_W - 6 - d) * self._pos
        knob = QColor("#ffffff" if self._pos > 0.5 else theme.TEXT)
        if not enabled:
            knob.setAlpha(140)
        p.setBrush(knob)
        p.drawEllipse(QRectF(x, track.top() + 3, d, d))
        if self.hasFocus():
            p.setPen(QColor(theme.ACCENT))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(track.adjusted(-2, -2, 2, 2), self.TRACK_H / 2 + 2, self.TRACK_H / 2 + 2)
        if self.text():
            txt = QColor(theme.TEXT if self.isChecked() else theme.MUTED)
            if not enabled:
                txt.setAlpha(120)
            p.setPen(txt)
            r = self.rect().adjusted(self.TRACK_W + self.GAP + 1, 0, 0, 0)
            p.drawText(r, Qt.AlignVCenter | Qt.AlignLeft, self.text())
        p.end()
