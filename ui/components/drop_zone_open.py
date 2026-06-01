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
    QGridLayout,
)
from PySide6.QtCore import Qt, Signal

from ..widgets import (
    apply_shadow,
    CustomToolTip,
    ElidedLabel,
    HeroIconWidget,
)
from ..utils import format_file_size
from ..buttons import ClearButton
from core.constants import (
    MAGIC_BYTES,
    VERSION_V1,
    VERSION_V2,
    SALT_SIZE,
    FILE_ID_SIZE,
    V2_FLAG_KDF_PARAMS,
    KDF_ID_ARGON2ID,
    KDF_ID_PBKDF2_SHA256,
)


class DropTargetFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)
        self.on_file_dropped = None
        # Default empty state (consistent with DropZoneLock)
        self.setProperty("empty", True)

    def set_empty_state(self, is_empty: bool):
        """Set empty state via property so global stylesheet applies (same as DropZoneLock)."""
        self.setProperty("empty", is_empty)
        self.style().unpolish(self)
        self.style().polish(self)

    def _set_drag_state(self, state: bool):
        self.setProperty("dragActive", state)
        self.style().unpolish(self)
        self.style().polish(self)

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
        self.btn_browse_center.clicked.connect(self._pilih_file)

        self.lbl_footer_empty = QLabel(
            "Hanya file dengan ekstensi .adtn yang dapat dibuka"
        )
        self.lbl_footer_empty.setObjectName("DropZoneFooter")
        self.lbl_footer_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lay_empty.addStretch(1)
        lay_empty.addWidget(self.icon_empty, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay_empty.addSpacing(16)
        lay_empty.addWidget(self.lbl_main_empty)
        lay_empty.addSpacing(2)
        lay_empty.addWidget(self.lbl_sub_empty)
        lay_empty.addSpacing(20)
        lay_empty.addWidget(
            self.btn_browse_center, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        lay_empty.addSpacing(24)
        lay_empty.addWidget(self.lbl_footer_empty)
        lay_empty.addStretch(1)

        return page_empty

    def _build_filled_state(self) -> QWidget:
        """Filled state matching the reference design.
        Structure:
        - Header + subtitle
        - Main file card (icon + name + "Siap untuk didekripsi" + path + VALID + X + metadata grid)
        - Ganti File button
        - Success info box (shield)
        - INFORMASI ENKRIPSI section (3 items)
        """
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(20, 12, 20, 14)
        lay.setSpacing(0)

        # Header group: title + helper text harus terasa sebagai satu grup visual.
        header_group = QWidget()
        header_lay = QVBoxLayout(header_group)
        header_lay.setContentsMargins(0, 0, 0, 0)
        header_lay.setSpacing(6)

        header = QLabel("File Brankas (.adtn)")
        header.setObjectName("CardTitle")
        header_lay.addWidget(header)

        sub = QLabel("Pilih file brankas yang ingin Anda buka.")
        sub.setObjectName("CardSubtitle")
        header_lay.addWidget(sub)

        lay.addWidget(header_group)
        lay.addSpacing(24)

        # === Main File Info Card ===
        info_card = QFrame()
        info_card.setObjectName("FileInfoCard")
        card_lay = QVBoxLayout(info_card)
        card_lay.setContentsMargins(14, 11, 14, 12)  # Slightly tighter top padding
        card_lay.setSpacing(7)

        # Top row: icon + (filename + ready text + path) + format badge + clear
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.icon_file = QLabel()
        self.icon_file.setPixmap(
            qta.icon("mdi6.file-lock", color="#00D2C8").pixmap(22, 22)
        )
        top_row.addWidget(self.icon_file, 0, Qt.AlignmentFlag.AlignTop)

        name_col = QVBoxLayout()
        name_col.setSpacing(
            1
        )  # Tightened gap between filename and text below (Siap + path)

        # Use ElidedLabel for long filenames (middle elide) — prevents clipping/wrapping issues
        self.lbl_filename = ElidedLabel("...", mode=Qt.TextElideMode.ElideMiddle)
        self.lbl_filename.setStyleSheet(
            "color: white; font-weight: 700; font-size: 10.5pt; background: transparent;"
        )
        name_col.addWidget(self.lbl_filename)

        # "Siap untuk didekripsi" — matches reference exactly
        self.lbl_ready = QLabel("Siap dibuka")
        self.lbl_ready.setObjectName("FileReadySubtitle")
        name_col.addWidget(self.lbl_ready)

        self.lbl_fullpath = ElidedLabel("...", mode=Qt.TextElideMode.ElideMiddle)
        self.lbl_fullpath.setStyleSheet(
            "color: #8B95A5; font-size: 8pt; font-weight: 300; background: transparent;"
        )
        name_col.addWidget(self.lbl_fullpath)

        top_row.addLayout(name_col, 1)

        # Format badge — bukan verifikasi kriptografis penuh.
        self.valid_badge = QLabel("FORMAT OK")
        self.valid_badge.setObjectName("ValidBadge")
        self.valid_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.valid_badge.setFixedHeight(18)
        top_row.addWidget(self.valid_badge, 0, Qt.AlignmentFlag.AlignTop)

        # Clear X
        self.btn_clear = ClearButton()
        self.btn_clear.clicked.connect(self._clear_file)
        top_row.addWidget(self.btn_clear, 0, Qt.AlignmentFlag.AlignTop)

        card_lay.addLayout(top_row)

        card_lay.addSpacing(4)  # Extra breathing between top info and metadata

        # 4-col metadata — tighter but safe to avoid clipping
        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)
        self.meta_items = []
        meta_defs = [
            ("mdi6.file-outline", "Ukuran File", "—"),
            ("mdi6.file-document", "Tipe File", "File Brankas (.adtn)"),
            ("mdi6.calendar", "Tanggal File", "—"),
            ("mdi6.shield-lock", "Enkripsi", "AES-256-GCM"),
        ]
        for icon_name, label_text, initial_value in meta_defs:
            item = self._create_meta_item(icon_name, label_text, initial_value)
            meta_row.addWidget(item, 1)
        card_lay.addLayout(meta_row)

        lay.addWidget(info_card)

        lay.addSpacing(16)

        # Ganti button
        self.btn_ganti = QPushButton("  Ganti File Brankas")
        self.btn_ganti.setIcon(qta.icon("mdi6.file-find", color="#8B95A5"))
        self.btn_ganti.setFixedHeight(36)
        self.btn_ganti.setObjectName("BtnGantiFile")
        self.btn_ganti.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ganti.clicked.connect(self._pilih_file)
        lay.addWidget(self.btn_ganti)

        lay.addSpacing(24)

        # Detail Keamanan section (bordered container)
        enc_section = QFrame()
        enc_section.setObjectName("EncInfoSection")

        enc_lay = QVBoxLayout(enc_section)
        enc_lay.setContentsMargins(14, 12, 14, 12)
        enc_lay.setSpacing(8)

        enc_title = QLabel("Detail Keamanan")
        enc_title.setObjectName("EncSectionTitle")
        enc_lay.addWidget(enc_title)
        enc_lay.addSpacing(4)

        enc_grid = QGridLayout()
        enc_grid.setHorizontalSpacing(16)
        enc_grid.setVerticalSpacing(10)
        self.enc_items = []
        enc_defs = [
            ("mdi6.shield-lock", "Enkripsi", "AES-256-GCM"),
            ("mdi6.key-variant", "KDF", "—"),
            ("mdi6.package-variant-closed", "Format", "—"),
            ("mdi6.fingerprint", "Integritas", "Belum diverifikasi"),
        ]
        for idx, (icon_name, label_text, initial_value) in enumerate(enc_defs):
            item = self._create_encryption_info_item(
                icon_name, label_text, initial_value
            )
            enc_grid.addWidget(item, idx // 2, idx % 2)
        enc_lay.addLayout(enc_grid)

        lay.addWidget(enc_section)

        return page

    def _create_meta_item(
        self, icon_name: str, label_text: str, value_text: str
    ) -> QWidget:
        """Create one metadata column (compact, reference style)."""
        container = QFrame()
        container.setStyleSheet("background: transparent; border: none;")
        v = QVBoxLayout(container)
        v.setContentsMargins(3, 1, 3, 1)
        v.setSpacing(1)

        ic = QLabel()
        ic.setPixmap(qta.icon(icon_name, color="#00D2C8").pixmap(13, 13))
        v.addWidget(ic, 0, Qt.AlignmentFlag.AlignLeft)

        lbl = QLabel(label_text)
        lbl.setObjectName("MetaLabel")
        v.addWidget(lbl)

        val = QLabel(value_text)
        val.setObjectName("MetaValue")
        val.setWordWrap(True)
        v.addWidget(val)

        container._meta_icon = ic
        container._meta_label = lbl
        container._meta_value = val
        self.meta_items.append(container)
        return container

    def _create_encryption_info_item(
        self, icon_name: str, label_text: str, value_text: str
    ) -> QWidget:
        """Horizontal item for Detail Keamanan section."""
        container = QFrame()
        container.setStyleSheet("background: transparent; border: none;")

        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(9)

        # Icon on the left side (32px as requested, vertically centered)
        ic = QLabel()
        ic.setPixmap(qta.icon(icon_name, color="#00D2C8").pixmap(26, 26))
        ic.setFixedSize(26, 26)
        h.addWidget(ic, 0, Qt.AlignmentFlag.AlignVCenter)

        # Text column on the right
        v = QVBoxLayout()
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)

        lbl = QLabel(label_text)
        lbl.setStyleSheet("color: #8B95A5; font-size: 8pt; font-weight: 400;")
        v.addWidget(lbl)

        val = QLabel(value_text)
        val.setStyleSheet("color: #E8ECF3; font-size: 9pt; font-weight: 600;")
        v.addWidget(val)

        h.addLayout(v, 1)

        # Store for dynamic update
        container._enc_val = val
        self.enc_items.append(container)
        return container

    def _update_filled_info(self, path: str):
        """Populate the rich metadata card with real file information."""
        if not path or not os.path.exists(path):
            return

        try:
            stat = os.stat(path)
            size_str = format_file_size(stat.st_size)

            # Indonesian month names
            months = {
                1: "Jan",
                2: "Feb",
                3: "Mar",
                4: "Apr",
                5: "Mei",
                6: "Jun",
                7: "Jul",
                8: "Agt",
                9: "Sep",
                10: "Okt",
                11: "Nov",
                12: "Des",
            }
            import datetime as dt

            mtime = dt.datetime.fromtimestamp(stat.st_mtime)
            date_str = f"{mtime.day} {months[mtime.month]} {mtime.year}, {mtime.strftime('%H:%M')}"

            filename = os.path.basename(path)
            fullpath = path
        except Exception:
            size_str = "—"
            date_str = "—"
            filename = os.path.basename(path) if path else "..."
            fullpath = path or "..."

        vault_info = self._read_vault_display_info(path)

        # Update widgets
        self.lbl_filename.setText(filename)
        self.lbl_fullpath.setText(fullpath)
        self.valid_badge.setText(vault_info["badge"])

        # 4 metadata columns
        if len(self.meta_items) >= 4:
            self.meta_items[0]._meta_value.setText(size_str)
            self.meta_items[1]._meta_value.setText("File Brankas (.adtn)")
            self.meta_items[2]._meta_value.setText(date_str)
            self.meta_items[3]._meta_value.setText(vault_info["encryption"])

        # Detail keamanan: Enkripsi, KDF, Format, Integritas.
        if len(self.enc_items) >= 4:
            self.enc_items[0]._enc_val.setText(vault_info["encryption"])
            self.enc_items[1]._enc_val.setText(vault_info["kdf"])
            self.enc_items[2]._enc_val.setText(vault_info["format"])
            self.enc_items[3]._enc_val.setText("Belum diverifikasi")

    def _read_vault_display_info(self, path: str) -> dict[str, str]:
        """Baca metadata header ringan untuk display UI.

        Ini bukan verifikasi integritas kriptografis. Status tetap "Belum
        diverifikasi" sampai proses buka brankas selesai dengan sukses.
        """
        info = {
            "badge": "FORMAT OK",
            "encryption": "AES-256-GCM",
            "kdf": "—",
            "format": "—",
        }

        try:
            with open(path, "rb") as f:
                if f.read(4) != MAGIC_BYTES:
                    info.update({"badge": "FORMAT ?", "format": "Tidak dikenali"})
                    return info

                version = f.read(1)
                if version == VERSION_V1:
                    info.update({"kdf": "PBKDF2", "format": "Vault v1 / Legacy"})
                    return info

                if version != VERSION_V2:
                    info.update({"badge": "FORMAT ?", "format": "Versi tidak didukung"})
                    return info

                # v2: salt + file_id + chunk_size + flags
                f.read(SALT_SIZE + FILE_ID_SIZE)
                f.read(4)
                flags_raw = f.read(4)
                if len(flags_raw) != 4:
                    info.update({"badge": "FORMAT ?", "format": "Header tidak lengkap"})
                    return info

                flags = int.from_bytes(flags_raw, byteorder="big")
                kdf = "PBKDF2 Legacy"
                if flags & V2_FLAG_KDF_PARAMS:
                    section = f.read(3)
                    if len(section) != 3:
                        info.update(
                            {"badge": "FORMAT ?", "format": "Header tidak lengkap"}
                        )
                        return info
                    kdf_id = section[0]
                    params_len = int.from_bytes(section[1:3], byteorder="big")
                    f.read(params_len)
                    if kdf_id == KDF_ID_ARGON2ID:
                        kdf = "Argon2id"
                    elif kdf_id == KDF_ID_PBKDF2_SHA256:
                        kdf = "PBKDF2"
                    else:
                        kdf = "Tidak didukung"

                info.update({"kdf": kdf, "format": "Vault v2"})
                return info
        except Exception:
            info.update({"badge": "FORMAT ?", "format": "Tidak terbaca"})
            return info

    def _update_card_style(self, is_empty: bool):
        # Use property-based styling for empty state (same system as DropZoneLock)
        # so global QSS in styles.py applies consistently.
        if is_empty:
            if hasattr(self.card_file, "set_empty_state"):
                self.card_file.set_empty_state(True)
            # For filled state we still override with inline (different visual treatment)
        else:
            self.card_file.setStyleSheet("""
                QFrame#DropArea { border: 1px solid #232B3E; background-color: #111625; border-radius: 12px; }
                QFrame#DropArea[dragActive="true"] { border: 2px dashed #00D2C8; background-color: #181F32; }
            """)

    def _setup_accessibility(self):
        self.btn_browse_center.installEventFilter(self)

        if hasattr(self, "lbl_fullpath"):
            self.lbl_fullpath.installEventFilter(self)
        if hasattr(self, "lbl_ready"):
            self.lbl_ready.installEventFilter(self)

        self.btn_ganti.installEventFilter(self)
        if hasattr(self, "btn_clear"):
            self.btn_clear.installEventFilter(self)

        self.btn_browse_center.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_ganti.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if hasattr(self, "btn_clear"):
            self.btn_clear.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def eventFilter(self, obj, event):
        # Tooltip for full path on hover (filled state)
        if event.type() == event.Type.Enter:
            target = getattr(self, "lbl_fullpath", None)
            if obj == target and self._path_file:
                self._custom_tooltip.request_show(self._path_file)
                return True
        elif event.type() == event.Type.Leave:
            target = getattr(self, "lbl_fullpath", None)
            if obj == target:
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
        self.stack_file.setCurrentIndex(1)
        self._update_card_style(False)
        self._update_filled_info(path)

        self.btn_ganti.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_clear.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.file_changed.emit(path)

    def _clear_file(self):
        self._path_file = ""
        self._custom_tooltip.hide_tooltip()
        self.stack_file.setCurrentIndex(0)
        self._update_card_style(True)

        self.btn_ganti.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if hasattr(self, "btn_clear"):
            self.btn_clear.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.file_changed.emit("")

    def _pilih_file(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Pilih File Brankas", "", "Adyton Crypt Files (*.adtn)"
        )
        if f:
            self._set_file(f)

    # --- PUBLIC API ---
    def load_file(self, path: str) -> None:
        self._set_file(path)

    def choose_file(self) -> None:
        self._pilih_file()

    def get_file(self) -> str:
        return self._path_file

    def reset_zone(self):
        self._clear_file()

    def set_busy(self, busy: bool):
        # Empty state controls
        if hasattr(self, "btn_browse_center"):
            self.btn_browse_center.setEnabled(not busy)

        # Filled state controls (may not exist yet if never loaded a file)
        if hasattr(self, "btn_ganti"):
            self.btn_ganti.setEnabled(not busy)
        if hasattr(self, "btn_clear"):
            self.btn_clear.setEnabled(not busy)
