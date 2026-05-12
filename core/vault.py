"""
core/vault.py
Logika utama: kunci folder/file (enkripsi) dan buka brankas (dekripsi).
Dioptimasi dengan Single-Pass I/O Streaming menggunakan Tarfile + Memory Buffering.
Multi-file support: Menggabungkan banyak file/folder menjadi satu brankas.
"""

import os
import shutil
import uuid
import tempfile
import tarfile
from cryptography.exceptions import InvalidTag

from .crypto import CHUNK_SIZE, derive_key, make_encryptor, make_decryptor, safe_cb

# ── File Operations ───────────────────────────────────────────────────────────


def secure_delete(path: str):
    """
    Menimpa file dengan nol sebelum dihapus.
    PERHATIAN: Tidak menjamin penghapusan aman di SSD/NVMe karena wear leveling.
    """
    if not os.path.exists(path):
        return
    if os.path.isfile(path):
        try:
            size = os.path.getsize(path)
            with open(path, "r+b") as f:
                written = 0
                while written < size:
                    chunk = min(CHUNK_SIZE, size - written)
                    f.write(b"\x00" * chunk)
                    written += chunk
            os.remove(path)
        except Exception:
            pass
    elif os.path.isdir(path):
        for root, dirs, files in os.walk(path, topdown=False):
            for name in files:
                secure_delete(os.path.join(root, name))
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root, name))
                except OSError:
                    pass
        try:
            os.rmdir(path)
        except OSError:
            shutil.rmtree(path, ignore_errors=True)


# ── Custom Stream Classes ─────────────────────────────────────────────────────


class EncryptingStream:
    """Pipa memori ajaib yang dilengkapi Buffer (Waduk) untuk enkripsi."""

    def __init__(self, target_file, encryptor, progress_cb, total_bytes):
        self.target_file = target_file
        self.encryptor = encryptor
        self.progress_cb = progress_cb
        self.total_bytes = total_bytes
        self.bytes_written = 0
        self.buffer = bytearray()
        self._last_pct = 0.0
        self._flushed = False

    def write(self, data: bytes):
        self.buffer.extend(data)
        self.bytes_written += len(data)

        if self.total_bytes > 0:
            pct = min(0.89, 0.05 + 0.85 * (self.bytes_written / self.total_bytes))
            if pct - self._last_pct >= 0.005:
                safe_cb(self.progress_cb, pct)
                self._last_pct = pct

        if len(self.buffer) >= CHUNK_SIZE:
            encrypted = self.encryptor.update(bytes(self.buffer))
            if encrypted:
                self.target_file.write(encrypted)
            self.buffer.clear()

        return len(data)

    def flush(self):
        if self._flushed:
            return
        self._flushed = True
        if self.buffer:
            encrypted = self.encryptor.update(bytes(self.buffer))
            if encrypted:
                self.target_file.write(encrypted)
            self.buffer.clear()

    def close(self):
        self.flush()


