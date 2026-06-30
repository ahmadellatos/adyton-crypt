"""Tests untuk verify_vault — verifikasi vault tanpa menulis output (parity 7-Zip "Test").

Cakupan: credential benar/salah, deteksi korupsi vs wrong-password, truncation, file
asing, vault 2FA (keyfile), recovery key, dan invariant "tidak menulis apa pun ke disk".
"""

import os

from core.crypto import generate_recovery_code
from core.vault import (
    CORRUPT_VAULT_MESSAGE,
    VaultStatus,
    generate_keyfile,
    kunci_brankas,
    verify_vault,
)

PASSWORD = "P@ssw0rd!Kuat123"


def _make_source(tmp_path, name="rahasia"):
    source = tmp_path / name
    nested = source / "nested"
    nested.mkdir(parents=True)
    (source / "a.txt").write_text("alpha" * 1000, encoding="utf-8")
    (nested / "b.txt").write_bytes(os.urandom(40_000))
    return source


def _lock(tmp_path, **kwargs):
    source = _make_source(tmp_path)
    vault_path = tmp_path / "vault.adtn"
    status, message = kunci_brankas([str(source)], str(vault_path), PASSWORD, **kwargs)
    assert status == VaultStatus.SUCCESS, message
    return source, vault_path


def _flip_byte(path, offset):
    with open(path, "r+b") as f:
        f.seek(offset)
        b = f.read(1)
        f.seek(offset)
        f.write(bytes([b[0] ^ 0xFF]))


# ── Jalur sukses ─────────────────────────────────────────────────────────────────


def test_verify_succeeds_with_correct_password(tmp_path):
    _, vault_path = _lock(tmp_path)
    status, message = verify_vault(str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS
    assert "intact" in message.lower()


def test_verify_succeeds_with_recovery_code(tmp_path):
    code = generate_recovery_code()
    _, vault_path = _lock(tmp_path, recovery_secret=code, recovery_type="code")
    assert verify_vault(str(vault_path), code)[0] == VaultStatus.SUCCESS
    # Password tetap memverifikasi juga.
    assert verify_vault(str(vault_path), PASSWORD)[0] == VaultStatus.SUCCESS


def test_verify_reports_progress(tmp_path):
    _, vault_path = _lock(tmp_path)
    seen = []
    status, _ = verify_vault(str(vault_path), PASSWORD, progress_cb=seen.append)
    assert status == VaultStatus.SUCCESS
    assert seen and seen[-1] == 1.0
    assert all(0.0 <= v <= 1.0 for v in seen)


# ── Credential salah ───────────────────────────────────────────────────────────────


def test_verify_wrong_password(tmp_path):
    _, vault_path = _lock(tmp_path)
    status, message = verify_vault(str(vault_path), "salah-total")
    assert status == VaultStatus.WRONG_PASSWORD
    assert message is None


# ── Deteksi korupsi (BUKAN wrong-password) ──────────────────────────────────────────


def test_verify_detects_corruption_in_final_tag(tmp_path):
    """Credential benar tapi byte terakhir (tag FINAL) diubah → CORRUPT, bukan wrong-pw."""
    _, vault_path = _lock(tmp_path)
    size = vault_path.stat().st_size
    _flip_byte(vault_path, size - 1)
    status, message = verify_vault(str(vault_path), PASSWORD)
    assert status == VaultStatus.ERROR
    assert message == CORRUPT_VAULT_MESSAGE


def test_verify_detects_corruption_in_data_record(tmp_path):
    """Byte di tengah arsip (data record) diubah → CORRUPT, password tetap benar."""
    _, vault_path = _lock(tmp_path)
    size = vault_path.stat().st_size
    _flip_byte(vault_path, size // 2)
    status, message = verify_vault(str(vault_path), PASSWORD)
    assert status == VaultStatus.ERROR
    assert message == CORRUPT_VAULT_MESSAGE


def test_verify_detects_truncation(tmp_path):
    """Vault dipotong → record/tag tak lengkap → CORRUPT (credential masih benar)."""
    _, vault_path = _lock(tmp_path)
    data = vault_path.read_bytes()
    vault_path.write_bytes(data[:-30])  # buang sebagian record FINAL
    status, message = verify_vault(str(vault_path), PASSWORD)
    assert status == VaultStatus.ERROR
    assert message == CORRUPT_VAULT_MESSAGE


def test_tampered_wrapped_key_reads_as_wrong_password(tmp_path):
    """Tamper pada wrapped master key membuat unwrap gagal → WRONG_PASSWORD (fail-closed).

    Layout single-password no-hint: core header 29B + slot_count(1) + slot
    [type(1)+kdf_id(1)+params_len(2)+params(12)+salt(16)+nonce(12)+wrapped(48)].
    Offset 80 jatuh di dalam region wrapped master key → AEAD unwrap InvalidTag.
    """
    _, vault_path = _lock(tmp_path)
    _flip_byte(vault_path, 80)
    status, _ = verify_vault(str(vault_path), PASSWORD)
    assert status == VaultStatus.WRONG_PASSWORD


# ── File asing / format ────────────────────────────────────────────────────────────


def test_verify_rejects_non_vault(tmp_path):
    bogus = tmp_path / "notavault.adtn"
    bogus.write_bytes(b"this is not a vault at all" * 50)
    status, message = verify_vault(str(bogus), PASSWORD)
    assert status == VaultStatus.ERROR
    assert "valid Adyton Crypt vault" in message


# ── 2FA / keyfile ──────────────────────────────────────────────────────────────────


def test_verify_2fa_requires_keyfile(tmp_path):
    keyfile = tmp_path / "key.bin"
    assert generate_keyfile(str(keyfile))[0] == VaultStatus.SUCCESS
    _, vault_path = _lock(tmp_path, keyfile_path=str(keyfile))

    # Tanpa keyfile (vault tanpa recovery) → slot keyfile dilewati → WRONG_PASSWORD.
    assert verify_vault(str(vault_path), PASSWORD)[0] == VaultStatus.WRONG_PASSWORD
    # Dengan keyfile → SUCCESS.
    status, _ = verify_vault(str(vault_path), PASSWORD, keyfile_path=str(keyfile))
    assert status == VaultStatus.SUCCESS


# ── Invariant: tidak menulis apa pun ke disk ────────────────────────────────────────


def test_verify_writes_nothing_to_disk(tmp_path):
    source, vault_path = _lock(tmp_path)
    before = {p.name for p in tmp_path.iterdir()}

    status, _ = verify_vault(str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS

    after = {p.name for p in tmp_path.iterdir()}
    # Tidak membuat folder tujuan, file temp, maupun direktori ._dec_*.
    assert after == before
    assert not list(tmp_path.glob("._dec_*"))


def test_verify_works_even_when_target_folder_exists(tmp_path):
    """Verify tak butuh tujuan: walau folder seukuran nama vault sudah ada, tetap SUCCESS
    (tidak mengembalikan OVERWRITE_NEEDED seperti buka_brankas)."""
    source, vault_path = _lock(tmp_path)  # folder sumber 'rahasia' masih ada
    assert source.exists()
    status, _ = verify_vault(str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS
    # Sumber asli tidak disentuh.
    assert (source / "a.txt").exists()
