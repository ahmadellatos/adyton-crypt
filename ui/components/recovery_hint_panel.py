"""
Modul: recovery_hint_panel.py
Deskripsi: Opsi opsional saat MEMBUAT vault (Tab Kunci): recovery key + password
           hint. Recovery bisa berupa kode app-generated (ditampilkan setelah
           kunci) atau passphrase pilihan user. Hint disimpan TANPA enkripsi.

           Pemilih metode memakai MethodCard bersama agar tampil konsisten dengan
           Tab Manage.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ..i18n import register
from ..styles import CLR_WARN
from ..widgets import MethodCard, PasswordLineEdit, ToggleSwitch, make_recovery_info_box


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
        self._mode = self.MODE_CODE
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
        title = QLabel()
        title.setObjectName("SectionLabel")
        register(title, "recovery.add.title", "Add a recovery key")
        desc = QLabel()
        desc.setObjectName("OptionDesc")
        desc.setWordWrap(True)
        register(desc, "recovery.add.desc", "A second way in if you ever forget the password.")
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

        body.addWidget(make_recovery_info_box())

        method_lbl = QLabel()
        method_lbl.setObjectName("SectionLabel")
        register(method_lbl, "recovery.method", "Recovery method")
        body.addWidget(method_lbl)

        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.card_code = MethodCard(
            "mdi6.dice-5-outline",
            "Generate code",
            "Create a one-time recovery code, shown once.",
        )
        self.card_code.tr_set(
            "recovery.card.code.title",
            "Generate code",
            "recovery.card.code.desc",
            "Create a one-time recovery code, shown once.",
        )
        self.card_pass = MethodCard(
            "mdi6.form-textbox-password",
            "Use passphrase",
            "Set a recovery phrase you choose yourself.",
        )
        self.card_pass.tr_set(
            "recovery.card.pass.title",
            "Use passphrase",
            "recovery.card.pass.desc",
            "Set a recovery phrase you choose yourself.",
        )
        cards.addWidget(self.card_code, 1)
        cards.addWidget(self.card_pass, 1)
        body.addLayout(cards)

        self.entry_pass = PasswordLineEdit()
        register(
            self.entry_pass,
            "recovery.passphrase_placeholder",
            "Recovery passphrase…",
            "setPlaceholderText",
        )
        self.entry_pass.setAccessibleName("Recovery passphrase")
        self.entry_pass.hide()
        body.addWidget(self.entry_pass)

        self.recovery_body.setVisible(False)
        lay.addWidget(self.recovery_body)

        # --- Hint (selalu terlihat) ---
        lay.addSpacing(6)
        hint_title = QLabel()
        hint_title.setObjectName("SectionLabel")
        register(hint_title, "hint.title", "Password hint (optional)")
        lay.addWidget(hint_title)

        hint_frame, self.entry_hint = _make_text_input("e.g. our first trip together")
        register(
            self.entry_hint,
            "hint.placeholder",
            "e.g. our first trip together",
            "setPlaceholderText",
        )
        self.entry_hint.setAccessibleName("Password hint")
        self.entry_hint.setMaxLength(160)
        lay.addWidget(hint_frame)

        hint_warn = QLabel()
        hint_warn.setObjectName("OptionDesc")
        hint_warn.setWordWrap(True)
        register(
            hint_warn,
            "hint.warn",
            "Stored unencrypted in the vault — never put your actual password here.",
        )
        hint_warn.setStyleSheet(f"color: {CLR_WARN};")
        lay.addWidget(hint_warn)

        # Default metode: generate code.
        self.card_code.set_selected(True)
        self.card_pass.set_selected(False)

        # Sinyal
        self.switch_recovery.toggled.connect(self._on_recovery_toggled)
        self.card_code.clicked.connect(lambda: self._select_method(self.MODE_CODE))
        self.card_pass.clicked.connect(lambda: self._select_method(self.MODE_PASSPHRASE))
        self.entry_pass.textChanged.connect(lambda *_: self.changed.emit())
        self.entry_hint.textChanged.connect(lambda *_: self.changed.emit())

    # ── Reaksi ──────────────────────────────────────────────────────────────
    def _on_recovery_toggled(self, on: bool):
        self.recovery_body.setVisible(on)
        self.changed.emit()

    def _select_method(self, method: str):
        self._mode = method
        self.card_code.set_selected(method == self.MODE_CODE)
        self.card_pass.set_selected(method == self.MODE_PASSPHRASE)
        self.entry_pass.setVisible(method == self.MODE_PASSPHRASE)
        self.changed.emit()

    # ── Public API (dipanggil TabKunci) ─────────────────────────────────────
    def recovery_enabled(self) -> bool:
        return self.switch_recovery.isChecked()

    def recovery_mode(self) -> str:
        return self._mode

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
        self.card_code.setEnabled(not busy)
        self.card_pass.setEnabled(not busy)
        self.entry_pass.setEnabled(not busy)
        self.entry_hint.setEnabled(not busy)

    def reset(self):
        self.switch_recovery.setChecked(False)
        self._mode = self.MODE_CODE
        self.card_code.set_selected(True)
        self.card_pass.set_selected(False)
        self.entry_pass.clear()
        self.entry_pass.hide()
        self.entry_hint.clear()
        self.recovery_body.setVisible(False)
