"""
core/constants.py
Konstanta bersama untuk protokol Adyton Crypt dan parameter kriptografi.
Tujuan: Sentralisasi magic numbers agar mudah dikelola dan diaudit.
"""

from __future__ import annotations

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
# AAD wrap    = MAGIC+VERSION+FILE_ID+slot_meta  (mengikat wrapped MK ke
#               identitas vault + parameter slot; cegah slot-swap & tamper).

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
SUPPORTED_FLAGS = FLAG_HINT

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
