"""Tests untuk Recent Vaults (opt-in) di SettingsStore."""

import os

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings

from ui.settings_store import RECENT_VAULTS_MAX, SettingsStore


def _isolated_store(tmp_path) -> SettingsStore:
    s = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    return SettingsStore(s)


def _names(store) -> list[str]:
    return [os.path.basename(e["path"]) for e in store.recent_vaults()]


@pytest.mark.qt
def test_recent_disabled_by_default(qtbot, tmp_path):
    st = _isolated_store(tmp_path)
    assert st.recent_enabled() is False
    # Saat mati, mencatat = no-op (tidak ada jejak yang tertulis).
    st.add_recent_vault(str(tmp_path / "a.adtn"))
    assert st.recent_vaults() == []


@pytest.mark.qt
def test_recent_add_newest_first(qtbot, tmp_path):
    st = _isolated_store(tmp_path)
    st.set_recent_enabled(True)
    st.add_recent_vault(str(tmp_path / "a.adtn"))
    st.add_recent_vault(str(tmp_path / "b.adtn"))
    assert _names(st) == ["b.adtn", "a.adtn"]


@pytest.mark.qt
def test_recent_dedupe_moves_to_front(qtbot, tmp_path):
    st = _isolated_store(tmp_path)
    st.set_recent_enabled(True)
    st.add_recent_vault(str(tmp_path / "a.adtn"))
    st.add_recent_vault(str(tmp_path / "b.adtn"))
    st.add_recent_vault(str(tmp_path / "a.adtn"))
    assert _names(st) == ["a.adtn", "b.adtn"]
    assert len(st.recent_vaults()) == 2


@pytest.mark.qt
def test_recent_capped(qtbot, tmp_path):
    st = _isolated_store(tmp_path)
    st.set_recent_enabled(True)
    for i in range(RECENT_VAULTS_MAX + 5):
        st.add_recent_vault(str(tmp_path / f"v{i}.adtn"))
    assert len(st.recent_vaults()) == RECENT_VAULTS_MAX
    # Yang terbaru dipertahankan di puncak; yang terlama dibuang.
    assert _names(st)[0] == f"v{RECENT_VAULTS_MAX + 4}.adtn"


@pytest.mark.qt
def test_recent_remove(qtbot, tmp_path):
    st = _isolated_store(tmp_path)
    st.set_recent_enabled(True)
    st.add_recent_vault(str(tmp_path / "a.adtn"))
    st.add_recent_vault(str(tmp_path / "b.adtn"))
    st.remove_recent_vault(str(tmp_path / "a.adtn"))
    assert _names(st) == ["b.adtn"]


@pytest.mark.qt
def test_recent_disable_clears_and_stays_cleared(qtbot, tmp_path):
    st = _isolated_store(tmp_path)
    st.set_recent_enabled(True)
    st.add_recent_vault(str(tmp_path / "a.adtn"))
    # Mematikan fitur menghapus jejak yang sudah tersimpan (privasi).
    st.set_recent_enabled(False)
    assert st.recent_vaults() == []
    # Menyalakan lagi tidak memunculkan kembali daftar lama.
    st.set_recent_enabled(True)
    assert st.recent_vaults() == []


@pytest.mark.qt
def test_recent_clear_emits_signal(qtbot, tmp_path):
    st = _isolated_store(tmp_path)
    st.set_recent_enabled(True)
    st.add_recent_vault(str(tmp_path / "a.adtn"))
    seen = []
    st.changed.connect(lambda k: seen.append(k))
    st.clear_recent_vaults()
    assert st.recent_vaults() == []
    assert "privacy/recent_vaults" in seen


@pytest.mark.qt
def test_recent_add_emits_signal(qtbot, tmp_path):
    st = _isolated_store(tmp_path)
    st.set_recent_enabled(True)
    seen = []
    st.changed.connect(lambda k: seen.append(k))
    st.add_recent_vault(str(tmp_path / "a.adtn"))
    assert "privacy/recent_vaults" in seen


@pytest.mark.qt
def test_recent_reset_to_defaults_clears(qtbot, tmp_path):
    st = _isolated_store(tmp_path)
    st.set_recent_enabled(True)
    st.add_recent_vault(str(tmp_path / "a.adtn"))
    st.reset_to_defaults()
    assert st.recent_enabled() is False
    assert st.recent_vaults() == []
