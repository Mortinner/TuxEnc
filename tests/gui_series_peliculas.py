"""1.3.5: TuxEnc no se fía de una identificación que contradice dónde está el vídeo.

Caso de Marcos: capítulos con el número escrito de forma rara acabaron como películas en la
biblioteca de películas, 57 de ellos con el mismo nombre de película y (2), (3)… Ahora:
  * un vídeo de Series (o de una carpeta «Season NN») identificado como película,
  * un vídeo de Películas identificado como serie,
  * varios vídeos identificados como la misma película,
quedan como dudosos y no se renombran hasta que se confirman a mano con «Identificar…».
"""
import os, shutil, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.media import FF, M  # noqa: E402
T = Path("/tmp/tx-series-pelis"); shutil.rmtree(T, ignore_errors=True); T.mkdir()
os.environ.update(TUXENC_FFMPEG_DIR=FF, XDG_CONFIG_HOME=str(T/"c"), XDG_CACHE_HOME=str(T/"k"),
                  XDG_STATE_HOME=str(T/"s"), XDG_DATA_HOME=str(T/"d"), QT_QPA_PLATFORM="offscreen",
                  PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
from tuxenc import i18n  # noqa: E402
i18n.set_language("es")
from tuxenc.app import _make_app  # noqa: E402
app = _make_app()
import tuxenc.ui.main_window as mw  # noqa: E402
from tuxenc.config import Config  # noqa: E402
from tuxenc.library import AMBIGUOUS, EPISODE, OK  # noqa: E402
from retitler.providers import ResultKind, SearchResult  # noqa: E402
from retitler.search import SearchResponse  # noqa: E402
from tests.fake_search import ARROW, BABEL, FakeSearcher  # noqa: E402

SEAQUEST_MOVIE = SearchResult("tmdb", ResultKind.MOVIE, 999, "SeaQuest DSV", 1993, score=0.97)
FOO_MOVIE = SearchResult("tmdb", ResultKind.MOVIE, 998, "Foo", 1990, score=0.97)


class Searcher(FakeSearcher):
    def search(self, query, kind=None, year=None):
        q = query.casefold()
        if "seaquest" in q:
            return SearchResponse([SEAQUEST_MOVIE])
        if "foo" in q:
            return SearchResponse([FOO_MOVIE])
        return super().search(query, kind, year)


def pump(sec):
    t = time.time()
    while time.time() - t < sec:
        app.processEvents(); time.sleep(0.02)


def wait(cond, to=30):
    t = time.time()
    while not cond() and time.time() - t < to:
        pump(0.05)
    return cond()


series, movies, down = T / "Series", T / "Peliculas", T / "descargas"
files = {
    "season": series / "SeaQuest DSV (1993)" / "Season 01" / "SeaQuest DSV (1993) - raro.mkv",
    "series": series / "Foo (1990)" / "Foo (1990) - especial.mkv",
    "movie_as_show": movies / "A" / "Arrow.S01E02.720p.mkv",
    "babel1": down / "Babel (2006) 720p.mkv",
    "babel2": down / "otra" / "Babel (2006) 720p.mkv",
    "arrow_ok": down / "Arrow.S01E03.720p.mkv",
}
for f in files.values():
    f.parent.mkdir(parents=True, exist_ok=True)
    os.link(M + "hd720.mkv", f)

cfg = Config()
cfg.engines_notice_shown = True
cfg.convert_on, cfg.rename_on = False, True
cfg.output_mode, cfg.series_root, cfg.movie_root = "library", str(series), str(movies)
w = mw.MainWindow(cfg)
w.show()
w.rename.lib.searcher = Searcher()
w.add_paths([str(T / d) for d in ("Series", "Peliculas", "descargas")])
assert wait(lambda: len(w.engine.jobs) == len(files) and all(j.ident not in ("pending", "off") for j in w.engine.jobs))
pump(0.3)
job = {k: next(j for j in w.engine.jobs if j.input == str(f)) for k, f in files.items()}
state = {k: (j.ident, j.note) for k, j in job.items()}
for k, v in state.items():
    print(f"{k:14} {v[0]:10} {v[1]}")

# Dentro de «Season 01» es un capítulo; el buscador solo da una película: dudoso
assert job["season"].ident == AMBIGUOUS and "carpeta de temporada" in job["season"].note
# En Series sin carpeta de temporada, identificado como película: dudoso
assert job["series"].ident == AMBIGUOUS and "Está en Series" in job["series"].note
# En Películas, identificado como serie: dudoso
assert job["movie_as_show"].ident == AMBIGUOUS and "Está en Películas" in job["movie_as_show"].note
# Dos vídeos con la misma película: los dos dudosos
for k in ("babel1", "babel2"):
    assert job[k].ident == AMBIGUOUS and "2 vídeos parecen la misma película" in job[k].note, k
# Lo normal sigue igual
assert job["arrow_ok"].ident == OK, state["arrow_ok"]
# Los dudosos no tienen nombre nuevo, así que no se renombran
assert all(not job[k].preview for k in files if k != "arrow_ok")

# Confirmar a mano una de las Babel: esa queda bien (la otra sigue preguntando)
w.rename._on_chosen(job["babel1"].id, w.rename.lib.choose(job["babel1"].rt, BABEL))
pump(0.2)
assert job["babel1"].ident == OK and job["babel1"].preview, (job["babel1"].ident, job["babel1"].note)
assert job["babel2"].ident == AMBIGUOUS
# Confirmar a mano el de Películas como serie (el usuario manda)
w.rename._on_chosen(job["movie_as_show"].id,
                    w.rename.lib.choose(job["movie_as_show"].rt, ARROW))
pump(0.2)
assert job["movie_as_show"].ident == OK, job["movie_as_show"].note
print("OK: las identificaciones que no cuadran con la carpeta se preguntan")
app.processEvents()
os._exit(0)
