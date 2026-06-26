"""Tests for IPC token authentication on the single-instance pipe.

The single-instance QLocalServer accepts local connections and can drive
encrypt/decrypt on supplied paths. A shared-secret token (readable only from the
user's app-data) is now required so arbitrary local processes can't inject
commands just by knowing the pipe name and protocol.
"""

import secrets

import main


def _reset_token_cache():
    main._IPC_TOKEN_CACHE = None


def test_ipc_token_is_nonempty_stable_and_persistent(tmp_path, monkeypatch):
    _reset_token_cache()
    monkeypatch.setattr(main, "get_data_dir", lambda: tmp_path)

    token = main._ipc_token()
    assert token
    assert len(token) >= 32

    # Stabil dalam proses (cache).
    assert main._ipc_token() == token

    # Persisten lewat file: proses lain (cache di-reset) membaca token yang sama.
    _reset_token_cache()
    assert main._ipc_token() == token
    assert (tmp_path / "ipc.token").read_text(encoding="utf-8").strip() == token


def test_frame_command_roundtrips_with_valid_token(tmp_path, monkeypatch):
    _reset_token_cache()
    monkeypatch.setattr(main, "get_data_dir", lambda: tmp_path)

    framed = main._frame_command("WAKEUP|C:/secret.adtn")
    token, sep, command = framed.partition("\n")

    assert sep == "\n"
    assert command == "WAKEUP|C:/secret.adtn"
    assert secrets.compare_digest(token, main._ipc_token())


def test_forged_token_does_not_match(tmp_path, monkeypatch):
    _reset_token_cache()
    monkeypatch.setattr(main, "get_data_dir", lambda: tmp_path)

    expected = main._ipc_token()
    forged = "deadbeef\nQUICK|encrypt|C:/victim.txt"
    token, _, command = forged.partition("\n")

    assert not secrets.compare_digest(token, expected)
    assert command == "QUICK|encrypt|C:/victim.txt"  # payload tetap terbaca, tapi ditolak


def test_token_falls_back_to_empty_when_appdata_unwritable(tmp_path, monkeypatch):
    """Best-effort: bila app-data tak bisa ditulis, token = "" dan IPC tetap jalan
    (pengirim & penerima di mesin yang sama tetap konsisten)."""
    _reset_token_cache()

    def _boom():
        raise OSError("read-only app data")

    monkeypatch.setattr(main, "get_data_dir", _boom)
    assert main._ipc_token() == ""
    # Pengirim & penerima sama-sama "" → cocok (tanpa proteksi, tapi fungsional).
    framed = main._frame_command("WAKEUP|x")
    token, _, _ = framed.partition("\n")
    assert secrets.compare_digest(token, main._ipc_token())
