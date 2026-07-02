"""
core/vault_extract.py
Ekstraksi, secure wipe, temp-file handling, pending/resume-overwrite, dan
orkestrasi buka/unlock vault.
"""

import contextlib
import os
import shutil
import stat
import tarfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path, PureWindowsPath

import zstandard
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from loguru import logger

from .constants import (
    ARGON2ID_PARAMS_SIZE,
    CHUNK_RECORD_OVERHEAD,
    CHUNK_SIZE,
    COMPRESSED_DECRYPT_RATIO_GUESS,
    CORE_HEADER_SIZE,
    CORRUPT_VAULT_MESSAGE,
    DISK_OVERHEAD_BYTES,
    EXTRACT_STAGING_PREFIX,
    FLAG_COMPRESSED,
    GENERIC_FAILURE_MESSAGE,
    MAGIC_BYTES,
    MAX_HEADER_SIZE,
    MAX_VIRTUAL_NAME_LENGTH,
    OLD_TEMP_MAX_AGE_SECONDS,
    RECORD_TYPE_DATA,
    RECORD_TYPE_FINAL,
    RECORD_TYPE_METADATA,
    SALT_SIZE,
    TAG_SIZE,
    VERSION,
    WRAP_NONCE_SIZE,
    WRAPPED_KEY_SIZE,
    ZSTD_DISK_ESTIMATE_RATIO,
    VaultEntry,
    VaultStatus,
)
from .crypto import safe_cb
from .vault_stream import (
    ChunkedAEADDecryptingStream,
    _hint_bytes_from_header,
    _load_keyfile_material,
    _parse_header,
    _read_exact,
    _read_record_header,
    _record_aad,
    _record_context,
    _record_nonce,
    _recover_master_key,
)


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


class _VaultOpenError(Exception):
    """Sinyal internal saat membuka vault untuk browse/ekstrak (bukan bug).

    Membawa ``VaultStatus`` + pesan agar pemanggil publik memetakan hasil dengan
    tepat: format asing / chunk aneh → ``ERROR``; credential salah → ``WRONG_PASSWORD``;
    data rusak setelah credential benar → ``ERROR`` + ``CORRUPT_VAULT_MESSAGE``.
    """

    def __init__(self, status: VaultStatus, message: str | None):
        super().__init__(message or "")
        self.status = status
        self.message = message


def _open_and_unlock(
    fk, password: str, keyfile_material: bytes | None
) -> tuple[dict, AESGCM, bytes, str]:
    """Parse header, pulihkan Master Key, & baca record metadata (nama folder root).

    ``fk`` harus berada tepat SETELAH byte VERSION (MAGIC+VERSION sudah divalidasi
    pemanggil). Mengembalikan ``(hdr, aesgcm, header_context, nama_folder)``. Melempar
    ``_VaultOpenError`` untuk semua kegagalan yang diharapkan sehingga pemanggil publik
    (list/extract) memetakan status secara seragam. Setelah MK terbukti benar (AAD wrap
    mengikat credential), kegagalan berikutnya diperlakukan sebagai KORUPSI — bukan
    password salah — sama seperti ``verify_vault``.
    """
    try:
        hdr = _parse_header(fk)
    except ValueError as exc:
        raise _VaultOpenError(VaultStatus.ERROR, str(exc)) from exc

    stored_chunk_size = hdr["chunk_size"]
    if stored_chunk_size <= 0 or stored_chunk_size > CHUNK_SIZE:
        raise _VaultOpenError(
            VaultStatus.ERROR,
            "The vault's chunk parameters are invalid, or the file is corrupted.",
        )

    master_key = _recover_master_key(
        password, hdr["file_id"], _hint_bytes_from_header(hdr), hdr["slots"], keyfile_material
    )
    if master_key is None:
        raise _VaultOpenError(VaultStatus.WRONG_PASSWORD, None)

    aesgcm = AESGCM(master_key)
    header_context = _record_context(hdr["file_id"], stored_chunk_size, hdr["flags"])

    try:
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
        nama_folder, name_offset = _parse_virtual_folder_name(metadata_plaintext)
        if name_offset != len(metadata_plaintext):
            raise ValueError("invalid extra metadata")
    except (InvalidTag, ValueError) as exc:
        raise _VaultOpenError(VaultStatus.ERROR, CORRUPT_VAULT_MESSAGE) from exc

    return hdr, aesgcm, header_context, nama_folder


