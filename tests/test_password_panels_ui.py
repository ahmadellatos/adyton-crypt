"""Qt-level tests for the shared password widgets: CreatePasswordForm, the thin
PasswordPanelLock wrapper, and the reusable widget builders."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QSizePolicy

from ui.components.create_password_form import CreatePasswordForm
from ui.components.password_panel_lock import PasswordPanelLock
from ui.widgets import (
    PasswordLineEdit,
    build_card_header,
    build_tips_box,
    make_generator_button,
)


def _press_enter(line_edit, modifier=Qt.KeyboardModifier.NoModifier):
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, modifier)
    QApplication.sendEvent(line_edit, ev)
    return ev


# 14 chars, no dictionary words, all four character classes present.
STRONG_PW = "Zr4!qP9mWk2$tL"


@pytest.mark.qt
def test_create_form_enforces_full_gate(qtbot):
    form = CreatePasswordForm()
    qtbot.addWidget(form)

    assert form.is_valid() is False  # empty

    form.entry_pw1.setText("weak")
    form.entry_pw2.setText("weak")
    assert form.is_valid() is False  # fails checklist

    form.entry_pw1.setText(STRONG_PW)
    form.entry_pw2.setText(STRONG_PW)
    assert form.is_valid() is True
    assert form.get_password() == STRONG_PW

    form.entry_pw2.setText(STRONG_PW + "x")
    assert form.is_valid() is False  # mismatched confirmation


@pytest.mark.qt
def test_create_form_generate_produces_valid_matching_password(qtbot):
    form = CreatePasswordForm()
    qtbot.addWidget(form)

    form.generate()
    assert form.is_valid() is True
    assert form.get_password() == form.entry_pw2.text()


@pytest.mark.qt
def test_create_form_reset_clears_and_invalidates(qtbot):
    form = CreatePasswordForm()
    qtbot.addWidget(form)

    form.generate()
    form.reset()
    assert form.get_password() == ""
    assert form.is_valid() is False


@pytest.mark.qt
def test_create_form_emits_valid_state(qtbot):
    form = CreatePasswordForm()
    qtbot.addWidget(form)

    seen: list[bool] = []
    form.valid_state_changed.connect(seen.append)
    form.entry_pw1.setText(STRONG_PW)
    form.entry_pw2.setText(STRONG_PW)
    assert seen[-1] is True


@pytest.mark.qt
def test_lock_panel_delegates_to_form(qtbot):
    panel = PasswordPanelLock()
    qtbot.addWidget(panel)

    assert panel.get_password() == ""

    panel.btn_gen.click()  # generator fills the embedded form
    assert panel.get_password() != ""
    assert panel.form.is_valid() is True

    panel.reset_fields()
    assert panel.get_password() == ""


@pytest.mark.qt
def test_lock_panel_reemits_valid_signal(qtbot):
    panel = PasswordPanelLock()
    qtbot.addWidget(panel)

    seen: list[bool] = []
    panel.valid_state_changed.connect(seen.append)
    panel.btn_gen.click()
    assert seen[-1] is True


@pytest.mark.qt
def test_shared_builders(qtbot):
    btn = make_generator_button()
    assert btn.objectName() == "BtnGen"

    _, title, sub = build_card_header(
        "mdi6.key-outline", "#ffffff", "Title", "Subtitle", button=btn
    )
    assert title.objectName() == "CardTitle"
    assert sub.objectName() == "CardSubtitle"
    assert title.text() == "Title"
    assert sub.text() == "Subtitle"

    # tips = (icon_name, color, i18n_key, default_text); label text comes from the default.
    box = build_tips_box([("mdi6.lock-outline", "#ffffff", "tips.demo", "hello")])
    assert box.objectName() == "TipsBox"
    from PySide6.QtWidgets import QLabel

    tip_texts = [lbl.text() for lbl in box.findChildren(QLabel) if lbl.objectName() == "TipText"]
    assert tip_texts == ["hello"]


@pytest.mark.qt
def test_password_input_height_is_fixed_and_uniform(qtbot):
    # Every password field is a PasswordLineEdit; pinning its vertical policy
    # keeps the box a uniform 52px regardless of surrounding layout space
    # (regression guard for the Text-tab decrypt field looking taller).
    pe = PasswordLineEdit("placeholder")
    qtbot.addWidget(pe)
    assert pe.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Fixed
    assert pe.sizeHint().height() == 52


@pytest.mark.qt
def test_lock_enter_from_main_and_recovery_fields(qtbot):
    """Enter di field password utama MAUPUN recovery passphrase memicu aksi kunci,
    dan event dikonsumsi (tak merambat ke CTA → cegah bug start-lalu-cancel)."""
    panel = PasswordPanelLock()
    qtbot.addWidget(panel)

    fired = []
    panel.attach_return_event(lambda: fired.append(1))

    ev_main = _press_enter(panel.form.entry_pw2.line_edit)
    ev_rec = _press_enter(panel.recovery_hint.entry_pass.line_edit)

    assert len(fired) == 2  # kedua field memicu aksi
    assert ev_main.isAccepted() is True
    assert ev_rec.isAccepted() is True


@pytest.mark.qt
def test_create_form_enter_consumed_and_fires_once(qtbot):
    """CreatePasswordForm (Lock/Text/Manage): Enter di confirm → submit sekali,
    Ctrl+Enter tidak submit."""
    form = CreatePasswordForm()
    qtbot.addWidget(form)

    fired = []
    form.attach_return_event(lambda: fired.append(1))

    ev = _press_enter(form.entry_pw2.line_edit)
    assert fired == [1]
    assert ev.isAccepted() is True

    _press_enter(form.entry_pw2.line_edit, Qt.KeyboardModifier.ControlModifier)
    assert fired == [1]  # Ctrl+Enter tidak menambah submit
