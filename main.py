"""
main.py
Entry point Digital Locker dengan Loguru dan kapabilitas System Tray.
"""

import os
import sys
from loguru import logger
from PySide6.QtWidgets import QApplication

os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")

# Setup Loguru: Rotasi log otomatis jika melebihi 10MB
logger.add(
    "digital_locker.log",
    rotation="10 MB",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {module}:{function} - {message}",
)

from ui.app import AppBrankas
from ui.styles import load_stylesheet


def main():
    app = QApplication(sys.argv)

    # Mencegah aplikasi terbunuh total (exit) ketika window ditutup (X).
    # Agar bisa berjalan terus di System Tray (background).
    app.setQuitOnLastWindowClosed(False)

    # FIX PENTING: Terapkan stylesheet secara GLOBAL di sini!
    # Karena dipanggil sebelum window apapun dibuat, widget Top-Level
    # seperti QToolTip dijamin 100% bakal tunduk sama CSS kita.
    app.setStyleSheet(load_stylesheet())

    window = AppBrankas()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
