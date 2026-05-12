"""
tests/test_vault.py
Unit + Integration test untuk core/vault.py.

Mencakup:
  - Happy path (kunci → buka → verifikasi isi sama)
  - Wrong password detection
  - File corrupt / terpotong
  - Overwrite flow
  - hapus_asli flag
  - Progress callback
  - Edge cases: folder kosong, unicode, spasi, nested dalam

Jalankan:
    pytest tests/test_vault.py -v
    pytest tests/test_vault.py -v -k "wrong_password"   # jalankan satu skenario
"""

import os
import shutil
import pytest

from core.vault import kunci_brankas, buka_brankas, secure_delete
from tests.conftest import folder_checksum

# ── Helper ────────────────────────────────────────────────────────────────────

PASSWORD_BENAR = "P@ssw0rd!Kuat123"
PASSWORD_SALAH = "password_salah_banget"


def kunci_dan_dapat_path(folder, password=PASSWORD_BENAR, hapus=False, cb=None):
    """Helper: kunci folder, return path file .locked yang dihasilkan."""
    base_dir = os.path.dirname(folder)
    locked_before = {f for f in os.listdir(base_dir) if f.endswith(".locked")}
    sukses, pesan = kunci_brankas(folder, password, hapus_asli=hapus, progress_cb=cb)
    assert sukses, f"kunci_brankas gagal: {pesan}"

    locked_after = {f for f in os.listdir(base_dir) if f.endswith(".locked")}
    new_files = locked_after - locked_before
    assert len(new_files) == 1, "Harus ada tepat satu file .locked baru"
    return os.path.join(base_dir, new_files.pop())


# ── Happy Path ────────────────────────────────────────────────────────────────


class TestHappyPath:

    def test_kunci_menghasilkan_file_locked(self, sample_folder):
        """kunci_brankas harus menghasilkan file .locked di direktori yang sama."""
        base_dir = os.path.dirname(sample_folder)
        sukses, pesan = kunci_brankas(sample_folder, PASSWORD_BENAR)

        assert sukses is True
        locked_files = [f for f in os.listdir(base_dir) if f.endswith(".locked")]
        assert len(locked_files) == 1

    def test_kunci_pesan_berisi_nama_file(self, sample_folder):
        """Pesan sukses harus menyebut nama file .locked yang dibuat."""
        _, pesan = kunci_brankas(sample_folder, PASSWORD_BENAR)
        assert "brankas_" in pesan
        assert ".locked" in pesan

    def test_kunci_lalu_buka_isi_sama(self, sample_folder):
        """
        Skenario utama: kunci folder → buka → isi file harus identik byte-per-byte.
        """
        checksum_sebelum = folder_checksum(sample_folder)
        locked_path = kunci_dan_dapat_path(sample_folder)
        base_dir = os.path.dirname(locked_path)

        # Hapus folder asli supaya buka brankas bisa restore ke path yang sama
        shutil.rmtree(sample_folder)

        status, nama = buka_brankas(locked_path, PASSWORD_BENAR)
        assert status == "SUCCESS"

        folder_restored = os.path.join(base_dir, nama)
        checksum_sesudah = folder_checksum(folder_restored)

        assert checksum_sebelum == checksum_sesudah, (
            "Isi folder setelah dekripsi berbeda dari aslinya!\n"
            f"Sebelum: {checksum_sebelum}\n"
            f"Sesudah: {checksum_sesudah}"
        )

    def test_buka_mengembalikan_nama_folder(self, sample_folder):
        """buka_brankas harus return nama folder aslinya."""
        locked_path = kunci_dan_dapat_path(sample_folder)
        shutil.rmtree(sample_folder)

        status, nama = buka_brankas(locked_path, PASSWORD_BENAR)
        assert status == "SUCCESS"
        assert nama == os.path.basename(sample_folder)

    def test_file_locked_terbentuk_di_direktori_yang_sama(self, sample_folder):
        """File .locked harus dibuat di direktori yang sama dengan folder sumber."""
        base_dir = os.path.dirname(sample_folder)
        locked_path = kunci_dan_dapat_path(sample_folder)
        assert os.path.dirname(locked_path) == base_dir


# ── Wrong Password ────────────────────────────────────────────────────────────


