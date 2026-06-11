"""
Modul: app.py
Deskripsi: Antarmuka jendela utama (Main Window) dari aplikasi Adyton Crypt.
           Mengelola routing tab, System Tray, dan kontrol jendela frameless.
           Dilengkapi Modern UWP Toast Notification menggunakan Winotify.
"""

import os

import qtawesome as qta
from loguru import logger
from PySide6.QtCore import QPropertyAnimation, QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)
from qframelesswindow import FramelessMainWindow

from core.paths import get_asset_path

from .styles import CLR_TEXT_MUTED

try:
    from winotify import Notification, audio

    HAS_WINOTIFY = True
except ImportError:
    HAS_WINOTIFY = False

from .constants import APP_AUMID, APP_NAME, APP_VERSION
from .dialogs import ModernMessageBox
from .menus import AccessibleCenteredMenu, CenteredMenuAction
from .tab_buka import TabBuka
from .tab_kunci import TabKunci
from .tab_teks import TabTeks  # <-- [TAMBAHAN] Import Tab Teks
from .widgets import CustomTitleBar

# =========================================================================
# MAIN WINDOW
# =========================================================================


class AppBrankas(FramelessMainWindow):
    def __init__(self):
        super().__init__()

        self._quitting = False
        self.setMinimumSize(1280, 720)
        self.setObjectName("MainWindow")

        app_icon = self._load_app_icon()
        self.setWindowIcon(app_icon)

        self._init_ui()
        self._init_tray(app_icon)
        self._center_window()

    # =========================================================================
    # INIT
    # =========================================================================

    def _load_app_icon(self) -> QIcon:
        """Load ikon aplikasi dari .ico, fallback ke PNG jika gagal."""
        icon = QIcon(get_asset_path("assets/icon_adyton.ico"))
        if icon.isNull():
            logger.warning("File .ico gagal dimuat. Menggunakan PNG fallback.")
            icon = QIcon(get_asset_path("assets/logo_adyton2.png"))
        return icon

    def _center_window(self) -> None:
        self.resize(1300, 740)
        center_point = QApplication.primaryScreen().availableGeometry().center()
        frame_geo = self.frameGeometry()
        frame_geo.moveCenter(center_point)
        self.move(frame_geo.topLeft())

    def _init_ui(self) -> None:
        central_widget = QWidget()
        central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 32, 0, 0)
        main_layout.setSpacing(0)

        self.title_bar = CustomTitleBar(self)
        self.setTitleBar(self.title_bar)

        # Body: split horizontal — sidebar navigasi (kiri) + area konten (kanan)
        body = QWidget()
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)

        self._build_sidebar(body_lay)  # logo + MODE + tombol navigasi vertikal

        content_container = QWidget()
        content_lay = QVBoxLayout(content_container)
        content_lay.setContentsMargins(30, 8, 30, 15)
        content_lay.setSpacing(22)

        self._build_topbar(content_lay)  # status AES-256 GCM tetap di kanan atas

        self.stacked_tabs = QStackedWidget()
        self.tab_kunci = TabKunci()
        self.tab_buka = TabBuka()
        self.tab_teks = TabTeks()  # <-- [TAMBAHAN] Inisialisasi Tab Teks

        self.stacked_tabs.addWidget(self.tab_kunci)
        self.stacked_tabs.addWidget(self.tab_buka)
        self.stacked_tabs.addWidget(self.tab_teks)  # <-- [TAMBAHAN] Masukkan ke StackedWidget

        self.tab_kunci.worker_started.connect(
            lambda worker: self._bind_worker_to_tray(worker, "kunci")
        )
        self.tab_buka.worker_started.connect(
            lambda worker: self._bind_worker_to_tray(worker, "buka")
        )
        self.tab_kunci.system_notification.connect(self._show_system_notif)
        self.tab_buka.system_notification.connect(self._show_system_notif)
        self.tab_teks.system_notification.connect(
            self._show_system_notif
        )  # <-- [TAMBAHAN] Bind Notifikasi Teks
        self.tab_buka.status_changed.connect(self._set_header_security_status)

        content_lay.addWidget(self.stacked_tabs, 1)
        self._build_footer(content_lay)

        body_lay.addWidget(content_container, 1)
        main_layout.addWidget(body, 1)

        # Tab order navigation
        self.setTabOrder(self.btn_nav_kunci, self.btn_nav_buka)
        self.setTabOrder(self.btn_nav_buka, self.btn_nav_teks)
        self.tab_group.buttonClicked.connect(self._update_action_button_tab_order)

        self._update_action_button_tab_order()
        self._update_page_header(0)  # judul awal: Kunci Folder

    def _init_tray(self, app_icon: QIcon) -> None:
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(
            app_icon if not app_icon.isNull() else qta.icon("mdi6.shield-lock", color="white")
        )

        tray_menu = AccessibleCenteredMenu()

        act_show = CenteredMenuAction("Buka Adyton Crypt", "mdi6.window-maximize", parent=tray_menu)
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

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _is_busy(self) -> bool:
        return (self.tab_kunci.worker is not None and self.tab_kunci.worker.isRunning()) or (
            self.tab_buka.worker is not None and self.tab_buka.worker.isRunning()
        )

    # =========================================================================
    # TRAY & LOCKS
    # =========================================================================

    def _on_tray_click(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()

    def _bind_worker_to_tray(self, worker, source_tab: str) -> None:
        if not worker:
            return

        self.tray.setToolTip(f"{APP_NAME} — Sedang memproses...")
        worker.progress.connect(
            lambda v: self.tray.setToolTip(f"{APP_NAME} — Progress {int(v * 100)}%")
        )
        self._set_operation_lock(source_tab, True)
        worker.finished.connect(lambda: self.tray.setToolTip(APP_NAME))
        worker.finished.connect(lambda: self._set_operation_lock(source_tab, False))

    def _set_navigation_busy(self, busy: bool) -> None:
        self.btn_nav_kunci.setEnabled(True)
        self.btn_nav_buka.setEnabled(True)
        self.btn_nav_teks.setEnabled(True)

    def _set_operation_lock(self, source_tab: str, busy: bool) -> None:
        self.btn_nav_kunci.setEnabled(True)
        self.btn_nav_buka.setEnabled(True)
        self.btn_nav_teks.setEnabled(True)

        msg = "Bisa pindah tab, tetapi operasi baru dikunci sampai proses selesai." if busy else ""
        self.btn_nav_kunci.setToolTip(msg)
        self.btn_nav_buka.setToolTip(msg)
        self.btn_nav_teks.setToolTip(msg)

        self.tab_kunci.set_external_busy(busy and source_tab != "kunci")
        self.tab_buka.set_external_busy(busy and source_tab != "buka")
        self.tab_teks.set_external_busy(
            busy and source_tab != "teks"
        )  # <-- [TAMBAHAN] Lock tab teks jika file sedang diproses

    def _set_header_security_status(self, title: str, subtitle: str, state: str = "idle") -> None:
        colors = {
            "idle": "#00D2C8",
            "ready": "#00D2C8",
            "busy": "#F1C40F",
            "success": "#2ECC71",
            "warn": "#F1C40F",
            "error": "#E74C3C",
        }
        icons = {
            "idle": "mdi6.shield-check",
            "ready": "mdi6.shield-search",
            "busy": "mdi6.shield-sync",
            "success": "mdi6.shield-check",
            "warn": "mdi6.alert-circle",
            "error": "mdi6.shield-alert",
        }
        color = colors.get(state, "#00D2C8")
        icon_name = icons.get(state, "mdi6.shield-check")
        self.lbl_status_icon.setPixmap(qta.icon(icon_name, color=color).pixmap(28, 28))
        self.lbl_stat_title.setText(title)
        self.lbl_stat_sub.setText(subtitle)
        self.lbl_stat_sub.setStyleSheet(f"color: {color}; font-weight: 600;")

    # =========================================================================
    # NOTIFIKASI
    # =========================================================================

    def _show_system_notif(self, title: str, message: str) -> None:
        if HAS_WINOTIFY:
            try:
                icon_path = os.path.abspath(get_asset_path("assets/icon_adyton.png"))
                toast = Notification(
                    app_id=APP_AUMID,
                    title=title,
                    msg=message,
                    icon=icon_path,
                    duration="short",
                )
                toast.set_audio(audio.Default, loop=False)
                toast.show()
                return
            except Exception as e:
                logger.warning(f"Winotify gagal memunculkan notif: {e}")

        logger.warning("Menggunakan notifikasi fallback Qt.")
        self.tray.showMessage(
            title,
            message,
            QIcon(get_asset_path("assets/icon_adyton.png")),
            5000,
        )

    # =========================================================================
    # QUIT
    # =========================================================================

    def _quit_sepenuhnya(self) -> None:
        if self._is_busy():
            self.showNormal()
            self.activateWindow()
            dialog = ModernMessageBox(
                title="Proses Sedang Berjalan",
                message=(
                    "Aplikasi sedang memproses enkripsi/dekripsi file.\n\n"
                    "Mematikan aplikasi secara paksa sekarang dapat menyebabkan "
                    "file korup atau data hilang. Silakan tunggu hingga proses "
                    "selesai atau batalkan proses terlebih dahulu."
                ),
                icon_name="mdi6.alert-decagram",
                icon_color="#E74C3C",
                parent=self,
            )
            dialog.btn_yes.setText("Mengerti")
            dialog.btn_cancel.hide()
            dialog.exec()
            return

        self._quitting = True
        QApplication.instance().quit()

    def closeEvent(self, event) -> None:
        if self._quitting:
            event.accept()
            return

        event.ignore()
        self.hide()
        self._show_system_notif(
            f"{APP_NAME} Berjalan",
            "Aplikasi di-minimize ke System Tray untuk memproses di latar belakang.",
        )
        logger.info("Window di-minimize ke System Tray.")

    # =========================================================================
    # UI BUILDERS
    # =========================================================================

    def _build_sidebar(self, parent_layout: QHBoxLayout) -> None:
        """Sidebar kiri: logo, label MODE, dan tombol navigasi vertikal."""
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)

        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(18, 20, 18, 18)
        lay.setSpacing(6)

        # Logo di atas sidebar
        lbl_logo = QLabel()
        pixmap = QPixmap(get_asset_path("assets/logo_adyton2.png"))
        if not pixmap.isNull():
            lbl_logo.setPixmap(
                pixmap.scaledToHeight(36, Qt.TransformationMode.SmoothTransformation)
            )
        else:
            lbl_logo.setText("ADYTON")
            lbl_logo.setStyleSheet("color: white; font-weight: 700; font-size: 13pt;")
        lay.addWidget(lbl_logo)
        lay.addSpacing(24)

        # Label seksi
        lbl_mode = QLabel("MODE")
        lbl_mode.setObjectName("SidebarSection")
        lay.addWidget(lbl_mode)
        lay.addSpacing(2)

        # Tombol navigasi (vertikal)
        self.btn_nav_kunci = self._make_tab_button(" Kunci Folder", "mdi6.lock")
        self.btn_nav_kunci.setChecked(True)
        self.btn_nav_kunci.setAccessibleName("Tab Kunci Folder")

        self.btn_nav_buka = self._make_tab_button(" Buka Brankas", "mdi6.lock-open-variant")
        self.btn_nav_buka.setAccessibleName("Tab Buka Brankas")

        self.btn_nav_teks = self._make_tab_button(" Teks", "mdi6.file-lock")
        self.btn_nav_teks.setAccessibleName("Tab Enkripsi Teks")

        self.tab_group = QButtonGroup(self)
        self.tab_group.addButton(self.btn_nav_kunci, 0)
        self.tab_group.addButton(self.btn_nav_buka, 1)
        self.tab_group.addButton(self.btn_nav_teks, 2)
        self.tab_group.buttonClicked.connect(self._on_tab_changed)

        lay.addWidget(self.btn_nav_kunci)
        lay.addWidget(self.btn_nav_buka)
        lay.addWidget(self.btn_nav_teks)
        lay.addStretch()

        parent_layout.addWidget(sidebar)

    def _build_topbar(self, parent_layout: QVBoxLayout) -> None:
        """Bar atas area konten: status AES-256 GCM (tetap di kanan atas)."""
        topbar = QFrame()
        topbar.setObjectName("HeaderWrapper")
        topbar.setContentsMargins(0, 0, 0, 0)

        lay = QHBoxLayout(topbar)
        lay.setContentsMargins(0, 6, 0, 6)
        lay.setSpacing(12)

        # Kiri — judul + subtitle per-tab (diperbarui di _update_page_header)
        lay_page = QVBoxLayout()
        lay_page.setSpacing(2)
        lay_page.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.lbl_page_title = QLabel("")
        self.lbl_page_title.setObjectName("PageTitle")
        self.lbl_page_sub = QLabel("")
        self.lbl_page_sub.setObjectName("PageSubtitle")
        lay_page.addWidget(self.lbl_page_title)
        lay_page.addWidget(self.lbl_page_sub)
        lay.addLayout(lay_page)
        lay.addStretch()

        self.lbl_status_icon = QLabel()
        self.lbl_status_icon.setPixmap(
            qta.icon("mdi6.shield-check", color="#00D2C8").pixmap(28, 28)
        )

        lay_status = QVBoxLayout()
        lay_status.setSpacing(1)
        lay_status.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.lbl_stat_title = QLabel("AES-256 • GCM")
        self.lbl_stat_title.setObjectName("MutedText")
        self.lbl_stat_sub = QLabel("Enkripsi lokal aktif")
        self.lbl_stat_sub.setObjectName("AccentText")
        lay_status.addWidget(self.lbl_stat_title)
        lay_status.addWidget(self.lbl_stat_sub)

        lay.addWidget(self.lbl_status_icon)
        lay.addLayout(lay_status)
        parent_layout.addWidget(topbar)

    def _make_tab_button(self, label: str, icon_name: str) -> QPushButton:
        """Factory tombol navigasi sidebar (vertikal, teks rata kiri)."""
        btn = QPushButton(label)
        btn.setIcon(qta.icon(icon_name, color="#8B95A5", color_on="white"))
        btn.setIconSize(QSize(18, 18))
        btn.setObjectName("NavBtn")
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(44)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return btn

    def _build_footer(self, parent_layout: QVBoxLayout) -> None:
        footer_wrapper = QFrame()
        footer_wrapper.setObjectName("MainFooter")

        lay_footer = QHBoxLayout(footer_wrapper)
        lay_footer.setContentsMargins(0, 12, 0, 4)
        lay_footer.setSpacing(12)

        lay_safe = QHBoxLayout()
        lay_safe.setSpacing(6)
        lbl_safe_icon = QLabel()
        lbl_safe_icon.setPixmap(qta.icon("mdi6.shield-check", color=CLR_TEXT_MUTED).pixmap(15, 15))
        lbl_safe_text = QLabel("Password tidak dikirim ke mana pun")
        lbl_safe_text.setObjectName("MutedText")
        lay_safe.addWidget(lbl_safe_icon)
        lay_safe.addWidget(lbl_safe_text)

        lay_ver = QHBoxLayout()
        lay_ver.setSpacing(6)
        lbl_ver_text = QLabel(f"Version {APP_VERSION}")
        lbl_ver_text.setObjectName("MutedText")
        lbl_ver_icon = QLabel()
        lbl_ver_icon.setPixmap(qta.icon("mdi6.check-circle", color=CLR_TEXT_MUTED).pixmap(15, 15))
        lay_ver.addWidget(lbl_ver_text)
        lay_ver.addWidget(lbl_ver_icon)

        lay_footer.addLayout(lay_safe)
        lay_footer.addStretch()
        lay_footer.addLayout(lay_ver)
        parent_layout.addWidget(footer_wrapper)

    # =========================================================================
    # EVENT HANDLERS
    # =========================================================================

    # Judul + subtitle yang tampil di kiri atas untuk tiap tab (indeks stack).
    PAGE_HEADERS = {
        0: ("Kunci Folder", "Pilih target, buat password yang kuat, lalu enkripsi."),
        1: ("Buka Brankas", "Pilih brankas terenkripsi dan masukkan password untuk membuka."),
        2: ("Teks", "Enkripsi atau dekripsi teks secara langsung dengan password."),
    }

    def _update_page_header(self, index: int) -> None:
        title, subtitle = self.PAGE_HEADERS.get(index, ("", ""))
        self.lbl_page_title.setText(title)
        self.lbl_page_sub.setText(subtitle)

    def _on_tab_changed(self, button: QPushButton) -> None:
        new_idx = self.tab_group.id(button)
        if new_idx != self.stacked_tabs.currentIndex():
            self.stacked_tabs.setCurrentIndex(new_idx)
        self._update_page_header(new_idx)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._anim_window = QPropertyAnimation(self, b"windowOpacity")
        self._anim_window.setDuration(100)
        self._anim_window.setStartValue(0.0)
        self._anim_window.setEndValue(1.0)
        self._anim_window.start()

    def buka_file_dari_luar(self, path: str) -> None:
        logger.info(f"File Association dipicu untuk file: {path}")
        self.btn_nav_buka.setChecked(True)
        self.btn_nav_kunci.setChecked(False)
        self.btn_nav_teks.setChecked(False)
        self.stacked_tabs.setCurrentIndex(1)
        self._update_page_header(1)
        self.tab_buka.auto_load_file(path)

    def _update_action_button_tab_order(self):
        current_tab = self.stacked_tabs.currentWidget()
        if hasattr(current_tab, "btn_aksi"):
            self.setTabOrder(self.btn_nav_teks, current_tab.btn_aksi)
