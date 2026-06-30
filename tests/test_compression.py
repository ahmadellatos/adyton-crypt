"""Tests untuk kompresi opsional (zstd) sebelum enkripsi.

Cakupan: round-trip terkompresi, rasio < tanpa kompresi, flag header, kompat vault
tak terkompresi, interaksi dengan verify / recovery / keyfile / hint, jalur resume
overwrite, dan data inkompresibel/empty.
"""

import shutil

from core.constants import FLAG_COMPRESSED
from core.crypto import generate_recovery_code
from core.vault import (
    CORRUPT_VAULT_MESSAGE,
    VaultStatus,
    _read_header_from_path,
    buka_brankas,
    generate_keyfile,
    kunci_brankas,
    read_vault_hint,
    verify_vault,
)

PASSWORD = "P@ssw0rd!Kuat123"


def _make_source(tmp_path, name="rahasia", filler="A"):
    source = tmp_path / name
    nested = source / "nested"
    nested.mkdir(parents=True, exist_ok=True)
    # Sangat kompresibel agar perbedaan ukuran jelas.
    (source / "a.txt").write_text(filler * 200_000, encoding="utf-8")
    (nested / "b.txt").write_text("hello world " * 20_000, encoding="utf-8")
    return source


def _lock(tmp_path, vault_name="vault.adtn", **kwargs):
    source = _make_source(tmp_path)
    vault_path = tmp_path / vault_name
    status, message = kunci_brankas([str(source)], str(vault_path), PASSWORD, **kwargs)
    assert status == VaultStatus.SUCCESS, message
    return source, vault_path


def _restore_and_check(vault_path, tmp_path, secret=PASSWORD, force=False, **kwargs):
    status, name = buka_brankas(str(vault_path), secret, force=force, **kwargs)
    assert status == VaultStatus.SUCCESS, name
    restored = tmp_path / name
    assert (restored / "a.txt").read_text(encoding="utf-8") == "A" * 200_000
    assert (restored / "nested" / "b.txt").read_text(encoding="utf-8") == "hello world " * 20_000
    return restored


# ── Round-trip & rasio ─────────────────────────────────────────────────────────────


def test_compressed_roundtrip(tmp_path):
    source, vault_path = _lock(tmp_path, compress=True)
    shutil.rmtree(source)
    _restore_and_check(vault_path, tmp_path)


def test_compressed_is_smaller(tmp_path):
    _, plain = _lock(tmp_path, vault_name="plain.adtn", compress=False)
    _, comp = _lock(tmp_path, vault_name="comp.adtn", compress=True)
    assert comp.stat().st_size < plain.stat().st_size


def test_flag_set_only_when_compressed(tmp_path):
    _, comp = _lock(tmp_path, vault_name="c.adtn", compress=True)
    _, plain = _lock(tmp_path, vault_name="p.adtn", compress=False)
    assert _read_header_from_path(comp)["flags"] & FLAG_COMPRESSED
    assert not (_read_header_from_path(plain)["flags"] & FLAG_COMPRESSED)


def test_uncompressed_still_opens(tmp_path):
    """Regression: vault tanpa kompresi (default) tetap terbuka sama persis."""
    source, vault_path = _lock(tmp_path, compress=False)
    shutil.rmtree(source)
    _restore_and_check(vault_path, tmp_path)


# ── Data inkompresibel & empty ──────────────────────────────────────────────────────


