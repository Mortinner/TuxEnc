"""1.3.6: el título del archivo es el de otro capítulo → dudoso, con el capítulo propuesto.

En la cola se avisa («El título del archivo es el de S01E02…») y, al pulsar «Identificar…»,
la ventana ya trae marcado ese capítulo.
"""
import os, shutil, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.media import FF, M  # noqa: E402
T = Path("/tmp/tx-titulo-cap"); shutil.rmtree(T, ignore_errors=True); T.mkdir()
os.environ.update(TUXENC_FFMPEG_DIR=FF, XDG_CONFIG_HOME=str(T/"c"), XDG_CACHE_HOME=str(T/"k"),
                  XDG_STATE_HOME=str(T/"s"), XDG_DATA_HOME=str(T/"d"), QT_QPA_PLATFORM="offscreen",
                  PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
from tuxenc import i18n  # noqa: E402
i18n.set_language("es")
from tuxenc.app import _make_app  # noqa: E402
app = _make_app()
import tuxenc.ui.main_window as mw  # noqa: E402
import tuxenc.ui.rename_ctrl as rc  # noqa: E402
from tuxenc.config import Config  # noqa: E402
from tuxenc.library import AMBIGUOUS, OK  # noqa: E402
from tests.fake_search import ARROW, FakeSearcher  # noqa: E402


def pump(sec):
    t = time.time()
    while time.time() - t < sec:
        app.processEvents(); time.sleep(0.02)


def wait(cond, to=30):
    t = time.time()
    while not cond() and time.time() - t < to:
        pump(0.05)
    return cond()


d = T / "Arrow (2012)" / "Season 01"
d.mkdir(parents=True)
os.link(M + "hd720.mkv", d / "Arrow (2012) - S01E01 - Honra a tu padre.mkv")   # es el título del E02
os.link(M + "hd720.mkv", d / "Arrow (2012) - S01E03 - Pistoleros solitarios.mkv")   # cuadra

cfg = Config()
cfg.engines_notice_shown = True
cfg.convert_on, cfg.rename_on = False, True
w = mw.MainWindow(cfg)
w.show()
w.rename.lib.searcher = FakeSearcher()
w.add_paths([str(T / "Arrow (2012)")])
assert wait(lambda: len(w.engine.jobs) == 2 and all(j.ident not in ("pending", "off") for j in w.engine.jobs))
pump(0.3)
bad = next(j for j in w.engine.jobs if "E01" in j.name)
good = next(j for j in w.engine.jobs if "E03" in j.name)
print("E01:", bad.ident, bad.note)
print("E03:", good.ident, good.note)
assert good.ident == OK
assert bad.ident == AMBIGUOUS and "S01E02" in bad.note and "Honra a tu padre" in bad.note, bad.note
assert not bad.preview

# La ventana de «Identificar…» propone el capítulo del título
seen = {}


def fake_exec(self):
    seen["want"] = (self.want_season, self.want_eps)
    self.result_match, self.result_season, self.result_episodes = ARROW, 1, (2,)
    return 1


rc.MatchDialog.exec = fake_exec
w.rename.open_match(bad)
assert wait(lambda: bad.ident == OK), (bad.ident, bad.note)
assert seen["want"] == (1, (2,)), seen
assert "S01E02 - Honra a tu padre" in bad.preview, bad.preview
print("OK: propone", seen["want"], "→", bad.preview)
app.processEvents()
os._exit(0)
