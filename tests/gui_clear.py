"""Menú «Limpiar»: terminados, sin empezar y vaciar la cola con conversiones en marcha."""
import os, shutil, sys, time
from pathlib import Path
sys.path.insert(0, "/home/claude/tuxenc")
T = Path("/tmp/tx-clear"); shutil.rmtree(T, ignore_errors=True); T.mkdir()
os.environ.update(TUXENC_FFMPEG_DIR="/home/claude/dl/rel-8.1/ffmpeg-n8.1-latest-linux64-gpl-shared-8.1/bin",
                  XDG_CONFIG_HOME=str(T/"c"), XDG_CACHE_HOME=str(T/"k"), XDG_STATE_HOME=str(T/"s"), QT_QPA_PLATFORM="offscreen")
lang = sys.argv[1] if len(sys.argv) > 1 else "es"
from tuxenc import i18n; i18n.set_language(lang)
from tuxenc.app import _make_app
app = _make_app()
import tuxenc.ui.main_window as mw
from tuxenc.config import Config
from PySide6.QtWidgets import QMessageBox
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
def pump(sec):
    t = time.time()
    while time.time() - t < sec: app.processEvents(); time.sleep(0.03)
src = Path("/home/claude/testmedia/chosen-remux.mkv")
files = []
for i in range(1, 13):
    f = T / f"Serie equivocada S01E{i:02}.mkv"; shutil.copy(src, f); files.append(str(f))
cfg = Config(); cfg.parallel = 1
cfg.settings = {"video_encoder": "libx265", "rate_mode": "crf", "quality": 22, "preset": "slow"}
w = mw.MainWindow(cfg); w.resize(1280, 820); w.show(); pump(1)
w.engine.set_parallel(1)
w.add_paths(files)
t0 = time.time()
while (w.pending_probes or len(w.engine.jobs) < 12) and time.time() - t0 < 60: pump(0.2)
ended = []
orig_end = getattr(w, "_run_end_action", None)
w._start(); pump(3)
st = lambda: sorted({j.status for j in w.engine.jobs})
print("en cola:", len(w.engine.jobs), st())
w._fill_clear_menu()
print("menú:", [a.text() for a in w.clear_menu.actions() if a.text()])
w.clear_menu.popup(w.clear_btn.mapToGlobal(w.clear_btn.rect().bottomLeft())); pump(0.4)
from PySide6.QtGui import QPainter
img = w.grab(); pnt = QPainter(img)
pnt.drawPixmap(w.clear_btn.mapTo(w, w.clear_btn.rect().bottomLeft()), w.clear_menu.grab()); pnt.end()
img.save(f"/tmp/shots-merge/{lang}-12-limpiar.png"); w.clear_menu.hide()
w._clear_pending(); pump(0.5)
print("tras quitar sin empezar:", len(w.engine.jobs), st(), "| activa:", w.engine.active)
w._clear_all(); wait_ok = (lambda t0=time.time(): [pump(0.2) for _ in iter(lambda: bool(w.engine.running) and time.time() - t0 < 20, False)])(); 
print("tras vaciar:", len(w.engine.jobs), "| activa:", w.engine.active, "| en marcha:", len(w.engine.running),
      "| botón activo:", w.clear_btn.isEnabled(), "| restos:", sorted(p.name for p in T.glob("*.tmp*")) or "ninguno",
      "| originales:", len(list(T.glob("Serie*.mkv"))))
w.engine.shutdown()
