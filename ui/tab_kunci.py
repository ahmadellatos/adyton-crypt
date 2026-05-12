"""
ui/tab_kunci.py
Perbaikan Spasi (margin dihilangkan untuk presisi) & Ikon Input.
"""

import os
import re
import logging
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QFrame,
    QCheckBox,
    QScrollArea,
    QMenu,
    QMessageBox,
)
from PySide6.QtCore import Qt

from core.vault import kunci_brankas
from .widgets import CryptoWorker, AnimatedNotifBar, apply_shadow, BigActionBtn

log = logging.getLogger(__name__)


def pw_strength(pw: str) -> int:
    if not pw:
        return -1
    score = 0
    if len(pw) >= 8:
        score += 1
    if re.search(r"[A-Z]", pw) and re.search(r"[a-z]", pw):
        score += 1
    if re.search(r"\d", pw):
        score += 1
    if re.search(r"[!@#$%^&*()\-_=+\[\]{};:'\",.<>/?\\|`~]", pw):
        score += 1
    if pw and (max(pw.count(c) for c in set(pw)) / len(pw)) > 0.5:
        score = max(0, score - 1)
    return min(score, 3)


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

        # --- KOLOM KIRI ---
        v_left = QVBoxLayout()
        self.card_target = MultiDropFrame()
        self.card_target.on_paths_dropped = self._add_paths
        apply_shadow(self.card_target, blur_radius=30, opacity=40)

        lay_target = QVBoxLayout(self.card_target)
        lay_target.setContentsMargins(25, 25, 25, 25)
        lay_target.setSpacing(15)

        row_hdr = QHBoxLayout()
        icon_folder = QLabel("\ue8b7")
        icon_folder.setObjectName("Icon")
        icon_folder.setStyleSheet("font-size: 20pt; color: #F1C40F;")

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

        self.btn_add = QPushButton("\ue710  Tambah")
        self.btn_add.setObjectName("BtnGhost")
        self.btn_add.setFixedSize(100, 36)
        self.btn_add.setStyleSheet(
            "QPushButton#BtnGhost { font-size: 10pt; border: 1px solid #232B3E; } QPushButton::menu-indicator { image: none; width: 0px; }"
        )

        menu = QMenu(self)
        menu.addAction("\ue8a5  File", self._pilih_file)
        menu.addAction("\ue8b7  Folder", self._pilih_folder)
        self.btn_add.setMenu(menu)
        row_hdr.addWidget(self.btn_add, alignment=Qt.AlignmentFlag.AlignTop)
        lay_target.addLayout(row_hdr)

        self.scroll_area = QScrollArea()
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.list_container)
        self.scroll_area.setWidgetResizable(True)
        lay_target.addWidget(self.scroll_area, 1)

        v_left.addWidget(self.card_target, 1)

        # Checkbox Hapus Asli (FIX 5 & 6)
        lay_chk = QHBoxLayout()
        lay_chk.setContentsMargins(5, 5, 5, 0)
        lay_chk.setSpacing(0)  # FIX: Matikan spasi otomatis bawaan layout

        self.chk_hapus = QCheckBox()
        self.chk_hapus.setStyleSheet(
            "QCheckBox::indicator { width: 20px; height: 20px; border-radius: 4px; background: #181F32; border: 1px solid #232B3E; } QCheckBox::indicator:checked { background: #E74C3C; image: none; }"
        )

        v_chk_txt = QVBoxLayout()
        v_chk_txt.setSpacing(2)
        lbl_chk_title = QLabel("Hapus file/folder asli setelah dikunci")
        lbl_chk_title.setStyleSheet("font-size: 10pt; color: #FFFFFF;")
        lbl_chk_desc = QLabel(
            "File atau folder asli akan dihapus setelah proses penguncian berhasil."
        )
        lbl_chk_desc.setStyleSheet("font-size: 9pt; color: #8B95A5;")
        v_chk_txt.addWidget(lbl_chk_title)
        v_chk_txt.addWidget(lbl_chk_desc)

        lay_chk.addWidget(self.chk_hapus, alignment=Qt.AlignmentFlag.AlignTop)
        lay_chk.addSpacing(10)  # Jarak eksak 10px setelah checkbox
        lay_chk.addLayout(v_chk_txt)
        v_left.addLayout(lay_chk)
        h_cols.addLayout(v_left, 1)

        # --- KOLOM KANAN ---
        v_right = QVBoxLayout()
        card_pw = QFrame()
        card_pw.setObjectName("Card")
        apply_shadow(card_pw, blur_radius=30, opacity=40)

        lay_pw = QVBoxLayout(card_pw)
        lay_pw.setContentsMargins(25, 25, 25, 25)
        lay_pw.setSpacing(15)

        row_hdr_pw = QHBoxLayout()
        icon_key = QLabel("\ue104")
        icon_key.setObjectName("Icon")
        icon_key.setStyleSheet("font-size: 20pt; color: #F39C12;")
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

        # Input 1
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

        self.btn_toggle_pw = QPushButton("\ue18b")
        self.btn_toggle_pw.setObjectName("BtnEye")
        self.btn_toggle_pw.setFixedSize(
            40, 45
        )  # Karena padding sudah 0, ikon tak akan kepotong
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

        # Input 2
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
        self.lbl_match.setStyleSheet(
            "font-family: 'Segoe MDL2 Assets'; font-size: 14pt; background: transparent;"
        )
        lay_box2.addWidget(self.lbl_match)
        lay_pw.addWidget(box_pw2)

        lay_pw.addStretch()

        # Tips Box (FIX 5 & 6)
        tips_box = QFrame()
        tips_box.setObjectName("TipsBox")
        lay_tips = QHBoxLayout(tips_box)
        lay_tips.setContentsMargins(15, 15, 15, 15)
        lay_tips.setSpacing(0)  # FIX: Matikan spasi otomatis bawaan layout

        icon_shield = QLabel("\uea18")
        icon_shield.setObjectName("Icon")
        icon_shield.setStyleSheet("font-size: 20pt; color: #00D2C8;")

        v_tips = QVBoxLayout()
        v_tips.setSpacing(2)
        lbl_tips_title = QLabel("Tips Keamanan")
        lbl_tips_title.setStyleSheet("font-weight: 800; font-size: 10pt;")
        lbl_tips_desc = QLabel(
            "Gunakan minimal 8 karakter dengan kombinasi huruf besar, huruf kecil, angka, dan simbol untuk keamanan maksimal."
        )
        lbl_tips_desc.setWordWrap(True)
        lbl_tips_desc.setStyleSheet("font-size: 9pt; color: #8B95A5;")
        v_tips.addWidget(lbl_tips_title)
        v_tips.addWidget(lbl_tips_desc)

        lay_tips.addWidget(icon_shield, alignment=Qt.AlignmentFlag.AlignTop)
        lay_tips.addSpacing(12)  # Jarak eksak 12px setelah tameng
        lay_tips.addLayout(v_tips)
        lay_pw.addWidget(tips_box)

        v_right.addWidget(card_pw, 1)
        h_cols.addLayout(v_right, 1)
        main_layout.addLayout(h_cols)

        # --- BOTTOM ACTION BAR ---
        self.notif = AnimatedNotifBar()
        main_layout.addWidget(self.notif)

        self.btn_aksi = BigActionBtn(
            "KUNCI SEKARANG", "Proses penguncian akan dimulai", icon="\ue72e"
        )
        self.btn_aksi.setEnabled(False)
        self.btn_aksi.clicked.connect(self._proses)
        apply_shadow(self.btn_aksi, blur_radius=20, y_offset=4, opacity=80)
        main_layout.addWidget(self.btn_aksi)

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
            row.setObjectName("Inner")
            row.setFixedHeight(56)
            r_lay = QHBoxLayout(row)
            r_lay.setContentsMargins(15, 0, 15, 0)

            ikon = QLabel("\ue8a5" if os.path.isfile(p) else "\ue8b7")
            ikon.setObjectName("Icon")
            ikon.setStyleSheet(
                "font-size: 16pt; background: transparent; color: #8B95A5;"
            )

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

            btn_rm = QPushButton("\ue8bb")
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
        self.btn_toggle_pw.setStyleSheet(f"color: {color};")

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
            self.lbl_match.setText("")
        elif pw1 == pw2:
            self.lbl_match.setText("\ue73e")
            self.lbl_match.setStyleSheet("color: #00D2C8; background: transparent;")
        else:
            self.lbl_match.setText("\uea39")
            self.lbl_match.setStyleSheet("color: #E74C3C; background: transparent;")

        self._validate_state()

    def _validate_state(self):
        pw1, pw2 = self.entry_pw1.text(), self.entry_pw2.text()
        self.btn_aksi.setEnabled(len(self._paths) > 0 and bool(pw1) and (pw1 == pw2))

    def _proses(self):
        if not self._paths or (self.worker and self.worker.isRunning()):
            return
        pw = self.entry_pw1.text()

        if self.chk_hapus.isChecked():
            reply = QMessageBox.warning(
                self,
                "Konfirmasi",
                "File asli akan dihapus. Lanjutkan?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes:
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
            self.chk_hapus.isChecked(),
        )
        self.worker.progress.connect(
            lambda v: self.btn_aksi.setTextLabels(
                "MENGUNCI...", f"Progress: {int(v*100)}%"
            )
        )
        self.worker.finished.connect(self._on_selesai)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def _set_busy(self, busy: bool):
        self.btn_aksi.setEnabled(not busy)
        self.btn_add.setEnabled(not busy)
        if busy:
            self.btn_aksi.setTextLabels(
                "MENGUNCI BRANKAS...", "Harap tunggu, proses sedang berjalan"
            )
        else:
            self.btn_aksi.setTextLabels(
                "KUNCI SEKARANG", "Proses penguncian akan dimulai"
            )
            self._validate_state()

    def _on_selesai(self, result):
        self._set_busy(False)
        sukses, pesan = result
        if sukses:
            self.notif.show_msg("ok", f"✔ {pesan}", 6000)
            self.entry_pw1.clear()
            self.entry_pw2.clear()
            self._paths.clear()
            self.chk_hapus.setChecked(False)
            self._render_list()
        else:
            log.error("Gagal: %s", pesan)
            self.notif.show_msg("err", f"✖ {pesan}", 6000)
