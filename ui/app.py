"""
ui/app.py
Menerapkan Frameless Window dan penyempurnaan proporsi Tab Pill.
"""

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QFrame,
    QButtonGroup,
    QSizePolicy,
)
from PySide6.QtCore import Qt

from .tab_kunci import TabKunci
from .tab_buka import TabBuka
from .styles import load_stylesheet
from .widgets import CustomTitleBar


class AppBrankas(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(1100, 700)

        self.setStyleSheet(load_stylesheet())
        self._init_ui()

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.title_bar = CustomTitleBar(self)
        main_layout.addWidget(self.title_bar)

        content_container = QWidget()
        content_lay = QVBoxLayout(content_container)
        content_lay.setContentsMargins(30, 20, 30, 15)
        content_lay.setSpacing(25)

        self._build_header(content_lay)

        self.stacked_tabs = QStackedWidget()
        self.tab_kunci = TabKunci()
        self.tab_buka = TabBuka()
        self.stacked_tabs.addWidget(self.tab_kunci)
        self.stacked_tabs.addWidget(self.tab_buka)
        content_lay.addWidget(self.stacked_tabs, 1)

        self._build_footer(content_lay)
        main_layout.addWidget(content_container, 1)

    def _build_header(self, parent_layout):
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        # --- KIRI: Logo Vektor ---
        lay_kiri = QHBoxLayout()
        lay_kiri.setSpacing(15)
        lbl_logo = QLabel("\ue72e")
        lbl_logo.setObjectName("Icon")
        lbl_logo.setStyleSheet("font-size: 34pt; color: #00D2C8;")

        lay_title = QVBoxLayout()
        lay_title.setSpacing(0)
        lay_title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lbl_title = QLabel("Digital Locker")
        lbl_title.setObjectName("AppTitle")
        lbl_sub = QLabel("Secure AES-256 Encryption")
        lbl_sub.setObjectName("AppSubtitle")
        lay_title.addWidget(lbl_title)
        lay_title.addWidget(lbl_sub)

        lay_kiri.addWidget(lbl_logo)
        lay_kiri.addLayout(lay_title)
        header_layout.addLayout(lay_kiri)

        header_layout.addStretch()

        # --- TENGAH: Segmented Tab Buttons (Proporsi Diperbaiki) ---
        tab_container = QFrame()
        tab_container.setObjectName("TabContainer")
        tab_container.setFixedSize(320, 48)
        lay_tabs = QHBoxLayout(tab_container)
        lay_tabs.setContentsMargins(4, 4, 4, 4)
        lay_tabs.setSpacing(4)

        self.btn_nav_kunci = QPushButton("\ue72e  Kunci Folder")
        self.btn_nav_kunci.setObjectName("TabBtn")
        self.btn_nav_kunci.setCheckable(True)
        self.btn_nav_kunci.setChecked(True)
        # Force tombol memenuhi tinggi container
        self.btn_nav_kunci.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self.btn_nav_buka = QPushButton("\ue785  Buka Brankas")
        self.btn_nav_buka.setObjectName("TabBtn")
        self.btn_nav_buka.setCheckable(True)
        self.btn_nav_buka.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self.tab_group = QButtonGroup(self)
        self.tab_group.addButton(self.btn_nav_kunci, 0)
        self.tab_group.addButton(self.btn_nav_buka, 1)
        self.tab_group.buttonClicked.connect(self._on_tab_changed)

        lay_tabs.addWidget(self.btn_nav_kunci)
        lay_tabs.addWidget(self.btn_nav_buka)
        header_layout.addWidget(tab_container)

        header_layout.addStretch()

        # --- KANAN: Status Vektor (Tombol Setting Dihapus) ---
        lay_kanan = QHBoxLayout()
        lay_kanan.setSpacing(15)
        lbl_shield = QLabel("\uea18")
        lbl_shield.setObjectName("Icon")
        lbl_shield.setStyleSheet("font-size: 24pt; color: #00D2C8;")

        lay_status = QVBoxLayout()
        lay_status.setSpacing(0)
        lay_status.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lbl_stat_title = QLabel("AES-256 • GCM")
        lbl_stat_title.setStyleSheet(
            "font-size: 9pt; font-weight: bold; color: #8B95A5;"
        )
        lbl_stat_sub = QLabel("Data Anda aman")
        lbl_stat_sub.setStyleSheet("font-size: 9pt; color: #00D2C8; font-weight: 600;")
        lay_status.addWidget(lbl_stat_title)
        lay_status.addWidget(lbl_stat_sub)

        lay_kanan.addWidget(lbl_shield)
        lay_kanan.addLayout(lay_status)
        # (btn_settings sudah dihapus dari sini)

        header_layout.addLayout(lay_kanan)
        parent_layout.addLayout(header_layout)

    def _build_footer(self, parent_layout):
        lay_footer = QHBoxLayout()
        lbl_safe = QLabel("\uea18  Semua operasi aman dan terenkripsi")
        lbl_safe.setObjectName("Icon")
        lbl_safe.setStyleSheet("color: #8B95A5; font-size: 9pt;")

        # Versi diubah menjadi 1.0.0
        lbl_ver = QLabel("Version 1.0.0 \ue73e")
        lbl_ver.setObjectName("Icon")
        lbl_ver.setStyleSheet("color: #8B95A5; font-size: 9pt;")

        lay_footer.addWidget(lbl_safe)
        lay_footer.addStretch()
        lay_footer.addWidget(lbl_ver)
        parent_layout.addLayout(lay_footer)

    def _on_tab_changed(self, button):
        idx = self.tab_group.id(button)
        self.stacked_tabs.setCurrentIndex(idx)
