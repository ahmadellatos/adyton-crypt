"""Qt-level tests untuk Tab Manage + pengenalan format vault di drop zone.

Termasuk regresi penting: drop zone HARUS mengenali vault Adyton sebagai openable,
kalau tidak tab Buka maupun Manage tak bisa memuat vault default.
"""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from core.crypto import generate_recovery_code
from core.vault import (
    VaultStatus,
    add_keyfile,
    generate_keyfile,
    kunci_brankas,
    remove_keyfile,
    vault_info,
)
from ui.components.drop_zone_open import DropZoneOpen
from ui.tab_manage import TabManage

PASSWORD = "P@ssw0rd!Kuat123"


def _make_vault(tmp_path, **kwargs) -> str:
    src = tmp_path / "secret"
    src.mkdir(exist_ok=True)
    (src / "a.txt").write_text("hello", encoding="utf-8")
    vault = tmp_path / "v.adtn"
    status, message = kunci_brankas([str(src)], str(vault), PASSWORD, **kwargs)
    assert status == VaultStatus.SUCCESS, message
    return str(vault)


def _make_keyfile(tmp_path, name: str = "adyton.key") -> str:
    path = tmp_path / name
    status, message = generate_keyfile(str(path))
    assert status == VaultStatus.SUCCESS, message
    return str(path)


def _make_unsupported_vault(tmp_path) -> str:
    """Vault Adyton dengan byte versi asing → tak bisa dikelola di Manage."""
    base = _make_vault(tmp_path)
    data = bytearray(Path(base).read_bytes())
    data[4] = 0x02  # byte versi yang tidak dikenali
    out = tmp_path / "unsupported.adtn"
    out.write_bytes(bytes(data))
    return str(out)


@pytest.mark.qt
def test_dropzone_recognizes_vault(qtbot, tmp_path):
    vault = _make_vault(tmp_path)
    dz = DropZoneOpen()
    qtbot.addWidget(dz)

    dz.load_file(vault)
    assert dz.can_open_file() is True
    assert dz.get_file() == vault


@pytest.mark.qt
def test_dropzone_rejects_garbage_adtn(qtbot, tmp_path):
    bad = tmp_path / "bad.adtn"
    bad.write_bytes(b"not a real vault at all")
    dz = DropZoneOpen()
    qtbot.addWidget(dz)

    dz.load_file(str(bad))
    assert dz.can_open_file() is False


@pytest.mark.qt
def test_manage_loads_vault_and_enables_actions(qtbot, tmp_path):
    vault = _make_vault(tmp_path, hint="my hint")
    tab = TabManage()
    qtbot.addWidget(tab)

    tab.drop_zone.load_file(vault)
    # Gating: memuat vault saja belum cukup — aksi tetap nonaktif sampai
    # kredensial saat ini + password baru yang valid terisi.
    assert tab.btn_change.isEnabled() is False
    assert "Adyton Vault" in tab.lbl_info.text()
    assert "Hint: yes" in tab.lbl_info.text()

    tab.entry_current.setText(PASSWORD)
    tab.form.entry_pw1.setText(PASSWORD)
    tab.form.entry_pw2.setText(PASSWORD)
    assert tab.btn_change.isEnabled() is True


@pytest.mark.qt
def test_manage_recovery_section_without_recovery(qtbot, tmp_path):
    vault = _make_vault(tmp_path)
    tab = TabManage()
    qtbot.addWidget(tab)
    tab.show()

    tab.drop_zone.load_file(vault)
    tab.stack.setCurrentIndex(1)  # buka halaman "Recovery key"
    assert tab.add_controls.isVisible() is True
    assert tab.btn_remove.isVisible() is False


