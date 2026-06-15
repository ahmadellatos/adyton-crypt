"""Tests for non-Qt UI utility helpers."""

from core.vault import VaultStatus
from ui.utils import (
    ProgressETA,
    format_progress_label,
    format_user_error,
    progress_stage_label,
)


def test_format_user_error_wrong_password_is_actionable():
    msg = format_user_error(VaultStatus.WRONG_PASSWORD, None, "buka")
    assert "password" in msg.lower()
    assert "corrupted" in msg
    assert "Error:" not in msg


def test_format_user_error_strips_technical_prefix():
    msg = format_user_error(VaultStatus.ERROR, "Error: disk full", "kunci")
    assert msg.startswith("Couldn't lock the vault.")
    assert "Error:" not in msg
    assert "disk full" in msg


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
    assert eta.last_eta != "Calculating…"


def test_progress_eta_uses_readable_approx_wording(monkeypatch):
    ticks = iter([0.0, 2.0, 4.0])
    monkeypatch.setattr("ui.utils.time.monotonic", lambda: next(ticks))

    eta = ProgressETA(min_update_interval=0.0)
    eta.update(0.10)
    label = eta.update(0.50)

    assert label.startswith("about") or label == "Almost done"
    assert "~" not in label


def test_open_progress_label_makes_cancel_affordance_clear():
    title, subtitle = format_progress_label(0.62, "buka", "about 1m 13s left")

    assert title == "Opening vault"
    assert "Click to cancel" in subtitle
    assert "Extracting" in subtitle


def test_progress_stage_label_for_open_flow():
    assert progress_stage_label(0.01, "buka") == "Verifying password"
    assert progress_stage_label(0.50, "buka") == "Extracting data"
    assert progress_stage_label(0.93, "buka") == "Moving result"
