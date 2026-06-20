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

# v1 = AES-GCM monolitik lama. v2 = chunked AEAD streaming (key langsung dari
# password). v3 = envelope: Master Key acak mengenkripsi record, lalu dibungkus
# (wrapped) per-credential di keyslot. v3 memungkinkan ganti password dan
# recovery key tanpa enkripsi ulang seluruh data.
# KDF tidak diikat ke nomor versi format; v2/v3 memakai field kdf_id eksplisit
# agar PBKDF2 legacy dan Argon2id bisa dibedakan.
VERSION_V1 = b"\x01"
VERSION_V2 = b"\x02"
VERSION_V3 = b"\x03"
VERSION = VERSION_V3

SALT_SIZE = 16
NONCE_SIZE_V1 = 12
TAG_SIZE = 16
FILE_ID_SIZE = 16

# Header layout v1: MAGIC(4) + VERSION(1) + SALT(16) + NONCE(12)
HEADER_SIZE_V1 = 4 + 1 + SALT_SIZE + NONCE_SIZE_V1
OVERHEAD_V1 = HEADER_SIZE_V1 + TAG_SIZE

# Header layout v2 legacy:
# MAGIC(4) + VERSION(1) + SALT(16) + FILE_ID(16) + CHUNK_SIZE(4) + FLAGS(4)
#
# Header layout v2 extended (new):
# legacy header + KDF_ID(1) + KDF_PARAMS_LEN(2) + KDF_PARAMS(N)
#
# HEADER_SIZE_V2 intentionally remains the legacy/base size for backward
# compatibility with existing imports/tests. Use V2_KDF_SECTION_* for extended
# headers.
HEADER_SIZE_V2 = 4 + 1 + SALT_SIZE + FILE_ID_SIZE + 4 + 4
V2_KDF_SECTION_HEADER_SIZE = 1 + 2  # KDF_ID(1) + PARAMS_LEN(2)
CHUNK_RECORD_HEADER_SIZE = 1 + 8 + 4  # TYPE(1) + INDEX(8) + PLAINTEXT_LEN(4)
CHUNK_RECORD_OVERHEAD = CHUNK_RECORD_HEADER_SIZE + TAG_SIZE
V2_FLAG_NONE = 0
V2_FLAG_KDF_PARAMS = 1 << 0
V2_SUPPORTED_FLAGS = V2_FLAG_KDF_PARAMS

# Backward-compatible aliases for older tests/helpers that import HEADER_SIZE/OVERHEAD.
HEADER_SIZE = HEADER_SIZE_V1
OVERHEAD = OVERHEAD_V1

# Chunk record types for v2/v3 (record layout sama persis; hanya sumber key beda).
RECORD_TYPE_METADATA = 0
RECORD_TYPE_DATA = 1
RECORD_TYPE_FINAL = 2

# ============================================================================
# PROTOKOL v3 — ENVELOPE / KEYSLOT
# ============================================================================
#
# Header v3:
#   MAGIC(4) + VERSION(1=0x03) + FILE_ID(16) + CHUNK_SIZE(4) + FLAGS(4)
#   [jika FLAGS & V3_FLAG_HINT]  HINT_LEN(2) + HINT(HINT_LEN)
#   SLOT_COUNT(1)
#   SLOT_COUNT × keyslot:
#       SLOT_TYPE(1) + KDF_ID(1) + KDF_PARAMS_LEN(2) + KDF_PARAMS(N)
#       + SALT(16) + WRAP_NONCE(12) + WRAPPED_MASTER_KEY(48)
#
# AAD record  = MAGIC+VERSION_V3+FILE_ID+CHUNK_SIZE+FLAGS  (TANPA keyslot, agar
#               ganti password cukup menulis ulang region keyslot — record tetap
#               valid karena key record = Master Key acak yang tidak berubah).
# AAD wrap    = MAGIC+VERSION_V3+FILE_ID+slot_meta  (mengikat wrapped MK ke
#               identitas vault + parameter slot; cegah slot-swap & tamper).

MASTER_KEY_SIZE = 32
WRAP_NONCE_SIZE = 12
WRAPPED_KEY_SIZE = MASTER_KEY_SIZE + TAG_SIZE  # 48
MAX_KEYSLOTS = 8

