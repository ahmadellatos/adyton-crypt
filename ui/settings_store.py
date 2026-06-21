"""
Modul: settings_store.py
Deskripsi: Penyimpanan preferensi aplikasi (QSettings, scope APP_ORG/APP_NAME yang
           di-set di main.py). Satu sumber kebenaran untuk Settings — dibaca UI
           maupun alur kunci (mis. level KDF, default opsi, clipboard, auto-lock).

Memancarkan sinyal ``changed(key)`` agar konsumen live (clipboard, auto-lock, i18n)
bisa bereaksi tanpa restart.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QSettings, Signal

from core.constants import DEFAULT_KDF_LEVEL, KDF_LEVELS

# Key kanonik + nilai default. Default mencerminkan perilaku hardcode sebelumnya
# (Moderate KDF, clipboard 30s, opsi mati) agar tanpa Settings pun perilaku sama.
KEY_KDF_LEVEL = "security/kdf_level"
KEY_DELETE_ORIGINAL = "defaults/delete_original"
KEY_SECURE_WIPE = "defaults/secure_wipe"
KEY_CLIPBOARD_SECONDS = "privacy/clipboard_seconds"
KEY_AUTO_LOCK_ENABLED = "privacy/auto_lock_enabled"
KEY_AUTO_LOCK_MINUTES = "privacy/auto_lock_minutes"
KEY_THEME = "appearance/theme"
KEY_LANGUAGE = "appearance/language"

_DEFAULTS: dict[str, object] = {
    KEY_KDF_LEVEL: DEFAULT_KDF_LEVEL,
    KEY_DELETE_ORIGINAL: False,
    KEY_SECURE_WIPE: False,
    KEY_CLIPBOARD_SECONDS: 30,  # 0 = matikan auto-clear
    KEY_AUTO_LOCK_ENABLED: False,
    KEY_AUTO_LOCK_MINUTES: 5,
    KEY_THEME: "dark",
    KEY_LANGUAGE: "en",
}

CLIPBOARD_SECOND_CHOICES = (0, 15, 30, 60)
AUTO_LOCK_MINUTE_CHOICES = (1, 5, 15)
THEME_CHOICES = ("dark", "system")
LANGUAGE_CHOICES = ("en", "id")


class SettingsStore(QObject):
    """Wrapper tipis & bertipe di atas QSettings + sinyal perubahan."""

    changed = Signal(str)  # key yang berubah ("*" untuk reset)

    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__()
        # ``settings`` opsional untuk isolasi test; default = scope app (QSettings()).
        self._s = settings if settings is not None else QSettings()

    # ── helper generik ──────────────────────────────────────────────────────
    def _get(self, key: str, typ):
        return self._s.value(key, _DEFAULTS[key], type=typ)

    def _set(self, key: str, value) -> None:
        if self._s.value(key, _DEFAULTS[key], type=type(value)) == value:
            return
        self._s.setValue(key, value)
        self._s.sync()
        self.changed.emit(key)

    # ── Security ────────────────────────────────────────────────────────────
    def kdf_level(self) -> str:
        lvl = self._s.value(KEY_KDF_LEVEL, DEFAULT_KDF_LEVEL, type=str)
        return lvl if lvl in KDF_LEVELS else DEFAULT_KDF_LEVEL

    def set_kdf_level(self, value: str) -> None:
        self._set(KEY_KDF_LEVEL, value if value in KDF_LEVELS else DEFAULT_KDF_LEVEL)

    # ── Defaults (Tab Lock) ─────────────────────────────────────────────────
    def delete_original(self) -> bool:
        return self._get(KEY_DELETE_ORIGINAL, bool)

    def set_delete_original(self, value: bool) -> None:
        self._set(KEY_DELETE_ORIGINAL, bool(value))

    def secure_wipe(self) -> bool:
        return self._get(KEY_SECURE_WIPE, bool)

    def set_secure_wipe(self, value: bool) -> None:
        self._set(KEY_SECURE_WIPE, bool(value))

    # ── Privacy ─────────────────────────────────────────────────────────────
    def clipboard_seconds(self) -> int:
        return self._get(KEY_CLIPBOARD_SECONDS, int)

    def set_clipboard_seconds(self, value: int) -> None:
        self._set(KEY_CLIPBOARD_SECONDS, int(value))

    def auto_lock_enabled(self) -> bool:
        return self._get(KEY_AUTO_LOCK_ENABLED, bool)

    def set_auto_lock_enabled(self, value: bool) -> None:
        self._set(KEY_AUTO_LOCK_ENABLED, bool(value))

    def auto_lock_minutes(self) -> int:
        return self._get(KEY_AUTO_LOCK_MINUTES, int)

    def set_auto_lock_minutes(self, value: int) -> None:
        self._set(KEY_AUTO_LOCK_MINUTES, int(value))

    # ── Appearance ──────────────────────────────────────────────────────────
    def theme(self) -> str:
        return self._get(KEY_THEME, str)

    def set_theme(self, value: str) -> None:
        self._set(KEY_THEME, value if value in THEME_CHOICES else "dark")

    def language(self) -> str:
        return self._get(KEY_LANGUAGE, str)

    def set_language(self, value: str) -> None:
        self._set(KEY_LANGUAGE, value if value in LANGUAGE_CHOICES else "en")

    # ── Reset ───────────────────────────────────────────────────────────────
    def reset_to_defaults(self) -> None:
        for key in _DEFAULTS:
            self._s.remove(key)
        self._s.sync()
        self.changed.emit("*")


_store: SettingsStore | None = None


def get_settings() -> SettingsStore:
    """Akses singleton SettingsStore (dibuat saat pertama dipanggil)."""
    global _store
    if _store is None:
        _store = SettingsStore()
    return _store
