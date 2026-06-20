"""
core/text_vault.py
Enkripsi dan dekripsi teks langsung (bukan file) menggunakan AES-256-GCM + Argon2id.

Format output (string yang bisa di-copy/paste):
    ADTN_TEXT:1:<base64url(salt[16] + nonce[12] + ciphertext + tag[16])>

Desain sengaja dibuat sederhana — tidak pakai chunking karena teks jarang
melampaui beberapa KB. Satu AES-GCM call sudah cukup dan lebih mudah diaudit.
"""

from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from loguru import logger

from .constants import (
    NONCE_SIZE,
    SALT_SIZE,
    TAG_SIZE,
)
from .crypto import derive_key_argon2id, make_decryptor, make_encryptor

# ─── Konstanta format ────────────────────────────────────────────────────────

TEXT_VAULT_PREFIX = "ADTN_TEXT:1:"
_MIN_PAYLOAD_LEN = SALT_SIZE + NONCE_SIZE + TAG_SIZE  # tanpa ciphertext = teks kosong

# Parameter KDF DIBEKUKAN untuk format versi 1.
# JANGAN ganti nilai ini — format "ADTN_TEXT:1:" tidak menyimpan parameter KDF
# di payload, sehingga dekripsi bergantung pada nilai yang persis sama dengan
# saat enkripsi. Jika parameter perlu dinaikkan, buat versi format baru
# (ADTN_TEXT:2:) yang menyertakan parameter KDF di dalam payload.
# Saat ini disengaja sama dengan default constants.py, tapi sengaja tidak
# di-import langsung agar perubahan default tidak diam-diam merusak teks lama.
TEXT_V1_ARGON2ID_ITERATIONS = 3
TEXT_V1_ARGON2ID_LANES = 4
TEXT_V1_ARGON2ID_MEMORY_COST_KIB = 64 * 1024


# ─── Public API ──────────────────────────────────────────────────────────────


def encrypt_text(plaintext: str, password: str) -> str:
    """Enkripsi *plaintext* dengan *password*, kembalikan string ADTN_TEXT:1:...

    Menggunakan Argon2id untuk key derivation (64 MiB, 3 iterasi, 4 lane) dan
    AES-256-GCM untuk enkripsi. Salt dan nonce di-generate secara acak tiap panggilan.

    Args:
        plaintext: Teks UTF-8 yang ingin dienkripsi.
        password:  Password yang akan dipakai sebagai kunci.

    Returns:
        String ADTN_TEXT:1:<base64url> yang aman untuk di-copy/paste/share.

    Raises:
        ValueError: Jika plaintext atau password kosong.
    """
    if not plaintext:
        raise ValueError("Text cannot be empty.")
    if not password:
        raise ValueError("Password cannot be empty.")

    data = plaintext.encode("utf-8")
    salt = os.urandom(SALT_SIZE)
    nonce = os.urandom(NONCE_SIZE)

    key = derive_key_argon2id(
        password,
        salt,
        iterations=TEXT_V1_ARGON2ID_ITERATIONS,
        lanes=TEXT_V1_ARGON2ID_LANES,
        memory_cost=TEXT_V1_ARGON2ID_MEMORY_COST_KIB,
    )

    enc = make_encryptor(key, nonce)
    ciphertext = enc.update(data) + enc.finalize()
    tag = enc.tag

    payload = salt + nonce + ciphertext + tag
    encoded = base64.urlsafe_b64encode(payload).decode("ascii")
    logger.debug(f"encrypt_text: {len(data)} byte plaintext → {len(encoded)} char ciphertext")
    return TEXT_VAULT_PREFIX + encoded


def decrypt_text(encrypted: str, password: str) -> str:
    """Dekripsi string ADTN_TEXT:1:... kembali ke plaintext UTF-8.

    Args:
        encrypted: String hasil encrypt_text (boleh ada whitespace di tepi).
        password:  Password yang sama saat enkripsi.

    Returns:
        Teks asli sebagai string UTF-8.

    Raises:
        ValueError:  Format string tidak valid atau data terlalu pendek.
        InvalidTag:  Password salah atau data telah dimodifikasi/rusak.
    """
    if not password:
        raise ValueError("Password cannot be empty.")

    encrypted = encrypted.strip()

    if not encrypted.startswith(TEXT_VAULT_PREFIX):
        raise ValueError(
            "Not a valid Adyton Crypt Text format.\n"
            "Make sure the encrypted text starts with 'ADTN_TEXT:1:'."
        )

    b64_part = encrypted[len(TEXT_VAULT_PREFIX) :]
    try:
        # urlsafe_b64decode toleran terhadap padding yang kurang
        padding_needed = (4 - len(b64_part) % 4) % 4
        payload = base64.urlsafe_b64decode(b64_part + "=" * padding_needed)
    except Exception as exc:
        raise ValueError(f"Base64 data could not be decoded: {exc}") from exc

    if len(payload) < _MIN_PAYLOAD_LEN:
        raise ValueError("Data too short — possibly corrupted or truncated.")

    salt = payload[:SALT_SIZE]
    nonce = payload[SALT_SIZE : SALT_SIZE + NONCE_SIZE]
    tag = payload[-TAG_SIZE:]
    ciphertext = payload[SALT_SIZE + NONCE_SIZE : -TAG_SIZE]

    key = derive_key_argon2id(
        password,
        salt,
        iterations=TEXT_V1_ARGON2ID_ITERATIONS,
        lanes=TEXT_V1_ARGON2ID_LANES,
        memory_cost=TEXT_V1_ARGON2ID_MEMORY_COST_KIB,
    )

    dec = make_decryptor(key, nonce, tag)
    try:
        plaintext_bytes = dec.update(ciphertext) + dec.finalize()
    except InvalidTag as exc:
        raise InvalidTag("Wrong password or the data was modified.") from exc

    try:
        return plaintext_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Decrypted data is not valid UTF-8: {exc}") from exc


def is_encrypted_text(s: str) -> bool:
    """Return True jika string terlihat seperti output encrypt_text."""
    return s.strip().startswith(TEXT_VAULT_PREFIX)
