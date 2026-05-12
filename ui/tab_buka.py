"""
ui/tab_buka.py
Adaptasi input box dengan ikon terintegrasi di dalamnya.
"""

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
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics

from core.vault import buka_brankas
from .widgets import CryptoWorker, AnimatedNotifBar, apply_shadow, BigActionBtn

log = logging.getLogger(__name__)


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

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(20)

        h_container = QHBoxLayout()
        h_container.setSpacing(20)

        # --- KOLOM KIRI ---
        self.card_file = DropTargetFrame()
        apply_shadow(self.card_file, blur_radius=30, opacity=40)
        self.card_file.on_file_dropped = self._set_file

        v_left = QVBoxLayout(self.card_file)
        v_left.setContentsMargins(25, 25, 25, 25)
        v_left.setSpacing(15)

        lbl_title_file = QLabel("FILE BRANKAS (.locked)")
        lbl_title_file.setObjectName("CardTitle")
        v_left.addWidget(lbl_title_file)

        row_browse = QHBoxLayout()
        self.btn_browse = QPushButton("\ue8a5  Browse .locked")
        self.btn_browse.setStyleSheet("font-family: 'Segoe UI', 'Segoe MDL2 Assets';")
        self.btn_browse.setFixedHeight(45)
        self.btn_browse.clicked.connect(self._pilih_file)
        row_browse.addWidget(self.btn_browse)

        self.btn_clear = QPushButton("\ue8bb")
        self.btn_clear.setObjectName("BtnGhost")
        self.btn_clear.setFixedSize(45, 45)
        self.btn_clear.clicked.connect(self._clear_file)
        self.btn_clear.hide()
        row_browse.addWidget(self.btn_clear)
        v_left.addLayout(row_browse)

        self.lbl_path = QLabel("File belum dipilih\n\natau seret file .locked ke sini")
        self.lbl_path.setObjectName("Inner")
        self.lbl_path.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_path.setWordWrap(True)
        self.lbl_path.setStyleSheet("color: #8B95A5; font-weight: bold;")
        v_left.addWidget(self.lbl_path, 1)
        h_container.addWidget(self.card_file, 1)

        # --- KOLOM KANAN ---
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

        # Menggunakan struktur InputBox (Ikon Mata Terintegrasi di dalam)
        box_pw = QFrame()
        box_pw.setObjectName("InputBox")
        lay_box = QHBoxLayout(box_pw)
        lay_box.setContentsMargins(10, 0, 5, 0)
        lay_box.setSpacing(0)

        self.entry_pw = QLineEdit()
        self.entry_pw.setObjectName("InputInside")
        self.entry_pw.setFixedHeight(45)
        self.entry_pw.setPlaceholderText("Ketik password di sini…")
        self.entry_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.entry_pw.textChanged.connect(self._validate_state)
        self.entry_pw.returnPressed.connect(self._proses)
        lay_box.addWidget(self.entry_pw)

        self.btn_toggle_pw = QPushButton("\ue18b")
        self.btn_toggle_pw.setObjectName("BtnEye")
        self.btn_toggle_pw.setFixedSize(40, 45)
        self.btn_toggle_pw.clicked.connect(self._toggle_pw)
        lay_box.addWidget(self.btn_toggle_pw)

        v_pw.addWidget(box_pw)
        v_pw.addStretch()
        col_right.addWidget(card_pw, 1)
        h_container.addLayout(col_right, 1)

        main_layout.addLayout(h_container)

        # --- ACTION AREA ---
        self.notif = AnimatedNotifBar()
        main_layout.addWidget(self.notif)

        self.btn_aksi = BigActionBtn(
            "BUKA BRANKAS", "Masukkan password untuk membuka kunci", icon="\ue785"
        )
        self.btn_aksi.setEnabled(False)
        self.btn_aksi.clicked.connect(self._proses)
        apply_shadow(self.btn_aksi, blur_radius=20, y_offset=4, opacity=80)
        main_layout.addWidget(self.btn_aksi)

    def _toggle_pw(self):
        mode = (
            QLineEdit.EchoMode.Normal
            if self.entry_pw.echoMode() == QLineEdit.EchoMode.Password
            else QLineEdit.EchoMode.Password
        )
        self.entry_pw.setEchoMode(mode)

        # Animasi warna ikon Eye saat diklik
        color = "#00D2C8" if mode == QLineEdit.EchoMode.Normal else "#8B95A5"
        self.btn_toggle_pw.setStyleSheet(f"color: {color};")

    def _validate_state(self):
        self.notif.hide_msg()
        if not self._konfirmasi_timpa:
            self.btn_aksi.setEnabled(
                self._path_file is not None and bool(self.entry_pw.text())
            )

    def _set_file(self, path: str):
        self._path_file = path
        metrics = QFontMetrics(self.lbl_path.font())
        available_width = self.lbl_path.width() - 24
        tampil = (
            metrics.elidedText(path, Qt.TextElideMode.ElideLeft, available_width)
            if available_width > 0
            else path
        )

        self.lbl_path.setText(tampil)
        self.lbl_path.setToolTip(path)
        self.lbl_path.setStyleSheet(f"color: #00D2C8; font-weight: bold;")
        self.btn_clear.show()
        self._reset_timpa()
        self._validate_state()

    def _clear_file(self):
        self._path_file = None
        self.lbl_path.setText("File belum dipilih\n\natau seret file .locked ke sini")
        self.lbl_path.setToolTip("")
        self.lbl_path.setStyleSheet("color: #8B95A5; font-weight: bold;")
        self.btn_clear.hide()
        self._reset_timpa()
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

    def _proses(self):
        if self.worker is not None and self.worker.isRunning():
            return
        force = self._konfirmasi_timpa
        if force:
            self._reset_timpa()

        pw = self.entry_pw.text()
        if not self._path_file or not pw:
            return

        self._set_busy(True)
        self.worker = CryptoWorker(buka_brankas, self._path_file, pw, force)
        self.worker.progress.connect(
            lambda v: self.btn_aksi.setTextLabels(
                "MEMBUKA...", f"Progress: {int(v*100)}%"
            )
        )
        self.worker.finished.connect(self._on_selesai)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def _set_busy(self, busy: bool):
        self.btn_aksi.setEnabled(not busy)
        self.btn_browse.setEnabled(not busy)
        if busy:
            self.btn_aksi.setTextLabels("MEMBUKA BRANKAS...", "Harap tunggu...")
        else:
            self.btn_aksi.setTextLabels(
                "BUKA BRANKAS", "Masukkan password untuk membuka kunci"
            )
            self._validate_state()

    def _on_selesai(self, result):
        self._set_busy(False)
        status, msg = result

        if status == "SUCCESS":
            self.notif.show_msg(
                "ok", f"Folder/File '{msg}' berhasil dikembalikan!", 6000
            )
            self.entry_pw.clear()
            self._clear_file()
        elif status == "WRONG_PW":
            self.notif.show_msg("err", "Password salah! Coba lagi.")
        elif status == "OVERWRITE":
            self._konfirmasi_timpa = True
            self.btn_aksi.setTextLabels(
                "TIMPA FILE YANG ADA", "Klik lagi untuk memaksa ekstrak"
            )
            self.btn_aksi.setEnabled(True)
            self.notif.show_msg("warn", f"'{msg}' sudah ada! Klik lagi untuk menimpa.")
        else:
            log.error("Error: %s", msg)
            self.notif.show_msg("err", f"Error: {msg}", 8000)
