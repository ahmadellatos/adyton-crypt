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
)
from PySide6.QtCore import Qt, QSize


class BigActionBtn(QPushButton):
    """Tombol aksi besar utama (Kunci / Buka)."""

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
        self.lbl_title.setStyleSheet("font-size: 13pt; font-weight: 700; color: white;")

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
            f"font-size: 13pt; font-weight: 700; color: rgba(255,255,255,{opacity});"
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