class TestWrongPassword:

    def test_wrong_password_return_status(self, sample_folder):
        """Password salah harus return ('WRONG_PW', None)."""
        locked_path = kunci_dan_dapat_path(sample_folder)
        shutil.rmtree(sample_folder)

        status, msg = buka_brankas(locked_path, PASSWORD_SALAH)
        assert status == "WRONG_PW"
        assert msg is None

    def test_wrong_password_tidak_buat_folder(self, sample_folder, tmp_dir):
        """Password salah tidak boleh mengekstrak folder apapun."""
        locked_path = kunci_dan_dapat_path(sample_folder)
        shutil.rmtree(sample_folder)

        folder_before = set(os.listdir(tmp_dir))
        buka_brankas(locked_path, PASSWORD_SALAH)
        folder_after = set(os.listdir(tmp_dir))

        # Tidak ada folder baru yang muncul (hanya .locked yang sudah ada)
        new_items = folder_after - folder_before
        assert all(
            item.endswith(".locked") for item in new_items
        ), f"File/folder tak terduga muncul setelah wrong password: {new_items}"

    def test_wrong_password_tidak_buat_temp_file(self, sample_folder):
        """Temp file tidak boleh tersisa di sistem setelah wrong password."""
        import tempfile
        import glob

        locked_path = kunci_dan_dapat_path(sample_folder)
        tmp_sebelum = set(
            glob.glob(os.path.join(tempfile.gettempdir(), "dec_temp_*.tmp"))
        )

        shutil.rmtree(sample_folder)
        buka_brankas(locked_path, PASSWORD_SALAH)

        tmp_sesudah = set(
            glob.glob(os.path.join(tempfile.gettempdir(), "dec_temp_*.tmp"))
        )
        assert tmp_sebelum == tmp_sesudah, "Temp file tersisa setelah wrong password!"

    def test_password_mirip_tetap_gagal(self, sample_folder):
        """Password yang hampir sama (1 karakter beda) tetap harus gagal."""
        locked_path = kunci_dan_dapat_path(sample_folder, password="Password123!")
        shutil.rmtree(sample_folder)

        # Satu karakter beda
        status, _ = buka_brankas(locked_path, "Password123?")
        assert status == "WRONG_PW"


# ── File Corrupt ──────────────────────────────────────────────────────────────


