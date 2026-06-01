"""
Regression tests for output-path safety when locking a vault.
"""

from core.vault import VaultStatus, kunci_brankas


PASSWORD = "P@ssw0rd!Kuat123"


def test_kunci_rejects_vault_saved_inside_source_folder(tmp_path):
    source = tmp_path / "rahasia"
    source.mkdir()
    (source / "dokumen.txt").write_text("sangat rahasia", encoding="utf-8")

    target = source / "rahasia.adtn"

    status, message = kunci_brankas(
        [str(source)],
        str(target),
        PASSWORD,
        hapus_asli=True,
    )

    assert status == VaultStatus.ERROR
    assert "tidak boleh" in message
    assert source.exists(), "Folder sumber harus tetap ada jika target tidak aman"
    assert not target.exists(), "Vault tidak boleh dibuat di dalam folder sumber"


def test_kunci_rejects_vault_same_path_as_source_file(tmp_path):
    source = tmp_path / "data.adtn"
    source.write_text("file asli", encoding="utf-8")

    status, message = kunci_brankas(
        [str(source)],
        str(source),
        PASSWORD,
        hapus_asli=True,
    )

    assert status == VaultStatus.ERROR
    assert "tidak boleh" in message
    assert source.read_text(encoding="utf-8") == "file asli"


def test_kunci_allows_vault_next_to_source_folder(tmp_path):
    source = tmp_path / "rahasia"
    source.mkdir()
    (source / "dokumen.txt").write_text("sangat rahasia", encoding="utf-8")

    target = tmp_path / "rahasia.adtn"

    status, message = kunci_brankas([str(source)], str(target), PASSWORD)

    assert status == VaultStatus.SUCCESS, message
    assert target.exists()
    assert source.exists()
