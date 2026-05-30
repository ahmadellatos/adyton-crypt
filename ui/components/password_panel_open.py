import qtawesome as qta
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFrame,
)
from PySide6.QtCore import Qt, QSize, Signal

from ..widgets import apply_shadow
from ..styles import (
    CLR_TIPS_BG,
    CLR_TIPS_BORDER,
    CLR_TEXT_MUTED,
    CLR_ACCENT,
    CLR_WARN,
)


class PasswordPanelOpen(QFrame):
    # Emit boolean True jika password tidak kosong
    valid_state_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        apply_shadow(self, blur_radius=30, opacity=40)
        self._build_ui()
        self._setup_accessibility()

    def _build_ui(self):
        v_pw = QVBoxLayout(self)
        v_pw.setContentsMargins(24, 20, 24, 20)
        v_pw.setSpacing(12)  # Match premium rhythm from Kunci side

        lbl_title_pw = QLabel("MASUKKAN PASSWORD")
        lbl_title_pw.setObjectName("CardTitle")
        v_pw.addWidget(lbl_title_pw)
        v_pw.addSpacing(8)  # Tighter, more consistent with Kunci panel

        self.box_pw = QFrame()
        self.box_pw.setObjectName("InputBox")
        lay_box = QHBoxLayout(self.box_pw)
        lay_box.setContentsMargins(12, 0, 6, 0)
        lay_box.setSpacing(0)

        self.entry_pw = QLineEdit()
        self.entry_pw.setObjectName("InputInside")
        self.entry_pw.setFixedHeight(45)
        self.entry_pw.setPlaceholderText("Ketik password di sini…")
        self.entry_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.entry_pw.setAccessibleName("Password untuk Membuka Brankas")
        self.entry_pw.textChanged.connect(self._on_pw_change)
        lay_box.addWidget(self.entry_pw)

        self.btn_toggle_pw = QPushButton()
        self.btn_toggle_pw.setIcon(qta.icon("mdi6.eye-outline", color=CLR_TEXT_MUTED))
        self.btn_toggle_pw.setIconSize(QSize(22, 22))
        self.btn_toggle_pw.setObjectName("BtnEye")
        self.btn_toggle_pw.setFixedSize(44, 45)  # Match Kunci side for consistency
        self.btn_toggle_pw.clicked.connect(self._toggle_pw)
        lay_box.addWidget(self.btn_toggle_pw)

        v_pw.addWidget(self.box_pw)
        v_pw.addStretch()
        v_pw.addWidget(self._build_info_box())

    def _build_info_box(self) -> QFrame:
        info_box = QFrame()
        info_box.setObjectName("TipsBox")
        lay_info = QVBoxLayout(info_box)
        lay_info.setContentsMargins(12, 10, 12, 10)
        lay_info.setSpacing(8)  # Slightly tighter for premium feel

        tips = [
            (
                "mdi6.shield-key-outline",
                CLR_ACCENT,
                "Password tidak dapat dipulihkan. Simpan di tempat yang aman.",
            ),
            (
                "mdi6.lock-alert-outline",
                CLR_WARN,
                "Pastikan password sama persis dengan yang digunakan saat mengunci.",
            ),
            (
                "mdi6.file-lock-outline",
                CLR_TEXT_MUTED,
                "Hanya file .adtn yang dibuat oleh Adyton Crypt yang dapat dibuka.",
            ),
        ]

        for icon_name, color, text in tips:
            row = QHBoxLayout()
            row.setSpacing(10)
            lbl_ic = QLabel()
            lbl_ic.setPixmap(qta.icon(icon_name, color=color).pixmap(16, 16))
            lbl_ic.setFixedSize(16, 16)  # Consistent with other icons in the app
            row.addWidget(lbl_ic, alignment=Qt.AlignmentFlag.AlignTop)

            lbl_tx = QLabel(text)
            lbl_tx.setWordWrap(True)
            lbl_tx.setObjectName("MutedText")
            row.addWidget(lbl_tx, 1)
            lay_info.addLayout(row)

        return info_box

    def _setup_accessibility(self):
        self.entry_pw.installEventFilter(self)
        self.btn_toggle_pw.installEventFilter(self)
        self.setTabOrder(self.entry_pw, self.btn_toggle_pw)

    def eventFilter(self, obj, event):
        if event.type() in (event.Type.FocusIn, event.Type.FocusOut):
            if (
                isinstance(obj, QLineEdit)
                and obj.parent()
                and obj.parent().objectName() == "InputBox"
            ):
                is_focus = event.type() == event.Type.FocusIn
                box = obj.parent()
                box.setProperty("focused", is_focus)
                box.style().unpolish(box)
                box.style().polish(box)
        elif event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                if isinstance(obj, QPushButton) and obj.objectName() == "BtnEye":
                    obj.click()
                    return True
        return super().eventFilter(obj, event)

    def _toggle_pw(self):
        mode = (
            QLineEdit.EchoMode.Normal
            if self.entry_pw.echoMode() == QLineEdit.EchoMode.Password
            else QLineEdit.EchoMode.Password
        )
        self.entry_pw.setEchoMode(mode)
        color = CLR_ACCENT if mode == QLineEdit.EchoMode.Normal else CLR_TEXT_MUTED
        icon_name = (
            "mdi6.eye-outline"
            if mode == QLineEdit.EchoMode.Password
            else "mdi6.eye-off-outline"
        )
        self.btn_toggle_pw.setIcon(qta.icon(icon_name, color=color))

    def _on_pw_change(self):
        pw = self.entry_pw.text()
        self.valid_state_changed.emit(bool(pw))

    # --- PUBLIC API ---
    def get_password(self) -> str:
        return self.entry_pw.text()

    def reset_field(self):
        self.entry_pw.blockSignals(True)
        self.entry_pw.clear()
        self.entry_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.btn_toggle_pw.setIcon(qta.icon("mdi6.eye-outline", color=CLR_TEXT_MUTED))
        self.entry_pw.blockSignals(False)
        self.valid_state_changed.emit(False)

    def attach_return_event(self, slot_func):
        self.entry_pw.returnPressed.connect(slot_func)