class DecryptingStream:
    """
    Pipa memori ajaib untuk dekripsi Single-Pass.
    Membaca langsung dari ciphertext, mendekripsi, dan membuang ke buffer tarfile.
    Menghindari double-disk space usage.
    """

    def __init__(
        self,
        target_file,
        decryptor,
        bytes_remaining,
        initial_buffer,
        progress_cb,
        total_len,
        bytes_read_so_far,
    ):
        self.target_file = target_file
        self.decryptor = decryptor
        self.bytes_remaining = bytes_remaining
        self.buffer = bytearray(initial_buffer)
        self.progress_cb = progress_cb
        self.total_len = total_len
        self.bytes_read_so_far = bytes_read_so_far
        self._last_pct = 0.0
        self._finalized = False

    def read(self, size=-1):
        # Jika diminta membaca semua (exhaust)
        if size < 0:
            result = bytearray(self.buffer)
            self.buffer.clear()
            while self.bytes_remaining > 0:
                chunk_sz = min(CHUNK_SIZE, self.bytes_remaining)
                chunk = self.target_file.read(chunk_sz)
                self.bytes_remaining -= len(chunk)
                result.extend(self.decryptor.update(chunk))
                self._update_progress(len(chunk))

            if not self._finalized:
                self._finalized = True
                result.extend(
                    self.decryptor.finalize()
                )  # Raises InvalidTag jika data tampered
            return bytes(result)

        # Membaca per chunk sesuai permintaan tarfile
        result = bytearray()
        while len(result) < size and (self.bytes_remaining > 0 or self.buffer):
            if self.buffer:
                take = min(size - len(result), len(self.buffer))
                result.extend(self.buffer[:take])
                del self.buffer[:take]
            else:
                chunk_sz = min(CHUNK_SIZE, self.bytes_remaining)
                if chunk_sz == 0:
                    break
                chunk = self.target_file.read(chunk_sz)
                self.bytes_remaining -= len(chunk)
                self._update_progress(len(chunk))

                decrypted = self.decryptor.update(chunk)
                self.buffer.extend(decrypted)

        # Finalisasi GCM ketika semua ciphertext sudah dibaca
        if self.bytes_remaining == 0 and not self.buffer and not self._finalized:
            self._finalized = True
            final_bytes = (
                self.decryptor.finalize()
            )  # Raises InvalidTag jika password salah/tampered
            if final_bytes:
                take = min(size - len(result), len(final_bytes))
                result.extend(final_bytes[:take])
                self.buffer.extend(final_bytes[take:])

        return bytes(result)

    def _update_progress(self, bytes_added):
        self.bytes_read_so_far += bytes_added
        # Skala progress ke 0.95 (5% sisa untuk proses shutil di tahap akhir)
        pct = min(0.95, 0.80 * (self.bytes_read_so_far / (self.total_len or 1)))
        if pct - self._last_pct >= 0.005:
            safe_cb(self.progress_cb, pct)
            self._last_pct = pct


# ── Logic Pembantu ────────────────────────────────────────────────────────────


def _hitung_total_size(paths: list[str]) -> int:
    """Menghitung total ukuran byte dari kumpulan file/folder."""
    total = 0
    for p in paths:
        if os.path.isfile(p):
            total += os.path.getsize(p)
        elif os.path.isdir(p):
            total += sum(
                os.path.getsize(os.path.join(r, f))
                for r, _, files in os.walk(p)
                for f in files
                if not os.path.islink(os.path.join(r, f))
            )
    return total or 1


# ── Public API ────────────────────────────────────────────────────────────────


def kunci_brankas(
    paths: list[str],
    path_simpan: str,
    password: str,
    hapus_asli: bool = False,
    progress_cb=None,
) -> tuple[bool, str]:
    """Mengunci satu atau banyak file/folder ke dalam satu file .locked."""
    path_backup = path_simpan + ".bak"
    backup_dibuat = False

    try:
        if os.path.exists(path_simpan):
            os.replace(path_simpan, path_backup)
            backup_dibuat = True

        salt = os.urandom(16)
        nonce = os.urandom(12)

        key = derive_key(password, salt)
        safe_cb(progress_cb, 0.05)

        total_size = _hitung_total_size(paths)
        encryptor = make_encryptor(key, nonce)

        is_single_file = len(paths) == 1 and os.path.isfile(paths[0])
        is_single_dir = len(paths) == 1 and os.path.isdir(paths[0])

        if is_single_file:
            nama_virtual = os.path.basename(paths[0])
            target_dir = ""
        elif is_single_dir:
            nama_virtual = os.path.basename(os.path.abspath(paths[0]))
            target_dir = ""
        else:
            nama_file = os.path.basename(path_simpan)
            target_dir = os.path.splitext(nama_file)[0] or "Brankas_Rahasia"
            nama_virtual = target_dir

        nama_bytes = nama_virtual.encode("utf-8")
        panjang_nama = len(nama_bytes).to_bytes(2, byteorder="big")

        with open(path_simpan, "wb") as fk:
            fk.write(salt)
            fk.write(nonce)
            fk.write(encryptor.update(panjang_nama + nama_bytes))

            out_stream = EncryptingStream(fk, encryptor, progress_cb, total_size)

            with tarfile.open(fileobj=out_stream, mode="w|") as tar:
                for p in paths:
                    if not os.path.exists(p):
                        continue
                    nama_item = os.path.basename(os.path.abspath(p))
                    arcname = (
                        os.path.join(target_dir, nama_item) if target_dir else nama_item
                    )
                    tar.add(p, arcname=arcname)

            out_stream.flush()
            fk.write(encryptor.finalize())
            fk.write(encryptor.tag)

        safe_cb(progress_cb, 0.90)

        if backup_dibuat and os.path.exists(path_backup):
            os.remove(path_backup)

        if hapus_asli:
            safe_cb(progress_cb, 0.95)
            for p in paths:
                secure_delete(p)

        size_mb = os.path.getsize(path_simpan) / (1024 * 1024)
        safe_cb(progress_cb, 1.0)
        return True, f"Brankas berhasil dikunci!\nUkuran: {size_mb:.1f} MB"

    except Exception as exc:
        if os.path.exists(path_simpan):
            os.remove(path_simpan)
        if backup_dibuat and os.path.exists(path_backup):
            os.rename(path_backup, path_simpan)
        return False, str(exc)


