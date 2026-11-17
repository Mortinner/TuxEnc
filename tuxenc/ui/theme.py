"""Tema visual oscuro de TuxEnc (mismos colores que el icono)."""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

BG = "#141a2c"
PANEL = "#1b2238"
PANEL2 = "#222b47"
BORDER = "#2c3658"
TEXT = "#e8ecf7"
MUTED = "#8d97b5"
ACCENT = "#2fd5ff"
WARM = "#ff7a3d"
PINK = "#ff5e8a"
OK = "#3ddc97"
BAD = "#ff5d6c"
AMBER = "#ffc24b"

QSS = f"""
QWidget {{ color: {TEXT}; font-size: 10pt; }}
QMainWindow, QDialog {{ background: {BG}; }}
QToolTip {{ background: {PANEL2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}
QLabel#Title {{ font-size: 15pt; font-weight: 700; }}
QLabel#Muted, QLabel.muted {{ color: {MUTED}; }}
QLabel#Summary {{ color: {MUTED}; padding: 2px 0; }}
QLabel#DropTitle {{ font-size: 14pt; font-weight: 600; }}
QLabel#SectionTitle {{ font-weight: 700; color: {ACCENT}; padding-top: 6px; }}
QFrame#Card, QWidget#Card {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#DropZone {{ background: {PANEL}; border: 2px dashed {BORDER}; border-radius: 16px; }}
QFrame#DropZone[hover="true"] {{ border-color: {ACCENT}; }}
QFrame#Footer {{ background: {PANEL}; border-top: 1px solid {BORDER}; }}

QPushButton, QToolButton {{
    background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 6px 12px; min-height: 18px;
}}
QPushButton:hover, QToolButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled, QToolButton:disabled {{ color: #5b6585; border-color: #252e4a; }}
QPushButton#Primary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {WARM}, stop:1 {PINK});
    border: none; color: white; font-weight: 700; padding: 8px 22px;
}}
QPushButton#Primary:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff8c55, stop:1 #ff76a0); }}
QPushButton#Primary:disabled {{ background: {PANEL2}; color: #5b6585; }}
QToolButton#Mode {{ padding: 5px 12px; color: {MUTED}; }}
QToolButton#Mode:checked {{ background: #1f3b52; border-color: {ACCENT}; color: {TEXT}; font-weight: 600; }}
QToolButton#Flat {{ background: transparent; border: none; padding: 3px 6px; color: {MUTED}; }}
QToolButton#Flat:hover {{ color: {TEXT}; background: {PANEL2}; border-radius: 6px; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}

QComboBox, QSpinBox, QLineEdit {{
    background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 5px 8px;
    min-height: 18px;
}}
QComboBox:hover, QSpinBox:hover, QLineEdit:hover {{ border-color: {ACCENT}; }}
QComboBox:disabled, QSpinBox:disabled, QLineEdit:disabled {{ color: #5b6585; background: #1a2135; border-color: #232c46; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {PANEL2}; border: 1px solid {BORDER}; selection-background-color: {BORDER};
    outline: none; padding: 4px;
}}
QComboBox#PresetCombo {{ font-weight: 600; padding: 6px 10px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; border: none; }}

QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px; border: 1px solid {BORDER}; background: {PANEL2};
}}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ image: url(@CHECK@); }}
QListWidget#TrackList::indicator {{ width: 16px; height: 16px; border: 1px solid {BORDER}; border-radius: 4px; background: {BG}; }}
QListWidget#TrackList::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url(@CHECK@); }}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ background: #1a2135; }}

QSlider::groove:horizontal {{ height: 6px; background: {PANEL2}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: white; width: 16px; margin: -6px 0; border-radius: 8px; }}
QSlider::handle:horizontal:disabled {{ background: #5b6585; }}
QSlider::sub-page:horizontal:disabled {{ background: #3a4466; }}

QProgressBar {{ background: {PANEL2}; border: none; border-radius: 3px; text-align: center; }}
QProgressBar::chunk {{
    border-radius: 3px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {WARM}, stop:0.5 {PINK}, stop:1 {ACCENT});
}}
QProgressBar#Thin {{ max-height: 5px; min-height: 5px; }}
QProgressBar#Done::chunk {{ background: {OK}; }}
QProgressBar#Bad::chunk {{ background: {BAD}; }}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent; color: {MUTED}; padding: 8px 12px; border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ border: none; padding: 0; margin: 0 0 6px 0; }}
QListWidget::item:selected {{ background: transparent; }}
QListWidget#LangList {{ background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 2px; }}
QListWidget#LangList::item {{ padding: 4px 8px; margin: 1px; border-radius: 6px; }}
QListWidget#LangList::item:selected {{ background: {BORDER}; }}
QListWidget#TrackList {{ background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px; }}
QListWidget#TrackList::item {{ padding: 4px; margin: 0; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QMenu {{ background: {PANEL2}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {BORDER}; }}
QMenu::item:disabled {{ color: {MUTED}; background: transparent; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}
QSplitter::handle {{ background: {BG}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
"""


def apply(app: QApplication) -> None:
    app.setStyle(QStyleFactory.create("Fusion"))
    pal = QPalette()
    roles = {
        QPalette.Window: BG, QPalette.WindowText: TEXT, QPalette.Base: PANEL2,
        QPalette.AlternateBase: PANEL, QPalette.Text: TEXT, QPalette.Button: PANEL2,
        QPalette.ButtonText: TEXT, QPalette.Highlight: "#2f6bd8", QPalette.HighlightedText: "#ffffff",
        QPalette.ToolTipBase: PANEL2, QPalette.ToolTipText: TEXT, QPalette.PlaceholderText: MUTED,
        QPalette.Link: ACCENT,
    }
    for role, color in roles.items():
        pal.setColor(role, QColor(color))
    for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
        pal.setColor(QPalette.Disabled, role, QColor("#5b6585"))
    app.setPalette(pal)
    from ..paths import ASSETS_DIR
    app.setStyleSheet(QSS.replace("@CHECK@", str(ASSETS_DIR / "check.svg")))
