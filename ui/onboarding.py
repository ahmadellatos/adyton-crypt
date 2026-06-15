"""
Modul: onboarding.py
Deskripsi: Pengalaman first-run Adyton Crypt — splash bermerek yang otomatis
           berlanjut ke wizard 4 langkah (Welcome → Private by design → Three
           tools → You're all set), ditutup dengan layar selesai.

           Dibangun native PySide6 mengikuti "Adyton Crypt — Design System":
           memakai token CLR_* dari ui/styles.py dan ikon qtawesome (mdi6),
           tanpa hex baru. Tata letak, copy, dan spacing mengikuti referensi
           desain (Onboarding.reference) persis.

           Struktur: QStackedWidget dengan 6 halaman (splash, step1..4, done)
           ditambah footer navigasi tetap yang hanya tampil pada step 1–4.
           Animasi (cincin berputar/berdenyut, sapuan loading) bersifat dekoratif
           dan tidak pernah menyembunyikan konten saat diam.
"""

import math

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
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.paths import get_asset_path

from .styles import (
    ACCENT_RGB,
    CLR_ACCENT,
    CLR_ACCENT_HOVER,
    CLR_ACCENT_TEXT,
    CLR_BORDER,
    CLR_CARD,
    CLR_HOVER_BG,
    CLR_INPUT_BORDER,
    CLR_INSET,
    CLR_LINE,
    CLR_MONO_META,
    CLR_ON_ACCENT,
    CLR_SUCCESS,
    CLR_TEXT_DIM,
    CLR_TEXT_FAINT,
    CLR_TEXT_MAIN,
    CLR_TEXT_MUTED,
    CLR_WARN,
    CLR_WARN_TEXT,
    CLR_WINDOW,
    FONT_MONO,
    SUCCESS_RGB,
    WARN_RGB,
)

# Komponen RGB untuk QColor terpaint (sejajar dengan token rgba di styles).
_ACCENT_QRGB = (79, 191, 201)
_SUCCESS_QRGB = (134, 203, 163)


def _qcolor(rgb: tuple[int, int, int], alpha: float) -> QColor:
    c = QColor(*rgb)
    c.setAlphaF(alpha)
    return c


def _set_letter_spacing(label: QLabel, px: float) -> None:
    """Terapkan letter-spacing absolut via QFont (QSS Qt tidak mendukungnya)."""
    f = label.font()
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, px)
    label.setFont(f)


class _WrapLabel(QLabel):
    """QLabel word-wrap dengan sizeHint akurat (tinggi = heightForWidth pada lebar
    target). QLabel biasa melaporkan sizeHint pada lebar sempit asumtif sehingga
    tinggi membengkak — itu membuat layout salah hitung & menekan widget lain
    hingga teks (descender) terpotong."""

    def __init__(self, width: int, text: str = "", parent=None):
        super().__init__(text, parent)
        self._w = width
        self.setWordWrap(True)

    def sizeHint(self):
        return QSize(self._w, self.heightForWidth(self._w))

    def minimumSizeHint(self):
        return QSize(0, self.heightForWidth(self._w))


def _label(
    text: str,
    size_px: float,
    weight: int,
    color: str,
    *,
    family: str | None = None,
    wrap: bool = False,
    ls: float | None = None,
    align: Qt.AlignmentFlag | None = None,
    max_w: int | None = None,
) -> QLabel:
    if wrap and max_w:
        lbl: QLabel = _WrapLabel(max_w, text)
    else:
        lbl = QLabel(text)
        if wrap:
            lbl.setWordWrap(True)
    css = f"font-size:{size_px}px; font-weight:{weight}; color:{color}; background:transparent;"
    if family:
        css += f" font-family:{family};"
    lbl.setStyleSheet(css)
    if max_w:
        lbl.setMaximumWidth(max_w)
    if align is not None:
        lbl.setAlignment(align)
    if ls is not None:
        _set_letter_spacing(lbl, ls)
    return lbl


def _logo(size: int) -> QLabel:
    lbl = QLabel()
    lbl.setFixedSize(size, size)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet("background:transparent;")
    pm = QPixmap(get_asset_path("assets/icon_adyton.png"))
    if not pm.isNull():
        lbl.setPixmap(
            pm.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
    return lbl


def _overlay(*widgets: QWidget) -> QWidget:
    """Tumpuk widget pada satu sel grid (terpusat); urutan = z-order bawah→atas."""
    holder = QWidget()
    holder.setStyleSheet("background:transparent;")
    grid = QGridLayout(holder)
    grid.setContentsMargins(0, 0, 0, 0)
    for w in widgets:
        grid.addWidget(w, 0, 0, Qt.AlignmentFlag.AlignCenter)
    return holder


def _icon_tile(
    size: int,
    icon_name: str,
    icon_px: int,
    radius: int,
    *,
    tint_a: float = 0.12,
    border_a: float | None = None,
    rgb: str = ACCENT_RGB,
    icon_color: str = CLR_ACCENT_TEXT,
) -> QLabel:
    """Petak ikon sudut-lembut bertint (mis. ubin alat / petak fokus)."""
    tile = QLabel()
    tile.setFixedSize(size, size)
    tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
    tile.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(icon_px, icon_px))
    css = f"background:rgba({rgb}, {tint_a}); border-radius:{radius}px;"
    if border_a is not None:
        css += f" border:1px solid rgba({rgb}, {border_a});"
    tile.setStyleSheet(css)
    return tile


