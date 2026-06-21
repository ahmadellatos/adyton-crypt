"""
Regression tests for Argon2id keyslot derivation and tamper-resistance.
"""

import os
import shutil

import pytest

from core.constants import (
    ARGON2ID_PARAMS_SIZE,
    CORE_HEADER_SIZE,
    FLAG_NONE,
    KDF_ID_ARGON2ID,
    KDF_LEVEL_INTERACTIVE,
    KDF_LEVEL_PARANOID,
    MAGIC_BYTES,
    SLOT_TYPE_PASSWORD,
    VERSION,
    kdf_params_for_level,
)

# Offset awal Argon2id params di slot 0 untuk vault default (tanpa hint, satu slot
# password): core header + slot_count(1) + slot_type(1) + kdf_id(1) + params_len(2).
_SLOT0_PARAMS_START = CORE_HEADER_SIZE + 1 + 1 + 1 + 2

from core.crypto import derive_key_for_kdf
from core.vault import (
    VaultStatus,
    _encode_argon2id_params,
    buka_brankas,
    change_password,
    kunci_brankas,
)

PASSWORD = "P@ssw0rd!Kuat123"


def _make_source_folder(tmp_path):
    source = tmp_path / "argon2_source"
    source.mkdir()
    (source / "secret.txt").write_text("secret content", encoding="utf-8")
    return source


def test_new_vaults_use_envelope_with_argon2id_keyslot(tmp_path):
    source = _make_source_folder(tmp_path)
    vault_path = tmp_path / "argon2.adtn"

    status, message = kunci_brankas([str(source)], str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS, message

    with vault_path.open("rb") as f:
        assert f.read(4) == MAGIC_BYTES
        assert f.read(1) == VERSION
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
        assert flags == FLAG_NONE  # no hint by default
        assert slot_count == 1  # password-only by default (no recovery key)
        assert slot_type == SLOT_TYPE_PASSWORD
        assert kdf_id == KDF_ID_ARGON2ID
        assert params_len == ARGON2ID_PARAMS_SIZE
        assert len(params) == ARGON2ID_PARAMS_SIZE


def test_argon2id_roundtrip_and_wrong_password(tmp_path):
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


def test_keyslot_kdf_params_are_bound_to_wrap_aad(tmp_path):
    source = _make_source_folder(tmp_path)
    vault_path = tmp_path / "tamper-kdf.adtn"

    status, message = kunci_brankas([str(source)], str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS, message
    shutil.rmtree(source)

    data = bytearray(vault_path.read_bytes())
    # Flip one bit in the keyslot's Argon2id params. The params are bound into the
    # wrap AAD, so the master key can no longer be unwrapped.
    data[_SLOT0_PARAMS_START + ARGON2ID_PARAMS_SIZE - 1] ^= 0x01
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
    memory_cost_offset = _SLOT0_PARAMS_START + 8
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

    assert len(key1) == 32
    assert key1 == key2

    # An unknown KDF id must be rejected, never silently misinterpreted.
    with pytest.raises(ValueError):
        derive_key_for_kdf(PASSWORD, salt, 99, {})


# ── KDF level selection (Settings) ──────────────────────────────────────────────


def _read_slot0_params(vault_path) -> dict[str, int]:
    data = vault_path.read_bytes()
    s = _SLOT0_PARAMS_START
    return {
        "iterations": int.from_bytes(data[s : s + 4], "big"),
        "lanes": int.from_bytes(data[s + 4 : s + 8], "big"),
        "memory_cost": int.from_bytes(data[s + 8 : s + 12], "big"),
    }


def test_kdf_level_paranoid_is_stored_and_opens(tmp_path):
    source = _make_source_folder(tmp_path)
    vault_path = tmp_path / "paranoid.adtn"
    params = kdf_params_for_level(KDF_LEVEL_PARANOID)

    status, message = kunci_brankas([str(source)], str(vault_path), PASSWORD, kdf_params=params)
    assert status == VaultStatus.SUCCESS, message
    assert _read_slot0_params(vault_path) == params

    shutil.rmtree(source)
    status, _ = buka_brankas(str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS


def test_kdf_level_interactive_uses_lighter_params(tmp_path):
    source = _make_source_folder(tmp_path)
    vault_path = tmp_path / "interactive.adtn"
    params = kdf_params_for_level(KDF_LEVEL_INTERACTIVE)

    status, _ = kunci_brankas([str(source)], str(vault_path), PASSWORD, kdf_params=params)
    assert status == VaultStatus.SUCCESS
    stored = _read_slot0_params(vault_path)
    assert stored["iterations"] == 2
    assert stored["memory_cost"] == 32 * 1024


def test_change_password_preserves_kdf_level(tmp_path):
    source = _make_source_folder(tmp_path)
    vault_path = tmp_path / "lvl.adtn"
    params = kdf_params_for_level(KDF_LEVEL_PARANOID)
    kunci_brankas([str(source)], str(vault_path), PASSWORD, kdf_params=params)
    shutil.rmtree(source)

    before = _read_slot0_params(vault_path)
    status, _ = change_password(str(vault_path), PASSWORD, "An0therStr0ng!Pass")
    assert status == VaultStatus.SUCCESS
    after = _read_slot0_params(vault_path)
    assert after == before == params
