"""UI policy regression: the Text tab now enforces the same password gate as
the Lock tab (full checklist + zxcvbn strength) when encrypting, while staying
permissive when decrypting an existing password."""

import pytest

pytest.importorskip("PySide6")

from ui.tab_teks import PasswordPanelTeks

# 14 chars, no dictionary words, all four character classes present.
STRONG_PW = "Zr4!qP9mWk2$tL"


@pytest.mark.qt
def test_text_encrypt_mode_requires_lock_grade_password(qtbot):
    panel = PasswordPanelTeks()
    qtbot.addWidget(panel)

    assert panel.get_mode() == "enkripsi"

    # Weak password (too short, missing character classes) — even when the
    # confirmation matches, the gate must reject it.
    panel.entry_pw1.setText("weak")
    panel.entry_pw2.setText("weak")
    assert panel.is_valid() is False

    # Strong password meeting all five rules + matching confirm → accepted.
    panel.entry_pw1.setText(STRONG_PW)
    panel.entry_pw2.setText(STRONG_PW)
    assert panel.is_valid() is True

    # Mismatched confirmation → rejected again.
    panel.entry_pw2.setText(STRONG_PW + "x")
    assert panel.is_valid() is False


@pytest.mark.qt
def test_text_decrypt_mode_accepts_any_nonempty_password(qtbot):
    panel = PasswordPanelTeks()
    qtbot.addWidget(panel)

    # Strength can't be enforced on a password that was chosen previously.
    panel.btn_mode_dekripsi.setChecked(True)
    panel._on_mode_button_clicked(panel.btn_mode_dekripsi)
    assert panel.get_mode() == "dekripsi"

    panel.entry_pw1.setText("x")
    assert panel.is_valid() is True

    panel.entry_pw1.setText("")
    assert panel.is_valid() is False