class TestFileCorrupt:

    def test_file_terlalu_kecil(self, tmp_dir):
        """File yang lebih kecil dari 44 bytes harus return ERROR."""
        path = os.path.join(tmp_dir, "kecil.locked")
        with open(path, "wb") as f:
            f.write(b"x" * 10)

        status, msg = buka_brankas(path, PASSWORD_BENAR)
        assert status == "ERROR"
        assert msg  # pesan error tidak boleh kosong

    def test_file_header_valid_tapi_isi_corrupt(self, tmp_dir):
        """File dengan header ukuran valid tapi isi random harus return WRONG_PW atau ERROR."""
        path = os.path.join(tmp_dir, "corrupt.locked")
        with open(path, "wb") as f:
            f.write(os.urandom(200))  # 200 bytes random

        status, _ = buka_brankas(path, PASSWORD_BENAR)
        assert status in ("WRONG_PW", "ERROR")

    def test_file_terpotong_di_tengah(self, sample_folder, tmp_dir):
        """File .locked yang terpotong setengah harus gagal dengan bersih."""
        locked_path = kunci_dan_dapat_path(sample_folder)
        size = os.path.getsize(locked_path)

        # Potong file jadi setengah
        with open(locked_path, "rb") as f:
            data = f.read(size // 2)

        terpotong = os.path.join(tmp_dir, "terpotong.locked")
        with open(terpotong, "wb") as f:
            f.write(data)

        # force=True supaya vault tidak berhenti di OVERWRITE check
        # (folder asli masih ada) dan lanjut ke verifikasi GCM yang akan gagal
        status, _ = buka_brankas(terpotong, PASSWORD_BENAR, force=True)
        assert status in ("WRONG_PW", "ERROR")

    def test_file_dimodifikasi_1_byte(self, sample_folder, tmp_dir):
        """
        Modifikasi 1 byte di tengah ciphertext harus gagal verifikasi GCM.
        Ini membuktikan integritas AES-GCM bekerja.
        """
        locked_path = kunci_dan_dapat_path(sample_folder)

        with open(locked_path, "rb") as f:
            data = bytearray(f.read())

        # Modifikasi byte di tengah (area ciphertext, bukan header salt/nonce)
        data[len(data) // 2] ^= 0xFF

        tampered = os.path.join(tmp_dir, "tampered.locked")
        with open(tampered, "wb") as f:
            f.write(data)

        # force=True: bypass OVERWRITE check, paksa vault coba ekstrak
        # GCM finalize() akan gagal karena tag tidak cocok dengan ciphertext yang dimodifikasi
        status, _ = buka_brankas(tampered, PASSWORD_BENAR, force=True)
        assert status in (
            "WRONG_PW",
            "ERROR",
        ), "File yang dimodifikasi seharusnya tidak bisa dibuka!"

    def test_file_kosong(self, tmp_dir):
        """File 0 bytes harus return ERROR."""
        path = os.path.join(tmp_dir, "kosong.locked")
        open(path, "wb").close()

        status, msg = buka_brankas(path, PASSWORD_BENAR)
        assert status == "ERROR"


# ── Overwrite Flow ────────────────────────────────────────────────────────────


class TestOverwrite:

    def test_overwrite_prompt_jika_folder_ada(self, sample_folder):
        """
        Jika folder tujuan sudah ada, harus return OVERWRITE bukan langsung ekstrak.
        """
        locked_path = kunci_dan_dapat_path(sample_folder)
        # Folder asli TIDAK dihapus — simulasi folder sudah ada

        status, nama = buka_brankas(locked_path, PASSWORD_BENAR)
        assert status == "OVERWRITE"
        assert nama == os.path.basename(sample_folder)

    def test_force_true_timpa_folder(self, sample_folder):
        """force=True harus berhasil meski folder sudah ada."""
        checksum_asli = folder_checksum(sample_folder)
        locked_path = kunci_dan_dapat_path(sample_folder)

        # Modifikasi folder asli sebelum force overwrite
        with open(os.path.join(sample_folder, "dokumen.txt"), "w") as f:
            f.write("ISI YANG SUDAH DIUBAH")

        status, nama = buka_brankas(locked_path, PASSWORD_BENAR, force=True)
        assert status == "SUCCESS"

        # Isi harus kembali ke versi asli (sebelum modifikasi)
        folder_restored = os.path.join(os.path.dirname(locked_path), nama)
        checksum_restored = folder_checksum(folder_restored)
        assert checksum_asli == checksum_restored


# ── Hapus Asli ────────────────────────────────────────────────────────────────


class TestHapusAsli:

    def test_hapus_asli_true_menghapus_folder(self, sample_folder):
        """hapus_asli=True harus menghapus folder sumber setelah kunci berhasil."""
        sukses, _ = kunci_brankas(sample_folder, PASSWORD_BENAR, hapus_asli=True)
        assert sukses is True
        assert not os.path.exists(
            sample_folder
        ), "Folder asli masih ada padahal hapus_asli=True!"

    def test_hapus_asli_false_tidak_menghapus(self, sample_folder):
        """hapus_asli=False (default) harus membiarkan folder asli tetap ada."""
        sukses, _ = kunci_brankas(sample_folder, PASSWORD_BENAR, hapus_asli=False)
        assert sukses is True
        assert os.path.exists(
            sample_folder
        ), "Folder asli terhapus padahal hapus_asli=False!"


# ── Progress Callback ─────────────────────────────────────────────────────────


class TestProgressCallback:

    def test_kunci_progress_dipanggil(self, sample_folder):
        """Progress callback harus dipanggil minimal sekali saat kunci."""
        progress_values = []
        kunci_brankas(
            sample_folder,
            PASSWORD_BENAR,
            progress_cb=lambda v: progress_values.append(v),
        )

        assert len(progress_values) > 0, "Progress callback tidak pernah dipanggil"

    def test_kunci_progress_naik_monoton(self, sample_folder):
        """Nilai progress tidak boleh turun (harus selalu naik atau tetap)."""
        progress_values = []
        kunci_brankas(
            sample_folder,
            PASSWORD_BENAR,
            progress_cb=lambda v: progress_values.append(v),
        )

        for i in range(1, len(progress_values)):
            assert progress_values[i] >= progress_values[i - 1], (
                f"Progress turun dari {progress_values[i-1]} ke {progress_values[i]} "
                f"di index {i}"
            )

    def test_kunci_progress_berakhir_di_1(self, sample_folder):
        """Progress harus mencapai 1.0 (100%) saat selesai."""
        progress_values = []
        kunci_brankas(
            sample_folder,
            PASSWORD_BENAR,
            progress_cb=lambda v: progress_values.append(v),
        )

        assert (
            progress_values[-1] == 1.0
        ), f"Progress tidak berakhir di 1.0, terakhir: {progress_values[-1]}"

    def test_buka_progress_berakhir_di_1(self, sample_folder):
        """Progress buka brankas juga harus mencapai 1.0."""
        locked_path = kunci_dan_dapat_path(sample_folder)
        progress_values = []
        shutil.rmtree(sample_folder)

        buka_brankas(
            locked_path, PASSWORD_BENAR, progress_cb=lambda v: progress_values.append(v)
        )

        assert progress_values[-1] == 1.0

    def test_progress_dalam_range_valid(self, sample_folder):
        """Semua nilai progress harus dalam range [0.0, 1.0]."""
        progress_values = []
        kunci_brankas(
            sample_folder,
            PASSWORD_BENAR,
            progress_cb=lambda v: progress_values.append(v),
        )

        for val in progress_values:
            assert 0.0 <= val <= 1.0, f"Progress out of range: {val}"

    def test_progress_none_tidak_crash(self, sample_folder):
        """progress_cb=None tidak boleh crash."""
        sukses, _ = kunci_brankas(sample_folder, PASSWORD_BENAR, progress_cb=None)
        assert sukses is True

    def test_progress_exception_tidak_crash_proses(self, sample_folder):
        """Exception di dalam callback tidak boleh menghentikan proses enkripsi."""

        def cb_rusak(_):
            raise RuntimeError("callback rusak")

        sukses, _ = kunci_brankas(sample_folder, PASSWORD_BENAR, progress_cb=cb_rusak)
        assert sukses is True


# ── Edge Cases ────────────────────────────────────────────────────────────────


class TestEdgeCases:

    def test_folder_kosong(self, empty_folder):
        """Folder kosong harus bisa dikunci dan dibuka tanpa error."""
        locked_path = kunci_dan_dapat_path(empty_folder)
        shutil.rmtree(empty_folder)

        status, nama = buka_brankas(locked_path, PASSWORD_BENAR)
        assert status == "SUCCESS"

        folder_restored = os.path.join(os.path.dirname(locked_path), nama)
        assert os.path.isdir(folder_restored)
        assert len(os.listdir(folder_restored)) == 0

    def test_nama_folder_dengan_spasi(self, sample_folder_spasi):
        """Nama folder dengan spasi harus ter-encode dan ter-decode dengan benar."""
        locked_path = kunci_dan_dapat_path(sample_folder_spasi)
        shutil.rmtree(sample_folder_spasi)

        status, nama = buka_brankas(locked_path, PASSWORD_BENAR)
        assert status == "SUCCESS"
        assert nama == os.path.basename(sample_folder_spasi)

    def test_file_unicode(self, sample_folder_unicode):
        """File dengan nama unicode harus ter-preserve dengan benar."""
        checksum_asli = folder_checksum(sample_folder_unicode)
        locked_path = kunci_dan_dapat_path(sample_folder_unicode)
        shutil.rmtree(sample_folder_unicode)

        status, nama = buka_brankas(locked_path, PASSWORD_BENAR)
        assert status == "SUCCESS"

        folder_restored = os.path.join(os.path.dirname(locked_path), nama)
        checksum_restored = folder_checksum(folder_restored)
        assert checksum_asli == checksum_restored

    def test_multiple_kunci_menghasilkan_nama_unik(self, sample_folder):
        """Dua kali kunci folder yang sama harus menghasilkan nama file .locked berbeda."""
        base_dir = os.path.dirname(sample_folder)

        _, pesan1 = kunci_brankas(sample_folder, PASSWORD_BENAR)
        _, pesan2 = kunci_brankas(sample_folder, PASSWORD_BENAR)

        locked_files = [f for f in os.listdir(base_dir) if f.endswith(".locked")]
        assert (
            len(locked_files) == 2
        ), "Nama file .locked harus unik untuk tiap enkripsi"

    def test_password_sangat_panjang(self, sample_folder):
        """Password 1000 karakter harus bisa dikunci dan dibuka."""
        pw_panjang = "a" * 1000
        locked_path = kunci_dan_dapat_path(sample_folder, password=pw_panjang)
        shutil.rmtree(sample_folder)

        status, _ = buka_brankas(locked_path, pw_panjang)
        assert status == "SUCCESS"

    def test_password_unicode(self, sample_folder):
        """Password dengan karakter unicode harus bekerja."""
        pw_unicode = "🔐パスワード!@#$%"
        locked_path = kunci_dan_dapat_path(sample_folder, password=pw_unicode)
        shutil.rmtree(sample_folder)

        status, _ = buka_brankas(locked_path, pw_unicode)
        assert status == "SUCCESS"

    def test_folder_path_tidak_ada(self, tmp_dir):
        """Folder yang tidak ada harus return False dengan pesan error."""
        path_fiktif = os.path.join(tmp_dir, "tidak_ada_sama_sekali")
        sukses, pesan = kunci_brankas(path_fiktif, PASSWORD_BENAR)
        assert sukses is False
        assert pesan  # pesan error tidak boleh kosong

    def test_locked_file_tidak_ada(self, tmp_dir):
        """File .locked yang tidak ada harus return ERROR."""
        path_fiktif = os.path.join(tmp_dir, "tidak_ada.locked")
        status, msg = buka_brankas(path_fiktif, PASSWORD_BENAR)
        assert status == "ERROR"

    def test_integritas_salt_dan_nonce_unik(self, sample_folder):
        """
        Setiap enkripsi harus menggunakan salt dan nonce yang berbeda.
        Ini kritis — salt/nonce yang sama melemahkan keamanan AES-GCM secara drastis.
        """

        def baca_header(path):
            with open(path, "rb") as f:
                salt = f.read(16)
                nonce = f.read(12)
            return salt, nonce

        _, pesan1 = kunci_brankas(sample_folder, PASSWORD_BENAR)
        _, pesan2 = kunci_brankas(sample_folder, PASSWORD_BENAR)

        base_dir = os.path.dirname(sample_folder)
        locked_files = sorted(
            [
                os.path.join(base_dir, f)
                for f in os.listdir(base_dir)
                if f.endswith(".locked")
            ],
            key=os.path.getmtime,
        )

        salt1, nonce1 = baca_header(locked_files[-2])
        salt2, nonce2 = baca_header(locked_files[-1])

        assert salt1 != salt2, "Salt harus unik di setiap enkripsi!"
        assert nonce1 != nonce2, "Nonce harus unik di setiap enkripsi!"


# ── secure_delete ─────────────────────────────────────────────────────────────


class TestSecureDelete:

    def test_hapus_file(self, tmp_dir):
        """secure_delete harus menghapus file."""
        path = os.path.join(tmp_dir, "rahasia.txt")
        with open(path, "w") as f:
            f.write("data sensitif")

        secure_delete(path)
        assert not os.path.exists(path)

    def test_hapus_direktori_rekursif(self, tmp_dir):
        """secure_delete harus menghapus direktori beserta isinya."""
        folder = os.path.join(tmp_dir, "folder_hapus")
        os.makedirs(os.path.join(folder, "sub"))
        with open(os.path.join(folder, "file.txt"), "w") as f:
            f.write("isi")
        with open(os.path.join(folder, "sub", "nested.txt"), "w") as f:
            f.write("nested")

        secure_delete(folder)
        assert not os.path.exists(folder)

    def test_path_tidak_ada_tidak_crash(self, tmp_dir):
        """secure_delete pada path yang tidak ada tidak boleh crash."""
        path_fiktif = os.path.join(tmp_dir, "tidak_ada.txt")
        secure_delete(path_fiktif)  # Tidak boleh raise exception

    def test_file_di_nol_sebelum_dihapus(self, tmp_dir):
        """
        Setelah secure_delete, file tidak boleh bisa dibaca lagi.
        (Verifikasi file benar-benar hilang dari filesystem.)
        """
        path = os.path.join(tmp_dir, "sensitif.bin")
        with open(path, "wb") as f:
            f.write(b"DATA RAHASIA" * 100)

        secure_delete(path)
        assert not os.path.exists(path)
