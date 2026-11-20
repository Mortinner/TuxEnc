"""Prueba de punta a punta de la interfaz unificada (offscreen, buscador simulado)."""
import os, shutil, sys, time
from pathlib import Path
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from tests.media import FF, M, MEDIA  # noqa: E402,F401  (FFmpeg y vídeos de prueba)
T = Path("/tmp/tx-merge"); shutil.rmtree(T, ignore_errors=True); T.mkdir()
os.environ.update(TUXENC_FFMPEG_DIR=FF,
                  XDG_CONFIG_HOME=str(T / "cfg"), XDG_CACHE_HOME=str(T / "cache"), XDG_STATE_HOME=str(T / "state"),
                  QT_QPA_PLATFORM="offscreen")
lang = sys.argv[1] if len(sys.argv) > 1 else "es"
from tuxenc import i18n; i18n.set_language(lang)
from tuxenc.app import _make_app
app = _make_app()
import tuxenc.ui.main_window as mw
from PySide6.QtWidgets import QMessageBox
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
msgs = []; QMessageBox.information = staticmethod(lambda *a, **k: msgs.append(a[2]))
QMessageBox.warning = staticmethod(lambda *a, **k: msgs.append("WARN " + a[2]))
from tests.fake_search import FakeSearcher, BATMAN
from tuxenc.config import Config
shots = Path("/tmp/shots-merge"); shots.mkdir(exist_ok=True)

def pump(sec):
    t = time.time()
    while time.time() - t < sec:
        app.processEvents(); time.sleep(0.03)

def wait(cond, timeout=120):
    t = time.time()
    while not cond() and time.time() - t < timeout:
        pump(0.2)
    return cond()

down = T / "Descargas"; shutil.copytree(MEDIA / "lib", down)
lib_series, lib_movies = T / "Multimedia/Series", T / "Multimedia/Peliculas"
cfg = Config(); cfg.advanced_open = False
cfg.series_root, cfg.movie_root = str(lib_series), str(lib_movies)
cfg.settings = {"video_encoder": "libx264", "speed_preset": "ultrafast", "max_height": 1080, "audio_codec": "aac"}
w = mw.MainWindow(cfg); w.resize(1100, 900); w.show(); pump(1.5)
w.rename.lib.searcher = FakeSearcher()

# ---------------- 1) solo renombrar
w.conv_btn.setChecked(False); w.ren_btn.setChecked(True); pump(0.3)
w.out_combo.setCurrentIndex(w.out_combo.findData("library")); w._on_output_chosen(w.out_combo.currentIndex()); pump(0.3)
print("salida:", w.cfg.output_mode, "| barra visible:", w.bar.isVisible(), "-", w.bar_lbl.text()[:60])
w.add_paths([str(down)]); assert wait(lambda: len(w.engine.jobs) == 4 and all(j.ident != "pending" for j in w.engine.jobs))
for j in w.engine.jobs: print(f"  {j.name:34s} {j.ident:9s} {j.note[:60]!s:60s} -> {j.preview}")
w.grab().save(str(shots / f"{lang}-1-identificados.png"))
from tuxenc.ui.rename_ctrl import MatchDialog
batman = next(j for j in w.engine.jobs if "Batman" in j.name)
d = MatchDialog(w.rename, batman, w); d.show(); pump(0.4); d.grab().save(str(shots / f"{lang}-2-coincidencia.png")); d.close()
w.rename._submit(w.rename._choose_task, batman.id, batman.rt, BATMAN)
assert wait(lambda: batman.ident == "ok")
print("  elegido a mano:", batman.note, "->", batman.preview)
w._start(); assert wait(lambda: all(j.status == "done" for j in w.engine.jobs))
pump(0.5); w.grab().save(str(shots / f"{lang}-3-renombrados.png"))
print("RENOMBRADOS:"); [print("  ", p.relative_to(T)) for p in sorted((T / "Multimedia").rglob("*")) if p.is_file()]
print("quedan en Descargas:", sorted(p.name for p in down.iterdir()))
print("deshacer visible:", w.undo_btn.isVisible())
w._undo_rename(); assert wait(lambda: all(j.status == "waiting" for j in w.engine.jobs))
print("tras deshacer, Descargas:", len(list(down.iterdir())), "archivos | biblioteca vacía:", not any(p.is_file() for p in (T / "Multimedia").rglob("*")), "|", msgs[-1])

# ---------------- 2) convertir + renombrar
w.conv_btn.setChecked(True); pump(0.3)
batman.ident = "ambiguous"; batman.rt = batman.rt.__class__(batman.rt.path, batman.rt.parsed, True, batman.rt.candidates)  # vuelve a dudosa
w.rename.update_preview(batman); w.queue.sync(w.engine.jobs)
w.engine.set_parallel(2)
w._start(); pump(1.5)
print("retenido (dudoso):", batman.hold, batman.status)
w.grab().save(str(shots / f"{lang}-4-convirtiendo.png"))
assert wait(lambda: all(j.status == "done" for j in w.engine.jobs if not j.hold), 300)
print("los identificados terminaron; Batman sigue esperando:", batman.status, batman.hold, "| cola sigue abierta:", w.engine.active)
w.rename._submit(w.rename._choose_task, batman.id, batman.rt, BATMAN)
assert wait(lambda: batman.status == "done", 300)
pump(1); w.grab().save(str(shots / f"{lang}-5-convertidos.png"))
print("CONVERTIDOS:")
from tuxenc.probe import probe
import subprocess
for p in sorted((T / "Multimedia").rglob("*")):
    if p.is_file():
        extra = ""
        if p.suffix == ".mkv":
            i = probe(str(p)); v = i.main_video
            tags = subprocess.run([os.environ["TUXENC_FFMPEG_DIR"] + "/ffprobe", "-v", "error", "-show_entries", "format_tags=title,show,season_number,episode_sort", "-of", "compact=p=0", str(p)], capture_output=True, text=True).stdout.strip()
            extra = f"  [{v.width}x{v.height} {v.codec}] {tags}"
        print("  ", p.relative_to(T), extra)
print("originales intactos:", len(list(down.iterdir())), "| avisos:", [j.warning for j in w.engine.jobs if j.warning])
print("cola terminada:", not w.engine.active)
w.engine.shutdown()
