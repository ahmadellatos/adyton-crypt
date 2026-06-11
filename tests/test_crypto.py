"""
tests/test_crypto.py
Unit test untuk core/crypto.py — primitif kriptografi.

Jalankan:
    pytest tests/test_crypto.py -v
"""

import os

import pytest

from core.constants import CHUNK_SIZE
from core.crypto import derive_key, make_decryptor, make_encryptor, safe_cb

# ── derive_key ────────────────────────────────────────────────────────────────


class TestDeriveKey:
    def test_output_length(self):
        """Kunci yang dihasilkan harus tepat 32 bytes (256-bit)."""
        key = derive_key("password123", os.urandom(16))
        assert len(key) == 32

    def test_deterministic(self):
        """Password + salt yang sama harus selalu hasilkan kunci yang sama."""
        salt = os.urandom(16)
        key1 = derive_key("sama", salt)
        key2 = derive_key("sama", salt)
        assert key1 == key2

    def test_different_salt_different_key(self):
        """Salt berbeda harus hasilkan kunci berbeda meskipun password sama."""
        pw = "password"
        key1 = derive_key(pw, os.urandom(16))
        key2 = derive_key(pw, os.urandom(16))
        assert key1 != key2

    def test_different_password_different_key(self):
        """Password berbeda harus hasilkan kunci berbeda meskipun salt sama."""
        salt = os.urandom(16)
        key1 = derive_key("password_a", salt)
        key2 = derive_key("password_b", salt)
        assert key1 != key2

    def test_returns_bytes(self):
        """Output harus berupa bytes, bukan string atau tipe lain."""
        key = derive_key("test", os.urandom(16))
        assert isinstance(key, bytes)

    def test_empty_password(self):
        """Password kosong tetap harus menghasilkan kunci (bukan crash)."""
        key = derive_key("", os.urandom(16))
        assert len(key) == 32

    def test_unicode_password(self):
        """Password unicode (emoji, kanji, dll) harus ditangani tanpa error."""
        key = derive_key("p@$$w0rd🔐日本語", os.urandom(16))
        assert len(key) == 32

    def test_long_password(self):
        """Password sangat panjang tidak boleh crash."""
        key = derive_key("a" * 1000, os.urandom(16))
        assert len(key) == 32


# ── make_encryptor / make_decryptor ───────────────────────────────────────────


