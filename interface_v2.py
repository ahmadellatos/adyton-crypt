import customtkinter as ctk
from tkinter import filedialog
import threading
import re

from engine import kunci_brankas_logic, buka_brankas_logic

# ── Global Theme ──────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Palette Constants ─────────────────────────────────────────────────────────
CLR_SUCCESS  = "#2ECC71"
CLR_WARNING  = "#E67E22"
CLR_ERROR    = "#E74C3C"
CLR_INFO     = "#1f6aa5"
CLR_MUTED    = "gray"
CLR_DARK_BTN = "#2A2A2A"
CLR_HOVER    = "#404040"

STRENGTH_COLORS = ["#E74C3C", "#E67E22", "#F1C40F", "#2ECC71"]
STRENGTH_LABELS = ["Lemah", "Cukup", "Kuat", "Sangat Kuat"]


# ── Helper: Password Strength (0-3) ───────────────────────────────────────────
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
    if re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]", pw):
        score += 1
    # Cap to 3 for indexing
    return min(score, 3)


# ── Main Application ──────────────────────────────────────────────────────────
class AppBrankas(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Digital Locker - Professional")

        # ── Center window ──
        app_width, app_height = 500, 620
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{app_width}x{app_height}+{int(sw/2 - app_width/2)}+{int(sh/2 - app_height/2)}")
        self.resizable(False, False)

        # ── Tab View ──
        self.tabview = ctk.CTkTabview(self, width=465, height=580, corner_radius=15)
        self.tabview.pack(padx=18, pady=10)
        self.tab_kunci = self.tabview.add("🔒  Kunci Folder")
        self.tab_buka  = self.tabview.add("🔓  Buka Brankas")

        self.setup_tab_kunci()
        self.setup_tab_buka()

    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 1 — KUNCI FOLDER
    # ═══════════════════════════════════════════════════════════════════════════
    def setup_tab_kunci(self):
        self.path_folder_kunci = None
        self.show_pw_v1        = False

        # Header
        ctk.CTkLabel(
            self.tab_kunci,
            text="Pilih Folder untuk Diamankan",
            font=("Arial", 16, "bold")
        ).pack(pady=(15, 8))

        # ── Folder picker row ──
        row_folder = ctk.CTkFrame(self.tab_kunci, fg_color="transparent")
        row_folder.pack(fill="x", padx=30)

        self.btn_browse_kunci = ctk.CTkButton(
            row_folder, text="📂 Browse Folder",
            command=self.pilih_folder, corner_radius=8
        )
        self.btn_browse_kunci.pack(side="left", expand=True, fill="x", padx=(0, 5))

        self.btn_clear_kunci = ctk.CTkButton(
            row_folder, text="✖", width=35,
            fg_color=CLR_DARK_BTN, hover_color=CLR_HOVER,
            command=self.clear_pilihan_kunci
        )
        # Hidden until folder is selected

        self.lbl_path_folder = ctk.CTkLabel(
            self.tab_kunci,
            text="Belum ada folder dipilih",
            text_color=CLR_MUTED, font=("Arial", 11),
            wraplength=400
        )
        self.lbl_path_folder.pack(pady=(3, 10))

        # ── Password field ──
        ctk.CTkLabel(
            self.tab_kunci, text="Password Brankas",
            font=("Arial", 12, "bold")
        ).pack(anchor="w", padx=35)

        row_pw1 = ctk.CTkFrame(self.tab_kunci, fg_color="transparent")
        row_pw1.pack(fill="x", padx=30, pady=(0, 4))

        self.entry_pw_kunci = ctk.CTkEntry(
            row_pw1, placeholder_text="Buat password kuat...",
            show="*", height=35, corner_radius=8
        )
        self.entry_pw_kunci.pack(side="left", expand=True, fill="x")
        self.entry_pw_kunci.bind("<KeyRelease>", self._on_pw_kunci_change)

        ctk.CTkButton(
            row_pw1, text="👁", width=35, height=35,
            fg_color="transparent", hover_color=CLR_HOVER,
            command=self.toggle_pw_kunci
        ).pack(side="right", padx=(5, 0))

        # ── Strength meter ──
        self.frame_strength = ctk.CTkFrame(self.tab_kunci, fg_color="transparent")
        self.frame_strength.pack(fill="x", padx=30, pady=(0, 8))

        self.strength_bar = ctk.CTkProgressBar(
            self.frame_strength, height=6, corner_radius=4
        )
        self.strength_bar.set(0)
        self.strength_bar.pack(side="left", expand=True, fill="x", padx=(0, 8))

        self.lbl_strength = ctk.CTkLabel(
            self.frame_strength, text="", width=80,
            font=("Arial", 10), text_color=CLR_MUTED
        )
        self.lbl_strength.pack(side="right")

        # ── Confirm password ──
        ctk.CTkLabel(
            self.tab_kunci, text="Konfirmasi Password",
            font=("Arial", 12, "bold")
        ).pack(anchor="w", padx=35)

        row_pw1c = ctk.CTkFrame(self.tab_kunci, fg_color="transparent")
        row_pw1c.pack(fill="x", padx=30, pady=(0, 4))

        self.entry_pw_kunci_konfirm = ctk.CTkEntry(
            row_pw1c, placeholder_text="Ulangi password...",
            show="*", height=35, corner_radius=8
        )
        self.entry_pw_kunci_konfirm.pack(side="left", expand=True, fill="x")
        self.entry_pw_kunci_konfirm.bind("<KeyRelease>", self._on_konfirm_change)
        self.entry_pw_kunci_konfirm.bind("<Return>", lambda e: self.proses_kunci())

        # Match indicator label
        self.lbl_match = ctk.CTkLabel(
            self.tab_kunci, text="",
            font=("Arial", 10), text_color=CLR_MUTED
        )
        self.lbl_match.pack(anchor="e", padx=35, pady=(0, 10))

        # ── Progress bar (hidden by default) ──
        self.progress_kunci = ctk.CTkProgressBar(self.tab_kunci, mode="indeterminate", height=6)

        # ── Action button ──
        self.btn_eksekusi_kunci = ctk.CTkButton(
            self.tab_kunci,
            text="KUNCI SEKARANG",
            font=("Arial", 13, "bold"),
            height=42, corner_radius=10,
            command=self.proses_kunci
        )
        self.btn_eksekusi_kunci.pack(fill="x", padx=30, pady=(8, 6))

        self.lbl_status_kunci = ctk.CTkLabel(
            self.tab_kunci, text="",
            font=("Arial", 12), wraplength=400
        )
        self.lbl_status_kunci.pack(pady=4)

    # ── Live feedback: password strength ──
    def _on_pw_kunci_change(self, _event=None):
        pw    = self.entry_pw_kunci.get()
        score = _pw_strength(pw)
        if score < 0:
            self.strength_bar.set(0)
            self.lbl_strength.configure(text="")
        else:
            self.strength_bar.set((score + 1) / 4)
            self.strength_bar.configure(progress_color=STRENGTH_COLORS[score])
            self.lbl_strength.configure(
                text=STRENGTH_LABELS[score],
                text_color=STRENGTH_COLORS[score]
            )
        # Also re-check match if confirm has content
        self._on_konfirm_change()
        # Clear old status
        self.lbl_status_kunci.configure(text="")

    # ── Live feedback: password match ──
    def _on_konfirm_change(self, _event=None):
        pw1 = self.entry_pw_kunci.get()
        pw2 = self.entry_pw_kunci_konfirm.get()
        if not pw2:
            self.lbl_match.configure(text="")
        elif pw1 == pw2:
            self.lbl_match.configure(text="✔ Password cocok", text_color=CLR_SUCCESS)
        else:
            self.lbl_match.configure(text="✖ Belum cocok", text_color=CLR_ERROR)

    def toggle_pw_kunci(self):
        self.show_pw_v1 = not self.show_pw_v1
        char = "" if self.show_pw_v1 else "*"
        self.entry_pw_kunci.configure(show=char)
        self.entry_pw_kunci_konfirm.configure(show=char)

    def clear_pilihan_kunci(self):
        self.path_folder_kunci = None
        self.lbl_path_folder.configure(text="Belum ada folder dipilih", text_color=CLR_MUTED)
        self.btn_clear_kunci.pack_forget()

    def pilih_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.path_folder_kunci = folder
            tampil = folder if len(folder) < 48 else "..." + folder[-45:]
            self.lbl_path_folder.configure(text=tampil, text_color=CLR_INFO)
            self.btn_clear_kunci.pack(side="right", padx=(5, 0))
            self.lbl_status_kunci.configure(text="")

    def proses_kunci(self):
        if not self.path_folder_kunci:
            self.lbl_status_kunci.configure(text="⚠️ Pilih folder dulu!", text_color=CLR_WARNING)
            return
        pw, pw2 = self.entry_pw_kunci.get(), self.entry_pw_kunci_konfirm.get()
        if not pw:
            self.lbl_status_kunci.configure(text="⚠️ Password tidak boleh kosong!", text_color=CLR_WARNING)
            return
        if pw != pw2:
            self.lbl_status_kunci.configure(text="⚠️ Password tidak cocok!", text_color=CLR_WARNING)
            return

        self._set_busy_kunci(True)
        threading.Thread(
            target=self._run_kunci,
            args=(self.path_folder_kunci, pw),
            daemon=True
        ).start()

    def _set_busy_kunci(self, busy: bool):
        if busy:
            self.btn_eksekusi_kunci.configure(state="disabled", text="⏳ Memproses...")
            self.btn_browse_kunci.configure(state="disabled")
            self.progress_kunci.pack(fill="x", padx=30, pady=(0, 4))
            self.progress_kunci.start()
        else:
            self.progress_kunci.stop()
            self.progress_kunci.pack_forget()
            self.btn_eksekusi_kunci.configure(state="normal", text="KUNCI SEKARANG")
            self.btn_browse_kunci.configure(state="normal")

    def _run_kunci(self, path, pw):
        res, msg = kunci_brankas_logic(path, pw)
        self.after(0, lambda: self._selesai_kunci(res, msg))

    def _selesai_kunci(self, sukses, pesan):
        self._set_busy_kunci(False)
        if sukses:
            self.lbl_status_kunci.configure(text="✔️ " + pesan, text_color=CLR_SUCCESS)
            self.entry_pw_kunci.delete(0, "end")
            self.entry_pw_kunci_konfirm.delete(0, "end")
            self.lbl_match.configure(text="")
            self.strength_bar.set(0)
            self.lbl_strength.configure(text="")
            self.clear_pilihan_kunci()
        else:
            self.lbl_status_kunci.configure(text="❌ " + pesan, text_color=CLR_ERROR)

    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 2 — BUKA BRANKAS
    # ═══════════════════════════════════════════════════════════════════════════
    def setup_tab_buka(self):
        self.path_file_buka             = None
        self.show_pw_v2                 = False
        self.menunggu_konfirmasi_timpa  = False

        ctk.CTkLabel(
            self.tab_buka,
            text="Pilih Brankas untuk Dibongkar",
            font=("Arial", 16, "bold")
        ).pack(pady=(15, 8))

        # ── File picker row ──
        row_file = ctk.CTkFrame(self.tab_buka, fg_color="transparent")
        row_file.pack(fill="x", padx=30)

        self.btn_browse_buka = ctk.CTkButton(
            row_file, text="📄 Browse .locked",
            command=self.pilih_file, corner_radius=8
        )
        self.btn_browse_buka.pack(side="left", expand=True, fill="x", padx=(0, 5))

        self.btn_clear_buka = ctk.CTkButton(
            row_file, text="✖", width=35,
            fg_color=CLR_DARK_BTN, hover_color=CLR_HOVER,
            command=self.clear_pilihan_buka
        )
        # Hidden until file is selected

        self.lbl_path_file = ctk.CTkLabel(
            self.tab_buka,
            text="File belum dipilih",
            text_color=CLR_MUTED, font=("Arial", 11),
            wraplength=400
        )
        self.lbl_path_file.pack(pady=(3, 10))

        # ── Password field ──
        ctk.CTkLabel(
            self.tab_buka, text="Password Brankas",
            font=("Arial", 12, "bold")
        ).pack(anchor="w", padx=35)

        row_pw2 = ctk.CTkFrame(self.tab_buka, fg_color="transparent")
        row_pw2.pack(fill="x", padx=30, pady=(0, 15))

        self.entry_pw_buka = ctk.CTkEntry(
            row_pw2, placeholder_text="Ketik password di sini...",
            show="*", height=35, corner_radius=8
        )
        self.entry_pw_buka.pack(side="left", expand=True, fill="x")
        self.entry_pw_buka.bind("<Return>", lambda e: self.proses_buka())
        self.entry_pw_buka.bind("<KeyRelease>", lambda e: self.lbl_status_buka.configure(text=""))

        ctk.CTkButton(
            row_pw2, text="👁", width=35, height=35,
            fg_color="transparent", hover_color=CLR_HOVER,
            command=self.toggle_pw_buka
        ).pack(side="right", padx=(5, 0))

        # ── Progress bar (hidden by default) ──
        self.progress_buka = ctk.CTkProgressBar(self.tab_buka, mode="indeterminate", height=6)

        # ── Action button ──
        self.btn_eksekusi_buka = ctk.CTkButton(
            self.tab_buka,
            text="BUKA BRANKAS",
            font=("Arial", 13, "bold"),
            height=42, corner_radius=10,
            fg_color="#2980B9", hover_color="#1F618D",
            command=self.proses_buka
        )
        self.btn_eksekusi_buka.pack(fill="x", padx=30, pady=(8, 6))

        self.lbl_status_buka = ctk.CTkLabel(
            self.tab_buka, text="",
            font=("Arial", 12), wraplength=400
        )
        self.lbl_status_buka.pack(pady=4)

    def toggle_pw_buka(self):
        self.show_pw_v2 = not self.show_pw_v2
        self.entry_pw_buka.configure(show="" if self.show_pw_v2 else "*")

    def clear_pilihan_buka(self):
        self.path_file_buka = None
        self.lbl_path_file.configure(text="File belum dipilih", text_color=CLR_MUTED)
        self.btn_clear_buka.pack_forget()
        self._reset_confirm_timpa()

    def pilih_file(self):
        f = filedialog.askopenfilename(filetypes=[("Locked Files", "*.locked")])
        if f:
            self.path_file_buka = f
            tampil = f if len(f) < 48 else "..." + f[-45:]
            self.lbl_path_file.configure(text=tampil, text_color=CLR_INFO)
            self.btn_clear_buka.pack(side="right", padx=(5, 0))
            self.lbl_status_buka.configure(text="")
            self._reset_confirm_timpa()

    def _reset_confirm_timpa(self):
        self.menunggu_konfirmasi_timpa = False
        self.btn_eksekusi_buka.configure(
            text="BUKA BRANKAS",
            fg_color="#2980B9", hover_color="#1F618D"
        )

    def proses_buka(self):
        force = False
        if self.menunggu_konfirmasi_timpa:
            force = True
            self._reset_confirm_timpa()

        if not self.path_file_buka:
            self.lbl_status_buka.configure(text="⚠️ Pilih file .locked dulu!", text_color=CLR_WARNING)
            return
        pw = self.entry_pw_buka.get()
        if not pw:
            self.lbl_status_buka.configure(text="⚠️ Masukkan password!", text_color=CLR_WARNING)
            return

        self._set_busy_buka(True)
        threading.Thread(
            target=self._run_buka,
            args=(self.path_file_buka, pw, force),
            daemon=True
        ).start()

    def _set_busy_buka(self, busy: bool):
        if busy:
            self.btn_eksekusi_buka.configure(state="disabled", text="⏳ Membuka...")
            self.btn_browse_buka.configure(state="disabled")
            self.progress_buka.pack(fill="x", padx=30, pady=(0, 4))
            self.progress_buka.start()
        else:
            self.progress_buka.stop()
            self.progress_buka.pack_forget()
            self.btn_eksekusi_buka.configure(state="normal")
            self.btn_browse_buka.configure(state="normal")

    def _run_buka(self, path, pw, force):
        status, msg = buka_brankas_logic(path, pw, force)
        self.after(0, lambda: self._selesai_buka(status, msg))

    def _selesai_buka(self, status, msg):
        self._set_busy_buka(False)
        if status == "SUCCESS":
            self.lbl_status_buka.configure(
                text=f"✔️ Berhasil! Folder '{msg}' kembali.",
                text_color=CLR_SUCCESS
            )
            self.entry_pw_buka.delete(0, "end")
            self.clear_pilihan_buka()
        elif status == "WRONG_PW":
            self.lbl_status_buka.configure(text="❌ Password Salah!", text_color=CLR_ERROR)
            self.btn_eksekusi_buka.configure(text="BUKA BRANKAS")
        elif status == "OVERWRITE":
            self.menunggu_konfirmasi_timpa = True
            self.btn_eksekusi_buka.configure(
                text="⚠️ KLIK LAGI UNTUK TIMPA",
                fg_color="#C0392B", hover_color="#96281B"
            )
            self.lbl_status_buka.configure(
                text=f"⚠️ Folder '{msg}' sudah ada! Timpa?",
                text_color=CLR_WARNING
            )
        else:
            self.lbl_status_buka.configure(text="❌ Error: " + msg, text_color=CLR_ERROR)