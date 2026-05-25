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
    QScrollArea,
    QStackedWidget,
    QDialog,
)
from PySide6.QtCore import Qt, Signal

from ..widgets import (
    apply_shadow,
    CustomToolTip,
    ElidedLabel,
    HeroIconWidget,
    CenteredMenuAction,
    AccessibleCenteredMenu,
    ClearButton,
    TambahClearSplitButton,
    ModernMessageBox,
)


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

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
            event.accept()
        else:
            super().keyPressEvent(event)


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


class DropZoneLock(QWidget):
    # Sinyal untuk parent (TabKunci)
    paths_changed = Signal(list)
    warning_emitted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paths = []
        self._custom_tooltip = CustomToolTip(self)
        self._build_ui()
        self._setup_accessibility()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Buat Menu Dropdown internal
        self.menu = AccessibleCenteredMenu(self)
        action_file = CenteredMenuAction("File", "mdi6.file-document", parent=self.menu)
        action_file.triggered.connect(self._pilih_file)
        self.menu.addAction(action_file)

        action_folder = CenteredMenuAction("Folder", "mdi6.folder", parent=self.menu)
        action_folder.triggered.connect(self._pilih_folder)
        self.menu.addAction(action_folder)

        self.card_target = MultiDropFrame()
        self.card_target.on_paths_dropped = self._add_paths
        apply_shadow(self.card_target, blur_radius=30, opacity=40)

        lay_target = QVBoxLayout(self.card_target)
        lay_target.setContentsMargins(2, 2, 2, 2)

        self.stack_target = QStackedWidget()
        lay_target.addWidget(self.stack_target)

        self._build_empty_state()
        self._build_list_state()

        self._update_card_style(True)
        main_layout.addWidget(self.card_target)

    def _build_empty_state(self):
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

        self.lbl_sub_empty = QLabel(
            "atau klik tombol di bawah untuk memilih secara manual"
        )
        self.lbl_sub_empty.setStyleSheet("font-size: 10pt; color: #8B95A5;")
        self.lbl_sub_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_empty_browse = QPushButton(" Pilih Target")
        self.btn_empty_browse.setIcon(qta.icon("mdi6.folder-plus", color="white"))
        self.btn_empty_browse.setObjectName("BtnBrowseLg")
        self.btn_empty_browse.setFixedSize(220, 42)
        self.btn_empty_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_empty_browse.setMenu(self.menu)

        self.lbl_footer_empty = QLabel(
            "Mendukung semua format file dan folder tak terbatas"
        )
        self.lbl_footer_empty.setStyleSheet("font-size: 9pt; color: #8B95A5;")
        self.lbl_footer_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

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

    def _build_list_state(self):
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
        v_hdr_text.addWidget(lbl_target)
        v_hdr_text.addWidget(lbl_target_sub)

        self.btn_split_add = TambahClearSplitButton(self.menu, self._clear_all_paths)
        self.btn_add = self.btn_split_add.btn_add

        row_hdr.addWidget(icon_folder)
        row_hdr.addLayout(v_hdr_text)
        row_hdr.addStretch()
        row_hdr.addWidget(self.btn_split_add, alignment=Qt.AlignmentFlag.AlignTop)

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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "icon_empty"):
            return

        win = self.window()
        win_h = win.height() if win else self.height()
        compact = win_h <= 690 or self.card_target.height() < 300

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
                QFrame#DropArea { border: 2px dashed #232B3E; background-color: #0B101E; border-radius: 12px; }
                QFrame#DropArea[dragActive="true"] { border: 2px dashed #00D2C8; background-color: #181F32; }
            """)
        else:
            self.card_target.setStyleSheet("""
                QFrame#DropArea { border: 1px solid #232B3E; background-color: #111625; border-radius: 12px; }
                QFrame#DropArea[dragActive="true"] { border: 2px dashed #00D2C8; background-color: #181F32; }
            """)

    def _setup_accessibility(self):
        self.btn_empty_browse.installEventFilter(self)
        self.btn_split_add.btn_add.installEventFilter(self)
        self.btn_split_add.btn_clear.installEventFilter(self)

        self.btn_empty_browse.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_split_add.btn_add.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_split_add.btn_clear.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def eventFilter(self, obj, event):
        if event.type() == event.Type.Enter and isinstance(obj, ClearButton):
            self._custom_tooltip.hide_tooltip()
            return False
        elif event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                if isinstance(obj, QPushButton):
                    if obj in (self.btn_empty_browse, self.btn_add):
                        if obj.menu():
                            obj.showMenu()
                        return True
                    elif isinstance(obj, ClearButton):
                        obj.click()
                        return True
        return super().eventFilter(obj, event)

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
            if p.lower().endswith(".adtn"):
                self.warning_emitted.emit(
                    f"⚠ '{os.path.basename(p)}' sudah jadi file brankas!"
                )
                continue
            if p not in self._paths:
                self._paths.append(p)
        self._render_list()

    def _remove_path(self, path):
        if path in self._paths:
            self._paths.remove(path)
            self._render_list()

    def _clear_all_paths(self):
        if not self._paths:
            return
        if len(self._paths) > 1:
            dialog = ModernMessageBox(
                title="Bersihkan Daftar Target",
                message=f"Apakah Anda yakin ingin menghapus semua {len(self._paths)} target dari daftar?",
                icon_name="mdi6.trash-can-outline",
                icon_color="#E74C3C",
                parent=self,
            )
            dialog.btn_yes.setText("Bersihkan")
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
        self._paths.clear()
        self._render_list()

    def _render_list(self):
        self._custom_tooltip.hide_tooltip()
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._paths:
            self.btn_split_add.set_clear_visible(False)
            self.stack_target.setCurrentIndex(0)
            self._update_card_style(True)
            self.paths_changed.emit(self._paths)
            return

        self.stack_target.setCurrentIndex(1)
        self._update_card_style(False)
        self.btn_split_add.set_clear_visible(True)

        for p in self._paths:
            row = FileListRow(p, self._custom_tooltip)
            r_lay = QHBoxLayout(row)
            r_lay.setContentsMargins(15, 0, 15, 0)

            ikon = QLabel()
            ikon_name = "mdi6.file-document" if os.path.isfile(p) else "mdi6.folder"
            ikon.setPixmap(qta.icon(ikon_name, color="#8B95A5").pixmap(24, 24))

            v_file = QVBoxLayout()
            v_file.setSpacing(2)
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

            btn_rm = ClearButton()
            btn_rm.clicked.connect(
                lambda checked=False, path=p: self._remove_path(path)
            )
            btn_rm.installEventFilter(self)

            r_lay.addWidget(ikon)
            r_lay.addSpacing(10)
            r_lay.addLayout(v_file, 1)
            r_lay.addWidget(lbl_sz)
            r_lay.addSpacing(10)
            r_lay.addWidget(btn_rm)
            self.list_layout.addWidget(row)

        self.list_layout.addStretch()
        self.paths_changed.emit(self._paths)

    # --- PUBLIC API ---
    def get_paths(self) -> list:
        return self._paths

    def clear_paths(self):
        self._paths.clear()
        self._render_list()

    def set_busy(self, busy: bool):
        self.btn_empty_browse.setEnabled(not busy)
        self.btn_split_add.setEnabled(not busy)
        self.inner_frame.setEnabled(not busy)