@pytest.mark.qt
def test_manage_recovery_section_with_recovery(qtbot, tmp_path):
    vault = _make_vault(tmp_path, recovery_secret=generate_recovery_code(), recovery_type="code")
    tab = TabManage()
    qtbot.addWidget(tab)
    tab.show()

    tab.drop_zone.load_file(vault)
    tab.stack.setCurrentIndex(1)  # buka halaman "Recovery key"
    assert "Recovery key: yes" in tab.lbl_info.text()
    assert tab.btn_remove.isVisible() is True
    assert tab.add_controls.isVisible() is False


@pytest.mark.qt
def test_manage_card_height_follows_active_page(qtbot, tmp_path):
    """Card harus menyusut mengikuti konten: halaman 'Recovery key' jauh lebih
    pendek dari halaman 'Change password' (form panjang)."""
    vault = _make_vault(tmp_path, recovery_secret=generate_recovery_code(), recovery_type="code")
    tab = TabManage()
    qtbot.addWidget(tab)
    tab.drop_zone.load_file(vault)

    tab.stack.setCurrentIndex(0)  # change password (form tinggi)
    pw_h = tab.stack.maximumHeight()
    tab.stack.setCurrentIndex(1)  # recovery (pendek)
    rec_h = tab.stack.maximumHeight()

    assert rec_h < pw_h


@pytest.mark.qt
def test_manage_recovery_method_toggle_no_inflation(qtbot, tmp_path):
    """Regresi: passphrase → kembali ke 'generate code' tidak boleh membuat stack
    (dan kartu metode) memuai — tinggi harus kembali persis seperti semula."""
    vault = _make_vault(tmp_path)  # tanpa recovery → alur tambah
    tab = TabManage()
    qtbot.addWidget(tab)
    tab.drop_zone.load_file(vault)
    tab.stack.setCurrentIndex(1)

    h_code = tab.stack.maximumHeight()
    tab._select_method("passphrase")
    h_pass = tab.stack.maximumHeight()
    tab._select_method("code")
    h_code_again = tab.stack.maximumHeight()

    assert h_pass > h_code  # halaman passphrase lebih tinggi (ada field)
    assert h_code_again == h_code  # balik ke tinggi semula, tidak memuai


@pytest.mark.qt
def test_manage_unsupported_vault_badge_matches_status(qtbot, tmp_path):
    """Vault dengan versi asing → badge kartu harus 'UNSUPPORTED' (bukan tetap
    'FORMAT ✓'), dan _guard() menolak aksi. Memuat vault valid mengembalikan badge
    'ok' + aksi aktif."""
    unsupported = _make_unsupported_vault(tmp_path)
    valid = _make_vault(tmp_path)
    tab = TabManage()
    qtbot.addWidget(tab)

    tab.drop_zone.load_file(unsupported)
    assert tab.drop_zone.valid_badge.text() == "UNSUPPORTED"
    assert tab.drop_zone.valid_badge.property("state") == "warn"
    # Vault tak dikenali tidak boleh bisa dikelola walau kontrol tetap interaktif.
    assert tab._guard() is False

    tab.drop_zone.load_file(valid)
    assert tab.drop_zone.valid_badge.property("state") == "ok"
    # Vault valid termuat, tetapi aksi baru aktif setelah precondition
    # kredensial lengkap (gating yang sama seperti tab lain).
    assert tab.btn_change.isEnabled() is False
    tab.entry_current.setText(PASSWORD)
    tab.form.entry_pw1.setText(PASSWORD)
    tab.form.entry_pw2.setText(PASSWORD)
    assert tab.btn_change.isEnabled() is True


@pytest.mark.qt
def test_manage_input_clickable_after_clear(qtbot, tmp_path):
    """Regresi: muat vault lalu clear → input password harus tetap enabled
    (bisa diklik), bukan ter-disable."""
    vault = _make_vault(tmp_path)
    tab = TabManage()
    qtbot.addWidget(tab)

    tab.drop_zone.load_file(vault)
    assert tab.entry_current.isEnabled() is True
    tab.drop_zone.reset_zone()  # tombol × → clear
    assert tab.entry_current.isEnabled() is True


