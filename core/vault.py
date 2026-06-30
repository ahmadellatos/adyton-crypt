"""
core/vault.py
Logika utama: kunci folder/file (enkripsi) dan buka brankas (dekripsi).
Dioptimasi dengan Single-Pass I/O Streaming, pathlib, dan Cancellation Support.
Telah ditambal dari celah keamanan Path Traversal (TarSlip) dan rapuhnya deteksi password.
"""

import contextlib
import hashlib
import os
import shutil
import stat
import tarfile
import time
import uuid
from collections.abc import Callable
from enum import Enum
from pathlib import Path, PureWindowsPath

import zstandard
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
    COMPRESSED_DECRYPT_RATIO_GUESS,
    CORE_HEADER_SIZE,
    DISK_OVERHEAD_BYTES,
    FILE_ID_SIZE,
    FLAG_COMPRESSED,
    FLAG_HINT,
    FLAG_NONE,
    KDF_ID_ARGON2ID,
    KEYFILE_MAX_SIZE,
    MAGIC_BYTES,
    MASTER_KEY_SIZE,
    MAX_HEADER_SIZE,
    MAX_HINT_LENGTH,
    MAX_KEYSLOTS,
    MAX_VIRTUAL_NAME_LENGTH,
    OLD_TEMP_MAX_AGE_SECONDS,
    PASSWORD_SLOT_TYPES,
    RECORD_TYPE_DATA,
    RECORD_TYPE_FINAL,
    RECORD_TYPE_METADATA,
    RECOVERY_SLOT_TYPES,
    SALT_SIZE,
    SLOT_TYPE_PASSWORD,
    SLOT_TYPE_PASSWORD_KEYFILE,
    SLOT_TYPE_RECOVERY_CODE,
    SLOT_TYPE_RECOVERY_PASSPHRASE,
    SUPPORTED_FLAGS,
    TAG_SIZE,
    VALID_SLOT_TYPES,
    VERSION,
    WRAP_NONCE_SIZE,
    WRAPPED_KEY_SIZE,
    ZSTD_COMPRESSION_LEVEL,
    ZSTD_DISK_ESTIMATE_RATIO,
)
from .crypto import (
    combine_kek_with_keyfile,
    derive_key_for_kdf,
    generate_keyfile_bytes,
    normalize_recovery_code,
    safe_cb,
)


class VaultStatus(Enum):
    SUCCESS = "success"
    WRONG_PASSWORD = "wrong_password"  # nosec B105
    OVERWRITE_NEEDED = "overwrite_needed"
    ERROR = "error"
    CANCELLED = "cancelled"


# Pesan untuk exception TAK TERDUGA (catch-all `except Exception`). Sengaja TIDAK
# menyertakan str(exc): teks exception bisa memuat path absolut atau detail internal
# yang lalu bocor ke UI (mis. "[WinError 5] Access is denied: 'C:\\Users\\...\\rahasia.adtn'").
# Detail lengkap tetap masuk log (logger.exception) untuk diagnosis. Kalimat ini
# netral-operasi sehingga rapi baik berdiri sendiri (Tab Manage) maupun setelah
# awalan "Couldn't open/lock the vault." dari format_user_error.
GENERIC_FAILURE_MESSAGE = (
    "Check the file, your permissions, and free disk space, then try again. "
    "Technical details were saved to the log."
)

