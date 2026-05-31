"""
Modul: widgets.py
Deskripsi: Kumpulan komponen UI (Widget) kustom yang reusable.
"""

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget,
    QFrame,
    QLabel,
    QHBoxLayout,
    QGraphicsDropShadowEffect,
    QPushButton,
    QSizePolicy,
    QLineEdit,
)
from PySide6.QtCore import (
    Qt,
    QPropertyAnimation,
    QEasingCurve,
    QTimer,
    QSize,
    QPoint,
    Signal,
)
from PySide6.QtGui import QColor, QCursor, QPixmap

from core.paths import get_asset_path

from .styles import CLR_TEXT_MUTED, CLR_ACCENT
from .utils import apply_shadow




# ── HERO ICON WIDGET (FOLDER GLOWING) ───────────────────────────────
class HeroIconWidget(QWidget):
    def __init__(self, mode="kunci", parent=None):
        super().__init__(parent)
        self.setFixedSize(160, 110)

        self._sparkle_glows = []
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
            self._sparkle_glows.append(glow)

        lbl_folder = QLabel(self)
        lbl_folder.setPixmap(qta.icon("mdi6.folder", color="#2A344A").pixmap(90, 90))
        lbl_folder.setGeometry(35, 10, 90, 90)
        lbl_folder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_overlay = QLabel(self)
        icon_name = "mdi6.shield-lock" if mode == "kunci" else "mdi6.shield-key"

        self._overlay_icon_name = icon_name
        lbl_overlay.setPixmap(qta.icon(icon_name, color="#00D2C8").pixmap(36, 36))
        lbl_overlay.setGeometry(62, 42, 36, 36)
        lbl_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._overlay_icon = lbl_overlay
        self._glow_overlay = QGraphicsDropShadowEffect(self)
        self._glow_overlay.setBlurRadius(25)
        self._glow_overlay.setColor(QColor("#00D2C8"))
        self._glow_overlay.setXOffset(0)
        self._glow_overlay.setYOffset(0)
        lbl_overlay.setGraphicsEffect(self._glow_overlay)

    def set_drag_active(self, active: bool):
        """Intensify the icon glow when drag is active over the drop area."""
        if active:
            # Main shield icon - EXTREMELY bright + brighter base icon
            if hasattr(self, "_glow_overlay") and self._glow_overlay:
                self._glow_overlay.setBlurRadius(75)
                self._glow_overlay.setColor(QColor(200, 255, 255, 255))

            if hasattr(self, "_overlay_icon") and hasattr(self, "_overlay_icon_name"):
                self._overlay_icon.setPixmap(
                    qta.icon(self._overlay_icon_name, color="#7FFFFF").pixmap(36, 36)
                )

            # Sparkles - very bright and large
            for glow in getattr(self, "_sparkle_glows", []):
                glow.setBlurRadius(40)
                glow.setColor(QColor(230, 255, 255, 255))

            self.update()
        else:
            # Return to normal
            if hasattr(self, "_glow_overlay") and self._glow_overlay:
                self._glow_overlay.setBlurRadius(25)
                self._glow_overlay.setColor(QColor("#00D2C8"))

            if hasattr(self, "_overlay_icon") and hasattr(self, "_overlay_icon_name"):
                self._overlay_icon.setPixmap(
                    qta.icon(self._overlay_icon_name, color="#00D2C8").pixmap(36, 36)
                )

            for glow in getattr(self, "_sparkle_glows", []):
                glow.setBlurRadius(15)
                glow.setColor(QColor("#4A90E2"))

            self.update()


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
        pixmap = QPixmap(get_asset_path("assets/icon_adyton.png"))
        self.lbl_icon.setPixmap(
            pixmap.scaled(
                16,
                16,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

        # Judul bersih
        lbl_title = QLabel("Adyton Crypt")
        lbl_title.setObjectName("MutedText")

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
            f"QLabel {{ border: none; background: transparent; color: {fg_color}; font-weight: 600; font-size: 10pt; }}"
        )
        self.lbl_icon.setPixmap(qta.icon(icon_name, color=fg_color).pixmap(24, 24))
        self.lbl_text.setStyleSheet(
            f"color: {fg_color}; font-weight: 600; font-size: 10pt;"
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


# ── PASSWORD LINE EDIT WITH TOGGLE ────────────────────────────────
class PasswordLineEdit(QFrame):
    """
    Reusable password input field with eye toggle button.
    Provides consistent look and behavior across the app.
    """

    textChanged = Signal(str)

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)

        self.setObjectName("InputBox")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 6, 0)
        lay.setSpacing(0)

        self.line_edit = QLineEdit()
        self.line_edit.setObjectName("InputInside")
        self.line_edit.setFixedHeight(45)
        self.line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        if placeholder:
            self.line_edit.setPlaceholderText(placeholder)
        self.line_edit.textChanged.connect(self.textChanged)
        lay.addWidget(self.line_edit)

        self.btn_toggle = QPushButton()
        self.btn_toggle.setIcon(qta.icon("mdi6.eye-outline", color=CLR_TEXT_MUTED))
        self.btn_toggle.setIconSize(QSize(22, 22))
        self.btn_toggle.setObjectName("BtnEye")
        self.btn_toggle.setFixedSize(44, 45)
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.clicked.connect(self._toggle_visibility)
        lay.addWidget(self.btn_toggle)

        # Store reference to styles (imported at top level)
        self._muted_color = CLR_TEXT_MUTED
        self._accent_color = CLR_ACCENT

    def _toggle_visibility(self):
        if self.line_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle.setIcon(qta.icon("mdi6.eye-off-outline", color=self._accent_color))
        else:
            self.line_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle.setIcon(qta.icon("mdi6.eye-outline", color=self._muted_color))

    # --- Public API ---
    def text(self) -> str:
        return self.line_edit.text()

    def setText(self, text: str):
        self.line_edit.setText(text)

    def setPlaceholderText(self, text: str):
        self.line_edit.setPlaceholderText(text)

    def setAccessibleName(self, name: str):
        self.line_edit.setAccessibleName(name)

    def clear(self):
        self.line_edit.clear()
        self.setEchoMode(QLineEdit.EchoMode.Password)

    def setEnabled(self, enabled: bool):
        self.line_edit.setEnabled(enabled)
        self.btn_toggle.setEnabled(enabled)

    def installEventFilter(self, obj):
        self.line_edit.installEventFilter(obj)
        self.btn_toggle.installEventFilter(obj)

    # --- Echo mode control (public API) ---
    def setEchoMode(self, mode):
        self.line_edit.setEchoMode(mode)
        self._update_toggle_icon()

    def echoMode(self):
        return self.line_edit.echoMode()

    def _update_toggle_icon(self):
        if self.line_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.btn_toggle.setIcon(qta.icon("mdi6.eye-outline", color=self._muted_color))
        else:
            self.btn_toggle.setIcon(qta.icon("mdi6.eye-off-outline", color=self._accent_color))

    # Forward common signals
    @property
    def returnPressed(self):
        return self.line_edit.returnPressed