@pytest.mark.qt
def test_manage_input_stays_clickable_after_clear(qtbot, tmp_path):
    """Regresi: setelah vault di-clear dari drop zone, input password tetap bisa
    diklik (tidak ter-disable seperti bug sebelumnya)."""
    vault = _make_vault(tmp_path)
    tab = TabManage()
    qtbot.addWidget(tab)

    tab.drop_zone.load_file(vault)
    assert tab.entry_current.isEnabled() is True

    tab.drop_zone.reset_zone()  # klik × untuk clear vault
    assert tab.entry_current.isEnabled() is True


@pytest.mark.qt
def test_manage_guard_requires_credential(qtbot, tmp_path):
    vault = _make_vault(tmp_path)
    tab = TabManage()
    qtbot.addWidget(tab)

    tab.drop_zone.load_file(vault)
    assert tab._guard() is False  # no current credential yet

    tab.entry_current.setText(PASSWORD)
    assert tab._guard() is True


@pytest.mark.qt
def test_manage_rejects_unselected_vault(qtbot):
    tab = TabManage()
    qtbot.addWidget(tab)
    tab.entry_current.setText("whatever")
    assert tab._guard() is False  # no vault selected


# ── Keyfile / 2FA management (segmen ketiga) ────────────────────────────────


@pytest.mark.qt
def test_manage_keyfile_section_without_keyfile(qtbot, tmp_path):
    """Vault non-2FA → halaman Keyfile menampilkan kontrol AKTIFKAN; baris keyfile
    'current' di atas tetap tersembunyi (vault belum membutuhkan keyfile)."""
    vault = _make_vault(tmp_path)
    tab = TabManage()
    qtbot.addWidget(tab)
    tab.show()

    tab.drop_zone.load_file(vault)
    tab.stack.setCurrentIndex(2)  # halaman Keyfile
    assert tab.kf_add_controls.isVisible() is True
    assert tab.kf_remove_controls.isVisible() is False
    assert tab.keyfile_row.isVisible() is False


@pytest.mark.qt
def test_manage_keyfile_section_with_keyfile(qtbot, tmp_path):
    """Vault 2FA → halaman Keyfile menampilkan kontrol MATIKAN; baris keyfile
    'current' muncul untuk menyuplai keyfile."""
    keyfile = _make_keyfile(tmp_path)
    vault = _make_vault(tmp_path, keyfile_path=keyfile)
    assert vault_info(vault)["requires_keyfile"] is True
    tab = TabManage()
    qtbot.addWidget(tab)
    tab.show()

    tab.drop_zone.load_file(vault)
    tab.stack.setCurrentIndex(2)
    assert tab.kf_add_controls.isVisible() is False
    assert tab.kf_remove_controls.isVisible() is True
    assert tab.keyfile_row.isVisible() is True


@pytest.mark.qt
def test_manage_enable_keyfile_gating(qtbot, tmp_path):
    """btn_kf_add aktif hanya setelah password + keyfile baru terpilih."""
    keyfile = _make_keyfile(tmp_path)
    vault = _make_vault(tmp_path)
    tab = TabManage()
    qtbot.addWidget(tab)

    tab.drop_zone.load_file(vault)
    tab.stack.setCurrentIndex(2)
    assert tab.btn_kf_add.isEnabled() is False
    tab.entry_current.setText(PASSWORD)
    assert tab.btn_kf_add.isEnabled() is False  # password saja belum cukup
    tab._add_keyfile_path = keyfile
    tab._refresh_action_buttons()
    assert tab.btn_kf_add.isEnabled() is True


