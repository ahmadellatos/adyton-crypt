"""Tes menu native: sudut membulat (filter global) + hover bertema."""

import re

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QTextEdit

import ui.styles as styles
from ui.app import _RoundedMenuFilter
from ui.menus import AccessibleCenteredMenu


@pytest.mark.qt
def test_native_menu_gets_translucent_frameless(qtbot):
    # Filter global membulatkan QMenu native: WA_TranslucentBackground + frameless
    # diset saat Polish agar border-radius QSS tak "bocor" jadi sudut lancip.
    from PySide6.QtWidgets import QApplication

    filt = _RoundedMenuFilter()
    QApplication.instance().installEventFilter(filt)
    try:
        m = QMenu()
        m.addAction("Undo")
        m.ensurePolished()
        assert m.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        assert bool(m.windowFlags() & Qt.WindowType.FramelessWindowHint)
    finally:
        QApplication.instance().removeEventFilter(filt)


@pytest.mark.qt
def test_textedit_context_menu_rounded(qtbot):
    from PySide6.QtWidgets import QApplication

    filt = _RoundedMenuFilter()
    QApplication.instance().installEventFilter(filt)
    try:
        te = QTextEdit()
        qtbot.addWidget(te)
        cm = te.createStandardContextMenu()
        cm.ensurePolished()
        assert cm.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    finally:
        QApplication.instance().removeEventFilter(filt)


@pytest.mark.qt
def test_accessible_menu_already_translucent(qtbot):
    # Menu kustom sudah mengatur translucent sendiri → filter melewatinya (idempotent).
    acm = AccessibleCenteredMenu()
    qtbot.addWidget(acm)
    acm.ensurePolished()
    assert acm.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


@pytest.mark.qt
def test_enter_filter_steps_aside_when_popup_open(qtbot):
    # Regresi: Enter pada menu yang dibuka dari tombol dulu dibajak
    # _EnterActivatesButtonFilter (meng-klik ulang tombol) → menu "cuma bisa spasi".
    # Kini filter MELEPAS Enter saat ada popup aktif → menu menanganinya sendiri.
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication, QPushButton

    from ui.app import _EnterActivatesButtonFilter
    from ui.menus import CenteredMenuAction

    filt = _EnterActivatesButtonFilter()
    btn = QPushButton("x")
    qtbot.addWidget(btn)
    btn.show()
    # Aktifkan window tombol dulu agar setFocus() benar-benar mendarat. Di platform
    # offscreen (suite penuh berbagi satu QApplication), setFocus() hanya efektif bila
    # top-level window tombol adalah window aktif; tanpa ini fokus bisa tak mendarat
    # tergantung state window dari test sebelumnya → focusWidget() None (bukan tombol).
    btn.activateWindow()
    btn.setFocus(Qt.FocusReason.OtherFocusReason)
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)

    # Tanpa popup: Enter pada tombol fokus tetap dikonsumsi (perilaku lama dipertahankan).
    assert filt.eventFilter(btn, ev) is True

    # Menu terbuka → Enter TIDAK dikonsumsi (diteruskan ke menu untuk diaktifkan).
    menu = AccessibleCenteredMenu()
    menu.addAction(CenteredMenuAction("File", "mdi6.file-outline", parent=menu))
    qtbot.addWidget(menu)
    menu.popup(btn.mapToGlobal(btn.rect().bottomLeft()))
    qtbot.waitUntil(lambda: QApplication.activePopupWidget() is not None, timeout=1000)
    assert filt.eventFilter(menu, ev) is False
    menu.close()


def test_menu_hover_is_accent_tint_not_background():
    # Regresi: dulu QMenu::item:selected = CLR_CARD (warna latar) → hover tak terlihat.
    qss = styles.load_stylesheet()
    sel = re.search(r"QMenu::item:selected \{([^}]*)\}", qss)
    assert sel is not None
    body = sel.group(1)
    assert "rgba(" in body  # tint aksen
    assert styles.CLR_CARD not in body  # bukan lagi warna latar menu
