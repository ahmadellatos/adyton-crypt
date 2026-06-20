"""Qt-level tests untuk tampilan hint + affordance recovery di panel buka vault."""

import pytest

pytest.importorskip("PySide6")

from ui.components.password_panel_open import (
    _PLACEHOLDER_PW,
    _PLACEHOLDER_PW_RECOVERY,
    PasswordPanelOpen,
)


def _placeholder(panel: PasswordPanelOpen) -> str:
    return panel.entry_pw.line_edit.placeholderText()


@pytest.mark.qt
def test_hint_shown_and_recovery_placeholder(qtbot):
    panel = PasswordPanelOpen()
    qtbot.addWidget(panel)
    panel.show()

    panel.show_vault_meta("mom's birthplace", has_recovery=True)

    assert panel.hint_box.isVisible() is True
    assert "mom's birthplace" in panel.lbl_hint.text()
    assert _placeholder(panel) == _PLACEHOLDER_PW_RECOVERY


@pytest.mark.qt
def test_no_hint_no_recovery(qtbot):
    panel = PasswordPanelOpen()
    qtbot.addWidget(panel)
    panel.show()

    panel.show_vault_meta(None, has_recovery=False)

    assert panel.hint_box.isVisible() is False
    assert _placeholder(panel) == _PLACEHOLDER_PW


@pytest.mark.qt
def test_hint_persists_after_wrong_password(qtbot):
    panel = PasswordPanelOpen()
    qtbot.addWidget(panel)
    panel.show()

    panel.show_vault_meta("the usual one", has_recovery=False)
    panel.set_error_state("Wrong password or corrupted file.")

    assert panel.hint_box.isVisible() is True  # tetap membantu setelah salah


@pytest.mark.qt
def test_hint_hidden_while_processing(qtbot):
    panel = PasswordPanelOpen()
    qtbot.addWidget(panel)
    panel.show()

    panel.show_vault_meta("the usual one", has_recovery=False)
    panel.set_processing_state("vault.adtn", "1.2 MB", "Verifying password")

    assert panel.hint_box.isVisible() is False


@pytest.mark.qt
def test_clear_meta_resets_placeholder(qtbot):
    panel = PasswordPanelOpen()
    qtbot.addWidget(panel)
    panel.show()

    panel.show_vault_meta("hint", has_recovery=True)
    panel.clear_vault_meta()

    assert panel.hint_box.isVisible() is False
    assert _placeholder(panel) == _PLACEHOLDER_PW
