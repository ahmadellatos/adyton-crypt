"""
ui/theme.py
Semua konstanta warna, font, dan token desain.
Ubah di sini untuk ganti tema keseluruhan aplikasi.
"""
import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Fonts ─────────────────────────────────────────────────────────────────────
FONT_TITLE = ("Segoe UI", 18, "bold")
FONT_LABEL = ("Segoe UI", 11, "bold")
FONT_BODY  = ("Segoe UI", 11)
FONT_SMALL = ("Segoe UI", 10)
FONT_BTN   = ("Segoe UI", 12, "bold")

# ── Colors ────────────────────────────────────────────────────────────────────
CLR_BG        = "#12141F"
CLR_CARD      = "#1E2235"
CLR_INNER     = "#161824"
CLR_ACCENT    = "#00C6BE"
CLR_ACCENT_HV = "#009E96"
CLR_DANGER    = "#C0392B"
CLR_DANGER_HV = "#A93226"
CLR_MUTED     = "#6B7280"
CLR_BORDER    = "#2D3452"
CLR_BORDER_DRAG = CLR_ACCENT

CLR_CARD_HOVER = "#252B42"   # Hover background saat drag masuk ke card
CLR_HOVER_BTN  = "#3D4562"   # Hover tombol sekunder (✕, OptionMenu, dll)
CLR_SEGMENTED  = "#1E2235"   # Background tab selector (segmented button)
CLR_MATCH_OK   = "#2ECC71"   # Indikator password cocok
CLR_MATCH_ERR  = "#E74C3C"   # Indikator password belum cocok

CLR_NOTIF_OK   = ("#0D2B1E", "#1DB954")   # (bg, text)
CLR_NOTIF_ERR  = ("#2B0D0D", "#E74C3C")
CLR_NOTIF_WARN = ("#2B1E0D", "#F39C12")

# ── Password Strength ─────────────────────────────────────────────────────────
STRENGTH_COLORS = ["#E74C3C", "#E67E22", "#F1C40F", "#2ECC71"]
STRENGTH_LABELS = ["Lemah", "Cukup", "Kuat", "Sangat Kuat"]