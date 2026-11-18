"""☰ + ventana única de ajustes (6 pestañas), interruptores de modo y «Acerca de»."""
import os, shutil, sys, time, faulthandler
faulthandler.dump_traceback_later(40, exit=True)
from pathlib import Path
sys.path.insert(0, "/home/claude/tuxenc")
T = Path("/tmp/tx-settings"); shutil.rmtree(T, ignore_errors=True); T.mkdir()
os.environ.update(TUXENC_FFMPEG_DIR="/home/claude/dl/rel-8.1/ffmpeg-n8.1-latest-linux64-gpl-shared-8.1/bin",
                  XDG_CONFIG_HOME=str(T/"c"), XDG_CACHE_HOME=str(T/"k"), XDG_STATE_HOME=str(T/"s"),
                  QT_QPA_PLATFORM="offscreen", PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
lang = sys.argv[1] if len(sys.argv) > 1 else "es"
from tuxenc import i18n; i18n.set_language(lang)
from tuxenc.app import _make_app
app = _make_app()
import tuxenc.ui.main_window as mw
from retitler.config import KeyStore
KeyStore.BUILTIN = {"tmdb": "x" * 32, "tvdb": "y" * 36}
import tuxenc.ui.settings_window as sw
from tuxenc.config import Config
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QMessageBox, QInputDialog
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: None)
def pump(sec):
    t = time.time()
    while time.time() - t < sec: app.processEvents(); time.sleep(0.03)
O = Path("/tmp/shots-merge"); O.mkdir(exist_ok=True)

cfg = Config(); cfg.engines_notice_shown = True; cfg.rename_on = True
w = mw.MainWindow(cfg); w.resize(1180, 520); w.show(); pump(1)
w.engine.set_parallel(1)
w.add_paths(["/home/claude/testmedia/clip1.mp4"]); pump(2)
# cabecera + menú ☰ desplegado
m = w.menu_btn.menu(); m.popup(w.menu_btn.mapToGlobal(w.menu_btn.rect().bottomLeft())); pump(0.4)
img = w.grab(); p = QPainter(img); mp = m.grab(); br = w.menu_btn.mapTo(w, w.menu_btn.rect().bottomRight())
p.drawPixmap(br.x() - mp.width(), br.y(), mp); p.end(); img.save(str(O / f"{lang}-19-menu.png")); m.hide()
print("menú ☰:", [a.text() for a in m.actions() if a.text()])
print("interruptores:", w.conv_btn.isChecked(), w.ren_btn.isChecked(), "| tipo:", type(w.conv_btn).__name__)

# los dos modos apagados: los ajustes se abren igual (todas las pestañas)
w.conv_btn.setChecked(False); pump(0.2); w.ren_btn.setChecked(False); pump(0.3)
print("modos apagados → conv:", cfg.convert_on, "ren:", cfg.rename_on)
w.grab().save(str(O / f"{lang}-20-interruptores-off.png"))
w.conv_btn.setChecked(True); w.ren_btn.setChecked(True); pump(0.3)

shots = {}
def fake_exec(self):
    self.show(); pump(0.4)
    name = sw.TABS[self.tabs.currentIndex()]
    self.grab().save(str(O / f"{lang}-21-ajustes-{name}.png")); shots[name] = True
    if name == "conversion":                     # un cambio aquí llega al resumen de la ventana principal
        before = w.summary.text()
        self.main.panel.load(self.main.panel.settings.copy().__class__(**{**self.main.panel.settings.to_dict(), "quality": 30}))
        self.main.panel.changed.emit(); pump(0.2)
        print("conversión: resumen cambia:", before != w.summary.text(), "| modificado:", "✎ (" in w.summary.text())
    if name == "presets":
        QInputDialog.getText = staticmethod(lambda *a, **k: ("Mi preset", True))
        self._save_preset(); pump(0.2)
        names = [self.preset_list.item(i).text() for i in range(self.preset_list.count())]
        print("presets tras guardar:", [n for n in names if "Mi preset" in n])
        mine = next(i for i in range(self.preset_list.count()) if "Mi preset" in self.preset_list.item(i).text())
        first = 0
        self.preset_list.setCurrentRow(first); self._use_preset(); pump(0.2)
        print("usar el primero → en uso:", w.current_key, "| combo:", w.preset_combo.currentText())
        self.preset_list.setCurrentRow(mine); print("borrar habilitado en el mío:", self.p_del.isEnabled())
        self._delete_preset(); pump(0.2)
        print("tras borrar, queda «Mi preset»:", any("Mi preset" in self.preset_list.item(i).text() for i in range(self.preset_list.count())))
        self.preset_list.setCurrentRow(0); print("borrar habilitado en uno incorporado:", self.p_del.isEnabled())
    self.hide()
    return 1
sw.SettingsWindow.exec = fake_exec
for tab in sw.TABS:
    w.open_settings(tab)
print("pestañas abiertas:", list(shots))
about = w.settings_window
txt = " ".join(l.text() for l in about.findChildren(sw.QLabel))
print("acerca de: autor:", "Mortinner" in txt, "| contacto:", "mortinner@gmail.com" in txt, "| Claude:", "Claude" in txt)
# la barra de avisos abre «Buscadores»
w._bar_kind = "engines"; opened = []
w.open_settings = lambda t="conversion": opened.append(t)
w._on_bar_action(); print("aviso → pestaña:", opened)
w.engine.shutdown(); w.rename.shutdown()
