import os

import pytest

from retitler import renamer
from retitler.renamer import History, ItemStatus, RenameError, build_plan, execute


def touch(directory, *names):
    out = []
    for name in names:
        p = directory / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(name)
        out.append(p)
    return out


def names(directory):
    return sorted(str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file())


def test_simple_rename_and_undo(tmp_path):
    a, b = touch(tmp_path, "a.mkv", "b.mkv")
    hist = History(tmp_path / "h" / "history.jsonl")
    plan = build_plan([(a, "Uno.mkv"), (b, "Dos.mkv")])
    assert [i.status for i in plan] == [ItemStatus.READY] * 2
    res = execute(plan, hist)
    assert names(tmp_path) == ["Dos.mkv", "Uno.mkv", "h/history.jsonl"]
    assert (tmp_path / "Uno.mkv").read_text() == "a.mkv"      # el contenido viaja con el archivo
    hist.undo_last()
    assert names(tmp_path) == ["a.mkv", "b.mkv", "h/history.jsonl"]
    assert hist.last_undoable() is None
    with pytest.raises(RenameError, match="nada que deshacer"):
        hist.undo_last()
    assert res.entry_id


def test_duplicates_get_suffix_in_input_order(tmp_path):
    files = touch(tmp_path, "x1.mkv", "x2.mkv", "x3.mkv", "x4.mp4")
    plan = build_plan([(f, "Serie - 1x01.mkv") for f in files[:3]] + [(files[3], "Serie - 1x01.mp4")])
    assert [i.target.name for i in plan] == [
        "Serie - 1x01.mkv", "Serie - 1x01 (2).mkv", "Serie - 1x01 (3).mkv", "Serie - 1x01.mp4"]
    assert [i.status for i in plan] == [ItemStatus.READY, ItemStatus.SUFFIXED, ItemStatus.SUFFIXED, ItemStatus.READY]
    execute(plan)
    assert names(tmp_path) == ["Serie - 1x01 (2).mkv", "Serie - 1x01 (3).mkv", "Serie - 1x01.mkv", "Serie - 1x01.mp4"]


def test_duplicates_are_case_insensitive(tmp_path):
    a, b = touch(tmp_path, "a.mkv", "b.mkv")
    plan = build_plan([(a, "Show.mkv"), (b, "SHOW.mkv")])
    assert plan[1].target.name == "SHOW (2).mkv"


def test_suffix_keeps_subtitle_language_extension(tmp_path):
    a, b = touch(tmp_path, "a.es.srt", "b.es.srt")
    plan = build_plan([(a, "Peli.es.srt"), (b, "Peli.es.srt")])
    assert plan[1].target.name == "Peli (2).es.srt"


def test_existing_file_on_disk_is_never_overwritten(tmp_path):
    src, existing = touch(tmp_path, "a.mkv", "Serie - 1x01.mkv")
    plan = build_plan([(src, "Serie - 1x01.mkv")])
    assert plan[0].status is ItemStatus.SUFFIXED and plan[0].target.name == "Serie - 1x01 (2).mkv"
    execute(plan)
    assert existing.read_text() == "Serie - 1x01.mkv"


def test_unchanged_and_skipped(tmp_path):
    a, b, c = touch(tmp_path, "ok.mkv", "sin-nombre.mkv", "malo.mkv")
    plan = build_plan([(a, "ok.mkv"), (b, None), (c, "../fuera.mkv")])
    assert [i.status for i in plan] == [ItemStatus.UNCHANGED, ItemStatus.SKIPPED, ItemStatus.SKIPPED]
    assert execute(plan).moves == []
    assert names(tmp_path) == ["malo.mkv", "ok.mkv", "sin-nombre.mkv"]


def test_unchanged_file_reserves_its_name(tmp_path):
    keep, other = touch(tmp_path, "Show.mkv", "other.mkv")
    plan = build_plan([(keep, "Show.mkv"), (other, "Show.mkv")])
    assert plan[1].target.name == "Show (2).mkv"


