import os, shutil, sys, time
from pathlib import Path
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from tests.media import FF, M, MEDIA  # noqa: E402,F401  (FFmpeg y vídeos de prueba)
T = Path("/tmp/tx-big"); shutil.rmtree(T, ignore_errors=True); T.mkdir()
os.environ.update(TUXENC_FFMPEG_DIR=FF,
                  XDG_CONFIG_HOME=str(T/"c"), XDG_CACHE_HOME=str(T/"k"), XDG_STATE_HOME=str(T/"s"), QT_QPA_PLATFORM="offscreen")
lang = sys.argv[1] if len(sys.argv) > 1 else "es"
from tuxenc import i18n; i18n.set_language(lang)
from tuxenc.app import _make_app
app = _make_app()
import tuxenc.ui.main_window as mw
from tuxenc import library as L
from PySide6.QtWidgets import QMessageBox
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QMessageBox.warning = staticmethod(lambda *a, **k: print("AVISO:", a[2]))
binp = T/"Papelera"; binp.mkdir()
L.trash = lambda p: (shutil.move(str(p), binp / Path(p).name) if Path(p).exists() else None) or True
from tests.fake_search import FakeSearcher
from tuxenc.config import Config
def pump(sec):
    t = time.time()
    while time.time() - t < sec: app.processEvents(); time.sleep(0.03)
def wait(c, to=120):
    t = time.time()
    while not c() and time.time() - t < to: pump(0.1)
    return c()
down = T/"Descargas"; down.mkdir()
for f in ("Babel.2006.BluRay.mkv", "Babel.2006.BluRay.spa.forced.srt"):
    shutil.copy(M + f"lib/{f}", down/f)
cfg = Config(); cfg.rename_on = True; cfg.convert_on = True; cfg.output_mode = "library"
cfg.series_root, cfg.movie_root = str(T/"Series"), str(T/"Peliculas"); cfg.original_after = "trash"
cfg.settings = {"video_encoder": "libx264", "speed_preset": "ultrafast", "rate_mode": "cbr", "bitrate": 30000, "audio_codec": "aac", "copy_if_lower": False}
w = mw.MainWindow(cfg); w.resize(1100, 420); w.show(); pump(1); w.rename.lib.searcher = FakeSearcher()
w._bar_dismissed.add("tmdb"); w._update_bar()
w.add_paths([str(down)]); assert wait(lambda: w.engine.jobs and w.engine.jobs[0].ident == "ok")
w._start(); job = w.engine.jobs[0]; assert wait(lambda: job.status == "done")
pump(0.5)
print("ocupa:", job.out_size, "vs original", job.info.size, "| bigger:", job.bigger)
print("original intacto aunque la opción era «papelera»:", (down/"Babel.2006.BluRay.mkv").exists())
row = w.queue.rows[job.id][1]
print("pregunta visible:", row.decide.isVisible(), "|", row.decide_lbl.text())
w.grab().save(f"/tmp/shots-merge/{lang}-9-ocupa-mas.png")
w._on_row_action("use_orig", job.id); assert wait(lambda: job.decision == "original")
pump(0.3)
print("estado:", row.state.text(), "| pregunta visible:", row.decide.isVisible())
lib_files = sorted(str(p.relative_to(T)) for p in (T/"Peliculas").rglob("*") if p.is_file())
print("en la biblioteca:", lib_files)
print("es el original:", (T/"Peliculas/B/Babel (2006) - [1080p].mkv").read_bytes() == (MEDIA / "lib/Babel.2006.BluRay.mkv").read_bytes())
print("en la papelera:", sorted(p.name for p in binp.iterdir()), "| Descargas:", sorted(p.name for p in down.iterdir()))
w.grab().save(f"/tmp/shots-merge/{lang}-10-original.png")
w.engine.shutdown(); w.rename.shutdown()
