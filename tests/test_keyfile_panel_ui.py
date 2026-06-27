"""Qt-level tests untuk KeyfilePanel (Tab Kunci, faktor kedua 2FA).

Fokus utama: regresi bug "toggle keyfile dimatikan tapi vault tetap 2FA". Panel
HARUS hanya melaporkan keyfile saat toggle benar-benar aktif — kalau user memilih
keyfile lalu mematikan toggle, ``keyfile_path()`` wajib kosong sehingga lapisan
TabKunci tak diam-diam mengunci vault sebagai 2FA (risiko lockout).
"""

import pytest

pytest.importorskip("PySide6")

from ui.components.keyfile_panel import KeyfilePanel
from ui.components.password_panel_lock import PasswordPanelLock


@pytest.mark.qt
def test_keyfile_path_empty_by_default(qtbot):
    panel = KeyfilePanel()
    qtbot.addWidget(panel)

    assert panel.keyfile_enabled() is False
    assert panel.keyfile_path() == ""
    assert panel.has_pending_keyfile_error() is False


@pytest.mark.qt
def test_keyfile_path_reported_only_when_enabled(qtbot):
    panel = KeyfilePanel()
    qtbot.addWidget(panel)
    panel.set_password_ready(True)

    panel.switch_keyfile.setChecked(True)
    panel._set_keyfile("C:/secret/key.bin")

    assert panel.keyfile_enabled() is True
    assert panel.keyfile_path() == "C:/secret/key.bin"
    assert panel.has_pending_keyfile_error() is False


@pytest.mark.qt
def test_disabling_toggle_after_choosing_clears_reported_keyfile(qtbot):
    """REGRESI Bug #1: pilih keyfile lalu MATIKAN toggle → keyfile tak terpakai.

    Tanpa fix, ``_keyfile_path`` yang tertinggal bocor lewat ``keyfile_path()`` dan
    vault dibuat 2FA padahal user sudah menonaktifkan keyfile.
    """
    panel = KeyfilePanel()
    qtbot.addWidget(panel)
    panel.set_password_ready(True)

    panel.switch_keyfile.setChecked(True)
    panel._set_keyfile("C:/secret/key.bin")
    assert panel.keyfile_path() == "C:/secret/key.bin"

    # User berubah pikiran: matikan keyfile protection.
    panel.switch_keyfile.setChecked(False)

    assert panel.keyfile_enabled() is False
    assert panel.keyfile_path() == ""  # tak boleh bocor ke kunci_brankas


@pytest.mark.qt
def test_pending_error_when_enabled_without_file(qtbot):
    panel = KeyfilePanel()
    qtbot.addWidget(panel)
    panel.set_password_ready(True)

    panel.switch_keyfile.setChecked(True)
    assert panel.keyfile_path() == ""
    assert panel.has_pending_keyfile_error() is True


@pytest.mark.qt
def test_lock_panel_passthrough_respects_toggle(qtbot):
    """PasswordPanelLock meneruskan keadaan toggle apa adanya ke TabKunci."""
    panel = PasswordPanelLock()
    qtbot.addWidget(panel)
    panel.keyfile_panel.set_password_ready(True)

    panel.keyfile_panel.switch_keyfile.setChecked(True)
    panel.keyfile_panel._set_keyfile("C:/secret/key.bin")
    assert panel.keyfile_path() == "C:/secret/key.bin"

    panel.keyfile_panel.switch_keyfile.setChecked(False)
    assert panel.keyfile_path() == ""
