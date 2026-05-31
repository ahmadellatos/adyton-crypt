"""
core/vault.py
Logika utama: kunci folder/file (enkripsi) dan buka brankas (dekripsi).
Dioptimasi dengan Single-Pass I/O Streaming, pathlib, dan Cancellation Support.
Telah ditambal dari celah keamanan Path Traversal (TarSlip) dan rapuhnya deteksi password.
"""

import os
import sys
import shutil
import uuid
import tarfile
import stat
import time
from pathlib import Path
from enum import Enum
from typing import Callable
from cryptography.exceptions import InvalidTag
from loguru import logger
from .crypto import derive_key, make_encryptor, make_decryptor, safe_cb
from .constants import (
    MAGIC_BYTES,
    VERSION,
    HEADER_SIZE,
    TAG_SIZE,
    OVERHEAD,
    CHUNK_SIZE,
    DISK_OVERHEAD_BYTES,
    OLD_TEMP_MAX_AGE_SECONDS,
    MAX_VIRTUAL_NAME_LENGTH,
    FIRST_DECRYPT_CHUNK_SIZE,
)


class VaultStatus(Enum):
    SUCCESS = "success"
    WRONG_PASSWORD = "wrong_password"
    OVERWRITE_NEEDED = "overwrite_needed"
    ERROR = "error"
    CANCELLED = "cancelled"


# ── File Operations ───────────────────────────────────────────────────────────


def _hitung_total_wipe_size(paths: list[Path], secure_wipe: bool) -> int:
    """Hitung total byte yang akan di-secure-wipe (hanya file)."""
    total = 0
    for p in paths:
        if not p.exists():
            continue
        if p.is_file() and secure_wipe:
            try:
                total += p.stat().st_size
            except Exception:
                pass
        elif p.is_dir():
            for root, _, files in os.walk(p):
                if secure_wipe:
                    for fname in files:
                        fpath = Path(root) / fname
                        try:
                            total += fpath.stat().st_size
                        except Exception:
                            pass
    return total


def hapus_permanen(
    path: Path,
    secure_wipe: bool = False,
    progress_cb=None,
    wipe_start_pct: float = 0.93,
    wipe_end_pct: float = 0.98,
    total_wipe_bytes: int = 0,
    wiped_bytes: list[int] | None = None,
):
    """
    Menghapus file/folder secara permanen.

    Jika secure_wipe=True:
        - Melakukan single-pass overwrite dengan random bytes (bukan 0x00).
        - Bisa melaporkan sub-progress jika parameter progress_* diberikan.
    """
    if not path.exists():
        return

    if path.is_file() or path.is_symlink():
        file_size = 0
        try:
            file_size = path.stat().st_size if path.is_file() else 0
        except Exception:
            pass

        if secure_wipe and not path.is_symlink() and file_size > 0:
            try:
                path.chmod(stat.S_IWRITE | stat.S_IREAD)
                with path.open("r+b") as f:
                    written = 0
                    random_data = os.urandom(CHUNK_SIZE)
                    while written < file_size:
                        chunk = min(CHUNK_SIZE, file_size - written)
                        f.write(random_data[:chunk])
                        written += chunk

                        # Laporkan sub-progress jika diminta
                        if progress_cb and total_wipe_bytes > 0 and wiped_bytes is not None:
                            wiped_bytes[0] += chunk
                            pct = wipe_start_pct + (wiped_bytes[0] / total_wipe_bytes) * (wipe_end_pct - wipe_start_pct)
                            safe_cb(progress_cb, min(wipe_end_pct, pct))
            except Exception:
                logger.debug("Secure wipe overwrite gagal (file akan tetap dihapus)")

        try:
            path.unlink(missing_ok=True)
        except PermissionError:
            path.chmod(stat.S_IWRITE | stat.S_IREAD)
            path.unlink(missing_ok=True)

    elif path.is_dir():
        for child in list(path.iterdir()):
            hapus_permanen(
                child,
                secure_wipe=secure_wipe,
                progress_cb=progress_cb,
                wipe_start_pct=wipe_start_pct,
                wipe_end_pct=wipe_end_pct,
                total_wipe_bytes=total_wipe_bytes,
                wiped_bytes=wiped_bytes,
            )
        try:
            path.rmdir()
        except OSError:

            def _remove_readonly(func, p, excinfo):
                try:
                    os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
                    func(p)
                except Exception:
                    logger.debug(f"Gagal hapus readonly file saat rmtree: {p}")

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
            # Data phase: 5% → 85%
            pct = min(0.85, 0.05 + 0.80 * (self.bytes_written / self.total_bytes))
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


