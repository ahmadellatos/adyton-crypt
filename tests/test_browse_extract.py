"""Tests untuk browse isi vault + ekstrak selektif (streaming, read-only).

Cakupan: list isi (file/folder/size/root-strip), invariant nol-disk, vault
terkompresi & 2FA, wrong-password, korupsi; ekstrak subset (hanya terpilih),
ekstrak dir, TarSlip aman, cancel & korup mid-stream → tujuan bersih, tabrakan
nama tak menimpa, pra-cek disk.
"""

import os

from core.crypto import generate_recovery_code
from core.vault import (
    CORRUPT_VAULT_MESSAGE,
    VaultStatus,
    extract_selected,
    generate_keyfile,
    kunci_brankas,
    list_vault_contents,
)

PASSWORD = "P@ssw0rd!Kuat123"


def _make_source(tmp_path, name="MyStuff"):
    source = tmp_path / name
    (source / "docs" / "sub").mkdir(parents=True)
    (source / "docs" / "a.txt").write_text("alpha" * 200, encoding="utf-8")
    (source / "docs" / "sub" / "b.bin").write_bytes(os.urandom(6000))
    (source / "readme.md").write_text("top\n" * 100, encoding="utf-8")
    (source / "empty").mkdir()
    return source


def _lock(tmp_path, **kwargs):
    source = _make_source(tmp_path)
    vault_path = tmp_path / "vault.adtn"
    status, message = kunci_brankas([str(source)], str(vault_path), PASSWORD, **kwargs)
    assert status == VaultStatus.SUCCESS, message
    return source, vault_path


def _flip_byte(path, offset):
    with open(path, "r+b") as f:
        f.seek(offset)
        b = f.read(1)
        f.seek(offset)
        f.write(bytes([b[0] ^ 0xFF]))


def _rels(entries):
    return {e.rel_path for e in entries}


# ── list_vault_contents ─────────────────────────────────────────────────────────


def test_list_returns_entries_with_root_stripped(tmp_path):
    _, vault = _lock(tmp_path)
    status, root, entries = list_vault_contents(str(vault), PASSWORD)
    assert status == VaultStatus.SUCCESS
    assert root == "MyStuff"
    rels = _rels(entries)
    assert "readme.md" in rels
    assert "docs/a.txt" in rels
    assert "docs/sub/b.bin" in rels
    assert "empty" in rels
    # Tidak ada entri yang masih membawa prefix root.
    assert not any(r == "MyStuff" or r.startswith("MyStuff/") for r in rels)


def test_list_sizes_and_dir_flags(tmp_path):
    source, vault = _lock(tmp_path)
    _, _, entries = list_vault_contents(str(vault), PASSWORD)
    by_path = {e.rel_path: e for e in entries}
    assert by_path["readme.md"].is_dir is False
    # Ukuran = ukuran byte nyata di disk (Windows menerjemahkan \n→\r\n saat tulis teks).
    assert by_path["readme.md"].size == (source / "readme.md").stat().st_size
    assert by_path["docs/sub/b.bin"].size == 6000
    assert by_path["docs"].is_dir is True
    assert by_path["docs"].size == 0
    assert by_path["empty"].is_dir is True


def test_list_writes_nothing_to_disk(tmp_path):
    _, vault = _lock(tmp_path)
    before = set(os.listdir(tmp_path))
    status, _, _ = list_vault_contents(str(vault), PASSWORD)
    after = set(os.listdir(tmp_path))
    assert status == VaultStatus.SUCCESS
    assert before == after  # nol disk: tak ada temp/output baru


def test_list_reports_progress(tmp_path):
    _, vault = _lock(tmp_path)
    seen = []
    status, _, _ = list_vault_contents(str(vault), PASSWORD, progress_cb=seen.append)
    assert status == VaultStatus.SUCCESS
    assert seen and seen[-1] == 1.0


def test_list_compressed_vault(tmp_path):
    _, vault = _lock(tmp_path, compress=True)
    status, root, entries = list_vault_contents(str(vault), PASSWORD)
    assert status == VaultStatus.SUCCESS
    assert "docs/sub/b.bin" in _rels(entries)


def test_list_wrong_password(tmp_path):
    _, vault = _lock(tmp_path)
    status, root, entries = list_vault_contents(str(vault), "salah-banget")
    assert status == VaultStatus.WRONG_PASSWORD
    assert entries is None


def test_list_with_recovery_code(tmp_path):
    code = generate_recovery_code()
    source = _make_source(tmp_path)
    vault = tmp_path / "vault.adtn"
    st, msg = kunci_brankas(
        [str(source)], str(vault), PASSWORD, recovery_secret=code, recovery_type="code"
    )
    assert st == VaultStatus.SUCCESS, msg
    assert list_vault_contents(str(vault), code)[0] == VaultStatus.SUCCESS


def test_list_2fa_keyfile(tmp_path):
    keyfile = tmp_path / "key.bin"
    assert generate_keyfile(str(keyfile))[0] == VaultStatus.SUCCESS
    source = _make_source(tmp_path)
    vault = tmp_path / "vault.adtn"
    st, msg = kunci_brankas([str(source)], str(vault), PASSWORD, keyfile_path=str(keyfile))
    assert st == VaultStatus.SUCCESS, msg
    # Tanpa keyfile → gagal (WRONG_PASSWORD); dengan keyfile → sukses.
    assert list_vault_contents(str(vault), PASSWORD)[0] == VaultStatus.WRONG_PASSWORD
    status, _, entries = list_vault_contents(str(vault), PASSWORD, keyfile_path=str(keyfile))
    assert status == VaultStatus.SUCCESS
    assert "readme.md" in _rels(entries)


