"""Tes perilaku CustomToolTip (tooltip global path/item) — butuh qtbot."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCursor

import ui.styles as styles
from ui.widgets import CustomToolTip


@pytest.mark.qt
def test_show_now_visible_and_timer_running(qtbot):
    tip = CustomToolTip()
    qtbot.addWidget(tip)
    tip.show_now("hello")
    assert tip.isVisible()
    assert tip._monitor_timer.isActive()  # polling pergerakan mouse aktif saat tampil


@pytest.mark.qt
def test_hide_on_move_stops_timer_no_stale_reshow(qtbot):
    # Regresi bug: dulu gerakan mouse hanya hide() tanpa stop timer → timer jalan
    # terus + bisa MUNCULKAN ULANG teks lama saat kursor diam lagi. Kini gerakan
    # memanggil hide_tooltip() (stop timer); show berikutnya hanya dari hover baru.
    tip = CustomToolTip()
    qtbot.addWidget(tip)
    tip.show_now("path-A")
    tip._last_cursor_pos = QCursor.pos() + QPoint(200, 200)  # simulasikan 'mouse pindah'
    tip._check_mouse_state()
    assert not tip.isVisible()
    assert not tip._monitor_timer.isActive()  # WAJIB berhenti → tak ada re-show basi


@pytest.mark.qt
def test_auto_hide_after_stillness(qtbot):
    tip = CustomToolTip()
    qtbot.addWidget(tip)
    tip.show_now("stay")
    tip._last_cursor_pos = QCursor.pos()  # 'diam'
    ticks = 0
    while tip.isVisible() and ticks < 1000:
        tip._check_mouse_state()
        ticks += 1
    assert not tip.isVisible()
    assert ticks * 50 >= tip._hide_delay_ms  # auto-hide ~5 dtk
    assert not tip._monitor_timer.isActive()


@pytest.mark.qt
def test_plaintext_and_zwsp_injection(qtbot):
    # Tooltip menampilkan path APA ADANYA: rich-text tak boleh ditafsir, dan
    # titik-putus zero-width disisipkan di pemisah agar path panjang bisa wrap.
    tip = CustomToolTip()
    qtbot.addWidget(tip)
    tip._pending_text = r"C:\Users\me\<b>&x</b>\vault.adtn"
    tip._do_show()
    zwsp = chr(0x200B)  # U+200B ZERO WIDTH SPACE
    assert tip.textFormat() == Qt.TextFormat.PlainText
    assert "<b>" in tip.text()  # tetap literal, bukan tag
    assert zwsp in tip.text()  # ZWSP disisipkan di pemisah path
    assert zwsp not in tip._pending_text  # sumber dedup tetap bersih


@pytest.mark.qt
def test_long_path_wraps_instead_of_one_wide_line(qtbot):
    tip = CustomToolTip()
    qtbot.addWidget(tip)
    tip._pending_text = "C:/" + "/".join(f"folder{i:02d}" for i in range(40))
    tip._do_show()
    assert tip.width() <= 560 + 4  # lebar dibatasi
    assert tip.height() > 30  # membungkus jadi beberapa baris (tak terpotong)


@pytest.mark.qt
def test_translucent_background_for_rounded_corners(qtbot):
    # Sudut membulat: window tooltip persegi opaque akan "membocorkan" border-radius
    # QSS jadi sudut lancip; WA_TranslucentBackground + paintEvent manual mengatasinya.
    tip = CustomToolTip()
    qtbot.addWidget(tip)
    assert tip.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


@pytest.mark.qt
def test_style_geometry_shared_but_colors_themed(qtbot):
    # Sanity: tooltip pakai satu objectName yang distyle QSS global (size/radius sama),
    # warna ikut tema (dipastikan di test_theme); di sini cukup objectName benar.
    tip = CustomToolTip()
    qtbot.addWidget(tip)
    assert tip.objectName() == "CustomToolTip"
    assert styles.CLR_TOOLTIP_BG  # token ada
