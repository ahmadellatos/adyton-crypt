import os

import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ..i18n import register, tr
from ..styles import (
    CLR_ACCENT,
    CLR_BORDER,
    CLR_INSET,
    CLR_TEXT_MUTED,
    CLR_WARN,
)
from ..widgets import ElidedLabel, PasswordLineEdit, apply_shadow, build_tips_box

_PLACEHOLDER_PW = "Type your password here…"
_PLACEHOLDER_PW_RECOVERY = "Password or recovery key…"


def _placeholder_pw() -> str:
    return tr("open.pw.placeholder", _PLACEHOLDER_PW)


def _placeholder_pw_recovery() -> str:
    return tr("open.pw.placeholder.recovery", _PLACEHOLDER_PW_RECOVERY)


class PasswordPanelOpen(QFrame):
    # Emit boolean True jika password tidak kosong
    valid_state_changed = Signal(bool)
    retry_requested = Signal()
    pick_file_requested = Signal()
    # Dipancarkan saat pilihan keyfile berubah → TabBuka me-revalidasi tombol Open
    # (untuk vault 2FA tanpa recovery, keyfile wajib agar tombol aktif).
    keyfile_changed = Signal()
    # Enter di field password → minta buka vault. Dipancarkan dari eventFilter yang
    # SEKALIGUS mengonsumsi event Enter (lihat eventFilter) agar tidak merambat ke
    # tombol CTA yang menerima fokus saat field disembunyikan.
    submit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        apply_shadow(self, blur_radius=30, opacity=40)
        self._build_ui()
        self._setup_accessibility()

    def _build_ui(self):
        self.v_pw = QVBoxLayout(self)
        self.v_pw.setContentsMargins(24, 18, 24, 18)
        self.v_pw.setSpacing(11)

        self.lbl_title_pw = QLabel()
        self.lbl_title_pw.setObjectName("CardTitle")
        register(self.lbl_title_pw, "open.pw.title", "Enter Your Password")
        self.v_pw.addWidget(self.lbl_title_pw)

        self.sub_pw = QLabel()
        self.sub_pw.setObjectName("CardSubtitle")
        self.sub_pw.setWordWrap(True)
        register(self.sub_pw, "open.pw.sub", "Enter the password you used when locking this vault.")
        self.v_pw.addWidget(self.sub_pw)
        self.v_pw.addSpacing(4)

        self._vault_hint: str | None = None
        self._vault_has_recovery = False
        self._vault_requires_keyfile = False
        self._keyfile_path = ""
        self.hint_box = self._build_hint_box()
        self.hint_box.hide()
        self.v_pw.addWidget(self.hint_box)

        self.entry_pw = PasswordLineEdit(_placeholder_pw())
        register(
            self.entry_pw, "a11y.pw.open_vault", "Password to open the vault", "setAccessibleName"
        )
        self.entry_pw.textChanged.connect(self._on_pw_change)
        self.v_pw.addWidget(self.entry_pw)

        self.keyfile_box = self._build_keyfile_box()
        self.keyfile_box.hide()
        self.v_pw.addWidget(self.keyfile_box)

        self.status_box = self._build_status_box()
        self.status_box.hide()
        self.v_pw.addWidget(self.status_box)

        self.error_box = self._build_error_box()
        self.error_box.hide()
        self.v_pw.addWidget(self.error_box)

        self.v_pw.addStretch(1)
        self.secondary_actions = self._build_secondary_actions()
        self.v_pw.addWidget(self.secondary_actions)
        self.info_box = self._build_info_box()
        self.v_pw.addWidget(self.info_box)

    def _build_secondary_actions(self) -> QFrame:
        """Aksi sekunder atas vault (Verify + Browse) — satu baris dua tombol.

        Ditempatkan di sini (bukan di dasar tab, ditumpuk full-width) agar berdampingan
        & dekat dengan input password: kedua aksi butuh password/keyfile yang sama
        seperti "Buka Vault". Label sengaja ringkas agar muat setengah lebar; makna
        penuh ada di tooltip. ``TabBuka`` memakai ``btn_verify``/``btn_browse`` untuk
        gating & wiring sinyal, dan menyembunyikan seluruh baris ini saat operasi jalan.
        """
        box = QFrame()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        self.btn_verify = QPushButton()
        self.btn_verify.setObjectName("BtnInlineSecondary")
        self.btn_verify.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_verify.setMinimumHeight(40)
        self.btn_verify.setIcon(qta.icon("mdi6.shield-search", color=CLR_TEXT_MUTED))
        register(self.btn_verify, "open.verify.btn", "Verify integrity")
        register(
            self.btn_verify,
            "open.verify.tip",
            "Check every block without extracting anything",
            "setToolTip",
        )
        register(
            self.btn_verify,
            "a11y.btn.verify_vault",
            "Verify vault integrity button",
            "setAccessibleName",
        )
        self.btn_verify.setEnabled(False)

        self.btn_browse = QPushButton()
        self.btn_browse.setObjectName("BtnInlineSecondary")
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.setMinimumHeight(40)
        self.btn_browse.setIcon(qta.icon("mdi6.folder-search-outline", color=CLR_TEXT_MUTED))
        register(self.btn_browse, "open.browse.btn", "Browse contents")
        register(
            self.btn_browse,
            "open.browse.tip",
            "List the files inside and extract only the ones you pick",
            "setToolTip",
        )
        register(
            self.btn_browse,
            "a11y.btn.browse_vault",
            "Browse vault contents button",
            "setAccessibleName",
        )
        self.btn_browse.setEnabled(False)

        row.addWidget(self.btn_verify, 1)
        row.addWidget(self.btn_browse, 1)
        return box

    def _build_info_box(self) -> QFrame:
        tips = [
            (
                "mdi6.shield-check-outline",
                CLR_ACCENT,
                "open.tip.1",
                "Your password can't be recovered. Keep it somewhere safe.",
            ),
            (
                "mdi6.lock-outline",
                CLR_WARN,
                "open.tip.2",
                "Use the exact password you created when locking this vault.",
            ),
            (
                "mdi6.file-document-outline",
                CLR_TEXT_MUTED,
                "open.tip.3",
                "Only .adtn files created by Adyton Crypt can be opened.",
            ),
        ]
        return build_tips_box(tips, content_margins=(14, 12, 14, 12), spacing=10, icon_px=15)

    def _build_keyfile_box(self) -> QFrame:
        """Pemilih keyfile (2FA), hanya tampil bila vault membutuhkan keyfile.

        Keyfile bersifat opsional di UI: user boleh memakai recovery key (yang tak
        butuh keyfile) sebagai gantinya. Jadi tidak ada pemaksaan keras di sini —
        cukup affordance + penyimpanan path; pemeriksaan benar/salah terjadi saat
        dekripsi.
        """
        box = QFrame()
        box.setObjectName("KeyfileOpenBox")
        box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        box.setStyleSheet(
            f"QFrame#KeyfileOpenBox {{ background-color: {CLR_INSET};"
            f" border: 1px solid {CLR_BORDER}; border-radius: 10px; }}"
        )
        outer = QVBoxLayout(box)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(10)
        icon = QLabel()
        icon.setPixmap(qta.icon("mdi6.key-chain-variant", color=CLR_ACCENT).pixmap(16, 16))
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)

        self.lbl_keyfile = ElidedLabel(tr("open.keyfile.none", "No keyfile selected"))
        self.lbl_keyfile.setObjectName("MutedText")
        row.addWidget(self.lbl_keyfile, 1)

        self.btn_choose_keyfile = QPushButton()
        register(self.btn_choose_keyfile, "open.keyfile.choose", "Select keyfile")
        self.btn_choose_keyfile.setObjectName("BtnInlineSecondary")
        self.btn_choose_keyfile.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_choose_keyfile.clicked.connect(self._choose_keyfile)
        row.addWidget(self.btn_choose_keyfile, 0)
        outer.addLayout(row)

        # Teks note di-set di _apply_meta (tergantung ada/tidaknya recovery key); di
        # sini cukup registrasi varian "ada recovery" sebagai default bilingual.
        self.lbl_keyfile_note = QLabel()
        register(
            self.lbl_keyfile_note,
            "open.keyfile.note",
            "This vault needs its keyfile. Select it, or use your recovery key instead.",
        )
        self.lbl_keyfile_note.setObjectName("OptionDesc")
        self.lbl_keyfile_note.setWordWrap(True)
        outer.addWidget(self.lbl_keyfile_note)
        return box

    def _choose_keyfile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("open.keyfile.dialog", "Select keyfile"), "", ""
        )
        if path:
            self._keyfile_path = path
            self.lbl_keyfile.setText(os.path.basename(path))
            self.keyfile_changed.emit()

    def _build_hint_box(self) -> QFrame:
        box = QFrame()
        box.setObjectName("HintBox")
        box.setStyleSheet(
            f"QFrame#HintBox {{ background-color: {CLR_INSET};"
            f" border: 1px solid {CLR_BORDER}; border-radius: 10px; }}"
        )
        lay = QHBoxLayout(box)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)
        self._hint_icon = QLabel()
        self._hint_icon.setPixmap(
            qta.icon("mdi6.lightbulb-on-outline", color=CLR_WARN).pixmap(16, 16)
        )
        lay.addWidget(self._hint_icon, alignment=Qt.AlignmentFlag.AlignTop)
        self.lbl_hint = QLabel("")
        self.lbl_hint.setObjectName("MutedText")
        self.lbl_hint.setWordWrap(True)
        # Hint berasal dari pembuat vault dan ditampilkan ke siapa pun yang membuka
        # file. Paksa PlainText agar markup Qt (mis. <b>, <img>) tidak pernah
        # di-render — hindari layout rusak / teks menyamar dari hint berbahaya.
        self.lbl_hint.setTextFormat(Qt.TextFormat.PlainText)
        lay.addWidget(self.lbl_hint, 1)
        return box

    def _build_status_box(self) -> QFrame:
        box = QFrame()
        box.setObjectName("ProcessStatusBox")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        intro = QLabel()
        register(
            intro,
            "open.pw.status.intro",
            "Your vault is being verified and extracted. Keep the app open and the drive connected until it finishes.",
        )
        intro.setObjectName("ProcessText")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        self.lbl_status_file = self._make_status_row(lay, "open.pw.status.file", "File", "—")
        self.lbl_status_size = self._make_status_row(lay, "open.pw.status.size", "Size", "—")
        self.lbl_status_stage = self._make_status_row(
            lay, "open.pw.status.stage", "Stage", tr("open.pw.status.preparing", "Preparing vault")
        )

        return box

    def _build_error_box(self) -> QFrame:
        box = QFrame()
        box.setObjectName("OpenErrorBox")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(12)

        self.lbl_error_msg = QLabel()
        register(self.lbl_error_msg, "open.pw.error", "Incorrect password or corrupted vault file.")
        self.lbl_error_msg.setObjectName("OpenErrorText")
        self.lbl_error_msg.setWordWrap(True)
        lay.addWidget(self.lbl_error_msg)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_retry = QPushButton()
        register(self.btn_retry, "open.pw.retry", "Try Again")
        self.btn_retry.setObjectName("BtnInlinePrimary")
        self.btn_retry.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_retry.clicked.connect(self.retry_requested.emit)
        row.addWidget(self.btn_retry)

        self.btn_pick_file = QPushButton()
        register(self.btn_pick_file, "open.pw.pickfile", "Choose Another File")
        self.btn_pick_file.setObjectName("BtnInlineSecondary")
        self.btn_pick_file.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pick_file.clicked.connect(self.pick_file_requested.emit)
        row.addWidget(self.btn_pick_file)
        row.addStretch(1)
        lay.addLayout(row)

        return box

    def _make_status_row(
        self, parent_layout: QVBoxLayout, label_key: str, label_default: str, value: str
    ) -> QLabel:
        row = QHBoxLayout()
        row.setSpacing(12)
        lbl = QLabel()
        register(lbl, label_key, label_default)
        lbl.setObjectName("ProcessLabel")
        lbl.setFixedWidth(64)
        val = QLabel(value)
        val.setObjectName("ProcessValue")
        val.setWordWrap(True)
        row.addWidget(lbl)
        row.addWidget(val, 1)
        parent_layout.addLayout(row)
        return val

    def _setup_accessibility(self):
        self.entry_pw.installEventFilter(self)
        self.setTabOrder(self.entry_pw, self.entry_pw)  # internal handling

    def eventFilter(self, obj, event):
        # entry_pw adalah PasswordLineEdit (komposit): installEventFilter-nya memasang
        # filter ke QLineEdit di dalamnya, jadi event Enter tiba dengan obj = line_edit,
        # BUKAN entry_pw. Cocokkan ke line_edit itu.
        if obj is self.entry_pw.line_edit and event.type() == event.Type.KeyPress:
            if (
                event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and not event.isAutoRepeat()
                and event.modifiers()
                in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.KeypadModifier)
            ):
                # Picu buka lalu KONSUMSI event Enter di sini. Kalau dibiarkan merambat,
                # QLineEdit tidak meng-accept Enter (agar bisa mengaktifkan tombol default),
                # sehingga event sampai ke tombol CTA yang menerima fokus begitu field
                # password disembunyikan → _EnterActivatesButtonFilter mengkliknya →
                # _proses kedua = dekripsi langsung di-cancel begitu dimulai.
                self.submit_requested.emit()
                return True
        if event.type() in (event.Type.FocusIn, event.Type.FocusOut):
            if obj == self.entry_pw:
                is_focus = event.type() == event.Type.FocusIn
                self.entry_pw.setProperty("focused", is_focus)
                self.entry_pw.style().unpolish(self.entry_pw)
                self.entry_pw.style().polish(self.entry_pw)
        return super().eventFilter(obj, event)

    def _on_pw_change(self):
        pw = self.entry_pw.text()
        if self.error_box.isVisible():
            self.error_box.hide()
            self.info_box.show()
            self.lbl_title_pw.setText(tr("open.pw.title", "Enter Your Password"))
            self.sub_pw.setText(
                tr("open.pw.sub", "Enter the password you used when locking this vault.")
            )
        self.valid_state_changed.emit(bool(pw))

    # --- PUBLIC API ---
    def show_vault_meta(
        self, hint: str | None, has_recovery: bool, requires_keyfile: bool = False
    ) -> None:
        """Tampilkan hint (jika ada) & sesuaikan affordance recovery key / keyfile."""
        # Vault baru → mulai tanpa keyfile carry-over dari vault sebelumnya. Keyfile
        # bersifat vault-independent, tapi memakai pilihan vault lama bisa menampilkan
        # label basi atau diam-diam mengoper keyfile yang salah; user memilih ulang.
        self._clear_keyfile()
        self._vault_hint = (hint or "").strip() or None
        self._vault_has_recovery = bool(has_recovery)
        self._vault_requires_keyfile = bool(requires_keyfile)
        self._apply_meta()

    def clear_vault_meta(self) -> None:
        self._vault_hint = None
        self._vault_has_recovery = False
        self._vault_requires_keyfile = False
        self._clear_keyfile()
        self.hint_box.hide()
        self.keyfile_box.hide()
        self.entry_pw.setPlaceholderText(_placeholder_pw())

    def _clear_keyfile(self) -> None:
        self._keyfile_path = ""
        if hasattr(self, "lbl_keyfile"):
            self.lbl_keyfile.setText(tr("open.keyfile.none", "No keyfile selected"))

    def _apply_meta(self) -> None:
        if self._vault_hint:
            self.lbl_hint.setText(tr("open.pw.hint", "Hint: {hint}").format(hint=self._vault_hint))
            self.hint_box.show()
        else:
            self.hint_box.hide()
        self.keyfile_box.setVisible(self._vault_requires_keyfile)
        if self._vault_requires_keyfile:
            # Jangan menyarankan recovery key bila vault memang tak punya — menyesatkan.
            if self._vault_has_recovery:
                self.lbl_keyfile_note.setText(
                    tr(
                        "open.keyfile.note",
                        "This vault needs its keyfile. Select it, or use your recovery "
                        "key instead.",
                    )
                )
            else:
                self.lbl_keyfile_note.setText(
                    tr("open.keyfile.note.norecovery", "This vault needs its keyfile to open.")
                )
        self.entry_pw.setPlaceholderText(
            _placeholder_pw_recovery() if self._vault_has_recovery else _placeholder_pw()
        )

    def keyfile_path(self) -> str:
        """Path keyfile terpilih (atau '' bila tak ada). Hanya relevan untuk 2FA."""
        return self._keyfile_path

    def requires_keyfile(self) -> bool:
        """True bila vault terpilih butuh keyfile (slot password dilindungi 2FA)."""
        return self._vault_requires_keyfile

    def has_recovery(self) -> bool:
        """True bila vault terpilih punya recovery key (jalur break-glass tanpa keyfile)."""
        return self._vault_has_recovery

    def get_password(self) -> str:
        return self.entry_pw.text()

    def reset_field(self):
        self.entry_pw.blockSignals(True)
        self.entry_pw.clear()
        self.entry_pw.blockSignals(False)
        self.valid_state_changed.emit(False)

    def attach_return_event(self, slot_func):
        # Pakai submit_requested (dari eventFilter yang mengonsumsi Enter), BUKAN
        # returnPressed: returnPressed membiarkan event Enter merambat ke tombol CTA
        # dan memicu cancel begitu dekripsi dimulai. submit_requested + konsumsi event
        # memastikan Enter hanya memicu satu aksi buka.
        self.submit_requested.connect(slot_func)

    def set_idle_state(self) -> None:
        self.lbl_title_pw.setText(tr("open.pw.title", "Enter Your Password"))
        self.sub_pw.setText(
            tr("open.pw.sub", "Enter the password you used when locking this vault.")
        )
        self.entry_pw.show()
        self.entry_pw.setEnabled(True)
        self.status_box.hide()
        self.error_box.hide()
        self.info_box.show()
        self._apply_meta()

    def set_processing_state(self, file_name: str, size_text: str, stage: str) -> None:
        self.lbl_title_pw.setText(tr("open.pw.opening.title", "Opening Vault"))
        self.sub_pw.setText(tr("open.pw.opening.sub", "The vault is being verified and extracted."))
        self.entry_pw.hide()
        self.entry_pw.setEnabled(False)
        self.info_box.hide()
        self.error_box.hide()
        self.hint_box.hide()
        self.keyfile_box.hide()
        self.status_box.show()
        self.lbl_status_file.setText(file_name or "—")
        self.lbl_status_size.setText(size_text or "—")
        self.lbl_status_stage.setText(stage or tr("open.pw.status.preparing", "Preparing vault"))

    def update_processing_stage(self, stage: str) -> None:
        self.lbl_status_stage.setText(stage or tr("open.pw.status.processing", "Processing"))

    def set_error_state(self, message: str) -> None:
        self.lbl_title_pw.setText(tr("open.pw.failed.title", "Failed to Open Vault"))
        self.sub_pw.setText(
            tr("open.pw.failed.sub", "Wrong password, corrupted file, or unsupported format.")
        )
        self.entry_pw.show()
        self.entry_pw.setEnabled(True)
        self.status_box.hide()
        self.info_box.hide()
        self.error_box.show()
        self.lbl_error_msg.setText(message)
        self._apply_meta()  # hint tetap terlihat setelah password salah
        self.entry_pw.setFocus(Qt.FocusReason.OtherFocusReason)
