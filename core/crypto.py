"""
core/crypto.py
Primitif kriptografi: key derivation dan helper enkripsi/dekripsi AES-256-GCM.
"""

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from loguru import logger

from .constants import CHUNK_SIZE


def derive_key(password: str, salt: bytes) -> bytes:
    """Turunkan kunci 256-bit dari password menggunakan PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,
        backend=default_backend(),
    )
    return kdf.derive(password.encode())


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