# Tipe keyslot (menentukan normalisasi credential saat derive KEK).
SLOT_TYPE_PASSWORD = 0
SLOT_TYPE_RECOVERY_CODE = 1  # kode acak app-generated; di-normalisasi sebelum KDF
SLOT_TYPE_RECOVERY_PASSPHRASE = 2  # frasa pilihan user; dipakai apa adanya
VALID_SLOT_TYPES = (
    SLOT_TYPE_PASSWORD,
    SLOT_TYPE_RECOVERY_CODE,
    SLOT_TYPE_RECOVERY_PASSPHRASE,
)
RECOVERY_SLOT_TYPES = (SLOT_TYPE_RECOVERY_CODE, SLOT_TYPE_RECOVERY_PASSPHRASE)

# Flags v3.
V3_FLAG_NONE = 0
V3_FLAG_HINT = 1 << 0
V3_SUPPORTED_FLAGS = V3_FLAG_HINT

# Hint password disimpan TANPA enkripsi (harus terbaca sebelum unlock).
MAX_HINT_LENGTH = 256  # byte UTF-8

# MAGIC(4)+VERSION(1)+FILE_ID(16)+CHUNK_SIZE(4)+FLAGS(4)
V3_CORE_HEADER_SIZE = 4 + 1 + FILE_ID_SIZE + 4 + 4
# V3_MAX_HEADER_SIZE didefinisikan di bawah, setelah ARGON2ID_PARAMS_SIZE
# tersedia (dipakai untuk estimasi kebutuhan disk saat membuat vault).

# ============================================================================
# KRIPTO & PERFORMA
# ============================================================================

CHUNK_SIZE = 16 * 1024 * 1024  # 16 MB — sweet spot performa vs memory

# KDF identifiers stored in v2 extended headers.
KDF_ID_PBKDF2_SHA256 = 1
KDF_ID_ARGON2ID = 2

# Legacy PBKDF2 parameter. Kept for opening v1 and v2-legacy vaults.
PBKDF2_ITERATIONS = 600_000

# Default Argon2id parameters for newly-created v2 vaults. memory_cost is KiB.
# 64 MiB keeps interactive UX reasonable while adding memory hardness.
ARGON2ID_ITERATIONS = 3
ARGON2ID_LANES = 4
ARGON2ID_MEMORY_COST_KIB = 64 * 1024
ARGON2ID_PARAMS_SIZE = 12  # iterations(4) + lanes(4) + memory_cost_kib(4)

# Bound atas ukuran header v3 untuk estimasi kebutuhan disk (hint maksimal + slot
# penuh). Jauh lebih kecil dari DISK_OVERHEAD_BYTES, jadi sengaja konservatif.
_V3_SLOT_FIXED_SIZE = 1 + 1 + 2 + ARGON2ID_PARAMS_SIZE + SALT_SIZE + WRAP_NONCE_SIZE + WRAPPED_KEY_SIZE
V3_MAX_HEADER_SIZE = V3_CORE_HEADER_SIZE + (2 + MAX_HINT_LENGTH) + 1 + MAX_KEYSLOTS * _V3_SLOT_FIXED_SIZE

# Upper bounds for Argon2id parameters read from a vault header. A malicious or
# corrupted .adtn could otherwise request gigabytes/terabytes of memory and OOM
# the app when opening it. These ceilings stay far above the defaults above, so
# any realistic future increase keeps working while absurd values are rejected.
ARGON2ID_MAX_ITERATIONS = 64
ARGON2ID_MAX_LANES = 64
ARGON2ID_MAX_MEMORY_COST_KIB = 2 * 1024 * 1024  # 2 GiB

# ============================================================================
# PARAMETER APLIKASI (disesuaikan dari magic numbers sebelumnya)
# ============================================================================

DISK_OVERHEAD_BYTES = 50 * 1024 * 1024  # Buffer ruang disk saat kunci/buka
OLD_TEMP_MAX_AGE_SECONDS = 300  # 5 menit — umur maksimal temp decrypt dir
MAX_VIRTUAL_NAME_LENGTH = 512  # Batas aman untuk nama folder virtual
FIRST_DECRYPT_CHUNK_SIZE = 1024  # Ukuran chunk pertama untuk parsing nama v1

# Progress thresholds (bisa dipakai untuk future improvement)
PROGRESS_NAME_PARSE_THRESHOLD = 0.05
PROGRESS_DECRYPT_THRESHOLD = 0.90
PROGRESS_EXTRACT_START = 0.92
PROGRESS_EXTRACT_END = 0.99
