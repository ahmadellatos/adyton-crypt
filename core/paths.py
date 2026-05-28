"""
core/paths.py
Utilitas untuk manajemen path absolut yang aman untuk Nuitka.
"""

import os
import sys
from pathlib import Path


def get_app_root() -> Path:
    """Mendapatkan root direktori aplikasi."""
    if getattr(sys, "frozen", False):
        # Build Nuitka: aset ada di sebelah .exe
        return Path(sys.executable).parent
    # Dev mode: naik dua level dari core/ ke root proyek
    return Path(__file__).resolve().parent.parent


def get_asset_path(relative_path: str) -> str:
    """Menerjemahkan relative path menjadi absolute path ke aset."""
    return str(get_app_root() / relative_path)


def get_data_dir() -> Path:
    """
    - Dev mode  → folder proyek
    - Build mode → LOCALAPPDATA/AdytonCrypt, fallback ke folder .exe
    """
    if getattr(sys, "frozen", False):
        local_appdata = os.getenv("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata) / "AdytonCrypt"
        # Fallback jika LOCALAPPDATA tidak tersedia
        return Path(sys.executable).parent
    return get_app_root()
