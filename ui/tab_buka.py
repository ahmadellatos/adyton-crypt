"""
ui/tab_buka.py
Frame untuk tab "Buka Brankas".
Disamakan dengan layout 2 Kolom Horizontal.
"""
import os
import threading
from tkinter import filedialog
import customtkinter as ctk

from core.vault import buka_brankas
from .dnd import DND_AVAILABLE, register_drop_file
from .theme import (
    FONT_LABEL, FONT_SMALL, FONT_BTN, FONT_BODY,
    CLR_ACCENT, CLR_ACCENT_HV, CLR_DANGER, CLR_DANGER_HV,
    CLR_INNER, CLR_BORDER, CLR_MUTED, CLR_CARD,
    CLR_CARD_HOVER, CLR_HOVER_BTN, CLR_BORDER_DRAG,
)
from .widgets import make_card, NotifBar, ProgressRow


class TabBuka(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._path_file: str | None = None
        self._show_pw          = False
        self._konfirmasi_timpa = False
        self._build()

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build(self):
        ctk.CTkLabel(
            self, text="Masukkan file .locked dan password untuk membuka",
            font=FONT_SMALL, text_color=CLR_MUTED,
        ).pack(pady=(0, 4))

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=5, pady=0)

        self.col_left = ctk.CTkFrame(container, fg_color="transparent")
        self.col_left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        self.col_right = ctk.CTkFrame(container, fg_color="transparent")
        self.col_right.pack(side="right", fill="both", expand=True, padx=(8, 0))

        self._build_card_file()
        self._build_card_password()
        self._build_action()

    def _build_card_file(self):
        self._card_file = ctk.CTkFrame(
            self.col_left, fg_color=CLR_CARD, corner_radius=10,
            border_width=2, border_color=CLR_CARD,
        )
        self._card_file.pack(fill="both", expand=True, padx=0, pady=0)

        ctk.CTkLabel(
            self._card_file, text="📄  FILE BRANKAS (.locked)",
            font=FONT_LABEL, text_color=CLR_MUTED,
        ).pack(anchor="w", padx=14, pady=(10, 6))

        row = ctk.CTkFrame(self._card_file, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 10))

        self.btn_browse = ctk.CTkButton(
            row, text="Browse  .locked",
            font=FONT_BTN, height=36, corner_radius=8,
            fg_color=CLR_ACCENT, hover_color=CLR_ACCENT_HV, text_color="#000000",
            command=self._pilih_file,
        )
        self.btn_browse.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.btn_clear = ctk.CTkButton(
            row, text="✖", width=36, height=36,
            fg_color=CLR_BORDER, hover_color=CLR_HOVER_BTN,
            font=FONT_BODY, command=self._clear_file,
        )

        hint = "File belum dipilih\n\natau seret file .locked ke sini" if DND_AVAILABLE else "File belum dipilih"
        self.lbl_path = ctk.CTkLabel(
            self._card_file, text=hint,
            font=FONT_SMALL, text_color=CLR_MUTED,
            wraplength=250, anchor="center",
            fg_color=CLR_INNER, corner_radius=8,
        )
        self.lbl_path.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self._register_dnd()

    def _register_dnd(self):
        targets = [self._card_file, self.btn_browse, self.lbl_path]
        for widget in targets:
            register_drop_file(
                widget,
                on_drop=self._on_drop_file,
                extension=".locked",
                on_enter=self._on_drag_enter,
                on_leave=self._on_drag_leave,
            )

    def _on_drag_enter(self):
        self._card_file.configure(fg_color=CLR_CARD_HOVER, border_color=CLR_BORDER_DRAG)
        if not self._path_file:
            self.lbl_path.configure(text="📄  Lepaskan file .locked di sini…", text_color=CLR_ACCENT)

    def _on_drag_leave(self):
        self._card_file.configure(fg_color=CLR_CARD, border_color=CLR_CARD)
        if not self._path_file:
            hint = "File belum dipilih\n\natau seret file .locked ke sini" if DND_AVAILABLE else "File belum dipilih"
            self.lbl_path.configure(text=hint, text_color=CLR_MUTED)

    def _on_drop_file(self, path: str):
        self._set_file(path)

    def _build_card_password(self):
        card = make_card(self.col_right, padx=0, pady=(0, 12))
        ctk.CTkLabel(
            card, text="🔑  MASUKKAN PASSWORD",
            font=FONT_LABEL, text_color=CLR_MUTED,
        ).pack(anchor="w", padx=14, pady=(10, 6))

        row_pw = ctk.CTkFrame(card, fg_color="transparent")
        row_pw.pack(fill="x", padx=14, pady=(0, 14))

        self.entry_pw = ctk.CTkEntry(
            row_pw, placeholder_text="Ketik password di sini…",
            show="*", height=36, corner_radius=8,
            fg_color=CLR_INNER, border_color=CLR_BORDER, border_width=1,
        )
        self.entry_pw.pack(side="left", expand=True, fill="x")
        self.entry_pw.bind("<Return>", lambda _: self._proses())
        self.entry_pw.bind("<KeyRelease>", self._on_pw_change)

        ctk.CTkButton(
            row_pw, text="👁", width=36, height=36,
            fg_color="transparent", hover_color=CLR_CARD,
            command=self._toggle_pw,
        ).pack(side="right", padx=(6, 0))

    def _build_action(self):
        # FIX: konsisten dengan tab_kunci — bungkus dalam action_frame
        # dan pin ke bawah kolom kanan via side="bottom".
        self.action_frame = ctk.CTkFrame(self.col_right, fg_color="transparent")
        self.action_frame.pack(side="bottom", fill="x")

        # _progress dibuat sebagai child action_frame tapi tidak di-pack dulu.
        # Akan di-pack oleh _set_busy(True) dengan before=btn_aksi.
        self._progress = ProgressRow(self.action_frame, accent_color=CLR_ACCENT)

        self.btn_aksi = ctk.CTkButton(
            self.action_frame, text="BUKA BRANKAS",
            font=FONT_BTN, height=42, corner_radius=10,
            fg_color=CLR_ACCENT, hover_color=CLR_ACCENT_HV, text_color="#000000",
            command=self._proses, state="disabled",
        )
        self.btn_aksi.pack(fill="x", padx=0, pady=(2, 6))

        self.notif = NotifBar(self.action_frame)
        self.notif.pack(fill="x", padx=0, ipady=4)

    # ── Controls ──────────────────────────────────────────────────────────────

    def _toggle_pw(self):
        self._show_pw = not self._show_pw
        self.entry_pw.configure(show="" if self._show_pw else "*")

    def _on_pw_change(self, _=None):
        """Dipanggil tiap KeyRelease — clear notif dan re-validate state."""
        self.notif.clear()
        self._validate_state()

    def _validate_state(self):
        """Disable tombol BUKA BRANKAS sampai file dipilih dan password diisi."""
        ada_file = self._path_file is not None
        ada_pw   = bool(self.entry_pw.get())
        state    = "normal" if (ada_file and ada_pw) else "disabled"
        # Jangan override state saat sedang menunggu konfirmasi timpa
        if not self._konfirmasi_timpa:
            self.btn_aksi.configure(state=state)

    def _set_file(self, path: str):
        self._path_file = path
        tampil = path if len(path) < 40 else "…" + path[-37:]
        self.lbl_path.configure(text=tampil, text_color=CLR_ACCENT)
        self.btn_clear.pack(side="right", padx=(6, 0))
        self.notif.clear()
        self._reset_timpa()
        self._validate_state()

    def _pilih_file(self):
        f = filedialog.askopenfilename(filetypes=[("Locked Files", "*.locked")])
        if f:
            self._set_file(f)

    def _clear_file(self):
        self._path_file = None
        hint = "File belum dipilih\n\natau seret file .locked ke sini" if DND_AVAILABLE else "File belum dipilih"
        self.lbl_path.configure(text=hint, text_color=CLR_MUTED)
        self.btn_clear.pack_forget()
        self._reset_timpa()
        self._validate_state()

    def _reset_timpa(self):
        self._konfirmasi_timpa = False
        self.btn_aksi.configure(
            text="BUKA BRANKAS",
            fg_color=CLR_ACCENT, hover_color=CLR_ACCENT_HV, text_color="#000000",
        )

    # ── Process ───────────────────────────────────────────────────────────────

    def _proses(self):
        force = False
        if self._konfirmasi_timpa:
            force = True
            self._reset_timpa()

        if not self._path_file:
            return self.notif.show("warn", "⚠  Pilih file .locked dulu!", auto_hide_ms=5000)
        pw = self.entry_pw.get()
        if not pw:
            return self.notif.show("warn", "⚠  Masukkan password!", auto_hide_ms=5000)

        snap_path = self._path_file
        cb        = self._progress.make_callback(self)
        self._set_busy(True)

        def _tugas():
            result = buka_brankas(snap_path, pw, force, progress_cb=cb)
            self.after(0, lambda: self._on_selesai(*result))

        threading.Thread(target=_tugas, daemon=True).start()

    def _set_busy(self, busy: bool):
        if busy:
            self._progress.reset()
            self._progress.pack(fill="x", padx=0, pady=(0, 4), before=self.btn_aksi)
            self.btn_aksi.configure(state="disabled", text="⏳  Membuka…")
            self.btn_browse.configure(state="disabled")
        else:
            self._progress.pack_forget()
            # FIX: reset teks tombol di sini agar tidak stuck "⏳ Membuka…"
            # pada kasus ERROR yang tidak set teks secara eksplisit.
            self.btn_aksi.configure(text="BUKA BRANKAS")
            self.btn_browse.configure(state="normal")
            # Re-validate agar state tombol akurat setelah proses selesai
            self._validate_state()

    def _on_selesai(self, status: str, msg: str | None):
        self._set_busy(False)

        if status == "SUCCESS":
            # Tentukan label yang akurat: cek apakah hasil ekstraksi folder atau file
            base_dir    = os.path.dirname(self._path_file or "")
            path_hasil  = os.path.join(base_dir, msg or "")
            label       = "Folder" if os.path.isdir(path_hasil) else "File"
            # FIX: konsisten dengan tab_kunci — auto_hide_ms=6000
            self.notif.show("ok", f"✔  {label} '{msg}' berhasil dikembalikan!", auto_hide_ms=6000)
            self.entry_pw.delete(0, "end")
            self._clear_file()

        elif status == "WRONG_PW":
            # Tidak pakai auto_hide — user perlu tahu kenapa gagal.
            # Notif hilang saat user mulai ngetik ulang (_on_pw_change → notif.clear()).
            self.notif.show("err", "✖  Password salah! Coba lagi.")
            # _set_busy sudah reset teks dan validate state, tidak perlu lagi di sini

        elif status == "OVERWRITE":
            self._konfirmasi_timpa = True
            self.btn_aksi.configure(
                text="⚠  KLIK LAGI UNTUK TIMPA",
                fg_color=CLR_DANGER, hover_color=CLR_DANGER_HV, text_color="#FFFFFF",
                state="normal",
            )
            self.notif.show("warn", f"⚠  '{msg}' sudah ada! Klik tombol lagi untuk menimpa.")

        else:
            self.notif.show("err", f"✖  Error: {msg}", auto_hide_ms=8000)