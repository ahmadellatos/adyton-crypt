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

    # In encrypt mode the password fields live in the shared CreatePasswordForm.
    # Weak password (too short, missing character classes) — even when the
    # confirmation matches, the gate must reject it.
    panel.form.entry_pw1.setText("weak")
    panel.form.entry_pw2.setText("weak")
    assert panel.is_valid() is False

    # Strong password meeting all five rules + matching confirm → accepted.
    panel.form.entry_pw1.setText(STRONG_PW)
    panel.form.entry_pw2.setText(STRONG_PW)
    assert panel.is_valid() is True

    # Mismatched confirmation → rejected again.
    panel.form.entry_pw2.setText(STRONG_PW + "x")
    assert panel.is_valid() is False


@pytest.mark.qt
def test_text_decrypt_mode_accepts_any_nonempty_password(qtbot):
    panel = PasswordPanelTeks()
    qtbot.addWidget(panel)

    # Strength can't be enforced on a password that was chosen previously.
    panel.set_mode("dekripsi")
    assert panel.get_mode() == "dekripsi"

    panel.entry_decrypt.setText("x")
    assert panel.is_valid() is True

    panel.entry_decrypt.setText("")
    assert panel.is_valid() is False


@pytest.mark.qt
def test_set_mode_emits_only_on_change(qtbot):
    panel = PasswordPanelTeks()
    qtbot.addWidget(panel)

    with qtbot.assertNotEmitted(panel.mode_changed):
        panel.set_mode("enkripsi")  # already in this mode → no signal

    with qtbot.waitSignal(panel.mode_changed) as blocker:
        panel.set_mode("dekripsi")
    assert blocker.args == ["dekripsi"]
