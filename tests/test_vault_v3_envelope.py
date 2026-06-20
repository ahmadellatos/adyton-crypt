"""Tests untuk format envelope: recovery key, password hint, dan ganti password
tanpa enkripsi ulang data.

Mencakup fitur kritis #1 (recovery + hint) dan #2 (change password / re-key).
"""

import shutil

from core.constants import MAGIC_BYTES
from core.crypto import generate_recovery_code, normalize_recovery_code
from core.vault import (
    VaultStatus,
    _read_header_from_path,
    add_recovery_key,
    buka_brankas,
    change_password,
    kunci_brankas,
    read_vault_hint,
    remove_recovery_key,
    vault_info,
)

PASSWORD = "P@ssw0rd!Kuat123"
NEW_PASSWORD = "An0ther$trongPass456"


def _make_source(tmp_path, name="rahasia"):
    source = tmp_path / name
    nested = source / "nested"
    nested.mkdir(parents=True)
    (source / "a.txt").write_text("alpha", encoding="utf-8")
    (nested / "b.txt").write_text("beta", encoding="utf-8")
    return source


def _lock(tmp_path, **kwargs):
    source = _make_source(tmp_path)
    vault_path = tmp_path / "vault.adtn"
    status, message = kunci_brankas([str(source)], str(vault_path), PASSWORD, **kwargs)
    assert status == VaultStatus.SUCCESS, message
    return source, vault_path


def _assert_restores(vault_path, tmp_path, secret):
    status, restored_name = buka_brankas(str(vault_path), secret)
    assert status == VaultStatus.SUCCESS
    restored = tmp_path / restored_name
    assert (restored / "a.txt").read_text(encoding="utf-8") == "alpha"
    assert (restored / "nested" / "b.txt").read_text(encoding="utf-8") == "beta"
    # Bersihkan agar test berikutnya tidak terhalang folder tujuan yang ada.
    shutil.rmtree(restored)


# ── Recovery code ────────────────────────────────────────────────────────────────


def test_recovery_code_generation_and_normalization():
    code = generate_recovery_code()
    groups = code.split("-")
    assert len(groups) == 8
    assert all(len(g) == 4 for g in groups)
    # Normalisasi toleran kapitalisasi & separator, tetap setara.
    assert normalize_recovery_code(code) == normalize_recovery_code(code.lower())
    assert normalize_recovery_code(code) == normalize_recovery_code(code.replace("-", " "))
    assert "-" not in normalize_recovery_code(code)


def test_vault_with_recovery_code_opens_with_password_or_code(tmp_path):
    code = generate_recovery_code()
    source, vault_path = _lock(tmp_path, recovery_secret=code, recovery_type="code")
    shutil.rmtree(source)

    # Password tetap bekerja.
    _assert_restores(vault_path, tmp_path, PASSWORD)
    # Recovery code membuka vault secara independen.
    _assert_restores(vault_path, tmp_path, code)
    # Bahkan kalau diketik dengan kapitalisasi/separator berbeda.
    mangled = code.lower().replace("-", " ")
    _assert_restores(vault_path, tmp_path, mangled)

    # Secret asal-asalan tetap ditolak sebagai wrong password.
    status, message = buka_brankas(str(vault_path), "totally-wrong-secret")
    assert status == VaultStatus.WRONG_PASSWORD
    assert message is None


def test_vault_with_recovery_passphrase(tmp_path):
    passphrase = "correct horse battery staple recovery"
    source, vault_path = _lock(tmp_path, recovery_secret=passphrase, recovery_type="passphrase")
    shutil.rmtree(source)

    _assert_restores(vault_path, tmp_path, PASSWORD)
    _assert_restores(vault_path, tmp_path, passphrase)
    # Passphrase case-sensitive (tidak dinormalisasi seperti code).
    status, _ = buka_brankas(str(vault_path), passphrase.upper())
    assert status == VaultStatus.WRONG_PASSWORD


# ── Password hint ────────────────────────────────────────────────────────────────


def test_hint_is_readable_without_password(tmp_path):
    _, vault_path = _lock(tmp_path, hint="kota kelahiran ibu")
    assert read_vault_hint(str(vault_path)) == "kota kelahiran ibu"

    info = vault_info(str(vault_path))
    assert info["format"] == "Adyton Vault"
    assert info["has_hint"] is True
    assert info["hint"] == "kota kelahiran ibu"
    assert info["supports_change_password"] is True


def test_no_hint_by_default(tmp_path):
    _, vault_path = _lock(tmp_path)
    assert read_vault_hint(str(vault_path)) is None
    assert vault_info(str(vault_path))["has_hint"] is False


def test_hint_is_stored_in_plaintext(tmp_path):
    """Honesty check: hint memang TIDAK dienkripsi (harus terbaca sebelum unlock)."""
    marker = "petunjuk-yang-terlihat-mentah"
    _, vault_path = _lock(tmp_path, hint=marker)
    assert marker.encode("utf-8") in vault_path.read_bytes()


def test_oversized_hint_is_truncated(tmp_path):
    long_hint = "x" * 5000
    _, vault_path = _lock(tmp_path, hint=long_hint)
    stored = read_vault_hint(str(vault_path))
    assert stored is not None
    assert 0 < len(stored.encode("utf-8")) <= 256


# ── Change password (#2) ─────────────────────────────────────────────────────────


def test_change_password_old_fails_new_works(tmp_path):
    source, vault_path = _lock(tmp_path)
    shutil.rmtree(source)

    status, message = change_password(str(vault_path), PASSWORD, NEW_PASSWORD)
    assert status == VaultStatus.SUCCESS, message

    status, _ = buka_brankas(str(vault_path), PASSWORD)
    assert status == VaultStatus.WRONG_PASSWORD

    _assert_restores(vault_path, tmp_path, NEW_PASSWORD)


