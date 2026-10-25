import pytest

from khapa_core.engine import SyncNode


class Clock:
    def __init__(self, t=1_000_000):
        self.t = t

    def __call__(self):
        return self.t


def mk(name, t0=1_000_000):
    clock = Clock(t0)
    return SyncNode(name, clock), clock


class ManualScheduler:
    """Collects scheduled callbacks so tests decide when they run."""

    def __init__(self):
        self.jobs = []

    def __call__(self, delay, fn):
        job = _Job(fn)
        self.jobs.append(job)
        return job

    def flush(self):
        jobs, self.jobs = self.jobs, []
        for j in jobs:
            if not j.cancelled:
                j.fn()


class _Job:
    def __init__(self, fn):
        self.fn, self.cancelled = fn, False

    def cancel(self):
        self.cancelled = True


@pytest.fixture
def sched():
    return ManualScheduler()
