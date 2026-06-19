"""Tests for core/text_vault.py — the ADTN_TEXT:1: text encryption path.

Pure (no Qt). Argon2id derivation is somewhat costly, so the happy-path token is
computed once at module scope and reused across the tamper/wrong-password cases.
"""

import base64

import pytest
from cryptography.exceptions import InvalidTag

from core.text_vault import (
    TEXT_VAULT_PREFIX,
    decrypt_text,
    encrypt_text,
    is_encrypted_text,
)

PASSWORD = "Correct Horse Battery Staple 42!"
PLAINTEXT = "Pesan rahasia — café, 日本語,\nbaris kedua dengan angka 12345."


@pytest.fixture(scope="module")
def token() -> str:
    return encrypt_text(PLAINTEXT, PASSWORD)


def _decode_payload(token: str) -> bytes:
    b64 = token[len(TEXT_VAULT_PREFIX) :]
    padding = (4 - len(b64) % 4) % 4
    return base64.urlsafe_b64decode(b64 + "=" * padding)


def _reencode(payload: bytes) -> str:
    return TEXT_VAULT_PREFIX + base64.urlsafe_b64encode(payload).decode("ascii")


# ── Happy path ──────────────────────────────────────────────────────────────


def test_roundtrip_recovers_plaintext(token):
    assert decrypt_text(token, PASSWORD) == PLAINTEXT


def test_token_is_prefixed_and_detected(token):
    assert token.startswith(TEXT_VAULT_PREFIX)
    assert is_encrypted_text(token)


def test_encryption_is_nondeterministic():
    a = encrypt_text(PLAINTEXT, PASSWORD)
    b = encrypt_text(PLAINTEXT, PASSWORD)
    assert a != b  # random salt + nonce per call
    assert decrypt_text(a, PASSWORD) == decrypt_text(b, PASSWORD) == PLAINTEXT


def test_surrounding_whitespace_tolerated(token):
    assert decrypt_text(f"\n  {token}  \n", PASSWORD) == PLAINTEXT


def test_missing_base64_padding_tolerated(token):
    assert decrypt_text(token.rstrip("="), PASSWORD) == PLAINTEXT


# ── Authentication / integrity ──────────────────────────────────────────────


def test_wrong_password_raises_invalid_tag(token):
    with pytest.raises(InvalidTag):
        decrypt_text(token, PASSWORD + "x")


def test_tampered_tag_raises_invalid_tag(token):
    payload = bytearray(_decode_payload(token))
    payload[-1] ^= 0x01  # flip one bit of the GCM tag
    with pytest.raises(InvalidTag):
        decrypt_text(_reencode(bytes(payload)), PASSWORD)


def test_tampered_ciphertext_raises_invalid_tag(token):
    payload = bytearray(_decode_payload(token))
    # First ciphertext byte sits right after salt(16) + nonce(12).
    payload[28] ^= 0x01
    with pytest.raises(InvalidTag):
        decrypt_text(_reencode(bytes(payload)), PASSWORD)


# ── Input validation ────────────────────────────────────────────────────────


def test_encrypt_rejects_empty_plaintext():
    with pytest.raises(ValueError):
        encrypt_text("", PASSWORD)


def test_encrypt_rejects_empty_password():
    with pytest.raises(ValueError):
        encrypt_text(PLAINTEXT, "")


def test_decrypt_rejects_empty_password(token):
    with pytest.raises(ValueError):
        decrypt_text(token, "")


def test_decrypt_rejects_missing_prefix():
    with pytest.raises(ValueError):
        decrypt_text("just some plain text", PASSWORD)


def test_decrypt_rejects_invalid_base64():
    with pytest.raises(ValueError):
        decrypt_text(TEXT_VAULT_PREFIX + "@@@@ not base64 @@@@", PASSWORD)


def test_decrypt_rejects_short_payload():
    short = _reencode(b"abc")  # well below salt+nonce+tag
    with pytest.raises(ValueError):
        decrypt_text(short, PASSWORD)


# ── is_encrypted_text ───────────────────────────────────────────────────────


def test_is_encrypted_text_detection():
    assert is_encrypted_text(f"  {TEXT_VAULT_PREFIX}abc  ") is True
    assert is_encrypted_text("hello world") is False
    assert is_encrypted_text("") is False
