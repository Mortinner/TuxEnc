"""Menú «⚙ Ajustes», aviso de buscadores del primer arranque y sección «Buscadores» con claves integradas."""
import os, shutil, sys, time
from pathlib import Path
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from tests.media import FF, M, MEDIA  # noqa: E402,F401  (FFmpeg y vídeos de prueba)
T = Path("/tmp/tx-engines"); shutil.rmtree(T, ignore_errors=True); T.mkdir()
os.environ.update(TUXENC_FFMPEG_DIR=FF,
                  XDG_CONFIG_HOME=str(T/"c"), XDG_CACHE_HOME=str(T/"k"), XDG_STATE_HOME=str(T/"s"),
                  QT_QPA_PLATFORM="offscreen", PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
lang = sys.argv[1] if len(sys.argv) > 1 else "es"
from tuxenc import i18n; i18n.set_language(lang)
from tuxenc.app import _make_app
app = _make_app()
import tuxenc.ui.main_window as mw
import tuxenc.ui.settings_window as sw
from retitler.config import KeyStore
KeyStore.BUILTIN = {"tmdb": "x" * 32, "tvdb": "y" * 36}             # como el AppImage oficial
import tuxenc.ui.dialogs as dl
from tuxenc.config import Config
def pump(sec):
    t = time.time()
    while time.time() - t < sec: app.processEvents(); time.sleep(0.03)

cfg = Config()
w = mw.MainWindow(cfg); w.resize(1180, 560); w.show(); pump(1)
print("aviso visible:", w.bar.isVisible(), "|", w.bar_lbl.text())
# la sección de buscadores
dlg = w.settings_window
dlg.tabs.setCurrentIndex(2); dlg.resize(820, 900); dlg.show(); pump(0.5)
rp = dlg.rename_prefs
print("estados:", {s: rp.key_rows[s][1].text() for s in rp.key_rows})
dlg.grab().save(f"/tmp/shots-merge/{lang}-17-buscadores.png")
# poner clave propia de IMDb (sin red: se guarda sin comprobar) y quitarla
rp.key_rows["omdb"][0].setText("abcd1234"); rp._save_key("omdb"); pump(0.2)
print("IMDb tras poner la mía:", rp.key_rows["omdb"][1].text().split(" · ")[0], "| botón quitar:", rp.key_rows["omdb"][2].isVisible())
rp._clear_key("omdb"); pump(0.2); print("IMDb tras quitarla:", rp.key_rows["omdb"][1].text()[:40])
dlg.tabs.setCurrentIndex(sw.TABS.index("about")); pump(0.2)
sa = dlg.tabs.currentWidget(); sa.verticalScrollBar().setValue(sa.verticalScrollBar().maximum()); pump(0.2)
dlg.grab().save(f"/tmp/shots-merge/{lang}-18-creditos.png")
dlg.hide()
w.close(); cfg2 = Config.load()
print("aviso marcado como visto:", cfg2.engines_notice_shown)
w2 = mw.MainWindow(cfg2); w2.show(); pump(0.5)
print("segundo arranque, aviso:", w2.bar.isVisible())
