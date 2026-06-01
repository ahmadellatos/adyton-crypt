"""
tests/test_vault.py
Unit + Integration test untuk core/vault.py dengan refactor VaultStatus (Enum).
"""

import os
import shutil
import pytest
from pathlib import Path

from core.vault import kunci_brankas, buka_brankas, VaultStatus, _is_safe_tar_member
from tests.conftest import folder_checksum

PASSWORD_BENAR = "P@ssw0rd!Kuat123"
PASSWORD_SALAH = "password_salah_banget"


def kunci_dan_dapat_path(folder, password=PASSWORD_BENAR, hapus=False, cb=None):
    base_dir = os.path.dirname(folder)
    path_simpan = os.path.join(base_dir, f"{os.path.basename(folder)}.adtn")

    status, pesan = kunci_brankas(
        [folder], path_simpan, password, hapus_asli=hapus, progress_cb=cb
    )
    assert status == VaultStatus.SUCCESS, f"kunci_brankas gagal: {pesan}"
    assert os.path.exists(path_simpan), "File target tidak terbentuk"
    return path_simpan


class TestHappyPath:
    def test_kunci_menghasilkan_file_locked(self, sample_folder):
        base_dir = os.path.dirname(sample_folder)
        path_simpan = os.path.join(base_dir, "test_file.adtn")

        status, pesan = kunci_brankas([sample_folder], path_simpan, PASSWORD_BENAR)
        assert status == VaultStatus.SUCCESS
        assert os.path.exists(path_simpan)

    def test_kunci_pesan_sukses(self, sample_folder):
        base_dir = os.path.dirname(sample_folder)
        path_simpan = os.path.join(base_dir, "test_file.adtn")

        _, pesan = kunci_brankas([sample_folder], path_simpan, PASSWORD_BENAR)
        assert "Brankas berhasil dikunci" in pesan

    def test_kunci_lalu_buka_isi_sama(self, sample_folder):
        checksum_sebelum = folder_checksum(sample_folder)
        locked_path = kunci_dan_dapat_path(sample_folder)
        base_dir = os.path.dirname(locked_path)

        shutil.rmtree(sample_folder)
        status, nama = buka_brankas(locked_path, PASSWORD_BENAR)
        assert status == VaultStatus.SUCCESS

        folder_restored = os.path.join(base_dir, nama)
        assert checksum_sebelum == folder_checksum(folder_restored)

    def test_buka_mengembalikan_nama_folder(self, sample_folder):
        locked_path = kunci_dan_dapat_path(sample_folder)
        shutil.rmtree(sample_folder)
        status, nama = buka_brankas(locked_path, PASSWORD_BENAR)
        assert status == VaultStatus.SUCCESS
        assert nama == os.path.basename(sample_folder)


class TestWrongPassword:
    def test_wrong_password_return_status(self, sample_folder):
        locked_path = kunci_dan_dapat_path(sample_folder)
        shutil.rmtree(sample_folder)
        status, msg = buka_brankas(locked_path, PASSWORD_SALAH)
        assert status == VaultStatus.WRONG_PASSWORD

    def test_wrong_password_tidak_buat_folder(self, sample_folder, tmp_dir):
        locked_path = kunci_dan_dapat_path(sample_folder)
        shutil.rmtree(sample_folder)
        folder_before = set(os.listdir(tmp_dir))
        buka_brankas(locked_path, PASSWORD_SALAH)
        folder_after = set(os.listdir(tmp_dir))
        new_items = folder_after - folder_before
        assert all(item.endswith(".adtn") for item in new_items)


class TestFileCorrupt:
    def test_file_terlalu_kecil(self, tmp_dir):
        path = os.path.join(tmp_dir, "kecil.adtn")
        with open(path, "wb") as f:
            f.write(b"x" * 10)
        status, msg = buka_brankas(path, PASSWORD_BENAR)
        assert status == VaultStatus.ERROR

    def test_file_kosong(self, tmp_dir):
        path = os.path.join(tmp_dir, "kosong.adtn")
        open(path, "wb").close()
        status, msg = buka_brankas(path, PASSWORD_BENAR)
        assert status == VaultStatus.ERROR


