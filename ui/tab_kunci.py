"""
Modul: tab_kunci.py
Deskripsi: Controller utama untuk Tab "Kunci Folder".
           Memancarkan sinyal ke app.py untuk UWP Toast (Winotify).
"""

import os
import time
from loguru import logger
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QDialog, QFrame
from PySide6.QtCore import Qt, Signal

from core.vault import kunci_brankas, VaultStatus
from core.worker import CryptoWorker
from .widgets import AnimatedNotifBar
from .utils import apply_shadow
from .buttons import BigActionBtn
from .dialogs import ModernMessageBox
from .constants import APP_NAME
from .utils import get_eta_string, format_progress_label, apply_cancelling_state, start_crypto_worker

# --- IMPORT SMART COMPONENTS (Sesuai dengan nama asli file lu!) ---
from .components.drop_zone_lock import DropZoneLock
from .components.password_panel_lock import PasswordPanelLock
from .components.options_panel import OptionsPanel


class TabKunci(QWidget):
    # SINYAL NATIVE untuk ditangkap app.py
    system_notification = Signal(str, str)
    worker_started = Signal(object)  # emits the CryptoWorker instance

    def __init__(self):
        super().__init__()
        self.worker: CryptoWorker | None = None
        self._is_password_valid = False
        self._has_files = False
        self._crypto_start_time: float | None = None

        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(20)

        # Inisialisasi sesuai nama Class asli lu
        self.drop_zone = DropZoneLock()
        self.options_panel = OptionsPanel()
        self.password_panel = PasswordPanelLock()

        h_cols = QHBoxLayout()
        h_cols.setSpacing(20)

        v_left = QVBoxLayout()
        v_left.addWidget(self.drop_zone, 1)
        v_left.addWidget(self.options_panel)

        h_cols.addLayout(v_left, 1)
        h_cols.addWidget(self.password_panel, 1)
        main_layout.addLayout(h_cols)

        self.btn_aksi = BigActionBtn(
            "KUNCI SEKARANG", "Proses penguncian akan dimulai", icon_name="mdi6.lock"
        )
        self.btn_aksi.setAccessibleName("Tombol Kunci Brankas")
        self.btn_aksi.setEnabled(False)
        self.btn_aksi.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        apply_shadow(self.btn_aksi, blur_radius=24, y_offset=5, opacity=85)  # Option B: sedikit lebih berani

        main_layout.addWidget(self.btn_aksi)
        self.notif = AnimatedNotifBar(self)

    def _connect_signals(self):
        self.btn_aksi.clicked.connect(self._proses)
        self.password_panel.attach_return_event(self._proses)
        self.drop_zone.paths_changed.connect(self._on_paths_changed)
        self.drop_zone.warning_emitted.connect(
            lambda msg: self.notif.show_msg("warn", msg, 4000)
        )
        self.password_panel.valid_state_changed.connect(self._on_password_valid_changed)
        self.options_panel.hapus_asli_changed.connect(self._update_btn_label)

    def _on_paths_changed(self, paths: list):
        self._has_files = len(paths) > 0
        self._validate_state()

    def _on_password_valid_changed(self, is_valid: bool):
        self._is_password_valid = is_valid
        self._validate_state()

    def _validate_state(self):
        if self.worker is not None:
            return
        enabled = self._has_files and self._is_password_valid
        self.btn_aksi.setEnabled(enabled)
        self.btn_aksi.setFocusPolicy(
            Qt.FocusPolicy.StrongFocus if enabled else Qt.FocusPolicy.NoFocus
        )

    def _update_btn_label(self, is_hapus_asli: bool):
        if is_hapus_asli:
            self.btn_aksi.setTextLabels(
                "ENKRIPSI & HAPUS ASLI", "File asli akan dihapus setelah dikunci"
            )
        else:
            self.btn_aksi.setTextLabels(
                "KUNCI SEKARANG", "Proses penguncian akan dimulai"
            )

    def _update_progress(self, val):
        if self.worker and not self.worker.is_cancelled():
            eta_str = get_eta_string(self._crypto_start_time, val)
            title, subtitle = format_progress_label(val, "kunci", eta_str)
            self.btn_aksi.setTextLabels(title, subtitle)


    def _proses(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self._crypto_start_time = None
            apply_cancelling_state(self.btn_aksi)
            return

        paths = self.drop_zone.get_paths()
        pw = self.password_panel.get_password()
        hapus_asli = self.options_panel.is_hapus_asli()
        secure_wipe = self.options_panel.is_secure_wipe()

        if hapus_asli:
            dialog = ModernMessageBox(
                title="Konfirmasi Hapus Asli",
                message="File atau folder asli akan DIHAPUS PERMANEN setelah berhasil dikunci.\n\nApakah Anda yakin ingin melanjutkan?",
                parent=self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

        default_name = os.path.basename(paths[0]) or "Brankas_Rahasia"
        self.btn_aksi.clearFocus()

        path_simpan, _ = QFileDialog.getSaveFileName(
            self, "Simpan Brankas", f"{default_name}.adtn", "File Terkunci (*.adtn)"
        )
        if not path_simpan:
            return

        self._crypto_start_time = time.time()
        self._set_busy(True)
        self.worker = CryptoWorker(
            kunci_brankas,
            list(paths),
            path_simpan,
            pw,
            hapus_asli=hapus_asli,
            secure_wipe=secure_wipe,
            parent=self,
        )

        self.password_panel.reset_fields()
        self._is_password_valid = False

        start_crypto_worker(self.worker, self._update_progress, self._on_selesai)
        self.worker_started.emit(self.worker)

    def _set_busy(self, busy: bool):
        self.drop_zone.set_busy(busy)
        self.options_panel.set_busy(busy)
        self.password_panel.setEnabled(not busy)

        if busy:
            self.btn_aksi.setTextLabels(
                "MENGUNCI BRANKAS...", "Harap tunggu, proses sedang berjalan"
            )
            self.btn_aksi.setEnabled(True)
            self.btn_aksi.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        else:
            self._update_btn_label(self.options_panel.is_hapus_asli())
            self._validate_state()

    def _on_selesai(self, result):
        self.worker = None
        status, msg = result

        if status == VaultStatus.SUCCESS:
            self.drop_zone.clear_paths()
            self.options_panel.reset_options()

        self._set_busy(False)
        self._crypto_start_time = None

        if status == VaultStatus.SUCCESS:
            logger.info(f"Enkripsi sukses: {msg}")
            self.notif.show_msg("ok", f" {msg}", 6000)

            # PANCARKAN SINYAL KE APP.PY UNTUK WINOTIFY
            self.system_notification.emit(
                APP_NAME, "Brankas dikunci dengan aman."
            )

        elif status == VaultStatus.CANCELLED:
            logger.info("Enkripsi dibatalkan oleh pengguna.")
            self.notif.show_msg("warn", "Proses penguncian dibatalkan.", 4000)
        else:
            logger.error(f"Gagal mengunci: {msg}")
            self.notif.show_msg("err", f" {msg}", 6000)
