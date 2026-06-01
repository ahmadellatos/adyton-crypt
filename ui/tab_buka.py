"""
Modul: tab_buka.py
Deskripsi: Controller utama untuk Tab "Buka Brankas".
           Memancarkan sinyal ke app.py untuk UWP Toast (Winotify).
"""

import os
from loguru import logger
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QDialog
from PySide6.QtCore import Qt, Signal

from core.vault import buka_brankas, VaultStatus
from core.worker import CryptoWorker
from .widgets import AnimatedNotifBar
from .utils import apply_shadow
from .buttons import BigActionBtn
from .dialogs import ModernMessageBox
from .constants import APP_NAME
from .utils import (
    ProgressETA,
    format_progress_label,
    format_user_error,
    apply_cancelling_state,
    start_crypto_worker,
)

# --- IMPORT SMART COMPONENTS (Sesuai dengan nama asli file lu!) ---
from .components.drop_zone_open import DropZoneOpen
from .components.password_panel_open import PasswordPanelOpen


class TabBuka(QWidget):
    # SINYAL NATIVE untuk ditangkap app.py
    system_notification = Signal(str, str)
    worker_started = Signal(object)  # emits the CryptoWorker instance

    def __init__(self):
        super().__init__()
        self.worker: CryptoWorker | None = None
        self._konfirmasi_timpa = False
        self._cached_pw = None
        self._has_file = False
        self._has_password = False
        self._progress_eta = ProgressETA()

        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(
            22
        )  # Sedikit lebih lapang untuk harmoni visual dua kolom

        # Inisialisasi sesuai nama Class asli lu
        self.drop_zone = DropZoneOpen()
        self.password_panel = PasswordPanelOpen()

        h_container = QHBoxLayout()
        h_container.setSpacing(28)  # More generous separation between columns
        h_container.addWidget(self.drop_zone, 1)
        h_container.addWidget(self.password_panel, 1)
        main_layout.addLayout(h_container)

        self.btn_aksi = BigActionBtn(
            "BUKA BRANKAS",
            "Masukkan password untuk membuka",
            icon_name="mdi6.lock-open-variant",
        )
        self.btn_aksi.setAccessibleName("Tombol Buka Brankas")
        self.btn_aksi.setEnabled(False)
        self.btn_aksi.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        apply_shadow(
            self.btn_aksi, blur_radius=24, y_offset=5, opacity=85
        )  # Option B: sedikit lebih berani

        main_layout.addWidget(self.btn_aksi)
        self.notif = AnimatedNotifBar(self)

    def _connect_signals(self):
        self.btn_aksi.clicked.connect(self._proses)
        self.password_panel.attach_return_event(self._proses)
        self.drop_zone.file_changed.connect(self._on_file_changed)
        self.password_panel.valid_state_changed.connect(self._on_password_valid_changed)

    def _on_file_changed(self, path: str):
        self._has_file = bool(path)
        self._reset_timpa()
        self._validate_state()

    def _on_password_valid_changed(self, is_valid: bool):
        self.notif.hide_msg()
        self._has_password = is_valid
        self._validate_state()

    def _validate_state(self):
        if self.worker is not None:
            return
        if not self._konfirmasi_timpa:
            enabled = self._has_file and self._has_password
            self.btn_aksi.setEnabled(enabled)
            self.btn_aksi.setFocusPolicy(
                Qt.FocusPolicy.StrongFocus if enabled else Qt.FocusPolicy.NoFocus
            )

    def _reset_timpa(self):
        self._konfirmasi_timpa = False
        self.btn_aksi.setTextLabels(
            "BUKA BRANKAS", "Masukkan password untuk membuka kunci"
        )

    def _proses(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self._progress_eta.reset()
            apply_cancelling_state(self.btn_aksi)
            return

        force = self._konfirmasi_timpa
        path_file = self.drop_zone.get_file()

        if force and self._cached_pw:
            pw = self._cached_pw
        else:
            pw = self.password_panel.get_password()
            self._cached_pw = pw

        if force:
            self._reset_timpa()

        if not path_file or not pw:
            return

        self._progress_eta.reset()
        self._set_busy(True)
        self.worker = CryptoWorker(buka_brankas, path_file, pw, force, parent=self)
        self.password_panel.reset_field()

        start_crypto_worker(self.worker, self._update_progress, self._on_selesai)
        self.worker_started.emit(self.worker)

    def _update_progress(self, val):
        if self.worker and not self.worker.is_cancelled():
            eta_str = self._progress_eta.update(val)
            title, subtitle = format_progress_label(val, "buka", eta_str)
            self.btn_aksi.setTextLabels(title, subtitle)

    def _set_busy(self, busy: bool):
        self.drop_zone.set_busy(busy)
        self.password_panel.setEnabled(not busy)

        if busy:
            self.btn_aksi.setTextLabels(
                "MEMBUKA BRANKAS...", "Mempersiapkan dekripsi..."
            )
            self.btn_aksi.setEnabled(True)
            self.btn_aksi.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        else:
            self.btn_aksi.setTextLabels(
                "BUKA BRANKAS", "Masukkan password untuk membuka"
            )
            self._validate_state()
            self._progress_eta.reset()

    def _on_selesai(self, result):
        self.worker = None
        status, msg = result

        self._set_busy(False)
        self._progress_eta.reset()

        if status != VaultStatus.OVERWRITE_NEEDED:
            self._cached_pw = None

        if status == VaultStatus.SUCCESS:
            self.drop_zone.reset_zone()
            logger.info(f"Dekripsi sukses: {msg}")
            self.notif.show_msg(
                "ok", f"Folder/File '{msg}' berhasil dikembalikan!", 6000
            )

            # PANCARKAN SINYAL KE APP.PY UNTUK WINOTIFY
            self.system_notification.emit(APP_NAME, f"Brankas '{msg}' berhasil dibuka.")

        elif status == VaultStatus.CANCELLED:
            logger.info("Dekripsi dibatalkan pengguna.")
            self.notif.show_msg("warn", "Dekripsi dibatalkan pengguna.", 4000)

        elif status == VaultStatus.WRONG_PASSWORD:
            logger.warning("Dekripsi gagal: Password salah.")
            self.notif.show_msg("err", format_user_error(status, msg, "buka"), 8000)

        elif status == VaultStatus.OVERWRITE_NEEDED:
            dialog = ModernMessageBox(
                title="Konfirmasi Timpa File",
                message=(
                    f"Folder/file bernama '{msg}' sudah ada di lokasi tujuan.\n\n"
                    "Adyton akan mengekstrak ke lokasi sementara terlebih dahulu, lalu mengganti data lama hanya setelah proses buka brankas sukses.\n\n"
                    "Lanjutkan menimpa data lama?"
                ),
                icon_name="mdi6.alert-decagram",
                icon_color="#E74C3C",
                parent=self,
            )
            dialog.btn_yes.setText("Timpa Data")

            if dialog.exec() == QDialog.DialogCode.Accepted:
                self._konfirmasi_timpa = True
                self._proses()
            else:
                self._cached_pw = None
                self._reset_timpa()
                self._validate_state()
                logger.info("Dekripsi dibatalkan: User menolak overwrite file asli.")
        else:
            logger.error(f"Dekripsi gagal: {msg}")
            self.notif.show_msg("err", format_user_error(status, msg, "buka"), 8000)

    def auto_load_file(self, path: str) -> None:
        self.drop_zone.load_file(path)
