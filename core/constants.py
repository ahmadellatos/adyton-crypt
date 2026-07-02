"""
core/constants.py
Konstanta bersama untuk protokol Adyton Crypt dan parameter kriptografi.
Tujuan: Sentralisasi magic numbers agar mudah dikelola dan diaudit.
"""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple

# ============================================================================
# PROTOKOL FILE FORMAT
# ============================================================================

MAGIC_BYTES = b"ADTN"

# Adyton Crypt punya SATU format vault: envelope / keyslot. Master Key acak
# mengenkripsi record (chunked AEAD), lalu dibungkus (wrapped) per-credential di
# keyslot. Ini memungkinkan ganti password dan recovery key tanpa enkripsi ulang
# seluruh data. Byte versi tetap dipertahankan agar format bisa berevolusi dan
# file dari versi mendatang/korup bisa ditolak dengan rapi.
VERSION = b"\x01"

SALT_SIZE = 16
NONCE_SIZE = 12  # AES-GCM 96-bit nonce (juga dipakai core/text_vault.py)
TAG_SIZE = 16
FILE_ID_SIZE = 16

CHUNK_RECORD_HEADER_SIZE = 1 + 8 + 4  # TYPE(1) + INDEX(8) + PLAINTEXT_LEN(4)
CHUNK_RECORD_OVERHEAD = CHUNK_RECORD_HEADER_SIZE + TAG_SIZE

# Chunk record types untuk mesin record (metadata/data/final).
RECORD_TYPE_METADATA = 0
RECORD_TYPE_DATA = 1
RECORD_TYPE_FINAL = 2

# ============================================================================
# PROTOKOL ENVELOPE / KEYSLOT
# ============================================================================
#
# Header:
#   MAGIC(4) + VERSION(1) + FILE_ID(16) + CHUNK_SIZE(4) + FLAGS(4)
#   [jika FLAGS & FLAG_HINT]  HINT_LEN(2) + HINT(HINT_LEN)
#   SLOT_COUNT(1)
#   SLOT_COUNT × keyslot:
#       SLOT_TYPE(1) + KDF_ID(1) + KDF_PARAMS_LEN(2) + KDF_PARAMS(N)
#       + SALT(16) + WRAP_NONCE(12) + WRAPPED_MASTER_KEY(48)
#
# AAD record  = MAGIC+VERSION+FILE_ID+CHUNK_SIZE+FLAGS  (TANPA keyslot, agar
#               ganti password cukup menulis ulang region keyslot — record tetap
#               valid karena key record = Master Key acak yang tidak berubah).
# AAD wrap    = MAGIC+VERSION+FILE_ID+HINT_BYTES+slot_meta  (mengikat wrapped MK
#               ke identitas vault + hint plaintext + parameter slot; cegah
#               slot-swap, tamper hint, & tamper parameter. HINT_BYTES kosong untuk
#               vault tanpa hint → AAD identik dengan format sebelum hint diikat).

MASTER_KEY_SIZE = 32
WRAP_NONCE_SIZE = 12
WRAPPED_KEY_SIZE = MASTER_KEY_SIZE + TAG_SIZE  # 48
MAX_KEYSLOTS = 8

# Tipe keyslot (menentukan normalisasi credential saat derive KEK).
SLOT_TYPE_PASSWORD = 0
SLOT_TYPE_RECOVERY_CODE = 1  # kode acak app-generated; di-normalisasi sebelum KDF
SLOT_TYPE_RECOVERY_PASSPHRASE = 2  # frasa pilihan user; dipakai apa adanya
SLOT_TYPE_PASSWORD_KEYFILE = 3  # 2FA: KEK = gabung(Argon2id(password), keyfile)
VALID_SLOT_TYPES = (
    SLOT_TYPE_PASSWORD,
    SLOT_TYPE_RECOVERY_CODE,
    SLOT_TYPE_RECOVERY_PASSPHRASE,
    SLOT_TYPE_PASSWORD_KEYFILE,
)
RECOVERY_SLOT_TYPES = (SLOT_TYPE_RECOVERY_CODE, SLOT_TYPE_RECOVERY_PASSPHRASE)
# Slot yang menyimpan faktor "password" vault (boleh dilindungi keyfile / tidak).
PASSWORD_SLOT_TYPES = (SLOT_TYPE_PASSWORD, SLOT_TYPE_PASSWORD_KEYFILE)

