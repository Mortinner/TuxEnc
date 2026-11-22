"""1.3.5: registro que sobrevive a que lo borren y peticiones iguales a la vez que van una vez."""
import logging
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retitler import log as L  # noqa: E402
from retitler.providers import CachedFetch, JsonCache, NotFound  # noqa: E402


def test_el_registro_se_vuelve_a_crear_si_se_borra(tmp_path):
    f = tmp_path / "renombrado.log"
    h = L._Handler(f, maxBytes=5_000_000, backupCount=2, encoding="utf-8")
    lg = logging.getLogger("prueba-135")
    lg.addHandler(h)
    lg.setLevel(logging.INFO)
    try:
        lg.info("uno")
        f.unlink()                       # como hizo Marcos con TuxEnc abierto
        lg.info("dos")
        assert f.read_text() == "dos\n"
        f.rename(tmp_path / "copia.log")
        lg.info("tres")
        assert f.read_text() == "tres\n" and (tmp_path / "copia.log").read_text() == "dos\n"
    finally:
        lg.removeHandler(h)
        h.close()


def test_el_registro_sigue_rotando(tmp_path):
    f = tmp_path / "r.log"
    h = L._Handler(f, maxBytes=200, backupCount=2, encoding="utf-8")
    lg = logging.getLogger("prueba-135-rot")
    lg.addHandler(h)
    lg.setLevel(logging.INFO)
    try:
        for i in range(40):
            lg.info("línea %02d con algo de texto", i)
        assert (tmp_path / "r.log.1").exists() and (tmp_path / "r.log.2").exists()
        assert "línea 39" in f.read_text()
    finally:
        lg.removeHandler(h)
        h.close()


@pytest.mark.parametrize("missing", [False, True])
def test_misma_direccion_a_la_vez_se_pide_una_vez(missing):
    calls = []

    def fetch(url, headers):
        calls.append(url)
        time.sleep(0.2)
        if missing:
            raise NotFound("no")
        return {"ok": 1}

    cf = CachedFetch(fetch, JsonCache(None))
    out = []

    def worker():
        try:
            out.append(cf("https://api.themoviedb.org/3/tv/65153/season/2", {}))
        except NotFound:
            out.append("404")

    ts = [threading.Thread(target=worker) for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(calls) == 1
    assert out == (["404"] * 4 if missing else [{"ok": 1}] * 4)