def test_chain_and_swap_and_case_only(tmp_path):
    a, b, c = touch(tmp_path, "A.mkv", "B.mkv", "C.mkv")
    # cadena A->B, B->C, C->D y cambio de mayúsculas
    execute(build_plan([(a, "B.mkv"), (b, "C.mkv"), (c, "D.mkv")]))
    assert [(n, (tmp_path / n).read_text()) for n in names(tmp_path)] == [("B.mkv", "A.mkv"), ("C.mkv", "B.mkv"), ("D.mkv", "C.mkv")]

    x, y = tmp_path / "B.mkv", tmp_path / "C.mkv"    # intercambio B<->C
    execute(build_plan([(x, "C.mkv"), (y, "B.mkv")]))
    assert (tmp_path / "B.mkv").read_text() == "B.mkv" and (tmp_path / "C.mkv").read_text() == "A.mkv"

    execute(build_plan([(tmp_path / "D.mkv", "d.mkv")]))  # solo mayúsculas
    assert "d.mkv" in names(tmp_path) and "D.mkv" not in names(tmp_path)
    assert not [n for n in os.listdir(tmp_path) if n.endswith("retitler-tmp")]


def test_folders_are_created_and_removed_on_undo(tmp_path):
    (a,) = touch(tmp_path, "a.mkv")
    hist = History(tmp_path / "state" / "h.jsonl")
    execute(build_plan([(a, "Serie/Temporada 01/Serie - 1x01.mkv")]), hist)
    assert (tmp_path / "Serie/Temporada 01/Serie - 1x01.mkv").exists()
    hist.undo_last()
    assert (tmp_path / "a.mkv").exists() and not (tmp_path / "Serie").exists()


def test_target_root(tmp_path):
    (a,) = touch(tmp_path / "descargas", "a.mkv")
    plan = build_plan([(a, "Serie/x.mkv")], target_root=tmp_path / "biblioteca")
    execute(plan)
    assert (tmp_path / "biblioteca/Serie/x.mkv").exists()


def test_failure_midway_rolls_everything_back(tmp_path, monkeypatch):
    files = touch(tmp_path, "a.mkv", "b.mkv", "c.mkv")
    plan = build_plan([(f, f"nuevo-{f.name}") for f in files])
    real, calls = os.rename, []

    def flaky(src, dst):
        calls.append(src)
        if len(calls) == 3:
            raise PermissionError("denegado")
        return real(src, dst)

    monkeypatch.setattr(renamer.os, "rename", flaky)
    with pytest.raises(RenameError, match="No se ha cambiado nada"):
        execute(plan)
    monkeypatch.setattr(renamer.os, "rename", real)
    assert names(tmp_path) == ["a.mkv", "b.mkv", "c.mkv"]


def test_preflight_catches_vanished_source_and_new_conflict(tmp_path):
    a, b = touch(tmp_path, "a.mkv", "b.mkv")
    plan = build_plan([(a, "x.mkv"), (b, "y.mkv")])
    b.unlink()
    with pytest.raises(RenameError, match="No existe"):
        execute(plan)
    assert names(tmp_path) == ["a.mkv"]                      # no se ha movido nada
    touch(tmp_path, "x.mkv")                                 # aparece algo en el destino después de planificar
    with pytest.raises(RenameError, match="Ya existe"):
        execute(build_plan([(a, "x.mkv")]) and [renamer.PlanItem(a, tmp_path / "x.mkv", ItemStatus.READY)])
    assert (tmp_path / "x.mkv").read_text() == "x.mkv"


def test_undo_refuses_when_original_name_is_taken(tmp_path):
    (a,) = touch(tmp_path, "a.mkv")
    hist = History(tmp_path / "h.jsonl")
    execute(build_plan([(a, "nuevo.mkv")]), hist)
    touch(tmp_path, "a.mkv")                                 # alguien crea otro "a.mkv"
    with pytest.raises(RenameError):
        hist.undo_last()
    assert names(tmp_path) == ["a.mkv", "h.jsonl", "nuevo.mkv"]
    assert hist.last_undoable() is not None                  # sigue pendiente


def test_history_ignores_garbage_and_undone_entries(tmp_path):
    (a,) = touch(tmp_path, "a.mkv")
    hist = History(tmp_path / "h.jsonl")
    hist.path.write_text("basura\n[1,2]\n{\"sin\": \"id\"}\n")
    execute(build_plan([(a, "b.mkv")]), hist)
    execute(build_plan([(tmp_path / "b.mkv", "c.mkv")]), hist)
    assert len(hist.entries()) == 2
    hist.undo_last()                                         # deshace solo el último lote
    assert names(tmp_path) == ["b.mkv", "h.jsonl"]
    hist.undo_last()
    assert names(tmp_path) == ["a.mkv", "h.jsonl"]


def test_duplicate_inputs_are_rejected(tmp_path):
    (a,) = touch(tmp_path, "a.mkv")
    item = renamer.PlanItem(a, tmp_path / "x.mkv", ItemStatus.READY)
    with pytest.raises(RenameError):
        execute([item, item])


