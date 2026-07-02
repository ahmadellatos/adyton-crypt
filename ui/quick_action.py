"""
Modul: quick_action.py
Deskripsi: Window mini transient untuk Windows context menu (klik kanan).
           Tiga mode — Encrypt / Decrypt / Shred — disusun ulang dari komponen
           shared yang sama dengan TabKunci/TabBuka, tanpa sidebar, tab, atau
           onboarding. Satu tugas, satu window, tutup = proses keluar.

           Dipanggil dari main.py lewat flag CLI (--encrypt / --decrypt / --shred)
           dan sengaja melewati single-instance lock + tray agar tiap aksi berdiri
           sendiri.
"""

import contextlib
import os
from enum import Enum, auto
from pathlib import Path

import qtawesome as qta
from loguru import logger
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from qframelesswindow import FramelessWindow

from core.constants import DELETE_ORIGINAL_FAILED_MESSAGE, kdf_params_for_level
from core.paths import get_asset_path
from core.vault import (
    VaultStatus,
    buka_brankas,
    cancel_pending_overwrite,
    hapus_permanen,
    kunci_brankas,
    vault_info,
)
from core.worker import CryptoWorker

from .buttons import BigActionBtn
from .components.options_panel import OptionsPanel
from .components.password_panel_lock import PasswordPanelLock
from .components.password_panel_open import PasswordPanelOpen
from .constants import APP_NAME
from .core_messages import localize_core_message
from .dialogs import ModernMessageBox
from .i18n import tr
from .settings_store import get_settings
from .styles import CLR_ACCENT, CLR_DANGER
from .utils import (
    ProgressETA,
    apply_cancelling_state,
    format_file_size,
    format_progress_label,
    format_user_error,
    start_crypto_worker,
)
from .widgets import AnimatedNotifBar, CustomTitleBar


class QuickMode(Enum):
    ENCRYPT = auto()
    DECRYPT = auto()
    SHRED = auto()


def _shred_paths(paths, secure_wipe, progress_cb=None, is_cancelled=None):
    """Hapus permanen beberapa path, lapor progress kasar per-item.

    Ditulis dengan signature progress_cb/is_cancelled agar CryptoWorker bisa
    menyuntik callback-nya sama seperti kunci_brankas/buka_brankas.
    """
    total = len(paths)
    for i, p in enumerate(paths):
        if is_cancelled and is_cancelled():
            return VaultStatus.CANCELLED, None
        hapus_permanen(Path(p), secure_wipe=secure_wipe)
        if progress_cb:
            progress_cb((i + 1) / total)
    msg = (
        tr("quick.shred.done.one", "1 item permanently deleted.")
        if total == 1
        else tr("quick.shred.done.many", "{n} items permanently deleted.").format(n=total)
    )
    return VaultStatus.SUCCESS, msg


