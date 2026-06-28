"""
Modul: settings_window.py
Deskripsi: Jendela Settings (frameless dialog) — Security (level KDF), Defaults,
           Privacy (clipboard/auto-lock), Appearance (tema/bahasa), About.

Membaca/menyimpan lewat ``settings_store`` dan dwibahasa lewat ``i18n`` (ganti
bahasa live untuk jendela ini).
"""

from __future__ import annotations

import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.constants import (
    KDF_LEVEL_INTERACTIVE,
    KDF_LEVEL_MODERATE,
    KDF_LEVEL_PARANOID,
)

from .i18n import i18n, tr
from .settings_store import get_settings
from .styles import (
    CLR_ACCENT,
    CLR_BORDER,
    CLR_CARD,
    CLR_HOVER_BG,
    CLR_INPUT_BORDER,
    CLR_INSET,
    CLR_LINE,
    CLR_LIST_SELECTED,
    CLR_ON_ACCENT,
    CLR_TEXT_DIM,
    CLR_TEXT_MAIN,
    CLR_WARN,
    CLR_WINDOW,
)
from .widgets import MethodCard, ToggleSwitch, apply_shadow


class SettingsWindow(QDialog):
    # Diminta saat user klik "Restart now" (tema baru diterapkan via restart).
    restart_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.s = get_settings()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)

        # Bahasa aktif mengikuti preferensi tersimpan.
        i18n().set_language(self.s.language())
        i18n().language_changed.connect(self._retranslate)

        self._build_ui()
        self._load_from_settings()
        self._retranslate()

    # ── Build ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Scrim gelap menutupi seluruh window induk; panel di tengahnya (overlay modal).
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._scrim = QFrame()
        self._scrim.setObjectName("SettingsScrim")
        self._scrim.setStyleSheet("QFrame#SettingsScrim { background: rgba(0, 0, 0, 0.5); }")
        self._scrim.mousePressEvent = self._scrim_clicked
        outer.addWidget(self._scrim)

        scrim_lay = QVBoxLayout(self._scrim)
        scrim_lay.setContentsMargins(24, 24, 24, 24)
        scrim_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.root = QFrame()
        self.root.setObjectName("SettingsRoot")
        self.root.setFixedWidth(560)
        self.root.setStyleSheet(
            f"QFrame#SettingsRoot {{ background:{CLR_WINDOW}; border:1px solid {CLR_LINE};"
            " border-radius:16px; }"
        )
        apply_shadow(self.root, blur_radius=40, y_offset=10, opacity=120)
        scrim_lay.addWidget(self.root, 0, Qt.AlignmentFlag.AlignCenter)

        root_lay = QVBoxLayout(self.root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        root_lay.addWidget(self._build_titlebar())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        scroll.setMinimumHeight(540)
        scroll.setMaximumHeight(640)

        body = QWidget()
        self.body_lay = QVBoxLayout(body)
        self.body_lay.setContentsMargins(16, 16, 16, 16)
        self.body_lay.setSpacing(14)
        self._build_sections()
        self.body_lay.addStretch(1)
        scroll.setWidget(body)
        root_lay.addWidget(scroll, 1)

        root_lay.addWidget(self._build_footer())

    def _build_titlebar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("SettingsTitlebar")
        bar.setFixedHeight(46)
        bar.setStyleSheet(
            f"QFrame#SettingsTitlebar {{ background:{CLR_INSET}; border-top-left-radius:16px;"
            f" border-top-right-radius:16px; border-bottom:1px solid {CLR_LINE}; }}"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 12, 0)
        lay.setSpacing(9)
        ic = QLabel()
        ic.setPixmap(qta.icon("mdi6.cog-outline", color=CLR_ACCENT).pixmap(18, 18))
        lay.addWidget(ic)
        self.lbl_title = QLabel("Settings")
        self.lbl_title.setStyleSheet(f"color:{CLR_TEXT_MAIN}; font-size:11pt; font-weight:700;")
        lay.addWidget(self.lbl_title)
        lay.addStretch()
        btn_close = QPushButton()
        btn_close.setIcon(qta.icon("mdi6.close", color=CLR_TEXT_DIM))
        btn_close.setObjectName("SettingsClose")
        btn_close.setFixedSize(30, 30)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(
            "QPushButton#SettingsClose { border:none; border-radius:8px; background:transparent; }"
            f" QPushButton#SettingsClose:hover {{ background:{CLR_HOVER_BG}; }}"
        )
        btn_close.clicked.connect(self.accept)
        lay.addWidget(btn_close)
        return bar

    def _build_sections(self):
        # ── Security ──
        sec, lay = self._section(
            "mdi6.shield-lock-outline",
            "settings.security",
            "Security",
            "settings.security.cap",
            "How your vaults are protected",
        )
        self.lbl_kdf = self._label("settings.kdf.label", "Encryption strength", main=True)
        self.lbl_kdf_desc = self._label(
            "settings.kdf.desc",
            "Argon2id key derivation — stronger is slower to unlock.",
        )
        head = QVBoxLayout()
        head.setSpacing(3)
        head.addWidget(self.lbl_kdf)
        head.addWidget(self.lbl_kdf_desc)
        lay.addLayout(head)

        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.card_interactive = MethodCard("mdi6.flash-outline", "Interactive", "")
        self.card_moderate = MethodCard("mdi6.scale-balance", "Moderate", "")
        self.card_paranoid = MethodCard("mdi6.shield-outline", "Paranoid", "")
        self._kdf_cards = {
            KDF_LEVEL_INTERACTIVE: self.card_interactive,
            KDF_LEVEL_MODERATE: self.card_moderate,
            KDF_LEVEL_PARANOID: self.card_paranoid,
        }
        for lvl, card in self._kdf_cards.items():
            cards.addWidget(card, 1)
            card.clicked.connect(lambda checked=False, level=lvl: self._select_kdf(level))
        lay.addLayout(cards)
        self.body_lay.addWidget(sec)

        # ── Defaults ──
        sec, lay = self._section(
            "mdi6.tune-variant",
            "settings.defaults",
            "Defaults",
            "settings.defaults.cap",
            "Pre-set options for the Lock tab",
        )
        self.sw_delete = ToggleSwitch(checked=False)
        self.lbl_delete = self._label(
            "settings.delete_original", "Delete original after locking", main=True
        )
        self.lbl_delete_desc = self._label("settings.delete_original.desc", "")
        lay.addLayout(self._row(self.lbl_delete, self.lbl_delete_desc, self.sw_delete))
        self.sw_wipe = ToggleSwitch(checked=False)
        self.lbl_wipe = self._label("settings.secure_wipe", "Secure wipe", main=True)
        self.lbl_wipe_desc = self._label(
            "settings.secure_wipe.desc", "Overwrite data before deleting (slower)."
        )
        lay.addLayout(self._row(self.lbl_wipe, self.lbl_wipe_desc, self.sw_wipe, divider=True))
        self.sw_delete.toggled.connect(self.s.set_delete_original)
        self.sw_wipe.toggled.connect(self.s.set_secure_wipe)
        self.body_lay.addWidget(sec)

        # ── Privacy ──
        sec, lay = self._section(
            "mdi6.eye-off-outline",
            "settings.privacy",
            "Privacy",
            "settings.privacy.cap",
            "Reduce traces left behind",
        )
        self.combo_clip = self._combo()
        self.lbl_clip = self._label("settings.clipboard", "Clipboard auto-clear", main=True)
        self.lbl_clip_desc = self._label(
            "settings.clipboard.desc", "Clear copied secrets after a delay."
        )
        lay.addLayout(self._row(self.lbl_clip, self.lbl_clip_desc, self.combo_clip))
        self.combo_clip.currentIndexChanged.connect(
            lambda *_: self.s.set_clipboard_seconds(int(self.combo_clip.currentData()))
        )

        self.sw_autolock = ToggleSwitch(checked=False)
        self.combo_minutes = self._combo(min_w=86)
        self.lbl_autolock = self._label("settings.auto_lock", "Auto-lock on idle", main=True)
        self.lbl_autolock_desc = self._label(
            "settings.auto_lock.desc", "Clear sensitive fields after inactivity."
        )
        right = QHBoxLayout()
        right.setSpacing(8)
        right.addWidget(self.combo_minutes)
        right.addWidget(self.sw_autolock)
        lay.addLayout(self._row(self.lbl_autolock, self.lbl_autolock_desc, right, divider=True))
        self.sw_autolock.toggled.connect(self._on_autolock_toggled)
        self.combo_minutes.currentIndexChanged.connect(
            lambda *_: self.s.set_auto_lock_minutes(int(self.combo_minutes.currentData()))
        )

        self.sw_recent = ToggleSwitch(checked=False)
        self.btn_clear_recent = QPushButton("Clear")
        self.btn_clear_recent.setObjectName("SettingsClearRecent")
        self.btn_clear_recent.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_recent.setStyleSheet(
            "QPushButton#SettingsClearRecent { border: none; background: transparent;"
            f" color: {CLR_TEXT_DIM}; font-size: 11px; }}"
            f" QPushButton#SettingsClearRecent:hover {{ color: {CLR_ACCENT}; }}"
        )
        self.btn_clear_recent.clicked.connect(self.s.clear_recent_vaults)
        self.lbl_recent = self._label("settings.recent", "Remember recent vaults", main=True)
        self.lbl_recent_desc = self._label(
            "settings.recent.desc",
            "Show recently locked or opened vaults for quick access.",
        )
        recent_ctrl = QHBoxLayout()
        recent_ctrl.setSpacing(8)
        recent_ctrl.addWidget(self.btn_clear_recent)
        recent_ctrl.addWidget(self.sw_recent)
        lay.addLayout(self._row(self.lbl_recent, self.lbl_recent_desc, recent_ctrl, divider=True))
        self.sw_recent.toggled.connect(self._on_recent_toggled)
        self.body_lay.addWidget(sec)

        # ── Notifications ──
        sec, lay = self._section(
            "mdi6.bell-outline",
            "settings.notifications",
            "Notifications",
            "settings.notifications.cap",
            "Alerts from the app",
        )
        self.sw_tray_notif = ToggleSwitch(checked=True)
        self.lbl_tray_notif = self._label(
            "settings.tray_notif", "Notify when minimized to tray", main=True
        )
        self.lbl_tray_notif_desc = self._label(
            "settings.tray_notif.desc",
            "Show a notification when the window hides to the system tray.",
        )
        lay.addLayout(self._row(self.lbl_tray_notif, self.lbl_tray_notif_desc, self.sw_tray_notif))
        self.sw_tray_notif.toggled.connect(self.s.set_tray_notif)
        self.body_lay.addWidget(sec)

        # ── Appearance ──
        sec, lay = self._section(
            "mdi6.palette-outline",
            "settings.appearance",
            "Appearance",
            "settings.appearance.cap",
            "Look and language",
        )
        self.combo_theme = self._combo()
        self.lbl_theme = self._label("settings.theme", "Theme", main=True)
        self.lbl_theme_desc = self._label(
            "settings.theme.desc", "Dark, Light, or follow your system."
        )
        lay.addLayout(self._row(self.lbl_theme, self.lbl_theme_desc, self.combo_theme))
        # Hint + tombol restart: tema diresolusi saat startup (banyak warna di-bake
        # saat build widget/ikon), jadi tema baru berlaku setelah app dibuka ulang.
        # Tombol "Restart now" menjadikannya sekali klik. Kotak ini hanya muncul saat
        # tema terpilih beda dari yang sedang aktif.
        self.theme_restart_box = QWidget()
        rr = QHBoxLayout(self.theme_restart_box)
        rr.setContentsMargins(0, 4, 0, 0)
        rr.setSpacing(10)
        self.lbl_theme_restart = self._label(
            "settings.theme.restart", "Restart to apply the new theme."
        )
        self.lbl_theme_restart.setStyleSheet(
            f"color: {CLR_WARN}; font-size: 11px; font-weight: 600; border:none;"
        )
        rr.addWidget(self.lbl_theme_restart, 1)
        self.btn_restart = QPushButton(tr("settings.theme.restart_btn", "Restart now"))
        self.btn_restart.setObjectName("BtnInlinePrimary")
        self.btn_restart.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_restart.clicked.connect(lambda: self.restart_requested.emit())
        rr.addWidget(self.btn_restart, 0)
        self.theme_restart_box.setVisible(False)
        lay.addWidget(self.theme_restart_box)
        self.combo_theme.currentIndexChanged.connect(self._on_theme_changed)

        self.combo_lang = self._combo()
        self.lbl_lang = self._label("settings.language", "Language", main=True)
        self.lbl_lang_desc = self._label("settings.language.desc", "Interface language.")
        lay.addLayout(self._row(self.lbl_lang, self.lbl_lang_desc, self.combo_lang, divider=True))
        self.combo_lang.currentIndexChanged.connect(self._on_language_changed)
        self.body_lay.addWidget(sec)

        # ── About ──
        sec, lay = self._section(
            "mdi6.information-outline",
            "settings.about",
            "About",
            "settings.about.cap",
            "Local AES-256-GCM + Argon2id encryption",
        )
        name = QLabel("Adyton Crypt")
        name.setStyleSheet(f"color:{CLR_TEXT_MAIN}; font-size:12.5px; font-weight:600;")
        self.lbl_about_build = self._label("settings.about.build", "Pre-release build.")
        col = QVBoxLayout()
        col.setSpacing(3)
        col.addWidget(name)
        col.addWidget(self.lbl_about_build)
        ver = QLabel("v1.0")
        ver.setStyleSheet(
            f"color:{CLR_TEXT_DIM}; font-family:'JetBrains Mono',monospace; font-size:10px;"
            f" background:{CLR_INSET}; border:1px solid {CLR_BORDER}; border-radius:8px; padding:5px 10px;"
        )
        about_row = QHBoxLayout()
        about_row.addLayout(col, 1)
        about_row.addWidget(ver, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(about_row)
        self.body_lay.addWidget(sec)

    def _build_footer(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("SettingsFooter")
        bar.setStyleSheet(
            f"QFrame#SettingsFooter {{ background:{CLR_INSET}; border-top:1px solid {CLR_LINE};"
            " border-bottom-left-radius:16px; border-bottom-right-radius:16px; }"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 12, 16, 12)
        self.btn_reset = QPushButton("Reset to defaults")
        self.btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset.setStyleSheet(
            f"QPushButton {{ border:none; background:transparent; color:{CLR_TEXT_DIM}; font-size:12px; }}"
            f" QPushButton:hover {{ color:{CLR_WARN}; }}"
        )
        self.btn_reset.clicked.connect(self._on_reset)
        self.btn_done = QPushButton("Done")
        self.btn_done.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_done.setStyleSheet(
            f"QPushButton {{ background:{CLR_ACCENT}; color:{CLR_ON_ACCENT}; font-size:12.5px;"
            " font-weight:700; border:none; border-radius:10px; padding:9px 22px; }"
        )
        self.btn_done.clicked.connect(self.accept)
        lay.addWidget(self.btn_reset)
        lay.addStretch()
        lay.addWidget(self.btn_done)
        return bar

    # ── Small builders ─────────────────────────────────────────────────────
    def _section(self, icon, title_key, title_def, cap_key, cap_def):
        # Selektor di-scope ke objectName agar border/radius TIDAK menetes ke child
        # QFrame (mis. ToggleSwitch) — penyebab toggle ber-border sebelumnya.
        card = QFrame()
        card.setObjectName("SettingsCard")
        card.setStyleSheet(
            f"QFrame#SettingsCard {{ background:{CLR_CARD}; border:1px solid {CLR_BORDER};"
            " border-radius:16px; }"
        )
        outer = QVBoxLayout(card)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(10)
        box = QFrame()
        box.setObjectName("SettingsSecIcon")
        box.setFixedSize(30, 30)
        box.setStyleSheet(
            f"QFrame#SettingsSecIcon {{ background:{CLR_INSET}; border:1px solid {CLR_BORDER};"
            " border-radius:9px; }"
        )
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        il = QLabel()
        il.setPixmap(qta.icon(icon, color=CLR_ACCENT).pixmap(16, 16))
        il.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bl.addWidget(il)
        head.addWidget(box)
        tcol = QVBoxLayout()
        tcol.setSpacing(1)
        t = self._label(title_key, title_def, main=True)
        c = self._label(cap_key, cap_def)
        tcol.addWidget(t)
        tcol.addWidget(c)
        head.addLayout(tcol, 1)
        outer.addLayout(head)
        outer.addSpacing(2)
        return card, outer

    def _label(self, key, default, main=False) -> QLabel:
        lbl = QLabel(default)
        lbl.setWordWrap(True)
        if main:
            lbl.setStyleSheet(
                f"color:{CLR_TEXT_MAIN}; font-size:12.5px; font-weight:600; border:none;"
            )
        else:
            lbl.setStyleSheet(f"color:{CLR_TEXT_DIM}; font-size:11px; border:none;")
        lbl._i18n = (key, default)
        return lbl

    def _row(self, lbl, desc, control, divider=False) -> QVBoxLayout:
        wrap = QVBoxLayout()
        wrap.setSpacing(0)
        if divider:
            line = QFrame()
            line.setFixedHeight(1)
            line.setStyleSheet(f"background:{CLR_LINE}; border:none;")
            wrap.addWidget(line)
            wrap.addSpacing(11)
        row = QHBoxLayout()
        row.setSpacing(16)
        col = QVBoxLayout()
        col.setSpacing(3)
        col.addWidget(lbl)
        col.addWidget(desc)
        row.addLayout(col, 1)
        if isinstance(control, QHBoxLayout):
            row.addLayout(control, 0)
        else:
            row.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        wrap.addLayout(row)
        if not divider:
            wrap.addSpacing(11)
        return wrap

    def _combo(self, min_w: int = 138) -> QComboBox:
        cb = QComboBox()
        cb.setCursor(Qt.CursorShape.PointingHandCursor)
        cb.setStyleSheet(
            f"QComboBox {{ background:{CLR_INSET}; border:1px solid {CLR_INPUT_BORDER};"
            f" border-radius:10px; padding:7px 12px; color:{CLR_TEXT_MAIN}; min-width:{min_w}px; }}"
            " QComboBox::drop-down { border:none; width:22px; }"
            # Popup: padding di dalam frame + tiap item dipadatkan (padding & sudut
            # membulat). Highlight yang mengikuti mouse (hover) di popup QComboBox pakai
            # mekanisme *selection* → selection-background-color WAJIB diisi (jangan
            # transparent, atau hover hilang); ::item:hover ditambah utk berjaga-jaga.
            # selection-color WAJIB diset juga: default Qt = putih (HighlightedText) →
            # di light theme teks item terpilih jadi putih nyaris tak terbaca di atas
            # highlight terang. Samakan dgn teks normal agar tetap terbaca.
            f" QComboBox QAbstractItemView {{ background:{CLR_CARD}; border:1px solid {CLR_BORDER};"
            f" border-radius:10px; padding:4px; selection-background-color:{CLR_LIST_SELECTED};"
            f" selection-color:{CLR_TEXT_MAIN}; color:{CLR_TEXT_MAIN}; outline:none; }}"
            " QComboBox QAbstractItemView::item { padding:7px 10px; border-radius:7px;"
            " min-height:18px; }"
            f" QComboBox QAbstractItemView::item:hover {{ background:{CLR_LIST_SELECTED}; }}"
        )
        # Jarak nyata antar-item (gap) — andal di semua platform; QSS ::item margin
        # sering diabaikan oleh view popup QComboBox.
        cb.view().setSpacing(2)
        return cb

    # ── State <-> settings ─────────────────────────────────────────────────
    def _select_kdf(self, level: str):
        for lvl, card in self._kdf_cards.items():
            card.set_selected(lvl == level)
        self.s.set_kdf_level(level)

    def _on_autolock_toggled(self, on: bool):
        self.s.set_auto_lock_enabled(on)
        self.combo_minutes.setVisible(on)

    def _on_recent_toggled(self, on: bool):
        self.s.set_recent_enabled(on)
        self.btn_clear_recent.setVisible(on)

    def _on_language_changed(self, *_):
        lang = str(self.combo_lang.currentData())
        self.s.set_language(lang)
        i18n().set_language(lang)  # memicu _retranslate lewat sinyal

    def _on_theme_changed(self, *_):
        pref = str(self.combo_theme.currentData())
        self.s.set_theme(pref)
        self._update_theme_restart_box()

    def _update_theme_restart_box(self) -> None:
        """Tampilkan kotak "Restart now" bila tema TERSIMPAN beda dari yang aktif.

        Dihitung dari preferensi tersimpan (bukan hanya saat combo berubah) agar saat
        Settings dibuka ulang dengan perubahan tema yang belum di-restart, user tetap
        melihat — dan bisa memakai — tombol Restart. Tema diresolusi sekali saat startup
        (lihat ui/styles.py), jadi perubahannya baru berlaku setelah app dibuka ulang.
        """
        import ui.styles as styles

        needs_restart = styles.resolve_theme(self.s.theme()) != styles.ACTIVE_THEME
        self.theme_restart_box.setVisible(needs_restart)

    def _on_reset(self):
        self.s.reset_to_defaults()
        self._load_from_settings()
        i18n().set_language(self.s.language())
        self._retranslate()

    def _load_from_settings(self):
        self._select_kdf(self.s.kdf_level())
        self.sw_delete.setChecked(self.s.delete_original())
        self.sw_wipe.setChecked(self.s.secure_wipe())

        self._fill_combo(
            self.combo_clip,
            [(0, None), (15, None), (30, None), (60, None)],
            self.s.clipboard_seconds(),
        )
        self.sw_autolock.setChecked(self.s.auto_lock_enabled())
        self._fill_combo(
            self.combo_minutes, [(1, None), (5, None), (15, None)], self.s.auto_lock_minutes()
        )
        self.combo_minutes.setVisible(self.s.auto_lock_enabled())
        self.sw_recent.setChecked(self.s.recent_enabled())
        self.btn_clear_recent.setVisible(self.s.recent_enabled())
        self.sw_tray_notif.setChecked(self.s.tray_notif())
        self._fill_combo(
            self.combo_theme,
            [("dark", "Dark"), ("light", "Light"), ("system", "System")],
            self.s.theme(),
        )
        self._fill_combo(
            self.combo_lang, [("en", "English"), ("id", "Indonesia")], self.s.language()
        )
        # Pending theme change (dipilih tapi belum restart) harus tetap menampilkan
        # kotak Restart saat Settings dibuka ulang — lihat _update_theme_restart_box.
        self._update_theme_restart_box()

    def _fill_combo(self, cb: QComboBox, items, current):
        cb.blockSignals(True)
        cb.clear()
        for value, label in items:
            cb.addItem(label if label is not None else str(value), value)
        idx = cb.findData(current)
        cb.setCurrentIndex(idx if idx >= 0 else 0)
        cb.blockSignals(False)

    # ── i18n ────────────────────────────────────────────────────────────────
    def _retranslate(self, *_):
        self.setWindowTitle(tr("settings.title", "Settings"))
        self.lbl_title.setText(tr("settings.title", "Settings"))
        for lbl in self.findChildren(QLabel):
            meta = getattr(lbl, "_i18n", None)
            if meta:
                lbl.setText(tr(meta[0], meta[1]))
        self.btn_restart.setText(tr("settings.theme.restart_btn", "Restart now"))
        self.card_interactive.set_texts(
            tr("settings.kdf.interactive", "Interactive"),
            tr("settings.kdf.interactive.desc", "Fastest unlock. Everyday use."),
        )
        self.card_moderate.set_texts(
            tr("settings.kdf.moderate", "Moderate"),
            tr("settings.kdf.moderate.desc", "Balanced security and speed."),
        )
        self.card_paranoid.set_texts(
            tr("settings.kdf.paranoid", "Paranoid"),
            tr("settings.kdf.paranoid.desc", "Maximum hardness. Slower."),
        )
        # Delete-original desc memuat penegasan "Destructive" berwarna warn.
        self.lbl_delete_desc.setText(
            tr("settings.delete_original.desc", "Removes the source once the vault is verified.")
            + f"  <span style='color:{CLR_WARN}'>"
            + tr("settings.destructive", "Destructive.")
            + "</span>"
        )
        # Combo dengan label dinamis (detik/menit) — pertahankan nilai terpilih.
        secs = int(self.combo_clip.currentData() or 0)
        self._fill_combo(
            self.combo_clip,
            [
                (
                    v,
                    tr("settings.off", "Off")
                    if v == 0
                    else tr("settings.seconds", "{n} seconds").format(n=v),
                )
                for v in (0, 15, 30, 60)
            ],
            secs,
        )
        mins = int(self.combo_minutes.currentData() or 1)
        self._fill_combo(
            self.combo_minutes,
            [(v, tr("settings.minutes", "{n} min").format(n=v)) for v in (1, 5, 15)],
            mins,
        )
        self._fill_combo(
            self.combo_theme,
            [
                ("dark", tr("settings.theme.dark", "Dark")),
                ("light", tr("settings.theme.light", "Light")),
                ("system", tr("settings.theme.system", "System")),
            ],
            self.s.theme(),
        )
        self.btn_clear_recent.setText(tr("settings.recent.clear", "Clear"))
        self.btn_reset.setText(tr("settings.reset", "Reset to defaults"))
        self.btn_done.setText(tr("settings.done", "Done"))

    # ── Overlay geometry & scrim ──────────────────────────────────────────────
    def showEvent(self, event):
        super().showEvent(event)
        # Tutupi seluruh window induk agar scrim meredupkan app & panel ter-center.
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.window().geometry())

    def _scrim_clicked(self, event):
        # Klik di area gelap (di luar panel) menutup Settings; klik di panel diabaikan.
        if not self.root.geometry().contains(event.position().toPoint()):
            self.accept()
