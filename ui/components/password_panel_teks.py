"""
Modul: password_panel_teks.py
Deskripsi: Panel password Tab Teks — toggle Encrypt/Decrypt. Mode enkripsi memakai
           CreatePasswordForm bersama (gate = Tab Kunci); mode dekripsi cukup satu
           field password (validasi non-kosong).
"""

import qtawesome as qta
from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from ..styles import CLR_ACCENT, CLR_ON_ACCENT, CLR_TEXT_DIM, CLR_WARN
from ..widgets import (
    PasswordLineEdit,
    apply_shadow,
    build_card_header,
    build_tips_box,
    make_generator_button,
)
from .create_password_form import CreatePasswordForm


class PasswordPanelTeks(QFrame):
    """Panel kanan Tab Teks: toggle mode (enkripsi/dekripsi) + input password.

    Mode enkripsi memakai CreatePasswordForm bersama (gate = Tab Kunci); mode
    dekripsi cukup satu field password (validasi non-kosong).
    """

    valid_state_changed = Signal(bool)
    mode_changed = Signal(str)  # "enkripsi" | "dekripsi"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        apply_shadow(self, blur_radius=30, opacity=40)
        self._mode = "enkripsi"
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(10)

        # ── Header ────────────────────────────────────────────────────────────
        self.btn_gen = make_generator_button()
        header, self.lbl_card_title, self.lbl_card_sub = build_card_header(
            "mdi6.key-outline",
            CLR_WARN,
            "Set a Password",
            "A strong password keeps your text safe",
            button=self.btn_gen,
        )
        lay.addLayout(header)

        # ── Mode toggle ───────────────────────────────────────────────────────
        toggle_container = QFrame()
        toggle_container.setObjectName("TabContainer")
        toggle_container.setFixedHeight(38)
        lay_toggle = QHBoxLayout(toggle_container)
        lay_toggle.setContentsMargins(3, 3, 3, 3)
        lay_toggle.setSpacing(3)

        self.btn_mode_enkripsi = QPushButton(" Encrypt")
        self.btn_mode_enkripsi.setIcon(
            qta.icon("mdi6.lock-outline", color=CLR_TEXT_DIM, color_on=CLR_ON_ACCENT)
        )
        self.btn_mode_enkripsi.setIconSize(QSize(16, 16))
        self.btn_mode_enkripsi.setObjectName("TabBtn")
        self.btn_mode_enkripsi.setCheckable(True)
        self.btn_mode_enkripsi.setChecked(True)
        self.btn_mode_enkripsi.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self.btn_mode_dekripsi = QPushButton(" Decrypt")
        self.btn_mode_dekripsi.setIcon(
            qta.icon("mdi6.lock-open-variant-outline", color=CLR_TEXT_DIM, color_on=CLR_ON_ACCENT)
        )
        self.btn_mode_dekripsi.setIconSize(QSize(16, 16))
        self.btn_mode_dekripsi.setObjectName("TabBtn")
        self.btn_mode_dekripsi.setCheckable(True)
        self.btn_mode_dekripsi.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self.btn_mode_enkripsi, 0)
        self._mode_group.addButton(self.btn_mode_dekripsi, 1)
        self._mode_group.buttonClicked.connect(self._on_toggle_clicked)

        lay_toggle.addWidget(self.btn_mode_enkripsi)
        lay_toggle.addWidget(self.btn_mode_dekripsi)
        lay.addWidget(toggle_container)

        # ── Mode enkripsi: form pembuatan password bersama (= Tab Kunci) ───────
        self.form = CreatePasswordForm()
        self.form.valid_state_changed.connect(lambda _: self._check_valid())
        lay.addWidget(self.form)

        # ── Mode dekripsi: cukup satu field password ───────────────────────────
        self.entry_decrypt = PasswordLineEdit("Type your password here…")
        self.entry_decrypt.setAccessibleName("Text decryption password")
        self.entry_decrypt.textChanged.connect(lambda _: self._check_valid())
        lay.addWidget(self.entry_decrypt)

        # Generator mengisi form (hanya relevan di mode enkripsi)
        self.btn_gen.clicked.connect(self.form.generate)

        # Serap ruang vertikal sisa (spt Tab Kunci & Tab Buka) supaya input tidak
        # ikut melar saat mode dekripsi; tips dipin ke bawah seperti Tab Buka.
        lay.addStretch()

        # ── Tips ──────────────────────────────────────────────────────────────
        self._tips_box = self._build_tips_box()
        lay.addWidget(self._tips_box)

        # Inisialisasi tampilan ke mode enkripsi
        self.set_mode("enkripsi")

    # ── Tips builder ──────────────────────────────────────────────────────────

    def _build_tips_box(self) -> QFrame:
        tips = [
            (
                "mdi6.shield-check-outline",
                CLR_ACCENT,
                "Your password can't be recovered. Keep it somewhere safe.",
            ),
            (
                "mdi6.clipboard-text-outline",
                CLR_ACCENT,
                "The encrypted result can be saved anywhere — email, notes, chat.",
            ),
            (
                "mdi6.lock-outline",
                CLR_ACCENT,
                "To decrypt, use the exact same password you set here.",
            ),
        ]
        return build_tips_box(tips)

    # ── Mode switching ──────────────────────────────────────────────────────

    def _on_toggle_clicked(self, button: QPushButton):
        mode = "enkripsi" if self._mode_group.id(button) == 0 else "dekripsi"
        self.set_mode(mode)

    def set_mode(self, mode: str):
        """Atur mode panel. Aman dipanggil dari luar (mis. auto-detect TabTeks)."""
        changed = mode != self._mode
        self._mode = mode
        is_enc = mode == "enkripsi"

        self.lbl_card_title.setText("Set a Password" if is_enc else "Enter Your Password")
        self.lbl_card_sub.setText(
            "A strong password keeps your text safe"
            if is_enc
            else "Enter the password you used during encryption"
        )
        self.btn_gen.setVisible(is_enc)
        self.form.setVisible(is_enc)
        self.entry_decrypt.setVisible(not is_enc)

        # Sinkronkan tombol toggle (penting saat set_mode dipanggil programatis)
        self.btn_mode_enkripsi.setChecked(is_enc)
        self.btn_mode_dekripsi.setChecked(not is_enc)

        # Bersihkan input tiap ganti mode
        self.form.reset()
        self.entry_decrypt.clear()

        if changed:
            self.mode_changed.emit(mode)
        self._check_valid()

    # ── Password validation ───────────────────────────────────────────────────

    def _check_valid(self):
        ok = self.form.is_valid() if self._mode == "enkripsi" else bool(self.entry_decrypt.text())
        self.valid_state_changed.emit(ok)

    # ── Public API ────────────────────────────────────────────────────────────

    def get_mode(self) -> str:
        return self._mode

    def get_password(self) -> str:
        if self._mode == "enkripsi":
            return self.form.get_password()
        return self.entry_decrypt.text()

    def is_valid(self) -> bool:
        if self._mode == "enkripsi":
            return self.form.is_valid()
        return bool(self.entry_decrypt.text())

    def set_busy(self, busy: bool):
        self.form.set_busy(busy)
        self.entry_decrypt.setEnabled(not busy)
        self.btn_gen.setEnabled(not busy)
        self.btn_mode_enkripsi.setEnabled(not busy)
        self.btn_mode_dekripsi.setEnabled(not busy)

    def reset(self):
        self.form.reset()
        self.entry_decrypt.clear()
        self._check_valid()

    def attach_return_event(self, callback):
        """Daftarkan callback Enter di field password kedua mode."""
        self.form.attach_return_event(callback)
        self.entry_decrypt.returnPressed.connect(callback)
