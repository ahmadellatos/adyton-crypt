"""
Modul: widgets.py
Deskripsi: Kumpulan komponen UI (Widget) kustom.
           Diperbarui: Fix efek Hover dan Click pada CenteredMenuAction.

Catatan: CryptoWorker telah dipindah ke core/worker.py karena merupakan
         business logic threading, bukan UI component.
"""

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget,
    QFrame,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QGraphicsDropShadowEffect,
    QPushButton,
    QDialog,
    QProxyStyle,
    QStyle,
    QSizePolicy,
    QWidgetAction,
    QMenu,
)
from PySide6.QtCore import (
    Qt,
    QPropertyAnimation,
    QEasingCurve,
    QTimer,
    QSize,
    QPoint,
)
from PySide6.QtGui import QColor, QCursor

from .styles import CLR_INNER, CLR_BORDER


def apply_shadow(widget, blur_radius=20, y_offset=6, opacity=60):
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(blur_radius)
    shadow.setXOffset(0)
    shadow.setYOffset(y_offset)
    shadow.setColor(QColor(0, 0, 0, opacity))
    widget.setGraphicsEffect(shadow)


# ── HERO ICON WIDGET (FOLDER GLOWING) ───────────────────────────────
class HeroIconWidget(QWidget):
    def __init__(self, mode="kunci", parent=None):
        super().__init__(parent)
        self.setFixedSize(160, 110)

        sparkles = [
            (30, 15, 14, "#4A90E2"),
            (10, 40, 10, "#4A90E2"),
            (125, 35, 14, "#4A90E2"),
            (140, 65, 10, "#4A90E2"),
        ]

        for x, y, sz, col in sparkles:
            lbl = QLabel(self)
            lbl.setPixmap(qta.icon("mdi6.star-four-points", color=col).pixmap(sz, sz))
            lbl.setGeometry(x, y, sz, sz)
            glow = QGraphicsDropShadowEffect(self)
            glow.setBlurRadius(15)
            glow.setColor(QColor(col))
            glow.setXOffset(0)
            glow.setYOffset(0)
            lbl.setGraphicsEffect(glow)

        lbl_folder = QLabel(self)
        lbl_folder.setPixmap(qta.icon("mdi6.folder", color="#2A344A").pixmap(90, 90))
        lbl_folder.setGeometry(35, 10, 90, 90)
        lbl_folder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_overlay = QLabel(self)
        icon_name = "mdi6.shield-lock" if mode == "kunci" else "mdi6.shield-key"

        lbl_overlay.setPixmap(qta.icon(icon_name, color="#00D2C8").pixmap(36, 36))
        lbl_overlay.setGeometry(62, 42, 36, 36)
        lbl_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        glow_overlay = QGraphicsDropShadowEffect(self)
        glow_overlay.setBlurRadius(25)
        glow_overlay.setColor(QColor("#00D2C8"))
        glow_overlay.setXOffset(0)
        glow_overlay.setYOffset(0)
        lbl_overlay.setGraphicsEffect(glow_overlay)


# ── CUSTOM TOOLTIP ──────────────────────────────────────────────────
class CustomToolTip(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)

        self.setStyleSheet("""
            QLabel {
                background-color: #111625;
                color: #FFFFFF;
                border: 1px solid #232B3E;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 9pt;
            }
        """)
        self.hide()

        # Timer tunggal untuk polling pergerakan mouse setiap 50ms
        self._monitor_timer = QTimer(self)
        self._monitor_timer.setInterval(50)
        self._monitor_timer.timeout.connect(self._check_mouse_state)

        self._pending_text = ""
        self._last_cursor_pos = QPoint()
        self._time_hovered = 0

        # Standar durasi UX OS Native
        self._show_delay_ms = 1000  # Nongol setelah mouse diam 1 detik
        self._hide_delay_ms = 5000  # Hilang otomatis setelah 5 detik (jika tidak gerak)

    def request_show(self, text):
        self._pending_text = text
        self._last_cursor_pos = QCursor.pos()
        self._time_hovered = 0
        self._monitor_timer.start()

    def _check_mouse_state(self):
        current_pos = QCursor.pos()

        # Hitung jarak pergerakan mouse dari posisi terakhir (Toleransi 5 pixel/anti-jitter)
        diff = current_pos - self._last_cursor_pos
        distance_sq = diff.x() ** 2 + diff.y() ** 2

        if distance_sq > 25:  # Jika mouse bergerak lebih dari ~5 px
            self._last_cursor_pos = current_pos
            self._time_hovered = 0  # Reset timer!
            if self.isVisible():
                self.hide()  # Langsung sembunyikan jika user gerak
        else:
            # Jika mouse terpantau diam, teruskan hitungan
            self._time_hovered += 50

            # Waktunya tampilkan
            if self._time_hovered == self._show_delay_ms and not self.isVisible():
                self._do_show()
            # Waktunya autohide (expired)
            elif (
                self._time_hovered >= (self._show_delay_ms + self._hide_delay_ms)
                and self.isVisible()
            ):
                self.hide_tooltip()

    def _do_show(self):
        self.setText(self._pending_text)
        self.adjustSize()
        pos = QCursor.pos()
        # Offset biar gak nutupin kursor
        self.move(pos.x() + 15, pos.y() + 15)
        self.show()

    def hide_tooltip(self):
        self._monitor_timer.stop()
        self.hide()


