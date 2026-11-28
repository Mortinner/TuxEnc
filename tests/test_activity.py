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
    monkeypatch.setattr(activity, "MAX_LINES", 10)
    for i in range(25):
        activity.record_conversion(f"/a/{i}.mkv", f"/b/{i}.mkv", renamed=False, path=act)
    lines = act.read_text().splitlines()
    assert len(lines) <= 10 and json.loads(lines[-1])["src"] == "/a/24.mkv"
