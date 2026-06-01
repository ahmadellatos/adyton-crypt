"""
Modul: app.py
Deskripsi: Antarmuka jendela utama (Main Window) dari aplikasi Adyton Crypt.
           Mengelola routing tab, System Tray, dan kontrol jendela frameless.
           Dilengkapi Modern UWP Toast Notification menggunakan Winotify.
"""

import os
import sys
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

from .styles import CLR_TEXT_MUTED
from loguru import logger
from qframelesswindow import FramelessMainWindow
from core.paths import get_asset_path

try:
    from winotify import Notification, audio

    HAS_WINOTIFY = True
except ImportError:
    HAS_WINOTIFY = False

from .tab_kunci import TabKunci
from .tab_buka import TabBuka
from .constants import APP_NAME, APP_VERSION, APP_AUMID
from .widgets import CustomTitleBar
from .menus import AccessibleCenteredMenu, CenteredMenuAction
from .dialogs import ModernMessageBox

# =========================================================================
# MAIN WINDOW
# =========================================================================


class AppBrankas(FramelessMainWindow):
    def __init__(self):
        super().__init__()

        self._quitting = False
        self.setMinimumSize(1100, 700)
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
        # Initial window size (no compact mode - always full design size)
        self.resize(1100, 700)
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

        content_container = QWidget()
        content_lay = QVBoxLayout(content_container)
        content_lay.setContentsMargins(30, 8, 30, 15)
        content_lay.setSpacing(22)

        self._build_header(content_lay)

        self.stacked_tabs = QStackedWidget()
        self.tab_kunci = TabKunci()
        self.tab_buka = TabBuka()
        self.stacked_tabs.addWidget(self.tab_kunci)
        self.stacked_tabs.addWidget(self.tab_buka)

        self.tab_kunci.worker_started.connect(
            lambda worker: self._bind_worker_to_tray(worker, "kunci")
        )
        self.tab_buka.worker_started.connect(
            lambda worker: self._bind_worker_to_tray(worker, "buka")
        )
        self.tab_kunci.system_notification.connect(self._show_system_notif)
        self.tab_buka.system_notification.connect(self._show_system_notif)
        self.tab_buka.status_changed.connect(self._set_header_security_status)

        content_lay.addWidget(self.stacked_tabs, 1)

        # Systematic tab order at main window level
        self.setTabOrder(self.btn_nav_kunci, self.btn_nav_buka)
        # The content inside the active tab will manage its own tab order.
        # We connect the action button focus when the tab changes.
        self.tab_group.buttonClicked.connect(self._update_action_button_tab_order)

        self._build_footer(content_lay)
        main_layout.addWidget(content_container, 1)

        # Initial tab order setup
        self._update_action_button_tab_order()

    def _init_tray(self, app_icon: QIcon) -> None:
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(
            app_icon
            if not app_icon.isNull()
            else qta.icon("mdi6.shield-lock", color="white")
        )

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

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _is_busy(self) -> bool:
        """Return True jika ada worker enkripsi atau dekripsi yang sedang berjalan."""
        return (
            self.tab_kunci.worker is not None and self.tab_kunci.worker.isRunning()
        ) or (self.tab_buka.worker is not None and self.tab_buka.worker.isRunning())

    # =========================================================================
    # TRAY
    # =========================================================================

    def _on_tray_click(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()

    def _bind_worker_to_tray(self, worker, source_tab: str) -> None:
        """Bind progress/finished signals dari worker baru ke tray tooltip.

        Navigasi tab tetap aktif agar UI tidak terasa freeze. Yang dikunci
        hanyalah aksi memulai operasi crypto lain di tab sebelah.
        """
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
        """Kompatibilitas lama: navigasi tidak lagi dikunci saat proses.

        User tetap boleh pindah tab untuk melihat UI. Operasi baru dikunci
        lewat _set_operation_lock().
        """
        self.btn_nav_kunci.setEnabled(True)
        self.btn_nav_buka.setEnabled(True)

    def _set_operation_lock(self, source_tab: str, busy: bool) -> None:
        """Kunci aksi crypto di tab lain tanpa mematikan navigasi tab."""
        self.btn_nav_kunci.setEnabled(True)
        self.btn_nav_buka.setEnabled(True)
        if busy:
            self.btn_nav_kunci.setToolTip(
                "Bisa pindah tab, tetapi operasi baru dikunci sampai proses selesai."
            )
            self.btn_nav_buka.setToolTip(
                "Bisa pindah tab, tetapi operasi baru dikunci sampai proses selesai."
            )
        else:
            self.btn_nav_kunci.setToolTip("")
            self.btn_nav_buka.setToolTip("")

        self.tab_kunci.set_external_busy(busy and source_tab != "kunci")
        self.tab_buka.set_external_busy(busy and source_tab != "buka")

    def _set_header_security_status(
        self, title: str, subtitle: str, state: str = "idle"
    ) -> None:
        """Update status keamanan kanan atas sesuai state Tab Buka."""
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
        """Tampilkan UWP Toast via winotify. Fallback ke Qt tray jika tidak tersedia."""
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

    def _build_header(self, parent_layout: QVBoxLayout) -> None:
        # Wrapper header dengan subtle separator
        header_wrapper = QFrame()
        header_wrapper.setObjectName("HeaderWrapper")
        header_wrapper.setContentsMargins(0, 0, 0, 0)

        header_layout = QHBoxLayout(header_wrapper)
        header_layout.setContentsMargins(0, 6, 0, 6)  # lebih rapat tanpa separator
        header_layout.setSpacing(20)

        # Kiri — logo
        lay_kiri = QHBoxLayout()
        lay_kiri.setSpacing(12)
        lbl_logo = QLabel()
        pixmap = QPixmap(get_asset_path("assets/logo_adyton2.png"))
        if not pixmap.isNull():
            lbl_logo.setPixmap(
                pixmap.scaledToHeight(
                    40, Qt.TransformationMode.SmoothTransformation
                )  # sedikit lebih kecil untuk balance
            )
        else:
            lbl_logo.setText("LOGO NOT FOUND")
            lbl_logo.setStyleSheet("color: red; font-weight: 700;")
        lay_kiri.addWidget(lbl_logo)
        header_layout.addLayout(lay_kiri)
        header_layout.addStretch()

        # Tengah — tab navigation
        tab_container = QFrame()
        tab_container.setObjectName("TabContainer")
        tab_container.setFixedSize(340, 46)  # lebih tipis sesuai request
        lay_tabs = QHBoxLayout(tab_container)
        lay_tabs.setContentsMargins(4, 3, 4, 3)
        lay_tabs.setSpacing(4)

        self.btn_nav_kunci = self._make_tab_button(" Kunci Folder", "mdi6.lock")
        self.btn_nav_kunci.setChecked(True)
        self.btn_nav_kunci.setAccessibleName("Tab Kunci Folder")

        self.btn_nav_buka = self._make_tab_button(
            " Buka Brankas", "mdi6.lock-open-variant"
        )
        self.btn_nav_buka.setAccessibleName("Tab Buka Brankas")

        self.tab_group = QButtonGroup(self)
        self.tab_group.addButton(self.btn_nav_kunci, 0)
        self.tab_group.addButton(self.btn_nav_buka, 1)
        self.tab_group.buttonClicked.connect(self._on_tab_changed)

        lay_tabs.addWidget(self.btn_nav_kunci)
        lay_tabs.addWidget(self.btn_nav_buka)
        header_layout.addWidget(tab_container)
        header_layout.addStretch()

        # Kanan — status enkripsi (lebih premium)
        lay_kanan = QHBoxLayout()
        lay_kanan.setSpacing(12)

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

        lay_kanan.addWidget(self.lbl_status_icon)
        lay_kanan.addLayout(lay_status)
        header_layout.addLayout(lay_kanan)

        parent_layout.addWidget(header_wrapper)

    def _make_tab_button(self, label: str, icon_name: str) -> QPushButton:
        """Factory untuk tombol navigasi tab."""
        btn = QPushButton(label)
        btn.setIcon(qta.icon(icon_name, color="#8B95A5", color_on="white"))
        btn.setIconSize(QSize(18, 18))
        btn.setObjectName("TabBtn")
        btn.setCheckable(True)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return btn

    def _build_footer(self, parent_layout: QVBoxLayout) -> None:
        footer_wrapper = QFrame()
        footer_wrapper.setObjectName("MainFooter")

        lay_footer = QHBoxLayout(footer_wrapper)
        lay_footer.setContentsMargins(0, 12, 0, 4)  # Premium breathing
        lay_footer.setSpacing(12)

        lay_safe = QHBoxLayout()
        lay_safe.setSpacing(6)
        lbl_safe_icon = QLabel()
        lbl_safe_icon.setPixmap(
            qta.icon("mdi6.shield-check", color=CLR_TEXT_MUTED).pixmap(15, 15)
        )
        lbl_safe_text = QLabel("Password tidak dikirim ke mana pun")
        lbl_safe_text.setObjectName("MutedText")
        lay_safe.addWidget(lbl_safe_icon)
        lay_safe.addWidget(lbl_safe_text)

        lay_ver = QHBoxLayout()
        lay_ver.setSpacing(6)
        lbl_ver_text = QLabel(f"Version {APP_VERSION}")
        lbl_ver_text.setObjectName("MutedText")
        lbl_ver_icon = QLabel()
        lbl_ver_icon.setPixmap(
            qta.icon("mdi6.check-circle", color=CLR_TEXT_MUTED).pixmap(15, 15)
        )
        lay_ver.addWidget(lbl_ver_text)
        lay_ver.addWidget(lbl_ver_icon)

        lay_footer.addLayout(lay_safe)
        lay_footer.addStretch()
        lay_footer.addLayout(lay_ver)
        parent_layout.addWidget(footer_wrapper)

    # =========================================================================
    # EVENT HANDLERS
    # =========================================================================

    def _on_tab_changed(self, button: QPushButton) -> None:
        new_idx = self.tab_group.id(button)
        if new_idx != self.stacked_tabs.currentIndex():
            self.stacked_tabs.setCurrentIndex(new_idx)

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
        self.stacked_tabs.setCurrentIndex(1)
        self.tab_buka.auto_load_file(path)

    def _update_action_button_tab_order(self):
        """Ensure logical tab order from navigation to the current tab's action button."""
        current_tab = self.stacked_tabs.currentWidget()
        if hasattr(current_tab, "btn_aksi"):
            self.setTabOrder(self.btn_nav_buka, current_tab.btn_aksi)
