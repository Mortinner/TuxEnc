"""Las filas no cambian de alto al identificarse, y el botón principal espera (1.3.0).

Antes, al terminar de identificarse, la fila crecía (aparecían la identificación y el nombre nuevo)
y Qt la pintaba un instante con el alto viejo: el contenido salía aplastado y la etiqueta
«Solo renombrar» se veía como un rectángulo encima del título, fila tras fila.
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
T = Path(tempfile.mkdtemp(prefix="tx-filas-"))
os.environ.update(XDG_CONFIG_HOME=str(T / "c"), XDG_CACHE_HOME=str(T / "k"), XDG_STATE_HOME=str(T / "s"),
                  XDG_DATA_HOME=str(T / "d"), QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"),
                  PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
from tests.media import MEDIA  # noqa: E402
from tuxenc import i18n  # noqa: E402
i18n.set_language("es")
from tuxenc.app import _make_app  # noqa: E402
app = _make_app()
import tuxenc.ui.main_window as mw  # noqa: E402
from tuxenc.config import Config  # noqa: E402
from tests.fake_search import FakeSearcher  # noqa: E402


class Slow(FakeSearcher):
    def search(self, *a, **k):
        time.sleep(0.2)
        return super().search(*a, **k)


src = T / "in"
src.mkdir()
for e in range(1, 9):
    shutil.copy(MEDIA / "lib" / "Arrow.S01E02.1080p.WEB-DL.mkv", src / f"Arrow (2012) - S01E{e:02} - Capítulo {e}.mkv")

cfg = Config()
cfg.engines_notice_shown = True
cfg.convert_on, cfg.rename_on = False, True
w = mw.MainWindow(cfg)
w.resize(946, 700)
w.show()
w.rename.lib.searcher = Slow()
w.add_paths([str(src)])

squeezed, heights, btn_states = [], set(), set()
t0 = time.time()
while time.time() - t0 < 20 and not (len(w.engine.jobs) == 8 and all(j.ident == "ok" for j in w.engine.jobs)):
    app.processEvents()
    for _item, row in w.queue.rows.values():
        if row.isVisible():
            if row.height() + 1 < row.sizeHint().height():
                squeezed.append(row.job_id)
            heights.add(row.sizeHint().height())
    if w.pending_probes or any(j.ident == "pending" for j in w.engine.jobs):
        btn_states.add((w.start_btn.isEnabled(), w.start_btn.toolTip().split(":")[0]))
    time.sleep(0.01)
assert all(j.ident == "ok" for j in w.engine.jobs), [j.ident for j in w.engine.jobs]
print("altos de fila vistos:", sorted(heights), "| filas aplastadas:", len(squeezed))
assert not squeezed, f"filas pintadas aplastadas: {squeezed[:10]}"
assert len(heights) == 1, f"las filas cambian de alto al identificarse: {sorted(heights)}"
# Mientras se analiza o identifica, «Iniciar» está desactivado y explica por qué
print("botón mientras espera:", btn_states)
assert btn_states and all(not en and tip.startswith("Espera") for en, tip in btn_states), btn_states
app.processEvents()
w._refresh_controls()
assert w.start_btn.isEnabled() and not w.start_btn.toolTip(), (w.start_btn.isEnabled(), w.start_btn.toolTip())
assert "Identificando" not in w.status_lbl.text()
w.engine.shutdown()
w.rename.shutdown()
print("OK")
