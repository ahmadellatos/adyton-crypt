"""
core/vault.py
Logika utama: kunci folder/file (enkripsi) dan buka brankas (dekripsi).
Dioptimasi dengan Single-Pass I/O Streaming, pathlib, dan Cancellation Support.
Dilengkapi mode opsi Secure Wipe untuk HDD tradisional.
"""

import os
import shutil
import uuid
import tarfile
import stat
import time  # FIX: Import time untuk perhitungan umur folder temp
from pathlib import Path
from enum import Enum
from typing import Callable, Optional
from cryptography.exceptions import InvalidTag

from .crypto import CHUNK_SIZE, derive_key, make_encryptor, make_decryptor, safe_cb

HEADER_SIZE = 16 + 12
TAG_SIZE = 16
OVERHEAD = HEADER_SIZE + TAG_SIZE


class VaultStatus(Enum):
    SUCCESS = "success"
    WRONG_PASSWORD = "wrong_password"
    OVERWRITE_NEEDED = "overwrite_needed"
    ERROR = "error"
    CANCELLED = "cancelled"


# ── File Operations ───────────────────────────────────────────────────────────


def hapus_permanen(path: Path, secure_wipe: bool = False):
    """
    Menghapus file/folder.
    Jika secure_wipe aktif, file akan ditimpa dengan byte 0x00 sebelum dihapus.
    """
    if not path.exists():
        return

    if path.is_file() or path.is_symlink():
        if secure_wipe and not path.is_symlink():
            try:
                path.chmod(stat.S_IWRITE)
                size = path.stat().st_size
                with path.open("r+b") as f:
                    written = 0
                    kosong = b"\x00" * CHUNK_SIZE
                    while written < size:
                        chunk = min(CHUNK_SIZE, size - written)
                        f.write(kosong[:chunk])
                        written += chunk
            except Exception:
                pass

        try:
            path.unlink(missing_ok=True)
        except PermissionError:
            path.chmod(stat.S_IWRITE)
            path.unlink(missing_ok=True)

    elif path.is_dir():
        for child in path.iterdir():
            hapus_permanen(child, secure_wipe)
        try:
            path.rmdir()
        except OSError:

            def _remove_readonly(func, p, excinfo):
                try:
                    os.chmod(p, stat.S_IWRITE)
                    func(p)
                except Exception:
                    pass

            shutil.rmtree(path, onerror=_remove_readonly)


# ── Custom Stream Classes ─────────────────────────────────────────────────────


class EncryptingStream:
    def __init__(
        self,
        target_file,
        encryptor,
        progress_cb,
        total_bytes,
        is_cancelled: Callable[[], bool] = None,
    ):
        self.target_file = target_file
        self.encryptor = encryptor
        self.progress_cb = progress_cb
        self.total_bytes = total_bytes
        self.bytes_written = 0
        self.buffer = bytearray()
        self._last_pct = 0.0
        self._flushed = False
        self.is_cancelled = is_cancelled

    def write(self, data: bytes):
        if self.is_cancelled and self.is_cancelled():
            raise InterruptedError("Operasi dibatalkan oleh pengguna.")

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
    def __init__(
        self,
        target_file,
        decryptor,
        bytes_remaining,
        initial_buffer,
        progress_cb,
        total_len,
        bytes_read_so_far,
        is_cancelled: Callable[[], bool] = None,
    ):
        self.target_file = target_file
        self.decryptor = decryptor
        self.bytes_remaining = bytes_remaining
        self.buffer = bytes(initial_buffer)
        self.buf_offset = 0
        self.progress_cb = progress_cb
        self.total_len = total_len
        self.bytes_read_so_far = bytes_read_so_far
        self._last_pct = 0.0
        self._finalized = False
        self.is_cancelled = is_cancelled

    def read(self, size=-1):
        if self.is_cancelled and self.is_cancelled():
            raise InterruptedError("Operasi dibatalkan oleh pengguna.")

        if size < 0:
            result = bytearray(self.buffer[self.buf_offset :])
            self.buffer = b""
            self.buf_offset = 0

            while self.bytes_remaining > 0:
                if self.is_cancelled and self.is_cancelled():
                    raise InterruptedError("Operasi dibatalkan oleh pengguna.")

                chunk_sz = min(CHUNK_SIZE, self.bytes_remaining)
                chunk = self.target_file.read(chunk_sz)
                self.bytes_remaining -= len(chunk)
                result.extend(self.decryptor.update(chunk))
                self._update_progress(len(chunk))

            if not self._finalized:
                self._finalized = True
                result.extend(self.decryptor.finalize())
            return bytes(result)

        result = bytearray()
        while len(result) < size:
            if self.buf_offset < len(self.buffer):
                take = min(size - len(result), len(self.buffer) - self.buf_offset)
                result.extend(self.buffer[self.buf_offset : self.buf_offset + take])
                self.buf_offset += take
            elif self.bytes_remaining > 0:
                if self.is_cancelled and self.is_cancelled():
                    raise InterruptedError("Operasi dibatalkan oleh pengguna.")

                chunk_sz = min(CHUNK_SIZE, self.bytes_remaining)
                chunk = self.target_file.read(chunk_sz)
                self.bytes_remaining -= len(chunk)
                self._update_progress(len(chunk))

                self.buffer = self.decryptor.update(chunk)
                self.buf_offset = 0
            elif not self._finalized:
                self._finalized = True
                self.buffer = self.decryptor.finalize()
                self.buf_offset = 0
            else:
                break

        return bytes(result)

    def _update_progress(self, bytes_added):
        self.bytes_read_so_far += bytes_added
        pct = min(0.95, 0.05 + 0.90 * (self.bytes_read_so_far / (self.total_len or 1)))
        if pct - self._last_pct >= 0.005:
            safe_cb(self.progress_cb, pct)
            self._last_pct = pct


