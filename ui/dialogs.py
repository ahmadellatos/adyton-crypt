"""
Modul: dialogs.py
Deskripsi: Dialog dan message box kustom.
"""

import qtawesome as qta
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
)

from .i18n import register, tr
from .styles import (
    CLR_ACCENT,
    CLR_BORDER,
    CLR_INSET,
    CLR_SUCCESS,
    CLR_WARN,
    FONT_MONO,
)
from .utils import CLIPBOARD_AUTO_CLEAR_MS, copy_to_clipboard_auto_clear
from .widgets import ScrimDialogMixin, ToggleSwitch, apply_shadow


class ModernMessageBox(ScrimDialogMixin, QDialog):
    """Dialog konfirmasi modern dengan style dark dan centering yang reliable."""

    def __init__(
        self, title, message, icon_name="mdi6.alert-outline", icon_color=CLR_WARN, parent=None
    ):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.parent_widget = parent

        container = QFrame(self)
        container.setObjectName("Card")
        container.setFixedWidth(460)
        apply_shadow(container, blur_radius=30, y_offset=8, opacity=60)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        main_layout.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)  # Premium tight rhythm

        lbl_title = QLabel(title)
        lbl_title.setObjectName("CardTitle")
        layout.addWidget(lbl_title)

        content_lay = QHBoxLayout()
        content_lay.setSpacing(15)

        lbl_icon = QLabel()
        lbl_icon.setPixmap(
            qta.icon(icon_name, color=icon_color).pixmap(32, 32)
        )  # More balanced size
        content_lay.addWidget(lbl_icon, alignment=Qt.AlignmentFlag.AlignTop)

        lbl_msg = QLabel(message)
        lbl_msg.setWordWrap(True)
        lbl_msg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        lbl_msg.setObjectName("MutedText")

        content_lay.addWidget(lbl_msg, 1)

        layout.addLayout(content_lay)
        layout.addSpacing(8)  # Tighter premium spacing before buttons

        btn_lay = QHBoxLayout()
        btn_lay.setSpacing(10)  # Premium tight button spacing
        btn_lay.addStretch()

        self.btn_cancel = QPushButton()
        register(self.btn_cancel, "common.cancel", "Cancel")
        self.btn_cancel.setObjectName("BtnDialogCancel")
        self.btn_cancel.setFixedHeight(42)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_yes = QPushButton()
        register(self.btn_yes, "common.continue", "Continue")
        self.btn_yes.setFixedHeight(42)
        self.btn_yes.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_yes.setObjectName("BtnAlertConfirm")
        self.btn_yes.clicked.connect(self.accept)

        btn_lay.addWidget(self.btn_cancel)
        btn_lay.addWidget(self.btn_yes)
        layout.addLayout(btn_lay)

        self.btn_yes.setDefault(True)
        self.btn_yes.setAutoDefault(True)
        self.btn_cancel.setAutoDefault(True)

    def showEvent(self, event):
        super().showEvent(event)
        self._show_modal_scrim()
        QTimer.singleShot(0, self._center_dialog)

    def hideEvent(self, event):
        self._hide_modal_scrim()
        super().hideEvent(event)

    def _center_dialog(self):
        """Pusatkan dialog ke tengah parent window secara reliable."""
        self.adjustSize()

        if self.parent_widget:
            top_level = self.parent_widget.window()
            if top_level and top_level.isVisible():
                parent_center = top_level.mapToGlobal(top_level.rect().center())
                self.move(parent_center - self.rect().center())
                return

        # Fallback: center ke layar utama
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - self.rect().center())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)


