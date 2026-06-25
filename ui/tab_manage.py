"""
Modul: tab_manage.py
Deskripsi: Tab "Manage Vault" — ganti password dan kelola recovery key untuk
           vault yang sudah ada, tanpa mengenkripsi ulang data.
"""

import qtawesome as qta
from loguru import logger
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.crypto import generate_recovery_code
from core.vault import (
    VaultStatus,
    add_recovery_key,
    change_password,
    remove_recovery_key,
    vault_info,
)
from core.worker import CryptoWorker

from .components.create_password_form import CreatePasswordForm
from .components.drop_zone_open import DropZoneOpen
from .components.recent_vaults_bar import RecentVaultsBar
from .dialogs import ModernMessageBox, RecoveryCodeDialog
from .i18n import register, tr
from .styles import CLR_ACCENT, CLR_TEXT_DIM, CLR_WARN
from .widgets import (
    AnimatedNotifBar,
    MethodCard,
    PasswordLineEdit,
    apply_shadow,
    build_card_header,
    make_recovery_info_box,
)

_MODE_CODE = "code"
_MODE_PASSPHRASE = "passphrase"


class TabManage(QWidget):
    system_notification = Signal(str, str)
    status_changed = Signal(str, str, str)

    def __init__(self):
        super().__init__()
        self.worker: CryptoWorker | None = None
        self._vault_path: str | None = None
        self._info: dict = {}
        # Sibuk (operasi berjalan) — precondition vault dihitung langsung dari
        # _vault_path + _info di _refresh_action_buttons.
        self._busy = False
        self._build_ui()
        self._connect_signals()
        self._sync_stack_height(self.stack.currentIndex())
        self._refresh_action_buttons()  # mulai: tombol aksi nonaktif

    # ── UI ──────────────────────────────────────────────────────────────────
    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(22)

        self.drop_zone = DropZoneOpen()

        # Card kanan dibungkus holder transparan [card, stretch]: card mengikuti
        # tinggi kontennya (stretch transparan menyerap ruang di bawahnya).
        holder = QWidget()
        holder_lay = QVBoxLayout(holder)
        holder_lay.setContentsMargins(0, 0, 0, 0)
        holder_lay.setSpacing(0)
        holder_lay.addWidget(self._build_panel())
        holder_lay.addStretch(1)

        # Kolom kiri: drop zone mengisi ruang di ATAS, Recent mengisi sisa di BAWAH-nya
        # (memanfaatkan ruang kosong karena panel kanan—form ganti password—lebih tinggi).
        # Recent dibatasi 2 kartu agar muat di kolom setengah-lebar. Saat Recent mati/
        # kosong ia sembunyi (0px) dan drop zone mengisi penuh → tetap tanpa void.
        self.recent_bar = RecentVaultsBar(max_cards=2)
        self.recent_bar.open_requested.connect(self._open_recent)
        left_col = QWidget()
        left_lay = QVBoxLayout(left_col)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(22)
        # Drop zone hug-content (tidak melar mengikuti panel kanan yang tinggi);
        # Recent menyusul di bawah; trailing stretch menyerap sisa ruang sebagai
        # padding transparan tipis (alih-alih membesarkan kartu drop zone).
        left_lay.addWidget(self.drop_zone, 0)
        left_lay.addWidget(self.recent_bar, 0)
        left_lay.addStretch(1)

        cols = QHBoxLayout()
        cols.setSpacing(28)
        cols.addWidget(left_col, 1)
        cols.addWidget(holder, 1)

        # Kolom dibungkus SATU scroll luar (mengganti scroll-panel lama) agar Security
        # Details / form panjang tidak terpotong saat tinggi jendela mepet.
        scroll_content = QWidget()
        sc_lay = QVBoxLayout(scroll_content)
        sc_lay.setContentsMargins(0, 0, 0, 0)
        sc_lay.setSpacing(0)
        sc_lay.addLayout(cols, 1)

        self.content_scroll = QScrollArea()
        self.content_scroll.setObjectName("ManageScrollArea")
        self.content_scroll.setWidget(scroll_content)
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content_scroll.setStyleSheet(
            "QScrollArea#ManageScrollArea, QScrollArea#ManageScrollArea > QWidget > QWidget"
            " { background: transparent; }"
        )
        main_layout.addWidget(self.content_scroll, 1)

        self.notif = AnimatedNotifBar(self)

    def _open_recent(self, path: str) -> None:
        if self.worker is not None:
            return
        self.drop_zone.load_file(path)

    def _build_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        apply_shadow(card, blur_radius=30, opacity=40)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(10)

        header, lbl_h_title, lbl_h_sub = build_card_header(
            "mdi6.cog-outline",
            CLR_ACCENT,
            "Manage Vault",
            "Change the password or recovery key of an existing vault",
        )
        register(lbl_h_title, "manage.title", "Manage Vault")
        register(
            lbl_h_sub, "manage.sub", "Change the password or recovery key of an existing vault"
        )
        lay.addLayout(header)

        self.lbl_info = QLabel()
        self.lbl_info.setObjectName("OptionDesc")
        self.lbl_info.setWordWrap(True)
        register(self.lbl_info, "manage.select", "Select a vault file to manage.")
        lay.addWidget(self.lbl_info)

        lay.addSpacing(4)
        lbl_cur = QLabel()
        lbl_cur.setObjectName("SectionLabel")
        register(lbl_cur, "manage.current_label", "Current password or recovery key")
        lay.addWidget(lbl_cur)
        self.entry_current = PasswordLineEdit()
        register(
            self.entry_current,
            "manage.current_placeholder",
            "Enter the current password or recovery key…",
            "setPlaceholderText",
        )
        register(
            self.entry_current,
            "a11y.manage.current",
            "Current password or recovery key",
            "setAccessibleName",
        )
        lay.addWidget(self.entry_current)

        # Segmented: pilih aksi (gaya konsisten dgn toggle Enkripsi/Dekripsi).
        seg_container = QFrame()
        seg_container.setObjectName("TabContainer")
        seg_container.setFixedHeight(38)
        seg = QHBoxLayout(seg_container)
        seg.setContentsMargins(3, 3, 3, 3)
        seg.setSpacing(3)
        self.btn_seg_pw = QPushButton()
        register(self.btn_seg_pw, "manage.seg.pw", " Change password")
        self.btn_seg_pw.setIcon(
            qta.icon("mdi6.lock-outline", color=CLR_TEXT_DIM, color_on=CLR_ACCENT)
        )
        self.btn_seg_rec = QPushButton()
        register(self.btn_seg_rec, "manage.seg.rec", " Recovery key")
        self.btn_seg_rec.setIcon(
            qta.icon("mdi6.key-outline", color=CLR_TEXT_DIM, color_on=CLR_ACCENT)
        )
        for b in (self.btn_seg_pw, self.btn_seg_rec):
            b.setCheckable(True)
            b.setObjectName("TabBtn")
            b.setIconSize(QSize(16, 16))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            seg.addWidget(b, 1)
        self._seg_group = QButtonGroup(self)
        self._seg_group.setExclusive(True)
        self._seg_group.addButton(self.btn_seg_pw, 0)
        self._seg_group.addButton(self.btn_seg_rec, 1)
        self.btn_seg_pw.setChecked(True)
        lay.addSpacing(2)
        lay.addWidget(seg_container)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_page_password())
        self.stack.addWidget(self._build_page_recovery())
        # Stack mengikuti tinggi halaman AKTIF (bukan halaman tertinggi) supaya
        # card menyusut saat aksi "Recovery key" yang pendek dipilih.
        self.stack.currentChanged.connect(self._sync_stack_height)
        lay.addWidget(self.stack)
        return card

    def _build_page_password(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(10)

        self.form = CreatePasswordForm()
        lay.addWidget(self.form)

        self.btn_change = QPushButton()
        register(self.btn_change, "manage.btn.change", "Change Password")
        self.btn_change.setObjectName("BtnInlinePrimary")
        self.btn_change.setFixedHeight(40)
        self.btn_change.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(self.btn_change)
        return page

    def _build_page_recovery(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(10)

        # === Kasus TAMBAH recovery (saat vault belum punya recovery key) ===
        self.add_controls = QWidget()
        add_lay = QVBoxLayout(self.add_controls)
        add_lay.setContentsMargins(0, 0, 0, 0)
        add_lay.setSpacing(12)

        add_lay.addWidget(make_recovery_info_box())

        method_lbl = QLabel()
        method_lbl.setObjectName("SectionLabel")
        register(method_lbl, "manage.method_label", "Recovery method")
        add_lay.addWidget(method_lbl)

        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.card_gen = MethodCard(
            "mdi6.dice-5-outline",
            "Generate code",
            "Create a one-time recovery code, shown once.",
        )
        self.card_gen.tr_set(
            "recovery.card.code.title",
            "Generate code",
            "recovery.card.code.desc",
            "Create a one-time recovery code, shown once.",
        )
        self.card_pass = MethodCard(
            "mdi6.form-textbox-password",
            "Use passphrase",
            "Set a recovery phrase you choose yourself.",
        )
        self.card_pass.tr_set(
            "recovery.card.pass.title",
            "Use passphrase",
            "recovery.card.pass.desc",
            "Set a recovery phrase you choose yourself.",
        )
        cards.addWidget(self.card_gen, 1)
        cards.addWidget(self.card_pass, 1)
        add_lay.addLayout(cards)

        self.entry_rec_pass = PasswordLineEdit()
        register(
            self.entry_rec_pass,
            "manage.passphrase_placeholder",
            "Recovery passphrase…",
            "setPlaceholderText",
        )
        register(
            self.entry_rec_pass,
            "a11y.manage.new_rec",
            "New recovery passphrase",
            "setAccessibleName",
        )
        self.entry_rec_pass.hide()
        add_lay.addWidget(self.entry_rec_pass)

        self.btn_add = QPushButton()
        register(self.btn_add, "manage.btn.add", "Add Recovery Key")
        self.btn_add.setObjectName("BtnInlinePrimary")
        self.btn_add.setFixedHeight(40)
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        add_lay.addWidget(self.btn_add)
        lay.addWidget(self.add_controls)

        # === Kasus HAPUS recovery (saat vault sudah punya recovery key) ===
        self.lbl_rec_state = QLabel()
        self.lbl_rec_state.setObjectName("OptionDesc")
        self.lbl_rec_state.setWordWrap(True)
        register(self.lbl_rec_state, "manage.has_recovery", "This vault has a recovery key.")
        self.lbl_rec_state.hide()
        lay.addWidget(self.lbl_rec_state)

        self.btn_remove = QPushButton()
        register(self.btn_remove, "manage.btn.remove", "Remove Recovery Key")
        self.btn_remove.setObjectName("BtnInlineSecondary")
        self.btn_remove.setFixedHeight(40)
        self.btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove.hide()
        lay.addWidget(self.btn_remove)

        # Pilihan metode (default: generate code).
        self._rec_method = _MODE_CODE
        self.card_gen.set_selected(True)
        self.card_pass.set_selected(False)
        self.card_gen.clicked.connect(lambda: self._select_method(_MODE_CODE))
        self.card_pass.clicked.connect(lambda: self._select_method(_MODE_PASSPHRASE))
        return page

    def _select_method(self, method: str):
        self._rec_method = method
        self.card_gen.set_selected(method == _MODE_CODE)
        self.card_pass.set_selected(method == _MODE_PASSPHRASE)
        self.entry_rec_pass.setVisible(method == _MODE_PASSPHRASE)
        self._sync_stack_height()
        self._refresh_action_buttons()

    def _sync_stack_height(self, *_) -> None:
        """Patok tinggi stack ke halaman aktif agar card mengikuti kontennya.

        Tanpa ini, QStackedWidget memesan tinggi halaman tertinggi, sehingga card
        tetap tinggi (ruang kosong) saat halaman pendek ditampilkan.
        """
        page = self.stack.currentWidget()
        if page is None:
            return
        # Paksa layout (dan child seperti add_controls) menghitung ulang DULU,
        # supaya sizeHint tidak basi setelah field passphrase disembunyikan —
        # kalau basi, stack dipatok terlalu tinggi dan kartu metode ikut memuai.
        for lay in (self.add_controls.layout(), page.layout()):
            if lay is not None:
                lay.invalidate()
                lay.activate()
        self.stack.setFixedHeight(page.sizeHint().height())

    def _connect_signals(self):
        self.drop_zone.file_changed.connect(self._on_file_changed)
        self._seg_group.idClicked.connect(self.stack.setCurrentIndex)
        self.btn_change.clicked.connect(self._change_password)
        self.btn_add.clicked.connect(self._add_recovery)
        self.btn_remove.clicked.connect(self._remove_recovery)
        # Gate tombol aksi: aktif hanya saat precondition + validitas terpenuhi
        # (analog Lock Now / Open Vault / Encrypt Text).
        self.form.valid_state_changed.connect(lambda *_: self._refresh_action_buttons())
        self.entry_current.textChanged.connect(lambda *_: self._refresh_action_buttons())
        self.entry_rec_pass.textChanged.connect(lambda *_: self._refresh_action_buttons())

    # ── Vault selection ───────────────────────────────────────────────────────
    def _on_file_changed(self, path: str):
        self._vault_path = path or None
        self.entry_current.clear()
        self.form.reset()
        self.entry_rec_pass.clear()
        if not path or not self.drop_zone.can_open_file():
            self.lbl_info.setText(tr("manage.select", "Select a vault file to manage."))
            # Biarkan kontrol tetap interaktif (input bisa diklik) walau belum ada
            # vault — _guard() yang mencegah aksi dengan pesan jelas. Memakai True
            # juga me-reset state setelah sebelumnya memuat vault unsupported.
            self._set_actions_enabled(True)
            self.status_changed.emit(
                tr("manage.status.idle.title", "Manage vault"),
                tr("manage.status.idle.sub", "Select a vault to manage"),
                "idle",
            )
            return
        self._refresh_info()

    def _refresh_info(self):
        if not self._vault_path:
            return
        self._info = vault_info(self._vault_path)
        fmt = self._info.get("format", "unknown")

        if not self._info.get("supports_change_password"):
            self.lbl_info.setText(
                tr(
                    "manage.unsupported",
                    "This vault was made by a different version of Adyton Crypt ({fmt}) "
                    "and can't be managed here. Please update the app.",
                ).format(fmt=fmt)
            )
            self._set_actions_enabled(False)
            # Badge di kartu vault ikut menandai "unsupported" agar konsisten dengan
            # status di header (bukan tetap "FORMAT ✓").
            self.drop_zone.set_verification_state(
                "unsupported",
                tr(
                    "manage.different_version", "Different version ({fmt}) — can't be managed here"
                ).format(fmt=fmt),
            )
            self.status_changed.emit(
                tr("manage.status.unsupported.title", "Unsupported format"),
                tr("manage.status.unsupported.sub", "Update the app to manage"),
                "warn",
            )
            return

        has_recovery = self._info.get("has_recovery", False)
        has_hint = self._info.get("has_hint", False)
        yes, no = tr("common.yes", "yes"), tr("common.no", "no")
        self.lbl_info.setText(
            tr("manage.info", "Format {fmt} · Recovery key: {rec} · Hint: {hint}").format(
                fmt=fmt, rec=yes if has_recovery else no, hint=yes if has_hint else no
            )
        )
        self._set_actions_enabled(True)
        self.drop_zone.set_verification_state("pending", tr("manage.ready", "Ready to manage"))
        self._update_recovery_section(has_recovery)
        self.status_changed.emit(
            tr("manage.ready", "Ready to manage"),
            tr("manage.ready.sub", "Enter the current password"),
            "ready",
        )

    def _update_recovery_section(self, has_recovery: bool):
        # Sudah punya recovery → tawarkan hapus. Belum → tampilkan pilihan tambah.
        self.add_controls.setVisible(not has_recovery)
        self.lbl_rec_state.setVisible(has_recovery)
        self.btn_remove.setVisible(has_recovery)
        # Tinggi halaman recovery berubah (add vs remove) → samakan tinggi stack.
        self._sync_stack_height(self.stack.currentIndex())

    def _set_actions_enabled(self, enabled: bool):
        # Input tetap interaktif; tombol AKSI di-gate terpisah lewat
        # _refresh_action_buttons (disable sampai precondition + valid).
        for w in (
            self.entry_current,
            self.btn_seg_pw,
            self.btn_seg_rec,
            self.form,
            self.card_gen,
            self.card_pass,
            self.entry_rec_pass,
        ):
            w.setEnabled(enabled)
        self._refresh_action_buttons()

    def _refresh_action_buttons(self):
        """Tombol aksi aktif HANYA saat preconditionnya terpenuhi — analog tombol
        Lock Now / Open Vault / Encrypt Text yang disable sampai valid:
        vault valid termuat, tak sibuk, kredensial saat ini terisi, dan input
        aksi (password baru / passphrase recovery) memenuhi syarat."""
        # Precondition vault = persis seperti _guard() (dihitung langsung dari
        # state, bukan flag yang bisa basi saat drop-zone re-emit file_changed).
        vault_ok = bool(self._vault_path) and self._info.get("supports_change_password", False)
        ready = vault_ok and not self._busy and bool(self.entry_current.text())
        self.btn_change.setEnabled(ready and self.form.is_valid())
        rec_ok = self._rec_method == _MODE_CODE or bool(self.entry_rec_pass.text().strip())
        self.btn_add.setEnabled(ready and rec_ok)
        self.btn_remove.setEnabled(ready)

    # ── Validation helpers ────────────────────────────────────────────────────
    def _guard(self) -> bool:
        if self.worker is not None:
            return False
        if not self._vault_path or not self._info.get("supports_change_password"):
            self.notif.show_msg(
                "warn", tr("manage.guard.select", "Select a vault to manage first."), 4000
            )
            return False
        if not self.entry_current.text():
            self.notif.show_msg(
                "warn",
                tr("manage.guard.current", "Enter the current password or recovery key."),
                4000,
            )
            return False
        return True

    # ── Actions ───────────────────────────────────────────────────────────────
    def _change_password(self):
        if not self._guard():
            return
        if not self.form.is_valid():
            self.notif.show_msg(
                "warn",
                tr("manage.invalid_pw", "Choose a new password that meets all the requirements."),
                4000,
            )
            return
        self._run_action(
            change_password, self._vault_path, self.entry_current.text(), self.form.get_password()
        )

    def _add_recovery(self):
        if not self._guard():
            return
        if self._rec_method == _MODE_PASSPHRASE:
            passphrase = self.entry_rec_pass.text()
            if not passphrase.strip():
                self.notif.show_msg(
                    "warn", tr("manage.passphrase_empty", "Enter a recovery passphrase."), 4000
                )
                return
            self._run_action(
                add_recovery_key,
                self._vault_path,
                self.entry_current.text(),
                passphrase,
                _MODE_PASSPHRASE,
            )
        else:
            code = generate_recovery_code()
            if RecoveryCodeDialog(code, parent=self).exec() != QDialog.DialogCode.Accepted:
                return
            self._run_action(
                add_recovery_key, self._vault_path, self.entry_current.text(), code, _MODE_CODE
            )

    def _remove_recovery(self):
        if not self._guard():
            return
        dialog = ModernMessageBox(
            title=tr("manage.remove.title", "Remove Recovery Key"),
            message=tr(
                "manage.remove.msg",
                "The recovery key for this vault will be removed. After this, only the "
                "password can open it.\n\nRemove the recovery key?",
            ),
            icon_name="mdi6.key-remove-outline",
            icon_color=CLR_WARN,
            parent=self,
        )
        dialog.btn_yes.setText(tr("common.remove", "Remove"))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_action(remove_recovery_key, self._vault_path, self.entry_current.text())

    # ── Worker plumbing ───────────────────────────────────────────────────────
    def _run_action(self, func, *args):
        self._set_busy(True)
        self.worker = CryptoWorker(func, *args, parent=self)
        self.worker.finished.connect(self._on_worker_done)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def _set_busy(self, busy: bool):
        self._busy = busy
        self.drop_zone.set_busy(busy)
        self._set_actions_enabled(not busy)
        if busy:
            self.status_changed.emit(
                tr("manage.status.working.title", "Working"),
                tr("manage.status.working.sub", "Updating the vault"),
                "busy",
            )

    def _on_worker_done(self, result):
        self.worker = None
        # Undo state "busy" untuk SEMUA hasil: drop zone (Change Vault File / X),
        # input, dan flag _busy. Tanpa ini, kontrol kiri ketinggalan disabled.
        self._set_busy(False)
        status, message = result

        if status == VaultStatus.SUCCESS:
            self.entry_current.clear()
            self.form.reset()
            self.entry_rec_pass.clear()
            self._refresh_info()  # juga re-enable kontrol
            self.notif.show_msg(
                "ok", f" {message or tr('manage.done', 'Vault updated successfully.')}", 6000
            )
            self.status_changed.emit(
                tr("manage.status.done.title", "Done"),
                tr("manage.status.done.sub", "Vault updated successfully"),
                "success",
            )
            self.system_notification.emit(
                "Adyton Crypt", tr("manage.notif.updated", "Vault credentials updated.")
            )
            logger.info(f"Manage vault sukses: {message}")
        elif status == VaultStatus.WRONG_PASSWORD:
            self.notif.show_msg(
                "err",
                tr("manage.wrong", "The current password or recovery key is incorrect."),
                7000,
            )
            self.status_changed.emit(
                tr("manage.status.wrong.title", "Incorrect credential"),
                tr("manage.status.wrong.sub", "Try again"),
                "error",
            )
        else:
            self.notif.show_msg(
                "err", message or tr("manage.fail", "Couldn't update the vault."), 8000
            )
            self.status_changed.emit(
                tr("manage.status.failed.title", "Failed"),
                tr("manage.status.failed.sub", "Couldn't update the vault"),
                "error",
            )
            logger.error(f"Manage vault gagal: {message}")

    # ── External ──────────────────────────────────────────────────────────────
    def auto_load_file(self, path: str) -> None:
        self.drop_zone.load_file(path)
