"""Bounded background jobs for local Hub clients."""

from dataclasses import dataclass, field
from threading import Event, Lock, Thread
from time import monotonic
from uuid import uuid4


class Cancelled(Exception):
    pass


class Busy(RuntimeError):
    pass


@dataclass
class Job:
    deadline: float
    cancelled: Event = field(default_factory=Event)
    released: Event = field(default_factory=Event)
    progress: tuple = (0, 0, 0)
    result: dict | None = None
    error: str | None = None
    warning: str | None = None
    finished: bool = False

    def check(self):
        # shortcut: cancellation waits for filesystem calls to return, isolate work in a process if a hard timeout is needed.
        if self.cancelled.is_set() or monotonic() > self.deadline:
            self.cancelled.set()
            raise Cancelled

    def report(self, entries, files, size):
        self.progress = (entries, files, size)

    def status(self):
        state = "running"
        if self.finished:
            state = "cancelled" if self.cancelled.is_set() else "failed" if self.error else "done"
        elif self.cancelled.is_set():
            state = "cancelling"
        entries, files, size = self.progress
        value = {"state": state, "entries": entries, "files": files, "bytes": size}
        if self.warning:
            value["warning"] = self.warning
        if state == "done":
            value["result"] = self.result
        elif state == "failed":
            value["error"] = self.error
        return value


class Jobs:
    def __init__(self, lease_seconds=15):
        self.lease_seconds = lease_seconds
        self.lock = Lock()
        self.active = None
        self.identity = None
        self.closed = False

    def start(self, work):
        with self.lock:
            if self.closed:
                raise Busy("Сервер Hub завершает работу")
            if self.active and (not self.active.finished or
                                (self.active.result is not None and monotonic() < self.active.deadline)):
                raise Busy("Дождись завершения текущего расчёта или отмени его")
            identity = uuid4().hex
            job = Job(monotonic() + self.lease_seconds)
            self.active, self.identity = job, identity
            try:
                Thread(target=self._run, args=(job, work), daemon=True, name="hub-job").start()
            except RuntimeError:
                self.active = self.identity = None
                raise
            return identity

    def _run(self, job, work):
        try:
            result = work(job)
            job.check()
        except Cancelled:
            result = None
        except Exception as exc:
            result = None
            job.error = str(exc) or type(exc).__name__
        with self.lock:
            job.result = None if job.cancelled.is_set() else result
            job.finished = True
            has_result = job.result is not None
            remaining = job.deadline - monotonic()
        if has_result and not job.released.wait(max(0, remaining)):
            with self.lock:
                if self.active is job:
                    self.active = self.identity = None

    def poll(self, identity, *, cancel=False):
        with self.lock:
            if self.active is None or identity != self.identity:
                return None
            job = self.active
            now = monotonic()
            if cancel or now > job.deadline:
                job.cancelled.set()
                job.result = None
                job.released.set()
            elif not job.finished and not job.cancelled.is_set():
                job.deadline = now + self.lease_seconds
            status = job.status()
            if job.finished and not cancel:
                job.released.set()
                self.active = self.identity = None
            return status

    def shutdown(self):
        with self.lock:
            self.closed = True
            if self.active:
                self.active.cancelled.set()
                self.active.released.set()
                self.active = self.identity = None
