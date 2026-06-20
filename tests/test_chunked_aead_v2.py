"""
Regression tests for the v2 chunked AEAD vault format.
"""

import io
import os
import shutil
import tarfile

from core.constants import MAGIC_BYTES, VERSION, VERSION_V1, VERSION_V3
from core.crypto import derive_key, make_encryptor
from core.vault import VaultStatus, buka_brankas, kunci_brankas

PASSWORD = "P@ssw0rd!Kuat123"


def _make_source_folder(tmp_path):
    source = tmp_path / "rahasia_v2"
    nested = source / "nested"
    nested.mkdir(parents=True)
    (source / "a.txt").write_text("alpha", encoding="utf-8")
    (nested / "b.txt").write_text("beta", encoding="utf-8")
    return source


def _corrupt_last_byte(path):
    data = bytearray(path.read_bytes())
    data[-1] ^= 0x01
    path.write_bytes(data)


def test_new_vaults_use_envelope_v3_and_roundtrip(tmp_path):
    source = _make_source_folder(tmp_path)
    vault_path = tmp_path / "rahasia_v2.adtn"

    status, message = kunci_brankas([str(source)], str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS, message

    with vault_path.open("rb") as f:
        assert f.read(4) == MAGIC_BYTES
        assert f.read(1) == VERSION_V3
        assert VERSION == VERSION_V3

    shutil.rmtree(source)
    status, restored_name = buka_brankas(str(vault_path), PASSWORD)

    assert status == VaultStatus.SUCCESS
    restored = tmp_path / restored_name
    assert (restored / "a.txt").read_text(encoding="utf-8") == "alpha"
    assert (restored / "nested" / "b.txt").read_text(encoding="utf-8") == "beta"


def test_corrupted_final_record_does_not_prompt_overwrite_or_leave_temp(tmp_path):
    source = _make_source_folder(tmp_path)
    vault_path = tmp_path / "rahasia_v2.adtn"

    status, message = kunci_brankas([str(source)], str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS, message

    # Folder tujuan masih ada. Walau metadata v2 valid, prompt overwrite tidak
    # boleh muncul jika final record rusak karena seluruh vault belum valid.
    _corrupt_last_byte(vault_path)
    before = set(tmp_path.glob("._dec_*"))
    status, message = buka_brankas(str(vault_path), PASSWORD)
    after = set(tmp_path.glob("._dec_*"))

    assert status == VaultStatus.WRONG_PASSWORD
    assert message is None
    assert after == before
    assert (source / "a.txt").read_text(encoding="utf-8") == "alpha"


def test_truncated_v2_vault_is_rejected_without_temp_leak(tmp_path):
    source = _make_source_folder(tmp_path)
    vault_path = tmp_path / "rahasia_v2.adtn"

    status, message = kunci_brankas([str(source)], str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS, message
    shutil.rmtree(source)

    data = vault_path.read_bytes()
    vault_path.write_bytes(data[:-23])

    before = set(tmp_path.glob("._dec_*"))
    status, _ = buka_brankas(str(vault_path), PASSWORD)
    after = set(tmp_path.glob("._dec_*"))

    assert status == VaultStatus.WRONG_PASSWORD
    assert after == before
    assert not source.exists()


def _create_legacy_v1_vault(tmp_path):
    folder_name = "legacy_v1"
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = derive_key(PASSWORD, salt)

    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
        data = b"legacy content"
        info = tarfile.TarInfo(name=f"{folder_name}/legacy.txt")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

    name_bytes = folder_name.encode("utf-8")
    plaintext = len(name_bytes).to_bytes(2, "big") + name_bytes + tar_buffer.getvalue()

    encryptor = make_encryptor(key, nonce)
    ciphertext = encryptor.update(plaintext) + encryptor.finalize()

    vault_path = tmp_path / "legacy_v1.adtn"
    with vault_path.open("wb") as f:
        f.write(MAGIC_BYTES)
        f.write(VERSION_V1)
        f.write(salt)
        f.write(nonce)
        f.write(ciphertext)
        f.write(encryptor.tag)

    return vault_path


def test_legacy_v1_vaults_remain_readable(tmp_path):
    vault_path = _create_legacy_v1_vault(tmp_path)

    status, restored_name = buka_brankas(str(vault_path), PASSWORD)

    assert status == VaultStatus.SUCCESS
    assert restored_name == "legacy_v1"
    assert (tmp_path / restored_name / "legacy.txt").read_text(encoding="utf-8") == "legacy content"
