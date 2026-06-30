"""Qt-level tests untuk OptionsPanel — fokus toggle kompresi (opsi mandiri)."""

import pytest

pytest.importorskip("PySide6")

from ui.components.options_panel import OptionsPanel


@pytest.mark.qt
def test_compress_default_off(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    assert panel.is_compress() is False


@pytest.mark.qt
def test_is_compress_reflects_toggle(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    panel.switch_compress.setChecked(True)
    assert panel.is_compress() is True


@pytest.mark.qt
def test_apply_defaults_sets_compress(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    panel.apply_defaults(delete_original=False, secure_wipe=False, compress=True)
    assert panel.is_compress() is True


@pytest.mark.qt
def test_reset_options_keeps_compress(qtbot):
    """Kompresi tak destruktif → tidak di-reset antar-operasi (beda dari Delete original)."""
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    panel.switch_compress.setChecked(True)
    panel.switch_hapus.setChecked(True)

    panel.reset_options()

    assert panel.is_compress() is True  # tetap menyala
    assert panel.is_hapus_asli() is False  # delete di-reset


@pytest.mark.qt
def test_set_busy_disables_compress(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    panel.set_busy(True)
    assert panel.switch_compress.isEnabled() is False
    panel.set_busy(False)
    assert panel.switch_compress.isEnabled() is True
