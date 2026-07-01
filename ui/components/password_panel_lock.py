"""
Modul: password_panel_lock.py
Deskripsi: Panel password Tab Kunci. Kini tipis — Card + header (ikon, judul,
           tombol generator) yang membungkus CreatePasswordForm bersama.
           Logika strength/checklist/konfirmasi hidup di CreatePasswordForm.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
)

from ..i18n import register
from ..styles import CLR_WARN
from ..widgets import apply_shadow, build_card_header, make_generator_button
from .create_password_form import CreatePasswordForm
from .keyfile_panel import KeyfilePanel
from .recovery_hint_panel import RecoveryHintPanel


class PasswordPanelLock(QFrame):
    # Diteruskan dari CreatePasswordForm agar TabKunci tak perlu berubah.
    valid_state_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        apply_shadow(self, blur_radius=30, opacity=40)
        self._build_ui()
        self._setup_accessibility()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(10)

        self.btn_gen = make_generator_button()
        header, lbl_t, lbl_s = build_card_header(
            "mdi6.key-outline",
            CLR_WARN,
            "Set a Password",
            "A strong password keeps your data safe",
            button=self.btn_gen,
        )
        register(lbl_t, "card.setpw.title", "Set a Password")
        register(lbl_s, "card.setpw.sub.lock", "A strong password keeps your data safe")
        lay.addLayout(header)
        lay.addSpacing(4)

        self.form = CreatePasswordForm()
        self.form.valid_state_changed.connect(self.valid_state_changed)
        self.btn_gen.clicked.connect(self.form.generate)
        lay.addWidget(self.form)

        lay.addSpacing(8)
        self.recovery_hint = RecoveryHintPanel()
        # Toggle "Add recovery key" aktif hanya setelah semua syarat checklist
        # password terpenuhi.
        self.form.requirements_met_changed.connect(self.recovery_hint.set_password_ready)
        lay.addWidget(self.recovery_hint)

        lay.addSpacing(8)
        self.keyfile_panel = KeyfilePanel()
        # Toggle keyfile (2FA) juga aktif hanya setelah password memenuhi syarat.
        self.form.requirements_met_changed.connect(self.keyfile_panel.set_password_ready)
        lay.addWidget(self.keyfile_panel)

        lay.addStretch()

    def _setup_accessibility(self):
        self.btn_gen.installEventFilter(self)
        self.btn_gen.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setTabOrder(self.btn_gen, self.form.entry_pw1)
        self.setTabOrder(self.form.entry_pw1, self.form.entry_pw2)

    def eventFilter(self, obj, event):
        if event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                if obj is self.btn_gen:
                    obj.click()
                    return True
        return super().eventFilter(obj, event)

    # ── PUBLIC API (dipanggil oleh TabKunci) ────────────────────────────────
    def get_password(self) -> str:
        return self.form.get_password()

    def reset_fields(self):
        self.form.reset()
        self.recovery_hint.reset()
        self.keyfile_panel.reset()

    def attach_return_event(self, slot_func):
        # Enter di field password utama MAUPUN field recovery passphrase memicu kunci,
        # seragam dengan tab lain (Enter = jalankan aksi utama).
        self.form.attach_return_event(slot_func)
        self.recovery_hint.attach_return_event(slot_func)

    # --- Recovery key + hint passthrough ---
    def recovery_enabled(self) -> bool:
        return self.recovery_hint.recovery_enabled()

    def recovery_mode(self) -> str:
        return self.recovery_hint.recovery_mode()

    def recovery_passphrase(self) -> str:
        return self.recovery_hint.recovery_passphrase()

    def has_pending_passphrase_error(self) -> bool:
        return self.recovery_hint.has_pending_passphrase_error()

    def get_hint(self) -> str:
        return self.recovery_hint.get_hint()

    # --- Keyfile (2FA) passthrough ---
    def keyfile_enabled(self) -> bool:
        return self.keyfile_panel.keyfile_enabled()

    def keyfile_path(self) -> str:
        return self.keyfile_panel.keyfile_path()

    def has_pending_keyfile_error(self) -> bool:
        return self.keyfile_panel.has_pending_keyfile_error()
