"""
Modul: tab_kunci.py
Deskripsi: Antarmuka untuk Tab "Kunci Folder"
           Diperbarui: Menggunakan CenteredMenuAction untuk menu Dropdown rata tengah.
"""

import os
import secrets
import string
from loguru import logger
import qtawesome as qta
from zxcvbn import zxcvbn

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QFrame,
    QScrollArea,
    QMenu,
    QDialog,
    QStackedWidget,
)
from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QKeyEvent

from core.vault import kunci_brankas, VaultStatus
from core.worker import CryptoWorker
from .widgets import (
    AnimatedNotifBar,
    apply_shadow,
    BigActionBtn,
    ModernMessageBox,
    CustomToolTip,
    ElidedLabel,
    HeroIconWidget,
    CenteredMenuAction,
    AccessibleCenteredMenu,
)

notification = None
try:
    from plyer import notification

    HAS_PLYER = True
except ImportError:
    HAS_PLYER = False


def pw_strength(pw: str) -> int:
    if not pw:
        return -1
    hasil = zxcvbn(pw)
    skor = hasil["score"]
    return 0 if skor <= 1 else skor - 1


STRENGTH_COLORS = ["#E74C3C", "#E67E22", "#00D2C8", "#00D2C8"]
STRENGTH_LABELS = ["Lemah", "Cukup", "Kuat", "Sangat Kuat"]


