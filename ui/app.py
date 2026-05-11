"""
ui/app.py
Jendela utama aplikasi.
Sekarang menggunakan orientasi Horizontal (Landscape).
"""
import customtkinter as ctk

from .dnd import DND_AVAILABLE, TkinterDnD
from .theme import FONT_TITLE, CLR_BG, CLR_ACCENT, CLR_ACCENT_HV, CLR_MUTED, CLR_BORDER
from .tab_kunci import TabKunci
from .tab_buka import TabBuka

if DND_AVAILABLE:
    class _AppBase(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self):
            super().__init__()
            self.TkdndVersion = TkinterDnD._require(self)
else:
    class _AppBase(ctk.CTk):
        def __init__(self):
            super().__init__()

class AppBrankas(_AppBase):
    def __init__(self):
        super().__init__()
        self.title("Digital Locker — Professional")
        self.configure(fg_color=CLR_BG)
        self.resizable(False, False)

        # ── WINDOW DIBIKIN HORIZONTAL (LANDSCAPE) ──
        w, h = 880, 480 
        self.geometry(
            f"{w}x{h}"
            f"+{(self.winfo_screenwidth()  - w) // 2}"
            f"+{(self.winfo_screenheight() - h) // 2}"
        )

        self._build_header()
        self._build_tabs()

    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=CLR_BG, height=56)
        hdr.pack(fill="x", padx=20, pady=(12, 0))
        hdr.pack_propagate(False)

        ctk.CTkLabel(
            hdr, text="🔐  Digital Locker",
            font=FONT_TITLE, text_color=CLR_ACCENT,
        ).pack(side="left", pady=8)

        ctk.CTkLabel(
            hdr, text="AES-256 · GCM",
            font=("Segoe UI", 10), text_color=CLR_MUTED,
        ).pack(side="right", pady=8)

        ctk.CTkFrame(self, fg_color=CLR_BORDER, height=1).pack(
            fill="x", padx=20, pady=(0, 4)
        )

    def _build_tabs(self):
        # Tabview dilebarkan
        tabview = ctk.CTkTabview(
            self, width=840, height=390, corner_radius=12,
            fg_color=CLR_BG,
            segmented_button_fg_color="#1E2235",
            segmented_button_selected_color=CLR_ACCENT,
            segmented_button_selected_hover_color=CLR_ACCENT_HV,
            segmented_button_unselected_color="#1E2235",
            segmented_button_unselected_hover_color=CLR_BORDER,
            text_color="#FFFFFF",
            text_color_disabled=CLR_MUTED,
        )
        tabview.pack(padx=15, pady=(0, 8))

        tab_k = tabview.add("  🔒  Kunci Folder  ")
        tab_b = tabview.add("  🔓  Buka Brankas  ")

        TabKunci(tab_k).pack(fill="both", expand=True)
        TabBuka(tab_b).pack(fill="both", expand=True)