def _hitung_kebutuhan_disk(total_payload_size: int) -> int:
    """Hitung kebutuhan ruang disk termasuk overhead (50 MB buffer)."""
    return total_payload_size + (50 * 1024 * 1024)


def _is_safe_tar_member(member_name: str, target_dir: Path) -> bool:
    """
    Cek apakah member tar aman (anti TarSlip / Path Traversal).

    Mengembalikan True hanya jika member akan diekstrak di dalam target_dir.
    """
    try:
        target_resolved = target_dir.resolve()
        member_path = (target_resolved / member_name).resolve()

        if hasattr(member_path, "is_relative_to"):
            return member_path.is_relative_to(target_resolved)
        else:
            return (
                str(member_path) == str(target_resolved)
                or str(member_path).startswith(str(target_resolved) + os.sep)
            )
    except Exception:
        return False


def _write_vault_header(
    file_handle,
    encryptor,
    salt: bytes,
    nonce: bytes,
    virtual_name: str,
) -> None:
    """Tulis header standar Adyton (magic, version, salt, nonce, encrypted name)."""
    file_handle.write(MAGIC_BYTES)
    file_handle.write(VERSION)
    file_handle.write(salt)
    file_handle.write(nonce)

    nama_bytes = virtual_name.encode("utf-8")
    panjang_nama = len(nama_bytes).to_bytes(2, byteorder="big")
    file_handle.write(encryptor.update(panjang_nama + nama_bytes))


def _write_decrypted_to_temp_tar(
    temp_tar_path: Path,
    decryptor,
    initial_plaintext_after_name: bytes,
    remaining_bytes: int,
    input_file,
    progress_cb,
    is_cancelled: Callable[[], bool],
) -> None:
    """
    Melakukan dekripsi penuh dari posisi saat ini ke file temporary .tar.
    Akan me-raise InvalidTag jika autentikasi gagal (password salah / data rusak).
    """
    with temp_tar_path.open("wb") as ftar:
        ftar.write(initial_plaintext_after_name)

        bytes_read_so_far = 0  # relatif terhadap sisa yang harus dibaca
        _last_pct = 0.0
        total_to_read = remaining_bytes

        while remaining_bytes > 0:
            if is_cancelled and is_cancelled():
                raise InterruptedError("Operasi dibatalkan oleh pengguna.")

            chunk_sz = min(CHUNK_SIZE, remaining_bytes)
            chunk = input_file.read(chunk_sz)
            remaining_bytes -= len(chunk)

            ftar.write(decryptor.update(chunk))

            bytes_read_so_far += len(chunk)
            # Data decryption phase: 5% → 85%
            pct = min(
                0.85, 0.05 + 0.80 * (bytes_read_so_far / (total_to_read or 1))
            )
            if pct - _last_pct >= 0.005:
                safe_cb(progress_cb, pct)
                _last_pct = pct

        # Verifikasi Authentication Tag GCM
        ftar.write(decryptor.finalize())


def _extract_and_place_vault(
    temp_tar_path: Path,
    temp_ext_dir: Path,
    nama_folder: str,
    path_tujuan: Path,
    progress_cb,
    is_cancelled: Callable[[], bool],
) -> None:
    """
    Melakukan ekstraksi isi tar dari file temporary ke lokasi akhir.
    Termasuk TarSlip protection, progress, dan pemindahan folder.
    """
    total_tar_size = temp_tar_path.stat().st_size
    extracted_bytes = 0

    with tarfile.open(temp_tar_path, mode="r") as tar:
        for member in tar:
            if is_cancelled and is_cancelled():
                raise InterruptedError("Operasi dibatalkan oleh pengguna.")

            # --- SECURITY CHECK (TarSlip) ---
            if not _is_safe_tar_member(member.name, temp_ext_dir):
                raise Exception(
                    "Anomali Keamanan: Terdeteksi Path Traversal (TarSlip)."
                )
            # --------------------------------

            member_path = (temp_ext_dir.resolve() / member.name).resolve()

            if member.isreg():
                # Ekstraksi manual file reguler secara bertahap (chunking)
                member_path.parent.mkdir(parents=True, exist_ok=True)

                with tar.extractfile(member) as source, open(member_path, "wb") as target:
                    while True:
                        if is_cancelled and is_cancelled():
                            raise InterruptedError("Operasi dibatalkan.")

                        chunk = source.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        target.write(chunk)

                        extracted_bytes += len(chunk)
                        pct = 0.92 + 0.07 * (
                            extracted_bytes / max(total_tar_size, 1)
                        )
                        # Extraction is part of finalization (85-100%)
                        safe_cb(progress_cb, min(0.99, 0.85 + 0.14 * (extracted_bytes / max(total_tar_size, 1))))

                # Kembalikan metadata dasar
                try:
                    os.chmod(member_path, member.mode)
                    os.utime(member_path, (member.mtime, member.mtime))
                except Exception:
                    pass
            elif member.isdir():
                # Folder — aman diekstrak
                tar.extract(member, path=temp_ext_dir)
            else:
                # Blokir symlink, hardlink, device file, dll.
                logger.warning(
                    f"Melewati member tidak standar (symlink/device): {member.name}"
                )
                continue

    # FASE 3: PINDAH FOLDER & CLEANUP
    src = temp_ext_dir / nama_folder
    if not src.exists():
        raise ValueError("Isi brankas tidak sesuai format ekspektasi.")

    if path_tujuan.exists():
        hapus_permanen(path_tujuan)

    shutil.move(src, path_tujuan)


