"""Capítulos numerados solo con un número (caso de Marcos, 1.3.0): 71 «Dinosaucers NN.mp4».

Antes: solo el 01 se identificaba y «misma serie» no se aplicaba a ninguno. Ahora:
- todos se reconocen como capítulos y se busca la serie una sola vez;
- la numeración absoluta se convierte (T1 con 65 capítulos → «66» es T2E01);
- si la serie no se encuentra sola, identificar uno a mano con «misma serie» arregla los 71, y
  la casilla dice a cuántos afecta;
- las películas con número («Rocky 2», «Ocean's 11», «2012») siguen siendo películas.
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.media import M  # noqa: E402
T = Path(tempfile.mkdtemp(prefix="tx-dino-"))
os.environ.update(XDG_CONFIG_HOME=str(T / "c"), XDG_CACHE_HOME=str(T / "k"), XDG_STATE_HOME=str(T / "s"),
                  XDG_DATA_HOME=str(T / "d"), QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"),
                  PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
from tuxenc import i18n  # noqa: E402
i18n.set_language("es")
from tuxenc.app import _make_app  # noqa: E402
app = _make_app()
import tuxenc.ui.main_window as mw  # noqa: E402
import tuxenc.ui.rename_ctrl as rc  # noqa: E402
from tuxenc.config import Config  # noqa: E402
from retitler.providers import EpisodeInfo, ResultKind, SearchResult  # noqa: E402
from retitler.search import SearchResponse  # noqa: E402

DINO = SearchResult("tmdb", ResultKind.SERIES, 4418, "Dinosaucers", 1987, score=0.95)
MOVIES = {"rocky": SearchResult("tmdb", ResultKind.MOVIE, 1367, "Rocky II", 1979, score=0.9),
          "ocean's": SearchResult("tmdb", ResultKind.MOVIE, 161, "Ocean's Eleven", 2001, score=0.9),
          "2012": SearchResult("tmdb", ResultKind.MOVIE, 14161, "2012", 2009, score=0.9)}
COUNTS = {1: 65, 2: 6}


class Fake:
    def __init__(self):
        self.find_dino = True
        self.queries: list[tuple] = []

    def search(self, query, kind=None, year=None):
        self.queries.append((query, kind.value if kind is not None else None))
        q = query.casefold()
        if "dinosaucers" in q:
            return SearchResponse([DINO] if self.find_dino else [])
        for key, res in MOVIES.items():
            if q.startswith(key):
                return SearchResponse([res])
        return SearchResponse([])

    def search_parsed(self, parsed):
        return self.search(parsed.title, kind=parsed.kind, year=parsed.year)

    def episode_titles_detailed(self, result, season, episodes):
        return [EpisodeInfo(season, n, f"Episodio {season}x{n:02}", source="tmdb") for n in episodes]

    def seasons(self, result):
        return list(COUNTS) + [0]

    def season_episodes(self, result, season):
        return [EpisodeInfo(season, i, f"Episodio {season}x{i:02}", source="tmdb")
                for i in range(1, COUNTS.get(season, 0) + 1)]


def pump(sec):
    t = time.time()
    while time.time() - t < sec:
        app.processEvents()
        time.sleep(0.02)


def wait(cond, to=60):
    t = time.time()
    while not cond() and time.time() - t < to:
        pump(0.05)
    return cond()


tv = T / "Series"
tv.mkdir()
for i in range(1, 72):
    os.link(M + "hd720.mkv", tv / f"Dinosaucers {i:02}.mp4")
pelis = T / "Peliculas"
pelis.mkdir()
for name in ("Rocky 2.mkv", "Rocky 3.mkv", "Ocean's 11.mkv", "2012.mkv"):
    os.link(M + "hd720.mkv", pelis / name)

cfg = Config()
cfg.engines_notice_shown = True
cfg.convert_on, cfg.rename_on = False, True
cfg.output_mode = "library"
cfg.series_root, cfg.movie_root = str(T / "Bib" / "Series"), str(T / "Bib" / "Peliculas")
w = mw.MainWindow(cfg)
w.show()
fake = Fake()
w.rename.lib.searcher = fake
w.add_paths([str(tv), str(pelis)])
assert wait(lambda: len(w.engine.jobs) == 75 and not w.pending_probes
            and all(j.ident not in ("off", "pending") for j in w.engine.jobs)), [j.ident for j in w.engine.jobs][:10]
dino = {int(j.name[12:14]): j for j in w.engine.jobs if j.name.startswith("Dinosaucers")}
movies = {j.name: j for j in w.engine.jobs if not j.name.startswith("Dinosaucers")}

# 1) Los 71 son capítulos de la misma serie y se ha buscado «Dinosaucers» una sola vez
assert all(j.ident == "ok" for j in dino.values()), {k: j.ident for k, j in dino.items() if j.ident != "ok"}
assert sum(1 for q, _ in fake.queries if "dinosaucers" in q.casefold()) == 1, fake.queries
eps = {k: (j.rt.parsed.season, j.rt.parsed.episodes) for k, j in dino.items()}
assert eps[1] == (1, (1,)) and eps[65] == (1, (65,)) and eps[66] == (2, (1,)) and eps[71] == (2, (6,)), eps
assert "S02E01" in dino[66].preview and "Episodio 2x01" in dino[66].preview, dino[66].preview
print("vista previa del 66:", dino[66].preview)

# 2) Las películas con número siguen siendo películas
for name, j in movies.items():
    assert j.rt.parsed.kind.value != "episode", (name, j.rt.parsed)
    assert j.rt.chosen is not None and j.rt.chosen.kind is ResultKind.MOVIE, (name, j.rt.chosen)
print("películas:", {n: j.rt.chosen.label for n, j in movies.items()})

# 3) Si la serie no aparece sola: identificar uno a mano con «misma serie» arregla los 71
w.engine.jobs[:] = [j for j in w.engine.jobs if not j.name.startswith("Dinosaucers")]
w.queue.sync(w.engine.jobs)
fake.find_dino = False
fake.queries.clear()
w.rename.lib.memo.clear()
w.add_paths([str(tv)])
assert wait(lambda: len(w.engine.jobs) == 75 and not w.pending_probes
            and all(j.ident not in ("off", "pending") for j in w.engine.jobs))
dino = {int(j.name[12:14]): j for j in w.engine.jobs if j.name.startswith("Dinosaucers")}
assert all(j.ident == "none" for j in dino.values()), {j.ident for j in dino.values()}
labels = []


def fake_exec(self):
    labels.append(self.same.text())
    self.result_match, self.result_season, self.result_episodes = DINO, None, None
    self.same.setVisible(self.same_count != 0)     # como al elegir la serie en la lista
    self.same.setChecked(True)
    return 1


rc.MatchDialog.exec = fake_exec
w.rename.open_match(dino[1])
assert wait(lambda: all(j.ident == "ok" for j in dino.values())), {k: j.ident for k, j in dino.items() if j.ident != "ok"}
print("casilla:", labels[0])
assert "otros 70 capítulos de «Dinosaucers»" in labels[0], labels
assert (dino[66].rt.parsed.season, dino[66].rt.parsed.episodes) == (2, (1,))
assert all(j.rt.chosen.kind is ResultKind.MOVIE for j in movies.values())     # no se tocan
w.engine.shutdown()
w.rename.shutdown()
shutil.rmtree(T, ignore_errors=True)
print("OK")
