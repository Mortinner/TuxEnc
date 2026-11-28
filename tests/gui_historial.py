"""Pestaña «Historial»: una tarjeta por vídeo, con el diseño de las filas de la cola (1.3.7)."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
T = Path(tempfile.mkdtemp(prefix="tx-historial-"))
os.environ.update(XDG_CONFIG_HOME=str(T / "c"), XDG_CACHE_HOME=str(T / "k"), XDG_STATE_HOME=str(T / "s"),
                  XDG_DATA_HOME=str(T / "d"), QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"),
                  PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
from tests.media import FF  # noqa: E402,F401

from tuxenc import activity, i18n  # noqa: E402
lang = sys.argv[1] if len(sys.argv) > 1 else "es"
i18n.set_language(lang)
from tuxenc.app import _make_app  # noqa: E402
from tuxenc.i18n import tr  # noqa: E402
app = _make_app()
import tuxenc.ui.history_view as hv  # noqa: E402
import tuxenc.ui.main_window as mw  # noqa: E402
import tuxenc.ui.settings_window as sw  # noqa: E402
from retitler.renamer import History  # noqa: E402
from tuxenc.config import Config  # noqa: E402


def pump(sec):
    t = time.time()
    while time.time() - t < sec:
        app.processEvents()
        time.sleep(0.03)


lib = T / "Series" / "Endeavour (2013)" / "Season 08"
lib.mkdir(parents=True)
final = lib / "Endeavour (2013) - S08E03 - Terminus - [1080p].mkv"
final.write_bytes(b"x")
h = History()
h.path.parent.mkdir(parents=True, exist_ok=True)
rows = [
    {"id": "a1", "time": "2026-11-25T07:18:43+00:00", "created_dirs": [],
     "moves": [[str(T / "Descargas/Telegram/8x03 - El detective Endeavour.mkv"), str(final)],
               [str(T / "Descargas/Telegram/8x03 - El detective Endeavour.es.srt"),
                str(final.with_suffix(".es.srt"))]]},
    {"id": "b2", "time": "2026-11-26T10:00:00+00:00", "created_dirs": [],
     "moves": [[str(T / "Descargas/Babel.2006.mkv"), str(T / "Peliculas/B/Babel (2006) - [1080p].mkv")]]},
    {"id": "b2", "undone": "2026-11-26T10:05:00+00:00"},
]
h.path.write_text("".join(json.dumps(r) + "\n" for r in rows))
activity.record_conversion(str(T / "Descargas/Outlander 2x09.mkv"),
                           str(T / "Series/Outlander (2025)/Season 02/Outlander (2025) - S02E09 - Uno - [1080p].mkv"),
                           renamed=True, original="trash", subs=2)

cfg = Config()
cfg.engines_notice_shown = True
w = mw.MainWindow(cfg)
w.show()
pump(0.5)
assert "history" in sw.TABS
dlg = sw.SettingsWindow(w)
opened = {}
dlg.exec = lambda: (dlg.resize(900, 640), dlg.show(), pump(0.6),
                    dlg.grab().save(str(T / f"{lang}-historial.png")), opened.setdefault("ok", True))
dlg.open_tab("history")
cards = dlg.history.box.findChildren(hv.HistoryCard)
assert len(cards) == 3, len(cards)
texts = [" | ".join(lbl.text() for lbl in c.findChildren(hv.QLabel)) for c in cards]
print("\n".join(texts))
assert tr("hist_kind_convert_rename") in texts[0] and tr("hist_trashed") in texts[0]
assert tr("hist_undone") in texts[1]
assert tr("hist_kind_rename") in texts[2] and "Terminus" in texts[2] and "8x03 - El detective" in texts[2]
assert tr("hist_subs", n=1) in texts[2]
opened_dirs = []
hv._open = lambda folder: opened_dirs.append(folder)
cards[2].mouseDoubleClickEvent(None)
assert opened_dirs == [lib], opened_dirs
# Vacío
h.path.unlink()
activity.ACTIVITY_FILE.unlink()
dlg.history.reload()
assert dlg.history.summary.text() == tr("hist_empty") and not dlg.history.box.findChildren(hv.HistoryCard)
print("captura:", T / f"{lang}-historial.png")
print("TODO OK")
