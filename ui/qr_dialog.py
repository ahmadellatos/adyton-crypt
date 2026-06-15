"""
Modul: qr_dialog.py
Deskripsi: Dialog "Bagikan via QR" untuk hasil enkripsi teks (ADTN_TEXT).
           QR di-render langsung dengan QPainter dari matrix qrcode —
           tanpa dependensi Pillow.

Catatan keamanan: QR code TIDAK menambah keamanan. Isinya adalah teks
terenkripsi yang sama persis; keamanan tetap berasal dari AES-256-GCM
dan kerahasiaan password.
"""

from __future__ import annotations

import qrcode
import qtawesome as qta
from loguru import logger
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QVBoxLayout,
)

from .styles import CLR_ACCENT, CLR_TEXT_MUTED
from .widgets import apply_shadow

# ─── Kapasitas ────────────────────────────────────────────────────────────────
# QR byte-mode, versi 40, error correction M = 2.331 byte.
# String ADTN_TEXT seluruhnya ASCII (1 byte/karakter), jadi batas karakter = batas byte.
# Dipilih level M (bukan L/2.953) agar QR lebih toleran terhadap layar
# silau/buram saat di-scan kamera HP.
QR_MAX_CHARS = 2331

# Ukuran render: modul QR digambar dalam grid, lalu di-scale ke ukuran tampil.
_QR_DISPLAY_SIZE = 340  # px di dialog
_QR_EXPORT_SCALE = 12  # px per modul saat simpan PNG (tajam untuk dicetak)
_QUIET_ZONE = 4  # modul border putih — wajib minimal 4 sesuai spek QR


def make_qr_image(text: str, module_px: int = _QR_EXPORT_SCALE) -> QImage | None:
    """Render *text* menjadi QImage QR (hitam di atas putih).

    Return None jika teks melebihi kapasitas QR.

    QR selalu digambar hitam-di-atas-putih apa pun tema aplikasi —
    scanner kamera HP jauh lebih andal membaca kontras standar ini.
    """
    if len(text) > QR_MAX_CHARS:
        return None

    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        border=_QUIET_ZONE,
        box_size=1,  # tidak dipakai (kita render sendiri), tapi wajib > 0
    )
    qr.add_data(text)
    try:
        qr.make(fit=True)
    except qrcode.exceptions.DataOverflowError:
        return None

    matrix = qr.get_matrix()  # list[list[bool]] — sudah termasuk quiet zone
    n = len(matrix)
    size = n * module_px

    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))

    painter = QPainter(image)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("black"))
    for row_idx, row in enumerate(matrix):
        for col_idx, dark in enumerate(row):
            if dark:
                painter.drawRect(col_idx * module_px, row_idx * module_px, module_px, module_px)
    painter.end()
    return image


class QRShareDialog(QDialog):
    """Dialog menampilkan QR dari teks terenkripsi, dengan opsi simpan PNG."""

    def __init__(self, encrypted_text: str, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.parent_widget = parent
        self._encrypted_text = encrypted_text
        self._qr_image = make_qr_image(encrypted_text)

        container = QFrame(self)
        container.setObjectName("Card")
        container.setFixedWidth(440)
        apply_shadow(container, blur_radius=30, y_offset=8, opacity=60)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        main_layout.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # ── Header ────────────────────────────────────────────────────────────
        row_hdr = QHBoxLayout()
        row_hdr.setSpacing(10)
        lbl_icon = QLabel()
        lbl_icon.setPixmap(qta.icon("mdi6.qrcode", color=CLR_ACCENT).pixmap(28, 28))
        lbl_title = QLabel("Share via QR Code")
        lbl_title.setObjectName("CardTitle")
        row_hdr.addWidget(lbl_icon)
        row_hdr.addWidget(lbl_title, 1)
        layout.addLayout(row_hdr)

        # ── QR image (panel putih agar mudah di-scan dari layar) ─────────────
        self.lbl_qr = QLabel()
        self.lbl_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_qr.setFixedSize(_QR_DISPLAY_SIZE + 24, _QR_DISPLAY_SIZE + 24)
        self.lbl_qr.setStyleSheet("background-color: white; border-radius: 12px; padding: 12px;")
        if self._qr_image is not None:
            pixmap = QPixmap.fromImage(self._qr_image).scaled(
                _QR_DISPLAY_SIZE,
                _QR_DISPLAY_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                # FastTransformation menjaga tepi modul tetap tajam —
                # smoothing justru membuat QR blur dan susah di-scan.
                Qt.TransformationMode.FastTransformation,
            )
            self.lbl_qr.setPixmap(pixmap)
        layout.addWidget(self.lbl_qr, alignment=Qt.AlignmentFlag.AlignCenter)

        # ── Keterangan ────────────────────────────────────────────────────────
        lbl_info = QLabel(
            "Scan with a phone camera to transfer the encrypted text.\n"
            "This QR is safe for anyone to see — its contents stay locked without the password."
        )
        lbl_info.setWordWrap(True)
        lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_info.setStyleSheet(f"font-size: 8.5pt; color: {CLR_TEXT_MUTED};")
        layout.addWidget(lbl_info)

        layout.addSpacing(4)

        # ── Tombol ────────────────────────────────────────────────────────────
        btn_lay = QHBoxLayout()
        btn_lay.setSpacing(10)
        btn_lay.addStretch()

        self.btn_save = QPushButton(" Save PNG")
        self.btn_save.setIcon(qta.icon("mdi6.download-outline", color="white"))
        self.btn_save.setObjectName("BtnDialogCancel")
        self.btn_save.setFixedHeight(42)
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self._save_png)

        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("BtnAlertConfirm")
        self.btn_close.setFixedHeight(42)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.accept)
        self.btn_close.setDefault(True)
        self.btn_close.setAutoDefault(True)

        btn_lay.addWidget(self.btn_save)
        btn_lay.addWidget(self.btn_close)
        layout.addLayout(btn_lay)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _save_png(self):
        if self._qr_image is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save QR Code",
            "adyton_qr.png",
            "PNG Image (*.png)",
        )
        if not path:
            return
        if self._qr_image.save(path, "PNG"):
            logger.info(f"QR disimpan ke: {path}")
            self.btn_save.setText(" Saved ✓")
            QTimer.singleShot(2200, lambda: self.btn_save.setText(" Save PNG"))
        else:
            logger.error(f"Gagal menyimpan QR ke: {path}")

    # ── Centering (pola sama dengan ModernMessageBox) ─────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._center_dialog)

    def _center_dialog(self):
        self.adjustSize()
        if self.parent_widget:
            top_level = self.parent_widget.window()
            if top_level and top_level.isVisible():
                parent_center = top_level.mapToGlobal(top_level.rect().center())
                self.move(parent_center - self.rect().center())
                return
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - self.rect().center())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)
