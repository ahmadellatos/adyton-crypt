"""
Modul: widgets.py
Deskripsi: Kumpulan komponen UI (Widget) kustom yang reusable.
"""

import qtawesome as qta
from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.paths import get_asset_path

from .styles import (
    CLR_ACCENT,
    CLR_ACCENT_HOVER,
    CLR_BORDER,
    CLR_DANGER,
    CLR_DANGER_BG,
    CLR_HOVER_BG,
    CLR_INPUT_BORDER,
    CLR_INSET,
    CLR_PANEL_SOFT,
    CLR_SUCCESS,
    CLR_SUCCESS_BG,
    CLR_TEXT_DIM,
    CLR_TEXT_MAIN,
    CLR_TEXT_MUTED,
    CLR_TOGGLE_OFF,
    CLR_WARN,
    CLR_WARN_BG,
    CLR_WINDOW,
    accent_color,
    overlay_color,
)
from .utils import apply_shadow

# ── SHARED BUILDERS ─────────────────────────────────────────────────


def make_generator_button() -> QPushButton:
    """Tombol "Generator" standar (dipakai panel password Kunci & Teks)."""
    from .i18n import register

    btn = QPushButton()
    register(btn, "generator", " Generator")
    btn.setIcon(qta.icon("mdi6.creation", color=CLR_TEXT_MAIN))
    btn.setFixedHeight(36)
    btn.setObjectName("BtnGen")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    register(btn, "a11y.gen_password", "Generate Strong Password", "setAccessibleName")
    return btn


class MethodCard(QAbstractButton):
    """Kartu pilihan metode (radio-card) — perilaku & a11y setara segmented control.

    Dipakai bersama di Tab Manage, panel recovery Tab Lock, dan pemilih KDF di
    Settings agar pemilih metode tampil & berperilaku konsisten.

    Berbasis ``QAbstractButton`` (bukan QFrame) agar Qt otomatis mengekspos state
    *checked* ke screen reader dan menangani fokus/keyboard secara native — persis
    seperti tombol segmented (QPushButton checkable) di Tab Manage: role a11y
    ``CheckBox`` + state checked, tiap kartu satu tab-stop, Space/Enter memilih.

    ``checkable`` mengekspos state-nya; ``nextCheckState`` di-override agar kartu
    aktif tak bisa di-uncheck (perilaku eksklusif). Pemilihan eksklusif antar
    kartu (mematikan yang lain) tetap diatur handler parent — sama seperti
    sebelumnya — sehingga tak butuh QButtonGroup di tiap call-site.
    """

    def __init__(self, icon_name: str, title: str, desc: str, parent=None):
        super().__init__(parent)
        self.setObjectName("MethodCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Checkable → state checked terekspos a11y (role CheckBox, seperti segmented).
        self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # QAbstractButton default vertikalnya Fixed → tiap kartu pakai tinggi
        # sendiri (jadi tinggi sebelah saat deskripsi wrap beda). Samakan dengan
        # QFrame (Preferred) agar row menyetarakan tinggi kedua kartu.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setAccessibleName(title)
        self._icon_name = icon_name

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self._icon = QLabel()
        top.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        top.addStretch()
        self._indicator = QLabel()
        top.addWidget(self._indicator, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        lay.addLayout(top)

        self._title = QLabel(title)
        self._title.setObjectName("SectionLabel")
        lay.addWidget(self._title)

        self._desc = QLabel(desc)
        self._desc.setObjectName("OptionDesc")
        self._desc.setWordWrap(True)
        lay.addWidget(self._desc)
        lay.addStretch(1)

        # Klik di mana pun pada kartu mengenai tombol, bukan label anak.
        for w in (self._icon, self._indicator, self._title, self._desc):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        # Visual mengikuti state checked (klik native / setChecked sama-sama jalan).
        self.toggled.connect(self._render)
        self._render(False)

    def _render(self, checked: bool):
        # Background/border kartu digambar di paintEvent (QAbstractButton.paintEvent
        # pure-virtual, jadi stylesheet bg tak otomatis tergambar). Di sini cukup
        # perbarui ikon + indikator lalu minta repaint.
        self._icon.setPixmap(
            qta.icon(self._icon_name, color=CLR_ACCENT if checked else CLR_TEXT_MUTED).pixmap(
                20, 20
            )
        )
        self._indicator.setPixmap(
            qta.icon(
                "mdi6.check-circle" if checked else "mdi6.circle-outline",
                color=CLR_ACCENT if checked else CLR_TEXT_MUTED,
            ).pixmap(18, 18)
        )
        self.update()

    # ── API kompatibel (dipakai call-site lama) ──────────────────────────────
    def set_selected(self, selected: bool):
        self.setChecked(selected)

    def is_selected(self) -> bool:
        return self.isChecked()

    def set_texts(self, title: str, desc: str) -> None:
        """Perbarui judul + deskripsi (dipakai saat ganti bahasa)."""
        self._title.setText(title)
        self._desc.setText(desc)
        self.setAccessibleName(title)

    def tr_set(self, title_key: str, title_def: str, desc_key: str, desc_def: str) -> None:
        """Daftarkan judul/deskripsi untuk i18n live (lewat tree-walk retranslate)."""
        from .i18n import register

        register(self._title, title_key, title_def)
        register(self._desc, desc_key, desc_def)
        # Nama aksesibilitas kartu = judulnya, ikut bahasa.
        register(self, title_key, title_def, "setAccessibleName")

    def nextCheckState(self):
        # Kartu aktif tak boleh di-uncheck sendiri (perilaku eksklusif, seperti
        # grup segmented). Klik/Space pada kartu non-aktif → jadi aktif; pada
        # kartu aktif → tetap aktif. Mematikan kartu lain diurus handler parent.
        if not self.isChecked():
            self.setChecked(True)

    def keyPressEvent(self, event):
        # Space sudah ditangani QAbstractButton secara native; tambahkan Enter.
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
            event.accept()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        # QAbstractButton.paintEvent pure-virtual → gambar sendiri seluruhnya
        # (jangan panggil super()). Background + border mengikuti state checked.
        checked = self.isChecked()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        bg = accent_color(26) if checked else overlay_color(5)
        painter.setBrush(bg)
        painter.setPen(QPen(QColor(CLR_ACCENT if checked else CLR_BORDER), 1.5))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 11, 11)

        # Cincin fokus keyboard di dalam border, warna teks utama agar jelas beda
        # dari border aksen penanda "selected". Properti kbFocus diset oleh
        # _FocusRingFilter hanya saat navigasi keyboard (bukan klik mouse).
        if self.property("kbFocus"):
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(CLR_TEXT_MAIN), 1.5))
            painter.drawRoundedRect(self.rect().adjusted(3, 3, -3, -3), 9, 9)