@contextlib.contextmanager
def _open_payload_tar_stream(
    fk,
    aesgcm: AESGCM,
    header_context: bytes,
    stored_chunk_size: int,
    total_size: int,
    compressed: bool,
    progress_cb=None,
    is_cancelled: Callable[[], bool] | None = None,
):
    """Buka payload tar langsung dari ``fk`` via stream-decrypt (tanpa temp file).

    Membungkus ``ChunkedAEADDecryptingStream`` (→ zstd ``stream_reader`` bila
    terkompresi) dengan ``tarfile`` mode ``"r|"``. Dipakai browse & ekstrak selektif:
    tak ada plaintext seluruh payload yang jatuh ke disk. Pola sama dengan
    ``_open_payload_tar`` tapi sumbernya reader in-memory, bukan tar temp.
    """
    reader = ChunkedAEADDecryptingStream(
        fk,
        aesgcm,
        header_context,
        stored_chunk_size,
        total_size,
        start_index=1,
        progress_cb=progress_cb,
        is_cancelled=is_cancelled,
    )
    try:
        if compressed:
            zreader = zstandard.ZstdDecompressor().stream_reader(reader)
            with tarfile.open(fileobj=zreader, mode="r|") as tar:
                yield tar
        else:
            with tarfile.open(fileobj=reader, mode="r|") as tar:
                yield tar
    finally:
        reader.close()


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


def discard_all_pending_overwrites() -> None:
    """Buang SEMUA hasil dekripsi tertunda beserta tar plaintext sementaranya.

    Dipanggil saat aplikasi keluar (``aboutToQuit``). Tanpa ini, menutup app saat
    dialog konfirmasi overwrite masih terbuka meninggalkan tar plaintext di disk
    tanpa batas waktu — sweep umur ``._dec_*`` hanya berjalan bila user membuka
    vault lagi di folder yang sama.
    """
    for key in list(_pending_extracts):
        _discard_pending(key)


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
            # Metadata sudah terautentikasi (MK benar) tapi strukturnya tak valid —
            # itu korupsi, bukan password salah (konsisten dgn verify/_open_and_unlock).
            return VaultStatus.ERROR, CORRUPT_VAULT_MESSAGE

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
        # Credential salah sudah ditangani eksplisit di atas (unwrap gagal →
        # WRONG_PASSWORD). InvalidTag yang sampai ke sini berarti record/tail
        # yang rusak atau file terpotong — laporkan jujur sebagai vault korup
        # (konsisten dengan verify_vault), bukan "password salah".
        return VaultStatus.ERROR, CORRUPT_VAULT_MESSAGE
    except (tarfile.ReadError, zstandard.ZstdError):
        # Payload sudah lolos seluruh tag AEAD tapi bukan tar/zstd yang valid —
        # isi vault rusak sejak dibuat / diubah; password terbukti benar.
        return VaultStatus.ERROR, CORRUPT_VAULT_MESSAGE
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


# ── Browse isi + ekstrak selektif (read-only, stream-decrypt) ────────────────────


def _read_and_check_prelude(fk, total_size: int) -> None:
    """Validasi MAGIC+VERSION+ukuran minimum; ``fk`` maju ke tepat setelah VERSION.

    Melempar ``_VaultOpenError`` (ERROR) untuk file asing / versi beda / terlalu kecil.
    """
    if fk.read(4) != MAGIC_BYTES:
        raise _VaultOpenError(VaultStatus.ERROR, "This file isn't a valid Adyton Crypt vault.")
    if fk.read(1) != VERSION:
        raise _VaultOpenError(
            VaultStatus.ERROR,
            "This vault was made by a different version of Adyton Crypt. Please update the app.",
        )
    min_slot = 1 + 1 + 2 + ARGON2ID_PARAMS_SIZE + SALT_SIZE + WRAP_NONCE_SIZE + WRAPPED_KEY_SIZE
    min_size = CORE_HEADER_SIZE + 1 + min_slot + (2 * CHUNK_RECORD_OVERHEAD)
    if total_size < min_size:
        raise _VaultOpenError(VaultStatus.ERROR, "The vault file is too small or incomplete.")


