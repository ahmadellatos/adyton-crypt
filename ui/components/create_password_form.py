"""
Modul: create_password_form.py
Deskripsi: Widget reusable untuk PEMBUATAN password — input + meter kekuatan
           (collapse beranimasi) + checklist 5 kriteria + konfirmasi + indikator
           cocok/tidak. Dipakai bersama oleh Tab Kunci dan Tab Teks (mode
           enkripsi). Header, tombol generator, dan toggle mode TETAP milik panel
           pemanggil; form hanya menyediakan method generate().

           Spacing mengikuti PasswordPanelLock (grup pw1 ber-spacing 0).
"""

import qtawesome as qta
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..i18n import register, tr
from ..password_strength import (
    CHECKLIST_ITEMS,
    STRENGTH_COLORS,
    STRENGTH_LABELS,
    generate_password,
    is_strong,
    password_rules,
    pw_strength,
)
from ..styles import CLR_BORDER, CLR_DANGER, CLR_SUCCESS, muted_label_style
from ..widgets import PasswordLineEdit

_STRENGTH_REVEAL_H = 26
_ANIM_MS = 250  # mengikuti Tab Kunci

# Kunci i18n untuk label checklist & meter — sejajar urutan dengan
# password_strength.CHECKLIST_ITEMS / STRENGTH_LABELS (sumber kebenaran English).
_CHECKLIST_KEYS = [
    ("pw.chk.len", "At least 8 characters"),
    ("pw.chk.upper", "Uppercase letter (A-Z)"),
    ("pw.chk.lower", "Lowercase letter (a-z)"),
    ("pw.chk.num", "Number (0-9)"),
    ("pw.chk.sym", "Symbol (!@#$%^&*)"),
]
_STRENGTH_KEYS = [
    ("pw.weak", "Weak"),
    ("pw.fair", "Fair"),
    ("pw.strong", "Strong"),
    ("pw.verystrong", "Very Strong"),
]