def test_change_password_does_not_reencrypt_data(tmp_path):
    """Inti #2: ganti password hanya menulis ulang region header/keyslot — seluruh
    record (data terenkripsi) harus byte-identik."""
    _, vault_path = _lock(tmp_path)

    header_end = _read_header_from_path(vault_path)["header_end"]
    records_before = vault_path.read_bytes()[header_end:]

    status, message = change_password(str(vault_path), PASSWORD, NEW_PASSWORD)
    assert status == VaultStatus.SUCCESS, message

    after = _read_header_from_path(vault_path)
    records_after = vault_path.read_bytes()[after["header_end"] :]

    assert after["header_end"] == header_end  # panjang header tidak berubah
    assert records_after == records_before  # data tidak disentuh


def test_change_password_wrong_old_password(tmp_path):
    source, vault_path = _lock(tmp_path)
    shutil.rmtree(source)

    status, message = change_password(str(vault_path), "wrong-old", NEW_PASSWORD)
    assert status == VaultStatus.WRONG_PASSWORD
    # Vault tetap bisa dibuka dengan password lama (tidak rusak).
    _assert_restores(vault_path, tmp_path, PASSWORD)


def test_change_password_rejects_empty_new(tmp_path):
    _, vault_path = _lock(tmp_path)
    status, _ = change_password(str(vault_path), PASSWORD, "   ")
    assert status == VaultStatus.ERROR


def test_change_password_keeps_recovery_slot(tmp_path):
    code = generate_recovery_code()
    source, vault_path = _lock(tmp_path, recovery_secret=code, recovery_type="code")
    shutil.rmtree(source)

    status, _ = change_password(str(vault_path), PASSWORD, NEW_PASSWORD)
    assert status == VaultStatus.SUCCESS

    _assert_restores(vault_path, tmp_path, NEW_PASSWORD)
    _assert_restores(vault_path, tmp_path, code)  # recovery masih valid


def test_reset_password_using_recovery_code(tmp_path):
    """Recovery code bisa dipakai sebagai 'old credential' untuk set password baru."""
    code = generate_recovery_code()
    source, vault_path = _lock(tmp_path, recovery_secret=code, recovery_type="code")
    shutil.rmtree(source)

    status, _ = change_password(str(vault_path), code, NEW_PASSWORD)
    assert status == VaultStatus.SUCCESS
    _assert_restores(vault_path, tmp_path, NEW_PASSWORD)


def test_change_password_on_foreign_format_is_rejected(tmp_path):
    fake = tmp_path / "old.adtn"
    fake.write_bytes(MAGIC_BYTES + b"\x02" + b"\x00" * 64)
    status, message = change_password(str(fake), PASSWORD, NEW_PASSWORD)
    assert status == VaultStatus.ERROR
    assert "different version" in (message or "").lower()


# ── Add / remove recovery key on existing vault ──────────────────────────────────


def test_add_then_remove_recovery_key(tmp_path):
    source, vault_path = _lock(tmp_path)
    shutil.rmtree(source)

    assert vault_info(str(vault_path))["has_recovery"] is False

    code = generate_recovery_code()
    status, message = add_recovery_key(str(vault_path), PASSWORD, code, "code")
    assert status == VaultStatus.SUCCESS, message
    assert vault_info(str(vault_path))["has_recovery"] is True

    # Password & recovery sama-sama membuka setelah ditambahkan.
    _assert_restores(vault_path, tmp_path, PASSWORD)
    _assert_restores(vault_path, tmp_path, code)

    status, message = remove_recovery_key(str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS, message
    assert vault_info(str(vault_path))["has_recovery"] is False

    # Recovery code tidak lagi membuka; password tetap.
    status, _ = buka_brankas(str(vault_path), code)
    assert status == VaultStatus.WRONG_PASSWORD
    _assert_restores(vault_path, tmp_path, PASSWORD)


def test_add_recovery_key_rejected_when_present(tmp_path):
    code = generate_recovery_code()
    source, vault_path = _lock(tmp_path, recovery_secret=code, recovery_type="code")
    shutil.rmtree(source)

    status, message = add_recovery_key(str(vault_path), PASSWORD, generate_recovery_code(), "code")
    assert status == VaultStatus.ERROR
    assert "already has a recovery" in (message or "").lower()


def test_add_recovery_key_wrong_password(tmp_path):
    _, vault_path = _lock(tmp_path)
    status, _ = add_recovery_key(str(vault_path), "wrong", generate_recovery_code(), "code")
    assert status == VaultStatus.WRONG_PASSWORD


def test_remove_recovery_key_when_absent(tmp_path):
    _, vault_path = _lock(tmp_path)
    status, message = remove_recovery_key(str(vault_path), PASSWORD)
    assert status == VaultStatus.ERROR
    assert "no recovery key" in (message or "").lower()


# ── Tamper resistance ────────────────────────────────────────────────────────────


def test_tampered_wrapped_master_key_fails_closed(tmp_path):
    source, vault_path = _lock(tmp_path)
    shutil.rmtree(source)

    # Flip byte terakhir dari keyslot pertama (di dalam wrapped master key).
    hdr = _read_header_from_path(vault_path)
    # Wrapped MK adalah 48 byte terakhir dari slot pertama; slot pertama berakhir
    # tepat sebelum slot berikutnya / akhir region keyslot. Untuk vault 1-slot,
    # itu berakhir di header_end. Flip byte sebelum header_end.
    data = bytearray(vault_path.read_bytes())
    data[hdr["header_end"] - 1] ^= 0x01
    vault_path.write_bytes(data)

    status, _ = buka_brankas(str(vault_path), PASSWORD)
    assert status == VaultStatus.WRONG_PASSWORD
