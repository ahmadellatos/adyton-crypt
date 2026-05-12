"""
tests/conftest.py
Fixtures bersama yang dipakai oleh semua test file.
Dijalankan otomatis oleh pytest sebelum test apapun.
"""

import os
import shutil
import tempfile
import pytest

# ── Fixtures Dasar ────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_dir():
    """
    Temporary directory bersih yang otomatis dihapus setelah tiap test selesai.
    Semua operasi file dalam test HARUS pakai ini, bukan hardcode path.
    """
    d = tempfile.mkdtemp(prefix="locker_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_folder(tmp_dir):
    """
    Folder dummy dengan struktur file realistis untuk test enkripsi.

    Struktur:
        sample_folder/
        ├── dokumen.txt          (teks biasa)
        ├── data.bin             (binary random)
        └── subfolder/
            ├── nested.txt       (teks dalam subfolder)
            └── empty_file.txt   (file kosong — edge case)
    """
    folder = os.path.join(tmp_dir, "sample_folder")
    sub = os.path.join(folder, "subfolder")
    os.makedirs(sub)

    # File teks biasa
    with open(os.path.join(folder, "dokumen.txt"), "w", encoding="utf-8") as f:
        f.write("Ini file rahasia.\nBaris kedua.\nBaris ketiga dengan angka 12345.")

    # File binary (simulasi gambar/dokumen biner)
    with open(os.path.join(folder, "data.bin"), "wb") as f:
        f.write(os.urandom(1024 * 64))  # 64 KB random bytes

    # File dalam subfolder
    with open(os.path.join(sub, "nested.txt"), "w", encoding="utf-8") as f:
        f.write("File dalam subfolder — pastikan struktur direktori terjaga.")

    # File kosong (edge case yang sering bikin bug di archiver)
    open(os.path.join(sub, "empty_file.txt"), "w").close()

    return folder


@pytest.fixture
def sample_folder_unicode(tmp_dir):
    """
    Folder dengan nama file berkarakter unicode — edge case encoding.
    """
    folder = os.path.join(tmp_dir, "folder_unicode")
    os.makedirs(folder)

    with open(os.path.join(folder, "résumé.txt"), "w", encoding="utf-8") as f:
        f.write("Café, naïve, jalapeño, Ångström")

    with open(os.path.join(folder, "日本語.txt"), "w", encoding="utf-8") as f:
        f.write("テスト用ファイル")

    return folder


@pytest.fixture
def empty_folder(tmp_dir):
    """Folder benar-benar kosong — edge case untuk archiver."""
    folder = os.path.join(tmp_dir, "empty_folder")
    os.makedirs(folder)
    return folder


@pytest.fixture
def sample_folder_spasi(tmp_dir):
    """Folder dengan spasi dan karakter khusus di nama."""
    folder = os.path.join(tmp_dir, "folder dengan spasi (2024)")
    os.makedirs(folder)
    with open(os.path.join(folder, "file normal.txt"), "w") as f:
        f.write("test spasi di nama folder")
    return folder


# ── Helper Functions ──────────────────────────────────────────────────────────


def folder_checksum(folder_path: str) -> dict:
    """
    Buat checksum sederhana dari semua file dalam folder.
    Dipakai untuk verifikasi isi folder sebelum dan sesudah enkripsi-dekripsi.
    Returns: dict {relative_path: (size_bytes, content_hash)}
    """
    import hashlib

    result = {}
    for root, _, files in os.walk(folder_path):
        for fname in files:
            fpath = os.path.join(root, fname)
            rel_path = os.path.relpath(fpath, folder_path)
            with open(fpath, "rb") as f:
                content = f.read()
            h = hashlib.sha256(content).hexdigest()
            result[rel_path] = (len(content), h)
    return result
