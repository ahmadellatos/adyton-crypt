"""
main.py
Entry point Adyton Crypt dengan Loguru, kapabilitas System Tray,
Single Instance Lock (IPC) dengan File Association Support, dan Global Exception Handler.
"""

import os
import sys
import ctypes
from loguru import logger
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtNetwork import QLocalServer, QLocalSocket

# =========================================================================
# FIX CRITICAL: Paksa CWD selalu berada di root folder aplikasi
# Ini menyelesaikan masalah aset pecah/kosong saat double click file .adtn
# =========================================================================
app_root = os.path.dirname(os.path.abspath(__file__))
os.chdir(app_root)

from ui.app import AppBrankas
from ui.styles import load_stylesheet

os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")
os.environ["QT_FONT_DPI"] = "96"


def setup_logging():
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
        enqueue=True,
    )
    return log_path


def global_exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical(
        "Uncaught exception:\n", exc_info=(exc_type, exc_value, exc_traceback)
    )


def main():
    log_path = setup_logging()
    sys.excepthook = global_exception_handler

    myappid = "AdytonSecurity.AdytonCrypt.App.1"
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("Adyton Crypt")
    app.setOrganizationName("Adyton Security")
    app.setQuitOnLastWindowClosed(False)

    # Ambil argument file jika dibuka dari luar
    file_arg = (
        sys.argv[1]
        if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".adtn")
        else ""
    )

    # =========================================================================
    # SINGLE INSTANCE LOCK WITH PAYLOAD (ROBUST WINDOWS IPC)
    # =========================================================================
    socket = QLocalSocket()
    socket.connectToServer(myappid)

    if socket.waitForConnected(500):
        # 1. Jika connect berhasil, berarti instance utama SEHAT dan SEDANG JALAN.
        logger.info("Instance lain aktif. Mengirim sinyal WAKEUP + Path File.")
        payload = f"WAKEUP|{file_arg}".encode("utf-8")
        socket.write(payload)
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        sys.exit(0)
    else:
        # 2. Jika connect gagal (misal server belum ada, ATAU sisa sampah aplikasi crash)
        socket.deleteLater()

        # Coba bersihkan socket lama yang mungkin nyangkut (Abaikan jika gagal karena permission)
        try:
            QLocalServer.removeServer(myappid)
        except Exception as e:
            logger.debug(
                f"Gagal menghapus server IPC lama (biasanya aman diabaikan): {e}"
            )

        # 3. Deklarasikan diri sebagai Instance Pertama (Server)
        single_server = QLocalServer()
        if not single_server.listen(myappid):
            logger.error(
                f"FATAL: Gagal membuat IPC Server. {single_server.errorString()}"
            )
            # Kalau di titik ini gagal listen, biarkan aplikasi tetap jalan tapi tanpa fitur IPC.
    # =========================================================================

    logger.info("=== Memulai Adyton Crypt ===")

    # Load Fonts
    fonts_loaded = False
    for weight in ["Regular", "Medium", "SemiBold", "Bold"]:
        font_path = f"assets/fonts/IBMPlexSans-{weight}.ttf"
        if os.path.exists(font_path):
            QFontDatabase.addApplicationFont(font_path)
            fonts_loaded = True

    if fonts_loaded:
        font = QFont("IBM Plex Sans")
    else:
        font = QFont("Segoe UI")

    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)

    try:
        app.setStyleSheet(load_stylesheet())
    except Exception as e:
        logger.error(f"Gagal memuat stylesheet: {e}")

    window = AppBrankas()

    # =========================================================================
    # LISTENER SINGLE INSTANCE (Menerima kiriman file saat aplikasi standby)
    # =========================================================================
    def handle_wakeup():
        client = single_server.nextPendingConnection()
        if client.waitForReadyRead(500):
            try:
                data_bytes = client.readAll().data()
                payload = data_bytes.decode("utf-8")
                if payload.startswith("WAKEUP|"):
                    _, path = payload.split("|", 1)

                    window.showNormal()
                    window.activateWindow()
                    window.raise_()

                    # Jika ada kiriman file adtn baru, load langsung!
                    if path and os.path.exists(path):
                        window.buka_file_dari_luar(path)
            except Exception as e:
                logger.error(f"Gagal parsing IPC Wakeup payload: {e}")
        client.disconnectFromServer()

    single_server.newConnection.connect(handle_wakeup)

    window.show()

    # Jika aplikasi pertama kali dibuka langsung membawa file .adtn
    if file_arg and os.path.exists(file_arg):
        window.buka_file_dari_luar(file_arg)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
