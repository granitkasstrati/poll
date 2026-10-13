"""Run slow work (network fetches, screening, Claude streaming) off the UI thread."""

from __future__ import annotations

import threading
import traceback
from typing import Any, Callable

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal


class WorkerSignals(QObject):
    result = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(object)  # free-form payload: (i, n, label), a text chunk, …
    finished = pyqtSignal()


class Worker(QRunnable):
    """Call fn(*args, progress=emit, cancel=event, **kwargs) on the global thread pool.

    `fn` receives `progress` (a callable that emits the progress signal) and
    `cancel` (a threading.Event set by .cancel()) as keyword arguments.
    """

    def __init__(self, fn: Callable[..., Any], *args, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = WorkerSignals()
        self.cancel_event = threading.Event()
        self.setAutoDelete(True)

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            out = self.fn(*self.args, progress=self.signals.progress.emit, cancel=self.cancel_event, **self.kwargs)
        except Exception as exc:  # surface every failure to the UI instead of dying silently
            msg = f"{exc.__class__.__name__}: {exc}"
            traceback.print_exc()
            try:
                self.signals.error.emit(msg)
            except RuntimeError:
                pass  # receiver already deleted (window closed)
        else:
            try:
                self.signals.result.emit(out)
            except RuntimeError:
                pass
        finally:
            try:
                self.signals.finished.emit()
            except RuntimeError:
                pass


_active: set[Worker] = set()  # keep Python wrappers alive until the job finishes


def start(worker: Worker) -> Worker:
    _active.add(worker)
    worker.signals.finished.connect(lambda: _active.discard(worker))
    QThreadPool.globalInstance().start(worker)
    return worker
