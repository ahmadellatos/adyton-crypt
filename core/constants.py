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
VERSION = b"\x01"

# Header layout
HEADER_SIZE = 4 + 1 + 16 + 12      # MAGIC(4) + VERSION(1) + SALT(16) + NONCE(12)
TAG_SIZE = 16
OVERHEAD = HEADER_SIZE + TAG_SIZE

# ============================================================================
# KRIPTO & PERFORMA
# ============================================================================

CHUNK_SIZE = 16 * 1024 * 1024      # 16 MB — sweet spot performa vs memory

# ============================================================================
# PARAMETER APLIKASI (disesuaikan dari magic numbers sebelumnya)
# ============================================================================

DISK_OVERHEAD_BYTES = 50 * 1024 * 1024          # Buffer ruang disk saat kunci/buka
OLD_TEMP_MAX_AGE_SECONDS = 300                  # 5 menit — umur maksimal temp decrypt dir
MAX_VIRTUAL_NAME_LENGTH = 512                   # Batas aman untuk nama folder virtual
FIRST_DECRYPT_CHUNK_SIZE = 1024                 # Ukuran chunk pertama untuk parsing nama

# Progress thresholds (bisa dipakai untuk future improvement)
PROGRESS_NAME_PARSE_THRESHOLD = 0.05
PROGRESS_DECRYPT_THRESHOLD = 0.90
PROGRESS_EXTRACT_START = 0.92
PROGRESS_EXTRACT_END = 0.99
