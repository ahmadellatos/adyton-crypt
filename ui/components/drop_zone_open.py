import os
import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QFrame,
    QStackedWidget,
)
from PySide6.QtCore import Qt, Signal

from ..widgets import (
    apply_shadow,
    CustomToolTip,
    ElidedLabel,
    HeroIconWidget,
)
from ..buttons import ClearButton
from ..styles import CLR_TEXT_MUTED


class DropTargetFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)
        self.on_file_dropped = None
        self.setProperty("empty", True)

    def set_empty_state(self, is_empty: bool):
        """Set empty state via property (global stylesheet will handle visual)."""
        self.setProperty("empty", is_empty)
        self.style().unpolish(self)
        self.style().polish(self)

    def _set_drag_state(self, state: bool):
        self.setProperty("dragActive", state)
        self.style().unpolish(self)
        self.style().polish(self)

        # Intensify icon glow when dragging (look for icon on parent DropZoneOpen)
        parent = self.parent()
        if parent and hasattr(parent, "icon_empty") and parent.icon_empty:
            parent.icon_empty.set_drag_active(state)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".adtn"):
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
            if path.lower().endswith(".adtn"):
                if self.on_file_dropped:
                    self.on_file_dropped(path)
                break


class DropZoneOpen(QWidget):
    # Sinyal terpancar saat file dipilih atau dihapus
    file_changed = Signal(str)  # str kosong "" jika dihapus

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path_file = ""
        self._custom_tooltip = CustomToolTip(self)
        self._build_ui()
        self._setup_accessibility()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

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
        main_layout.addWidget(self.card_file)

    def _build_empty_state(self) -> QWidget:
        page_empty = QWidget()
        lay_empty = QVBoxLayout(page_empty)
        lay_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay_empty.setSpacing(0)

        self.icon_empty = HeroIconWidget(mode="buka")
        self.icon_empty.setMaximumHeight(85)

        self.lbl_main_empty = QLabel("Drag & drop file .adtn ke sini")
        self.lbl_main_empty.setObjectName("DropZoneMainText")
        self.lbl_main_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_sub_empty = QLabel("atau klik tombol di bawah untuk memilih file")
        self.lbl_sub_empty.setObjectName("DropZoneSubText")
        self.lbl_sub_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_browse_center = QPushButton(" Pilih File Brankas")
        self.btn_browse_center.setIcon(qta.icon("mdi6.folder-search", color="white"))
        self.btn_browse_center.setFixedSize(220, 42)
        self.btn_browse_center.setObjectName("BtnBrowseLg")
        self.btn_browse_center.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse_center.setAccessibleName("Pilih File Brankas untuk Dibuka")
        self.btn_browse_center.clicked.connect(self._pilih_file)

        self.lbl_footer_empty = QLabel(
            "Hanya file dengan ekstensi .adtn yang dapat dibuka"
        )
        self.lbl_footer_empty.setObjectName("DropZoneFooter")
        self.lbl_footer_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lay_empty.addStretch(2)
        lay_empty.addWidget(self.icon_empty, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay_empty.addSpacing(18)
        lay_empty.addWidget(self.lbl_main_empty)
        lay_empty.addSpacing(3)
        lay_empty.addWidget(self.lbl_sub_empty)
        lay_empty.addSpacing(22)
        lay_empty.addWidget(
            self.btn_browse_center, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        lay_empty.addSpacing(28)
        lay_empty.addWidget(self.lbl_footer_empty)
        lay_empty.addStretch(2)

        return page_empty

    def _build_filled_state(self) -> QWidget:
        page_filled = QWidget()
        lay_filled = QVBoxLayout(page_filled)
        lay_filled.setContentsMargins(23, 23, 23, 23)
        lay_filled.setSpacing(15)

        lbl_title_file = QLabel("FILE BRANKAS (.adtn)")
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
            "color: {CLR_TEXT_MUTED}; font-size: 9pt; border: none; background: transparent;"
        )
        v_fname.addWidget(self.lbl_path_filled)
        v_fname.addWidget(lbl_path_desc)

        self.btn_clear = ClearButton()
        self.btn_clear.setAccessibleName("Hapus File dari Daftar")
        self.btn_clear.clicked.connect(self._clear_file)

        lay_fbox.addWidget(icon_locked)
        lay_fbox.addSpacing(10)
        lay_fbox.addLayout(v_fname, 1)
        lay_fbox.addWidget(self.btn_clear)
        lay_filled.addWidget(file_box)

        self.btn_ganti = QPushButton(" Ganti File Brankas")
        self.btn_ganti.setIcon(qta.icon("mdi6.file-find", color="white"))
        self.btn_ganti.setFixedHeight(40)
        self.btn_ganti.setAccessibleName("Ganti File Brankas")
        self.btn_ganti.clicked.connect(self._pilih_file)
        lay_filled.addWidget(self.btn_ganti)

        lay_filled.addStretch()
        return page_filled

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "icon_empty"):
            return

        win = self.window()
        win_h = win.height() if win else self.height()
        compact = win_h <= 690 or self.card_file.height() < 300

        if compact:
            self.icon_empty.setMaximumHeight(52)
            self.lbl_main_empty.setObjectName("DropZoneMainText")  # QSS will handle size
            self.lbl_sub_empty.setObjectName("DropZoneSubText")
            self.btn_browse_center.setFixedSize(180, 34)
            self.lbl_footer_empty.hide()
        else:
            self.icon_empty.setMaximumHeight(85)
            self.lbl_main_empty.setObjectName("DropZoneMainText")
            self.lbl_sub_empty.setObjectName("DropZoneSubText")
            self.btn_browse_center.setFixedSize(220, 42)
            self.lbl_footer_empty.show()

    def _update_card_style(self, is_empty: bool):
        """Update visual state via properties (styled globally in styles.py)."""
        if hasattr(self, "card_file") and hasattr(self.card_file, "set_empty_state"):
            self.card_file.set_empty_state(is_empty)

    def _setup_accessibility(self):
        self.btn_browse_center.installEventFilter(self)
        self.lbl_path_filled.installEventFilter(self)
        self.btn_ganti.installEventFilter(self)
        self.btn_clear.installEventFilter(self)

        self.btn_browse_center.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_ganti.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_clear.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def eventFilter(self, obj, event):
        if event.type() == event.Type.Enter:
            if obj == self.lbl_path_filled and self._path_file:
                self._custom_tooltip.request_show(self._path_file)
                return True
        elif event.type() == event.Type.Leave:
            if obj == self.lbl_path_filled:
                self._custom_tooltip.hide_tooltip()
                return True
        elif event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                if obj == self.btn_browse_center:
                    obj.click()
                    return True
        return super().eventFilter(obj, event)

    def _set_file(self, path: str):
        self._path_file = path
        self.lbl_path_filled.setText(os.path.basename(path))
        self.stack_file.setCurrentIndex(1)
        self._update_card_style(False)
        self.btn_ganti.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_clear.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.file_changed.emit(path)

    def _clear_file(self):
        self._path_file = ""
        self._custom_tooltip.hide_tooltip()
        self.stack_file.setCurrentIndex(0)
        self._update_card_style(True)
        self.btn_ganti.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_clear.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.file_changed.emit("")

    def _pilih_file(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Pilih File Brankas", "", "Adyton Crypt Files (*.adtn)"
        )
        if f:
            self._set_file(f)

    # --- PUBLIC API ---
    def get_file(self) -> str:
        return self._path_file

    def reset_zone(self):
        self._clear_file()

    def set_busy(self, busy: bool):
        self.btn_browse_center.setEnabled(not busy)
        self.btn_ganti.setEnabled(not busy)
        self.btn_clear.setEnabled(not busy)
