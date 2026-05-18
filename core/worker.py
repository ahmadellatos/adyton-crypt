"""
core/worker.py
Threading worker untuk operasi kriptografi (enkripsi/dekripsi).
Dipisah dari ui/widgets.py karena ini business logic, bukan UI component.
"""

import inspect
from PySide6.QtCore import QThread, Signal

from core.vault import VaultStatus


class CryptoWorker(QThread):
    progress = Signal(float)
    finished = Signal(tuple)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            sig = inspect.signature(self.func)
            if "is_cancelled" in sig.parameters:
                self.kwargs["is_cancelled"] = lambda: self._is_cancelled

            self.kwargs["progress_cb"] = lambda val: self.progress.emit(val)

            result = self.func(*self.args, **self.kwargs)
            self.finished.emit(result if isinstance(result, tuple) else (result,))

        except Exception as e:
            self.finished.emit((VaultStatus.ERROR, str(e)))
