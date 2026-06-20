"""
core/crypto.py
Primitif kriptografi: key derivation dan helper enkripsi/dekripsi AES-256-GCM.
"""

from __future__ import annotations

import base64
import secrets

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from loguru import logger

from .constants import (
    ARGON2ID_ITERATIONS,
    ARGON2ID_LANES,
    ARGON2ID_MAX_ITERATIONS,
    ARGON2ID_MAX_LANES,
    ARGON2ID_MAX_MEMORY_COST_KIB,
    ARGON2ID_MEMORY_COST_KIB,
    KDF_ID_ARGON2ID,
    KDF_ID_PBKDF2_SHA256,
    PBKDF2_ITERATIONS,
)


def _password_bytes(password: str) -> bytes:
    return password.encode("utf-8")


# ── Recovery code ───────────────────────────────────────────────────────────────

# Alfabet base32 RFC 4648 (huruf besar + 2-7). Dipakai untuk normalisasi kode
# recovery agar input user yang berbeda kapitalisasi/separator tetap cocok.
_B32_ALPHABET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")
RECOVERY_CODE_BYTES = 20  # 160-bit entropi — sangat jauh dari bisa ditebak
_RECOVERY_GROUP = 4


def generate_recovery_code() -> str:
    """Buat recovery code acak entropi tinggi, dikelompokkan agar mudah dibaca.

    Bentuk tampilan: ``ABCD-EFGH-IJKL-...`` (base32, 8 grup × 4 karakter).
    Normalisasi sebelum dipakai sebagai credential dilakukan di
    :func:`normalize_recovery_code`.
    """
    raw = secrets.token_bytes(RECOVERY_CODE_BYTES)
    b32 = base64.b32encode(raw).decode("ascii").rstrip("=")
    groups = [b32[i : i + _RECOVERY_GROUP] for i in range(0, len(b32), _RECOVERY_GROUP)]
    return "-".join(groups)


def normalize_recovery_code(code: str) -> str:
    """Normalisasi recovery code: huruf besar, buang karakter non-base32.

    Membuat input toleran terhadap spasi, tanda hubung, dan kapitalisasi yang
    berbeda dari saat ditampilkan, tanpa mengubah entropi efektif.
    """
    return "".join(ch for ch in code.upper() if ch in _B32_ALPHABET)


def derive_key_pbkdf2(
    password: str,
    salt: bytes,
    iterations: int = PBKDF2_ITERATIONS,
) -> bytes:
    """Turunkan kunci 256-bit memakai PBKDF2-HMAC-SHA256.

    Dipertahankan untuk backward compatibility v1 dan v2 legacy.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
        backend=default_backend(),
    )
    return kdf.derive(_password_bytes(password))


def derive_key_argon2id(
    password: str,
    salt: bytes,
    iterations: int = ARGON2ID_ITERATIONS,
    lanes: int = ARGON2ID_LANES,
    memory_cost: int = ARGON2ID_MEMORY_COST_KIB,
) -> bytes:
    """Turunkan kunci 256-bit memakai Argon2id.

    ``memory_cost`` memakai satuan KiB sesuai API ``cryptography``.
    """
    if iterations <= 0 or lanes <= 0 or memory_cost <= 0:
        raise ValueError("Invalid Argon2id parameter.")
    if (
        iterations > ARGON2ID_MAX_ITERATIONS
        or lanes > ARGON2ID_MAX_LANES
        or memory_cost > ARGON2ID_MAX_MEMORY_COST_KIB
    ):
        # Defense in depth: never hand absurd cost factors to the KDF, even if a
        # caller bypassed header decoding. Prevents OOM/hang on crafted input.
        raise ValueError("Argon2id parameters exceed the safe maximum.")

    kdf = Argon2id(
        salt=salt,
        length=32,
        iterations=iterations,
        lanes=lanes,
        memory_cost=memory_cost,
    )
    return kdf.derive(_password_bytes(password))


def derive_key_for_kdf(
    password: str,
    salt: bytes,
    kdf_id: int,
    params: dict[str, int] | None = None,
) -> bytes:
    """Dispatch key derivation berdasarkan kdf_id dari header vault."""
    params = params or {}

    if kdf_id == KDF_ID_PBKDF2_SHA256:
        return derive_key_pbkdf2(
            password,
            salt,
            iterations=params.get("iterations", PBKDF2_ITERATIONS),
        )

    if kdf_id == KDF_ID_ARGON2ID:
        return derive_key_argon2id(
            password,
            salt,
            iterations=params.get("iterations", ARGON2ID_ITERATIONS),
            lanes=params.get("lanes", ARGON2ID_LANES),
            memory_cost=params.get("memory_cost", ARGON2ID_MEMORY_COST_KIB),
        )

    raise ValueError("This vault KDF isn't supported by this app version.")


def derive_key(password: str, salt: bytes) -> bytes:
    """Backward-compatible alias: PBKDF2-HMAC-SHA256 legacy."""
    return derive_key_pbkdf2(password, salt)


def make_encryptor(key: bytes, nonce: bytes):
    """Buat AES-256-GCM encryptor."""
    return Cipher(
        algorithms.AES(key),
        modes.GCM(nonce),
        backend=default_backend(),
    ).encryptor()


def make_decryptor(key: bytes, nonce: bytes, tag: bytes):
    """Buat AES-256-GCM decryptor dengan tag verifikasi."""
    return Cipher(
        algorithms.AES(key),
        modes.GCM(nonce, tag),
        backend=default_backend(),
    ).decryptor()


def safe_cb(progress_cb, val: float):
    """Panggil progress callback dengan aman — tidak crash jika None atau exception."""
    if progress_cb:
        try:
            progress_cb(max(0.0, min(1.0, val)))
        except Exception:
            logger.debug("Progress callback gagal (diabaikan)", exc_info=True)
