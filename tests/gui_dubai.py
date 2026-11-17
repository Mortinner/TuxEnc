"""Caso real «Aeropuerto de Dubái»: no sale por nombre; se pega el enlace de IMDb en «Identificar…»
y la serie se aplica a todos los capítulos. Buscador REAL con respuestas simuladas de TMDB y TVmaze."""
import os, shutil, sys, time
from pathlib import Path
sys.path.insert(0, "/home/claude/tuxenc")
T = Path("/tmp/tx-dubai"); shutil.rmtree(T, ignore_errors=True); T.mkdir()
os.environ.update(TUXENC_FFMPEG_DIR="/home/claude/dl/rel-8.1/ffmpeg-n8.1-latest-linux64-gpl-shared-8.1/bin",
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

SHOW = {"id": 61234, "name": "Aeropuerto de Dubái", "original_name": "Ultimate Airport Dubai",
        "first_air_date": "2013-11-06", "popularity": 3.1,
        "seasons": [{"season_number": 1, "episode_count": 3}, {"season_number": 2, "episode_count": 2}]}
EPS = {1: ["Llegadas", "Tormenta de arena", "El A380"], 2: ["Aviones averiados", "Aduanas"]}
routes = {
    "/3/search/tv": {"results": []}, "/3/search/movie": {"results": []},
    "/3/find/tt3324124": {"tv_results": [SHOW], "movie_results": []},
    "/3/tv/61234": SHOW, "/3/tv/61234/external_ids": {"imdb_id": "tt3324124"},
    "/search/shows": [], "/lookup/shows": {"id": 8001, "name": "Ultimate Airport Dubai", "premiered": "2013-11-06"},
    "/shows/8001/episodes": [{"season": s, "number": i + 1, "name": f"Episode {i + 1}"}
                             for s, t in EPS.items() for i, _ in enumerate(t)],
}
for s, titles in EPS.items():
    routes[f"/3/tv/61234/season/{s}"] = {"episodes": [{"episode_number": i + 1, "name": t, "air_date": f"2013-11-{6 + i:02}"}
                                                      for i, t in enumerate(titles)]}
fetch = FakeFetch(routes)

def pump(sec):
    t = time.time()
    while time.time() - t < sec: app.processEvents(); time.sleep(0.03)
def wait(c, to=60):
    t = time.time()
    while not c() and time.time() - t < to: pump(0.1)
    return c()

down = T / "D"; down.mkdir()
src = "/home/claude/testmedia/lib/Arrow.S01E02.1080p.WEB-DL.mkv"
for i in (1, 2, 3):
    shutil.copy(src, down / f"Aeropuerto de Dubai (2013) - S01E0{i} - Episodio {i}.mkv")
cfg = Config(); cfg.rename_on = True; cfg.convert_on = False
w = mw.MainWindow(cfg); w.resize(1100, 560); w.show(); pump(1)
w.rename.lib.searcher = Searcher(TMDBClient("a" * 32, "es", fetch=fetch), TVmazeClient(fetch=fetch))
w._bar_dismissed.add("tmdb"); w._update_bar()
w.add_paths([str(down)]); assert wait(lambda: len(w.engine.jobs) == 3 and all(j.ident != "pending" for j in w.engine.jobs))
print("por nombre:", sorted({j.ident for j in w.engine.jobs}), "|", w.engine.jobs[0].note)
first = min(w.engine.jobs, key=lambda j: j.name)

def fake_exec(self):
    self.show()
    self.kind.setCurrentIndex(1)                           # «Serie» (el fallo de dev.11)
    self.query.setText("https://www.imdb.com/es-es/title/tt3324124/"); self._search()
    assert wait(lambda: self.list.count() > 0 or "⚠" in self.status.text()), self.status.text()
    print("con el enlace:", [self.list.item(i).text() for i in range(self.list.count())], "| aviso:", self.status.text() or "ninguno")
    assert wait(lambda: self.eps.count() > 1 and self.eps.item(0).data(0x0100) is not None)
    print("temporadas:", [self.season.itemText(i) for i in range(self.season.count())])
    print("capítulos:", [self.eps.item(i).text() for i in range(self.eps.count())])
    self.eps.clearSelection(); self.eps.item(0).setSelected(True); pump(0.2)
    print("resumen:", self.choice.text(), "| aplicar a los demás:", self.same.isVisible() and self.same.isChecked())
    self.grab().save(f"/tmp/shots-merge/{lang}-13-enlace.png")
    self._accept()
    return 1
rc.MatchDialog.exec = fake_exec
w._on_row_action("double", first.id)
assert wait(lambda: all(j.ident == "ok" for j in w.engine.jobs)), [j.note for j in w.engine.jobs]
for j in sorted(w.engine.jobs, key=lambda j: j.name):
    print(" ", j.name, "->", j.preview)
w.grab().save(f"/tmp/shots-merge/{lang}-14-dubai-cola.png")
w.engine.shutdown(); w.rename.shutdown()
