import os, shutil, sys, time
from pathlib import Path
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from tests.media import FF, M, MEDIA  # noqa: E402,F401  (FFmpeg y vídeos de prueba)
T = Path("/tmp/tx-ident"); shutil.rmtree(T, ignore_errors=True); T.mkdir()
os.environ.update(TUXENC_FFMPEG_DIR=FF,
                  XDG_CONFIG_HOME=str(T/"c"), XDG_CACHE_HOME=str(T/"k"), XDG_STATE_HOME=str(T/"s"), QT_QPA_PLATFORM="offscreen")
lang = sys.argv[1] if len(sys.argv) > 1 else "es"
from tuxenc import i18n; i18n.set_language(lang)
from tuxenc.app import _make_app
app = _make_app()
import tuxenc.ui.main_window as mw
import tuxenc.ui.rename_ctrl as rc
from PySide6.QtWidgets import QMessageBox
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
from tests.fake_search import FakeSearcher
from tuxenc.config import Config
def pump(sec):
    t = time.time()
    while time.time() - t < sec: app.processEvents(); time.sleep(0.03)
def wait(c, to=60):
    t = time.time()
    while not c() and time.time() - t < to: pump(0.1)
    return c()
down = T/"D"; down.mkdir()
shutil.copy(M + "lib/Arrow.S01E03.1080p.WEB-DL.mkv", down/"Arrow EN DIRECTO.mkv")
shutil.copy(M + "lib/Arrow.S01E02.1080p.WEB-DL.mkv", down/"Arrow.S01E02.mkv")
cfg = Config(); cfg.rename_on = True; cfg.convert_on = False
w = mw.MainWindow(cfg); w.resize(1100, 520); w.show(); pump(1); w.rename.lib.searcher = FakeSearcher()
w._bar_dismissed.add("tmdb"); w._update_bar()
w.add_paths([str(down)]); assert wait(lambda: len(w.engine.jobs) == 2 and all(j.ident != "pending" for j in w.engine.jobs))
job = next(j for j in w.engine.jobs if "DIRECTO" in j.name)
other = next(j for j in w.engine.jobs if j is not job)
print("estado:", job.ident, "|", job.note)
print("botón de la fila:", job.id in w.queue.rows and w.queue.rows[job.id][1].buttons["match"].text(),
      "visible:", w.queue.rows[job.id][1].buttons["match"].isVisible())
w.grab().save(f"/tmp/shots-merge/{lang}-7-falta-capitulo.png")

def fake_exec(self):
    self.show()
    assert wait(lambda: self.eps.count() > 1 and self.eps.item(0).data(0x0100) is not None)
    print("temporadas:", [self.season.itemText(i) for i in range(self.season.count())], "| elegida:", self.season.currentText())
    print("capítulos:", [self.eps.item(i).text() for i in range(self.eps.count())])
    # buscar a mano con «Serie» elegido en el desplegable (fallo de dev.11: 'str' has no 'value')
    self.kind.setCurrentIndex(1); self.query.setText("Arrow"); self._search()
    assert wait(lambda: self.list.count() > 0 or "⚠" in self.status.text()), self.status.text()
    print("búsqueda a mano como Serie:", self.list.count(), "resultado(s) | aviso:", self.status.text() or "ninguno")
    self.kind.setCurrentIndex(2); self.query.setText("Babel"); self._search()
    assert wait(lambda: self.list.count() > 0 or "⚠" in self.status.text())
    print("búsqueda a mano como Película:", self.list.count(), "| aviso:", self.status.text() or "ninguno")
    self.kind.setCurrentIndex(1); self.query.setText("Arrow"); self._search()
    assert wait(lambda: self.list.count() > 0)
    assert wait(lambda: self.eps.count() > 1 and self.eps.item(0).data(0x0100) is not None)
    self.season.setCurrentIndex(0)                       # cambiar a la temporada 1
    assert wait(lambda: self.eps.count() == 4 and self.eps.item(0).data(0x0100) is not None)
    self.eps.item(1).setSelected(True); pump(0.2)
    print("resumen:", self.choice.text(), "| Aceptar activo:", self.ok.isEnabled())
    self.grab().save(f"/tmp/shots-merge/{lang}-8-identificar.png")
    # capítulo doble
    self.eps.item(2).setSelected(True); pump(0.1); print("doble:", self.choice.text())
    self.eps.item(2).setSelected(False); pump(0.1)
    self._accept()
    return 1
rc.MatchDialog.exec = fake_exec
w._on_row_action("double", job.id)       # doble clic en la fila
assert wait(lambda: job.ident == "ok")
print("tras elegir:", job.note, "->", job.preview)
print("el otro capítulo no se tocó:", other.note, "->", other.preview)
w.engine.shutdown(); w.rename.shutdown()