def test_suffix_respects_255_bytes(tmp_path):
    long = tmp_path / ("ñ" * 120 + ".mkv")
    out = renamer._with_suffix(long, 2)
    assert len(out.name.encode()) <= 255 and out.name.endswith(" (2).mkv")


def test_cross_device_move_copies_then_deletes(tmp_path, monkeypatch):
    """Entre discos distintos (EXDEV) se copia y se borra el original; deshacer lo devuelve."""
    import errno as _errno
    import os as _os
    from retitler import renamer as rn
    real_rename = _os.rename

    def fake_rename(a, b):
        a, b = str(a), str(b)
        if ("lib" in a) != ("lib" in b) and ".retitler-tmp" not in a:
            raise OSError(_errno.EXDEV, "Invalid cross-device link")
        return real_rename(a, b)

    monkeypatch.setattr(rn.os, "rename", fake_rename)
    src = tmp_path / "down" / "Babel.2006.mkv"
    src.parent.mkdir()
    src.write_bytes(b"x" * 1000)
    lib = tmp_path / "lib"
    lib.mkdir()
    plan = rn.build_plan([(src, "B/Babel (2006) - [1080p].mkv")], lib)
    hist = rn.History(tmp_path / "h.jsonl")
    rn.execute(plan, hist)
    dst = lib / "B" / "Babel (2006) - [1080p].mkv"
    assert dst.read_bytes() == b"x" * 1000 and not src.exists()
    assert not list(lib.rglob("*.retitler-tmp"))
    hist.undo_last()
    assert src.read_bytes() == b"x" * 1000 and not dst.exists() and not (lib / "B").exists()


def test_big_batch_in_parallel_and_rollback_when_one_fails(tmp_path, monkeypatch):
    """1.3.0: los movimientos van varios a la vez; si uno falla, se deshacen todos (también las
    carpetas creadas), y un nombre que aparece después del plan nunca se pisa."""
    src = tmp_path / "down"
    src.mkdir()
    files = [src / f"Serie.S01E{i:02}.mkv" for i in range(1, 41)]
    for f in files:
        f.write_bytes(f.name.encode())
    lib = tmp_path / "lib"
    lib.mkdir()
    entries = [(f, f"Serie (2020)/Season 01/Serie (2020) - S01E{i:02}.mkv") for i, f in enumerate(files, 1)]
    plan = build_plan(entries, lib)
    # Un movimiento falla a mitad del lote (con otros en marcha a la vez): todo vuelve atrás
    real, calls = os.rename, []

    def flaky(a, b):
        calls.append(a)
        if len(calls) == 20:
            raise PermissionError("denegado")
        return real(a, b)

    monkeypatch.setattr(renamer.os, "rename", flaky)
    with pytest.raises(RenameError, match="No se ha cambiado nada"):
        execute(plan)
    monkeypatch.setattr(renamer.os, "rename", real)
    assert sorted(p.name for p in src.iterdir()) == sorted(f.name for f in files)
    assert all(f.read_bytes() == f.name.encode() for f in files)
    assert not (lib / "Serie (2020)").exists()
    # Alguien crea un destino entre el plan y la ejecución: se detecta y no se pisa
    late = lib / "Serie (2020)" / "Season 01" / "Serie (2020) - S01E25.mkv"
    late.parent.mkdir(parents=True)
    late.write_bytes(b"ajeno")
    with pytest.raises(RenameError, match="Ya existe"):
        execute(plan)
    assert late.read_bytes() == b"ajeno" and len(list(src.iterdir())) == 40
    late.unlink()
    # Sin el intruso: los 40 en su sitio y el historial permite deshacerlo todo
    hist = History(tmp_path / "h.jsonl")
    res = execute(build_plan(entries, lib), hist)
    assert len(res.moves) == 40 and not any(src.iterdir())
    assert len(list((lib / "Serie (2020)" / "Season 01").iterdir())) == 40
    hist.undo_last()
    assert len(list(src.iterdir())) == 40


def test_progress_reports_every_file_once_with_parallel_moves(tmp_path):
    files = touch(tmp_path, *[f"v{i}.mkv" for i in range(30)])
    seen = []
    renamer._apply_moves([(f, f.with_name("n-" + f.name)) for f in files],
                         progress=lambda ev, s: seen.append((ev, s.name)))
    assert sorted(n for ev, n in seen if ev == "done") == sorted(f.name for f in files)
