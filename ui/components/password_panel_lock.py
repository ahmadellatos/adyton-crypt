import secrets
import string
import qtawesome as qta
from zxcvbn import zxcvbn

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFrame,
)
from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, Signal

# Import dari parent project
from ..widgets import apply_shadow
from ..styles import (
    CLR_TEXT_MAIN,
    CLR_DANGER,
    CLR_WARN,
    CLR_ACCENT,
    CLR_SUCCESS,
    CLR_BORDER,
    muted_label_style,
)


def pw_strength(pw: str) -> int:
    if not pw:
        return -1
    hasil = zxcvbn(pw)
    skor = hasil["score"]
    return 0 if skor <= 1 else skor - 1


STRENGTH_COLORS = [CLR_DANGER, CLR_WARN, CLR_ACCENT, CLR_ACCENT]
STRENGTH_LABELS = ["Lemah", "Cukup", "Kuat", "Sangat Kuat"]


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
        lay_pw.setContentsMargins(20, 20, 20, 20)
        lay_pw.setSpacing(8)

        # Header card password
        row_hdr_pw = QHBoxLayout()
        icon_key = QLabel()
        icon_key.setPixmap(qta.icon("mdi6.key-variant", color="#F39C12").pixmap(32, 32))
        icon_key.setAlignment(Qt.AlignmentFlag.AlignTop)

        v_hdr_pw_txt = QVBoxLayout()
        v_hdr_pw_txt.setSpacing(2)
        lbl_pw = QLabel("BUAT PASSWORD")
        lbl_pw.setObjectName("CardTitle")
        lbl_pw_sub = QLabel("Buat password yang kuat untuk melindungi data Anda")
        lbl_pw_sub.setObjectName("CardSubtitle")
        lbl_pw_sub.setWordWrap(True)
        v_hdr_pw_txt.addWidget(lbl_pw)
        v_hdr_pw_txt.addWidget(lbl_pw_sub)

        self.btn_gen = QPushButton(" Generator")
        self.btn_gen.setIcon(qta.icon("mdi6.creation", color="white"))
        self.btn_gen.setFixedHeight(32)
        self.btn_gen.setObjectName("BtnGen")
        self.btn_gen.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_gen.setAccessibleName("Generate Password Kuat")
        self.btn_gen.clicked.connect(self._generate_pw)

        row_hdr_pw.addWidget(icon_key)
        row_hdr_pw.addLayout(v_hdr_pw_txt, 1)
        row_hdr_pw.addWidget(self.btn_gen, alignment=Qt.AlignmentFlag.AlignTop)
        lay_pw.addLayout(row_hdr_pw)

        # Input password pertama
        lbl_in1 = QLabel("Password")
        lbl_in1.setStyleSheet("font-weight: 600;")
        lay_pw.addWidget(lbl_in1)

        v_pw1_group = QVBoxLayout()
        v_pw1_group.setSpacing(0)

        box_pw1 = QFrame()
        self.box_pw1 = box_pw1
        box_pw1.setObjectName("InputBox")
        lay_box1 = QHBoxLayout(box_pw1)
        lay_box1.setContentsMargins(10, 0, 5, 0)
        lay_box1.setSpacing(0)

        self.entry_pw1 = QLineEdit()
        self.entry_pw1.setObjectName("InputInside")
        self.entry_pw1.setFixedHeight(45)
        self.entry_pw1.setEchoMode(QLineEdit.EchoMode.Password)
        self.entry_pw1.setPlaceholderText("Buat password yang kuat...")
        self.entry_pw1.setAccessibleName("Password Baru")
        self.entry_pw1.textChanged.connect(self._on_pw_change)
        lay_box1.addWidget(self.entry_pw1)

        self.btn_toggle_pw1 = QPushButton()
        self.btn_toggle_pw1.setIcon(qta.icon("mdi6.eye-outline", color="#8B95A5"))
        self.btn_toggle_pw1.setIconSize(QSize(22, 22))
        self.btn_toggle_pw1.setObjectName("BtnEye")
        self.btn_toggle_pw1.setFixedSize(40, 45)
        self.btn_toggle_pw1.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_pw1.clicked.connect(
            lambda: self._toggle_field(self.entry_pw1, self.btn_toggle_pw1)
        )
        lay_box1.addWidget(self.btn_toggle_pw1)
        v_pw1_group.addWidget(box_pw1)

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

        self.lbl_str = QLabel("Kekuatan: -")
        self.lbl_str.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.lbl_str.setStyleSheet(muted_label_style("9pt") + " font-weight: bold;")
        self.lbl_str.setMinimumWidth(140)
        row_str.addWidget(self.lbl_str)
        v_pw1_group.addWidget(self.widget_strength)

        self.anim_strength = QPropertyAnimation(self.widget_strength, b"maximumHeight")
        self.anim_strength.setDuration(250)
        self.anim_strength.setEasingCurve(QEasingCurve.Type.InOutCubic)

        # Checklist kriteria password
        self.lay_chk = QVBoxLayout()
        self.lay_chk.setContentsMargins(5, 12, 5, 5)

        grid_chk = QGridLayout()
        grid_chk.setContentsMargins(0, 0, 0, 0)
        grid_chk.setHorizontalSpacing(15)
        grid_chk.setVerticalSpacing(8)
        grid_chk.setColumnStretch(0, 1)
        grid_chk.setColumnStretch(1, 1)

        def _create_chk_item(text):
            lay = QHBoxLayout()
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(8)
            icon = QLabel()
            icon.setPixmap(
                qta.icon("mdi6.check-circle", color="#232B3E").pixmap(16, 16)
            )
            lbl = QLabel(text)
            lbl.setStyleSheet(muted_label_style("9pt"))
            lbl.setWordWrap(True)
            lay.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)
            lay.addWidget(lbl, 1)
            return lay, icon, lbl

        l1, self.chk_len_icon, self.chk_len_lbl = _create_chk_item("Minimal 8 karakter")
        l2, self.chk_upper_icon, self.chk_upper_lbl = _create_chk_item(
            "Huruf besar (A-Z)"
        )
        l3, self.chk_lower_icon, self.chk_lower_lbl = _create_chk_item(
            "Huruf kecil (a-z)"
        )
        l4, self.chk_digit_icon, self.chk_digit_lbl = _create_chk_item("Angka (0-9)")
        l5, self.chk_sym_icon, self.chk_sym_lbl = _create_chk_item("Simbol (!@#$%^&*)")

        grid_chk.addLayout(l1, 0, 0)
        grid_chk.addLayout(l4, 0, 1)
        grid_chk.addLayout(l2, 1, 0)
        grid_chk.addLayout(l5, 1, 1)
        grid_chk.addLayout(l3, 2, 0)

        self.lay_chk.addLayout(grid_chk)
        v_pw1_group.addLayout(self.lay_chk)
        lay_pw.addLayout(v_pw1_group)

        # Input konfirmasi password
        lbl_in2 = QLabel("Konfirmasi Password")
        lbl_in2.setStyleSheet("font-weight: 600;")
        lay_pw.addWidget(lbl_in2)

        box_pw2 = QFrame()
        self.box_pw2 = box_pw2
        box_pw2.setObjectName("InputBox")
        lay_box2 = QHBoxLayout(box_pw2)
        lay_box2.setContentsMargins(10, 0, 5, 0)
        lay_box2.setSpacing(0)

        self.entry_pw2 = QLineEdit()
        self.entry_pw2.setObjectName("InputInside")
        self.entry_pw2.setFixedHeight(45)
        self.entry_pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self.entry_pw2.setPlaceholderText("Ketik ulang password...")
        self.entry_pw2.setAccessibleName("Konfirmasi Password Baru")
        self.entry_pw2.textChanged.connect(self._on_pw_change)
        lay_box2.addWidget(self.entry_pw2)

        self.btn_toggle_pw2 = QPushButton()
        self.btn_toggle_pw2.setIcon(qta.icon("mdi6.eye-outline", color="#8B95A5"))
        self.btn_toggle_pw2.setIconSize(QSize(22, 22))
        self.btn_toggle_pw2.setObjectName("BtnEye")
        self.btn_toggle_pw2.setFixedSize(40, 45)
        self.btn_toggle_pw2.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_pw2.clicked.connect(
            lambda: self._toggle_field(self.entry_pw2, self.btn_toggle_pw2)
        )
        lay_box2.addWidget(self.btn_toggle_pw2)
        lay_pw.addWidget(box_pw2)

        # Indikator match/tidak
        self.lay_match = QHBoxLayout()
        self.lay_match.setContentsMargins(5, 5, 0, 0)
        self.lay_match.setSpacing(8)
        self.icon_match = QLabel()
        self.icon_match.setFixedSize(16, 16)
        self.lbl_match_txt = QLabel("Password cocok")
        self.lbl_match_txt.setStyleSheet(
            "font-size: 9pt; color: #28c75d; font-weight: bold;"
        )
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
        self.btn_toggle_pw1.installEventFilter(self)
        self.entry_pw2.installEventFilter(self)
        self.btn_toggle_pw2.installEventFilter(self)

        self.btn_gen.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setTabOrder(self.btn_gen, self.entry_pw1)
        self.setTabOrder(self.entry_pw1, self.btn_toggle_pw1)
        self.setTabOrder(self.btn_toggle_pw1, self.entry_pw2)
        self.setTabOrder(self.entry_pw2, self.btn_toggle_pw2)

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
                if isinstance(obj, QPushButton):
                    if obj.objectName() == "BtnEye" or obj == self.btn_gen:
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
        self.btn_toggle_pw1.setIcon(qta.icon("mdi6.eye-off-outline", color="#8B95A5"))
        self.btn_toggle_pw2.setIcon(qta.icon("mdi6.eye-off-outline", color="#8B95A5"))

    def _toggle_field(self, entry: QLineEdit, btn: QPushButton):
        mode = (
            QLineEdit.EchoMode.Normal
            if entry.echoMode() == QLineEdit.EchoMode.Password
            else QLineEdit.EchoMode.Password
        )
        entry.setEchoMode(mode)
        color = "#00D2C8" if mode == QLineEdit.EchoMode.Normal else "#8B95A5"
        icon_name = (
            "mdi6.eye-outline"
            if mode == QLineEdit.EchoMode.Password
            else "mdi6.eye-off-outline"
        )
        btn.setIcon(qta.icon(icon_name, color=color))

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
                self.lbl_str.setText("Kekuatan: -")
                self.lbl_str.setStyleSheet(muted_label_style("9pt") + " font-weight: bold;")
            else:
                self.lbl_str.setText(f"Kekuatan: {STRENGTH_LABELS[score]}")
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
                icon.setPixmap(
                    qta.icon("mdi6.check-circle", color="#28c75d").pixmap(16, 16)
                )
                lbl.setStyleSheet(f"color: {CLR_TEXT_MAIN}; font-size: 9pt;")
            else:
                icon.setPixmap(
                    qta.icon("mdi6.check-circle", color="#232B3E").pixmap(16, 16)
                )
                lbl.setStyleSheet(muted_label_style("9pt"))

        # Match logic
        if not pw2:
            self.icon_match.hide()
            self.lbl_match_txt.hide()
        elif pw1 == pw2:
            self.icon_match.show()
            self.lbl_match_txt.show()
            self.icon_match.setPixmap(
                qta.icon("mdi6.check-circle", color="#28c75d").pixmap(16, 16)
            )
            self.lbl_match_txt.setText("Password cocok")
            self.lbl_match_txt.setStyleSheet(
                f"font-size: 9pt; color: {CLR_SUCCESS}; font-weight: bold;"
            )
        else:
            self.icon_match.show()
            self.lbl_match_txt.show()
            self.icon_match.setPixmap(
                qta.icon("mdi6.close-circle", color="#E74C3C").pixmap(16, 16)
            )
            self.lbl_match_txt.setText("Password tidak cocok")
            self.lbl_match_txt.setStyleSheet(
                "font-size: 9pt; color: #E74C3C; font-weight: bold;"
            )

        # Evaluasi final state
        score = pw_strength(pw1)
        is_strong_enough = score >= 1
        is_valid = bool(pw1) and (pw1 == pw2) and is_strong_enough

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
        self.entry_pw1.setEchoMode(QLineEdit.EchoMode.Password)
        self.entry_pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self.btn_toggle_pw1.setIcon(qta.icon("mdi6.eye-outline", color="#8B95A5"))
        self.btn_toggle_pw2.setIcon(qta.icon("mdi6.eye-outline", color="#8B95A5"))

        self.entry_pw1.blockSignals(False)
        self.entry_pw2.blockSignals(False)
        self._on_pw_change()  # Trigger refresh UI

    def attach_return_event(self, slot_func):
        """Meneruskan event tombol Enter ke fungsi eksekusi parent."""
        self.entry_pw2.returnPressed.connect(slot_func)
