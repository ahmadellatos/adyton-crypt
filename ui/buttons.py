"""
Modul: buttons.py
Deskripsi: Tombol-tombol aksi kustom (BigActionBtn, ClearButton, split button).
"""

import qtawesome as qta
from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from .styles import (
    CLR_ACCENT,
    CLR_ACCENT_DK,
    CLR_BORDER,
    CLR_DANGER,
    CLR_HOVER_BG,
    CLR_INSET,
    CLR_LINE,
    CLR_ON_ACCENT,
    CLR_TEXT_DIM,
    CLR_TEXT_FAINT,
    CLR_TEXT_MAIN,
)


class BigActionBtn(QPushButton):
    """Tombol aksi besar utama (Kunci / Buka)."""

    def __init__(self, title, subtitle, icon_name="mdi6.lock-outline", parent=None):
        super().__init__(parent)
        self.setObjectName("BtnAksiBesar")
        self.setFixedHeight(58)  # pill ramping, satu baris (design system CTA)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.icon_name = icon_name
        self._progress_visible = False
        self._display_progress = 0.0
        self._progress_anim = QPropertyAnimation(self, b"progressFill", self)
        self._progress_anim.setDuration(260)
        self._progress_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._cta_lay = lay = QHBoxLayout(self)
        lay.setContentsMargins(28, 6, 28, 6)

        self.lbl_icon = QLabel()
        self.lbl_icon.setPixmap(
            qta.icon(self.icon_name, color=CLR_ON_ACCENT).pixmap(22, 22)
        )  # ikon gelap di atas latar aksen

        v_lay = QVBoxLayout()
        v_lay.setSpacing(1)
        v_lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("CardTitle")
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setObjectName("MutedText")
        self.lbl_sub.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.lbl_sub.hide()  # subtitle hanya tampil saat progress

        v_lay.addWidget(self.lbl_title)
        v_lay.addWidget(self.lbl_sub)

        # Teks gelap di atas latar aksen (kalem, datar) — CTA satu baris
        self.lbl_title.setStyleSheet(
            f"font-size: 13.5pt; font-weight: 800; color: {CLR_ON_ACCENT}; letter-spacing: 0.2px;"
        )
        self.lbl_sub.setStyleSheet(
            "font-size: 9pt; font-weight: 600; color: rgba(7, 32, 37, 0.78);"
        )

        # Terpusat saat idle, rata kiri saat progress (leading stretch index 0
        # dikecilkan ke 0 sehingga konten bergeser ke kiri).
        lay.addStretch(1)  # index 0 — leading
        lay.addWidget(self.lbl_icon)
        lay.addSpacing(11)
        lay.addLayout(v_lay)
        lay.addStretch(1)  # trailing

        # Hover glow state (we mutate the existing effect instead of replacing it)
        self._original_shadow_color = None
        self._original_blur = None
        self._original_y_offset = None

        # Set initial enabled state so colors are correct from the start
        self.setEnabled(True)

    def setEnabled(self, val):
        super().setEnabled(val)
        color_val = CLR_ON_ACCENT if val else CLR_TEXT_FAINT

        self.lbl_icon.setPixmap(qta.icon(self.icon_name, color=color_val).pixmap(22, 22))

        if val:
            # Aktif — teks gelap di atas aksen
            self.lbl_title.setStyleSheet(
                f"font-size: 13.5pt; font-weight: 800; color: {CLR_ON_ACCENT}; letter-spacing: 0.2px;"
            )
            self.lbl_sub.setStyleSheet(
                "font-size: 9pt; font-weight: 600; color: rgba(7, 32, 37, 0.78);"
            )
        else:
            # Nonaktif — teks redup di atas latar disabled
            self.lbl_title.setStyleSheet(
                f"font-size: 13.5pt; font-weight: 700; color: {CLR_TEXT_FAINT};"
            )
            self.lbl_sub.setStyleSheet(f"font-size: 9pt; color: {CLR_TEXT_FAINT};")

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
        if visible:
            # Saat progress, teks/ikon putih agar terbaca di atas isian aksen
            # maupun bagian track gelap yang belum terisi. Subtitle ditampilkan
            # (baris kedua) untuk info %/ETA/tahap.
            self.lbl_icon.setPixmap(qta.icon(self.icon_name, color="#FFFFFF").pixmap(22, 22))
            self.lbl_title.setStyleSheet(
                "font-size: 12.5pt; font-weight: 800; color: #FFFFFF; letter-spacing: 0.2px;"
            )
            self.lbl_sub.setStyleSheet(
                "font-size: 8.5pt; font-weight: 600; color: rgba(255,255,255,0.85);"
            )
            self.lbl_sub.show()
            self._cta_lay.setStretch(0, 0)  # rata kiri saat progress
            self._apply_progress_style()
        else:
            self.lbl_sub.hide()
            self._cta_lay.setStretch(0, 1)  # kembali terpusat
            self._apply_progress_style()
            self.setEnabled(self.isEnabled())  # pulihkan warna teks/ikon gelap

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
        # Isian datar: aksen sampai titik p, lalu track inset gelap. Sisi fill
        # dibuat tajam dengan dua stop berdekatan; nilai p dianimasikan agar mulus.
        right_stop = min(1.0, p + 0.002)
        self.setStyleSheet(f"""
            QPushButton#BtnAksiBesar {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {CLR_ACCENT_DK},
                    stop:{p:.4f} {CLR_ACCENT_DK},
                    stop:{right_stop:.4f} {CLR_INSET},
                    stop:1 {CLR_INSET}
                );
                border: none;
                border-radius: 29px;
                padding: 0px 34px;
            }}
            QPushButton#BtnAksiBesar:hover {{
                border: none;
            }}
            QPushButton#BtnAksiBesar[kbFocus="true"] {{
                border: 2px solid {CLR_TEXT_MAIN};
            }}
            QPushButton#BtnAksiBesar:disabled {{
                background-color: {CLR_INSET};
                border: 1px solid {CLR_LINE};
            }}
        """)

    def setVisualIcons(self, left_icon_name: str | None = None):
        """Update ikon aksi tanpa membuat ulang tombol.

        Dipakai untuk membuat tombol proses lebih jelas sebagai tombol cancel.
        """
        if left_icon_name:
            self.icon_name = left_icon_name
        self.setEnabled(self.isEnabled())

    def resetVisualIcons(self, left_icon_name: str | None = None):
        if left_icon_name:
            self.icon_name = left_icon_name
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

        # Angkat dengan bayangan gelap halus — tanpa glow/halo neon.
        effect.setColor(QColor(8, 18, 22, 150))
        effect.setBlurRadius(34)
        effect.setYOffset(9)

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
        self.setIcon(qta.icon("mdi6.close", color=CLR_TEXT_DIM))
        self.setIconSize(QSize(20, 20))

        self.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; }}
            /* HOVER: latar bahaya untuk penanda destruktif */
            QPushButton:hover {{ background: {CLR_DANGER}; border-radius: 7px; }}
            /* FOCUS: cincin aksen, latar transparan (jangan bahaya) */
            QPushButton[kbFocus="true"] {{ border: 2px solid {CLR_ACCENT}; background: transparent; border-radius: 7px; }}
        """)

    def enterEvent(self, event):
        self.setIcon(qta.icon("mdi6.close", color=CLR_ON_ACCENT))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(qta.icon("mdi6.close", color=CLR_TEXT_DIM))
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

        self.setStyleSheet(f"""
            QFrame#SplitActionFrame {{
                background-color: transparent;
                border: 1px solid {CLR_BORDER};
                border-radius: 11px;
            }}
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # --- 1. Bagian Kiri: Tombol Tambah ---
        self.btn_add = QPushButton()
        self.btn_add.setText(" Add")
        self.btn_add.setIcon(qta.icon("mdi6.plus", color=CLR_TEXT_DIM))
        self.btn_add.setMenu(menu)
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._style_add_split = f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {CLR_TEXT_DIM};
                font-size: 10pt;
                font-weight: 700;
                padding-left: 12px;
                padding-right: 12px;
                height: 34px;
                border-top-left-radius: 10px;
                border-bottom-left-radius: 10px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
            }}
            QPushButton:hover {{ color: {CLR_TEXT_MAIN}; background-color: {CLR_HOVER_BG}; }}
            QPushButton[kbFocus="true"] {{ border: 2px solid {CLR_ACCENT}; background-color: {CLR_HOVER_BG}; }}
            QPushButton::menu-indicator {{ image: none; width: 0px; }}
        """
        self._style_add_full = f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {CLR_TEXT_DIM};
                font-size: 10pt;
                font-weight: 700;
                padding-left: 12px;
                padding-right: 12px;
                height: 34px;
                border-radius: 10px;
            }}
            QPushButton:hover {{ color: {CLR_TEXT_MAIN}; background-color: {CLR_HOVER_BG}; }}
            QPushButton[kbFocus="true"] {{ border: 2px solid {CLR_ACCENT}; background-color: {CLR_HOVER_BG}; }}
            QPushButton::menu-indicator {{ image: none; width: 0px; }}
        """
        self.btn_add.setStyleSheet(self._style_add_split)

        # --- 2. Bagian Tengah: Garis Pemisah ---
        self.sep = QFrame()
        self.sep.setFixedWidth(1)
        self.sep.setStyleSheet(f"background-color: {CLR_LINE};")

        # --- 3. Bagian Kanan: Tombol Trashcan (Clear All) ---
        self.btn_clear = QPushButton()
        self.btn_clear.setIcon(qta.icon("mdi6.trash-can-outline", color=CLR_TEXT_DIM))
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_clear.setFixedWidth(38)
        self.btn_clear.clicked.connect(clear_callback)
        self.btn_clear.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                height: 34px;
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                border-top-right-radius: 10px;
                border-bottom-right-radius: 10px;
            }}
            QPushButton:hover {{
                background-color: {CLR_DANGER};
            }}
            QPushButton[kbFocus="true"] {{
                border: 2px solid {CLR_ACCENT};
                background-color: {CLR_INSET};
            }}
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
                self.btn_clear.setIcon(qta.icon("mdi6.trash-can-outline", color=CLR_ON_ACCENT))
        elif event.type() == event.Type.Leave:
            if obj == self.btn_clear:
                self.btn_clear.setIcon(qta.icon("mdi6.trash-can-outline", color=CLR_TEXT_DIM))
        elif event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                if obj == self.btn_clear:
                    self.btn_clear.click()
                    return True

        return super().eventFilter(obj, event)
