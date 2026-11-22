"""1.3.5: añadir miles de vídeos no se hace cada vez más lento.

Antes, cada fila nueva hacía que Qt recolocara todas las anteriores: con 500 vídeos la cola
tardaba 4,5 s y con 2000, 42 s (el tiempo crecía con el cuadrado). El análisis se simula
instantáneo para medir solo la cola: con el doble de vídeos tiene que tardar más o menos el doble.
"""
import copy, os, shutil, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
T = Path(tempfile.mkdtemp(prefix="tx-cola-grande-"))
os.environ.update(XDG_CONFIG_HOME=str(T/"c"), XDG_CACHE_HOME=str(T/"k"), XDG_STATE_HOME=str(T/"s"),
                  XDG_DATA_HOME=str(T/"d"), QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"),
                  PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
from tests.media import MEDIA  # noqa: E402
from tuxenc import i18n  # noqa: E402
i18n.set_language("es")
from tuxenc.app import _make_app  # noqa: E402
app = _make_app()
import tuxenc.ui.main_window as mw  # noqa: E402
from tuxenc.config import Config  # noqa: E402
from tests.fake_search import FakeSearcher  # noqa: E402

sample = mw.probe(str(MEDIA / "lib" / "Arrow.S01E02.1080p.WEB-DL.mkv"), measure_audio=False)


def fast_probe(path, measure_audio=False, timeout=60):
    info = copy.deepcopy(sample)
    info.path = path
    return info


mw.probe = fast_probe


def load(n: int) -> float:
    src = T / f"in{n}"
    for k in range(n):
        d = src / "Arrow (2012)" / f"Season {k // 500 + 1:02}"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"Arrow (2012) - S{k // 500 + 1:02}E{k % 500 + 1:03}.mkv").touch()
    cfg = Config()
    cfg.engines_notice_shown = True
    cfg.convert_on, cfg.rename_on = False, True
    w = mw.MainWindow(cfg)
    w.resize(946, 700)
    w.show()
    w.rename.lib.searcher = FakeSearcher()
    t0 = time.monotonic()
    w.add_paths([str(src)])
    while w.pending_probes or any(j.ident == "pending" for j in w.engine.jobs) or len(w.engine.jobs) < n:
        app.processEvents()
        time.sleep(0.001)
    took = time.monotonic() - t0
    assert len(w.queue.rows) == n and w.queue.count() == n
    ids = [w.queue.item(i).data(0x0100) for i in range(w.queue.count())]
    assert ids == [j.id for j in w.engine.jobs], "la lista no sigue el orden de la cola"
    w.close()
    w.deleteLater()
    app.processEvents()
    return took


small, big = load(500), load(2000)
print(f"500 vídeos: {small:.1f} s · 2000 vídeos: {big:.1f} s · proporción {big / small:.1f} (lineal ≈ 4, cuadrado ≈ 16)")
assert big / small < 7, "la cola crece más deprisa que el número de vídeos"
shutil.rmtree(T, ignore_errors=True)
os._exit(0)
