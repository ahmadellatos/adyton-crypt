import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ..styles import (
    CLR_ACCENT,
    CLR_TEXT_MUTED,
    CLR_WARN,
)
from ..widgets import PasswordLineEdit, apply_shadow


class PasswordPanelOpen(QFrame):
    # Emit boolean True jika password tidak kosong
    valid_state_changed = Signal(bool)
    retry_requested = Signal()
    pick_file_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        apply_shadow(self, blur_radius=30, opacity=40)
        self._build_ui()
        self._setup_accessibility()

    def _build_ui(self):
        self.v_pw = QVBoxLayout(self)
        self.v_pw.setContentsMargins(24, 18, 24, 18)
        self.v_pw.setSpacing(11)

        self.lbl_title_pw = QLabel("Masukkan Password")
        self.lbl_title_pw.setObjectName("CardTitle")
        self.v_pw.addWidget(self.lbl_title_pw)

        self.sub_pw = QLabel("Masukkan password untuk membuka brankas Anda.")
        self.sub_pw.setObjectName("CardSubtitle")
        self.sub_pw.setWordWrap(True)
        self.v_pw.addWidget(self.sub_pw)
        self.v_pw.addSpacing(4)

        self.entry_pw = PasswordLineEdit("Ketik password di sini…")
        self.entry_pw.setAccessibleName("Password untuk Membuka Brankas")
        self.entry_pw.textChanged.connect(self._on_pw_change)
        self.v_pw.addWidget(self.entry_pw)

        self.status_box = self._build_status_box()
        self.status_box.hide()
        self.v_pw.addWidget(self.status_box)

        self.error_box = self._build_error_box()
        self.error_box.hide()
        self.v_pw.addWidget(self.error_box)

        self.v_pw.addStretch(1)
        self.info_box = self._build_info_box()
        self.v_pw.addWidget(self.info_box)

    def _build_info_box(self) -> QFrame:
        info_box = QFrame()
        info_box.setObjectName("TipsBox")
        lay_info = QVBoxLayout(info_box)
        lay_info.setContentsMargins(14, 12, 14, 12)
        lay_info.setSpacing(10)

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
            row.setSpacing(8)
            lbl_ic = QLabel()
            lbl_ic.setPixmap(qta.icon(icon_name, color=color).pixmap(15, 15))
            lbl_ic.setFixedSize(15, 15)
            row.addWidget(lbl_ic, alignment=Qt.AlignmentFlag.AlignTop)

            lbl_tx = QLabel(text)
            lbl_tx.setWordWrap(True)
            lbl_tx.setObjectName("TipText")
            row.addWidget(lbl_tx, 1)
            lay_info.addLayout(row)

        return info_box

    def _build_status_box(self) -> QFrame:
        box = QFrame()
        box.setObjectName("ProcessStatusBox")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        intro = QLabel(
            "Vault sedang diverifikasi dan diekstrak. Jangan tutup aplikasi atau cabut drive sampai proses selesai."
        )
        intro.setObjectName("ProcessText")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        self.lbl_status_file = self._make_status_row(lay, "File", "—")
        self.lbl_status_size = self._make_status_row(lay, "Ukuran", "—")
        self.lbl_status_stage = self._make_status_row(lay, "Tahap", "Menyiapkan vault")

        return box

    def _build_error_box(self) -> QFrame:
        box = QFrame()
        box.setObjectName("OpenErrorBox")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(12)

        self.lbl_error_msg = QLabel("Password salah atau file brankas rusak.")
        self.lbl_error_msg.setObjectName("OpenErrorText")
        self.lbl_error_msg.setWordWrap(True)
        lay.addWidget(self.lbl_error_msg)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_retry = QPushButton("Coba Lagi")
        self.btn_retry.setObjectName("BtnInlinePrimary")
        self.btn_retry.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_retry.clicked.connect(self.retry_requested.emit)
        row.addWidget(self.btn_retry)

        self.btn_pick_file = QPushButton("Pilih File Lain")
        self.btn_pick_file.setObjectName("BtnInlineSecondary")
        self.btn_pick_file.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pick_file.clicked.connect(self.pick_file_requested.emit)
        row.addWidget(self.btn_pick_file)
        row.addStretch(1)
        lay.addLayout(row)

        return box

    def _make_status_row(self, parent_layout: QVBoxLayout, label: str, value: str) -> QLabel:
        row = QHBoxLayout()
        row.setSpacing(12)
        lbl = QLabel(label)
        lbl.setObjectName("ProcessLabel")
        lbl.setFixedWidth(64)
        val = QLabel(value)
        val.setObjectName("ProcessValue")
        val.setWordWrap(True)
        row.addWidget(lbl)
        row.addWidget(val, 1)
        parent_layout.addLayout(row)
        return val

    def _setup_accessibility(self):
        self.entry_pw.installEventFilter(self)
        self.setTabOrder(self.entry_pw, self.entry_pw)  # internal handling

    def eventFilter(self, obj, event):
        if event.type() in (event.Type.FocusIn, event.Type.FocusOut):
            if obj == self.entry_pw:
                is_focus = event.type() == event.Type.FocusIn
                self.entry_pw.setProperty("focused", is_focus)
                self.entry_pw.style().unpolish(self.entry_pw)
                self.entry_pw.style().polish(self.entry_pw)
        return super().eventFilter(obj, event)

    def _on_pw_change(self):
        pw = self.entry_pw.text()
        if self.error_box.isVisible():
            self.error_box.hide()
            self.info_box.show()
            self.lbl_title_pw.setText("Masukkan Password")
            self.sub_pw.setText("Masukkan password untuk membuka brankas Anda.")
        self.valid_state_changed.emit(bool(pw))

    # --- PUBLIC API ---
    def get_password(self) -> str:
        return self.entry_pw.text()

    def reset_field(self):
        self.entry_pw.blockSignals(True)
        self.entry_pw.clear()
        self.entry_pw.blockSignals(False)
        self.valid_state_changed.emit(False)

    def attach_return_event(self, slot_func):
        self.entry_pw.returnPressed.connect(slot_func)

    def set_idle_state(self) -> None:
        self.lbl_title_pw.setText("Masukkan Password")
        self.sub_pw.setText("Masukkan password untuk membuka brankas Anda.")
        self.entry_pw.show()
        self.entry_pw.setEnabled(True)
        self.status_box.hide()
        self.error_box.hide()
        self.info_box.show()

    def set_processing_state(self, file_name: str, size_text: str, stage: str) -> None:
        self.lbl_title_pw.setText("Membuka Brankas")
        self.sub_pw.setText("Vault sedang diverifikasi dan diekstrak.")
        self.entry_pw.hide()
        self.entry_pw.setEnabled(False)
        self.info_box.hide()
        self.error_box.hide()
        self.status_box.show()
        self.lbl_status_file.setText(file_name or "—")
        self.lbl_status_size.setText(size_text or "—")
        self.lbl_status_stage.setText(stage or "Menyiapkan vault")

    def update_processing_stage(self, stage: str) -> None:
        self.lbl_status_stage.setText(stage or "Memproses")

    def set_error_state(self, message: str) -> None:
        self.lbl_title_pw.setText("Gagal Membuka Brankas")
        self.sub_pw.setText("Password salah, file rusak, atau vault tidak didukung.")
        self.entry_pw.show()
        self.entry_pw.setEnabled(True)
        self.status_box.hide()
        self.info_box.hide()
        self.error_box.show()
        self.lbl_error_msg.setText(message)
        self.entry_pw.setFocus(Qt.FocusReason.OtherFocusReason)
