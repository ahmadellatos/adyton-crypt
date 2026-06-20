"""
Modul: recovery_hint_panel.py
Deskripsi: Opsi opsional saat MEMBUAT vault (Tab Kunci): recovery key + password
           hint. Recovery bisa berupa kode app-generated (ditampilkan setelah
           kunci) atau passphrase pilihan user. Hint disimpan TANPA enkripsi.
"""

import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..styles import CLR_WARN
from ..widgets import PasswordLineEdit, ToggleSwitch


def _make_text_input(placeholder: str) -> tuple[QFrame, QLineEdit]:
    """Input teks biasa dengan styling InputBox yang sama seperti field lain."""
    frame = QFrame()
    frame.setObjectName("InputBox")
    lay = QHBoxLayout(frame)
    lay.setContentsMargins(12, 0, 12, 0)
    lay.setSpacing(0)
    edit = QLineEdit()
    edit.setObjectName("InputInside")
    edit.setFixedHeight(52)
    edit.setPlaceholderText(placeholder)
    lay.addWidget(edit)
    return frame, edit


class RecoveryHintPanel(QWidget):
    """Recovery key + password hint opsional untuk pembuatan vault."""

    MODE_CODE = "code"
    MODE_PASSPHRASE = "passphrase"

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        container = QFrame(self)
        container.setObjectName("OptionsPanel")
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        container.setStyleSheet(
            "QFrame#OptionsPanel { background: rgba(255, 255, 255, 0.04); border-radius: 12px; }"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

        lay = QVBoxLayout(container)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)

        # --- Baris toggle recovery ---
        row = QHBoxLayout()
        row.setSpacing(12)
        txt = QVBoxLayout()
        txt.setSpacing(3)
        title = QLabel("Add a recovery key")
        title.setObjectName("SectionLabel")
        desc = QLabel("A second way in if you ever forget the password.")
        desc.setObjectName("OptionDesc")
        desc.setWordWrap(True)
        txt.addWidget(title)
        txt.addWidget(desc)

        self.switch_recovery = ToggleSwitch(checked=False)
        self.switch_recovery.setAccessibleName("Add a recovery key")

        row.addLayout(txt, 1)
        row.addWidget(self.switch_recovery, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(row)

        # --- Body recovery (muncul saat toggle ON) ---
        self.recovery_body = QWidget()
        body = QVBoxLayout(self.recovery_body)
        body.setContentsMargins(0, 8, 0, 0)
        body.setSpacing(8)

        seg = QHBoxLayout()
        seg.setSpacing(8)
        self.btn_code = QPushButton(" Generate code")
        self.btn_code.setIcon(qta.icon("mdi6.dice-5-outline", color="white"))
        self.btn_pass = QPushButton(" Use passphrase")
        self.btn_pass.setIcon(qta.icon("mdi6.form-textbox-password", color="white"))
        for b in (self.btn_code, self.btn_pass):
            b.setCheckable(True)
            b.setObjectName("BtnGen")
            b.setFixedHeight(34)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            seg.addWidget(b, 1)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.addButton(self.btn_code)
        self._group.addButton(self.btn_pass)
        self.btn_code.setChecked(True)
        body.addLayout(seg)

        self.entry_pass = PasswordLineEdit("Recovery passphrase…")
        self.entry_pass.setAccessibleName("Recovery passphrase")
        self.entry_pass.hide()
        body.addWidget(self.entry_pass)

        self.lbl_code_note = QLabel(
            "A one-time recovery code will be shown after locking — save it somewhere safe."
        )
        self.lbl_code_note.setObjectName("OptionDesc")
        self.lbl_code_note.setWordWrap(True)
        body.addWidget(self.lbl_code_note)

        self.recovery_body.setVisible(False)
        lay.addWidget(self.recovery_body)

        # --- Hint (selalu terlihat) ---
        lay.addSpacing(6)
        hint_title = QLabel("Password hint (optional)")
        hint_title.setObjectName("SectionLabel")
        lay.addWidget(hint_title)

        hint_frame, self.entry_hint = _make_text_input("e.g. our first trip together")
        self.entry_hint.setAccessibleName("Password hint")
        self.entry_hint.setMaxLength(160)
        lay.addWidget(hint_frame)

        hint_warn = QLabel(
            "Stored unencrypted in the vault — never put your actual password here."
        )
        hint_warn.setObjectName("OptionDesc")
        hint_warn.setWordWrap(True)
        hint_warn.setStyleSheet(f"color: {CLR_WARN};")
        lay.addWidget(hint_warn)

        # Sinyal
        self.switch_recovery.toggled.connect(self._on_recovery_toggled)
        self.btn_pass.toggled.connect(self._on_mode_changed)
        self.entry_pass.textChanged.connect(lambda *_: self.changed.emit())
        self.entry_hint.textChanged.connect(lambda *_: self.changed.emit())

    # ── Reaksi ──────────────────────────────────────────────────────────────
    def _on_recovery_toggled(self, on: bool):
        self.recovery_body.setVisible(on)
        self.changed.emit()

    def _on_mode_changed(self, passphrase_mode: bool):
        self.entry_pass.setVisible(passphrase_mode)
        self.lbl_code_note.setVisible(not passphrase_mode)
        self.changed.emit()

    # ── Public API (dipanggil TabKunci) ─────────────────────────────────────
    def recovery_enabled(self) -> bool:
        return self.switch_recovery.isChecked()

    def recovery_mode(self) -> str:
        return self.MODE_PASSPHRASE if self.btn_pass.isChecked() else self.MODE_CODE

    def recovery_passphrase(self) -> str:
        return self.entry_pass.text()

    def get_hint(self) -> str:
        return self.entry_hint.text().strip()

    def has_pending_passphrase_error(self) -> bool:
        """True jika recovery aktif dengan mode passphrase tapi passphrase kosong."""
        return (
            self.recovery_enabled()
            and self.recovery_mode() == self.MODE_PASSPHRASE
            and not self.recovery_passphrase().strip()
        )

    def set_busy(self, busy: bool):
        self.switch_recovery.setEnabled(not busy)
        self.btn_code.setEnabled(not busy)
        self.btn_pass.setEnabled(not busy)
        self.entry_pass.setEnabled(not busy)
        self.entry_hint.setEnabled(not busy)

    def reset(self):
        self.switch_recovery.setChecked(False)
        self.btn_code.setChecked(True)
        self.entry_pass.clear()
        self.entry_hint.clear()
        self.recovery_body.setVisible(False)
        self.entry_pass.hide()
        self.lbl_code_note.setVisible(True)
