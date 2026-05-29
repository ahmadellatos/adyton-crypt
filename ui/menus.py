"""
Modul: menus.py
Deskripsi: Komponen menu kustom (Centered menu dengan icon dan highlight).
"""

import qtawesome as qta
from PySide6.QtWidgets import (
    QProxyStyle,
    QStyle,
    QMenu,
    QWidgetAction,
    QWidget,
    QHBoxLayout,
    QLabel,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


class CenteredMenuStyle(QProxyStyle):
    def drawControl(self, element, option, painter, widget=None):
        if element == QStyle.ControlElement.CE_MenuItem:
            option.displayAlignment = Qt.AlignmentFlag.AlignCenter
            # Gambar background highlight manual saat item selected/fokus
            if option.state & QStyle.StateFlag.State_Selected:
                painter.fillRect(option.rect, QColor("#181F32"))
        super().drawControl(element, option, painter, widget)


class HoverMenuWidget(QWidget):
    def __init__(
        self, text, icon_name, icon_color, text_color, action_ref, parent=None
    ):
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
        if self._highlighted:
            self.setStyleSheet(
                "QWidget#CenteredMenuItem { background-color: #181F32; border-radius: 4px; }"
            )
        else:
            self.setStyleSheet(
                "QWidget#CenteredMenuItem { background-color: transparent; border-radius: 4px; }"
            )

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
    def __init__(
        self, text, icon_name, icon_color="white", text_color="white", parent=None
    ):
        super().__init__(parent)
        self.parent_menu = parent
        self.w = HoverMenuWidget(text, icon_name, icon_color, text_color, self, parent)
        self.setDefaultWidget(self.w)

    def set_highlighted(self, highlighted: bool):
        self.w.set_highlighted(highlighted)
        if highlighted:
            self.w.setStyleSheet(
                "QWidget#CenteredMenuItem { background-color: #181F32; border-radius: 4px; }"
            )
        else:
            self.w.setStyleSheet(
                "QWidget#CenteredMenuItem { background-color: transparent; border-radius: 4px; }"
            )