# Pesan saat verifikasi menemukan vault yang BISA di-unlock (credential benar) tapi
# salah satu record gagal cek integritas (tag AEAD tak valid / file terpotong). Ini
# berbeda dari WRONG_PASSWORD: Master Key sudah terbukti benar, jadi kegagalan di sini
# berarti datanya yang rusak/diubah — bukan password yang salah.
CORRUPT_VAULT_MESSAGE = (
    "This vault opened, but some of its data failed the integrity check. The file may be "
    "incomplete, corrupted, or modified. If you have a backup, restore from it."
)


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

        # Secure wipe: ganti nama file ke acak sebelum unlink agar nama asli
        # (yang sendiri bisa membocorkan isi, mis. "Gaji_2026.pdf") tidak
        # tertinggal di direktori/MFT NTFS untuk dibaca tool recovery. Symlink
        # tidak di-rename — cukup dilepas tautannya.
        target = path
        if secure_wipe and not path.is_symlink():
            with contextlib.suppress(OSError):
                scrambled = path.with_name(uuid.uuid4().hex)
                os.replace(path, scrambled)
                target = scrambled

        try:
            target.unlink(missing_ok=True)
        except PermissionError:
            target.chmod(stat.S_IWRITE | stat.S_IREAD)
            target.unlink(missing_ok=True)

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
    compress: bool = False,
) -> int:
    """Hitung kebutuhan ruang disk saat membuat vault (chunked AEAD).

    AES-GCM per record menambah 16-byte tag per metadata/data/final record,
    ditambah header record 13 byte. Estimasi plaintext tar tetap konservatif
    untuk banyak file kecil.

    Untuk lock TERKOMPRESI, output yang benar-benar ditulis ke disk ≈ ukuran
    TERKOMPRESI — tar mentah TIDAK pernah ditulis ke disk (di-stream tar→zstd→AEAD
    langsung ke file vault). Jadi reservasi payload diturunkan dengan asumsi rasio
    ``ZSTD_DISK_ESTIMATE_RATIO`` agar lock yang valid pada disk sempit tak ditolak
    percuma. Bila data ternyata kurang kompresibel, penulisan bisa kehabisan ruang di
    tengah → aman (vault parsial dihapus + backup dipulihkan, sumber asli tak disentuh).
    Overhead record tetap dihitung dari ukuran mentah (konservatif; nilainya ~ratusan
    byte per 16 MB, jadi efeknya dapat diabaikan).
    """
    metadata_size = 2 + len(virtual_name.encode("utf-8"))
    estimated_tar_size = _estimate_tar_plaintext_size(paths, target_dir)
    data_records = max(1, (estimated_tar_size + CHUNK_SIZE - 1) // CHUNK_SIZE)
    payload_reserve = estimated_tar_size
    if compress:
        payload_reserve = estimated_tar_size // ZSTD_DISK_ESTIMATE_RATIO
    return (
        MAX_HEADER_SIZE  # header (bound atas: hint maksimal + slot penuh)
        + CHUNK_RECORD_OVERHEAD  # metadata record
        + metadata_size
        + (data_records * CHUNK_RECORD_OVERHEAD)
        + payload_reserve
        + CHUNK_RECORD_OVERHEAD  # final record
        + DISK_OVERHEAD_BYTES
    )


def _hitung_kebutuhan_disk_buka(cipher_len: int, compressed: bool = False) -> int:
    """Hitung kebutuhan ruang disk saat membuka vault.

    Setelah tag GCM valid, proses buka menyimpan temporary tar plaintext dan
    mengekstraknya ke folder sementara sebelum dipindahkan ke lokasi akhir.
    Karena itu kebutuhan ruang bisa mendekati 2x payload, bukan hanya ukuran
    ciphertext.

    Untuk vault TERKOMPRESI, payload terdekompresi bisa jauh lebih besar dari
    ciphertext, jadi reservasi dinaikkan dengan asumsi rasio konservatif
    (``COMPRESSED_DECRYPT_RATIO_GUESS``). Ini hanya pra-cek UX: bila rasio nyata lebih
    tinggi lagi, ekstraksi gagal dengan rollback aman (folder tujuan lama tak disentuh
    sebelum hasil ekstraksi lengkap), jadi under-estimate tak menyebabkan kehilangan data.
    """
    if compressed:
        return cipher_len + (cipher_len * COMPRESSED_DECRYPT_RATIO_GUESS) + DISK_OVERHEAD_BYTES
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


def _encode_argon2id_params(
    iterations: int = ARGON2ID_ITERATIONS,
    lanes: int = ARGON2ID_LANES,
    memory_cost: int = ARGON2ID_MEMORY_COST_KIB,
) -> bytes:
    """Encode parameter Argon2id ke format keyslot."""
    for value in (iterations, lanes, memory_cost):
        if value <= 0 or value >= 2**32:
            raise ValueError("Argon2id parameter out of range.")

    return (
        iterations.to_bytes(4, byteorder="big")
        + lanes.to_bytes(4, byteorder="big")
        + memory_cost.to_bytes(4, byteorder="big")
    )


def _decode_argon2id_params(params: bytes) -> dict[str, int]:
    """Decode parameter Argon2id dari keyslot."""
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


def _record_header(record_type: int, record_index: int, plaintext_len: int) -> bytes:
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


def _record_nonce(record_index: int) -> bytes:
    """Nonce AES-GCM 96-bit deterministik per record.

    Aman karena key setiap vault unik dari salt+password, dan setiap record
    dalam vault yang sama memakai indeks unik yang diverifikasi berurutan.
    """
    if record_index < 0 or record_index >= 2**96:
        raise ValueError("record_index out of nonce range")
    return record_index.to_bytes(12, byteorder="big")


def _record_aad(header_context: bytes, record_header: bytes) -> bytes:
    return header_context + record_header


def _write_record(
    file_handle,
    aesgcm: AESGCM,
    header_context: bytes,
    record_type: int,
    record_index: int,
    plaintext: bytes,
) -> None:
    record_header = _record_header(record_type, record_index, len(plaintext))
    ciphertext = aesgcm.encrypt(
        _record_nonce(record_index),
        plaintext,
        _record_aad(header_context, record_header),
    )
    file_handle.write(record_header)
    file_handle.write(ciphertext)


def _read_exact(file_handle, size: int) -> bytes:
    data = file_handle.read(size)
    if len(data) != size:
        raise InvalidTag
    return data


def _read_record_header(file_handle) -> tuple[int, int, int, bytes]:
    raw = _read_exact(file_handle, CHUNK_RECORD_HEADER_SIZE)
    record_type = raw[0]
    record_index = int.from_bytes(raw[1:9], byteorder="big")
    plaintext_len = int.from_bytes(raw[9:13], byteorder="big")
    return record_type, record_index, plaintext_len, raw


class ChunkedAEADEncryptingStream:
    """File-like writer untuk tarfile yang mengenkripsi output sebagai record AEAD.

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
        _write_record(
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
        _write_record(
            self.target_file,
            self.aesgcm,
            self.header_context,
            RECORD_TYPE_FINAL,
            self.record_index,
            b"",
        )
        self._finished = True


class _CompressProgressWriter:
    """File-like di SISI INPUT tar saat kompresi aktif.

    Saat vault dikompresi, ``ChunkedAEADEncryptingStream`` menerima byte TERKOMPRESI,
    sehingga progress berbasis output-nya tak lagi mencerminkan kemajuan terhadap data
    sumber. Wrapper ini duduk di antara ``tarfile`` dan zstd writer: meneruskan byte tar
    mentah ke zstd, melaporkan progress berdasarkan byte UNCOMPRESSED yang ditulis, dan
    mengecek pembatalan per-write (lebih responsif daripada menunggu blok zstd ter-flush
    ke lapisan enkripsi). Saat kompresi aktif, progress di ``ChunkedAEADEncryptingStream``
    dimatikan (``progress_cb=None``) agar tidak ada laporan ganda.
    """

    def __init__(self, dest, progress_cb, total_bytes: int, is_cancelled: Callable[[], bool]):
        self.dest = dest
        self.progress_cb = progress_cb
        self.total_bytes = total_bytes
        self.is_cancelled = is_cancelled
        self.written = 0
        self._last_pct = 0.0

    def write(self, data: bytes) -> int:
        if self.is_cancelled and self.is_cancelled():
            raise InterruptedError("Operation cancelled by the user.")
        self.dest.write(data)
        self.written += len(data)
        if self.total_bytes > 0:
            pct = min(0.85, 0.05 + 0.80 * (self.written / self.total_bytes))
            if pct - self._last_pct >= 0.005:
                safe_cb(self.progress_cb, pct)
                self._last_pct = pct
        return len(data)

    def flush(self):
        # Jangan paksa zstd menutup blok di tiap flush tarfile (sinkronisasi, bukan
        # akhir stream); frame difinalkan saat zstd writer ditutup oleh pemanggil.
        return


# ── Format Envelope / Keyslot ───────────────────────────────────────────────────
#
# Master Key (MK) acak mengenkripsi seluruh record. MK dibungkus per-credential di
# keyslot. Karena key record adalah MK yang tidak berubah, ganti password / tambah
# recovery cukup menulis ulang region keyslot — record tidak perlu dienkripsi ulang.


def _record_context(file_id: bytes, chunk_size: int, flags: int) -> bytes:
    """AAD setiap record. Sengaja TANPA keyslot/hint agar re-key murah.

    FILE_ID acak mengikat record ke vault ini; chunk_size & flags ditetapkan saat
    pembuatan dan tidak berubah seumur hidup vault.
    """
    return (
        MAGIC_BYTES
        + VERSION
        + file_id
        + chunk_size.to_bytes(4, byteorder="big")
        + flags.to_bytes(4, byteorder="big")
    )


def _slot_meta(
    slot_type: int,
    kdf_id: int,
    kdf_params_raw: bytes,
    salt: bytes,
    wrap_nonce: bytes,
) -> bytes:
    """Bagian keyslot yang dibawa di AAD wrap (semua kecuali wrapped master key)."""
    return (
        bytes([slot_type, kdf_id])
        + len(kdf_params_raw).to_bytes(2, byteorder="big")
        + kdf_params_raw
        + salt
        + wrap_nonce
    )


def _slot_wrap_aad(file_id: bytes, hint_bytes: bytes, meta: bytes) -> bytes:
    """AAD untuk membungkus MK: mengikat ke identitas vault + hint + parameter slot.

    Mencegah slot ditukar antar-vault (file_id), mencegah parameter slot
    (kdf, salt, nonce) diutak-atik diam-diam, dan **mengikat password hint** yang
    disimpan plaintext di header. Tanpa ini hint tidak terautentikasi sama sekali:
    siapa pun yang bisa menulis ke file vault bisa mengganti teks hint (mis. untuk
    menyesatkan korban) tanpa terdeteksi. Dengan hint masuk AAD, tamper apa pun
    pada hint membuat unwrap MK gagal → dilaporkan wrong_password (fail-closed).

    ``hint_bytes`` adalah byte mentah hint persis seperti di header (kosong untuk
    vault tanpa hint). Vault tanpa hint menghasilkan AAD identik dengan format
    sebelum hint diautentikasi, jadi vault lama tanpa hint tetap bisa dibuka.
    """
    return MAGIC_BYTES + VERSION + file_id + hint_bytes + meta


def _derive_slot_kek(
    slot_type: int,
    secret: str,
    salt: bytes,
    kdf_id: int,
    kdf_params: dict[str, int],
    keyfile_material: bytes | None = None,
) -> bytes | None:
    """Turunkan Key Encryption Key untuk satu slot dari credential-nya.

    Untuk slot 2FA (``SLOT_TYPE_PASSWORD_KEYFILE``) KEK = gabung(Argon2id(password),
    keyfile); bila keyfile tak tersedia, kembalikan ``None`` agar pemanggil melewati
    slot ini TANPA menjalankan Argon2id yang mahal (mis. saat user memakai recovery
    key di vault 2FA — keyfile tidak diperlukan untuk slot recovery).
    """
    if slot_type == SLOT_TYPE_PASSWORD_KEYFILE and keyfile_material is None:
        return None
    if slot_type == SLOT_TYPE_RECOVERY_CODE:
        secret = normalize_recovery_code(secret)
    kek = derive_key_for_kdf(secret, salt, kdf_id, kdf_params)
    if slot_type == SLOT_TYPE_PASSWORD_KEYFILE:
        kek = combine_kek_with_keyfile(kek, keyfile_material)
    return kek


def _build_keyslot(
    master_key: bytes,
    file_id: bytes,
    slot_type: int,
    secret: str,
    kdf_params: dict[str, int] | None = None,
    hint_bytes: bytes = b"",
    keyfile_material: bytes | None = None,
) -> bytes:
    """Bangun satu keyslot lengkap (meta + wrapped MK) dari sebuah credential.

    ``kdf_params`` opsional memilih kekuatan Argon2id (level KDF); bila None dipakai
    default vault. Parameter di-encode lalu di-decode lagi agar nilainya tervalidasi
    & dibatasi ceiling sebelum dipakai. ``hint_bytes`` (mentah, byte hint di header)
    diikat ke AAD wrap agar hint terautentikasi — pemanggil WAJIB memakai byte hint
    yang sama persis dengan yang ditulis ``_build_header``. ``keyfile_material`` WAJIB
    untuk slot ``SLOT_TYPE_PASSWORD_KEYFILE`` (2FA) dan diabaikan untuk slot lain.
    """
    salt = os.urandom(SALT_SIZE)
    wrap_nonce = os.urandom(WRAP_NONCE_SIZE)
    if kdf_params:
        kdf_params_raw = _encode_argon2id_params(
            kdf_params["iterations"], kdf_params["lanes"], kdf_params["memory_cost"]
        )
    else:
        kdf_params_raw = _encode_argon2id_params()
    kdf_params = _decode_argon2id_params(kdf_params_raw)
    kek = _derive_slot_kek(slot_type, secret, salt, KDF_ID_ARGON2ID, kdf_params, keyfile_material)
    if kek is None:
        # Hanya terjadi bila slot keyfile dibangun tanpa keyfile — bug pemanggil.
        raise ValueError("A keyfile is required to build this keyslot.")
    meta = _slot_meta(slot_type, KDF_ID_ARGON2ID, kdf_params_raw, salt, wrap_nonce)
    wrapped = AESGCM(kek).encrypt(wrap_nonce, master_key, _slot_wrap_aad(file_id, hint_bytes, meta))
    return meta + wrapped


def _load_keyfile_material(keyfile_path: str) -> bytes:
    """Baca keyfile dari disk (stream, dibatasi ukuran) → material 32-byte.

    Melempar ``ValueError`` dengan pesan path-free yang aman ditampilkan ke user bila
    file kosong, terlalu besar, atau tak terbaca. Hashing streaming agar keyfile besar
    tak dimuat seluruhnya ke memori; di atas ``KEYFILE_MAX_SIZE`` ditolak.
    """
    path = Path(keyfile_path)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError("The keyfile could not be read. Check that it still exists.") from exc
    if size == 0:
        raise ValueError("The keyfile is empty. Choose a non-empty file or generate one.")
    if size > KEYFILE_MAX_SIZE:
        raise ValueError("The keyfile is too large. Choose a file under 64 MB.")
    hasher = hashlib.sha256()
    read_total = 0
    try:
        with path.open("rb") as fk:
            for block in iter(lambda: fk.read(1024 * 1024), b""):
                # Cap di dalam loop, jangan hanya andalkan stat() di atas: file bisa
                # tumbuh antara stat dan baca (TOCTOU), atau menunjuk file spesial/
                # virtual yang stat-nya kecil tapi mengalir tanpa henti. Tolak alih-alih
                # mem-hash tanpa batas (mencegah hang / baca raksasa saat membuka vault).
                read_total += len(block)
                if read_total > KEYFILE_MAX_SIZE:
                    raise ValueError("The keyfile is too large. Choose a file under 64 MB.")
                hasher.update(block)
    except OSError as exc:
        raise ValueError("The keyfile could not be read. Check that it still exists.") from exc
    return hasher.digest()


def generate_keyfile(keyfile_path: str) -> tuple[VaultStatus, str]:
    """Tulis keyfile acak entropi tinggi ke ``keyfile_path``.

    Menolak menimpa file yang sudah ada (mencegah merusak keyfile/dokumen lain).
    """
    path = Path(keyfile_path)
    try:
        if path.exists():
            return VaultStatus.ERROR, "A file with that name already exists. Choose another name."
        # x = exclusive create: gagal bila file muncul di antara cek dan tulis (race).
        with path.open("xb") as fk:
            fk.write(generate_keyfile_bytes())
            fk.flush()
            os.fsync(fk.fileno())
        return (
            VaultStatus.SUCCESS,
            "Keyfile created. Keep it safe — you'll need it to open the vault.",
        )
    except FileExistsError:
        return VaultStatus.ERROR, "A file with that name already exists. Choose another name."
    except Exception:
        logger.exception("Gagal membuat keyfile.")
        return VaultStatus.ERROR, GENERIC_FAILURE_MESSAGE


def _slot_bytes(slot: dict) -> bytes:
    """Serialisasi ulang slot hasil parse ke bytes on-disk."""
    return slot["meta"] + slot["wrapped"]


def _build_header(
    file_id: bytes,
    chunk_size: int,
    flags: int,
    hint_bytes: bytes,
    slots: list[bytes],
) -> bytes:
    """Rakit header lengkap (core + hint opsional + daftar keyslot)."""
    if not 1 <= len(slots) <= MAX_KEYSLOTS:
        raise ValueError("keyslot count out of range")
    parts = [
        MAGIC_BYTES,
        VERSION,
        file_id,
        chunk_size.to_bytes(4, byteorder="big"),
        flags.to_bytes(4, byteorder="big"),
    ]
    if flags & FLAG_HINT:
        parts.append(len(hint_bytes).to_bytes(2, byteorder="big") + hint_bytes)
    parts.append(bytes([len(slots)]))
    parts.extend(slots)
    return b"".join(parts)


def _parse_header(fk) -> dict:
    """Parse header dari file yang sudah dibaca MAGIC+VERSION-nya.

    Melempar ``InvalidTag`` bila file terpotong (ditangani sebagai wrong_password
    oleh pemanggil) dan ``ValueError`` untuk header yang strukturnya tidak valid.
    """
    file_id = _read_exact(fk, FILE_ID_SIZE)
    chunk_size = int.from_bytes(_read_exact(fk, 4), byteorder="big")
    flags = int.from_bytes(_read_exact(fk, 4), byteorder="big")

    if flags & ~SUPPORTED_FLAGS:
        raise ValueError("This vault flag isn't supported by this app version.")

    hint = None
    hint_bytes = b""
    if flags & FLAG_HINT:
        hint_len = int.from_bytes(_read_exact(fk, 2), byteorder="big")
        if hint_len > MAX_HINT_LENGTH:
            raise ValueError("Invalid vault hint length; the file may be corrupted.")
        # Simpan byte mentah: dipakai apa adanya untuk AAD wrap (hint terautentikasi)
        # agar tidak bergantung pada round-trip decode/encode yang bisa lossy.
        hint_bytes = _read_exact(fk, hint_len)
        hint = hint_bytes.decode("utf-8", "replace")

    slot_count = _read_exact(fk, 1)[0]
    if not 1 <= slot_count <= MAX_KEYSLOTS:
        raise ValueError("Invalid keyslot count; the file may be corrupted.")

    slots: list[dict] = []
    for _ in range(slot_count):
        slot_type = _read_exact(fk, 1)[0]
        kdf_id = _read_exact(fk, 1)[0]
        params_len = int.from_bytes(_read_exact(fk, 2), byteorder="big")
        kdf_params_raw = _read_exact(fk, params_len)
        salt = _read_exact(fk, SALT_SIZE)
        wrap_nonce = _read_exact(fk, WRAP_NONCE_SIZE)
        wrapped = _read_exact(fk, WRAPPED_KEY_SIZE)

        if slot_type not in VALID_SLOT_TYPES or kdf_id != KDF_ID_ARGON2ID:
            raise ValueError("This vault keyslot isn't supported by this app version.")

        slots.append(
            {
                "slot_type": slot_type,
                "kdf_id": kdf_id,
                "kdf_params_raw": kdf_params_raw,
                "kdf_params": _decode_argon2id_params(kdf_params_raw),
                "salt": salt,
                "wrap_nonce": wrap_nonce,
                "wrapped": wrapped,
                "meta": _slot_meta(slot_type, kdf_id, kdf_params_raw, salt, wrap_nonce),
            }
        )

    return {
        "file_id": file_id,
        "chunk_size": chunk_size,
        "flags": flags,
        "hint": hint,
        "hint_bytes": hint_bytes,
        "slots": slots,
        "header_end": fk.tell(),
    }


def _recover_master_key(
    secret: str,
    file_id: bytes,
    hint_bytes: bytes,
    slots: list[dict],
    keyfile_material: bytes | None = None,
) -> bytes | None:
    """Coba credential terhadap tiap slot; kembalikan MK pada slot pertama yang cocok.

    Slot dicoba berurutan, jadi password benar di slot 0 hanya butuh satu derivasi
    KDF. Hanya secret yang salah yang membayar derivasi semua slot. ``hint_bytes``
    (byte hint mentah dari header) ikut diautentikasi via AAD wrap.

    ``keyfile_material`` (bila ada) dipakai untuk slot 2FA. Slot keyfile dilewati
    tanpa biaya KDF saat keyfile tak tersedia, sehingga recovery key tetap membuka
    vault 2FA tanpa keyfile (jalur break-glass).
    """
    for slot in slots:
        kek = _derive_slot_kek(
            slot["slot_type"],
            secret,
            slot["salt"],
            slot["kdf_id"],
            slot["kdf_params"],
            keyfile_material,
        )
        if kek is None:
            continue
        try:
            master_key = AESGCM(kek).decrypt(
                slot["wrap_nonce"],
                slot["wrapped"],
                _slot_wrap_aad(file_id, hint_bytes, slot["meta"]),
            )
        except (InvalidTag, ValueError):
            continue
        if len(master_key) == MASTER_KEY_SIZE:
            return master_key
    return None


def _read_header_from_path(path: Path) -> dict:
    """Buka file dan parse header-nya (tanpa credential). Raise bila format asing."""
    with path.open("rb") as fk:
        if fk.read(4) != MAGIC_BYTES:
            raise ValueError("This file isn't a valid Adyton Crypt vault.")
        version = fk.read(1)
        if version != VERSION:
            raise ValueError("wrong_format")
        return _parse_header(fk)


@contextlib.contextmanager
def _open_payload_tar(temp_tar_path: Path, compressed: bool):
    """Buka tar payload hasil dekripsi; decompress streaming bila vault terkompresi.

    Vault tak terkompresi → tar dibuka seekable (mode ``"r"``) seperti biasa. Vault
    terkompresi → file temp berisi tar ter-zstd; dibaca lewat ``stream_reader`` dan
    dibuka tarfile mode streaming (``"r|"``) sehingga tar terdekompresi TIDAK perlu
    ditulis ulang ke disk (puncak pemakaian disk tetap ≈ ukuran payload, bukan 2×).
    Loop ekstraksi membaca tiap member secara berurutan & penuh, jadi kompatibel
    dengan mode streaming.
    """
    if not compressed:
        with tarfile.open(temp_tar_path, mode="r") as tar:
            yield tar
        return
    with temp_tar_path.open("rb") as f:
        reader = zstandard.ZstdDecompressor().stream_reader(f)
        with tarfile.open(fileobj=reader, mode="r|") as tar:
            yield tar


def _extract_and_place_vault(
    temp_tar_path: Path,
    temp_ext_dir: Path,
    nama_folder: str,
    path_tujuan: Path,
    progress_cb,
    is_cancelled: Callable[[], bool],
    compressed: bool = False,
) -> None:
    """
    Melakukan ekstraksi isi tar dari file temporary ke lokasi akhir.
    Termasuk TarSlip protection, progress, dan pemindahan folder. Bila ``compressed``,
    file temp didecompress streaming (zstd) tanpa menulis tar terdekompresi ke disk.
    """
    # Denominator progress: ukuran file temp (untuk vault terkompresi ini ukuran
    # TERKOMPRESI, jadi progress fase ekstraksi hanya perkiraan & ter-cap di 0.99).
    total_tar_size = temp_tar_path.stat().st_size
    extracted_bytes = 0

    with _open_payload_tar(temp_tar_path, compressed) as tar:
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
    Setiap record sudah mendapat tag GCM sendiri saat ditulis. Fungsi ini tetap
    hanya sanity check cepat, bukan full read-back.
    """
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if f.read(4) != MAGIC_BYTES:
                return False
            version = f.read(1)

        if version == VERSION:
            # Core header + slot_count(1) + minimal 1 slot + metadata & final record.
            min_slot = (
                1 + 1 + 2 + ARGON2ID_PARAMS_SIZE + SALT_SIZE + WRAP_NONCE_SIZE + WRAPPED_KEY_SIZE
            )
            return size >= CORE_HEADER_SIZE + 1 + min_slot + (2 * CHUNK_RECORD_OVERHEAD)
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


def _sanitize_virtual_name(name: str) -> str:
    """Pastikan nama root yang disimpan di metadata vault selalu lolos
    :func:`_validate_virtual_folder_name`.

    Dipanggil saat MEMBUAT vault. Tanpa ini, nama file vault / sumber yang
    mengandung karakter ilegal, berakhir titik/spasi, memakai nama device reserved
    Windows, atau diawali pola temp internal bisa menghasilkan vault yang sukses
    dibuat TAPI ditolak saat dibuka (undecryptable). Nilai hasilnya dipakai
    konsisten untuk metadata maupun root arcname tar sehingga round-trip cocok.
    """
    safe = "".join("_" if (ch in '/\\<>:"|?*' or ord(ch) < 32) else ch for ch in name)
    safe = safe.rstrip(" .")

    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if safe and (safe.split(".", 1)[0].upper() in reserved or safe.startswith("._dec_")):
        safe = "_" + safe

    # Batasi panjang byte (truncate aman terhadap multibyte) lalu rapikan ujung.
    safe = safe.encode("utf-8")[:MAX_VIRTUAL_NAME_LENGTH].decode("utf-8", "ignore").rstrip(" .")

    # Jaring pengaman: apa pun yang masih gagal validasi jatuh ke fallback aman.
    try:
        return _validate_virtual_folder_name(safe)
    except ValueError:
        return "Brankas"


# ── Resume cache untuk konfirmasi overwrite ──────────────────────────────────────
#
# Saat membuka vault dan folder tujuan sudah ada, SELURUH arsip tetap didekripsi &
# diverifikasi penuh (tag GCM tiap record, termasuk FINAL) SEBELUM user diminta
# konfirmasi overwrite — invariant keamanan "jangan prompt sebelum terverifikasi
# penuh" tidak berubah. Tapi alih-alih membuang tar plaintext yang sudah
# terverifikasi lalu mendekripsi ulang saat user menekan "Replace", tar itu
# disimpan sementara dan dipakai ulang. Jadi vault besar hanya didekripsi SEKALI.
#
# Asumsi konkurensi: hanya SATU operasi crypto berjalan pada satu waktu (dijamin
# lapisan UI yang mengunci tab lain), jadi akses cache ini efektif single-thread.
# Entri yatim (mis. user menutup app saat dialog terbuka) dibersihkan oleh sweep
# ``._dec_*`` di buka_brankas berdasarkan umur (OLD_TEMP_MAX_AGE_SECONDS).


class _PendingExtract:
    """Tar plaintext terverifikasi yang menunggu konfirmasi overwrite."""

    __slots__ = (
        "temp_ext_dir",
        "temp_tar_path",
        "nama_folder",
        "vault_size",
        "vault_mtime",
        "compressed",
    )

    def __init__(
        self, temp_ext_dir, temp_tar_path, nama_folder, vault_size, vault_mtime, compressed=False
    ):
        self.temp_ext_dir = temp_ext_dir
        self.temp_tar_path = temp_tar_path
        self.nama_folder = nama_folder
        self.vault_size = vault_size
        self.vault_mtime = vault_mtime
        self.compressed = compressed


_pending_extracts: dict[str, _PendingExtract] = {}


def _pending_key(locked_path) -> str:
    return os.path.normcase(os.path.abspath(str(locked_path)))


def _stat_signature(path: Path) -> tuple[int, int]:
    st = path.stat()
    return st.st_size, st.st_mtime_ns


def _discard_pending(key: str) -> None:
    """Buang entri pending dan bersihkan tar sementaranya (kalau masih ada)."""
    handle = _pending_extracts.pop(key, None)
    if handle is not None and handle.temp_ext_dir.exists():
        _cleanup_temp_decrypt_dir(handle.temp_ext_dir)


def cancel_pending_overwrite(locked_path) -> None:
    """Buang hasil dekripsi terverifikasi yang menunggu konfirmasi overwrite.

    Dipanggil UI saat user MENOLAK mengganti data lama (atau membatalkan), agar tar
    sementara tidak menumpuk sampai sweep umur membersihkannya. Aman dipanggil walau
    tidak ada yang tertunda.
    """
    _discard_pending(_pending_key(locked_path))


def _try_resume_overwrite(
    pkey: str,
    target_path: Path,
    progress_cb,
    is_cancelled: Callable[[], bool] | None,
) -> tuple[VaultStatus, str | None] | None:
    """Lanjutkan ekstraksi dari tar terverifikasi bila ada (skip dekripsi ulang).

    Return tuple hasil bila resume dipakai, atau ``None`` untuk jatuh ke alur
    dekripsi normal (cache basi, file vault berubah, atau tar sementara hilang).
    """
    handle = _pending_extracts.get(pkey)
    if handle is None:
        return None

    # Validasi kesegaran: vault tidak berubah & tar sementara masih ada. Kalau
    # tidak, buang dan biarkan pemanggil mendekripsi ulang dari awal (selalu aman).
    try:
        signature = _stat_signature(target_path)
    except OSError:
        _discard_pending(pkey)
        return None
    if (
        signature != (handle.vault_size, handle.vault_mtime)
        or not handle.temp_tar_path.exists()
        or not handle.temp_ext_dir.exists()
    ):
        _discard_pending(pkey)
        return None

    _pending_extracts.pop(pkey, None)
    path_tujuan = target_path.parent / handle.nama_folder
    try:
        _extract_and_place_vault(
            handle.temp_tar_path,
            handle.temp_ext_dir,
            handle.nama_folder,
            path_tujuan,
            progress_cb,
            is_cancelled,
            compressed=handle.compressed,
        )
        safe_cb(progress_cb, 1.0)
        return VaultStatus.SUCCESS, handle.nama_folder
    except InterruptedError:
        return VaultStatus.CANCELLED, "Operation cancelled. No existing data was changed."
    except Exception:
        logger.exception("Gagal melanjutkan ekstraksi (resume overwrite).")
        return VaultStatus.ERROR, GENERIC_FAILURE_MESSAGE
    finally:
        if handle.temp_ext_dir.exists():
            _cleanup_temp_decrypt_dir(handle.temp_ext_dir)


def _buka_brankas_from_open_file(
    fk,
    target_path: Path,
    total_size: int,
    password: str,
    force: bool,
    progress_cb,
    is_cancelled: Callable[[], bool] | None,
    keyfile_material: bytes | None = None,
) -> tuple[VaultStatus, str | None]:
    """Buka vault format envelope.

    Header memuat keyslot dan key record adalah Master Key yang di-unwrap dari
    salah satu slot (password atau recovery), lalu setiap record didekripsi dengan
    MK itu.

    Security invariant: plaintext record hanya ditulis setelah tag AEAD record itu
    valid; prompt overwrite hanya setelah seluruh record (termasuk FINAL) valid;
    data tujuan lama tidak disentuh sebelum tar terverifikasi penuh. Saat overwrite
    dibutuhkan, tar terverifikasi disimpan (``keep_temp``) untuk dipakai ulang oleh
    konfirmasi "Replace" lewat _try_resume_overwrite — tidak ada dekripsi ganda.
    """
    base_dir = target_path.parent
    temp_ext_dir: Path | None = None
    keep_temp = False  # True bila tar disimpan untuk resume konfirmasi overwrite

    try:
        try:
            hdr = _parse_header(fk)
        except ValueError as exc:
            return VaultStatus.ERROR, str(exc)

        file_id = hdr["file_id"]
        stored_chunk_size = hdr["chunk_size"]
        flags = hdr["flags"]
        compressed = bool(flags & FLAG_COMPRESSED)

        if stored_chunk_size <= 0 or stored_chunk_size > CHUNK_SIZE:
            return (
                VaultStatus.ERROR,
                "The vault's chunk parameters are invalid, or the file is corrupted.",
            )

        safe_cb(progress_cb, 0.02)
        master_key = _recover_master_key(
            password, file_id, _hint_bytes_from_header(hdr), hdr["slots"], keyfile_material
        )
        if master_key is None:
            return VaultStatus.WRONG_PASSWORD, None

        aesgcm = AESGCM(master_key)
        header_context = _record_context(file_id, stored_chunk_size, flags)
        safe_cb(progress_cb, 0.05)

        # Record 0 wajib metadata terenkripsi: panjang nama + nama virtual.
        record_type, record_index, plaintext_len, record_header = _read_record_header(fk)
        if (
            record_type != RECORD_TYPE_METADATA
            or record_index != 0
            or plaintext_len < 2
            or plaintext_len > 2 + MAX_VIRTUAL_NAME_LENGTH
        ):
            raise InvalidTag

        metadata_ciphertext = _read_exact(fk, plaintext_len + TAG_SIZE)
        metadata_plaintext = aesgcm.decrypt(
            _record_nonce(record_index),
            metadata_ciphertext,
            _record_aad(header_context, record_header),
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

                record_type, record_index, plaintext_len, record_header = _read_record_header(fk)
                if record_index != expected_index:
                    raise InvalidTag

                if record_type == RECORD_TYPE_DATA:
                    if plaintext_len <= 0 or plaintext_len > stored_chunk_size:
                        raise InvalidTag

                    ciphertext = _read_exact(fk, plaintext_len + TAG_SIZE)
                    plaintext = aesgcm.decrypt(
                        _record_nonce(record_index),
                        ciphertext,
                        _record_aad(header_context, record_header),
                    )
                    if len(plaintext) != plaintext_len:
                        raise InvalidTag

                    ftar.write(plaintext)
                    expected_index += 1

                    pct = min(0.85, 0.05 + 0.80 * (fk.tell() / max(total_size, 1)))
                    if pct - last_pct >= 0.005:
                        safe_cb(progress_cb, pct)
                        last_pct = pct

                elif record_type == RECORD_TYPE_FINAL:
                    if plaintext_len != 0:
                        raise InvalidTag
                    ciphertext = _read_exact(fk, TAG_SIZE)
                    final_plaintext = aesgcm.decrypt(
                        _record_nonce(record_index),
                        ciphertext,
                        _record_aad(header_context, record_header),
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
            raise InvalidTag

        safe_cb(progress_cb, 0.85)

        path_tujuan = base_dir / nama_folder
        if path_tujuan.exists() and not force:
            # Arsip sudah terverifikasi PENUH di atas. Simpan tar sementara &
            # tahan cleanup-nya supaya konfirmasi "Replace" bisa langsung
            # mengekstrak tanpa mendekripsi ulang vault (lihat _try_resume_overwrite).
            try:
                size, mtime = _stat_signature(target_path)
                pkey = _pending_key(target_path)
                _discard_pending(pkey)  # buang pending lama untuk vault ini bila ada
                _pending_extracts[pkey] = _PendingExtract(
                    temp_ext_dir, temp_tar_path, nama_folder, size, mtime, compressed
                )
                keep_temp = True
            except OSError:
                keep_temp = False  # gagal simpan → biarkan dibersihkan, retry dekripsi ulang
            return VaultStatus.OVERWRITE_NEEDED, nama_folder

        _extract_and_place_vault(
            temp_tar_path,
            temp_ext_dir,
            nama_folder,
            path_tujuan,
            progress_cb,
            is_cancelled,
            compressed=compressed,
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
    except Exception:
        logger.exception("Gagal membuka brankas envelope.")
        return VaultStatus.ERROR, GENERIC_FAILURE_MESSAGE
    finally:
        # keep_temp=True hanya saat tar disimpan untuk resume konfirmasi overwrite;
        # cleanup-nya jadi tanggung jawab _try_resume_overwrite / cancel_pending_overwrite.
        if temp_ext_dir and temp_ext_dir.exists() and not keep_temp:
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
    recovery_secret: str | None = None,
    recovery_type: str = "code",
    hint: str | None = None,
    kdf_params: dict[str, int] | None = None,
    keyfile_path: str | None = None,
    compress: bool = False,
) -> tuple[VaultStatus, str]:
    """Buat vault envelope dari ``paths``.

    ``recovery_secret`` opsional menambah keyslot kedua: ``recovery_type="code"``
    untuk kode app-generated (di-normalisasi saat unlock) atau ``"passphrase"``
    untuk frasa pilihan user. ``hint`` opsional disimpan TANPA enkripsi di header
    (harus terbaca sebelum unlock) dan dibatasi ``MAX_HINT_LENGTH`` byte.

    ``keyfile_path`` opsional mengaktifkan 2FA: slot password digabung dengan isi
    keyfile sehingga membuka vault WAJIB punya password DAN keyfile. Recovery key
    (bila ada) tetap membuka vault sendiri sebagai jalur break-glass.
    """
    valid_paths = [p for p in paths if Path(p).exists()]
    if not valid_paths:
        return VaultStatus.ERROR, "No valid file/folder to lock."

    if not password or not password.strip():
        return VaultStatus.ERROR, "Password cannot be empty."

    keyfile_material: bytes | None = None
    if keyfile_path:
        try:
            keyfile_material = _load_keyfile_material(keyfile_path)
        except ValueError as exc:
            return VaultStatus.ERROR, str(exc)

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

    # Keyfile (2FA) tidak boleh berada di dalam / sama dengan sumber yang dikunci:
    # ia akan ikut diarsipkan ke dalam vault DAN — bila "hapus asli" aktif — ikut
    # terhapus/di-wipe bersama sumber, sehingga vault butuh keyfile yang sudah lenyap
    # → terkunci permanen (kecuali ada recovery key). Tolak lebih awal.
    if keyfile_path:
        keyfile_obj = Path(keyfile_path)
        for source in valid_paths:
            if _target_conflicts_with_source(keyfile_obj, Path(source)):
                return (
                    VaultStatus.ERROR,
                    "The keyfile can't be the same as, or inside, the file or folder "
                    'being locked. It would be archived into the vault and — with "delete '
                    'original" on — wiped along with it, locking you out. Store the keyfile '
                    "somewhere else.",
                )

    if len(valid_paths) == 1:
        nama_virtual = _sanitize_virtual_name(Path(valid_paths[0]).name)
        target_dir = ""
    else:
        nama_virtual = _sanitize_virtual_name(target_path.stem or "Brankas_Rahasia")
        target_dir = nama_virtual

    backup_path: Path | None = None
    backup_dibuat = False

    try:
        free_space = shutil.disk_usage(target_path.parent).free
        total_size = _hitung_total_size(valid_paths)
        required_space = _hitung_kebutuhan_disk_kunci(
            valid_paths, nama_virtual, target_dir, compress
        )

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

        file_id = os.urandom(FILE_ID_SIZE)
        master_key = os.urandom(MASTER_KEY_SIZE)

        flags = FLAG_NONE
        hint_bytes = b""
        if hint:
            # Potong ke batas byte lalu bersihkan char multibyte yang terpotong.
            hint_bytes = hint.encode("utf-8")[:MAX_HINT_LENGTH]
            hint_bytes = hint_bytes.decode("utf-8", "ignore").encode("utf-8")
            if hint_bytes:
                flags |= FLAG_HINT
        if compress:
            flags |= FLAG_COMPRESSED

        pw_slot_type = SLOT_TYPE_PASSWORD_KEYFILE if keyfile_material else SLOT_TYPE_PASSWORD
        slots = [
            _build_keyslot(
                master_key,
                file_id,
                pw_slot_type,
                password,
                kdf_params=kdf_params,
                hint_bytes=hint_bytes,
                keyfile_material=keyfile_material,
            )
        ]
        if recovery_secret and recovery_secret.strip():
            rtype = (
                SLOT_TYPE_RECOVERY_CODE
                if recovery_type == "code"
                else SLOT_TYPE_RECOVERY_PASSPHRASE
            )
            slots.append(
                _build_keyslot(
                    master_key,
                    file_id,
                    rtype,
                    recovery_secret,
                    kdf_params=kdf_params,
                    hint_bytes=hint_bytes,
                )
            )

        header = _build_header(file_id, CHUNK_SIZE, flags, hint_bytes, slots)
        header_context = _record_context(file_id, CHUNK_SIZE, flags)
        aesgcm = AESGCM(master_key)
        safe_cb(progress_cb, 0.03)  # Key derivation + slot wrapping done

        with target_path.open("wb") as fk:
            fk.write(header)

            nama_bytes = nama_virtual.encode("utf-8")
            metadata_plaintext = len(nama_bytes).to_bytes(2, byteorder="big") + nama_bytes
            _write_record(
                fk,
                aesgcm,
                header_context,
                RECORD_TYPE_METADATA,
                0,
                metadata_plaintext,
            )

            # Saat kompresi aktif, ChunkedAEADEncryptingStream menerima byte TERKOMPRESI,
            # jadi progress-nya dimatikan (progress_cb=None) dan dilaporkan dari sisi
            # input tar oleh _CompressProgressWriter (berbasis byte uncompressed).
            out_stream = ChunkedAEADEncryptingStream(
                fk,
                aesgcm,
                header_context,
                None if compress else progress_cb,
                total_size,
                is_cancelled,
            )

            def _add_sources(tar):
                for p in valid_paths:
                    path_item = Path(p)
                    # Single-file: root arcname HARUS = nama_virtual (sudah disanitasi)
                    # agar cocok dengan nama yang divalidasi saat dekripsi. Multi-file:
                    # semua item ditaruh di bawah folder target_dir (= nama_virtual).
                    arcname = (
                        (Path(target_dir) / path_item.name).as_posix()
                        if target_dir
                        else nama_virtual
                    )
                    tar.add(path_item, arcname=arcname)

            if compress:
                # tar → zstd writer → out_stream (AEAD record). closefd=False agar
                # menutup zstd writer TIDAK menutup out_stream (finish() dipanggil sendiri).
                cctx = zstandard.ZstdCompressor(level=ZSTD_COMPRESSION_LEVEL)
                with cctx.stream_writer(out_stream, closefd=False) as zwriter:
                    tar_sink = _CompressProgressWriter(
                        zwriter, progress_cb, total_size, is_cancelled
                    )
                    with tarfile.open(fileobj=tar_sink, mode="w|") as tar:
                        _add_sources(tar)
                # zstd writer ditutup di sini → frame difinalkan, semua byte terkompresi
                # sudah mengalir ke out_stream.
                out_stream.finish()
            else:
                with tarfile.open(fileobj=out_stream, mode="w|") as tar:
                    _add_sources(tar)
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
    except Exception:
        logger.exception("Gagal mengunci brankas karena error tak terduga.")
        if target_path.exists():
            target_path.unlink(missing_ok=True)
        if backup_dibuat and backup_path and backup_path.exists():
            backup_path.replace(target_path)
        return VaultStatus.ERROR, GENERIC_FAILURE_MESSAGE


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
    keyfile_path: str | None = None,
) -> tuple[VaultStatus, str | None]:
    target_path = Path(locked_path)
    pkey = _pending_key(target_path)

    # Konfirmasi "Replace": kalau ada tar terverifikasi yang tertahan untuk vault
    # ini, ekstrak langsung tanpa mendekripsi ulang. Kalau cache basi/hilang,
    # _try_resume_overwrite mengembalikan None dan kita lanjut dekripsi normal.
    if force:
        resumed = _try_resume_overwrite(pkey, target_path, progress_cb, is_cancelled)
        if resumed is not None:
            return resumed
    else:
        # Pembukaan baru (non-force) menggantikan konfirmasi yang menggantung.
        _discard_pending(pkey)

    try:
        total_size = target_path.stat().st_size
        base_dir = target_path.parent

        with target_path.open("rb") as fk:
            # 1. Validasi Magic Bytes (sebelum cek ukuran agar file asing dilaporkan
            #    sebagai "bukan vault", bukan "terlalu kecil").
            magic = fk.read(4)
            if magic != MAGIC_BYTES:
                return (
                    VaultStatus.ERROR,
                    "This file isn't a valid Adyton Crypt vault.",
                )

            # 2. Validasi Versi
            version = fk.read(1)
            if version != VERSION:
                return (
                    VaultStatus.ERROR,
                    "This vault was made by a different version of Adyton Crypt. "
                    "Please update the app.",
                )

            # 3. Sanity ukuran: header inti + slot_count(1) + slot minimal +
            #    metadata & final record.
            min_slot = (
                1 + 1 + 2 + ARGON2ID_PARAMS_SIZE + SALT_SIZE + WRAP_NONCE_SIZE + WRAPPED_KEY_SIZE
            )
            min_size = CORE_HEADER_SIZE + 1 + min_slot + (2 * CHUNK_RECORD_OVERHEAD)
            if total_size < min_size:
                return VaultStatus.ERROR, "The vault file is too small or incomplete."

            # Intip flag kompresi (FLAGS = 4 byte terakhir core header) untuk reservasi
            # disk yang tepat, lalu seek kembali ke posisi tepat setelah VERSION agar
            # _parse_header (dipanggil _buka_brankas_from_open_file) tak terpengaruh.
            compressed = False
            peek = fk.read(CORE_HEADER_SIZE - 5)  # FILE_ID(16)+CHUNK_SIZE(4)+FLAGS(4)
            if len(peek) == CORE_HEADER_SIZE - 5:
                compressed = bool(int.from_bytes(peek[-4:], byteorder="big") & FLAG_COMPRESSED)
            fk.seek(5)

            # 4. Ruang disk: dekripsi menyimpan temp tar + ekstraksi (≈2× payload; lebih
            #    untuk vault terkompresi karena payload terdekompresi > ciphertext).
            free_space = shutil.disk_usage(base_dir).free
            required_space = _hitung_kebutuhan_disk_buka(total_size, compressed)
            if free_space < required_space:
                req_mb = required_space / (1024 * 1024)
                free_mb = free_space / (1024 * 1024)
                return (
                    VaultStatus.ERROR,
                    f"Not enough storage space.\nDisk free: {free_mb:.1f} MB. At least {req_mb:.1f} MB is required.",
                )

            # Hapus temp folder yang umurnya > 5 menit
            for old_temp in base_dir.glob("._dec_*"):
                if old_temp.is_dir():
                    try:
                        age = time.time() - old_temp.stat().st_mtime
                        if age > OLD_TEMP_MAX_AGE_SECONDS:
                            shutil.rmtree(old_temp, ignore_errors=True)
                    except Exception:
                        logger.debug("Gagal bersihkan old temp decrypt dir (diabaikan)")

            # Keyfile (2FA) di-load di sini agar jalur resume overwrite (force, di
            # atas) tak terpengaruh — resume memakai tar yang sudah terverifikasi.
            keyfile_material: bytes | None = None
            if keyfile_path:
                try:
                    keyfile_material = _load_keyfile_material(keyfile_path)
                except ValueError as exc:
                    return VaultStatus.ERROR, str(exc)

            safe_cb(progress_cb, 0.01)  # Mulai proses buka

            return _buka_brankas_from_open_file(
                fk,
                target_path,
                total_size,
                password,
                force,
                progress_cb,
                is_cancelled,
                keyfile_material,
            )

    except Exception:
        logger.exception(
            "Gagal membuka brankas karena error internal saat proses dekripsi/ekstraksi."
        )
        return VaultStatus.ERROR, GENERIC_FAILURE_MESSAGE


def verify_vault(
    locked_path: str,
    password: str,
    progress_cb=None,
    is_cancelled: Callable[[], bool] = None,
    keyfile_path: str | None = None,
) -> tuple[VaultStatus, str | None]:
    """Verifikasi sebuah vault tanpa menulis output (parity 7-Zip "Test").

    Membuktikan DUA hal sekaligus tanpa folder tujuan & tanpa plaintext menyentuh
    disk: (1) credential benar (password / recovery key / keyfile membuka salah satu
    slot), dan (2) seluruh arsip utuh sampai byte terakhir — setiap tag AES-GCM
    (metadata, semua data, FINAL) terverifikasi. Guna: cek brankas backup/arsip dari
    bit-rot, truncation, atau tamper tanpa membongkarnya, atau di komputer pinjaman
    tanpa plaintext jatuh ke disk.

    Status:
      * ``SUCCESS`` — credential benar & semua data utuh.
      * ``WRONG_PASSWORD`` — credential tidak membuka vault.
      * ``CANCELLED`` — dibatalkan user.
      * ``ERROR`` — bukan vault / versi beda / **vault rusak** (credential benar tapi
        ada record gagal cek integritas → pesan ``CORRUPT_VAULT_MESSAGE``).

    Tidak ada penulisan ke disk dan tidak menyentuh cache resume overwrite, jadi aman
    dipanggil kapan saja tanpa efek samping.
    """
    target_path = Path(locked_path)
    try:
        total_size = target_path.stat().st_size

        with target_path.open("rb") as fk:
            magic = fk.read(4)
            if magic != MAGIC_BYTES:
                return VaultStatus.ERROR, "This file isn't a valid Adyton Crypt vault."

            version = fk.read(1)
            if version != VERSION:
                return (
                    VaultStatus.ERROR,
                    "This vault was made by a different version of Adyton Crypt. "
                    "Please update the app.",
                )

            min_slot = (
                1 + 1 + 2 + ARGON2ID_PARAMS_SIZE + SALT_SIZE + WRAP_NONCE_SIZE + WRAPPED_KEY_SIZE
            )
            min_size = CORE_HEADER_SIZE + 1 + min_slot + (2 * CHUNK_RECORD_OVERHEAD)
            if total_size < min_size:
                return VaultStatus.ERROR, "The vault file is too small or incomplete."

            keyfile_material: bytes | None = None
            if keyfile_path:
                try:
                    keyfile_material = _load_keyfile_material(keyfile_path)
                except ValueError as exc:
                    return VaultStatus.ERROR, str(exc)

            try:
                hdr = _parse_header(fk)
            except ValueError as exc:
                return VaultStatus.ERROR, str(exc)

            file_id = hdr["file_id"]
            stored_chunk_size = hdr["chunk_size"]
            flags = hdr["flags"]
            if stored_chunk_size <= 0 or stored_chunk_size > CHUNK_SIZE:
                return (
                    VaultStatus.ERROR,
                    "The vault's chunk parameters are invalid, or the file is corrupted.",
                )

            safe_cb(progress_cb, 0.02)
            master_key = _recover_master_key(
                password, file_id, _hint_bytes_from_header(hdr), hdr["slots"], keyfile_material
            )
            if master_key is None:
                return VaultStatus.WRONG_PASSWORD, None

            aesgcm = AESGCM(master_key)
            header_context = _record_context(file_id, stored_chunk_size, flags)
            safe_cb(progress_cb, 0.05)

            # Credential SUDAH terbukti benar; mulai dari sini setiap InvalidTag berarti
            # DATA yang rusak (bukan password salah). Bedakan agar pesan ke user jujur:
            # "vault rusak", bukan "password salah".
            try:
                # Record 0: metadata terenkripsi (panjang nama + nama virtual).
                record_type, record_index, plaintext_len, record_header = _read_record_header(fk)
                if (
                    record_type != RECORD_TYPE_METADATA
                    or record_index != 0
                    or plaintext_len < 2
                    or plaintext_len > 2 + MAX_VIRTUAL_NAME_LENGTH
                ):
                    raise InvalidTag
                metadata_ciphertext = _read_exact(fk, plaintext_len + TAG_SIZE)
                metadata_plaintext = aesgcm.decrypt(
                    _record_nonce(record_index),
                    metadata_ciphertext,
                    _record_aad(header_context, record_header),
                )
                _parse_virtual_folder_name(metadata_plaintext)

                expected_index = 1
                last_pct = 0.0
                while True:
                    if is_cancelled and is_cancelled():
                        return VaultStatus.CANCELLED, "Verification cancelled."

                    record_type, record_index, plaintext_len, record_header = _read_record_header(
                        fk
                    )
                    if record_index != expected_index:
                        raise InvalidTag

                    if record_type == RECORD_TYPE_DATA:
                        if plaintext_len <= 0 or plaintext_len > stored_chunk_size:
                            raise InvalidTag
                        ciphertext = _read_exact(fk, plaintext_len + TAG_SIZE)
                        plaintext = aesgcm.decrypt(
                            _record_nonce(record_index),
                            ciphertext,
                            _record_aad(header_context, record_header),
                        )
                        # Plaintext sengaja DIBUANG (tak ditulis ke disk); kita hanya
                        # peduli tag-nya valid. Cek panjang sebagai jaring tambahan.
                        if len(plaintext) != plaintext_len:
                            raise InvalidTag
                        expected_index += 1

                        pct = min(0.98, 0.05 + 0.93 * (fk.tell() / max(total_size, 1)))
                        if pct - last_pct >= 0.005:
                            safe_cb(progress_cb, pct)
                            last_pct = pct

                    elif record_type == RECORD_TYPE_FINAL:
                        if plaintext_len != 0:
                            raise InvalidTag
                        ciphertext = _read_exact(fk, TAG_SIZE)
                        final_plaintext = aesgcm.decrypt(
                            _record_nonce(record_index),
                            ciphertext,
                            _record_aad(header_context, record_header),
                        )
                        if final_plaintext != b"":
                            raise InvalidTag
                        break
                    else:
                        raise InvalidTag

                # Tidak boleh ada byte sisa setelah FINAL — kalau ada, file tak konsisten.
                if fk.tell() != total_size:
                    raise InvalidTag
            except InvalidTag:
                return VaultStatus.ERROR, CORRUPT_VAULT_MESSAGE
            except ValueError:
                # _parse_virtual_folder_name menolak metadata yang strukturnya aneh.
                # Dengan MK yang benar ini menandakan korupsi, bukan password salah.
                return VaultStatus.ERROR, CORRUPT_VAULT_MESSAGE

        safe_cb(progress_cb, 1.0)
        return (
            VaultStatus.SUCCESS,
            "Vault verified — your credential is correct and all data is intact.",
        )

    except Exception:
        logger.exception("Gagal memverifikasi brankas.")
        return VaultStatus.ERROR, GENERIC_FAILURE_MESSAGE


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


# ── Manajemen credential vault (ganti password / recovery / hint) ────────────────


def _format_label(version: bytes | None) -> str:
    return "Adyton Vault" if version == VERSION else "unknown"


def read_vault_hint(vault_path: str) -> str | None:
    """Baca password hint dari header tanpa perlu password. None jika tidak ada."""
    try:
        return _read_header_from_path(Path(vault_path)).get("hint")
    except Exception:
        return None


def vault_info(vault_path: str) -> dict:
    """Ringkas metadata vault untuk UI tanpa membutuhkan password.

    Mengembalikan format, ada/tidaknya hint & recovery key, dan apakah vault
    mendukung ganti password. Tidak pernah melempar exception.
    """
    info = {
        "format": "unknown",
        "supports_change_password": False,
        "has_hint": False,
        "hint": None,
        "has_recovery": False,
        "requires_keyfile": False,
        "slot_count": 0,
    }
    path = Path(vault_path)
    try:
        with path.open("rb") as fk:
            if fk.read(4) != MAGIC_BYTES:
                return info
            version = fk.read(1)
        info["format"] = _format_label(version)
        if version != VERSION:
            return info

        hdr = _read_header_from_path(path)
        info.update(
            {
                "supports_change_password": True,
                "has_hint": hdr["hint"] is not None,
                "hint": hdr["hint"],
                "has_recovery": any(s["slot_type"] in RECOVERY_SLOT_TYPES for s in hdr["slots"]),
                "requires_keyfile": any(
                    s["slot_type"] == SLOT_TYPE_PASSWORD_KEYFILE for s in hdr["slots"]
                ),
                "slot_count": len(hdr["slots"]),
            }
        )
    except Exception:
        logger.opt(exception=True).debug("vault_info gagal membaca header (non-fatal)")
    return info


def _load_for_management(
    path: Path,
    secret: str,
    keyfile_material: bytes | None = None,
) -> tuple[VaultStatus, str | None, dict | None, bytes | None]:
    """Buka header + recover Master Key untuk operasi manajemen credential.

    Return ``(status, message_or_None, header_or_None, master_key_or_None)``.
    Status SUCCESS berarti ``header`` dan ``master_key`` terisi. ``keyfile_material``
    dipakai untuk membuka slot 2FA (lihat ``_recover_master_key``).
    """
    try:
        hdr = _read_header_from_path(path)
    except ValueError as exc:
        if str(exc) == "wrong_format":
            return (
                VaultStatus.ERROR,
                "This vault was made by a different version of Adyton Crypt and "
                "can't be managed here. Please update the app.",
                None,
                None,
            )
        return VaultStatus.ERROR, str(exc), None, None
    except FileNotFoundError:
        return VaultStatus.ERROR, "The vault file could not be found.", None, None
    except Exception:
        logger.exception("Gagal membaca header untuk manajemen.")
        return VaultStatus.ERROR, GENERIC_FAILURE_MESSAGE, None, None

    master_key = _recover_master_key(
        secret, hdr["file_id"], _hint_bytes_from_header(hdr), hdr["slots"], keyfile_material
    )
    if master_key is None:
        return VaultStatus.WRONG_PASSWORD, None, None, None

    return VaultStatus.SUCCESS, None, hdr, master_key


def _load_keyfile_material_optional(keyfile_path: str | None) -> tuple[bytes | None, str | None]:
    """Load keyfile bila path diberikan. Return ``(material, error_message)``.

    ``material`` None bila tak ada keyfile; ``error_message`` non-None bila path
    diberikan tapi gagal dibaca (pesan path-free aman ditampilkan).
    """
    if not keyfile_path:
        return None, None
    try:
        return _load_keyfile_material(keyfile_path), None
    except ValueError as exc:
        return None, str(exc)


def _read_header_for_management(path: Path) -> tuple[VaultStatus, str | None, dict | None]:
    """Baca header vault untuk operasi manajemen TANPA membukanya (tanpa credential).

    Memetakan error baca header ke pesan path-free yang aman ditampilkan. Dipakai
    operasi yang perlu inspeksi slot sebelum unlock (mis. tambah/hapus keyfile yang
    membuka slot password secara spesifik, bukan slot apa pun).
    """
    try:
        return VaultStatus.SUCCESS, None, _read_header_from_path(path)
    except ValueError as exc:
        if str(exc) == "wrong_format":
            return (
                VaultStatus.ERROR,
                "This vault was made by a different version of Adyton Crypt and "
                "can't be managed here. Please update the app.",
                None,
            )
        return VaultStatus.ERROR, str(exc), None
    except FileNotFoundError:
        return VaultStatus.ERROR, "The vault file could not be found.", None
    except Exception:
        logger.exception("Gagal membaca header untuk manajemen.")
        return VaultStatus.ERROR, GENERIC_FAILURE_MESSAGE, None


def _hint_bytes_from_header(hdr: dict) -> bytes:
    """Byte hint mentah persis seperti tersimpan di header.

    Dipakai untuk DUA hal yang harus konsisten byte-per-byte: menulis ulang header
    (``_build_header``) dan mengikat hint ke AAD wrap (``_slot_wrap_aad``). Kalau
    keduanya tidak identik, MK tidak akan bisa di-unwrap setelah header ditulis ulang.
    """
    return hdr.get("hint_bytes", b"")


def _rewrite_header_full(
    path: Path, old_header_end: int, new_header: bytes
) -> tuple[VaultStatus, str]:
    """Tulis ulang header yang panjangnya berubah, lewat temp file + atomic replace.

    Dipakai saat menambah/menghapus keyslot (header bertambah/berkurang). Record
    di belakang header disalin apa adanya — O(ukuran vault), tapi aman karena
    file asli baru diganti setelah temp lengkap & ter-fsync.
    """
    tmp: Path | None = None
    try:
        free = shutil.disk_usage(path.parent).free
        if free < path.stat().st_size + DISK_OVERHEAD_BYTES:
            return VaultStatus.ERROR, "Not enough storage space to update the vault."

        tmp = _make_unique_replace_backup_path(path)
        with path.open("rb") as src, tmp.open("wb") as dst:
            dst.write(new_header)
            src.seek(old_header_end)
            while True:
                chunk = src.read(CHUNK_SIZE)
                if not chunk:
                    break
                dst.write(chunk)
            dst.flush()
            os.fsync(dst.fileno())

        os.replace(tmp, path)
        tmp = None
        return VaultStatus.SUCCESS, "Vault updated successfully."
    except Exception:
        logger.exception("Gagal menulis ulang header (full rewrite).")
        if tmp is not None:
            with contextlib.suppress(Exception):
                tmp.unlink(missing_ok=True)
        return VaultStatus.ERROR, GENERIC_FAILURE_MESSAGE


def _unlock_password_slot(
    hdr: dict, password: str, keyfile_material: bytes | None = None
) -> bytes | None:
    """Unwrap MK lewat slot PASSWORD vault secara spesifik (bukan slot recovery).

    Dipakai operasi yang mengubah faktor password (tambah/hapus keyfile) sehingga
    yakin secret yang diberikan benar-benar password — bukan recovery key yang
    kebetulan membuka slot lain — sebelum slot password ditulis ulang.
    """
    pw_slot = next((s for s in hdr["slots"] if s["slot_type"] in PASSWORD_SLOT_TYPES), None)
    if pw_slot is None:
        return None
    kek = _derive_slot_kek(
        pw_slot["slot_type"],
        password,
        pw_slot["salt"],
        pw_slot["kdf_id"],
        pw_slot["kdf_params"],
        keyfile_material,
    )
    if kek is None:
        return None
    try:
        master_key = AESGCM(kek).decrypt(
            pw_slot["wrap_nonce"],
            pw_slot["wrapped"],
            _slot_wrap_aad(hdr["file_id"], _hint_bytes_from_header(hdr), pw_slot["meta"]),
        )
    except (InvalidTag, ValueError):
        return None
    return master_key if len(master_key) == MASTER_KEY_SIZE else None


def change_password(
    vault_path: str,
    old_password: str,
    new_password: str,
    keyfile_path: str | None = None,
) -> tuple[VaultStatus, str | None]:
    """Ganti password vault tanpa mengenkripsi ulang data.

    Hanya keyslot password yang ditulis ulang (panjang identik), jadi operasi ini
    O(ukuran header), bukan O(ukuran vault). ``old_password`` boleh berupa password
    lama ATAU recovery key — apa pun yang berhasil membuka salah satu slot.

    Untuk vault 2FA (slot password dilindungi keyfile), ``keyfile_path`` WAJIB
    diberikan: slot password baru tetap dilindungi keyfile yang sama, jadi 2FA tidak
    diam-diam dilepas. (Melepas keyfile adalah aksi terpisah ``remove_keyfile``.)
    """
    if not new_password or not new_password.strip():
        return VaultStatus.ERROR, "New password cannot be empty."

    keyfile_material, kf_error = _load_keyfile_material_optional(keyfile_path)
    if kf_error:
        return VaultStatus.ERROR, kf_error

    path = Path(vault_path)
    status, message, hdr = _read_header_for_management(path)
    if status != VaultStatus.SUCCESS:
        return status, message

    pw_index = next(
        (i for i, s in enumerate(hdr["slots"]) if s["slot_type"] in PASSWORD_SLOT_TYPES),
        None,
    )
    if pw_index is None:
        return VaultStatus.ERROR, "This vault has no password slot to change."

    pw_slot_type = hdr["slots"][pw_index]["slot_type"]
    # Cek kebutuhan keyfile SEBELUM unlock agar pesan membantu (bukan WRONG_PASSWORD):
    # slot password baru tetap dilindungi keyfile, jadi keyfile wajib untuk membangunnya.
    if pw_slot_type == SLOT_TYPE_PASSWORD_KEYFILE and keyfile_material is None:
        return (
            VaultStatus.ERROR,
            "This vault uses a keyfile. Select the keyfile to change its password.",
        )

    master_key = _recover_master_key(
        old_password, hdr["file_id"], _hint_bytes_from_header(hdr), hdr["slots"], keyfile_material
    )
    if master_key is None:
        return VaultStatus.WRONG_PASSWORD, None

    # Pertahankan level KDF slot lama agar header tetap sepanjang semula (invariant
    # re-key in-place) dan kekuatan yang dipilih user tidak diam-diam diturunkan.
    slot_bytes = [_slot_bytes(s) for s in hdr["slots"]]
    slot_bytes[pw_index] = _build_keyslot(
        master_key,
        hdr["file_id"],
        pw_slot_type,
        new_password,
        kdf_params=hdr["slots"][pw_index]["kdf_params"],
        hint_bytes=_hint_bytes_from_header(hdr),
        keyfile_material=keyfile_material,
    )
    new_header = _build_header(
        hdr["file_id"], hdr["chunk_size"], hdr["flags"], _hint_bytes_from_header(hdr), slot_bytes
    )

    # Re-key tidak boleh mengubah panjang header (slot password fixed-size). Kalau
    # berubah, batalkan tanpa menulis apa pun demi keamanan.
    if len(new_header) != hdr["header_end"]:
        return VaultStatus.ERROR, "Internal error: header length changed during re-key."

    # Tulis lewat temp file + atomic os.replace, BUKAN overwrite in-place. Region
    # keyslot bisa melebihi satu sektor disk (hint + beberapa slot), jadi tulis
    # in-place rentan torn-write saat power-loss di tengah tulis → vault rusak dan
    # tak bisa dibuka oleh password lama MAUPUN baru. Konsisten dengan
    # add_recovery_key / remove_recovery_key.
    status, message = _rewrite_header_full(path, hdr["header_end"], new_header)
    if status == VaultStatus.SUCCESS:
        return VaultStatus.SUCCESS, "Password changed successfully."
    return status, message


def add_recovery_key(
    vault_path: str,
    password: str,
    recovery_secret: str,
    recovery_type: str = "code",
    keyfile_path: str | None = None,
) -> tuple[VaultStatus, str | None]:
    """Tambahkan keyslot recovery ke vault yang sudah ada.

    Header bertambah panjang, jadi vault ditulis ulang (temp + atomic replace).
    Menolak bila sudah ada recovery key. Untuk vault 2FA, ``keyfile_path`` dipakai
    bersama ``password`` untuk membukanya.
    """
    if not recovery_secret or not recovery_secret.strip():
        return VaultStatus.ERROR, "Recovery secret cannot be empty."

    keyfile_material, kf_error = _load_keyfile_material_optional(keyfile_path)
    if kf_error:
        return VaultStatus.ERROR, kf_error

    path = Path(vault_path)
    status, message, hdr, master_key = _load_for_management(path, password, keyfile_material)
    if status != VaultStatus.SUCCESS:
        return status, message

    if any(s["slot_type"] in RECOVERY_SLOT_TYPES for s in hdr["slots"]):
        return (
            VaultStatus.ERROR,
            "This vault already has a recovery key. Remove it first to set a new one.",
        )
    if len(hdr["slots"]) >= MAX_KEYSLOTS:
        return VaultStatus.ERROR, "This vault already has the maximum number of keyslots."

    # Samakan level KDF recovery dengan slot password vault agar konsisten.
    pw_slot = next((s for s in hdr["slots"] if s["slot_type"] in PASSWORD_SLOT_TYPES), None)
    level_params = pw_slot["kdf_params"] if pw_slot else None
    rtype = SLOT_TYPE_RECOVERY_CODE if recovery_type == "code" else SLOT_TYPE_RECOVERY_PASSPHRASE
    new_slot = _build_keyslot(
        master_key,
        hdr["file_id"],
        rtype,
        recovery_secret,
        kdf_params=level_params,
        hint_bytes=_hint_bytes_from_header(hdr),
    )
    slot_bytes = [_slot_bytes(s) for s in hdr["slots"]] + [new_slot]
    new_header = _build_header(
        hdr["file_id"], hdr["chunk_size"], hdr["flags"], _hint_bytes_from_header(hdr), slot_bytes
    )
    return _rewrite_header_full(path, hdr["header_end"], new_header)


def remove_recovery_key(
    vault_path: str,
    password: str,
    keyfile_path: str | None = None,
) -> tuple[VaultStatus, str | None]:
    """Hapus keyslot recovery dari vault. ``password`` harus membuka slot mana pun.

    Untuk vault 2FA, ``keyfile_path`` dipakai bersama ``password`` untuk membukanya.
    """
    keyfile_material, kf_error = _load_keyfile_material_optional(keyfile_path)
    if kf_error:
        return VaultStatus.ERROR, kf_error

    path = Path(vault_path)
    status, message, hdr, master_key = _load_for_management(path, password, keyfile_material)
    if status != VaultStatus.SUCCESS:
        return status, message

    kept = [s for s in hdr["slots"] if s["slot_type"] not in RECOVERY_SLOT_TYPES]
    if len(kept) == len(hdr["slots"]):
        return VaultStatus.ERROR, "This vault has no recovery key to remove."
    if not kept:
        return VaultStatus.ERROR, "Cannot remove the last keyslot from the vault."

    slot_bytes = [_slot_bytes(s) for s in kept]
    new_header = _build_header(
        hdr["file_id"], hdr["chunk_size"], hdr["flags"], _hint_bytes_from_header(hdr), slot_bytes
    )
    return _rewrite_header_full(path, hdr["header_end"], new_header)


def add_keyfile(
    vault_path: str,
    password: str,
    keyfile_path: str,
) -> tuple[VaultStatus, str | None]:
    """Aktifkan 2FA pada vault yang sudah ada: lindungi slot password dengan keyfile.

    Yang BERUBAH hanya region keyslot (panjang header identik — slot password & slot
    keyfile berukuran sama), tapi penulisannya tetap lewat ``_rewrite_header_full``
    (temp + atomic replace) yang **menyalin seluruh isi vault**, jadi secara I/O ini
    **O(ukuran vault)** dan butuh ruang disk kosong ≈ sebesar vault (bisa memunculkan
    "Not enough storage space to update the vault" untuk vault besar). ``password``
    HARUS membuka slot password (bukan recovery key), karena slot itu dibangun ulang
    menjadi slot keyfile dari password yang sama.
    """
    keyfile_material, kf_error = _load_keyfile_material_optional(keyfile_path)
    if kf_error:
        return VaultStatus.ERROR, kf_error
    if keyfile_material is None:
        return VaultStatus.ERROR, "Select a keyfile to protect this vault."

    path = Path(vault_path)
    status, message, hdr = _read_header_for_management(path)
    if status != VaultStatus.SUCCESS:
        return status, message

    pw_index = next(
        (i for i, s in enumerate(hdr["slots"]) if s["slot_type"] in PASSWORD_SLOT_TYPES),
        None,
    )
    if pw_index is None:
        return VaultStatus.ERROR, "This vault has no password slot."
    if hdr["slots"][pw_index]["slot_type"] == SLOT_TYPE_PASSWORD_KEYFILE:
        return VaultStatus.ERROR, "This vault is already protected by a keyfile."

    # Buktikan secret adalah password (membuka slot password), lalu bangun ulang slot
    # itu sebagai slot keyfile dari password yang sama.
    master_key = _unlock_password_slot(hdr, password)
    if master_key is None:
        return VaultStatus.WRONG_PASSWORD, None

    slot_bytes = [_slot_bytes(s) for s in hdr["slots"]]
    slot_bytes[pw_index] = _build_keyslot(
        master_key,
        hdr["file_id"],
        SLOT_TYPE_PASSWORD_KEYFILE,
        password,
        kdf_params=hdr["slots"][pw_index]["kdf_params"],
        hint_bytes=_hint_bytes_from_header(hdr),
        keyfile_material=keyfile_material,
    )
    new_header = _build_header(
        hdr["file_id"], hdr["chunk_size"], hdr["flags"], _hint_bytes_from_header(hdr), slot_bytes
    )
    if len(new_header) != hdr["header_end"]:
        return VaultStatus.ERROR, "Internal error: header length changed while adding keyfile."

    status, message = _rewrite_header_full(path, hdr["header_end"], new_header)
    if status == VaultStatus.SUCCESS:
        return (
            VaultStatus.SUCCESS,
            "Keyfile added. You'll now need it plus your password to open this vault.",
        )
    return status, message


def remove_keyfile(
    vault_path: str,
    password: str,
    keyfile_path: str,
) -> tuple[VaultStatus, str | None]:
    """Matikan 2FA: lepas perlindungan keyfile dari slot password.

    Membutuhkan ``password`` DAN ``keyfile_path`` (keduanya membuka slot password),
    lalu membangun ulang slot itu sebagai slot password biasa. Panjang header tetap,
    tetapi seperti ``add_keyfile`` penulisannya lewat ``_rewrite_header_full`` yang
    menyalin seluruh isi vault → secara I/O **O(ukuran vault)** + butuh ruang disk
    kosong ≈ sebesar vault.
    """
    keyfile_material, kf_error = _load_keyfile_material_optional(keyfile_path)
    if kf_error:
        return VaultStatus.ERROR, kf_error
    if keyfile_material is None:
        return VaultStatus.ERROR, "Select the keyfile to remove keyfile protection."

    path = Path(vault_path)
    status, message, hdr = _read_header_for_management(path)
    if status != VaultStatus.SUCCESS:
        return status, message

    pw_index = next(
        (i for i, s in enumerate(hdr["slots"]) if s["slot_type"] in PASSWORD_SLOT_TYPES),
        None,
    )
    if pw_index is None:
        return VaultStatus.ERROR, "This vault has no password slot."
    if hdr["slots"][pw_index]["slot_type"] != SLOT_TYPE_PASSWORD_KEYFILE:
        return VaultStatus.ERROR, "This vault isn't protected by a keyfile."

    master_key = _unlock_password_slot(hdr, password, keyfile_material)
    if master_key is None:
        return VaultStatus.WRONG_PASSWORD, None

    slot_bytes = [_slot_bytes(s) for s in hdr["slots"]]
    slot_bytes[pw_index] = _build_keyslot(
        master_key,
        hdr["file_id"],
        SLOT_TYPE_PASSWORD,
        password,
        kdf_params=hdr["slots"][pw_index]["kdf_params"],
        hint_bytes=_hint_bytes_from_header(hdr),
    )
    new_header = _build_header(
        hdr["file_id"], hdr["chunk_size"], hdr["flags"], _hint_bytes_from_header(hdr), slot_bytes
    )
    if len(new_header) != hdr["header_end"]:
        return VaultStatus.ERROR, "Internal error: header length changed while removing keyfile."

    status, message = _rewrite_header_full(path, hdr["header_end"], new_header)
    if status == VaultStatus.SUCCESS:
        return VaultStatus.SUCCESS, "Keyfile removed. Your password alone now opens this vault."
    return status, message
