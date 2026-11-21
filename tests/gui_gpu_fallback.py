"""La GPU no responde al arrancar (1.3.3): se convierte con la CPU solo en esa sesión.

Antes, el cambio a x265 se guardaba y el preset se quedaba en CPU para siempre, aunque al día
siguiente NVENC funcionara. Ahora el preset no cambia, la barra lo avisa y se recupera solo.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
T = Path(tempfile.mkdtemp(prefix="tx-gpu-"))
os.environ.update(XDG_CONFIG_HOME=str(T / "c"), XDG_CACHE_HOME=str(T / "k"), XDG_STATE_HOME=str(T / "s"),
                  XDG_DATA_HOME=str(T / "d"), QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"),
                  PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
from tests.media import FF  # noqa: E402,F401
from tuxenc import i18n  # noqa: E402
i18n.set_language("es")
from tuxenc.app import _make_app  # noqa: E402
app = _make_app()
from PySide6.QtWidgets import QMessageBox  # noqa: E402
import tuxenc.ui.main_window as mw  # noqa: E402
from tuxenc.catalog import VIDEO_ENCODERS  # noqa: E402
from tuxenc.config import Config  # noqa: E402

boxes = []
QMessageBox.information = staticmethod(lambda *a, **k: boxes.append(a))      # no debe salir ninguna
SOFT = [e.id for e in VIDEO_ENCODERS if not e.hw]
WITH_GPU = SOFT + ["hevc_nvenc", "h264_nvenc"]


def pump(sec=0.3):
    t = time.time()
    while time.time() - t < sec:
        app.processEvents()
        time.sleep(0.02)


def window():
    w = mw.MainWindow(Config.load())
    w._start_hw_detection = lambda: None
    w.show()
    pump()
    return w


cfg = Config()
cfg.engines_notice_shown = True
s = cfg.settings or {}
cfg.save()
w = window()
st = w.panel.settings
st.video_encoder, st.quality, st.speed_preset = "hevc_nvenc", 28, "p5"
w.panel.load(st)
pump()
assert w._settings_to_save()["video_encoder"] == "hevc_nvenc"

# 1) Arranque con la GPU caída: se usa x265 en esta sesión, sin ventana, con aviso en la barra
w._on_hw_ready(SOFT)
pump()
assert w.panel.settings.video_encoder == "libx265", w.panel.settings.video_encoder
assert w._bar_kind == "hw_fallback" and w.bar.isVisible(), (w._bar_kind, w.bar_lbl.text())
print("barra:", w.bar_lbl.text())
assert not boxes, boxes
# Lo que se guarda sigue siendo NVENC (también al cerrar)
assert w._settings_to_save()["video_encoder"] == "hevc_nvenc"
w.close()
pump()
c = Config.load()
assert c.settings["video_encoder"] == "hevc_nvenc" and c.hw_fallback == "hevc_nvenc", (c.settings["video_encoder"], c.hw_fallback)

# 2) Siguiente arranque con la GPU bien: NVENC otra vez y aviso de que se ha recuperado
w = window()
w._on_hw_ready(WITH_GPU)
pump()
assert w.panel.settings.video_encoder == "hevc_nvenc"
assert w._bar_kind == "hw_recovered" and w.bar.isVisible(), w._bar_kind
print("barra:", w.bar_lbl.text())
assert w.cfg.hw_fallback == ""
w.close()
pump()

# 3) Con la GPU caída, si el usuario elige otro codificador a mano, eso sí se guarda
w = window()
w._on_hw_ready(SOFT)
st = w.panel.settings
st.video_encoder = "libx264"
w.panel.load(st)
pump()
w.close()
pump()
c = Config.load()
assert c.settings["video_encoder"] == "libx264" and c.hw_fallback == "", (c.settings["video_encoder"], c.hw_fallback)
for win in (w,):
    win.engine.shutdown()
print("OK")
