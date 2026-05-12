"""
ui/widgets.py
Membuat Custom Title Bar, Shadow, dan Tombol Vektor raksasa.
"""

from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QGraphicsDropShadowEffect,
    QPushButton,
)
from PySide6.QtCore import Qt, QThread, Signal, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QColor

from .styles import CLR_INNER, CLR_BORDER


def apply_shadow(widget, blur_radius=20, y_offset=6, opacity=60):
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(blur_radius)
    shadow.setXOffset(0)
    shadow.setYOffset(y_offset)
    shadow.setColor(QColor(0, 0, 0, opacity))
    widget.setGraphicsEffect(shadow)


class CustomTitleBar(QFrame):
    """Baris judul (Title bar) kustom untuk menggantikan bawaan Windows."""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent_window = parent
        self.setFixedHeight(32)
        self.setStyleSheet("background-color: #0B101E;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(15, 0, 0, 0)
        lay.setSpacing(10)

        lbl_icon = QLabel("\ue72e")  # Ikon gembok kecil
        lbl_icon.setObjectName("Icon")
        lbl_icon.setStyleSheet("color: #00D2C8; font-size: 10pt;")

        lbl_title = QLabel("Digital Locker — Professional")
        lbl_title.setStyleSheet("color: #8B95A5; font-size: 9pt;")

        lay.addWidget(lbl_icon)
        lay.addWidget(lbl_title)
        lay.addStretch()

        # Window Controls
        btn_min = QPushButton("\ue921")
        btn_min.setObjectName("BtnGhost")
        btn_min.setFixedSize(40, 32)
        btn_min.clicked.connect(self.parent_window.showMinimized)

        btn_max = QPushButton("\ue922")
        btn_max.setObjectName("BtnGhost")
        btn_max.setFixedSize(40, 32)
        btn_max.clicked.connect(self._toggle_maximize)

        btn_close = QPushButton("\ue8bb")
        btn_close.setObjectName("BtnGhost")
        btn_close.setFixedSize(40, 32)
        btn_close.setStyleSheet(
            "QPushButton#BtnGhost:hover { background-color: #E74C3C; color: white; border-radius: 0; }"
        )
        btn_close.clicked.connect(self.parent_window.close)

        lay.addWidget(btn_min)
        lay.addWidget(btn_max)
        lay.addWidget(btn_close)

    def _toggle_maximize(self):
        if self.parent_window.isMaximized():
            self.parent_window.showNormal()
        else:
            self.parent_window.showMaximized()

    # Memungkinkan window di-drag dari Title Bar
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if hasattr(self, "drag_pos"):
            delta = event.globalPosition().toPoint() - self.drag_pos
            self.parent_window.move(self.parent_window.pos() + delta)
            self.drag_pos = event.globalPosition().toPoint()


class BigActionBtn(QPushButton):
    """Tombol Gradient raksasa dengan Ikon Vektor Segoe MDL2."""

    def __init__(self, title, subtitle, icon="\ue72e", parent=None):  # Default: Gembok
        super().__init__(parent)
        self.setObjectName("BtnAksiBesar")
        self.setFixedHeight(75)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(25, 10, 25, 10)

        self.lbl_icon = QLabel(icon)
        self.lbl_icon.setObjectName("Icon")
        self.lbl_icon.setStyleSheet("font-size: 20pt; color: white;")

        v_lay = QVBoxLayout()
        v_lay.setSpacing(2)
        v_lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("font-size: 13pt; font-weight: 800; color: white;")

        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setStyleSheet("font-size: 9pt; color: rgba(255, 255, 255, 0.75);")

        v_lay.addWidget(self.lbl_title)
        v_lay.addWidget(self.lbl_sub)

        self.lbl_arrow = QLabel("\ue72a")  # Ikon Panah Kanan Vektor
        self.lbl_arrow.setObjectName("Icon")
        self.lbl_arrow.setStyleSheet("font-size: 16pt; color: white;")

        lay.addWidget(self.lbl_icon)
        lay.addSpacing(15)
        lay.addLayout(v_lay)
        lay.addStretch()
        lay.addWidget(self.lbl_arrow)

    def setEnabled(self, val):
        super().setEnabled(val)
        opacity = "1.0" if val else "0.3"
        color_val = f"rgba(255,255,255,{opacity})"
        self.lbl_title.setStyleSheet(
            f"font-size: 13pt; font-weight: 800; color: {color_val};"
        )
        self.lbl_sub.setStyleSheet(
            f"font-size: 9pt; color: rgba(255,255,255,{float(opacity)*0.75});"
        )
        self.lbl_icon.setStyleSheet(f"font-size: 20pt; color: {color_val};")
        self.lbl_arrow.setStyleSheet(f"font-size: 16pt; color: {color_val};")

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

    def run(self):
        try:
            result = self.func(
                *self.args,
                progress_cb=lambda val: self.progress.emit(val),
                **self.kwargs,
            )
            self.finished.emit(result if isinstance(result, tuple) else (result,))
        except Exception as e:
            self.finished.emit((False, str(e)))


class AnimatedNotifBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(0)
        self.setStyleSheet("background-color: transparent; border-radius: 6px;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        self.lbl = QLabel("")
        self.lbl.setObjectName("Icon")  # Memungkinkan mixing teks dan ikon
        self.lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl.setWordWrap(True)
        layout.addWidget(self.lbl)

        self.anim = QPropertyAnimation(self, b"maximumHeight")
        self.anim.setDuration(300)
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuint)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide_msg)

    def show_msg(self, kind: str, msg: str, auto_hide_ms: int = 0):
        self.timer.stop()
        bg_color = (
            "#0D2B1E" if kind == "ok" else ("#2B0D0D" if kind == "err" else "#2B1E0D")
        )
        fg_color = (
            "#00D2C8" if kind == "ok" else ("#E74C3C" if kind == "err" else "#F39C12")
        )
        icon = (
            "\ue73e" if kind == "ok" else ("\uea39" if kind == "err" else "\ue7ba")
        )  # Ikon vektor

        self.setStyleSheet(
            f"background-color: {bg_color}; border-radius: 6px; border: 1px solid {CLR_BORDER};"
        )
        self.lbl.setStyleSheet(
            f"color: {fg_color}; font-weight: bold; font-family: 'Segoe UI', 'Segoe MDL2 Assets';"
        )
        self.lbl.setText(f"{icon}  {msg}")

        self.anim.setStartValue(self.height())
        self.anim.setEndValue(45)
        self.anim.start()
        if auto_hide_ms > 0:
            self.timer.start(auto_hide_ms)

    def hide_msg(self):
        self.timer.stop()
        self.anim.setStartValue(self.height())
        self.anim.setEndValue(0)
        self.anim.start()
