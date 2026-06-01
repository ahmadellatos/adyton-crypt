"""
Regression tests for buka_brankas authentication order.

Plaintext must not be written to disk and overwrite prompts must not be shown
until the AES-GCM authentication tag has been verified successfully.
"""

import shutil

from core.vault import VaultStatus, buka_brankas, kunci_brankas


PASSWORD = "P@ssw0rd!Kuat123"


def _make_source_folder(tmp_path):
    source = tmp_path / "sample_folder"
    nested = source / "subfolder"
    nested.mkdir(parents=True)
    (source / "dokumen.txt").write_text("Ini file rahasia", encoding="utf-8")
    (nested / "nested.txt").write_text("Isi nested", encoding="utf-8")
    return source


def _corrupt_gcm_tag(vault_path):
    data = bytearray(vault_path.read_bytes())
    data[-1] ^= 0x01
    vault_path.write_bytes(data)


def test_corrupted_tag_does_not_return_overwrite_needed_when_target_folder_exists(tmp_path):
    source = _make_source_folder(tmp_path)
    vault_path = tmp_path / "sample_folder.adtn"

    status, message = kunci_brankas([str(source)], str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS, message

    # Folder tujuan masih ada. Implementasi lama akan mem-parse nama dari chunk awal
    # lalu mengembalikan OVERWRITE_NEEDED sebelum finalize() memverifikasi tag GCM.
    _corrupt_gcm_tag(vault_path)

    status, message = buka_brankas(str(vault_path), PASSWORD)

    assert status == VaultStatus.WRONG_PASSWORD
    assert message is None
    assert (source / "dokumen.txt").read_text(encoding="utf-8") == "Ini file rahasia"


def test_corrupted_tag_does_not_leave_plaintext_temp_dir(tmp_path):
    source = _make_source_folder(tmp_path)
    vault_path = tmp_path / "sample_folder.adtn"

    status, message = kunci_brankas([str(source)], str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS, message
    shutil.rmtree(source)
    _corrupt_gcm_tag(vault_path)

    before = set(tmp_path.glob("._dec_*"))
    status, _ = buka_brankas(str(vault_path), PASSWORD)
    after = set(tmp_path.glob("._dec_*"))

    assert status == VaultStatus.WRONG_PASSWORD
    assert after == before
    assert not source.exists()


def test_authenticated_decrypt_still_restores_valid_vault(tmp_path):
    source = _make_source_folder(tmp_path)
    vault_path = tmp_path / "sample_folder.adtn"

    status, message = kunci_brankas([str(source)], str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS, message

    shutil.rmtree(source)
    status, restored_name = buka_brankas(str(vault_path), PASSWORD)

    assert status == VaultStatus.SUCCESS
    restored = tmp_path / restored_name
    assert (restored / "dokumen.txt").read_text(encoding="utf-8") == "Ini file rahasia"
    assert (restored / "subfolder" / "nested.txt").read_text(encoding="utf-8") == "Isi nested"
