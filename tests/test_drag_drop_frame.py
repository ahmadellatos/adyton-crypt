"""Tests for the shared DragDropFrame path-selection logic — the accept/multi
wiring used by DropZoneLock (multi, existing paths) and DropZoneOpen (single,
.adtn only). Exercises _selected_paths directly (synthetic QDropEvents don't
preserve QMimeData type under PySide6)."""

import os

import pytest

pytest.importorskip("PySide6")

from ui.widgets import DragDropFrame


@pytest.mark.qt
def test_multi_mode_keeps_all_accepted(qtbot, tmp_path):
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    f2 = tmp_path / "b.txt"
    f2.write_text("y")

    frame = DragDropFrame(multi=True, accept=lambda p: bool(p) and os.path.exists(p))
    qtbot.addWidget(frame)

    selected = frame._selected_paths([str(f1), str(f2)])
    assert sorted(selected) == sorted([str(f1), str(f2)])


@pytest.mark.qt
def test_multi_mode_filters_out_nonexistent(qtbot, tmp_path):
    real = tmp_path / "real.txt"
    real.write_text("x")
    ghost = tmp_path / "ghost.txt"  # never created

    frame = DragDropFrame(multi=True, accept=lambda p: bool(p) and os.path.exists(p))
    qtbot.addWidget(frame)

    assert frame._selected_paths([str(real), str(ghost)]) == [str(real)]


@pytest.mark.qt
def test_single_mode_takes_first_accepted_only(qtbot, tmp_path):
    other = tmp_path / "x.bin"
    v1 = tmp_path / "one.adtn"
    v2 = tmp_path / "two.adtn"

    frame = DragDropFrame(multi=False, accept=lambda p: p.lower().endswith(".adtn"))
    qtbot.addWidget(frame)

    assert frame._selected_paths([str(other), str(v1), str(v2)]) == [str(v1)]


@pytest.mark.qt
def test_no_accepted_path_returns_empty(qtbot, tmp_path):
    frame = DragDropFrame(multi=False, accept=lambda p: p.lower().endswith(".adtn"))
    qtbot.addWidget(frame)

    assert frame._selected_paths([str(tmp_path / "x.bin")]) == []


@pytest.mark.qt
def test_default_accept_keeps_nonempty(qtbot):
    frame = DragDropFrame(multi=True)  # no accept → keep any non-empty path
    qtbot.addWidget(frame)

    assert frame._selected_paths(["/some/path", "", "/other"]) == ["/some/path", "/other"]
