"""
Modul: i18n.py
Deskripsi: Lapisan terjemahan ringan (runtime) untuk UI.

Sengaja tidak memakai .ts/.qm Qt Linguist agar bisa ganti bahasa LIVE tanpa
toolchain. ``tr(key, default)`` mengembalikan teks bahasa aktif; default selalu
teks Inggris. Memancarkan ``language_changed`` agar widget bisa retranslate.

Cakupan awal: jendela Settings (permukaan pertama yang dwibahasa). Menerjemahkan
sisa aplikasi dilakukan bertahap dengan membungkus string memakai ``tr()``.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

# Hanya entri non-Inggris yang perlu didefinisikan; "en" memakai default di situs panggil.
_TRANSLATIONS: dict[str, dict[str, str]] = {
    "id": {
        "settings.title": "Pengaturan",
        "settings.security": "Keamanan",
        "settings.security.cap": "Bagaimana vault kamu dilindungi",
        "settings.kdf.label": "Kekuatan enkripsi",
        "settings.kdf.desc": "Derivasi kunci Argon2id — makin kuat makin lambat dibuka.",
        "settings.kdf.interactive": "Interaktif",
        "settings.kdf.interactive.desc": "Buka tercepat. Pemakaian harian.",
        "settings.kdf.moderate": "Sedang",
        "settings.kdf.moderate.desc": "Seimbang antara keamanan & kecepatan.",
        "settings.kdf.paranoid": "Paranoid",
        "settings.kdf.paranoid.desc": "Kekerasan maksimum. Lebih lambat.",
        "settings.defaults": "Default",
        "settings.defaults.cap": "Opsi bawaan untuk tab Kunci",
        "settings.delete_original": "Hapus asli setelah dikunci",
        "settings.delete_original.desc": "Menghapus sumber setelah vault terverifikasi.",
        "settings.destructive": "Merusak.",
        "settings.secure_wipe": "Hapus aman (timpa data)",
        "settings.secure_wipe.desc": "Timpa data sebelum dihapus (lebih lambat).",
        "settings.privacy": "Privasi",
        "settings.privacy.cap": "Kurangi jejak yang tertinggal",
        "settings.clipboard": "Bersihkan clipboard otomatis",
        "settings.clipboard.desc": "Hapus rahasia yang disalin setelah jeda.",
        "settings.off": "Mati",
        "settings.auto_lock": "Kunci otomatis saat idle",
        "settings.auto_lock.desc": "Bersihkan kolom sensitif setelah tidak aktif.",
        "settings.appearance": "Tampilan",
        "settings.appearance.cap": "Tampilan & bahasa",
        "settings.theme": "Tema",
        "settings.theme.desc": "Mode gelap disarankan.",
        "settings.theme.dark": "Gelap",
        "settings.theme.system": "Sistem",
        "settings.language": "Bahasa",
        "settings.language.desc": "Bahasa antarmuka.",
        "settings.about": "Tentang",
        "settings.about.cap": "Enkripsi lokal AES-256-GCM + Argon2id",
        "settings.about.build": "Versi pra-rilis.",
        "settings.reset": "Setel ulang ke default",
        "settings.done": "Selesai",
        "settings.seconds": "{n} detik",
        "settings.minutes": "{n} mnt",
    }
}


class _I18n(QObject):
    language_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._lang = "en"

    def language(self) -> str:
        return self._lang

    def set_language(self, lang: str) -> None:
        lang = lang if lang in ({"en"} | set(_TRANSLATIONS)) else "en"
        if lang != self._lang:
            self._lang = lang
            self.language_changed.emit(lang)

    def tr(self, key: str, default: str) -> str:
        if self._lang == "en":
            return default
        return _TRANSLATIONS.get(self._lang, {}).get(key, default)


_i18n = _I18n()


def i18n() -> _I18n:
    return _i18n


def tr(key: str, default: str) -> str:
    return _i18n.tr(key, default)
