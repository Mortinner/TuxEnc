"""Vista de la cola: una fila por vídeo y zona de arrastre cuando está vacía."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPixmap
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMenu, QProgressBar, QPushButton, QSizePolicy, QToolButton,
                               QVBoxLayout, QWidget)

from ..engine import (ACTIVE, CANCELLED, DONE, FAILED, PAUSED, PREPARING, RUNNING, WAITING, Job)
from ..i18n import tr
from ..paths import ASSETS_DIR
from ..probe import format_duration
from . import theme

_DOT = {WAITING: theme.MUTED, PREPARING: theme.AMBER, RUNNING: theme.ACCENT,
        PAUSED: theme.AMBER, DONE: theme.OK, FAILED: theme.BAD, CANCELLED: theme.MUTED}


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit in ("B", "KB") else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


class ElidedLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full = text
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setText(text)

    def setText(self, text):  # noqa: N802
        self._full = text
        self._elide()

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self._elide()

    def _elide(self):
        fm = QFontMetrics(self.font())
        super().setText(fm.elidedText(self._full, Qt.ElideMiddle, max(40, self.width())))
        self.setToolTip(self._full)


# Modo actual de la ventana (lo actualiza MainWindow): sin «Convertir», «Pistas…» no aplica
MODE = {"convert": True, "rename": False, "active": False}


def _css(widget, css: str) -> None:
    """setStyleSheet es caro en Qt (y gasta memoria): solo se aplica si el estilo cambia."""
    if widget.property("_css") != css:
        widget.setProperty("_css", css)
        widget.setStyleSheet(css)


class JobRow(QFrame):
    action = Signal(str, int)        # (acción, job_id)

    def __init__(self, job: Job, parent=None):
        super().__init__(parent)
        self.job_id = job.id
        self.setObjectName("Card")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 10, 10)
        lay.setSpacing(12)

        self.dot = QLabel()
        self.dot.setFixedSize(10, 10)
        lay.addWidget(self.dot, 0, Qt.AlignVCenter)

        mid = QVBoxLayout()
        mid.setSpacing(4)
        self.name = ElidedLabel(job.name)
        self.name.setStyleSheet("font-weight: 600;")
        self.detail = ElidedLabel(job.info.summary())
        self.detail.setObjectName("Muted")
        # Renombrado: qué es (identificación) y cómo quedará
        self.ident = ElidedLabel("")
        self.target = ElidedLabel("")
        self.target.setObjectName("Muted")
        self.copied = ElidedLabel("")
        self.copied.setStyleSheet(f"color: {theme.ACCENT};")
        self.bar = QProgressBar()
        self.bar.setObjectName("Thin")
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self.name, 1)
        self.task = QLabel()
        self.task.setStyleSheet("font-size: 11px;")
        top.addWidget(self.task, 0)
        mid.addLayout(top)
        mid.addWidget(self.detail)
        mid.addWidget(self.ident)
        mid.addWidget(self.target)
        mid.addWidget(self.copied)
        # El convertido ocupa más que el original: el usuario decide
        self.decide = QWidget()
        dl = QHBoxLayout(self.decide)
        dl.setContentsMargins(0, 2, 0, 2)
        dl.setSpacing(6)
        self.decide_lbl = QLabel()
        self.decide_lbl.setStyleSheet(f"color: {theme.AMBER};")
        dl.addWidget(self.decide_lbl)
        for key, text, tip in (("use_conv", tr("bigger_use_conv"), tr("bigger_use_conv_tip")),
                               ("use_orig", tr("bigger_use_orig"), tr("bigger_use_orig_tip")),
                               ("keep_both", tr("bigger_keep_both"), tr("bigger_keep_both_tip"))):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, k=key: self.action.emit(k, self.job_id))
            dl.addWidget(b)
        dl.addStretch(1)
        mid.addWidget(self.decide)
        mid.addWidget(self.bar)
        lay.addLayout(mid, 1)

        right = QVBoxLayout()
        right.setSpacing(4)
        self.state = QLabel()
        self.state.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.state.setMinimumWidth(190)
        right.addWidget(self.state)
        btns = QHBoxLayout()
        btns.setSpacing(2)
        btns.setAlignment(Qt.AlignRight)
        self.buttons: dict[str, QToolButton] = {}
        for key, text, tip in (("match", tr("match_btn"), tr("match_tip")),
                               ("tracks", tr("tracks"), tr("tracks_tip")),
                               ("log", tr("view_log"), tr("view_log")),
                               ("retry", "↻", tr("retry")),
                               ("play", "▶", tr("play")),
                               ("folder", tr("open_folder"), tr("open_folder")),
                               ("cancel", "✕", tr("cancel_job")),
                               ("remove", "✕", tr("remove"))):
            b = QToolButton()
            b.setObjectName("Flat")
            b.setText(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, k=key: self.action.emit(k, self.job_id))
            btns.addWidget(b)
            self.buttons[key] = b
        right.addLayout(btns)
        lay.addLayout(right, 0)
        self.update_from(job)

    def contextMenuEvent(self, e):  # noqa: N802
        self.action.emit("menu", self.job_id)

    def mouseDoubleClickEvent(self, e):  # noqa: N802
        self.action.emit("double", self.job_id)

    def update_from(self, job: Job) -> None:
        st = job.status
        # Tarea del vídeo: mientras está pendiente, la que marcan los interruptores; después, la que se fijó
        conv = MODE["convert"] if job.staged else job.task_convert
        ren = MODE["rename"] if job.staged else job.task_rename
        key = "task_both" if conv and ren else "task_conv" if conv else "task_ren" if ren else "task_none"
        color = {"task_both": theme.ACCENT, "task_conv": theme.WARM, "task_ren": theme.AMBER}.get(key, theme.MUTED)
        self.task.setText(tr(key))
        _css(self.task, f"font-size: 11px; font-weight: 600; color: {color}; border: 1px solid {color};"
                                " border-radius: 8px; padding: 1px 8px;")
        _css(self.dot, f"background: {_DOT[st]}; border-radius: 5px;")
        detail = job.info.summary()
        if job.output and st not in (WAITING,) and not job.rename:
            detail += "  →  " + job.output.rsplit("/", 1)[-1]
        if job.audio_override is not None or job.sub_override is not None \
                or job.burn_override is not None:
            detail += f"  · {tr('custom_tracks')}"
        self.detail.setText(detail)

        # Con renombrado, las dos líneas (identificación y nombre nuevo) se reservan desde el principio,
        # aunque aún estén vacías: si la fila crece al identificarse, Qt la pinta un instante aplastada
        # (la etiqueta de la tarea salía como un rectángulo encima del título).
        renaming = job.ident != "off" or bool(MODE["rename"] if job.staged else job.task_rename)
        self.ident.setVisible(renaming)
        if renaming:
            color = {"ok": theme.OK, "pending": theme.MUTED}.get(job.ident, theme.AMBER)
            _css(self.ident, f"color: {color};")
            self.ident.setText(job.note or "\u00a0")
        final = job.renamed_to or (job.output if job.rename and st in (DONE,) else "")
        target = ("→ " + final) if final else (("→ " + job.preview) if job.preview else "")
        self.target.setVisible(renaming)
        self.target.setText(target or "\u00a0")
        copied = job.plan is not None and job.plan.video_copied and st != WAITING
        self.copied.setVisible(copied)
        if copied:
            self.copied.setText("ℹ " + tr("video_copied", src=job.plan.src_kbps,
                                         dst=job.settings.bitrate if job.settings else 0))
        asking = st == DONE and job.bigger and not job.decision
        self.decide.setVisible(asking)
        if asking:
            pct = job.out_size / job.info.size * 100 if job.info.size else 0
            self.decide_lbl.setText(tr("bigger_q", pct=f"{pct:.0f}"))

        self.bar.setObjectName("Thin")
        if st == DONE:
            self.bar.setValue(1000)
            self.bar.setObjectName("Done")
        elif st == FAILED:
            self.bar.setObjectName("Bad")
        else:
            self.bar.setValue(int(job.progress * 1000))
        _css(self.bar, "max-height: 5px; min-height: 5px;")
        self.bar.style().unpolish(self.bar)
        self.bar.style().polish(self.bar)

        text = tr(f"st_{st}")
        if st in (RUNNING, PAUSED):
            bits = [f"{job.progress * 100:.0f}%"]
            if job.eta >= 0 and st == RUNNING:
                bits.append(tr("remaining", t=format_duration(job.eta)))
            if job.fps and st == RUNNING:
                bits.append(f"{job.fps:.0f} fps")
            if job.pass_total > 1:
                bits.append(tr("pass_n", n=job.pass_no, t=job.pass_total))
            text = (tr("st_paused") + " · " if st == PAUSED else "") + " · ".join(bits)
        elif st == DONE and job.decision in ("original", "converted"):
            text = tr("bigger_kept_orig" if job.decision == "original" else "bigger_kept_conv")
        elif st == DONE and job.renamed_to:
            text = tr("renamed_ok")
        elif st == DONE:
            ratio = (f"{job.out_size / job.info.size * 100:.0f}%"
                     if job.info.size else "—")
            text = "✓ " + tr("done_info", size=human_size(job.out_size), ratio=ratio,
                             t=format_duration(job.elapsed))
        elif st == PREPARING and job.rename_state == "copying":
            text = "⇢ " + tr("rn_copying")
        elif st == PREPARING and job.rename_state == "moved":
            text = tr("rn_moved")
        elif st == PREPARING and job.task_rename and not job.task_convert:
            text = tr("rn_waiting")
        elif st == WAITING and job.hold:
            text = "⏳ " + tr("held")
        elif st == WAITING and job.staged and MODE.get("active"):
            text = "✚ " + tr("st_new")
        elif st == FAILED:
            text = "✕ " + tr("st_failed")
            self.setToolTip(job.error)
        if st == DONE and job.warning:
            text += "  ⚠"
            self.setToolTip(tr("post_warning", w=job.warning))
        self.state.setText(text)
        color = {DONE: theme.OK, FAILED: theme.BAD}.get(st, theme.TEXT if st in ACTIVE
                                                       else theme.MUTED)
        _css(self.state, f"color: {color};")

        vis = {
            "match": renaming and st == WAITING and job.ident != "pending",
            "tracks": (st == WAITING and conv
                       and bool(job.info.audio or job.info.subtitles)),
            "log": st in (FAILED, DONE) and bool(job.log_path) and not job.renamed_to,
            "retry": st in (FAILED, CANCELLED),
            "play": st == DONE,
            "folder": st == DONE,
            "cancel": st in ACTIVE,
            "remove": st not in ACTIVE,
        }
        for k, b in self.buttons.items():
            b.setVisible(vis[k])


class DropZone(QFrame):
    add_files = Signal()
    add_folder = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropZone")
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(12)
        icon = QLabel()
        pm = QPixmap(str(ASSETS_DIR / "tuxenc-256.png"))
        icon.setPixmap(pm.scaled(132, 132, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        icon.setAlignment(Qt.AlignCenter)
        title = QLabel(tr("drop_title"))
        title.setObjectName("DropTitle")
        title.setAlignment(Qt.AlignCenter)
        sub = QLabel(tr("drop_sub"))
        sub.setObjectName("Muted")
        sub.setAlignment(Qt.AlignCenter)
        row = QHBoxLayout()
        row.setAlignment(Qt.AlignCenter)
        b1 = QPushButton(tr("add_files"))
        b2 = QPushButton(tr("add_folder"))
        b1.clicked.connect(self.add_files)
        b2.clicked.connect(self.add_folder)
        row.addWidget(b1)
        row.addWidget(b2)
        lay.addWidget(icon)
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addSpacing(6)
        lay.addLayout(row)

    def set_hover(self, on: bool) -> None:
        self.setProperty("hover", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class QueueList(QListWidget):
    """Lista con una JobRow por elemento."""

    row_action = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.setSelectionMode(QListWidget.NoSelection)
        self.setSpacing(0)
        self.rows: dict[int, tuple[QListWidgetItem, JobRow]] = {}

    def sync(self, jobs: list[Job], refresh: bool = True) -> None:
        """Pone la lista igual que `jobs`. Con refresh=False solo añade y quita filas
        (al añadir cientos de vídeos, repintar todas las filas cada vez era lo que más costaba)."""
        ids = [j.id for j in jobs]
        wanted = set(ids)
        # quitar los que ya no están
        for jid in list(self.rows):
            if jid not in wanted:
                item, _row = self.rows.pop(jid)
                self.takeItem(self.row(item))
        current = [self.item(i).data(Qt.UserRole) for i in range(self.count())]
        if current != [i for i in ids if i in self.rows]:
            # el orden ha cambiado (p. ej. el usuario reordenó): se rehace la lista
            for jid in list(self.rows):
                item, _ = self.rows.pop(jid)
                self.takeItem(self.row(item))
        # los que faltan se insertan en su sitio; rehacerlo todo con cada vídeo nuevo era O(n²)
        for pos, j in enumerate(jobs):
            if j.id not in self.rows:
                self._add(j, pos)
            elif refresh:
                self.update_job(j)

    def _add(self, job: Job, pos: int | None = None) -> None:
        row = JobRow(job)
        row.action.connect(self.row_action)
        item = QListWidgetItem()
        item.setData(Qt.UserRole, job.id)
        item.setSizeHint(QSize(100, row.sizeHint().height() + 6))
        if pos is None or pos >= self.count():
            self.addItem(item)
        else:
            self.insertItem(pos, item)
        self.setItemWidget(item, row)
        self.rows[job.id] = (item, row)

    def update_job(self, job: Job) -> None:
        entry = self.rows.get(job.id)
        if entry:
            item, row = entry
            row.update_from(job)
            h = row.sizeHint().height() + 6
            if item.sizeHint().height() != h:
                item.setSizeHint(QSize(100, h))


def job_menu(parent: QWidget, job: Job) -> QMenu:
    m = QMenu(parent)
    acts = []
    if job.status == WAITING:
        if job.ident not in ("off", "pending"):
            acts += [("match", tr("match_btn"))]
        acts += [("tracks", tr("tracks")), ("up", tr("move_up")), ("down", tr("move_down"))]
    if job.status == DONE:
        acts += [("play", tr("play")), ("folder", tr("open_folder"))]
    if job.status in (FAILED, CANCELLED):
        acts += [("retry", tr("retry"))]
    if job.log_path:
        acts += [("log", tr("view_log"))]
    if job.status in ACTIVE:
        acts += [("cancel", tr("cancel_job"))]
    else:
        acts += [("remove", tr("remove"))]
    for key, label in acts:
        a = m.addAction(label)
        a.setData(key)
    return m
