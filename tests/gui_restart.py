"""Reinicio tras actualizar / integrar y tras cambiar de idioma; relanzado real del proceso."""
import json, os, shutil, stat, sys, time
from pathlib import Path
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from tests.media import FF, M, MEDIA  # noqa: E402,F401  (FFmpeg y vídeos de prueba)
T = Path("/tmp/tx-restart"); shutil.rmtree(T, ignore_errors=True); T.mkdir()
(T / "dl").mkdir(); new_ai = T / "dl" / "TuxEnc-nuevo.AppImage"; new_ai.write_text("x")
os.environ.update(TUXENC_FFMPEG_DIR=FF,
                  XDG_CONFIG_HOME=str(T/"c"), XDG_CACHE_HOME=str(T/"k"), XDG_STATE_HOME=str(T/"s"),
                  XDG_DATA_HOME=str(T/"d"), HOME=str(T), QT_QPA_PLATFORM="offscreen", APPIMAGE=str(new_ai),
                  TUXENC_ORIG_LD_LIBRARY_PATH="/orig/lib", LD_LIBRARY_PATH="/appimage/lib:/orig/lib")
from tuxenc import i18n; i18n.set_language("es")
from tuxenc.app import _make_app, relaunch
app = _make_app(); app.setQuitOnLastWindowClosed(False)
import tuxenc.ui.main_window as mw
from tuxenc import integration, VERSION
from tuxenc.config import Config
def pump(sec):
    t = time.time()
    while time.time() - t < sec: app.processEvents(); time.sleep(0.03)
def wait(c, to=30):
    t = time.time()
    while not c() and time.time() - t < to: pump(0.1)
    return c()

# --- 1) actualización: ya había una versión integrada (dev.12)
integration.DATA_DIR.mkdir(parents=True, exist_ok=True); integration.APPS_DIR.mkdir(parents=True, exist_ok=True)
integration.INSTALLED_APPIMAGE.write_text("viejo")
(integration.APPS_DIR / "tuxenc.desktop").write_text("[Desktop Entry]")
integration.MANIFEST.write_text(json.dumps({"files": [], "dirs": [], "version": "0.0.1-dev.12"}))
shown = []
mw.MainWindow._restart_box = lambda self, text, lang=None, ask=False: (shown.append((text, lang, ask)), True)[1]
class FakeIntegDlg:
    def __init__(self, update=False, parent=None): self.update = update
    def exec(self): return 1
    class shortcut:
        @staticmethod
        def isChecked(): return False
mw.IntegrationDialog = FakeIntegDlg
cfg = Config()
w = mw.MainWindow(cfg); w.show(); pump(0.5)
w.add_paths([M + "clip1.mp4"]); assert wait(lambda: len(w.engine.jobs) == 1 and not w.pending_probes)
old = integration.installed_version(); integration.integrate(False); w._after_integrate(True, old); pump(0.3)   # como desde Preferencias
print("1) aviso:", shown[-1][0].replace("<br>", " | "))
print("   copia instalada actualizada:", integration.INSTALLED_APPIMAGE.read_text() == "x",
      "| versión en el manifiesto:", integration.installed_version() == VERSION)
print("   reinicio pedido:", w.restart_request, "| ventana cerrada:", not w.isVisible())

# --- 2) idioma: de español a inglés
import tuxenc.ui.settings_window as swm
class FakePrefs:
    lang = "en"
swm.SettingsWindow.open_tab = lambda self, tab="conversion": None
swm.SettingsWindow.chosen_lang = lambda self: FakePrefs.lang
w2 = mw.MainWindow(Config()); w2.show(); pump(0.3)
w2.add_paths([M + "clip2.mp4"]); assert wait(lambda: len(w2.engine.jobs) == 1 and not w2.pending_probes)
w2._open_prefs(); pump(0.3)
print("2) pregunta:", shown[-1][0].replace("<br>", " | "), "| idioma del aviso:", shown[-1][1], "| con «Más tarde»:", shown[-1][2])
print("   reinicio pedido:", w2.restart_request)
# mismo idioma: no pregunta
FakePrefs.lang = "auto"; i18n.set_language("es")
w3 = mw.MainWindow(Config()); w3.show(); n = len(shown); w3._open_prefs(); pump(0.2)
print("   sin cambiar de idioma no pregunta:", len(shown) == n and w3.restart_request is None)

# --- 3) relanzado real: un «AppImage» falso que apunta lo que recibe
fake = T / "fake-tuxenc"
out = T / "lanzado.txt"
fake.write_text(f'#!/bin/sh\necho "args=$*" > {out}\necho "APPIMAGE=${{APPIMAGE-}}" >> {out}\necho "LD=$LD_LIBRARY_PATH" >> {out}\necho "PWD=$(pwd)" >> {out}\n')
fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
relaunch(str(fake), ["/v/a b.mkv", "/v/c.mp4"])
assert wait(lambda: out.exists() and out.read_text().count("\n") >= 4, 10)
print("3) proceso nuevo:", out.read_text().strip().replace("\n", " | "))
for x in (w, w2, w3):
    x.engine.shutdown(); x.rename.shutdown()