def buka_brankas(
    locked_path: str, password: str, force: bool = False, progress_cb=None
) -> tuple[str, str | None]:
    """
    Membuka file .locked secara streaming (Single-Pass) tanpa menggunakan file temporary disk.
    Mencegah storage kembung (double disk space) dan meningkatkan kecepatan.
    """
    temp_ext_dir = None
    try:
        total_size = os.path.getsize(locked_path)
        if total_size < 44:
            return "ERROR", "File terlalu kecil/rusak."

        cipher_len = total_size - 44

        with open(locked_path, "rb") as fk:
            salt = fk.read(16)
            nonce = fk.read(12)
            fk.seek(-16, os.SEEK_END)
            tag = fk.read(16)
            fk.seek(28)

            key = derive_key(password, salt)
            decryptor = make_decryptor(key, nonce, tag)

            first_sz = min(1024, cipher_len)
            first_chunk = fk.read(first_sz)
            bytes_remaining = cipher_len - first_sz

            decrypted_first = decryptor.update(first_chunk)

            # Ekstrak header (nama_folder)
            try:
                panjang_nama = int.from_bytes(decrypted_first[:2], byteorder="big")
                if panjang_nama > 512:
                    return "WRONG_PW", None
                if len(decrypted_first) < 2 + panjang_nama:
                    return "ERROR", "File brankas rusak atau terpotong."
                nama_folder = decrypted_first[2 : 2 + panjang_nama].decode("utf-8")
            except Exception:
                return "WRONG_PW", None

            base_dir = os.path.dirname(locked_path)
            path_tujuan = os.path.join(base_dir, nama_folder)

            # Cek eksistensi sebelum bongkar
            if os.path.exists(path_tujuan) and not force:
                return "OVERWRITE", nama_folder

            initial_buffer = decrypted_first[2 + panjang_nama :]
            in_stream = DecryptingStream(
                fk,
                decryptor,
                bytes_remaining,
                initial_buffer,
                progress_cb,
                cipher_len,
                first_sz,
            )

            # Ekstrak ke folder sembunyi di directory yang SAMA agar pindah file bersifat instant (atomic O(1))
            id_temp = uuid.uuid4().hex[:8]
            temp_ext_dir = os.path.join(base_dir, f"._dec_{id_temp}")
            os.makedirs(temp_ext_dir, exist_ok=True)

            try:
                # Eksekusi ekstraksi secara Streaming
                with tarfile.open(fileobj=in_stream, mode="r|") as tar:
                    tar.extractall(path=temp_ext_dir)

                # Drain sisa bytes untuk memastikan finalize() terpanggil dan AES-GCM divalidasi
                in_stream.read()

                src = os.path.join(temp_ext_dir, nama_folder)
                if not os.path.exists(src):
                    raise ValueError("Isi brankas tidak sesuai format ekspektasi.")

                # Berhasil divalidasi! Hapus file lama jika 'force' aktif
                if os.path.exists(path_tujuan):
                    secure_delete(path_tujuan)

                # Pindah atomic instan (karena di disk/volume yang sama)
                shutil.move(src, path_tujuan)

            except InvalidTag:
                return "WRONG_PW", None
            except Exception as exc:
                # Fallback untuk exception turunan dari error AES-GCM atau Tar rusak
                if getattr(
                    exc, "__class__", None
                ) is InvalidTag or "DECRYPT_FAIL" in str(exc):
                    return "WRONG_PW", None
                return "ERROR", f"Ekstraksi gagal/arsip rusak: {exc}"

        safe_cb(progress_cb, 1.0)
        return "SUCCESS", nama_folder

    except Exception as exc:
        return "ERROR", str(exc)
    finally:
        # Cleanup: hapus folder sementara jika ternyata masih ada (karena gagal/crash)
        if temp_ext_dir and os.path.exists(temp_ext_dir):
            secure_delete(temp_ext_dir)
