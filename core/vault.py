"""
core/vault.py
Logika utama: kunci folder/file (enkripsi) dan buka brankas (dekripsi).
Dioptimasi dengan Single-Pass I/O Streaming, pathlib, dan Cancellation Support.
Telah ditambal dari celah keamanan Path Traversal (TarSlip) dan rapuhnya deteksi password.

Modul tipis (orkestrator publik). Implementasi dipecah ke:
  - vault_stream.py   — format envelope/keyslot & streaming crypto chunked AEAD
  - vault_extract.py  — ekstraksi, secure wipe, pending/resume-overwrite
  - vault_inspect.py  — inspeksi metadata read-only (tanpa credential)
  - vault_manage.py   — manajemen credential (ganti password/recovery/keyfile)
Semua nama di bawah diimpor & diekspos ulang di sini agar API publik
(``from core.vault import ...``) tidak berubah.
"""

import os
import shutil
import tarfile
import time
from collections.abc import Callable
from pathlib import Path

import zstandard
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from loguru import logger

from .constants import (
    ARGON2ID_PARAMS_SIZE,
    CHUNK_RECORD_OVERHEAD,
    CHUNK_SIZE,
    CORE_HEADER_SIZE,
    CORRUPT_VAULT_MESSAGE,
    DELETE_ORIGINAL_FAILED_MESSAGE,
    FILE_ID_SIZE,
    FLAG_COMPRESSED,
    FLAG_HINT,
    FLAG_NONE,
    GENERIC_FAILURE_MESSAGE,
    KEYFILE_CREATED_MESSAGE,
    KEYFILE_INSIDE_SOURCE_MESSAGE,
    MAGIC_BYTES,
    MASTER_KEY_SIZE,
    MAX_HINT_LENGTH,
    MAX_VIRTUAL_NAME_LENGTH,
    OLD_TEMP_MAX_AGE_SECONDS,
    RECORD_TYPE_DATA,
    RECORD_TYPE_FINAL,
    RECORD_TYPE_METADATA,
    SALT_SIZE,
    SAVE_INSIDE_SOURCE_MESSAGE,
    SLOT_TYPE_PASSWORD,
    SLOT_TYPE_PASSWORD_KEYFILE,
    SLOT_TYPE_RECOVERY_CODE,
    SLOT_TYPE_RECOVERY_PASSPHRASE,
    TAG_SIZE,
    VERIFY_DISK_FAIL_MESSAGE,
    VERSION,
    WRAP_NONCE_SIZE,
    WRAPPED_KEY_SIZE,
    ZSTD_COMPRESSION_LEVEL,
    VaultStatus,
)
from .crypto import safe_cb
from .vault_extract import (
    _buka_brankas_from_open_file,
    _discard_pending,
    _hitung_kebutuhan_disk_buka,
    _hitung_kebutuhan_disk_kunci,
    _hitung_total_size,
    _hitung_total_wipe_size,
    _is_safe_tar_member,
    _make_unique_backup_path,
    _parse_virtual_folder_name,
    _pending_key,
    _sanitize_virtual_name,
    _target_conflicts_with_source,
    _try_resume_overwrite,
    _validate_virtual_folder_name,
    cancel_pending_overwrite,
    discard_all_pending_overwrites,
    extract_selected,
    hapus_permanen,
    list_vault_contents,
)
from .vault_inspect import (
    _quick_verify_vault,
    _read_header_from_path,
    read_vault_hint,
    vault_info,
)
from .vault_manage import (
    add_keyfile,
    add_recovery_key,
    change_password,
    remove_keyfile,
    remove_recovery_key,
)
from .vault_stream import (
    ChunkedAEADEncryptingStream,
    _build_header,
    _build_keyslot,
    _CompressProgressWriter,
    _encode_argon2id_params,
    _hint_bytes_from_header,
    _load_keyfile_material,
    _parse_header,
    _read_exact,
    _read_record_header,
    _record_aad,
    _record_context,
    _record_nonce,
    _recover_master_key,
    _write_record,
    generate_keyfile,
)

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
# 5. Setelah vault final ter-commit (fsync + backup lama dibuang), vault TIDAK
#    BOLEH dihapus oleh error handler — kegagalan menghapus sumber dilaporkan
#    sebagai SUCCESS + DELETE_ORIGINAL_FAILED_MESSAGE (peringatan), bukan ERROR.
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
            return (VaultStatus.ERROR, SAVE_INSIDE_SOURCE_MESSAGE)

    # Keyfile (2FA) tidak boleh berada di dalam / sama dengan sumber yang dikunci:
    # ia akan ikut diarsipkan ke dalam vault DAN — bila "hapus asli" aktif — ikut
    # terhapus/di-wipe bersama sumber, sehingga vault butuh keyfile yang sudah lenyap
    # → terkunci permanen (kecuali ada recovery key). Tolak lebih awal.
    if keyfile_path:
        keyfile_obj = Path(keyfile_path)
        for source in valid_paths:
            if _target_conflicts_with_source(keyfile_obj, Path(source)):
                return (VaultStatus.ERROR, KEYFILE_INSIDE_SOURCE_MESSAGE)

    if len(valid_paths) == 1:
        nama_virtual = _sanitize_virtual_name(Path(valid_paths[0]).name)
        target_dir = ""
    else:
        nama_virtual = _sanitize_virtual_name(target_path.stem or "Brankas_Rahasia")
        target_dir = nama_virtual

    backup_path: Path | None = None
    backup_dibuat = False
    # True setelah vault final ter-fsync ke disk & backup lama dibuang. Sejak titik
    # ini vault TIDAK BOLEH dihapus oleh error handler mana pun — kegagalan fase
    # berikutnya (hapus asli, stat) dilaporkan sebagai peringatan, bukan rollback.
    vault_committed = False

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
        vault_committed = True

        gagal_hapus = False
        if hapus_asli:
            safe_cb(progress_cb, 0.88)
            if not _quick_verify_vault(target_path):
                return (VaultStatus.ERROR, VERIFY_DISK_FAIL_MESSAGE)
            safe_cb(progress_cb, 0.90)  # Verification done

            # Kegagalan hapus per-path (file dipegang app lain / AV — umum di
            # Windows) TIDAK boleh menggagalkan operasi: vault sudah terverifikasi.
            # Path lain tetap dicoba dihapus, lalu user diberi peringatan.
            if secure_wipe:
                wipe_paths = [Path(p) for p in valid_paths]
                total_wipe = _hitung_total_wipe_size(wipe_paths, True)
                wiped_counter = [0]

                for p in wipe_paths:
                    try:
                        hapus_permanen(
                            p,
                            secure_wipe=True,
                            progress_cb=progress_cb,
                            wipe_start_pct=0.90,
                            wipe_end_pct=0.98,
                            total_wipe_bytes=total_wipe,
                            wiped_bytes=wiped_counter,
                        )
                    except Exception:
                        logger.exception(f"Gagal menghapus sumber setelah lock: {p}")
                        gagal_hapus = True
            else:
                for p in valid_paths:
                    try:
                        hapus_permanen(Path(p), secure_wipe=False)
                    except Exception:
                        logger.exception(f"Gagal menghapus sumber setelah lock: {p}")
                        gagal_hapus = True

            safe_cb(progress_cb, 0.99)  # Wipe + cleanup done

        if gagal_hapus:
            safe_cb(progress_cb, 1.0)
            return (VaultStatus.SUCCESS, DELETE_ORIGINAL_FAILED_MESSAGE)

        try:
            size_mb = target_path.stat().st_size / (1024 * 1024)
            done_msg = f"Vault locked successfully!\nSize: {size_mb:.1f} MB"
        except OSError:
            done_msg = "Vault locked successfully!"
        safe_cb(progress_cb, 1.0)
        return (VaultStatus.SUCCESS, done_msg)

    except InterruptedError:
        if vault_committed:
            # Tidak ada titik pembatalan pasca-commit; jaring pengaman saja —
            # vault yang sudah final tidak pernah dibongkar.
            return (VaultStatus.SUCCESS, "Vault locked successfully!")
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
        if vault_committed:
            # Vault final sudah tersimpan & (bila hapus_asli) terverifikasi — error
            # pasca-commit apa pun tidak boleh menghapusnya. Fase pasca-commit
            # praktis hanya penghapusan sumber, jadi laporkan sebagai itu.
            if hapus_asli:
                return (VaultStatus.SUCCESS, DELETE_ORIGINAL_FAILED_MESSAGE)
            return (VaultStatus.SUCCESS, "Vault locked successfully!")
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
# 4. Credential salah dilaporkan sebagai WRONG_PASSWORD (definitif di unwrap
#    keyslot). Kegagalan SETELAH Master Key terbukti benar berarti DATA rusak
#    dan dilaporkan ERROR + CORRUPT_VAULT_MESSAGE — konsisten dengan
#    verify_vault/browse/extract, agar user tidak menebak-nebak password
#    padahal filenya yang rusak.
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
