"""
main.py
Entry point Adyton Crypt dengan Loguru, kapabilitas System Tray,
Single Instance Lock (IPC) dengan File Association Support, dan Global Exception Handler.
"""

import argparse
import contextlib
import ctypes
import os
import sys
import traceback

from loguru import logger
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from core.paths import get_asset_path, get_data_dir
from ui.app import AppBrankas
from ui.constants import APP_AUMID, APP_NAME
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
        with contextlib.suppress(Exception):
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_AUMID)


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
    except Exception:  # noqa: S110
        pass


def setup_qt_env() -> None:
    """Set environment variable Qt sebelum QApplication dibuat."""
    os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")
    os.environ["QT_FONT_DPI"] = "96"


def setup_fonts(app: QApplication) -> None:
    """Load Plus Jakarta Sans (UI) + JetBrains Mono (kode/payload) sesuai design system.

    Plus Jakarta Sans dipakai untuk seluruh UI; JetBrains Mono khusus
    token/kode/payload. Fallback ke Segoe UI bila file font tidak tersedia.
    """
    fonts_loaded = False

    # Plus Jakarta Sans — keluarga UI utama (400/500/600/700/800)
    jakarta_weights = ["Regular", "Medium", "SemiBold", "Bold", "ExtraBold"]
    for weight in jakarta_weights:
        font_path = get_asset_path(f"assets/fonts/PlusJakartaSans-{weight}.ttf")
        if os.path.exists(font_path):
            QFontDatabase.addApplicationFont(font_path)
            fonts_loaded = True

    # JetBrains Mono — khusus payload/token/kode
    for weight in ["Regular", "Medium"]:
        font_path = get_asset_path(f"assets/fonts/JetBrainsMono-{weight}.ttf")
        if os.path.exists(font_path):
            QFontDatabase.addApplicationFont(font_path)

    font = QFont("Plus Jakarta Sans" if fonts_loaded else "Segoe UI")
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)


def global_exception_handler(exc_type, exc_value, exc_traceback) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.critical("Uncaught exception:\n", exc_info=(exc_type, exc_value, exc_traceback))

    app = QApplication.instance()
    if app:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle(f"Unexpected Error — {APP_NAME}")
        msg.setText("Something went wrong unexpectedly.")
        msg.setInformativeText("Adyton needs to close. Check the log file for details.")
        tb_string = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        msg.setDetailedText(f"Error type: {exc_type.__name__}\n\nTraceback:\n{tb_string}")
        msg.exec()


# =========================================================================
# IPC HANDLER
# =========================================================================


def _bring_to_front(window: "AppBrankas") -> None:
    window.showNormal()
    window.activateWindow()
    window.raise_()


def handle_wakeup(server: QLocalServer, window: "AppBrankas") -> None:
    """Terima payload dari instance kedua dan tangani.

    Dua jenis pesan:
      WAKEUP|<path>            → asosiasi file (double-click .adtn) → buka decrypt
      QUICK|<mode>|<p1>|<p2>…  → context menu (hybrid) → encrypt/decrypt di app ini
    """
    client = server.nextPendingConnection()
    if client is None:
        return
    # Data bisa sudah ter-buffer sebelum slot ini jalan (umum di koneksi pertama);
    # hanya tunggu bila belum ada apa pun, agar tidak melewatkan payload.
    if client.bytesAvailable() == 0 and not client.waitForReadyRead(1000):
        client.disconnectFromServer()
        return
    try:
        payload = client.readAll().data().decode("utf-8")
        if payload.startswith("QUICK|"):
            parts = payload.split("|")
            mode = parts[1] if len(parts) > 1 else ""
            paths = [p for p in parts[2:] if p and os.path.exists(p)]
            _bring_to_front(window)
            if mode == "encrypt" and paths:
                window.kunci_file_dari_luar(paths)
            elif mode == "decrypt" and paths:
                window.buka_file_dari_luar(paths[0])
        elif payload.startswith("WAKEUP|"):
            parts = payload.split("|", 1)
            path = parts[1] if len(parts) > 1 else ""
            _bring_to_front(window)
            if path and os.path.exists(path):
                window.buka_file_dari_luar(path)
    except Exception as e:
        logger.error(f"Gagal parsing IPC payload: {e}")
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
    payload = f"WAKEUP|{file_arg}".encode()
    socket.write(payload)
    socket.waitForBytesWritten(500)
    socket.disconnectFromServer()
    return True