class RecoveryCodeDialog(ScrimDialogMixin, QDialog):
    """Tampilkan recovery code sekali — copy (auto-clear) + gate 'sudah disimpan'.

    Dialog ini SATU-SATUNYA tempat kode ditampilkan; tidak bisa dilihat lagi.
    Tombol konfirmasi baru aktif setelah user menyatakan sudah menyimpannya.
    """

    def __init__(self, code: str, parent=None):
        super().__init__(parent)
        self._code = code
        self.parent_widget = parent
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        container = QFrame(self)
        container.setObjectName("Card")
        container.setFixedWidth(480)
        apply_shadow(container, blur_radius=30, y_offset=8, opacity=60)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        main_layout.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel()
        register(title, "recovery.dialog.title", "Save your recovery key")
        title.setObjectName("CardTitle")
        layout.addWidget(title)

        warn_row = QHBoxLayout()
        warn_row.setSpacing(15)
        icon = QLabel()
        icon.setPixmap(qta.icon("mdi6.key-alert-outline", color=CLR_WARN).pixmap(32, 32))
        warn_row.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)
        msg = QLabel()
        register(
            msg,
            "recovery.dialog.msg",
            "This is the only way back into your vault if you forget the password. "
            "It can't be shown again or recovered for you — store it somewhere safe.",
        )
        msg.setWordWrap(True)
        msg.setObjectName("MutedText")
        msg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        warn_row.addWidget(msg, 1)
        layout.addLayout(warn_row)

        self.code_box = QTextEdit()
        self.code_box.setReadOnly(True)
        self.code_box.setPlainText(code)
        self.code_box.setFixedHeight(72)
        self.code_box.setStyleSheet(
            f"""
            QTextEdit {{
                background-color: {CLR_INSET};
                color: {CLR_ACCENT};
                border: 1.5px solid {CLR_BORDER};
                border-radius: 12px;
                padding: 12px;
                font-family: {FONT_MONO};
                font-size: 13pt;
                letter-spacing: 1px;
            }}
            """
        )
        layout.addWidget(self.code_box)

        self.btn_copy = QPushButton()
        register(self.btn_copy, "recovery.dialog.copy", " Copy recovery key")
        self.btn_copy.setIcon(qta.icon("mdi6.content-copy", color="white"))
        self.btn_copy.setObjectName("BtnGen")
        self.btn_copy.setFixedHeight(38)
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.clicked.connect(self._copy)
        layout.addWidget(self.btn_copy)

        self.lbl_copy_confirm = QLabel("")
        self.lbl_copy_confirm.setStyleSheet(
            f"font-size: 8.5pt; font-weight: 500; color: {CLR_SUCCESS};"
        )
        layout.addWidget(self.lbl_copy_confirm)

        # Gate: konfirmasi sudah menyimpan.
        gate_row = QHBoxLayout()
        gate_row.setSpacing(12)
        self.switch_saved = ToggleSwitch(checked=False)
        self.switch_saved.setAccessibleName("I have saved my recovery key")
        gate_lbl = QLabel()
        register(gate_lbl, "recovery.dialog.gate", "I've saved my recovery key")
        gate_lbl.setObjectName("SectionLabel")
        gate_lbl.setWordWrap(True)
        gate_row.addWidget(self.switch_saved, 0, Qt.AlignmentFlag.AlignVCenter)
        gate_row.addWidget(gate_lbl, 1)
        layout.addLayout(gate_row)

        layout.addSpacing(4)
        btn_lay = QHBoxLayout()
        btn_lay.setSpacing(10)
        btn_lay.addStretch()
        self.btn_cancel = QPushButton()
        register(self.btn_cancel, "common.cancel", "Cancel")
        self.btn_cancel.setObjectName("BtnDialogCancel")
        self.btn_cancel.setFixedHeight(42)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_yes = QPushButton()
        register(self.btn_yes, "common.continue", "Continue")
        self.btn_yes.setObjectName("BtnAlertConfirm")
        self.btn_yes.setFixedHeight(42)
        self.btn_yes.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_yes.setEnabled(False)
        self.btn_yes.clicked.connect(self.accept)
        btn_lay.addWidget(self.btn_cancel)
        btn_lay.addWidget(self.btn_yes)
        layout.addLayout(btn_lay)

        self.switch_saved.toggled.connect(self.btn_yes.setEnabled)

    def _copy(self):
        copy_to_clipboard_auto_clear(self._code)
        secs = CLIPBOARD_AUTO_CLEAR_MS // 1000
        self.lbl_copy_confirm.setText(
            tr("recovery.dialog.copied", "✓ Copied — clipboard auto-clears in {s}s").format(s=secs)
        )
        QTimer.singleShot(3000, lambda: self.lbl_copy_confirm.setText(""))

    def showEvent(self, event):
        super().showEvent(event)
        self._show_modal_scrim()
        QTimer.singleShot(0, self._center_dialog)

    def hideEvent(self, event):
        self._hide_modal_scrim()
        super().hideEvent(event)

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
        # Jangan biarkan Enter/Escape menutup dialog penting ini secara tak sengaja.
        if event.key() == Qt.Key.Key_Escape:
            return
        super().keyPressEvent(event)
