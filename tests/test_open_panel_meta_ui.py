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


@pytest.mark.qt
def test_keyfile_box_and_getters_follow_meta(qtbot):
    """Bug F: getter requires_keyfile/has_recovery mengikuti meta vault."""
    panel = PasswordPanelOpen()
    qtbot.addWidget(panel)
    panel.show()

    panel.show_vault_meta(None, has_recovery=False, requires_keyfile=True)
    assert panel.requires_keyfile() is True
    assert panel.has_recovery() is False
    assert panel.keyfile_box.isVisible() is True

    panel.show_vault_meta(None, has_recovery=False, requires_keyfile=False)
    assert panel.requires_keyfile() is False
    assert panel.keyfile_box.isVisible() is False


@pytest.mark.qt
def test_keyfile_cleared_when_switching_vaults(qtbot):
    """Bug B: pilihan keyfile vault lama tak boleh terbawa ke vault berikutnya."""
    panel = PasswordPanelOpen()
    qtbot.addWidget(panel)
    panel.show()

    panel.show_vault_meta(None, has_recovery=False, requires_keyfile=True)
    # Simulasikan user memilih keyfile untuk vault A.
    panel._keyfile_path = "C:/secret/key.bin"
    panel.lbl_keyfile.setText("key.bin")
    assert panel.keyfile_path() == "C:/secret/key.bin"

    # Pindah ke vault B → keyfile harus ter-reset.
    panel.show_vault_meta(None, has_recovery=False, requires_keyfile=True)
    assert panel.keyfile_path() == ""


@pytest.mark.qt
def test_keyfile_note_mentions_recovery_only_when_present(qtbot):
    """Bug E: note menyebut recovery key hanya bila vault memang punya."""
    panel = PasswordPanelOpen()
    qtbot.addWidget(panel)
    panel.show()

    panel.show_vault_meta(None, has_recovery=True, requires_keyfile=True)
    assert "recovery" in panel.lbl_keyfile_note.text().lower()

    panel.show_vault_meta(None, has_recovery=False, requires_keyfile=True)
    assert "recovery" not in panel.lbl_keyfile_note.text().lower()