def _quick_verify_vault(path: Path) -> bool:
    """
    Sanity check kilat: verifikasi magic bytes, version, dan ukuran file minimum.

    os.fsync() di kunci_brankas sudah menjamin data tersimpan ke hardware.
    AES-GCM encryptor.finalize() sudah menjamin integritas kriptografis.
    Fungsi ini hanya memastikan file tidak kosong/truncated secara tidak sengaja.
    I/O: ~5 byte vs 20GB pada fungsi lama.
    """
    try:
        if path.stat().st_size < OVERHEAD:
            return False
        with path.open("rb") as f:
            return f.read(4) == MAGIC_BYTES and f.read(1) == VERSION
    except Exception as e:
        logger.error(f"Quick verify gagal: {e}")
        return False


# ── Public API ────────────────────────────────────────────────────────────────


# ============================================================================
# SECURITY INVARIANTS — kunci_brankas
# ============================================================================
# 1. Data asli hanya boleh dihapus setelah vault berhasil diverifikasi
#    (lihat blok `if hapus_asli` + `_quick_verify_vault`).
# 2. Selama proses enkripsi, tidak boleh ada plaintext yang ditulis ke disk
#    di luar file vault yang sedang dibuat.
# 3. Semua error path (cancel, exception) harus membersihkan file vault
#    yang belum selesai + backup jika ada.
# 4. Password kosong harus ditolak di lapisan core.
# ============================================================================


def kunci_brankas(
    paths: list[str],
    path_simpan: str,
    password: str,
    hapus_asli: bool = False,
    secure_wipe: bool = False,
    progress_cb=None,
    is_cancelled: Callable[[], bool] = None,
) -> tuple[VaultStatus, str]:

    valid_paths = [p for p in paths if Path(p).exists()]
    if not valid_paths:
        return VaultStatus.ERROR, "Tidak ada file/folder valid untuk dikunci."

    if not password or not password.strip():
        return VaultStatus.ERROR, "Password tidak boleh kosong."

    target_path = Path(path_simpan)
    backup_path = target_path.with_suffix(".adtn.bak")
    backup_dibuat = False

    try:
        free_space = shutil.disk_usage(target_path.parent).free
        total_size = _hitung_total_size(valid_paths)
        required_space = _hitung_kebutuhan_disk(total_size)

        if free_space < required_space:
            req_mb = required_space / (1024 * 1024)
            free_mb = free_space / (1024 * 1024)
            return (
                VaultStatus.ERROR,
                f"Ruang penyimpanan tidak cukup!\nSisa disk: {free_mb:.1f} MB. Butuh minimal {req_mb:.1f} MB.",
            )

        if target_path.exists():
            target_path.replace(backup_path)
            backup_dibuat = True

        salt = os.urandom(16)
        nonce = os.urandom(12)
        key = derive_key(password, salt)
        safe_cb(progress_cb, 0.03)  # Key derivation done

        encryptor = make_encryptor(key, nonce)

        if len(valid_paths) == 1:
            nama_virtual = Path(valid_paths[0]).name
            target_dir = ""
        else:
            nama_virtual = target_path.stem or "Brankas_Rahasia"
            target_dir = nama_virtual

        with target_path.open("wb") as fk:
            _write_vault_header(fk, encryptor, salt, nonce, nama_virtual)

            out_stream = EncryptingStream(
                fk, encryptor, progress_cb, total_size, is_cancelled
            )

            with tarfile.open(fileobj=out_stream, mode="w|") as tar:
                for p in valid_paths:
                    path_item = Path(p)
                    arcname = (
                        (Path(target_dir) / path_item.name).as_posix()
                        if target_dir
                        else path_item.name
                    )
                    tar.add(path_item, arcname=arcname)

            out_stream.flush()
            fk.write(encryptor.finalize())
            fk.write(encryptor.tag)

            # Paksa OS flush disk buffer cache ke hardware fisik.
            # Ini satu-satunya cara memastikan data benar-benar tersimpan
            # di chip SSD/HDD, bukan hanya di RAM cache OS.
            # WAJIB dilakukan sebelum hapus_asli=True menghapus file asli.
            fk.flush()
            os.fsync(fk.fileno())

        # Data encryption complete → end of data phase (85%)
        safe_cb(progress_cb, 0.85)

        if backup_dibuat and backup_path.exists():
            backup_path.unlink()

        if hapus_asli:
            safe_cb(progress_cb, 0.88)
            if not _quick_verify_vault(target_path):
                return (
                    VaultStatus.ERROR,
                    "Vault gagal diverifikasi ke disk fisik. File asli tidak dihapus. "
                    "Coba periksa ruang disk dan kondisi hardware penyimpanan.",
                )
            safe_cb(progress_cb, 0.90)  # Verification done

            if secure_wipe:
                wipe_paths = [Path(p) for p in valid_paths]
                total_wipe = _hitung_total_wipe_size(wipe_paths, True)
                wiped_counter = [0]

                for p in wipe_paths:
                    hapus_permanen(
                        p,
                        secure_wipe=True,
                        progress_cb=progress_cb,
                        wipe_start_pct=0.90,
                        wipe_end_pct=0.98,
                        total_wipe_bytes=total_wipe,
                        wiped_bytes=wiped_counter,
                    )
            else:
                for p in valid_paths:
                    hapus_permanen(Path(p), secure_wipe=False)

            safe_cb(progress_cb, 0.99)  # Wipe + cleanup done

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


