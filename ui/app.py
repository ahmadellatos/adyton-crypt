"""
ui/app.py
Jendela utama PySide6 dengan efek bayangan (Drop Shadow).
"""

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTabWidget,
)
from PySide6.QtCore import Qt

from .tab_kunci import TabKunci
from .tab_buka import TabBuka
from .styles import load_stylesheet

# FIX #1 — apply_shadow tidak lagi didefinisikan di sini untuk menghindari
# circular import. Fungsi sudah dipindah ke widgets.py.
# Re-export agar kode lama yang import dari app.py tetap kompatibel.
from .widgets import apply_shadow  # noqa: F401


class AppBrankas(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Digital Locker — Professional")
        self.setFixedSize(880, 520)

        self.setStyleSheet(load_stylesheet())
        self._init_ui()

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(25, 20, 25, 20)
        main_layout.setSpacing(15)

        self._build_header(main_layout)

        self.tabs = QTabWidget()
        self.tabs.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.tab_kunci = TabKunci()
        self.tab_buka = TabBuka()

        self.tabs.addTab(self.tab_kunci, " 🔒 Kunci Folder ")
        self.tabs.addTab(self.tab_buka, " 🔓 Buka Brankas ")

        main_layout.addWidget(self.tabs)

    def _build_header(self, parent_layout):
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)

        lbl_title = QLabel("🔐  Digital Locker")
        lbl_title.setObjectName("AppTitle")

        lbl_subtitle = QLabel("AES-256 · GCM")
        lbl_subtitle.setObjectName("AppSubtitle")

        header_layout.addWidget(lbl_title)
        header_layout.addStretch()
        header_layout.addWidget(lbl_subtitle, alignment=Qt.AlignmentFlag.AlignBottom)

        parent_layout.addWidget(header_widget)
