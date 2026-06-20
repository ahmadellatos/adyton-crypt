"""
Regression tests for v2 KDF versioning and Argon2id migration.
"""

import io
import os
import shutil
import tarfile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.constants import (
    ARGON2ID_PARAMS_SIZE,
    KDF_ID_ARGON2ID,
    KDF_ID_PBKDF2_SHA256,
    MAGIC_BYTES,
    RECORD_TYPE_DATA,
    RECORD_TYPE_FINAL,
    RECORD_TYPE_METADATA,
    SLOT_TYPE_PASSWORD,
    V2_FLAG_NONE,
    V3_CORE_HEADER_SIZE,
    V3_FLAG_NONE,
    VERSION_V3,
)

# Offset awal Argon2id params di slot 0 untuk vault v3 default (tanpa hint,
# satu slot password): core header + slot_count(1) + slot_type(1) + kdf_id(1)
# + params_len(2).
_V3_SLOT0_PARAMS_START = V3_CORE_HEADER_SIZE + 1 + 1 + 1 + 2
from core.crypto import derive_key, derive_key_for_kdf
from core.vault import (
    VaultStatus,
    _encode_argon2id_params,
    _v2_header_context,
    _v2_write_record,
    buka_brankas,
    kunci_brankas,
)

PASSWORD = "P@ssw0rd!Kuat123"


def _make_source_folder(tmp_path):
    source = tmp_path / "argon2_source"
    source.mkdir()
    (source / "secret.txt").write_text("secret content", encoding="utf-8")
    return source


