"""
core/crypto.py
Primitif kriptografi: key derivation dan helper enkripsi/dekripsi AES-256-GCM.
"""

from __future__ import annotations

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.hazmat.backends import default_backend
from loguru import logger

from .constants import (
    ARGON2ID_ITERATIONS,
    ARGON2ID_LANES,
    ARGON2ID_MEMORY_COST_KIB,
    CHUNK_SIZE,
    KDF_ID_ARGON2ID,
    KDF_ID_PBKDF2_SHA256,
    PBKDF2_ITERATIONS,
)


def _password_bytes(password: str) -> bytes:
    return password.encode("utf-8")


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
        raise ValueError("Parameter Argon2id tidak valid.")

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

    raise ValueError("KDF vault tidak didukung oleh versi aplikasi ini.")


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
