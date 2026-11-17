import os, sys, time
sys.path.insert(0, "/home/claude/tuxenc")
os.environ["TUXENC_FFMPEG_DIR"] = "/home/claude/dl/rel-8.1/ffmpeg-n8.1-latest-linux64-gpl-shared-8.1/bin"
os.environ["XDG_CONFIG_HOME"] = "/tmp/tx-gpu-cfg"; os.environ["XDG_CACHE_HOME"] = "/tmp/tx-gpu-cache"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import tuxenc.hw as hw
hw.detect_available = lambda: ["libx264","libx265","libsvtav1","libvpx-vp9","h264_nvenc","hevc_nvenc","av1_nvenc"]
import tuxenc.ui.main_window as mw; mw.detect_available = hw.detect_available
from tuxenc import i18n; i18n.set_language("es")
from tuxenc.app import _make_app
app = _make_app()
from tuxenc.config import Config
from tuxenc.presets import import_handbrake, save_user_presets, load_user_presets
cfg = Config(); cfg.advanced_open = True; cfg.output_mode = "folder"; cfg.output_folder = "/home/morti/DataNas/Descargas"
cfg.settings = {"video_encoder": "libx265", "rate_mode": "cbr", "bitrate": 2000, "bit_depth": 10}
w = mw.MainWindow(cfg); w.resize(956, 1000); w.show()
def pump(sec):
    t = time.time()
    while time.time() - t < sec: app.processEvents(); time.sleep(0.03)
pump(2)
w.grab().save("/tmp/shots/gpu-1-x265-tip.png")
w.panel.codec.showPopup(); pump(0.5)
popup = w.panel.codec.view().window(); popup.grab().save("/tmp/shots/gpu-2-list.png"); w.panel.codec.hidePopup()
w.panel.gpu_btn.click(); pump(0.5)
print("tras pulsar 'Usar GPU':", w.panel.settings.video_encoder, w.panel.settings.rate_mode, w.panel.settings.bitrate)
# importar el preset de Marcos por el camino real de la GUI
from PySide6.QtWidgets import QFileDialog, QMessageBox
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("/tmp/1080_pelis.json", ""))
msgs = []; QMessageBox.information = staticmethod(lambda *a, **k: msgs.append(a[2]))
w._import_handbrake(); pump(0.5)
print("mensaje:", msgs, "| preset activo:", w.preset_combo.currentText(), "|", w.panel.settings.video_encoder, w.panel.settings.rate_mode, w.panel.settings.bitrate)
w.grab().save("/tmp/shots/gpu-3-imported.png")
w.engine.shutdown()
w.panel.tabs.setCurrentIndex(0); pump(0.3)
w.panel.grab().save("/tmp/shots/v4-video.png")
w.panel.speed.showPopup(); pump(0.4); w.panel.speed.view().window().grab().save("/tmp/shots/v4-speed.png"); w.panel.speed.hidePopup()
w.panel.tabs.setCurrentIndex(1); pump(0.3)
w.panel.grab().save("/tmp/shots/v4-picture.png")
