"""Actualizador en la interfaz, de principio a fin, contra un GitHub de mentira (servidor local).

TuxEnc «integrado» en una carpeta temporal → aviso de versión nueva → novedades → descarga con
progreso → SHA-256 → instalado (el anterior se guarda) → reiniciar → la versión nueva rehace la
integración. También: saltar una versión, suma que no coincide (no se instala nada) y volver atrás.

Capturas en /tmp/tx-update-shots (para revisarlas a mano).
"""
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
T = Path(tempfile.mkdtemp(prefix="tx-update-"))
os.environ.update(XDG_CONFIG_HOME=str(T / "c"), XDG_CACHE_HOME=str(T / "k"), XDG_STATE_HOME=str(T / "s"),
                  XDG_DATA_HOME=str(T / "d"), QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"),
                  PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
from tests.media import FF  # noqa: E402,F401
from tests.test_updater import FAKE_APPIMAGE, Server, make_zip  # noqa: E402

from tuxenc import VERSION, i18n, integration, updater  # noqa: E402
i18n.set_language(sys.argv[1] if len(sys.argv) > 1 else "es")
from tuxenc.app import _make_app  # noqa: E402
from tuxenc.i18n import tr  # noqa: E402
app = _make_app()
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton  # noqa: E402
import tuxenc.ui.main_window as mw  # noqa: E402
from tuxenc.config import Config  # noqa: E402

SHOTS = Path("/tmp/tx-update-shots")
shutil.rmtree(SHOTS, ignore_errors=True)
SHOTS.mkdir()
a, b, c = (int(x) for x in VERSION.split("-")[0].split("."))
NEW = f"{a}.{b}.{c + 1}"
OLD_BYTES = FAKE_APPIMAGE + b"VERSION-ACTUAL"
NEW_BYTES = FAKE_APPIMAGE + b"VERSION-NUEVA" + b"\0" * 2_500_000

# --- TuxEnc «integrado»: este proceso hace de la copia instalada en ~/.local/share/tuxenc
integration.DATA_DIR.mkdir(parents=True)
integration.INSTALLED_APPIMAGE.write_bytes(OLD_BYTES)
integration.MANIFEST.write_text(json.dumps({"files": [], "dirs": [], "version": VERSION}))
os.environ["APPIMAGE"] = str(integration.INSTALLED_APPIMAGE)
assert updater.can_self_update()

srv = Server()
srv.slow = 0.02
os.environ[updater.API_OVERRIDE_ENV] = srv.base + "/api/releases"
notes = ("\n### Añadido\n- **Actualizaciones desde la propia app**, comprobadas con SHA-256.\n"
         "- Volver a la versión anterior desde Preferencias.\n\n### English\n- Added: in-app updates.\n\n---\n"
         "**Descarga:** el archivo adjunto. Comprueba la descarga con `sha256sum -c SHA256SUMS`.\n")
srv.publish(VERSION, notes="versión actual")
srv.publish(NEW, zip_bytes=make_zip(NEW, payload=NEW_BYTES), notes=notes)


def pump(sec):
    t = time.time()
    while time.time() - t < sec:
        app.processEvents()
        time.sleep(0.02)


def wait(cond, to=30, what=""):
    t = time.time()
    while not cond() and time.time() - t < to:
        pump(0.05)
    assert cond(), "tiempo agotado: " + what


def shot(widget, name):
    pump(0.3)
    widget.grab().save(str(SHOTS / f"{name}.png"))


# Diálogos modales: cada paso espera su diálogo y hace algo con él
steps: list = []
seen: list[str] = []


def on_modal():
    m = QApplication.activeModalWidget()
    if m is None or not steps:
        return
    pred, act = steps[0]
    if pred(m):
        steps.pop(0)
        seen.append(type(m).__name__)
        QTimer.singleShot(0, lambda: act(m))   # fuera de este temporizador: puede abrir otro diálogo


poller = QTimer()
poller.timeout.connect(on_modal)
poller.start(150)


def click(m, text):
    btns = [b for b in m.findChildren(QPushButton) if b.text().replace("&", "") == text]
    assert btns, f"no hay botón «{text}» en {type(m).__name__}: {[b.text() for b in m.findChildren(QPushButton)]}"
    btns[0].click()


def is_cls(name):
    return lambda m: type(m).__name__ == name


def msgbox_with(text):
    return lambda m: type(m).__name__ == "QMessageBox" and text in m.text()


cfg = Config()
cfg.engines_notice_shown = True
w = mw.MainWindow(cfg)
w.resize(1100, 700)
w.show()
pump(0.5)
if w.bar.isVisible() and not w._bar_kind.startswith("update"):
    w._dismiss_bar()

# 1) Comprobación al arrancar → aviso en la barra
w.updater.auto_check()
wait(lambda: w._bar_kind == "update" and w.bar.isVisible(), what="aviso de versión nueva")
assert NEW in w.bar_lbl.text(), w.bar_lbl.text()
assert cfg.update_last_check > 0
shot(w, "1-aviso")
# Otra comprobación automática el mismo día no hace nada
w.updater.info = None
w.updater.auto_check()
assert not w.updater.checking
w.updater.check(manual=True)
wait(lambda: w.updater.info is not None, what="comprobación manual")


# 2) «Ver novedades» → diálogo con las notas → Actualizar → descarga → instalado → «Más tarde»
def look_notes(m):
    chk = m.findChildren(QCheckBox)[0]
    chk.setChecked(True)
    pump(0.3)
    html = m.notes.toPlainText()
    assert "Actualizaciones desde la propia app" in html and "Descarga" not in html, html
    shot(m, "2-novedades")
    click(m, tr("upd_install"))


progress_seen = []


def look_download(m):
    wait(lambda: m.bar.maximum() == 1000 and 0 < m.bar.value() < 1000, 20, "barra de progreso")
    progress_seen.append(m.bar.value())
    shot(m, "3-descargando")


def installed_later(m):
    shot(m, "4-instalada")
    click(m, tr("restart_later"))


steps += [(is_cls("UpdateDialog"), look_notes), (is_cls("DownloadDialog"), look_download),
          (msgbox_with(NEW), installed_later)]
w._on_bar_action()
wait(lambda: not steps, what="flujo de actualización")
assert progress_seen, "no se vio el avance de la descarga"
assert integration.INSTALLED_APPIMAGE.read_bytes() == NEW_BYTES
assert updater.PREVIOUS.read_bytes() == OLD_BYTES and updater.previous_version() == VERSION
assert not updater.STAGING.exists()
assert w._bar_kind == "update_ready" and w.bar.isVisible()
shot(w, "5-lista-para-reiniciar")


# 3) Preferencias: estado, sin «volver» mientras no se haya reiniciado
def look_prefs(m):
    assert NEW in m.upd_label.text(), m.upd_label.text()
    assert not m.upd_back_btn.isVisible()
    m.resize(900, 820)
    shot(m, "6-preferencias")
    click(m, tr("close"))


steps.append((is_cls("SettingsWindow"), look_prefs))
w.open_settings("prefs")
assert not steps

# 4) «Reiniciar» en la barra → pide reiniciar desde la copia instalada
w._on_bar_action()
pump(0.5)
assert w.restart_request is not None and w.restart_request[0] == str(integration.INSTALLED_APPIMAGE)
assert not w.isVisible()

# 5) La versión nueva al abrirse por primera vez rehace la integración (aquí: este mismo código)
integration.MANIFEST.write_text(json.dumps({"files": [], "dirs": [], "version": "1.0.0"}))
assert integration.finish_self_update() == "1.0.0"
assert integration.installed_version() == VERSION
assert (integration.APPS_DIR / "tuxenc.desktop").exists()
assert integration.finish_self_update() == ""          # la segunda vez ya no hay nada que hacer

# 6) Volver atrás desde Preferencias (ya reiniciado en la nueva: el que corre es VERSION y el
#    anterior guardado es otra versión)
json.dump({"version": "1.0.0"}, open(updater.PREVIOUS_INFO, "w"))
w2 = mw.MainWindow(Config.load())
w2.show()
pump(0.5)


def rollback(m):
    assert m.upd_back_btn.isVisible() and "1.0.0" in m.upd_back_btn.text()
    m.upd_back_btn.click()


def confirm_rollback(m):
    shot(m, "7-volver-atras")
    click(m, tr("upd_rollback", v="1.0.0"))


steps += [(is_cls("SettingsWindow"), rollback), (msgbox_with("1.0.0"), confirm_rollback)]
w2.open_settings("prefs")
wait(lambda: not steps, what="volver atrás")
pump(0.5)
assert integration.INSTALLED_APPIMAGE.read_bytes() == OLD_BYTES
assert updater.PREVIOUS.read_bytes() == NEW_BYTES and updater.previous_version() == VERSION
assert w2.restart_request is not None

# 7) Saltar una versión: no vuelve a avisar de esa
w3 = mw.MainWindow(Config.load())
w3.show()
w3.updater.check(manual=True)
wait(lambda: w3._bar_kind == "update", what="aviso (saltar)")
steps.append((is_cls("UpdateDialog"), lambda m: click(m, tr("upd_skip"))))
w3._on_bar_action()
wait(lambda: not steps, what="saltar")
pump(0.3)
def update_bar(win):
    return win.bar.isVisible() and win._bar_kind.startswith("update")


assert w3.cfg.update_skip == NEW and not update_bar(w3)
w3.updater.check(manual=True)
wait(lambda: not w3.updater.checking, what="comprobar tras saltar")
pump(0.3)
assert not update_bar(w3)

# 8) Suma SHA-256 que no coincide: error claro y no se toca nada
srv.releases.clear()
NEWER = f"{a}.{b}.{c + 2}"
srv.publish(NEWER, sums="0" * 64 + f"  TuxEnc-{NEWER}-linux-x86_64.zip\n", notes=notes)
before = integration.INSTALLED_APPIMAGE.read_bytes()
w3.updater.check(manual=True)
wait(lambda: update_bar(w3), what="aviso (suma mala)")


def bad_sum(m):
    shot(m, "8-suma-incorrecta")
    m.buttons()[0].click()


steps += [(is_cls("UpdateDialog"), lambda m: click(m, tr("upd_install"))),
          (msgbox_with(tr("upd_err_checksum")[:40]), bad_sum)]
w3._on_bar_action()
wait(lambda: not steps, what="error de suma")
assert integration.INSTALLED_APPIMAGE.read_bytes() == before
assert not updater.STAGING.exists()
log = (updater.LOG_FILE).read_text(encoding="utf-8")
assert "SHA-256 NO coincide" in log and "instalada la" in log and "vuelta a la 1.0.0" in log

for win in (w, w2, w3):
    win.engine.shutdown()
    win.rename.shutdown()
srv.close()
print("diálogos:", seen)
print("OK")