# ── ELIDED LABEL (Pemotong Teks ...) ────────────────────────────────
class ElidedLabel(QLabel):
    def __init__(self, text="", mode=Qt.TextElideMode.ElideMiddle, parent=None):
        super().__init__(text, parent)
        self._full_text = text
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(10)

    def setText(self, text):
        self._full_text = text
        self._update_elided_text()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elided_text()

    def _update_elided_text(self):
        metrics = self.fontMetrics()
        elided = metrics.elidedText(
            self._full_text, self._mode, max(10, self.width() - 5)
        )
        if self.text() != elided:
            super().setText(elided)

    def minimumSizeHint(self):
        return QSize(10, super().minimumSizeHint().height())

    def sizeHint(self):
        return QSize(50, super().sizeHint().height())


# ── MESSAGE BOX MODERN ──────────────────────────────────────────────
class ModernMessageBox(QDialog):
    def __init__(
        self, title, message, icon_name="mdi6.alert", icon_color="#F39C12", parent=None
    ):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(420)

        container = QFrame(self)
        container.setObjectName("Card")
        apply_shadow(container, blur_radius=30, y_offset=8, opacity=60)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(15)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-weight: 800; font-size: 12pt; color: white;")
        layout.addWidget(lbl_title)

        content_lay = QHBoxLayout()
        content_lay.setSpacing(15)

        lbl_icon = QLabel()
        lbl_icon.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(36, 36))
        content_lay.addWidget(lbl_icon, alignment=Qt.AlignmentFlag.AlignTop)

        lbl_msg = QLabel(message)
        lbl_msg.setWordWrap(True)
        lbl_msg.setStyleSheet("color: #8B95A5; font-size: 10pt; line-height: 1.4;")
        content_lay.addWidget(lbl_msg, 1)

        layout.addLayout(content_lay)
        layout.addSpacing(10)

        btn_lay = QHBoxLayout()
        btn_lay.setSpacing(12)
        btn_lay.addStretch()

        self.btn_cancel = QPushButton("Batal")
        self.btn_cancel.setFixedSize(90, 36)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_yes = QPushButton("Lanjutkan")
        self.btn_yes.setFixedSize(110, 36)
        self.btn_yes.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_yes.setStyleSheet("""
            QPushButton { 
                background-color: #E74C3C; 
                color: white; 
                border: 2px solid transparent; 
                border-radius: 8px; 
                font-weight: bold; 
            }
            QPushButton:hover { 
                background-color: #C0392B; 
            }
            QPushButton:focus { 
                border: 2px solid #FFFFFF; 
                background-color: #C0392B; 
            }
        """)
        self.btn_yes.clicked.connect(self.accept)

        btn_lay.addWidget(self.btn_cancel)
        btn_lay.addWidget(self.btn_yes)
        layout.addLayout(btn_lay)

        self.btn_yes.setDefault(True)
        self.btn_yes.setAutoDefault(True)
        self.btn_cancel.setAutoDefault(True)

        if parent:
            self.adjustSize()
            parent_center = parent.mapToGlobal(parent.rect().center())
            self.move(parent_center - self.rect().center())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)


