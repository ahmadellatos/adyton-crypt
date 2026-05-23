"""
Modul: app.py
Deskripsi: Merupakan antarmuka jendela utama (Main Window) dari aplikasi Adyton Crypt.
"""

import qtawesome as qta
from PySide6.QtWidgets import (
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
    QApplication,
)
from PySide6.QtCore import Qt, QSize, QPropertyAnimation
from PySide6.QtGui import QPixmap, QIcon
from loguru import logger
from qframelesswindow import FramelessMainWindow
from .tab_kunci import TabKunci
from .tab_buka import TabBuka
from .widgets import (
    CustomTitleBar,
    CenteredMenuAction,
    AccessibleCenteredMenu,
    ModernMessageBox,
)


class AppBrankas(FramelessMainWindow):
    def __init__(self):
        super().__init__()

        self._quitting = False

        self.setMinimumSize(960, 680)
        self.setObjectName("MainWindow")

        self._init_ui()
        self._init_tray()
        self._center_window()

        # Di dalem method __init__ lu (di deket kode tray lu yang ASLI)
        app_icon = QIcon("assets/icon_adyton.ico")

        # Ganti icon window utama
        self.setWindowIcon(app_icon)

        # Terus di kode self.tray lu yang ASLI, tinggal panggil ini:
        self.tray.setIcon(app_icon)

    def _center_window(self):
        self.resize(1100, 700)
        center_point = QApplication.primaryScreen().availableGeometry().center()
        frame_geo = self.frameGeometry()
        frame_geo.moveCenter(center_point)
        self.move(frame_geo.topLeft())

    def _init_ui(self):
        central_widget = QWidget()
        central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 32, 0, 0)
        main_layout.setSpacing(0)

        self.title_bar = CustomTitleBar(self)
        self.setTitleBar(self.title_bar)

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

        # FIX: Sambungkan progress worker ke tray tooltip agar user tahu
        # ada proses aktif meski window disembunyikan ke system tray
        self.tab_kunci.btn_aksi.clicked.connect(self._update_tray_on_busy)
        self.tab_buka.btn_aksi.clicked.connect(self._update_tray_on_busy)
        content_lay.addWidget(self.stacked_tabs, 1)

        self._build_footer(content_lay)
        main_layout.addWidget(content_container, 1)

    def _init_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(qta.icon("mdi6.shield-lock", color="#00D2C8"))

        tray_menu = AccessibleCenteredMenu()

        act_show = CenteredMenuAction(
            "Buka Adyton Crypt", "mdi6.window-maximize", parent=tray_menu
        )
        act_show.triggered.connect(self.showNormal)
        tray_menu.addAction(act_show)

        act_quit = CenteredMenuAction(
            "Keluar Sepenuhnya", "mdi6.power", icon_color="#E74C3C", parent=tray_menu
        )
        act_quit.triggered.connect(self._quit_sepenuhnya)
        tray_menu.addAction(act_quit)

        self.tray.setContextMenu(tray_menu)
        self.tray.show()

        self.tray.activated.connect(self._on_tray_click)

    def _on_tray_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()

    def _update_tray_on_busy(self):
        """FIX: Update tooltip tray saat proses enkripsi/dekripsi berjalan."""
        kunci_busy = (
            self.tab_kunci.worker is not None and self.tab_kunci.worker.isRunning()
        )
        buka_busy = (
            self.tab_buka.worker is not None and self.tab_buka.worker.isRunning()
        )
        if kunci_busy:
            self.tray.setToolTip("Adyton Crypt — Sedang mengenkripsi...")
            self.tab_kunci.worker.progress.connect(
                lambda v: self.tray.setToolTip(
                    f"Adyton Crypt — Mengenkripsi {int(v*100)}%"
                )
            )
            self.tab_kunci.worker.finished.connect(
                lambda: self.tray.setToolTip("Adyton Crypt")
            )
        elif buka_busy:
            self.tray.setToolTip("Adyton Crypt — Sedang mendekripsi...")
            self.tab_buka.worker.progress.connect(
                lambda v: self.tray.setToolTip(
                    f"Adyton Crypt — Mendekripsi {int(v*100)}%"
                )
            )
            self.tab_buka.worker.finished.connect(
                lambda: self.tray.setToolTip("Adyton Crypt")
            )

    def _quit_sepenuhnya(self):
        # FIX 2B: Cek state dari worker sebelum mengizinkan quit
        kunci_busy = (
            self.tab_kunci.worker is not None and self.tab_kunci.worker.isRunning()
        )
        buka_busy = (
            self.tab_buka.worker is not None and self.tab_buka.worker.isRunning()
        )

        if kunci_busy or buka_busy:
            # Munculkan window utamanya dulu kalau lagi ngumpet di tray
            self.showNormal()
            self.activateWindow()

            # Tampilkan dialog peringatan block
            dialog = ModernMessageBox(
                title="Proses Sedang Berjalan",
                message="Aplikasi sedang memproses enkripsi/dekripsi file.\n\nMematikan aplikasi secara paksa sekarang dapat menyebabkan file korup atau data hilang. Silakan tunggu hingga proses selesai atau batalkan proses terlebih dahulu.",
                icon_name="mdi6.alert-decagram",
                icon_color="#E74C3C",
                parent=self,
            )
            dialog.btn_yes.setText("Mengerti")
            dialog.btn_cancel.hide()  # Cuma butuh 1 tombol acknowledgement
            dialog.exec()
            return  # Stop eksekusi quit

        self._quitting = True
        QApplication.instance().quit()

    def closeEvent(self, event):
        if getattr(self, "_quitting", False):
            event.accept()
            return

        event.ignore()
        self.hide()
        self.tray.showMessage(
            "Adyton Crypt Berjalan",
            "Aplikasi di-minimize ke System Tray untuk memproses di latar belakang.",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )
        logger.info("Window di-minimize ke System Tray.")

    def _build_header(self, parent_layout):
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        lay_kiri = QHBoxLayout()
        lay_kiri.setSpacing(15)

        lbl_custom_logo = QLabel()

        pixmap = QPixmap("assets/logo_adyton2.png")

        if not pixmap.isNull():
            scaled_pixmap = pixmap.scaledToHeight(
                45, Qt.TransformationMode.SmoothTransformation
            )
            lbl_custom_logo.setPixmap(scaled_pixmap)
        else:
            lbl_custom_logo.setText("LOGO NOT FOUND")
            lbl_custom_logo.setStyleSheet("color: red; font-weight: bold;")

        lay_kiri.addWidget(lbl_custom_logo)

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
        self.stacked_tabs.setCurrentIndex(new_idx)

    def showEvent(self, event):
        super().showEvent(event)
        self._anim_window = QPropertyAnimation(self, b"windowOpacity")
        self._anim_window.setDuration(100)
        self._anim_window.setStartValue(0.0)
        self._anim_window.setEndValue(1.0)
        self._anim_window.start()
