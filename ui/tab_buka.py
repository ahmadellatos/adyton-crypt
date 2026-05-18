"""
Modul: tab_buka.py
Deskripsi: Antarmuka untuk Tab "Buka Brankas".
           Diperbarui: Fix layout overlap dengan mengatur ulang spacing dinamis,
           dan Fix Indentasi metode _on_selesai.
"""

import os
from loguru import logger
import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QFrame,
    QStackedWidget,
    QDialog,
)
from PySide6.QtCore import Qt, QSize

from core.vault import buka_brankas, VaultStatus
from core.worker import CryptoWorker
from .widgets import (
    AnimatedNotifBar,
    apply_shadow,
    BigActionBtn,
    ElidedLabel,
    HeroIconWidget,
    ModernMessageBox,
)

notification = None
try:
    from plyer import notification

    HAS_PLYER = True
except ImportError:
    HAS_PLYER = False


class DropTargetFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)
        self.on_file_dropped = None

    def _set_drag_state(self, state: bool):
        self.setProperty("dragActive", state)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".locked"):
                    self._set_drag_state(True)
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._set_drag_state(False)

    def dropEvent(self, event):
        self._set_drag_state(False)
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".locked"):
                if self.on_file_dropped:
                    self.on_file_dropped(path)
                break


class TabBuka(QWidget):
    def __init__(self):
        super().__init__()
        self._path_file = None
        self._konfirmasi_timpa = False
        self.worker: CryptoWorker | None = None
        self._build_ui()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_dnd_density()

    def _update_dnd_density(self):
        if not hasattr(self, "icon_empty"):
            return

        win = self.window()
        win_h = win.height() if win else self.height()
        card_h = self.card_file.height()

        compact = win_h <= 690 or card_h < 300

        if compact:
            self.icon_empty.setMaximumHeight(52)
            self.lbl_main_empty.setStyleSheet(
                "font-size: 10pt; font-weight: bold; color: white;"
            )
            self.lbl_sub_empty.setStyleSheet("font-size: 8pt; color: #8B95A5;")
            self.btn_browse_center.setFixedSize(180, 34)
            self.lbl_footer_empty.hide()
        else:
            self.icon_empty.setMaximumHeight(85)
            self.lbl_main_empty.setStyleSheet(
                "font-size: 13pt; font-weight: bold; color: white;"
            )
            self.lbl_sub_empty.setStyleSheet("font-size: 10pt; color: #8B95A5;")
            self.btn_browse_center.setFixedSize(220, 42)
            self.lbl_footer_empty.show()

    def _update_card_style(self, is_empty: bool):
        if is_empty:
            self.card_file.setStyleSheet("""
                QFrame#DropArea {
                    border: 2px dashed #232B3E;
                    background-color: #0B101E;
                    border-radius: 12px;
                }
                QFrame#DropArea[dragActive="true"] {
                    border: 2px dashed #00D2C8;
                    background-color: #181F32;
                }
            """)
        else:
            self.card_file.setStyleSheet("""
                QFrame#DropArea {
                    border: 1px solid #232B3E;
                    background-color: #111625;
                    border-radius: 12px;
                }
                QFrame#DropArea[dragActive="true"] {
                    border: 2px dashed #00D2C8;
                    background-color: #181F32;
                }
            """)

    # ── BUILD UI ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        """Orchestrator utama — merakit semua panel jadi satu layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(20)

        h_container = QHBoxLayout()
        h_container.setSpacing(20)
        h_container.addWidget(self._build_file_panel(), 1)
        h_container.addLayout(self._build_password_panel(), 1)
        main_layout.addLayout(h_container)

        self.btn_aksi = BigActionBtn(
            "BUKA BRANKAS",
            "Masukkan password untuk membuka",
            icon_name="mdi6.lock-open-variant",
        )
        self.btn_aksi.setEnabled(False)
        self.btn_aksi.clicked.connect(self._proses)
        apply_shadow(self.btn_aksi, blur_radius=20, y_offset=4, opacity=80)
        main_layout.addWidget(self.btn_aksi)

        self.notif = AnimatedNotifBar(self)
        self._setup_accessibility()

    def _build_file_panel(self) -> QFrame:
        """Panel kiri: drop zone dengan empty state & filled state."""
        self.card_file = DropTargetFrame()
        apply_shadow(self.card_file, blur_radius=30, opacity=40)
        self.card_file.on_file_dropped = self._set_file

        layout_card = QVBoxLayout(self.card_file)
        layout_card.setContentsMargins(2, 2, 2, 2)

        self.stack_file = QStackedWidget()
        layout_card.addWidget(self.stack_file)

        self.stack_file.addWidget(self._build_empty_state())
        self.stack_file.addWidget(self._build_filled_state())

        self._update_card_style(True)
        return self.card_file

    def _build_empty_state(self) -> QWidget:
        """Page 0 stack: drop zone kosong dengan hero icon."""
        page_empty = QWidget()
        lay_empty = QVBoxLayout(page_empty)
        lay_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay_empty.setSpacing(0)

        self.icon_empty = HeroIconWidget(mode="buka")
        self.icon_empty.setMaximumHeight(85)

        self.lbl_main_empty = QLabel("Drag & drop file .locked ke sini")
        self.lbl_main_empty.setStyleSheet(
            "font-size: 13pt; font-weight: bold; color: white;"
        )
        self.lbl_main_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_main_empty.setWordWrap(True)

        self.lbl_sub_empty = QLabel("atau klik tombol di bawah untuk memilih file")
        self.lbl_sub_empty.setStyleSheet("font-size: 10pt; color: #8B95A5;")
        self.lbl_sub_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_sub_empty.setWordWrap(True)

        self.btn_browse_center = QPushButton(" Pilih File Brankas")
        self.btn_browse_center.setIcon(qta.icon("mdi6.folder-search", color="white"))
        self.btn_browse_center.setFixedSize(220, 42)
        self.btn_browse_center.setObjectName("BtnBrowseLg")
        self.btn_browse_center.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse_center.clicked.connect(self._pilih_file)

        self.lbl_footer_empty = QLabel(
            "Hanya file dengan ekstensi .locked yang dapat dibuka"
        )
        self.lbl_footer_empty.setStyleSheet("font-size: 9pt; color: #8B95A5;")
        self.lbl_footer_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_footer_empty.setWordWrap(True)

        lay_empty.addStretch(1)
        lay_empty.addWidget(self.icon_empty, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay_empty.addStretch(1)
        lay_empty.addWidget(self.lbl_main_empty)
        lay_empty.addSpacing(2)
        lay_empty.addWidget(self.lbl_sub_empty)
        lay_empty.addStretch(1)
        lay_empty.addWidget(
            self.btn_browse_center, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        lay_empty.addStretch(1)
        lay_empty.addWidget(self.lbl_footer_empty)
        lay_empty.addStretch(1)

        return page_empty

    def _build_filled_state(self) -> QWidget:
        """Page 1 stack: info file yang sudah dipilih + tombol ganti."""
        page_filled = QWidget()
        lay_filled = QVBoxLayout(page_filled)
        lay_filled.setContentsMargins(23, 23, 23, 23)
        lay_filled.setSpacing(15)

        lbl_title_file = QLabel("FILE BRANKAS (.locked)")
        lbl_title_file.setObjectName("CardTitle")
        lay_filled.addWidget(lbl_title_file)

        file_box = QFrame()
        file_box.setStyleSheet(
            "background-color: #181F32; border: 1px solid #232B3E; border-radius: 8px;"
        )
        lay_fbox = QHBoxLayout(file_box)
        lay_fbox.setContentsMargins(15, 15, 15, 15)

        icon_locked = QLabel()
        icon_locked.setPixmap(
            qta.icon("mdi6.file-lock", color="#00D2C8").pixmap(32, 32)
        )

        v_fname = QVBoxLayout()
        v_fname.setSpacing(2)
        self.lbl_path_filled = ElidedLabel("...", mode=Qt.TextElideMode.ElideMiddle)
        self.lbl_path_filled.setStyleSheet(
            "color: white; font-weight: bold; font-size: 11pt; border: none; background: transparent;"
        )
        lbl_path_desc = QLabel("Siap untuk didekripsi")
        lbl_path_desc.setStyleSheet(
            "color: #8B95A5; font-size: 9pt; border: none; background: transparent;"
        )
        v_fname.addWidget(self.lbl_path_filled)
        v_fname.addWidget(lbl_path_desc)

        self.btn_clear = QPushButton()
        self.btn_clear.setIcon(
            qta.icon("mdi6.close", color="#8B95A5", color_active="white")
        )
        self.btn_clear.setFixedSize(32, 32)
        self.btn_clear.setStyleSheet(
            "QPushButton { background: transparent; border: none; } "
            "QPushButton:hover { background: #E74C3C; border-radius: 4px; }"
            "QPushButton:focus { border: 2px solid #00D2C8; background: #232B3E; }"
        )
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.clicked.connect(self._clear_file)

        lay_fbox.addWidget(icon_locked)
        lay_fbox.addSpacing(10)
        lay_fbox.addLayout(v_fname, 1)
        lay_fbox.addWidget(self.btn_clear)
        lay_filled.addWidget(file_box)

        self.btn_ganti = QPushButton(" Ganti File Brankas")
        self.btn_ganti.setIcon(qta.icon("mdi6.file-find", color="white"))
        self.btn_ganti.setFixedHeight(40)
        self.btn_ganti.clicked.connect(self._pilih_file)
        lay_filled.addWidget(self.btn_ganti)

        lay_filled.addStretch()
        return page_filled

    def _build_password_panel(self) -> QVBoxLayout:
        """Panel kanan: input password + info box tips keamanan."""
        col_right = QVBoxLayout()

        card_pw = QFrame()
        card_pw.setObjectName("Card")
        apply_shadow(card_pw, blur_radius=30, opacity=40)

        v_pw = QVBoxLayout(card_pw)
        v_pw.setContentsMargins(25, 25, 25, 25)
        v_pw.setSpacing(15)

        lbl_title_pw = QLabel("MASUKKAN PASSWORD")
        lbl_title_pw.setObjectName("CardTitle")
        v_pw.addWidget(lbl_title_pw)
        v_pw.addSpacing(10)

        # Input password
        self.box_pw = QFrame()
        self.box_pw.setObjectName("InputBox")
        lay_box = QHBoxLayout(self.box_pw)
        lay_box.setContentsMargins(10, 0, 5, 0)
        lay_box.setSpacing(0)

        self.entry_pw = QLineEdit()
        self.entry_pw.setObjectName("InputInside")
        self.entry_pw.setFixedHeight(45)
        self.entry_pw.setPlaceholderText("Ketik password di sini…")
        self.entry_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.entry_pw.textChanged.connect(self._on_pw_change)
        self.entry_pw.returnPressed.connect(self._proses)
        lay_box.addWidget(self.entry_pw)

        self.btn_toggle_pw = QPushButton()
        self.btn_toggle_pw.setIcon(qta.icon("mdi6.eye-outline", color="#8B95A5"))
        self.btn_toggle_pw.setIconSize(QSize(22, 22))
        self.btn_toggle_pw.setObjectName("BtnEye")
        self.btn_toggle_pw.setFixedSize(40, 45)
        self.btn_toggle_pw.clicked.connect(self._toggle_pw)
        lay_box.addWidget(self.btn_toggle_pw)

        v_pw.addWidget(self.box_pw)
        v_pw.addStretch()
        v_pw.addWidget(self._build_info_box())

        col_right.addWidget(card_pw, 1)
        return col_right

    def _build_info_box(self) -> QFrame:
        """Info box tips keamanan di bawah form password."""
        info_box = QFrame()
        info_box.setStyleSheet("""
            QFrame {
                background-color: #0E1A24;
                border: 1px solid #142E3B;
                border-radius: 8px;
            }
        """)
        lay_info = QVBoxLayout(info_box)
        lay_info.setContentsMargins(14, 12, 14, 12)
        lay_info.setSpacing(10)

        tips = [
            (
                "mdi6.shield-key-outline",
                "#00D2C8",
                "Password tidak dapat dipulihkan. Simpan di tempat yang aman.",
            ),
            (
                "mdi6.lock-alert-outline",
                "#F39C12",
                "Pastikan password sama persis dengan yang digunakan saat mengunci.",
            ),
            (
                "mdi6.file-lock-outline",
                "#8B95A5",
                "Hanya file .locked yang dibuat oleh Digital Locker yang dapat dibuka.",
            ),
        ]

        for icon_name, color, text in tips:
            row = QHBoxLayout()
            row.setSpacing(10)
            lbl_ic = QLabel()
            lbl_ic.setPixmap(qta.icon(icon_name, color=color).pixmap(18, 18))
            lbl_ic.setFixedSize(18, 18)
            lbl_ic.setAlignment(Qt.AlignmentFlag.AlignTop)
            lbl_tx = QLabel(text)
            lbl_tx.setWordWrap(True)
            lbl_tx.setStyleSheet(
                "font-size: 9pt; color: #8B95A5; background: transparent; border: none;"
            )
            row.addWidget(lbl_ic, alignment=Qt.AlignmentFlag.AlignTop)
            row.addWidget(lbl_tx, 1)
            lay_info.addLayout(row)

        return info_box

    def _setup_accessibility(self):
        """Setup focus policy, event filter, dan tab order."""
        self.btn_browse_center.installEventFilter(self)
        self.entry_pw.installEventFilter(self)
        self.btn_toggle_pw.installEventFilter(self)

        self.btn_browse_center.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_ganti.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_clear.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_aksi.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.setTabOrder(self.btn_browse_center, self.btn_ganti)
        self.setTabOrder(self.btn_ganti, self.btn_clear)
        self.setTabOrder(self.btn_clear, self.entry_pw)
        self.setTabOrder(self.entry_pw, self.btn_toggle_pw)
        self.setTabOrder(self.btn_toggle_pw, self.btn_aksi)

    # ── EVENT HANDLING ───────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if event.type() in (event.Type.FocusIn, event.Type.FocusOut):
            if (
                isinstance(obj, QLineEdit)
                and obj.parent()
                and obj.parent().objectName() == "InputBox"
            ):
                is_focus = event.type() == event.Type.FocusIn
                box = obj.parent()
                box.setProperty("focused", is_focus)
                box.style().unpolish(box)
                box.style().polish(box)

        elif event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                if isinstance(obj, QPushButton):
                    if obj.objectName() == "BtnEye":
                        obj.click()
                        return True
                    elif obj == self.btn_browse_center:  # TAMBAH BLOK INI
                        obj.click()
                        return True

        return super().eventFilter(obj, event)

    def _toggle_pw(self):
        mode = (
            QLineEdit.EchoMode.Normal
            if self.entry_pw.echoMode() == QLineEdit.EchoMode.Password
            else QLineEdit.EchoMode.Password
        )
        self.entry_pw.setEchoMode(mode)
        color = "#00D2C8" if mode == QLineEdit.EchoMode.Normal else "#8B95A5"
        icon_name = (
            "mdi6.eye-outline"
            if mode == QLineEdit.EchoMode.Password
            else "mdi6.eye-off-outline"
        )
        self.btn_toggle_pw.setIcon(qta.icon(icon_name, color=color))

    # ── STATE & VALIDATION ───────────────────────────────────────────────────

    def _on_pw_change(self):
        self.notif.hide_msg()
        self._validate_state()

    def _validate_state(self):
        if self.worker is not None:
            return
        if not self._konfirmasi_timpa:
            enabled = self._path_file is not None and bool(self.entry_pw.text())
            self.btn_aksi.setEnabled(enabled)
            self.btn_aksi.setFocusPolicy(
                Qt.FocusPolicy.StrongFocus if enabled else Qt.FocusPolicy.NoFocus
            )

    def _set_file(self, path: str):
        self._path_file = path
        self.lbl_path_filled.setText(os.path.basename(path))
        self.lbl_path_filled.setToolTip(path)

        self.stack_file.setCurrentIndex(1)
        self._update_card_style(False)
        self._reset_timpa()
        self.btn_ganti.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_clear.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._validate_state()

    def _clear_file(self):
        self._path_file = None
        self.stack_file.setCurrentIndex(0)
        self._update_card_style(True)
        self._reset_timpa()
        self.btn_ganti.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_clear.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._validate_state()

    def _pilih_file(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Pilih File Brankas", "", "Locked Files (*.locked)"
        )
        if f:
            self._set_file(f)

    def _reset_timpa(self):
        self._konfirmasi_timpa = False
        self.btn_aksi.setTextLabels(
            "BUKA BRANKAS", "Masukkan password untuk membuka kunci"
        )

    # ── PROSES DEKRIPSI ──────────────────────────────────────────────────────

    def _proses(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.btn_aksi.setTextLabels("MEMBATALKAN...", "Harap tunggu...")
            self.btn_aksi.setEnabled(False)
            return

        force = self._konfirmasi_timpa

        if force and getattr(self, "_cached_pw", None):
            pw = self._cached_pw
        else:
            pw = self.entry_pw.text()
            self._cached_pw = pw

        if force:
            self._reset_timpa()

        if not self._path_file or not pw:
            return

        self._set_busy(True)
        self.worker = CryptoWorker(buka_brankas, self._path_file, pw, force)

        self.entry_pw.blockSignals(True)
        self.entry_pw.clear()
        self.entry_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.btn_toggle_pw.setIcon(qta.icon("mdi6.eye-outline", color="#8B95A5"))
        self.entry_pw.blockSignals(False)

        self.worker.progress.connect(
            lambda v: self.btn_aksi.setTextLabels(
                "MEMBUKA...", f"Progress: {int(v*100)}% (Klik untuk Batal)"
            )
        )
        self.worker.finished.connect(self._on_selesai)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def _set_busy(self, busy: bool):
        self.btn_browse_center.setEnabled(not busy)
        self.btn_ganti.setEnabled(not busy)
        self.btn_clear.setEnabled(not busy)
        if busy:
            self.btn_aksi.setTextLabels("MEMBUKA BRANKAS...", "Harap tunggu...")
            self.btn_aksi.setEnabled(True)
        else:
            self.btn_aksi.setTextLabels(
                "BUKA BRANKAS", "Masukkan password untuk membuka"
            )
            self._validate_state()

    def _on_selesai(self, result):
        self.worker = None
        status, msg = result

        if status == VaultStatus.SUCCESS:
            self._cached_pw = None
            self._clear_file()

        self._set_busy(False)

        if status == VaultStatus.SUCCESS:
            logger.info(f"Dekripsi sukses: {msg}")
            self.notif.show_msg(
                "ok", f"Folder/File '{msg}' berhasil dikembalikan!", 6000
            )
            if HAS_PLYER and notification:
                try:
                    notification.notify(
                        title="Digital Locker",
                        message=f"Brankas '{msg}' berhasil dibuka.",
                        timeout=5,
                    )
                except Exception as e:
                    logger.warning(f"Notifikasi sistem gagal: {e}")

        elif status == VaultStatus.CANCELLED:
            self._cached_pw = None
            logger.info("Dekripsi dibatalkan pengguna.")
            self.notif.show_msg("warn", "Dekripsi dibatalkan pengguna.", 4000)

        elif status == VaultStatus.WRONG_PASSWORD:
            self._cached_pw = None
            logger.warning("Dekripsi gagal: Password salah.")
            self.notif.show_msg("err", "Password salah atau file corrupted! Coba lagi.")

        elif status == VaultStatus.OVERWRITE_NEEDED:
            dialog = ModernMessageBox(
                title="Konfirmasi Timpa File",
                message=f"Folder/File bernama '{msg}' sudah ada di lokasi tujuan.\n\nApakah Anda yakin ingin menimpanya? Data lama akan hilang secara permanen.",
                icon_name="mdi6.alert-decagram",
                icon_color="#E67E22",
                parent=self,
            )
            dialog.btn_yes.setText("Timpa Data")

            if dialog.exec() == QDialog.DialogCode.Accepted:
                self._konfirmasi_timpa = True
                self._proses()
            else:
                self._cached_pw = None
                self._reset_timpa()
                self._validate_state()
                logger.info("Dekripsi dibatalkan: User menolak overwrite file asli.")
                self.notif.show_msg(
                    "warn", "Dekripsi dibatalkan untuk melindungi file asli Anda.", 4000
                )

        else:
            self._cached_pw = None
            logger.error(f"Dekripsi gagal: {msg}")
            self.notif.show_msg("err", f"Error: {msg}", 8000)
