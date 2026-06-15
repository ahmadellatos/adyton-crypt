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
    QVBoxLayout,
)

from .styles import CLR_WARN
from .widgets import apply_shadow


class ModernMessageBox(QDialog):
    """Dialog konfirmasi modern dengan style dark dan centering yang reliable."""

    def __init__(self, title, message, icon_name="mdi6.alert", icon_color=CLR_WARN, parent=None):
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

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("BtnDialogCancel")
        self.btn_cancel.setFixedHeight(42)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_yes = QPushButton("Continue")
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
        QTimer.singleShot(0, self._center_dialog)

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
