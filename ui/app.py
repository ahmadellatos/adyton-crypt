"""
Modul: app.py
Deskripsi: Antarmuka jendela utama (Main Window) dari aplikasi Adyton Crypt.
           Mengelola routing tab, System Tray, dan kontrol jendela frameless.
           Dilengkapi Modern UWP Toast Notification menggunakan Winotify.
"""

import os

import qtawesome as qta
from loguru import logger
from PySide6.QtCore import QPropertyAnimation, QSettings, QSize, Qt, QTimer
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
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from qframelesswindow import FramelessMainWindow

from core.paths import get_asset_path

from .styles import CLR_ACCENT, CLR_TEXT_DIM, CLR_TEXT_MUTED

try:
    from winotify import Notification, audio

    HAS_WINOTIFY = True
except ImportError:
    HAS_WINOTIFY = False

from .constants import APP_AUMID, APP_NAME, APP_VERSION
from .dialogs import ModernMessageBox
from .menus import AccessibleCenteredMenu, CenteredMenuAction
from .onboarding import OnboardingView
from .tab_buka import TabBuka
from .tab_kunci import TabKunci
from .tab_manage import TabManage
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
        main_layout.setContentsMargins(0, 46, 0, 0)  # ruang untuk titlebar 46px
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
        content_lay.setContentsMargins(32, 10, 32, 16)
        content_lay.setSpacing(22)

        self._build_topbar(content_lay)  # status AES-256 GCM tetap di kanan atas

        self.stacked_tabs = QStackedWidget()
        self.tab_kunci = TabKunci()
        self.tab_buka = TabBuka()
        self.tab_teks = TabTeks()  # <-- [TAMBAHAN] Inisialisasi Tab Teks
        self.tab_manage = TabManage()

        self.stacked_tabs.addWidget(self.tab_kunci)
        self.stacked_tabs.addWidget(self.tab_buka)
        self.stacked_tabs.addWidget(self.tab_teks)  # <-- [TAMBAHAN] Masukkan ke StackedWidget
        self.stacked_tabs.addWidget(self.tab_manage)

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
        self.tab_manage.system_notification.connect(self._show_system_notif)

        # Status pill keamanan: tiap tab punya status sendiri; pill menampilkan
        # status tab yang sedang aktif (di-refresh saat ganti tab).
        self._default_status = ("AES-256 • GCM", "Local encryption active", "idle")
        self._tab_status = {
            0: self._default_status,
            1: self._default_status,
            2: self._default_status,
            3: self._default_status,
        }

        # Status pill kembali ke idle setelah 5 detik tanpa interaksi (kecuali
        # saat operasi sedang berjalan / state "busy", atau sudah idle).
        self._status_idle_timer = QTimer(self)
        self._status_idle_timer.setSingleShot(True)
        self._status_idle_timer.setInterval(5000)
        self._status_idle_timer.timeout.connect(self._revert_status_to_idle)

        self.tab_kunci.status_changed.connect(lambda t, s, st: self._on_tab_status(0, t, s, st))
        self.tab_buka.status_changed.connect(lambda t, s, st: self._on_tab_status(1, t, s, st))
        self.tab_teks.status_changed.connect(lambda t, s, st: self._on_tab_status(2, t, s, st))
        self.tab_manage.status_changed.connect(lambda t, s, st: self._on_tab_status(3, t, s, st))

        content_lay.addWidget(self.stacked_tabs, 1)
        self._build_footer(content_lay)

        body_lay.addWidget(content_container, 1)

        # Body stack: index 0 = tab UI normal, index 1 = onboarding first-run.
        # Onboarding tampil di bawah titlebar mengisi badan jendela (menggantikan
        # sidebar+konten) saat flag QSettings belum diset.
        self.body_stack = QStackedWidget()
        self.body_stack.addWidget(body)
        self._onboarding = None
        main_layout.addWidget(self.body_stack, 1)

        # Tab order navigation
        self.setTabOrder(self.btn_nav_kunci, self.btn_nav_buka)
        self.setTabOrder(self.btn_nav_buka, self.btn_nav_teks)
        self.setTabOrder(self.btn_nav_teks, self.btn_nav_manage)
        self.tab_group.buttonClicked.connect(self._update_action_button_tab_order)

        self._update_action_button_tab_order()
        self._update_page_header(0)  # judul awal: Kunci Folder

        self._maybe_start_onboarding()  # tampilkan wizard first-run bila perlu

    # =========================================================================
    # ONBOARDING (FIRST-RUN)
    # =========================================================================

    def _maybe_start_onboarding(self) -> None:
        """Tampilkan onboarding bila flag QSettings 'onboarding/completed' belum diset."""
        settings = QSettings()
        if not settings.value("onboarding/completed", False, type=bool):
            self._show_onboarding()

    def _show_onboarding(self) -> None:
        """Bangun (sekali) lalu tampilkan OnboardingView, mulai dari splash."""
        if self._onboarding is None:
            self._onboarding = OnboardingView()
            self._onboarding.completed.connect(self._finish_onboarding)
            self.body_stack.addWidget(self._onboarding)
        self.body_stack.setCurrentWidget(self._onboarding)
        self._onboarding.start()

    def _finish_onboarding(self) -> None:
        """Tandai onboarding selesai dan masuk ke UI tab normal."""
        QSettings().setValue("onboarding/completed", True)
        self.body_stack.setCurrentIndex(0)
        self.btn_nav_kunci.setFocus(Qt.FocusReason.OtherFocusReason)

    def _replay_onboarding(self) -> None:
        """Putar ulang onboarding dari tray; bawa window ke depan lebih dulu."""
        self.showNormal()
        self.activateWindow()
        self.raise_()
        self._show_onboarding()

    def _init_tray(self, app_icon: QIcon) -> None:
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(
            app_icon if not app_icon.isNull() else qta.icon("mdi6.shield-outline", color="white")
        )

        tray_menu = AccessibleCenteredMenu()

        act_show = CenteredMenuAction("Open Adyton Crypt", "mdi6.window-maximize", parent=tray_menu)
        act_show.triggered.connect(self.showNormal)
        tray_menu.addAction(act_show)

        act_intro = CenteredMenuAction(
            "Replay Introduction", "mdi6.compass-outline", parent=tray_menu
        )
        act_intro.triggered.connect(self._replay_onboarding)
        tray_menu.addAction(act_intro)

        act_quit = CenteredMenuAction(
            "Quit Completely", "mdi6.power", icon_color="#E89089", parent=tray_menu
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

        self.tray.setToolTip(f"{APP_NAME} — Processing...")
        worker.progress.connect(
            lambda v: self.tray.setToolTip(f"{APP_NAME} — Progress {int(v * 100)}%")
        )
        self._set_operation_lock(source_tab, True)
        worker.finished.connect(lambda: self.tray.setToolTip(APP_NAME))
        worker.finished.connect(lambda: self._set_operation_lock(source_tab, False))

    def _set_operation_lock(self, source_tab: str, busy: bool) -> None:
        self.btn_nav_kunci.setEnabled(True)
        self.btn_nav_buka.setEnabled(True)
        self.btn_nav_teks.setEnabled(True)

        msg = (
            "You can switch tabs, but new operations are paused until the current one finishes."
            if busy
            else ""
        )
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
            "idle": CLR_ACCENT,
            "ready": CLR_ACCENT,
            "busy": "#E8A855",
            "success": "#86CBA3",
            "warn": "#E8A855",
            "error": "#E89089",
        }
        icons = {
            "idle": "mdi6.shield-check-outline",
            "ready": "mdi6.shield-outline",
            "busy": "mdi6.shield-outline",
            "success": "mdi6.shield-check-outline",
            "warn": "mdi6.alert-circle-outline",
            "error": "mdi6.shield-alert-outline",
        }
        color = colors.get(state, CLR_ACCENT)
        icon_name = icons.get(state, "mdi6.shield-check-outline")
        self.lbl_status_icon.setPixmap(qta.icon(icon_name, color=color).pixmap(16, 16))
        self.lbl_status_text.setText(title)
        self.lbl_status_text.setStyleSheet(f"color: {color}; font-weight: 700; font-size: 9pt;")
        self.status_pill.setToolTip(subtitle)
        self.status_pill.setProperty("state", state)
        self.status_pill.style().unpolish(self.status_pill)
        self.status_pill.style().polish(self.status_pill)

        # Auto-revert ke idle setelah 5 detik tanpa interaksi. Saat "busy"
        # (operasi berjalan) atau sudah "idle", timer tidak berjalan.
        if state in ("idle", "busy"):
            self._status_idle_timer.stop()
        else:
            self._status_idle_timer.start()

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
                title="Operation in Progress",
                message=(
                    "Adyton is currently encrypting or decrypting a file.\n\n"
                    "Quitting now may corrupt the file or cause data loss. "
                    "Please wait for it to finish, or cancel the operation first."
                ),
                icon_name="mdi6.alert-octagon-outline",
                icon_color="#E89089",
                parent=self,
            )
            dialog.btn_yes.setText("Got it")
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
            f"{APP_NAME} is still running",
            "Adyton is in the System Tray. Any active operations will continue in the background.",
        )
        logger.info("Window di-minimize ke System Tray.")

    # =========================================================================
    # UI BUILDERS
    # =========================================================================

    def _build_sidebar(self, parent_layout: QHBoxLayout) -> None:
        """Rail navigasi kiri: lebar 96px, logo + tombol ikon (icon-only)."""
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(96)

        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(12, 20, 12, 22)
        lay.setSpacing(10)
        lay.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # Logo di puncak rail (ikon, dipusatkan)
        lbl_logo = QLabel()
        lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(get_asset_path("assets/icon_adyton.png"))
        if not pixmap.isNull():
            lbl_logo.setPixmap(
                pixmap.scaledToHeight(34, Qt.TransformationMode.SmoothTransformation)
            )
        else:
            lbl_logo.setText("A")
            lbl_logo.setStyleSheet(f"color: {CLR_ACCENT}; font-weight: 800; font-size: 16pt;")
        lay.addWidget(lbl_logo, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(20)

        # Tombol navigasi (ikon + label kecil di bawahnya)
        self.btn_nav_kunci = self._make_tab_button("Lock", "mdi6.lock-outline", "Lock Folder tab")
        self.btn_nav_kunci.setChecked(True)

        self.btn_nav_buka = self._make_tab_button(
            "Open", "mdi6.lock-open-variant-outline", "Open Vault tab"
        )

        self.btn_nav_teks = self._make_tab_button(
            "Text", "mdi6.text-box-outline", "Encrypt Text tab"
        )

        self.btn_nav_manage = self._make_tab_button(
            "Manage", "mdi6.cog-outline", "Manage Vault tab"
        )

        self.tab_group = QButtonGroup(self)
        self.tab_group.addButton(self.btn_nav_kunci, 0)
        self.tab_group.addButton(self.btn_nav_buka, 1)
        self.tab_group.addButton(self.btn_nav_teks, 2)
        self.tab_group.addButton(self.btn_nav_manage, 3)
        self.tab_group.buttonClicked.connect(self._on_tab_changed)

        lay.addWidget(self.btn_nav_kunci, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self.btn_nav_buka, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self.btn_nav_teks, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self.btn_nav_manage, alignment=Qt.AlignmentFlag.AlignHCenter)
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

        # Status keamanan sebagai pill badge (dot/ikon + teks), warna per-state.
        self.status_pill = QFrame()
        self.status_pill.setObjectName("StatusPill")
        self.status_pill.setProperty("state", "idle")
        pill_lay = QHBoxLayout(self.status_pill)
        pill_lay.setContentsMargins(13, 7, 15, 7)
        pill_lay.setSpacing(8)

        self.lbl_status_icon = QLabel()
        self.lbl_status_icon.setPixmap(
            qta.icon("mdi6.shield-check-outline", color=CLR_ACCENT).pixmap(16, 16)
        )
        self.lbl_status_text = QLabel("AES-256 • GCM")
        self.lbl_status_text.setObjectName("StatusPillText")
        self.lbl_status_text.setStyleSheet(
            f"color: {CLR_ACCENT}; font-weight: 700; font-size: 9pt;"
        )
        pill_lay.addWidget(self.lbl_status_icon)
        pill_lay.addWidget(self.lbl_status_text)

        lay.addWidget(self.status_pill, 0, Qt.AlignmentFlag.AlignVCenter)
        parent_layout.addWidget(topbar)

    def _make_tab_button(self, label: str, icon_name: str, accessible: str) -> QToolButton:
        """Factory tombol navigasi rail (ikon + label kecil di bawah)."""
        btn = QToolButton()
        btn.setText(label)
        btn.setIcon(qta.icon(icon_name, color=CLR_TEXT_DIM, color_on=CLR_ACCENT))
        btn.setIconSize(QSize(22, 22))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setObjectName("NavBtn")
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(72, 60)
        btn.setToolTip(accessible)
        btn.setAccessibleName(accessible)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
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
        lbl_safe_icon.setPixmap(
            qta.icon("mdi6.shield-check-outline", color=CLR_TEXT_MUTED).pixmap(15, 15)
        )
        lbl_safe_text = QLabel("Your password is never sent anywhere")
        lbl_safe_text.setObjectName("MutedText")
        lay_safe.addWidget(lbl_safe_icon)
        lay_safe.addWidget(lbl_safe_text)

        lay_ver = QHBoxLayout()
        lay_ver.setSpacing(6)
        lbl_ver_text = QLabel(f"Version {APP_VERSION}")
        lbl_ver_text.setObjectName("MutedText")
        lbl_ver_icon = QLabel()
        lbl_ver_icon.setPixmap(
            qta.icon("mdi6.check-circle-outline", color=CLR_TEXT_MUTED).pixmap(15, 15)
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

    # Judul + subtitle yang tampil di kiri atas untuk tiap tab (indeks stack).
    PAGE_HEADERS = {
        0: ("Lock Folder", "Choose a file or folder, set a password, and lock it."),
        1: ("Open Vault", "Select an encrypted vault file and enter your password to open it."),
        2: ("Text", "Encrypt or decrypt text with a password."),
        3: ("Manage Vault", "Change the password or recovery key of an existing vault."),
    }

    def _update_page_header(self, index: int) -> None:
        title, subtitle = self.PAGE_HEADERS.get(index, ("", ""))
        self.lbl_page_title.setText(title)
        self.lbl_page_sub.setText(subtitle)

    def _on_tab_status(self, idx: int, title: str, subtitle: str, state: str) -> None:
        """Simpan status per-tab; tampilkan di pill hanya jika tab itu sedang aktif."""
        self._tab_status[idx] = (title, subtitle, state)
        if self.stacked_tabs.currentIndex() == idx:
            self._set_header_security_status(title, subtitle, state)

    def _refresh_status_for_tab(self, idx: int) -> None:
        title, subtitle, state = self._tab_status.get(idx, self._default_status)
        self._set_header_security_status(title, subtitle, state)

    def _revert_status_to_idle(self) -> None:
        """Kembalikan status pill tab aktif ke idle setelah 5 detik tanpa interaksi."""
        idx = self.stacked_tabs.currentIndex()
        self._tab_status[idx] = self._default_status
        self._set_header_security_status(*self._default_status)

    def _on_tab_changed(self, button: QPushButton) -> None:
        new_idx = self.tab_group.id(button)
        if new_idx != self.stacked_tabs.currentIndex():
            self.stacked_tabs.setCurrentIndex(new_idx)
        self._update_page_header(new_idx)
        self._refresh_status_for_tab(new_idx)
        # Pindahkan fokus ke tab yang diaktifkan agar ring tidak "nyangkut" di
        # tab lama (QToolButton tidak mengambil fokus saat diklik dengan mouse).
        button.setFocus(Qt.FocusReason.MouseFocusReason)

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
        self._refresh_status_for_tab(1)
        self.btn_nav_buka.setFocus(Qt.FocusReason.OtherFocusReason)
        self.tab_buka.auto_load_file(path)

    def kunci_file_dari_luar(self, paths: list[str]) -> None:
        """Quick encrypt dari context menu (hybrid): muat path ke tab Kunci."""
        logger.info(f"Quick encrypt dipicu untuk {len(paths)} path.")
        self.btn_nav_kunci.setChecked(True)
        self.btn_nav_buka.setChecked(False)
        self.btn_nav_teks.setChecked(False)
        self.stacked_tabs.setCurrentIndex(0)
        self._update_page_header(0)
        self._refresh_status_for_tab(0)
        self.btn_nav_kunci.setFocus(Qt.FocusReason.OtherFocusReason)
        self.tab_kunci.auto_load_paths(paths)

    def _update_action_button_tab_order(self):
        current_tab = self.stacked_tabs.currentWidget()
        if hasattr(current_tab, "btn_aksi"):
            self.setTabOrder(self.btn_nav_teks, current_tab.btn_aksi)
