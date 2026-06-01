"""Qt worker tests separated from core vault tests.

The module is skipped at import time when PySide6 is unavailable, so running
`pytest` in a headless/core-only environment remains clean.
"""

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QThread

from core.vault import buka_brankas, kunci_brankas, VaultStatus
from core.worker import CryptoWorker

PASSWORD_BENAR = "P@ssw0rd!Kuat123"


def _lock_sample_folder(sample_folder: str) -> str:
    base_dir = os.path.dirname(sample_folder)
    locked_path = os.path.join(base_dir, f"{os.path.basename(sample_folder)}.adtn")
    status, msg = kunci_brankas([sample_folder], locked_path, PASSWORD_BENAR)
    assert status == VaultStatus.SUCCESS, msg
    return locked_path


@pytest.mark.qt
def test_cancel_during_buka_brankas_worker_does_not_crash(sample_folder):
    locked_path = _lock_sample_folder(sample_folder)

    worker = CryptoWorker(buka_brankas, locked_path, PASSWORD_BENAR)
    worker.start()
    QThread.msleep(5)
    worker.cancel()
    worker.wait(3000)

    assert not worker.isRunning()


@pytest.mark.qt
def test_no_temp_dir_left_after_worker_cancel(sample_folder, tmp_dir):
    locked_path = _lock_sample_folder(sample_folder)

    worker = CryptoWorker(buka_brankas, locked_path, PASSWORD_BENAR)
    worker.start()
    QThread.msleep(10)
    worker.cancel()
    worker.wait(3000)

    leaked = list(Path(tmp_dir).glob("._dec_*"))
    assert not leaked, f"Temporary files bocor setelah cancel: {leaked}"
