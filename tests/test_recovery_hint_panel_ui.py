"""Qt-level tests untuk UI recovery key + password hint (Tab Kunci).

Memverifikasi API panel yang dibaca TabKunci dan gate pada RecoveryCodeDialog.
"""

import pytest

pytest.importorskip("PySide6")

from ui.components.password_panel_lock import PasswordPanelLock
from ui.components.recovery_hint_panel import RecoveryHintPanel
from ui.dialogs import RecoveryCodeDialog


@pytest.mark.qt
def test_panel_defaults(qtbot):
    panel = RecoveryHintPanel()
    qtbot.addWidget(panel)

    assert panel.recovery_enabled() is False
    assert panel.recovery_mode() == RecoveryHintPanel.MODE_CODE
    assert panel.get_hint() == ""
    assert panel.has_pending_passphrase_error() is False
    assert panel.recovery_body.isVisible() is False


@pytest.mark.qt
def test_toggle_recovery_reveals_body(qtbot):
    panel = RecoveryHintPanel()
    qtbot.addWidget(panel)
    panel.show()

    panel.switch_recovery.setChecked(True)
    assert panel.recovery_enabled() is True
    assert panel.recovery_body.isVisible() is True


@pytest.mark.qt
def test_passphrase_mode_requires_passphrase(qtbot):
    panel = RecoveryHintPanel()
    qtbot.addWidget(panel)
    panel.show()

    panel.switch_recovery.setChecked(True)
    panel.card_pass.clicked.emit()  # memilih kartu passphrase

    assert panel.recovery_mode() == RecoveryHintPanel.MODE_PASSPHRASE
    assert panel.entry_pass.isVisible() is True
    assert panel.has_pending_passphrase_error() is True  # empty passphrase

    panel.entry_pass.setText("my recovery phrase")
    assert panel.has_pending_passphrase_error() is False
    assert panel.recovery_passphrase() == "my recovery phrase"


@pytest.mark.qt
def test_code_mode_has_no_passphrase_error(qtbot):
    panel = RecoveryHintPanel()
    qtbot.addWidget(panel)
    panel.switch_recovery.setChecked(True)
    # default mode is code
    assert panel.has_pending_passphrase_error() is False


@pytest.mark.qt
def test_hint_is_stripped(qtbot):
    panel = RecoveryHintPanel()
    qtbot.addWidget(panel)
    panel.entry_hint.setText("  trip to bali  ")
    assert panel.get_hint() == "trip to bali"


@pytest.mark.qt
def test_reset_clears_everything(qtbot):
    panel = RecoveryHintPanel()
    qtbot.addWidget(panel)
    panel.switch_recovery.setChecked(True)
    panel.card_pass.clicked.emit()
    panel.entry_pass.setText("x")
    panel.entry_hint.setText("y")

    panel.reset()

    assert panel.recovery_enabled() is False
    assert panel.recovery_mode() == RecoveryHintPanel.MODE_CODE
    assert panel.recovery_passphrase() == ""
    assert panel.get_hint() == ""


@pytest.mark.qt
def test_password_panel_lock_passthrough(qtbot):
    panel = PasswordPanelLock()
    qtbot.addWidget(panel)

    assert panel.recovery_enabled() is False
    assert panel.get_hint() == ""

    panel.recovery_hint.switch_recovery.setChecked(True)
    panel.recovery_hint.entry_hint.setText("hint text")
    assert panel.recovery_enabled() is True
    assert panel.get_hint() == "hint text"

    panel.reset_fields()
    assert panel.recovery_enabled() is False
    assert panel.get_hint() == ""


@pytest.mark.qt
def test_recovery_code_dialog_gate(qtbot):
    code = "ABCD-EFGH-IJKL-MNOP-QRST-UVWX-YZ23-4567"
    dlg = RecoveryCodeDialog(code, parent=None)
    qtbot.addWidget(dlg)

    # Tombol konfirmasi terkunci sampai user menyatakan sudah menyimpan.
    assert dlg.btn_yes.isEnabled() is False
    assert code in dlg.code_box.toPlainText()

    dlg.switch_saved.setChecked(True)
    assert dlg.btn_yes.isEnabled() is True

    # Copy tidak melempar (mengisi clipboard + auto-clear).
    dlg._copy()