def make_recovery_info_box(
    text: str = "Keep your recovery key somewhere safe — you'll need it to get back in.",
) -> QFrame:
    """Kotak info recovery (ikon + teks, nada netral).

    Satu baris yang berlaku untuk kedua metode (kode & passphrase); penjelasan
    "apa itu recovery" sudah ada di subtitle toggle + deskripsi tiap kartu.
    """
    box = QFrame()
    box.setObjectName("RecoveryInfoBox")
    box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    box.setStyleSheet(
        f"QFrame#RecoveryInfoBox {{ background: {CLR_PANEL_SOFT};"
        f" border: 1px solid {CLR_BORDER}; border-radius: 10px; }}"
    )
    lay = QHBoxLayout(box)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(10)
    icon = QLabel()
    icon.setPixmap(qta.icon("mdi6.information-outline", color=CLR_ACCENT).pixmap(16, 16))
    lay.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
    from .i18n import register

    txt = QLabel()
    txt.setObjectName("OptionDesc")
    txt.setWordWrap(True)
    register(txt, "recovery.infobox", text)
    lay.addWidget(txt, 1)
    return box


def build_card_header(
    icon_name: str,
    icon_color: str,
    title: str,
    subtitle: str,
    button: QPushButton | None = None,
    *,
    spacing: int = 10,
):
    """Header kartu standar: ikon 32px + CardTitle + CardSubtitle (+ tombol kanan).

    Mengembalikan (layout, title_label, subtitle_label). `button` opsional dipasang
    rata-kanan & top-aligned; caller tetap memegang referensinya.
    """
    row = QHBoxLayout()
    row.setSpacing(spacing)

    icon = QLabel()
    icon.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(32, 32))
    icon.setAlignment(Qt.AlignmentFlag.AlignTop)

    v = QVBoxLayout()
    v.setSpacing(3)
    lbl_title = QLabel(title)
    lbl_title.setObjectName("CardTitle")
    lbl_sub = QLabel(subtitle)
    lbl_sub.setObjectName("CardSubtitle")
    lbl_sub.setWordWrap(True)
    v.addWidget(lbl_title)
    v.addWidget(lbl_sub)

    row.addWidget(icon)
    row.addLayout(v, 1)
    if button is not None:
        row.addSpacing(8)
        row.addWidget(button, alignment=Qt.AlignmentFlag.AlignTop)
    return row, lbl_title, lbl_sub