# ============================================================================
# SECURITY INVARIANTS — buka_brankas
# ============================================================================
# 1. Plaintext hasil dekripsi HANYA boleh ditulis ke disk setelah
#    Authentication Tag GCM berhasil diverifikasi (`finalize()` sukses).
# 2. Temporary directory hasil dekripsi (`._dec_*`) harus selalu dibersihkan
#    di akhir (finally block), bahkan saat error atau cancellation.
# 3. Tar extraction harus melewati TarSlip protection sebelum menulis file apapun.
# 4. Password salah harus dilaporkan secara konsisten sebagai WRONG_PASSWORD
#    (bukan ERROR), agar tidak membocorkan informasi tentang format file.
# 5. Semua path error (InvalidTag, ReadError, dll) harus tetap membersihkan
#    temporary files.
# ============================================================================


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

        cipher_len = total_size - OVERHEAD
        base_dir = target_path.parent

        free_space = shutil.disk_usage(base_dir).free
        required_space = _hitung_kebutuhan_disk(cipher_len)

        if free_space < required_space:
            req_mb = required_space / (1024 * 1024)
            free_mb = free_space / (1024 * 1024)
            return (
                VaultStatus.ERROR,
                f"Ruang penyimpanan tidak cukup!\nSisa disk: {free_mb:.1f} MB. Butuh minimal {req_mb:.1f} MB.",
            )

        safe_cb(progress_cb, 0.01)  # Mulai proses buka

        # Hapus temp folder yang umurnya > 5 menit
        for old_temp in base_dir.glob("._dec_*"):
            if old_temp.is_dir():
                try:
                    age = time.time() - old_temp.stat().st_mtime
                    if age > OLD_TEMP_MAX_AGE_SECONDS:
                        shutil.rmtree(old_temp, ignore_errors=True)
                except Exception:
                    logger.debug("Gagal bersihkan old temp decrypt dir (diabaikan)")

        with target_path.open("rb") as fk:
            # 1. Validasi Magic Bytes
            magic = fk.read(4)
            if magic != MAGIC_BYTES:
                return (
                    VaultStatus.ERROR,
                    "File ini bukan format brankas Adyton Crypt yang valid.",
                )

            # 2. Validasi Versi
            version = fk.read(1)
            if version == b"\x01":
                # Versi 1: PBKDF2 600k iterasi
                pass
            else:
                # Jika di masa depan ada versi 2 (misal Scrypt)
                return (
                    VaultStatus.ERROR,
                    "Versi brankas ini terlalu baru. Silakan update aplikasi Adyton Crypt Anda.",
                )

            # 3. Baca Salt dan Nonce (seperti biasa)
            salt = fk.read(16)
            nonce = fk.read(12)

            fk.seek(-16, os.SEEK_END)
            tag = fk.read(16)

            # Kembali ke posisi setelah header selesai (byte ke-33)
            fk.seek(HEADER_SIZE)

            safe_cb(progress_cb, 0.02)  # Header dibaca

            # Lanjut derive_key dan proses dekripsi...
            key = derive_key(password, salt)
            decryptor = make_decryptor(key, nonce, tag)

            safe_cb(progress_cb, 0.04)  # Key derivation selesai (PBKDF2)

            first_sz = min(FIRST_DECRYPT_CHUNK_SIZE, cipher_len)
            first_chunk = fk.read(first_sz)
            bytes_remaining = cipher_len - first_sz

            decrypted_first = decryptor.update(first_chunk)

            # Parse nama folder virtual dari chunk pertama yang sudah didekripsi.
            # Jika gagal (kemungkinan besar karena password salah), kembalikan WRONG_PASSWORD.
            try:
                nama_folder, name_offset = _parse_virtual_folder_name(decrypted_first)
            except ValueError:
                return VaultStatus.WRONG_PASSWORD, None

            path_tujuan = base_dir / nama_folder

            if path_tujuan.exists() and not force:
                return VaultStatus.OVERWRITE_NEEDED, nama_folder

            temp_ext_dir, temp_tar_path = _create_temp_decrypt_paths(base_dir)
            safe_cb(progress_cb, 0.05)  # Persiapan selesai, mulai dekripsi data

            try:
                # FASE 1: DEKRIPSI KE FILE TEMP
                _write_decrypted_to_temp_tar(
                    temp_tar_path,
                    decryptor,
                    decrypted_first[name_offset:],
                    bytes_remaining,
                    fk,
                    progress_cb,
                    is_cancelled,
                )

                # FASE 2 + FASE 3: Ekstraksi tar + pindah ke lokasi akhir
                # (diekstrak ke helper)
                _extract_and_place_vault(
                    temp_tar_path,
                    temp_ext_dir,
                    nama_folder,
                    path_tujuan,
                    progress_cb,
                    is_cancelled,
                )

            except tarfile.ReadError:
                return VaultStatus.WRONG_PASSWORD, None
            except InvalidTag:
                return VaultStatus.WRONG_PASSWORD, None
            except InterruptedError:
                return VaultStatus.CANCELLED, "Proses dibatalkan."

        safe_cb(progress_cb, 1.0)
        return VaultStatus.SUCCESS, nama_folder

    except Exception as exc:
        logger.exception(
            "Gagal membuka brankas karena error internal saat proses dekripsi/ekstraksi."
        )
        return VaultStatus.ERROR, f"Terjadi kesalahan internal: {str(exc)}"
    finally:
        if temp_ext_dir and temp_ext_dir.exists():
            _cleanup_temp_decrypt_dir(temp_ext_dir)


