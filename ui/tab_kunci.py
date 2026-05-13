"""
Modul: tab_kunci.py
Deskripsi: Antarmuka untuk Tab "Kunci Folder"
           Ditambahkan fitur Advanced: Secure Wipe dengan peringatan UI.
           Secure Wipe sekarang collapsible (muncul animasi saat Hapus Asli dicentang).
"""

import os
from loguru import logger
import qtawesome as qta
from zxcvbn import zxcvbn
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QFrame,
    QScrollArea,
    QMenu,
    QDialog,
)
from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve

from core.vault import kunci_brankas, VaultStatus
from .widgets import (
    CryptoWorker,
    AnimatedNotifBar,
    apply_shadow,
    BigActionBtn,
    ModernMessageBox,
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
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(20)

        h_cols = QHBoxLayout()
        h_cols.setSpacing(20)

        # ---------------------------------------------
        # KIRI (Daftar Target)
        # ---------------------------------------------
        v_left = QVBoxLayout()
        self.card_target = MultiDropFrame()
        self.card_target.on_paths_dropped = self._add_paths
        apply_shadow(self.card_target, blur_radius=30, opacity=40)

        lay_target = QVBoxLayout(self.card_target)
        lay_target.setContentsMargins(25, 25, 25, 25)
        lay_target.setSpacing(15)

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
        v_hdr_text.addWidget(lbl_target)
        v_hdr_text.addWidget(lbl_target_sub)

        row_hdr.addWidget(icon_folder)
        row_hdr.addLayout(v_hdr_text)
        row_hdr.addStretch()

        self.btn_add = QPushButton(" Tambah")
        self.btn_add.setIcon(qta.icon("mdi6.plus", color="#8B95A5"))
        self.btn_add.setObjectName("BtnGhost")
        self.btn_add.setFixedSize(100, 36)
        self.btn_add.setStyleSheet(
            "QPushButton#BtnGhost { font-size: 10pt; border: 1px solid #232B3E; } QPushButton::menu-indicator { image: none; width: 0px; }"
        )

        menu = QMenu(self)
        action_file = menu.addAction(" File")
        action_file.setIcon(qta.icon("mdi6.file-document", color="white"))
        action_file.triggered.connect(self._pilih_file)

        action_folder = menu.addAction(" Folder")
        action_folder.setIcon(qta.icon("mdi6.folder", color="white"))
        action_folder.triggered.connect(self._pilih_folder)

        self.btn_add.setMenu(menu)
        row_hdr.addWidget(self.btn_add, alignment=Qt.AlignmentFlag.AlignTop)
        lay_target.addLayout(row_hdr)

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

        inner_lay.addWidget(self.scroll_area)
        lay_target.addWidget(self.inner_frame, 1)
        v_left.addWidget(self.card_target, 1)

        # ---------------------------------------------
        # CONTAINER OPSI HAPUS (Hapus Asli & Secure Wipe)
        # ---------------------------------------------
        lay_opsi_hapus = QVBoxLayout()
        lay_opsi_hapus.setSpacing(0)

        # 1. Checkbox Hapus File Asli
        lay_chk1 = QHBoxLayout()
        lay_chk1.setContentsMargins(5, 5, 5, 0)
        lay_chk1.setSpacing(0)

        self.chk_hapus = QFrame()
        self.chk_hapus.setFixedSize(22, 22)
        self.chk_hapus.setStyleSheet("""
            QFrame { background: #181F32; border: 1px solid #232B3E; border-radius: 4px; }
            QFrame[checked="true"] { background: #E74C3C; border: 1px solid #E74C3C; }
        """)
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
        v_chk_txt1.addWidget(lbl_chk_title1)
        v_chk_txt1.addWidget(lbl_chk_desc1)

        lay_chk1.addWidget(self.chk_hapus, alignment=Qt.AlignmentFlag.AlignVCenter)
        lay_chk1.addSpacing(10)
        lay_chk1.addLayout(v_chk_txt1)
        lay_opsi_hapus.addLayout(lay_chk1)

        # 2. Secure Wipe — Collapsible Container
        self.widget_secure_wipe = QWidget()
        self.widget_secure_wipe.setMaximumHeight(0)  # collapsed by default
        self.widget_secure_wipe.setMinimumHeight(0)

        lay_collapse = QVBoxLayout(self.widget_secure_wipe)
        lay_collapse.setContentsMargins(0, 4, 0, 0)
        lay_collapse.setSpacing(0)

        lay_chk2 = QHBoxLayout()
        lay_chk2.setContentsMargins(37, 5, 5, 5)
        lay_chk2.setSpacing(0)

        self.chk_secure = QFrame()
        self.chk_secure.setFixedSize(18, 18)
        self.chk_secure.setStyleSheet("""
            QFrame { background: #181F32; border: 1px solid #232B3E; border-radius: 4px; }
            QFrame[checked="true"] { background: #E67E22; border: 1px solid #E67E22; }
        """)
        self.chk_secure.setProperty("checked", False)
        self.chk_secure._checked = False

        lbl_chk_title2 = QLabel("Advanced: Secure Wipe (Timpa data)")
        lbl_chk_title2.setStyleSheet("font-size: 9pt; color: #FFFFFF;")

        lay_chk2.addWidget(self.chk_secure, alignment=Qt.AlignmentFlag.AlignVCenter)
        lay_chk2.addSpacing(10)
        lay_chk2.addWidget(lbl_chk_title2)
        lay_chk2.addStretch()
        lay_collapse.addLayout(lay_chk2)

        lay_opsi_hapus.addWidget(self.widget_secure_wipe)
        v_left.addLayout(lay_opsi_hapus)
        h_cols.addLayout(v_left, 1)

        # Animasi expand/collapse Secure Wipe
        self.anim_secure = QPropertyAnimation(self.widget_secure_wipe, b"maximumHeight")
        self.anim_secure.setDuration(250)
        self.anim_secure.setEasingCurve(QEasingCurve.Type.InOutCubic)

        # Logic Event Checkbox
        def _toggle_hapus_asli():
            self.chk_hapus._checked = not self.chk_hapus._checked
            self.chk_hapus.setProperty("checked", self.chk_hapus._checked)
            self.chk_hapus.style().unpolish(self.chk_hapus)
            self.chk_hapus.style().polish(self.chk_hapus)

            if self.chk_hapus._checked:
                # Expand Secure Wipe
                self.anim_secure.setStartValue(0)
                self.anim_secure.setEndValue(35)
                self.anim_secure.start()
            else:
                # Collapse Secure Wipe + reset
                self.anim_secure.setStartValue(self.widget_secure_wipe.maximumHeight())
                self.anim_secure.setEndValue(0)
                self.anim_secure.start()

                if self.chk_secure._checked:
                    self.chk_secure._checked = False
                    self.chk_secure.setProperty("checked", False)
                    self.chk_secure.style().unpolish(self.chk_secure)
                    self.chk_secure.style().polish(self.chk_secure)

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

        self.chk_hapus.mousePressEvent = lambda e: _toggle_hapus_asli()
        self.chk_secure.mousePressEvent = lambda e: _toggle_secure_wipe()

        # ---------------------------------------------
        # KANAN (Password Form)
        # ---------------------------------------------
        v_right = QVBoxLayout()
        card_pw = QFrame()
        card_pw.setObjectName("Card")
        apply_shadow(card_pw, blur_radius=30, opacity=40)

        lay_pw = QVBoxLayout(card_pw)
        lay_pw.setContentsMargins(25, 25, 25, 25)
        lay_pw.setSpacing(15)

        row_hdr_pw = QHBoxLayout()
        icon_key = QLabel()
        icon_key.setPixmap(qta.icon("mdi6.key-variant", color="#F39C12").pixmap(32, 32))

        v_hdr_pw_txt = QVBoxLayout()
        v_hdr_pw_txt.setSpacing(2)
        lbl_pw = QLabel("BUAT PASSWORD")
        lbl_pw.setObjectName("CardTitle")
        lbl_pw_sub = QLabel("Buat password yang kuat untuk melindungi data Anda")
        lbl_pw_sub.setObjectName("CardSubtitle")
        v_hdr_pw_txt.addWidget(lbl_pw)
        v_hdr_pw_txt.addWidget(lbl_pw_sub)

        row_hdr_pw.addWidget(icon_key)
        row_hdr_pw.addLayout(v_hdr_pw_txt)
        row_hdr_pw.addStretch()
        lay_pw.addLayout(row_hdr_pw)
        lay_pw.addSpacing(10)

        lbl_in1 = QLabel("Password")
        lbl_in1.setStyleSheet("font-weight: 600;")
        lay_pw.addWidget(lbl_in1)

        box_pw1 = QFrame()
        box_pw1.setObjectName("InputBox")
        lay_box1 = QHBoxLayout(box_pw1)
        lay_box1.setContentsMargins(10, 0, 5, 0)
        lay_box1.setSpacing(0)

        self.entry_pw1 = QLineEdit()
        self.entry_pw1.setObjectName("InputInside")
        self.entry_pw1.setFixedHeight(45)
        self.entry_pw1.setEchoMode(QLineEdit.EchoMode.Password)
        self.entry_pw1.textChanged.connect(self._on_pw_change)
        lay_box1.addWidget(self.entry_pw1)

        self.btn_toggle_pw = QPushButton()
        self.btn_toggle_pw.setIcon(qta.icon("mdi6.eye-outline", color="#8B95A5"))
        self.btn_toggle_pw.setIconSize(QSize(22, 22))
        self.btn_toggle_pw.setObjectName("BtnEye")
        self.btn_toggle_pw.setFixedSize(40, 45)
        self.btn_toggle_pw.clicked.connect(self._toggle_pw)
        lay_box1.addWidget(self.btn_toggle_pw)
        lay_pw.addWidget(box_pw1)

        row_str = QHBoxLayout()
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
        row_str.addWidget(self.lbl_str)
        lay_pw.addLayout(row_str)
        lay_pw.addSpacing(10)

        lbl_in2 = QLabel("Konfirmasi Password")
        lbl_in2.setStyleSheet("font-weight: 600;")
        lay_pw.addWidget(lbl_in2)

        box_pw2 = QFrame()
        box_pw2.setObjectName("InputBox")
        lay_box2 = QHBoxLayout(box_pw2)
        lay_box2.setContentsMargins(10, 0, 5, 0)
        lay_box2.setSpacing(0)

        self.entry_pw2 = QLineEdit()
        self.entry_pw2.setObjectName("InputInside")
        self.entry_pw2.setFixedHeight(45)
        self.entry_pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self.entry_pw2.textChanged.connect(self._on_pw_change)
        self.entry_pw2.returnPressed.connect(self._proses)
        lay_box2.addWidget(self.entry_pw2)

        self.lbl_match = QLabel("")
        self.lbl_match.setObjectName("IconInside")
        self.lbl_match.setFixedSize(40, 45)
        self.lbl_match.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay_box2.addWidget(self.lbl_match)
        lay_pw.addWidget(box_pw2)

        lay_pw.addStretch()

        tips_box = QFrame()
        tips_box.setObjectName("TipsBox")
        lay_tips = QHBoxLayout(tips_box)
        lay_tips.setContentsMargins(15, 15, 15, 15)
        lay_tips.setSpacing(12)

        icon_shield = QLabel()
        icon_shield.setPixmap(
            qta.icon("mdi6.shield-check-outline", color="#00D2C8").pixmap(32, 32)
        )
        icon_shield.setFixedSize(32, 32)

        v_tips = QVBoxLayout()
        v_tips.setSpacing(4)

        lbl_tips_title = QLabel("Tips Keamanan")
        lbl_tips_title.setStyleSheet("font-weight: 800; font-size: 10pt;")

        lbl_tips_desc = QLabel(
            "Minimal 8 karakter: huruf besar, huruf kecil, angka & simbol."
        )
        lbl_tips_desc.setWordWrap(True)
        lbl_tips_desc.setStyleSheet("font-size: 9pt; color: #8B95A5;")

        v_tips.addWidget(lbl_tips_title)
        v_tips.addWidget(lbl_tips_desc)

        lay_tips.addWidget(icon_shield, alignment=Qt.AlignmentFlag.AlignVCenter)
        lay_tips.addLayout(v_tips)

        lay_pw.addWidget(tips_box)

        v_right.addWidget(card_pw, 1)
        h_cols.addLayout(v_right, 1)
        main_layout.addLayout(h_cols)

        # BOTTOM ACTION BAR
        self.btn_aksi = BigActionBtn(
            "KUNCI SEKARANG", "Proses penguncian akan dimulai", icon_name="mdi6.lock"
        )
        self.btn_aksi.setEnabled(False)
        self.btn_aksi.clicked.connect(self._proses)
        apply_shadow(self.btn_aksi, blur_radius=20, y_offset=4, opacity=80)
        main_layout.addWidget(self.btn_aksi)

        self.notif = AnimatedNotifBar(self)
        self._render_list()

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
                    "warn", f"⚠ '{os.path.basename(p)}' sudah file brankas!", 4000
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
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._paths:
            lbl = QLabel("Belum ada target\n\nSeret file ke area ini")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                "color: #8B95A5; margin-top: 60px; font-weight: bold; font-size: 11pt;"
            )
            self.list_layout.addWidget(lbl)
            self._validate_state()
            return

        for p in self._paths:
            row = QFrame()
            row.setObjectName("ListItem")
            row.setFixedHeight(56)
            r_lay = QHBoxLayout(row)
            r_lay.setContentsMargins(15, 0, 15, 0)

            ikon = QLabel()
            ikon_name = "mdi6.file-document" if os.path.isfile(p) else "mdi6.folder"
            ikon.setPixmap(qta.icon(ikon_name, color="#8B95A5").pixmap(24, 24))

            v_file = QVBoxLayout()
            v_file.setSpacing(2)
            v_file.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            lbl_name = QLabel(os.path.basename(p))
            lbl_name.setStyleSheet(
                "font-weight: 600; font-size: 10pt; background: transparent;"
            )
            lbl_path = QLabel(p)
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

    def _toggle_pw(self):
        mode = (
            QLineEdit.EchoMode.Normal
            if self.entry_pw1.echoMode() == QLineEdit.EchoMode.Password
            else QLineEdit.EchoMode.Password
        )
        self.entry_pw1.setEchoMode(mode)
        self.entry_pw2.setEchoMode(mode)

        color = "#00D2C8" if mode == QLineEdit.EchoMode.Normal else "#8B95A5"
        icon_name = (
            "mdi6.eye-outline"
            if mode == QLineEdit.EchoMode.Password
            else "mdi6.eye-off-outline"
        )
        self.btn_toggle_pw.setIcon(qta.icon(icon_name, color=color))

    def _on_pw_change(self):
        self.notif.hide_msg()
        pw1, pw2 = self.entry_pw1.text(), self.entry_pw2.text()

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

        if not pw2:
            self.lbl_match.setPixmap(
                qta.icon("mdi6.check-bold", color="transparent").pixmap(20, 20)
            )
        elif pw1 == pw2:
            self.lbl_match.setPixmap(
                qta.icon("mdi6.check-bold", color="#00D2C8").pixmap(20, 20)
            )
        else:
            self.lbl_match.setPixmap(
                qta.icon("mdi6.close-thick", color="#E74C3C").pixmap(20, 20)
            )

        self._validate_state()

    def _validate_state(self):
        pw1, pw2 = self.entry_pw1.text(), self.entry_pw2.text()
        self.btn_aksi.setEnabled(len(self._paths) > 0 and bool(pw1) and (pw1 == pw2))

    def _proses(self):
        # Cancel Support
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
            self, "Simpan Brankas", f"{default_name}.locked", "Locked Files (*.locked)"
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
        self.entry_pw1.blockSignals(False)
        self.entry_pw2.blockSignals(False)

        for bar in self.str_bars:
            bar.setStyleSheet("background-color: #232B3E; border-radius: 3px;")
        self.lbl_str.setText("Kekuatan: -")
        self.lbl_str.setStyleSheet("font-size: 9pt; color: #8B95A5; font-weight: bold;")
        self.lbl_match.setPixmap(
            qta.icon("mdi6.check-bold", color="transparent").pixmap(20, 20)
        )

        del pw

        self.worker.progress.connect(
            lambda v: self.btn_aksi.setTextLabels(
                "MENGUNCI...", f"Progress: {int(v*100)}% (Klik untuk Batal)"
            )
        )
        self.worker.finished.connect(self._on_selesai)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def _set_busy(self, busy: bool):
        self.btn_add.setEnabled(not busy)
        if busy:
            self.btn_aksi.setTextLabels(
                "MENGUNCI BRANKAS...", "Harap tunggu, proses sedang berjalan"
            )
            self.btn_aksi.setEnabled(True)
        else:
            self.btn_aksi.setTextLabels(
                "KUNCI SEKARANG", "Proses penguncian akan dimulai"
            )
            self._validate_state()

    def _on_selesai(self, result):
        self.worker = None
        status, pesan = result

        if status == VaultStatus.SUCCESS:
            self._paths.clear()

            self.chk_hapus._checked = False
            self.chk_hapus.setProperty("checked", False)
            self.chk_hapus.style().unpolish(self.chk_hapus)
            self.chk_hapus.style().polish(self.chk_hapus)

            self.chk_secure._checked = False
            self.chk_secure.setProperty("checked", False)
            self.chk_secure.style().unpolish(self.chk_secure)
            self.chk_secure.style().polish(self.chk_secure)

            # Collapse secure wipe panel juga
            self.anim_secure.setStartValue(self.widget_secure_wipe.maximumHeight())
            self.anim_secure.setEndValue(0)
            self.anim_secure.start()

            self._render_list()

        self._set_busy(False)

        if status == VaultStatus.SUCCESS:
            self.notif.show_msg("ok", f" {pesan}", 6000)
            logger.info(f"Enkripsi sukses: {pesan}")
            if HAS_PLYER and notification:
                try:
                    notification.notify(
                        title="Digital Locker",
                        message="Brankas dikunci dengan aman.",
                        timeout=5,
                    )
                except:
                    pass
        elif status == VaultStatus.CANCELLED:
            self.notif.show_msg("warn", "Operasi penguncian dibatalkan pengguna.", 4000)
            logger.info("Enkripsi dibatalkan.")
        else:
            logger.error(f"Gagal mengunci: {pesan}")
            self.notif.show_msg("err", f" {pesan}", 6000)
