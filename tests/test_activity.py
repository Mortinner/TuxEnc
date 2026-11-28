"""Historial legible (pestaña «Historial»): renombrados del historial de deshacer y conversiones."""
import json

from retitler.renamer import History

from tuxenc import activity


def _history(tmp_path):
    h = tmp_path / "history.jsonl"
    rows = [
        {"id": "a1", "time": "2026-11-25T07:18:43+00:00", "created_dirs": [],
         "moves": [["/d/Telegram/8x03 - El detective Endeavour.mkv",
                    "/s/Endeavour (2013)/Season 08/Endeavour (2013) - S08E03 - Terminus - [1080p].mkv"],
                   ["/d/Telegram/8x03 - El detective Endeavour.es.srt",
                    "/s/Endeavour (2013)/Season 08/Endeavour (2013) - S08E03 - Terminus - [1080p].es.srt"]]},
        {"id": "b2", "time": "2026-11-26T10:00:00+00:00", "created_dirs": [],
         "moves": [["/d/Babel.2006.mkv", "/p/B/Babel (2006) - [1080p].mkv"]]},
        {"id": "b2", "undone": "2026-11-26T10:05:00+00:00"},
    ]
    h.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return History(h)


def test_mezcla_renombrados_y_conversiones_lo_ultimo_primero(tmp_path):
    act = tmp_path / "actividad.jsonl"
    activity.record_conversion("/d/Outlander 2x09.mkv", "/s/Outlander/Season 02/Outlander - S02E09.mkv",
                               renamed=True, original="trash", subs=1, path=act)
    items = activity.load(history=_history(tmp_path), path=act)
    assert [e.kind for e in items] == ["convert_rename", "rename", "rename"]
    conv, babel, endeavour = items
    assert conv.original == "trash" and conv.subs == 1 and conv.renamed
    assert babel.undone and not endeavour.undone
    assert endeavour.subs == 1 and endeavour.src.endswith("8x03 - El detective Endeavour.mkv")


def test_archivo_roto_no_rompe_nada(tmp_path):
    act = tmp_path / "actividad.jsonl"
    act.write_text("no es json\n{}\n")
    assert activity.load(history=History(tmp_path / "no-existe.jsonl"), path=act) == []


def test_se_recorta_al_crecer(tmp_path, monkeypatch):
    act = tmp_path / "actividad.jsonl"
    monkeypatch.setattr(activity, "MAX_BYTES", 2000)
    for i in range(60):
        activity.record_conversion(f"/a/{i}.mkv", f"/b/{i}.mkv", renamed=False, path=act)
    lines = act.read_text().splitlines()
    assert act.stat().st_size <= 2000 and json.loads(lines[-1])["src"] == "/a/59.mkv"
    assert all(json.loads(line) for line in lines)          # ninguna línea cortada


def test_lineas_al_reves_con_bloques_pequenos(tmp_path):
    f = tmp_path / "x.jsonl"
    lines = ["a" * 5, "b" * 300, "", "c", "d" * 70]
    f.write_text("\n".join(lines) + "\n")
    assert list(activity._reverse_lines(f, chunk=16)) == ["d" * 70, "c", "b" * 300, "a" * 5]


def _big_history(path, batches, per_batch):
    with open(path, "w") as fh:
        for b in range(batches):
            moves = [[f"/d/{b}-{i}.mkv", f"/s/Serie/Season 01/Serie - S01E{i:02d} - [1080p].mkv"]
                     for i in range(per_batch)]
            fh.write(json.dumps({"id": f"id{b}", "time": f"2026-01-01T00:00:{b % 60:02d}+00:00"
                                 if b < 60 else f"2027-{1 + b % 12:02d}-01T00:00:00+00:00",
                                 "moves": moves, "created_dirs": []}) + "\n")


def test_paginas_de_20(tmp_path):
    h = tmp_path / "history.jsonl"
    _big_history(h, 3, 15)                       # 45 vídeos
    act = tmp_path / "a.jsonl"
    p0, more0 = activity.page(0, history_path=h, path=act)
    p1, more1 = activity.page(1, history_path=h, path=act)
    p2, more2 = activity.page(2, history_path=h, path=act)
    assert (len(p0), more0, len(p1), more1, len(p2), more2) == (20, True, 20, True, 5, False)
    assert {e.src for e in p0}.isdisjoint({e.src for e in p1})


def test_primera_pagina_rapida_con_anos_de_historial(tmp_path):
    import time
    h = tmp_path / "history.jsonl"
    _big_history(h, 3000, 40)                    # 120 000 vídeos renombrados, unos 20 MB
    t = time.perf_counter()
    first, more = activity.page(0, history_path=h, path=tmp_path / "a.jsonl")
    assert len(first) == 20 and more
    assert time.perf_counter() - t < 0.5, "la primera página no debe leer todo el archivo"
