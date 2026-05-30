"""
main.py
Entry point Adyton Crypt dengan Loguru, kapabilitas System Tray,
Single Instance Lock (IPC) dengan File Association Support, dan Global Exception Handler.
"""

import os
import sys
import ctypes
import traceback
from loguru import logger
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from core.paths import get_data_dir, get_asset_path
from ui.constants import APP_NAME, APP_AUMID

from ui.app import AppBrankas
from ui.styles import load_stylesheet

# =========================================================================
# KONSTANTA APLIKASI
# =========================================================================
APP_ORG = "Adyton Security"


# =========================================================================
# SETUP FUNCTIONS
# =========================================================================


def setup_logging() -> str:
    """Log ke folder proyek saat dev, ke LOCALAPPDATA saat sudah di-build."""
    log_dir = get_data_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = str(log_dir / "adyton_crypt.log")

    logger.add(
        log_path,
        rotation="10 MB",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {module}:{function} - {message}",
        enqueue=True,
    )
    return log_path


def setup_windows_aumid() -> None:
    """Set Application User Model ID (AUMID) untuk konsistensi notifikasi Windows.
    Harus dipanggil sebelum QApplication dibuat.
    """
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_AUMID)
        except Exception:
            pass


def register_dev_shortcut() -> None:
    """Daftarkan AUMID + icon ke registry agar ikon toast konsisten saat dev mode.
    No-op jika sudah di-build (frozen) atau bukan Windows.
    """
    if sys.platform != "win32" or getattr(sys, "frozen", False):
        return
    try:
        import winreg

        key_path = rf"SOFTWARE\Classes\AppUserModelId\{APP_AUMID}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
            icon_path = os.path.abspath("assets/icon_adyton.ico")
            winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, icon_path)
    except Exception:
        pass


def setup_qt_env() -> None:
    """Set environment variable Qt sebelum QApplication dibuat."""
    os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")
    os.environ["QT_FONT_DPI"] = "96"


def setup_fonts(app: QApplication) -> None:
    """Load IBM Plex Sans (semua weight yang tersedia) + fallback ke Segoe UI."""
    fonts_loaded = False

    # Load main weights (user added many variants)
    main_weights = [
        "Thin", "ExtraLight", "Light",
        "Regular", "Medium", "SemiBold", "Bold"
    ]
    for weight in main_weights:
        font_path = get_asset_path(f"assets/fonts/IBMPlexSans-{weight}.ttf")
        if os.path.exists(font_path):
            QFontDatabase.addApplicationFont(font_path)
            fonts_loaded = True

    # Also load a few Condensed variants (useful for tight labels / size text)
    condensed_weights = ["Condensed-Regular", "Condensed-Medium", "Condensed-SemiBold"]
    for weight in condensed_weights:
        font_path = get_asset_path(f"assets/fonts/IBMPlexSans_{weight}.ttf")
        if os.path.exists(font_path):
            QFontDatabase.addApplicationFont(font_path)

    font = QFont("IBM Plex Sans" if fonts_loaded else "Segoe UI")
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)


def global_exception_handler(exc_type, exc_value, exc_traceback) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.critical(
        "Uncaught exception:\n", exc_info=(exc_type, exc_value, exc_traceback)
    )

    app = QApplication.instance()
    if app:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle(f"Fatal Error - {APP_NAME}")
        msg.setText("Terjadi kesalahan sistem yang tidak terduga.")
        msg.setInformativeText(
            "Aplikasi harus ditutup. Silakan periksa file log untuk detail lebih lanjut."
        )
        tb_string = "".join(
            traceback.format_exception(exc_type, exc_value, exc_traceback)
        )
        msg.setDetailedText(
            f"Tipe Error: {exc_type.__name__}\n\nTraceback:\n{tb_string}"
        )
        msg.exec()


# =========================================================================
# IPC HANDLER
# =========================================================================


def handle_wakeup(server: QLocalServer, window: "AppBrankas") -> None:
    """Terima payload WAKEUP dari instance kedua, lalu bawa window ke depan."""
    client = server.nextPendingConnection()
    if not client.waitForReadyRead(500):
        client.disconnectFromServer()
        return
    try:
        payload = client.readAll().data().decode("utf-8")
        if payload.startswith("WAKEUP|"):
            _, path = payload.split("|", 1)
            window.showNormal()
            window.activateWindow()
            window.raise_()
            if path and os.path.exists(path):
                window.buka_file_dari_luar(path)
    except Exception as e:
        logger.error(f"Gagal parsing IPC Wakeup payload: {e}")
    finally:
        client.disconnectFromServer()


# =========================================================================
# SINGLE INSTANCE LOCK
# =========================================================================


def try_send_to_existing_instance(file_arg: str) -> bool:
    """Coba kirim WAKEUP ke instance yang sudah berjalan.
    Return True jika berhasil (instance lain aktif), False jika tidak ada.
    """
    socket = QLocalSocket()
    socket.connectToServer(APP_AUMID)
    if not socket.waitForConnected(500):
        socket.deleteLater()
        return False

    logger.info("Instance lain aktif. Mengirim sinyal WAKEUP + Path File.")
    payload = f"WAKEUP|{file_arg}".encode("utf-8")
    socket.write(payload)
    socket.waitForBytesWritten(500)
    socket.disconnectFromServer()
    return True


def create_ipc_server() -> QLocalServer | None:
    """Buat IPC server untuk single instance lock.
    Return QLocalServer jika berhasil, None jika gagal.
    """
    try:
        QLocalServer.removeServer(APP_AUMID)
    except Exception as e:
        logger.debug(f"Gagal menghapus server IPC lama (biasanya aman diabaikan): {e}")

    server = QLocalServer()
    if not server.listen(APP_AUMID):
        logger.error(f"FATAL: Gagal membuat IPC Server. {server.errorString()}")
        return None
    return server


# =========================================================================
# MAIN
# =========================================================================


def main() -> None:
    # Urutan setup ini kritis — jangan diubah
    setup_windows_aumid()  # 1. AUMID harus di-set sebelum QApplication
    register_dev_shortcut()  # 2. Register icon di registry (no-op saat build)
    setup_qt_env()  # 3. Env Qt harus di-set sebelum QApplication

    log_path = setup_logging()
    logger.info(f"Log disimpan di: {log_path}")
    sys.excepthook = global_exception_handler

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    app.setQuitOnLastWindowClosed(False)

    file_arg = (
        sys.argv[1]
        if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".adtn")
        else ""
    )

    if try_send_to_existing_instance(file_arg):
        sys.exit(0)

    ipc_server = create_ipc_server()

    logger.info(f"=== Memulai {APP_NAME} ===")

    setup_fonts(app)

    try:
        app.setStyleSheet(load_stylesheet())
    except Exception as e:
        logger.error(f"Gagal memuat stylesheet: {e}")

    window = AppBrankas()

    if ipc_server is not None:
        ipc_server.newConnection.connect(lambda: handle_wakeup(ipc_server, window))

    window.show()

    if file_arg and os.path.exists(file_arg):
        window.buka_file_dari_luar(file_arg)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