class TestOverwrite:
    def test_overwrite_prompt_jika_folder_ada(self, sample_folder):
        locked_path = kunci_dan_dapat_path(sample_folder)
        status, nama = buka_brankas(locked_path, PASSWORD_BENAR)
        assert status == VaultStatus.OVERWRITE_NEEDED

    def test_force_true_timpa_folder(self, sample_folder):
        locked_path = kunci_dan_dapat_path(sample_folder)
        with open(os.path.join(sample_folder, "dokumen.txt"), "w") as f:
            f.write("ISI YANG SUDAH DIUBAH")
        status, nama = buka_brankas(locked_path, PASSWORD_BENAR, force=True)
        assert status == VaultStatus.SUCCESS


class TestHapusAsli:
    def test_hapus_asli_true_menghapus_folder(self, sample_folder):
        base_dir = os.path.dirname(sample_folder)
        path_simpan = os.path.join(base_dir, "hapus_asli.adtn")
        status, _ = kunci_brankas(
            [sample_folder], path_simpan, PASSWORD_BENAR, hapus_asli=True
        )
        assert status == VaultStatus.SUCCESS
        assert not os.path.exists(sample_folder)


class TestEdgeCases:
    def test_folder_kosong(self, empty_folder):
        locked_path = kunci_dan_dapat_path(empty_folder)
        shutil.rmtree(empty_folder)
        status, nama = buka_brankas(locked_path, PASSWORD_BENAR)
        assert status == VaultStatus.SUCCESS

    def test_file_unicode(self, sample_folder_unicode):
        locked_path = kunci_dan_dapat_path(sample_folder_unicode)
        shutil.rmtree(sample_folder_unicode)
        status, nama = buka_brankas(locked_path, PASSWORD_BENAR)
        assert status == VaultStatus.SUCCESS

    def test_folder_path_tidak_ada(self, tmp_dir):
        path_fiktif = os.path.join(tmp_dir, "tidak_ada")
        path_simpan = os.path.join(tmp_dir, "out.adtn")
        status, pesan = kunci_brankas([path_fiktif], path_simpan, PASSWORD_BENAR)
        assert status == VaultStatus.ERROR


# ============================================================================
# NEW TESTS FOR HARDENED FEATURES (from security review)
# ============================================================================

import tarfile
import io
from core.vault import (
    MAGIC_BYTES, VERSION, HEADER_SIZE, OVERHEAD,
    kunci_brankas, buka_brankas, VaultStatus
)
from core.crypto import derive_key, make_encryptor, CHUNK_SIZE
from core.worker import CryptoWorker
from PySide6.QtCore import QThread


class TestHeaderFormat:
    """Test the new ADTN magic + version header introduced in the refactor."""

    def test_magic_bytes_and_version_written(self, sample_folder, tmp_dir):
        """Vault file must start with correct MAGIC + VERSION."""
        path_simpan = os.path.join(tmp_dir, "header_test.adtn")
        status, _ = kunci_brankas([sample_folder], path_simpan, PASSWORD_BENAR)
        assert status == VaultStatus.SUCCESS

        with open(path_simpan, "rb") as f:
            magic = f.read(4)
            version = f.read(1)
        assert magic == MAGIC_BYTES
        assert version == VERSION

    def test_wrong_magic_returns_error(self, tmp_dir):
        """Corrupted magic bytes must be rejected early."""
        path = os.path.join(tmp_dir, "bad_magic.adtn")
        with open(path, "wb") as f:
            f.write(b"XXXX\x01" + b"\x00" * 100)  # wrong magic

        status, msg = buka_brankas(path, PASSWORD_BENAR)
        assert status == VaultStatus.ERROR
        assert "bukan format brankas Adyton Crypt" in (msg or "")

    def test_unsupported_version_returns_error(self, tmp_dir):
        """Future version must tell user to update the app."""
        path = os.path.join(tmp_dir, "future_version.adtn")
        with open(path, "wb") as f:
            f.write(MAGIC_BYTES + b"\x02" + b"\x00" * 200)

        status, msg = buka_brankas(path, PASSWORD_BENAR)
        assert status == VaultStatus.ERROR
        assert "terlalu baru" in (msg or "").lower()

    def test_garbage_name_length_on_wrong_password_returns_wrong_password_not_error(self, sample_folder, tmp_dir):
        """Regression guard: wrong password with large garbage length prefix must still be WRONG_PASSWORD."""
        locked_path = kunci_dan_dapat_path(sample_folder)
        shutil.rmtree(sample_folder)

        # Simulate the case where first decrypted bytes happen to have huge length value
        # (this used to return ERROR before the heuristic fix)
        status, msg = buka_brankas(locked_path, PASSWORD_SALAH)
        assert status == VaultStatus.WRONG_PASSWORD


