"""
Modul: tab_kunci.py
Deskripsi: Controller utama untuk Tab "Kunci Folder".
           Memancarkan sinyal ke app.py untuk UWP Toast (Winotify).
"""

import os

from loguru import logger
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.constants import DELETE_ORIGINAL_FAILED_MESSAGE, kdf_params_for_level
from core.crypto import generate_recovery_code
from core.vault import VaultStatus, kunci_brankas
from core.worker import CryptoWorker

from .buttons import BigActionBtn

# --- IMPORT SMART COMPONENTS (Sesuai dengan nama asli file lu!) ---
from .components.drop_zone_lock import DropZoneLock
from .components.options_panel import OptionsPanel
from .components.password_panel_lock import PasswordPanelLock
from .constants import APP_NAME
from .core_messages import localize_core_message
from .dialogs import ModernMessageBox, RecoveryCodeDialog
from .i18n import register, tr
from .settings_store import get_settings
from .utils import (
    ProgressETA,
    apply_cancelling_state,
    apply_shadow,
    format_file_size,
    format_progress_label,
    format_user_error,
    start_crypto_worker,
)
from .widgets import AnimatedNotifBar


class TabKunci(QWidget):
    # SINYAL NATIVE untuk ditangkap app.py
    system_notification = Signal(str, str)
    worker_started = Signal(object)  # emits the CryptoWorker instance
    status_changed = Signal(str, str, str)  # title, subtitle, state (untuk status pill)

    def __init__(self):
        super().__init__()
        self.worker: CryptoWorker | None = None
        self._is_password_valid = False
        self._has_files = False
        self._progress_eta = ProgressETA()
        self._external_busy = False
        self._last_saved_path: str | None = None  # untuk catat Recent saat sukses

        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(22)

        # Inisialisasi sesuai nama Class asli lu
        self.drop_zone = DropZoneLock()
        self.options_panel = OptionsPanel()
        self.options_panel.hide()
        self.password_panel = PasswordPanelLock()

        # Opsi "Delete original" kini berada di dalam card target (dasar daftar).
        self.drop_zone.embed_options(self.options_panel)

        # Terapkan default opsi dari Settings (Hapus Asli / Secure Wipe / Kompresi).
        _s = get_settings()
        self.options_panel.apply_defaults(_s.delete_original(), _s.secure_wipe(), _s.compress())

        # Panel password bisa lebih tinggi dari kolom (form + recovery + hint),
        # jadi dibungkus scroll area sendiri agar isinya tidak terpotong dan hanya
        # panel ini yang menggulir — drop zone di kiri tetap diam.
        self.pw_scroll = QScrollArea()
        self.pw_scroll.setObjectName("PwScrollArea")
        self.pw_scroll.setWidget(self.password_panel)
        self.pw_scroll.setWidgetResizable(True)
        self.pw_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.pw_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Hanya scroll area + viewport-nya yang transparan. JANGAN sertakan
        # "> QWidget > QWidget" karena itu mengenai panel (Card) langsung dan
        # menghapus latarnya — beda dari tab lain. Card di-set widget langsung,
        # jadi viewport-nya cukup satu "> QWidget".
        self.pw_scroll.setStyleSheet(
            "QScrollArea#PwScrollArea, QScrollArea#PwScrollArea > QWidget"
            " { background: transparent; }"
        )

        h_cols = QHBoxLayout()
        h_cols.setSpacing(28)

        v_left = QVBoxLayout()
        v_left.addWidget(self.drop_zone, 1)

        h_cols.addLayout(v_left, 1)
        h_cols.addWidget(self.pw_scroll, 1)
        main_layout.addLayout(h_cols)

        self.btn_aksi = BigActionBtn(
            tr("lock.action.title", "Lock Now"),
            tr("lock.action.sub", "Click to start encrypting your files"),
            icon_name="mdi6.lock-outline",
        )
        register(self.btn_aksi, "a11y.btn.lock_vault", "Lock Vault button", "setAccessibleName")
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
        self.drop_zone.paths_changed.connect(self._on_paths_changed)
        self.drop_zone.warning_emitted.connect(lambda msg: self.notif.show_msg("warn", msg, 4000))
        self.password_panel.valid_state_changed.connect(self._on_password_valid_changed)
        self.options_panel.hapus_asli_changed.connect(self._update_btn_label)
        # Hasil "Generate keyfile" (sukses/gagal) ditampilkan di notif bar.
        self.password_panel.keyfile_panel.notify.connect(
            lambda level, msg: self.notif.show_msg("ok" if level == "ok" else "err", msg, 5000)
        )

    def _on_paths_changed(self, paths: list):
        self._has_files = len(paths) > 0
        self.options_panel.setVisible(self._has_files)
        self._validate_state()

    def _on_password_valid_changed(self, is_valid: bool):
        self._is_password_valid = is_valid
        self._validate_state()

    def _validate_state(self):
        if self.worker is not None:
            return
        if self._external_busy:
            self.btn_aksi.setEnabled(False)
            self.btn_aksi.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            return
        enabled = self._has_files and self._is_password_valid
        self.btn_aksi.setEnabled(enabled)
        self.btn_aksi.setFocusPolicy(
            Qt.FocusPolicy.StrongFocus if enabled else Qt.FocusPolicy.NoFocus
        )
        self._emit_status()

    def _emit_status(self):
        """Pancarkan status keamanan tab Kunci untuk status pill di header."""
        if self.worker is not None:
            return
        if self._has_files and self._is_password_valid:
            self.status_changed.emit(
                tr("lock.status.ready", "Ready to lock"),
                tr("lock.status.ready.sub", "Target & password ready"),
                "ready",
            )
        elif self._has_files:
            self.status_changed.emit(
                tr("lock.status.complete_pw", "Complete the password"),
                tr("lock.status.complete_pw.sub", "Create a strong password"),
                "ready",
            )
        else:
            self.status_changed.emit(
                tr("status.aes", "AES-256 • GCM"),
                tr("status.local", "Local encryption active"),
                "idle",
            )

    def _update_btn_label(self, is_hapus_asli: bool):
        if self._external_busy and self.worker is None:
            self.btn_aksi.setTextLabels(
                tr("busy.other.title", "Another operation is running"),
                tr("busy.other.sub", "Wait for it to finish, or cancel it first"),
            )
            return
        if is_hapus_asli:
            self.btn_aksi.setTextLabels(
                tr("lock.action.delete.title", "Encrypt & Delete Original"),
                tr("lock.action.delete.sub", "The original file will be deleted after locking"),
            )
        else:
            self.btn_aksi.setTextLabels(
                tr("lock.action.title", "Lock Now"),
                tr("lock.action.sub", "Click to start encrypting your files"),
            )

    def set_external_busy(self, busy: bool) -> None:
        """Kunci aksi kunci saat tab lain sedang menjalankan operasi crypto."""
        self._external_busy = bool(busy)
        if self.worker is not None:
            return
        if busy:
            self.btn_aksi.setProgressVisible(False)
            self.btn_aksi.setEnabled(False)
            self.btn_aksi.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.btn_aksi.setTextLabels(
                tr("busy.other.title", "Another operation is running"),
                tr("busy.other.sub", "Wait for it to finish, or cancel it first"),
            )
        else:
            self.btn_aksi.setProgressVisible(False)
            self._update_btn_label(self.options_panel.is_hapus_asli())
            self._validate_state()

    def _update_progress(self, val):
        if self.worker and not self.worker.is_cancelled():
            eta_str = self._progress_eta.update(val)
            title, subtitle = format_progress_label(val, "kunci", eta_str)
            self.btn_aksi.setTextLabels(title, subtitle)
            self.btn_aksi.setProgressAnimated(val)

    def auto_load_paths(self, paths: list[str]) -> None:
        """Muat path dari luar (context menu hybrid) ke drop zone tab Kunci."""
        self.drop_zone.add_paths(list(paths))

    def _proses(self):
        if self._external_busy and self.worker is None:
            self.notif.show_msg(
                "warn",
                tr(
                    "busy.other.warn",
                    "Another operation is running. Wait for it to finish or cancel the current process.",
                ),
                4000,
            )
            return

        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self._progress_eta.reset()
            apply_cancelling_state(self.btn_aksi)
            return

        paths = self.drop_zone.get_paths()
        pw = self.password_panel.get_password()
        hapus_asli = self.options_panel.is_hapus_asli()
        secure_wipe = self.options_panel.is_secure_wipe()
        compress = self.options_panel.is_compress()

        # Enter di field password memicu _proses walau tombol aksi sedang disabled
        # (mis. belum ada target, atau password kosong). Cegah lebih dulu agar tidak
        # menyentuh paths[0] saat daftar kosong (IndexError) atau memproses password
        # kosong. Mirror guard di TabBuka._proses.
        if not paths or not pw:
            return

        # Recovery passphrase kosong: cegah lebih awal sebelum dialog apa pun.
        if self.password_panel.has_pending_passphrase_error():
            self.notif.show_msg(
                "warn",
                tr(
                    "lock.recovery.empty",
                    "Enter a recovery passphrase, or turn off the recovery key.",
                ),
                4000,
            )
            return

        # Keyfile (2FA) diaktifkan tapi belum dipilih: cegah lebih awal.
        if self.password_panel.has_pending_keyfile_error():
            self.notif.show_msg(
                "warn",
                tr(
                    "lock.keyfile.empty",
                    "Choose a keyfile, or turn off keyfile protection.",
                ),
                4000,
            )
            return

        if hapus_asli:
            dialog = ModernMessageBox(
                title=tr("lock.dialog.delete.title", "Confirm Delete"),
                message=tr(
                    "lock.dialog.delete.msg",
                    "The original file or folder will be permanently deleted after the vault is created and verified.\n\n"
                    "Make sure you have a backup of anything important before continuing.",
                ),
                parent=self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

        default_name = os.path.basename(paths[0]) or "Secret_Vault"
        self.btn_aksi.clearFocus()

        path_simpan, _ = QFileDialog.getSaveFileName(
            self,
            tr("lock.save_vault", "Save Vault"),
            f"{default_name}.adtn",
            tr("lock.save_filter", "Locked File (*.adtn)"),
        )
        if not path_simpan:
            return
        self._last_saved_path = path_simpan

        # Resolusi recovery key (opsional). Untuk mode "code", tampilkan kode dan
        # minta user mengonfirmasi sudah menyimpannya SEBELUM lock dimulai.
        recovery_secret = None
        recovery_type = "code"
        if self.password_panel.recovery_enabled():
            if self.password_panel.recovery_mode() == "passphrase":
                recovery_secret = self.password_panel.recovery_passphrase()
                recovery_type = "passphrase"
            else:
                code = generate_recovery_code()
                if RecoveryCodeDialog(code, parent=self).exec() != QDialog.DialogCode.Accepted:
                    return
                recovery_secret = code
                recovery_type = "code"

        hint = self.password_panel.get_hint() or None
        keyfile_path = self.password_panel.keyfile_path() or None

        self._progress_eta.reset()
        self._set_busy(True)
        self.worker = CryptoWorker(
            kunci_brankas,
            list(paths),
            path_simpan,
            pw,
            hapus_asli=hapus_asli,
            secure_wipe=secure_wipe,
            recovery_secret=recovery_secret,
            recovery_type=recovery_type,
            hint=hint,
            kdf_params=kdf_params_for_level(get_settings().kdf_level()),
            keyfile_path=keyfile_path,
            compress=compress,
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
            self.btn_aksi.setProgressVisible(True, 0.0)
            self.btn_aksi.setTextLabels(
                tr("lock.busy.title", "Locking vault"),
                tr("lock.busy.sub", "Preparing data • Click to cancel"),
            )
            self.btn_aksi.setEnabled(True)
            self.btn_aksi.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.status_changed.emit(
                tr("lock.status.locking", "Locking vault"),
                tr("lock.status.locking.sub", "Keep the app open"),
                "busy",
            )
        else:
            self.btn_aksi.setProgressVisible(False)
            self._update_btn_label(self.options_panel.is_hapus_asli())
            self._validate_state()

    def _on_selesai(self, result):
        self.worker = None
        status, msg = result

        if status == VaultStatus.SUCCESS:
            get_settings().add_recent_vault(self._last_saved_path)
            self.drop_zone.clear_paths()
            self.options_panel.reset_options()

        self._set_busy(False)
        self._progress_eta.reset()

        if status == VaultStatus.SUCCESS and msg == DELETE_ORIGINAL_FAILED_MESSAGE:
            # Vault jadi & terverifikasi, tapi sebagian sumber gagal dihapus (mis.
            # file sedang dibuka aplikasi lain). Sukses — tapi user HARUS tahu
            # file aslinya masih ada.
            logger.warning("Vault dibuat, tapi sebagian file asli gagal dihapus.")
            warn_msg = localize_core_message(msg)
            self.notif.show_msg("warn", f" {warn_msg}", 10000)
            self.status_changed.emit(
                tr("lock.status.locked", "Locked"),
                tr("lock.status.delete_failed.sub", "Some originals couldn't be deleted"),
                "warn",
            )
            self.system_notification.emit(APP_NAME, warn_msg)
        elif status == VaultStatus.SUCCESS:
            logger.info(f"Enkripsi sukses: {msg}")
            # Jangan tampilkan msg core mentah (English) di notif — itu bocor ke mode ID.
            # Pakai teks tr() + ukuran yang dihitung di sini (konsisten dgn tab Buka).
            try:
                size_txt = format_file_size(os.path.getsize(self._last_saved_path))
                done_msg = tr("lock.notif.done", "Vault locked securely — {size}.").format(
                    size=size_txt
                )
            except OSError:
                done_msg = tr("lock.notif.locked", "Vault locked securely.")
            self.notif.show_msg("ok", f" {done_msg}", 6000)
            self.status_changed.emit(
                tr("lock.status.locked", "Locked"),
                tr("lock.status.locked.sub", "Vault created successfully"),
                "success",
            )

            # PANCARKAN SINYAL KE APP.PY UNTUK WINOTIFY
            self.system_notification.emit(
                APP_NAME, tr("lock.notif.locked", "Vault locked securely.")
            )

        elif status == VaultStatus.CANCELLED:
            logger.info("Enkripsi dibatalkan oleh pengguna.")
            self.status_changed.emit(
                tr("lock.status.cancelled", "Cancelled"),
                tr("lock.status.cancelled.sub", "The locking process was cancelled"),
                "warn",
            )
            self.notif.show_msg("warn", tr("notif.cancelled", "Operation cancelled."), 4000)
        else:
            user_msg = format_user_error(status, msg, "kunci")
            logger.error(f"Gagal mengunci: {msg}")
            self.status_changed.emit(
                tr("lock.status.failed", "Failed to lock"),
                tr(
                    "lock.status.failed.sub",
                    "Check your file, permissions, or available disk space",
                ),
                "error",
            )
            self.notif.show_msg("err", user_msg, 8000)
