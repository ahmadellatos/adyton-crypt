"""
Modul: vault_browser_dialog.py
Deskripsi: Dialog "Browse contents" — menampilkan isi vault (hasil
           core.vault.list_vault_contents) sebagai pohon dengan checkbox, lalu
           mengembalikan subset terpilih untuk ekstrak selektif.

Dialog ini murni presentasi/pemilihan: ia TIDAK mendekripsi maupun mengekstrak.
Listing dilakukan controller (Tab Buka) di worker thread; ekstraksi juga dijalankan
controller setelah user menekan "Extract Selected" dan memilih folder tujuan.
"""

from __future__ import annotations

import qtawesome as qta
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from .i18n import register, tr
from .styles import (
    CLR_ACCENT,
    CLR_BORDER,
    CLR_CARD,
    CLR_HOVER_BG,
    CLR_INPUT_BORDER,
    CLR_INSET,
    CLR_LIST_SELECTED,
    CLR_TEXT_MAIN,
    CLR_TEXT_MUTED,
)
from .utils import format_file_size
from .widgets import ScrimDialogMixin, apply_shadow

# Peran data kustom pada kolom 0 tiap item pohon.
_ROLE_PATH = Qt.ItemDataRole.UserRole  # rel_path (str, pemisah "/")
_ROLE_ISDIR = Qt.ItemDataRole.UserRole + 1  # bool
_ROLE_SIZE = Qt.ItemDataRole.UserRole + 2  # int (byte; 0 untuk dir)


