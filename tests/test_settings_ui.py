"""Tests untuk Settings: store (QSettings), i18n, dan smoke jendela Settings."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings

from core.constants import DEFAULT_KDF_LEVEL, KDF_LEVEL_PARANOID
from ui.i18n import i18n, tr
from ui.settings_store import SettingsStore


def _isolated_store(tmp_path) -> SettingsStore:
    s = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    return SettingsStore(s)


@pytest.mark.qt
def test_settings_defaults(qtbot, tmp_path):
    st = _isolated_store(tmp_path)
    assert st.kdf_level() == DEFAULT_KDF_LEVEL
    assert st.delete_original() is False
    assert st.secure_wipe() is False
    assert st.compress() is False
    assert st.clipboard_seconds() == 30
    assert st.auto_lock_enabled() is False
    assert st.language() == "en"
    assert st.tray_notif() is True  # toast minimize-ke-tray default nyala


@pytest.mark.qt
def test_settings_roundtrip_and_change_signal(qtbot, tmp_path):
    st = _isolated_store(tmp_path)
    seen = []
    st.changed.connect(lambda k: seen.append(k))

    st.set_kdf_level(KDF_LEVEL_PARANOID)
    st.set_delete_original(True)
    st.set_compress(True)
    st.set_clipboard_seconds(0)
    st.set_auto_lock_enabled(True)
    st.set_language("id")
    st.set_tray_notif(False)

    assert st.kdf_level() == KDF_LEVEL_PARANOID
    assert st.delete_original() is True
    assert st.compress() is True
    assert st.clipboard_seconds() == 0
    assert st.auto_lock_enabled() is True
    assert st.language() == "id"
    assert st.tray_notif() is False
    assert "security/kdf_level" in seen
    assert "notifications/tray_minimized" in seen

    # Set ke nilai sama tidak memancarkan sinyal lagi.
    seen.clear()
    st.set_delete_original(True)
    assert seen == []

    # Nilai asing di-clamp ke yang valid.
    st.set_kdf_level("nonsense")
    assert st.kdf_level() == DEFAULT_KDF_LEVEL


@pytest.mark.qt
def test_settings_reset(qtbot, tmp_path):
    st = _isolated_store(tmp_path)
    st.set_kdf_level(KDF_LEVEL_PARANOID)
    st.set_delete_original(True)
    st.set_tray_notif(False)
    st.reset_to_defaults()
    assert st.kdf_level() == DEFAULT_KDF_LEVEL
    assert st.delete_original() is False
    assert st.tray_notif() is True


@pytest.mark.qt
def test_i18n_switch_language(qtbot):
    i18n().set_language("en")
    assert tr("settings.title", "Settings") == "Settings"
    assert tr("settings.done", "Done") == "Done"

    i18n().set_language("id")
    assert tr("settings.title", "Settings") == "Pengaturan"
    assert tr("settings.done", "Done") == "Selesai"
    # Key tanpa terjemahan jatuh ke default.
    assert tr("settings.unknown_key", "Fallback") == "Fallback"

    i18n().set_language("en")  # pulihkan agar tidak bocor ke test lain


@pytest.mark.qt
def test_theme_restart_box_reflects_pending_change(qtbot, tmp_path):
    """Regresi: kotak "Restart now" harus muncul saat tema TERSIMPAN beda dari aktif,
    bukan hanya pada saat combo diubah — sehingga membuka ulang Settings dengan
    perubahan tema yang belum di-restart tetap menampilkan tombol Restart."""
    import ui.styles as styles
    from ui.settings_window import SettingsWindow

    win = SettingsWindow()
    qtbot.addWidget(win)
    # Store terisolasi agar tak menyentuh QSettings user nyata.
    win.s = _isolated_store(tmp_path)
    try:
        styles.set_active_theme("dark")

        # Tersimpan=light, aktif=dark → kotak restart tampil meski combo tak diubah.
        win.s.set_theme("light")
        win._update_theme_restart_box()
        assert win.theme_restart_box.isHidden() is False

        # Tersimpan=dark=aktif → kotak tersembunyi.
        win.s.set_theme("dark")
        win._update_theme_restart_box()
        assert win.theme_restart_box.isHidden() is True
    finally:
        styles.set_active_theme("dark")


@pytest.mark.qt
def test_settings_window_builds_and_retranslates(qtbot):
    from ui.settings_window import SettingsWindow

    win = SettingsWindow()
    qtbot.addWidget(win)

    # Kartu KDF dan kontrol utama ada.
    assert win.card_moderate is not None
    assert win.combo_clip.count() == 4
    assert win.lbl_title.text() == "Settings"

    # Retranslate ke Indonesia mengganti judul jendela (i18n live).
    i18n().set_language("id")
    win._retranslate()
    assert win.lbl_title.text() == "Pengaturan"
    assert win.btn_done.text() == "Selesai"

    i18n().set_language("en")
    win._retranslate()
