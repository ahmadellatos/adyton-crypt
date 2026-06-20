"""
core/worker.py
Threading worker untuk operasi kriptografi (enkripsi/dekripsi).
Dipisah dari ui/widgets.py karena ini business logic, bukan UI component.
"""

import inspect

from loguru import logger
from PySide6.QtCore import QThread, Signal

from core.vault import VaultStatus


class CryptoWorker(QThread):
    progress = Signal(float)
    finished = Signal(tuple)

    def __init__(self, func, *args, parent=None, **kwargs):
        super().__init__(parent)
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def is_cancelled(self) -> bool:
        return self._is_cancelled

    def run(self):
        try:
            sig = inspect.signature(self.func)
            if "is_cancelled" in sig.parameters:
                self.kwargs["is_cancelled"] = lambda: self._is_cancelled

            # Hanya inject progress_cb bila fungsi target menerimanya. Operasi cepat
            # (mis. ganti password) tidak punya parameter ini.
            if "progress_cb" in sig.parameters:
                self.kwargs["progress_cb"] = lambda val: self.progress.emit(val)

            result = self.func(*self.args, **self.kwargs)
            self.finished.emit(result if isinstance(result, tuple) else (result,))

        except Exception as e:
            logger.exception("CryptoWorker gagal menjalankan operasi")
            self.finished.emit((VaultStatus.ERROR, str(e)))
