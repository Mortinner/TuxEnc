"""1.2.3: una sola lista. Con la cola en marcha, lo nuevo queda pendiente y el botón pasa a
«Añadir (n)» / «Renombrar (n)». Caso real de Marcos: apagar «Convertir» con la cola en marcha."""
import os, shutil, sys, time
from pathlib import Path
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from tests.media import FF, M, MEDIA  # noqa: E402,F401  (FFmpeg y vídeos de prueba)
T = Path("/tmp/tx-pend"); shutil.rmtree(T, ignore_errors=True); T.mkdir()
os.environ.update(TUXENC_FFMPEG_DIR=FF,
                  XDG_CONFIG_HOME=str(T/"c"), XDG_CACHE_HOME=str(T/"k"), XDG_STATE_HOME=str(T/"s"),
                  QT_QPA_PLATFORM="offscreen", PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
lang = sys.argv[1] if len(sys.argv) > 1 else "es"
from tuxenc import i18n; i18n.set_language(lang)
from tuxenc.app import _make_app
app = _make_app()
import tuxenc.ui.main_window as mw
from tuxenc.config import Config
from tests.fake_search import FakeSearcher
from PySide6.QtWidgets import QMessageBox
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: print("   aviso:", a[2][:90]))
def pump(sec):
    t = time.time()
    while time.time() - t < sec: app.processEvents(); time.sleep(0.03)
def wait(c, to=60):
    t = time.time()
    while not c() and time.time() - t < to: pump(0.1)
    return c()
O = Path("/tmp/shots-merge")
src = T / "src"; src.mkdir()
for i in (1, 2, 3):
    shutil.copy(M + "chosen-remux.mkv", src / f"pelicula{i}.mkv")
down = T / "down"; down.mkdir()
for n in ("Arrow.S01E02.1080p.WEB-DL.mkv", "Arrow.S01E03.1080p.WEB-DL.mkv"):
    shutil.copy(M + f"lib/{n}", down / n)

cfg = Config(); cfg.engines_notice_shown = True; cfg.convert_on = True; cfg.rename_on = False; cfg.parallel = 1
cfg.settings = {"video_encoder": "libx265", "rate_mode": "crf", "quality": 24, "preset": "slow"}
w = mw.MainWindow(cfg); w.resize(1280, 820); w.show(); pump(1)
w.rename.lib.searcher = FakeSearcher()
btn = lambda: (w.start_btn.text().strip(), w.start_btn.isEnabled())
running = lambda: sum(1 for j in w.engine.jobs if j.status in ("running", "preparing"))

w.add_paths([str(src / "pelicula1.mkv"), str(src / "pelicula2.mkv")])
assert wait(lambda: len(w.engine.jobs) == 2 and not w.pending_probes)
print("parada, 2 añadidos → botón:", btn(), "| simultáneos editable:", w.par_combo.isEnabled())
w.start_btn.click(); pump(0.5)
assert wait(lambda: running() == 1, 30)
print("en marcha → botón:", btn(), "| simultáneos editable:", w.par_combo.isEnabled())

# 1) añadir otra conversión con la cola en marcha: queda pendiente; «Añadir» la suma sin subir simultáneos
w.add_paths([str(src / "pelicula3.mkv")]); assert wait(lambda: len(w.engine.jobs) == 3 and not w.pending_probes)
print("nuevo pendiente → botón:", btn(), "| estado:", w.status_lbl.text())
pump(0.4); w.grab().save(str(O / f"{lang}-25-pendiente-anadir.png"))
w.start_btn.click(); pump(1)
p3 = next(j for j in w.engine.jobs if j.name == "pelicula3.mkv")
print("tras «Añadir» →", p3.status, "| en marcha a la vez:", running(), "(máx. 1) | botón:", btn())
q = p3.settings.quality
w.panel.load(w.panel.settings.__class__(**{**w.panel.settings.to_dict(), "quality": 33})); w.panel.changed.emit(); pump(0.2)
print("cambiar el preset después no le afecta:", p3.settings.quality == q)

# 2) el caso de Marcos: Convertir OFF + Renombrar ON y se añaden capítulos
w.conv_btn.setChecked(False); w.ren_btn.setChecked(True); pump(0.3)
w.add_paths([str(down)])
assert wait(lambda: sum(1 for j in w.engine.jobs if j.staged and j.ident == "ok") == 2)
print("capítulos pendientes → botón:", btn(), "| ¿convirtiéndose alguno?:",
      any(j.status in ("running", "preparing") for j in w.engine.jobs if "Arrow" in j.name))
pump(0.4); w.grab().save(str(O / f"{lang}-26-pendiente-renombrar.png"))
w.start_btn.click()
assert wait(lambda: sum(1 for j in w.engine.jobs if j.renamed_to) == 2, 30)
print("renombrados al momento:", [Path(j.renamed_to).name for j in w.engine.jobs if j.renamed_to])
print("   la cola sigue convirtiendo:", running() == 1, "| botón:", btn())

# 3) Detener: lo que no había empezado vuelve a pendiente
w.conv_btn.setChecked(True); w.ren_btn.setChecked(False); pump(0.3)
mw.QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
w._stop()
wait(lambda: not w.engine.is_busy(), 20); pump(0.5)
print("   motor:", w.engine.active, w.engine.counts(), {j.name: j.status for j in w.engine.jobs})
pend = [j.name for j in w.pending_jobs()]
print("tras Detener → pendientes:", pend, "| botón:", btn(), "| simultáneos editable:", w.par_combo.isEnabled())
w.engine.shutdown(); w.rename.shutdown()
