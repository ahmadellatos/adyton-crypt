"""
Modul: text_input_card.py
Deskripsi: Card input teks (kolom kiri Tab Teks) — text area + tombol paste/clear
           dan batas karakter adaptif (plaintext vs ciphertext).
"""

import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
)

from core.text_vault import TEXT_VAULT_PREFIX

from ..styles import (
    CLR_ACCENT,
    CLR_BORDER,
    CLR_DANGER,
    CLR_INSET,
    CLR_TEXT_MAIN,
    CLR_TEXT_MUTED,
)
from ..widgets import apply_shadow, build_card_header

MAX_INPUT_CHARS = 50_000
MAX_DECRYPT_CHARS = 300_000


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
        self.btn_paste = QPushButton(" Paste")
        self.btn_paste.setIcon(qta.icon("mdi6.clipboard-arrow-down-outline", color="white"))
        self.btn_paste.setFixedHeight(36)
        self.btn_paste.setObjectName("BtnGen")
        self.btn_paste.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_paste.setAccessibleName("Paste text from clipboard")
        self.btn_paste.clicked.connect(self._paste_clipboard)

        header, _, _ = build_card_header(
            "mdi6.text-box-edit-outline",
            CLR_ACCENT,
            "Text input",
            "Type or paste the text you want to encrypt/decrypt",
            button=self.btn_paste,
        )
        lay.addLayout(header)

        lay.addSpacing(4)

        # ── Text area ─────────────────────────────────────────────────────────
        self.text_edit = QTextEdit()
        self.text_edit.setObjectName("TextInputArea")
        self.text_edit.setPlaceholderText(
            "Type or paste text here…\n\nTip: Paste encrypted text (ADTN_TEXT:1:…) to decrypt it."
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
        self.btn_clear.setIcon(qta.icon("mdi6.trash-can-outline", color=CLR_TEXT_MUTED))
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