# ── DEKORASI TERPAINT (cincin, glow) ────────────────────────────────
class _RotatingRing(QWidget):
    """Cincin putus-putus (dashed) yang berputar 360° pada periode tertentu."""

    def __init__(
        self, diameter: int, color: QColor, period_ms: int, width: float = 1.5, parent=None
    ):
        super().__init__(parent)
        self.setFixedSize(diameter, diameter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._color = color
        self._w = width
        self._angle = 0.0
        self._anim = QPropertyAnimation(self, b"angle", self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(360.0)
        self._anim.setDuration(period_ms)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)

    def _get_angle(self) -> float:
        return self._angle

    def _set_angle(self, v: float) -> None:
        self._angle = v
        self.update()

    angle = Property(float, _get_angle, _set_angle)

    def showEvent(self, e):
        super().showEvent(e)
        self._anim.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._anim.stop()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.translate(self.width() / 2, self.height() / 2)
        p.rotate(self._angle)
        pen = QPen(self._color, self._w)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        r = self.width() / 2 - self._w
        p.drawEllipse(QRectF(-r, -r, 2 * r, 2 * r))


class _PulsingRing(QWidget):
    """Cincin solid yang berdenyut (opacity .55↔.12, skala 1↔1.28)."""

    def __init__(
        self,
        diameter: int,
        color: QColor,
        period_ms: int = 2800,
        delay_ms: int = 0,
        width: float = 1.5,
        parent=None,
    ):
        super().__init__(parent)
        box = round(diameter * 1.34)
        self.setFixedSize(box, box)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._diameter = diameter
        self._base_alpha = color.alphaF()
        self._color = QColor(color)
        self._w = width
        self._delay = delay_ms
        self._phase = 0.0
        self._anim = QPropertyAnimation(self, b"phase", self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(period_ms)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)

    def _get_phase(self) -> float:
        return self._phase

    def _set_phase(self, v: float) -> None:
        self._phase = v
        self.update()

    phase = Property(float, _get_phase, _set_phase)

    def showEvent(self, e):
        super().showEvent(e)
        if self._delay:
            QTimer.singleShot(self._delay, self._anim.start)
        else:
            self._anim.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._anim.stop()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        f = math.sin(math.pi * self._phase)  # 0 → 1 → 0
        opacity = 0.55 - 0.43 * f
        scale = 1.0 + 0.28 * f
        p.translate(self.width() / 2, self.height() / 2)
        p.scale(scale, scale)
        col = QColor(self._color)
        col.setAlphaF(self._base_alpha * opacity)
        p.setPen(QPen(col, self._w))
        p.setBrush(Qt.BrushStyle.NoBrush)
        r = self._diameter / 2
        p.drawEllipse(QRectF(-r, -r, 2 * r, 2 * r))


class _RadialGlow(QWidget):
    """Glow radial lembut (terang di pusat → transparan)."""

    def __init__(self, diameter: int, color: QColor, stop: float = 0.7, parent=None):
        super().__init__(parent)
        self.setFixedSize(diameter, diameter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._color = color
        self._stop = stop

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx, cy = self.width() / 2, self.height() / 2
        grad = QRadialGradient(cx, cy, self.width() / 2)
        grad.setColorAt(0.0, self._color)
        transparent = QColor(self._color)
        transparent.setAlpha(0)
        grad.setColorAt(self._stop, transparent)
        grad.setColorAt(1.0, transparent)
        p.fillRect(self.rect(), QBrush(grad))


class _GlowBg(QWidget):
    """Latar halaman (CLR_WINDOW) dengan satu glow radial aksen di belakang konten."""

    def __init__(self, cx: float, cy: float, alpha: float, stop: float, parent=None):
        super().__init__(parent)
        self._cx, self._cy = cx, cy
        self._alpha, self._stop = alpha, stop

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(CLR_WINDOW))
        w, h = self.width(), self.height()
        cx, cy = w * self._cx, h * self._cy
        # Radius gradien = jarak ke sudut terjauh (meniru circle farthest-corner).
        corners = [(0, 0), (w, 0), (0, h), (w, h)]
        radius = max(math.hypot(cx - x, cy - y) for x, y in corners)
        grad = QRadialGradient(cx, cy, radius)
        grad.setColorAt(0.0, _qcolor(_ACCENT_QRGB, self._alpha))
        grad.setColorAt(self._stop, _qcolor(_ACCENT_QRGB, 0.0))
        grad.setColorAt(1.0, _qcolor(_ACCENT_QRGB, 0.0))
        p.fillRect(self.rect(), QBrush(grad))


class _StagePane(QWidget):
    """Panel kiri onboarding: CLR_INSET + glow + dua cincin backdrop + garis kanan."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(48, 48, 48, 48)
        lay.setSpacing(0)
        lay.addStretch(1)
        self._slot = QVBoxLayout()
        self._slot.setSpacing(24)
        self._slot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addLayout(self._slot)
        lay.addStretch(1)

    def add_focal(self, *widgets: QWidget) -> None:
        for w in widgets:
            self._slot.addWidget(w, alignment=Qt.AlignmentFlag.AlignHCenter)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(CLR_INSET))

        # Glow radial di 50% / 42%.
        gx, gy = w * 0.5, h * 0.42
        gr = max(w, h) * 0.6
        glow = QRadialGradient(gx, gy, gr)
        glow.setColorAt(0.0, _qcolor(_ACCENT_QRGB, 0.09))
        glow.setColorAt(0.6, _qcolor(_ACCENT_QRGB, 0.0))
        glow.setColorAt(1.0, _qcolor(_ACCENT_QRGB, 0.0))
        p.fillRect(self.rect(), QBrush(glow))

        # Dua cincin backdrop dashed (420 & 300) di 50% / 46%.
        cx, cy = w * 0.5, h * 0.46
        p.setBrush(Qt.BrushStyle.NoBrush)
        for diameter, alpha in ((420, 0.08), (300, 0.06)):
            pen = QPen(_qcolor(_ACCENT_QRGB, alpha), 1)
            pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            r = diameter / 2
            p.drawEllipse(QRectF(cx - r, cy - r, diameter, diameter))

        # Garis pembatas kanan 1px.
        p.setPen(QPen(QColor(CLR_LINE), 1))
        p.drawLine(w - 1, 0, w - 1, h)


class _LoadingBar(QWidget):
    """Bar loading indeterminate: track 220×6 dengan isian 42% yang menyapu."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(220, 6)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background:{CLR_LINE}; border-radius:3px;")
        fw = round(220 * 0.42)
        self._fill = QFrame(self)
        self._fill.setFixedSize(fw, 6)
        self._fill.setStyleSheet(
            "border-radius:3px; background:qlineargradient("
            f"x1:0, y1:0, x2:1, y2:0, stop:0 rgba({ACCENT_RGB}, 0.2), stop:1 {CLR_ACCENT});"
        )
        self._anim = QPropertyAnimation(self._fill, b"pos", self)
        self._anim.setStartValue(QPoint(-round(fw * 1.3), 0))
        self._anim.setEndValue(QPoint(round(fw * 3.3), 0))
        self._anim.setDuration(1300)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)

    def showEvent(self, e):
        super().showEvent(e)
        self._anim.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._anim.stop()