# ── Keyfile (faktor "sesuatu yang kamu punya") ──────────────────────────────────
# Keyfile dipakai sebagai faktor kedua: isinya di-hash jadi material 32-byte yang
# dicampur ke KEK slot password (lihat core/crypto.combine_kek_with_keyfile). Tanpa
# keyfile yang persis sama, KEK tak bisa direkonstruksi → vault 2FA tak terbuka.
# Keyfile TIDAK terikat ke vault tertentu (file_id mengikat di AAD wrap), jadi satu
# keyfile boleh dipakai untuk banyak vault.
KEYFILE_MIN_SIZE = 1  # 0 byte ditolak (tak ada rahasia)
KEYFILE_MAX_SIZE = 64 * 1024 * 1024  # batas baca agar tak meng-hash file raksasa
KEYFILE_GENERATED_SIZE = 128  # byte acak saat app membuatkan keyfile (1024-bit)

# Flags header.
FLAG_NONE = 0
FLAG_HINT = 1 << 0
# Payload (stream tar) dikompres dengan zstd SEBELUM dienkripsi. Flag ini ikut di
# AAD record (lihat _record_context), jadi pilihan kompresi terautentikasi: tak bisa
# diubah diam-diam. Kompresi terjadi di dalam region terenkripsi → tidak membocorkan
# rasio/isi ke header cleartext. Hanya data record yang dikompres; record metadata
# (record 0, berisi nama folder) tetap apa adanya.
FLAG_COMPRESSED = 1 << 1
SUPPORTED_FLAGS = FLAG_HINT | FLAG_COMPRESSED

# Level zstd untuk kompresi opsional. Level 3 (default zstd) = sweet spot rasio vs
# kecepatan; aman untuk data besar yang jadi nilai jual app.
ZSTD_COMPRESSION_LEVEL = 3
# Saat membuka vault TERKOMPRESI, payload terdekompresi bisa jauh lebih besar dari
# ciphertext. Pemeriksaan ruang disk memakai asumsi rasio konservatif ini; bila rasio
# nyata lebih tinggi lagi, ekstraksi gagal dengan rollback aman (data lama tak disentuh).
COMPRESSED_DECRYPT_RATIO_GUESS = 4

# Saat MENGUNCI dengan kompresi, output yang ditulis ke disk ≈ ukuran TERKOMPRESI,
# bukan tar mentah. Karena rasio tak diketahui sebelum mengompres, pra-cek ruang disk
# mengasumsikan payload turun sebesar rasio ini (konservatif: hanya 2:1, sementara
# data yang layak dikompres biasanya jauh lebih baik). Kalau data ternyata kurang
# kompresibel, penulisan bisa kehabisan ruang DI TENGAH — itu aman (vault parsial
# dihapus + backup dipulihkan, sumber asli tak disentuh), jadi lebih baik agak
# optimistis di sini daripada menolak lock yang sebenarnya muat.
ZSTD_DISK_ESTIMATE_RATIO = 2

# Hint password disimpan TANPA enkripsi (harus terbaca sebelum unlock).
MAX_HINT_LENGTH = 256  # byte UTF-8

# MAGIC(4)+VERSION(1)+FILE_ID(16)+CHUNK_SIZE(4)+FLAGS(4)
CORE_HEADER_SIZE = 4 + 1 + FILE_ID_SIZE + 4 + 4
# MAX_HEADER_SIZE didefinisikan di bawah, setelah ARGON2ID_PARAMS_SIZE tersedia
# (dipakai untuk estimasi kebutuhan disk saat membuat vault).

# ============================================================================
# KRIPTO & PERFORMA
# ============================================================================

CHUNK_SIZE = 16 * 1024 * 1024  # 16 MB — sweet spot performa vs memory

# KDF identifier disimpan per-keyslot di header (extensible untuk KDF masa depan).
KDF_ID_ARGON2ID = 2

# Default Argon2id parameters untuk vault baru. memory_cost dalam KiB.
# 64 MiB menjaga UX interaktif tetap wajar sambil menambah memory hardness.
ARGON2ID_ITERATIONS = 3
ARGON2ID_LANES = 4
ARGON2ID_MEMORY_COST_KIB = 64 * 1024
ARGON2ID_PARAMS_SIZE = 12  # iterations(4) + lanes(4) + memory_cost_kib(4)

# Bound atas ukuran header untuk estimasi kebutuhan disk (hint maksimal + slot
# penuh). Jauh lebih kecil dari DISK_OVERHEAD_BYTES, jadi sengaja konservatif.
_SLOT_FIXED_SIZE = 1 + 1 + 2 + ARGON2ID_PARAMS_SIZE + SALT_SIZE + WRAP_NONCE_SIZE + WRAPPED_KEY_SIZE
MAX_HEADER_SIZE = CORE_HEADER_SIZE + (2 + MAX_HINT_LENGTH) + 1 + MAX_KEYSLOTS * _SLOT_FIXED_SIZE

# Upper bounds for Argon2id parameters read from a vault header. A malicious or
# corrupted .adtn could otherwise request gigabytes/terabytes of memory and OOM
# the app when opening it. These ceilings stay far above the defaults above, so
# any realistic future increase keeps working while absurd values are rejected.
ARGON2ID_MAX_ITERATIONS = 64
ARGON2ID_MAX_LANES = 64
ARGON2ID_MAX_MEMORY_COST_KIB = 2 * 1024 * 1024  # 2 GiB