class VaultBrowserDialog(ScrimDialogMixin, QDialog):
    """Tampilkan isi vault sebagai pohon checkable; kembalikan subset terpilih.

    Pakai lewat ``exec()`` (modal). Bila mengembalikan ``QDialog.Accepted`` user
    menekan "Extract Selected" — baca ``selected_paths()`` + ``selected_bytes()``.
    """

    def __init__(self, root_name: str, entries, parent=None):
        super().__init__(parent)
        self.parent_widget = parent
        self._file_items: list[QTreeWidgetItem] = []

        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        container = QFrame(self)
        container.setObjectName("Card")
        container.setFixedWidth(640)
        apply_shadow(container, blur_radius=30, y_offset=8, opacity=60)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(15, 15, 15, 15)
        outer.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel()
        register(title, "browser.title", "Vault contents")
        title.setObjectName("CardTitle")
        layout.addWidget(title)

        total_files = sum(1 for e in entries if not e.is_dir)
        total_bytes = sum(e.size for e in entries if not e.is_dir)
        self.lbl_subtitle = QLabel(
            tr(
                "browser.subtitle",
                "'{root}' • {count} files • {size}",
            ).format(root=root_name, count=total_files, size=format_file_size(total_bytes))
        )
        self.lbl_subtitle.setObjectName("MutedText")
        self.lbl_subtitle.setWordWrap(True)
        layout.addWidget(self.lbl_subtitle)

        # Baris aksi seleksi: Select all / Select none + ringkasan terpilih.
        sel_row = QHBoxLayout()
        sel_row.setSpacing(8)
        self.btn_all = QPushButton()
        register(self.btn_all, "browser.select_all", "Select all")
        self.btn_none = QPushButton()
        register(self.btn_none, "browser.select_none", "Select none")
        for b in (self.btn_all, self.btn_none):
            b.setObjectName("BtnGen")
            b.setFixedHeight(32)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_all.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        self.btn_none.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        sel_row.addWidget(self.btn_all)
        sel_row.addWidget(self.btn_none)
        sel_row.addStretch(1)
        self.lbl_summary = QLabel("")
        self.lbl_summary.setObjectName("MutedText")
        sel_row.addWidget(self.lbl_summary)
        layout.addLayout(sel_row)

        self.tree = QTreeWidget()
        self.tree.setObjectName("BrowserTree")
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels([tr("browser.col.name", "Name"), tr("browser.col.size", "Size")])
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(False)
        self.tree.setMinimumHeight(340)
        self.tree.setMaximumHeight(440)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setStyleSheet(self._tree_qss())
        layout.addWidget(self.tree)

        if entries:
            self._build_tree(entries)
        else:
            empty = QLabel()
            register(empty, "browser.empty", "This vault is empty.")
            empty.setObjectName("MutedText")
            layout.addWidget(empty)

        self.tree.itemChanged.connect(self._on_item_changed)

        # Footer.
        btn_lay = QHBoxLayout()
        btn_lay.setSpacing(10)
        btn_lay.addStretch(1)
        self.btn_cancel = QPushButton()
        register(self.btn_cancel, "common.cancel", "Cancel")
        self.btn_cancel.setObjectName("BtnDialogCancel")
        self.btn_cancel.setFixedHeight(42)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_extract = QPushButton()
        register(self.btn_extract, "browser.extract", "Extract Selected")
        self.btn_extract.setObjectName("BtnAlertConfirm")
        self.btn_extract.setFixedHeight(42)
        self.btn_extract.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_extract.setEnabled(False)
        self.btn_extract.clicked.connect(self.accept)
        btn_lay.addWidget(self.btn_cancel)
        btn_lay.addWidget(self.btn_extract)
        layout.addLayout(btn_lay)

        self._refresh_summary()

    # ── Konstruksi pohon ──────────────────────────────────────────────────────

    def _build_tree(self, entries) -> None:
        self.tree.blockSignals(True)
        nodes: dict[str, QTreeWidgetItem] = {}
        folder_icon = qta.icon("mdi6.folder-outline", color=CLR_ACCENT)
        file_icon = qta.icon("mdi6.file-outline", color=CLR_TEXT_MUTED)

        # Urutkan agar induk dibuat sebelum anak (path lebih pendek dulu).
        for entry in sorted(entries, key=lambda e: e.rel_path):
            parts = entry.rel_path.split("/")
            cur_path = ""
            parent_item: QTreeWidgetItem | None = None
            for part in parts:
                cur_path = part if not cur_path else f"{cur_path}/{part}"
                item = nodes.get(cur_path)
                if item is None:
                    item = QTreeWidgetItem([part, ""])
                    item.setData(0, _ROLE_PATH, cur_path)
                    item.setData(0, _ROLE_ISDIR, True)  # asumsi dir; leaf-file dikoreksi
                    item.setData(0, _ROLE_SIZE, 0)
                    item.setFlags(
                        (item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        & ~Qt.ItemFlag.ItemIsAutoTristate
                    )
                    item.setCheckState(0, Qt.CheckState.Unchecked)
                    item.setIcon(0, folder_icon)
                    nodes[cur_path] = item
                    if parent_item is None:
                        self.tree.addTopLevelItem(item)
                    else:
                        parent_item.addChild(item)
                parent_item = item

            leaf = nodes[entry.rel_path]
            leaf.setData(0, _ROLE_ISDIR, entry.is_dir)
            if not entry.is_dir:
                leaf.setData(0, _ROLE_SIZE, entry.size)
                leaf.setText(1, format_file_size(entry.size))
                leaf.setTextAlignment(
                    1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                leaf.setIcon(0, file_icon)
                self._file_items.append(leaf)
            else:
                leaf.setIcon(0, folder_icon)

        self.tree.expandToDepth(0)
        self.tree.blockSignals(False)

    # ── Propagasi checkbox (tri-state manual) ─────────────────────────────────

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        self.tree.blockSignals(True)
        state = item.checkState(0)
        if state != Qt.CheckState.PartiallyChecked:
            self._apply_to_children(item, state)
        self._recompute_parents(item)
        self.tree.blockSignals(False)
        self._refresh_summary()

    def _apply_to_children(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            self._apply_to_children(child, state)

    def _recompute_parents(self, item: QTreeWidgetItem) -> None:
        parent = item.parent()
        while parent is not None:
            states = {parent.child(i).checkState(0) for i in range(parent.childCount())}
            if states == {Qt.CheckState.Checked}:
                new_state = Qt.CheckState.Checked
            elif states == {Qt.CheckState.Unchecked}:
                new_state = Qt.CheckState.Unchecked
            else:
                new_state = Qt.CheckState.PartiallyChecked
            parent.setCheckState(0, new_state)
            parent = parent.parent()

    def _set_all(self, state: Qt.CheckState) -> None:
        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            top.setCheckState(0, state)
            self._apply_to_children(top, state)
        self.tree.blockSignals(False)
        self._refresh_summary()

    # ── Ringkasan + hasil ─────────────────────────────────────────────────────

    def _refresh_summary(self) -> None:
        count = self.selected_count()
        size = self.selected_bytes()
        self.lbl_summary.setText(
            tr("browser.selected_summary", "{count} selected • {size}").format(
                count=count, size=format_file_size(size)
            )
        )
        self.btn_extract.setEnabled(count > 0)

    def selected_count(self) -> int:
        return sum(1 for it in self._file_items if it.checkState(0) == Qt.CheckState.Checked)

    def selected_bytes(self) -> int:
        return sum(
            int(it.data(0, _ROLE_SIZE) or 0)
            for it in self._file_items
            if it.checkState(0) == Qt.CheckState.Checked
        )

    def selected_paths(self) -> list[str]:
        """rel_path terpilih (node ter-check paling atas; dir ter-check tak diurai).

        Dir yang seluruhnya ter-check dikembalikan sebagai satu path (anak-anaknya
        tersirat); node partial diurai agar hanya anak ter-check yang ikut. Konsumen
        core (`extract_selected`) mencocokkan persis maupun berdasarkan prefix dir.
        """
        out: list[str] = []

        def walk(item: QTreeWidgetItem) -> None:
            st = item.checkState(0)
            if st == Qt.CheckState.Checked:
                out.append(str(item.data(0, _ROLE_PATH)))
                return
            if st == Qt.CheckState.PartiallyChecked:
                for i in range(item.childCount()):
                    walk(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        return out

    def _tree_qss(self) -> str:
        return f"""
        QTreeWidget#BrowserTree {{
            background-color: {CLR_INSET};
            border: 1px solid {CLR_BORDER};
            border-radius: 12px;
            outline: none;
            padding: 4px;
        }}
        QTreeWidget#BrowserTree::item {{
            padding: 5px 2px;
            color: {CLR_TEXT_MAIN};
        }}
        QTreeWidget#BrowserTree::item:hover {{ background-color: {CLR_HOVER_BG}; }}
        QTreeWidget#BrowserTree::item:selected {{
            background-color: {CLR_LIST_SELECTED};
            color: {CLR_TEXT_MAIN};
        }}
        QTreeWidget#BrowserTree::indicator {{
            width: 16px; height: 16px;
            border: 1.5px solid {CLR_INPUT_BORDER};
            border-radius: 4px;
            background-color: {CLR_CARD};
        }}
        QTreeWidget#BrowserTree::indicator:checked {{
            background-color: {CLR_ACCENT};
            border-color: {CLR_ACCENT};
        }}
        QTreeWidget#BrowserTree::indicator:indeterminate {{
            background-color: {CLR_LIST_SELECTED};
            border-color: {CLR_ACCENT};
        }}
        QHeaderView::section {{
            background-color: {CLR_CARD};
            color: {CLR_TEXT_MUTED};
            border: none;
            padding: 6px 8px;
        }}
        """

    # ── Lifecycle (scrim + center, pola dialog lain) ──────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        self._show_modal_scrim()
        QTimer.singleShot(0, self._center_dialog)

    def hideEvent(self, event):
        self._hide_modal_scrim()
        super().hideEvent(event)

    def _center_dialog(self):
        self.adjustSize()
        if self.parent_widget:
            top_level = self.parent_widget.window()
            if top_level and top_level.isVisible():
                parent_center = top_level.mapToGlobal(top_level.rect().center())
                self.move(parent_center - self.rect().center())
                return
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - self.rect().center())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)
