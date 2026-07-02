"""
Modul: tab_teks.py
Deskripsi: Controller untuk Tab "Enkripsi Teks" — enkripsi/dekripsi teks secara langsung,
           clipboard support, dan tampilan hasil inline dengan animasi slide-in.
"""

from __future__ import annotations

import qtawesome as qta
from cryptography.exceptions import InvalidTag
from loguru import logger
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.text_vault import (
    decrypt_text,
    encrypt_text,
    is_encrypted_text,
)

from .buttons import BigActionBtn
from .components.password_panel_teks import PasswordPanelTeks
from .components.text_input_card import (
    MAX_DECRYPT_CHARS,
    MAX_INPUT_CHARS,
    TextInputCard,
)
from .components.text_result_card import TextResultCard
from .constants import APP_NAME
from .i18n import register, tr
from .styles import (
    CLR_ON_ACCENT,
)
from .utils import CLIPBOARD_AUTO_CLEAR_MS, copy_to_clipboard_auto_clear
from .widgets import (
    AnimatedNotifBar,
    apply_shadow,
)

# ═══════════════════════════════════════════════════════════════════════════════
# WORKER
# ═══════════════════════════════════════════════════════════════════════════════


class TextCryptoWorker(QThread):
    """Worker ringan untuk enkripsi/dekripsi teks di background thread.

    Signal finished membawa (result_str, error_str).
    Jika sukses: error_str kosong. Jika gagal: result_str kosong.
    """

    finished = Signal(str, str)

    def __init__(self, func, *args, parent=None):
        super().__init__(parent)
        self._func = func
        self._args = args

    def run(self):
        try:
            result = self._func(*self._args)
            self.finished.emit(result, "")
        except (ValueError, InvalidTag) as exc:
            # Pesan ini kurasi dari core (path-free, mis. "Wrong password…").
            self.finished.emit("", str(exc))
        except Exception:
            # Catch-all: jangan kirim str(exc) mentah ke UI; detail ke log saja.
            logger.exception("TextCryptoWorker: error tak terduga")
            self.finished.emit(
                "", "An unexpected error occurred. Technical details were saved to the log."
            )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB TEKS — CONTROLLER UTAMA
# ═══════════════════════════════════════════════════════════════════════════════