class QuickActionWindow(FramelessWindow):
    """Window mini satu-tugas untuk aksi context menu."""

    _FIXED_W = 480

    def __init__(self, mode: QuickMode, paths: list[str], parent=None):
        super().__init__(parent)
        self.mode = mode
        # Pertahanan berlapis: vault .adtn tak boleh masuk daftar kunci (nested lock).
        if mode is QuickMode.ENCRYPT:
            paths = [p for p in paths if not p.lower().endswith(".adtn")]
        self.paths = paths
        self.worker: CryptoWorker | None = None
        self._eta = ProgressETA()
        self._password_panel = None
        self._options_panel = None
        # Hanya ENCRYPT yang bisa melebihi layar kecil (password + options) →
        # butuh scroll. DECRYPT/SHRED ringkas, dibiarkan fixed tanpa scroll.
        self._use_scroll = mode is QuickMode.ENCRYPT

        self.setObjectName("CentralWidget")  # bg #16282E dari QSS global
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(get_asset_path("assets/icon_adyton.ico")))
        self.setResizeEnabled(False)  # window fixed — tak bisa diperkecil/perbesar
        self.setFixedWidth(self._FIXED_W)

        self._build_chrome()
        self._build_body()
        self._finalize_size()

    # ── chrome: title bar + scroll area (konten) + body ──────────────────
    def _build_chrome(self):
        self.title_bar = CustomTitleBar(self, compact=True)
        self.setTitleBar(self.title_bar)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, self.title_bar.height(), 0, 0)
        outer.setSpacing(0)

        self.body = QWidget()
        outer.addWidget(self.body)

        self._body_lay = QVBoxLayout(self.body)
        self._body_lay.setContentsMargins(20, 14, 20, 20)
        self._body_lay.setSpacing(16)

        if self._use_scroll:
            # ENCRYPT bisa lebih tinggi dari layar kecil (mis. 1366x768), apalagi
            # saat sub-opsi Secure Wipe terbuka — taruh di scroll area agar tombol
            # aksi tetap bisa di-pin di bawah dan selalu terlihat.
            self._scroll = QScrollArea()
            self._scroll.setWidgetResizable(True)
            self._scroll.setFrameShape(QFrame.Shape.NoFrame)
            self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
            self._scroll.viewport().setStyleSheet("background: transparent;")

            self._scroll_content = QWidget()
            self._content_lay = QVBoxLayout(self._scroll_content)
            self._content_lay.setContentsMargins(0, 0, 0, 0)
            self._content_lay.setSpacing(16)
            self._scroll.setWidget(self._scroll_content)
            self._body_lay.addWidget(self._scroll, 1)
        else:
            # DECRYPT / SHRED ringkas dan muat di layar → langsung di body, tanpa
            # scroll, dengan window fixed (seperti sebelumnya).
            self._content_lay = self._body_lay

        # Notif overlay — di-parent ke body (bukan masuk layout) agar slide-in
        # top-right tetap di bawah titlebar.
        self.notif = AnimatedNotifBar(self.body)

    # ── body: konten dalam scroll, tombol aksi di-pin di bawah ───────────
    def _build_body(self):
        self._content_lay.addWidget(self._build_summary())

        if self.mode is QuickMode.ENCRYPT:
            self._password_panel = PasswordPanelLock()
            self._options_panel = OptionsPanel()
            # Hormati default opsi dari Settings — sama seperti TabKunci di app utama.
            _s = get_settings()
            self._options_panel.apply_defaults(
                _s.delete_original(), _s.secure_wipe(), _s.compress()
            )
            self.btn = BigActionBtn(
                tr("quick.enc.action", "Lock to Vault"), "", icon_name="mdi6.lock-outline"
            )
            self._content_lay.addWidget(self._password_panel)
            self._content_lay.addWidget(self._options_panel)
            self._password_panel.valid_state_changed.connect(self.btn.setEnabled)
            self._password_panel.attach_return_event(self._on_action)
            self.btn.setEnabled(False)

        elif self.mode is QuickMode.DECRYPT:
            self._password_panel = PasswordPanelOpen()
            self.btn = BigActionBtn(
                tr("quick.dec.action", "Open Vault"), "", icon_name="mdi6.lock-open-outline"
            )
            self._content_lay.addWidget(self._password_panel)
            self._password_panel.valid_state_changed.connect(self.btn.setEnabled)
            self._password_panel.attach_return_event(self._on_action)
            self.btn.setEnabled(False)

        else:  # SHRED — tanpa password, langsung aktif (dijaga konfirmasi keras)
            self.btn = BigActionBtn(
                tr("quick.shred.action", "Securely Delete"),
                "",
                icon_name="mdi6.delete-forever-outline",
            )
            self.btn.setEnabled(True)

        if self._use_scroll:
            self._content_lay.addStretch(1)  # konten rata-atas saat layar lega

        self.btn.clicked.connect(self._on_action)
        self._body_lay.addWidget(self.btn)  # ENCRYPT: di-pin di luar scroll

    def _build_summary(self) -> QFrame:
        """Kartu ringkas: ikon + apa yang akan terjadi pada path yang dipilih."""
        icon_name, icon_color, title, subtitle = self._summary_text()

        card = QFrame()
        card.setObjectName("Card")
        lay = QHBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(14)

        lbl_icon = QLabel()
        lbl_icon.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(26, 26))
        lay.addWidget(lbl_icon, alignment=Qt.AlignmentFlag.AlignTop)

        text_lay = QVBoxLayout()
        text_lay.setSpacing(2)
        lbl_title = QLabel(title)
        lbl_title.setObjectName("CardTitle")
        lbl_title.setWordWrap(True)
        lbl_sub = QLabel(subtitle)
        lbl_sub.setObjectName("MutedText")
        lbl_sub.setWordWrap(True)
        text_lay.addWidget(lbl_title)
        text_lay.addWidget(lbl_sub)
        lay.addLayout(text_lay, 1)
        return card

    def _summary_text(self) -> tuple[str, str, str, str]:
        first = os.path.basename(self.paths[0].rstrip("\\/")) or self.paths[0]
        count = len(self.paths)
        more = tr("quick.more", " + {n} more").format(n=count - 1) if count > 1 else ""

        if self.mode is QuickMode.ENCRYPT:
            return (
                "mdi6.lock-outline",
                CLR_ACCENT,
                tr("quick.enc.title", "Lock “{first}”{more}").format(first=first, more=more),
                tr(
                    "quick.enc.sub",
                    "Set a password to pack everything into a single encrypted .adtn vault.",
                ),
            )
        if self.mode is QuickMode.DECRYPT:
            size = ""
            with contextlib.suppress(OSError):
                size = f" • {format_file_size(os.path.getsize(self.paths[0]))}"
            return (
                "mdi6.lock-open-outline",
                CLR_ACCENT,
                tr("quick.dec.title", "Open “{first}”").format(first=first),
                tr(
                    "quick.dec.sub", "Enter the password used when this vault was locked{size}."
                ).format(size=size),
            )
        return (
            "mdi6.alert-octagon-outline",
            CLR_DANGER,
            tr("quick.shred.title", "Permanently delete “{first}”{more}").format(
                first=first, more=more
            ),
            tr(
                "quick.shred.sub",
                "This cannot be undone. The file(s) will not go to the Recycle Bin.",
            ),
        )

    def _finalize_size(self):
        """Window fixed. ENCRYPT (scroll) di-cap ke layar agar tombol yang di-pin
        tak tertutup taskbar di layar kecil seperti 1366x768; DECRYPT/SHRED memakai
        tinggi konten apa adanya.
        """
        avail = QApplication.primaryScreen().availableGeometry()

        if self._use_scroll:
            self._scroll_content.adjustSize()
            margins = self._body_lay.contentsMargins()
            overhead = (
                self.title_bar.height()
                + margins.top()
                + margins.bottom()
                + self._body_lay.spacing()
                + self.btn.sizeHint().height()
            )
            desired = overhead + self._content_lay.sizeHint().height()
        else:
            self.body.adjustSize()
            desired = self.title_bar.height() + self.body.sizeHint().height()

        final_h = min(desired, avail.height() - 56)  # sisakan ruang taskbar/tepi
        self.setFixedSize(self._FIXED_W, final_h)

        geo = self.frameGeometry()
        geo.moveCenter(avail.center())
        # Jangan biarkan titlebar ketarik keluar tepi atas layar.
        self.move(geo.left(), max(avail.top(), geo.top()))

    # ── aksi utama: pola TabKunci (worker + progress + cancel) ───────────
    def _on_action(self):
        # 1) klik saat berjalan = cancel
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self._eta.reset()
            apply_cancelling_state(self.btn)
            return

        # 2) konfirmasi destruktif sebelum jalan
        if self.mode is QuickMode.ENCRYPT and self._options_panel.is_hapus_asli():
            if not self._confirm_delete_original():
                return
        if self.mode is QuickMode.SHRED and not self._confirm_shred():
            return

        # 3) susun worker per-mode
        worker = self._build_worker()
        if worker is None:  # mis. user batal memilih lokasi simpan
            return

        self.worker = worker
        self._set_busy(True)
        start_crypto_worker(self.worker, self._update_progress, self._on_done)

    def _build_worker(self) -> CryptoWorker | None:
        if self.mode is QuickMode.ENCRYPT:
            src0 = self.paths[0]
            if len(self.paths) == 1:
                default_path = f"{src0}.adtn"
            else:
                default_path = os.path.join(os.path.dirname(src0), "Secret_Vault.adtn")
            path_simpan, _ = QFileDialog.getSaveFileName(
                self,
                tr("quick.save", "Save Vault"),
                default_path,
                tr("quick.save.filter", "Locked File (*.adtn)"),
            )
            if not path_simpan:
                return None
            return CryptoWorker(
                kunci_brankas,
                list(self.paths),
                path_simpan,
                self._password_panel.get_password(),
                hapus_asli=self._options_panel.is_hapus_asli(),
                secure_wipe=self._options_panel.is_secure_wipe(),
                # Level KDF & kompresi mengikuti pilihan user — tanpa ini dialog mini
                # diam-diam memakai KDF default dan mengabaikan toggle Compress.
                kdf_params=kdf_params_for_level(get_settings().kdf_level()),
                compress=self._options_panel.is_compress(),
                parent=self,
            )

        if self.mode is QuickMode.DECRYPT:
            # Vault 2FA butuh keyfile yang tak bisa dipilih di dialog mini ini. Tanpa
            # cek ini, buka_brankas(password tanpa keyfile) melewati slot keyfile dan
            # gagal sebagai WRONG_PASSWORD yang menyesatkan. Arahkan ke app utama.
            if vault_info(self.paths[0]).get("requires_keyfile"):
                dlg = ModernMessageBox(
                    title=tr("quick.keyfile.title", "Keyfile required"),
                    message=tr(
                        "quick.keyfile.msg",
                        "This vault is protected by a keyfile (2FA). Open it from the "
                        "main Adyton Crypt app, where you can select the keyfile.",
                    ),
                    icon_name="mdi6.key-chain-variant",
                    icon_color=CLR_ACCENT,
                    parent=self,
                )
                dlg.btn_cancel.hide()
                dlg.btn_yes.setText(tr("common.ok", "OK"))
                dlg.exec()
                return None
            return CryptoWorker(
                buka_brankas,
                self.paths[0],
                self._password_panel.get_password(),
                parent=self,
            )

        # SHRED
        return CryptoWorker(_shred_paths, list(self.paths), False, parent=self)

    def _set_busy(self, busy: bool):
        if self._password_panel is not None:
            self._password_panel.setEnabled(not busy)
        if self._options_panel is not None:
            self._options_panel.set_busy(busy)

        if busy:
            self.btn.setProgressVisible(True, 0.0)
            self.btn.setTextLabels(
                self._busy_title(), tr("quick.busy.sub", "Preparing • Click to cancel")
            )
            self.btn.setEnabled(True)
            self.btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        else:
            self.btn.setProgressVisible(False)
            self.btn.setTextLabels(self._idle_title(), "")
            # Re-enable hanya jika input masih valid (SHRED selalu valid).
            if self.mode is QuickMode.SHRED:
                self.btn.setEnabled(True)

    def _update_progress(self, val: float):
        if self.worker and not self.worker.is_cancelled():
            mode_key = "buka" if self.mode is QuickMode.DECRYPT else "kunci"
            title, subtitle = format_progress_label(val, mode_key, self._eta.update(val))
            self.btn.setTextLabels(title, subtitle)
            self.btn.setProgressAnimated(val)

    def _on_done(self, result):
        self.worker = None
        status = result[0]
        msg = result[1] if len(result) > 1 else None
        self._set_busy(False)
        self._eta.reset()

        if status == VaultStatus.SUCCESS and msg == DELETE_ORIGINAL_FAILED_MESSAGE:
            # Vault jadi & terverifikasi, tapi sebagian sumber gagal dihapus.
            # Jangan auto-tutup: user harus sempat membaca bahwa file asli masih ada.
            logger.warning("Quick encrypt: vault dibuat, sebagian file asli gagal dihapus.")
            self.notif.show_msg("warn", f" {localize_core_message(msg)}", 10000)
            return

        if status == VaultStatus.SUCCESS:
            logger.info(f"Quick action sukses ({self.mode.name}): {msg}")
            self.notif.show_msg("ok", f" {self._success_text(msg)}", 3500)
            QTimer.singleShot(1200, self.close)  # auto-tutup setelah sukses
            return

        if status == VaultStatus.CANCELLED:
            self.notif.show_msg(
                "warn",
                tr("quick.cancelled", "Operation cancelled. No changes were made."),
                4000,
            )
            return

        if status == VaultStatus.OVERWRITE_NEEDED:
            # Vault sudah terverifikasi penuh; folder tujuan sudah ada. Tawarkan
            # konfirmasi Replace seperti di app utama — tanpa ini status jatuh ke
            # cabang error dan tampil sebagai "Couldn't open the vault. {nama}".
            self._confirm_overwrite(msg)
            return

        mode_key = "buka" if self.mode is QuickMode.DECRYPT else "kunci"
        user_msg = format_user_error(status, msg, mode_key)
        logger.error(f"Quick action gagal ({self.mode.name}): {msg}")
        self.notif.show_msg("err", user_msg, 8000)
        if self.mode is QuickMode.DECRYPT:
            # Window mini ini tak punya alur konfirmasi overwrite; jangan biarkan
            # tar terverifikasi (kalau OVERWRITE_NEEDED) menggantung di disk.
            cancel_pending_overwrite(self.paths[0])
            self._password_panel.reset_field()

    def _confirm_overwrite(self, name) -> None:
        """Konfirmasi Replace untuk DECRYPT saat folder tujuan sudah ada.

        Teks & kunci i18n sama dengan TabBuka. Bila user setuju, jalankan ulang
        dengan force=True — tar terverifikasi yang ditahan core dipakai ulang
        (resume), jadi tidak ada dekripsi ganda. Bila menolak, buang pending tar.
        """
        dialog = ModernMessageBox(
            title=tr("open.overwrite.title", "File Already Exists"),
            message=tr(
                "open.overwrite.msg",
                "A file or folder named '{name}' already exists at this location.\n\n"
                "Adyton will extract to a temporary folder first, and only replace the "
                "existing data once the vault opens successfully.\n\n"
                "Replace the existing data?",
            ).format(name=name),
            icon_name="mdi6.alert-octagon-outline",
            icon_color=CLR_DANGER,
            parent=self,
        )
        dialog.btn_yes.setText(tr("open.overwrite.replace", "Replace Data"))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            cancel_pending_overwrite(self.paths[0])
            self.notif.show_msg(
                "warn",
                tr("quick.cancelled", "Operation cancelled. No changes were made."),
                4000,
            )
            return

        # Password masih ada di panel (hanya di-reset pada jalur error); jalur
        # resume bahkan tidak memerlukannya selama cache pending masih segar.
        self.worker = CryptoWorker(
            buka_brankas,
            self.paths[0],
            self._password_panel.get_password(),
            True,
            parent=self,
        )
        self._set_busy(True)
        start_crypto_worker(self.worker, self._update_progress, self._on_done)

    # ── label & konfirmasi ───────────────────────────────────────────────
    def _idle_title(self) -> str:
        return {
            QuickMode.ENCRYPT: tr("quick.enc.action", "Lock to Vault"),
            QuickMode.DECRYPT: tr("quick.dec.action", "Open Vault"),
            QuickMode.SHRED: tr("quick.shred.action", "Securely Delete"),
        }[self.mode]

    def _busy_title(self) -> str:
        return {
            QuickMode.ENCRYPT: tr("quick.enc.busy", "Locking vault"),
            QuickMode.DECRYPT: tr("quick.dec.busy", "Opening vault"),
            QuickMode.SHRED: tr("quick.shred.busy", "Deleting"),
        }[self.mode]

    def _success_text(self, msg) -> str:
        if self.mode is QuickMode.ENCRYPT:
            return tr("quick.enc.ok", "Vault locked securely.")
        if self.mode is QuickMode.DECRYPT:
            return (
                tr("quick.dec.ok", "Vault opened: {name}").format(name=msg)
                if msg
                else tr("quick.dec.ok.noname", "Vault opened.")
            )
        return msg or tr("quick.shred.ok", "Deleted.")

    def _confirm_delete_original(self) -> bool:
        # Teks identik dengan Tab Kunci → pakai ulang kunci i18n yang sama.
        dialog = ModernMessageBox(
            title=tr("lock.dialog.delete.title", "Confirm Delete"),
            message=tr(
                "lock.dialog.delete.msg",
                "The original file or folder will be permanently deleted after the "
                "vault is created and verified.\n\n"
                "Make sure you have a backup of anything important before continuing.",
            ),
            parent=self,
        )
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _confirm_shred(self) -> bool:
        first = os.path.basename(self.paths[0].rstrip("\\/")) or self.paths[0]
        count = len(self.paths)
        target = (
            first if count == 1 else tr("quick.shred.confirm.count", "{n} items").format(n=count)
        )
        dialog = ModernMessageBox(
            title=tr("quick.shred.confirm.title", "Permanently Delete?"),
            message=tr(
                "quick.shred.confirm.msg",
                "“{target}” will be permanently deleted and will NOT go to the "
                "Recycle Bin. This action cannot be undone.\n\n"
                "Continue?",
            ).format(target=target),
            icon_name="mdi6.delete-forever-outline",
            icon_color=CLR_DANGER,
            parent=self,
        )
        return dialog.exec() == QDialog.DialogCode.Accepted

    def closeEvent(self, event):
        # Jangan biarkan proses keluar saat worker masih jalan tanpa peringatan.
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            if not self.worker.wait(5000):
                # Worker belum berhenti — menutup sekarang berarti membongkar
                # QThread yang masih hidup (crash saat proses keluar). Tahan
                # window; pembatalan tetap berjalan dan user bisa menutup lagi.
                self.notif.show_msg(
                    "warn",
                    tr(
                        "quick.closing.busy",
                        "Still cancelling — wait a moment, then close again.",
                    ),
                    4000,
                )
                event.ignore()
                return
        super().closeEvent(event)