@pytest.mark.qt
def test_manage_enable_keyfile_calls_core(qtbot, tmp_path, monkeypatch):
    """_enable_keyfile menjalankan add_keyfile(vault, password, keyfile)."""
    keyfile = _make_keyfile(tmp_path)
    vault = _make_vault(tmp_path)
    tab = TabManage()
    qtbot.addWidget(tab)

    tab.drop_zone.load_file(vault)
    tab.entry_current.setText(PASSWORD)
    tab._add_keyfile_path = keyfile

    captured = {}
    monkeypatch.setattr(
        tab, "_run_action", lambda func, *a, **k: captured.update(func=func, args=a, kwargs=k)
    )
    tab._enable_keyfile()
    assert captured["func"] is add_keyfile
    assert captured["args"] == (vault, PASSWORD, keyfile)
    assert captured["kwargs"] == {}


@pytest.mark.qt
def test_manage_enable_keyfile_blocked_without_keyfile(qtbot, tmp_path, monkeypatch):
    """Tanpa keyfile baru terpilih, _enable_keyfile tidak menjalankan worker."""
    vault = _make_vault(tmp_path)
    tab = TabManage()
    qtbot.addWidget(tab)

    tab.drop_zone.load_file(vault)
    tab.entry_current.setText(PASSWORD)

    ran = []
    monkeypatch.setattr(tab, "_run_action", lambda *a, **k: ran.append(True))
    tab._enable_keyfile()  # _add_keyfile_path kosong
    assert ran == []


@pytest.mark.qt
def test_manage_disable_keyfile_gating(qtbot, tmp_path):
    """btn_kf_remove aktif hanya setelah password + keyfile 'current' terpilih."""
    keyfile = _make_keyfile(tmp_path)
    vault = _make_vault(tmp_path, keyfile_path=keyfile)
    tab = TabManage()
    qtbot.addWidget(tab)

    tab.drop_zone.load_file(vault)
    tab.stack.setCurrentIndex(2)
    assert tab.btn_kf_remove.isEnabled() is False
    tab.entry_current.setText(PASSWORD)
    assert tab.btn_kf_remove.isEnabled() is False  # password saja belum cukup
    tab._manage_keyfile_path = keyfile
    tab._refresh_action_buttons()
    assert tab.btn_kf_remove.isEnabled() is True


@pytest.mark.qt
def test_manage_disable_keyfile_calls_core(qtbot, tmp_path, monkeypatch):
    """_disable_keyfile (setelah konfirmasi) menjalankan
    remove_keyfile(vault, password, keyfile)."""
    keyfile = _make_keyfile(tmp_path)
    vault = _make_vault(tmp_path, keyfile_path=keyfile)
    tab = TabManage()
    qtbot.addWidget(tab)

    tab.drop_zone.load_file(vault)
    tab.entry_current.setText(PASSWORD)
    tab._manage_keyfile_path = keyfile

    # Lewati dialog konfirmasi (anggap Accepted).
    from PySide6.QtWidgets import QDialog

    import ui.tab_manage as tm

    class _AcceptBox:
        def __init__(self, *a, **k):
            self.btn_yes = type("B", (), {"setText": lambda self, t: None})()

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(tm, "ModernMessageBox", _AcceptBox)
    captured = {}
    monkeypatch.setattr(
        tab, "_run_action", lambda func, *a, **k: captured.update(func=func, args=a)
    )
    tab._disable_keyfile()
    assert captured["func"] is remove_keyfile
    assert captured["args"] == (vault, PASSWORD, keyfile)


@pytest.mark.qt
def test_manage_keyfile_roundtrip_core(tmp_path):
    """Sanity core: aktifkan lalu matikan 2FA mengubah requires_keyfile bolak-balik."""
    keyfile = _make_keyfile(tmp_path)
    vault = _make_vault(tmp_path)
    assert vault_info(vault)["requires_keyfile"] is False

    status, _ = add_keyfile(vault, PASSWORD, keyfile)
    assert status == VaultStatus.SUCCESS
    assert vault_info(vault)["requires_keyfile"] is True

    status, _ = remove_keyfile(vault, PASSWORD, keyfile)
    assert status == VaultStatus.SUCCESS
    assert vault_info(vault)["requires_keyfile"] is False