class CreatePasswordForm(QWidget):
    """Form pembuatan password: input + strength + checklist + konfirmasi."""

    valid_state_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._strength_visible = False
        self._build_ui()

    # ── UI ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)  # margin luar disediakan panel
        lay.setSpacing(10)  # = lay_pw Tab Kunci

        lbl1 = QLabel()
        lbl1.setObjectName("SectionLabel")
        register(lbl1, "pw.label", "Password")
        lay.addWidget(lbl1)

        # Grup pw1: entry + strength + checklist menempel rapat (spacing 0),
        # ritme visual diatur oleh margin internal tiap bagian (spt Tab Kunci).
        v_pw1_group = QVBoxLayout()
        v_pw1_group.setSpacing(0)

        self.entry_pw1 = PasswordLineEdit()
        register(self.entry_pw1, "pw.placeholder", "Enter a strong password…", "setPlaceholderText")
        self.entry_pw1.setAccessibleName("New password")
        self.entry_pw1.textChanged.connect(self._on_change)
        v_pw1_group.addWidget(self.entry_pw1)
        v_pw1_group.addWidget(self._build_strength())
        v_pw1_group.addWidget(self._build_checklist())
        lay.addLayout(v_pw1_group)

        lay.addSpacing(6)  # jarak lega sebelum konfirmasi (Tab Kunci)

        lbl2 = QLabel()
        lbl2.setObjectName("SectionLabel")
        register(lbl2, "pw.confirm", "Confirm Password")
        lay.addWidget(lbl2)

        self.entry_pw2 = PasswordLineEdit()
        register(
            self.entry_pw2, "pw.confirm_placeholder", "Repeat your password…", "setPlaceholderText"
        )
        self.entry_pw2.setAccessibleName("Confirm new password")
        self.entry_pw2.textChanged.connect(self._on_change)
        lay.addWidget(self.entry_pw2)

        lay.addLayout(self._build_match())

    def _build_strength(self) -> QWidget:
        self._strength_widget = QWidget()
        self._strength_widget.setMaximumHeight(0)
        self._strength_widget.setMinimumHeight(0)

        row = QHBoxLayout(self._strength_widget)
        row.setContentsMargins(0, 8, 0, 0)
        row.setSpacing(8)

        self._bars: list[QFrame] = []
        for _ in range(4):
            bar = QFrame()
            bar.setFixedHeight(6)
            bar.setStyleSheet(f"background-color: {CLR_BORDER}; border-radius: 3px;")
            self._bars.append(bar)
            row.addWidget(bar, 1)

        self._lbl_str = QLabel(tr("pw.strength", "Strength"))
        self._lbl_str.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._lbl_str.setStyleSheet(muted_label_style("9pt") + " font-weight: 600;")
        self._lbl_str.setMinimumWidth(140)
        row.addWidget(self._lbl_str)

        self._anim = QPropertyAnimation(self._strength_widget, b"maximumHeight")
        self._anim.setDuration(_ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        return self._strength_widget

    def _build_checklist(self) -> QWidget:
        widget = QWidget()
        grid = QGridLayout(widget)
        grid.setContentsMargins(4, 8, 4, 2)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        # Tata letak sel sama persis dengan Tab Kunci.
        cells = [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1)]
        self._chk: list[tuple[QLabel, QLabel]] = []
        for i, (text, (r, c)) in enumerate(zip(CHECKLIST_ITEMS, cells, strict=True)):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            icon = QLabel()
            icon.setPixmap(qta.icon("mdi6.check-circle-outline", color=CLR_BORDER).pixmap(16, 16))
            lbl = QLabel()
            # default = teks English dari CHECKLIST_ITEMS (sumber kebenaran), key dari peta.
            register(lbl, _CHECKLIST_KEYS[i][0], text)
            lbl.setObjectName("ChecklistLabel")
            lbl.setProperty("valid", False)
            lbl.setWordWrap(True)
            row.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)
            row.addWidget(lbl, 1)
            grid.addLayout(row, r, c)
            self._chk.append((icon, lbl))
        return widget

    def _build_match(self) -> QHBoxLayout:
        lay = QHBoxLayout()
        lay.setContentsMargins(4, 2, 0, 0)
        lay.setSpacing(6)
        self._icon_match = QLabel()
        self._icon_match.setFixedSize(16, 16)
        self._lbl_match = QLabel("")
        self._lbl_match.setObjectName("PwMatchLabel")
        self._lbl_match.setWordWrap(True)
        lay.addWidget(self._icon_match, alignment=Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self._lbl_match, 1)
        self._icon_match.hide()
        self._lbl_match.hide()
        return lay

    # ── Reaksi ───────────────────────────────────────────────────────────────
    def _on_change(self, *_):
        pw1, pw2 = self.entry_pw1.text(), self.entry_pw2.text()
        self._sync_strength(pw1)
        self._sync_checklist(pw1)
        self._sync_match(pw1, pw2)
        ok = bool(pw1) and pw1 == pw2 and is_strong(pw1)
        self.valid_state_changed.emit(ok)

    def _sync_strength(self, pw1: str):
        want = bool(pw1)
        if want != self._strength_visible:
            self._strength_visible = want
            self._anim.stop()
            self._anim.setStartValue(self._strength_widget.maximumHeight())
            self._anim.setEndValue(_STRENGTH_REVEAL_H if want else 0)
            self._anim.start()

        score = pw_strength(pw1)
        for i, bar in enumerate(self._bars):
            color = STRENGTH_COLORS[score] if score >= 0 and i <= score else CLR_BORDER
            bar.setStyleSheet(f"background-color: {color}; border-radius: 3px;")

        if score < 0:
            self._lbl_str.setText(tr("pw.strength.none", "Strength: -"))
            self._lbl_str.setStyleSheet(muted_label_style("9pt") + " font-weight: 600;")
        else:
            label = tr(_STRENGTH_KEYS[score][0], STRENGTH_LABELS[score])
            self._lbl_str.setText(tr("pw.strength.val", "Strength: {label}").format(label=label))
            self._lbl_str.setStyleSheet(
                f"color: {STRENGTH_COLORS[score]}; font-size: 9pt; font-weight: bold;"
            )

    def _sync_checklist(self, pw1: str):
        for ok, (icon, lbl) in zip(password_rules(pw1), self._chk, strict=True):
            color = CLR_SUCCESS if ok else CLR_BORDER
            icon.setPixmap(qta.icon("mdi6.check-circle-outline", color=color).pixmap(16, 16))
            lbl.setProperty("valid", ok)
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)

    def _sync_match(self, pw1: str, pw2: str):
        if not pw2:
            self._icon_match.hide()
            self._lbl_match.hide()
            return
        self._icon_match.show()
        self._lbl_match.show()
        if pw1 == pw2:
            self._icon_match.setPixmap(
                qta.icon("mdi6.check-circle-outline", color=CLR_SUCCESS).pixmap(16, 16)
            )
            self._lbl_match.setText(tr("pw.match", "Passwords match"))
            self._lbl_match.setStyleSheet(f"color: {CLR_SUCCESS};")
        else:
            self._icon_match.setPixmap(
                qta.icon("mdi6.close-circle-outline", color=CLR_DANGER).pixmap(16, 16)
            )
            self._lbl_match.setText(tr("pw.nomatch", "Passwords don't match"))
            self._lbl_match.setStyleSheet(f"color: {CLR_DANGER};")

    # ── Public API ────────────────────────────────────────────────────────────
    def get_password(self) -> str:
        return self.entry_pw1.text()

    def is_valid(self) -> bool:
        pw1 = self.entry_pw1.text()
        return bool(pw1) and pw1 == self.entry_pw2.text() and is_strong(pw1)

    def generate(self):
        pw = generate_password()
        self.entry_pw1.setText(pw)
        self.entry_pw2.setText(pw)

    def set_busy(self, busy: bool):
        self.entry_pw1.setEnabled(not busy)
        self.entry_pw2.setEnabled(not busy)

    def reset(self):
        for entry in (self.entry_pw1, self.entry_pw2):
            entry.blockSignals(True)
            entry.clear()
            entry.blockSignals(False)
        self._on_change()  # refresh UI + pancarkan state

    def attach_return_event(self, slot):
        self.entry_pw2.returnPressed.connect(slot)
