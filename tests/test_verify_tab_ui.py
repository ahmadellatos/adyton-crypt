"""Qt-level tests untuk wiring tombol Verify di Tab Buka.

Menguji gating tombol (mirror Open), dispatch ke verify_vault, dan routing hasil
(_on_verify_done) tanpa benar-benar menjalankan worker thread.
"""

import pytest

pytest.importorskip("PySide6")

import ui.tab_buka as tab_buka_mod
from core.vault import VaultStatus, kunci_brankas, verify_vault
from ui.tab_buka import TabBuka

PASSWORD = "P@ssw0rd!Kuat123"


def _make_vault(tmp_path) -> str:
    src = tmp_path / "secret"
    src.mkdir(exist_ok=True)
    (src / "a.txt").write_text("hello", encoding="utf-8")
    vault = tmp_path / "v.adtn"
    status, message = kunci_brankas([str(src)], str(vault), PASSWORD)
    assert status == VaultStatus.SUCCESS, message
    return str(vault)


@pytest.mark.qt
def test_verify_button_starts_disabled(qtbot):
    tab = TabBuka()
    qtbot.addWidget(tab)
    assert tab.btn_verify.isEnabled() is False


@pytest.mark.qt
def test_verify_enabled_with_file_and_password(qtbot, tmp_path):
    vault = _make_vault(tmp_path)
    tab = TabBuka()
    qtbot.addWidget(tab)

    tab.drop_zone.load_file(vault)
    tab.password_panel.entry_pw.setText(PASSWORD)

    assert tab.btn_verify.isEnabled() is True
    assert tab.btn_aksi.isEnabled() is True


@pytest.mark.qt
def test_verify_dispatches_verify_vault(qtbot, tmp_path, monkeypatch):
    vault = _make_vault(tmp_path)
    tab = TabBuka()
    qtbot.addWidget(tab)
    tab.drop_zone.load_file(vault)
    tab.password_panel.entry_pw.setText(PASSWORD)

    captured = {}

    def fake_start(worker, progress_cb, done_cb):
        captured["worker"] = worker  # jangan start thread di test

    monkeypatch.setattr(tab_buka_mod, "start_crypto_worker", fake_start)

    tab._verify()

    assert tab._mode == "verify"
    assert captured["worker"].func is verify_vault
    # args: (path, password); keyfile_path via kwargs
    assert captured["worker"].args[0] == vault
    assert captured["worker"].args[1] == PASSWORD
    tab.worker = None  # lepas ref worker yang tak dijalankan


@pytest.mark.qt
def test_verify_noop_without_file(qtbot, monkeypatch):
    tab = TabBuka()
    qtbot.addWidget(tab)
    called = {"n": 0}
    monkeypatch.setattr(
        tab_buka_mod,
        "start_crypto_worker",
        lambda *a, **k: called.__setitem__("n", called["n"] + 1),
    )
    tab._verify()  # tanpa file/password → tidak dispatch
    assert called["n"] == 0
    assert tab.worker is None


@pytest.mark.qt
def test_on_verify_done_success_resets_mode(qtbot, tmp_path):
    vault = _make_vault(tmp_path)
    tab = TabBuka()
    qtbot.addWidget(tab)
    tab.drop_zone.load_file(vault)
    tab._mode = "verify"

    tab._on_verify_done((VaultStatus.SUCCESS, "Vault verified — all data is intact."))

    assert tab._mode == "open"
    # Sukses tidak memunculkan error box.
    assert tab.password_panel.error_box.isHidden() is True


@pytest.mark.qt
def test_on_verify_done_corrupt_shows_error(qtbot, tmp_path):
    from core.vault import CORRUPT_VAULT_MESSAGE

    vault = _make_vault(tmp_path)
    tab = TabBuka()
    qtbot.addWidget(tab)
    tab.drop_zone.load_file(vault)
    tab._mode = "verify"

    tab._on_verify_done((VaultStatus.ERROR, CORRUPT_VAULT_MESSAGE))

    assert tab._mode == "open"
    # Korupsi → error box tampil dengan pesan korupsi.
    assert tab.password_panel.error_box.isHidden() is False
    assert tab.password_panel.lbl_error_msg.text() == CORRUPT_VAULT_MESSAGE


@pytest.mark.qt
def test_on_verify_done_wrong_password_shows_error(qtbot, tmp_path):
    vault = _make_vault(tmp_path)
    tab = TabBuka()
    qtbot.addWidget(tab)
    tab.drop_zone.load_file(vault)
    tab._mode = "verify"

    tab._on_verify_done((VaultStatus.WRONG_PASSWORD, None))

    assert tab._mode == "open"
    assert tab.password_panel.error_box.isHidden() is False