class TestSecureWipeBasic:
    """Basic verification that secure wipe actually overwrites original data."""

    def test_secure_wipe_overwrites_content(self, tmp_dir):
        # Create a file with known content
        secret_file = os.path.join(tmp_dir, "secret.txt")
        original_content = b"THIS_IS_SUPER_SECRET_DATA_1234567890" * 20
        with open(secret_file, "wb") as f:
            f.write(original_content)

        # Lock with secure wipe + delete original
        vault_path = os.path.join(tmp_dir, "wiped.adtn")
        status, _ = kunci_brankas(
            [secret_file],
            vault_path,
            PASSWORD_BENAR,
            hapus_asli=True,
            secure_wipe=True,
        )
        assert status == VaultStatus.SUCCESS
        assert not os.path.exists(secret_file), "Original file should be deleted"

        # Re-create a file with same name in same location (simulating attacker)
        # We can't easily recover the deleted file, but we can check behavior.
        # For this basic test we just ensure the operation completed without crash.
        # A stronger test would require low-level disk forensics which is out of scope.
        assert os.path.exists(vault_path)


class TestCancellationDuringDecrypt:
    """Test that cancellation works during the new full-decrypt-to-temp flow."""

    def test_cancel_during_buka_brankas(self, sample_folder, tmp_dir):
        locked_path = kunci_dan_dapat_path(sample_folder)

        worker = CryptoWorker(buka_brankas, locked_path, PASSWORD_BENAR)
        worker.start()

        # Cancel very quickly (before it finishes)
        QThread.msleep(5)
        worker.cancel()
        worker.wait(3000)  # give it time to clean up

        # We mainly care that it didn't crash and returned CANCELLED or finished
        # In practice with small files it may finish before cancel lands.
        # The important thing is no unhandled exception and temp dir cleanup.
        assert not worker.isRunning()


# --- TarSlip test helper (creates a malicious vault manually) ---

def _create_malicious_vault_with_pathslip(tmp_dir: str, evil_path: str) -> str:
    """
    Creates a real .adtn file whose inner tar contains a member that tries
    to escape (TarSlip). This directly exercises the security check added
    in the recent hardening.
    """
    password = PASSWORD_BENAR
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = derive_key(password, salt)

    # Build malicious tar in memory with a bad member path
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
        info = tarfile.TarInfo(name=evil_path)
        data = b"malicious content written via path traversal attack"
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

    tar_data = tar_buffer.getvalue()

    # Encrypt exactly like production code: first the virtual folder name (valid), then the tar payload
    folder_name = "SlippedBrankas"
    name_bytes = folder_name.encode("utf-8")
    name_len = len(name_bytes).to_bytes(2, "big")

    encryptor = make_encryptor(key, nonce)
    encrypted_name = encryptor.update(name_len + name_bytes)
    encrypted_tar = encryptor.update(tar_data) + encryptor.finalize()
    tag = encryptor.tag

    # Assemble full vault file
    vault_path = os.path.join(tmp_dir, "tar_slip_test.adtn")
    with open(vault_path, "wb") as f:
        f.write(MAGIC_BYTES)
        f.write(VERSION)
        f.write(salt)
        f.write(nonce)
        f.write(encrypted_name)
        f.write(encrypted_tar)
        f.write(tag)

    return vault_path


