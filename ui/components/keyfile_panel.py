"""
Modul: keyfile_panel.py
Deskripsi: Opsi opsional saat MEMBUAT vault (Tab Kunci): lindungi dengan keyfile
           (2FA). Saat aktif, membuka vault WAJIB punya password DAN keyfile yang
           dipilih di sini. User bisa memilih file yang sudah ada atau membuat
           keyfile acak baru lewat tombol Generate.

           Gaya & gating (aktif hanya setelah password valid + tidak sedang sibuk)
           dibuat konsisten dengan RecoveryHintPanel.
"""

import os

import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.vault import VaultStatus, generate_keyfile

from ..i18n import register, tr
from ..styles import CLR_ACCENT, CLR_BORDER, CLR_INSET, CLR_WARN
from ..widgets import ElidedLabel, ToggleSwitch


class KeyfilePanel(QWidget):
    """Toggle + pemilih keyfile opsional untuk pembuatan vault (2FA)."""

    changed = Signal()
    # Diteruskan ke TabKunci untuk menampilkan notifikasi hasil generate keyfile.
    notify = Signal(str, str)  # (level: "ok"|"err", message)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._password_ready = False
        self._busy = False
        self._keyfile_path = ""
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

        # --- Baris toggle ---
        row = QHBoxLayout()
        row.setSpacing(12)
        txt = QVBoxLayout()
        txt.setSpacing(3)
        title = QLabel()
        title.setObjectName("SectionLabel")
        register(title, "keyfile.add.title", "Protect with a keyfile (2FA)")
        desc = QLabel()
        desc.setObjectName("OptionDesc")
        desc.setWordWrap(True)
        register(
            desc,
            "keyfile.add.desc",
            "Require a secret file in addition to your password to open this vault.",
        )
        txt.addWidget(title)
        txt.addWidget(desc)

        self.switch_keyfile = ToggleSwitch(checked=False)
        self.switch_keyfile.setEnabled(False)
        register(
            self.switch_keyfile,
            "a11y.switch.add_keyfile",
            "Protect with a keyfile",
            "setAccessibleName",
        )
        row.addLayout(txt, 1)
        row.addWidget(self.switch_keyfile, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(row)

        # --- Body (muncul saat toggle ON) ---
        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 8, 0, 0)
        body.setSpacing(8)

        body.addWidget(self._build_info_box())

        # Baris file terpilih + tombol.
        file_row = QHBoxLayout()
        file_row.setSpacing(10)
        icon = QLabel()
        icon.setPixmap(qta.icon("mdi6.key-chain-variant", color=CLR_ACCENT).pixmap(16, 16))
        file_row.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
        self.lbl_file = ElidedLabel(tr("keyfile.none", "No keyfile selected"))
        self.lbl_file.setObjectName("MutedText")
        file_row.addWidget(self.lbl_file, 1)
        body.addLayout(file_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.btn_choose = QPushButton()
        register(self.btn_choose, "keyfile.choose", "Choose file…")
        self.btn_choose.setObjectName("BtnInlineSecondary")
        self.btn_choose.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_choose.clicked.connect(self._choose_keyfile)
        btn_row.addWidget(self.btn_choose)

        self.btn_generate = QPushButton()
        register(self.btn_generate, "keyfile.generate", "Generate…")
        self.btn_generate.setObjectName("BtnInlineSecondary")
        self.btn_generate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_generate.clicked.connect(self._generate_keyfile)
        btn_row.addWidget(self.btn_generate)
        btn_row.addStretch(1)
        body.addLayout(btn_row)

        self.body.setVisible(False)
        lay.addWidget(self.body)

        self.switch_keyfile.toggled.connect(self._on_toggled)

    def _build_info_box(self) -> QFrame:
        box = QFrame()
        box.setObjectName("KeyfileInfoBox")
        box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        box.setStyleSheet(
            f"QFrame#KeyfileInfoBox {{ background-color: {CLR_INSET};"
            f" border: 1px solid {CLR_BORDER}; border-radius: 10px; }}"
        )
        lay = QHBoxLayout(box)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)
        icon = QLabel()
        icon.setPixmap(qta.icon("mdi6.alert-outline", color=CLR_WARN).pixmap(16, 16))
        lay.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        txt = QLabel()
        txt.setObjectName("OptionDesc")
        txt.setWordWrap(True)
        register(
            txt,
            "keyfile.warn",
            "You'll need this exact file plus your password every time. "
            "Keep a backup — lose the keyfile and only your recovery key can get you in.",
        )
        lay.addWidget(txt, 1)
        return box

    # ── Reaksi ──────────────────────────────────────────────────────────────
    def _on_toggled(self, on: bool):
        self.body.setVisible(on)
        self.changed.emit()

    def _set_keyfile(self, path: str):
        self._keyfile_path = path
        name = os.path.basename(path) if path else tr("keyfile.none", "No keyfile selected")
        self.lbl_file.setText(name)
        self.changed.emit()

    def _choose_keyfile(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("keyfile.choose.dialog", "Choose keyfile"), "", ""
        )
        if path:
            self._set_keyfile(path)

    def _generate_keyfile(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("keyfile.generate.dialog", "Create keyfile"),
            "adyton.key",
            tr("keyfile.generate.filter", "Keyfile (*.key)"),
        )
        if not path:
            return
        status, message = generate_keyfile(path)
        if status == VaultStatus.SUCCESS:
            self._set_keyfile(path)
            self.notify.emit("ok", message)
        else:
            self.notify.emit("err", message)

    # ── Public API (dipanggil TabKunci) ─────────────────────────────────────
    def keyfile_enabled(self) -> bool:
        return self.switch_keyfile.isChecked()

    def keyfile_path(self) -> str:
        return self._keyfile_path

    def has_pending_keyfile_error(self) -> bool:
        """True jika keyfile diaktifkan tapi belum ada file dipilih."""
        return self.keyfile_enabled() and not self._keyfile_path

    def set_password_ready(self, ready: bool):
        self._password_ready = bool(ready)
        self._refresh_switch_enabled()
        if not self._password_ready and self.switch_keyfile.isChecked():
            self.switch_keyfile.setChecked(False)

    def set_busy(self, busy: bool):
        self._busy = bool(busy)
        self._refresh_switch_enabled()
        self.btn_choose.setEnabled(not busy)
        self.btn_generate.setEnabled(not busy)

    def _refresh_switch_enabled(self):
        self.switch_keyfile.setEnabled(self._password_ready and not self._busy)

    def reset(self):
        self._password_ready = False
        self._refresh_switch_enabled()
        self.switch_keyfile.setChecked(False)
        self._keyfile_path = ""
        self.lbl_file.setText(tr("keyfile.none", "No keyfile selected"))
        self.body.setVisible(False)