# ── Logic Pembantu ────────────────────────────────────────────────────────────


def _hitung_total_size(paths: list[str]) -> int:
    total = 0
    for p in paths:
        path = Path(p)
        if path.is_file() and not path.is_symlink():
            total += path.stat().st_size
        elif path.is_dir():
            total += sum(
                f.stat().st_size
                for f in path.rglob("*")
                if f.is_file() and not f.is_symlink()
            )
    return total or 1


# ── Public API ────────────────────────────────────────────────────────────────


def kunci_brankas(
    paths: list[str],
    path_simpan: str,
    password: str,
    hapus_asli: bool = False,
    secure_wipe: bool = False,
    progress_cb=None,
    is_cancelled: Callable[[], bool] = None,
) -> tuple[VaultStatus, str]:

    # FIX: Validasi path kosong/tidak ada dari review test_folder_path_tidak_ada
    valid_paths = [p for p in paths if Path(p).exists()]
    if not valid_paths:
        return VaultStatus.ERROR, "Tidak ada file/folder valid untuk dikunci."

    target_path = Path(path_simpan)
    backup_path = target_path.with_suffix(".locked.bak")
    backup_dibuat = False

    try:
        if target_path.exists():
            target_path.replace(backup_path)
            backup_dibuat = True

        salt = os.urandom(16)
        nonce = os.urandom(12)
        key = derive_key(password, salt)
        safe_cb(progress_cb, 0.05)

        total_size = _hitung_total_size(valid_paths)
        encryptor = make_encryptor(key, nonce)

        is_single_file = len(valid_paths) == 1 and Path(valid_paths[0]).is_file()
        is_single_dir = len(valid_paths) == 1 and Path(valid_paths[0]).is_dir()

        if is_single_file or is_single_dir:
            nama_virtual = Path(valid_paths[0]).name
            target_dir = ""
        else:
            nama_virtual = target_path.stem or "Brankas_Rahasia"
            target_dir = nama_virtual

        nama_bytes = nama_virtual.encode("utf-8")
        panjang_nama = len(nama_bytes).to_bytes(2, byteorder="big")

        with target_path.open("wb") as fk:
            fk.write(salt)
            fk.write(nonce)
            fk.write(encryptor.update(panjang_nama + nama_bytes))

            out_stream = EncryptingStream(
                fk, encryptor, progress_cb, total_size, is_cancelled
            )

            with tarfile.open(fileobj=out_stream, mode="w|") as tar:
                for p in valid_paths:
                    path_item = Path(p)
                    arcname = (
                        str(Path(target_dir) / path_item.name)
                        if target_dir
                        else path_item.name
                    )
                    tar.add(str(path_item), arcname=arcname)

            out_stream.flush()
            fk.write(encryptor.finalize())
            fk.write(encryptor.tag)

        safe_cb(progress_cb, 0.90)

        if backup_dibuat and backup_path.exists():
            backup_path.unlink()

        if hapus_asli:
            safe_cb(progress_cb, 0.95)
            for p in valid_paths:
                hapus_permanen(Path(p), secure_wipe)

        size_mb = target_path.stat().st_size / (1024 * 1024)
        safe_cb(progress_cb, 1.0)
        return (
            VaultStatus.SUCCESS,
            f"Brankas berhasil dikunci!\nUkuran: {size_mb:.1f} MB",
        )

    except InterruptedError:
        if target_path.exists():
            target_path.unlink(missing_ok=True)
        if backup_dibuat and backup_path.exists():
            backup_path.replace(target_path)
        return VaultStatus.CANCELLED, "Proses dibatalkan."
    except Exception as exc:
        if target_path.exists():
            target_path.unlink(missing_ok=True)
        if backup_dibuat and backup_path.exists():
            backup_path.replace(target_path)
        return VaultStatus.ERROR, str(exc)


