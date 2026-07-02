"""
Regression guard: vault yang SUDAH terverifikasi tidak boleh ikut terhapus saat
fase hapus-asli gagal (mis. file sumber sedang dibuka aplikasi lain / dikunci AV
— skenario umum di Windows).

Sebelum fix, exception dari hapus_permanen jatuh ke handler generik kunci_brankas
yang menghapus file vault baru dan mengembalikan ERROR — dikombinasikan dengan
secure wipe parsial, itu jalur kehilangan data dua sisi.
"""

import pytest

import core.vault as vault_mod
from core.constants import DELETE_ORIGINAL_FAILED_MESSAGE
from core.vault import VaultStatus, buka_brankas, kunci_brankas

PASSWORD = "P@ssw0rd!Kuat123"


@pytest.fixture
def source_file(tmp_path):
    f = tmp_path / "rahasia.txt"
    f.write_text("isi sangat rahasia", encoding="utf-8")
    return f


def _fail_delete(*args, **kwargs):
    raise PermissionError("file sedang dipakai proses lain")


def test_delete_failure_keeps_verified_vault(tmp_path, source_file, monkeypatch):
    """hapus_permanen gagal → SUCCESS + pesan peringatan; vault & sumber tetap ada."""
    vault_path = tmp_path / "v.adtn"
    monkeypatch.setattr(vault_mod, "hapus_permanen", _fail_delete)

    status, msg = kunci_brankas([str(source_file)], str(vault_path), PASSWORD, hapus_asli=True)

    assert status == VaultStatus.SUCCESS
    assert msg == DELETE_ORIGINAL_FAILED_MESSAGE
    assert vault_path.exists(), "Vault terverifikasi tidak boleh ikut terhapus"
    assert source_file.exists(), "Sumber yang gagal dihapus harus tetap utuh"


def test_delete_failure_vault_still_opens(tmp_path, source_file, monkeypatch):
    """Vault hasil skenario gagal-hapus harus tetap valid & bisa dibuka."""
    vault_path = tmp_path / "v.adtn"
    monkeypatch.setattr(vault_mod, "hapus_permanen", _fail_delete)
    status, _ = kunci_brankas([str(source_file)], str(vault_path), PASSWORD, hapus_asli=True)
    assert status == VaultStatus.SUCCESS
    monkeypatch.undo()

    # Sumber masih ada → buka akan menimpa; pakai force lewat jalur normal:
    # hapus dulu sumber agar ekstraksi mendarat bersih.
    source_file.unlink()
    status, restored_name = buka_brankas(str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS
    restored = tmp_path / restored_name
    assert restored.read_text(encoding="utf-8") == "isi sangat rahasia"


def test_partial_delete_failure_still_deletes_other_paths(tmp_path, monkeypatch):
    """Kegagalan hapus satu path tidak menghentikan penghapusan path lain."""
    f1 = tmp_path / "a.txt"
    f1.write_text("alpha", encoding="utf-8")
    f2 = tmp_path / "b.txt"
    f2.write_text("beta", encoding="utf-8")
    vault_path = tmp_path / "multi.adtn"

    real_hapus = vault_mod.hapus_permanen

    def _fail_only_first(path, *args, **kwargs):
        if path.name == "a.txt":
            raise PermissionError("a.txt sedang dipakai")
        return real_hapus(path, *args, **kwargs)

    monkeypatch.setattr(vault_mod, "hapus_permanen", _fail_only_first)

    status, msg = kunci_brankas([str(f1), str(f2)], str(vault_path), PASSWORD, hapus_asli=True)

    assert status == VaultStatus.SUCCESS
    assert msg == DELETE_ORIGINAL_FAILED_MESSAGE
    assert vault_path.exists()
    assert f1.exists(), "Path yang gagal dihapus tetap ada"
    assert not f2.exists(), "Path lain tetap dihapus walau path pertama gagal"