def try_forward_quick_action(mode: str, paths: list[str]) -> bool:
    """Teruskan aksi context menu ke instance yang sudah berjalan (hybrid).

    Return True jika app aktif menerima (dialog mini tak perlu dibuka),
    False jika tidak ada instance → fallback ke dialog mini.
    """
    socket = QLocalSocket()
    socket.connectToServer(APP_AUMID)
    if not socket.waitForConnected(500):
        socket.deleteLater()
        return False

    payload = ("QUICK|" + mode + "|" + "|".join(paths)).encode("utf-8")
    socket.write(payload)
    socket.waitForBytesWritten(1000)
    socket.flush()
    # Tunggu server selesai membaca lalu menutup koneksi — mencegah race di mana
    # proses ini keluar dan merobohkan pipe sebelum server sempat membaca.
    socket.waitForDisconnected(2000)
    socket.deleteLater()
    logger.info(f"Quick action diteruskan ke instance aktif: {mode} ({len(paths)} path).")
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


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse argumen CLI.

    Flag quick-action (dipakai oleh context menu Windows) berdiri sendiri;
    argumen posisional `file` mempertahankan perilaku asosiasi file lama
    (double-click .adtn membuka full app).
    """
    parser = argparse.ArgumentParser(prog="adyton", add_help=False)
    parser.add_argument("--encrypt", nargs="+", metavar="PATH")
    parser.add_argument("--decrypt", metavar="VAULT")
    parser.add_argument("--shred", nargs="+", metavar="PATH")
    parser.add_argument("file", nargs="?", default=None)
    args, _ = parser.parse_known_args(argv[1:])
    return args


def apply_theme(app: QApplication) -> None:
    """Font + stylesheet design-system. Dibutuhkan SEMUA mode."""
    setup_fonts(app)
    try:
        app.setStyleSheet(load_stylesheet())
    except Exception as e:
        logger.error(f"Gagal memuat stylesheet: {e}")


def run_quick_action(app: QApplication, args: argparse.Namespace) -> int:
    """Mode transient untuk context menu — satu window, tutup = proses keluar.

    Sengaja melewati single-instance lock + tray: tiap aksi berdiri sendiri.
    """
    from ui.quick_action import QuickActionWindow, QuickMode

    app.setQuitOnLastWindowClosed(True)

    if args.encrypt:
        mode, paths, forward_mode = QuickMode.ENCRYPT, args.encrypt, "encrypt"
    elif args.decrypt:
        mode, paths, forward_mode = QuickMode.DECRYPT, [args.decrypt], "decrypt"
    else:
        # Shred tak punya padanan di full app → selalu dialog mini, tak diteruskan.
        mode, paths, forward_mode = QuickMode.SHRED, args.shred, None

    paths = [p for p in paths if os.path.exists(p)]
    if not paths:
        QMessageBox.warning(None, APP_NAME, "File atau folder tidak ditemukan.")
        return 1

    # Vault tidak boleh dikunci ulang (mencegah nested lock).
    if mode is QuickMode.ENCRYPT:
        non_vault = [p for p in paths if not p.lower().endswith(".adtn")]
        if not non_vault:
            QMessageBox.warning(
                None,
                APP_NAME,
                "File .adtn sudah berupa vault terkunci — tidak bisa dikunci lagi.",
            )
            return 1
        paths = non_vault

    # HYBRID: kalau app sudah berjalan di tray, teruskan ke instance itu (instan,
    # tanpa cold-start). Kalau tidak ada → buka dialog mini yang ringan.
    if forward_mode is not None and try_forward_quick_action(forward_mode, paths):
        return 0

    logger.info(f"=== Quick action (dialog): {mode.name} ({len(paths)} path) ===")
    window = QuickActionWindow(mode, paths)
    window.show()
    return app.exec()


def run_full_app(app: QApplication, args: argparse.Namespace) -> int:
    """Mode default — tray, IPC, single-instance lock (perilaku lama)."""
    app.setQuitOnLastWindowClosed(False)

    file_arg = args.file if (args.file and args.file.lower().endswith(".adtn")) else ""

    if try_send_to_existing_instance(file_arg):
        return 0

    ipc_server = create_ipc_server()

    logger.info(f"=== Memulai {APP_NAME} ===")

    window = AppBrankas()

    if ipc_server is not None:
        ipc_server.newConnection.connect(lambda: handle_wakeup(ipc_server, window))

    window.show()

    if file_arg and os.path.exists(file_arg):
        window.buka_file_dari_luar(file_arg)

    return app.exec()


def main() -> None:
    # Urutan setup ini kritis — jangan diubah
    setup_windows_aumid()  # 1. AUMID harus di-set sebelum QApplication
    register_dev_shortcut()  # 2. Register icon di registry (no-op saat build)
    setup_qt_env()  # 3. Env Qt harus di-set sebelum QApplication

    log_path = setup_logging()
    logger.info(f"Log disimpan di: {log_path}")
    sys.excepthook = global_exception_handler

    args = parse_args(sys.argv)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    apply_theme(app)

    is_quick = bool(args.encrypt or args.decrypt or args.shred)
    sys.exit(run_quick_action(app, args) if is_quick else run_full_app(app, args))


if __name__ == "__main__":
    main()
