"""
Modul: tab_teks.py
Deskripsi: Controller untuk Tab "Enkripsi Teks" — enkripsi/dekripsi teks secara langsung,
           clipboard support, dan tampilan hasil inline dengan animasi slide-in.
"""

from __future__ import annotations

import secrets
import string

import qtawesome as qta
from cryptography.exceptions import InvalidTag
from loguru import logger
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from zxcvbn import zxcvbn

from core.text_vault import (
    TEXT_VAULT_PREFIX,
    decrypt_text,
    encrypt_text,
    is_encrypted_text,
)

from .buttons import BigActionBtn
from .qr_dialog import QR_MAX_CHARS, QRShareDialog
from .styles import (
    CLR_ACCENT,
    CLR_BORDER,
    CLR_DANGER,
    CLR_INSET,
    CLR_ON_ACCENT,
    CLR_SUCCESS,
    CLR_TEXT_DIM,
    CLR_TEXT_MAIN,
    CLR_TEXT_MUTED,
    CLR_WARN,
    FONT_MONO,
)
from .widgets import AnimatedNotifBar, PasswordLineEdit, apply_shadow

MAX_INPUT_CHARS = 50_000
MAX_DECRYPT_CHARS = 300_000

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
            self.finished.emit("", str(exc))
        except Exception as exc:
            logger.exception("TextCryptoWorker: error tak terduga")
            self.finished.emit("", f"Unexpected error: {exc}")


# ═══════════════════════════════════════════════════════════════════════════════
# TEXT INPUT CARD
# ═══════════════════════════════════════════════════════════════════════════════


