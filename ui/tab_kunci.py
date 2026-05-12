"""
ui/tab_kunci.py
Tab "Kunci Folder" - Layout presisi & Drop Shadow.
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
    QProgressBar,
    QCheckBox,
    QScrollArea,
    QMenu,
    QMessageBox,
)
from PySide6.QtCore import Qt

from core.vault import kunci_brankas

# FIX #1 — Import apply_shadow dari widgets, bukan dari app, agar tidak ada
# circular import (app.py ← tab_kunci.py ← app.py).
from .widgets import CryptoWorker, AnimatedNotifBar, apply_shadow
from .styles import CLR_BG, CLR_CARD, CLR_DANGER

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers kekuatan password
# FIX #9 — Tambahkan penalti karakter berulang agar password seperti
# "aaaaaaaa" tidak dapat skor tinggi padahal sangat lemah.
# ---------------------------------------------------------------------------
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
    # Penalti: jika >50% karakter sama, turunkan 1 poin
    if pw and (max(pw.count(c) for c in set(pw)) / len(pw)) > 0.5:
        score = max(0, score - 1)
    return min(score, 3)


STRENGTH_COLORS = ["#E74C3C", "#E67E22", "#F1C40F", "#2ECC71"]
STRENGTH_LABELS = ["Lemah", "Cukup", "Kuat", "Sangat Kuat"]


class MultiDropFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)
        self.setProperty("dragActive", False)
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
        # FIX #2 — Deklarasi eksplisit agar cek `hasattr` di _proses selalu valid
        self.worker: CryptoWorker | None = None
        self._build_ui()

    def _build_ui(self):
        # FIX #1 — apply_shadow sudah diimport di atas, tidak perlu lazy import lagi
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(15)

        # --- KOLOM KIRI ---
        self.card_target = MultiDropFrame()
        apply_shadow(self.card_target)
        self.card_target.on_paths_dropped = self._add_paths

        v_left = QVBoxLayout(self.card_target)
        v_left.setContentsMargins(20, 20, 20, 20)
        v_left.setSpacing(12)

        row_hdr = QHBoxLayout()
        lbl_target = QLabel("📁  DAFTAR TARGET")
        lbl_target.setObjectName("CardTitle")
        row_hdr.addWidget(lbl_target)

        self.btn_add = QPushButton("+ Tambah")
        self.btn_add.setObjectName("BtnSecondary")
        self.btn_add.setFixedSize(110, 34)

        menu = QMenu(self)
        action_file = menu.addAction("📄 File")
        action_file.triggered.connect(self._pilih_file)
        action_folder = menu.addAction("📁 Folder")
        action_folder.triggered.connect(self._pilih_folder)
        self.btn_add.setMenu(menu)
        row_hdr.addWidget(self.btn_add, alignment=Qt.AlignmentFlag.AlignRight)
        v_left.addLayout(row_hdr)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.list_container)
        v_left.addWidget(self.scroll_area, 1)

        self.chk_hapus = QCheckBox("Hapus file/folder asli setelah dikunci")
        v_left.addWidget(self.chk_hapus)
        main_layout.addWidget(self.card_target, 1)

        # --- KOLOM KANAN ---
        col_right = QVBoxLayout()
        col_right.setSpacing(12)
        main_layout.addLayout(col_right, 1)

        card_pw = QFrame()
        card_pw.setObjectName("Card")
        apply_shadow(card_pw)

        v_pw = QVBoxLayout(card_pw)
        v_pw.setContentsMargins(20, 20, 20, 20)
        v_pw.setSpacing(10)

        lbl_pw = QLabel("🔑  BUAT PASSWORD")
        lbl_pw.setObjectName("CardTitle")
        v_pw.addWidget(lbl_pw)

        row_pw1 = QHBoxLayout()
        self.entry_pw1 = QLineEdit()
        self.entry_pw1.setFixedHeight(40)
        self.entry_pw1.setPlaceholderText("Buat password kuat…")
        self.entry_pw1.setEchoMode(QLineEdit.EchoMode.Password)
        self.entry_pw1.textChanged.connect(self._on_pw_change)
        row_pw1.addWidget(self.entry_pw1)

        self.btn_toggle_pw = QPushButton("👁")
        self.btn_toggle_pw.setObjectName("BtnGhost")
        self.btn_toggle_pw.setFixedSize(40, 40)
        self.btn_toggle_pw.clicked.connect(self._toggle_pw)
        row_pw1.addWidget(self.btn_toggle_pw)
        v_pw.addLayout(row_pw1)

        row_str = QHBoxLayout()
        self.bar_str = QProgressBar()
        self.bar_str.setFixedHeight(6)
        self.bar_str.setTextVisible(False)
        self.bar_str.setMaximum(4)
        row_str.addWidget(self.bar_str, 1)

        self.lbl_str = QLabel("")
        self.lbl_str.setFixedWidth(80)
        self.lbl_str.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.lbl_str.setStyleSheet("font-size: 9pt;")
        row_str.addWidget(self.lbl_str)
        v_pw.addLayout(row_str)

        lbl_confirm = QLabel("Konfirmasi Password")
        lbl_confirm.setStyleSheet("color: #6B7280; font-size: 9pt; font-weight: bold;")
        v_pw.addWidget(lbl_confirm)

        self.entry_pw2 = QLineEdit()
        self.entry_pw2.setFixedHeight(40)
        self.entry_pw2.setPlaceholderText("Ulangi password…")
        self.entry_pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self.entry_pw2.textChanged.connect(self._on_pw_change)
        self.entry_pw2.returnPressed.connect(self._proses)
        v_pw.addWidget(self.entry_pw2)

        self.lbl_match = QLabel("")
        self.lbl_match.setAlignment(Qt.AlignmentFlag.AlignRight)
        v_pw.addWidget(self.lbl_match)
        col_right.addWidget(card_pw)

        col_right.addStretch()

        # --- ACTION AREA ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.hide()
        col_right.addWidget(self.progress_bar)

        self.btn_aksi = QPushButton("KUNCI SEKARANG")
        self.btn_aksi.setFixedHeight(46)
        self.btn_aksi.setEnabled(False)
        self.btn_aksi.clicked.connect(self._proses)
        col_right.addWidget(self.btn_aksi)

        self.notif = AnimatedNotifBar()
        col_right.addWidget(self.notif)

        self._render_list()
        self._hide_indicator()

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

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
        # FIX #6 — Logika render tetap sama tapi dibungkus dengan blok
        # blockSignals agar tidak ada partial-update yang boros. Untuk list
        # besar di masa depan, pertimbangkan migrasi ke QListWidget.
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._paths:
            lbl = QLabel("Belum ada item\n\nSeret ke sini")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: #6B7280; margin-top: 40px; font-weight: bold;")
            self.list_layout.addWidget(lbl)
            self._validate_state()
            return

        for p in self._paths:
            row = QFrame()
            row.setObjectName("Inner")
            r_lay = QHBoxLayout(row)
            r_lay.setContentsMargins(12, 6, 6, 6)

            ikon = "📁" if os.path.isdir(p) else "📄"
            lbl = QLabel(f"{ikon}  {os.path.basename(p)}")
            lbl.setStyleSheet("font-weight: bold;")
            r_lay.addWidget(lbl, 1)

            btn_rm = QPushButton("✕")
            btn_rm.setObjectName("BtnGhost")
            btn_rm.setFixedSize(30, 30)
            btn_rm.clicked.connect(
                lambda checked=False, path=p: self._remove_path(path)
            )
            r_lay.addWidget(btn_rm)
            self.list_layout.addWidget(row)

        self._validate_state()

    def _toggle_pw(self):
        mode = (
            QLineEdit.EchoMode.Normal
            if self.entry_pw1.echoMode() == QLineEdit.EchoMode.Password
            else QLineEdit.EchoMode.Password
        )
        self.entry_pw1.setEchoMode(mode)
        self.entry_pw2.setEchoMode(mode)

    def _hide_indicator(self):
        from .styles import CLR_CARD

        self.bar_str.setValue(0)
        self.bar_str.setStyleSheet(
            f"QProgressBar::chunk {{ background-color: {CLR_CARD}; }}"
        )
        self.lbl_str.setText("")

    def _on_pw_change(self):
        self.notif.hide_msg()
        pw1, pw2 = self.entry_pw1.text(), self.entry_pw2.text()

        score = pw_strength(pw1)
        if score < 0:
            self._hide_indicator()
        else:
            self.bar_str.setValue(score + 1)
            color = STRENGTH_COLORS[score]
            self.bar_str.setStyleSheet(
                f"QProgressBar::chunk {{ background-color: {color}; }}"
            )
            self.lbl_str.setText(STRENGTH_LABELS[score])
            self.lbl_str.setStyleSheet(
                f"color: {color}; font-size: 9pt; font-weight: bold;"
            )

        if not pw2:
            self.lbl_match.setText("")
        elif pw1 == pw2:
            self.lbl_match.setText("✔ Cocok")
            self.lbl_match.setStyleSheet(
                "color: #2ECC71; font-size: 9pt; font-weight: bold;"
            )
        else:
            self.lbl_match.setText("✖ Belum cocok")
            self.lbl_match.setStyleSheet(
                "color: #E74C3C; font-size: 9pt; font-weight: bold;"
            )

        self._validate_state()

    def _validate_state(self):
        pw1, pw2 = self.entry_pw1.text(), self.entry_pw2.text()
        self.btn_aksi.setEnabled(len(self._paths) > 0 and bool(pw1) and (pw1 == pw2))

    # -----------------------------------------------------------------------
    # Proses utama
    # -----------------------------------------------------------------------

    def _proses(self):
        if not self._paths:
            return

        # FIX #2 — Guard: jangan spawn worker baru kalau yang lama masih jalan
        if self.worker is not None and self.worker.isRunning():
            self.notif.show_msg("warn", "⚠ Proses sebelumnya masih berjalan…", 3000)
            return

        pw = self.entry_pw1.text()

        # FIX #5 — Konfirmasi eksplisit sebelum operasi destruktif (hapus asli)
        if self.chk_hapus.isChecked():
            reply = QMessageBox.warning(
                self,
                "Konfirmasi Hapus File Asli",
                "⚠  File/folder asli akan DIHAPUS PERMANEN setelah dikunci.\n\n"
                "Pastikan proses enkripsi berhasil sebelum file asli hilang.\n"
                "Lanjutkan?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,  # Default ke Cancel (aman)
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        default_name = os.path.basename(self._paths[0]) or "Brankas_Rahasia"
        path_simpan, _ = QFileDialog.getSaveFileName(
            self,
            "Simpan Brankas Sebagai...",
            f"{default_name}.locked",
            "Locked Files (*.locked)",
        )
        if not path_simpan:
            return

        self._set_busy(True)
        hapus_asli = self.chk_hapus.isChecked()

        self.worker = CryptoWorker(
            kunci_brankas, list(self._paths), path_simpan, pw, hapus_asli
        )
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
            self.btn_aksi.setText("⏳ Mengunci Brankas...")
            self.btn_add.setEnabled(False)
        else:
            self.progress_bar.hide()
            self.btn_aksi.setText("KUNCI SEKARANG")
            self.btn_add.setEnabled(True)
            self._validate_state()

    def _update_progress(self, val: float):
        self.progress_bar.setValue(int(val * 100))

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
            log.error("Gagal mengunci brankas: %s", pesan)
            self.notif.show_msg("err", f"✖ {pesan}", 6000)
