"""remove_many: quita varios a la vez y cancela los que están en marcha."""
from tuxenc.engine import QueueEngine


class _Runner:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class _J:
    def __init__(self, i):
        self.id = i
        self.status = "waiting"


def test_remove_many():
    e = QueueEngine.__new__(QueueEngine)
    import threading
    e._lock = threading.RLock()
    e.jobs = [_J(i) for i in range(5)]
    r = _Runner()
    e.running = {2: r}
    e._schedule = lambda: None
    e.remove_many([1, 2, 4])
    assert [j.id for j in e.jobs] == [0, 3]
    assert r.cancelled
    e.remove_many([])
    assert [j.id for j in e.jobs] == [0, 3]
