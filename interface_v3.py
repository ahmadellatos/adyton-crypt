# Requirements: pip install customtkinter cryptography
# Python 3.10+

import customtkinter as ctk
from tkinter import filedialog
import threading
import re

from engine import kunci_brankas_logic, buka_brankas_logic

# ── Theme ─────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Design Tokens ─────────────────────────────────────────────────────────────
FONT_TITLE = ("Segoe UI", 15, "bold")
FONT_LABEL = ("Segoe UI", 11, "bold")
FONT_SMALL = ("Segoe UI", 10)
FONT_BTN   = ("Segoe UI", 12, "bold")

CLR_CARD      = "#1E2235"
CLR_INNER     = "#161824"
CLR_ACCENT    = "#00C6BE"
CLR_ACCENT_HV = "#009E96"
CLR_DANGER    = "#C0392B"
CLR_DANGER_HV = "#A93226"
CLR_MUTED     = "#6B7280"
CLR_BORDER    = "#2D3452"

CLR_NOTIF_OK   = ("#0D2B1E", "#1DB954")
CLR_NOTIF_ERR  = ("#2B0D0D", "#E74C3C")
CLR_NOTIF_WARN = ("#2B1E0D", "#F39C12")

STRENGTH_COLORS = ["#E74C3C", "#E67E22", "#F1C40F", "#2ECC71"]
STRENGTH_LABELS = ["Lemah", "Cukup", "Kuat", "Sangat Kuat"]


def _pw_strength(pw: str) -> int:
    if not pw:
        return -1
    score = 0
    if len(pw) >= 8:
        score += 1
    if re.search(r"[A-Z]", pw) and re.search(r"[a-z]", pw):
        score += 1
    if re.search(r"\d", pw):
        score += 1
    if re.search(r"[!@#$%^&*()\-_=+\[\]{};:'\",.<>/?\\|`~]", pw):
        score += 1
    return min(score, 3)


