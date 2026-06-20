"""
Regression tests for the chunked AEAD vault format (envelope).
"""

import shutil

from core.constants import MAGIC_BYTES, VERSION
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


def test_new_vaults_use_envelope_and_roundtrip(tmp_path):
    source = _make_source_folder(tmp_path)
    vault_path = tmp_path / "rahasia_v2.adtn"

    status, message = kunci_brankas([str(source)], str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS, message

    with vault_path.open("rb") as f:
        assert f.read(4) == MAGIC_BYTES
        assert f.read(1) == VERSION

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


def test_truncated_vault_is_rejected_without_temp_leak(tmp_path):
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


def test_foreign_version_byte_is_rejected(tmp_path):
    """File dengan byte versi asing harus ditolak, bukan dianggap salah password."""
    source = _make_source_folder(tmp_path)
    vault_path = tmp_path / "foreign.adtn"

    status, message = kunci_brankas([str(source)], str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS, message

    data = bytearray(vault_path.read_bytes())
    data[4] = 0x02  # ubah byte versi ke nilai yang tidak dikenali
    vault_path.write_bytes(data)

    status, _ = buka_brankas(str(vault_path), PASSWORD)
    assert status == VaultStatus.ERROR