class TestEncryptorDecryptor:
    def test_encrypt_decrypt_roundtrip(self):
        """Data yang dienkripsi harus bisa didekripsi kembali ke data asli."""
        key = os.urandom(32)
        nonce = os.urandom(12)
        data = b"Data rahasia yang sangat penting!"

        enc = make_encryptor(key, nonce)
        ciphertext = enc.update(data) + enc.finalize()
        tag = enc.tag

        dec = make_decryptor(key, nonce, tag)
        plaintext = dec.update(ciphertext) + dec.finalize()

        assert plaintext == data

    def test_wrong_key_fails(self):
        """Kunci yang salah harus gagal saat finalize (InvalidTag)."""
        from cryptography.exceptions import InvalidTag

        key_benar = os.urandom(32)
        key_salah = os.urandom(32)
        nonce = os.urandom(12)
        data = b"data sensitif"

        enc = make_encryptor(key_benar, nonce)
        ciphertext = enc.update(data) + enc.finalize()
        tag = enc.tag

        dec = make_decryptor(key_salah, nonce, tag)
        dec.update(ciphertext)
        with pytest.raises(InvalidTag):
            dec.finalize()

    def test_wrong_nonce_fails(self):
        """Nonce yang salah harus menghasilkan data yang berbeda / gagal verifikasi."""
        from cryptography.exceptions import InvalidTag

        key = os.urandom(32)
        nonce_benar = os.urandom(12)
        nonce_salah = os.urandom(12)
        data = b"data sensitif"

        enc = make_encryptor(key, nonce_benar)
        ciphertext = enc.update(data) + enc.finalize()
        tag = enc.tag

        dec = make_decryptor(key, nonce_salah, tag)
        dec.update(ciphertext)
        with pytest.raises(InvalidTag):
            dec.finalize()

    def test_tampered_ciphertext_fails(self):
        """Ciphertext yang dimodifikasi harus gagal verifikasi GCM."""
        from cryptography.exceptions import InvalidTag

        key = os.urandom(32)
        nonce = os.urandom(12)
        data = b"data asli yang panjang untuk testing"

        enc = make_encryptor(key, nonce)
        ciphertext = bytearray(enc.update(data) + enc.finalize())
        tag = enc.tag

        # Modifikasi 1 byte di tengah ciphertext
        ciphertext[len(ciphertext) // 2] ^= 0xFF

        dec = make_decryptor(key, nonce, tag)
        dec.update(bytes(ciphertext))
        with pytest.raises(InvalidTag):
            dec.finalize()

    def test_empty_data(self):
        """Data kosong tetap harus bisa diproses tanpa crash."""
        key = os.urandom(32)
        nonce = os.urandom(12)

        enc = make_encryptor(key, nonce)
        ciphertext = enc.update(b"") + enc.finalize()
        tag = enc.tag

        dec = make_decryptor(key, nonce, tag)
        plaintext = dec.update(ciphertext) + dec.finalize()

        assert plaintext == b""

    def test_large_data_chunked(self):
        """Data besar yang diproses dalam beberapa chunk harus tetap konsisten."""
        key = os.urandom(32)
        nonce = os.urandom(12)
        data = os.urandom(CHUNK_SIZE * 3 + 500)  # 3 chunk + sisa tanggung

        enc = make_encryptor(key, nonce)
        ciphertext = b""
        for i in range(0, len(data), CHUNK_SIZE):
            ciphertext += enc.update(data[i : i + CHUNK_SIZE])
        ciphertext += enc.finalize()
        tag = enc.tag

        dec = make_decryptor(key, nonce, tag)
        plaintext = b""
        for i in range(0, len(ciphertext), CHUNK_SIZE):
            plaintext += dec.update(ciphertext[i : i + CHUNK_SIZE])
        plaintext += dec.finalize()

        assert plaintext == data


# ── safe_cb ───────────────────────────────────────────────────────────────────


class TestSafeCb:
    def test_callback_dipanggil(self):
        """Callback harus dipanggil dengan nilai yang diberikan."""
        hasil = []
        safe_cb(lambda v: hasil.append(v), 0.5)
        assert hasil == [0.5]

    def test_none_tidak_crash(self):
        """Callback None tidak boleh crash."""
        safe_cb(None, 0.5)  # Tidak boleh raise exception

    def test_exception_dalam_callback_tidak_crash(self):
        """Exception di dalam callback tidak boleh crash program utama."""

        def cb_rusak(_):
            raise RuntimeError("callback error")

        safe_cb(cb_rusak, 0.5)  # Tidak boleh raise exception

    def test_nilai_diklem_0_sampai_1(self):
        """Nilai di luar [0, 1] harus diklem ke range valid."""
        hasil = []
        safe_cb(lambda v: hasil.append(v), -0.5)
        safe_cb(lambda v: hasil.append(v), 1.5)
        assert hasil[0] == 0.0
        assert hasil[1] == 1.0

    def test_batas_0_dan_1(self):
        """Nilai tepat 0.0 dan 1.0 harus lolos tanpa perubahan."""
        hasil = []
        safe_cb(lambda v: hasil.append(v), 0.0)
        safe_cb(lambda v: hasil.append(v), 1.0)
        assert hasil == [0.0, 1.0]


# ── CHUNK_SIZE ────────────────────────────────────────────────────────────────


class TestConstants:
    def test_chunk_size_minimal(self):
        """CHUNK_SIZE harus minimal 1MB untuk performa."""
        assert CHUNK_SIZE >= 1 * 1024 * 1024

    def test_chunk_size_tidak_terlalu_besar(self):
        """CHUNK_SIZE tidak boleh melebihi 64MB untuk menjaga memory usage."""
        assert CHUNK_SIZE <= 64 * 1024 * 1024