class TabTeks(QWidget):
    """Controller tab Enkripsi Teks."""

    system_notification = Signal(str, str)
    status_changed = Signal(str, str, str)  # title, subtitle, state (untuk status pill)

    def __init__(self):
        super().__init__()
        self.worker: TextCryptoWorker | None = None
        self._is_password_valid = False
        self._has_text = False
        self._external_busy = False

        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(22)

        self.input_card = TextInputCard()
        self.password_panel = PasswordPanelTeks()

        h_cols = QHBoxLayout()
        h_cols.setSpacing(28)
        # [PERBAIKAN] Teks card mengambil sisa ruang (stretch=1), Password panel fix (stretch=0)
        h_cols.addWidget(self.input_card, 1)
        h_cols.addWidget(self.password_panel, 1)

        # Result card (starts hidden, slides in after operation)
        self.result_card = TextResultCard()

        # [PERBAIKAN] Kolom + hasil dibungkus QScrollArea agar tidak pernah
        # saling menimpa saat jendela diperkecil (mis. tinggi minimum 700px)
        # atau saat result card muncul. Tombol aksi tetap dipin di bawah.
        scroll_inner = QWidget()
        scroll_inner.setObjectName("TeksScrollInner")
        scroll_lay = QVBoxLayout(scroll_inner)
        scroll_lay.setContentsMargins(0, 0, 8, 0)  # ruang kecil agar scrollbar tak menempel kartu
        scroll_lay.setSpacing(22)
        scroll_lay.addLayout(h_cols)
        scroll_lay.addWidget(self.result_card)
        scroll_lay.addStretch(1)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(scroll_inner)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setObjectName("TeksScrollArea")
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("QScrollArea, #TeksScrollInner { background: transparent; }")
        main_layout.addWidget(self.scroll_area, 1)

        # Tombol aksi utama
        self.btn_aksi = BigActionBtn(
            tr("text.action.enc.title", "Encrypt Text"),
            tr("text.action.enc.sub", "Enter text and create a password to begin"),
            icon_name="mdi6.lock-outline",
        )
        register(self.btn_aksi, "a11y.btn.encrypt_text", "Encrypt Text button", "setAccessibleName")
        self.btn_aksi.setEnabled(False)
        self.btn_aksi.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        apply_shadow(self.btn_aksi, blur_radius=24, y_offset=5, opacity=85)
        main_layout.addWidget(self.btn_aksi)

        self.notif = AnimatedNotifBar(self)

    def _connect_signals(self):
        self.btn_aksi.clicked.connect(self._proses)
        self.input_card.text_changed.connect(self._on_text_changed)
        self.input_card.limit_reached.connect(self._on_limit_reached)
        self.password_panel.valid_state_changed.connect(self._on_password_valid_changed)
        self.password_panel.mode_changed.connect(self._on_mode_changed)
        self.password_panel.attach_return_event(self._proses)
        self.result_card._anim.finished.connect(self._scroll_to_result)

    # ── State management ──────────────────────────────────────────────────────

    def _on_text_changed(self, text: str):
        self._has_text = bool(text.strip())
        # Auto-detect mode: jika teks terlihat seperti hasil enkripsi, switch ke dekripsi
        if self._has_text and is_encrypted_text(text):
            if self.password_panel.get_mode() != "dekripsi":
                self.password_panel.set_mode("dekripsi")
        self.result_card.hide_result()
        self._validate_state()

    def _on_limit_reached(self, limit: int):
        self.notif.show_msg(
            "error",
            tr("text.limit", "Text reached the maximum of {n} characters.").format(n=f"{limit:,}"),
            3500,
        )

    def _on_password_valid_changed(self, valid: bool):
        self._is_password_valid = valid
        self.notif.hide_msg()
        self._validate_state()

    def _on_mode_changed(self, mode: str):
        is_enc = mode == "enkripsi"
        if is_enc:
            self.btn_aksi.setTextLabels(
                tr("text.action.enc.title", "Encrypt Text"),
                tr("text.action.enc.sub", "Enter text and create a password to begin"),
            )
            self.btn_aksi.icon_name = "mdi6.lock-outline"
            self.btn_aksi.lbl_icon.setPixmap(
                qta.icon("mdi6.lock-outline", color=CLR_ON_ACCENT).pixmap(22, 22)
            )
        else:
            self.btn_aksi.setTextLabels(
                tr("text.action.dec.title", "Decrypt Text"),
                tr("text.action.dec.sub", "Enter encrypted text and the password to open"),
            )
            self.btn_aksi.icon_name = "mdi6.lock-open-variant-outline"
            self.btn_aksi.lbl_icon.setPixmap(
                qta.icon("mdi6.lock-open-variant-outline", color=CLR_ON_ACCENT).pixmap(22, 22)
            )
        # Batas input mengikuti mode: plaintext (enkripsi) vs ciphertext (dekripsi).
        self.input_card.set_max_chars(MAX_INPUT_CHARS if is_enc else MAX_DECRYPT_CHARS)
        self.result_card.hide_result()
        self._validate_state()

    def _validate_state(self):
        if self.worker is not None or self._external_busy:
            self.btn_aksi.setEnabled(False)
            return
        ok = self._has_text and self._is_password_valid
        self.btn_aksi.setEnabled(ok)
        self.btn_aksi.setFocusPolicy(Qt.FocusPolicy.StrongFocus if ok else Qt.FocusPolicy.NoFocus)
        self._emit_status()

    def _emit_status(self):
        """Pancarkan status keamanan tab Teks untuk status pill di header."""
        if self.worker is not None:
            return
        if self._has_text and self._is_password_valid:
            is_enc = self.password_panel.get_mode() == "enkripsi"
            sub = (
                tr("text.status.ready.enc", "Text & password ready to encrypt")
                if is_enc
                else tr("text.status.ready.dec", "Text & password ready to decrypt")
            )
            self.status_changed.emit(tr("text.status.ready", "Ready to process"), sub, "ready")
        else:
            self.status_changed.emit(
                tr("status.aes", "AES-256 • GCM"),
                tr("status.local", "Local encryption active"),
                "idle",
            )

    # ── Proses enkripsi / dekripsi ────────────────────────────────────────────

    def _proses(self):
        if self.worker is not None or not self.btn_aksi.isEnabled():
            return

        text = self.input_card.get_text().strip()
        password = self.password_panel.get_password()
        mode = self.password_panel.get_mode()

        if not text:
            self.notif.show_msg("warn", tr("text.empty", "Text cannot be empty."), 3500)
            return
        if not password:
            self.notif.show_msg("warn", tr("text.pw_empty", "Password cannot be empty."), 3500)
            return

        func = encrypt_text if mode == "enkripsi" else decrypt_text

        self._set_busy(True, mode)
        self.result_card.hide_result()
        self.notif.hide_msg()

        self.worker = TextCryptoWorker(func, text, password, parent=self)
        self.worker.finished.connect(self._on_finished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def _set_busy(self, busy: bool, mode: str = "enkripsi"):
        self.input_card.set_busy(busy)
        self.password_panel.set_busy(busy)
        self.btn_aksi.setEnabled(not busy)

        if busy:
            label = (
                tr("text.processing.enc", "Encrypting text…")
                if mode == "enkripsi"
                else tr("text.processing.dec", "Decrypting text…")
            )
            self.btn_aksi.setTextLabels(tr("text.processing.title", "Processing…"), label)
            self.status_changed.emit(
                tr("text.status.processing", "Processing text"),
                tr("text.status.processing.sub", "Almost there"),
                "busy",
            )
        else:
            # Restore label sesuai mode saat ini
            self._on_mode_changed(self.password_panel.get_mode())

    def _scroll_to_result(self):
        # Hanya scroll saat kartu sedang DITAMPILKAN (maxHeight menuju 350),
        # bukan saat disembunyikan (menuju 0).
        if self.result_card.maximumHeight() <= 1:
            return
        # QTimer(0) memberi layout satu siklus untuk memperbarui rentang scroll.
        QTimer.singleShot(0, lambda: self.scroll_area.ensureWidgetVisible(self.result_card, 0, 40))

    def _on_finished(self, result: str, error: str):
        self.worker = None
        mode = self.password_panel.get_mode()
        self._set_busy(False, mode)

        if error:
            msg = _format_text_error(error, mode)
            self.notif.show_msg("error", msg, 6000)
            logger.warning(f"TabTeks error ({mode}): {error}")
        else:
            self.result_card.show_result(result, mode)
            # Auto-copy ke clipboard dengan auto-clear (penting untuk plaintext
            # hasil dekripsi yang sensitif — tidak tertinggal di clipboard).
            copy_to_clipboard_auto_clear(result)
            secs = CLIPBOARD_AUTO_CLEAR_MS // 1000
            is_enc = mode == "enkripsi"
            ok_msg = (
                tr(
                    "text.notif.enc.ok",
                    "✓ Text encrypted successfully — copied (auto-clears in {s}s).",
                )
                if is_enc
                else tr(
                    "text.notif.dec.ok",
                    "✓ Text decrypted successfully — copied (auto-clears in {s}s).",
                )
            )
            # Toast seragam dengan tab lain: judul = nama app, body = kalimat hasil singkat.
            notif_body = (
                tr(
                    "text.notif.enc.body",
                    "Text encrypted — copied to the clipboard, auto-clears in {s}s.",
                )
                if is_enc
                else tr(
                    "text.notif.dec.body",
                    "Text decrypted — copied to the clipboard, auto-clears in {s}s.",
                )
            )
            self.system_notification.emit(APP_NAME, notif_body.format(s=secs))
            self.notif.show_msg("ok", ok_msg.format(s=secs), 4000)
            logger.info(f"TabTeks: {mode} berhasil — {len(result)} karakter")

        self._validate_state()
        # Status pill: success/error setelah _validate_state agar tidak ditimpa.
        if error:
            self.status_changed.emit(
                tr("text.status.failed", "Failed"),
                tr("text.status.failed.sub", "Check your password or text format"),
                "error",
            )
        else:
            self.status_changed.emit(
                tr("text.status.success", "Success"),
                tr("text.status.success.sub", "Result copied to clipboard"),
                "success",
            )

    # ── External busy (dari tab lain yang sedang memproses file) ──────────────

    def set_external_busy(self, busy: bool):
        self._external_busy = busy
        self._validate_state()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _format_text_error(error: str, mode: str) -> str:
    err_lower = error.lower()
    if "wrong password" in err_lower or "invalidtag" in err_lower or "modified" in err_lower:
        return tr(
            "text.err.wrong",
            "Incorrect password, or the encrypted text has been modified or corrupted.",
        )
    if "format" in err_lower or "valid" in err_lower or "adtn_text" in err_lower:
        return tr(
            "text.err.format",
            "Invalid format. Make sure the encrypted text starts with 'ADTN_TEXT:1:'.",
        )
    if "empty" in err_lower:
        if "password" in err_lower:
            return tr("text.err.empty_pw", "Password cannot be empty.")
        return tr("text.err.empty_text", "Text cannot be empty.")
    if mode == "enkripsi":
        return tr("text.err.enc", "Encryption failed. {detail}").format(detail=error)
    return tr("text.err.dec", "Decryption failed. {detail}").format(detail=error)