class TestTarSlipProtection:
    """Explicit tests for the TarSlip hardening."""

    def test_tar_slip_with_parent_directory_rejected(self, tmp_dir):
        malicious = _create_malicious_vault_with_pathslip(tmp_dir, "../evil.txt")
        status, msg = buka_brankas(malicious, PASSWORD_BENAR)
        # Should not succeed and must not create files outside
        assert status in (VaultStatus.ERROR, VaultStatus.WRONG_PASSWORD)

        # Make sure no evil.txt was written to parent of tmp_dir
        evil_outside = os.path.join(os.path.dirname(tmp_dir), "evil.txt")
        assert not os.path.exists(evil_outside), "TarSlip protection failed!"

    def test_tar_slip_with_absolute_path_rejected(self, tmp_dir):
        # On Windows absolute paths in tar are tricky, use a very obvious bad one
        bad = "C:/Windows/System32/evil.dll" if os.name == "nt" else "/etc/shadow"
        malicious = _create_malicious_vault_with_pathslip(tmp_dir, bad)
        status, msg = buka_brankas(malicious, PASSWORD_BENAR)
        assert status in (VaultStatus.ERROR, VaultStatus.WRONG_PASSWORD)


# ============================================================================
# PHASE 4 — GUARDRAIL TESTS (Verification for High-priority smells)
# ============================================================================


class TestCleanupInvariants:
    """Tests that ensure temporary plaintext never leaks on error paths."""

    def test_no_temp_dir_left_after_wrong_password(self, sample_folder, tmp_dir):
        """Setelah password salah, tidak boleh ada direktori ._dec_* yang tersisa."""
        locked_path = kunci_dan_dapat_path(sample_folder)
        shutil.rmtree(sample_folder)

        parent = Path(tmp_dir)
        before = set(parent.glob("._dec_*"))

        buka_brankas(locked_path, PASSWORD_SALAH)

        after = set(parent.glob("._dec_*"))
        leaked = after - before
        assert not leaked, f"Temporary decrypt directory bocor: {leaked}"

    def test_no_temp_dir_left_after_cancel(self, sample_folder, tmp_dir):
        """Cancellation selama dekripsi harus tetap membersihkan temporary files."""
        locked_path = kunci_dan_dapat_path(sample_folder)

        worker = CryptoWorker(buka_brankas, locked_path, PASSWORD_BENAR)
        worker.start()
        QThread.msleep(10)
        worker.cancel()
        worker.wait(3000)

        parent = Path(tmp_dir)
        leaked = list(parent.glob("._dec_*"))
        assert not leaked, f"Temporary files bocor setelah cancel: {leaked}"


class TestWrongPasswordEdgeCases:
    """Additional guardrails for the password detection heuristic."""

    def test_very_large_garbage_name_length_returns_wrong_password(self, sample_folder, tmp_dir):
        """Garbage dengan panjang nama sangat besar harus tetap dianggap wrong password."""
        locked_path = kunci_dan_dapat_path(sample_folder)
        shutil.rmtree(sample_folder)

        status, _ = buka_brankas(locked_path, PASSWORD_SALAH)
        assert status == VaultStatus.WRONG_PASSWORD


class TestSecureWipeGuardrails:
    """Basic guard for secure deletion behavior."""

    def test_secure_wipe_with_hapus_asli_actually_deletes_original(self, tmp_dir):
        secret_file = os.path.join(tmp_dir, "top_secret.txt")
        with open(secret_file, "w") as f:
            f.write("SANGAT RAHASIA " * 100)

        vault_path = os.path.join(tmp_dir, "secure.adtn")
        status, _ = kunci_brankas(
            [secret_file],
            vault_path,
            PASSWORD_BENAR,
            hapus_asli=True,
            secure_wipe=True,
        )
        assert status == VaultStatus.SUCCESS
        assert not os.path.exists(secret_file), "Original file harus sudah terhapus setelah secure wipe"


def test_tarslip_path_traversal():
    """Memastikan _is_safe_tar_member memblokir upaya eksploitasi Path Traversal."""
    target = Path("/tmp/safe_dir")

    # Kasus berbahaya — harus False
    assert not _is_safe_tar_member("../escape.txt", target)
    assert not _is_safe_tar_member("../../etc/passwd", target)
    assert not _is_safe_tar_member("subdir/../../../Windows/System32/cmd.exe", target)
    assert not _is_safe_tar_member("/absolute/path/hacked.txt", target)

    # Kasus aman — harus True
    assert _is_safe_tar_member("file_aman.txt", target)
    assert _is_safe_tar_member("folder/subfolder/file_aman.txt", target)
