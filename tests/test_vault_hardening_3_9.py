"""
Regression tests for security hardening items 3-9.
"""

from pathlib import Path

import pytest

from core.constants import DISK_OVERHEAD_BYTES, MAGIC_BYTES
from core.vault import (
    VaultStatus,
    _hitung_kebutuhan_disk_buka,
    _parse_virtual_folder_name,
    _validate_virtual_folder_name,
    kunci_brankas,
)

PASSWORD = "P@ssw0rd!Kuat123"


def _encoded_virtual_name(name: str) -> bytes:
    raw = name.encode("utf-8")
    return len(raw).to_bytes(2, byteorder="big") + raw + b"tar-bytes-after-name"


@pytest.mark.parametrize(
    "name",
    [
        "",
        ".",
        "..",
        "folder/sub",
        r"folder\\sub",
        "CON",
        "CON.txt",
        "NUL",
        "COM1",
        "LPT9.txt",
        "nama.",
        "nama ",
        "bad\x01name",
        "._dec_deadbeef",
        "C:folder",
        "folder:name",
        "folder?name",
    ],
)
def test_virtual_folder_name_rejects_unsafe_names(name):
    with pytest.raises(ValueError):
        _validate_virtual_folder_name(name)


def test_parse_virtual_folder_name_validates_name_before_path_use():
    with pytest.raises(ValueError):
        _parse_virtual_folder_name(_encoded_virtual_name("../escape"))


def test_parse_virtual_folder_name_accepts_safe_name():
    name, offset = _parse_virtual_folder_name(_encoded_virtual_name("Rahasia_2026"))

    assert name == "Rahasia_2026"
    assert offset == 2 + len("Rahasia_2026".encode("utf-8"))


def test_decrypt_disk_space_estimate_accounts_for_temp_tar_and_extracted_payload():
    cipher_len = 123_456

    assert _hitung_kebutuhan_disk_buka(cipher_len) == (cipher_len * 2) + DISK_OVERHEAD_BYTES


def test_existing_backup_file_is_not_overwritten_when_replacing_target(tmp_path):
    source = tmp_path / "rahasia"
    source.mkdir()
    (source / "dokumen.txt").write_text("isi rahasia", encoding="utf-8")

    target = tmp_path / "rahasia.adtn"
    target.write_bytes(b"vault lama")

    legacy_backup = target.with_suffix(".adtn.bak")
    legacy_backup.write_text("backup lama yang harus tetap ada", encoding="utf-8")

    status, message = kunci_brankas([str(source)], str(target), PASSWORD)

    assert status == VaultStatus.SUCCESS, message
    assert target.read_bytes().startswith(MAGIC_BYTES)
    assert legacy_backup.read_text(encoding="utf-8") == "backup lama yang harus tetap ada"
    assert not list(tmp_path.glob(f"{target.name}.bak-*")), "Backup unik sementara harus dibersihkan setelah sukses"
