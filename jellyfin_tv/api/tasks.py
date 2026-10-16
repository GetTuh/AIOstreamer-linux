import logging
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal, Slot

log = logging.getLogger("jellyfin_tv.tasks")


class TaskRunner(QObject):
    _done = Signal(object, object)

    def __init__(self, workers=4):
        super().__init__()
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="jftv")
        self._done.connect(self._deliver)

    def run(self, fn, on_done=None, on_error=None):
        def job():
            try:
                result = fn()
            except Exception as exc:
                log.warning("task failed: %s", exc, exc_info=log.isEnabledFor(logging.DEBUG))
                self._done.emit(on_error, exc)
                return
            self._done.emit(on_done, result)

        self._pool.submit(job)

    @Slot(object, object)
    def _deliver(self, callback, value):
        if callback is None:
            return
        try:
            callback(value)
        except RuntimeError as exc:
            log.debug("callback target gone: %s", exc)

    def shutdown(self):
        self._pool.shutdown(wait=False, cancel_futures=True)