def test_list_non_vault_file(tmp_path):
    junk = tmp_path / "notavault.adtn"
    junk.write_bytes(b"this is not a vault at all")
    status, msg, entries = list_vault_contents(str(junk), PASSWORD)
    assert status == VaultStatus.ERROR
    assert entries is None


def test_list_corrupt_data_record(tmp_path):
    _, vault = _lock(tmp_path)
    # Balik byte jauh di dalam file (region record data) → korup, credential benar.
    _flip_byte(vault, vault.stat().st_size - 40)
    status, msg, entries = list_vault_contents(str(vault), PASSWORD)
    assert status == VaultStatus.ERROR
    assert msg == CORRUPT_VAULT_MESSAGE
    assert entries is None


# ── extract_selected ─────────────────────────────────────────────────────────────


def _extract(vault, selected, dest, **kwargs):
    return extract_selected(str(vault), PASSWORD, selected, str(dest), **kwargs)


def _placed_files(base):
    return {p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()}


def test_extract_only_selected(tmp_path):
    _, vault = _lock(tmp_path)
    dest = tmp_path / "out"
    dest.mkdir()
    status, name = _extract(vault, ["readme.md"], dest)
    assert status == VaultStatus.SUCCESS
    placed = dest / name
    assert _placed_files(placed) == {"readme.md"}
    assert not (placed / "docs").exists()


def test_extract_selected_dir_includes_children(tmp_path):
    _, vault = _lock(tmp_path)
    dest = tmp_path / "out"
    dest.mkdir()
    status, name = _extract(vault, ["docs/sub"], dest)
    assert status == VaultStatus.SUCCESS
    placed = dest / name
    assert _placed_files(placed) == {"docs/sub/b.bin"}
    assert not (placed / "docs" / "a.txt").exists()


def test_extract_preserves_structure_and_content(tmp_path):
    source, vault = _lock(tmp_path)
    dest = tmp_path / "out"
    dest.mkdir()
    status, name = _extract(vault, ["docs/a.txt"], dest)
    assert status == VaultStatus.SUCCESS
    got = (dest / name / "docs" / "a.txt").read_text(encoding="utf-8")
    assert got == (source / "docs" / "a.txt").read_text(encoding="utf-8")


def test_extract_empty_selection_rejected(tmp_path):
    _, vault = _lock(tmp_path)
    dest = tmp_path / "out"
    dest.mkdir()
    status, _ = _extract(vault, [], dest)
    assert status == VaultStatus.ERROR


def test_extract_does_not_overwrite_existing(tmp_path):
    _, vault = _lock(tmp_path)
    dest = tmp_path / "out"
    dest.mkdir()
    status1, name1 = _extract(vault, ["readme.md"], dest)
    status2, name2 = _extract(vault, ["readme.md"], dest)
    assert status1 == status2 == VaultStatus.SUCCESS
    assert name1 != name2  # folder kedua diberi nama unik, tak menimpa
    assert (dest / name1 / "readme.md").exists()
    assert (dest / name2 / "readme.md").exists()


def test_extract_compressed(tmp_path):
    _, vault = _lock(tmp_path, compress=True)
    dest = tmp_path / "out"
    dest.mkdir()
    status, name = _extract(vault, ["docs/sub/b.bin"], dest)
    assert status == VaultStatus.SUCCESS
    assert (dest / name / "docs" / "sub" / "b.bin").stat().st_size == 6000


def test_extract_cancel_leaves_destination_clean(tmp_path):
    _, vault = _lock(tmp_path)
    dest = tmp_path / "out"
    dest.mkdir()
    status, _ = _extract(vault, ["docs", "readme.md"], dest, is_cancelled=lambda: True)
    assert status == VaultStatus.CANCELLED
    # Tak ada folder hasil maupun staging yang tertinggal.
    assert list(dest.iterdir()) == []


def test_extract_corrupt_leaves_destination_clean(tmp_path):
    _, vault = _lock(tmp_path)
    _flip_byte(vault, vault.stat().st_size - 40)
    dest = tmp_path / "out"
    dest.mkdir()
    status, msg = _extract(vault, ["docs", "readme.md"], dest)
    assert status == VaultStatus.ERROR
    assert list(dest.iterdir()) == []  # staging dibersihkan, tak ada parsial


def test_extract_wrong_password(tmp_path):
    _, vault = _lock(tmp_path)
    dest = tmp_path / "out"
    dest.mkdir()
    status, _ = extract_selected(str(vault), "salah", ["readme.md"], str(dest))
    assert status == VaultStatus.WRONG_PASSWORD
    assert list(dest.iterdir()) == []


def test_extract_disk_precheck(tmp_path):
    _, vault = _lock(tmp_path)
    dest = tmp_path / "out"
    dest.mkdir()
    # expected_bytes absurd → pra-cek disk menolak sebelum menulis apa pun.
    status, msg = _extract(vault, ["readme.md"], dest, expected_bytes=10**18)
    assert status == VaultStatus.ERROR
    assert "storage space" in msg.lower()
    assert list(dest.iterdir()) == []
