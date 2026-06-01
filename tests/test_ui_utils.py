"""Tests for non-Qt UI utility helpers."""

from ui.utils import (
    ProgressETA,
    format_progress_label,
    format_user_error,
    progress_stage_label,
)
from core.vault import VaultStatus


def test_format_user_error_wrong_password_is_actionable():
    msg = format_user_error(VaultStatus.WRONG_PASSWORD, None, "buka")
    assert "Password" in msg
    assert "rusak" in msg
    assert "Error:" not in msg


def test_format_user_error_strips_technical_prefix():
    msg = format_user_error(VaultStatus.ERROR, "Error: disk penuh", "kunci")
    assert msg.startswith("Tidak bisa mengunci brankas.")
    assert "Error:" not in msg
    assert "disk penuh" in msg


def test_progress_eta_never_regresses(monkeypatch):
    ticks = iter([0.0, 1.2, 2.4, 3.6])
    monkeypatch.setattr("ui.utils.time.monotonic", lambda: next(ticks))

    eta = ProgressETA(min_update_interval=0.0)
    eta.update(0.10)
    first_progress = eta.last_progress
    eta.update(0.30)
    eta.update(0.20)

    assert first_progress == 0.10
    assert eta.last_progress == 0.30
    assert eta.last_eta != "Menghitung..."


def test_progress_eta_uses_readable_approx_wording(monkeypatch):
    ticks = iter([0.0, 2.0, 4.0])
    monkeypatch.setattr("ui.utils.time.monotonic", lambda: next(ticks))

    eta = ProgressETA(min_update_interval=0.0)
    eta.update(0.10)
    label = eta.update(0.50)

    assert label.startswith("sekitar") or label == "Hampir selesai"
    assert "~" not in label


def test_open_progress_label_makes_cancel_affordance_clear():
    title, subtitle = format_progress_label(0.62, "buka", "sekitar 1m 13s lagi")

    assert title == "Membuka brankas"
    assert "Klik untuk membatalkan" in subtitle
    assert "Mengekstrak" in subtitle


def test_progress_stage_label_for_open_flow():
    assert progress_stage_label(0.01, "buka") == "Memverifikasi password"
    assert progress_stage_label(0.50, "buka") == "Mengekstrak data"
    assert progress_stage_label(0.93, "buka") == "Memindahkan hasil"
