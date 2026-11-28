"""TuxEnc instalado como paquete del sistema (AUR: tuxenc-bin), con TUXENC_PACKAGED.

- No se actualiza solo ni ofrece integrarse: Preferencias lo dice y esconde los botones.
- Si queda la copia AppImage integrada de antes, ofrece quitarla una vez al abrir y desde
  Preferencias; se van el programa, el menú y los iconos, y los ajustes se quedan.
- «--uninstall» remite al gestor de paquetes.
- «Acerca de» dice «Paquete del sistema (pacman)».
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
T = Path(tempfile.mkdtemp(prefix="tx-paquete-"))
os.environ.update(XDG_CONFIG_HOME=str(T / "c"), XDG_CACHE_HOME=str(T / "k"), XDG_STATE_HOME=str(T / "s"),
                  XDG_DATA_HOME=str(T / "d"), QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"),
                  PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring", TUXENC_PACKAGED="pacman")
os.environ.pop("APPIMAGE", None)
from tests.media import FF  # noqa: E402,F401

from tuxenc import i18n, integration, updater  # noqa: E402
i18n.set_language("es")
from tuxenc.app import _make_app  # noqa: E402
from tuxenc.i18n import tr  # noqa: E402
app = _make_app()
from PySide6.QtWidgets import QMessageBox  # noqa: E402
import tuxenc.app as txapp  # noqa: E402
import tuxenc.ui.main_window as mw  # noqa: E402
import tuxenc.ui.settings_window as sw  # noqa: E402
from tuxenc.config import Config  # noqa: E402


def pump(sec):
    t = time.time()
    while time.time() - t < sec:
        app.processEvents()
        time.sleep(0.03)


assert integration.packaged() == "pacman"
assert not updater.can_self_update()

# Copia AppImage integrada de antes (como la deja integrate())
integration.DATA_DIR.mkdir(parents=True)
integration.INSTALLED_APPIMAGE.write_bytes(b"\x7fELF viejo")
desk = integration.APPS_DIR / "tuxenc.desktop"
desk.parent.mkdir(parents=True)
desk.write_text(f"[Desktop Entry]\nExec={integration.INSTALLED_APPIMAGE} %F\n")
icon = integration.ICONS_DIR / "48x48" / "apps" / "tuxenc.png"
icon.parent.mkdir(parents=True)
icon.write_bytes(b"png")
integration.MANIFEST.write_text(json.dumps({"files": [str(integration.INSTALLED_APPIMAGE), str(desk), str(icon)],
                                            "dirs": [], "version": "1.3.5"}))
cfg = Config()
cfg.engines_notice_shown = True
cfg.save()
keep = Path(os.environ["XDG_CONFIG_HOME"]) / "tuxenc"
assert integration.is_integrated() and keep.exists()

# Preferencias: lo actualiza el gestor y ofrece quitar la copia AppImage
w = mw.MainWindow(cfg)
w.show()
pump(0.5)
dlg = sw.SettingsWindow(w)
dlg._refresh_integration()
dlg._refresh_updates()
assert "paquete del sistema (pacman)" in dlg.int_label.text(), dlg.int_label.text()
assert "copia AppImage" in dlg.int_label.text()
assert not dlg.int_btn.isHidden() and dlg.int_btn.text() == tr("remove_appimage_copy")
assert dlg.shortcut_btn.isHidden()
assert "paru -Syu" in dlg.upd_label.text(), dlg.upd_label.text()
assert all(b.isHidden() for b in (dlg.upd_auto, dlg.upd_check_btn, dlg.upd_view_btn, dlg.upd_back_btn))
rows = dict(dlg._system_rows({"kind": "local"}))
assert rows[tr("sys_runtime")] == "Paquete del sistema (pacman)", rows
print("preferencias: OK")

# Quitar la copia: se van programa, menú e icono; los ajustes se quedan
answers = []


def fake_exec(box):
    answers.append(box.text())
    for b in box.buttons():
        if b.text() == tr("remove_appimage_copy"):
            box._clicked = b
    return 0


QMessageBox.exec = fake_exec
QMessageBox.clickedButton = lambda box: getattr(box, "_clicked", None)
QMessageBox.information = staticmethod(lambda *a, **k: None)
dlg._integrate()
assert answers and "copia AppImage" in answers[0]
assert not integration.INSTALLED_APPIMAGE.exists() and not desk.exists() and not icon.exists()
assert not integration.MANIFEST.exists() and keep.exists() and not integration.is_integrated()
assert dlg.int_btn.isHidden() and "copia AppImage" not in dlg.int_label.text()
print("quitar la copia AppImage: OK")

# --uninstall remite al gestor de paquetes y no borra nada
answers.clear()
assert txapp.run_uninstall(app) == 0
assert answers and "pacman -R tuxenc-bin" in answers[0] and keep.exists()
print("desinstalar: OK")
w.close()
print("TODO OK")
