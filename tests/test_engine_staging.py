"""Pantalla dividida: el motor solo convierte lo que está en la cola y con la tarea «convertir».
Lo pendiente de confirmar o lo que es solo para renombrar no lo toca; los ajustes de cada vídeo se conservan."""
from types import SimpleNamespace

import pytest

import tuxenc.engine as eng
from tuxenc.catalog import EncodeSettings
from tuxenc.engine import Job, QueueEngine


class _FakeRunner:
    def __init__(self, engine, job, threads):
        self.job = job

    def start(self):
        pass

    def cancel(self):
        self.job.status = "cancelled"

    def pause(self):
        pass

    def resume(self):
        pass


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setattr(eng, "_Runner", _FakeRunner)
    e = QueueEngine()
    e.max_parallel = 8
    e.output_resolver = lambda job, st: "/tmp/out.mkv"
    e.settings_provider = lambda: EncodeSettings(quality=20)
    return e


def _job(**kw):
    info = SimpleNamespace(duration=10.0)
    return Job(input="/v/a.mkv", info=info, **kw)


def test_staged_and_rename_only_never_convert(engine):
    staged = _job(staged=True)
    rename_only = _job(task_convert=False, task_rename=True)
    queued = _job()
    for j in (staged, rename_only, queued):
        engine.add(j)
    engine.start()
    assert queued.status == "preparing"
    assert staged.status == "waiting" and rename_only.status == "waiting"
    assert staged.settings is None            # no se fijan ajustes a lo que se está preparando
    assert set(engine.running) == {queued.id}


def test_queue_finishes_with_only_staged_left(engine):
    done = []
    engine.on_queue_done = lambda jobs: done.append(jobs)
    staged = _job(staged=True)
    engine.add(staged)
    engine.start()
    assert not engine.active and done        # nada que convertir: la cola acaba y lo preparado sigue ahí
    assert staged.status == "waiting"


def test_settings_snapshot_survives_stop_and_retry(engine):
    a = _job(settings=EncodeSettings(quality=30))
    b = _job(settings=EncodeSettings(quality=26))
    engine.max_parallel = 1
    engine.add(a)
    engine.add(b)
    engine.start()
    engine.stop()
    assert b.status == "waiting" and b.settings.quality == 26     # lo fijado al añadirlo se mantiene
    a.status = "failed"
    engine.retry(a.id)
    assert a.settings.quality == 30


def test_counts_and_progress_ignore_staged(engine):
    engine.add(_job(staged=True))
    q = _job(settings=EncodeSettings())
    engine.add(q)
    c = engine.counts()
    assert c["staged"] == 1 and c["waiting"] == 1
    q.status, q.progress = "done", 1.0
    assert engine.overall_progress() == 1.0