def _rel_to_root(name: str, root: str) -> str:
    """Nama member tar → path relatif terhadap folder root (pemisah ``/``).

    Mengembalikan ``""`` untuk entri root itu sendiri.
    """
    norm = name.replace("\\", "/").strip("/")
    root = root.replace("\\", "/").strip("/")
    if norm == root:
        return ""
    prefix = root + "/"
    if norm.startswith(prefix):
        return norm[len(prefix) :]
    return norm


def _rel_selected(rel: str, selected_set: set[str]) -> bool:
    """True bila ``rel`` dipilih persis atau berada di bawah dir yang dipilih."""
    if rel in selected_set:
        return True
    return any(rel.startswith(sel + "/") for sel in selected_set)


def _unique_extract_target(base: Path) -> Path:
    """Path folder hasil ekstrak yang dijamin belum ada (``base`` atau ``base (n)``).

    Ekstrak selektif TIDAK pernah menimpa data yang sudah ada di tujuan — subset yang
    diekstrak selalu mendarat di folder barunya sendiri (mencegah kehilangan file yang
    tak ikut dipilih bila folder bernama sama sudah ada).
    """
    if not base.exists():
        return base
    for i in range(1, 1000):
        cand = base.with_name(f"{base.name} ({i})")
        if not cand.exists():
            return cand
    raise FileExistsError("Couldn't find a free name for the extracted folder.")


def list_vault_contents(
    locked_path: str,
    password: str,
    *,
    keyfile_path: str | None = None,
    progress_cb=None,
    is_cancelled: Callable[[], bool] | None = None,
) -> tuple[VaultStatus, str | None, list[VaultEntry] | None]:
    """Daftar isi vault TANPA menulis apa pun ke disk (browse).

    Stream-decrypt seluruh record (O(vault) CPU, **nol disk**) lalu mengumpulkan header
    TAR → daftar ``VaultEntry`` (rel_path relatif root, size, is_dir, mtime). Karena
    payload TAR berselang-seling dengan data di dalam region terenkripsi dan tak punya
    manifest, ini harus mendekripsi hampir seluruh stream — tapi data member dibuang,
    tak ada plaintext yang jatuh ke disk. Tak butuh folder tujuan & tak menyentuh cache
    resume overwrite.

    Return:
      * ``(SUCCESS, root_name, entries)``
      * ``(WRONG_PASSWORD, None, None)``
      * ``(CANCELLED, msg, None)``
      * ``(ERROR, msg, None)`` — bukan vault / versi beda / rusak.
    """
    target_path = Path(locked_path)
    try:
        total_size = target_path.stat().st_size

        keyfile_material: bytes | None = None
        if keyfile_path:
            try:
                keyfile_material = _load_keyfile_material(keyfile_path)
            except ValueError as exc:
                return VaultStatus.ERROR, str(exc), None

        with target_path.open("rb") as fk:
            try:
                _read_and_check_prelude(fk, total_size)
                hdr, aesgcm, header_context, nama_folder = _open_and_unlock(
                    fk, password, keyfile_material
                )
            except _VaultOpenError as exc:
                return exc.status, exc.message, None

            compressed = bool(hdr["flags"] & FLAG_COMPRESSED)
            entries: list[VaultEntry] = []
            try:
                with _open_payload_tar_stream(
                    fk,
                    aesgcm,
                    header_context,
                    hdr["chunk_size"],
                    total_size,
                    compressed,
                    progress_cb=progress_cb,
                    is_cancelled=is_cancelled,
                ) as tar:
                    for member in tar:
                        if is_cancelled and is_cancelled():
                            return VaultStatus.CANCELLED, "Browse cancelled.", None
                        rel = _rel_to_root(member.name, nama_folder)
                        if rel == "":
                            continue  # entri root itu sendiri
                        if member.isdir():
                            entries.append(VaultEntry(rel, 0, True, member.mtime))
                        elif member.isreg():
                            entries.append(VaultEntry(rel, member.size, False, member.mtime))
                        # symlink/device/hardlink dilewati (tak akan diekstrak juga).
            except InterruptedError:
                return VaultStatus.CANCELLED, "Browse cancelled.", None
            except (InvalidTag, tarfile.TarError, ValueError, zstandard.ZstdError):
                return VaultStatus.ERROR, CORRUPT_VAULT_MESSAGE, None

        safe_cb(progress_cb, 1.0)
        return VaultStatus.SUCCESS, nama_folder, entries

    except Exception:
        logger.exception("Gagal membaca daftar isi vault.")
        return VaultStatus.ERROR, GENERIC_FAILURE_MESSAGE, None


