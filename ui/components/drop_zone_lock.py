import os

import qtawesome as qta
from PySide6.QtCore import (
    QAbstractListModel,
    QEvent,
    QModelIndex,
    QRect,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from ..buttons import ClearButton, TambahClearSplitButton
from ..dialogs import ModernMessageBox
from ..menus import AccessibleCenteredMenu, CenteredMenuAction
from ..utils import format_file_size
from ..widgets import (
    CustomToolTip,
    HeroIconWidget,
)


class MultiDropFrame(QFrame):
    drag_state_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)
        self.on_paths_dropped = None
        # Default state
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
        self.drag_state_changed.emit(state)

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
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        valid_paths = [p for p in paths if os.path.exists(p)]
        if valid_paths and self.on_paths_dropped:
            self.on_paths_dropped(valid_paths)


class TargetListModel(QAbstractListModel):
    """Model untuk daftar path target (file/folder). Mendukung role kaya untuk delegate."""

    # Custom roles untuk delegate & a11y
    SizeRole = Qt.UserRole + 1
    TypeRole = Qt.UserRole + 2

    def __init__(self, paths=None, parent=None):
        super().__init__(parent)
        self._paths = list(paths) if paths else []

    def rowCount(self, parent=QModelIndex()):  # noqa: B008
        return len(self._paths)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        path = self._paths[row]

        if role == Qt.DisplayRole:
            return os.path.basename(path) or path
        elif role == Qt.UserRole or role == Qt.ToolTipRole:
            return path
        elif role == TargetListModel.SizeRole:
            try:
                if os.path.isfile(path):
                    return os.path.getsize(path)
                return -1  # folder marker
            except Exception:
                return -1
        elif role == TargetListModel.TypeRole:
            try:
                return "folder" if os.path.isdir(path) else "file"
            except Exception:
                return "file"
        elif role in (Qt.AccessibleTextRole, Qt.AccessibleDescriptionRole):
            basename = os.path.basename(path) or path
            typ = "Folder" if self.data(index, TargetListModel.TypeRole) == "folder" else "File"
            size_bytes = self.data(index, TargetListModel.SizeRole)
            if size_bytes >= 0:
                hsize = format_file_size(size_bytes)
                return f"{typ} {basename}, {hsize}. Path: {path}"
            else:
                return f"{typ} {basename}. Path: {path}"

        return None

    def setPaths(self, paths):
        """Ganti seluruh daftar path."""
        self.beginResetModel()
        self._paths = list(paths)
        self.endResetModel()

    def addPaths(self, new_paths):
        """Tambah beberapa path baru."""
        if not new_paths:
            return

        start = len(self._paths)
        self.beginInsertRows(QModelIndex(), start, start + len(new_paths) - 1)
        self._paths.extend(new_paths)
        self.endInsertRows()

    def removePath(self, path):
        """Hapus satu path tertentu."""
        if path not in self._paths:
            return

        row = self._paths.index(path)
        self.beginRemoveRows(QModelIndex(), row, row)
        self._paths.pop(row)
        self.endRemoveRows()

    def clear(self):
        """Hapus semua path."""
        self.beginResetModel()
        self._paths.clear()
        self.endResetModel()

    def getPaths(self):
        return list(self._paths)

    # No drag & drop reordering (removed as per request)