class NotifBar(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(
            parent, height=40, corner_radius=8,
            fg_color="transparent", **kwargs
        )
        self.lbl = ctk.CTkLabel(
            self, text="", font=("Segoe UI", 11),
            wraplength=380, anchor="center"
        )
        self.lbl.place(relx=0.5, rely=0.5, anchor="center")

    def show(self, kind: str, msg: str):
        bg, fg = {
            "ok":   CLR_NOTIF_OK,
            "err":  CLR_NOTIF_ERR,
            "warn": CLR_NOTIF_WARN,
        }.get(kind, ("transparent", CLR_MUTED))
        self.configure(fg_color=bg)
        self.lbl.configure(text=msg, text_color=fg)

    def clear(self):
        self.configure(fg_color="transparent")
        self.lbl.configure(text="")


def make_card(parent, padx=20, pady=(0, 12)):
    f = ctk.CTkFrame(parent, fg_color=CLR_CARD, corner_radius=10)
    f.pack(fill="x", padx=padx, pady=pady)
    return f


class AppBrankas(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Digital Locker — Professional")
        self.configure(fg_color="#12141F")

        w, h = 500, 680 # Diperbesar sedikit untuk checkbox hapus asli
        sw, self.winfo_screenwidth(), sh, self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(self.winfo_screenwidth() - w) // 2}+{(self.winfo_screenheight() - h) // 2}")
        self.resizable(False, False)

        # ── App Header ──
        hdr = ctk.CTkFrame(self, fg_color="#12141F", height=56)
        hdr.pack(fill="x", padx=20, pady=(12, 0))
        hdr.pack_propagate(False)
        ctk.CTkLabel(
            hdr, text="🔐  Digital Locker",
            font=("Segoe UI", 18, "bold"), text_color=CLR_ACCENT
        ).pack(side="left", pady=8)
        ctk.CTkLabel(
            hdr, text="AES-256 · GCM",
            font=("Segoe UI", 10), text_color=CLR_MUTED
        ).pack(side="right", pady=8)

        ctk.CTkFrame(self, fg_color=CLR_BORDER, height=1).pack(fill="x", padx=20, pady=(0, 4))

        # ── TabView ──
        self.tabview = ctk.CTkTabview(
            self, width=470, height=588, corner_radius=12,
            fg_color="#12141F",
            segmented_button_fg_color="#1E2235",
            segmented_button_selected_color=CLR_ACCENT,
            segmented_button_selected_hover_color=CLR_ACCENT_HV,
            segmented_button_unselected_color="#1E2235",
            segmented_button_unselected_hover_color=CLR_BORDER,
            text_color="#FFFFFF",
            text_color_disabled=CLR_MUTED,
        )
        self.tabview.pack(padx=15, pady=(0, 8))

        self.tab_kunci = self.tabview.add("  🔒  Kunci Folder  ")
        self.tab_buka  = self.tabview.add("  🔓  Buka Brankas  ")

        self.setup_tab_kunci()
        self.setup_tab_buka()

    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 1 — KUNCI FOLDER
    # ═══════════════════════════════════════════════════════════════════════════
    def setup_tab_kunci(self):
        self.path_folder_kunci = None
        self.show_pw_v1 = False
        self.var_hapus_asli = ctk.BooleanVar(value=False) # Variable Checkbox

        # Card 1: Folder picker
        c1 = make_card(self.tab_kunci)
        ctk.CTkLabel(c1, text="📁  FOLDER TARGET", font=FONT_LABEL,
                     text_color=CLR_MUTED).pack(anchor="w", padx=14, pady=(10, 6))

        row_f = ctk.CTkFrame(c1, fg_color="transparent")
        row_f.pack(fill="x", padx=14, pady=(0, 10))

        self.btn_browse_kunci = ctk.CTkButton(
            row_f, text="Browse Folder", font=FONT_BTN,
            height=36, corner_radius=8,
            fg_color=CLR_ACCENT, hover_color=CLR_ACCENT_HV, text_color="#000000",
            command=self.pilih_folder
        )
        self.btn_browse_kunci.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.btn_clear_kunci = ctk.CTkButton(
            row_f, text="✖", width=36, height=36,
            fg_color=CLR_BORDER, hover_color="#3D4562", font=("Segoe UI", 11),
            command=self.clear_pilihan_kunci
        )

        self.lbl_path_folder = ctk.CTkLabel(
            c1, text="Belum ada folder dipilih",
            font=FONT_SMALL, text_color=CLR_MUTED, wraplength=390, anchor="w"
        )
        self.lbl_path_folder.pack(anchor="w", padx=14, pady=(0, 6))

        # Checkbox Hapus Folder Asli
        self.chk_hapus_asli = ctk.CTkCheckBox(
            c1, text="Hapus folder asli setelah dikunci (Secure Wipe)",
            font=FONT_SMALL, text_color=CLR_MUTED, 
            variable=self.var_hapus_asli,
            fg_color=CLR_DANGER, hover_color=CLR_DANGER_HV, corner_radius=4,
            checkbox_width=18, checkbox_height=18
        )
        self.chk_hapus_asli.pack(anchor="w", padx=14, pady=(0, 12))

        # Card 2: Password
        c2 = make_card(self.tab_kunci)
        ctk.CTkLabel(c2, text="🔑  BUAT PASSWORD", font=FONT_LABEL,
                     text_color=CLR_MUTED).pack(anchor="w", padx=14, pady=(10, 6))

        self.row_pw = ctk.CTkFrame(c2, fg_color="transparent")
        self.row_pw.pack(fill="x", padx=14)

        self.entry_pw_kunci = ctk.CTkEntry(
            self.row_pw, placeholder_text="Buat password kuat…",
            show="*", height=36, corner_radius=8,
            fg_color=CLR_INNER, border_color=CLR_BORDER, border_width=1
        )
        self.entry_pw_kunci.pack(side="left", expand=True, fill="x")
        self.entry_pw_kunci.bind("<KeyRelease>", self._on_pw_kunci_change)

        ctk.CTkButton(
            self.row_pw, text="👁", width=36, height=36,
            fg_color="transparent", hover_color=CLR_CARD,
            command=self.toggle_pw_kunci
        ).pack(side="right", padx=(6, 0))

        self.row_str = ctk.CTkFrame(c2, fg_color="transparent")
        self.strength_bar = ctk.CTkProgressBar(self.row_str, height=5, corner_radius=3)
        self.strength_bar.set(0)
        self.strength_bar.pack(side="left", expand=True, fill="x", padx=(0, 8))
        self.lbl_strength = ctk.CTkLabel(
            self.row_str, text="", width=90, font=FONT_SMALL,
            text_color=CLR_MUTED, anchor="e"
        )
        self.lbl_strength.pack(side="right")

        ctk.CTkLabel(c2, text="Konfirmasi Password",
                     font=FONT_SMALL, text_color=CLR_MUTED).pack(
            anchor="w", padx=14, pady=(4, 2)
        )
        row_pc = ctk.CTkFrame(c2, fg_color="transparent")
        row_pc.pack(fill="x", padx=14)
        self.entry_pw_kunci_konfirm = ctk.CTkEntry(
            row_pc, placeholder_text="Ulangi password…",
            show="*", height=36, corner_radius=8,
            fg_color=CLR_INNER, border_color=CLR_BORDER, border_width=1
        )
        self.entry_pw_kunci_konfirm.pack(fill="x")
        self.entry_pw_kunci_konfirm.bind("<KeyRelease>", self._on_konfirm_change)
        self.entry_pw_kunci_konfirm.bind("<Return>", lambda e: self.proses_kunci())

        self.lbl_match = ctk.CTkLabel(c2, text="", font=FONT_SMALL, anchor="e")
        self.lbl_match.pack(anchor="e", padx=14, pady=(4, 10))

        self.progress_kunci = ctk.CTkProgressBar(
            self.tab_kunci, mode="indeterminate", height=5,
            progress_color=CLR_ACCENT
        )

        self.btn_eksekusi_kunci = ctk.CTkButton(
            self.tab_kunci, text="KUNCI SEKARANG",
            font=FONT_BTN, height=42, corner_radius=10,
            fg_color=CLR_ACCENT, hover_color=CLR_ACCENT_HV, text_color="#000000",
            command=self.proses_kunci
        )
        self.btn_eksekusi_kunci.pack(fill="x", padx=20, pady=(6, 8))

        self.notif_kunci = NotifBar(self.tab_kunci)
        self.notif_kunci.pack(fill="x", padx=20, ipady=6)

    def _on_pw_kunci_change(self, _=None):
        pw = self.entry_pw_kunci.get()
        s  = _pw_strength(pw)
        if s < 0:
            self.row_str.pack_forget()
            self.strength_bar.set(0)
            self.lbl_strength.configure(text="")
        else:
            self.row_str.pack(after=self.row_pw, fill="x", padx=14, pady=(6, 4))
            self.strength_bar.set((s + 1) / 4)
            self.strength_bar.configure(progress_color=STRENGTH_COLORS[s])
            self.lbl_strength.configure(
                text=STRENGTH_LABELS[s], text_color=STRENGTH_COLORS[s]
            )
        self._on_konfirm_change()
        self.notif_kunci.clear()

    def _on_konfirm_change(self, _=None):
        pw1, pw2 = self.entry_pw_kunci.get(), self.entry_pw_kunci_konfirm.get()
        if not pw2:
            self.lbl_match.configure(text="")
        elif pw1 == pw2:
            self.lbl_match.configure(text="✔  Cocok", text_color="#2ECC71")
        else:
            self.lbl_match.configure(text="✖  Belum cocok", text_color="#E74C3C")

    def toggle_pw_kunci(self):
        self.show_pw_v1 = not self.show_pw_v1
        c = "" if self.show_pw_v1 else "*"
        self.entry_pw_kunci.configure(show=c)
        self.entry_pw_kunci_konfirm.configure(show=c)

    def clear_pilihan_kunci(self):
        self.path_folder_kunci = None
        self.lbl_path_folder.configure(text="Belum ada folder dipilih", text_color=CLR_MUTED)
        self.btn_clear_kunci.pack_forget()

    def pilih_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.path_folder_kunci = folder
            tampil = folder if len(folder) < 50 else "…" + folder[-47:]
            self.lbl_path_folder.configure(text=tampil, text_color=CLR_ACCENT)
            self.btn_clear_kunci.pack(side="right", padx=(6, 0))
            self.notif_kunci.clear()

    def proses_kunci(self):
        if not self.path_folder_kunci:
            self.notif_kunci.show("warn", "⚠  Pilih folder dulu!")
            return
        pw, pw2 = self.entry_pw_kunci.get(), self.entry_pw_kunci_konfirm.get()
        if not pw:
            self.notif_kunci.show("warn", "⚠  Password tidak boleh kosong!")
            return
        if pw != pw2:
            self.notif_kunci.show("warn", "⚠  Password tidak cocok!")
            return

        path_snap, pw_snap = self.path_folder_kunci, pw
        hapus_snap = self.var_hapus_asli.get() # Ambil status checkbox
        
        self._busy_kunci(True)
        threading.Thread(
            target=lambda: self.after(
                0, lambda: self._selesai_kunci(*kunci_brankas_logic(path_snap, pw_snap, hapus_snap))
            ),
            daemon=True
        ).start()

    def _busy_kunci(self, on: bool):
        if on:
            self.btn_eksekusi_kunci.configure(state="disabled", text="⏳  Memproses…")
            self.btn_browse_kunci.configure(state="disabled")
            self.chk_hapus_asli.configure(state="disabled")
            self.progress_kunci.pack(fill="x", padx=20, pady=(0, 4))
            self.progress_kunci.start()
        else:
            self.progress_kunci.stop()
            self.progress_kunci.pack_forget()
            self.btn_eksekusi_kunci.configure(state="normal", text="KUNCI SEKARANG")
            self.btn_browse_kunci.configure(state="normal")
            self.chk_hapus_asli.configure(state="normal")

    def _selesai_kunci(self, sukses: bool, pesan: str):
        self._busy_kunci(False)
        if sukses:
            self.notif_kunci.show("ok", "✔  " + pesan)
            self.entry_pw_kunci.delete(0, "end")
            self.entry_pw_kunci_konfirm.delete(0, "end")
            self.lbl_match.configure(text="")
            self.strength_bar.set(0)
            self.lbl_strength.configure(text="")
            self.row_str.pack_forget()
            self.var_hapus_asli.set(False) # Reset checkbox
            self.clear_pilihan_kunci()
        else:
            self.notif_kunci.show("err", "✖  " + pesan)

    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 2 — BUKA BRANKAS
    # ═══════════════════════════════════════════════════════════════════════════
    def setup_tab_buka(self):
        self.path_file_buka            = None
        self.show_pw_v2                = False
        self.menunggu_konfirmasi_timpa = False

        ctk.CTkLabel(
            self.tab_buka,
            text="Masukkan file .locked dan password untuk membuka",
            font=FONT_SMALL, text_color=CLR_MUTED
        ).pack(pady=(10, 12))

        c1 = make_card(self.tab_buka)
        ctk.CTkLabel(c1, text="📄  FILE BRANKAS (.locked)", font=FONT_LABEL,
                     text_color=CLR_MUTED).pack(anchor="w", padx=14, pady=(10, 6))

        row_f = ctk.CTkFrame(c1, fg_color="transparent")
        row_f.pack(fill="x", padx=14, pady=(0, 10))

        self.btn_browse_buka = ctk.CTkButton(
            row_f, text="Browse  .locked", font=FONT_BTN,
            height=36, corner_radius=8,
            fg_color=CLR_ACCENT, hover_color=CLR_ACCENT_HV, text_color="#000000",
            command=self.pilih_file
        )
        self.btn_browse_buka.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.btn_clear_buka = ctk.CTkButton(
            row_f, text="✖", width=36, height=36,
            fg_color=CLR_BORDER, hover_color="#3D4562", font=("Segoe UI", 11),
            command=self.clear_pilihan_buka
        )

        self.lbl_path_file = ctk.CTkLabel(
            c1, text="File belum dipilih",
            font=FONT_SMALL, text_color=CLR_MUTED, wraplength=390, anchor="w"
        )
        self.lbl_path_file.pack(anchor="w", padx=14, pady=(0, 10))

        c2 = make_card(self.tab_buka)
        ctk.CTkLabel(c2, text="🔑  MASUKKAN PASSWORD", font=FONT_LABEL,
                     text_color=CLR_MUTED).pack(anchor="w", padx=14, pady=(10, 6))

        row_pw = ctk.CTkFrame(c2, fg_color="transparent")
        row_pw.pack(fill="x", padx=14, pady=(0, 14))

        self.entry_pw_buka = ctk.CTkEntry(
            row_pw, placeholder_text="Ketik password di sini…",
            show="*", height=36, corner_radius=8,
            fg_color=CLR_INNER, border_color=CLR_BORDER, border_width=1
        )
        self.entry_pw_buka.pack(side="left", expand=True, fill="x")
        self.entry_pw_buka.bind("<Return>", lambda e: self.proses_buka())
        self.entry_pw_buka.bind("<KeyRelease>", lambda e: self.notif_buka.clear())

        ctk.CTkButton(
            row_pw, text="👁", width=36, height=36,
            fg_color="transparent", hover_color=CLR_CARD,
            command=self.toggle_pw_buka
        ).pack(side="right", padx=(6, 0))

        self.progress_buka = ctk.CTkProgressBar(
            self.tab_buka, mode="indeterminate", height=5,
            progress_color=CLR_ACCENT
        )

        self.btn_eksekusi_buka = ctk.CTkButton(
            self.tab_buka, text="BUKA BRANKAS",
            font=FONT_BTN, height=42, corner_radius=10,
            fg_color=CLR_ACCENT, hover_color=CLR_ACCENT_HV, text_color="#000000",
            command=self.proses_buka
        )
        self.btn_eksekusi_buka.pack(fill="x", padx=20, pady=(6, 8))

        self.notif_buka = NotifBar(self.tab_buka)
        self.notif_buka.pack(fill="x", padx=20, ipady=6)

    def toggle_pw_buka(self):
        self.show_pw_v2 = not self.show_pw_v2
        self.entry_pw_buka.configure(show="" if self.show_pw_v2 else "*")

    def clear_pilihan_buka(self):
        self.path_file_buka = None
        self.lbl_path_file.configure(text="File belum dipilih", text_color=CLR_MUTED)
        self.btn_clear_buka.pack_forget()
        self._reset_timpa()

    def pilih_file(self):
        f = filedialog.askopenfilename(filetypes=[("Locked Files", "*.locked")])
        if f:
            self.path_file_buka = f
            tampil = f if len(f) < 50 else "…" + f[-47:]
            self.lbl_path_file.configure(text=tampil, text_color=CLR_ACCENT)
            self.btn_clear_buka.pack(side="right", padx=(6, 0))
            self.notif_buka.clear()
            self._reset_timpa()

    def _reset_timpa(self):
        self.menunggu_konfirmasi_timpa = False
        self.btn_eksekusi_buka.configure(
            text="BUKA BRANKAS",
            fg_color=CLR_ACCENT, hover_color=CLR_ACCENT_HV, text_color="#000000"
        )

    def proses_buka(self):
        force = False
        if self.menunggu_konfirmasi_timpa:
            force = True
            self._reset_timpa()

        if not self.path_file_buka:
            self.notif_buka.show("warn", "⚠  Pilih file .locked dulu!")
            return
        pw = self.entry_pw_buka.get()
        if not pw:
            self.notif_buka.show("warn", "⚠  Masukkan password!")
            return

        path_snap, pw_snap = self.path_file_buka, pw
        self._busy_buka(True)
        threading.Thread(
            target=lambda: self.after(
                0, lambda: self._selesai_buka(*buka_brankas_logic(path_snap, pw_snap, force))
            ),
            daemon=True
        ).start()

    def _busy_buka(self, on: bool):
        if on:
            self.btn_eksekusi_buka.configure(state="disabled", text="⏳  Membuka…")
            self.btn_browse_buka.configure(state="disabled")
            self.progress_buka.pack(fill="x", padx=20, pady=(0, 4))
            self.progress_buka.start()
        else:
            self.progress_buka.stop()
            self.progress_buka.pack_forget()
            self.btn_eksekusi_buka.configure(state="normal")
            self.btn_browse_buka.configure(state="normal")

    def _selesai_buka(self, status: str, msg):
        self._busy_buka(False)

        if status == "SUCCESS":
            self.notif_buka.show("ok", f"✔  Folder '{msg}' berhasil dikembalikan!")
            self.entry_pw_buka.delete(0, "end")
            self.clear_pilihan_buka()

        elif status == "WRONG_PW":
            self.notif_buka.show("err", "✖  Password salah! Coba lagi.")
            self.btn_eksekusi_buka.configure(text="BUKA BRANKAS")

        elif status == "OVERWRITE":
            self.menunggu_konfirmasi_timpa = True
            self.btn_eksekusi_buka.configure(
                text="⚠  KLIK LAGI UNTUK TIMPA",
                fg_color=CLR_DANGER, hover_color=CLR_DANGER_HV,
                text_color="#FFFFFF"
            )
            self.notif_buka.show("warn", f"⚠  Folder '{msg}' sudah ada! Klik tombol lagi untuk menimpa.")

        else:
            self.notif_buka.show("err", f"✖  Error: {msg}")

if __name__ == "__main__":
    app = AppBrankas()
    app.mainloop()