import os, sys, time, subprocess
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from tests.media import FF, M, MEDIA  # noqa: E402,F401  (FFmpeg y vídeos de prueba)
os.environ["TUXENC_FFMPEG_DIR"] = FF
os.environ["XDG_CONFIG_HOME"] = "/tmp/tx-p-cfg"; os.environ["XDG_CACHE_HOME"] = "/tmp/tx-p-cache"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from tuxenc import i18n; i18n.set_language("es")
from tuxenc.app import _make_app
app = _make_app()
from tuxenc.config import Config
import tuxenc.ui.main_window as mw
from PySide6.QtWidgets import QMessageBox
msgs = []; QMessageBox.information = staticmethod(lambda *a, **k: msgs.append(a[2]))
cfg = Config(); cfg.low_priority = False
cfg.settings = {"video_encoder": "libx265", "speed_preset": "medium", "audio_codec": "aac"}
w = mw.MainWindow(cfg); w.resize(956, 900); w.show()
def pump(sec):
    t = time.time()
    while time.time() - t < sec: app.processEvents(); time.sleep(0.03)
pump(3)
print("opciones simultáneos:", [w.par_combo.itemText(i) for i in range(w.par_combo.count())])
w.par_combo.setCurrentIndex(w.par_combo.findData(1)); pump(0.2)
print("elegido 1 ->", "engine.max_parallel =", w.engine.max_parallel, "| cfg.parallel =", cfg.parallel)
w.add_paths([M + "clip1.mp4", M + "clip2.mp4"]); pump(2)
w._start(); pump(3)
ni = lambda: subprocess.run("ps -o ni=,comm= -C ffmpeg", shell=True, capture_output=True, text=True).stdout.split()
print("prioridad normal, en marcha:", ni(), "| corriendo:", sum(1 for j in w.engine.jobs if j.status == "running"))
w.prio_chk.setChecked(True); pump(1)
print("tras marcar 'Prioridad baja' en caliente:", ni())
nices = [int(v) for v in ni()[::2]]
assert nices and min(nices) >= 10, f"«Prioridad baja» no se aplicó en caliente: {nices}"
tids = subprocess.run("for p in $(pgrep -x ffmpeg); do ps -L -o ni= -p $p; done | sort | uniq -c", shell=True, capture_output=True, text=True).stdout.split()
print("todos los hilos de ffmpeg (cuenta, nice):", tids)
w.engine.stop(); pump(2)
w.engine.retry(w.engine.jobs[0].id); w._start(); pump(3)
print("nuevo trabajo con prioridad baja desde el inicio:", ni())
w.engine.stop(); pump(1)
# aviso con motivo
from tuxenc.presets import import_handbrake
w._adapt(import_handbrake(str(__import__("pathlib").Path(__file__).resolve().parent / "fixtures" / "handbrake-1080-pelis.json"))[0].settings)
print("\nAVISO:\n" + msgs[-1])
assert w.engine.max_parallel == 1 and cfg.parallel == 1
w.engine.shutdown()
