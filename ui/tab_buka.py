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
        self.status_changed.emit("AES-256 • GCM", "Enkripsi lokal aktif", "idle")

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
        self.password_panel.retry_requested.connect(self._retry_after_error)
        self.password_panel.pick_file_requested.connect(self.drop_zone.choose_file)

    def _on_file_changed(self, path: str):
        self._has_file = bool(path) and self.drop_zone.can_open_file()
        self._reset_timpa()
        self.password_panel.set_idle_state()
        if path:
            if self._has_file:
                self.status_changed.emit(
                    "Vault siap dibuka", "Format valid • Belum diverifikasi", "ready"
                )
            else:
                self.status_changed.emit(
                    "File tidak valid", self.drop_zone.get_format_status(), "error"
                )
        else:
            self.status_changed.emit("AES-256 • GCM", "Enkripsi lokal aktif", "idle")
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
        self.btn_aksi.setTextLabels("Buka Brankas", "Masukkan password untuk membuka kunci")

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
                "Operasi lain berjalan", "Tunggu atau batalkan proses saat ini"
            )
        else:
            self._reset_timpa()
            self._validate_state()

    def _proses(self):
        if self._external_busy and self.worker is None:
            self.notif.show_msg(
                "warn",
                "Operasi lain sedang berjalan. Tunggu selesai atau batalkan proses saat ini.",
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
            self.password_panel.set_processing_state(file_name, size_text, "Memverifikasi password")
            self.status_changed.emit("Memverifikasi vault", "Jangan tutup aplikasi", "busy")
            self.btn_aksi.setVisualIcons("mdi6.close-circle", "mdi6.close")
            self.btn_aksi.setProgressVisible(True, 0.0)
            self.btn_aksi.setTextLabels(
                "Membuka brankas", "Menyiapkan vault • Klik untuk membatalkan"
            )
            self.btn_aksi.setEnabled(True)
            self.btn_aksi.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        else:
            self.btn_aksi.resetVisualIcons("mdi6.lock-open-variant")
            self.btn_aksi.setProgressVisible(False)
            self.btn_aksi.setTextLabels("Buka Brankas", "Masukkan password untuk membuka")
            if self._has_file:
                self.password_panel.set_idle_state()
                self.status_changed.emit("Vault siap dibuka", "Belum diverifikasi", "ready")
            else:
                self.password_panel.set_idle_state()
                self.status_changed.emit("AES-256 • GCM", "Enkripsi lokal aktif", "idle")
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
            self.status_changed.emit("Terverifikasi", "Data berhasil dibuka", "success")
            logger.info(f"Dekripsi sukses: {msg}")
            self.notif.show_msg("ok", f"Folder/File '{msg}' berhasil dikembalikan!", 6000)

            # PANCARKAN SINYAL KE APP.PY UNTUK WINOTIFY
            self.system_notification.emit(APP_NAME, f"Brankas '{msg}' berhasil dibuka.")

        elif status == VaultStatus.CANCELLED:
            logger.info("Dekripsi dibatalkan pengguna.")
            self.drop_zone.set_verification_state("pending", "Menunggu password")
            self.status_changed.emit("Proses dibatalkan", "File sementara dibersihkan", "warn")
            self.notif.show_msg("warn", "Dekripsi dibatalkan pengguna.", 4000)

        elif status == VaultStatus.WRONG_PASSWORD:
            logger.warning("Dekripsi gagal: Password salah.")
            user_msg = format_user_error(status, msg, "buka")
            self.drop_zone.set_verification_state("failed")
            self.status_changed.emit(
                "Gagal diverifikasi", "Password salah atau file rusak", "error"
            )
            self.password_panel.set_error_state(user_msg)
            self.notif.show_msg("err", user_msg, 8000)

        elif status == VaultStatus.OVERWRITE_NEEDED:
            self.drop_zone.set_verification_state("verified", "Terverifikasi, menunggu konfirmasi")
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
            user_msg = format_user_error(status, msg, "buka")
            self.drop_zone.set_verification_state("failed", "Gagal membuka file")
            self.status_changed.emit(
                "Gagal membuka", "Periksa file, izin, atau ruang disk", "error"
            )
            self.password_panel.set_error_state(user_msg)
            self.notif.show_msg("err", user_msg, 8000)

    def _retry_after_error(self) -> None:
        self.password_panel.set_idle_state()
        self.drop_zone.set_verification_state("pending", "Menunggu password")
        self._validate_state()

    def auto_load_file(self, path: str) -> None:
        self.drop_zone.load_file(path)
