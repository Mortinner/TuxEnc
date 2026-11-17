import os, sys, time, subprocess
sys.path.insert(0, "/home/claude/tuxenc")
os.environ["TUXENC_FFMPEG_DIR"] = "/home/claude/dl/rel-8.1/ffmpeg-n8.1-latest-linux64-gpl-shared-8.1/bin"
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
M = "/home/claude/testmedia/"
w.add_paths([M + "clip1.mp4", M + "clip2.mp4"]); pump(2)
w._start(); pump(3)
ni = lambda: subprocess.run("ps -o ni=,comm= -C ffmpeg", shell=True, capture_output=True, text=True).stdout.split()
print("prioridad normal, en marcha:", ni(), "| corriendo:", sum(1 for j in w.engine.jobs if j.status == "running"))
w.prio_chk.setChecked(True); pump(1)
print("tras marcar 'Prioridad baja' en caliente:", ni())
tids = subprocess.run("for p in $(pgrep -x ffmpeg); do ps -L -o ni= -p $p; done | sort | uniq -c", shell=True, capture_output=True, text=True).stdout.split()
print("todos los hilos de ffmpeg (cuenta, nice):", tids)
w.engine.stop(); pump(2)
w.engine.retry(w.engine.jobs[0].id); w._start(); pump(3)
print("nuevo trabajo con prioridad baja desde el inicio:", ni())
w.engine.stop(); pump(1)
# aviso con motivo
from tuxenc.presets import import_handbrake
w._adapt(import_handbrake("/tmp/1080_pelis.json")[0].settings)
print("\nAVISO:\n" + msgs[-1])
w.engine.shutdown()
