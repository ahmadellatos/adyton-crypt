import os

import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.constants import (
    ARGON2ID_PARAMS_SIZE,
    CHUNK_RECORD_OVERHEAD,
    CHUNK_SIZE,
    CORE_HEADER_SIZE,
    FILE_ID_SIZE,
    FLAG_HINT,
    MAGIC_BYTES,
    MAX_HINT_LENGTH,
    MAX_KEYSLOTS,
    SALT_SIZE,
    SUPPORTED_FLAGS,
    VERSION,
    WRAP_NONCE_SIZE,
    WRAPPED_KEY_SIZE,
)

from ..buttons import ClearButton
from ..i18n import register, tr
from ..styles import (
    CLR_ACCENT,
    CLR_BORDER,
    CLR_CARD,
    CLR_INSET,
    CLR_TEXT_DIM,
    CLR_TEXT_MAIN,
)
from ..utils import format_file_size
from ..widgets import (
    CustomToolTip,
    DragDropFrame,
    ElidedLabel,
    HeroIconWidget,
    apply_shadow,
)


class DropZoneOpen(QWidget):
    # Sinyal terpancar saat file dipilih atau dihapus
    file_changed = Signal(str)  # str kosong "" jika dihapus

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path_file = ""
        self._file_format_openable = False
        self._format_status_text = "—"
        self._format_badge_state = "idle"
        self._custom_tooltip = CustomToolTip(self)
        self._build_ui()
        self._setup_accessibility()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.card_file = DragDropFrame(multi=False, accept=lambda p: p.lower().endswith(".adtn"))
        apply_shadow(self.card_file, blur_radius=30, opacity=40)
        self.card_file.on_drop = lambda paths: self._set_file(paths[0])

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

        self.lbl_main_empty = QLabel()
        register(self.lbl_main_empty, "dz.empty.main", "Drag & drop a .adtn file here")
        self.lbl_main_empty.setObjectName("DropZoneMainText")
        self.lbl_main_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_sub_empty = QLabel()
        register(self.lbl_sub_empty, "dz.empty.sub", "or click the button below to choose a file")
        self.lbl_sub_empty.setObjectName("DropZoneSubText")
        self.lbl_sub_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_browse_center = QPushButton()
        register(self.btn_browse_center, "dz.empty.browse", " Choose Vault File")
        self.btn_browse_center.setIcon(qta.icon("mdi6.folder-open-outline", color="white"))
        self.btn_browse_center.setFixedSize(220, 42)
        self.btn_browse_center.setObjectName("BtnBrowseLg")
        self.btn_browse_center.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse_center.clicked.connect(self._pilih_file)

        self.lbl_footer_empty = QLabel()
        register(
            self.lbl_footer_empty, "dz.empty.footer", "Only .adtn vault files can be opened here"
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
        lay_empty.addWidget(self.btn_browse_center, alignment=Qt.AlignmentFlag.AlignHCenter)
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

        header = QLabel()
        register(header, "dz.filled.title", "Vault File (.adtn)")
        header.setObjectName("CardTitle")
        header_lay.addWidget(header)

        sub = QLabel()
        register(sub, "dz.filled.sub", "Select the vault file to open.")
        sub.setObjectName("CardSubtitle")
        header_lay.addWidget(sub)

        lay.addWidget(header_group)
        lay.addSpacing(24)

        # === Main File Info Card ===
        # Dibuat mengikuti reference: top area lapang + divider + metadata 4 kolom.
        info_card = QFrame()
        info_card.setObjectName("FileInfoCard")
        info_card.setMinimumHeight(126)

        card_lay = QVBoxLayout(info_card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(0)

        # Top row: icon besar + filename/status/path + VALID badge + clear.
        top_row = QHBoxLayout()
        top_row.setContentsMargins(14, 14, 12, 12)
        top_row.setSpacing(12)

        self.icon_file = QLabel()
        self.icon_file.setObjectName("SelectedFileIcon")
        self.icon_file.setPixmap(
            qta.icon("mdi6.file-document-outline", color=CLR_ACCENT).pixmap(38, 38)
        )
        self.icon_file.setFixedSize(44, 44)
        self.icon_file.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_row.addWidget(self.icon_file, 0, Qt.AlignmentFlag.AlignTop)

        name_col = QVBoxLayout()
        name_col.setContentsMargins(0, 0, 0, 0)
        name_col.setSpacing(3)

        self.lbl_filename = ElidedLabel("...", mode=Qt.TextElideMode.ElideMiddle)
        self.lbl_filename.setObjectName("SelectedFileName")
        name_col.addWidget(self.lbl_filename)

        self.lbl_ready = QLabel(tr("dz.ready", "Ready to open"))
        self.lbl_ready.setObjectName("FileReadySubtitle")
        name_col.addWidget(self.lbl_ready)

        self.lbl_fullpath = ElidedLabel("...", mode=Qt.TextElideMode.ElideMiddle)
        self.lbl_fullpath.setObjectName("SelectedFilePath")
        name_col.addWidget(self.lbl_fullpath)

        top_row.addLayout(name_col, 1)

        self.valid_badge = QLabel("FORMAT  ✓")
        self.valid_badge.setObjectName("ValidBadge")
        self.valid_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Tinggi tetap; lebar mengikuti teks (+padding QSS) agar teks panjang
        # seperti "UNSUPPORTED" tidak terpotong. Tanpa minimum eksplisit, layout
        # tak bisa menyusutkannya di bawah lebar teksnya.
        self.valid_badge.setFixedHeight(23)
        top_row.addWidget(self.valid_badge, 0, Qt.AlignmentFlag.AlignTop)

        self.btn_clear = ClearButton()
        self.btn_clear.clicked.connect(self._clear_file)
        top_row.addWidget(self.btn_clear, 0, Qt.AlignmentFlag.AlignTop)

        card_lay.addLayout(top_row)

        divider = QFrame()
        divider.setObjectName("FileCardDivider")
        divider.setFixedHeight(1)
        card_lay.addWidget(divider)

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(14, 9, 14, 10)
        meta_row.setSpacing(0)
        self.meta_items = []
        meta_defs = [
            ("dz.meta.size", "File Size", "—"),
            ("dz.meta.created", "Created", "—"),
            ("dz.meta.enc", "Encryption", "AES-256-GCM"),
            ("dz.meta.status", "Status", tr("dz.meta.waiting", "Waiting for password")),
        ]
        for idx, (label_key, label_default, initial_value) in enumerate(meta_defs):
            item = self._create_meta_item(tr(label_key, label_default), initial_value)
            register(item._meta_label, label_key, label_default)
            meta_row.addWidget(item, 1)
            if idx < len(meta_defs) - 1:
                sep = QFrame()
                sep.setObjectName("MetaSeparator")
                sep.setFixedWidth(1)
                meta_row.addWidget(sep)
        card_lay.addLayout(meta_row)

        lay.addWidget(info_card)

        lay.addSpacing(16)

        # Ganti button
        self.btn_ganti = QPushButton()
        register(self.btn_ganti, "dz.change", "  Change Vault File")
        self.btn_ganti.setIcon(qta.icon("mdi6.file-find-outline", color=CLR_TEXT_DIM))
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

        enc_title = QLabel()
        register(enc_title, "dz.sec.title", "Security Details")
        enc_title.setObjectName("EncSectionTitle")
        enc_lay.addWidget(enc_title)
        enc_lay.addSpacing(4)

        enc_grid = QGridLayout()
        enc_grid.setHorizontalSpacing(16)
        enc_grid.setVerticalSpacing(10)
        self.enc_items = []
        enc_defs = [
            ("mdi6.shield-outline", "dz.sec.enc", "Encryption", "AES-256-GCM"),
            ("mdi6.key-outline", "dz.sec.kdf", "KDF", "—"),
            ("mdi6.package-variant-closed", "dz.sec.format", "Format", "—"),
            (
                "mdi6.fingerprint",
                "dz.sec.integrity",
                "Integrity",
                tr("dz.sec.notverified", "Not yet verified"),
            ),
        ]
        for idx, (icon_name, label_key, label_default, initial_value) in enumerate(enc_defs):
            item = self._create_encryption_info_item(
                icon_name, tr(label_key, label_default), initial_value
            )
            register(item._enc_label, label_key, label_default)
            enc_grid.addWidget(item, idx // 2, idx % 2)
        enc_lay.addLayout(enc_grid)

        lay.addWidget(enc_section)
        # Serap sisa ruang vertikal di bawah agar header & section tidak melar
        # (tanpa ini, label judul/subjudul ikut memuai mengisi kolom yang tinggi).
        lay.addStretch(1)

        return page

    def _create_meta_item(self, label_text: str, value_text: str) -> QWidget:
        """Create one metadata column like the reference card."""
        container = QFrame()
        container.setObjectName("MetaItem")
        v = QVBoxLayout(container)
        v.setContentsMargins(10, 0, 10, 0)
        v.setSpacing(3)

        lbl = QLabel(label_text)
        lbl.setObjectName("MetaLabel")
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        v.addWidget(lbl)

        val = QLabel(value_text)
        val.setObjectName("MetaValue")
        val.setAlignment(Qt.AlignmentFlag.AlignLeft)
        val.setWordWrap(False)
        val.setMinimumHeight(16)
        v.addWidget(val)

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
        ic.setPixmap(qta.icon(icon_name, color=CLR_ACCENT).pixmap(26, 26))
        ic.setFixedSize(26, 26)
        h.addWidget(ic, 0, Qt.AlignmentFlag.AlignVCenter)

        # Text column on the right
        v = QVBoxLayout()
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)

        lbl = QLabel(label_text)
        lbl.setStyleSheet(f"color: {CLR_TEXT_DIM}; font-size: 8pt; font-weight: 600;")
        v.addWidget(lbl)

        val = QLabel(value_text)
        val.setStyleSheet(f"color: {CLR_TEXT_MAIN}; font-size: 9pt; font-weight: 700;")
        v.addWidget(val)

        h.addLayout(v, 1)

        # Store for dynamic update + i18n retranslate
        container._enc_label = lbl
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

            # Short month abbreviations for the "Created" field
            months = {
                1: "Jan",
                2: "Feb",
                3: "Mar",
                4: "Apr",
                5: "May",
                6: "Jun",
                7: "Jul",
                8: "Aug",
                9: "Sep",
                10: "Oct",
                11: "Nov",
                12: "Dec",
            }
            import datetime as dt

            mtime = dt.datetime.fromtimestamp(stat.st_mtime)
            date_str = f"{mtime.day} {months[mtime.month]} {mtime.year}"

            filename = os.path.basename(path)
            fullpath = path
        except Exception:
            size_str = "—"
            date_str = "—"
            filename = os.path.basename(path) if path else "..."
            fullpath = path or "..."

        vault_info = self._read_vault_display_info(path)
        self._file_format_openable = bool(vault_info["openable"])
        self._format_status_text = str(vault_info["status"])
        self._format_badge_state = str(vault_info["badge_state"])

        # Update widgets
        self.lbl_filename.setText(filename)
        self.lbl_fullpath.setText(fullpath)
        self.lbl_ready.setText(str(vault_info["subtitle"]))
        self._set_badge(str(vault_info["badge"]), str(vault_info["badge_state"]))

        # 4 metadata columns
        if len(self.meta_items) >= 4:
            self.meta_items[0]._meta_value.setText(size_str)
            self.meta_items[1]._meta_value.setText(date_str)
            self.meta_items[2]._meta_value.setText(str(vault_info["encryption"]))
            self.meta_items[3]._meta_value.setText(str(vault_info["status"]))

        # Detail keamanan: Enkripsi, KDF, Format, Integritas.
        if len(self.enc_items) >= 4:
            self.enc_items[0]._enc_val.setText(vault_info["encryption"])
            self.enc_items[1]._enc_val.setText(vault_info["kdf"])
            self.enc_items[2]._enc_val.setText(vault_info["format"])
            self.enc_items[3]._enc_val.setText(tr("dz.sec.notverified", "Not yet verified"))

    def _read_vault_display_info(self, path: str) -> dict[str, object]:
        """Baca metadata header ringan untuk display UI.

        Ini hanya validasi struktur/format vault, bukan verifikasi integritas
        kriptografis. Integritas baru dianggap valid setelah proses dekripsi
        sukses, karena tag AES-GCM membutuhkan password/key yang benar.
        """
        info = {
            "badge": "FORMAT  ✓",
            "badge_state": "ok",
            "encryption": "AES-256-GCM",
            "kdf": "—",
            "format": "—",
            "status": tr("dz.status.valid", "Valid format"),
            "subtitle": tr("dz.meta.waiting", "Waiting for password"),
            "openable": True,
        }

        def mark_problem(
            badge: str,
            status: str,
            fmt: str,
            *,
            state: str = "error",
            subtitle: str = "File can't be opened yet",
            openable: bool = False,
            kdf: str | None = None,
        ) -> dict[str, object]:
            info.update(
                {
                    "badge": badge,
                    "badge_state": state,
                    "status": status,
                    "format": fmt,
                    "subtitle": subtitle,
                    "openable": openable,
                }
            )
            if kdf is not None:
                info["kdf"] = kdf
            return info

        try:
            if not path.lower().endswith(".adtn"):
                return mark_problem(
                    "ERROR",
                    "Invalid extension",
                    "Not a .adtn file",
                )

            file_size = os.path.getsize(path)
            if file_size <= 0:
                return mark_problem("ERROR", "Empty file", "Incomplete")

            with open(path, "rb") as f:
                if f.read(4) != MAGIC_BYTES:
                    return mark_problem(
                        "ERROR",
                        "Not an Adyton vault",
                        "Unrecognized",
                    )

                version = f.read(1)
                if version != VERSION:
                    return mark_problem(
                        "UNSUPPORTED",
                        "Unsupported version",
                        "Newer/unknown version",
                        state="warn",
                        subtitle="Needs a newer app version",
                    )

                return self._inspect_header(f, file_size, info, mark_problem)
        except Exception:
            return mark_problem("ERROR", "Unreadable", "Unreadable")

    def _inspect_header(self, f, file_size, info, mark_problem):
        """Validasi struktur header (envelope) untuk display — bukan verifikasi
        kriptografis. Integritas baru dipastikan saat dekripsi dengan key benar."""
        min_slot = 1 + 1 + 2 + ARGON2ID_PARAMS_SIZE + SALT_SIZE + WRAP_NONCE_SIZE + WRAPPED_KEY_SIZE
        min_size = CORE_HEADER_SIZE + 1 + min_slot + (2 * CHUNK_RECORD_OVERHEAD)
        if file_size < min_size:
            return mark_problem("ERROR", "Incomplete file", "Adyton Vault", kdf="Argon2id")

        f.read(FILE_ID_SIZE)
        chunk_size_raw = f.read(4)
        if len(chunk_size_raw) != 4:
            return mark_problem("ERROR", "Incomplete header", "Adyton Vault")
        chunk_size = int.from_bytes(chunk_size_raw, byteorder="big")
        if chunk_size <= 0 or chunk_size > CHUNK_SIZE:
            return mark_problem("ERROR", "Invalid chunk parameter", "Adyton Vault")

        flags_raw = f.read(4)
        if len(flags_raw) != 4:
            return mark_problem("ERROR", "Incomplete header", "Adyton Vault")
        flags = int.from_bytes(flags_raw, byteorder="big")
        if flags & ~SUPPORTED_FLAGS:
            return mark_problem(
                "UNSUPPORTED",
                "Unsupported flag",
                "Adyton Vault",
                state="warn",
                subtitle="Needs a newer app version",
            )

        if flags & FLAG_HINT:
            hint_len_raw = f.read(2)
            if len(hint_len_raw) != 2:
                return mark_problem("ERROR", "Incomplete header", "Adyton Vault")
            hint_len = int.from_bytes(hint_len_raw, byteorder="big")
            if hint_len > MAX_HINT_LENGTH or len(f.read(hint_len)) != hint_len:
                return mark_problem("ERROR", "Invalid header", "Adyton Vault")

        slot_count_raw = f.read(1)
        if len(slot_count_raw) != 1 or not 1 <= slot_count_raw[0] <= MAX_KEYSLOTS:
            return mark_problem("ERROR", "Invalid keyslot count", "Adyton Vault")

        info.update(
            {
                "kdf": "Argon2id",
                "format": "Adyton Vault",
                "status": tr("dz.status.valid", "Valid format"),
                "subtitle": tr("dz.ready", "Ready to open"),
            }
        )
        return info

    def _set_badge(self, text: str, state: str):
        """Update badge kanan atas dan paksa QSS membaca ulang property state."""
        self.valid_badge.setText(text)
        self.valid_badge.setProperty("state", state)
        # Backward compatibility dengan QSS lama yang masih membaca property valid.
        self.valid_badge.setProperty("valid", state in {"ok", "verified", "busy"})
        self.valid_badge.style().unpolish(self.valid_badge)
        self.valid_badge.style().polish(self.valid_badge)

    def _set_meta_status(self, text: str):
        if len(self.meta_items) >= 4:
            self.meta_items[3]._meta_value.setText(text)

    def _set_integrity_status(self, text: str):
        if len(self.enc_items) >= 4:
            self.enc_items[3]._enc_val.setText(text)

    def can_open_file(self) -> bool:
        """True jika file lolos validasi format ringan dan boleh dicoba dibuka."""
        return bool(self._path_file and self._file_format_openable)

    def get_format_status(self) -> str:
        return self._format_status_text

    def set_verification_state(self, state: str, message: str | None = None):
        """Sinkronkan status UI setelah proses buka brankas berjalan.

        state:
        - pending: format valid, integritas belum diverifikasi
        - checking: sedang verifikasi password/tag AES-GCM
        - verified: password benar + tag AES-GCM valid
        - failed: password salah / file rusak / tag AES-GCM gagal
        """
        if not self._path_file:
            return

        if state == "checking":
            self.lbl_ready.setText(message or tr("dz.status.verifying_pw", "Verifying password"))
            self._set_badge("CHECK…", "busy")
            self._set_meta_status(tr("dz.status.verifying", "Verifying"))
            self._set_integrity_status(tr("dz.status.verifying", "Verifying"))
            return

        if state == "verified":
            self.lbl_ready.setText(
                message or tr("dz.status.integrity_verified", "Integrity verified")
            )
            self._set_badge("VERIFIED  ✓", "verified")
            self._set_meta_status(tr("dz.status.verified", "Verified"))
            self._set_integrity_status(tr("dz.status.verified", "Verified"))
            return

        if state == "failed":
            self.lbl_ready.setText(
                message or tr("dz.status.wrong", "Wrong password or corrupted file")
            )
            self._set_badge("FAILED", "error")
            self._set_meta_status(tr("dz.status.verification_failed", "Verification failed"))
            self._set_integrity_status(tr("dz.status.verification_failed", "Verification failed"))
            return

        if state == "unsupported":
            # Format valid sebagai vault, tapi tidak didukung untuk konteks ini
            # (mis. vault lama yang tak bisa dikelola di tab Manage).
            self.lbl_ready.setText(message or tr("dz.status.unsupported", "Unsupported format"))
            self._set_badge("UNSUPPORTED", "warn")
            self._set_meta_status(tr("dz.status.unsupported_here", "Unsupported here"))
            self._set_integrity_status("—")
            return

        # pending / cancelled / retry: kembali ke status hasil validasi format ringan.
        self.lbl_ready.setText(message or tr("dz.meta.waiting", "Waiting for password"))
        self._set_badge(
            "FORMAT  ✓" if self._file_format_openable else "ERROR",
            self._format_badge_state,
        )
        self._set_meta_status(self._format_status_text)
        self._set_integrity_status(tr("dz.sec.notverified", "Not yet verified"))

    def _update_card_style(self, is_empty: bool):
        # Use property-based styling for empty state (same system as DropZoneLock)
        # so global QSS in styles.py applies consistently.
        if is_empty:
            if hasattr(self.card_file, "set_empty_state"):
                self.card_file.set_empty_state(True)
            # For filled state we still override with inline (different visual treatment)
        else:
            self.card_file.setStyleSheet(f"""
                QFrame#DropArea {{ border: 1px solid {CLR_BORDER}; background-color: {CLR_CARD}; border-radius: 22px; }}
                QFrame#DropArea[dragActive="true"] {{ border: 1.5px dashed {CLR_ACCENT}; background-color: {CLR_INSET}; }}
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
        self._file_format_openable = False
        self._format_status_text = "—"
        self._format_badge_state = "idle"
        self._custom_tooltip.hide_tooltip()
        self.stack_file.setCurrentIndex(0)
        self._update_card_style(True)

        self.btn_ganti.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if hasattr(self, "btn_clear"):
            self.btn_clear.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.file_changed.emit("")

    def _pilih_file(self):
        f, _ = QFileDialog.getOpenFileName(
            self,
            tr("dz.choose_dialog", "Choose Vault File"),
            "",
            tr("dz.choose_filter", "Adyton Crypt Files (*.adtn)"),
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