class TextInputCard(QFrame):
    """Card kiri — area input teks dengan tombol paste dan clear."""

    text_changed = Signal(str)
    limit_reached = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        apply_shadow(self, blur_radius=30, opacity=40)
        self._max_chars = MAX_INPUT_CHARS  # diubah sesuai mode via set_max_chars()
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(10)

        # ── Header ────────────────────────────────────────────────────────────
        row_hdr = QHBoxLayout()
        row_hdr.setSpacing(10)

        icon_txt = QLabel()
        icon_txt.setPixmap(qta.icon("mdi6.text-box-edit-outline", color=CLR_ACCENT).pixmap(32, 32))
        icon_txt.setAlignment(Qt.AlignmentFlag.AlignTop)

        v_hdr_txt = QVBoxLayout()
        v_hdr_txt.setSpacing(3)
        lbl_title = QLabel("Text input")
        lbl_title.setObjectName("CardTitle")
        lbl_sub = QLabel("Type or paste the text you want to encrypt/decrypt")
        lbl_sub.setObjectName("CardSubtitle")
        lbl_sub.setWordWrap(True)
        v_hdr_txt.addWidget(lbl_title)
        v_hdr_txt.addWidget(lbl_sub)

        # Tombol paste di kanan header
        self.btn_paste = QPushButton(" Paste")
        self.btn_paste.setIcon(qta.icon("mdi6.clipboard-arrow-down-outline", color="white"))
        self.btn_paste.setFixedHeight(36)
        self.btn_paste.setObjectName("BtnGen")
        self.btn_paste.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_paste.setAccessibleName("Paste text from clipboard")
        self.btn_paste.clicked.connect(self._paste_clipboard)

        row_hdr.addWidget(icon_txt)
        row_hdr.addLayout(v_hdr_txt, 1)
        row_hdr.addSpacing(8)
        row_hdr.addWidget(self.btn_paste, alignment=Qt.AlignmentFlag.AlignTop)
        lay.addLayout(row_hdr)

        lay.addSpacing(4)

        # ── Text area ─────────────────────────────────────────────────────────
        self.text_edit = QTextEdit()
        self.text_edit.setObjectName("TextInputArea")
        self.text_edit.setPlaceholderText(
            "Type or paste text here…\n\n"
            "Tip: Paste encrypted text (ADTN_TEXT:1:…) to decrypt it."
        )
        self.text_edit.setMinimumHeight(180)
        self.text_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.text_edit.setTabChangesFocus(True)

        # [PERBAIKAN] Styling eksplisit untuk Dark Mode
        self.text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {CLR_INSET};
                color: {CLR_TEXT_MAIN};
                border: 1.5px solid {CLR_BORDER};
                border-radius: 14px;
                padding: 12px;
                font-size: 10.5pt;
            }}
            QTextEdit:focus {{
                border: 1.5px solid {CLR_ACCENT};
                background-color: #0E1B21;
            }}
        """)

        self.text_edit.textChanged.connect(self._on_text_changed)
        lay.addWidget(self.text_edit, 1)

        # ── Footer: jumlah karakter + tombol clear ────────────────────────────
        row_footer = QHBoxLayout()
        row_footer.setSpacing(8)

        self.lbl_char_count = QLabel("0 characters")
        self.lbl_char_count.setObjectName("MutedText")
        self.lbl_char_count.setStyleSheet(f"font-size: 8.5pt; color: {CLR_TEXT_MUTED};")

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setIcon(qta.icon("mdi6.delete-outline", color=CLR_TEXT_MUTED))
        self.btn_clear.setObjectName("BtnTransparent")
        self.btn_clear.setFixedHeight(34)
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setAccessibleName("Clear input text")
        self.btn_clear.clicked.connect(self.clear_text)

        row_footer.addWidget(self.lbl_char_count)
        row_footer.addStretch()
        row_footer.addWidget(self.btn_clear)
        lay.addLayout(row_footer)

    # ── Slots ────────────────────────────────────────────────────────────────

    def set_max_chars(self, n: int):
        """Atur batas panjang input sesuai mode (enkripsi/dekripsi)."""
        self._max_chars = n
        self._on_text_changed()  # terapkan ulang batas + perbarui counter

    def _on_text_changed(self):
        text = self.text_edit.toPlainText()
        n = len(text)

        # Teks terenkripsi (diawali prefix ADTN_TEXT) JANGAN pernah dipotong:
        # ciphertext jauh lebih panjang dari plaintext, dan memotongnya membuat
        # dekripsi gagal. Deteksi via prefix agar berlaku bahkan sebelum mode
        # otomatis berganti ke dekripsi.
        looks_encrypted = text.lstrip().startswith(TEXT_VAULT_PREFIX[:10])
        limit = MAX_DECRYPT_CHARS if looks_encrypted else self._max_chars

        # Batasi panjang: jika melebihi limit efektif, potong dan beri tahu.
        if n > limit:
            cursor = self.text_edit.textCursor()
            pos = cursor.position()
            self.text_edit.blockSignals(True)
            self.text_edit.setPlainText(text[:limit])
            self.text_edit.blockSignals(False)
            cursor.setPosition(min(pos, limit))
            self.text_edit.setTextCursor(cursor)
            text = self.text_edit.toPlainText()
            n = len(text)
            self.limit_reached.emit(limit)

        # Counter merah saat di batas (hanya relevan untuk plaintext/enkripsi).
        if n >= limit:
            self.lbl_char_count.setStyleSheet(f"font-size: 8.5pt; color: {CLR_DANGER};")
            self.lbl_char_count.setText(f"{n:,} / {limit:,} characters (max)")
        else:
            self.lbl_char_count.setStyleSheet(f"font-size: 8.5pt; color: {CLR_TEXT_MUTED};")
            self.lbl_char_count.setText(f"{n:,} characters")
        self.text_changed.emit(text)

    def _paste_clipboard(self):
        clipboard = QGuiApplication.clipboard()
        text = clipboard.text()
        if text:
            self.text_edit.setPlainText(text)
        else:
            self.text_edit.setPlaceholderText("Clipboard is empty or contains no text.")

    # ── Public API ───────────────────────────────────────────────────────────

    def get_text(self) -> str:
        return self.text_edit.toPlainText()

    def clear_text(self):
        self.text_edit.clear()

    def set_busy(self, busy: bool):
        self.text_edit.setReadOnly(busy)
        self.btn_paste.setEnabled(not busy)
        self.btn_clear.setEnabled(not busy)


# ═══════════════════════════════════════════════════════════════════════════════
# TEXT RESULT CARD  (slide-in setelah operasi berhasil)
# ═══════════════════════════════════════════════════════════════════════════════


class TextResultCard(QFrame):
    """Card hasil enkripsi/dekripsi — muncul dengan animasi slide-in."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        apply_shadow(self, blur_radius=30, opacity=40)
        self._mode = "enkripsi"
        self._build_ui()

        # Animasi slide-in: mulai dari maxHeight=0
        self.setMaximumHeight(0)
        self.setMinimumHeight(0)
        self._anim = QPropertyAnimation(self, b"maximumHeight")
        self._anim.setDuration(320)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(10)

        # ── Header ────────────────────────────────────────────────────────────
        row_hdr = QHBoxLayout()
        row_hdr.setSpacing(10)

        self.icon_result = QLabel()
        self.icon_result.setPixmap(
            qta.icon("mdi6.check-circle-outline", color=CLR_SUCCESS).pixmap(28, 28)
        )

        v_hdr = QVBoxLayout()
        v_hdr.setSpacing(2)
        self.lbl_result_title = QLabel("Encryption Result")
        self.lbl_result_title.setObjectName("CardTitle")
        self.lbl_result_sub = QLabel("Copy and save the encrypted text below")
        self.lbl_result_sub.setObjectName("CardSubtitle")
        v_hdr.addWidget(self.lbl_result_title)
        v_hdr.addWidget(self.lbl_result_sub)

        self.btn_copy = QPushButton(" Copy to Clipboard")
        self.btn_copy.setIcon(qta.icon("mdi6.content-copy", color="white"))
        self.btn_copy.setFixedHeight(36)
        self.btn_copy.setObjectName("BtnGen")
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.setAccessibleName("Copy result to clipboard")
        self.btn_copy.clicked.connect(self._copy_to_clipboard)

        self.btn_qr = QPushButton(" QR")
        self.btn_qr.setIcon(qta.icon("mdi6.qrcode", color="white"))
        self.btn_qr.setFixedHeight(36)
        self.btn_qr.setObjectName("BtnGen")
        self.btn_qr.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_qr.setAccessibleName("Show QR code of the encryption result")
        self.btn_qr.setToolTip(
            "Show the encryption result as a QR code to scan with a phone camera"
        )
        self.btn_qr.clicked.connect(self._show_qr)
        self.btn_qr.hide()

        row_hdr.addWidget(self.icon_result, alignment=Qt.AlignmentFlag.AlignTop)
        row_hdr.addLayout(v_hdr, 1)
        row_hdr.addSpacing(8)
        row_hdr.addWidget(self.btn_qr, alignment=Qt.AlignmentFlag.AlignTop)
        row_hdr.addWidget(self.btn_copy, alignment=Qt.AlignmentFlag.AlignTop)
        lay.addLayout(row_hdr)

        lay.addSpacing(4)

        # ── Output text area ──────────────────────────────────────────────────
        self.text_output = QTextEdit()
        self.text_output.setObjectName("TextOutputArea")
        self.text_output.setReadOnly(True)
        self.text_output.setMinimumHeight(100)
        self.text_output.setMaximumHeight(160)

        # [PERBAIKAN] Styling eksplisit untuk Dark Mode
        self.text_output.setStyleSheet(f"""
            QTextEdit {{
                background-color: {CLR_INSET};
                color: {CLR_ACCENT};
                border: 1.5px solid {CLR_BORDER};
                border-radius: 14px;
                padding: 12px;
                font-family: {FONT_MONO};
                font-size: 10pt;
            }}
        """)

        lay.addWidget(self.text_output)

        # ── Footer ────────────────────────────────────────────────────────────
        row_footer = QHBoxLayout()
        self.lbl_out_count = QLabel("0 characters")
        self.lbl_out_count.setObjectName("MutedText")
        self.lbl_out_count.setStyleSheet(f"font-size: 8.5pt; color: {CLR_TEXT_MUTED};")
        self.lbl_copy_confirm = QLabel("")
        self.lbl_copy_confirm.setStyleSheet(
            f"font-size: 8.5pt; font-weight: 500; color: {CLR_SUCCESS};"
        )
        row_footer.addWidget(self.lbl_out_count)
        row_footer.addStretch()
        row_footer.addWidget(self.lbl_copy_confirm)
        lay.addLayout(row_footer)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _copy_to_clipboard(self):
        text = self.text_output.toPlainText()
        if text:
            QGuiApplication.clipboard().setText(text)
            self.lbl_copy_confirm.setText("✓ Copied!")
            from PySide6.QtCore import QTimer

            QTimer.singleShot(2500, lambda: self.lbl_copy_confirm.setText(""))

    def _show_qr(self):
        text = self.text_output.toPlainText()
        if not text:
            return
        dialog = QRShareDialog(text, parent=self)
        dialog.exec()

    # ── Public API ────────────────────────────────────────────────────────────

    def show_result(self, text: str, mode: str):
        """Tampilkan hasil dan jalankan animasi slide-in."""
        self._mode = mode

        self.text_output.setPlainText(text)
        n = len(text)
        self.lbl_out_count.setText(f"{n:,} characters")
        self.lbl_copy_confirm.setText("")

        if mode == "enkripsi":
            self.lbl_result_title.setText("Encryption Result")
            self.lbl_result_sub.setText(
                "Copy and save this encrypted text — it can only be decrypted with the same password"
            )
            self.icon_result.setPixmap(
                qta.icon("mdi6.lock-check-outline", color=CLR_ACCENT).pixmap(28, 28)
            )
            self.btn_qr.setVisible(n <= QR_MAX_CHARS)
        else:
            self.lbl_result_title.setText("Decryption Result")
            self.lbl_result_sub.setText("Your original text has been restored")
            self.icon_result.setPixmap(
                qta.icon("mdi6.check-circle-outline", color=CLR_SUCCESS).pixmap(28, 28)
            )
            self.btn_qr.hide()

        self._anim.stop()
        self._anim.setStartValue(self.maximumHeight())
        self._anim.setEndValue(350)
        self._anim.start()

    def hide_result(self):
        """Sembunyikan card dengan animasi."""
        self._anim.stop()
        self._anim.setStartValue(self.maximumHeight())
        self._anim.setEndValue(0)
        self._anim.start()


