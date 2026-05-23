"""
main.py
Entry point Adyton Crypt dengan Loguru dan kapabilitas System Tray.
"""

import os
import sys
import ctypes
from loguru import logger
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont
from ui.app import AppBrankas
from ui.styles import load_stylesheet

os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")
os.environ["QT_FONT_DPI"] = "96"

local_appdata = os.getenv("LOCALAPPDATA")

if local_appdata:
    log_dir = os.path.join(local_appdata, "AdytonCrypt")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "adyton_crypt.log")
else:
    log_path = "adyton_crypt.log"

logger.add(
    log_path,
    rotation="10 MB",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {module}:{function} - {message}",
)


def main():
    myappid = "AdytonSecurity.AdytonCrypt.App.1"
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("Adyton Crypt")
    app.setOrganizationName("Adyton Security")
    app.setQuitOnLastWindowClosed(False)

    for weight in ["Regular", "Medium", "SemiBold", "Bold"]:
        QFontDatabase.addApplicationFont(f"assets/fonts/IBMPlexSans-{weight}.ttf")

    font = QFont("IBM Plex Sans")
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)

    app.setStyleSheet(load_stylesheet())

    window = AppBrankas()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
