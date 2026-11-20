"""Caso real «Foyle's War»: TMDB no tiene los capítulos en español; se conserva el título del archivo
(si lo trae) y el resto queda en inglés, marcado. Buscador REAL con respuestas simuladas."""
import os, shutil, sys, time
from pathlib import Path
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from tests.media import FF, M, MEDIA  # noqa: E402,F401  (FFmpeg y vídeos de prueba)
T = Path("/tmp/tx-foyle"); shutil.rmtree(T, ignore_errors=True); T.mkdir()
os.environ.update(TUXENC_FFMPEG_DIR=FF,
                  XDG_CONFIG_HOME=str(T/"c"), XDG_CACHE_HOME=str(T/"k"), XDG_STATE_HOME=str(T/"s"), QT_QPA_PLATFORM="offscreen")
lang = sys.argv[1] if len(sys.argv) > 1 else "es"
from tuxenc import i18n; i18n.set_language(lang)
from tuxenc.app import _make_app
app = _make_app()
import tuxenc.ui.main_window as mw
import tuxenc.ui.rename_ctrl as rc
from tuxenc.config import Config
from retitler.providers import TMDBClient, TVmazeClient
from retitler.search import Searcher
from tests.rt_core.fakes import FakeFetch

SHOW = {"id": 4057, "name": "Foyle's War", "original_name": "Foyle's War", "first_air_date": "2002-10-27",
        "popularity": 40.0, "seasons": [{"season_number": 1, "episode_count": 4}]}
EN = ["The German Woman", "The White Feather", "A Lesson in Murder", "Eagle Day"]
routes = {
    "/3/search/tv": {"results": [SHOW]}, "/3/search/movie": {"results": []},
    "/3/tv/4057": SHOW, "/3/tv/4057/external_ids": {"imdb_id": "tt0310455"},
    "/3/tv/4057/season/1": lambda q: {"episodes": [
        {"episode_number": i + 1, "name": (t if q["language"] == "en-US" else f"Episodio {i + 1}"),
         "air_date": f"2002-11-{i + 1:02}"} for i, t in enumerate(EN)]},
    "/search/shows": [{"show": {"id": 300, "name": "Foyle's War", "premiered": "2002-10-27", "weight": 90}}],
    "/lookup/shows": {"id": 300, "name": "Foyle's War", "premiered": "2002-10-27"},
    "/shows/300/episodes": [{"season": 1, "number": i + 1, "name": t} for i, t in enumerate(EN)],
}
fetch = FakeFetch(routes)
def pump(sec):
    t = time.time()
    while time.time() - t < sec: app.processEvents(); time.sleep(0.03)
def wait(c, to=60):
    t = time.time()
    while not c() and time.time() - t < to: pump(0.1)
    return c()

down = T / "D"; down.mkdir()
src = M + "lib/Arrow.S01E02.1080p.WEB-DL.mkv"
shutil.copy(src, down / "Foyle`s War (2002) - S01E01 - La mujer alemana.mkv")
shutil.copy(src, down / "Foyle`s War (2002) - S01E02.mkv")
cfg = Config(); cfg.rename_on = True; cfg.convert_on = False
w = mw.MainWindow(cfg); w.resize(1180, 420); w.show(); pump(1)
w.rename.lib.searcher = Searcher(TMDBClient("a" * 32, "es", fetch=fetch), TVmazeClient(fetch=fetch))
w._bar_dismissed.add("tmdb"); w._update_bar()
w.add_paths([str(down)]); assert wait(lambda: len(w.engine.jobs) == 2 and all(j.ident not in ("pending",) for j in w.engine.jobs))
for j in sorted(w.engine.jobs, key=lambda j: j.name):
    print(j.ident, "|", j.note, "\n   ->", j.preview)
w.grab().save(f"/tmp/shots-merge/{lang}-15-foyle.png")

def fake_exec(self):
    self.show(); self._search()
    assert wait(lambda: self.list.count() > 0)
    print("lista:", [self.list.item(i).text().split("\n")[0] for i in range(self.list.count())])
    self.reject(); return 0
rc.MatchDialog.exec = fake_exec
w._on_row_action("match", w.engine.jobs[0].id)
# desactivar la opción → vuelve el inglés
w.rename.lib.settings.keep_file_title = False
r = w.rename.lib.identify(str(down / "Foyle`s War (2002) - S01E01 - La mujer alemana.mkv"))[1]
print("opción desactivada:", r.titles)
w.engine.shutdown(); w.rename.shutdown()