class TargetListDelegate(QStyledItemDelegate):
    """Custom delegate untuk rendering item daftar target yang kaya:
    icon (file/folder), nama, path (elided), ukuran manusiawi, dan tombol hapus per-item.
    Mendukung hover state untuk tombol hapus dan background highlight.
    """

    remove_requested = Signal(str)  # emit full path saat delete diklik

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hovered_row = -1
        self._icon_cache = {}
        self._cached_base_font = None

        # Initialize with safe defaults so paint() never crashes
        default_font = QFont()
        self.name_font = QFont(default_font)
        self.name_font.setWeight(QFont.Weight.DemiBold)
        self.name_font.setPointSize(9.5)
        self.fm_name = QFontMetrics(self.name_font)

        self.path_font = QFont(default_font)
        self.path_font.setWeight(QFont.Weight.Light)
        self.path_font.setPointSize(8)
        self.fm_path = QFontMetrics(self.path_font)

        self.size_font = QFont(default_font)
        self.size_font.setWeight(QFont.Weight.Normal)
        self.size_font.setPointSize(8)
        self.fm_size = QFontMetrics(self.size_font)

    def _get_icon(self, path: str, size: int = 26):
        key = (path, size)
        if key in self._icon_cache:
            return self._icon_cache[key]
        exists = os.path.exists(path)
        is_dir = os.path.isdir(path) if exists else False
        if is_dir:
            icon = qta.icon("mdi6.folder", color="#F1C40F")
        else:
            icon = qta.icon("mdi6.file-document-outline", color="#00D2C8")
        pix = icon.pixmap(size, size)
        self._icon_cache[key] = pix
        return pix

    def _get_delete_pixmap(self, is_hovered: bool, size: int = 18):
        # Use the same icon as ClearButton ("mdi6.close")
        color = "#FFFFFF" if is_hovered else "#8B95A5"
        return qta.icon("mdi6.close", color=color).pixmap(size, size)

    def _update_font_cache(self, base_font: QFont):
        """Cache font objects to avoid expensive recreation on every paint() call."""
        if self._cached_base_font == base_font:
            return
        self._cached_base_font = QFont(base_font)

        self.name_font = QFont(base_font)
        self.name_font.setWeight(QFont.Weight.DemiBold)
        self.name_font.setPointSize(9.5)
        self.fm_name = QFontMetrics(self.name_font)

        self.path_font = QFont(base_font)
        self.path_font.setWeight(QFont.Weight.Light)
        self.path_font.setPointSize(8)
        self.fm_path = QFontMetrics(self.path_font)

        self.size_font = QFont(base_font)
        self.size_font.setWeight(QFont.Weight.Normal)
        self.size_font.setPointSize(8)
        self.fm_size = QFontMetrics(self.size_font)

    def paint(self, painter: QPainter, option, index):
        painter.save()
        self._update_font_cache(painter.font())

        # Make text crisp (fixes "pecah" / blurry text)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        rect = option.rect
        path = index.data(Qt.UserRole) or ""
        name = index.data(Qt.DisplayRole) or "?"
        size_bytes = index.data(TargetListModel.SizeRole)
        if size_bytes is None:
            size_bytes = -1

        is_selected = bool(option.state & QStyle.State_Selected)
        is_hovered = index.row() == self._hovered_row

        # Background highlight
        if is_selected:
            painter.fillRect(rect, QColor("#1E2A40"))
            accent = QRect(rect.left(), rect.top() + 2, 3, rect.height() - 4)
            painter.fillRect(accent, QColor("#00D2C8"))
        elif is_hovered:
            painter.fillRect(rect, QColor("#182033"))
        else:
            painter.setPen(QPen(QColor("#232B3E"), 1))
            painter.drawLine(
                rect.left() + 14,
                rect.bottom() - 1,
                rect.right() - 14,
                rect.bottom() - 1,
            )

        # Keyboard focus indicator
        is_focused_item = bool(option.state & QStyle.State_HasFocus)
        if is_focused_item and (is_selected or is_hovered):
            painter.setPen(QPen(QColor("#00D2C8"), 1, Qt.PenStyle.DashLine))
            focus_rect = rect.adjusted(1, 1, -1, -1)
            painter.drawRect(focus_rect)

        pad_x = 14
        pad_y = 8
        content = rect.adjusted(pad_x, pad_y, -pad_x, -pad_y)

        # Icon
        icon_size = 24
        icon_pix = self._get_icon(path, icon_size)
        icon_y = content.top() + (content.height() - icon_size) // 2
        painter.drawPixmap(content.left(), icon_y, icon_pix)

        text_x = content.left() + icon_size + 10

        # === Layout constants for right side (delete + size) ===
        del_size = 20
        del_x = content.right() - del_size - 2
        del_y = content.top() + (content.height() - del_size) // 2
        show_delete = is_hovered

        # Draw delete button first (hover only) — no font dependency
        if show_delete:
            # Red rounded background on hover (matching ClearButton style from Buka tab)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#E74C3C"))
            painter.drawRoundedRect(del_x, del_y, del_size, del_size, 4, 4)

            # White close icon
            del_pix = self._get_delete_pixmap(True, del_size - 4)
            icon_x = del_x + (del_size - (del_size - 4)) // 2
            icon_y = del_y + (del_size - (del_size - 4)) // 2
            painter.drawPixmap(icon_x, icon_y, del_pix)

        # Use cached fonts (performance optimization)
        size_str = format_file_size(size_bytes if size_bytes is not None else -1)

        size_w = self.fm_size.horizontalAdvance(size_str)

        # Right reservation: always leave room for size + comfortable gap.
        # When hovering, also reserve space for the delete button.
        right_reserve = 8
        if show_delete:
            right_reserve += del_size + 8

        # Size right-aligned within reserved area
        size_right = content.right() - right_reserve
        size_x = size_right - size_w

        # Path stops before gap + size (use path font metrics for correct eliding)
        path_to_size_gap = 12
        max_path_w = max(50, (size_x - path_to_size_gap) - text_x)

        # Name reservation
        name_right_reserve = 6 if show_delete else 2
        max_name_w = max(
            80,
            (content.right() - name_right_reserve - (del_size + 6 if show_delete else 0)) - text_x,
        )

        # === NAME (SemiBold 9.5pt) ===
        painter.setFont(self.name_font)
        elided_name = self.fm_name.elidedText(name, Qt.TextElideMode.ElideMiddle, max_name_w)
        painter.setPen(QColor("#FFFFFF"))
        name_y = content.top() + 13
        painter.drawText(text_x, name_y, elided_name)

        # === PATH (Light 8pt) + SIZE (Regular 8pt) ===
        painter.setFont(self.path_font)
        dirname = os.path.dirname(path) or ""
        path_elided = self.fm_path.elidedText(dirname, Qt.TextElideMode.ElideMiddle, max_path_w)
        painter.setPen(QColor("#8B95A5"))
        painter.drawText(text_x, name_y + 15, path_elided)

        painter.setFont(self.size_font)
        painter.setPen(QColor("#6B7688"))
        painter.drawText(size_x, name_y + 15, size_str)

        painter.restore()

    def sizeHint(self, option, index):
        # Fixed height for consistent rich rows (using richer typography now)
        w = option.rect.width() if option.rect.width() > 80 else 420
        return QSize(w, 58)

    def editorEvent(self, event, model, option, index):
        """Tangani klik pada tombol hapus (hanya muncul saat hover)."""
        if (
            event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
        ):
            rect = option.rect
            pad_x = 14
            pad_y = 8
            content = rect.adjusted(pad_x, pad_y, -pad_x, -pad_y)

            del_size = 20
            del_x = content.right() - del_size - 2
            del_y = content.top() + (content.height() - del_size) // 2
            del_rect = QRect(del_x, del_y, del_size, del_size)

            if del_rect.contains(event.pos()):
                path = index.data(Qt.UserRole)
                if path:
                    self.remove_requested.emit(str(path))
                    return True

        return super().editorEvent(event, model, option, index)


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
        # Shadow sekarang dihandle oleh wrapper di TabKunci (LeftColumn)

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

        # Connect drag signal (decoupled - no parent(). access)
        if hasattr(self, "card_target"):
            self.card_target.drag_state_changed.connect(self.icon_empty.set_drag_active)

        self.lbl_main_empty = QLabel("Drag & drop file atau folder ke sini")
        self.lbl_main_empty.setObjectName("DropZoneMainText")
        self.lbl_main_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_sub_empty = QLabel("atau klik tombol di bawah untuk memilih secara manual")
        self.lbl_sub_empty.setObjectName("DropZoneSubText")
        self.lbl_sub_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_empty_browse = QPushButton(" Pilih Target")
        self.btn_empty_browse.setIcon(qta.icon("mdi6.folder-plus", color="white"))
        self.btn_empty_browse.setObjectName("BtnBrowseLg")
        self.btn_empty_browse.setFixedSize(220, 42)
        self.btn_empty_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_empty_browse.setMenu(self.menu)

        self.lbl_footer_empty = QLabel("Mendukung semua format file dan folder tak terbatas")
        self.lbl_footer_empty.setObjectName("DropZoneFooter")
        self.lbl_footer_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lay_empty.addStretch(1)
        lay_empty.addWidget(self.icon_empty, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay_empty.addSpacing(16)
        lay_empty.addWidget(self.lbl_main_empty)
        lay_empty.addSpacing(2)
        lay_empty.addWidget(self.lbl_sub_empty)
        lay_empty.addSpacing(20)
        lay_empty.addWidget(self.btn_empty_browse, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay_empty.addSpacing(24)
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
        icon_folder.setPixmap(qta.icon("mdi6.folder-open", color="#F1C40F").pixmap(32, 32))

        v_hdr_text = QVBoxLayout()
        v_hdr_text.setSpacing(3)
        lbl_target = QLabel("DAFTAR TARGET")
        lbl_target.setObjectName("TargetHeaderTitle")  # bigger specific title for daftar target
        lbl_target_sub = QLabel("Pilih file atau folder yang akan dikunci")
        lbl_target_sub.setObjectName("CardSubtitle")
        v_hdr_text.addWidget(lbl_target)
        v_hdr_text.addWidget(lbl_target_sub)

        self.btn_split_add = TambahClearSplitButton(self.menu, self._clear_all_paths)
        self.btn_add = self.btn_split_add.btn_add
        self.btn_add.setAccessibleName("Tambah Target")
        self.btn_split_add.btn_clear.setAccessibleName("Bersihkan Semua Target")

        row_hdr.addWidget(icon_folder)
        row_hdr.addLayout(v_hdr_text)
        row_hdr.addStretch()
        row_hdr.addWidget(self.btn_split_add, alignment=Qt.AlignmentFlag.AlignTop)

        lay_list.addLayout(row_hdr)

        self.inner_frame = QFrame()
        self.inner_frame.setObjectName("Inner")
        inner_lay = QVBoxLayout(self.inner_frame)
        inner_lay.setContentsMargins(0, 5, 0, 5)

        # === TAHAP 1+2: QListView + Model + Delegate kaya (icon, path, size, delete per item) ===
        self.list_view = QListView()
        # PERBAIKAN: Selalu gunakan selector class (QListView) saat mencampur
        # property utama dengan child selector (QScrollBar). Ini mencegah Qt
        # membuang seluruh stylesheet dan menghasilkan error parse berulang.
        self.list_view.setStyleSheet("""
            QListView {
                background: transparent;
                border: none;
                outline: none;
            }

            QScrollBar:vertical {
                width: 6px;
                background: #1A2235;
            }
            QScrollBar::handle:vertical {
                background: #3A4558;
                border-radius: 3px;
                min-height: 20px;
            }
        """)
        self.list_view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.list_view.setMouseTracking(True)
        self.list_view.setUniformItemSizes(True)
        self.list_view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.list_view.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self.list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)

        # Drag & drop reordering disabled (not needed for encryption use case)
        self.list_view.setDragEnabled(False)
        self.list_view.setAcceptDrops(False)
        self.list_view.setDropIndicatorShown(False)

        self.list_view.setAccessibleName("Daftar Target")
        self.list_view.setAccessibleDescription(
            "Daftar file dan folder yang akan dikunci. Gunakan tombol hapus atau tombol Delete pada keyboard."
        )

        self.target_model = TargetListModel()
        self.list_view.setModel(self.target_model)

        self.target_delegate = TargetListDelegate(self.list_view)
        self.list_view.setItemDelegate(self.target_delegate)
        self.target_delegate.remove_requested.connect(self._remove_path)

        # Hover tracking + sync model changes (drag reorder etc.) back to _paths
        self.list_view.viewport().installEventFilter(self)
        self._connect_model_sync()

        inner_lay.addWidget(self.list_view)
        lay_list.addWidget(self.inner_frame, 1)
        self.stack_target.addWidget(page_list)

    def _update_card_style(self, is_empty: bool):
        """Update visual state via properties (styled globally in styles.py)."""
        if hasattr(self, "card_target") and hasattr(self.card_target, "set_empty_state"):
            self.card_target.set_empty_state(is_empty)

    def _setup_accessibility(self):
        self.btn_empty_browse.installEventFilter(self)
        self.btn_split_add.btn_add.installEventFilter(self)
        self.btn_split_add.btn_clear.installEventFilter(self)

        self.btn_empty_browse.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_split_add.btn_add.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_split_add.btn_clear.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def eventFilter(self, obj, event):
        # Existing: tooltip hide on ClearButton enter
        if event.type() == QEvent.Type.Enter and isinstance(obj, ClearButton):
            self._custom_tooltip.hide_tooltip()
            return False

        # Keyboard: Enter/Space for buttons + Delete key support di list view
        if event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                if isinstance(obj, QPushButton):
                    if obj in (self.btn_empty_browse, self.btn_add):
                        if obj.menu():
                            obj.showMenu()
                        return True
                    elif isinstance(obj, ClearButton):
                        obj.click()
                        return True
            # Delete key: hapus item terpilih di daftar target (nice-to-have a11y)
            if event.key() == Qt.Key.Key_Delete:
                if obj in (
                    self.list_view,
                    getattr(self, "list_view", None) and self.list_view.viewport(),
                ):
                    idx = self.list_view.currentIndex()
                    if idx.isValid():
                        path = idx.data(Qt.UserRole)
                        if path:
                            self._remove_path(path)
                            return True

        # Hover tracking untuk delegate (highlight + tombol hapus lebih terang)
        if hasattr(self, "list_view") and obj == self.list_view.viewport():
            if event.type() == QEvent.Type.MouseMove:
                idx = self.list_view.indexAt(event.pos())
                new_row = idx.row() if idx.isValid() else -1
                if new_row != getattr(self.target_delegate, "_hovered_row", -1):
                    self.target_delegate._hovered_row = new_row
                    self.list_view.viewport().update()
                return False
            elif event.type() == QEvent.Type.Leave:
                if getattr(self.target_delegate, "_hovered_row", -1) != -1:
                    self.target_delegate._hovered_row = -1
                    self.list_view.viewport().update()
                return False

        return super().eventFilter(obj, event)

    def _connect_model_sync(self):
        """Hubungkan sinyal model agar _paths dan UI tetap sinkron (penting untuk drag reorder)."""
        if not hasattr(self, "target_model"):
            return
        m = self.target_model
        m.rowsMoved.connect(self._sync_paths_from_model)
        m.rowsInserted.connect(self._sync_paths_from_model)
        m.rowsRemoved.connect(self._sync_paths_from_model)
        m.modelReset.connect(self._sync_paths_from_model)

    def _sync_paths_from_model(self, *args):
        """Sinkronkan self._paths dari model (setelah drag, remove via delegate, dll) lalu pancarkan sinyal."""
        if not hasattr(self, "target_model"):
            return
        self._paths = self.target_model.getPaths()
        self.paths_changed.emit(self._paths)
        # Reset hover state setelah perubahan struktural
        if hasattr(self, "target_delegate"):
            self.target_delegate._hovered_row = -1
            if hasattr(self, "list_view") and self.list_view.viewport():
                self.list_view.viewport().update()

    def _pilih_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Pilih Folder")
        if folder:
            self._add_paths([folder])

    def _pilih_file(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Pilih File")
        if files:
            self._add_paths(files)

    def _add_paths(self, new_paths):
        added = []
        for p in new_paths:
            if p.lower().endswith(".adtn"):
                self.warning_emitted.emit(f"⚠ '{os.path.basename(p)}' sudah jadi file brankas!")
                continue
            if p not in self._paths:
                self._paths.append(p)
                added.append(p)

        if added:
            self.target_model.addPaths(added)
            self.stack_target.setCurrentIndex(1)
            self._update_card_style(False)
            self.btn_split_add.set_clear_visible(True)
            self.paths_changed.emit(self._paths)

    def _remove_path(self, path):
        if path in self._paths:
            self._paths.remove(path)
            self.target_model.removePath(path)

            if not self._paths:
                self.stack_target.setCurrentIndex(0)
                self._update_card_style(True)
                self.btn_split_add.set_clear_visible(False)
            self.paths_changed.emit(self._paths)

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
        self.target_model.clear()
        self.stack_target.setCurrentIndex(0)
        self._update_card_style(True)
        self.btn_split_add.set_clear_visible(False)
        self.paths_changed.emit(self._paths)

    # --- PUBLIC API ---
    def get_paths(self) -> list:
        return self._paths

    def clear_paths(self):
        self._paths.clear()
        self.target_model.clear()
        self.stack_target.setCurrentIndex(0)
        self._update_card_style(True)
        self.btn_split_add.set_clear_visible(False)
        self.paths_changed.emit(self._paths)

    def set_busy(self, busy: bool):
        self.btn_empty_browse.setEnabled(not busy)
        self.btn_split_add.setEnabled(not busy)
        self.inner_frame.setEnabled(not busy)
