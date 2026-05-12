"""
main.py
Entry point untuk menjalankan aplikasi Digital Locker (versi PySide6).
"""

import os
import sys
import logging
from PySide6.QtWidgets import QApplication

# FIX #4 — HiDPI harus diaktifkan via environment variable SEBELUM
# QApplication dibuat, dan tidak dikunci di balik `sys.frozen` sehingga
# juga aktif saat development, bukan hanya saat di-build dengan PyInstaller.
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")

# FIX #10 — Tambahkan logging dasar agar error dari core/vault.py
# tercatat ke file, bukan hanya tampil di UI (memudahkan debugging).
logging.basicConfig(
    filename="digital_locker.log",
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from ui.app import AppBrankas  # noqa: E402 — import setelah env vars di-set


def main():
    app = QApplication(sys.argv)
    window = AppBrankas()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
