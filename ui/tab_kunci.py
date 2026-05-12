"""
ui/tab_kunci.py
Frame untuk tab "Kunci Folder".
Menggunakan layout 2 Kolom Horizontal.
"""
import os
import threading
from tkinter import filedialog
import customtkinter as ctk

from core.vault import kunci_brankas
from .dnd import DND_AVAILABLE, register_drop_multiple
from .theme import (
    FONT_LABEL, FONT_SMALL, FONT_BTN, FONT_BODY,
    CLR_ACCENT, CLR_ACCENT_HV, CLR_DANGER, CLR_DANGER_HV,
    CLR_INNER, CLR_BORDER, CLR_MUTED, CLR_CARD, CLR_BG,
    CLR_CARD_HOVER, CLR_HOVER_BTN, CLR_MATCH_OK, CLR_MATCH_ERR,
    STRENGTH_COLORS, STRENGTH_LABELS,
)
from .widgets import pw_strength, make_card, NotifBar, ProgressRow

CLR_BORDER_DRAG = CLR_ACCENT


class TabKunci(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._paths: list[str] = []
        self._show_pw   = False
        self._var_hapus = ctk.BooleanVar(value=False)
        self._build()

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=5, pady=0)

        self.col_left = ctk.CTkFrame(container, fg_color="transparent")
        self.col_left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        self.col_right = ctk.CTkFrame(container, fg_color="transparent")
        self.col_right.pack(side="right", fill="both", expand=True, padx=(8, 0))

        self._build_card_target()
        self._build_card_password()
        self._build_action()

    def _build_card_target(self):
        self._card_folder = ctk.CTkFrame(
            self.col_left, fg_color=CLR_CARD, corner_radius=10,
            border_width=2, border_color=CLR_CARD,
        )
        self._card_folder.pack(fill="both", expand=True, padx=0, pady=0)

        hdr_row = ctk.CTkFrame(self._card_folder, fg_color="transparent")
        hdr_row.pack(fill="x", padx=14, pady=(10, 6))

        ctk.CTkLabel(
            hdr_row, text="📁  DAFTAR TARGET", font=FONT_LABEL, text_color=CLR_MUTED
        ).pack(side="left")

        self.opt_add = ctk.CTkOptionMenu(
            hdr_row, values=["📄 File", "📁 Folder"],
            font=FONT_LABEL,
            width=100, height=28, corner_radius=6,
            fg_color=CLR_HOVER_BTN, button_color=CLR_HOVER_BTN,
            button_hover_color=CLR_BORDER, text_color="#FFFFFF",
            dropdown_font=FONT_BODY, dropdown_fg_color=CLR_CARD,
            dropdown_hover_color=CLR_ACCENT, dropdown_text_color="#FFFFFF",
            command=self._on_option_select,
        )
        self.opt_add.set("+ Tambah")
        self.opt_add.pack(side="right")

        self.list_frame = ctk.CTkScrollableFrame(
            self._card_folder, fg_color=CLR_INNER, corner_radius=8
        )
        self.list_frame.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        self._render_list()

        self.chk_hapus = ctk.CTkCheckBox(
            self._card_folder,
            text="Hapus file/folder asli setelah dikunci",
            font=FONT_SMALL, text_color=CLR_MUTED, variable=self._var_hapus,
            fg_color=CLR_DANGER, hover_color=CLR_DANGER_HV,
            corner_radius=4, checkbox_width=18, checkbox_height=18,
        )
        self.chk_hapus.pack(anchor="w", padx=14, pady=(0, 12))
        self._register_dnd()

    def _register_dnd(self):
        targets = [self._card_folder, self.list_frame, self.chk_hapus]
        for widget in targets:
            register_drop_multiple(
                widget,
                on_drop=self._on_drop_multiple,
                on_enter=self._on_drag_enter,
                on_leave=self._on_drag_leave,
            )

    def _on_drag_enter(self):
        self._card_folder.configure(fg_color=CLR_CARD_HOVER, border_color=CLR_BORDER_DRAG)

    def _on_drag_leave(self):
        self._card_folder.configure(fg_color=CLR_CARD, border_color=CLR_CARD)

    def _on_drop_multiple(self, paths: list[str]):
        self._add_paths(paths)

    def _build_card_password(self):
        card = make_card(self.col_right, padx=0, pady=(0, 12))
        ctk.CTkLabel(
            card, text="🔑  BUAT PASSWORD", font=FONT_LABEL, text_color=CLR_MUTED
        ).pack(anchor="w", padx=14, pady=(8, 4))

        self._row_pw = ctk.CTkFrame(card, fg_color="transparent")
        self._row_pw.pack(fill="x", padx=14)

        self.entry_pw = ctk.CTkEntry(
            self._row_pw, placeholder_text="Buat password kuat…",
            show="*", height=34, corner_radius=8,
            fg_color=CLR_INNER, border_color=CLR_BORDER, border_width=1,
        )
        self.entry_pw.pack(side="left", expand=True, fill="x")
        self.entry_pw.bind("<KeyRelease>", self._on_pw_change)

        ctk.CTkButton(
            self._row_pw, text="👁", width=34, height=34,
            fg_color="transparent", hover_color=CLR_CARD,
            command=self._toggle_pw,
        ).pack(side="right", padx=(6, 0))

        # Wadah indikator strength — tinggi dikunci, tidak resize layout
        self._row_str = ctk.CTkFrame(card, fg_color="transparent", height=20)
        self._row_str.pack_propagate(False)
        self._row_str.pack(fill="x", padx=14, pady=(2, 0))

        self._strength_bar = ctk.CTkProgressBar(self._row_str, height=5, corner_radius=3)
        self._strength_bar.pack(side="left", expand=True, fill="x", padx=(0, 8))

        self._lbl_strength = ctk.CTkLabel(
            self._row_str, text="", width=90,
            font=FONT_SMALL, text_color=CLR_CARD, anchor="e",
        )
        self._lbl_strength.pack(side="right")

        self._hide_indicator()

        ctk.CTkLabel(
            card, text="Konfirmasi Password", font=FONT_SMALL, text_color=CLR_MUTED
        ).pack(anchor="w", padx=14, pady=(2, 2))

        self.entry_pw_confirm = ctk.CTkEntry(
            card, placeholder_text="Ulangi password…",
            show="*", height=34, corner_radius=8,
            fg_color=CLR_INNER, border_color=CLR_BORDER, border_width=1,
        )
        self.entry_pw_confirm.pack(fill="x", padx=14)
        self.entry_pw_confirm.bind("<KeyRelease>", self._on_confirm_change)
        self.entry_pw_confirm.bind("<Return>", lambda _: self._proses())

        self._lbl_match = ctk.CTkLabel(card, text="", font=FONT_SMALL, anchor="e", height=14)
        self._lbl_match.pack(anchor="e", padx=14, pady=(2, 6))

    def _hide_indicator(self):
        """Samarkan indikator dengan warna background card."""
        self._strength_bar.set(0)
        self._strength_bar.configure(fg_color=CLR_CARD, progress_color=CLR_CARD)
        self._lbl_strength.configure(text="")

    def _show_indicator(self, s: int):
        """Tampilkan indikator dengan warna sesuai level kekuatan."""
        self._strength_bar.configure(fg_color=CLR_INNER, progress_color=STRENGTH_COLORS[s])
        self._strength_bar.set((s + 1) / 4)
        self._lbl_strength.configure(text=STRENGTH_LABELS[s], text_color=STRENGTH_COLORS[s])

    def _build_action(self):
        self.action_frame = ctk.CTkFrame(self.col_right, fg_color="transparent")
        self.action_frame.pack(side="bottom", fill="x")

        self._progress = ProgressRow(self.action_frame, accent_color=CLR_ACCENT)

        self.btn_aksi = ctk.CTkButton(
            self.action_frame, text="KUNCI SEKARANG",
            font=FONT_BTN, height=42, corner_radius=10,
            fg_color=CLR_ACCENT, hover_color=CLR_ACCENT_HV, text_color="#000000",
            command=self._proses, state="disabled",
        )
        self.btn_aksi.pack(fill="x", padx=0, pady=(2, 6))

        self.notif = NotifBar(self.action_frame)
        self.notif.pack(fill="x", padx=0, ipady=4)

    # ── Controls ──────────────────────────────────────────────────────────────

    def _on_option_select(self, choice: str):
        if choice == "📄 File":
            self._pilih_file()
        elif choice == "📁 Folder":
            self._pilih_folder()
        self.opt_add.set("+ Tambah")

    def _pilih_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self._add_paths([folder])

    def _pilih_file(self):
        files = filedialog.askopenfilenames()
        if files:
            self._add_paths(list(files))

    def _add_paths(self, new_paths: list[str]):
        for p in new_paths:
            if p not in self._paths:
                self._paths.append(p)
        self._render_list()
        self.notif.clear()

    def _remove_path(self, path: str):
        if path in self._paths:
            self._paths.remove(path)
            self._render_list()

    def _render_list(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        if not self._paths:
            teks = "Belum ada item\n\nSeret ke sini" if DND_AVAILABLE else "Belum ada item ditambahkan"
            ctk.CTkLabel(
                self.list_frame, text=teks,
                text_color=CLR_MUTED, font=FONT_SMALL,
            ).pack(pady=40)
            self._validate_state()
            return

        for p in self._paths:
            row = ctk.CTkFrame(self.list_frame, fg_color=CLR_BG, corner_radius=4)
            row.pack(fill="x", pady=2, padx=2)

            ikon = "📁" if os.path.isdir(p) else "📄"
            ctk.CTkLabel(
                row, text=f"{ikon}  {os.path.basename(p)}",
                font=FONT_BODY, anchor="w",
            ).pack(side="left", padx=8, pady=4)

            ctk.CTkButton(
                row, text="✕", width=24, height=24,
                fg_color="transparent", text_color=CLR_DANGER,
                hover_color=CLR_HOVER_BTN,
                command=lambda pt=p: self._remove_path(pt),
            ).pack(side="right", padx=4)

        self._validate_state()

    def _validate_state(self):
        if not hasattr(self, "entry_pw") or not hasattr(self, "btn_aksi"):
            return
        pw1, pw2  = self.entry_pw.get(), self.entry_pw_confirm.get()
        ada_file  = len(self._paths) > 0
        pw_valid  = bool(pw1) and (pw1 == pw2)
        state     = "normal" if (ada_file and pw_valid) else "disabled"
        self.btn_aksi.configure(state=state)

    def _on_pw_change(self, _=None):
        pw = self.entry_pw.get()
        s  = pw_strength(pw)
        if s < 0:
            self._hide_indicator()
        else:
            self._show_indicator(s)
        self._on_confirm_change()
        self.notif.clear()

    def _on_confirm_change(self, _=None):
        pw1, pw2 = self.entry_pw.get(), self.entry_pw_confirm.get()
        if not pw2:
            self._lbl_match.configure(text="")
        elif pw1 == pw2:
            self._lbl_match.configure(text="✔  Cocok", text_color=CLR_MATCH_OK)
        else:
            self._lbl_match.configure(text="✖  Belum cocok", text_color=CLR_MATCH_ERR)
        self._validate_state()

    def _toggle_pw(self):
        self._show_pw = not self._show_pw
        c = "" if self._show_pw else "*"
        self.entry_pw.configure(show=c)
        self.entry_pw_confirm.configure(show=c)

    # ── Process ───────────────────────────────────────────────────────────────

    def _proses(self):
        if not self._paths:
            return self.notif.show("warn", "⚠ Tambahkan file/folder dulu.", auto_hide_ms=5000)
        pw, pw2 = self.entry_pw.get(), self.entry_pw_confirm.get()
        if not pw:
            return self.notif.show("warn", "⚠  Password tidak boleh kosong!", auto_hide_ms=5000)
        if pw != pw2:
            return self.notif.show("warn", "⚠  Password tidak cocok!", auto_hide_ms=5000)

        default_name = os.path.basename(self._paths[0]) or "Brankas_Rahasia"
        path_simpan  = filedialog.asksaveasfilename(
            title="Simpan Brankas Sebagai...",
            initialfile=f"{default_name}.locked",
            defaultextension=".locked",
            filetypes=[("Digital Locker Archive", "*.locked"), ("All Files", "*.*")],
        )
        if not path_simpan:
            return

        snap_paths = list(self._paths)
        snap_hapus = self._var_hapus.get()
        cb         = self._progress.make_callback(self)
        self._set_busy(True)

        def _tugas():
            result = kunci_brankas(snap_paths, path_simpan, pw, snap_hapus, progress_cb=cb)
            self.after(0, lambda: self._on_selesai(*result))

        threading.Thread(target=_tugas, daemon=True).start()

    def _set_busy(self, busy: bool):
        if busy:
            self._progress.reset()
            self._progress.pack(fill="x", padx=0, pady=(0, 4), before=self.btn_aksi)
            self.btn_aksi.configure(state="disabled", text="⏳  Mengunci Brankas…")
            self.opt_add.configure(state="disabled")
            self.chk_hapus.configure(state="disabled")
        else:
            self._progress.pack_forget()
            self.btn_aksi.configure(state="normal", text="KUNCI SEKARANG")
            self.opt_add.configure(state="normal")
            self.chk_hapus.configure(state="normal")

    def _on_selesai(self, sukses: bool, pesan: str):
        self._set_busy(False)
        if sukses:
            self.notif.show("ok", "✔  " + pesan, auto_hide_ms=6000)
            self.entry_pw.delete(0, "end")
            self.entry_pw_confirm.delete(0, "end")
            self._lbl_match.configure(text="")
            self._hide_indicator()
            self._var_hapus.set(False)
            self._paths.clear()
            self._render_list()
        else:
            self.notif.show("err", "✖  " + pesan, auto_hide_ms=5000)