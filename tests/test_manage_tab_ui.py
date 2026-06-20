"""Qt-level tests untuk Tab Manage + pengenalan format v3 di drop zone.

Termasuk regresi penting: drop zone HARUS mengenali vault v3 sebagai openable,
kalau tidak tab Buka maupun Manage tak bisa memuat vault default.
"""

import io
import tarfile

import pytest

pytest.importorskip("PySide6")

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.constants import (
    RECORD_TYPE_DATA,
    RECORD_TYPE_FINAL,
    RECORD_TYPE_METADATA,
    V2_FLAG_NONE,
)
from core.crypto import derive_key, generate_recovery_code
from core.vault import (
    VaultStatus,
    _v2_header_context,
    _v2_write_record,
    kunci_brankas,
)
from ui.components.drop_zone_open import DropZoneOpen
from ui.tab_manage import TabManage

PASSWORD = "P@ssw0rd!Kuat123"


def _make_v3_vault(tmp_path, **kwargs) -> str:
    src = tmp_path / "secret"
    src.mkdir()
    (src / "a.txt").write_text("hello", encoding="utf-8")
    vault = tmp_path / "v.adtn"
    status, message = kunci_brankas([str(src)], str(vault), PASSWORD, **kwargs)
    assert status == VaultStatus.SUCCESS, message
    return str(vault)


def _make_v2_vault(tmp_path) -> str:
    """Bangun vault v2 chunked-AEAD minimal (format lama, tak bisa dikelola)."""
    import os

    folder = "data"
    salt, file_id = os.urandom(16), os.urandom(16)
    aesgcm = AESGCM(derive_key(PASSWORD, salt))
    hc = _v2_header_context(salt, file_id, 1024 * 1024, V2_FLAG_NONE)

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        data = b"hi"
        info = tarfile.TarInfo(name=f"{folder}/a.txt")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

    vault = tmp_path / "old_v2.adtn"
    with vault.open("wb") as f:
        f.write(hc)
        nb = folder.encode("utf-8")
        _v2_write_record(f, aesgcm, hc, RECORD_TYPE_METADATA, 0, len(nb).to_bytes(2, "big") + nb)
        _v2_write_record(f, aesgcm, hc, RECORD_TYPE_DATA, 1, buf.getvalue())
        _v2_write_record(f, aesgcm, hc, RECORD_TYPE_FINAL, 2, b"")
    return str(vault)


@pytest.mark.qt
def test_dropzone_recognizes_v3_vault(qtbot, tmp_path):
    vault = _make_v3_vault(tmp_path)
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
def test_manage_loads_v3_and_enables_actions(qtbot, tmp_path):
    vault = _make_v3_vault(tmp_path, hint="my hint")
    tab = TabManage()
    qtbot.addWidget(tab)

    tab.drop_zone.load_file(vault)
    assert tab.btn_change.isEnabled() is True
    assert "v3" in tab.lbl_info.text()
    assert "Hint: yes" in tab.lbl_info.text()


@pytest.mark.qt
def test_manage_recovery_section_without_recovery(qtbot, tmp_path):
    vault = _make_v3_vault(tmp_path)
    tab = TabManage()
    qtbot.addWidget(tab)
    tab.show()

    tab.drop_zone.load_file(vault)
    tab.stack.setCurrentIndex(1)  # buka halaman "Recovery key"
    assert tab.add_controls.isVisible() is True
    assert tab.btn_remove.isVisible() is False


@pytest.mark.qt
def test_manage_recovery_section_with_recovery(qtbot, tmp_path):
    vault = _make_v3_vault(
        tmp_path, recovery_secret=generate_recovery_code(), recovery_type="code"
    )
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
    vault = _make_v3_vault(
        tmp_path, recovery_secret=generate_recovery_code(), recovery_type="code"
    )
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
    vault = _make_v3_vault(tmp_path)  # tanpa recovery → alur tambah
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
def test_manage_unsupported_v2_badge_matches_status(qtbot, tmp_path):
    """Vault v2 tak bisa dikelola → badge kartu harus 'UNSUPPORTED' (bukan tetap
    'FORMAT ✓'), konsisten dengan status header. Memuat v3 mengembalikannya."""
    v2 = _make_v2_vault(tmp_path)
    v3 = _make_v3_vault(tmp_path)
    tab = TabManage()
    qtbot.addWidget(tab)

    tab.drop_zone.load_file(v2)
    assert tab.drop_zone.valid_badge.text() == "UNSUPPORTED"
    assert tab.drop_zone.valid_badge.property("state") == "warn"
    assert tab.btn_change.isEnabled() is False

    tab.drop_zone.load_file(v3)
    assert tab.drop_zone.valid_badge.property("state") == "ok"
    assert tab.btn_change.isEnabled() is True


@pytest.mark.qt
def test_manage_input_clickable_after_clear(qtbot, tmp_path):
    """Regresi: muat vault lalu clear → input password harus tetap enabled
    (bisa diklik), bukan ter-disable."""
    vault = _make_v3_vault(tmp_path)
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
    vault = _make_v3_vault(tmp_path)
    tab = TabManage()
    qtbot.addWidget(tab)

    tab.drop_zone.load_file(vault)
    assert tab.entry_current.isEnabled() is True

    tab.drop_zone.reset_zone()  # klik × untuk clear vault
    assert tab.entry_current.isEnabled() is True


@pytest.mark.qt
def test_manage_guard_requires_credential(qtbot, tmp_path):
    vault = _make_v3_vault(tmp_path)
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