def test_new_vaults_use_envelope_v3_with_argon2id_keyslot(tmp_path):
    source = _make_source_folder(tmp_path)
    vault_path = tmp_path / "argon2.adtn"

    status, message = kunci_brankas([str(source)], str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS, message

    with vault_path.open("rb") as f:
        assert f.read(4) == MAGIC_BYTES
        assert f.read(1) == VERSION_V3
        f.read(16)  # file_id
        chunk_size = int.from_bytes(f.read(4), "big")
        flags = int.from_bytes(f.read(4), "big")
        slot_count = f.read(1)[0]
        # Keyslot 0
        slot_type = f.read(1)[0]
        kdf_id = f.read(1)[0]
        params_len = int.from_bytes(f.read(2), "big")
        params = f.read(params_len)

        assert chunk_size > 0
        assert flags == V3_FLAG_NONE  # no hint by default
        assert slot_count == 1  # password-only by default (no recovery key)
        assert slot_type == SLOT_TYPE_PASSWORD
        assert kdf_id == KDF_ID_ARGON2ID
        assert params_len == ARGON2ID_PARAMS_SIZE
        assert len(params) == ARGON2ID_PARAMS_SIZE


def test_argon2id_v2_roundtrip_and_wrong_password(tmp_path):
    source = _make_source_folder(tmp_path)
    vault_path = tmp_path / "roundtrip.adtn"

    status, message = kunci_brankas([str(source)], str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS, message

    shutil.rmtree(source)

    status, message = buka_brankas(str(vault_path), "wrong-password")
    assert status == VaultStatus.WRONG_PASSWORD
    assert message is None
    assert not source.exists()

    status, restored_name = buka_brankas(str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS
    restored = tmp_path / restored_name
    assert (restored / "secret.txt").read_text(encoding="utf-8") == "secret content"


def _create_legacy_v2_pbkdf2_vault(tmp_path):
    """Create a v2 vault using the old chunked-AEAD header without kdf_id."""
    folder_name = "legacy_v2_pbkdf2"
    salt = os.urandom(16)
    file_id = os.urandom(16)
    chunk_size = 1024 * 1024
    flags = V2_FLAG_NONE
    key = derive_key(PASSWORD, salt)
    aesgcm = AESGCM(key)
    header_context = _v2_header_context(salt, file_id, chunk_size, flags)

    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
        data = b"legacy v2 content"
        info = tarfile.TarInfo(name=f"{folder_name}/legacy.txt")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

    vault_path = tmp_path / "legacy_v2_pbkdf2.adtn"
    with vault_path.open("wb") as f:
        f.write(header_context)
        name_bytes = folder_name.encode("utf-8")
        metadata = len(name_bytes).to_bytes(2, "big") + name_bytes
        _v2_write_record(f, aesgcm, header_context, RECORD_TYPE_METADATA, 0, metadata)
        _v2_write_record(f, aesgcm, header_context, RECORD_TYPE_DATA, 1, tar_buffer.getvalue())
        _v2_write_record(f, aesgcm, header_context, RECORD_TYPE_FINAL, 2, b"")

    return vault_path


def test_legacy_v2_pbkdf2_vaults_remain_readable(tmp_path):
    vault_path = _create_legacy_v2_pbkdf2_vault(tmp_path)

    status, restored_name = buka_brankas(str(vault_path), PASSWORD)

    assert status == VaultStatus.SUCCESS
    assert restored_name == "legacy_v2_pbkdf2"
    assert (tmp_path / restored_name / "legacy.txt").read_text(
        encoding="utf-8"
    ) == "legacy v2 content"


def test_keyslot_kdf_params_are_bound_to_wrap_aad(tmp_path):
    source = _make_source_folder(tmp_path)
    vault_path = tmp_path / "tamper-kdf.adtn"

    status, message = kunci_brankas([str(source)], str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS, message
    shutil.rmtree(source)

    data = bytearray(vault_path.read_bytes())
    # Flip one bit in the keyslot's Argon2id params. The params are bound into the
    # wrap AAD, so the master key can no longer be unwrapped.
    data[_V3_SLOT0_PARAMS_START + ARGON2ID_PARAMS_SIZE - 1] ^= 0x01
    vault_path.write_bytes(data)

    status, message = buka_brankas(str(vault_path), PASSWORD)
    assert status in {VaultStatus.WRONG_PASSWORD, VaultStatus.ERROR}
    assert not source.exists()


def test_oversized_argon2id_memory_cost_is_rejected_not_oom(tmp_path):
    """A crafted header asking for absurd Argon2id memory must be rejected at
    open time, never handed to the KDF (which would try to allocate it)."""
    source = _make_source_folder(tmp_path)
    vault_path = tmp_path / "argon2-oom.adtn"

    status, message = kunci_brankas([str(source)], str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS, message
    shutil.rmtree(source)

    # Keyslot params = iterations(4) + lanes(4) + memory_cost(4); overwrite
    # memory_cost with ~4 TiB worth of KiB so the open path must refuse it.
    data = bytearray(vault_path.read_bytes())
    memory_cost_offset = _V3_SLOT0_PARAMS_START + 8
    data[memory_cost_offset : memory_cost_offset + 4] = (0xFFFFFFFF).to_bytes(4, "big")
    vault_path.write_bytes(data)

    status, message = buka_brankas(str(vault_path), PASSWORD)
    assert status == VaultStatus.ERROR
    assert "safe maximum" in (message or "").lower()
    assert not source.exists()


def test_explicit_argon2id_key_derivation_dispatch_is_deterministic():
    salt = os.urandom(16)
    params = _encode_argon2id_params()
    decoded = {
        "iterations": int.from_bytes(params[0:4], "big"),
        "lanes": int.from_bytes(params[4:8], "big"),
        "memory_cost": int.from_bytes(params[8:12], "big"),
    }

    key1 = derive_key_for_kdf(PASSWORD, salt, KDF_ID_ARGON2ID, decoded)
    key2 = derive_key_for_kdf(PASSWORD, salt, KDF_ID_ARGON2ID, decoded)
    legacy_key = derive_key_for_kdf(PASSWORD, salt, KDF_ID_PBKDF2_SHA256, {})

    assert len(key1) == 32
    assert key1 == key2
    assert key1 != legacy_key