class KeyboardCheckbox(QFrame):
    """
    FIX: Custom checkbox yang mendukung keyboard navigation (Tab + Space/Enter).
    Menggantikan QFrame biasa yang tidak accessible via keyboard.
    """

    def __init__(self, size=22, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._checked = False
        self._on_toggle = None

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._on_toggle:
                self._on_toggle()
            event.accept()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if self._on_toggle:
            self._on_toggle()


class FileListRow(QFrame):
    def __init__(self, path: str, tooltip_widget, parent=None):
        super().__init__(parent)
        self._path = path
        self._tooltip_widget = tooltip_widget
        self.setObjectName("ListItem")
        self.setFixedHeight(56)

    def enterEvent(self, event):
        self._tooltip_widget.request_show(self._path)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._tooltip_widget.hide_tooltip()
        super().leaveEvent(event)


class MultiDropFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)
        self.on_paths_dropped = None

    def _set_drag_state(self, state: bool):
        self.setProperty("dragActive", state)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self._set_drag_state(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._set_drag_state(False)

    def dropEvent(self, event):
        self._set_drag_state(False)
        paths = [
            url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()
        ]
        valid_paths = [p for p in paths if os.path.exists(p)]
        if valid_paths and self.on_paths_dropped:
            self.on_paths_dropped(valid_paths)


class TabKunci(QWidget):
    def __init__(self):
        super().__init__()
        self._paths = []
        self.worker: CryptoWorker | None = None
        self._custom_tooltip = CustomToolTip(self)
        self._build_ui()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_dnd_density()

    def _update_dnd_density(self):
        if not hasattr(self, "icon_empty"):
            return

        win = self.window()
        win_h = win.height() if win else self.height()
        card_h = self.card_target.height()

        compact = win_h <= 690 or card_h < 300

        if compact:
            self.icon_empty.setMaximumHeight(52)
            self.lbl_main_empty.setStyleSheet(
                "font-size: 10pt; font-weight: bold; color: white;"
            )
            self.lbl_sub_empty.setStyleSheet("font-size: 8pt; color: #8B95A5;")
            self.btn_empty_browse.setFixedSize(180, 34)
            self.lbl_footer_empty.hide()
        else:
            self.icon_empty.setMaximumHeight(85)
            self.lbl_main_empty.setStyleSheet(
                "font-size: 13pt; font-weight: bold; color: white;"
            )
            self.lbl_sub_empty.setStyleSheet("font-size: 10pt; color: #8B95A5;")
            self.btn_empty_browse.setFixedSize(220, 42)
            self.lbl_footer_empty.show()

    def _update_card_style(self, is_empty: bool):
        if is_empty:
            self.card_target.setStyleSheet("""
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
            self.card_target.setStyleSheet("""
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

    def _build_ui(self):
        """Orchestrator utama — merakit semua panel jadi satu layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(20)

        # Buat shared dropdown menu yang dipakai kedua panel kiri
        menu = AccessibleCenteredMenu(self)
        action_file = CenteredMenuAction("File", "mdi6.file-document", parent=menu)
        action_file.triggered.connect(self._pilih_file)
        menu.addAction(action_file)
        action_folder = CenteredMenuAction("Folder", "mdi6.folder", parent=menu)
        action_folder.triggered.connect(self._pilih_folder)
        menu.addAction(action_folder)

        h_cols = QHBoxLayout()
        h_cols.setSpacing(20)
        h_cols.addLayout(self._build_left_panel(menu), 1)
        h_cols.addLayout(self._build_right_panel(), 1)
        main_layout.addLayout(h_cols)

        # Bottom action bar
        self.btn_aksi = BigActionBtn(
            "KUNCI SEKARANG", "Proses penguncian akan dimulai", icon_name="mdi6.lock"
        )
        self.btn_aksi.setEnabled(False)
        self.btn_aksi.clicked.connect(self._proses)
        apply_shadow(self.btn_aksi, blur_radius=20, y_offset=4, opacity=80)
        main_layout.addWidget(self.btn_aksi)

        self.notif = AnimatedNotifBar(self)
        self._render_list()
        self._setup_accessibility()

    def _build_left_panel(self, menu: QMenu) -> QVBoxLayout:
        """Membangun panel kiri: drop area file list + opsi hapus/secure wipe."""
        v_left = QVBoxLayout()

        # ── Drop area card ───────────────────────────────────────────
        self.card_target = MultiDropFrame()
        self.card_target.on_paths_dropped = self._add_paths
        apply_shadow(self.card_target, blur_radius=30, opacity=40)

        lay_target = QVBoxLayout(self.card_target)
        lay_target.setContentsMargins(2, 2, 2, 2)

        self.stack_target = QStackedWidget()
        lay_target.addWidget(self.stack_target)

        # Halaman kosong (empty state)
        page_empty = QWidget()
        lay_empty = QVBoxLayout(page_empty)
        lay_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay_empty.setSpacing(0)

        self.icon_empty = HeroIconWidget(mode="kunci")
        self.icon_empty.setMaximumHeight(85)

        self.lbl_main_empty = QLabel("Drag & drop file atau folder ke sini")
        self.lbl_main_empty.setStyleSheet(
            "font-size: 13pt; font-weight: bold; color: white;"
        )
        self.lbl_main_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_main_empty.setWordWrap(True)

        self.lbl_sub_empty = QLabel(
            "atau klik tombol di bawah untuk memilih secara manual"
        )
        self.lbl_sub_empty.setStyleSheet("font-size: 10pt; color: #8B95A5;")
        self.lbl_sub_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_sub_empty.setWordWrap(True)

        self.btn_empty_browse = QPushButton(" Pilih Target")
        self.btn_empty_browse.setIcon(qta.icon("mdi6.folder-plus", color="white"))
        self.btn_empty_browse.setObjectName("BtnBrowseLg")
        self.btn_empty_browse.setFixedSize(220, 42)
        self.btn_empty_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_empty_browse.setMenu(menu)

        self.lbl_footer_empty = QLabel(
            "Mendukung semua format file dan folder tak terbatas"
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
            self.btn_empty_browse, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        lay_empty.addStretch(1)
        lay_empty.addWidget(self.lbl_footer_empty)
        lay_empty.addStretch(1)
        self.stack_target.addWidget(page_empty)

        # Halaman berisi daftar file
        page_list = QWidget()
        lay_list = QVBoxLayout(page_list)
        lay_list.setContentsMargins(23, 23, 23, 23)
        lay_list.setSpacing(15)

        row_hdr = QHBoxLayout()
        icon_folder = QLabel()
        icon_folder.setPixmap(
            qta.icon("mdi6.folder-open", color="#F1C40F").pixmap(32, 32)
        )

        v_hdr_text = QVBoxLayout()
        v_hdr_text.setSpacing(2)
        lbl_target = QLabel("DAFTAR TARGET")
        lbl_target.setObjectName("CardTitle")
        lbl_target_sub = QLabel("Pilih file atau folder yang akan dikunci")
        lbl_target_sub.setObjectName("CardSubtitle")
        lbl_target_sub.setWordWrap(True)
        v_hdr_text.addWidget(lbl_target)
        v_hdr_text.addWidget(lbl_target_sub)

        self.btn_add = QPushButton(" Tambah")
        self.btn_add.setIcon(qta.icon("mdi6.plus", color="#8B95A5"))
        self.btn_add.setObjectName("BtnGhost")
        self.btn_add.setFixedSize(100, 36)
        self.btn_add.setStyleSheet(
            "QPushButton#BtnGhost { font-size: 10pt; border: 1px solid #232B3E; } QPushButton::menu-indicator { image: none; width: 0px; }"
        )
        self.btn_add.setMenu(menu)

        row_hdr.addWidget(icon_folder)
        row_hdr.addLayout(v_hdr_text)
        row_hdr.addStretch()
        row_hdr.addWidget(self.btn_add, alignment=Qt.AlignmentFlag.AlignTop)
        lay_list.addLayout(row_hdr)

        self.inner_frame = QFrame()
        self.inner_frame.setObjectName("Inner")
        inner_lay = QVBoxLayout(self.inner_frame)
        inner_lay.setContentsMargins(0, 5, 0, 5)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")
        self.list_container = QWidget()
        self.list_container.setStyleSheet("background: transparent;")
        self.list_container.setObjectName("ListContainer")

        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.list_layout.setSpacing(0)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area.setWidget(self.list_container)
        self.scroll_area.verticalScrollBar().valueChanged.connect(
            lambda _: self._custom_tooltip.hide_tooltip()
        )

        inner_lay.addWidget(self.scroll_area)
        lay_list.addWidget(self.inner_frame, 1)
        self.stack_target.addWidget(page_list)

        self._update_card_style(True)
        v_left.addWidget(self.card_target, 1)

        # ── Opsi hapus & secure wipe ─────────────────────────────────
        v_left.addLayout(self._build_options())

        return v_left

    def _build_right_panel(self) -> QVBoxLayout:
        """Membangun panel kanan: form input password + indikator kekuatan."""
        v_right = QVBoxLayout()

        card_pw = QFrame()
        card_pw.setObjectName("Card")
        apply_shadow(card_pw, blur_radius=30, opacity=40)

        lay_pw = QVBoxLayout(card_pw)
        lay_pw.setContentsMargins(20, 20, 20, 20)
        lay_pw.setSpacing(8)

        # Header card password
        row_hdr_pw = QHBoxLayout()
        icon_key = QLabel()
        icon_key.setPixmap(qta.icon("mdi6.key-variant", color="#F39C12").pixmap(32, 32))
        icon_key.setAlignment(Qt.AlignmentFlag.AlignTop)

        v_hdr_pw_txt = QVBoxLayout()
        v_hdr_pw_txt.setSpacing(2)
        lbl_pw = QLabel("BUAT PASSWORD")
        lbl_pw.setObjectName("CardTitle")
        lbl_pw_sub = QLabel("Buat password yang kuat untuk melindungi data Anda")
        lbl_pw_sub.setObjectName("CardSubtitle")
        lbl_pw_sub.setWordWrap(True)
        v_hdr_pw_txt.addWidget(lbl_pw)
        v_hdr_pw_txt.addWidget(lbl_pw_sub)

        self.btn_gen = QPushButton(" Generator")
        self.btn_gen.setIcon(qta.icon("mdi6.creation", color="white"))
        self.btn_gen.setFixedHeight(32)
        self.btn_gen.setObjectName("BtnGen")
        self.btn_gen.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_gen.clicked.connect(self._generate_pw)

        row_hdr_pw.addWidget(icon_key)
        row_hdr_pw.addLayout(v_hdr_pw_txt, 1)
        row_hdr_pw.addWidget(self.btn_gen, alignment=Qt.AlignmentFlag.AlignTop)
        lay_pw.addLayout(row_hdr_pw)

        # Input password pertama
        lbl_in1 = QLabel("Password")
        lbl_in1.setStyleSheet("font-weight: 600;")
        lay_pw.addWidget(lbl_in1)

        v_pw1_group = QVBoxLayout()
        v_pw1_group.setSpacing(0)

        box_pw1 = QFrame()
        self.box_pw1 = box_pw1
        box_pw1.setObjectName("InputBox")
        lay_box1 = QHBoxLayout(box_pw1)
        lay_box1.setContentsMargins(10, 0, 5, 0)
        lay_box1.setSpacing(0)

        self.entry_pw1 = QLineEdit()
        self.entry_pw1.setObjectName("InputInside")
        self.entry_pw1.setFixedHeight(45)
        self.entry_pw1.setEchoMode(QLineEdit.EchoMode.Password)
        self.entry_pw1.setPlaceholderText("Buat password yang kuat...")
        self.entry_pw1.textChanged.connect(self._on_pw_change)
        lay_box1.addWidget(self.entry_pw1)

        self.btn_toggle_pw1 = QPushButton()
        self.btn_toggle_pw1.setIcon(qta.icon("mdi6.eye-outline", color="#8B95A5"))
        self.btn_toggle_pw1.setIconSize(QSize(22, 22))
        self.btn_toggle_pw1.setObjectName("BtnEye")
        self.btn_toggle_pw1.setFixedSize(40, 45)
        self.btn_toggle_pw1.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_pw1.clicked.connect(
            lambda: self._toggle_field(self.entry_pw1, self.btn_toggle_pw1)
        )
        lay_box1.addWidget(self.btn_toggle_pw1)
        v_pw1_group.addWidget(box_pw1)

        # Strength bar (animasi collapse)
        self.widget_strength = QWidget()
        self.widget_strength.setMaximumHeight(0)
        self.widget_strength.setMinimumHeight(0)
        self._strength_visible = False

        row_str = QHBoxLayout(self.widget_strength)
        row_str.setContentsMargins(0, 8, 0, 0)
        row_str.setSpacing(8)

        self.str_bars = []
        for _ in range(4):
            bar = QFrame()
            bar.setFixedHeight(6)
            bar.setStyleSheet("background-color: #232B3E; border-radius: 3px;")
            self.str_bars.append(bar)
            row_str.addWidget(bar, 1)

        self.lbl_str = QLabel("Kekuatan: -")
        self.lbl_str.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.lbl_str.setStyleSheet("font-size: 9pt; color: #8B95A5; font-weight: bold;")
        self.lbl_str.setMinimumWidth(140)
        row_str.addWidget(self.lbl_str)
        v_pw1_group.addWidget(self.widget_strength)

        self.anim_strength = QPropertyAnimation(self.widget_strength, b"maximumHeight")
        self.anim_strength.setDuration(250)
        self.anim_strength.setEasingCurve(QEasingCurve.Type.InOutCubic)

        # Checklist kriteria password
        self.lay_chk = QVBoxLayout()
        self.lay_chk.setContentsMargins(5, 12, 5, 5)

        grid_chk = QGridLayout()
        grid_chk.setContentsMargins(0, 0, 0, 0)
        grid_chk.setHorizontalSpacing(15)
        grid_chk.setVerticalSpacing(8)
        grid_chk.setColumnStretch(0, 1)
        grid_chk.setColumnStretch(1, 1)

        def _create_chk_item(text):
            lay = QHBoxLayout()
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(8)
            icon = QLabel()
            icon.setPixmap(
                qta.icon("mdi6.check-circle", color="#232B3E").pixmap(16, 16)
            )
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #8B95A5; font-size: 9pt;")
            lbl.setWordWrap(True)
            lay.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)
            lay.addWidget(lbl, 1)
            return lay, icon, lbl

        l1, self.chk_len_icon, self.chk_len_lbl = _create_chk_item("Minimal 8 karakter")
        l2, self.chk_upper_icon, self.chk_upper_lbl = _create_chk_item(
            "Huruf besar (A-Z)"
        )
        l3, self.chk_lower_icon, self.chk_lower_lbl = _create_chk_item(
            "Huruf kecil (a-z)"
        )
        l4, self.chk_digit_icon, self.chk_digit_lbl = _create_chk_item("Angka (0-9)")
        l5, self.chk_sym_icon, self.chk_sym_lbl = _create_chk_item("Simbol (!@#$%^&*)")

        grid_chk.addLayout(l1, 0, 0)
        grid_chk.addLayout(l4, 0, 1)
        grid_chk.addLayout(l2, 1, 0)
        grid_chk.addLayout(l5, 1, 1)
        grid_chk.addLayout(l3, 2, 0)

        self.lay_chk.addLayout(grid_chk)
        v_pw1_group.addLayout(self.lay_chk)
        lay_pw.addLayout(v_pw1_group)

        # Input konfirmasi password
        lbl_in2 = QLabel("Konfirmasi Password")
        lbl_in2.setStyleSheet("font-weight: 600;")
        lay_pw.addWidget(lbl_in2)

        box_pw2 = QFrame()
        self.box_pw2 = box_pw2
        box_pw2.setObjectName("InputBox")
        lay_box2 = QHBoxLayout(box_pw2)
        lay_box2.setContentsMargins(10, 0, 5, 0)
        lay_box2.setSpacing(0)

        self.entry_pw2 = QLineEdit()
        self.entry_pw2.setObjectName("InputInside")
        self.entry_pw2.setFixedHeight(45)
        self.entry_pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self.entry_pw2.setPlaceholderText("Ketik ulang password...")
        self.entry_pw2.textChanged.connect(self._on_pw_change)
        self.entry_pw2.returnPressed.connect(self._proses)
        lay_box2.addWidget(self.entry_pw2)

        self.btn_toggle_pw2 = QPushButton()
        self.btn_toggle_pw2.setIcon(qta.icon("mdi6.eye-outline", color="#8B95A5"))
        self.btn_toggle_pw2.setIconSize(QSize(22, 22))
        self.btn_toggle_pw2.setObjectName("BtnEye")
        self.btn_toggle_pw2.setFixedSize(40, 45)
        self.btn_toggle_pw2.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_pw2.clicked.connect(
            lambda: self._toggle_field(self.entry_pw2, self.btn_toggle_pw2)
        )
        lay_box2.addWidget(self.btn_toggle_pw2)
        lay_pw.addWidget(box_pw2)

        # Indikator match/tidak
        self.lay_match = QHBoxLayout()
        self.lay_match.setContentsMargins(5, 5, 0, 0)
        self.lay_match.setSpacing(8)
        self.icon_match = QLabel()
        self.icon_match.setFixedSize(16, 16)
        self.lbl_match_txt = QLabel("Password cocok")
        self.lbl_match_txt.setStyleSheet(
            "font-size: 9pt; color: #28c75d; font-weight: bold;"
        )
        self.lbl_match_txt.setWordWrap(True)
        self.lay_match.addWidget(self.icon_match, alignment=Qt.AlignmentFlag.AlignTop)
        self.lay_match.addWidget(self.lbl_match_txt, 1)
        self.icon_match.hide()
        self.lbl_match_txt.hide()

        lay_pw.addLayout(self.lay_match)
        lay_pw.addStretch()

        v_right.addWidget(card_pw, 1)
        return v_right

    def _build_options(self) -> QVBoxLayout:
        """Membangun area opsi: checkbox hapus asli + collapse secure wipe."""
        lay_opsi_hapus = QVBoxLayout()
        lay_opsi_hapus.setSpacing(0)

        # Checkbox hapus asli
        lay_chk1 = QHBoxLayout()
        lay_chk1.setContentsMargins(5, 5, 5, 0)
        lay_chk1.setSpacing(0)

        self.chk_hapus = KeyboardCheckbox(size=22)
        self.chk_hapus.setObjectName("ChkHapus")
        self.chk_hapus.setProperty("checked", False)
        self.chk_hapus._checked = False

        v_chk_txt1 = QVBoxLayout()
        v_chk_txt1.setSpacing(2)
        lbl_chk_title1 = QLabel("Hapus file/folder asli setelah dikunci")
        lbl_chk_title1.setStyleSheet("font-size: 10pt; color: #FFFFFF;")
        lbl_chk_desc1 = QLabel(
            "File atau folder asli akan dihapus secara standar (Cepat & Aman untuk SSD)."
        )
        lbl_chk_desc1.setStyleSheet("font-size: 9pt; color: #8B95A5;")
        lbl_chk_desc1.setWordWrap(True)
        v_chk_txt1.addWidget(lbl_chk_title1)
        v_chk_txt1.addWidget(lbl_chk_desc1)

        lay_chk1.addWidget(self.chk_hapus, alignment=Qt.AlignmentFlag.AlignVCenter)
        lay_chk1.addSpacing(10)
        lay_chk1.addLayout(v_chk_txt1)
        lay_opsi_hapus.addLayout(lay_chk1)

        # Collapsible: secure wipe
        self.widget_secure_wipe = QWidget()
        self.widget_secure_wipe.setMaximumHeight(0)
        self.widget_secure_wipe.setMinimumHeight(0)

        self.chk_secure_container_visible = False

        lay_collapse = QVBoxLayout(self.widget_secure_wipe)
        lay_collapse.setContentsMargins(0, 4, 0, 0)
        lay_collapse.setSpacing(0)

        lay_chk2 = QHBoxLayout()
        lay_chk2.setContentsMargins(37, 5, 5, 5)
        lay_chk2.setSpacing(0)

        self.chk_secure = KeyboardCheckbox(size=18)
        self.chk_secure.setObjectName("ChkSecure")
        self.chk_secure.setProperty("checked", False)
        self.chk_secure._checked = False
        self.chk_secure.hide()

        lbl_chk_title2 = QLabel("Advanced: Secure Wipe (Timpa data)")
        lbl_chk_title2.setStyleSheet("font-size: 9pt; color: #FFFFFF;")

        lay_chk2.addWidget(self.chk_secure, alignment=Qt.AlignmentFlag.AlignVCenter)
        lay_chk2.addSpacing(10)
        lay_chk2.addWidget(lbl_chk_title2)
        lay_chk2.addStretch()
        lay_collapse.addLayout(lay_chk2)
        lay_opsi_hapus.addWidget(self.widget_secure_wipe)

        # Animasi collapse secure wipe
        self.anim_secure = QPropertyAnimation(self.widget_secure_wipe, b"maximumHeight")
        self.anim_secure.setDuration(250)
        self.anim_secure.setEasingCurve(QEasingCurve.Type.InOutCubic)

        # Toggle handlers
        def _toggle_hapus_asli():
            self.chk_hapus._checked = not self.chk_hapus._checked
            self.chk_hapus.setProperty("checked", self.chk_hapus._checked)
            self.chk_hapus.style().unpolish(self.chk_hapus)
            self.chk_hapus.style().polish(self.chk_hapus)

            if self.chk_hapus._checked:
                self.widget_secure_wipe.show()
                self.chk_secure.show()
                self.anim_secure.setStartValue(0)
                self.anim_secure.setEndValue(50)
                self.anim_secure.start()
            else:
                self.anim_secure.setStartValue(self.widget_secure_wipe.maximumHeight())
                self.anim_secure.setEndValue(0)
                self.anim_secure.start()
                self.anim_secure.finished.connect(self._on_secure_collapsed)
                if self.chk_secure._checked:
                    self.chk_secure._checked = False
                    self.chk_secure.setProperty("checked", False)
                    self.chk_secure.style().unpolish(self.chk_secure)
                    self.chk_secure.style().polish(self.chk_secure)

            self._update_btn_label()

        def _toggle_secure_wipe():
            if not self.chk_hapus._checked:
                return
            if not self.chk_secure._checked:
                dialog = ModernMessageBox(
                    title="Peringatan Perangkat Keras",
                    message="Secure Wipe akan menimpa data asli dengan byte kosong sebelum dihapus agar sulit dipulihkan.\n\n"
                    "PERHATIAN:\n"
                    "• Jangan gunakan opsi ini jika file berada di SSD atau Flashdisk karena dapat merusak umur disk.\n"
                    "• Hanya gunakan untuk Harddisk (HDD) piringan tradisional.\n\n"
                    "Apakah Anda yakin ingin mengaktifkan opsi ini?",
                    icon_name="mdi6.alert-decagram",
                    icon_color="#E67E22",
                    parent=self,
                )
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
            self.chk_secure._checked = not self.chk_secure._checked
            self.chk_secure.setProperty("checked", self.chk_secure._checked)
            self.chk_secure.style().unpolish(self.chk_secure)
            self.chk_secure.style().polish(self.chk_secure)

        self.chk_hapus._on_toggle = _toggle_hapus_asli
        self.chk_secure._on_toggle = _toggle_secure_wipe

        return lay_opsi_hapus

    def _setup_accessibility(self):
        """Memasang event filter, focus policy, dan tab order untuk keyboard navigation."""
        # Event filter untuk animasi border focus & keyboard shortcut
        self.btn_gen.installEventFilter(self)
        self.entry_pw1.installEventFilter(self)
        self.btn_toggle_pw1.installEventFilter(self)
        self.entry_pw2.installEventFilter(self)
        self.btn_toggle_pw2.installEventFilter(self)
        self.btn_empty_browse.installEventFilter(self)
        self.btn_add.installEventFilter(self)

        # Paksa tombol custom nerima fokus keyboard (Tab)
        self.btn_gen.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_empty_browse.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_add.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_aksi.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Tab order yang masuk akal
        self.setTabOrder(self.btn_empty_browse, self.btn_add)
        self.setTabOrder(self.btn_add, self.chk_hapus)
        self.setTabOrder(self.chk_hapus, self.chk_secure)
        self.setTabOrder(self.chk_secure, self.btn_gen)
        self.setTabOrder(self.btn_gen, self.entry_pw1)
        self.setTabOrder(self.entry_pw1, self.btn_toggle_pw1)
        self.setTabOrder(self.btn_toggle_pw1, self.entry_pw2)
        self.setTabOrder(self.entry_pw2, self.btn_toggle_pw2)
        self.setTabOrder(self.btn_toggle_pw2, self.btn_aksi)

    def eventFilter(self, obj, event):
        # 1. Animasi border luar otomatis saat QLineEdit fokus
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

        # 2. Fungsi tombol Enter untuk semua Ikon Mata
        elif event.type() == event.Type.KeyPress:
            # Cegat tombol Enter atau Spasi
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                if isinstance(obj, QPushButton):
                    # Logic buat tombol mata
                    if obj.objectName() == "BtnEye":
                        obj.click()
                        return True
                    # 🔥 TAMBAHIN INI: Logic buat buka menu Dropdown
                    elif obj in (
                        getattr(self, "btn_empty_browse", None),
                        getattr(self, "btn_add", None),
                    ):
                        if obj.menu():
                            obj.showMenu()  # Paksa menu terbuka
                        return True
                    elif obj == self.btn_gen:  # TAMBAH BLOK INI
                        obj.click()
                        return True

        return super().eventFilter(obj, event)

    def _generate_pw(self):
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        while True:
            pw = "".join(secrets.choice(alphabet) for i in range(16))
            if (
                any(c.islower() for c in pw)
                and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw)
                and any(not c.isalnum() and not c.isspace() for c in pw)
            ):
                break

        self.entry_pw1.setText(pw)
        self.entry_pw2.setText(pw)

        self.entry_pw1.setEchoMode(QLineEdit.EchoMode.Normal)
        self.entry_pw2.setEchoMode(QLineEdit.EchoMode.Normal)
        self.btn_toggle_pw1.setIcon(qta.icon("mdi6.eye-off-outline", color="#8B95A5"))
        self.btn_toggle_pw2.setIcon(qta.icon("mdi6.eye-off-outline", color="#8B95A5"))

    def _pilih_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Pilih Folder")
        if folder:
            self._add_paths([folder])

    def _pilih_file(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Pilih File")
        if files:
            self._add_paths(files)

    def _add_paths(self, new_paths):
        for p in new_paths:
            if p.lower().endswith(".locked"):
                self.notif.show_msg(
                    "warn", f"⚠ '{os.path.basename(p)}' sudah jadi file brankas!", 4000
                )
                continue
            if p not in self._paths:
                self._paths.append(p)
        self._render_list()

    def _remove_path(self, path):
        if path in self._paths:
            self._paths.remove(path)
            self._render_list()

    def _render_list(self):
        if hasattr(self, "_custom_tooltip"):
            self._custom_tooltip.hide_tooltip()

        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._paths:
            self.stack_target.setCurrentIndex(0)
            self._update_card_style(True)
            self._validate_state()
            return

        self.stack_target.setCurrentIndex(1)
        self._update_card_style(False)

        for p in self._paths:
            row = FileListRow(p, self._custom_tooltip)

            r_lay = QHBoxLayout(row)
            r_lay.setContentsMargins(15, 0, 15, 0)

            ikon = QLabel()
            ikon_name = "mdi6.file-document" if os.path.isfile(p) else "mdi6.folder"
            ikon.setPixmap(qta.icon(ikon_name, color="#8B95A5").pixmap(24, 24))

            v_file = QVBoxLayout()
            v_file.setSpacing(2)
            v_file.setAlignment(Qt.AlignmentFlag.AlignVCenter)

            lbl_name = ElidedLabel(
                os.path.basename(p), mode=Qt.TextElideMode.ElideMiddle
            )
            lbl_name.setStyleSheet(
                "font-weight: 600; font-size: 10pt; background: transparent;"
            )

            lbl_path = ElidedLabel(p, mode=Qt.TextElideMode.ElideMiddle)
            lbl_path.setStyleSheet(
                "font-size: 8pt; color: #8B95A5; background: transparent;"
            )

            v_file.addWidget(lbl_name)
            v_file.addWidget(lbl_path)

            size_str = ""
            if os.path.isfile(p):
                size_kb = os.path.getsize(p) / 1024
                size_str = (
                    f"{size_kb:.2f} KB"
                    if size_kb < 1024
                    else f"{(size_kb/1024):.2f} MB"
                )
            lbl_sz = QLabel(size_str)
            lbl_sz.setStyleSheet(
                "font-size: 9pt; color: #8B95A5; background: transparent;"
            )

            btn_rm = QPushButton()
            btn_rm.setIcon(
                qta.icon("mdi6.close", color="#8B95A5", color_active="white")
            )
            btn_rm.setIconSize(QSize(20, 20))
            btn_rm.setObjectName("BtnGhost")
            btn_rm.setFixedSize(32, 32)
            btn_rm.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            btn_rm.setToolTip(f"Hapus {os.path.basename(p)} dari daftar")
            btn_rm.clicked.connect(
                lambda checked=False, path=p: self._remove_path(path)
            )

            r_lay.addWidget(ikon)
            r_lay.addSpacing(10)
            r_lay.addLayout(v_file, 1)
            r_lay.addWidget(lbl_sz)
            r_lay.addSpacing(10)
            r_lay.addWidget(btn_rm)

            self.list_layout.addWidget(row)

        self.list_layout.addStretch()
        self._validate_state()

    def _make_btn_rm_accessible(self, btn_rm):
        """Pasang event filter agar Enter/Space bisa trigger btn_rm."""
        btn_rm.installEventFilter(self)

    def _toggle_field(self, entry: QLineEdit, btn: QPushButton):
        """FIX: Toggle show/hide per-field secara independen."""
        mode = (
            QLineEdit.EchoMode.Normal
            if entry.echoMode() == QLineEdit.EchoMode.Password
            else QLineEdit.EchoMode.Password
        )
        entry.setEchoMode(mode)
        color = "#00D2C8" if mode == QLineEdit.EchoMode.Normal else "#8B95A5"
        icon_name = (
            "mdi6.eye-outline"
            if mode == QLineEdit.EchoMode.Password
            else "mdi6.eye-off-outline"
        )
        btn.setIcon(qta.icon(icon_name, color=color))

    def _on_pw_change(self):
        self.notif.hide_msg()
        pw1, pw2 = self.entry_pw1.text(), self.entry_pw2.text()

        if not pw1:
            if getattr(self, "_strength_visible", False):
                self._strength_visible = False
                self.anim_strength.setStartValue(self.widget_strength.maximumHeight())
                self.anim_strength.setEndValue(0)
                self.anim_strength.start()
        else:
            if not getattr(self, "_strength_visible", False):
                self._strength_visible = True
                self.anim_strength.setStartValue(0)
                self.anim_strength.setEndValue(26)
                self.anim_strength.start()

            score = pw_strength(pw1)
            for i, bar in enumerate(self.str_bars):
                if score >= 0 and i <= score:
                    bar.setStyleSheet(
                        f"background-color: {STRENGTH_COLORS[score]}; border-radius: 3px;"
                    )
                else:
                    bar.setStyleSheet("background-color: #232B3E; border-radius: 3px;")

            if score < 0:
                self.lbl_str.setText("Kekuatan: -")
                self.lbl_str.setStyleSheet(
                    "font-size: 9pt; color: #8B95A5; font-weight: bold;"
                )
            else:
                self.lbl_str.setText(f"Kekuatan: {STRENGTH_LABELS[score]}")
                self.lbl_str.setStyleSheet(
                    f"color: {STRENGTH_COLORS[score]}; font-size: 9pt; font-weight: bold;"
                )

        rules = [
            (len(pw1) >= 8, self.chk_len_icon, self.chk_len_lbl),
            (any(c.isupper() for c in pw1), self.chk_upper_icon, self.chk_upper_lbl),
            (any(c.islower() for c in pw1), self.chk_lower_icon, self.chk_lower_lbl),
            (any(c.isdigit() for c in pw1), self.chk_digit_icon, self.chk_digit_lbl),
            (
                any(not c.isalnum() and not c.isspace() for c in pw1),
                self.chk_sym_icon,
                self.chk_sym_lbl,
            ),
        ]

        for is_valid, icon, lbl in rules:
            if is_valid:
                icon.setPixmap(
                    qta.icon("mdi6.check-circle", color="#28c75d").pixmap(16, 16)
                )
                lbl.setStyleSheet("color: #FFFFFF; font-size: 9pt;")
            else:
                icon.setPixmap(
                    qta.icon("mdi6.check-circle", color="#232B3E").pixmap(16, 16)
                )
                lbl.setStyleSheet("color: #8B95A5; font-size: 9pt;")

        if not pw2:
            self.icon_match.hide()
            self.lbl_match_txt.hide()
        elif pw1 == pw2:
            self.icon_match.show()
            self.lbl_match_txt.show()
            self.icon_match.setPixmap(
                qta.icon("mdi6.check-circle", color="#28c75d").pixmap(16, 16)
            )
            self.lbl_match_txt.setText("Password cocok")
            self.lbl_match_txt.setStyleSheet(
                "font-size: 9pt; color: #28c75d; font-weight: bold;"
            )
        else:
            self.icon_match.show()
            self.lbl_match_txt.show()
            self.icon_match.setPixmap(
                qta.icon("mdi6.close-circle", color="#E74C3C").pixmap(16, 16)
            )
            self.lbl_match_txt.setText("Password tidak cocok")
            self.lbl_match_txt.setStyleSheet(
                "font-size: 9pt; color: #E74C3C; font-weight: bold;"
            )

        self._validate_state()

    def _validate_state(self):
        if self.worker is not None:
            return
        pw1, pw2 = self.entry_pw1.text(), self.entry_pw2.text()
        score = pw_strength(pw1)
        is_strong_enough = score >= 1
        enabled = (
            len(self._paths) > 0 and bool(pw1) and (pw1 == pw2) and is_strong_enough
        )
        self.btn_aksi.setEnabled(enabled)
        self.btn_aksi.setFocusPolicy(
            Qt.FocusPolicy.StrongFocus if enabled else Qt.FocusPolicy.NoFocus
        )

    def _update_progress(self, val):
        if self.worker and not getattr(self.worker, "_is_cancelled", False):
            self.btn_aksi.setTextLabels(
                "MENGUNCI...", f"Progress: {int(val*100)}% (Klik untuk Batal)"
            )

    def _proses(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.btn_aksi.setTextLabels("MEMBATALKAN...", "Harap tunggu...")
            self.btn_aksi.setEnabled(False)
            return

        pw = self.entry_pw1.text()

        if self.chk_hapus._checked:
            dialog = ModernMessageBox(
                title="Konfirmasi Hapus Asli",
                message="File atau folder asli akan DIHAPUS PERMANEN setelah berhasil dikunci.\n\nApakah Anda yakin ingin melanjutkan?",
                parent=self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

        default_name = os.path.basename(self._paths[0]) or "Brankas_Rahasia"
        path_simpan, _ = QFileDialog.getSaveFileName(
            self, "Simpan Brankas", f"{default_name}.locked", "File Terkunci (*.locked)"
        )
        if not path_simpan:
            return

        self._set_busy(True)
        self.worker = CryptoWorker(
            kunci_brankas,
            list(self._paths),
            path_simpan,
            pw,
            hapus_asli=self.chk_hapus._checked,
            secure_wipe=self.chk_secure._checked,
        )

        self.entry_pw1.blockSignals(True)
        self.entry_pw2.blockSignals(True)
        self.entry_pw1.clear()
        self.entry_pw2.clear()

        self.entry_pw1.setEchoMode(QLineEdit.EchoMode.Password)
        self.entry_pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self.btn_toggle_pw1.setIcon(qta.icon("mdi6.eye-outline", color="#8B95A5"))
        self.btn_toggle_pw2.setIcon(qta.icon("mdi6.eye-outline", color="#8B95A5"))

        self.entry_pw1.blockSignals(False)
        self.entry_pw2.blockSignals(False)

        for bar in self.str_bars:
            bar.setStyleSheet("background-color: #232B3E; border-radius: 3px;")
        self.lbl_str.setText("Kekuatan: -")
        self.lbl_str.setStyleSheet("font-size: 9pt; color: #8B95A5; font-weight: bold;")

        self.icon_match.hide()
        self.lbl_match_txt.hide()

        self._on_pw_change()

        if getattr(self, "_strength_visible", False):
            self._strength_visible = False
            self.anim_strength.setStartValue(self.widget_strength.maximumHeight())
            self.anim_strength.setEndValue(0)
            self.anim_strength.start()

        # Ubah bagian .connect ini
        self.worker.progress.connect(self._update_progress)
        self.worker.finished.connect(self._on_selesai)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def _set_busy(self, busy: bool):
        self.btn_add.setEnabled(not busy)
        self.btn_empty_browse.setEnabled(not busy)
        self.btn_gen.setEnabled(not busy)
        # FIX: Disable seluruh file list saat proses berjalan
        # agar tombol X di tiap row tidak memberikan hover state yang menyesatkan
        self.inner_frame.setEnabled(not busy)
        if busy:
            self.btn_aksi.setTextLabels(
                "MENGUNCI BRANKAS...", "Harap tunggu, proses sedang berjalan"
            )
            self.btn_aksi.setEnabled(True)
        else:
            self._update_btn_label()
            self._validate_state()

    def _update_btn_label(self):
        """FIX: Ubah label tombol aksi secara dinamis sesuai state hapus_asli."""
        if self.chk_hapus._checked:
            self.btn_aksi.setTextLabels(
                "ENKRIPSI & HAPUS ASLI", "File asli akan dihapus setelah dikunci"
            )
        else:
            self.btn_aksi.setTextLabels(
                "KUNCI SEKARANG", "Proses penguncian akan dimulai"
            )

    def _on_secure_collapsed(self):
        self.chk_secure.hide()
        self.anim_secure.finished.disconnect(self._on_secure_collapsed)

    def _on_selesai(self, result):
        self.worker = None
        status, pesan = result

        if status == VaultStatus.SUCCESS:
            self._paths.clear()

            # Reset opsi UI hapus asli & secure wipe
            self.chk_hapus._checked = False
            self.chk_hapus.setProperty("checked", False)
            self.chk_hapus.style().unpolish(self.chk_hapus)
            self.chk_hapus.style().polish(self.chk_hapus)

            self.chk_secure._checked = False
            self.chk_secure.setProperty("checked", False)
            self.chk_secure.style().unpolish(self.chk_secure)
            self.chk_secure.style().polish(self.chk_secure)

            self.anim_secure.setStartValue(self.widget_secure_wipe.maximumHeight())
            self.anim_secure.setEndValue(0)
            self.anim_secure.start()

            self._render_list()

        self._set_busy(False)

        if status == VaultStatus.SUCCESS:
            logger.info(f"Enkripsi sukses: {pesan}")
            self.notif.show_msg("ok", f" {pesan}", 6000)
            if HAS_PLYER and notification:
                try:
                    notification.notify(
                        title="Digital Locker",
                        message="Brankas dikunci dengan aman.",
                        timeout=5,
                    )
                except Exception as e:
                    logger.warning(f"Notifikasi sistem gagal: {e}")

        elif status == VaultStatus.CANCELLED:
            logger.info("Enkripsi dibatalkan oleh pengguna.")
            self.notif.show_msg("warn", "Proses penguncian dibatalkan.", 4000)

        else:
            logger.error(f"Gagal mengunci: {pesan}")
            self.notif.show_msg("err", f" {pesan}", 6000)
