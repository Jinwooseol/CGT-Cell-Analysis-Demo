from PySide6.QtCore import QObject, QRunnable, Signal


class WorkerSignals(QObject):
    log = Signal(str)
    progress = Signal(int)
    done = Signal(dict)
    error = Signal(str)
    cancel = Signal()


class BaseWorker(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = WorkerSignals()
        self._canceled = False

    def request_cancel(self):
        self._canceled = True

    def check_abort(self):
        """Call on each processing-loop iteration to honor a cancellation request."""
        if self._canceled:
            raise RuntimeError("Worker canceled")