def build_tips_box(
    tips: list[tuple[str, str, str, str]],
    *,
    content_margins: tuple[int, int, int, int] = (14, 10, 14, 10),
    spacing: int = 7,
    icon_px: int = 14,
    row_spacing: int = 8,
) -> QFrame:
    """Kotak tips standar (#TipsBox). `tips` = list of (icon_name, color, key, default).

    Tiap baris teks didaftarkan via ``register`` sehingga ikut ter-retranslate
    saat bahasa berganti live.
    """
    from .i18n import register

    box = QFrame()
    box.setObjectName("TipsBox")
    lay = QVBoxLayout(box)
    lay.setContentsMargins(*content_margins)
    lay.setSpacing(spacing)

    for icon_name, color, key, default in tips:
        row = QHBoxLayout()
        row.setSpacing(row_spacing)
        lbl_ic = QLabel()
        lbl_ic.setPixmap(qta.icon(icon_name, color=color).pixmap(icon_px, icon_px))
        lbl_ic.setFixedSize(icon_px, icon_px)
        row.addWidget(lbl_ic, alignment=Qt.AlignmentFlag.AlignTop)
        lbl_tx = QLabel()
        register(lbl_tx, key, default)
        lbl_tx.setWordWrap(True)
        lbl_tx.setObjectName("TipText")
        row.addWidget(lbl_tx, 1)
        lay.addLayout(row)

    return box


# ── MODAL SCRIM ─────────────────────────────────────────────────────
class ScrimDialogMixin:
    """Mixin untuk QDialog frameless modal: meredupkan window induk dengan
    scrim gelap selama dialog terbuka.

    Scrim adalah child dari top-level window induk, di-raise ke atas sehingga
    menutupi konten induk tapi tetap DI BAWAH dialog (window terpisah di atasnya,
    persis seperti pola overlay di SettingsWindow). Panggil ``_show_modal_scrim``
    dari ``showEvent`` dan ``_hide_modal_scrim`` dari ``hideEvent``.
    """

    _SCRIM_COLOR = "rgba(0, 0, 0, 0.45)"

    def _scrim_host(self):
        parent = getattr(self, "parent_widget", None) or self.parentWidget()
        if parent is None:
            return None
        win = parent.window()
        return win if win is not None and win.isVisible() else None

    def _show_modal_scrim(self) -> None:
        host = self._scrim_host()
        if host is None:
            return
        self._hide_modal_scrim()  # jaga-jaga: jangan menumpuk scrim
        scrim = QFrame(host)
        scrim.setObjectName("ModalScrim")
        scrim.setStyleSheet(f"QFrame#ModalScrim {{ background: {self._SCRIM_COLOR}; }}")
        scrim.setGeometry(host.rect())
        scrim.raise_()
        scrim.show()
        self._modal_scrim = scrim

    def _hide_modal_scrim(self) -> None:
        scrim = getattr(self, "_modal_scrim", None)
        if scrim is not None:
            scrim.hide()
            scrim.deleteLater()
            self._modal_scrim = None


