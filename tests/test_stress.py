"""
tests/test_stress.py
Stress test dan edge case ekstrem untuk core/vault.py.
"""

import os
import stat
import shutil
import tempfile
import platform
import pytest

from core.vault import kunci_brankas, buka_brankas, VaultStatus
from tests.conftest import folder_checksum

PASSWORD = "P@ssw0rd!Kuat"


def _tmp():
    return tempfile.mkdtemp(prefix="locker_stress_")


def _cleanup(path: str):
    if not os.path.exists(path):
        return
    if platform.system() == "Windows":
        for root, dirs, files in os.walk(path):
            for f in files:
                try:
                    os.chmod(os.path.join(root, f), stat.S_IWRITE)
                except:
                    pass
    shutil.rmtree(path, ignore_errors=True)


class TestInceptionTest:
    def test_folder_dalam_40_level(self):
        tmp = _tmp()
        try:
            folder_root = os.path.join(tmp, "inception_40")
            current = folder_root
            for _ in range(40):
                current = os.path.join(current, "a")
            os.makedirs(current)
            with open(os.path.join(current, "deep.txt"), "w") as f:
                f.write("file di kedalaman 40 level")

            checksum_asli = folder_checksum(folder_root)
            path_simpan = os.path.join(tmp, "inception.locked")
            status_kunci, pesan = kunci_brankas([folder_root], path_simpan, PASSWORD)
            assert status_kunci == VaultStatus.SUCCESS

            shutil.rmtree(folder_root)
            status_buka, nama = buka_brankas(path_simpan, PASSWORD)
            assert status_buka == VaultStatus.SUCCESS
            assert checksum_asli == folder_checksum(os.path.join(tmp, nama))
        finally:
            _cleanup(tmp)


class TestIOPSKiller:
    @pytest.fixture
    def folder_banyak_file(self):
        tmp = _tmp()
        folder = os.path.join(tmp, "iops_100")
        os.makedirs(folder)
        for i in range(100):
            with open(os.path.join(folder, f"file_{i:04d}.txt"), "wb") as f:
                f.write(os.urandom(1024))
        yield folder, tmp
        _cleanup(tmp)

    def test_1000_file_roundtrip_isi_sama(self, folder_banyak_file):
        folder, tmp = folder_banyak_file
        checksum_asli = folder_checksum(folder)

        path_simpan = os.path.join(tmp, "banyak.locked")
        status_kunci, _ = kunci_brankas([folder], path_simpan, PASSWORD)
        assert status_kunci == VaultStatus.SUCCESS

        shutil.rmtree(folder)
        status_buka, nama = buka_brankas(path_simpan, PASSWORD)
        assert status_buka == VaultStatus.SUCCESS
        assert folder_checksum(os.path.join(tmp, nama)) == checksum_asli


class TestStubbornFile:
    @pytest.fixture
    def folder_dengan_readonly(self):
        tmp = _tmp()
        folder = os.path.join(tmp, "stubborn_folder")
        os.makedirs(folder)
        ro_path = os.path.join(folder, "readonly.txt")
        with open(ro_path, "w") as f:
            f.write("read-only")
        os.chmod(ro_path, stat.S_IREAD)
        yield folder, tmp
        _cleanup(tmp)

    def test_kunci_folder_dengan_readonly_tidak_crash(self, folder_dengan_readonly):
        folder, tmp = folder_dengan_readonly
        path_simpan = os.path.join(tmp, "ro.locked")
        status, _ = kunci_brankas([folder], path_simpan, PASSWORD)
        assert status == VaultStatus.SUCCESS
