"""
core/crypto.py
Primitif kriptografi: key derivation dan helper enkripsi/dekripsi AES-256-GCM.
"""

from __future__ import annotations

import base64
import hashlib
import secrets

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from loguru import logger

from .constants import (
    ARGON2ID_ITERATIONS,
    ARGON2ID_LANES,
    ARGON2ID_MAX_ITERATIONS,
    ARGON2ID_MAX_LANES,
    ARGON2ID_MAX_MEMORY_COST_KIB,
    ARGON2ID_MEMORY_COST_KIB,
    KDF_ID_ARGON2ID,
    KEYFILE_GENERATED_SIZE,
    MASTER_KEY_SIZE,
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


# ── Keyfile (faktor kedua / 2FA) ────────────────────────────────────────────────

# Domain separation untuk HKDF agar material keyfile tak bertabrakan penggunaan lain.
_KEYFILE_HKDF_INFO = b"adyton-crypt/keyfile-2fa/v1"


def generate_keyfile_bytes() -> bytes:
    """Buat isi keyfile acak entropi tinggi untuk disimpan user (mis. di USB)."""
    return secrets.token_bytes(KEYFILE_GENERATED_SIZE)


def derive_keyfile_material(keyfile_bytes: bytes) -> bytes:
    """Material 32-byte stabil dari isi keyfile (independen dari vault mana pun).

    SHA-256 atas byte mentah file: keyfile yang sama selalu menghasilkan material
    yang sama, sehingga satu keyfile bisa melindungi banyak vault. Pengikatan ke
    vault tertentu dilakukan oleh AAD wrap (file_id), bukan oleh material ini.
    """
    return hashlib.sha256(keyfile_bytes).digest()


def combine_kek_with_keyfile(base_kek: bytes, keyfile_material: bytes) -> bytes:
    """Campur material keyfile ke KEK turunan-password sehingga KEDUANYA wajib.

    HKDF-SHA256 atas keluaran Argon2id (``base_kek``) dengan material keyfile sebagai
    salt. Tanpa keyfile yang persis sama, KEK yang benar tak bisa direkonstruksi —
    jadi password saja (atau keyfile saja) tidak cukup membuka slot. Argon2id tetap
    menanggung beban brute-force pada faktor password yang berentropi rendah.
    """
    return HKDF(
        algorithm=hashes.SHA256(),
        length=MASTER_KEY_SIZE,
        salt=keyfile_material,
        info=_KEYFILE_HKDF_INFO,
    ).derive(base_kek)


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
    """Dispatch key derivation berdasarkan kdf_id dari keyslot vault.

    Saat ini hanya Argon2id; ``kdf_id`` tetap divalidasi agar header dari versi
    masa depan dengan KDF lain ditolak alih-alih disalahartikan.
    """
    params = params or {}

    if kdf_id == KDF_ID_ARGON2ID:
        return derive_key_argon2id(
            password,
            salt,
            iterations=params.get("iterations", ARGON2ID_ITERATIONS),
            lanes=params.get("lanes", ARGON2ID_LANES),
            memory_cost=params.get("memory_cost", ARGON2ID_MEMORY_COST_KIB),
        )

    raise ValueError("This vault KDF isn't supported by this app version.")


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
            logger.opt(exception=True).debug("Progress callback gagal (diabaikan)")
