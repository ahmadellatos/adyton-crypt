"""Qt-level tests untuk VaultBrowserDialog + wiring Browse/extract di Tab Buka.

Menguji pembangunan pohon, tri-state checkbox, kumpulan path terpilih, gating tombol,
serta dispatch _browse → list_vault_contents dan _prompt_and_extract → extract_selected
(tanpa menjalankan worker thread nyata).
"""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

import ui.tab_buka as tab_buka_mod
from core.constants import VaultEntry
from core.vault import VaultStatus, extract_selected, kunci_brankas, list_vault_contents
from ui.tab_buka import TabBuka
from ui.vault_browser_dialog import VaultBrowserDialog

PASSWORD = "P@ssw0rd!Kuat123"

_ENTRIES = [
    VaultEntry("docs", 0, True, 0),
    VaultEntry("docs/a.txt", 700, False, 0),
    VaultEntry("docs/sub", 0, True, 0),
    VaultEntry("docs/sub/b.bin", 5000, False, 0),
    VaultEntry("empty", 0, True, 0),
    VaultEntry("readme.md", 650, False, 0),
]


def _find(dialog, path):
    role = Qt.ItemDataRole.UserRole

    def walk(item):
        if str(item.data(0, role)) == path:
            return item
        for i in range(item.childCount()):
            r = walk(item.child(i))
            if r:
                return r
        return None

    for i in range(dialog.tree.topLevelItemCount()):
        r = walk(dialog.tree.topLevelItem(i))
        if r:
            return r
    return None


def _make_vault(tmp_path) -> str:
    src = tmp_path / "secret"
    src.mkdir(exist_ok=True)
    (src / "a.txt").write_text("hello", encoding="utf-8")
    vault = tmp_path / "v.adtn"
    status, message = kunci_brankas([str(src)], str(vault), PASSWORD)
    assert status == VaultStatus.SUCCESS, message
    return str(vault)


# ── Dialog ───────────────────────────────────────────────────────────────────────


@pytest.mark.qt
def test_dialog_builds_tree_and_counts_files(qtbot):
    dlg = VaultBrowserDialog("MyStuff", _ENTRIES)
    qtbot.addWidget(dlg)
    assert len(dlg._file_items) == 3
    assert dlg.selected_count() == 0
    assert dlg.btn_extract.isEnabled() is False


@pytest.mark.qt
def test_dialog_checking_dir_selects_children_tristate(qtbot):
    dlg = VaultBrowserDialog("MyStuff", _ENTRIES)
    qtbot.addWidget(dlg)

    sub = _find(dlg, "docs/sub")
    sub.setCheckState(0, Qt.CheckState.Checked)

    assert dlg.selected_count() == 1
    assert dlg.selected_bytes() == 5000
    # Induk 'docs' jadi partial karena a.txt belum dicentang.
    assert _find(dlg, "docs").checkState(0) == Qt.CheckState.PartiallyChecked
    # Path terpilih = node ter-check paling atas.
    assert dlg.selected_paths() == ["docs/sub"]
    assert dlg.btn_extract.isEnabled() is True


@pytest.mark.qt
def test_dialog_select_all_and_none(qtbot):
    dlg = VaultBrowserDialog("MyStuff", _ENTRIES)
    qtbot.addWidget(dlg)

    dlg._set_all(Qt.CheckState.Checked)
    assert dlg.selected_count() == 3
    assert dlg.selected_bytes() == 6350
    assert set(dlg.selected_paths()) == {"docs", "empty", "readme.md"}

    dlg._set_all(Qt.CheckState.Unchecked)
    assert dlg.selected_count() == 0
    assert dlg.btn_extract.isEnabled() is False


@pytest.mark.qt
def test_dialog_empty_vault(qtbot):
    dlg = VaultBrowserDialog("Empty", [])
    qtbot.addWidget(dlg)
    assert dlg.selected_count() == 0
    assert dlg.btn_extract.isEnabled() is False


# ── Wiring Tab Buka ────────────────────────────────────────────────────────────────


@pytest.mark.qt
def test_secondary_buttons_live_in_password_panel(qtbot):
    # Verify & Browse ada di baris aksi sekunder DALAM password panel (bukan
    # ditumpuk full-width di dasar tab), dan TabBuka meng-alias referensinya.
    tab = TabBuka()
    qtbot.addWidget(tab)
    assert tab.btn_verify is tab.password_panel.btn_verify
    assert tab.btn_browse is tab.password_panel.btn_browse
    assert tab.btn_verify.parent() is tab.password_panel.secondary_actions
    assert tab.btn_browse.parent() is tab.password_panel.secondary_actions