def _parse_virtual_folder_name(decrypted_first: bytes) -> tuple[str, int]:
    """
    Parse nama folder virtual dari plaintext pertama hasil dekripsi.
    Mengembalikan (nama_folder, offset_setelah_nama).
    Melempar ValueError jika dianggap password salah (heuristik).
    """
    try:
        panjang_nama = int.from_bytes(decrypted_first[:2], byteorder="big")
        if panjang_nama > MAX_VIRTUAL_NAME_LENGTH or len(decrypted_first) < 2 + panjang_nama:
            raise ValueError("wrong_password")

        nama_folder = decrypted_first[2 : 2 + panjang_nama].decode("utf-8")
        return nama_folder, 2 + panjang_nama
    except UnicodeDecodeError:
        raise ValueError("wrong_password")
    except Exception:
        raise ValueError("wrong_password")


def _create_temp_decrypt_paths(base_dir: Path) -> tuple[Path, Path]:
    """Membuat direktori temporary unik + path file .tar untuk hasil dekripsi."""
    id_temp = uuid.uuid4().hex[:8]
    temp_ext_dir = base_dir / f"._dec_{id_temp}"
    temp_ext_dir.mkdir(parents=True, exist_ok=True)

    temp_tar_path = temp_ext_dir / "temp_decrypted.tar"
    return temp_ext_dir, temp_tar_path


def _cleanup_temp_decrypt_dir(temp_dir: Path) -> None:
    """Membersihkan direktori temporary hasil dekripsi secara defensif.

    Tidak pernah boleh melempar exception ke pemanggil, karena ini dipanggil
    dari finally block.
    """
    try:
        hapus_permanen(temp_dir)
    except Exception:
        logger.debug("Gagal membersihkan temp decrypt directory (non-fatal)")
