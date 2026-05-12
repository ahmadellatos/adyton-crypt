"""
ui/tab_buka.py
Tab "Buka Brankas" dengan proporsi mewah ala CustomTkinter.
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
    QProgressBar,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics

from core.vault import buka_brankas

# FIX #1 — Import apply_shadow dari widgets, bukan dari app, agar tidak ada
# circular import (app.py ← tab_buka.py ← app.py).
from .widgets import CryptoWorker, AnimatedNotifBar, apply_shadow
from .styles import CLR_ACCENT

log = logging.getLogger(__name__)


class DropTargetFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)
        self.setProperty("dragActive", False)
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
        # FIX #2 — Deklarasi eksplisit agar cek `is not None` selalu valid
        self.worker: CryptoWorker | None = None
        self._build_ui()

    def _build_ui(self):
        # FIX #1 — apply_shadow sudah diimport di atas, tidak perlu lazy import lagi
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(15)

        lbl_info = QLabel("Masukkan file .locked dan password untuk membuka")
        lbl_info.setStyleSheet("color: #6B7280; font-size: 10pt; font-weight: bold;")
        main_layout.addWidget(lbl_info)

        h_container = QHBoxLayout()
        h_container.setSpacing(15)
        main_layout.addLayout(h_container)

        # --- KOLOM KIRI ---
        self.card_file = DropTargetFrame()
        apply_shadow(self.card_file)
        self.card_file.on_file_dropped = self._set_file

        v_left = QVBoxLayout(self.card_file)
        v_left.setContentsMargins(20, 20, 20, 20)
        v_left.setSpacing(15)

        lbl_title_file = QLabel("📄  FILE BRANKAS (.locked)")
        lbl_title_file.setObjectName("CardTitle")
        v_left.addWidget(lbl_title_file)

        row_browse = QHBoxLayout()
        self.btn_browse = QPushButton("Browse .locked")
        self.btn_browse.setFixedHeight(42)
        self.btn_browse.clicked.connect(self._pilih_file)
        row_browse.addWidget(self.btn_browse)

        self.btn_clear = QPushButton("✖")
        self.btn_clear.setObjectName("BtnGhost")
        self.btn_clear.setFixedSize(42, 42)
        self.btn_clear.clicked.connect(self._clear_file)
        self.btn_clear.hide()
        row_browse.addWidget(self.btn_clear)
        v_left.addLayout(row_browse)

        self.lbl_path = QLabel("File belum dipilih\n\natau seret file .locked ke sini")
        self.lbl_path.setObjectName("Inner")
        self.lbl_path.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_path.setWordWrap(True)
        self.lbl_path.setStyleSheet("color: #6B7280; font-weight: bold;")
        v_left.addWidget(self.lbl_path, 1)
        h_container.addWidget(self.card_file, 1)

        # --- KOLOM KANAN ---
        col_right = QVBoxLayout()
        col_right.setSpacing(12)
        h_container.addLayout(col_right, 1)

        card_pw = QFrame()
        card_pw.setObjectName("Card")
        apply_shadow(card_pw)

        v_pw = QVBoxLayout(card_pw)
        v_pw.setContentsMargins(20, 20, 20, 20)
        v_pw.setSpacing(15)

        lbl_title_pw = QLabel("🔑  MASUKKAN PASSWORD")
        lbl_title_pw.setObjectName("CardTitle")
        v_pw.addWidget(lbl_title_pw)

        row_pw_input = QHBoxLayout()
        self.entry_pw = QLineEdit()
        self.entry_pw.setFixedHeight(42)
        self.entry_pw.setPlaceholderText("Ketik password di sini…")
        self.entry_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.entry_pw.textChanged.connect(self._validate_state)
        self.entry_pw.returnPressed.connect(self._proses)
        row_pw_input.addWidget(self.entry_pw)

        self.btn_toggle_pw = QPushButton("👁")
        self.btn_toggle_pw.setObjectName("BtnGhost")
        self.btn_toggle_pw.setFixedSize(42, 42)
        self.btn_toggle_pw.clicked.connect(self._toggle_pw)
        row_pw_input.addWidget(self.btn_toggle_pw)

        v_pw.addLayout(row_pw_input)
        col_right.addWidget(card_pw)

        col_right.addStretch()

        # --- ACTION AREA ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.hide()
        col_right.addWidget(self.progress_bar)

        self.btn_aksi = QPushButton("BUKA BRANKAS")
        self.btn_aksi.setFixedHeight(46)
        self.btn_aksi.setEnabled(False)
        self.btn_aksi.clicked.connect(self._proses)
        col_right.addWidget(self.btn_aksi)

        self.notif = AnimatedNotifBar()
        col_right.addWidget(self.notif)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _toggle_pw(self):
        mode = (
            QLineEdit.EchoMode.Normal
            if self.entry_pw.echoMode() == QLineEdit.EchoMode.Password
            else QLineEdit.EchoMode.Password
        )
        self.entry_pw.setEchoMode(mode)

    def _validate_state(self):
        self.notif.hide_msg()
        if not self._konfirmasi_timpa:
            self.btn_aksi.setEnabled(
                self._path_file is not None and bool(self.entry_pw.text())
            )

    def _set_file(self, path: str):
        self._path_file = path

        # FIX #7 — Gunakan QFontMetrics.elidedText agar truncation responsif
        # terhadap lebar widget, bukan magic number hardcoded.
        metrics = QFontMetrics(self.lbl_path.font())
        available_width = self.lbl_path.width() - 24  # 24px untuk padding
        if available_width > 0:
            tampil = metrics.elidedText(
                path, Qt.TextElideMode.ElideLeft, available_width
            )
        else:
            # Fallback saat widget belum ter-render (width masih 0)
            tampil = path if len(path) < 50 else "…" + path[-47:]

        self.lbl_path.setText(tampil)
        self.lbl_path.setToolTip(path)  # Full path tetap bisa dilihat via tooltip
        self.lbl_path.setStyleSheet(f"color: {CLR_ACCENT}; font-weight: bold;")
        self.btn_clear.show()
        self._reset_timpa()
        self._validate_state()

    def _clear_file(self):
        self._path_file = None
        self.lbl_path.setText("File belum dipilih\n\natau seret file .locked ke sini")
        self.lbl_path.setToolTip("")
        self.lbl_path.setStyleSheet("color: #6B7280; font-weight: bold;")
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
        self.btn_aksi.setText("BUKA BRANKAS")
        self.btn_aksi.setObjectName("")
        self.btn_aksi.setStyleSheet("")

    # -----------------------------------------------------------------------
    # Proses utama
    # -----------------------------------------------------------------------

    def _proses(self):
        # FIX #2 — Guard: jangan spawn worker baru kalau yang lama masih jalan
        if self.worker is not None and self.worker.isRunning():
            self.notif.show_msg("warn", "⚠ Proses sebelumnya masih berjalan…", 3000)
            return

        force = self._konfirmasi_timpa
        if force:
            self._reset_timpa()

        if not self._path_file:
            return self.notif.show_msg("warn", "⚠ Pilih file .locked dulu!", 4000)
        pw = self.entry_pw.text()
        if not pw:
            return self.notif.show_msg("warn", "⚠ Masukkan password!", 4000)

        self._set_busy(True)
        self.worker = CryptoWorker(buka_brankas, self._path_file, pw, force)
        self.worker.progress.connect(self._update_progress)
        self.worker.finished.connect(self._on_selesai)
        # FIX #2 — Auto cleanup worker saat thread selesai
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def _set_busy(self, busy: bool):
        if busy:
            self.progress_bar.setValue(0)
            self.progress_bar.show()
            self.btn_aksi.setEnabled(False)
            self.btn_aksi.setText("⏳ Membuka...")
            self.btn_browse.setEnabled(False)
        else:
            self.progress_bar.hide()
            self.btn_aksi.setText("BUKA BRANKAS")
            self.btn_browse.setEnabled(True)
            self._validate_state()

    def _update_progress(self, val: float):
        self.progress_bar.setValue(int(val * 100))

    def _on_selesai(self, result):
        self._set_busy(False)
        status, msg = result

        if status == "SUCCESS":
            self.notif.show_msg(
                "ok", f"✔ Folder/File '{msg}' berhasil dikembalikan!", 6000
            )
            self.entry_pw.clear()
            self._clear_file()
        elif status == "WRONG_PW":
            self.notif.show_msg("err", "✖ Password salah! Coba lagi.")
        elif status == "OVERWRITE":
            self._konfirmasi_timpa = True
            self.btn_aksi.setText("⚠ KLIK LAGI UNTUK TIMPA")
            self.btn_aksi.setObjectName("BtnDanger")
            self.btn_aksi.setStyleSheet("/* Refreshing QSS state */")
            self.btn_aksi.setEnabled(True)
            self.notif.show_msg(
                "warn", f"⚠ '{msg}' sudah ada! Klik lagi untuk menimpa."
            )
        else:
            log.error("Gagal membuka brankas: %s", msg)
            self.notif.show_msg("err", f"✖ Error: {msg}", 8000)
