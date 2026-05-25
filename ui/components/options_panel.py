import qtawesome as qta
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QDialog
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Signal
from PySide6.QtGui import QKeyEvent

from ..widgets import ModernMessageBox


class KeyboardCheckbox(QFrame):
    def __init__(self, size=22, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._checked = False
        self._on_toggle = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.lbl_icon = QLabel()
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_icon)

    def set_checked(self, state: bool):
        self._checked = state
        self.setProperty("checked", state)
        self.style().unpolish(self)
        self.style().polish(self)

        if state:
            icon_sz = self.width() - 4
            self.lbl_icon.setPixmap(
                qta.icon("mdi6.check-bold", color="white").pixmap(icon_sz, icon_sz)
            )
        else:
            self.lbl_icon.clear()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._on_toggle:
                self._on_toggle()
            event.accept()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if self._on_toggle:
            self._on_toggle()


class OptionsPanel(QWidget):
    # Emit sinyal ketika opsi Hapus Asli berubah
    hapus_asli_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        lay_opsi_hapus = QVBoxLayout(self)
        lay_opsi_hapus.setContentsMargins(0, 0, 0, 0)
        lay_opsi_hapus.setSpacing(0)

        lay_chk1 = QHBoxLayout()
        lay_chk1.setContentsMargins(5, 5, 5, 0)
        lay_chk1.setSpacing(0)

        self.chk_hapus = KeyboardCheckbox(size=22)
        self.chk_hapus.setObjectName("ChkHapus")
        self.chk_hapus.set_checked(False)

        v_chk_txt1 = QVBoxLayout()
        v_chk_txt1.setSpacing(2)
        lbl_chk_title1 = QLabel("Hapus file/folder asli setelah dikunci")
        lbl_chk_title1.setStyleSheet("font-size: 10pt; color: #FFFFFF;")
        lbl_chk_desc1 = QLabel(
            "File atau folder asli akan dihapus secara standar (Cepat & Aman untuk SSD)."
        )
        lbl_chk_desc1.setStyleSheet("font-size: 9pt; color: #8B95A5;")
        v_chk_txt1.addWidget(lbl_chk_title1)
        v_chk_txt1.addWidget(lbl_chk_desc1)

        lay_chk1.addWidget(self.chk_hapus, alignment=Qt.AlignmentFlag.AlignVCenter)
        lay_chk1.addSpacing(10)
        lay_chk1.addLayout(v_chk_txt1)
        lay_opsi_hapus.addLayout(lay_chk1)

        self.widget_secure_wipe = QWidget()
        self.widget_secure_wipe.setMaximumHeight(0)
        self.widget_secure_wipe.setMinimumHeight(0)

        lay_collapse = QVBoxLayout(self.widget_secure_wipe)
        lay_collapse.setContentsMargins(37, 5, 5, 5)
        lay_collapse.setSpacing(0)

        lay_chk2 = QHBoxLayout()
        lay_chk2.setContentsMargins(0, 0, 0, 0)
        lay_chk2.setSpacing(0)

        self.chk_secure = KeyboardCheckbox(size=18)
        self.chk_secure.setObjectName("ChkSecure")
        self.chk_secure.set_checked(False)
        self.chk_secure.hide()

        lbl_chk_title2 = QLabel("Advanced: Secure Wipe (Timpa data)")
        lbl_chk_title2.setStyleSheet("font-size: 9pt; color: #FFFFFF;")

        lay_chk2.addWidget(self.chk_secure, alignment=Qt.AlignmentFlag.AlignVCenter)
        lay_chk2.addSpacing(10)
        lay_chk2.addWidget(lbl_chk_title2)
        lay_chk2.addStretch()
        lay_collapse.addLayout(lay_chk2)
        lay_opsi_hapus.addWidget(self.widget_secure_wipe)

        self.anim_secure = QPropertyAnimation(self.widget_secure_wipe, b"maximumHeight")
        self.anim_secure.setDuration(250)
        self.anim_secure.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self.chk_hapus._on_toggle = self._toggle_hapus_asli
        self.chk_secure._on_toggle = self._toggle_secure_wipe

    def _toggle_hapus_asli(self):
        self.chk_hapus.set_checked(not self.chk_hapus._checked)
        if self.chk_hapus._checked:
            self.widget_secure_wipe.show()
            self.chk_secure.show()
            self.anim_secure.setStartValue(0)
            self.anim_secure.setEndValue(50)
            self.anim_secure.start()
        else:
            self.anim_secure.setStartValue(self.widget_secure_wipe.maximumHeight())
            self.anim_secure.setEndValue(0)
            self.anim_secure.start()
            self.anim_secure.finished.connect(self._on_secure_collapsed)
            if self.chk_secure._checked:
                self.chk_secure.set_checked(False)

        self.hapus_asli_changed.emit(self.chk_hapus._checked)

    def _toggle_secure_wipe(self):
        if not self.chk_hapus._checked:
            return
        if not self.chk_secure._checked:
            dialog = ModernMessageBox(
                title="Peringatan Perangkat Keras",
                message="Secure Wipe akan menimpa data asli dengan byte kosong sebelum dihapus agar sulit dipulihkan.\n\n"
                "PERHATIAN:\n"
                "• Jangan gunakan opsi ini jika file berada di SSD karena dapat merusak disk.\n"
                "• Hanya gunakan untuk Harddisk (HDD).\n\n"
                "Apakah Anda yakin ingin mengaktifkan opsi ini?",
                icon_name="mdi6.alert-decagram",
                icon_color="#E67E22",
                parent=self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
        self.chk_secure.set_checked(not self.chk_secure._checked)

    def _on_secure_collapsed(self):
        self.chk_secure.hide()
        self.anim_secure.finished.disconnect(self._on_secure_collapsed)

    # --- PUBLIC API ---
    def is_hapus_asli(self) -> bool:
        return self.chk_hapus._checked

    def is_secure_wipe(self) -> bool:
        return self.chk_secure._checked

    def reset_options(self):
        if self.chk_hapus._checked:
            self.chk_hapus.set_checked(False)
            self.chk_secure.set_checked(False)
            self.anim_secure.setStartValue(self.widget_secure_wipe.maximumHeight())
            self.anim_secure.setEndValue(0)
            self.anim_secure.start()
            self.hapus_asli_changed.emit(False)

    def set_busy(self, busy: bool):
        self.chk_hapus.setEnabled(not busy)
        self.chk_secure.setEnabled(not busy)
