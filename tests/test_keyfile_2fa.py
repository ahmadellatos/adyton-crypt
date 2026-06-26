"""Tests untuk faktor kedua keyfile (2FA): create / open / kelola.

Model: slot password vault digabung dengan isi keyfile sehingga membuka vault WAJIB
punya password DAN keyfile. Recovery key (bila ada) tetap menjadi jalur break-glass
yang membuka vault sendiri tanpa keyfile.
"""

import shutil

from core.constants import (
    KEYFILE_GENERATED_SIZE,
    SLOT_TYPE_PASSWORD,
    SLOT_TYPE_PASSWORD_KEYFILE,
)
from core.crypto import generate_recovery_code
from core.vault import (
    VaultStatus,
    _read_header_from_path,
    add_keyfile,
    add_recovery_key,
    buka_brankas,
    change_password,
    generate_keyfile,
    kunci_brankas,
    remove_keyfile,
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


def _make_keyfile(tmp_path, name="secret.key", data=b"\x00\x01\x02keyfile-material\xff" * 4):
    kf = tmp_path / name
    kf.write_bytes(data)
    return kf


def _lock(tmp_path, password=PASSWORD, name="vault.adtn", **kwargs):
    source = _make_source(tmp_path)
    vault_path = tmp_path / name
    status, message = kunci_brankas([str(source)], str(vault_path), password, **kwargs)
    assert status == VaultStatus.SUCCESS, message
    shutil.rmtree(source)
    return vault_path


def _assert_restores(vault_path, tmp_path, secret, keyfile_path=None):
    status, restored_name = buka_brankas(str(vault_path), secret, keyfile_path=keyfile_path)
    assert status == VaultStatus.SUCCESS, f"expected SUCCESS, got {status}"
    restored = tmp_path / restored_name
    assert (restored / "a.txt").read_text(encoding="utf-8") == "alpha"
    assert (restored / "nested" / "b.txt").read_text(encoding="utf-8") == "beta"
    shutil.rmtree(restored)


# ── Create + open ────────────────────────────────────────────────────────────────


def test_keyfile_vault_needs_both_password_and_keyfile(tmp_path):
    kf = _make_keyfile(tmp_path)
    vault_path = _lock(tmp_path, keyfile_path=str(kf))

    # Slot password disimpan sebagai slot keyfile (2FA).
    hdr = _read_header_from_path(vault_path)
    assert hdr["slots"][0]["slot_type"] == SLOT_TYPE_PASSWORD_KEYFILE

    # Password + keyfile yang benar membuka vault.
    _assert_restores(vault_path, tmp_path, PASSWORD, keyfile_path=str(kf))

    # Password saja (tanpa keyfile) ditolak.
    status, _ = buka_brankas(str(vault_path), PASSWORD)
    assert status == VaultStatus.WRONG_PASSWORD

    # Keyfile benar tapi password salah ditolak.
    status, _ = buka_brankas(str(vault_path), "salah-password", keyfile_path=str(kf))
    assert status == VaultStatus.WRONG_PASSWORD

    # Password benar tapi keyfile salah ditolak.
    wrong_kf = _make_keyfile(tmp_path, name="wrong.key", data=b"isi keyfile yang berbeda")
    status, _ = buka_brankas(str(vault_path), PASSWORD, keyfile_path=str(wrong_kf))
    assert status == VaultStatus.WRONG_PASSWORD


def test_vault_info_reports_requires_keyfile(tmp_path):
    kf = _make_keyfile(tmp_path)
    vault_2fa = _lock(tmp_path, keyfile_path=str(kf), name="twofa.adtn")
    vault_plain = _lock(tmp_path, name="plain.adtn")

    assert vault_info(str(vault_2fa))["requires_keyfile"] is True
    assert vault_info(str(vault_plain))["requires_keyfile"] is False


def test_recovery_key_opens_2fa_vault_without_keyfile(tmp_path):
    """Recovery key = jalur break-glass: membuka vault 2FA tanpa keyfile."""
    kf = _make_keyfile(tmp_path)
    code = generate_recovery_code()
    vault_path = _lock(tmp_path, keyfile_path=str(kf), recovery_secret=code, recovery_type="code")

    # Recovery key membuka tanpa keyfile (kehilangan keyfile tetap bisa masuk).
    _assert_restores(vault_path, tmp_path, code)
    # Password + keyfile tetap bekerja.
    _assert_restores(vault_path, tmp_path, PASSWORD, keyfile_path=str(kf))
    # Password tanpa keyfile tetap ditolak.
    status, _ = buka_brankas(str(vault_path), PASSWORD)
    assert status == VaultStatus.WRONG_PASSWORD


def test_same_keyfile_two_vaults_are_independent(tmp_path):
    """Satu keyfile boleh dipakai banyak vault; file_id mengikat slot ke vault-nya."""
    kf = _make_keyfile(tmp_path)
    va = _lock(tmp_path, password=PASSWORD, name="a.adtn", keyfile_path=str(kf))
    vb = _lock(tmp_path, password=NEW_PASSWORD, name="b.adtn", keyfile_path=str(kf))

    _assert_restores(va, tmp_path, PASSWORD, keyfile_path=str(kf))
    _assert_restores(vb, tmp_path, NEW_PASSWORD, keyfile_path=str(kf))

    # Keyfile yang sama tapi password vault lain → tetap ditolak.
    status, _ = buka_brankas(str(va), NEW_PASSWORD, keyfile_path=str(kf))
    assert status == VaultStatus.WRONG_PASSWORD


# ── Keyfile validation & generation ──────────────────────────────────────────────


def test_empty_keyfile_rejected_on_lock(tmp_path):
    empty = tmp_path / "empty.key"
    empty.write_bytes(b"")
    source = _make_source(tmp_path)
    status, message = kunci_brankas(
        [str(source)], str(tmp_path / "v.adtn"), PASSWORD, keyfile_path=str(empty)
    )
    assert status == VaultStatus.ERROR
    assert "empty" in message.lower()


def test_missing_keyfile_path_errors_on_open(tmp_path):
    kf = _make_keyfile(tmp_path)
    vault_path = _lock(tmp_path, keyfile_path=str(kf))
    status, message = buka_brankas(
        str(vault_path), PASSWORD, keyfile_path=str(tmp_path / "nope.key")
    )
    assert status == VaultStatus.ERROR
    assert message and "keyfile" in message.lower()


def test_generate_keyfile_writes_random_bytes_and_refuses_overwrite(tmp_path):
    kf_path = tmp_path / "generated.key"
    status, _ = generate_keyfile(str(kf_path))
    assert status == VaultStatus.SUCCESS
    data = kf_path.read_bytes()
    assert len(data) == KEYFILE_GENERATED_SIZE

    # Tak menimpa file yang sudah ada.
    status, message = generate_keyfile(str(kf_path))
    assert status == VaultStatus.ERROR
    assert "already exists" in message.lower()

    # Keyfile hasil generate benar-benar berfungsi sebagai faktor.
    vault_path = _lock(tmp_path, keyfile_path=str(kf_path))
    _assert_restores(vault_path, tmp_path, PASSWORD, keyfile_path=str(kf_path))


# ── change_password pada vault 2FA ───────────────────────────────────────────────


def test_change_password_2fa_requires_keyfile(tmp_path):
    kf = _make_keyfile(tmp_path)
    vault_path = _lock(tmp_path, keyfile_path=str(kf))

    # Tanpa keyfile → ditolak dengan pesan minta keyfile.
    status, message = change_password(str(vault_path), PASSWORD, NEW_PASSWORD)
    assert status == VaultStatus.ERROR
    assert "keyfile" in message.lower()

    # Dengan keyfile → sukses; slot tetap tipe keyfile.
    status, _ = change_password(str(vault_path), PASSWORD, NEW_PASSWORD, keyfile_path=str(kf))
    assert status == VaultStatus.SUCCESS
    hdr = _read_header_from_path(vault_path)
    assert hdr["slots"][0]["slot_type"] == SLOT_TYPE_PASSWORD_KEYFILE

    # Password baru + keyfile membuka; password lama tidak.
    _assert_restores(vault_path, tmp_path, NEW_PASSWORD, keyfile_path=str(kf))
    status, _ = buka_brankas(str(vault_path), PASSWORD, keyfile_path=str(kf))
    assert status == VaultStatus.WRONG_PASSWORD


def test_change_password_2fa_via_recovery_keeps_keyfile(tmp_path):
    """Reset password pakai recovery key + keyfile → password baru tetap 2FA."""
    kf = _make_keyfile(tmp_path)
    code = generate_recovery_code()
    vault_path = _lock(tmp_path, keyfile_path=str(kf), recovery_secret=code, recovery_type="code")

    status, _ = change_password(str(vault_path), code, NEW_PASSWORD, keyfile_path=str(kf))
    assert status == VaultStatus.SUCCESS

    _assert_restores(vault_path, tmp_path, NEW_PASSWORD, keyfile_path=str(kf))
    # Recovery key tetap berlaku.
    _assert_restores(vault_path, tmp_path, code)


# ── add_keyfile / remove_keyfile ─────────────────────────────────────────────────


def test_add_keyfile_converts_plain_vault_to_2fa(tmp_path):
    kf = _make_keyfile(tmp_path)
    vault_path = _lock(tmp_path)  # vault biasa (password saja)
    assert vault_info(str(vault_path))["requires_keyfile"] is False

    status, _ = add_keyfile(str(vault_path), PASSWORD, str(kf))
    assert status == VaultStatus.SUCCESS
    assert vault_info(str(vault_path))["requires_keyfile"] is True

    # Sekarang butuh keduanya.
    _assert_restores(vault_path, tmp_path, PASSWORD, keyfile_path=str(kf))
    status, _ = buka_brankas(str(vault_path), PASSWORD)
    assert status == VaultStatus.WRONG_PASSWORD


def test_add_keyfile_wrong_password_rejected(tmp_path):
    kf = _make_keyfile(tmp_path)
    vault_path = _lock(tmp_path)
    status, _ = add_keyfile(str(vault_path), "password-salah", str(kf))
    assert status == VaultStatus.WRONG_PASSWORD
    # Vault tak berubah.
    assert vault_info(str(vault_path))["requires_keyfile"] is False


def test_add_keyfile_requires_actual_password_not_recovery(tmp_path):
    """add_keyfile membangun ulang slot password → recovery code tak boleh diterima."""
    kf = _make_keyfile(tmp_path)
    code = generate_recovery_code()
    vault_path = _lock(tmp_path, recovery_secret=code, recovery_type="code")

    status, _ = add_keyfile(str(vault_path), code, str(kf))
    assert status == VaultStatus.WRONG_PASSWORD
    assert vault_info(str(vault_path))["requires_keyfile"] is False


def test_add_keyfile_rejected_when_already_2fa(tmp_path):
    kf = _make_keyfile(tmp_path)
    vault_path = _lock(tmp_path, keyfile_path=str(kf))
    status, message = add_keyfile(str(vault_path), PASSWORD, str(kf))
    assert status == VaultStatus.ERROR
    assert "already" in message.lower()


def test_remove_keyfile_converts_2fa_to_plain(tmp_path):
    kf = _make_keyfile(tmp_path)
    vault_path = _lock(tmp_path, keyfile_path=str(kf))

    status, _ = remove_keyfile(str(vault_path), PASSWORD, str(kf))
    assert status == VaultStatus.SUCCESS
    assert vault_info(str(vault_path))["requires_keyfile"] is False

    hdr = _read_header_from_path(vault_path)
    assert hdr["slots"][0]["slot_type"] == SLOT_TYPE_PASSWORD

    # Password saja sekarang membuka.
    _assert_restores(vault_path, tmp_path, PASSWORD)


def test_remove_keyfile_wrong_keyfile_rejected(tmp_path):
    kf = _make_keyfile(tmp_path)
    vault_path = _lock(tmp_path, keyfile_path=str(kf))
    wrong_kf = _make_keyfile(tmp_path, name="wrong.key", data=b"keyfile lain")

    status, _ = remove_keyfile(str(vault_path), PASSWORD, str(wrong_kf))
    assert status == VaultStatus.WRONG_PASSWORD
    # Masih 2FA.
    assert vault_info(str(vault_path))["requires_keyfile"] is True


def test_remove_keyfile_on_plain_vault_errors(tmp_path):
    kf = _make_keyfile(tmp_path)
    vault_path = _lock(tmp_path)  # bukan 2FA
    status, message = remove_keyfile(str(vault_path), PASSWORD, str(kf))
    assert status == VaultStatus.ERROR
    assert "isn't protected by a keyfile" in message.lower() or "keyfile" in message.lower()


def test_add_recovery_to_2fa_vault_uses_keyfile(tmp_path):
    """add_recovery_key pada vault 2FA membutuhkan password + keyfile."""
    kf = _make_keyfile(tmp_path)
    vault_path = _lock(tmp_path, keyfile_path=str(kf))
    code = generate_recovery_code()

    # Tanpa keyfile, password saja tak membuka slot → ditolak.
    status, _ = add_recovery_key(str(vault_path), PASSWORD, code, "code")
    assert status == VaultStatus.WRONG_PASSWORD

    # Dengan keyfile → sukses, recovery key lalu membuka tanpa keyfile.
    status, _ = add_recovery_key(str(vault_path), PASSWORD, code, "code", keyfile_path=str(kf))
    assert status == VaultStatus.SUCCESS
    assert vault_info(str(vault_path))["has_recovery"] is True
    _assert_restores(vault_path, tmp_path, code)
