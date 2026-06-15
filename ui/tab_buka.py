"""
Modul: tab_buka.py
Deskripsi: Controller utama untuk Tab "Buka Brankas".
           Memancarkan sinyal ke app.py untuk UWP Toast (Winotify).
"""

import os

from loguru import logger
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QWidget

from core.vault import VaultStatus, buka_brankas
from core.worker import CryptoWorker

from .buttons import BigActionBtn

# --- IMPORT SMART COMPONENTS (Sesuai dengan nama asli file lu!) ---
from .components.drop_zone_open import DropZoneOpen
from .components.password_panel_open import PasswordPanelOpen
from .constants import APP_NAME
from .dialogs import ModernMessageBox
from .styles import CLR_DANGER
from .utils import (
    ProgressETA,
    apply_cancelling_state,
    apply_shadow,
    format_file_size,
    format_progress_label,
    format_user_error,
    progress_stage_label,
    start_crypto_worker,
)
from .widgets import AnimatedNotifBar


class TabBuka(QWidget):
    # SINYAL NATIVE untuk ditangkap app.py
    system_notification = Signal(str, str)
    worker_started = Signal(object)  # emits the CryptoWorker instance
    status_changed = Signal(str, str, str)  # title, subtitle, state

    def __init__(self):
        super().__init__()
        self.worker: CryptoWorker | None = None
        self._konfirmasi_timpa = False
        self._cached_pw = None
        self._has_file = False
        self._has_password = False
        self._progress_eta = ProgressETA()
        self._external_busy = False

        self._build_ui()
        self._connect_signals()
        self.status_changed.emit("AES-256 • GCM", "Local encryption active", "idle")

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(22)  # Sedikit lebih lapang untuk harmoni visual dua kolom

        # Inisialisasi sesuai nama Class asli lu
        self.drop_zone = DropZoneOpen()
        self.password_panel = PasswordPanelOpen()

        h_container = QHBoxLayout()
        h_container.setSpacing(28)  # More generous separation between columns
        h_container.addWidget(self.drop_zone, 1)
        h_container.addWidget(self.password_panel, 1)
        main_layout.addLayout(h_container)

        self.btn_aksi = BigActionBtn(
            "Open Vault",
            "Enter the password to open",
            icon_name="mdi6.lock-open-variant",
        )
        self.btn_aksi.setAccessibleName("Open Vault button")
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
        self.password_panel.retry_requested.connect(self._retry_after_error)
        self.password_panel.pick_file_requested.connect(self.drop_zone.choose_file)

    def _on_file_changed(self, path: str):
        self._has_file = bool(path) and self.drop_zone.can_open_file()
        self._reset_timpa()
        self.password_panel.set_idle_state()
        if path:
            if self._has_file:
                self.status_changed.emit(
                    "Vault ready to open", "Valid format • Not yet verified", "ready"
                )
            else:
                self.status_changed.emit(
                    "Invalid file", self.drop_zone.get_format_status(), "error"
                )
        else:
            self.status_changed.emit("AES-256 • GCM", "Local encryption active", "idle")
        self._validate_state()

    def _on_password_valid_changed(self, is_valid: bool):
        self.notif.hide_msg()
        self._has_password = is_valid
        self._validate_state()

    def _validate_state(self):
        if self.worker is not None:
            return
        if self._external_busy:
            self.btn_aksi.setEnabled(False)
            self.btn_aksi.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            return
        if not self._konfirmasi_timpa:
            enabled = self._has_file and self._has_password
            self.btn_aksi.setEnabled(enabled)
            self.btn_aksi.setFocusPolicy(
                Qt.FocusPolicy.StrongFocus if enabled else Qt.FocusPolicy.NoFocus
            )

    def _reset_timpa(self):
        self._konfirmasi_timpa = False
        self.btn_aksi.resetVisualIcons("mdi6.lock-open-variant")
        self.btn_aksi.setProgressVisible(False)
        self.btn_aksi.setTextLabels("Open Vault", "Enter the password to unlock")

    def set_external_busy(self, busy: bool) -> None:
        """Kunci aksi buka saat tab lain sedang menjalankan operasi crypto.

        Navigasi tab tetap dibiarkan aktif, tapi memulai operasi baru dikunci
        agar tidak ada dua worker crypto berjalan bersamaan.
        """
        self._external_busy = bool(busy)
        if self.worker is not None:
            return
        if busy:
            self.btn_aksi.setProgressVisible(False)
            self.btn_aksi.setEnabled(False)
            self.btn_aksi.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.btn_aksi.setTextLabels(
                "Another operation is running", "Wait for it to finish, or cancel it first"
            )
        else:
            self._reset_timpa()
            self._validate_state()

    def _proses(self):
        if self._external_busy and self.worker is None:
            self.notif.show_msg(
                "warn",
                "Another operation is running. Wait for it to finish or cancel the current process.",
                4000,
            )
            return

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
            stage = progress_stage_label(val, "buka")
            self.password_panel.update_processing_stage(stage)
            title, subtitle = format_progress_label(val, "buka", eta_str)
            self.btn_aksi.setTextLabels(title, subtitle)
            self.btn_aksi.setProgressAnimated(val)

    def _current_file_summary(self) -> tuple[str, str]:
        path_file = self.drop_zone.get_file()
        file_name = os.path.basename(path_file) if path_file else "—"
        try:
            size_text = format_file_size(os.path.getsize(path_file)) if path_file else "—"
        except OSError:
            size_text = "—"
        return file_name, size_text

    def _set_busy(self, busy: bool):
        self.drop_zone.set_busy(busy)

        if busy:
            self.drop_zone.set_verification_state("checking")
            file_name, size_text = self._current_file_summary()
            self.password_panel.set_processing_state(file_name, size_text, "Verifying password")
            self.status_changed.emit("Verifying vault", "Keep the app open", "busy")
            self.btn_aksi.setVisualIcons("mdi6.close-circle", "mdi6.close")
            self.btn_aksi.setProgressVisible(True, 0.0)
            self.btn_aksi.setTextLabels("Opening vault", "Preparing vault • Click to cancel")
            self.btn_aksi.setEnabled(True)
            self.btn_aksi.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        else:
            self.btn_aksi.resetVisualIcons("mdi6.lock-open-variant")
            self.btn_aksi.setProgressVisible(False)
            self.btn_aksi.setTextLabels("Open Vault", "Enter the password to open")
            if self._has_file:
                self.password_panel.set_idle_state()
                self.status_changed.emit("Vault ready to open", "Not yet verified", "ready")
            else:
                self.password_panel.set_idle_state()
                self.status_changed.emit("AES-256 • GCM", "Local encryption active", "idle")
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
            self.drop_zone.set_verification_state("verified")
            self.drop_zone.reset_zone()
            self.status_changed.emit("Verified", "Data opened successfully", "success")
            logger.info(f"Dekripsi sukses: {msg}")
            self.notif.show_msg("ok", f"'{msg}' restored successfully.", 6000)

            # PANCARKAN SINYAL KE APP.PY UNTUK WINOTIFY
            self.system_notification.emit(APP_NAME, f"Vault opened — '{msg}' is ready.")

        elif status == VaultStatus.CANCELLED:
            logger.info("Dekripsi dibatalkan pengguna.")
            self.drop_zone.set_verification_state("pending", "Waiting for password")
            self.status_changed.emit("Cancelled", "Temporary files cleaned up", "warn")
            self.notif.show_msg("warn", "Operation cancelled.", 4000)

        elif status == VaultStatus.WRONG_PASSWORD:
            logger.warning("Dekripsi gagal: Password salah.")
            user_msg = format_user_error(status, msg, "buka")
            self.drop_zone.set_verification_state("failed")
            self.status_changed.emit(
                "Verification failed", "Wrong password or corrupted file", "error"
            )
            self.password_panel.set_error_state(user_msg)
            self.notif.show_msg("err", user_msg, 8000)

        elif status == VaultStatus.OVERWRITE_NEEDED:
            self.drop_zone.set_verification_state("verified", "Verified, awaiting confirmation")
            dialog = ModernMessageBox(
                title="File Already Exists",
                message=(
                    f"A file or folder named '{msg}' already exists at this location.\n\n"
                    "Adyton will extract to a temporary folder first, and only replace the existing data once the vault opens successfully.\n\n"
                    "Replace the existing data?"
                ),
                icon_name="mdi6.alert-decagram",
                icon_color=CLR_DANGER,
                parent=self,
            )
            dialog.btn_yes.setText("Replace Data")

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
            user_msg = format_user_error(status, msg, "buka")
            self.drop_zone.set_verification_state("failed", "Failed to open file")
            self.status_changed.emit(
                "Failed to open", "Check your file, permissions, or available disk space", "error"
            )
            self.password_panel.set_error_state(user_msg)
            self.notif.show_msg("err", user_msg, 8000)

    def _retry_after_error(self) -> None:
        self.password_panel.set_idle_state()
        self.drop_zone.set_verification_state("pending", "Waiting for password")
        self._validate_state()

    def auto_load_file(self, path: str) -> None:
        self.drop_zone.load_file(path)