def test_incompressible_data_roundtrips(tmp_path):
    import os

    source = tmp_path / "blob"
    source.mkdir()
    payload = os.urandom(300_000)
    (source / "rand.bin").write_bytes(payload)
    vault_path = tmp_path / "v.adtn"
    status, _ = kunci_brankas([str(source)], str(vault_path), PASSWORD, compress=True)
    assert status == VaultStatus.SUCCESS
    shutil.rmtree(source)
    status, name = buka_brankas(str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS
    assert (tmp_path / name / "rand.bin").read_bytes() == payload


def test_compressed_multi_record_roundtrip(tmp_path):
    """Regresi: compressed output > CHUNK_SIZE (16 MB) → zstd stream dipotong jadi
    >1 record AEAD. Pastikan batas record yang memotong frame zstd transparan."""
    import os

    source = tmp_path / "blob"
    source.mkdir()
    payload = os.urandom(20 * 1024 * 1024)  # ~inkompresibel → output > 16 MB → 2+ record
    (source / "big.bin").write_bytes(payload)
    vault_path = tmp_path / "v.adtn"
    status, _ = kunci_brankas([str(source)], str(vault_path), PASSWORD, compress=True)
    assert status == VaultStatus.SUCCESS
    assert vault_path.stat().st_size > 16 * 1024 * 1024  # benar-benar multi-record
    shutil.rmtree(source)
    status, name = buka_brankas(str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS
    assert (tmp_path / name / "big.bin").read_bytes() == payload


def test_compressed_lock_cancel_cleans_up(tmp_path):
    """Batal saat lock terkompresi → CANCELLED + tak meninggalkan vault parsial."""
    source = _make_source(tmp_path)
    vault_path = tmp_path / "v.adtn"
    status, _ = kunci_brankas(
        [str(source)], str(vault_path), PASSWORD, compress=True, is_cancelled=lambda: True
    )
    assert status == VaultStatus.CANCELLED
    assert not vault_path.exists()


# ── Pra-cek ruang disk untuk lock terkompresi ───────────────────────────────────────


def _compressible_source(tmp_path):
    source = tmp_path / "docs"
    source.mkdir()
    (source / "big.txt").write_text("A" * 4_000_000, encoding="utf-8")
    return source


def test_compressed_disk_estimate_is_lower(tmp_path):
    """Reservasi disk untuk lock terkompresi < tak-terkompresi (payload diasumsikan turun)."""
    from core.constants import DISK_OVERHEAD_BYTES
    from core.vault import _hitung_kebutuhan_disk_kunci

    paths = [str(_compressible_source(tmp_path))]
    plain = _hitung_kebutuhan_disk_kunci(paths, "docs", "", compress=False)
    comp = _hitung_kebutuhan_disk_kunci(paths, "docs", "", compress=True)
    assert comp < plain
    assert comp >= DISK_OVERHEAD_BYTES  # buffer tetap jadi lantai


def test_compressed_lock_proceeds_on_tight_disk(tmp_path, monkeypatch):
    """Lock terkompresi LOLOS pra-cek pada ruang yang MENOLAK lock tak-terkompresi."""
    import types

    import core.vault as vault
    from core.vault import _hitung_kebutuhan_disk_kunci

    paths = [str(_compressible_source(tmp_path))]
    req_plain = _hitung_kebutuhan_disk_kunci(paths, "docs", "", compress=False)
    req_comp = _hitung_kebutuhan_disk_kunci(paths, "docs", "", compress=True)
    assert req_comp < req_plain

    # Ruang bebas tepat DI BAWAH kebutuhan tak-terkompresi, tapi DI ATAS terkompresi.
    fake_free = req_plain - 1
    assert fake_free >= req_comp
    monkeypatch.setattr(
        vault.shutil,
        "disk_usage",
        lambda _p: types.SimpleNamespace(total=0, used=0, free=fake_free),
    )

    # Tanpa kompresi → ditolak di pra-cek.
    st, msg = vault.kunci_brankas(paths, str(tmp_path / "plain.adtn"), PASSWORD, compress=False)
    assert st == VaultStatus.ERROR
    assert "storage" in msg.lower()

    # Dengan kompresi → lolos pra-cek & sukses (penulisan nyata ke disk tmp yang lega).
    v2 = tmp_path / "comp.adtn"
    st, msg = vault.kunci_brankas(paths, str(v2), PASSWORD, compress=True)
    assert st == VaultStatus.SUCCESS, msg
    assert v2.exists()


def test_empty_folder_compressed_roundtrips(tmp_path):
    source = tmp_path / "kosong"
    source.mkdir()
    vault_path = tmp_path / "v.adtn"
    status, _ = kunci_brankas([str(source)], str(vault_path), PASSWORD, compress=True)
    assert status == VaultStatus.SUCCESS
    shutil.rmtree(source)
    status, name = buka_brankas(str(vault_path), PASSWORD)
    assert status == VaultStatus.SUCCESS
    assert (tmp_path / name).is_dir()


# ── Interaksi fitur ──────────────────────────────────────────────────────────────────


def test_compressed_verify_succeeds(tmp_path):
    _, vault_path = _lock(tmp_path, compress=True)
    assert verify_vault(str(vault_path), PASSWORD)[0] == VaultStatus.SUCCESS


def test_compressed_verify_detects_corruption(tmp_path):
    _, vault_path = _lock(tmp_path, compress=True)
    size = vault_path.stat().st_size
    with open(vault_path, "r+b") as f:
        f.seek(size - 1)
        b = f.read(1)
        f.seek(size - 1)
        f.write(bytes([b[0] ^ 0xFF]))
    status, message = verify_vault(str(vault_path), PASSWORD)
    assert status == VaultStatus.ERROR
    assert message == CORRUPT_VAULT_MESSAGE


def test_compressed_wrong_password(tmp_path):
    _, vault_path = _lock(tmp_path, compress=True)
    assert buka_brankas(str(vault_path), "salah-total")[0] == VaultStatus.WRONG_PASSWORD


def test_compressed_with_recovery_code(tmp_path):
    code = generate_recovery_code()
    source, vault_path = _lock(tmp_path, compress=True, recovery_secret=code, recovery_type="code")
    shutil.rmtree(source)
    _restore_and_check(vault_path, tmp_path, secret=code)


def test_compressed_with_keyfile_2fa(tmp_path):
    keyfile = tmp_path / "key.bin"
    assert generate_keyfile(str(keyfile))[0] == VaultStatus.SUCCESS
    source, vault_path = _lock(tmp_path, compress=True, keyfile_path=str(keyfile))
    shutil.rmtree(source)
    # Tanpa keyfile → ditolak; dengan keyfile → sukses.
    assert buka_brankas(str(vault_path), PASSWORD)[0] == VaultStatus.WRONG_PASSWORD
    _restore_and_check(vault_path, tmp_path, keyfile_path=str(keyfile))


def test_compressed_with_hint(tmp_path):
    _, vault_path = _lock(tmp_path, compress=True, hint="kota lahir")
    assert read_vault_hint(str(vault_path)) == "kota lahir"
    assert verify_vault(str(vault_path), PASSWORD)[0] == VaultStatus.SUCCESS


# ── Jalur resume overwrite (memakai _PendingExtract.compressed) ──────────────────────


def test_compressed_overwrite_resume(tmp_path):
    """Folder tujuan ada → OVERWRITE_NEEDED; force → resume dari tar terkompresi."""
    source, vault_path = _lock(tmp_path, compress=True)  # folder 'rahasia' masih ada

    status, name = buka_brankas(str(vault_path), PASSWORD)
    assert status == VaultStatus.OVERWRITE_NEEDED
    assert name == source.name

    # Konfirmasi "Replace": resume harus mendekompresi tar yang tertahan dengan benar.
    restored = _restore_and_check(vault_path, tmp_path, force=True)
    assert restored == source