# Preset level KDF yang bisa dipilih user di Settings. "moderate" = default vault
# (identik dengan ARGON2ID_* di atas). Semua nilai di bawah ceiling ARGON2ID_MAX_*.
KDF_LEVEL_INTERACTIVE = "interactive"
KDF_LEVEL_MODERATE = "moderate"
KDF_LEVEL_PARANOID = "paranoid"
DEFAULT_KDF_LEVEL = KDF_LEVEL_MODERATE

KDF_LEVELS = {
    KDF_LEVEL_INTERACTIVE: {"iterations": 2, "lanes": ARGON2ID_LANES, "memory_cost": 32 * 1024},
    KDF_LEVEL_MODERATE: {
        "iterations": ARGON2ID_ITERATIONS,
        "lanes": ARGON2ID_LANES,
        "memory_cost": ARGON2ID_MEMORY_COST_KIB,
    },
    KDF_LEVEL_PARANOID: {"iterations": 4, "lanes": ARGON2ID_LANES, "memory_cost": 256 * 1024},
}


def kdf_params_for_level(level: str) -> dict[str, int]:
    """Parameter Argon2id untuk sebuah level KDF (fallback ke default bila asing)."""
    return dict(KDF_LEVELS.get(level, KDF_LEVELS[DEFAULT_KDF_LEVEL]))


# ============================================================================
# PARAMETER APLIKASI (disesuaikan dari magic numbers sebelumnya)
# ============================================================================

DISK_OVERHEAD_BYTES = 50 * 1024 * 1024  # Buffer ruang disk saat kunci/buka
OLD_TEMP_MAX_AGE_SECONDS = 300  # 5 menit — umur maksimal temp decrypt dir
MAX_VIRTUAL_NAME_LENGTH = 512  # Batas aman untuk nama folder virtual

# ============================================================================
# BROWSE / EKSTRAK SELEKTIF (read-only; tanpa perubahan format)
# ============================================================================

# Prefix folder staging saat ekstrak selektif. Hasil ekstraksi ditulis ke folder
# ini DI DALAM tujuan pilihan user, lalu dipindahkan ke tempat final hanya setelah
# stream selesai sukses → tujuan final tak pernah berisi hasil parsial.
EXTRACT_STAGING_PREFIX = "._ext_"


class VaultEntry(NamedTuple):
    """Satu entri isi vault untuk browse (nama relatif terhadap root, ukuran, tipe).

    ``rel_path`` sudah dilepas prefix nama folder root (mis. ``docs/a.txt``), memakai
    pemisah ``/``. Untuk direktori ``size`` = 0. Dikumpulkan dari header TAR saat
    stream-decrypt tanpa menulis apa pun ke disk.
    """

    rel_path: str
    size: int
    is_dir: bool
    mtime: float


# ============================================================================
# STATUS & PESAN HASIL OPERASI
# ============================================================================


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

# Pesan panjang/multi-baris dijadikan konstanta agar lapisan UI (ui/core_messages.py)
# bisa memetakannya ke terjemahan dengan aman — tanpa menyalin ulang teks persis
# (rawan salah ketik pada em-dash / tanda kutip).
SAVE_INSIDE_SOURCE_MESSAGE = (
    "The vault's save location can't be the same as, or inside, the "
    "file/folder being locked. Choose another location so the vault isn't "
    "deleted along with it or pulled into the archive."
)
KEYFILE_INSIDE_SOURCE_MESSAGE = (
    "The keyfile can't be the same as, or inside, the file or folder "
    'being locked. It would be archived into the vault and — with "delete '
    'original" on — wiped along with it, locking you out. Store the keyfile '
    "somewhere else."
)
VERIFY_DISK_FAIL_MESSAGE = (
    "The vault couldn't be verified on the physical disk. The original file was not deleted. "
    "Try checking your disk space and the condition of your storage hardware."
)
KEYFILE_CREATED_MESSAGE = "Keyfile created. Keep it safe — you'll need it to open the vault."
# Vault final SUDAH tersimpan & terverifikasi, tapi sebagian sumber gagal dihapus
# (mis. file sedang dibuka aplikasi lain / dikunci antivirus — umum di Windows).
# Status tetap SUCCESS: vault aman dan tidak boleh ikut dihapus hanya karena fase
# hapus-asli gagal; UI menampilkan pesan ini sebagai peringatan.
DELETE_ORIGINAL_FAILED_MESSAGE = (
    "The vault was created and verified, but some of the original files couldn't be "
    "deleted — they may be open in another app or write-protected. Your data is safely "
    "locked in the vault; delete the originals manually."
)
