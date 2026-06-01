"""
Modul: buttons.py
Deskripsi: Tombol-tombol aksi kustom (BigActionBtn, ClearButton, split button).
"""

import qtawesome as qta
from PySide6.QtWidgets import (
    QPushButton,
    QFrame,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QColor


class BigActionBtn(QPushButton):
    """Tombol aksi besar utama (Kunci / Buka)."""

    def __init__(self, title, subtitle, icon_name="mdi6.lock", parent=None):
        super().__init__(parent)
        self.setObjectName("BtnAksiBesar")
        self.setFixedHeight(82)  # Option B: sedikit lebih tinggi & berani
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.icon_name = icon_name
        self._right_icon_name = "mdi6.chevron-right"
        self._right_icon_size = 27
        self._progress_visible = False
        self._display_progress = 0.0
        self._progress_anim = QPropertyAnimation(self, b"progressFill", self)
        self._progress_anim.setDuration(260)
        self._progress_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(28, 12, 28, 12)  # Proporsi lebih baik untuk tinggi 82px

        self.lbl_icon = QLabel()
        self.lbl_icon.setPixmap(
            qta.icon(self.icon_name, color="white").pixmap(34, 34)
        )  # Sedikit lebih besar (Option B)

        v_lay = QVBoxLayout()
        v_lay.setSpacing(2)
        v_lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("CardTitle")

        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setObjectName("MutedText")

        v_lay.addWidget(self.lbl_title)
        v_lay.addWidget(self.lbl_sub)

        # Refined typography for Option B (minimalist premium + sedikit berani)
        self.lbl_title.setStyleSheet(
            "font-size: 14pt; font-weight: 600; color: white; letter-spacing: 0.2px;"
        )
        self.lbl_sub.setStyleSheet("font-size: 9.5pt; color: rgba(255,255,255,0.82);")

        self.lbl_arrow = QLabel()
        self.lbl_arrow.setPixmap(
            qta.icon(self._right_icon_name, color="white").pixmap(
                self._right_icon_size, self._right_icon_size
            )
        )

        lay.addWidget(self.lbl_icon)
        lay.addSpacing(15)
        lay.addLayout(v_lay)
        lay.addStretch()
        lay.addWidget(self.lbl_arrow)

        # Hover glow state (we mutate the existing effect instead of replacing it)
        self._original_shadow_color = None
        self._original_blur = None
        self._original_y_offset = None

        # Set initial enabled state so colors are correct from the start
        self.setEnabled(True)

    def setEnabled(self, val):
        super().setEnabled(val)
        color_val = "white" if val else "rgba(255,255,255,0.35)"

        self.lbl_icon.setPixmap(
            qta.icon(self.icon_name, color=color_val).pixmap(34, 34)
        )
        self.lbl_arrow.setPixmap(
            qta.icon(self._right_icon_name, color=color_val).pixmap(
                self._right_icon_size, self._right_icon_size
            )
        )

        # Refined typography with proper hierarchy for Option B
        if val:
            # Active state - premium strong but not shouting
            self.lbl_title.setStyleSheet(
                "font-size: 14pt; font-weight: 600; color: white; letter-spacing: 0.2px;"
            )
            self.lbl_sub.setStyleSheet(
                "font-size: 9.5pt; color: rgba(255,255,255,0.82);"
            )
        else:
            # Disabled state - properly muted (not just faded white)
            self.lbl_title.setStyleSheet(
                "font-size: 14pt; font-weight: 500; color: rgba(255,255,255,0.45);"
            )
            self.lbl_sub.setStyleSheet(
                "font-size: 9.5pt; color: rgba(255,255,255,0.35);"
            )

        self._apply_progress_style()

    def setTextLabels(self, title, subtitle=""):
        self.lbl_title.setText(title)
        self.lbl_sub.setText(subtitle)

    def _get_progress_fill(self) -> float:
        return self._display_progress

    def _set_progress_fill(self, value: float) -> None:
        self._display_progress = max(0.0, min(1.0, float(value)))
        self._apply_progress_style()

    progressFill = Property(float, _get_progress_fill, _set_progress_fill)

    def setProgressVisible(self, visible: bool, initial_value: float = 0.0) -> None:
        """Aktifkan visual progress fill di tombol aksi besar.

        Progress fill memakai property animation agar perubahan progress terasa
        hidup walaupun callback worker datang tidak rata. Saat nonaktif, styling
        tombol kembali ke stylesheet global.
        """
        self._progress_visible = bool(visible)
        self._progress_anim.stop()
        self._display_progress = max(0.0, min(1.0, float(initial_value)))
        self._apply_progress_style()

    def setProgressAnimated(self, value: float, duration_ms: int = 260) -> None:
        """Animasi progress fill ke nilai baru secara smooth."""
        if not self._progress_visible:
            return
        target = max(0.0, min(1.0, float(value)))
        if target < self._display_progress:
            # Jangan mundurkan progress visual; ini menghindari kesan glitch.
            target = self._display_progress
        self._progress_anim.stop()
        self._progress_anim.setDuration(max(80, int(duration_ms)))
        self._progress_anim.setStartValue(self._display_progress)
        self._progress_anim.setEndValue(target)
        self._progress_anim.start()

    def _apply_progress_style(self) -> None:
        if not self._progress_visible:
            self.setStyleSheet("")
            return

        p = max(0.0, min(1.0, self._display_progress))
        # Split stops dibuat sangat dekat agar sisi fill terlihat tajam tapi
        # tetap smooth karena nilai p dianimasikan.
        left_stop = max(0.0, p - 0.010)
        right_stop = min(1.0, p + 0.002)
        self.setStyleSheet(f"""
            QPushButton#BtnAksiBesar {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00D2C8,
                    stop:{left_stop:.4f} #00B7AE,
                    stop:{p:.4f} #009E96,
                    stop:{right_stop:.4f} #172033,
                    stop:1 #111625
                );
                border: 1px solid #00EFE5;
                border-radius: 12px;
                padding: 13px 34px;
            }}
            QPushButton#BtnAksiBesar:hover {{
                border: 1px solid #FFFFFF;
            }}
            QPushButton#BtnAksiBesar:focus {{
                border: 2px solid #FFFFFF;
            }}
            QPushButton#BtnAksiBesar:disabled {{
                background-color: #151C2C;
                border: 1px solid #232B3E;
            }}
        """)

    def setVisualIcons(
        self, left_icon_name: str | None = None, right_icon_name: str | None = None
    ):
        """Update ikon aksi tanpa membuat ulang tombol.

        Dipakai untuk membuat tombol proses lebih jelas sebagai tombol cancel.
        """
        if left_icon_name:
            self.icon_name = left_icon_name
        if right_icon_name:
            self._right_icon_name = right_icon_name
        self.setEnabled(self.isEnabled())

    def resetVisualIcons(self, left_icon_name: str | None = None):
        if left_icon_name:
            self.icon_name = left_icon_name
        self._right_icon_name = "mdi6.chevron-right"
        self._right_icon_size = 27
        self.setEnabled(self.isEnabled())

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
            event.accept()
        else:
            super().keyPressEvent(event)

    # --- Hover Shadow (Teal glow) ---
    # We mutate the *existing* QGraphicsDropShadowEffect instead of replacing it.
    # This avoids "C++ object already deleted" crashes.
    def enterEvent(self, event):
        self._apply_hover_glow()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._restore_normal_shadow()
        super().leaveEvent(event)

    def _apply_hover_glow(self):
        effect = self.graphicsEffect()
        if not isinstance(effect, QGraphicsDropShadowEffect):
            return

        # Save original values the first time we hover
        if self._original_shadow_color is None:
            self._original_shadow_color = effect.color()
            self._original_blur = effect.blurRadius()
            self._original_y_offset = effect.yOffset()

        # Switch to a nice teal glow
        effect.setColor(QColor(0, 210, 200, 120))
        effect.setBlurRadius(30)
        effect.setYOffset(0)  # centered glow

    def _restore_normal_shadow(self):
        effect = self.graphicsEffect()
        if not isinstance(effect, QGraphicsDropShadowEffect):
            return

        if self._original_shadow_color is not None:
            effect.setColor(self._original_shadow_color)
            effect.setBlurRadius(self._original_blur or 24)
            effect.setYOffset(self._original_y_offset or 5)


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
            /* HOVER: Background merah untuk penanda destruktif */
            QPushButton:hover { background: #E74C3C; border-radius: 4px; }
            /* FOCUS: Outline Cyan, background transparan (jangan merah) */
            QPushButton:focus { border: 2px solid #00D2C8; background: transparent; border-radius: 4px; }
        """)

    def enterEvent(self, event):
        self.setIcon(qta.icon("mdi6.close", color="#FFFFFF"))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(qta.icon("mdi6.close", color="#8B95A5"))
        super().leaveEvent(event)


class TambahClearSplitButton(QFrame):
    """
    Custom Split Button terintegrasi: "[+] Tambah | [Trashcan]"
    Cincin fokus (focus ring) dan hover dipisah secara independen untuk tiap tombol.
    """

    def __init__(self, menu, clear_callback, parent=None):
        super().__init__(parent)
        self.setObjectName("SplitActionFrame")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.setStyleSheet("""
            QFrame#SplitActionFrame {
                background-color: transparent;
                border: 1px solid #232B3E;
                border-radius: 8px;
            }
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # --- 1. Bagian Kiri: Tombol Tambah ---
        self.btn_add = QPushButton()
        self.btn_add.setText(" Tambah")
        self.btn_add.setIcon(qta.icon("mdi6.plus", color="#8B95A5"))
        self.btn_add.setMenu(menu)
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._style_add_split = """
            QPushButton {
                background: transparent;
                border: none;
                color: #8B95A5;
                font-size: 10pt;
                font-weight: 600;
                padding-left: 12px;
                padding-right: 12px;
                height: 34px;
                border-top-left-radius: 7px;
                border-bottom-left-radius: 7px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
            }
            QPushButton:hover { color: white; background-color: #181F32; }
            QPushButton:focus { border: 2px solid #00D2C8; background-color: #181F32; }
            QPushButton::menu-indicator { image: none; width: 0px; }
        """
        self._style_add_full = """
            QPushButton {
                background: transparent;
                border: none;
                color: #8B95A5;
                font-size: 10pt;
                font-weight: 600;
                padding-left: 12px;
                padding-right: 12px;
                height: 34px;
                border-radius: 7px;
            }
            QPushButton:hover { color: white; background-color: #181F32; }
            QPushButton:focus { border: 2px solid #00D2C8; background-color: #181F32; }
            QPushButton::menu-indicator { image: none; width: 0px; }
        """
        self.btn_add.setStyleSheet(self._style_add_split)

        # --- 2. Bagian Tengah: Garis Pemisah ---
        self.sep = QFrame()
        self.sep.setFixedWidth(1)
        self.sep.setStyleSheet("background-color: #232B3E;")

        # --- 3. Bagian Kanan: Tombol Trashcan (Clear All) ---
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
            QPushButton:focus {
                border: 2px solid #00D2C8;
                background-color: #232B3E;
            }
        """)

        lay.addWidget(self.btn_add, 1)
        lay.addWidget(self.sep)
        lay.addWidget(self.btn_clear)

        self.btn_add.installEventFilter(self)
        self.btn_clear.installEventFilter(self)

    def set_clear_visible(self, visible: bool):
        """Ubah tampilan dinamis & ganti radius tombol 'Tambah' jika sendirian"""
        self.sep.setVisible(visible)
        self.btn_clear.setVisible(visible)
        if visible:
            self.setFixedSize(145, 36)
            self.btn_add.setStyleSheet(self._style_add_split)
        else:
            self.setFixedSize(100, 36)
            self.btn_add.setStyleSheet(self._style_add_full)

    def eventFilter(self, obj, event):
        if event.type() == event.Type.Enter:
            if obj == self.btn_clear:
                self.btn_clear.setIcon(
                    qta.icon("mdi6.trash-can-outline", color="#FFFFFF")
                )
        elif event.type() == event.Type.Leave:
            if obj == self.btn_clear:
                self.btn_clear.setIcon(
                    qta.icon("mdi6.trash-can-outline", color="#8B95A5")
                )
        elif event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                if obj == self.btn_clear:
                    self.btn_clear.click()
                    return True

        return super().eventFilter(obj, event)