@pytest.mark.qt
def test_browse_button_starts_disabled(qtbot):
    tab = TabBuka()
    qtbot.addWidget(tab)
    assert tab.btn_browse.isEnabled() is False


@pytest.mark.qt
def test_browse_enabled_with_file_and_password(qtbot, tmp_path):
    vault = _make_vault(tmp_path)
    tab = TabBuka()
    qtbot.addWidget(tab)
    tab.drop_zone.load_file(vault)
    tab.password_panel.entry_pw.setText(PASSWORD)
    assert tab.btn_browse.isEnabled() is True


@pytest.mark.qt
def test_browse_dispatches_list_vault_contents(qtbot, tmp_path, monkeypatch):
    vault = _make_vault(tmp_path)
    tab = TabBuka()
    qtbot.addWidget(tab)
    tab.drop_zone.load_file(vault)
    tab.password_panel.entry_pw.setText(PASSWORD)

    captured = {}
    monkeypatch.setattr(
        tab_buka_mod, "start_crypto_worker", lambda w, p, d: captured.update(worker=w)
    )

    tab._browse()

    assert tab._mode == "browse"
    assert captured["worker"].func is list_vault_contents
    assert captured["worker"].args[0] == vault
    assert captured["worker"].args[1] == PASSWORD
    # Credential di-cache untuk pass ekstrak berikutnya.
    assert tab._cached_pw == PASSWORD
    tab.worker = None


@pytest.mark.qt
def test_prompt_and_extract_dispatches_extract_selected(qtbot, tmp_path, monkeypatch):
    vault = _make_vault(tmp_path)
    tab = TabBuka()
    qtbot.addWidget(tab)
    tab.drop_zone.load_file(vault)
    tab._cached_pw = PASSWORD
    tab._cached_keyfile = None

    # Dialog "diterima" dengan pilihan; folder tujuan dipilih.
    monkeypatch.setattr(VaultBrowserDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(VaultBrowserDialog, "selected_paths", lambda self: ["readme.md"])
    monkeypatch.setattr(VaultBrowserDialog, "selected_bytes", lambda self: 650)
    dest = tmp_path / "out"
    dest.mkdir()
    monkeypatch.setattr(tab_buka_mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(dest))

    captured = {}
    monkeypatch.setattr(
        tab_buka_mod, "start_crypto_worker", lambda w, p, d: captured.update(worker=w)
    )

    tab._prompt_and_extract("secret", _ENTRIES)

    assert tab._mode == "extract"
    w = captured["worker"]
    assert w.func is extract_selected
    assert w.args[0] == vault
    assert w.args[1] == PASSWORD
    assert w.args[2] == ["readme.md"]
    assert w.args[3] == str(dest)
    assert w.kwargs["expected_bytes"] == 650
    tab.worker = None


@pytest.mark.qt
def test_prompt_and_extract_cancelled_dialog_no_dispatch(qtbot, tmp_path, monkeypatch):
    tab = TabBuka()
    qtbot.addWidget(tab)
    tab._cached_pw = PASSWORD

    monkeypatch.setattr(VaultBrowserDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    called = {"n": 0}
    monkeypatch.setattr(
        tab_buka_mod,
        "start_crypto_worker",
        lambda *a, **k: called.__setitem__("n", called["n"] + 1),
    )

    tab._prompt_and_extract("secret", _ENTRIES)

    assert called["n"] == 0
    assert tab._cached_pw is None  # credential dibuang saat batal


@pytest.mark.qt
def test_on_extract_done_success(qtbot, tmp_path):
    vault = _make_vault(tmp_path)
    tab = TabBuka()
    qtbot.addWidget(tab)
    tab.drop_zone.load_file(vault)
    tab._mode = "extract"

    tab._on_extract_done((VaultStatus.SUCCESS, "secret"))

    assert tab._mode == "open"
    assert tab.password_panel.error_box.isHidden() is True


@pytest.mark.qt
def test_on_extract_done_error_shows_message(qtbot, tmp_path):
    vault = _make_vault(tmp_path)
    tab = TabBuka()
    qtbot.addWidget(tab)
    tab.drop_zone.load_file(vault)
    tab._mode = "extract"

    tab._on_extract_done((VaultStatus.ERROR, "Couldn't extract the selected items."))

    assert tab._mode == "open"
    assert tab.password_panel.error_box.isHidden() is False
