"""Tests untuk clipboard auto-clear helper (ui.utils.copy_to_clipboard_auto_clear).

Memverifikasi: teks benar tersalin, terhapus otomatis setelah timeout, dan TIDAK
menimpa isi clipboard bila user sudah menyalin sesuatu yang lain di antaranya.
"""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication

from ui.utils import copy_to_clipboard_auto_clear

# Timeout pendek + buffer tunggu agar test cepat namun stabil.
_CLEAR_MS = 150
_WAIT_MS = 500


@pytest.mark.qt
def test_copy_places_text_on_clipboard(qtbot):
    copy_to_clipboard_auto_clear("secret-value-123", timeout_ms=_CLEAR_MS)
    assert QGuiApplication.clipboard().text() == "secret-value-123"
    # Bersihkan jadwal clear yang masih menggantung agar tidak bocor ke test lain.
    qtbot.wait(_WAIT_MS)


@pytest.mark.qt
def test_clipboard_is_cleared_after_timeout(qtbot):
    copy_to_clipboard_auto_clear("ephemeral-secret", timeout_ms=_CLEAR_MS)
    assert QGuiApplication.clipboard().text() == "ephemeral-secret"

    qtbot.wait(_WAIT_MS)
    assert QGuiApplication.clipboard().text() == ""


@pytest.mark.qt
def test_clear_skipped_when_clipboard_changed(qtbot):
    """Jika user menyalin sesuatu yang lain sebelum timer berbunyi, isi baru itu
    tidak boleh ikut terhapus."""
    copy_to_clipboard_auto_clear("first-copy", timeout_ms=_CLEAR_MS)
    # User menyalin hal lain (mis. lewat aplikasi/aksi lain) sebelum auto-clear.
    QGuiApplication.clipboard().setText("user-typed-something-else")

    qtbot.wait(_WAIT_MS)
    assert QGuiApplication.clipboard().text() == "user-typed-something-else"


@pytest.mark.qt
def test_new_copy_resets_previous_timer(qtbot):
    """Salinan kedua harus me-reset jadwal clear yang pertama, bukan menumpuk."""
    copy_to_clipboard_auto_clear("old", timeout_ms=_CLEAR_MS)
    # Salin lagi dengan timeout lebih panjang sebelum timer pertama berbunyi.
    copy_to_clipboard_auto_clear("new", timeout_ms=_CLEAR_MS * 6)

    # Setelah jendela timer pertama lewat, "new" harus MASIH ada (timer di-reset).
    qtbot.wait(_WAIT_MS)
    assert QGuiApplication.clipboard().text() == "new"

    # Dan akhirnya terhapus setelah timeout yang lebih panjang berlalu.
    qtbot.wait(_CLEAR_MS * 6)
    assert QGuiApplication.clipboard().text() == ""
