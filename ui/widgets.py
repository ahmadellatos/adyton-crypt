"""
ui/widgets.py
Komponen UI kustom, utilitas shadow, dan QThread worker.
"""

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QGraphicsDropShadowEffect
from PySide6.QtCore import Qt, QThread, Signal, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QColor

from .styles import (
    CLR_NOTIF_OK_BG,
    CLR_NOTIF_OK_FG,
    CLR_NOTIF_ERR_BG,
    CLR_NOTIF_ERR_FG,
    CLR_NOTIF_WARN_BG,
    CLR_NOTIF_WARN_FG,
)


# ---------------------------------------------------------------------------
# FIX #1 — apply_shadow dipindah ke sini agar tidak ada circular import
# dari tab_kunci.py / tab_buka.py ke app.py
# ---------------------------------------------------------------------------
def apply_shadow(widget):
    """Memberikan efek melayang (Drop Shadow) ala desain modern."""
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(20)
    shadow.setXOffset(0)
    shadow.setYOffset(6)
    shadow.setColor(QColor(0, 0, 0, 80))
    widget.setGraphicsEffect(shadow)


class CryptoWorker(QThread):
    """
    Background thread untuk kriptografi.
    Memancarkan sinyal progress ke GUI thread utama.
    """

    progress = Signal(float)
    finished = Signal(tuple)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        # FIX #3 — progress_cb dikirim eksplisit, tidak mutasi self.kwargs
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
    """Notifikasi bar mulus dengan QPropertyAnimation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(0)
        self.setStyleSheet("background-color: transparent; border-radius: 6px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)

        self.lbl = QLabel("")
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

        if kind == "ok":
            self.setStyleSheet(
                f"background-color: {CLR_NOTIF_OK_BG}; border-radius: 6px;"
            )
            self.lbl.setStyleSheet(f"color: {CLR_NOTIF_OK_FG}; font-weight: bold;")
        elif kind == "err":
            self.setStyleSheet(
                f"background-color: {CLR_NOTIF_ERR_BG}; border-radius: 6px;"
            )
            self.lbl.setStyleSheet(f"color: {CLR_NOTIF_ERR_FG}; font-weight: bold;")
        elif kind == "warn":
            self.setStyleSheet(
                f"background-color: {CLR_NOTIF_WARN_BG}; border-radius: 6px;"
            )
            self.lbl.setStyleSheet(f"color: {CLR_NOTIF_WARN_FG}; font-weight: bold;")

        self.lbl.setText(msg)

        self.anim.setStartValue(self.height())
        self.anim.setEndValue(45)
        self.anim.start()

        if auto_hide_ms > 0:
            self.timer.start(auto_hide_ms)

    def hide_msg(self):
        self.timer.stop()
        self.lbl.setText("")
        self.anim.setStartValue(self.height())
        self.anim.setEndValue(0)
        self.anim.start()
