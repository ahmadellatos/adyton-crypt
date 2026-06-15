"""
core/vault.py
Logika utama: kunci folder/file (enkripsi) dan buka brankas (dekripsi).
Dioptimasi dengan Single-Pass I/O Streaming, pathlib, dan Cancellation Support.
Telah ditambal dari celah keamanan Path Traversal (TarSlip) dan rapuhnya deteksi password.
"""

import contextlib
import os
import shutil
import stat
import tarfile
import time
import uuid
from collections.abc import Callable
from enum import Enum
from pathlib import Path, PureWindowsPath

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from loguru import logger

from .constants import (
    ARGON2ID_ITERATIONS,
    ARGON2ID_LANES,
    ARGON2ID_MAX_ITERATIONS,
    ARGON2ID_MAX_LANES,
    ARGON2ID_MAX_MEMORY_COST_KIB,
    ARGON2ID_MEMORY_COST_KIB,
    ARGON2ID_PARAMS_SIZE,
    CHUNK_RECORD_HEADER_SIZE,
    CHUNK_RECORD_OVERHEAD,
    CHUNK_SIZE,
    DISK_OVERHEAD_BYTES,
    FIRST_DECRYPT_CHUNK_SIZE,
    HEADER_SIZE,
    HEADER_SIZE_V2,
    KDF_ID_ARGON2ID,
    KDF_ID_PBKDF2_SHA256,
    MAGIC_BYTES,
    MAX_VIRTUAL_NAME_LENGTH,
    OLD_TEMP_MAX_AGE_SECONDS,
    OVERHEAD,
    OVERHEAD_V1,
    RECORD_TYPE_DATA,
    RECORD_TYPE_FINAL,
    RECORD_TYPE_METADATA,
    TAG_SIZE,
    V2_FLAG_KDF_PARAMS,
    V2_FLAG_NONE,
    V2_KDF_SECTION_HEADER_SIZE,
    V2_SUPPORTED_FLAGS,
    VERSION_V1,
    VERSION_V2,
)
from .crypto import (
    derive_key,
    derive_key_argon2id,
    derive_key_for_kdf,
    make_decryptor,
    safe_cb,
)


class VaultStatus(Enum):
    SUCCESS = "success"
    WRONG_PASSWORD = "wrong_password"  # nosec B105
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
            with contextlib.suppress(Exception):
                total += p.stat().st_size
        elif p.is_dir():
            for root, _, files in os.walk(p):
                if secure_wipe:
                    for fname in files:
                        fpath = Path(root) / fname
                        with contextlib.suppress(Exception):
                            total += fpath.stat().st_size
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
        with contextlib.suppress(Exception):
            file_size = path.stat().st_size if path.is_file() else 0

        if secure_wipe and not path.is_symlink() and file_size > 0:
            try:
                path.chmod(stat.S_IWRITE | stat.S_IREAD)
                with path.open("r+b") as f:
                    written = 0
                    while written < file_size:
                        chunk = min(CHUNK_SIZE, file_size - written)
                        # Generate fresh random data per chunk — jangan reuse blok
                        # yang sama untuk file > CHUNK_SIZE (lebih aman dan unpredictable)
                        f.write(os.urandom(chunk))
                        written += chunk

                        # Laporkan sub-progress jika diminta
                        if progress_cb and total_wipe_bytes > 0 and wiped_bytes is not None:
                            wiped_bytes[0] += chunk
                            pct = wipe_start_pct + (wiped_bytes[0] / total_wipe_bytes) * (
                                wipe_end_pct - wipe_start_pct
                            )
                            safe_cb(progress_cb, min(wipe_end_pct, pct))

                    f.flush()
                    os.fsync(f.fileno())
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
            raise InterruptedError("Operation cancelled by the user.")

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
                f.stat().st_size for f in path.rglob("*") if f.is_file() and not f.is_symlink()
            )
    return total or 1


