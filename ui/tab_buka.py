"""
Modul: tab_buka.py
Deskripsi: Controller utama untuk Tab "Buka Brankas".
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

from core.vault import (
    VaultStatus,
    buka_brankas,
    cancel_pending_overwrite,
    extract_selected,
    list_vault_contents,
    verify_vault,
)
from core.worker import CryptoWorker

from .buttons import BigActionBtn

# --- IMPORT SMART COMPONENTS (Sesuai dengan nama asli file lu!) ---
from .components.drop_zone_open import DropZoneOpen
from .components.password_panel_open import PasswordPanelOpen
from .components.recent_vaults_bar import RecentVaultsBar
from .constants import APP_NAME
from .core_messages import localize_core_message
from .dialogs import ModernMessageBox
from .i18n import register, tr
from .settings_store import get_settings
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
from .vault_browser_dialog import VaultBrowserDialog
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
        self._cached_keyfile = None
        self._has_file = False
        self._has_password = False
        self._progress_eta = ProgressETA()
        self._external_busy = False
        # Operasi yang sedang berjalan di worker bersama: "open" (ekstrak) atau
        # "verify" (cek integritas tanpa menulis). Mengarahkan label progress &
        # routing hasil; di-reset ke "open" tiap kali idle.
        self._mode = "open"

        self._build_ui()
        self._connect_signals()
        self.status_changed.emit(
            tr("status.aes", "AES-256 • GCM"), tr("status.local", "Local encryption active"), "idle"
        )

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(22)  # Sedikit lebih lapang untuk harmoni visual dua kolom

        # Inisialisasi sesuai nama Class asli lu
        self.drop_zone = DropZoneOpen()
        self.password_panel = PasswordPanelOpen()

        # Verify & Browse hidup di dasar password panel (berdampingan, dekat input
        # password). Referensi di-alias agar logika gating/visibilitas TabBuka tak
        # perlu berubah — keduanya tetap self.btn_verify / self.btn_browse.
        self.btn_verify = self.password_panel.btn_verify
        self.btn_browse = self.password_panel.btn_browse

        h_container = QHBoxLayout()
        h_container.setSpacing(28)  # More generous separation between columns
        h_container.addWidget(self.drop_zone, 1)
        h_container.addWidget(self.password_panel, 1)

        # Strip Recent Vaults full-width (opt-in; sembunyi saat mati/kosong).
        self.recent_bar = RecentVaultsBar()
        self.recent_bar.open_requested.connect(self._open_recent)

        # Kolom + Recent dibungkus scroll; tombol aksi (pill) di-anchor DI LUAR scroll
        # agar selalu terlihat, dan konten panjang (Security Details + Recent) bisa
        # digulir alih-alih terpotong saat tinggi jendela mepet.
        scroll_content = QWidget()
        sc_lay = QVBoxLayout(scroll_content)
        sc_lay.setContentsMargins(0, 0, 0, 0)
        sc_lay.setSpacing(22)
        sc_lay.addLayout(h_container, 1)
        sc_lay.addWidget(self.recent_bar)

        self.content_scroll = QScrollArea()
        self.content_scroll.setObjectName("OpenScrollArea")
        self.content_scroll.setWidget(scroll_content)
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content_scroll.setStyleSheet(
            "QScrollArea#OpenScrollArea, QScrollArea#OpenScrollArea > QWidget > QWidget"
            " { background: transparent; }"
        )
        main_layout.addWidget(self.content_scroll, 1)

        self.btn_aksi = BigActionBtn(
            tr("open.action.title", "Open Vault"),
            tr("open.action.sub", "Enter the password to open"),
            icon_name="mdi6.lock-open-variant-outline",
        )
        register(self.btn_aksi, "a11y.btn.open_vault", "Open Vault button", "setAccessibleName")
        self.btn_aksi.setEnabled(False)
        self.btn_aksi.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        apply_shadow(
            self.btn_aksi, blur_radius=24, y_offset=5, opacity=85
        )  # Option B: sedikit lebih berani

        main_layout.addWidget(self.btn_aksi)

        # btn_verify & btn_browse dibangun DI DALAM password panel (baris berdampingan
        # dekat input password) — lihat PasswordPanelOpen._build_secondary_actions.
        # Bagian bawah tab kini bersih: hanya CTA "Buka Vault".

        self.notif = AnimatedNotifBar(self)

    def _open_recent(self, path: str) -> None:
        if self.worker is not None or self._external_busy:
            return
        self.drop_zone.load_file(path)

    def _connect_signals(self):
        self.btn_aksi.clicked.connect(self._proses)
        self.btn_verify.clicked.connect(self._verify)
        self.btn_browse.clicked.connect(self._browse)
        self.password_panel.attach_return_event(self._proses)
        self.drop_zone.file_changed.connect(self._on_file_changed)
        self.password_panel.valid_state_changed.connect(self._on_password_valid_changed)
        self.password_panel.retry_requested.connect(self._retry_after_error)
        self.password_panel.pick_file_requested.connect(self.drop_zone.choose_file)
        self.password_panel.keyfile_changed.connect(self._validate_state)

    def _on_file_changed(self, path: str):
        self._has_file = bool(path) and self.drop_zone.can_open_file()
        self._reset_timpa()
        self.password_panel.set_idle_state()
        if path:
            if self._has_file:
                # Reuse meta yang sudah ditangkap drop zone dari satu pembacaan header;
                # jangan baca header lagi (hindari I/O ganda di main thread).
                hint, has_recovery, requires_keyfile = self.drop_zone.get_vault_meta()
                self.password_panel.show_vault_meta(hint, has_recovery, requires_keyfile)
                self.status_changed.emit(
                    tr("open.status.ready", "Vault ready to open"),
                    tr("open.status.ready.sub", "Valid format • Not yet verified"),
                    "ready",
                )
            else:
                self.password_panel.clear_vault_meta()
                self.status_changed.emit(
                    tr("open.status.invalid", "Invalid file"),
                    self.drop_zone.get_format_status(),
                    "error",
                )
        else:
            self.password_panel.clear_vault_meta()
            self.status_changed.emit(
                tr("status.aes", "AES-256 • GCM"),
                tr("status.local", "Local encryption active"),
                "idle",
            )
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
            self.btn_verify.setEnabled(False)
            self.btn_browse.setEnabled(False)
            return
        if not self._konfirmasi_timpa:
            enabled = self._has_file and self._has_password
            # Bila vault butuh keyfile DAN tak punya recovery key, keyfile adalah
            # satu-satunya faktor kedua → wajib dipilih sebelum tombol aktif (tanpa ini
            # user mengetuk Open lalu kena WRONG_PASSWORD). Vault 2FA yang punya recovery
            # tidak digate: user boleh memakai recovery key tanpa keyfile.
            if (
                enabled
                and self.password_panel.requires_keyfile()
                and not self.password_panel.has_recovery()
                and not self.password_panel.keyfile_path()
            ):
                enabled = False
            self.btn_aksi.setEnabled(enabled)
            self.btn_aksi.setFocusPolicy(
                Qt.FocusPolicy.StrongFocus if enabled else Qt.FocusPolicy.NoFocus
            )
            # Verify & Browse dibuka pada syarat yang sama (file valid + password +
            # keyfile bila wajib).
            self.btn_verify.setEnabled(enabled)
            self.btn_browse.setEnabled(enabled)

    def _reset_timpa(self):
        self._konfirmasi_timpa = False
        self.btn_aksi.resetVisualIcons("mdi6.lock-open-variant-outline")
        self.btn_aksi.setProgressVisible(False)
        self.btn_aksi.setTextLabels(
            tr("open.action.title", "Open Vault"),
            tr("open.action.sub2", "Enter the password to unlock"),
        )

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
            self.btn_verify.setEnabled(False)
            self.btn_browse.setEnabled(False)
            self.btn_aksi.setTextLabels(
                tr("busy.other.title", "Another operation is running"),
                tr("busy.other.sub", "Wait for it to finish, or cancel it first"),
            )
        else:
            self._reset_timpa()
            self._validate_state()

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

        force = self._konfirmasi_timpa
        path_file = self.drop_zone.get_file()

        if force and self._cached_pw:
            pw = self._cached_pw
            keyfile = self._cached_keyfile
        else:
            pw = self.password_panel.get_password()
            keyfile = self.password_panel.keyfile_path() or None
            self._cached_pw = pw
            self._cached_keyfile = keyfile

        if force:
            self._reset_timpa()

        if not path_file or not pw:
            return

        self._mode = "open"
        self._progress_eta.reset()
        self._set_busy(True)
        self.worker = CryptoWorker(
            buka_brankas, path_file, pw, force, keyfile_path=keyfile, parent=self
        )
        self.password_panel.reset_field()

        start_crypto_worker(self.worker, self._update_progress, self._on_selesai)
        self.worker_started.emit(self.worker)

    def _verify(self):
        """Verifikasi integritas vault tanpa mengekstrak (tanpa folder tujuan).

        Memakai worker bersama yang sama dengan Open (hanya satu operasi crypto pada
        satu waktu). Tombol Open besar menjadi permukaan progress/cancel; hasil
        diarahkan ke ``_on_verify_done`` lewat ``self._mode``.
        """
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

        path_file = self.drop_zone.get_file()
        pw = self.password_panel.get_password()
        keyfile = self.password_panel.keyfile_path() or None
        if not path_file or not pw:
            return

        self._mode = "verify"
        self._progress_eta.reset()
        self._set_busy(True)
        self.worker = CryptoWorker(verify_vault, path_file, pw, keyfile_path=keyfile, parent=self)
        self.password_panel.reset_field()

        start_crypto_worker(self.worker, self._update_progress, self._on_verify_done)
        self.worker_started.emit(self.worker)

    def _browse(self):
        """Baca daftar isi vault (stream-decrypt, tanpa menulis ke disk) → dialog.

        Memakai worker bersama yang sama dengan Open/Verify. Password + keyfile
        di-cache karena ekstrak (bila user memilih) butuh pass dekripsi kedua.
        """
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

        path_file = self.drop_zone.get_file()
        pw = self.password_panel.get_password()
        keyfile = self.password_panel.keyfile_path() or None
        if not path_file or not pw:
            return

        self._mode = "browse"
        self._cached_pw = pw
        self._cached_keyfile = keyfile
        self._progress_eta.reset()
        self._set_busy(True)
        self.worker = CryptoWorker(
            list_vault_contents, path_file, pw, keyfile_path=keyfile, parent=self
        )
        self.password_panel.reset_field()

        start_crypto_worker(self.worker, self._update_progress, self._on_browse_listed)
        self.worker_started.emit(self.worker)

    def _on_browse_listed(self, result):
        self.worker = None
        status = result[0]
        self._mode = "open"

        self._set_busy(False)
        self._progress_eta.reset()

        if status == VaultStatus.SUCCESS:
            root_name, entries = result[1], result[2]
            self.drop_zone.set_verification_state("verified")
            self.status_changed.emit(
                tr("open.browse.ok.title", "Vault contents ready"),
                tr("open.browse.ok.sub", "Choose what to extract"),
                "success",
            )
            self._prompt_and_extract(root_name, entries or [])
            return

        # Selain sukses: buang credential yang di-cache (tak jadi ekstrak).
        self._cached_pw = None
        self._cached_keyfile = None

        if status == VaultStatus.CANCELLED:
            logger.info("Browse dibatalkan pengguna.")
            self.drop_zone.set_verification_state(
                "pending", tr("dz.meta.waiting", "Waiting for password")
            )
            self.status_changed.emit(
                tr("open.status.cancelled", "Cancelled"),
                tr("open.status.cancelled.sub", "Temporary files cleaned up"),
                "warn",
            )
            self.notif.show_msg("warn", tr("notif.cancelled", "Operation cancelled."), 4000)

        elif status == VaultStatus.WRONG_PASSWORD:
            logger.warning("Browse gagal: credential salah.")
            user_msg = format_user_error(status, result[1], "buka")
            if self.password_panel.requires_keyfile() and not self.password_panel.keyfile_path():
                user_msg = tr(
                    "open.wrongpw.keyfile",
                    "Wrong password or recovery key. If you're using your password, "
                    "also select the keyfile this vault needs.",
                )
            self.drop_zone.set_verification_state("failed")
            self.status_changed.emit(
                tr("open.status.failed", "Verification failed"),
                tr("open.status.failed.sub", "Wrong password or corrupted file"),
                "error",
            )
            self.password_panel.set_error_state(user_msg)
            self.notif.show_msg("err", user_msg, 8000)

        else:
            logger.warning(f"Browse gagal: {result[1]}")
            user_msg = localize_core_message(result[1]) or tr(
                "open.browse.fail.msg", "Couldn't read the vault contents. It may be corrupted."
            )
            self.drop_zone.set_verification_state("failed")
            self.status_changed.emit(
                tr("open.browse.fail.title", "Couldn't read contents"),
                tr("open.browse.fail.sub", "The vault may be corrupted or modified"),
                "error",
            )
            self.password_panel.set_error_state(user_msg)
            self.notif.show_msg("err", user_msg, 9000)

    def _prompt_and_extract(self, root_name: str, entries):
        """Buka dialog isi vault; bila user memilih & konfirmasi → ekstrak selektif."""
        dialog = VaultBrowserDialog(root_name, entries, parent=self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        selected = dialog.selected_paths() if accepted else []
        expected = dialog.selected_bytes() if accepted else 0

        if not accepted or not selected:
            self._cached_pw = None
            self._cached_keyfile = None
            self.drop_zone.set_verification_state("verified")
            return

        dest = QFileDialog.getExistingDirectory(
            self, tr("open.extract.pick_dest", "Choose where to extract the selected items")
        )
        if not dest:
            self._cached_pw = None
            self._cached_keyfile = None
            self.drop_zone.set_verification_state("verified")
            return

        path_file = self.drop_zone.get_file()
        pw = self._cached_pw
        keyfile = self._cached_keyfile
        if not path_file or not pw:
            return

        self._mode = "extract"
        self._progress_eta.reset()
        self._set_busy(True)
        self.worker = CryptoWorker(
            extract_selected,
            path_file,
            pw,
            selected,
            dest,
            keyfile_path=keyfile,
            expected_bytes=expected,
            parent=self,
        )
        start_crypto_worker(self.worker, self._update_progress, self._on_extract_done)
        self.worker_started.emit(self.worker)

    def _on_extract_done(self, result):
        self.worker = None
        status, msg = result
        self._mode = "open"
        self._cached_pw = None
        self._cached_keyfile = None

        self._set_busy(False)
        self._progress_eta.reset()

        if status == VaultStatus.SUCCESS:
            self.drop_zone.set_verification_state("verified")
            self.status_changed.emit(
                tr("open.extract.ok.title", "Extraction complete"),
                tr("open.extract.ok.sub", "Selected items were saved"),
                "success",
            )
            logger.info(f"Ekstrak selektif sukses: {msg}")
            self.notif.show_msg(
                "ok",
                tr("open.extract.ok.msg", "Extracted the selected items to '{name}'.").format(
                    name=msg
                ),
                6000,
            )
            self.system_notification.emit(
                APP_NAME,
                tr("open.extract.notif", "Extraction finished — '{name}' is ready.").format(
                    name=msg
                ),
            )

        elif status == VaultStatus.CANCELLED:
            logger.info("Ekstrak selektif dibatalkan pengguna.")
            self.drop_zone.set_verification_state("verified")
            self.status_changed.emit(
                tr("open.status.cancelled", "Cancelled"),
                tr("open.status.cancelled.sub", "Temporary files cleaned up"),
                "warn",
            )
            self.notif.show_msg("warn", tr("notif.cancelled", "Operation cancelled."), 4000)

        else:
            logger.warning(f"Ekstrak selektif gagal: {msg}")
            user_msg = localize_core_message(msg) or tr(
                "open.extract.fail.msg", "Couldn't extract the selected items."
            )
            self.drop_zone.set_verification_state("verified")
            self.status_changed.emit(
                tr("open.extract.fail.title", "Extraction failed"),
                tr("open.extract.fail.sub", "Check the destination, permissions, or disk space"),
                "error",
            )
            self.password_panel.set_error_state(user_msg)
            self.notif.show_msg("err", user_msg, 9000)

    def _update_progress(self, val):
        if self.worker and not self.worker.is_cancelled():
            eta_str = self._progress_eta.update(val)
            if self._mode in ("verify", "browse", "extract"):
                pct = int(max(0.0, min(1.0, val)) * 100)
                if self._mode == "browse":
                    stage = tr("open.browse.stage", "Reading contents")
                    title = tr("open.browse.busy.title", "Reading vault contents")
                elif self._mode == "extract":
                    stage = tr("open.extract.stage", "Extracting files")
                    title = tr("open.extract.busy.title", "Extracting selected files")
                else:
                    stage = tr("open.verify.stage", "Checking integrity")
                    title = tr("open.verify.busy.title", "Verifying vault")
                self.password_panel.update_processing_stage(stage)
                self.btn_aksi.setTextLabels(
                    title,
                    f"{pct}% • {eta_str} • " + tr("open.verify.click_cancel", "Click to cancel"),
                )
                self.btn_aksi.setProgressAnimated(val)
                return
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
        # Verify & Browse memakai tombol Open besar sebagai permukaan progress/cancel,
        # jadi baris aksi sekunder (di password panel) disembunyikan selama operasi.
        self.password_panel.secondary_actions.setVisible(not busy)

        if busy:
            verifying = self._mode == "verify"
            browsing = self._mode == "browse"
            extracting = self._mode == "extract"
            self.drop_zone.set_verification_state("checking")
            file_name, size_text = self._current_file_summary()
            if browsing:
                panel_stage = tr("open.browse.stage", "Reading contents")
            elif extracting:
                panel_stage = tr("open.extract.stage", "Extracting files")
            elif verifying:
                panel_stage = tr("open.verify.stage", "Checking integrity")
            else:
                panel_stage = tr("dz.status.verifying_pw", "Verifying password")
            self.password_panel.set_processing_state(file_name, size_text, panel_stage)
            self.status_changed.emit(
                tr("open.status.verifying", "Verifying vault"),
                tr("open.status.verifying.sub", "Keep the app open"),
                "busy",
            )
            self.btn_aksi.setVisualIcons("mdi6.close-circle-outline")
            self.btn_aksi.setProgressVisible(True, 0.0)
            if browsing:
                self.btn_aksi.setTextLabels(
                    tr("open.browse.busy.title", "Reading vault contents"),
                    tr("open.browse.busy.sub", "Decrypting to list files • Click to cancel"),
                )
            elif extracting:
                self.btn_aksi.setTextLabels(
                    tr("open.extract.busy.title", "Extracting selected files"),
                    tr("open.extract.busy.sub", "Writing to destination • Click to cancel"),
                )
            elif verifying:
                self.btn_aksi.setTextLabels(
                    tr("open.verify.busy.title", "Verifying vault"),
                    tr("open.verify.busy.sub", "Checking integrity • Click to cancel"),
                )
            else:
                self.btn_aksi.setTextLabels(
                    tr("open.busy.title", "Opening vault"),
                    tr("open.busy.sub", "Preparing vault • Click to cancel"),
                )
            self.btn_aksi.setEnabled(True)
            self.btn_aksi.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        else:
            self.btn_aksi.resetVisualIcons("mdi6.lock-open-variant-outline")
            self.btn_aksi.setProgressVisible(False)
            self.btn_aksi.setTextLabels(
                tr("open.action.title", "Open Vault"),
                tr("open.action.sub", "Enter the password to open"),
            )
            if self._has_file:
                self.password_panel.set_idle_state()
                self.status_changed.emit(
                    tr("open.status.ready", "Vault ready to open"),
                    tr("open.status.notverified", "Not yet verified"),
                    "ready",
                )
            else:
                self.password_panel.set_idle_state()
                self.status_changed.emit(
                    tr("status.aes", "AES-256 • GCM"),
                    tr("status.local", "Local encryption active"),
                    "idle",
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
            self._cached_keyfile = None

        if status == VaultStatus.SUCCESS:
            # Catat ke Recent SEBELUM reset_zone() membersihkan path terpilih.
            get_settings().add_recent_vault(self.drop_zone.get_file())
            self.drop_zone.set_verification_state("verified")
            self.drop_zone.reset_zone()
            self.status_changed.emit(
                tr("open.status.verified", "Verified"),
                tr("open.status.verified.sub", "Data opened successfully"),
                "success",
            )
            logger.info(f"Dekripsi sukses: {msg}")
            self.notif.show_msg(
                "ok", tr("open.restored", "'{name}' restored successfully.").format(name=msg), 6000
            )

            # PANCARKAN SINYAL KE APP.PY UNTUK WINOTIFY
            self.system_notification.emit(
                APP_NAME,
                tr("open.notif.opened", "Vault opened — '{name}' is ready.").format(name=msg),
            )

        elif status == VaultStatus.CANCELLED:
            logger.info("Dekripsi dibatalkan pengguna.")
            self.drop_zone.set_verification_state(
                "pending", tr("dz.meta.waiting", "Waiting for password")
            )
            self.status_changed.emit(
                tr("open.status.cancelled", "Cancelled"),
                tr("open.status.cancelled.sub", "Temporary files cleaned up"),
                "warn",
            )
            self.notif.show_msg("warn", tr("notif.cancelled", "Operation cancelled."), 4000)

        elif status == VaultStatus.WRONG_PASSWORD:
            logger.warning("Dekripsi gagal: Password salah.")
            user_msg = format_user_error(status, msg, "buka")
            # Vault 2FA dibuka tanpa keyfile → slot keyfile dilewati, hasilnya
            # WRONG_PASSWORD yang menyesatkan. Beri petunjuk yang benar (recovery key
            # tetap valid tanpa keyfile, jadi nadanya kondisional).
            if self.password_panel.requires_keyfile() and not self.password_panel.keyfile_path():
                user_msg = tr(
                    "open.wrongpw.keyfile",
                    "Wrong password or recovery key. If you're using your password, "
                    "also select the keyfile this vault needs.",
                )
            self.drop_zone.set_verification_state("failed")
            self.status_changed.emit(
                tr("open.status.failed", "Verification failed"),
                tr("open.status.failed.sub", "Wrong password or corrupted file"),
                "error",
            )
            self.password_panel.set_error_state(user_msg)
            self.notif.show_msg("err", user_msg, 8000)

        elif status == VaultStatus.OVERWRITE_NEEDED:
            self.drop_zone.set_verification_state(
                "verified", tr("open.awaiting", "Verified, awaiting confirmation")
            )
            dialog = ModernMessageBox(
                title=tr("open.overwrite.title", "File Already Exists"),
                message=tr(
                    "open.overwrite.msg",
                    "A file or folder named '{name}' already exists at this location.\n\n"
                    "Adyton will extract to a temporary folder first, and only replace the existing data once the vault opens successfully.\n\n"
                    "Replace the existing data?",
                ).format(name=msg),
                icon_name="mdi6.alert-octagon-outline",
                icon_color=CLR_DANGER,
                parent=self,
            )
            dialog.btn_yes.setText(tr("open.overwrite.replace", "Replace Data"))

            if dialog.exec() == QDialog.DialogCode.Accepted:
                self._konfirmasi_timpa = True
                self._proses()
            else:
                # User menolak: buang tar terverifikasi yang ditahan untuk resume
                # agar tidak menumpuk sampai sweep umur membersihkannya.
                cancel_pending_overwrite(self.drop_zone.get_file())
                self._cached_pw = None
                self._cached_keyfile = None
                self._reset_timpa()
                self._validate_state()
                logger.info("Dekripsi dibatalkan: User menolak overwrite file asli.")
        else:
            logger.error(f"Dekripsi gagal: {msg}")
            user_msg = format_user_error(status, msg, "buka")
            self.drop_zone.set_verification_state(
                "failed", tr("open.failopen.dz", "Failed to open file")
            )
            self.status_changed.emit(
                tr("open.status.failopen", "Failed to open"),
                tr(
                    "open.status.failopen.sub",
                    "Check your file, permissions, or available disk space",
                ),
                "error",
            )
            self.password_panel.set_error_state(user_msg)
            self.notif.show_msg("err", user_msg, 8000)

    def _on_verify_done(self, result):
        self.worker = None
        status, msg = result
        self._mode = "open"

        self._set_busy(False)
        self._progress_eta.reset()

        if status == VaultStatus.SUCCESS:
            # Pertahankan file yang dimuat (user mungkin lanjut "Open" setelahnya).
            self.drop_zone.set_verification_state("verified")
            self.status_changed.emit(
                tr("open.verify.ok.title", "Integrity verified"),
                tr("open.verify.ok.sub", "Credential correct • all data intact"),
                "success",
            )
            logger.info("Verifikasi vault sukses.")
            self.notif.show_msg(
                "ok",
                localize_core_message(msg)
                or tr("open.verify.ok.msg", "Vault verified — all data is intact."),
                6000,
            )

        elif status == VaultStatus.CANCELLED:
            logger.info("Verifikasi vault dibatalkan pengguna.")
            self.drop_zone.set_verification_state(
                "pending", tr("dz.meta.waiting", "Waiting for password")
            )
            self.status_changed.emit(
                tr("open.status.cancelled", "Cancelled"),
                tr("open.status.cancelled.sub", "Temporary files cleaned up"),
                "warn",
            )
            self.notif.show_msg("warn", tr("notif.cancelled", "Operation cancelled."), 4000)

        elif status == VaultStatus.WRONG_PASSWORD:
            logger.warning("Verifikasi gagal: credential salah.")
            user_msg = format_user_error(status, msg, "buka")
            if self.password_panel.requires_keyfile() and not self.password_panel.keyfile_path():
                user_msg = tr(
                    "open.wrongpw.keyfile",
                    "Wrong password or recovery key. If you're using your password, "
                    "also select the keyfile this vault needs.",
                )
            self.drop_zone.set_verification_state("failed")
            self.status_changed.emit(
                tr("open.status.failed", "Verification failed"),
                tr("open.status.failed.sub", "Wrong password or corrupted file"),
                "error",
            )
            self.password_panel.set_error_state(user_msg)
            self.notif.show_msg("err", user_msg, 8000)

        else:
            # ERROR: vault rusak / bukan vault / format beda. Pesan core sudah
            # path-free & ramah, jadi ditampilkan apa adanya.
            logger.warning(f"Verifikasi gagal: {msg}")
            user_msg = localize_core_message(msg) or tr(
                "open.verify.fail.msg", "Couldn't verify the vault. It may be corrupted."
            )
            self.drop_zone.set_verification_state("failed")
            self.status_changed.emit(
                tr("open.verify.fail.title", "Integrity check failed"),
                tr("open.verify.fail.sub", "The vault may be corrupted or modified"),
                "error",
            )
            self.password_panel.set_error_state(user_msg)
            self.notif.show_msg("err", user_msg, 9000)

    def clear_credential_cache(self) -> None:
        """Buang password/keyfile yang di-cache (untuk konfirmasi overwrite dan
        ekstrak-setelah-browse). Dipanggil auto-lock idle sebagai bagian panic-clear —
        mengosongkan field saja tidak cukup karena salinan ini tetap di memori.
        Konsekuensinya konfirmasi Replace berikutnya minta password lagi (wajar
        untuk fitur panic)."""
        self._cached_pw = None
        self._cached_keyfile = None

    def _retry_after_error(self) -> None:
        self.password_panel.set_idle_state()
        self.drop_zone.set_verification_state(
            "pending", tr("dz.meta.waiting", "Waiting for password")
        )
        self._validate_state()

    def auto_load_file(self, path: str) -> None:
        self.drop_zone.load_file(path)
