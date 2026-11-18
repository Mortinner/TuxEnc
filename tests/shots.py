import os, sys, time
sys.path.insert(0, "/home/claude/tuxenc")
os.environ["TUXENC_FFMPEG_DIR"] = "/home/claude/dl/rel-8.1/ffmpeg-n8.1-latest-linux64-gpl-shared-8.1/bin"
os.environ["XDG_CONFIG_HOME"] = "/tmp/tx-shot-cfg"; os.environ["XDG_CACHE_HOME"] = "/tmp/tx-shot-cache"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
lang = sys.argv[1] if len(sys.argv) > 1 else "es"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from tuxenc import i18n
from tuxenc.config import Config
i18n.set_language(lang)
from tuxenc.app import _make_app
app = _make_app()
from tuxenc.ui.main_window import MainWindow
cfg = Config(); cfg.advanced_open = False
w = MainWindow(cfg); w.resize(1280, 760); w.show()
out = "/tmp/shots"; os.makedirs(out, exist_ok=True)
def pump(sec):
    t = time.time()
    while time.time() - t < sec: app.processEvents(); time.sleep(0.03)
pump(2.5)
w.grab().save(f"{out}/{lang}-1-empty.png")
M = "/home/claude/testmedia/"
w.add_paths([M + "Película de prueba [2024].mkv", M + "clip1.mp4", M + "clip2.mp4", M + "clip3.mp4", M + "entrelazado.mkv"])
pump(3)
pass  # el panel de conversión está ahora en la ventana de ajustes
w.grab().save(f"{out}/{lang}-2-queue-settings.png")
w.engine.set_parallel(2)
w.panel.tabs.setCurrentIndex(2); pump(0.3)
w.panel.a_mode.setCurrentIndex(1)
w._start(); pump(5)
w.grab().save(f"{out}/{lang}-3-running.png")
w.panel.tabs.setCurrentIndex(3); pump(0.3)
while w.engine.active: pump(0.5)
pump(1)
w.grab().save(f"{out}/{lang}-4-done.png")
from tuxenc.ui.dialogs import TracksDialog, IntegrationDialog
from tuxenc import integration
j = next(x for x in w.engine.jobs if x.name.startswith("Pel")); j.status = "waiting"
d = TracksDialog(j, w.panel.settings, w); d.show(); pump(0.5); d.grab().save(f"{out}/{lang}-5-tracks.png"); d.close()
d = w.settings_window; d.tabs.setCurrentIndex(4); d.show(); pump(0.5); d.grab().save(f"{out}/{lang}-6-prefs.png"); d.hide()
d = IntegrationDialog(False, w); d.show(); pump(0.5); d.grab().save(f"{out}/{lang}-7-integrate.png"); d.close()
print("jobs:", [(j.name, j.status, j.error[:80]) for j in w.engine.jobs])
w.engine.shutdown()
