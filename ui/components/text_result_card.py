"""
Modul: text_result_card.py
Deskripsi: Card hasil enkripsi/dekripsi Tab Teks — muncul dengan animasi slide-in,
           tombol Copy to Clipboard, dan QR share.
"""

import qtawesome as qta
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from ..i18n import register, tr
from ..qr_dialog import QR_MAX_CHARS, QRShareDialog
from ..styles import (
    CLR_ACCENT,
    CLR_BORDER,
    CLR_INSET,
    CLR_SUCCESS,
    CLR_TEXT_MUTED,
    FONT_MONO,
)
from ..utils import CLIPBOARD_AUTO_CLEAR_MS, copy_to_clipboard_auto_clear
from ..widgets import apply_shadow


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
        self.lbl_result_title = QLabel(tr("text.result.enc.title", "Encryption Result"))
        self.lbl_result_title.setObjectName("CardTitle")
        self.lbl_result_sub = QLabel(
            tr("text.result.enc.sub", "Copy and save the encrypted text below")
        )
        self.lbl_result_sub.setObjectName("CardSubtitle")
        v_hdr.addWidget(self.lbl_result_title)
        v_hdr.addWidget(self.lbl_result_sub)

        self.btn_copy = QPushButton()
        register(self.btn_copy, "text.result.copy", " Copy to Clipboard")
        self.btn_copy.setIcon(qta.icon("mdi6.content-copy", color="white"))
        self.btn_copy.setFixedHeight(36)
        self.btn_copy.setObjectName("BtnGen")
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.setAccessibleName("Copy result to clipboard")
        self.btn_copy.clicked.connect(self._copy_to_clipboard)

        self.btn_qr = QPushButton()
        register(self.btn_qr, "text.result.qr", " QR")
        self.btn_qr.setIcon(qta.icon("mdi6.qrcode", color="white"))
        self.btn_qr.setFixedHeight(36)
        self.btn_qr.setObjectName("BtnGen")
        self.btn_qr.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_qr.setAccessibleName("Show QR code of the encryption result")
        self.btn_qr.setToolTip(
            tr(
                "text.result.qr.tip",
                "Show the encryption result as a QR code to scan with a phone camera",
            )
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
        self.lbl_out_count = QLabel(tr("text.input.count", "{n} characters").format(n=0))
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
            copy_to_clipboard_auto_clear(text)
            secs = CLIPBOARD_AUTO_CLEAR_MS // 1000
            self.lbl_copy_confirm.setText(
                tr("text.result.copied", "✓ Copied — auto-clears in {s}s").format(s=secs)
            )
            QTimer.singleShot(3000, lambda: self.lbl_copy_confirm.setText(""))

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
        self.lbl_out_count.setText(tr("text.input.count", "{n} characters").format(n=f"{n:,}"))
        self.lbl_copy_confirm.setText("")

        if mode == "enkripsi":
            self.lbl_result_title.setText(tr("text.result.enc.title", "Encryption Result"))
            self.lbl_result_sub.setText(
                tr(
                    "text.result.enc.sub2",
                    "Copy and save this encrypted text — it can only be decrypted with the same password",
                )
            )
            self.icon_result.setPixmap(
                qta.icon("mdi6.lock-outline", color=CLR_ACCENT).pixmap(28, 28)
            )
            self.btn_qr.setVisible(n <= QR_MAX_CHARS)
        else:
            self.lbl_result_title.setText(tr("text.result.dec.title", "Decryption Result"))
            self.lbl_result_sub.setText(
                tr("text.result.dec.sub", "Your original text has been restored")
            )
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
