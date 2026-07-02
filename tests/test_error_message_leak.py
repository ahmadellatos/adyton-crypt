"""Regresi temuan #4: exception TAK TERDUGA tidak boleh membocorkan teks exception
mentah (yang bisa memuat path absolut) ke pesan yang tampil di UI.

Catch-all `except Exception` di core kini mengembalikan ``GENERIC_FAILURE_MESSAGE``;
detail lengkap hanya masuk log (logger.exception). Pesan kurasi yang memang aman
(mis. "Not enough storage space", "This file isn't a valid Adyton Crypt vault")
tetap diteruskan apa adanya — itu diuji terpisah & tidak terpengaruh perubahan ini.
"""

import shutil

from core import vault as vault_mod
from core import vault_extract as vault_extract_mod
from core.vault import (
    GENERIC_FAILURE_MESSAGE,
    VaultStatus,
    buka_brankas,
    change_password,
    kunci_brankas,
)

PASSWORD = "P@ssw0rd!Kuat123"
NEW_PASSWORD = "An0ther$trongPass456"
SECRET_PATH = r"C:\Users\victim\SuperSecret\rahasia.adtn"


def _make_source(tmp_path):
    source = tmp_path / "rahasia"
    source.mkdir()
    (source / "a.txt").write_text("alpha", encoding="utf-8")
    return source


def _boom(*_a, **_k):
    # Meniru error OS yang teks-nya MEMUAT path absolut korban.
    raise OSError(f"[WinError 5] Access is denied: '{SECRET_PATH}'")


def _assert_clean(message):
    assert message == GENERIC_FAILURE_MESSAGE
    assert SECRET_PATH not in (message or "")
    assert "WinError" not in (message or "")


def test_buka_brankas_unexpected_error_does_not_leak_path(tmp_path, monkeypatch):
    source = _make_source(tmp_path)
    vault_path = tmp_path / "v.adtn"
    assert kunci_brankas([str(source)], str(vault_path), PASSWORD)[0] == VaultStatus.SUCCESS
    shutil.rmtree(source)  # tujuan tak ada → lanjut ke ekstraksi (bukan overwrite)

    monkeypatch.setattr(vault_extract_mod, "_extract_and_place_vault", _boom)
    status, message = buka_brankas(str(vault_path), PASSWORD)
    assert status == VaultStatus.ERROR
    _assert_clean(message)


def test_kunci_brankas_unexpected_error_does_not_leak_path(tmp_path, monkeypatch):
    source = _make_source(tmp_path)
    vault_path = tmp_path / "v.adtn"

    monkeypatch.setattr(vault_mod, "_build_header", _boom)
    status, message = kunci_brankas([str(source)], str(vault_path), PASSWORD)
    assert status == VaultStatus.ERROR
    _assert_clean(message)


def test_change_password_unexpected_error_does_not_leak_path(tmp_path, monkeypatch):
    source = _make_source(tmp_path)
    vault_path = tmp_path / "v.adtn"
    assert kunci_brankas([str(source)], str(vault_path), PASSWORD)[0] == VaultStatus.SUCCESS

    # Paksa gagal di tengah penulisan ulang header (_rewrite_header_full).
    monkeypatch.setattr(vault_mod.shutil, "disk_usage", _boom)
    status, message = change_password(str(vault_path), PASSWORD, NEW_PASSWORD)
    assert status == VaultStatus.ERROR
    _assert_clean(message)


def test_curated_messages_still_pass_through(tmp_path):
    """Pesan kurasi (path-free) TIDAK ikut digenerikkan — format file asing tetap
    memberi pesan spesifik yang berguna, bukan pesan generik."""
    fake = tmp_path / "bukan.adtn"
    fake.write_bytes(b"XXXX\x01" + b"\x00" * 200)  # magic salah
    status, message = buka_brankas(str(fake), PASSWORD)
    assert status == VaultStatus.ERROR
    assert "isn't a valid Adyton Crypt vault" in (message or "")
    assert message != GENERIC_FAILURE_MESSAGE