def extract_selected(
    locked_path: str,
    password: str,
    selected,
    dest_dir: str,
    *,
    keyfile_path: str | None = None,
    expected_bytes: int | None = None,
    progress_cb=None,
    is_cancelled: Callable[[], bool] | None = None,
) -> tuple[VaultStatus, str | None]:
    """Ekstrak HANYA item terpilih dari vault ke ``dest_dir`` (stream-decrypt).

    ``selected`` = iterable rel_path (file/dir, relatif root, pemisah ``/``) pilihan
    user. Member yang cocok (persis atau di bawah dir terpilih) diekstrak ke folder
    **staging** di dalam ``dest_dir``, lalu subtree root dipindahkan ke folder final
    unik (``<root>`` atau ``<root> (n)``) **hanya setelah stream selesai sukses** →
    tujuan final tak pernah berisi hasil parsial & tak pernah menimpa data lama
    (cancel/korup/error → staging dibersihkan). Reuse proteksi TarSlip
    ``_is_safe_tar_member``; symlink/device dilewati. Peak disk ≈ ukuran subset
    terpilih, bukan 2×.

    Catatan invariant: berbeda dari ``buka_brankas`` yang memverifikasi SELURUH arsip
    sebelum menaruh apa pun, ekstrak selektif menulis saat mengalir. Relaksasi ini
    ditutup dengan staging-lalu-move: setiap record tetap diverifikasi tag-nya sebelum
    byte-nya ditulis, dan tujuan final hanya menerima subtree yang sudah lengkap.
    """
    target_path = Path(locked_path)
    dest = Path(dest_dir)
    selected_set = {s.replace("\\", "/").strip("/") for s in selected if s not in (None, "")}
    if not selected_set:
        return VaultStatus.ERROR, "No items were selected to extract."

    staging: Path | None = None
    try:
        total_size = target_path.stat().st_size

        if not dest.is_dir():
            return VaultStatus.ERROR, "The destination folder doesn't exist."

        # Sapu staging ekstrak yatim (app crash / force-kill saat ekstrak selektif)
        # yang umurnya melewati batas — pola sama dengan sweep ._dec_* di buka_brankas.
        for old_staging in dest.glob(f"{EXTRACT_STAGING_PREFIX}*"):
            if old_staging.is_dir():
                try:
                    if time.time() - old_staging.stat().st_mtime > OLD_TEMP_MAX_AGE_SECONDS:
                        shutil.rmtree(old_staging, ignore_errors=True)
                except Exception:
                    logger.debug("Gagal bersihkan staging ekstrak lama (diabaikan)")

        # Pra-cek disk (best-effort): butuh ruang ≈ ukuran subset terpilih + overhead.
        if expected_bytes:
            free = shutil.disk_usage(dest).free
            required = expected_bytes + DISK_OVERHEAD_BYTES
            if free < required:
                req_mb = required / (1024 * 1024)
                free_mb = free / (1024 * 1024)
                return (
                    VaultStatus.ERROR,
                    f"Not enough storage space.\nDisk free: {free_mb:.1f} MB. "
                    f"At least {req_mb:.1f} MB is required.",
                )

        keyfile_material: bytes | None = None
        if keyfile_path:
            try:
                keyfile_material = _load_keyfile_material(keyfile_path)
            except ValueError as exc:
                return VaultStatus.ERROR, str(exc)

        with target_path.open("rb") as fk:
            try:
                _read_and_check_prelude(fk, total_size)
                hdr, aesgcm, header_context, nama_folder = _open_and_unlock(
                    fk, password, keyfile_material
                )
            except _VaultOpenError as exc:
                return exc.status, exc.message

            compressed = bool(hdr["flags"] & FLAG_COMPRESSED)
            staging = dest / f"{EXTRACT_STAGING_PREFIX}{uuid.uuid4().hex[:8]}"
            staging.mkdir(parents=True, exist_ok=False)
            staging_resolved = staging.resolve()
            extracted_any = False

            try:
                with _open_payload_tar_stream(
                    fk,
                    aesgcm,
                    header_context,
                    hdr["chunk_size"],
                    total_size,
                    compressed,
                    progress_cb=progress_cb,
                    is_cancelled=is_cancelled,
                ) as tar:
                    for member in tar:
                        if is_cancelled and is_cancelled():
                            raise InterruptedError("Operation cancelled by the user.")
                        rel = _rel_to_root(member.name, nama_folder)
                        if rel == "" or not _rel_selected(rel, selected_set):
                            continue

                        if not _is_safe_tar_member(member.name, staging):
                            raise Exception("Security anomaly: path traversal (TarSlip) detected.")
                        member_path = (staging_resolved / member.name).resolve()

                        if member.isdir():
                            member_path.mkdir(parents=True, exist_ok=True)
                            extracted_any = True
                        elif member.isreg():
                            member_path.parent.mkdir(parents=True, exist_ok=True)
                            with (
                                tar.extractfile(member) as source,
                                open(member_path, "wb") as tgt,
                            ):
                                while True:
                                    if is_cancelled and is_cancelled():
                                        raise InterruptedError("Operation cancelled by the user.")
                                    chunk = source.read(CHUNK_SIZE)
                                    if not chunk:
                                        break
                                    tgt.write(chunk)
                            with contextlib.suppress(Exception):
                                os.chmod(member_path, member.mode)
                                os.utime(member_path, (member.mtime, member.mtime))
                            extracted_any = True
                        else:
                            logger.warning(f"Melewati member tidak standar: {member.name}")
            except InterruptedError:
                _cleanup_temp_decrypt_dir(staging)
                staging = None
                return VaultStatus.CANCELLED, "Extraction cancelled. No files were placed."
            except (InvalidTag, tarfile.TarError, ValueError, zstandard.ZstdError):
                _cleanup_temp_decrypt_dir(staging)
                staging = None
                return VaultStatus.ERROR, CORRUPT_VAULT_MESSAGE

        if not extracted_any:
            _cleanup_temp_decrypt_dir(staging)
            staging = None
            return VaultStatus.ERROR, "None of the selected items were found in the vault."

        src_root = staging / nama_folder
        if not src_root.exists():
            # Semestinya tak terjadi (semua member berawalan root); jaga agar tak
            # meninggalkan staging & laporkan sebagai kegagalan tak terduga.
            _cleanup_temp_decrypt_dir(staging)
            staging = None
            return VaultStatus.ERROR, GENERIC_FAILURE_MESSAGE

        final_dst = _unique_extract_target(dest / nama_folder)
        # staging berada DI DALAM dest → rename dalam volume yang sama (atomik).
        os.replace(src_root, final_dst)
        _cleanup_temp_decrypt_dir(staging)
        staging = None

        safe_cb(progress_cb, 1.0)
        return VaultStatus.SUCCESS, final_dst.name

    except Exception:
        logger.exception("Gagal mengekstrak item terpilih dari vault.")
        if staging is not None:
            _cleanup_temp_decrypt_dir(staging)
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
