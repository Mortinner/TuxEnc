"""«Usar esta misma serie para los demás capítulos»: se aplica a todos los capítulos de la serie
que no han empezado, también a los ya identificados (caso de Marcos: había que ir uno a uno).
Se respetan los capítulos elegidos a mano uno a uno."""
import os, shutil, sys, time
from pathlib import Path
sys.path.insert(0, "/home/claude/tuxenc")
T = Path("/tmp/tx-same"); shutil.rmtree(T, ignore_errors=True); T.mkdir()
os.environ.update(TUXENC_FFMPEG_DIR="/home/claude/dl/rel-8.1/ffmpeg-n8.1-latest-linux64-gpl-shared-8.1/bin",
                  XDG_CONFIG_HOME=str(T/"c"), XDG_CACHE_HOME=str(T/"k"), XDG_STATE_HOME=str(T/"s"),
                  QT_QPA_PLATFORM="offscreen", PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
from tuxenc.app import _make_app
app = _make_app()
import tuxenc.ui.main_window as mw, tuxenc.ui.rename_ctrl as rc
from tuxenc.config import Config
from tests.fake_search import FakeSearcher, ARROW, ARROW_TVM
def pump(sec):
    t = time.time()
    while time.time() - t < sec: app.processEvents(); time.sleep(0.02)
def wait(c, to=30):
    t = time.time()
    while not c() and time.time() - t < to: pump(0.05)
    return c()
src = T / "arrow"; src.mkdir()
for e in (1, 2, 3, 4):
    os.link("/home/claude/testmedia/hd720.mkv", src / f"Arrow.S01E{e:02}.720p.mkv")
cfg = Config(); cfg.engines_notice_shown = True; cfg.convert_on = False; cfg.rename_on = True
w = mw.MainWindow(cfg); w.show()
w.rename.lib.searcher = FakeSearcher()
w.add_paths([str(src)])
assert wait(lambda: len(w.engine.jobs) == 4 and all(j.ident == "ok" for j in w.engine.jobs))
by = {j.name[6:12]: j for j in w.engine.jobs}
prov = lambda: {k: j.rt.chosen.provider for k, j in sorted(by.items())}
print("identificados solos:", prov())

def dialog(match, season=None, episodes=None, same=False):
    def fake_exec(self):
        self.result_match, self.result_season, self.result_episodes = match, season, episodes
        self.same.setVisible(True); self.same.setChecked(same)
        return 1
    rc.MatchDialog.exec = fake_exec

# El usuario fija a mano el capítulo de S01E03 (con TMDB): ese debe respetarse
dialog(ARROW, 1, (3,)); w.rename.open_match(by["S01E03"])
assert wait(lambda: by["S01E03"].ident == "ok")
# Corrige el S01E01 eligiendo TVmaze y marca «misma serie para los demás»
dialog(ARROW_TVM, same=True); w.rename.open_match(by["S01E01"])
assert wait(lambda: all(j.ident == "ok" for j in w.engine.jobs))
print("tras «misma serie»:", prov())
print("   capítulos conservados:", {k: (j.rt.parsed.season, j.rt.parsed.episodes) for k, j in sorted(by.items())})
assert prov() == {"S01E01": "tvmaze", "S01E02": "tvmaze", "S01E03": "tmdb", "S01E04": "tvmaze"}, prov()
# Segunda corrección (vuelve a TMDB): los que cambió «misma serie» siguen cambiando, no quedan bloqueados
dialog(ARROW, same=True); w.rename.open_match(by["S01E02"])
assert wait(lambda: all(j.ident == "ok" for j in w.engine.jobs) and by["S01E04"].rt.chosen.provider == "tmdb")
print("segunda corrección desde otro capítulo:", prov())
print("OK")
w.engine.shutdown(); w.rename.shutdown()