def buka_brankas(
    locked_path: str,
    password: str,
    force: bool = False,
    progress_cb=None,
    is_cancelled: Callable[[], bool] = None,
) -> tuple[VaultStatus, str | None]:
    target_path = Path(locked_path)
    temp_ext_dir = None

    try:
        total_size = target_path.stat().st_size
        if total_size < OVERHEAD:
            return VaultStatus.ERROR, "File terlalu kecil/rusak."

        cipher_len = total_size - 44
        base_dir = target_path.parent

        # FIX: Race condition cleanup — hanya hapus temp folder yang umurnya > 5 menit (stale)
        for old_temp in base_dir.glob("._dec_*"):
            if old_temp.is_dir():
                try:
                    age = time.time() - old_temp.stat().st_mtime
                    if age > 300:  # 300 detik = 5 menit
                        shutil.rmtree(old_temp, ignore_errors=True)
                except Exception:
                    pass

        with target_path.open("rb") as fk:
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

            try:
                panjang_nama = int.from_bytes(decrypted_first[:2], byteorder="big")
                if panjang_nama > 512:
                    return VaultStatus.WRONG_PASSWORD, None
                if len(decrypted_first) < 2 + panjang_nama:
                    return VaultStatus.ERROR, "File brankas rusak atau terpotong."
                nama_folder = decrypted_first[2 : 2 + panjang_nama].decode("utf-8")
            except Exception:
                return VaultStatus.WRONG_PASSWORD, None

            path_tujuan = base_dir / nama_folder

            if path_tujuan.exists() and not force:
                return VaultStatus.OVERWRITE_NEEDED, nama_folder

            initial_buffer = decrypted_first[2 + panjang_nama :]
            in_stream = DecryptingStream(
                fk,
                decryptor,
                bytes_remaining,
                initial_buffer,
                progress_cb,
                cipher_len,
                first_sz,
                is_cancelled,
            )

            id_temp = uuid.uuid4().hex[:8]
            temp_ext_dir = base_dir / f"._dec_{id_temp}"
            temp_ext_dir.mkdir(parents=True, exist_ok=True)

            try:
                with tarfile.open(fileobj=in_stream, mode="r|") as tar:
                    tar.extractall(path=str(temp_ext_dir), filter="data")

                in_stream.read()

                src = temp_ext_dir / nama_folder
                if not src.exists():
                    raise ValueError("Isi brankas tidak sesuai format ekspektasi.")

                if path_tujuan.exists():
                    hapus_permanen(path_tujuan)

                shutil.move(str(src), str(path_tujuan))

            except InvalidTag:
                return VaultStatus.WRONG_PASSWORD, None
            except InterruptedError:
                return VaultStatus.CANCELLED, "Proses dibatalkan."

        safe_cb(progress_cb, 1.0)
        return VaultStatus.SUCCESS, nama_folder

    except Exception as exc:
        return VaultStatus.ERROR, str(exc)
    finally:
        if temp_ext_dir and temp_ext_dir.exists():
            hapus_permanen(temp_ext_dir)
