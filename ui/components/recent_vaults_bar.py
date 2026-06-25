"""
Modul: recent_vaults_bar.py
Deskripsi: Strip "Recent Vaults" full-width di dasar tab Buka/Kelola (opt-in).

Membaca daftar dari ``settings_store`` dan menyembunyikan diri (tanpa memakan ruang)
saat fitur mati atau daftar kosong. Kartu horizontal: ikon + nama + meta + tombol ×.
Klik kartu = minta buka; klik × = hapus dari daftar.
"""

from __future__ import annotations

import datetime as dt
import os

import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..i18n import register, tr
from ..settings_store import get_settings
from ..styles import (
    CLR_ACCENT,
    CLR_BORDER,
    CLR_CARD,
    CLR_HOVER_BG,
    CLR_HOVER_BORDER,
    CLR_INSET,
    CLR_TEXT_DIM,
    CLR_TEXT_FAINT,
    CLR_TEXT_MAIN,
)
from ..utils import format_file_size
from ..widgets import ElidedLabel, apply_shadow

_MONTHS = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}


class _RecentCard(QFrame):
    """Kartu horizontal satu vault di dalam strip Recent."""

    open_requested = Signal(str)
    remove_requested = Signal(str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._path = path
        exists = os.path.exists(path)
        self.setObjectName("RecentCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(58)
        # Lebar tetap & rata-kiri: 1 kartu pun tampak seperti tile normal, bukan
        # melar memenuhi panel. Min/maks supaya 4 kartu tetap muat di lebar minimum.
        self.setMinimumWidth(248)
        self.setMaximumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            f"QFrame#RecentCard {{ background: {CLR_INSET}; border: 1px solid {CLR_BORDER};"
            " border-radius: 12px; }"
            f" QFrame#RecentCard:hover {{ background: {CLR_HOVER_BG}; border: 1px solid {CLR_HOVER_BORDER}; }}"
        )
        h = QHBoxLayout(self)
        h.setContentsMargins(11, 9, 7, 9)
        h.setSpacing(11)

        icon_box = QLabel()
        icon_name = "mdi6.file-lock-outline" if exists else "mdi6.file-remove-outline"
        icon_box.setPixmap(
            qta.icon(icon_name, color=CLR_ACCENT if exists else CLR_TEXT_FAINT).pixmap(24, 24)
        )
        icon_box.setFixedSize(34, 34)
        icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_box.setStyleSheet(f"background: {CLR_CARD}; border-radius: 9px;")
        h.addWidget(icon_box, 0, Qt.AlignmentFlag.AlignVCenter)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        name = os.path.basename(path) or path
        lbl_name = ElidedLabel(name, mode=Qt.TextElideMode.ElideMiddle)
        lbl_name.setStyleSheet(
            f"color: {CLR_TEXT_MAIN if exists else CLR_TEXT_FAINT};"
            " font-size: 9.5pt; font-weight: 600; background: transparent;"
        )
        lbl_name.setToolTip(path)
        col.addWidget(lbl_name)
        lbl_meta = QLabel(self._meta(path, exists))
        lbl_meta.setStyleSheet(f"color: {CLR_TEXT_FAINT}; font-size: 8pt; background: transparent;")
        col.addWidget(lbl_meta)
        h.addLayout(col, 1)

        btn_x = QPushButton()
        btn_x.setObjectName("RecentCardX")
        btn_x.setIcon(qta.icon("mdi6.close", color=CLR_TEXT_FAINT))
        btn_x.setFixedSize(22, 22)
        btn_x.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_x.setToolTip(tr("dz.recent.remove", "Remove from list"))
        btn_x.setStyleSheet(
            "QPushButton#RecentCardX { border: none; background: transparent; border-radius: 6px; }"
            f" QPushButton#RecentCardX:hover {{ background: {CLR_CARD}; }}"
        )
        btn_x.clicked.connect(lambda: self.remove_requested.emit(self._path))
        h.addWidget(btn_x, 0, Qt.AlignmentFlag.AlignTop)

    def _meta(self, path: str, exists: bool) -> str:
        if not exists:
            return tr("dz.recent.missing", "missing")
        try:
            st = os.stat(path)
            d = dt.datetime.fromtimestamp(st.st_mtime)
            return f"{format_file_size(st.st_size)} · {d.day} {_MONTHS[d.month]} {d.year}"
        except OSError:
            return ""

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.open_requested.emit(self._path)
        super().mouseReleaseEvent(event)


class RecentVaultsBar(QWidget):
    """Strip 'Recent Vaults' full-width (opt-in). Sembunyi saat mati/kosong.

    Memancarkan ``open_requested(path)`` saat kartu yang masih ada diklik; hapus
    ditangani langsung lewat settings (memicu refresh semua bar).
    """

    open_requested = Signal(str)

    def __init__(self, parent=None, max_cards: int = 4):
        super().__init__(parent)
        self._settings = get_settings()
        self._max_cards = max_cards  # Open full-width = 4; Manage kolom setengah = 2
        self._build_ui()
        self._settings.changed.connect(self._on_settings_changed)
        self._refresh()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.panel = QFrame()
        self.panel.setObjectName("RecentBar")
        self.panel.setStyleSheet(
            f"QFrame#RecentBar {{ background: {CLR_CARD}; border: 1px solid {CLR_BORDER};"
            " border-radius: 16px; }"
        )
        apply_shadow(self.panel, blur_radius=24, opacity=30)
        outer.addWidget(self.panel)

        lay = QVBoxLayout(self.panel)
        lay.setContentsMargins(18, 12, 18, 14)
        lay.setSpacing(11)

        head = QHBoxLayout()
        head.setSpacing(8)
        ic = QLabel()
        ic.setPixmap(qta.icon("mdi6.history", color=CLR_TEXT_DIM).pixmap(16, 16))
        head.addWidget(ic, 0, Qt.AlignmentFlag.AlignVCenter)
        title = QLabel()
        register(title, "recentbar.title", "Recent Vaults")
        title.setStyleSheet(
            f"color: {CLR_TEXT_MAIN}; font-size: 10pt; font-weight: 700; background: transparent;"
        )
        head.addWidget(title)
        head.addSpacing(6)
        sub = QLabel()
        register(sub, "recentbar.sub", "Quick access to vaults you've used")
        sub.setStyleSheet(f"color: {CLR_TEXT_FAINT}; font-size: 8.5pt; background: transparent;")
        head.addWidget(sub)
        head.addStretch(1)
        self.btn_clear = QPushButton()
        register(self.btn_clear, "dz.recent.clear", "Clear")
        self.btn_clear.setObjectName("RecentBarClear")
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setStyleSheet(
            "QPushButton#RecentBarClear { border: none; background: transparent;"
            f" color: {CLR_TEXT_DIM}; font-size: 9pt; }}"
            f" QPushButton#RecentBarClear:hover {{ color: {CLR_ACCENT}; }}"
        )
        self.btn_clear.clicked.connect(self._settings.clear_recent_vaults)
        head.addWidget(self.btn_clear)
        lay.addLayout(head)

        self.cards_row = QHBoxLayout()
        self.cards_row.setContentsMargins(0, 0, 0, 0)
        self.cards_row.setSpacing(12)
        lay.addLayout(self.cards_row)

    def _on_settings_changed(self, key: str) -> None:
        if key == "*" or key.startswith("privacy/recent"):
            self._refresh()

    def _clear_cards(self) -> None:
        while self.cards_row.count():
            item = self.cards_row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _refresh(self) -> None:
        self._clear_cards()
        if not self._settings.recent_enabled():
            self.hide()
            return
        entries = self._settings.recent_vaults()[: self._max_cards]
        if not entries:
            self.hide()
            return
        for entry in entries:
            card = _RecentCard(entry["path"])
            card.open_requested.connect(self._on_open)
            card.remove_requested.connect(self._settings.remove_recent_vault)
            self.cards_row.addWidget(card, 0)
        # Kartu rata-kiri; sisa lebar diserap stretch (seperti toolbar recent files).
        self.cards_row.addStretch(1)
        self.show()

    def _on_open(self, path: str) -> None:
        if not os.path.exists(path):
            self._settings.remove_recent_vault(path)
            return
        self.open_requested.emit(path)