# ── DRAG-DROP FRAME ─────────────────────────────────────────────────
class DragDropFrame(QFrame):
    """Area drop file standar (#DropArea), diparametrikan untuk dua mode.

    - Tab Kunci: ``multi=True`` — terima semua path yang lolos ``accept``.
    - Tab Buka:  ``multi=False`` — ambil item pertama yang lolos ``accept``
      (mis. hanya ``.adtn``).

    Set ``on_drop`` ke ``callable(list[str])`` (untuk single-mode list selalu 1
    item). ``drag_state_changed(bool)`` dipancarkan saat drag masuk/keluar dan
    boleh diabaikan oleh pemanggil yang tak memerlukannya.
    """

    drag_state_changed = Signal(bool)

    def __init__(self, parent=None, *, multi: bool = True, accept=None):
        super().__init__(parent)
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)
        self._multi = multi
        self._accept = accept  # callable(path)->bool, atau None = terima non-kosong
        self.on_drop = None  # callable(list[str])
        self.setProperty("empty", True)

    def set_empty_state(self, is_empty: bool):
        """Set state kosong via property (stylesheet global yang menanganinya)."""
        self.setProperty("empty", is_empty)
        self.style().unpolish(self)
        self.style().polish(self)

    def _set_drag_state(self, state: bool):
        self.setProperty("dragActive", state)
        self.style().unpolish(self)
        self.style().polish(self)
        self.drag_state_changed.emit(state)

    def _accepts(self, path: str) -> bool:
        if self._accept is not None:
            return self._accept(path)
        return bool(path)

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if any(self._accepts(u.toLocalFile()) for u in urls):
            self._set_drag_state(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._set_drag_state(False)

    def _selected_paths(self, local_files: list[str]) -> list[str]:
        """Saring lewat `accept` dan batasi sesuai `multi`. Dipisah agar mudah diuji."""
        accepted = [p for p in local_files if self._accepts(p)]
        if not accepted:
            return []
        return accepted if self._multi else accepted[:1]

    def dropEvent(self, event):
        self._set_drag_state(False)
        paths = self._selected_paths([u.toLocalFile() for u in event.mimeData().urls()])
        if paths and self.on_drop:
            self.on_drop(paths)


# ── HERO ICON WIDGET (FOLDER GLOWING) ───────────────────────────────
class HeroIconWidget(QWidget):
    """Ikon hero drop zone — tenang & minimal (folder kalem + shield aksen).

    Sesuai design system: tanpa glow/halo neon. Saat drag aktif, ikon shield
    hanya dinaikkan ke aksen hover dengan bayangan aksen yang sangat halus.
    """

    def __init__(self, mode="kunci", parent=None):
        super().__init__(parent)
        self.setFixedSize(160, 110)

        lbl_folder = QLabel(self)
        lbl_folder.setPixmap(qta.icon("mdi6.folder-outline", color=CLR_INPUT_BORDER).pixmap(90, 90))
        lbl_folder.setGeometry(35, 10, 90, 90)
        lbl_folder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_overlay = QLabel(self)
        icon_name = "mdi6.shield-outline" if mode == "kunci" else "mdi6.shield-check-outline"

        self._overlay_icon_name = icon_name
        lbl_overlay.setPixmap(qta.icon(icon_name, color=CLR_ACCENT).pixmap(36, 36))
        lbl_overlay.setGeometry(62, 42, 36, 36)
        lbl_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._overlay_icon = lbl_overlay
        # Bayangan halus (bukan glow) — sangat samar saat idle.
        self._glow_overlay = QGraphicsDropShadowEffect(self)
        self._glow_overlay.setBlurRadius(0)
        self._glow_overlay.setColor(QColor(79, 191, 201, 0))
        self._glow_overlay.setXOffset(0)
        self._glow_overlay.setYOffset(0)
        lbl_overlay.setGraphicsEffect(self._glow_overlay)

    def set_drag_active(self, active: bool):
        """Beri penekanan halus saat drag aktif — tetap kalem, tanpa neon."""
        if active:
            self._glow_overlay.setBlurRadius(22)
            self._glow_overlay.setColor(QColor(79, 191, 201, 150))
            self._overlay_icon.setPixmap(
                qta.icon(self._overlay_icon_name, color=CLR_ACCENT_HOVER).pixmap(36, 36)
            )
        else:
            self._glow_overlay.setBlurRadius(0)
            self._glow_overlay.setColor(QColor(79, 191, 201, 0))
            self._overlay_icon.setPixmap(
                qta.icon(self._overlay_icon_name, color=CLR_ACCENT).pixmap(36, 36)
            )
        self.update()


# ── CUSTOM TOOLTIP ──────────────────────────────────────────────────
class CustomToolTip(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        # Gaya diambil dari QSS global (selektor `QToolTip, QLabel#CustomToolTip`)
        # supaya tooltip path (widget kustom ini) IDENTIK dengan tooltip native —
        # satu sumber kebenaran, tak ada style inline yang bisa melenceng.
        self.setObjectName("CustomToolTip")
        self.hide()

        # Timer tunggal untuk polling pergerakan mouse setiap 50ms
        self._monitor_timer = QTimer(self)
        self._monitor_timer.setInterval(50)
        self._monitor_timer.timeout.connect(self._check_mouse_state)

        self._pending_text = ""
        self._last_cursor_pos = QPoint()
        self._time_hovered = 0

        # Standar durasi UX OS Native
        self._show_delay_ms = 1000  # Nongol setelah mouse diam 1 detik
        self._hide_delay_ms = 5000  # Hilang otomatis setelah 5 detik (jika tidak gerak)

    def show_now(self, text):
        """Tampilkan SEGERA (dipakai filter tooltip global, setelah delay native Qt).

        Qt sudah menerapkan delay hover-nya, jadi tooltip langsung tampil. Timer
        tetap jalan untuk sembunyi-saat-gerak & auto-hide. Idempotent bila teks
        sama & sudah tampil.
        """
        if self.isVisible() and text == self._pending_text:
            return
        self._pending_text = text
        self._last_cursor_pos = QCursor.pos()
        self._do_show()
        self._time_hovered = self._show_delay_ms  # lewati gerbang 'show delay'
        self._monitor_timer.start()

    def _check_mouse_state(self):
        current_pos = QCursor.pos()

        # Hitung jarak pergerakan mouse dari posisi terakhir (Toleransi 5 pixel/anti-jitter)
        diff = current_pos - self._last_cursor_pos
        distance_sq = diff.x() ** 2 + diff.y() ** 2

        if distance_sq > 25:  # Jika mouse bergerak lebih dari ~5 px
            self._last_cursor_pos = current_pos
            self._time_hovered = 0  # Reset timer!
            if self.isVisible():
                self.hide()  # Langsung sembunyikan jika user gerak
        else:
            # Jika mouse terpantau diam, teruskan hitungan
            self._time_hovered += 50

            # Waktunya tampilkan
            if self._time_hovered == self._show_delay_ms and not self.isVisible():
                self._do_show()
            # Waktunya autohide (expired)
            elif (
                self._time_hovered >= (self._show_delay_ms + self._hide_delay_ms)
                and self.isVisible()
            ):
                self.hide_tooltip()

    def _do_show(self):
        self.setText(self._pending_text)
        self.adjustSize()
        pos = QCursor.pos()

        # Clamp to screen to avoid tooltip going off-screen
        screen = QGuiApplication.screenAt(pos)
        if screen:
            geom = screen.availableGeometry()
            x = pos.x() + 15
            y = pos.y() + 15

            if x + self.width() > geom.right():
                x = pos.x() - self.width() - 5
            if y + self.height() > geom.bottom():
                y = pos.y() - self.height() - 5

            self.move(max(geom.left(), x), max(geom.top(), y))
        else:
            self.move(pos.x() + 15, pos.y() + 15)

        self.show()

    def hide_tooltip(self):
        self._monitor_timer.stop()
        self.hide()


# ── ELIDED LABEL (Pemotong Teks ...) ────────────────────────────────
class ElidedLabel(QLabel):
    def __init__(self, text="", mode=Qt.TextElideMode.ElideMiddle, parent=None):
        super().__init__(text, parent)
        self._full_text = text
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(10)

    def setText(self, text):
        self._full_text = text
        self._update_elided_text()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elided_text()

    def _update_elided_text(self):
        metrics = self.fontMetrics()
        elided = metrics.elidedText(self._full_text, self._mode, max(10, self.width() - 5))
        if self.text() != elided:
            super().setText(elided)

    def minimumSizeHint(self):
        return QSize(10, super().minimumSizeHint().height())

    def sizeHint(self):
        return QSize(50, super().sizeHint().height())


# ── TITLE BAR BUTTON (DINAMIS & HOVER EFEK) ─────────────────────────
class TitleBarButton(QPushButton):
    def __init__(self, icon_name: str, hover_bg_color: str, parent=None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.hover_bg = hover_bg_color
        self.setFixedSize(46, 46)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setIcon(qta.icon(self.icon_name, color=CLR_TEXT_DIM))
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 0;
            }}
            QPushButton:hover {{
                background-color: {self.hover_bg};
            }}
        """)

    def enterEvent(self, event):
        self.setIcon(qta.icon(self.icon_name, color=CLR_TEXT_MAIN))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(qta.icon(self.icon_name, color=CLR_TEXT_DIM))
        super().leaveEvent(event)

    def change_icon(self, new_icon_name: str):
        self.icon_name = new_icon_name
        current_color = CLR_TEXT_MAIN if self.underMouse() else CLR_TEXT_DIM
        self.setIcon(qta.icon(self.icon_name, color=current_color))


# ── TITLE BAR CUSTOM ────────────────────────────────────────────────
class CustomTitleBar(QFrame):
    def __init__(self, parent, compact: bool = False, title: str = "Adyton Crypt"):
        super().__init__(parent)
        self.parent_window = parent
        self.setFixedHeight(46)
        # Mode compact (quick-action) menyatu dengan badan window; app utama tetap
        # memakai warna inset agar titlebar terbaca terpisah dari konten.
        bar_bg = CLR_WINDOW if compact else CLR_INSET
        self.setStyleSheet(f"background-color: {bar_bg};")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 0, 0, 0)
        lay.setSpacing(10)

        self.lbl_icon = QLabel()
        pixmap = QPixmap(get_asset_path("assets/icon_adyton.png"))
        self.lbl_icon.setPixmap(
            pixmap.scaled(
                18,
                18,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

        # Judul bersih
        lbl_title = QLabel(title)
        lbl_title.setObjectName("MutedText")

        lay.addWidget(self.lbl_icon)
        lay.addWidget(lbl_title)
        lay.addStretch()

        control_lay = QHBoxLayout()
        control_lay.setContentsMargins(0, 0, 0, 0)
        control_lay.setSpacing(0)

        self.btn_min = TitleBarButton("mdi6.minus", CLR_HOVER_BG, self)
        self.btn_min.clicked.connect(self.parent_window.showMinimized)

        self.btn_max = TitleBarButton("mdi6.window-maximize", CLR_HOVER_BG, self)
        self.btn_max.clicked.connect(self._toggle_maximize)

        self.btn_close = TitleBarButton("mdi6.close", CLR_DANGER, self)
        self.btn_close.clicked.connect(self.parent_window.close)

        control_lay.addWidget(self.btn_min)
        control_lay.addWidget(self.btn_max)
        control_lay.addWidget(self.btn_close)

        lay.addLayout(control_lay)

        # Window transient (mis. quick-action dari context menu) hanya perlu tombol
        # tutup — minimize/maximize tidak relevan untuk dialog satu-tugas.
        if compact:
            self.btn_min.hide()
            self.btn_max.hide()

    def _toggle_maximize(self):
        if self.parent_window.isMaximized():
            self.parent_window.showNormal()
            self.btn_max.change_icon("mdi6.window-maximize")
        else:
            self.parent_window.showMaximized()
            self.btn_max.change_icon("mdi6.window-restore")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.parent_window.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()


# ── WIDGET LAINNYA ──────────────────────────────────────────────────
class AnimatedNotifBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NotifBar")
        self.setMinimumWidth(280)
        self.setMaximumWidth(500)
        self.setMinimumHeight(55)
        self.setStyleSheet("background-color: transparent; border-radius: 10px;")

        apply_shadow(self, blur_radius=30, y_offset=10, opacity=60)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(12)

        self.lbl_icon = QLabel()
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_text = QLabel("")
        self.lbl_text.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.lbl_text.setWordWrap(True)

        self.btn_close = QPushButton()
        self.btn_close.setIcon(
            qta.icon("mdi6.close", color=CLR_TEXT_DIM, color_active=CLR_TEXT_MAIN)
        )
        self.btn_close.setIconSize(QSize(18, 18))
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setStyleSheet("background: transparent; border: none;")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.hide_msg)

        layout.addWidget(self.lbl_icon)
        layout.addWidget(self.lbl_text, 1)
        layout.addWidget(self.btn_close, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(400)
        self.anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self.anim.finished.connect(self._on_anim_finished)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide_msg)

        self.hide()

    def showEvent(self, event):
        super().showEvent(event)
        parent = self.parentWidget()
        if parent:
            parent.removeEventFilter(self)
            parent.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj == self.parentWidget() and event.type() == event.Type.Resize:
            if self.isVisible() and self.pos().y() >= 0:
                target_x = self.parentWidget().width() - self.width() - 20
                self.move(target_x, self.pos().y())
        return super().eventFilter(obj, event)

    def _on_anim_finished(self):
        if self.pos().y() < 0:
            self.hide()

    def show_msg(self, kind: str, msg: str, auto_hide_ms: int = 4000):
        self.timer.stop()
        self.anim.stop()

        bg_color = (
            CLR_SUCCESS_BG if kind == "ok" else (CLR_DANGER_BG if kind == "err" else CLR_WARN_BG)
        )
        fg_color = CLR_SUCCESS if kind == "ok" else (CLR_DANGER if kind == "err" else CLR_WARN)
        icon_name = (
            "mdi6.check-circle-outline"
            if kind == "ok"
            else ("mdi6.close-circle-outline" if kind == "err" else "mdi6.alert-circle-outline")
        )

        self.setStyleSheet(
            f"QFrame#NotifBar {{ background-color: {bg_color}; border-radius: 10px; border: none; }}"
            f"QLabel {{ border: none; background: transparent; color: {fg_color}; font-weight: 700; font-size: 10pt; }}"
        )
        self.lbl_icon.setPixmap(qta.icon(icon_name, color=fg_color).pixmap(24, 24))
        self.lbl_text.setStyleSheet(f"color: {fg_color}; font-weight: 600; font-size: 10pt;")
        self.lbl_text.setText(msg)

        self.raise_()
        self.adjustSize()
        self.show()

        if self.parentWidget():
            p_rect = self.parentWidget().rect()
            target_x = p_rect.width() - self.width() - 20
            target_y = 20
            start_y = -self.minimumHeight() - 20
        else:
            target_x = 20
            target_y = 20
            start_y = -100

        if not self.isVisible() or self.pos().y() < 0:
            self.anim.setStartValue(QPoint(target_x, start_y))
        else:
            self.anim.setStartValue(self.pos())

        self.anim.setEndValue(QPoint(target_x, target_y))
        self.anim.start()

        if auto_hide_ms > 0:
            self.timer.start(auto_hide_ms)

    def hide_msg(self):
        self.timer.stop()
        if not self.isVisible() or self.pos().y() < 0:
            return

        if self.parentWidget():
            target_x = self.pos().x()
            target_y = -self.minimumHeight() - 20
        else:
            target_x = 20
            target_y = -100

        self.anim.stop()
        self.anim.setStartValue(self.pos())
        self.anim.setEndValue(QPoint(target_x, target_y))
        self.anim.start()


# ── PASSWORD LINE EDIT WITH TOGGLE ────────────────────────────────
class PasswordLineEdit(QFrame):
    """
    Reusable password input field with eye toggle button.
    Provides consistent look and behavior across the app.
    """

    textChanged = Signal(str)
    returnPressed = Signal()  # Proper Signal definition (not @property)

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)

        self.setObjectName("InputBox")
        # Tinggi dipatok agar SEMUA input password seragam 52px di mana pun
        # dipakai — frame tak ikut melar saat layout punya ruang vertikal lebih
        # (mis. Tab Teks mode dekripsi yang field-nya sedikit).
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 6, 0)
        lay.setSpacing(0)

        self.line_edit = QLineEdit()
        self.line_edit.setObjectName("InputInside")
        self.line_edit.setFixedHeight(52)
        self.line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        if placeholder:
            self.line_edit.setPlaceholderText(placeholder)
        self.line_edit.textChanged.connect(self.textChanged)
        lay.addWidget(self.line_edit)

        self.btn_toggle = QPushButton()
        self.btn_toggle.setIcon(qta.icon("mdi6.eye-outline", color=CLR_TEXT_MUTED))
        self.btn_toggle.setIconSize(QSize(22, 22))
        self.btn_toggle.setObjectName("BtnEye")
        self.btn_toggle.setFixedSize(40, 52)
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.clicked.connect(self._toggle_visibility)
        self.btn_toggle.installEventFilter(self)
        # Highlight InputBox saat field/tombol mata fokus (state 'focused' di QSS).
        self.line_edit.installEventFilter(self)
        from .i18n import register, tr

        register(
            self.btn_toggle, "a11y.toggle_password", "Show or hide password", "setAccessibleName"
        )
        self.btn_toggle.setToolTip(tr("pw.show", "Show password"))
        self.line_edit.returnPressed.connect(self.returnPressed)
        lay.addWidget(self.btn_toggle)

        # Store reference to styles (imported at top level)
        self._muted_color = CLR_TEXT_MUTED
        self._accent_color = CLR_ACCENT

    def eventFilter(self, obj, event):
        if obj is self.btn_toggle and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.btn_toggle.click()
                return True
        if obj is self.btn_toggle and event.type() in (event.Type.Enter, event.Type.Leave):
            # Hover: cerahkan ikon mata (feedback hover yang terlihat).
            self._update_toggle_icon(hover=event.type() == event.Type.Enter)
        if obj in (self.line_edit, self.btn_toggle) and event.type() in (
            event.Type.FocusIn,
            event.Type.FocusOut,
        ):
            # Tunda satu siklus agar perpindahan fokus field <-> tombol mata tidak
            # mematikan highlight sekejap (anti-flicker).
            QTimer.singleShot(0, self._sync_focus_style)
        return super().eventFilter(obj, event)

    def _sync_focus_style(self):
        """Aktifkan border aksen InputBox saat field ATAU tombol mata memegang fokus."""
        focused = self.line_edit.hasFocus() or self.btn_toggle.hasFocus()
        if bool(self.property("focused")) != focused:
            self.setProperty("focused", focused)
            self.style().unpolish(self)
            self.style().polish(self)

    def _toggle_visibility(self):
        from .i18n import tr

        if self.line_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle.setToolTip(tr("pw.hide", "Hide password"))
        else:
            self.line_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle.setToolTip(tr("pw.show", "Show password"))
        # Perbarui ikon, hormati apakah kursor masih di atas tombol.
        self._update_toggle_icon(hover=self.btn_toggle.underMouse())

    # --- Public API ---
    def text(self) -> str:
        return self.line_edit.text()

    def setText(self, text: str):
        self.line_edit.setText(text)

    def setPlaceholderText(self, text: str):
        self.line_edit.setPlaceholderText(text)

    def setAccessibleName(self, name: str):
        self.line_edit.setAccessibleName(name)

    def clear(self):
        self.line_edit.clear()
        self.setEchoMode(QLineEdit.EchoMode.Password)

    def setEnabled(self, enabled: bool):
        self.line_edit.setEnabled(enabled)
        self.btn_toggle.setEnabled(enabled)

    def installEventFilter(self, obj):
        self.line_edit.installEventFilter(obj)
        self.btn_toggle.installEventFilter(obj)

    # --- Echo mode control (public API) ---
    def setEchoMode(self, mode):
        self.line_edit.setEchoMode(mode)
        self._update_toggle_icon()

    def echoMode(self):
        return self.line_edit.echoMode()

    def _update_toggle_icon(self, hover: bool = False):
        # Hover mencerahkan ikon (qtawesome tak ikut QSS :hover). Warna mengikuti
        # state echo mode: tersembunyi = mata muted, terlihat = mata-coret aksen.
        if self.line_edit.echoMode() == QLineEdit.EchoMode.Password:
            color = CLR_TEXT_MAIN if hover else self._muted_color
            self.btn_toggle.setIcon(qta.icon("mdi6.eye-outline", color=color))
        else:
            color = CLR_ACCENT_HOVER if hover else self._accent_color
            self.btn_toggle.setIcon(qta.icon("mdi6.eye-off-outline", color=color))


# ── TOGGLE SWITCH (iOS-style pill) ────────────────────────────────
class ToggleSwitch(QFrame):
    """Toggle switch (track + knob) dengan animasi geser & dukungan keyboard."""

    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self._checked = bool(checked)
        self._knob = 1.0 if self._checked else 0.0
        self.setFixedSize(46, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

        self._anim = QPropertyAnimation(self, b"knobPos")
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    # --- properti animasi knob (0=off, 1=on) ---
    def _get_knob(self) -> float:
        return self._knob

    def _set_knob(self, value: float):
        self._knob = value
        self.update()

    knobPos = Property(float, _get_knob, _set_knob)

    # --- API publik ---
    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, state: bool, animate: bool = True):
        state = bool(state)
        if state == self._checked:
            return
        self._checked = state
        target = 1.0 if state else 0.0
        if animate and self.isVisible():
            self._anim.stop()
            self._anim.setStartValue(self._knob)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._set_knob(target)
        self.toggled.emit(self._checked)

    def toggle(self):
        self.setChecked(not self._checked)

    # --- interaksi ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.toggle()
            event.accept()
        else:
            super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.isEnabled():
                self.toggle()
            event.accept()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self.rect()
        radius = r.height() / 2
        t = self._knob

        # Track — interpolasi warna off → on (well recessed gelap → aksen). OFF
        # dibuat jauh lebih gelap dari kartu/panel di belakangnya agar pill toggle
        # jelas terbaca sebagai kontrol (tidak menyatu dengan latar).
        off, on = QColor(CLR_TOGGLE_OFF), QColor(CLR_ACCENT)
        track = QColor(
            int(off.red() + (on.red() - off.red()) * t),
            int(off.green() + (on.green() - off.green()) * t),
            int(off.blue() + (on.blue() - off.blue()) * t),
        )
        if not self.isEnabled():
            track.setAlpha(110)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(r, radius, radius)

        # Rim tipis saat OFF (memudar saat ON) — menegaskan tepi pill di atas latar
        # gelap; state ON sudah terang (aksen) jadi tak butuh rim.
        rim = QColor(CLR_INPUT_BORDER)
        rim.setAlphaF((1.0 - t) * (0.6 if self.isEnabled() else 0.3))
        if rim.alphaF() > 0.0:
            painter.setPen(QPen(rim, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5), radius - 0.5, radius - 0.5
            )

        # Knob putih yang menggeser
        margin = 3
        knob_d = r.height() - margin * 2
        x = margin + t * (r.width() - knob_d - margin * 2)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(int(round(x)), margin, knob_d, knob_d)

        # Ring fokus keyboard-only (kbFocus diset _FocusRingFilter). Warna kontras
        # per state: aksen saat OFF (track abu-abu), putih saat ON (track aksen) —
        # agar ring tetap jelas terlihat di kedua kondisi.
        if self.property("kbFocus"):
            ring = QColor(CLR_TEXT_MAIN if self._checked else CLR_ACCENT)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(ring, 2))
            painter.drawRoundedRect(r.adjusted(1, 1, -1, -1), radius - 1, radius - 1)
