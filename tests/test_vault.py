"""
tests/test_vault.py
Unit + Integration test untuk core/vault.py dengan refactor VaultStatus (Enum).
"""

import os
import shutil
import pytest

from core.vault import kunci_brankas, buka_brankas, VaultStatus
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
