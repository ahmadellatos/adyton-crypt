import qtawesome as qta
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..dialogs import ModernMessageBox
from ..styles import CLR_WARN_DK
from ..widgets import ToggleSwitch


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

    _SECURE_H = 58  # tinggi terbuka sub-opsi Secure Wipe (judul + subjudul)

    def _build_ui(self):
        # Section opsi di dasar card target — latar rounded halus agar terpisah
        # visual dari daftar di atasnya.
        container = QFrame(self)
        container.setObjectName("OptionsPanel")
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        container.setStyleSheet(
            "QFrame#OptionsPanel { background: rgba(255, 255, 255, 0.04);" " border-radius: 12px; }"
        )

        lay_opsi_hapus = QVBoxLayout(container)
        lay_opsi_hapus.setContentsMargins(16, 14, 16, 14)
        lay_opsi_hapus.setSpacing(6)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)

        # --- Baris utama: judul + deskripsi (kiri), toggle (kanan) ---
        lay_chk1 = QHBoxLayout()
        lay_chk1.setContentsMargins(0, 0, 0, 0)
        lay_chk1.setSpacing(12)

        v_chk_txt1 = QVBoxLayout()
        v_chk_txt1.setSpacing(3)
        lbl_chk_title1 = QLabel("Delete original after locking")
        lbl_chk_title1.setObjectName("SectionLabel")
        lbl_chk_desc1 = QLabel("Standard deletion — fast & safe for SSDs.")
        lbl_chk_desc1.setObjectName("OptionDesc")
        lbl_chk_desc1.setWordWrap(True)
        v_chk_txt1.addWidget(lbl_chk_title1)
        v_chk_txt1.addWidget(lbl_chk_desc1)

        self.switch_hapus = ToggleSwitch(checked=False)
        self.switch_hapus.setAccessibleName("Delete original file after locking")

        lay_chk1.addLayout(v_chk_txt1, 1)
        lay_chk1.addWidget(self.switch_hapus, 0, Qt.AlignmentFlag.AlignVCenter)
        lay_opsi_hapus.addLayout(lay_chk1)

        # --- Sub-opsi collapsible: Secure Wipe (checkbox + judul + subjudul) ---
        self.widget_secure_wipe = QWidget()
        self.widget_secure_wipe.setMaximumHeight(0)
        self.widget_secure_wipe.setMinimumHeight(0)

        lay_collapse = QVBoxLayout(self.widget_secure_wipe)
        lay_collapse.setContentsMargins(0, 10, 0, 0)
        lay_collapse.setSpacing(4)

        lay_chk2 = QHBoxLayout()
        lay_chk2.setContentsMargins(0, 0, 0, 0)
        lay_chk2.setSpacing(12)

        self.chk_secure = KeyboardCheckbox(size=20)
        self.chk_secure.setObjectName("ChkSecure")
        self.chk_secure.set_checked(False)
        self.chk_secure.hide()

        v_chk_txt2 = QVBoxLayout()
        v_chk_txt2.setSpacing(2)
        lbl_chk_title2 = QLabel("Advanced: Secure Wipe (overwrite data)")
        lbl_chk_title2.setObjectName("SectionLabel")
        lbl_chk_desc2 = QLabel("Slower — for HDDs or highly sensitive data.")
        lbl_chk_desc2.setObjectName("OptionDesc")
        lbl_chk_desc2.setWordWrap(True)
        v_chk_txt2.addWidget(lbl_chk_title2)
        v_chk_txt2.addWidget(lbl_chk_desc2)
        self.chk_secure.setAccessibleName("Secure Wipe — overwrite original data")

        lay_chk2.addWidget(self.chk_secure, alignment=Qt.AlignmentFlag.AlignVCenter)
        lay_chk2.addLayout(v_chk_txt2, 1)
        lay_collapse.addLayout(lay_chk2)
        lay_opsi_hapus.addWidget(self.widget_secure_wipe)

        self.anim_secure = QPropertyAnimation(self.widget_secure_wipe, b"maximumHeight")
        self.anim_secure.setDuration(250)
        self.anim_secure.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self.anim_secure.finished.connect(self._on_secure_collapsed)
        self.switch_hapus.toggled.connect(self._on_hapus_toggled)
        self.chk_secure._on_toggle = self._toggle_secure_wipe

    def _on_hapus_toggled(self, checked: bool):
        self.anim_secure.stop()
        self.anim_secure.setStartValue(self.widget_secure_wipe.maximumHeight())
        if checked:
            self.widget_secure_wipe.show()
            self.chk_secure.show()
            self.anim_secure.setEndValue(self._SECURE_H)
        else:
            self.anim_secure.setEndValue(0)
            if self.chk_secure._checked:
                self.chk_secure.set_checked(False)
        self.anim_secure.start()
        self.hapus_asli_changed.emit(checked)

    def _toggle_secure_wipe(self):
        if not self.switch_hapus.isChecked():
            return
        if not self.chk_secure._checked:
            dialog = ModernMessageBox(
                title="Heads Up: Hardware Compatibility",
                message="Secure Wipe overwrites the original data with random bytes before deleting, making recovery much harder.\n\n"
                "Important:\n"
                "• Avoid this on SSDs — repeated overwrites accelerate drive wear.\n"
                "• Use it only for traditional hard drives (HDD).\n\n"
                "Enable Secure Wipe?",
                icon_name="mdi6.alert-decagram",
                icon_color=CLR_WARN_DK,
                parent=self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
        self.chk_secure.set_checked(not self.chk_secure._checked)

    def _on_secure_collapsed(self):
        # 'finished' terhubung permanen; sembunyikan checkbox hanya saat benar-benar
        # tertutup (toggle OFF) agar tidak fokusable/terlihat ketika collapsed.
        if not self.switch_hapus.isChecked():
            self.chk_secure.hide()

    # --- PUBLIC API ---
    def is_hapus_asli(self) -> bool:
        return self.switch_hapus.isChecked()

    def is_secure_wipe(self) -> bool:
        return self.chk_secure._checked

    def reset_options(self):
        if self.switch_hapus.isChecked():
            self.switch_hapus.setChecked(False)  # memicu _on_hapus_toggled (collapse + emit)

    def set_busy(self, busy: bool):
        self.switch_hapus.setEnabled(not busy)
        self.chk_secure.setEnabled(not busy)
