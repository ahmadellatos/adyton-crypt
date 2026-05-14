"""
Modul: app.py
Deskripsi: Merupakan antarmuka jendela utama (Main Window) dari aplikasi Digital Locker.
           Menangani tata letak (layout) kerangka aplikasi, instalasi System Tray untuk
           tugas latar belakang, pengikatan (binding) tab kontrol antara fitur Kunci
           dan Buka Brankas, serta implementasi kustom Title Bar (Frameless Window).
"""

import sys
import qtawesome as qta
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
    QSystemTrayIcon,
    QMenu,
    QApplication,
    QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, QSize, QPropertyAnimation
from loguru import logger

from .tab_kunci import TabKunci
from .tab_buka import TabBuka
from .widgets import CustomTitleBar


class AppBrankas(QMainWindow):
    """
    Kelas Induk Jendela Aplikasi Digital Locker.
    """

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(1100, 700)

        # Translucency tetap aktif agar sisi membulat CustomTitleBar
        # dapat digambar/di-render secara mulus tanpa latar hitam kotak di sudutnya.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._init_ui()
        self._init_tray()

        # FIX: Posisikan jendela di tengah layar saat diinisialisasi
        self._center_window()

    def _center_window(self):
        """Memposisikan jendela aplikasi tepat di tengah layar secara otomatis."""
        self.resize(1100, 700)  # Set paksa ke ukuran ideal sebelum menghitung
        center_point = QApplication.primaryScreen().availableGeometry().center()
        frame_geo = self.frameGeometry()
        frame_geo.moveCenter(center_point)
        self.move(frame_geo.topLeft())

    def _init_ui(self):
        """Membangun arsitektur User Interface utama aplikasi."""
        central_widget = QWidget()
        central_widget.setObjectName("CentralWidget")
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

    def _init_tray(self):
        """Menginisialisasi modul System Tray Icon agar bisa berjalan di background."""
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(qta.icon("mdi6.shield-lock", color="#00D2C8"))

        tray_menu = QMenu()

        act_show = tray_menu.addAction(" Buka Digital Locker")
        act_show.setIcon(qta.icon("mdi6.window-maximize", color="white"))
        act_show.triggered.connect(self.showNormal)

        act_quit = tray_menu.addAction(" Keluar Sepenuhnya")
        act_quit.setIcon(qta.icon("mdi6.power", color="#E74C3C"))
        act_quit.triggered.connect(QApplication.instance().quit)

        self.tray.setContextMenu(tray_menu)
        self.tray.show()

        self.tray.activated.connect(self._on_tray_click)

    def _on_tray_click(self, reason):
        """Merespon event klik pada ikon System Tray."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()

    def closeEvent(self, event):
        """
        Pencegatan event ketika pengguna menekan tombol X (Close).
        Alih-alih membunuh proses, aplikasi disembunyikan dan dioper ke latar belakang.
        """
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "Digital Locker Berjalan",
            "Aplikasi di-minimize ke System Tray untuk memproses di latar belakang.",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )
        logger.info("Window di-minimize ke System Tray.")

    def _build_header(self, parent_layout):
        """Membangun komponen header atas (Logo, Teks, dan Tombol Navigasi Tab)."""
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        lay_kiri = QHBoxLayout()
        lay_kiri.setSpacing(15)

        lbl_logo = QLabel()
        lbl_logo.setPixmap(qta.icon("mdi6.lock", color="#00D2C8").pixmap(48, 48))

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

        tab_container = QFrame()
        tab_container.setObjectName("TabContainer")
        tab_container.setFixedSize(320, 48)
        lay_tabs = QHBoxLayout(tab_container)
        lay_tabs.setContentsMargins(4, 4, 4, 4)
        lay_tabs.setSpacing(4)

        self.btn_nav_kunci = QPushButton(" Kunci Folder")
        self.btn_nav_kunci.setIcon(
            qta.icon("mdi6.lock", color="#8B95A5", color_on="white")
        )
        self.btn_nav_kunci.setIconSize(QSize(20, 20))
        self.btn_nav_kunci.setObjectName("TabBtn")
        self.btn_nav_kunci.setCheckable(True)
        self.btn_nav_kunci.setChecked(True)
        self.btn_nav_kunci.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self.btn_nav_buka = QPushButton(" Buka Brankas")
        self.btn_nav_buka.setIcon(
            qta.icon("mdi6.lock-open-variant", color="#8B95A5", color_on="white")
        )
        self.btn_nav_buka.setIconSize(QSize(20, 20))
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

        lay_kanan = QHBoxLayout()
        lay_kanan.setSpacing(15)

        lbl_shield = QLabel()
        lbl_shield.setPixmap(
            qta.icon("mdi6.shield-check", color="#00D2C8").pixmap(32, 32)
        )

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

        header_layout.addLayout(lay_kanan)
        parent_layout.addLayout(header_layout)

    def _build_footer(self, parent_layout):
        """Membangun komponen footer penutup di dasar aplikasi."""
        lay_footer = QHBoxLayout()

        lay_safe = QHBoxLayout()
        lay_safe.setSpacing(8)
        lbl_safe_icon = QLabel()
        lbl_safe_icon.setPixmap(
            qta.icon("mdi6.shield-check", color="#8B95A5").pixmap(16, 16)
        )
        lbl_safe_text = QLabel("Semua operasi aman dan terenkripsi")
        lbl_safe_text.setStyleSheet("color: #8B95A5; font-size: 9pt;")
        lay_safe.addWidget(lbl_safe_icon)
        lay_safe.addWidget(lbl_safe_text)

        lay_ver = QHBoxLayout()
        lay_ver.setSpacing(8)
        lbl_ver_text = QLabel("Version 1.0.0")
        lbl_ver_text.setStyleSheet("color: #8B95A5; font-size: 9pt;")
        lbl_ver_icon = QLabel()
        lbl_ver_icon.setPixmap(
            qta.icon("mdi6.check-circle", color="#8B95A5").pixmap(16, 16)
        )
        lay_ver.addWidget(lbl_ver_text)
        lay_ver.addWidget(lbl_ver_icon)

        lay_footer.addLayout(lay_safe)
        lay_footer.addStretch()
        lay_footer.addLayout(lay_ver)
        parent_layout.addLayout(lay_footer)

    def _on_tab_changed(self, button):
        new_idx = self.tab_group.id(button)
        if new_idx == self.stacked_tabs.currentIndex():
            return

        old_widget = self.stacked_tabs.currentWidget()
        effect = QGraphicsOpacityEffect(old_widget)
        old_widget.setGraphicsEffect(effect)

        self._anim_out = QPropertyAnimation(effect, b"opacity")
        self._anim_out.setDuration(60)
        self._anim_out.setStartValue(1.0)
        self._anim_out.setEndValue(0.0)
        self._anim_out.finished.connect(
            lambda: self._finish_tab_switch(new_idx, old_widget)
        )
        self._anim_out.start()

    def _finish_tab_switch(self, new_idx, old_widget):
        old_widget.setGraphicsEffect(None)
        self.stacked_tabs.setCurrentIndex(new_idx)

        new_widget = self.stacked_tabs.currentWidget()
        effect = QGraphicsOpacityEffect(new_widget)
        new_widget.setGraphicsEffect(effect)

        self._anim_in = QPropertyAnimation(effect, b"opacity")
        self._anim_in.setDuration(75)
        self._anim_in.setStartValue(0.0)
        self._anim_in.setEndValue(1.0)
        self._anim_in.finished.connect(lambda: new_widget.setGraphicsEffect(None))
        self._anim_in.start()

    def showEvent(self, event):
        super().showEvent(event)
        self._anim_window = QPropertyAnimation(self, b"windowOpacity")
        self._anim_window.setDuration(100)
        self._anim_window.setStartValue(0.0)
        self._anim_window.setEndValue(1.0)
        self._anim_window.start()
