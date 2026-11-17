"""Punto de entrada de TuxEnc."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from . import APP_ID, APP_NAME, VERSION, i18n, integration
from .config import Config
from .i18n import tr
from .paths import ASSETS_DIR, appimage_path, clean_env, ensure_dirs
from .ui import theme

SERVER_NAME = f"{APP_ID}-{os.getuid()}"
JUST_INSTALLED = "TUXENC_JUST_INSTALLED"     # «first» o la versión anterior: el nuevo proceso lo avisa
QUIT_CMD = "quit_for_update"


def _make_app() -> QApplication:
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(VERSION)
    app.setOrganizationName(APP_ID)
    app.setDesktopFileName(APP_ID)   # en Wayland enlaza la ventana con tuxenc.desktop (icono)
    app.setWindowIcon(QIcon(str(ASSETS_DIR / "tuxenc-256.png")))
    theme.apply(app)
    if i18n.current() == "es":
        # Textos propios de Qt (diálogos de archivo, menús contextuales…)
        from PySide6.QtCore import QLibraryInfo, QTranslator
        qt_tr = QTranslator(app)
        if qt_tr.load("qtbase_es", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
            app.installTranslator(qt_tr)
    return app


def run_uninstall(app: QApplication) -> int:
    box = QMessageBox(QMessageBox.Question, tr("uninstall_title"), tr("uninstall_q"))
    box.setIconPixmap(QIcon(str(ASSETS_DIR / "tuxenc-256.png")).pixmap(72, 72))
    yes = box.addButton(tr("uninstall_yes"), QMessageBox.DestructiveRole)
    box.addButton(tr("cancel"), QMessageBox.RejectRole)
    box.exec()
    if box.clickedButton() is not yes:
        return 0
    integration.uninstall()
    QMessageBox.information(None, tr("uninstall_title"), tr("uninstall_done"))
    return 0


def relaunch(exe: str | None, files: list[str], extra_env: dict | None = None) -> None:
    """Abre TuxEnc de nuevo (tras actualizar o cambiar de idioma) como un proceso independiente."""
    env = clean_env()
    env.pop(JUST_INSTALLED, None)
    env.update(extra_env or {})
    for var in ("APPDIR", "APPIMAGE", "ARGV0", "OWD"):    # que el nuevo AppImage ponga los suyos
        env.pop(var, None)
    if exe:
        cmd = [str(exe)]
    elif appimage_path():
        cmd = [str(appimage_path())]
    else:                                                # desarrollo: python run.py
        cmd = [sys.executable, os.path.abspath(sys.argv[0])]
    subprocess.Popen(cmd + list(files), env=env, start_new_session=True, cwd=os.path.expanduser("~"),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _running() -> bool:
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    ok = sock.waitForConnected(300)
    sock.abort()
    return ok


def _ask_running_to_quit() -> tuple[str, list[str]]:
    """Pide al TuxEnc abierto que se cierre para actualizar.

    Devuelve ("closed", archivos en espera), ("busy", []) si el usuario no quiso cerrarlo
    (conversiones en marcha) u ("old", []) si es una versión que no entiende la petición.
    """
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(1000):
        return "closed", []
    sock.write((json.dumps({"cmd": QUIT_CMD}) + "\n").encode("utf-8"))
    sock.flush()
    buf, acked, result = b"", False, None
    deadline_ack = time.monotonic() + 3
    deadline = time.monotonic() + 30 * 60       # el usuario puede tardar en contestar «¿cerrar?»
    while result is None:
        limit = deadline_ack if not acked else deadline
        if time.monotonic() > limit:
            break
        if sock.state() == QLocalSocket.UnconnectedState and not sock.bytesAvailable():
            break
        if sock.waitForReadyRead(200):
            buf += bytes(sock.readAll())
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            try:
                msg = json.loads(line.decode("utf-8") or "{}")
            except ValueError:
                continue
            if msg.get("ack"):
                acked = True
            elif "ok" in msg:
                result = msg
    sock.abort()
    if not acked:
        return "old", []
    if not result or not result.get("ok"):
        return "busy", []
    t = time.monotonic() + 15                    # esperar a que el proceso viejo termine del todo
    while _running() and time.monotonic() < t:
        time.sleep(0.2)
    return "closed", list(result.get("files") or [])


def _install_flow(cfg: Config, files: list[str]) -> bool:
    """Si se ha abierto un AppImage descargado (no la copia instalada), pregunta antes de abrir
    nada si integrarlo / actualizar. Devuelve True si este proceso ya ha terminado su trabajo."""
    from .ui.dialogs import IntegrationDialog
    if not integration.running_from_appimage() or integration.running_installed_copy():
        return False
    update = integration.is_integrated()
    old = integration.installed_version() if update else ""
    if update and old == VERSION:
        return False                              # la misma versión: abrir sin preguntar
    if not update and cfg.integration_prompted:
        return False
    running = _running()
    dlg = IntegrationDialog(update=update, old=old, running=running)
    if not dlg.exec():
        if not update:
            cfg.integration_prompted = True
            cfg.save()
        return False                              # «Ahora no»: se sigue como siempre
    pending: list[str] = []
    if running:
        state, pending = _ask_running_to_quit()
        if state == "old":
            QMessageBox.information(None, APP_NAME, tr("update_close_old"))
            return True
        if state == "busy":
            QMessageBox.information(None, APP_NAME, tr("update_cancelled_busy"))
            return True
    try:
        integration.integrate(desktop_shortcut=dlg.shortcut.isChecked() or update)
    except Exception as exc:  # noqa: BLE001
        QMessageBox.warning(None, APP_NAME, tr("integrate_fail", err=str(exc)))
        files.extend(f for f in pending if f not in files)
        return False                              # se abre esta copia, con lo que hubiera en cola
    fresh = Config.load()                         # el TuxEnc viejo pudo guardar sus ajustes al cerrarse
    fresh.integration_prompted = True
    fresh.save()
    allf = list(dict.fromkeys(pending + files))
    relaunch(str(integration.INSTALLED_APPIMAGE), allf, {JUST_INSTALLED: (old or "?") if update else "first"})
    return True


def _send_to_running(files: list[str]) -> bool:
    """Si TuxEnc ya está abierto, le pasa los archivos y devuelve True."""
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(300):
        return False
    sock.write(json.dumps({"files": files}).encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


def main() -> int:
    args = sys.argv[1:]
    cfg = Config.load()
    i18n.set_language(cfg.ui_lang)
    ensure_dirs()

    if "--uninstall" in args:
        app = _make_app()
        return run_uninstall(app)

    files = [os.path.abspath(a) for a in args if not a.startswith("-") and os.path.exists(a)]
    app = _make_app()
    if _install_flow(cfg, files):
        return 0
    if _send_to_running(files):
        return 0

    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    server.listen(SERVER_NAME)

    from .ui.main_window import MainWindow
    win = MainWindow(cfg)

    def on_conn():
        sock = server.nextPendingConnection()
        if sock is None:
            return

        def read():
            raw = bytes(sock.readAll()).decode("utf-8", "replace").strip()
            try:
                data = json.loads(raw.splitlines()[0] if raw else "{}")
            except ValueError:
                data = {}
            if data.get("cmd") == QUIT_CMD:
                sock.write(b'{"ack": true}\n')
                sock.flush()
                waiting = [j.input for j in win.engine.jobs if j.status == "waiting"]
                win.showNormal()
                win.raise_()
                closed = win.close()           # si hay conversiones, pregunta como siempre
                sock.write((json.dumps({"ok": closed, "files": waiting if closed else []}) + "\n").encode())
                sock.flush()
                sock.waitForBytesWritten(2000)
                return
            if data.get("files"):
                win.add_paths(data["files"])
            win.showNormal()
            win.raise_()
            win.activateWindow()

        sock.readyRead.connect(read)
        sock.disconnected.connect(sock.deleteLater)

    server.newConnection.connect(on_conn)
    win.show()
    if files:
        QTimer.singleShot(200, lambda: win.add_paths(files))
    just = os.environ.pop(JUST_INSTALLED, None)
    if just:
        QTimer.singleShot(400, lambda: win.show_just_installed(just))

    # Ctrl+C en una terminal cierra bien (útil al desarrollar)
    signal.signal(signal.SIGINT, lambda *_: win.close())
    keepalive = QTimer()
    keepalive.timeout.connect(lambda: None)
    keepalive.start(500)
    rc = app.exec()
    if win.restart_request is not None:
        server.close()                  # si no, el nuevo le pasaría los archivos a este y se cerraría
        QLocalServer.removeServer(SERVER_NAME)
        relaunch(*win.restart_request)
    return rc


if __name__ == "__main__":
    sys.exit(main())