# ── TITLE BAR BUTTON (DINAMIS & HOVER EFEK) ─────────────────────────
class TitleBarButton(QPushButton):
    def __init__(self, icon_name: str, hover_bg_color: str, parent=None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.hover_bg = hover_bg_color
        self.setFixedSize(40, 32)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setIcon(qta.icon(self.icon_name, color="#8B95A5"))
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 0;
            }}
            QPushButton:hover {{
                background-color: {self.hover_bg};
            }}
        """)

    def enterEvent(self, event):
        self.setIcon(qta.icon(self.icon_name, color="#FFFFFF"))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(qta.icon(self.icon_name, color="#8B95A5"))
        super().leaveEvent(event)

    def change_icon(self, new_icon_name: str):
        self.icon_name = new_icon_name
        current_color = "#FFFFFF" if self.underMouse() else "#8B95A5"
        self.setIcon(qta.icon(self.icon_name, color=current_color))


# ── TITLE BAR CUSTOM ────────────────────────────────────────────────
class CustomTitleBar(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_window = parent
        self.setFixedHeight(32)
        self.setStyleSheet("background-color: #0B101E;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(15, 0, 0, 0)
        lay.setSpacing(10)

        self.lbl_icon = QLabel()
        self.lbl_icon.setPixmap(qta.icon("mdi6.lock", color="#00D2C8").pixmap(14, 14))

        lbl_title = QLabel("Digital Locker — Professional")
        lbl_title.setStyleSheet("color: #8B95A5; font-size: 9pt;")

        lay.addWidget(self.lbl_icon)
        lay.addWidget(lbl_title)
        lay.addStretch()

        control_lay = QHBoxLayout()
        control_lay.setContentsMargins(0, 0, 0, 0)
        control_lay.setSpacing(0)

        self.btn_min = TitleBarButton("mdi6.minus", "#232B3E", self)
        self.btn_min.clicked.connect(self.parent_window.showMinimized)

        self.btn_max = TitleBarButton("mdi6.window-maximize", "#232B3E", self)
        self.btn_max.clicked.connect(self._toggle_maximize)

        self.btn_close = TitleBarButton("mdi6.close", "#E74C3C", self)
        self.btn_close.clicked.connect(self.parent_window.close)

        control_lay.addWidget(self.btn_min)
        control_lay.addWidget(self.btn_max)
        control_lay.addWidget(self.btn_close)

        lay.addLayout(control_lay)

    def _toggle_maximize(self):
        if self.parent_window.isMaximized():
            self.parent_window.showNormal()
            self.btn_max.change_icon("mdi6.window-maximize")
        else:
            self.parent_window.showMaximized()
            self.btn_max.change_icon("mdi6.window-restore")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.parent_window.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()


# ── WIDGET LAINNYA ──────────────────────────────────────────────────
class BigActionBtn(QPushButton):
    def __init__(self, title, subtitle, icon_name="mdi6.lock", parent=None):
        super().__init__(parent)
        self.setObjectName("BtnAksiBesar")
        self.setFixedHeight(75)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.icon_name = icon_name

        lay = QHBoxLayout(self)
        lay.setContentsMargins(25, 10, 25, 10)

        self.lbl_icon = QLabel()
        self.lbl_icon.setPixmap(qta.icon(self.icon_name, color="white").pixmap(32, 32))

        v_lay = QVBoxLayout()
        v_lay.setSpacing(2)
        v_lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("font-size: 13pt; font-weight: 800; color: white;")

        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setStyleSheet("font-size: 9pt; color: rgba(255, 255, 255, 0.75);")

        v_lay.addWidget(self.lbl_title)
        v_lay.addWidget(self.lbl_sub)

        self.lbl_arrow = QLabel()
        self.lbl_arrow.setPixmap(
            qta.icon("mdi6.chevron-right", color="white").pixmap(24, 24)
        )

        lay.addWidget(self.lbl_icon)
        lay.addSpacing(15)
        lay.addLayout(v_lay)
        lay.addStretch()
        lay.addWidget(self.lbl_arrow)

    def setEnabled(self, val):
        super().setEnabled(val)
        opacity = "1.0" if val else "0.3"
        color_val = "white" if val else "rgba(255,255,255,0.3)"

        self.lbl_icon.setPixmap(
            qta.icon(self.icon_name, color=color_val).pixmap(32, 32)
        )
        self.lbl_arrow.setPixmap(
            qta.icon("mdi6.chevron-right", color=color_val).pixmap(24, 24)
        )

        self.lbl_title.setStyleSheet(
            f"font-size: 13pt; font-weight: 800; color: rgba(255,255,255,{opacity});"
        )
        self.lbl_sub.setStyleSheet(
            f"font-size: 9pt; color: rgba(255,255,255,{float(opacity)*0.75});"
        )

    def setTextLabels(self, title, subtitle=""):
        self.lbl_title.setText(title)
        self.lbl_sub.setText(subtitle)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
            event.accept()
        else:
            super().keyPressEvent(event)


class AnimatedNotifBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NotifBar")
        self.setMinimumWidth(280)
        self.setMaximumWidth(500)
        self.setMinimumHeight(55)
        self.setStyleSheet("background-color: transparent; border-radius: 8px;")

        apply_shadow(self, blur_radius=30, y_offset=10, opacity=60)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(12)

        self.lbl_icon = QLabel()
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_text = QLabel("")
        self.lbl_text.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        self.lbl_text.setWordWrap(True)

        self.btn_close = QPushButton()
        self.btn_close.setIcon(
            qta.icon("mdi6.close", color="#8B95A5", color_active="white")
        )
        self.btn_close.setIconSize(QSize(18, 18))
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setStyleSheet("background: transparent; border: none;")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.hide_msg)

        layout.addWidget(self.lbl_icon)
        layout.addWidget(self.lbl_text, 1)
        layout.addWidget(self.btn_close, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(400)
        self.anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self.anim.finished.connect(self._on_anim_finished)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide_msg)

        self.hide()

    def showEvent(self, event):
        super().showEvent(event)
        parent = self.parentWidget()
        if parent:
            parent.removeEventFilter(self)
            parent.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj == self.parentWidget() and event.type() == event.Type.Resize:
            if self.isVisible() and self.pos().y() >= 0:
                target_x = self.parentWidget().width() - self.width() - 20
                self.move(target_x, self.pos().y())
        return super().eventFilter(obj, event)

    def _on_anim_finished(self):
        if self.pos().y() < 0:
            self.hide()

    def show_msg(self, kind: str, msg: str, auto_hide_ms: int = 4000):
        self.timer.stop()
        self.anim.stop()

        bg_color = (
            "#0D2B1E" if kind == "ok" else ("#2B0D0D" if kind == "err" else "#2B1E0D")
        )
        fg_color = (
            "#00D2C8" if kind == "ok" else ("#E74C3C" if kind == "err" else "#F39C12")
        )
        icon_name = (
            "mdi6.check-circle"
            if kind == "ok"
            else ("mdi6.close-circle" if kind == "err" else "mdi6.alert-circle")
        )

        self.setStyleSheet(
            f"QFrame#NotifBar {{ background-color: {bg_color}; border-radius: 8px; border: none; }}"
            f"QLabel {{ border: none; background: transparent; color: {fg_color}; font-weight: bold; font-size: 10pt; }}"
        )
        self.lbl_icon.setPixmap(qta.icon(icon_name, color=fg_color).pixmap(24, 24))
        self.lbl_text.setStyleSheet(
            f"color: {fg_color}; font-weight: bold; font-size: 10pt;"
        )
        self.lbl_text.setText(msg)

        self.raise_()
        self.adjustSize()
        self.show()

        if self.parentWidget():
            p_rect = self.parentWidget().rect()
            target_x = p_rect.width() - self.width() - 20
            target_y = 20
            start_y = -self.minimumHeight() - 20
        else:
            target_x = 20
            target_y = 20
            start_y = -100

        if not self.isVisible() or self.pos().y() < 0:
            self.anim.setStartValue(QPoint(target_x, start_y))
        else:
            self.anim.setStartValue(self.pos())

        self.anim.setEndValue(QPoint(target_x, target_y))
        self.anim.start()

        if auto_hide_ms > 0:
            self.timer.start(auto_hide_ms)

    def hide_msg(self):
        self.timer.stop()
        if not self.isVisible() or self.pos().y() < 0:
            return

        if self.parentWidget():
            target_x = self.pos().x()
            target_y = -self.minimumHeight() - 20
        else:
            target_x = 20
            target_y = -100

        self.anim.stop()
        self.anim.setStartValue(self.pos())
        self.anim.setEndValue(QPoint(target_x, target_y))
        self.anim.start()


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
        # TAMBAH METHOD INI
        self._highlighted = highlighted
        self._apply_style()

    def enterEvent(self, event):
        self._highlighted = True  # UBAH: pakai flag, bukan langsung setStyleSheet
        self._apply_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._highlighted = False  # UBAH: pakai flag
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


class ClearButton(QPushButton):
    """
    Tombol silang (X) destruktif dengan efek hover.
    Otomatis mengubah background jadi merah dan ikon jadi putih saat di-hover.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(32, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setIcon(qta.icon("mdi6.close", color="#8B95A5"))
        self.setIconSize(QSize(20, 20))

        self.setStyleSheet("""
            QPushButton { background: transparent; border: none; }
            QPushButton:hover { background: #E74C3C; border-radius: 4px; }
            QPushButton:focus { border: 2px solid #00D2C8; background: #232B3E; border-radius: 4px; }
        """)

    def enterEvent(self, event):
        # Ubah ikon jadi putih saat mouse masuk (hover)
        self.setIcon(qta.icon("mdi6.close", color="#FFFFFF"))
        super().enterEvent(event)

    def leaveEvent(self, event):
        # Kembalikan ikon jadi abu-abu saat mouse keluar
        self.setIcon(qta.icon("mdi6.close", color="#8B95A5"))
        super().leaveEvent(event)


# ── INTEGRATED TAMBAH & CLEAR SPLIT BUTTON ───────────────────────────
class TambahClearSplitButton(QFrame):
    """
    Custom Split Button terintegrasi: "[+] Tambah | [Trashcan]"
    Otomatis dapet focus ring cyan terpadu dan hover efek destruktif merah di area trashcan.
    """

    def __init__(self, menu, clear_callback, parent=None):
        super().__init__(parent)
        self.setObjectName("SplitActionFrame")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Fokus diatur oleh tombol anak

        self.setStyleSheet("""
            QFrame#SplitActionFrame {
                background-color: transparent;
                border: 1px solid #232B3E;
                border-radius: 8px;
            }
            QFrame#SplitActionFrame[focused="true"] {
                border: 2px solid #00D2C8;
            }
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 1. Bagian Kiri: Tombol Tambah
        self.btn_add = QPushButton()
        self.btn_add.setText(" Tambah")
        self.btn_add.setIcon(qta.icon("mdi6.plus", color="#8B95A5"))
        self.btn_add.setMenu(menu)
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_add.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #8B95A5;
                font-size: 10pt;
                font-weight: 600;
                padding-left: 12px;
                padding-right: 12px;
                height: 34px;
            }
            QPushButton:hover { color: white; }
            QPushButton::menu-indicator { image: none; width: 0px; }
        """)

        # 2. Bagian Tengah: Garis Pembatas Pemisah (Separator |)
        self.sep = QFrame()
        self.sep.setFixedWidth(1)
        self.sep.setStyleSheet("background-color: #232B3E;")

        # 3. Bagian Kanan: Tombol Trashcan (Clear All)
        self.btn_clear = QPushButton()
        self.btn_clear.setIcon(qta.icon("mdi6.trash-can-outline", color="#8B95A5"))
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_clear.setFixedWidth(38)
        self.btn_clear.clicked.connect(clear_callback)
        self.btn_clear.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                height: 34px;
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                border-top-right-radius: 7px;
                border-bottom-right-radius: 7px;
            }
            QPushButton:hover {
                background-color: #E74C3C;
            }
        """)

        lay.addWidget(self.btn_add, 1)
        lay.addWidget(self.sep)
        lay.addWidget(self.btn_clear)

        # Daftarkan ke filter internal untuk mengontrol efek focus ring dan ikon
        self.btn_add.installEventFilter(self)
        self.btn_clear.installEventFilter(self)

    def set_clear_visible(self, visible: bool):
        """Mengatur tampilan tombol secara dinamis berdasarkan isi file list"""
        self.sep.setVisible(visible)
        self.btn_clear.setVisible(visible)
        if visible:
            self.setFixedSize(145, 36)
        else:
            self.setFixedSize(100, 36)

    def eventFilter(self, obj, event):
        # Kelola focus ring terpadu pada parent border (QFrame)
        if event.type() in (event.Type.FocusIn, event.Type.FocusOut):
            has_focus = self.btn_add.hasFocus() or (
                self.btn_clear.isVisible() and self.btn_clear.hasFocus()
            )
            self.setProperty("focused", has_focus)
            self.style().unpolish(self)
            self.style().polish(self)

        # Efek ikon menyala putih saat disorot khusus area trashcan
        elif event.type() == event.Type.Enter:
            if obj == self.btn_clear:
                self.btn_clear.setIcon(
                    qta.icon("mdi6.trash-can-outline", color="#FFFFFF")
                )
        elif event.type() == event.Type.Leave:
            if obj == self.btn_clear:
                self.btn_clear.setIcon(
                    qta.icon("mdi6.trash-can-outline", color="#8B95A5")
                )

        # Dukungan a11y keyboard khusus tombol trashcan
        elif event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                if obj == self.btn_clear:
                    self.btn_clear.click()
                    return True

        return super().eventFilter(obj, event)