# ═══════════════════════════════════════════════════════════════════════════════
# PASSWORD PANEL TEKS
# ═══════════════════════════════════════════════════════════════════════════════

_STRENGTH_COLORS = [CLR_DANGER, CLR_WARN, CLR_ACCENT, CLR_SUCCESS]
_STRENGTH_LABELS = ["Weak", "Fair", "Strong", "Very Strong"]


def _pw_score(pw: str) -> int:
    """Return 0-3 (indeks ke STRENGTH_COLORS/LABELS). -1 jika kosong."""
    if not pw:
        return -1
    skor = zxcvbn(pw)["score"]
    return 0 if skor <= 1 else skor - 1


def _password_rules(pw: str) -> list[bool]:
    """Lima kriteria checklist password — sama persis dengan Tab Kunci.

    Urutan: panjang ≥ 8, huruf besar, huruf kecil, angka, simbol.
    """
    return [
        len(pw) >= 8,
        any(c.isupper() for c in pw),
        any(c.islower() for c in pw),
        any(c.isdigit() for c in pw),
        any(not c.isalnum() and not c.isspace() for c in pw),
    ]


class PasswordPanelTeks(QFrame):
    """Panel kanan: mode toggle (enkripsi/dekripsi) + password input."""

    valid_state_changed = Signal(bool)
    mode_changed = Signal(str)  # "enkripsi" | "dekripsi"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        apply_shadow(self, blur_radius=30, opacity=40)
        self._current_mode = "enkripsi"
        self._strength_visible = False
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(10)

        # ── Header ────────────────────────────────────────────────────────────
        row_hdr = QHBoxLayout()
        row_hdr.setSpacing(10)
        icon_key = QLabel()
        icon_key.setPixmap(qta.icon("mdi6.key-variant", color=CLR_WARN).pixmap(32, 32))
        icon_key.setAlignment(Qt.AlignmentFlag.AlignTop)

        v_hdr = QVBoxLayout()
        v_hdr.setSpacing(3)
        self.lbl_card_title = QLabel("Set a Password")
        self.lbl_card_title.setObjectName("CardTitle")
        self.lbl_card_sub = QLabel("A strong password keeps your text safe")
        self.lbl_card_sub.setObjectName("CardSubtitle")
        self.lbl_card_sub.setWordWrap(True)
        v_hdr.addWidget(self.lbl_card_title)
        v_hdr.addWidget(self.lbl_card_sub)

        # Tombol generate password (hanya muncul di mode enkripsi)
        self.btn_gen = QPushButton(" Generator")
        self.btn_gen.setIcon(qta.icon("mdi6.creation", color="white"))
        self.btn_gen.setFixedHeight(36)
        self.btn_gen.setObjectName("BtnGen")
        self.btn_gen.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_gen.setAccessibleName("Generate Strong Password")
        self.btn_gen.clicked.connect(self._generate_pw)

        row_hdr.addWidget(icon_key)
        row_hdr.addLayout(v_hdr, 1)
        row_hdr.addSpacing(8)
        row_hdr.addWidget(self.btn_gen, alignment=Qt.AlignmentFlag.AlignTop)
        lay.addLayout(row_hdr)

        # ── Mode toggle ───────────────────────────────────────────────────────
        toggle_container = QFrame()
        toggle_container.setObjectName("TabContainer")
        toggle_container.setFixedHeight(38)
        lay_toggle = QHBoxLayout(toggle_container)
        lay_toggle.setContentsMargins(3, 3, 3, 3)
        lay_toggle.setSpacing(3)

        self.btn_mode_enkripsi = QPushButton(" Encrypt")
        self.btn_mode_enkripsi.setIcon(
            qta.icon("mdi6.lock-plus-outline", color=CLR_TEXT_DIM, color_on=CLR_ON_ACCENT)
        )
        self.btn_mode_enkripsi.setIconSize(QSize(16, 16))
        self.btn_mode_enkripsi.setObjectName("TabBtn")
        self.btn_mode_enkripsi.setCheckable(True)
        self.btn_mode_enkripsi.setChecked(True)
        self.btn_mode_enkripsi.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self.btn_mode_dekripsi = QPushButton(" Decrypt")
        self.btn_mode_dekripsi.setIcon(
            qta.icon("mdi6.lock-open-variant-outline", color=CLR_TEXT_DIM, color_on=CLR_ON_ACCENT)
        )
        self.btn_mode_dekripsi.setIconSize(QSize(16, 16))
        self.btn_mode_dekripsi.setObjectName("TabBtn")
        self.btn_mode_dekripsi.setCheckable(True)
        self.btn_mode_dekripsi.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self.btn_mode_enkripsi, 0)
        self._mode_group.addButton(self.btn_mode_dekripsi, 1)
        self._mode_group.buttonClicked.connect(self._on_mode_button_clicked)

        lay_toggle.addWidget(self.btn_mode_enkripsi)
        lay_toggle.addWidget(self.btn_mode_dekripsi)
        lay.addWidget(toggle_container)

        # ── Password utama ────────────────────────────────────────────────────
        self.lbl_pw1 = QLabel("Password")
        self.lbl_pw1.setObjectName("SectionLabel")
        lay.addWidget(self.lbl_pw1)

        self.entry_pw1 = PasswordLineEdit("Type your password here…")
        self.entry_pw1.setAccessibleName("Text encryption password")
        self.entry_pw1.textChanged.connect(self._on_pw1_changed)
        lay.addWidget(self.entry_pw1)

        # ── Strength bar (enkripsi saja) ───────────────────────────────────────
        self._strength_widget = QWidget()
        self._strength_widget.setMaximumHeight(0)
        self._strength_widget.setMinimumHeight(0)

        lay_strength = QVBoxLayout(self._strength_widget)
        lay_strength.setContentsMargins(0, 4, 0, 0)
        lay_strength.setSpacing(4)

        # 4 segmen bar
        row_bars = QHBoxLayout()
        row_bars.setSpacing(4)
        self._strength_bars: list[QFrame] = []
        for _ in range(4):
            bar = QFrame()
            bar.setFixedHeight(4)
            bar.setStyleSheet(f"border-radius: 2px; background-color: {CLR_BORDER};")
            self._strength_bars.append(bar)
            row_bars.addWidget(bar)
        lay_strength.addLayout(row_bars)

        self.lbl_strength = QLabel("")
        self.lbl_strength.setStyleSheet("font-size: 8.5pt;")
        lay_strength.addWidget(self.lbl_strength)

        self._anim_strength = QPropertyAnimation(self._strength_widget, b"maximumHeight")
        self._anim_strength.setDuration(220)
        self._anim_strength.setEasingCurve(QEasingCurve.Type.InOutCubic)

        lay.addWidget(self._strength_widget)

        # ── Checklist kriteria password (enkripsi saja) ───────────────────────
        # Disamakan dengan Tab Kunci: tombol baru aktif hanya bila semua kriteria
        # terpenuhi + skor zxcvbn cukup. Teks sering dibagikan, jadi gate-nya sama.
        self._checklist_widget = self._build_checklist()
        lay.addWidget(self._checklist_widget)

        # ── Password konfirmasi (enkripsi saja) ───────────────────────────────
        self._confirm_widget = QWidget()
        self._confirm_widget.setMaximumHeight(0)
        self._confirm_widget.setMinimumHeight(0)

        lay_confirm = QVBoxLayout(self._confirm_widget)
        lay_confirm.setContentsMargins(0, 0, 0, 0)
        lay_confirm.setSpacing(6)

        lbl_pw2 = QLabel("Confirm Password")
        lbl_pw2.setObjectName("SectionLabel")
        lay_confirm.addWidget(lbl_pw2)

        self.entry_pw2 = PasswordLineEdit("Repeat password…")
        self.entry_pw2.setAccessibleName("Confirm text encryption password")
        self.entry_pw2.textChanged.connect(self._on_pw2_changed)
        lay_confirm.addWidget(self.entry_pw2)

        self.lbl_match = QLabel("")
        self.lbl_match.setObjectName("PwMatchLabel")
        lay_confirm.addWidget(self.lbl_match)

        self._anim_confirm = QPropertyAnimation(self._confirm_widget, b"maximumHeight")
        self._anim_confirm.setDuration(220)
        self._anim_confirm.setEasingCurve(QEasingCurve.Type.InOutCubic)

        lay.addWidget(self._confirm_widget)

        lay.addSpacing(10)

        # ── Tips ──────────────────────────────────────────────────────────────
        self._tips_box = self._build_tips_box()
        lay.addWidget(self._tips_box)

        # Inisialisasi ke mode enkripsi
        self._apply_mode("enkripsi", animated=False)

    # ── Tips builder ──────────────────────────────────────────────────────────

    def _build_tips_box(self) -> QFrame:
        box = QFrame()
        box.setObjectName("TipsBox")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(7)

        self._tips: list[tuple[str, str]] = [
            (
                "mdi6.shield-key-outline",
                "Your password can't be recovered. Keep it somewhere safe.",
            ),
            (
                "mdi6.clipboard-text-outline",
                "The encrypted result can be saved anywhere — email, notes, chat.",
            ),
            ("mdi6.lock-alert-outline", "To decrypt, use the exact same password you set here."),
        ]
        self._tip_labels: list[QLabel] = []

        for icon_name, text in self._tips:
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl_ic = QLabel()
            lbl_ic.setPixmap(qta.icon(icon_name, color=CLR_ACCENT).pixmap(14, 14))
            lbl_ic.setFixedSize(14, 14)
            row.addWidget(lbl_ic, alignment=Qt.AlignmentFlag.AlignTop)
            lbl_tx = QLabel(text)
            lbl_tx.setWordWrap(True)
            lbl_tx.setObjectName("TipText")
            self._tip_labels.append(lbl_tx)
            row.addWidget(lbl_tx, 1)
            lay.addLayout(row)

        return box

    # ── Mode switching ────────────────────────────────────────────────────────

    def _on_mode_button_clicked(self, button: QPushButton):
        mode = "enkripsi" if self._mode_group.id(button) == 0 else "dekripsi"
        if mode != self._current_mode:
            self._apply_mode(mode, animated=True)
            self.mode_changed.emit(mode)

    def _apply_mode(self, mode: str, animated: bool = True):
        self._current_mode = mode
        is_enc = mode == "enkripsi"

        self.lbl_card_title.setText("Set a Password" if is_enc else "Enter Your Password")
        self.lbl_card_sub.setText(
            "A strong password keeps your text safe"
            if is_enc
            else "Enter the password you used during encryption"
        )
        self.btn_gen.setVisible(is_enc)
        self._checklist_widget.setVisible(is_enc)
        self.lbl_pw1.setText("Password" if is_enc else "Password")

        # Strength bar TIDAK auto-muncul saat pindah mode — baru tampil ketika
        # user mulai mengetik password (lihat _on_pw1_changed), konsisten dgn Tab Kunci.
        target_strength = 0
        target_confirm = 92 if is_enc else 0

        if animated:
            for anim, target in [
                (self._anim_strength, target_strength),
                (self._anim_confirm, target_confirm),
            ]:
                anim.stop()
                anim.setStartValue(anim.targetObject().maximumHeight())
                anim.setEndValue(target)
                anim.start()
        else:
            self._strength_widget.setMaximumHeight(target_strength)
            self._strength_widget.setMinimumHeight(0)
            self._confirm_widget.setMaximumHeight(target_confirm)
            self._confirm_widget.setMinimumHeight(0)

        # Reset field
        self.entry_pw1.clear()
        self.entry_pw2.clear()
        self.lbl_match.setText("")
        self._strength_visible = False
        self._update_strength_bars(-1)
        self._update_checklist("")
        self._check_valid()

    # ── Password validation ───────────────────────────────────────────────────

    def _on_pw1_changed(self, text: str):
        if self._current_mode == "enkripsi":
            # Reveal/hide strength bar mengikuti ada-tidaknya input (spt Tab Kunci)
            if not text:
                if self._strength_visible:
                    self._strength_visible = False
                    self._anim_strength.stop()
                    self._anim_strength.setStartValue(self._strength_widget.maximumHeight())
                    self._anim_strength.setEndValue(0)
                    self._anim_strength.start()
            else:
                if not self._strength_visible:
                    self._strength_visible = True
                    self._anim_strength.stop()
                    self._anim_strength.setStartValue(self._strength_widget.maximumHeight())
                    self._anim_strength.setEndValue(44)
                    self._anim_strength.start()
                self._update_strength_bars(_pw_score(text))
            self._update_checklist(text)
            self._update_match_label()
        self._check_valid()

    def _on_pw2_changed(self, _: str):
        self._update_match_label()
        self._check_valid()

    def _update_strength_bars(self, score: int):
        for i, bar in enumerate(self._strength_bars):
            if score >= 0 and i <= score:
                color = _STRENGTH_COLORS[score]
                bar.setStyleSheet(f"border-radius: 2px; background-color: {color};")
            else:
                bar.setStyleSheet(f"border-radius: 2px; background-color: {CLR_BORDER};")
        if score >= 0:
            label = _STRENGTH_LABELS[score]
            color = _STRENGTH_COLORS[score]
            self.lbl_strength.setText(f"Password strength: {label}")
            self.lbl_strength.setStyleSheet(f"font-size: 8.5pt; color: {color};")
        else:
            self.lbl_strength.setText("")

    def _build_checklist(self) -> QWidget:
        """Checklist 5 kriteria, tata letak mirror Tab Kunci."""
        widget = QWidget()
        grid = QGridLayout(widget)
        grid.setContentsMargins(4, 8, 4, 2)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        def _item(text: str):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            icon = QLabel()
            icon.setPixmap(qta.icon("mdi6.check-circle-outline", color=CLR_BORDER).pixmap(16, 16))
            lbl = QLabel(text)
            lbl.setObjectName("ChecklistLabel")
            lbl.setProperty("valid", False)
            lbl.setWordWrap(True)
            row.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)
            row.addWidget(lbl, 1)
            return row, icon, lbl

        l1, self.chk_len_icon, self.chk_len_lbl = _item("At least 8 characters")
        l2, self.chk_upper_icon, self.chk_upper_lbl = _item("Uppercase letter (A-Z)")
        l3, self.chk_lower_icon, self.chk_lower_lbl = _item("Lowercase letter (a-z)")
        l4, self.chk_digit_icon, self.chk_digit_lbl = _item("Number (0-9)")
        l5, self.chk_sym_icon, self.chk_sym_lbl = _item("Symbol (!@#$%^&*)")

        grid.addLayout(l1, 0, 0)
        grid.addLayout(l4, 0, 1)
        grid.addLayout(l2, 1, 0)
        grid.addLayout(l5, 1, 1)
        grid.addLayout(l3, 2, 0)
        return widget

    def _update_checklist(self, pw: str) -> None:
        items = [
            (self.chk_len_icon, self.chk_len_lbl),
            (self.chk_upper_icon, self.chk_upper_lbl),
            (self.chk_lower_icon, self.chk_lower_lbl),
            (self.chk_digit_icon, self.chk_digit_lbl),
            (self.chk_sym_icon, self.chk_sym_lbl),
        ]
        for ok, (icon, lbl) in zip(_password_rules(pw), items, strict=True):
            if ok:
                icon.setPixmap(qta.icon("mdi6.check-circle", color=CLR_SUCCESS).pixmap(16, 16))
            else:
                icon.setPixmap(
                    qta.icon("mdi6.check-circle-outline", color=CLR_BORDER).pixmap(16, 16)
                )
            lbl.setProperty("valid", ok)
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)

    def _update_match_label(self):
        pw1 = self.entry_pw1.text()
        pw2 = self.entry_pw2.text()
        if not pw2:
            self.lbl_match.setText("")
            return
        if pw1 == pw2:
            self.lbl_match.setText("✓ Passwords match")
            self.lbl_match.setStyleSheet(
                f"font-size: 8.5pt; font-weight: 500; color: {CLR_SUCCESS};"
            )
        else:
            self.lbl_match.setText("✗ Passwords don't match")
            self.lbl_match.setStyleSheet(
                f"font-size: 8.5pt; font-weight: 500; color: {CLR_DANGER};"
            )

    def _check_valid(self):
        pw1 = self.entry_pw1.text()
        if self._current_mode == "enkripsi":
            pw2 = self.entry_pw2.text()
            # Gate disamakan dengan Tab Kunci: semua kriteria checklist terpenuhi
            # + skor zxcvbn cukup (≥1 setelah remap = "Fair"+) + konfirmasi cocok.
            rules_ok = all(_password_rules(pw1))
            is_strong_enough = _pw_score(pw1) >= 1
            ok = bool(pw1) and pw1 == pw2 and rules_ok and is_strong_enough
        else:
            ok = bool(pw1)
        self.valid_state_changed.emit(ok)

    # ── Password generator ────────────────────────────────────────────────────

    def _generate_pw(self):
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
        # Pastikan hasil generate selalu lolos checklist (mirror Tab Kunci),
        # supaya tombol aksi tidak ikut nonaktif setelah generate.
        while True:
            pw = "".join(secrets.choice(alphabet) for _ in range(20))
            if all(_password_rules(pw)):
                break
        self.entry_pw1.setText(pw)
        self.entry_pw2.setText(pw)

    # ── Public API ────────────────────────────────────────────────────────────

    def get_mode(self) -> str:
        return self._current_mode

    def get_password(self) -> str:
        return self.entry_pw1.text()

    def is_valid(self) -> bool:
        pw1 = self.entry_pw1.text()
        if self._current_mode == "enkripsi":
            return (
                bool(pw1)
                and pw1 == self.entry_pw2.text()
                and all(_password_rules(pw1))
                and _pw_score(pw1) >= 1
            )
        return bool(pw1)

    def reset(self):
        self.entry_pw1.clear()
        self.entry_pw2.clear()
        self.lbl_match.setText("")
        self._update_strength_bars(-1)
        self.valid_state_changed.emit(False)

    def set_busy(self, busy: bool):
        self.entry_pw1.setEnabled(not busy)
        self.entry_pw2.setEnabled(not busy)
        self.btn_gen.setEnabled(not busy)
        self.btn_mode_enkripsi.setEnabled(not busy)
        self.btn_mode_dekripsi.setEnabled(not busy)

    def attach_return_event(self, callback):
        """Daftarkan callback Enter di field password."""
        self.entry_pw1.line_edit.returnPressed.connect(callback)
        self.entry_pw2.line_edit.returnPressed.connect(callback)


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
            "Encrypt Text",
            "Enter text and create a password to begin",
            icon_name="mdi6.lock-plus",
        )
        self.btn_aksi.setAccessibleName("Encrypt Text button")
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
                self.password_panel.btn_mode_dekripsi.setChecked(True)
                self.password_panel._on_mode_button_clicked(self.password_panel.btn_mode_dekripsi)
        self.result_card.hide_result()
        self._validate_state()

    def _on_limit_reached(self, limit: int):
        self.notif.show_msg(
            "error",
            f"Text reached the maximum of {limit:,} characters.",
            3500,
        )

    def _on_password_valid_changed(self, valid: bool):
        self._is_password_valid = valid
        self.notif.hide_msg()
        self._validate_state()

    def _on_mode_changed(self, mode: str):
        is_enc = mode == "enkripsi"
        if is_enc:
            self.btn_aksi.setTextLabels("Encrypt Text", "Enter text and create a password to begin")
            self.btn_aksi.icon_name = "mdi6.lock-plus"
            self.btn_aksi.lbl_icon.setPixmap(
                qta.icon("mdi6.lock-plus", color=CLR_ON_ACCENT).pixmap(22, 22)
            )
        else:
            self.btn_aksi.setTextLabels(
                "Decrypt Text", "Enter encrypted text and the password to open"
            )
            self.btn_aksi.icon_name = "mdi6.lock-open-check-outline"
            self.btn_aksi.lbl_icon.setPixmap(
                qta.icon("mdi6.lock-open-check-outline", color=CLR_ON_ACCENT).pixmap(22, 22)
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
            verb = "encrypt" if self.password_panel.get_mode() == "enkripsi" else "decrypt"
            self.status_changed.emit(
                "Ready to process", f"Text & password ready to {verb}", "ready"
            )
        else:
            self.status_changed.emit("AES-256 • GCM", "Local encryption active", "idle")

    # ── Proses enkripsi / dekripsi ────────────────────────────────────────────

    def _proses(self):
        if self.worker is not None or not self.btn_aksi.isEnabled():
            return

        text = self.input_card.get_text().strip()
        password = self.password_panel.get_password()
        mode = self.password_panel.get_mode()

        if not text:
            self.notif.show_msg("warn", "Text cannot be empty.", 3500)
            return
        if not password:
            self.notif.show_msg("warn", "Password cannot be empty.", 3500)
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
            label = "Encrypting text…" if mode == "enkripsi" else "Decrypting text…"
            self.btn_aksi.setTextLabels("Processing…", label)
            self.status_changed.emit("Processing text", "Almost there", "busy")
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
            # Auto-copy ke clipboard
            QGuiApplication.clipboard().setText(result)
            verb = "encrypted" if mode == "enkripsi" else "decrypted"
            self.system_notification.emit(
                f"Text {verb} successfully",
                "The result was automatically copied to the clipboard.",
            )
            self.notif.show_msg(
                "ok",
                f"✓ Text {verb} successfully — copied to clipboard.",
                4000,
            )
            logger.info(f"TabTeks: {mode} berhasil — {len(result)} karakter")

        self._validate_state()
        # Status pill: success/error setelah _validate_state agar tidak ditimpa.
        if error:
            self.status_changed.emit("Failed", "Check your password or text format", "error")
        else:
            self.status_changed.emit("Success", "Result copied to clipboard", "success")

    # ── External busy (dari tab lain yang sedang memproses file) ──────────────

    def set_external_busy(self, busy: bool):
        self._external_busy = busy
        self._validate_state()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _format_text_error(error: str, mode: str) -> str:
    err_lower = error.lower()
    if "wrong password" in err_lower or "invalidtag" in err_lower or "modified" in err_lower:
        return "Incorrect password, or the encrypted text has been modified or corrupted."
    if "format" in err_lower or "valid" in err_lower or "adtn_text" in err_lower:
        return "Invalid format. Make sure the encrypted text starts with 'ADTN_TEXT:1:'."
    if "empty" in err_lower:
        return error
    prefix = "Encryption failed" if mode == "enkripsi" else "Decryption failed"
    return f"{prefix}. {error}"
