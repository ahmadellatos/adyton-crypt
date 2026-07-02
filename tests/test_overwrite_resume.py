"""Tests for the verified-archive resume cache used on overwrite confirmation.

When the destination folder already exists, the whole archive is still decrypted
and verified BEFORE the overwrite prompt (security invariant unchanged). The
verified temp tar is then reused when the user confirms "Replace", so a large
vault is decrypted only ONCE instead of twice.
"""

from core import vault as vault_mod
from core.vault import (
    VaultStatus,
    buka_brankas,
    cancel_pending_overwrite,
    kunci_brankas,
)

PASSWORD = "P@ssw0rd!Kuat123"


def _make_source(tmp_path):
    source = tmp_path / "rahasia"
    source.mkdir()
    (source / "a.txt").write_text("alpha", encoding="utf-8")
    return source


def test_overwrite_then_force_resumes_without_redecrypt(tmp_path, monkeypatch):
    source = _make_source(tmp_path)
    vault_path = tmp_path / "v.adtn"
    assert kunci_brankas([str(source)], str(vault_path), PASSWORD)[0] == VaultStatus.SUCCESS

    # Folder tujuan masih ada → prompt overwrite; tar terverifikasi ditahan.
    status, _ = buka_brankas(str(vault_path), PASSWORD)
    assert status == VaultStatus.OVERWRITE_NEEDED
    assert list(tmp_path.glob("._dec_*")), "tar sementara harus ditahan untuk resume"

    # Pada force-retry, dekripsi ulang TIDAK boleh terjadi: ekstraksi langsung dari
    # tar terverifikasi. Spy mendeteksi panggilan dekripsi penuh berulang.
    called = {"n": 0}
    real = vault_mod._buka_brankas_from_open_file

    def spy(*args, **kwargs):
        called["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(vault_mod, "_buka_brankas_from_open_file", spy)

    status, name = buka_brankas(str(vault_path), PASSWORD, force=True)
    assert status == VaultStatus.SUCCESS
    assert called["n"] == 0, "resume harus melewati dekripsi ulang"
    assert not list(tmp_path.glob("._dec_*")), "temp dibersihkan setelah resume"
    assert (tmp_path / name / "a.txt").read_text(encoding="utf-8") == "alpha"


def test_cancel_pending_overwrite_cleans_temp(tmp_path):
    source = _make_source(tmp_path)
    vault_path = tmp_path / "v.adtn"
    kunci_brankas([str(source)], str(vault_path), PASSWORD)

    status, _ = buka_brankas(str(vault_path), PASSWORD)
    assert status == VaultStatus.OVERWRITE_NEEDED
    assert list(tmp_path.glob("._dec_*"))

    # User menolak → tar terverifikasi dibuang, tak ada yang menggantung.
    cancel_pending_overwrite(str(vault_path))
    assert not list(tmp_path.glob("._dec_*"))


def test_force_open_without_pending_does_full_decrypt(tmp_path):
    """force=True tanpa konfirmasi sebelumnya (mis. dipanggil langsung) tetap
    bekerja lewat dekripsi penuh — resume hanyalah optimasi, bukan keharusan."""
    source = _make_source(tmp_path)
    vault_path = tmp_path / "v.adtn"
    kunci_brankas([str(source)], str(vault_path), PASSWORD)

    status, name = buka_brankas(str(vault_path), PASSWORD, force=True)
    assert status == VaultStatus.SUCCESS
    assert (tmp_path / name / "a.txt").read_text(encoding="utf-8") == "alpha"
    assert not list(tmp_path.glob("._dec_*"))


def test_stale_pending_is_discarded_when_vault_changes(tmp_path):
    """Kalau file vault berubah setelah prompt, cache resume dibuang dan dekripsi
    diulang dari awal (fail-safe, bukan resume dari tar basi)."""
    source = _make_source(tmp_path)
    vault_path = tmp_path / "v.adtn"
    kunci_brankas([str(source)], str(vault_path), PASSWORD)

    status, _ = buka_brankas(str(vault_path), PASSWORD)
    assert status == VaultStatus.OVERWRITE_NEEDED

    # Ubah UKURAN file vault setelah prompt (signature pasti berubah, tak bergantung
    # resolusi mtime): resume harus menolak cache & dekripsi ulang, yang lalu gagal
    # sebagai vault korup (ada byte sisa setelah FINAL). Yang penting: tidak
    # mengekstrak tar basi diam-diam.
    data = bytearray(vault_path.read_bytes())
    data.append(0x00)
    vault_path.write_bytes(data)

    status, _ = buka_brankas(str(vault_path), PASSWORD, force=True)
    assert status == VaultStatus.ERROR
    assert not list(tmp_path.glob("._dec_*"))