# ── ELEMEN INTERAKTIF (pill, dots) ──────────────────────────────────
class _HoverPill(QFrame):
    """Pill/teks yang bisa diklik dengan state hover & disabled (footer/done)."""

    clicked = Signal()

    def __init__(
        self,
        text: str,
        *,
        height: int,
        pad_h: int,
        radius: int,
        normal_bg: str,
        hover_bg: str,
        fg: str,
        fg_hover: str | None = None,
        normal_border: str = "transparent",
        hover_border: str | None = None,
        font_px: float = 14,
        font_weight: int = 700,
        icon_left: str | None = None,
        icon_right: str | None = None,
        icon_px: int = 16,
        icon_color: str | None = None,
        gap: int = 10,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("OnbPill")
        self.setFixedHeight(height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._enabled_state = True
        self._radius = radius
        self._normal_bg = normal_bg
        self._hover_bg = hover_bg
        self._normal_border = normal_border
        self._hover_border = hover_border or normal_border
        self._fg = fg
        self._fg_hover = fg_hover or fg
        self._font_px = font_px
        self._font_weight = font_weight
        self._icon_color = icon_color or fg

        lay = QHBoxLayout(self)
        lay.setContentsMargins(pad_h, 0, pad_h, 0)
        lay.setSpacing(gap)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._icons: list[tuple[QLabel, str, int]] = []
        if icon_left:
            self._icons.append((self._add_icon(lay, icon_left, icon_px), icon_left, icon_px))
        self._lbl = QLabel(text)
        lay.addWidget(self._lbl)
        if icon_right:
            self._icons.append((self._add_icon(lay, icon_right, icon_px), icon_right, icon_px))

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._apply(hover=False)

    def _add_icon(self, lay: QHBoxLayout, name: str, px: int) -> QLabel:
        ic = QLabel()
        ic.setStyleSheet("background:transparent;")
        ic.setPixmap(qta.icon(name, color=self._icon_color).pixmap(px, px))
        lay.addWidget(ic)
        return ic

    def _recolor_icons(self, color: str) -> None:
        for lbl, name, px in self._icons:
            lbl.setPixmap(qta.icon(name, color=color).pixmap(px, px))

    def _apply(self, hover: bool) -> None:
        bg = self._hover_bg if hover else self._normal_bg
        border = self._hover_border if hover else self._normal_border
        fg = self._fg_hover if hover else self._fg
        self.setStyleSheet(
            f"#OnbPill {{ background:{bg}; border:1px solid {border}; border-radius:{self._radius}px; }}"
        )
        self._lbl.setStyleSheet(
            f"background:transparent; font-size:{self._font_px}px; "
            f"font-weight:{self._font_weight}; color:{fg};"
        )

    def setNavEnabled(self, enabled: bool) -> None:
        self._enabled_state = enabled
        if enabled:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self._recolor_icons(self._icon_color)
            self._apply(hover=False)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self._recolor_icons(CLR_TEXT_FAINT)
            self.setStyleSheet(
                f"#OnbPill {{ background:transparent; border:1px solid transparent; "
                f"border-radius:{self._radius}px; }}"
            )
            self._lbl.setStyleSheet(
                f"background:transparent; font-size:{self._font_px}px; "
                f"font-weight:{self._font_weight}; color:{CLR_TEXT_FAINT};"
            )

    def enterEvent(self, e):
        if self._enabled_state:
            self._apply(hover=True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        if self._enabled_state:
            self._apply(hover=False)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if self._enabled_state and e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            e.accept()
        else:
            super().mousePressEvent(e)


class _Dot(QFrame):
    """Titik progress yang menganimasikan lebar (8 ↔ 26)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(8)
        self.setFixedWidth(8)
        self._bw = 8
        self._anim = QPropertyAnimation(self, b"barWidth", self)
        self._anim.setDuration(250)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._set_color(CLR_INPUT_BORDER)

    def _get_bw(self) -> float:
        return float(self._bw)

    def _set_bw(self, v: float) -> None:
        self._bw = v
        self.setFixedWidth(int(round(v)))

    barWidth = Property(float, _get_bw, _set_bw)

    def _set_color(self, color: str) -> None:
        self.setStyleSheet(f"background:{color}; border-radius:4px;")

    def set_state(self, active: bool, completed: bool) -> None:
        if active:
            color = CLR_ACCENT
        elif completed:
            color = f"rgba({ACCENT_RGB}, 0.5)"
        else:
            color = CLR_INPUT_BORDER
        self._set_color(color)
        target = 26 if active else 8
        self._anim.stop()
        self._anim.setStartValue(float(self._bw))
        self._anim.setEndValue(float(target))
        self._anim.start()


class _StepDots(QWidget):
    def __init__(self, count: int = 4, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dots = [_Dot() for _ in range(count)]
        for d in self._dots:
            lay.addWidget(d)

    def set_step(self, step: int) -> None:
        for i, dot in enumerate(self._dots):
            dot.set_state(active=(i == step - 1), completed=(i < step - 1))


# ── KONTEN PER-STEP ─────────────────────────────────────────────────
_STEP_COPY = {
    1: (
        "WELCOME TO ADYTON CRYPT",
        "Encrypt anything. Keep it on your device.",
        "Adyton Crypt locks your files, folders, and notes behind strong encryption "
        "— right here on your computer. No accounts, no cloud, no servers.",
    ),
    2: (
        "PRIVATE BY DESIGN",
        "Your data never leaves this machine.",
        "Every lock and unlock happens offline. Your password and files are processed "
        "entirely on your device, and are never uploaded, synced, or sent anywhere.",
    ),
    3: (
        "THREE TOOLS, ONE VAULT",
        "Lock folders, open vaults, encrypt text.",
        "Three focused tools share the same calm workflow — so protecting something "
        "always feels the same.",
    ),
    4: (
        "YOU'RE ALL SET",
        "One thing worth remembering.",
        "Your password is the only key. Adyton can't reset or recover it — if it's lost, "
        "the data is gone for good. Keep it somewhere safe.",
    ),
}


def _list_card(rows: list[tuple[str, str, str]]) -> QFrame:
    """Kartu daftar (step 2 & 3): tiap baris = ubin ikon 42 + judul + sub."""
    card = QFrame()
    card.setObjectName("OnbListCard")
    # Selector ber-objectName agar border tidak bocor ke label anak (QSS Qt:
    # deklarasi border tanpa selector menurun ke widget keturunan).
    card.setStyleSheet(
        f"#OnbListCard {{ background:{CLR_CARD}; border:1px solid {CLR_BORDER}; "
        "border-radius:18px; }"
    )
    v = QVBoxLayout(card)
    v.setContentsMargins(8, 8, 8, 8)
    v.setSpacing(6)
    for icon_name, title, sub in rows:
        row = QWidget()
        row.setStyleSheet("background:transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(16, 14, 16, 14)
        rl.setSpacing(14)
        rl.addWidget(_icon_tile(42, icon_name, 20, 12), alignment=Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(_label(title, 14.5, 700, CLR_TEXT_MAIN))
        col.addWidget(_label(sub, 12.5, 500, CLR_TEXT_DIM))
        rl.addLayout(col, 1)
        v.addWidget(row)
    # Jangan biarkan kartu menyusut di bawah tinggi alaminya (cegah baris menumpuk).
    card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
    return card


def _pill(
    text: str,
    *,
    rgb: str = ACCENT_RGB,
    bg_a: float = 0.1,
    border_a: float = 0.22,
    fg: str = CLR_ACCENT_TEXT,
    dot: bool = False,
) -> QFrame:
    frame = QFrame()
    frame.setObjectName("OnbInfoPill")
    frame.setStyleSheet(
        f"#OnbInfoPill {{ background:rgba({rgb}, {bg_a}); "
        f"border:1px solid rgba({rgb}, {border_a}); border-radius:17px; }}"
    )
    frame.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    lay = QHBoxLayout(frame)
    lay.setContentsMargins(16, 9, 16, 9)
    lay.setSpacing(8)
    if dot:
        d = QLabel()
        d.setFixedSize(7, 7)
        d.setStyleSheet(f"background:{CLR_ACCENT}; border-radius:3px;")
        lay.addWidget(d)
    lay.addWidget(_label(text, 12, 700, fg))
    return frame


def _chip(text: str) -> QFrame:
    chip = QFrame()
    chip.setObjectName("OnbChip")
    chip.setStyleSheet(
        f"#OnbChip {{ background:{CLR_INSET}; border:1px solid {CLR_BORDER}; "
        "border-radius:18px; }"
    )
    chip.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    lay = QHBoxLayout(chip)
    lay.setContentsMargins(15, 10, 15, 10)
    lay.setSpacing(8)
    ic = QLabel()
    ic.setStyleSheet("background:transparent;")
    ic.setPixmap(qta.icon("mdi6.check", color=CLR_ACCENT_TEXT).pixmap(14, 14))
    lay.addWidget(ic)
    lay.addWidget(_label(text, 12.5, 600, CLR_TEXT_MUTED))
    return chip


def _notice_row(icon_name: str, icon_color: str, rgb: str, title: str, sub: str) -> QFrame:
    """Baris pemberitahuan step 4 (tinted success/warning, radius 16)."""
    row = QFrame()
    row.setObjectName("OnbNotice")
    row.setStyleSheet(
        f"#OnbNotice {{ background:rgba({rgb}, 0.07); "
        f"border:1px solid rgba({rgb}, 0.22); border-radius:16px; }}"
    )
    lay = QHBoxLayout(row)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(14)
    ic = QLabel()
    ic.setStyleSheet("background:transparent;")
    ic.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(22, 22))
    lay.addWidget(ic, alignment=Qt.AlignmentFlag.AlignTop)
    col = QVBoxLayout()
    col.setSpacing(2)
    col.addWidget(_label(title, 14, 700, CLR_TEXT_MAIN))
    col.addWidget(_label(sub, 12.5, 500, CLR_TEXT_DIM))
    lay.addLayout(col, 1)
    return row


# ── ONBOARDING VIEW ─────────────────────────────────────────────────
class OnboardingView(QWidget):
    """First-run wizard: splash → 4 langkah → selesai. Emit `completed` saat masuk app."""

    completed = Signal()

    SPLASH = 0
    DONE = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("OnboardingView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"#OnboardingView {{ background:{CLR_WINDOW}; }}")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._step = self.SPLASH

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_splash())  # 0
        for n in (1, 2, 3, 4):
            self.stack.addWidget(self._build_step(n))  # 1..4
        self.stack.addWidget(self._build_done())  # 5

        self._footer = self._build_footer()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.stack, 1)
        root.addWidget(self._footer)

        self._splash_timer = QTimer(self)
        self._splash_timer.setSingleShot(True)
        self._splash_timer.setInterval(2600)
        self._splash_timer.timeout.connect(self._on_splash_timeout)

    # --- API publik ---
    def start(self) -> None:
        """Tampilkan splash dan mulai hitung mundur auto-advance ke step 1."""
        self._go(self.SPLASH)
        self._splash_timer.start()
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    # --- navigasi ---
    def _on_splash_timeout(self) -> None:
        if self._step == self.SPLASH:
            self._go(1)

    def _next(self) -> None:
        if 1 <= self._step < 4:
            self._go(self._step + 1)
        elif self._step == 4:
            self._go(self.DONE)

    def _back(self) -> None:
        if self._step > 1:
            self._go(self._step - 1)

    def _skip(self) -> None:
        self._splash_timer.stop()
        self._go(self.DONE)

    def _replay(self) -> None:
        self._go(1)

    def _finish(self) -> None:
        self._splash_timer.stop()
        self.completed.emit()

    def _go(self, step: int) -> None:
        self._step = step
        self.stack.setCurrentIndex(step)
        is_onboard = 1 <= step <= 4
        self._footer.setVisible(is_onboard)
        if is_onboard:
            self._dots.set_step(step)
            self._back_pill.setNavEnabled(step > 1)
            self._skip_pill.setVisible(step < 4)
            self._next_pill.set_text("Get Started" if step == 4 else "Continue")
        if step in (self.SPLASH, self.DONE):
            self.setFocus(Qt.FocusReason.OtherFocusReason)

    # --- keyboard (hanya saat step 1–4) ---
    def keyPressEvent(self, e):
        if 1 <= self._step <= 4:
            key = e.key()
            if key in (Qt.Key.Key_Right, Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._next()
                return
            if key == Qt.Key.Key_Left:
                self._back()
                return
            if key == Qt.Key.Key_Escape:
                self._skip()
                return
        super().keyPressEvent(e)

    # --- halaman: splash ---
    def _build_splash(self) -> QWidget:
        page = _GlowBg(0.5, 0.36, 0.10, 0.56)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        col = QVBoxLayout()
        col.setSpacing(30)
        col.setAlignment(Qt.AlignmentFlag.AlignCenter)

        focal = _overlay(
            _RotatingRing(188, _qcolor(_ACCENT_QRGB, 0.30), 16000),
            _RadialGlow(140, _qcolor(_ACCENT_QRGB, 0.28)),
            _logo(104),
        )
        col.addWidget(focal, alignment=Qt.AlignmentFlag.AlignHCenter)

        brand = QVBoxLayout()
        brand.setSpacing(8)
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wordmark = _label("Adyton Crypt", 27, 800, CLR_TEXT_MAIN, ls=-0.5)
        wordmark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.addWidget(wordmark, alignment=Qt.AlignmentFlag.AlignHCenter)
        brand.addWidget(
            _label(
                "Local file encryption, done calmly",
                13.5,
                500,
                CLR_TEXT_DIM,
                align=Qt.AlignmentFlag.AlignCenter,
            ),
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )
        col.addLayout(brand)

        loading = QVBoxLayout()
        loading.setSpacing(13)
        loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading.addWidget(_LoadingBar(), alignment=Qt.AlignmentFlag.AlignHCenter)
        loading.addWidget(
            _label(
                "Loading secure modules…",
                11.5,
                500,
                CLR_TEXT_FAINT,
                align=Qt.AlignmentFlag.AlignCenter,
            ),
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )
        col.addLayout(loading)

        outer.addLayout(col)
        return page

    # --- halaman: step 1–4 ---
    def _build_step(self, step: int) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background:transparent;")
        lay = QHBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        stage = _StagePane()
        self._populate_stage(stage, step)
        lay.addWidget(stage, 45)

        lay.addWidget(self._build_content(step), 55)
        return page

    def _populate_stage(self, stage: _StagePane, step: int) -> None:
        if step == 1:
            stage.add_focal(
                _overlay(
                    _RotatingRing(230, _qcolor(_ACCENT_QRGB, 0.32), 22000),
                    _RadialGlow(172, _qcolor(_ACCENT_QRGB, 0.22)),
                    _logo(124),
                ),
                _label("Local encryption, done calmly", 13, 600, CLR_TEXT_DIM),
            )
        elif step == 2:
            tile = _icon_tile(152, "mdi6.shield-check-outline", 80, 36, border_a=0.26)
            stage.add_focal(
                _overlay(
                    _PulsingRing(200, _qcolor(_ACCENT_QRGB, 0.30), 2800, 0),
                    _PulsingRing(166, _qcolor(_ACCENT_QRGB, 0.22), 2800, 600),
                    tile,
                ),
                _pill("100% offline · no network", dot=True),
            )
        elif step == 3:
            tiles = QWidget()
            tiles.setStyleSheet("background:transparent;")
            row = QHBoxLayout(tiles)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(18)
            for icon_name in (
                "mdi6.lock-outline",
                "mdi6.lock-open-variant-outline",
                "mdi6.text-box-outline",
            ):
                row.addWidget(_icon_tile(84, icon_name, 36, 22, border_a=0.24))
            stage.add_focal(tiles, _pill("Three focused tools, one workflow"))
        elif step == 4:
            tile = _icon_tile(152, "mdi6.key-outline", 78, 36, border_a=0.26)
            stage.add_focal(
                _overlay(_PulsingRing(200, _qcolor(_ACCENT_QRGB, 0.28), 2800, 0), tile),
                _pill(
                    "Your key, your responsibility",
                    rgb=WARN_RGB,
                    bg_a=0.12,
                    border_a=0.26,
                    fg=CLR_WARN_TEXT,
                ),
            )

    def _build_content(self, step: int) -> QWidget:
        eyebrow, title, body = _STEP_COPY[step]

        pane = QWidget()
        pane.setStyleSheet("background:transparent;")
        v = QVBoxLayout(pane)
        v.setContentsMargins(64, 40, 64, 40)
        v.setSpacing(0)

        counter_row = QHBoxLayout()
        counter_row.addStretch(1)
        counter_row.addWidget(
            _label(f"0{step} / 04", 12, 500, CLR_TEXT_FAINT, family=FONT_MONO, ls=1)
        )
        v.addLayout(counter_row)

        block = QWidget()
        block.setStyleSheet("background:transparent;")
        # Lebar tetap 520 (content pane selalu ≥576 pada minimum 1280) supaya
        # judul/teks wrap pada lebar yang sama seperti referensi, bukan sizeHint.
        block.setFixedWidth(520)
        bl = QVBoxLayout(block)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(22)
        # Pemusatan vertikal dilakukan DI DALAM block (stretch atas/bawah) sementara
        # block mengisi penuh tinggi pane — jadi item teks selalu mendapat tinggi
        # penuhnya dan tidak pernah tertekan (mencegah descender terpotong).
        bl.addStretch(1)
        bl.addWidget(_label(eyebrow, 12, 700, CLR_ACCENT_TEXT, ls=2))
        bl.addWidget(_label(title, 38, 800, CLR_TEXT_MAIN, wrap=True, ls=-0.6, max_w=520))
        bl.addWidget(_label(body, 16, 500, CLR_TEXT_MUTED, wrap=True, max_w=480))
        bl.addWidget(self._supporting(step))
        bl.addStretch(1)

        # Rata kiri via HBox + stretch; block_row diberi faktor stretch agar block
        # mengisi seluruh ruang vertikal yang tersisa.
        block_row = QHBoxLayout()
        block_row.setContentsMargins(0, 0, 0, 0)
        block_row.addWidget(block)
        block_row.addStretch(1)
        v.addLayout(block_row, 1)
        return pane

    def _supporting(self, step: int) -> QWidget:
        if step == 1:
            holder = QWidget()
            holder.setStyleSheet("background:transparent;")
            row = QHBoxLayout(holder)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(10)
            for text in ("No sign-up", "Works fully offline", "Open .adtn format"):
                row.addWidget(_chip(text))
            row.addStretch(1)
            return holder
        if step == 2:
            return _list_card(
                [
                    (
                        "mdi6.shield-outline",
                        "AES-256-GCM",
                        "Authenticated encryption for every byte",
                    ),
                    (
                        "mdi6.key-outline",
                        "Argon2id key protection",
                        "Slow, memory-hard defence against guessing",
                    ),
                    (
                        "mdi6.web-off",
                        "No network access",
                        "Adyton never opens a connection",
                    ),
                ]
            )
        if step == 3:
            return _list_card(
                [
                    (
                        "mdi6.lock-outline",
                        "Lock Folder",
                        "Pack a whole folder into one .adtn vault",
                    ),
                    (
                        "mdi6.lock-open-variant-outline",
                        "Open Vault",
                        "Reopen and extract a vault you locked before",
                    ),
                    (
                        "mdi6.text-box-outline",
                        "Encrypt Text",
                        "Turn a private note into a shareable cipher",
                    ),
                ]
            )
        # step 4 — dua baris pemberitahuan
        holder = QWidget()
        holder.setStyleSheet("background:transparent;")
        col = QVBoxLayout(holder)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(12)
        col.addWidget(
            _notice_row(
                "mdi6.check-circle-outline",
                CLR_SUCCESS,
                SUCCESS_RGB,
                "Strong encryption, ready to go",
                "AES-256-GCM and Argon2id, fully on this device.",
            )
        )
        col.addWidget(
            _notice_row(
                "mdi6.alert-outline",
                CLR_WARN,
                WARN_RGB,
                "Your password can't be recovered",
                "If you lose it, the data is gone for good — store it safely.",
            )
        )
        return holder

    # --- footer navigasi (step 1–4) ---
    def _build_footer(self) -> QWidget:
        footer = QFrame()
        footer.setObjectName("OnbFooter")
        footer.setFixedHeight(84)
        footer.setStyleSheet(
            f"#OnbFooter {{ background:{CLR_INSET}; border-top:1px solid {CLR_LINE}; }}"
        )
        grid = QGridLayout(footer)
        grid.setContentsMargins(40, 0, 40, 0)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 1)

        self._back_pill = _HoverPill(
            "Back",
            height=46,
            pad_h=18,
            radius=23,
            normal_bg=CLR_WINDOW,
            hover_bg=CLR_WINDOW,
            normal_border=CLR_INPUT_BORDER,
            fg=CLR_TEXT_MUTED,
            font_px=13.5,
            font_weight=600,
            icon_left="mdi6.arrow-left",
            icon_px=15,
            icon_color=CLR_TEXT_MUTED,
            gap=8,
        )
        self._back_pill.clicked.connect(self._back)
        grid.addWidget(self._back_pill, 0, 0, alignment=Qt.AlignmentFlag.AlignLeft)

        self._dots = _StepDots(4)
        grid.addWidget(self._dots, 0, 1, alignment=Qt.AlignmentFlag.AlignCenter)

        right = QWidget()
        right.setStyleSheet("background:transparent;")
        rl = QHBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(18)
        rl.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._skip_pill = _HoverPill(
            "Skip tour",
            height=24,
            pad_h=0,
            radius=0,
            normal_bg="transparent",
            hover_bg="transparent",
            fg=CLR_MONO_META,
            fg_hover=CLR_TEXT_MUTED,
            font_px=13,
            font_weight=600,
        )
        self._skip_pill.clicked.connect(self._skip)
        rl.addWidget(self._skip_pill)

        self._next_pill = _PrimaryPill("Continue")
        self._next_pill.clicked.connect(self._next)
        rl.addWidget(self._next_pill)

        grid.addWidget(right, 0, 2, alignment=Qt.AlignmentFlag.AlignRight)
        return footer

    # --- halaman: done ---
    def _build_done(self) -> QWidget:
        page = _GlowBg(0.5, 0.40, 0.08, 0.58)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addStretch(1)

        # Container lebar tetap 460 dipusatkan horizontal — lebar pasti agar body
        # multi-baris menghitung tinggi wrap dengan benar (tidak menumpuk).
        hrow = QHBoxLayout()
        hrow.setContentsMargins(0, 0, 0, 0)
        hrow.addStretch(1)
        container = QWidget()
        container.setStyleSheet("background:transparent;")
        container.setFixedWidth(460)
        hrow.addWidget(container)
        hrow.addStretch(1)
        outer.addLayout(hrow)
        outer.addStretch(1)

        col = QVBoxLayout(container)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(22)

        tile = _icon_tile(
            92,
            "mdi6.check",
            46,
            28,
            tint_a=0.12,
            border_a=0.28,
            rgb=SUCCESS_RGB,
            icon_color=CLR_SUCCESS,
        )
        col.addWidget(
            _overlay(_PulsingRing(120, _qcolor(_SUCCESS_QRGB, 0.30), 2800, 0), tile),
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )

        heading = _label(
            "You're all set", 30, 800, CLR_TEXT_MAIN, ls=-0.5, align=Qt.AlignmentFlag.AlignCenter
        )
        col.addWidget(heading)

        body = _label(
            "Adyton Crypt is ready. From here the app opens to your tools — "
            "lock your first folder whenever you are.",
            15,
            500,
            CLR_TEXT_MUTED,
            wrap=True,
            align=Qt.AlignmentFlag.AlignCenter,
            max_w=460,
        )
        col.addWidget(body)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.setAlignment(Qt.AlignmentFlag.AlignCenter)

        replay = _HoverPill(
            "Replay introduction",
            height=48,
            pad_h=22,
            radius=24,
            normal_bg=CLR_INSET,
            hover_bg=CLR_HOVER_BG,
            normal_border=CLR_INPUT_BORDER,
            hover_border=CLR_BORDER,
            fg=CLR_TEXT_MUTED,
            font_px=13.5,
            font_weight=600,
            icon_left="mdi6.refresh",
            icon_px=15,
            icon_color=CLR_TEXT_MUTED,
            gap=9,
        )
        replay.clicked.connect(self._replay)
        buttons.addWidget(replay)

        open_app = _PrimaryPill("Open Adyton Crypt", height=48)
        open_app.clicked.connect(self._finish)
        buttons.addWidget(open_app)

        col.addLayout(buttons)
        return page


class _PrimaryPill(_HoverPill):
    """Pill CTA aksen (Continue / Get Started / Open Adyton Crypt) dengan panah kanan."""

    def __init__(self, text: str, height: int = 50, parent=None):
        super().__init__(
            text,
            height=height,
            pad_h=26,
            radius=height // 2,
            normal_bg=CLR_ACCENT,
            hover_bg=CLR_ACCENT_HOVER,
            fg=CLR_ON_ACCENT,
            font_px=14,
            font_weight=700,
            icon_right="mdi6.arrow-right",
            icon_px=16,
            icon_color=CLR_ON_ACCENT,
            gap=10,
            parent=parent,
        )

    def set_text(self, text: str) -> None:
        self._lbl.setText(text)
