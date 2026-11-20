"""Capturas del README: docs/capturas/<idioma>-*.png.

Uso:  QT_QPA_PLATFORM=offscreen python tests/capturas_readme.py es
      QT_QPA_PLATFORM=offscreen python tests/capturas_readme.py en

Usa los vídeos de prueba generados (tests/media.py) y el buscador simulado, sin internet.
"""
import os
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tests.media import FF, MEDIA  # noqa: E402

T = Path("/tmp/tx-capturas")
shutil.rmtree(T, ignore_errors=True)
T.mkdir()
os.environ.update(TUXENC_FFMPEG_DIR=FF, XDG_CONFIG_HOME=str(T / "c"), XDG_CACHE_HOME=str(T / "k"),
                  XDG_STATE_HOME=str(T / "s"), XDG_DATA_HOME=str(T / "d"),
                  QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"),
                  PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
lang = sys.argv[1] if len(sys.argv) > 1 else "es"

from tuxenc import i18n  # noqa: E402
i18n.set_language(lang)
from tuxenc.app import _make_app  # noqa: E402
app = _make_app()
import tuxenc.ui.main_window as mw  # noqa: E402
import tuxenc.ui.rename_ctrl as rc  # noqa: E402
import tuxenc.ui.settings_window as sw  # noqa: E402
from tuxenc.config import Config  # noqa: E402
from tests.fake_search import FakeSearcher  # noqa: E402

OUT = REPO / "docs" / "capturas"
OUT.mkdir(parents=True, exist_ok=True)


def pump(sec):
    t = time.time()
    while time.time() - t < sec:
        app.processEvents()
        time.sleep(0.02)


def wait(cond, to=60):
    t = time.time()
    while not cond() and time.time() - t < to:
        pump(0.05)
    assert cond(), "tiempo agotado"


def save(widget, name):
    pump(0.4)
    widget.grab().save(str(OUT / f"{lang}-{name}.png"))
    print("captura:", OUT / f"{lang}-{name}.png")


# Una carpeta de descargas con tres capítulos de una serie y una película
down = T / "Descargas"
down.mkdir()
for e, src in ((1, "Arrow.S01E02.1080p.WEB-DL.mkv"), (2, "Arrow.S01E02.1080p.WEB-DL.mkv"),
               (3, "Arrow.S01E03.1080p.WEB-DL.mkv")):
    shutil.copy(MEDIA / "lib" / src, down / f"Arrow.S01E{e:02}.1080p.WEB-DL.mkv")
shutil.copy(MEDIA / "lib" / "Babel.2006.BluRay.mkv", down / "Babel.2006.BluRay.mkv")

cfg = Config()
cfg.engines_notice_shown = True
cfg.convert_on, cfg.rename_on = True, True
cfg.output_mode = "library"
cfg.series_root, cfg.movie_root = str(T / "Biblioteca" / "Series"), str(T / "Biblioteca" / "Peliculas")
cfg.parallel = 2
w = mw.MainWindow(cfg)
w.resize(1180, 760)
w.show()
w.rename.lib.searcher = FakeSearcher()
pump(1)
if w.bar.isVisible():          # aviso de claves: sale porque las pruebas no llevan claves integradas
    w._dismiss_bar()

# 1) Cola preparada: identificación y vista previa del nombre nuevo
w.add_paths([str(down)])
wait(lambda: len(w.engine.jobs) == 4 and not w.pending_probes
     and all(j.ident == "ok" for j in w.engine.jobs))
save(w, "cola")


# 2) «Identificar…» con la serie, sus temporadas y capítulos
def fake_match_exec(self):
    self.show()
    wait(lambda: self.eps.count() > 1 and self.eps.item(0).data(0x0100) is not None)
    self.eps.item(1).setSelected(True)
    save(self, "identificar")
    return 0


rc.MatchDialog.exec = fake_match_exec
w.rename.open_match(next(j for j in w.engine.jobs if "E02" in j.name))
pump(0.5)

# 3) Convirtiendo dos a la vez, cada uno a su carpeta de la biblioteca
w.start_btn.click()
wait(lambda: sum(1 for j in w.engine.jobs if j.status == "running" and j.progress > 0.15) >= 2, 120)
save(w, "convirtiendo")
w.engine.stop()
pump(1)


# 4) Ajustes: pestaña Conversión
def fake_settings_exec(self):
    self.resize(900, 820)
    self.show()
    save(self, "ajustes")
    self.hide()
    return 0


sw.SettingsWindow.exec = fake_settings_exec
w.open_settings("conversion")

w.engine.shutdown()
w.rename.shutdown()
