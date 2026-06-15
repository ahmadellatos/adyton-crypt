import secrets
import string

import qtawesome as qta
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from zxcvbn import zxcvbn

from ..styles import (
    CLR_ACCENT,
    CLR_BORDER,
    CLR_DANGER,
    CLR_SUCCESS,
    CLR_WARN,
    muted_label_style,
)

# Import dari parent project
from ..widgets import PasswordLineEdit, apply_shadow


def pw_strength(pw: str) -> int:
    if not pw:
        return -1
    hasil = zxcvbn(pw)
    skor = hasil["score"]
    return 0 if skor <= 1 else skor - 1


STRENGTH_COLORS = [CLR_DANGER, CLR_WARN, CLR_ACCENT, CLR_ACCENT]
STRENGTH_LABELS = ["Weak", "Fair", "Strong", "Very Strong"]


class PasswordPanelLock(QFrame):
    # Sinyal untuk memberitahu TabKunci apakah password sudah memenuhi syarat
    valid_state_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        apply_shadow(self, blur_radius=30, opacity=40)

        self._strength_visible = False
        self._build_ui()
        self._setup_accessibility()

    def _build_ui(self):
        lay_pw = QVBoxLayout(self)
        lay_pw.setContentsMargins(24, 18, 24, 18)
        lay_pw.setSpacing(10)  # Tight but premium vertical rhythm

        # Header card password
        row_hdr_pw = QHBoxLayout()
        icon_key = QLabel()
        icon_key.setPixmap(qta.icon("mdi6.key-variant", color=CLR_WARN).pixmap(32, 32))
        icon_key.setAlignment(Qt.AlignmentFlag.AlignTop)

        v_hdr_pw_txt = QVBoxLayout()
        v_hdr_pw_txt.setSpacing(3)
        lbl_pw = QLabel("Set a Password")
        lbl_pw.setObjectName("CardTitle")
        lbl_pw_sub = QLabel("A strong password keeps your data safe")
        lbl_pw_sub.setObjectName("CardSubtitle")
        lbl_pw_sub.setWordWrap(True)
        v_hdr_pw_txt.addWidget(lbl_pw)
        v_hdr_pw_txt.addWidget(lbl_pw_sub)

        self.btn_gen = QPushButton(" Generator")
        self.btn_gen.setIcon(qta.icon("mdi6.creation", color="white"))
        self.btn_gen.setFixedHeight(36)  # lebih seimbang dengan header & icon 32px
        self.btn_gen.setObjectName("BtnGen")
        self.btn_gen.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_gen.setAccessibleName("Generate Strong Password")
        self.btn_gen.clicked.connect(self._generate_pw)

        row_hdr_pw.addWidget(icon_key)
        row_hdr_pw.addLayout(v_hdr_pw_txt, 1)
        row_hdr_pw.addSpacing(8)
        row_hdr_pw.addWidget(self.btn_gen, alignment=Qt.AlignmentFlag.AlignTop)
        lay_pw.addLayout(row_hdr_pw)

        lay_pw.addSpacing(4)

        # Input password pertama
        lbl_in1 = QLabel("Password")
        lbl_in1.setObjectName("SectionLabel")
        lay_pw.addWidget(lbl_in1)

        v_pw1_group = QVBoxLayout()
        v_pw1_group.setSpacing(0)

        self.entry_pw1 = PasswordLineEdit("Enter a strong password…")
        self.entry_pw1.setAccessibleName("New password")
        self.entry_pw1.textChanged.connect(self._on_pw_change)
        v_pw1_group.addWidget(self.entry_pw1)

        # Strength bar (animasi collapse)
        self.widget_strength = QWidget()
        self.widget_strength.setMaximumHeight(0)
        self.widget_strength.setMinimumHeight(0)

        row_str = QHBoxLayout(self.widget_strength)
        row_str.setContentsMargins(0, 8, 0, 0)
        row_str.setSpacing(8)

        self.str_bars = []
        for _ in range(4):
            bar = QFrame()
            bar.setFixedHeight(6)
            bar.setStyleSheet(f"background-color: {CLR_BORDER}; border-radius: 3px;")
            self.str_bars.append(bar)
            row_str.addWidget(bar, 1)

        self.lbl_str = QLabel("Strength")
        self.lbl_str.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.lbl_str.setStyleSheet(muted_label_style("9pt") + " font-weight: 600;")
        self.lbl_str.setMinimumWidth(140)
        row_str.addWidget(self.lbl_str)
        v_pw1_group.addWidget(self.widget_strength)

        self.anim_strength = QPropertyAnimation(self.widget_strength, b"maximumHeight")
        self.anim_strength.setDuration(250)
        self.anim_strength.setEasingCurve(QEasingCurve.Type.InOutCubic)

        # Checklist kriteria password
        self.lay_chk = QVBoxLayout()
        self.lay_chk.setContentsMargins(4, 8, 4, 2)

        grid_chk = QGridLayout()
        grid_chk.setContentsMargins(0, 0, 0, 0)
        grid_chk.setHorizontalSpacing(20)
        grid_chk.setVerticalSpacing(6)
        grid_chk.setColumnStretch(0, 1)
        grid_chk.setColumnStretch(1, 1)

        def _create_chk_item(text):
            lay = QHBoxLayout()
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(6)
            icon = QLabel()
            icon.setPixmap(qta.icon("mdi6.check-circle-outline", color=CLR_BORDER).pixmap(16, 16))
            lbl = QLabel(text)
            lbl.setObjectName("ChecklistLabel")
            lbl.setProperty("valid", False)
            lbl.setWordWrap(True)
            lay.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)
            lay.addWidget(lbl, 1)
            return lay, icon, lbl

        l1, self.chk_len_icon, self.chk_len_lbl = _create_chk_item("At least 8 characters")
        l2, self.chk_upper_icon, self.chk_upper_lbl = _create_chk_item("Uppercase letter (A-Z)")
        l3, self.chk_lower_icon, self.chk_lower_lbl = _create_chk_item("Lowercase letter (a-z)")
        l4, self.chk_digit_icon, self.chk_digit_lbl = _create_chk_item("Number (0-9)")
        l5, self.chk_sym_icon, self.chk_sym_lbl = _create_chk_item("Symbol (!@#$%^&*)")

        grid_chk.addLayout(l1, 0, 0)
        grid_chk.addLayout(l4, 0, 1)
        grid_chk.addLayout(l2, 1, 0)
        grid_chk.addLayout(l5, 1, 1)
        grid_chk.addLayout(l3, 2, 0)

        self.lay_chk.addLayout(grid_chk)
        v_pw1_group.addLayout(self.lay_chk)
        lay_pw.addLayout(v_pw1_group)

        # Jarak yang lebih lega sebelum section konfirmasi (premium breathing)
        lay_pw.addSpacing(6)

        # Input konfirmasi password
        lbl_in2 = QLabel("Confirm Password")
        lbl_in2.setObjectName("SectionLabel")
        lay_pw.addWidget(lbl_in2)

        self.entry_pw2 = PasswordLineEdit("Repeat your password…")
        self.entry_pw2.setAccessibleName("Confirm new password")
        self.entry_pw2.textChanged.connect(self._on_pw_change)
        lay_pw.addWidget(self.entry_pw2)

        # Indikator match / tidak cocok
        self.lay_match = QHBoxLayout()
        self.lay_match.setContentsMargins(4, 2, 0, 0)
        self.lay_match.setSpacing(6)
        self.icon_match = QLabel()
        self.icon_match.setFixedSize(16, 16)
        self.lbl_match_txt = QLabel("Passwords match")
        self.lbl_match_txt.setObjectName("PwMatchLabel")
        self.lbl_match_txt.setWordWrap(True)
        self.lay_match.addWidget(self.icon_match, alignment=Qt.AlignmentFlag.AlignTop)
        self.lay_match.addWidget(self.lbl_match_txt, 1)
        self.icon_match.hide()
        self.lbl_match_txt.hide()

        lay_pw.addLayout(self.lay_match)
        lay_pw.addStretch()

    def _setup_accessibility(self):
        self.btn_gen.installEventFilter(self)
        self.entry_pw1.installEventFilter(self)
        self.entry_pw2.installEventFilter(self)

        self.btn_gen.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setTabOrder(self.btn_gen, self.entry_pw1)
        self.setTabOrder(self.entry_pw1, self.entry_pw2)

    def eventFilter(self, obj, event):
        # Focus styling is now handled inside PasswordLineEdit
        if event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                if isinstance(obj, QPushButton):
                    if obj == self.btn_gen:
                        obj.click()
                        return True

        return super().eventFilter(obj, event)

    def _generate_pw(self):
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        while True:
            pw = "".join(secrets.choice(alphabet) for i in range(16))
            if (
                any(c.islower() for c in pw)
                and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw)
                and any(not c.isalnum() and not c.isspace() for c in pw)
            ):
                break

        self.entry_pw1.setText(pw)
        self.entry_pw2.setText(pw)
        self.entry_pw1.setEchoMode(QLineEdit.EchoMode.Normal)
        self.entry_pw2.setEchoMode(QLineEdit.EchoMode.Normal)

    def _on_pw_change(self):
        pw1, pw2 = self.entry_pw1.text(), self.entry_pw2.text()

        # Logic animasi strength
        if not pw1:
            if self._strength_visible:
                self._strength_visible = False
                self.anim_strength.setStartValue(self.widget_strength.maximumHeight())
                self.anim_strength.setEndValue(0)
                self.anim_strength.start()
        else:
            if not self._strength_visible:
                self._strength_visible = True
                self.anim_strength.setStartValue(0)
                self.anim_strength.setEndValue(26)
                self.anim_strength.start()

            score = pw_strength(pw1)
            for i, bar in enumerate(self.str_bars):
                if score >= 0 and i <= score:
                    bar.setStyleSheet(
                        f"background-color: {STRENGTH_COLORS[score]}; border-radius: 3px;"
                    )
                else:
                    bar.setStyleSheet(f"background-color: {CLR_BORDER}; border-radius: 3px;")

            if score < 0:
                self.lbl_str.setText("Strength: -")
                self.lbl_str.setStyleSheet(muted_label_style("9pt") + " font-weight: 600;")
            else:
                self.lbl_str.setText(f"Strength: {STRENGTH_LABELS[score]}")
                self.lbl_str.setStyleSheet(
                    f"color: {STRENGTH_COLORS[score]}; font-size: 9pt; font-weight: bold;"
                )

        # Update checklist
        rules = [
            (len(pw1) >= 8, self.chk_len_icon, self.chk_len_lbl),
            (any(c.isupper() for c in pw1), self.chk_upper_icon, self.chk_upper_lbl),
            (any(c.islower() for c in pw1), self.chk_lower_icon, self.chk_lower_lbl),
            (any(c.isdigit() for c in pw1), self.chk_digit_icon, self.chk_digit_lbl),
            (
                any(not c.isalnum() and not c.isspace() for c in pw1),
                self.chk_sym_icon,
                self.chk_sym_lbl,
            ),
        ]

        for is_valid, icon, lbl in rules:
            if is_valid:
                icon.setPixmap(qta.icon("mdi6.check-circle", color=CLR_SUCCESS).pixmap(16, 16))
                lbl.setProperty("valid", True)
            else:
                icon.setPixmap(
                    qta.icon("mdi6.check-circle-outline", color=CLR_BORDER).pixmap(16, 16)
                )
                lbl.setProperty("valid", False)
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)

        # Match logic
        if not pw2:
            self.icon_match.hide()
            self.lbl_match_txt.hide()
        elif pw1 == pw2:
            self.icon_match.show()
            self.lbl_match_txt.show()
            self.icon_match.setPixmap(
                qta.icon("mdi6.check-circle", color=CLR_SUCCESS).pixmap(16, 16)
            )
            self.lbl_match_txt.setText("Passwords match")
            self.lbl_match_txt.setStyleSheet(f"color: {CLR_SUCCESS};")
        else:
            self.icon_match.show()
            self.lbl_match_txt.show()
            self.icon_match.setPixmap(
                qta.icon("mdi6.close-circle", color=CLR_DANGER).pixmap(16, 16)
            )
            self.lbl_match_txt.setText("Passwords don't match")
            self.lbl_match_txt.setStyleSheet(f"color: {CLR_DANGER};")

        # Evaluasi final state
        # Tombol kunci hanya aktif jika seluruh checklist yang ditampilkan
        # kepada user benar-benar terpenuhi, bukan hanya skor zxcvbn.
        score = pw_strength(pw1)
        rules_ok = all(rule_ok for rule_ok, _, _ in rules)
        is_strong_enough = score >= 1
        is_valid = bool(pw1) and (pw1 == pw2) and rules_ok and is_strong_enough

        # Pancarkan sinyal ke parent!
        self.valid_state_changed.emit(is_valid)

    # --- PUBLIC API (Untuk dipanggil oleh TabKunci) ---
    def get_password(self) -> str:
        """Mengambil teks password saat ini."""
        return self.entry_pw1.text()

    def reset_fields(self):
        """Mengosongkan form password setelah berhasil."""
        self.entry_pw1.blockSignals(True)
        self.entry_pw2.blockSignals(True)

        self.entry_pw1.clear()
        self.entry_pw2.clear()

        self.entry_pw1.blockSignals(False)
        self.entry_pw2.blockSignals(False)
        self._on_pw_change()  # Trigger refresh UI

    def attach_return_event(self, slot_func):
        """Meneruskan event tombol Enter ke fungsi eksekusi parent."""
        self.entry_pw2.returnPressed.connect(slot_func)
