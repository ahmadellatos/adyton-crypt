"""
Modul: widgets.py
Deskripsi: Berisi kumpulan komponen UI (Widget) kustom.
           Sudah dioptimasi sesuai review (MouseRelease, Resize Event, Safe Worker).
"""

import inspect
import qtawesome as qta
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QGraphicsDropShadowEffect,
    QPushButton,
    QDialog,
)
from PySide6.QtCore import (
    Qt,
    QThread,
    Signal,
    QPropertyAnimation,
    QEasingCurve,
    QTimer,
    QSize,
    QPoint,
)
from PySide6.QtGui import QColor

from .styles import CLR_INNER, CLR_BORDER


def apply_shadow(widget, blur_radius=20, y_offset=6, opacity=60):
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(blur_radius)
    shadow.setXOffset(0)
    shadow.setYOffset(y_offset)
    shadow.setColor(QColor(0, 0, 0, opacity))
    widget.setGraphicsEffect(shadow)


class ModernMessageBox(QDialog):
    """Custom Dialog berdesain modern untuk menggantikan QMessageBox OS."""

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
            QPushButton { background-color: #E74C3C; color: white; border: none; border-radius: 8px; font-weight: bold; }
            QPushButton:hover { background-color: #C0392B; }
        """)
        self.btn_yes.clicked.connect(self.accept)

        btn_lay.addWidget(self.btn_cancel)
        btn_lay.addWidget(self.btn_yes)
        layout.addLayout(btn_lay)


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

        self.btn_min = QPushButton()
        self.btn_min.setIcon(qta.icon("mdi6.minus", color="#8B95A5"))
        self.btn_min.setObjectName("BtnGhost")
        self.btn_min.setFixedSize(40, 32)
        self.btn_min.clicked.connect(self.parent_window.showMinimized)

        self.btn_max = QPushButton()
        self.btn_max.setIcon(qta.icon("mdi6.window-maximize", color="#8B95A5"))
        self.btn_max.setObjectName("BtnGhost")
        self.btn_max.setFixedSize(40, 32)
        self.btn_max.clicked.connect(self._toggle_maximize)

        self.btn_close = QPushButton()
        self.btn_close.setIcon(
            qta.icon("mdi6.close", color="#8B95A5", color_active="white")
        )
        self.btn_close.setObjectName("BtnGhost")
        self.btn_close.setFixedSize(40, 32)
        self.btn_close.setStyleSheet(
            "QPushButton#BtnGhost:hover { background-color: #E74C3C; border-radius: 0; }"
        )
        self.btn_close.clicked.connect(self.parent_window.close)

        lay.addWidget(self.btn_min)
        lay.addWidget(self.btn_max)
        lay.addWidget(self.btn_close)

    def _toggle_maximize(self):
        if self.parent_window.isMaximized():
            self.parent_window.showNormal()
            self.btn_max.setIcon(qta.icon("mdi6.window-maximize", color="#8B95A5"))
        else:
            self.parent_window.showMaximized()
            self.btn_max.setIcon(qta.icon("mdi6.window-restore", color="#8B95A5"))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if hasattr(self, "drag_pos"):
            delta = event.globalPosition().toPoint() - self.drag_pos
            self.parent_window.move(self.parent_window.pos() + delta)
            self.drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        """FIX: Membersihkan state drag_pos agar window tidak melompat tak sengaja."""
        if hasattr(self, "drag_pos"):
            del self.drag_pos


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


class CryptoWorker(QThread):
    progress = Signal(float)
    finished = Signal(tuple)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self._is_cancelled = False  # Status pembatalan

    def cancel(self):
        """Meminta worker untuk berhenti."""
        self._is_cancelled = True

    def run(self):
        try:
            # FIX: Cek apakah fungsi di vault.py nerima 'is_cancelled' pakai inspect
            # Jadi aplikasinya nggak akan crash meskipun file vault.py belum lu update!
            sig = inspect.signature(self.func)
            if "is_cancelled" in sig.parameters:
                self.kwargs["is_cancelled"] = lambda: self._is_cancelled

            self.kwargs["progress_cb"] = lambda val: self.progress.emit(val)
            result = self.func(*self.args, **self.kwargs)

            if self._is_cancelled:
                self.finished.emit((False, "Operasi dibatalkan oleh pengguna."))
            else:
                self.finished.emit(result if isinstance(result, tuple) else (result,))
        except Exception as e:
            self.finished.emit((False, str(e)))


class AnimatedNotifBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(380)
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
        layout.addWidget(self.btn_close, alignment=Qt.AlignmentFlag.AlignTop)

        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(400)
        self.anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self.anim.finished.connect(self._on_anim_finished)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide_msg)

        # FIX: Mendaftarkan notifikasi ke event window resize
        if self.parentWidget():
            self.parentWidget().installEventFilter(self)

        self.hide()

    def eventFilter(self, obj, event):
        """Memastikan posisi notifikasi tetap nempel di kanan atas pas di-resize."""
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
            f"background-color: {bg_color}; border-radius: 8px; border: 1px solid {CLR_BORDER};"
        )
        self.lbl_icon.setPixmap(qta.icon(icon_name, color=fg_color).pixmap(24, 24))
        self.lbl_text.setStyleSheet(
            f"color: {fg_color}; font-weight: bold; font-size: 10pt;"
        )
        self.lbl_text.setText(msg)

        self.raise_()
        self.show()

        if self.parentWidget():
            p_rect = self.parentWidget().rect()
            target_x = p_rect.width() - self.width() - 20
            target_y = 20
            start_y = -self.height() - 20
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
            target_y = -self.height() - 20
        else:
            target_x = 20
            target_y = -100

        self.anim.stop()
        self.anim.setStartValue(self.pos())
        self.anim.setEndValue(QPoint(target_x, target_y))
        self.anim.start()