def _round_up_tar_block(size: int) -> int:
    """Bulatkan ukuran payload member tar ke blok 512 byte."""
    return ((size + 511) // 512) * 512


def _estimate_tar_member_size(path: Path) -> int:
    """Estimasi konservatif ukuran satu member tar beserta payload-nya."""
    size = 512  # header tar per member
    try:
        if path.is_file() and not path.is_symlink():
            size += _round_up_tar_block(path.stat().st_size)
    except OSError:
        pass
    return size


def _estimate_tar_plaintext_size(paths: list[str], target_dir: str = "") -> int:
    """Estimasi ukuran plaintext tar yang akan dienkripsi.

    Estimasi ini sengaja konservatif agar pemeriksaan ruang disk tidak terlalu
    optimistis pada folder dengan banyak file kecil. Tar menambah header 512
    byte untuk tiap member dan membulatkan payload file ke kelipatan 512 byte.
    """
    total = 1024  # dua blok kosong penutup arsip tar

    for p in paths:
        root_path = Path(p)
        if not root_path.exists():
            continue

        total += _estimate_tar_member_size(root_path)

        if root_path.is_dir() and not root_path.is_symlink():
            for current_root, dirs, files in os.walk(root_path):
                current = Path(current_root)

                for dirname in dirs:
                    total += _estimate_tar_member_size(current / dirname)

                for filename in files:
                    total += _estimate_tar_member_size(current / filename)

    return max(total, 1024)


def _hitung_kebutuhan_disk_kunci(
    paths: list[str],
    virtual_name: str,
    target_dir: str = "",
) -> int:
    """Hitung kebutuhan ruang disk saat membuat vault v2 chunked AEAD.

    AES-GCM per record menambah 16-byte tag per metadata/data/final record,
    ditambah header record 13 byte. Estimasi plaintext tar tetap konservatif
    untuk banyak file kecil.
    """
    metadata_size = 2 + len(virtual_name.encode("utf-8"))
    estimated_tar_size = _estimate_tar_plaintext_size(paths, target_dir)
    data_records = max(1, (estimated_tar_size + CHUNK_SIZE - 1) // CHUNK_SIZE)
    return (
        HEADER_SIZE_V2
        + V2_KDF_SECTION_HEADER_SIZE
        + ARGON2ID_PARAMS_SIZE
        + CHUNK_RECORD_OVERHEAD  # metadata record
        + metadata_size
        + (data_records * CHUNK_RECORD_OVERHEAD)
        + estimated_tar_size
        + CHUNK_RECORD_OVERHEAD  # final record
        + DISK_OVERHEAD_BYTES
    )


def _hitung_kebutuhan_disk_buka(cipher_len: int) -> int:
    """Hitung kebutuhan ruang disk saat membuka vault.

    Setelah tag GCM valid, proses buka menyimpan temporary tar plaintext dan
    mengekstraknya ke folder sementara sebelum dipindahkan ke lokasi akhir.
    Karena itu kebutuhan ruang bisa mendekati 2x payload, bukan hanya ukuran
    ciphertext.
    """
    return (cipher_len * 2) + DISK_OVERHEAD_BYTES


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
            return str(member_path) == str(target_resolved) or str(member_path).startswith(
                str(target_resolved) + os.sep
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
    """Tulis header Adyton v1 lama (dipertahankan untuk kompatibilitas internal)."""
    file_handle.write(MAGIC_BYTES)
    file_handle.write(VERSION_V1)
    file_handle.write(salt)
    file_handle.write(nonce)

    nama_bytes = virtual_name.encode("utf-8")
    panjang_nama = len(nama_bytes).to_bytes(2, byteorder="big")
    file_handle.write(encryptor.update(panjang_nama + nama_bytes))


def _v2_header_context(
    salt: bytes,
    file_id: bytes,
    chunk_size: int,
    flags: int = V2_FLAG_NONE,
    kdf_section: bytes = b"",
) -> bytes:
    """Bytes header v2 yang juga dipakai sebagai konteks AAD setiap record.

    Untuk v2 legacy, ``kdf_section`` kosong dan KDF dianggap PBKDF2.
    Untuk vault baru, ``flags`` memuat ``V2_FLAG_KDF_PARAMS`` dan section ini
    menyimpan ``kdf_id + kdf_params``. Seluruh header, termasuk parameter KDF,
    diikat ke AAD setiap record agar tidak bisa ditukar diam-diam.
    """
    return (
        MAGIC_BYTES
        + VERSION_V2
        + salt
        + file_id
        + chunk_size.to_bytes(4, byteorder="big")
        + flags.to_bytes(4, byteorder="big")
        + kdf_section
    )


def _encode_argon2id_params(
    iterations: int = ARGON2ID_ITERATIONS,
    lanes: int = ARGON2ID_LANES,
    memory_cost: int = ARGON2ID_MEMORY_COST_KIB,
) -> bytes:
    """Encode parameter Argon2id ke format header v2 extended."""
    for value in (iterations, lanes, memory_cost):
        if value <= 0 or value >= 2**32:
            raise ValueError("Argon2id parameter out of range.")

    return (
        iterations.to_bytes(4, byteorder="big")
        + lanes.to_bytes(4, byteorder="big")
        + memory_cost.to_bytes(4, byteorder="big")
    )


def _decode_argon2id_params(params: bytes) -> dict[str, int]:
    """Decode parameter Argon2id dari header v2 extended."""
    if len(params) != ARGON2ID_PARAMS_SIZE:
        raise ValueError("Invalid Argon2id parameter size.")

    iterations = int.from_bytes(params[0:4], byteorder="big")
    lanes = int.from_bytes(params[4:8], byteorder="big")
    memory_cost = int.from_bytes(params[8:12], byteorder="big")

    if iterations <= 0 or lanes <= 0 or memory_cost <= 0:
        raise ValueError("Invalid Argon2id parameter.")

    # Reject crafted headers that request absurd cost factors. Without this an
    # attacker-supplied vault could make Argon2id allocate gigabytes/terabytes
    # and OOM the app the moment someone tries to open it.
    if (
        iterations > ARGON2ID_MAX_ITERATIONS
        or lanes > ARGON2ID_MAX_LANES
        or memory_cost > ARGON2ID_MAX_MEMORY_COST_KIB
    ):
        raise ValueError("Argon2id parameters exceed the safe maximum.")

    return {
        "iterations": iterations,
        "lanes": lanes,
        "memory_cost": memory_cost,
    }


def _v2_kdf_section(kdf_id: int, params: bytes) -> bytes:
    """Bangun section KDF untuk header v2 extended."""
    if not 0 <= kdf_id <= 255:
        raise ValueError("kdf_id out of range")
    if len(params) >= 2**16:
        raise ValueError("KDF parameter too long")
    return bytes([kdf_id]) + len(params).to_bytes(2, byteorder="big") + params


def _v2_parse_kdf_section(
    file_handle,
    flags: int,
) -> tuple[int, dict[str, int], bytes]:
    """Parse KDF section dari v2 header.

    Mengembalikan ``(kdf_id, params_dict, kdf_section_raw)``. Vault v2 lama
    tidak memiliki section ini dan diperlakukan sebagai PBKDF2 legacy.
    """
    if flags & ~V2_SUPPORTED_FLAGS:
        raise ValueError("This vault flag isn't supported by this app version.")

    if not (flags & V2_FLAG_KDF_PARAMS):
        return KDF_ID_PBKDF2_SHA256, {}, b""

    raw_header = _v2_read_exact(file_handle, V2_KDF_SECTION_HEADER_SIZE)
    kdf_id = raw_header[0]
    params_len = int.from_bytes(raw_header[1:3], byteorder="big")
    params_raw = _v2_read_exact(file_handle, params_len)
    kdf_section = raw_header + params_raw

    if kdf_id == KDF_ID_ARGON2ID:
        return kdf_id, _decode_argon2id_params(params_raw), kdf_section

    if kdf_id == KDF_ID_PBKDF2_SHA256:
        # Reserved for future explicit PBKDF2 headers. Current legacy v2 uses no section.
        if len(params_raw) != 4:
            raise ValueError("Invalid PBKDF2 parameter.")
        iterations = int.from_bytes(params_raw, byteorder="big")
        if iterations <= 0:
            raise ValueError("Invalid PBKDF2 parameter.")
        return kdf_id, {"iterations": iterations}, kdf_section

    raise ValueError("This vault KDF isn't supported by this app version.")


def _v2_record_header(record_type: int, record_index: int, plaintext_len: int) -> bytes:
    if not 0 <= record_type <= 255:
        raise ValueError("record_type out of range")
    if record_index < 0 or record_index >= 2**64:
        raise ValueError("record_index out of range")
    if plaintext_len < 0 or plaintext_len >= 2**32:
        raise ValueError("plaintext_len out of range")
    return (
        record_type.to_bytes(1, byteorder="big")
        + record_index.to_bytes(8, byteorder="big")
        + plaintext_len.to_bytes(4, byteorder="big")
    )


def _v2_nonce(record_index: int) -> bytes:
    """Nonce AES-GCM 96-bit deterministik per record.

    Aman karena key setiap vault unik dari salt+password, dan setiap record
    dalam vault yang sama memakai indeks unik yang diverifikasi berurutan.
    """
    if record_index < 0 or record_index >= 2**96:
        raise ValueError("record_index out of nonce range")
    return record_index.to_bytes(12, byteorder="big")


def _v2_aad(header_context: bytes, record_header: bytes) -> bytes:
    return header_context + record_header


def _v2_write_record(
    file_handle,
    aesgcm: AESGCM,
    header_context: bytes,
    record_type: int,
    record_index: int,
    plaintext: bytes,
) -> None:
    record_header = _v2_record_header(record_type, record_index, len(plaintext))
    ciphertext = aesgcm.encrypt(
        _v2_nonce(record_index),
        plaintext,
        _v2_aad(header_context, record_header),
    )
    file_handle.write(record_header)
    file_handle.write(ciphertext)


def _v2_read_exact(file_handle, size: int) -> bytes:
    data = file_handle.read(size)
    if len(data) != size:
        raise InvalidTag
    return data


def _v2_read_record_header(file_handle) -> tuple[int, int, int, bytes]:
    raw = _v2_read_exact(file_handle, CHUNK_RECORD_HEADER_SIZE)
    record_type = raw[0]
    record_index = int.from_bytes(raw[1:9], byteorder="big")
    plaintext_len = int.from_bytes(raw[9:13], byteorder="big")
    return record_type, record_index, plaintext_len, raw


class ChunkedAEADEncryptingStream:
    """File-like writer untuk tarfile yang mengenkripsi output sebagai record v2.

    Setiap data chunk dienkripsi dengan AES-GCM sendiri. Saat dibuka, setiap
    chunk harus lolos verifikasi tag sebelum plaintext chunk itu boleh ditulis
    ke disk. Ini menghindari two-pass decrypt tanpa kembali ke plaintext
    unauthenticated.
    """

    def __init__(
        self,
        target_file,
        aesgcm: AESGCM,
        header_context: bytes,
        progress_cb,
        total_bytes: int,
        is_cancelled: Callable[[], bool] = None,
        chunk_size: int = CHUNK_SIZE,
    ):
        self.target_file = target_file
        self.aesgcm = aesgcm
        self.header_context = header_context
        self.progress_cb = progress_cb
        self.total_bytes = total_bytes
        self.chunk_size = chunk_size
        self.is_cancelled = is_cancelled
        self.buffer = bytearray()
        self.bytes_written = 0
        self.record_index = 1  # index 0 dipakai metadata
        self._last_pct = 0.0
        self._finished = False

    def write(self, data: bytes):
        if self.is_cancelled and self.is_cancelled():
            raise InterruptedError("Operation cancelled by the user.")

        self.buffer.extend(data)
        self.bytes_written += len(data)

        while len(self.buffer) >= self.chunk_size:
            self._emit_data_record(bytes(self.buffer[: self.chunk_size]))
            del self.buffer[: self.chunk_size]

        if self.total_bytes > 0:
            pct = min(0.85, 0.05 + 0.80 * (self.bytes_written / self.total_bytes))
            if pct - self._last_pct >= 0.005:
                safe_cb(self.progress_cb, pct)
                self._last_pct = pct

        return len(data)

    def _emit_data_record(self, plaintext: bytes) -> None:
        _v2_write_record(
            self.target_file,
            self.aesgcm,
            self.header_context,
            RECORD_TYPE_DATA,
            self.record_index,
            plaintext,
        )
        self.record_index += 1

    def flush(self):
        # Jangan flush buffer parsial di sini; tarfile bisa memanggil flush() untuk
        # sinkronisasi, bukan sebagai akhir stream. Record parsial ditutup di finish().
        return

    def close(self):
        return

    def finish(self) -> None:
        if self._finished:
            return
        if self.buffer:
            self._emit_data_record(bytes(self.buffer))
            self.buffer.clear()
        _v2_write_record(
            self.target_file,
            self.aesgcm,
            self.header_context,
            RECORD_TYPE_FINAL,
            self.record_index,
            b"",
        )
        self._finished = True


def _verify_gcm_before_plaintext_write(
    input_file,
    key: bytes,
    nonce: bytes,
    tag: bytes,
    cipher_len: int,
    progress_cb,
    is_cancelled: Callable[[], bool],
) -> bytes:
    """
    Verifikasi seluruh ciphertext AES-GCM sebelum plaintext ditulis ke disk.

    Fungsi ini melakukan pass pertama dekripsi ke memori/sink saja, lalu memanggil
    ``finalize()``. Output plaintext tidak pernah ditulis ke file pada fase ini.
    Setelah fungsi ini sukses, caller boleh melakukan pass kedua untuk menulis
    plaintext ke temporary tar.
    """
    input_file.seek(HEADER_SIZE)
    decryptor = make_decryptor(key, nonce, tag)

    first_sz = min(FIRST_DECRYPT_CHUNK_SIZE, cipher_len)
    first_chunk = input_file.read(first_sz)
    if len(first_chunk) != first_sz:
        raise InvalidTag

    first_plaintext = decryptor.update(first_chunk)

    remaining_bytes = cipher_len - first_sz
    bytes_verified = first_sz
    _last_pct = 0.0

    while remaining_bytes > 0:
        if is_cancelled and is_cancelled():
            raise InterruptedError("Operation cancelled by the user.")

        chunk_sz = min(CHUNK_SIZE, remaining_bytes)
        chunk = input_file.read(chunk_sz)
        if not chunk:
            raise InvalidTag

        remaining_bytes -= len(chunk)
        bytes_verified += len(chunk)

        # Plaintext sengaja dibuang. Tujuannya hanya autentikasi GCM.
        decryptor.update(chunk)

        # Verification phase: 5% → 45%
        pct = min(0.45, 0.05 + 0.40 * (bytes_verified / max(cipher_len, 1)))
        if pct - _last_pct >= 0.005:
            safe_cb(progress_cb, pct)
            _last_pct = pct

    # Titik keamanan utama: tag GCM harus valid sebelum ada plaintext di disk.
    first_plaintext += decryptor.finalize()
    safe_cb(progress_cb, 0.45)
    return first_plaintext


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
    Melakukan pass kedua dekripsi ke file temporary .tar.

    PRECONDITION: seluruh ciphertext dari vault yang sama sudah lolos
    autentikasi GCM lewat ``_verify_gcm_before_plaintext_write``. Karena itu
    plaintext baru ditulis ke disk setelah tag GCM valid pada pass pertama.
    Pass kedua tetap memanggil ``finalize()`` sebagai guard tambahan.
    """
    with temp_tar_path.open("wb") as ftar:
        ftar.write(initial_plaintext_after_name)

        bytes_read_so_far = 0  # relatif terhadap sisa yang harus dibaca
        _last_pct = 0.0
        total_to_read = remaining_bytes

        while remaining_bytes > 0:
            if is_cancelled and is_cancelled():
                raise InterruptedError("Operation cancelled by the user.")

            chunk_sz = min(CHUNK_SIZE, remaining_bytes)
            chunk = input_file.read(chunk_sz)
            if not chunk:
                raise InvalidTag
            remaining_bytes -= len(chunk)

            ftar.write(decryptor.update(chunk))

            bytes_read_so_far += len(chunk)
            # Authenticated plaintext write phase: 45% → 85%
            pct = min(0.85, 0.45 + 0.40 * (bytes_read_so_far / (total_to_read or 1)))
            if pct - _last_pct >= 0.005:
                safe_cb(progress_cb, pct)
                _last_pct = pct

        # Guard tambahan: memastikan pass kedua membaca ciphertext yang konsisten.
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
                raise InterruptedError("Operation cancelled by the user.")

            # --- SECURITY CHECK (TarSlip) ---
            if not _is_safe_tar_member(member.name, temp_ext_dir):
                raise Exception("Security anomaly: path traversal (TarSlip) detected.")
            # --------------------------------

            member_path = (temp_ext_dir.resolve() / member.name).resolve()

            if member.isreg():
                # Ekstraksi manual file reguler secara bertahap (chunking)
                member_path.parent.mkdir(parents=True, exist_ok=True)

                with tar.extractfile(member) as source, open(member_path, "wb") as target:
                    while True:
                        if is_cancelled and is_cancelled():
                            raise InterruptedError("Operation cancelled by the user.")

                        chunk = source.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        target.write(chunk)

                        extracted_bytes += len(chunk)
                        pct = min(
                            0.99,
                            0.85 + 0.14 * (extracted_bytes / max(total_tar_size, 1)),
                        )
                        safe_cb(progress_cb, pct)

                # Kembalikan metadata dasar
                with contextlib.suppress(Exception):
                    os.chmod(member_path, member.mode)
                    os.utime(member_path, (member.mtime, member.mtime))
            elif member.isdir():
                # Folder — aman diekstrak
                # filter="data" wajib di Python 3.14+ (default berubah dari None)
                tar.extract(member, path=temp_ext_dir, filter="data")
            else:
                # Blokir symlink, hardlink, device file, dll.
                logger.warning(f"Melewati member tidak standar (symlink/device): {member.name}")
                continue

    # FASE 3: PINDAH FOLDER & CLEANUP
    src = temp_ext_dir / nama_folder
    if not src.exists():
        raise ValueError("Vault contents don't match the expected format.")

    backup_existing: Path | None = None
    if path_tujuan.exists():
        # Force-overwrite dibuat transactional: data lama dipindahkan dulu ke
        # staging backup di direktori yang sama, hasil ekstraksi dipasang ke
        # path final, lalu backup lama baru dihapus setelah move sukses.
        backup_existing = _make_unique_replace_backup_path(path_tujuan)
        path_tujuan.rename(backup_existing)

    try:
        shutil.move(src, path_tujuan)
    except Exception:
        # Jangan biarkan data lama hilang jika pemindahan hasil ekstraksi gagal.
        # Jika move meninggalkan target parsial, singkirkan dulu sebelum restore.
        if path_tujuan.exists():
            try:
                hapus_permanen(path_tujuan)
            except Exception:
                logger.warning("Gagal membersihkan target parsial saat rollback overwrite.")
        if backup_existing and backup_existing.exists() and not path_tujuan.exists():
            backup_existing.rename(path_tujuan)
        raise

    if backup_existing and backup_existing.exists():
        hapus_permanen(backup_existing)


def _quick_verify_vault(path: Path) -> bool:
    """
    Sanity check kilat: verifikasi magic bytes, version, dan ukuran file minimum.

    os.fsync() di kunci_brankas sudah menjamin data tersimpan ke hardware.
    Untuk v2 chunked AEAD, setiap record sudah mendapat tag GCM sendiri saat
    ditulis. Fungsi ini tetap hanya sanity check cepat, bukan full read-back.
    """
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if f.read(4) != MAGIC_BYTES:
                return False
            version = f.read(1)

        if version == VERSION_V1:
            return size >= OVERHEAD_V1
        if version == VERSION_V2:
            # Header v2 legacy + minimal metadata record + final record.
            # Extended Argon2id header is larger, so this remains a safe lower bound.
            return size >= HEADER_SIZE_V2 + (2 * CHUNK_RECORD_OVERHEAD)
        return False
    except Exception as e:
        logger.error(f"Quick verify gagal: {e}")
        return False


def _target_conflicts_with_source(target_path: Path, source_path: Path) -> bool:
    """Return True if target vault would be written over/inside a source item.

    This prevents data loss when ``hapus_asli=True``: a vault saved inside a
    selected folder would be deleted together with the original folder after a
    successful lock operation. The check is kept unconditional because writing
    the output into the input tree can also make tar include a partial vault.
    """
    target_resolved = target_path.resolve(strict=False)
    source_resolved = source_path.resolve(strict=False)

    if target_resolved == source_resolved:
        return True

    return source_path.is_dir() and target_resolved.is_relative_to(source_resolved)


def _make_unique_backup_path(target_path: Path) -> Path:
    """Buat path backup unik tanpa menimpa file backup yang sudah ada."""
    for _ in range(100):
        candidate = target_path.with_name(f"{target_path.name}.bak-{uuid.uuid4().hex[:8]}")
        if not candidate.exists():
            return candidate
    raise FileExistsError("Couldn't create a unique backup name for the old vault.")


def _make_unique_replace_backup_path(target_path: Path) -> Path:
    """Buat path staging backup untuk force-overwrite tanpa menimpa data lama."""
    for _ in range(100):
        candidate = target_path.with_name(f"{target_path.name}.replace-{uuid.uuid4().hex[:8]}")
        if not candidate.exists():
            return candidate
    raise FileExistsError("Couldn't create a unique staging backup for the old data.")


def _validate_virtual_folder_name(name: str) -> str:
    """Validasi nama root hasil dekripsi sebelum dipakai sebagai path tujuan."""
    if not name or name in {".", ".."}:
        raise ValueError("invalid_virtual_name")

    if len(name.encode("utf-8")) > MAX_VIRTUAL_NAME_LENGTH:
        raise ValueError("invalid_virtual_name")

    if any(ord(ch) < 32 for ch in name):
        raise ValueError("invalid_virtual_name")

    if "/" in name or "\\" in name:
        raise ValueError("invalid_virtual_name")

    if Path(name).is_absolute() or PureWindowsPath(name).is_absolute():
        raise ValueError("invalid_virtual_name")

    if any(ch in name for ch in '<>:"|?*'):
        raise ValueError("invalid_virtual_name")

    stripped = name.rstrip(" .")
    if stripped != name or not stripped:
        raise ValueError("invalid_virtual_name")

    windows_reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    windows_basename = stripped.split(".", 1)[0].upper()
    if windows_basename in windows_reserved:
        raise ValueError("invalid_virtual_name")

    # Hindari benturan dengan pola direktori temp internal yang dibersihkan otomatis.
    if name.startswith("._dec_"):
        raise ValueError("invalid_virtual_name")

    return name


def _buka_brankas_v2_from_open_file(
    fk,
    target_path: Path,
    total_size: int,
    password: str,
    force: bool,
    progress_cb,
    is_cancelled: Callable[[], bool] | None,
) -> tuple[VaultStatus, str | None]:
    """Buka vault format v2 chunked AEAD.

    Security invariant v2:
    - Setiap plaintext chunk hanya ditulis ke temp tar setelah tag AEAD record itu valid.
    - Prompt overwrite baru dikembalikan setelah seluruh record, termasuk FINAL, valid.
    - Data tujuan lama tidak disentuh sebelum tar sudah terdekripsi dan diverifikasi penuh.
    """
    base_dir = target_path.parent
    temp_ext_dir: Path | None = None

    try:
        if total_size < HEADER_SIZE_V2 + (2 * CHUNK_RECORD_OVERHEAD):
            return VaultStatus.ERROR, "The vault file is too small or incomplete."

        salt = _v2_read_exact(fk, 16)
        file_id = _v2_read_exact(fk, 16)
        stored_chunk_size = int.from_bytes(_v2_read_exact(fk, 4), byteorder="big")
        flags = int.from_bytes(_v2_read_exact(fk, 4), byteorder="big")

        if stored_chunk_size <= 0 or stored_chunk_size > CHUNK_SIZE:
            return (
                VaultStatus.ERROR,
                "The vault's chunk parameters are invalid, or the file is corrupted.",
            )

        try:
            kdf_id, kdf_params, kdf_section = _v2_parse_kdf_section(fk, flags)
        except ValueError as exc:
            return VaultStatus.ERROR, str(exc)

        header_context = _v2_header_context(
            salt,
            file_id,
            stored_chunk_size,
            flags,
            kdf_section,
        )

        safe_cb(progress_cb, 0.02)
        try:
            key = derive_key_for_kdf(password, salt, kdf_id, kdf_params)
        except ValueError as exc:
            return VaultStatus.ERROR, str(exc)
        aesgcm = AESGCM(key)
        safe_cb(progress_cb, 0.04)

        # Record 0 wajib metadata terenkripsi: panjang nama + nama virtual.
        record_type, record_index, plaintext_len, record_header = _v2_read_record_header(fk)
        if (
            record_type != RECORD_TYPE_METADATA
            or record_index != 0
            or plaintext_len < 2
            or plaintext_len > 2 + MAX_VIRTUAL_NAME_LENGTH
        ):
            raise InvalidTag

        metadata_ciphertext = _v2_read_exact(fk, plaintext_len + TAG_SIZE)
        metadata_plaintext = aesgcm.decrypt(
            _v2_nonce(record_index),
            metadata_ciphertext,
            _v2_aad(header_context, record_header),
        )

        try:
            nama_folder, name_offset = _parse_virtual_folder_name(metadata_plaintext)
            if name_offset != len(metadata_plaintext):
                raise ValueError("invalid extra metadata")
        except ValueError:
            return VaultStatus.WRONG_PASSWORD, None

        temp_ext_dir, temp_tar_path = _create_temp_decrypt_paths(base_dir)
        expected_index = 1
        last_pct = 0.0

        with temp_tar_path.open("wb") as ftar:
            while True:
                if is_cancelled and is_cancelled():
                    raise InterruptedError("Operation cancelled by the user.")

                record_type, record_index, plaintext_len, record_header = _v2_read_record_header(fk)
                if record_index != expected_index:
                    raise InvalidTag

                if record_type == RECORD_TYPE_DATA:
                    if plaintext_len <= 0 or plaintext_len > stored_chunk_size:
                        raise InvalidTag

                    ciphertext = _v2_read_exact(fk, plaintext_len + TAG_SIZE)
                    plaintext = aesgcm.decrypt(
                        _v2_nonce(record_index),
                        ciphertext,
                        _v2_aad(header_context, record_header),
                    )
                    if len(plaintext) != plaintext_len:
                        raise InvalidTag

                    # Aman: plaintext record ini sudah terautentikasi.
                    ftar.write(plaintext)
                    expected_index += 1

                    pct = min(0.85, 0.05 + 0.80 * (fk.tell() / max(total_size, 1)))
                    if pct - last_pct >= 0.005:
                        safe_cb(progress_cb, pct)
                        last_pct = pct

                elif record_type == RECORD_TYPE_FINAL:
                    if plaintext_len != 0:
                        raise InvalidTag
                    ciphertext = _v2_read_exact(fk, TAG_SIZE)
                    final_plaintext = aesgcm.decrypt(
                        _v2_nonce(record_index),
                        ciphertext,
                        _v2_aad(header_context, record_header),
                    )
                    if final_plaintext != b"":
                        raise InvalidTag
                    expected_index += 1
                    break
                else:
                    raise InvalidTag

            ftar.flush()
            os.fsync(ftar.fileno())

        if fk.tell() != total_size:
            # Jangan izinkan trailing bytes yang tidak ikut diautentikasi.
            raise InvalidTag

        safe_cb(progress_cb, 0.85)

        path_tujuan = base_dir / nama_folder
        if path_tujuan.exists() and not force:
            return VaultStatus.OVERWRITE_NEEDED, nama_folder

        _extract_and_place_vault(
            temp_tar_path,
            temp_ext_dir,
            nama_folder,
            path_tujuan,
            progress_cb,
            is_cancelled,
        )

        safe_cb(progress_cb, 1.0)
        return VaultStatus.SUCCESS, nama_folder

    except InvalidTag:
        return VaultStatus.WRONG_PASSWORD, None
    except tarfile.ReadError:
        return VaultStatus.WRONG_PASSWORD, None
    except InterruptedError:
        return (
            VaultStatus.CANCELLED,
            "Operation cancelled. No existing data was changed.",
        )
    except Exception as exc:
        logger.exception("Gagal membuka brankas v2 chunked AEAD.")
        return VaultStatus.ERROR, f"An internal error occurred: {str(exc)}"
    finally:
        if temp_ext_dir and temp_ext_dir.exists():
            _cleanup_temp_decrypt_dir(temp_ext_dir)


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
        return VaultStatus.ERROR, "No valid file/folder to lock."

    if not password or not password.strip():
        return VaultStatus.ERROR, "Password cannot be empty."

    target_path = Path(path_simpan)

    for source in valid_paths:
        source_path = Path(source)
        if _target_conflicts_with_source(target_path, source_path):
            return (
                VaultStatus.ERROR,
                "The vault's save location can't be the same as, or inside, the "
                "file/folder being locked. Choose another location so the vault isn't "
                "deleted along with it or pulled into the archive.",
            )

    if len(valid_paths) == 1:
        nama_virtual = Path(valid_paths[0]).name
        target_dir = ""
    else:
        nama_virtual = target_path.stem or "Brankas_Rahasia"
        target_dir = nama_virtual

    backup_path: Path | None = None
    backup_dibuat = False

    try:
        free_space = shutil.disk_usage(target_path.parent).free
        total_size = _hitung_total_size(valid_paths)
        required_space = _hitung_kebutuhan_disk_kunci(valid_paths, nama_virtual, target_dir)

        if free_space < required_space:
            req_mb = required_space / (1024 * 1024)
            free_mb = free_space / (1024 * 1024)
            return (
                VaultStatus.ERROR,
                f"Not enough storage space.\nDisk free: {free_mb:.1f} MB. At least {req_mb:.1f} MB is required.",
            )

        if target_path.exists():
            backup_path = _make_unique_backup_path(target_path)
            target_path.replace(backup_path)
            backup_dibuat = True

        salt = os.urandom(16)
        file_id = os.urandom(16)
        argon2_params_raw = _encode_argon2id_params()
        kdf_section = _v2_kdf_section(KDF_ID_ARGON2ID, argon2_params_raw)
        flags = V2_FLAG_KDF_PARAMS
        header_context = _v2_header_context(
            salt,
            file_id,
            CHUNK_SIZE,
            flags,
            kdf_section,
        )

        key = derive_key_argon2id(password, salt)
        aesgcm = AESGCM(key)
        safe_cb(progress_cb, 0.03)  # Key derivation done

        with target_path.open("wb") as fk:
            fk.write(header_context)

            nama_bytes = nama_virtual.encode("utf-8")
            metadata_plaintext = len(nama_bytes).to_bytes(2, byteorder="big") + nama_bytes
            _v2_write_record(
                fk,
                aesgcm,
                header_context,
                RECORD_TYPE_METADATA,
                0,
                metadata_plaintext,
            )

            out_stream = ChunkedAEADEncryptingStream(
                fk, aesgcm, header_context, progress_cb, total_size, is_cancelled
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

            out_stream.finish()

            # Paksa OS flush disk buffer cache ke hardware fisik.
            # Ini satu-satunya cara memastikan data benar-benar tersimpan
            # di chip SSD/HDD, bukan hanya di RAM cache OS.
            # WAJIB dilakukan sebelum hapus_asli=True menghapus file asli.
            fk.flush()
            os.fsync(fk.fileno())

        # Data encryption complete → end of data phase (85%)
        safe_cb(progress_cb, 0.85)

        if backup_dibuat and backup_path and backup_path.exists():
            backup_path.unlink()

        if hapus_asli:
            safe_cb(progress_cb, 0.88)
            if not _quick_verify_vault(target_path):
                return (
                    VaultStatus.ERROR,
                    "The vault couldn't be verified on the physical disk. The original file was not deleted. "
                    "Try checking your disk space and the condition of your storage hardware.",
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
            f"Vault locked successfully!\nSize: {size_mb:.1f} MB",
        )

    except InterruptedError:
        if target_path.exists():
            target_path.unlink(missing_ok=True)
        if backup_dibuat and backup_path and backup_path.exists():
            backup_path.replace(target_path)
        return (
            VaultStatus.CANCELLED,
            "Operation cancelled. No existing data was changed.",
        )
    except Exception as exc:
        if target_path.exists():
            target_path.unlink(missing_ok=True)
        if backup_dibuat and backup_path and backup_path.exists():
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
            return VaultStatus.ERROR, "The vault file is too small or incomplete."

        cipher_len = total_size - OVERHEAD
        base_dir = target_path.parent

        free_space = shutil.disk_usage(base_dir).free
        required_space = _hitung_kebutuhan_disk_buka(cipher_len)

        if free_space < required_space:
            req_mb = required_space / (1024 * 1024)
            free_mb = free_space / (1024 * 1024)
            return (
                VaultStatus.ERROR,
                f"Not enough storage space.\nDisk free: {free_mb:.1f} MB. At least {req_mb:.1f} MB is required.",
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
                    "This file isn't a valid Adyton Crypt vault.",
                )

            # 2. Validasi Versi
            version = fk.read(1)
            if version == VERSION_V2:
                return _buka_brankas_v2_from_open_file(
                    fk,
                    target_path,
                    total_size,
                    password,
                    force,
                    progress_cb,
                    is_cancelled,
                )
            if version == VERSION_V1:
                # Versi 1: AES-GCM monolitik lama, dibuka via two-pass.
                pass
            else:
                return (
                    VaultStatus.ERROR,
                    "This vault was made by a newer version. Please update Adyton Crypt.",
                )

            # 3. Baca Salt dan Nonce (format v1)
            salt = fk.read(16)
            nonce = fk.read(12)

            fk.seek(-16, os.SEEK_END)
            tag = fk.read(16)

            # Kembali ke posisi setelah header selesai (byte ke-33)
            fk.seek(HEADER_SIZE)

            safe_cb(progress_cb, 0.02)  # Header dibaca

            # Lanjut derive_key dan verifikasi autentikasi sebelum plaintext ditulis.
            key = derive_key(password, salt)

            safe_cb(progress_cb, 0.04)  # Key derivation selesai (PBKDF2)

            try:
                # FASE 1: AUTHENTICATION-ONLY PASS
                # Decryptor menghasilkan plaintext di memori, tetapi output dibuang
                # dan tidak ditulis ke disk sebelum finalize() memverifikasi tag GCM.
                decrypted_first = _verify_gcm_before_plaintext_write(
                    fk,
                    key,
                    nonce,
                    tag,
                    cipher_len,
                    progress_cb,
                    is_cancelled,
                )
            except InvalidTag:
                return VaultStatus.WRONG_PASSWORD, None
            except InterruptedError:
                return (
                    VaultStatus.CANCELLED,
                    "Operation cancelled. No existing data was changed.",
                )

            # Parse nama folder dan prompt overwrite hanya setelah tag GCM valid.
            try:
                nama_folder, name_offset = _parse_virtual_folder_name(decrypted_first)
            except ValueError:
                return VaultStatus.WRONG_PASSWORD, None

            path_tujuan = base_dir / nama_folder

            if path_tujuan.exists() and not force:
                return VaultStatus.OVERWRITE_NEEDED, nama_folder

            temp_ext_dir, temp_tar_path = _create_temp_decrypt_paths(base_dir)
            safe_cb(progress_cb, 0.46)  # Aman menulis plaintext terautentikasi ke temp tar

            try:
                # FASE 2: AUTHENTICATED PLAINTEXT WRITE PASS
                fk.seek(HEADER_SIZE)
                decryptor_for_write = make_decryptor(key, nonce, tag)
                first_sz = min(FIRST_DECRYPT_CHUNK_SIZE, cipher_len)
                first_chunk = fk.read(first_sz)
                if len(first_chunk) != first_sz:
                    raise InvalidTag

                decrypted_first_for_write = decryptor_for_write.update(first_chunk)
                bytes_remaining = cipher_len - first_sz

                _write_decrypted_to_temp_tar(
                    temp_tar_path,
                    decryptor_for_write,
                    decrypted_first_for_write[name_offset:],
                    bytes_remaining,
                    fk,
                    progress_cb,
                    is_cancelled,
                )

                # FASE 3 + FASE 4: Ekstraksi tar + pindah ke lokasi akhir
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
                return (
                    VaultStatus.CANCELLED,
                    "Operation cancelled. No existing data was changed.",
                )

        safe_cb(progress_cb, 1.0)
        return VaultStatus.SUCCESS, nama_folder

    except Exception as exc:
        logger.exception(
            "Gagal membuka brankas karena error internal saat proses dekripsi/ekstraksi."
        )
        return VaultStatus.ERROR, f"An internal error occurred: {str(exc)}"
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
        nama_folder = _validate_virtual_folder_name(nama_folder)
        return nama_folder, 2 + panjang_nama
    except UnicodeDecodeError:
        raise ValueError("wrong_password") from None
    except Exception:
        raise ValueError("wrong_password") from None


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
