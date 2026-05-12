"""
tests/test_stress.py
Stress test dan edge case ekstrem untuk core/vault.py.

Tiga skenario:
  1. Inception Test  — folder sangat dalam (Windows MAX_PATH limit)
  2. IOPS Killer     — ribuan file kecil
  3. Stubborn File   — file read-only / terkunci di dalam folder

Jalankan:
    pytest tests/test_stress.py -v -s

    # Jalankan satu test saja:
    pytest tests/test_stress.py -v -k "inception"
    pytest tests/test_stress.py -v -k "iops"
    pytest tests/test_stress.py -v -k "stubborn"

CATATAN: Test ini sengaja dibiarkan EXPOSE bug nyata di kode.
Kalau ada yang FAIL, itu artinya ada yang perlu difix di vault.py.
"""

import os
import sys
import stat
import shutil
import tempfile
import platform
import pytest

from core.vault import kunci_brankas, buka_brankas, secure_delete
from tests.conftest import folder_checksum

PASSWORD = "P@ssw0rd!Kuat"

# ── Helpers ───────────────────────────────────────────────────────────────────


def _tmp():
    """Buat temp dir bersih, return path-nya."""
    return tempfile.mkdtemp(prefix="locker_stress_")


def _cleanup(path: str):
    """Hapus temp dir dengan paksa, abaikan read-only (untuk cleanup setelah test)."""
    if not os.path.exists(path):
        return
    if platform.system() == "Windows":
        # Di Windows, read-only file harus di-unlock dulu sebelum bisa dihapus
        for root, dirs, files in os.walk(path):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    os.chmod(fp, stat.S_IWRITE)
                except Exception:
                    pass
    shutil.rmtree(path, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
# 1. THE INCEPTION TEST — Folder Sangat Dalam
# ─────────────────────────────────────────────────────────────────────────────


class TestInceptionTest:
    """
    Windows MAX_PATH = 260 karakter.
    Kalau total path (base_dir + nama folder + subfolder chain) > 260 char,
    os.walk, tarfile.add(), dan open() akan throw FileNotFoundError atau
    OSError: [Errno 2] di Windows tanpa Long Path support.

    Dua sub-test:
    a) Mendekati batas (240 char) — harus BERHASIL
    b) Melampaui batas (300+ char) — dokumentasi behavior (crash atau handled)
    """

    def test_folder_dalam_40_level(self):
        """
        Folder bersarang 40 level dengan nama pendek ('a').
        Total path sekitar 120 karakter — harus aman di semua OS.
        """
        tmp = _tmp()
        try:
            # Bangun struktur folder: tmp/a/a/a/.../a (40 level)
            folder_root = os.path.join(tmp, "inception_40")
            current = folder_root
            for _ in range(40):
                current = os.path.join(current, "a")
            os.makedirs(current)

            # Taruh file di level terdalam
            with open(os.path.join(current, "deep.txt"), "w") as f:
                f.write("file di kedalaman 40 level")

            checksum_asli = folder_checksum(folder_root)

            sukses, pesan = kunci_brankas(folder_root, PASSWORD)
            assert sukses, f"Gagal kunci folder 40 level: {pesan}"

            shutil.rmtree(folder_root)

            locked_files = [
                os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith(".locked")
            ]
            assert locked_files, "Tidak ada file .locked yang terbentuk"

            status, nama = buka_brankas(locked_files[0], PASSWORD)
            assert (
                status == "SUCCESS"
            ), f"Gagal buka folder 40 level: status={status}, msg={nama}"

            restored = os.path.join(tmp, nama)
            checksum_buka = folder_checksum(restored)
            assert (
                checksum_asli == checksum_buka
            ), "Isi folder tidak sama setelah 40 level!"

        finally:
            _cleanup(tmp)

    def test_folder_mendekati_max_path(self):
        """
        Folder dengan total path mendekati 240 karakter (tepat di bawah batas 260).
        Nama folder dan subfolder dibuat panjang secara sengaja.
        Harus BERHASIL — ini masih dalam batas aman.
        """
        tmp = _tmp()
        try:
            # Hitung sisa ruang untuk nama folder
            # Format: tmp_path \ folder_name \ sub \ file.txt
            sisa = 240 - len(tmp) - 20  # 20 untuk "\sub\file.txt"
            sisa = max(10, min(sisa, 80))  # clamp supaya tidak negatif
            nama_panjang = "F" * sisa

            folder_root = os.path.join(tmp, nama_panjang)
            sub = os.path.join(folder_root, "sub")
            os.makedirs(sub)
            with open(os.path.join(sub, "file.txt"), "w") as f:
                f.write("test mendekati MAX_PATH")

            total_path_len = len(os.path.join(sub, "file.txt"))

            sukses, pesan = kunci_brankas(folder_root, PASSWORD)
            assert sukses, (
                f"Gagal kunci folder ~{total_path_len} char path: {pesan}\n"
                f"Base dir: {tmp}\n"
                f"Folder: {folder_root}"
            )

        finally:
            _cleanup(tmp)

    @pytest.mark.skipif(
        platform.system() != "Windows", reason="MAX_PATH hanya relevan di Windows"
    )
    def test_folder_melampaui_max_path_windows(self):
        """
        Folder dengan path > 260 karakter di Windows.

        EXPECTED BEHAVIOR:
        - Kalau Windows Long Path DISABLED (default): kunci_brankas() harus
          return (False, <pesan error>) — TIDAK boleh crash dengan exception
          yang tidak tertangani.
        - Kalau Windows Long Path ENABLED (Group Policy/Registry):
          kunci_brankas() harus BERHASIL.

        Test ini lulus di kedua kondisi — yang penting tidak crash.
        """
        tmp = _tmp()
        try:
            # Buat path yang pasti > 260 char
            # Nama folder 200 karakter + path tmp yang biasanya 40-60 char = > 260
            nama_sangat_panjang = "X" * 200
            folder_root = os.path.join(tmp, nama_sangat_panjang)

            try:
                sub = os.path.join(folder_root, "sub")
                os.makedirs(sub)
                with open(os.path.join(sub, "file.txt"), "w") as f:
                    f.write("test over MAX_PATH")
            except OSError:
                pytest.skip(
                    "OS tidak bisa membuat folder dengan path > 260 char — "
                    "Long Path disabled, test diskip"
                )

            # Kalau berhasil dibuat, coba kunci — hasilnya boleh sukses atau gagal,
            # tapi TIDAK boleh raise exception yang tidak tertangani
            try:
                sukses, pesan = kunci_brankas(folder_root, PASSWORD)
                # Tidak perlu assert sukses — boleh gagal
                # Yang penting: return (bool, str), bukan crash
                assert isinstance(sukses, bool), "Return type harus bool"
                assert isinstance(pesan, str), "Pesan harus string"
            except Exception as e:
                pytest.fail(
                    f"kunci_brankas() CRASH dengan unhandled exception: {type(e).__name__}: {e}\n"
                    f"Seharusnya return (False, pesan_error) bukan raise exception."
                )

        finally:
            _cleanup(tmp)


# ─────────────────────────────────────────────────────────────────────────────
# 2. THE IOPS KILLER — Ribuan File Kecil
# ─────────────────────────────────────────────────────────────────────────────


class TestIOPSKiller:
    """
    Controller SSD dan loop direktori diuji dengan volume file tinggi.
    Bug yang sering muncul: progress bar stuck, os.walk memory hog,
    atau tarfile timeout pada ribuan file kecil.
    """

    @pytest.fixture
    def folder_banyak_file(self):
        """1.000 file @ 1 KB = total ~1 MB."""
        tmp = _tmp()
        folder = os.path.join(tmp, "iops_1000")
        os.makedirs(folder)
        for i in range(1_000):
            with open(os.path.join(folder, f"file_{i:04d}.txt"), "wb") as f:
                f.write(os.urandom(1024))  # 1 KB per file
        yield folder, tmp
        _cleanup(tmp)

    @pytest.fixture
    def folder_sangat_banyak_file(self):
        """5.000 file @ 256 bytes = total ~1.25 MB."""
        tmp = _tmp()
        folder = os.path.join(tmp, "iops_5000")
        os.makedirs(folder)
        for i in range(5_000):
            with open(os.path.join(folder, f"f_{i:05d}.bin"), "wb") as f:
                f.write(os.urandom(256))
        yield folder, tmp
        _cleanup(tmp)

    def test_1000_file_kunci_berhasil(self, folder_banyak_file):
        """1.000 file kecil harus bisa dikunci tanpa error."""
        folder, tmp = folder_banyak_file
        sukses, pesan = kunci_brankas(folder, PASSWORD)
        assert sukses, f"Gagal kunci 1.000 file: {pesan}"

    def test_1000_file_roundtrip_isi_sama(self, folder_banyak_file):
        """1.000 file kecil: kunci → buka → semua file harus identik."""
        folder, tmp = folder_banyak_file
        checksum_asli = folder_checksum(folder)

        locked_before = set(os.listdir(tmp))
        sukses, _ = kunci_brankas(folder, PASSWORD)
        assert sukses

        shutil.rmtree(folder)

        locked_file = [
            os.path.join(tmp, f)
            for f in os.listdir(tmp)
            if f.endswith(".locked") and f not in locked_before
        ]
        assert locked_file

        status, nama = buka_brankas(locked_file[0], PASSWORD)
        assert status == "SUCCESS", f"Gagal buka 1.000 file: {nama}"

        restored = os.path.join(tmp, nama)
        assert (
            folder_checksum(restored) == checksum_asli
        ), "Ada file yang corrupt atau hilang setelah buka 1.000 file!"

    def test_1000_file_jumlah_file_terjaga(self, folder_banyak_file):
        """Jumlah file setelah dekripsi harus sama persis — tidak ada yang hilang."""
        folder, tmp = folder_banyak_file

        jumlah_asli = sum(len(files) for _, _, files in os.walk(folder))

        locked_before = set(os.listdir(tmp))
        kunci_brankas(folder, PASSWORD)
        shutil.rmtree(folder)

        locked_file = [
            os.path.join(tmp, f)
            for f in os.listdir(tmp)
            if f.endswith(".locked") and f not in locked_before
        ]
        buka_brankas(locked_file[0], PASSWORD)

        restored = os.path.join(tmp, os.path.basename(folder))
        jumlah_buka = sum(len(files) for _, _, files in os.walk(restored))

        assert (
            jumlah_asli == jumlah_buka
        ), f"Jumlah file berbeda! Asli: {jumlah_asli}, Setelah buka: {jumlah_buka}"

    def test_5000_file_kunci_tidak_crash(self, folder_sangat_banyak_file):
        """
        5.000 file kecil — stress test untuk os.walk dan tarfile.
        Minimal harus tidak crash. Sukses lebih bagus.
        """
        folder, tmp = folder_sangat_banyak_file
        try:
            sukses, pesan = kunci_brankas(folder, PASSWORD)
            # Boleh sukses atau gagal — yang penting tidak raise exception
            assert isinstance(sukses, bool)
        except Exception as e:
            pytest.fail(
                f"kunci_brankas() CRASH pada 5.000 file: {type(e).__name__}: {e}"
            )

    def test_progress_tidak_freeze_pada_banyak_file(self, folder_banyak_file):
        """
        Dengan 1.000 file, progress callback tidak boleh terlalu jarang dipanggil
        (indikasi throttle terlalu ketat yang bikin progress bar visual freeze).
        Minimal harus dipanggil > 3 kali untuk file 1MB.
        """
        folder, tmp = folder_banyak_file
        progress_log = []

        kunci_brankas(folder, PASSWORD, progress_cb=lambda v: progress_log.append(v))

        assert len(progress_log) > 3, (
            f"Progress hanya dipanggil {len(progress_log)} kali untuk 1.000 file — "
            f"progress bar akan terasa frozen di UI"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. THE STUBBORN FILE — File Read-Only / Terkunci
# ─────────────────────────────────────────────────────────────────────────────


class TestStubbornFile:
    """
    File dengan permission read-only atau terkunci oleh proses lain.
    secure_delete() harus gracefully skip — tidak crash.
    kunci_brankas() harus tetap berhasil mengenkripsi (read saja, tidak perlu write).
    """

    @pytest.fixture
    def folder_dengan_readonly(self):
        """
        Folder dengan campuran file normal dan read-only.
        """
        tmp = _tmp()
        folder = os.path.join(tmp, "stubborn_folder")
        os.makedirs(folder)

        # File normal
        with open(os.path.join(folder, "normal.txt"), "w") as f:
            f.write("file normal, bisa dihapus")

        # File read-only
        ro_path = os.path.join(folder, "readonly.txt")
        with open(ro_path, "w") as f:
            f.write("file read-only, tidak bisa dihapus langsung")
        os.chmod(ro_path, stat.S_IREAD)  # Cabut write permission

        # Sub-folder dengan file read-only
        sub = os.path.join(folder, "sub_readonly")
        os.makedirs(sub)
        ro_sub = os.path.join(sub, "protected.bin")
        with open(ro_sub, "wb") as f:
            f.write(os.urandom(512))
        os.chmod(ro_sub, stat.S_IREAD)

        yield folder, tmp
        _cleanup(tmp)

    def test_kunci_folder_dengan_readonly_tidak_crash(self, folder_dengan_readonly):
        """
        kunci_brankas() hanya MEMBACA file — read-only tidak harusnya jadi masalah.
        Harus berhasil mengenkripsi termasuk file read-only di dalamnya.
        """
        folder, tmp = folder_dengan_readonly
        sukses, pesan = kunci_brankas(folder, PASSWORD)
        assert (
            sukses
        ), f"kunci_brankas() gagal pada folder dengan file read-only: {pesan}"

    def test_kunci_readonly_isi_terjaga(self, folder_dengan_readonly):
        """
        Isi file read-only harus ter-enkripsi dan bisa dikembalikan dengan benar.
        """
        folder, tmp = folder_dengan_readonly
        checksum_asli = folder_checksum(folder)

        locked_before = set(os.listdir(tmp))
        sukses, _ = kunci_brankas(folder, PASSWORD)
        assert sukses

        _cleanup(folder)

        locked_file = [
            os.path.join(tmp, f)
            for f in os.listdir(tmp)
            if f.endswith(".locked") and f not in locked_before
        ]
        assert locked_file

        status, nama = buka_brankas(locked_file[0], PASSWORD)
        assert status == "SUCCESS"

        restored = os.path.join(tmp, nama)
        checksum_buka = folder_checksum(restored)

        # Bandingkan isi (ukuran + hash) — permission tidak dibandingkan
        # karena tar tidak selalu preserve permission Windows
        assert (
            checksum_asli == checksum_buka
        ), "Isi file read-only berubah setelah enkripsi-dekripsi!"

    def test_secure_delete_readonly_tidak_crash(self, folder_dengan_readonly):
        """
        secure_delete() pada folder yang berisi file read-only tidak boleh crash.
        Boleh skip file yang tidak bisa dihapus — yang penting tidak raise exception.
        """
        folder, tmp = folder_dengan_readonly
        try:
            secure_delete(folder)
            # Tidak perlu assert folder terhapus — yang penting tidak crash
        except Exception as e:
            pytest.fail(
                f"secure_delete() CRASH pada file read-only: {type(e).__name__}: {e}"
            )

    def test_secure_delete_hapus_asli_readonly_tidak_crash(
        self, folder_dengan_readonly
    ):
        """
        hapus_asli=True dengan file read-only di dalamnya tidak boleh crash.
        Program boleh meninggalkan file read-only yang tidak bisa dihapus,
        tapi proses enkripsi tetap harus berhasil.
        """
        folder, tmp = folder_dengan_readonly
        try:
            sukses, pesan = kunci_brankas(folder, PASSWORD, hapus_asli=True)
            # Enkripsi harus sukses meskipun hapus mungkin partial
            assert sukses, f"kunci_brankas() gagal: {pesan}"
        except Exception as e:
            pytest.fail(
                f"kunci_brankas(hapus_asli=True) CRASH pada file read-only: "
                f"{type(e).__name__}: {e}"
            )

    @pytest.mark.skipif(
        platform.system() != "Windows",
        reason="File locking dengan sharing violation spesifik Windows",
    )
    def test_kunci_file_yang_sedang_dibuka_windows(self):
        """
        Windows: file yang sedang dibuka oleh proses lain tidak bisa dibaca
        jika dibuka dengan exclusive lock. Test ini verifikasi behavior-nya.
        """
        import msvcrt

        tmp = _tmp()
        folder = os.path.join(tmp, "locked_folder")
        os.makedirs(folder)

        locked_file = os.path.join(folder, "sedang_dibuka.txt")
        with open(locked_file, "w") as f:
            f.write("file ini sedang terbuka")

        # Buka file dengan exclusive lock
        fh = open(locked_file, "r")
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)

            try:
                sukses, pesan = kunci_brankas(folder, PASSWORD)
                assert isinstance(sukses, bool), "Harus return bool, tidak crash"
            except Exception as e:
                pytest.fail(
                    f"kunci_brankas() CRASH pada file yang terkunci: "
                    f"{type(e).__name__}: {e}"
                )
        finally:
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
            fh.close()
            _cleanup(tmp)
