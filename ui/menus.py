"""
Modul: menus.py
Deskripsi: Komponen menu kustom (Centered menu dengan icon dan highlight).
"""

import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QWidget,
    QWidgetAction,
)

from .styles import ACCENT_RGB, CLR_TEXT_DIM, CLR_TEXT_MAIN

# Latar item menu — highlight memakai tint aksen BERTEMA (ACCENT_RGB ikut light/dark),
# bukan teal hardcoded yang dulu salah hue di tema terang.
_MENU_ITEM_HIGHLIGHT = f"QWidget#CenteredMenuItem {{ background-color: rgba({ACCENT_RGB}, 0.12); border-radius: 7px; }}"
_MENU_ITEM_NORMAL = (
    "QWidget#CenteredMenuItem { background-color: transparent; border-radius: 7px; }"
)


class HoverMenuWidget(QWidget):
    def __init__(self, text, icon_name, icon_color, text_color, action_ref, parent=None):
        super().__init__(parent)
        self.action_ref = action_ref
        self._highlighted = False
        self.setObjectName("CenteredMenuItem")
        self.setStyleSheet(
            "QWidget#CenteredMenuItem { background-color: transparent; border-radius: 4px; }"
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(15, 8, 15, 8)
        lay.setSpacing(10)

        lay.addStretch()
        self.lbl_icon = QLabel()
        self.lbl_icon.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(16, 16))
        self.lbl_icon.setStyleSheet("background: transparent; border: none;")
        lay.addWidget(self.lbl_icon)

        self.lbl_text = QLabel(text)
        self.lbl_text.setStyleSheet(
            f"color: {text_color}; font-size: 10pt; font-weight: 500; background: transparent; border: none;"
        )
        lay.addWidget(self.lbl_text)
        lay.addStretch()

    def _apply_style(self):
        self.setStyleSheet(_MENU_ITEM_HIGHLIGHT if self._highlighted else _MENU_ITEM_NORMAL)

    def set_highlighted(self, highlighted: bool):
        self._highlighted = highlighted
        self._apply_style()

    def enterEvent(self, event):
        self._highlighted = True
        self._apply_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._highlighted = False
        self._apply_style()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Trigger langsung dari custom widget saat diklik
            self.action_ref.trigger()

            # Jika punya parent menu (seperti tray_menu), segera tutup setelah klik!
            if hasattr(self.action_ref, "parent_menu") and self.action_ref.parent_menu:
                self.action_ref.parent_menu.close()
        super().mouseReleaseEvent(event)


class AccessibleCenteredMenu(QMenu):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Cegah "kebocoran" sudut: window popup QMenu sebenarnya persegi dan
        # opaque, sehingga area di luar lengkungan border-radius menampilkan
        # background default. Dengan background translucent + tanpa frame/shadow
        # native, sudut di luar radius menjadi benar-benar transparan.
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.hovered.connect(self._on_action_hovered)
        self.aboutToHide.connect(self._reset_highlights)

    def _on_action_hovered(self, action):
        for act in self.actions():
            if isinstance(act, CenteredMenuAction):
                act.set_highlighted(act == action)

    def _reset_highlights(self):
        for act in self.actions():
            if isinstance(act, CenteredMenuAction):
                act.set_highlighted(False)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            active = self.activeAction()
            if active:
                active.trigger()
                self.close()
                event.accept()
                return
        super().keyPressEvent(event)


class CenteredMenuAction(QWidgetAction):
    def __init__(self, text, icon_name, icon_color=None, text_color=None, parent=None):
        super().__init__(parent)
        # Default bertema (token diresolusi saat import): ikon muted, teks utama —
        # putih murni dulu tak terbaca di menu putih (tema light).
        icon_color = icon_color if icon_color is not None else CLR_TEXT_DIM
        text_color = text_color if text_color is not None else CLR_TEXT_MAIN
        self.parent_menu = parent
        self.w = HoverMenuWidget(text, icon_name, icon_color, text_color, self, parent)
        self.setDefaultWidget(self.w)
        # Teks pada QAction-nya sendiri (selain label di custom widget) agar
        # screen reader mengumumkan nama item — tanpa ini item terbaca kosong.
        self.setText(text)

    def set_text(self, text: str) -> None:
        """Perbarui label menu (dipakai saat ganti bahasa)."""
        self.w.lbl_text.setText(text)
        self.setText(text)  # jaga nama aksesibilitas tetap sinkron

    def set_highlighted(self, highlighted: bool):
        self.w.set_highlighted(highlighted)
        self.w.setStyleSheet(_MENU_ITEM_HIGHLIGHT if highlighted else _MENU_ITEM_NORMAL)
